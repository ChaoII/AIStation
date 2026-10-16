#!/usr/bin/env python3
"""为 skillhub 精选的 200 个技能用 Qwen 生成真实、独特、契合技能的图标。

skillhub 的 iconUrl 对很多技能返回的是「通用占位图」（黑底 skill logo / 抽象图案），
且大量技能共用同一张，导致市场里图标重复、无意义。此脚本用 LLM 从技能名/分类/简介
派生「图形符号 + 渐变配色」，再用 Qwen-Image-2.1 生成扁平 App 图标，覆盖替换占位 PNG，
并把原本无 iconUrl 而回退成分类 emoji 的技能补成真实图标。

用法（后端根目录）：
    .venv/Scripts/python.exe scripts/gen_skillhub_icons.py                 # 全量 200
    .venv/Scripts/python.exe scripts/gen_skillhub_icons.py --only word-docx-1,健身...  # 试点
    .venv/Scripts/python.exe scripts/gen_skillhub_icons.py --force         # 强制覆盖已存在

输出：frontend/public/market-icons/skillhub-<slug>.png（1024 生成后缩到 256）。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.plugin.module_ai.market.skillhub_skills import SKILLHUB_SKILLS  # noqa: E402

BASE_URL = os.environ.get("QWEN_BASE_URL", "http://llm.bsh-tech.com:8086/v1")
API_KEY = os.environ.get(
    "QWEN_API_KEY", "sk-5m3fKeqyWTko99yCUD85FMXRFKenoIXr50NJ85kaqnfPMe8r"
)
IMG_MODEL = os.environ.get("QWEN_IMAGE_MODEL", "smbs/Image-2.1")
TEXT_MODEL = os.environ.get("QWEN_TEXT_MODEL", "smbs/LLM-284B-MXFP4")

OUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "market-icons")
)
DATA_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "plugin", "module_ai", "market", "skillhub_skills.py")
)

STYLE = (
    "flat vector app icon, rounded square tile, {bg} gradient background, "
    "centered single bold white {symbol} glyph, minimal, crisp clean edges, "
    "soft inner glow, high contrast, modern product logo style, 1:1"
)
NEGATIVE = "text, letters, words, numbers, watermark, photo, realistic, 3d clutter, multiple objects, frame, border"

# 分类兜底：LLM 失败时用分类默认「符号 + 渐变」，保证仍能生成
CATEGORY_STYLE: dict[str, tuple[str, str]] = {
    "办公效率": ("indigo to violet", "document page with a pen"),
    "开发编程": ("slate to indigo", "code brackets"),
    "内容创作": ("violet to pink", "paint brush with a spark"),
    "数据分析": ("cyan to blue", "bar chart with a magnifier"),
    "行业专业": ("amber to orange", "shield with a check mark"),
    "生活服务": ("emerald to teal", "leaf"),
    "AI Agent": ("blue to cyan", "chip with sparkles"),
}
DEFAULT_BG = "blue to indigo"
DEFAULT_SYM = "abstract spark"

# 个别技能 LLM 派生多次失败、回退到通用兜底符号，手工指定更契合的 (符号, 渐变)
OVERRIDES: dict[str, tuple[str, str]] = {
    "llx": ("一张页面与提炼出的摘要卡片叠加，卡片由多条概括横线构成", "sky blue to indigo"),
    "sglk666": ("红笔批改的作文纸，旁边升起评分等级条", "rose to orange"),
    "drug-regulatory-affairs": ("一粒胶囊与叠放的法规文件", "teal to cyan"),
    "home-renovation-new": ("房屋轮廓内叠加卷尺与清单勾选", "amber to orange"),
}


def _shrink(png_bytes: bytes, size: int = 256) -> bytes:
    """等比缩放到 size×size（PIL 可用时）。"""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return png_bytes


COLOR_WORDS = {
    "indigo", "violet", "blue", "cyan", "teal", "green", "emerald", "amber",
    "orange", "red", "rose", "pink", "purple", "slate", "gray", "grey",
    "fuchsia", "sky", "lime", "magenta", "yellow", "navy", "aqua",
}


def _is_color(s: str) -> bool:
    """判断字符串是否更像「渐变/颜色」描述而非图形符号。"""
    s = s.lower()
    return (" to " in s) or (sum(1 for w in COLOR_WORDS if w in s) >= 2)


def _normalize(sym: str, bg: str) -> tuple[str, str]:
    """LLM 可能把颜色填进 symbol、图形填进 bg；统一成 (图形符号, 渐变)."""
    if _is_color(sym) and not _is_color(bg):
        return bg, sym  # 交换
    return sym, bg


def llm_derive(client: OpenAI, name: str, category: str, description: str, avoid: str = "") -> tuple[str, str]:
    """用 LLM 从技能名/分类/简介派生「图形符号 + 渐变配色」，失败回退分类默认。

    符号为纯图形、能体现该技能的独特主题（参考简介），避免通用分类符号。
    avoid：若提供，要求生成的符号与它不同（用于去重）。
    """
    prompt = (
        "你是扁平 App 图标设计师。为一个技能卡片设计图标，给出一个纯图形白色符号与背景渐变。\n"
        f"技能名：{name}\n"
        f"分类：{category}\n"
        f"简介：{description[:220]}\n"
        "要求：\n"
        "- 符号只用非文字图形（禁止字母/数字/文字），必须体现该技能的**独特主题**（结合简介的具体内容），"
        "不要用过于通用的分类符号（如 shield/check/星星）；\n"
        "- 背景给一个具体渐变描述（如 indigo to violet、emerald to teal）；\n"
        '只输出一行 JSON：{"symbol":"图形描述","bg":"渐变描述"}'
    )
    if avoid:
        prompt += (
            f"\n⚠️ 注意：其它技能已经使用了符号「{avoid}」。请**完全避开**它，"
            "选择一个与之**截然不同**、更能体现该技能独特处理对象的图形符号。"
        )
    # 284B 为推理模型：推理耗尽 max_tokens 会导致 content=None 或 JSON 截断，需放宽 token 并重试
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1200,
            )
            txt = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if m and '"symbol"' in txt and '"bg"' in txt:
                try:
                    obj = json.loads(m.group(0))
                except json.JSONDecodeError:
                    # JSON 被截断（finish=length），尝试补全：取到最后一个 `}` 为止
                    obj = None
                if obj is None:
                    txt2 = txt.strip()
                    last = txt2.rfind("}")
                    if last != -1:
                        try:
                            obj = json.loads(txt2[: last + 1])
                        except json.JSONDecodeError:
                            obj = None
                if obj is None:
                    # 尝试补全缺失的引号/括号
                    fixed = txt2
                    if not fixed.rstrip().endswith("}"):
                        fixed += '"}'
                    try:
                        obj = json.loads(fixed)
                    except json.JSONDecodeError:
                        obj = None
                if obj:
                    sym = (obj.get("symbol") or "").strip()
                    bg = (obj.get("bg") or "").strip()
                    if sym and bg:
                        return _normalize(sym, bg)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ 派生失败（{exc}），重试 {attempt + 1}/3")
    # 重试耗尽，回退分类默认
    cat_bg, cat_sym = CATEGORY_STYLE.get(category, (DEFAULT_BG, DEFAULT_SYM))
    return cat_sym, cat_bg


def _slug(skill: dict) -> str:
    return skill.get("source_slug") or skill["key"].replace("skillhub-", "")


def gen_one(client: OpenAI, skill: dict, force: bool, avoid: str = "") -> tuple[str, str, str, str]:
    """生成一张图标，返回 (slug, shape, color, status)。avoid 为需避免的符号提示。"""
    slug = _slug(skill)
    out_path = os.path.join(OUT_DIR, f"skillhub-{slug}.png")
    if os.path.exists(out_path) and not force:
        return slug, "", "", "skip(exists)"
    if slug in OVERRIDES:
        shape, color = OVERRIDES[slug]
    else:
        shape, color = llm_derive(client, skill["name"], skill.get("category", ""), skill.get("description", ""), avoid=avoid)
    prompt = STYLE.format(bg=color, symbol=shape)
    try:
        resp = client.images.generate(
            model=IMG_MODEL,
            prompt=prompt,
            size="1024x1024",
            n=1,
            response_format="b64_json",
            extra_body={"negative_prompt": NEGATIVE},
        )
    except Exception as exc:  # noqa: BLE001
        return slug, shape, color, f"fail(image): {type(exc).__name__}: {exc}"
    raw = base64.b64decode(resp.data[0].b64_json)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(_shrink(raw))
    return slug, shape, color, f"ok({shape[:26]!r})"


def rewrite_data_file(skills: list[dict]) -> None:
    """把 emoji 兜底的 icon 更新为 market-icons 路径，并重写数据文件。"""
    changed = 0
    for s in skills:
        icon = s.get("icon", "")
        if not (isinstance(icon, str) and icon.startswith("market-icons/")):
            slug = s.get("source_slug") or s["key"].replace("skillhub-", "")
            s["icon"] = f"market-icons/skillhub-{slug}.png"
            changed += 1
    if changed:
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
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"✅ 已更新数据文件 icon（{changed} 个 emoji → market-icons 路径）→ {DATA_FILE}")
    else:
        print("ℹ️ 数据文件 icon 均已为 market-icons 路径，无需改动")


def run_batch(client: OpenAI, targets: list[dict], force: bool, concurrency: int, avoid_map: dict) -> dict:
    """生成一批，返回 {slug: (shape,color,status)}。"""
    results: dict[str, tuple[str, str, str]] = {}
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(gen_one, client, s, force, avoid_map.get(_slug(s), "")): s for s in targets}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                got, shape, color, msg = fut.result()
                results[got] = (shape, color, msg)
                if msg.startswith("ok") or msg.startswith("skip"):
                    ok += 1
                    print(f"[OK] {got}: {msg}", flush=True)
                else:
                    fail += 1
                    print(f"[FAIL] {got}: {msg}", file=sys.stderr, flush=True)
            except Exception as exc:  # noqa: BLE001
                slug = _slug(s)
                fail += 1
                print(f"[FAIL] {slug}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
    print(f"本批：成功 {ok}，失败 {fail}", flush=True)
    return results


def dedupe_pass(client: OpenAI, targets: list[dict], results: dict, concurrency: int) -> tuple[dict, int]:
    """找出「符号+配色」完全重复的技能，用 avoid 重新生成差异化；返回 (更新后results, 命中数)。"""
    first: dict[tuple[str, str], str] = {}
    dup: list[str] = []
    for slug, (shape, color, _status) in results.items():
        if not shape:
            continue
        key = (shape, color)
        if key in first:
            dup.append(slug)
        else:
            first[key] = slug
    if not dup:
        return results, 0
    dup_set = set(dup)
    avoid_map = {slug: results[slug][0] for slug in dup}
    re_targets = [s for s in targets if _slug(s) in dup_set]
    print(f"发现 {len(dup)} 个符号+配色重复，重新生成差异化图标…", flush=True)
    new_res = run_batch(client, re_targets, True, concurrency, avoid_map)
    for slug, val in new_res.items():
        results[slug] = val
    return results, len(dup)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--only", default="", help="逗号分隔的 slug 列表，仅生成这些")
    p.add_argument("--force", action="store_true", help="强制覆盖已存在的 PNG")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--max-dedupe", type=int, default=3, help="去重重生成最大轮数")
    args = p.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    targets = [s for s in SKILLHUB_SKILLS if not only or (s.get("source_slug") in only)]
    if not targets:
        print("⚠️ 没有匹配的技能")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    print(f"目标 {len(targets)} 张 → {OUT_DIR}", flush=True)

    results = run_batch(client, targets, args.force, args.concurrency, {})
    for _ in range(args.max_dedupe):
        results, n = dedupe_pass(client, targets, results, args.concurrency)
        if n == 0:
            break

    ok_count = sum(
        1
        for s in targets
        if os.path.exists(os.path.join(OUT_DIR, f"skillhub-{_slug(s)}.png"))
    )
    print(f"完成：已产出文件 {ok_count}/{len(targets)}", flush=True)
    # 仅全量生成（非 --only）且全部产出时，才把 emoji 兜底 icon 更新为 PNG 路径
    if not args.only and ok_count == len(targets):
        rewrite_data_file(SKILLHUB_SKILLS)


if __name__ == "__main__":
    main()
