#!/usr/bin/env python3
"""为智能体（ai_agents）用 Qwen 生成真实、各不相同、契合的图标。

智能体当前用「首字母彩色圆」当头像（ag.avatar 未使用）。本脚本用 LLM 从
智能体名/角色/能力派生「图形符号 + 渐变配色」，再用 Qwen-Image-2.1 生成扁平
App 图标，输出到 frontend/public/agent-icons/<id>.png，并把 ai_agents.avatar
回写为 "agent-icons/<id>.png"，前端卡片/对话用 IconTile 展示。

用法（后端根目录）：
    .venv/Scripts/python.exe scripts/gen_agent_icons.py            # 全量（无 avatar 的）
    .venv/Scripts/python.exe scripts/gen_agent_icons.py --only 1  # 试点
    .venv/Scripts/python.exe scripts/gen_agent_icons.py --force   # 强制覆盖
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys

import psycopg
from openai import OpenAI

# ---- dev 库（backend/env/.env.dev）----
DB = dict(
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "root"),
    password=os.environ.get("DB_PASSWORD", "ServBay.dev"),
    dbname=os.environ.get("DB_NAME", "aistation"),
)

BASE_URL = os.environ.get("QWEN_BASE_URL", "http://llm.bsh-tech.com:8086/v1")
API_KEY = os.environ.get(
    "QWEN_API_KEY", "sk-5m3fKeqyWTko99yCUD85FMXRFKenoIXr50NJ85kaqnfPMe8r"
)
IMG_MODEL = os.environ.get("QWEN_IMAGE_MODEL", "smbs/Image-2.1")
TEXT_MODEL = os.environ.get("QWEN_TEXT_MODEL", "smbs/LLM-284B-MXFP4")

OUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "agent-icons")
)

STYLE = (
    "flat vector app icon, rounded square tile, {bg} gradient background, "
    "centered single bold white {symbol} glyph, minimal, crisp clean edges, "
    "soft inner glow, high contrast, modern product logo style, 1:1"
)
NEGATIVE = "text, letters, words, numbers, watermark, photo, realistic, 3d clutter, multiple objects, frame, border"

DEFAULT_BG = "blue to indigo"
DEFAULT_SYM = "abstract spark"

COLOR_WORDS = {
    "indigo", "violet", "blue", "cyan", "teal", "green", "emerald", "amber",
    "orange", "red", "rose", "pink", "purple", "slate", "gray", "grey",
    "fuchsia", "sky", "lime", "magenta", "yellow", "navy", "aqua",
}


def _is_color(s: str) -> bool:
    s = (s or "").lower()
    return (" to " in s) or (sum(1 for w in COLOR_WORDS if w in s) >= 2)


def _normalize(sym: str, bg: str) -> tuple[str, str]:
    if _is_color(sym) and not _is_color(bg):
        return bg, sym
    return sym, bg


def _shrink(png_bytes: bytes, size: int = 256) -> bytes:
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return png_bytes


def llm_derive(client: OpenAI, name: str, category: str, description: str) -> tuple[str, str]:
    prompt = (
        "你是扁平 App 图标设计师。为一个 AI 智能体设计图标，给出一个纯图形白色符号与背景渐变。\n"
        f"智能体名：{name}\n"
        f"分类：{category or '通用'}\n"
        f"角色/能力：{description[:220]}\n"
        "要求：\n"
        "- 符号只用非文字图形（禁止字母/数字/文字），必须体现该智能体的**独特主题**（结合角色/能力），"
        "不要用过于通用的分类符号（如 shield/check/星星）；\n"
        "- 背景给一个具体渐变描述（如 indigo to violet、emerald to teal）；\n"
        '只输出一行 JSON：{"symbol":"图形描述","bg":"渐变描述"}'
    )
    for _ in range(3):
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
                    obj = None
                if obj is None:
                    txt2 = txt.strip()
                    last = txt2.rfind("}")
                    if last != -1:
                        try:
                            obj = json.loads(txt2[: last + 1])
                        except json.JSONDecodeError:
                            obj = None
                if obj:
                    sym = (obj.get("symbol") or "").strip()
                    bg = (obj.get("bg") or "").strip()
                    if sym and bg:
                        return _normalize(sym, bg)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ 派生失败（{exc}），重试", flush=True)
    return DEFAULT_SYM, DEFAULT_BG


def gen_one(client: OpenAI, agent: dict, force: bool) -> str:
    aid = agent["id"]
    out_path = os.path.join(OUT_DIR, f"{aid}.png")
    if os.path.exists(out_path) and not force:
        return f"skip(exists {aid}.png)"
    symbol, color = llm_derive(
        client, agent["name"], agent.get("category", ""), agent.get("role", "")
    )
    prompt = STYLE.format(bg=color, symbol=symbol)
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
        return f"fail(image): {type(exc).__name__}: {exc}"
    raw = base64.b64decode(resp.data[0].b64_json)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(_shrink(raw))
    return f"ok({symbol[:24]!r})"


def load_agents(only: set[int]) -> list[dict]:
    conn = psycopg.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT a.id, a.agent_name, a.agent_role, a.avatar, COALESCE(c.name,'') "
            "FROM ai_agents a LEFT JOIN ai_agent_categories c ON c.id = a.category_id "
            "WHERE (a.avatar IS NULL OR a.avatar = '') AND a.is_deleted = false ORDER BY a.id"
        )
        rows = [
            {"id": r[0], "name": r[1], "role": r[2] or "", "avatar": r[3], "category": r[4]}
            for r in cur.fetchall()
            if not only or r[0] in only
        ]
        return rows
    finally:
        conn.close()


def write_avatar(aid: int, avatar: str) -> None:
    conn = psycopg.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE ai_agents SET avatar=%s WHERE id=%s", (avatar, aid))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--only", default="", help="逗号分隔的智能体 id，仅生成这些")
    p.add_argument("--force", action="store_true", help="强制覆盖已存在的 PNG")
    args = p.parse_args()

    only = {int(s) for s in args.only.split(",") if s.strip()}
    agents = load_agents(only)
    if not agents:
        print("ℹ️ 没有需要生成图标的智能体（全为空 avatar？用 --force 重新生成本次已生成的）")
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    print(f"目标 {len(agents)} 个智能体 → {OUT_DIR}", flush=True)

    for agent in agents:
        msg = gen_one(client, agent, args.force)
        if msg.startswith("ok"):
            avatar = f"agent-icons/{agent['id']}.png"
            write_avatar(agent["id"], avatar)
            print(f"[OK] #{agent['id']} {agent['name']}: {msg} → avatar={avatar}", flush=True)
        else:
            print(f"[WARN] #{agent['id']} {agent['name']}: {msg}", flush=True)


if __name__ == "__main__":
    main()
