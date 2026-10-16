#!/usr/bin/env python3
"""从 skillhub.cn API 精选中文/免密钥技能，固化进 ``market/skillhub_skills.py``。

用法（在后端根目录）：
    .venv/Scripts/python.exe scripts/_generate_skillhub_skills.py --limit 200

流程：
1. 分页拉 `/api/skills`（按综合分 score 降序）并筛选（有中文描述、免 API Key、非付费、非 pay-skill）；
2. 按规范化显示名去重 + 与内置 `_SKILLS` 撞名去重；
3. 逐个取详情（剔除安全报告非 benign 的）/SKILL.md，组装中文指令 content；
4. 输出 `app/plugin/module_ai/market/skillhub_skills.py`（标准库，零新增依赖）。

纯函数见 ``app/plugin/module_ai/market/skillhub_curation.py``；测试见 ``tests/test_skillhub_curation.py``。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

# 把 backend 根加入 sys.path，使 `import app` 可用（与其它 scripts 惯例一致）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugin.module_ai.market.seed import _SKILLS  # noqa: E402
from app.plugin.module_ai.market.skillhub_curation import (  # noqa: E402
    build_skill_content,
    category_emoji,
    clean_display_name,
    has_cjk,
    map_category,
)

BASE = "https://api.skillhub.cn"
UA = "aistation-skillhub-gen/1.0 (curation script)"


def _json(url: str, retries: int = 3, timeout: int = 30) -> dict:
    """GET JSON，429/5xx 指数退避重试。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001  # 网络/解析异常统一重试
            if attempt >= retries - 1:
                print(f"  ⚠️ 拉取失败（{exc}），放弃：{url}")
                return {}
            time.sleep(2**attempt)
    return {}


def _raw(url: str, retries: int = 3, timeout: int = 30) -> str:
    """GET 原始正文（SKILL.md），跟随 302，失败返回空串。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            if attempt >= retries - 1:
                print(f"  ⚠️ 拉取 SKILL.md 失败（{exc}）：{url}")
                return ""
            time.sleep(2**attempt)
    return ""


def collect_candidates(max_pages: int = 30) -> list[dict]:
    """分页拉取高分技能列表，去重页内重复 slug。"""
    out: list[dict] = []
    seen_slugs: set[str] = set()
    for page in range(1, max_pages + 1):
        q = urllib.parse.urlencode(
            {
                "labels": "requires_api_key:false",
                "sortBy": "score",
                "order": "desc",
                "pageSize": 100,
                "page": page,
            }
        )
        data = _json(f"{BASE}/api/skills?{q}")
        items = ((data or {}).get("data") or {}).get("skills") or []
        if not items:
            break
        for it in items:
            slug = it.get("slug")
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                out.append(it)
        if len(items) < 100:
            break
    return out


def is_usable(c: dict) -> bool:
    """筛选：非付费、免 API Key、有中文描述、有 slug、评分>0。"""
    if c.get("category") == "pay-skill":
        return False
    labels = c.get("labels") or {}
    if labels.get("requires_api_key") == "true":
        return False
    if labels.get("pricing_type") == "paid":
        return False
    if not has_cjk(c.get("description_zh") or ""):
        return False
    if not c.get("slug"):
        return False
    return (c.get("score") or 0) > 0


def _norm(name: str) -> str:
    return clean_display_name(name).lower()


def select_skills(candidates: list[dict]) -> list[dict]:
    """去重（规范化名保留最高分）+ 剔除与内置 `_SKILLS` 撞名，按 score 降序返回。"""
    builtin_names = {_norm(s["name"]) for s in _SKILLS}
    by_name: dict[str, dict] = {}
    for c in candidates:
        if not is_usable(c):
            continue
        disp = (c.get("namespace") or {}).get("displayName") or c.get("name") or ""
        name_key = _norm(disp)
        if not name_key or name_key in builtin_names:
            continue
        cur = by_name.get(name_key)
        if cur is None or (c.get("score") or 0) > (cur.get("score") or 0):
            by_name[name_key] = c
    return sorted(by_name.values(), key=lambda c: c.get("score") or 0, reverse=True)


def _license_from_md(md: str) -> str | None:
    m = re.search(r"^license:\s*(.+)$", md, flags=re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip() if m else None


def fetch_skill(slug: str, cand: dict, skip_risk: bool = True) -> dict | None:
    """取详情 + SKILL.md → 组装技能条目；风险/失败返回 None。"""
    detail = _json(f"{BASE}/api/v1/skills/{slug}")
    if not detail:
        return None
    skill = detail.get("skill") or {}
    if skip_risk:
        for report in (skill.get("securityReports") or {}).values():
            if (report or {}).get("status") != "benign":
                print(f"  ⚠️ 安全报告非 benign，跳过：{slug}")
                return None

    files = _json(f"{BASE}/api/v1/skills/{slug}/files")
    md_path = None
    for f in (files or {}).get("files") or []:
        if f.get("path") == "SKILL.md":
            md_path = f.get("path")
            break
    if not md_path:
        print(f"  ⚠️ 无 SKILL.md，跳过：{slug}")
        return None

    md = _raw(f"{BASE}/api/v1/skills/{slug}/file?path={md_path}")
    if not md.strip():
        md = (cand.get("description_zh") or "") or ""

    desc_zh = (cand.get("description_zh") or cand.get("description") or "").strip()
    license_name = _license_from_md(md) or skill.get("license")
    display = skill.get("displayName") or (cand.get("namespace") or {}).get("displayName") or cand.get("name") or slug
    category = map_category(cand.get("category") or "")
    tags = list((cand.get("tags") or {}).keys())[:5] + ["skillhub"]

    content = build_skill_content(source_slug=slug, description_zh=desc_zh, sk_md=md, license=license_name)
    return {
        "key": f"skillhub-{slug}",
        "name": display,
        "category": category,
        "description": desc_zh[:200],
        "tags": tags,
        "content": content,
        "featured": False,
        "icon": category_emoji(category),
        "source": "skillhub.cn",
        "source_slug": slug,
        "license": license_name,
    }


def write_data(skills: list[dict], out_path: str) -> None:
    lines = [
        "# 由 scripts/_generate_skillhub_skills.py 生成，勿手改。",
        "",
        "from __future__ import annotations",
        "",
        "# 条目结构：{key, name, category, description, tags, content, featured, icon, source, source_slug, license}",
        "SKILLHUB_SKILLS: list[dict] = [",
    ]
    for s in skills:
        lines.append("    " + repr(s) + ",")
    lines.append("]")
    dir_name = os.path.dirname(out_path)
    os.makedirs(dir_name, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"✅ 已写入 {len(skills)} 项技能 → {out_path}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="生成 skillhub 精选技能数据")
    parser.add_argument("--limit", type=int, default=200, help="目标条数（默认 200）")
    parser.add_argument("--max-pages", type=int, default=30, help="列表拉取最大页数（默认 30）")
    parser.add_argument(
        "--out",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "app",
            "plugin",
            "module_ai",
            "market",
            "skillhub_skills.py",
        ),
        help="输出路径",
    )
    args = parser.parse_args()

    print("🔄 拉取候选列表…")
    candidates = collect_candidates(args.max_pages)
    print(f"  候选 {len(candidates)} 条")
    selected = select_skills(candidates)
    print(f"  精选（去重/撞名剔除后） {len(selected)} 条")

    skills: list[dict] = []
    seen_keys: set[str] = set()
    for cand in selected:
        if len(skills) >= args.limit:
            break
        slug = cand["slug"]
        ent = fetch_skill(slug, cand)
        if ent is None or ent["key"] in seen_keys:
            continue
        seen_keys.add(ent["key"])
        skills.append(ent)
        print(f"  [{len(skills)}/{args.limit}] {ent['name']}")
        time.sleep(0.2)

    if len(skills) < args.limit:
        print(f"⚠️ 仅取到 {len(skills)} 条，未达目标 {args.limit}；可调大 --max-pages 或降低 --limit。")

    write_data(skills, args.out)


if __name__ == "__main__":
    main()
