#!/usr/bin/env python3
"""批量生成能力市场商品图标（Qwen-Image-2.1 网关，扁平 App 图标风格）。

用法：
    cd backend && .venv/Scripts/python.exe scripts/gen_market_icons.py [--only key1,key2] [--concurrency 4]

输出：frontend/public/market-icons/<key>.png（1024 生成后缩到 256，减小体积）
"""
from __future__ import annotations

import argparse
import base64
import io
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

BASE_URL = os.environ.get("QWEN_IMAGE_BASE_URL", "http://llm.bsh-tech.com:8086/v1")
API_KEY = os.environ.get(
    "QWEN_IMAGE_API_KEY", "sk-5m3fKeqyWTko99yCUD85FMXRFKenoIXr50NJ85kaqnfPMe8r"
)
MODEL = os.environ.get("QWEN_IMAGE_MODEL", "smbs/Image-2.1")

OUT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "market-icons")
)

STYLE = (
    "flat vector app icon, rounded square tile, {bg} gradient background, "
    "centered single bold white {symbol} glyph, minimal, crisp clean edges, "
    "soft inner glow, high contrast, modern product logo style, 1:1"
)
NEGATIVE = "text, letters, words, numbers, watermark, photo, realistic, 3d clutter, multiple objects, frame, border"

# key -> (背景色描述, 白色符号描述)
ICONS: dict[str, tuple[str, str]] = {
    # ---- 通用技能 ----
    "skill-doc-writing": ("indigo to violet", "document page with a fountain pen"),
    "skill-meeting-notes": ("blue to cyan", "speech bubble with a check mark"),
    "skill-email-writing": ("sky blue to deep blue", "envelope"),
    "skill-weekly-report": ("emerald to teal", "calendar with a bar chart"),
    "skill-code-review": ("slate to indigo", "curly braces with a magnifier"),
    "skill-sql-helper": ("violet to fuchsia", "database cylinder"),
    "skill-data-analysis": ("cyan to blue", "rising line chart with a magnifier"),
    "skill-translate-polish": ("teal to green", "globe with two opposite arrows"),
    "skill-ppt-outline": ("orange to amber", "presentation screen with bullet lines"),
    "skill-requirement-breakdown": ("amber to orange", "checklist with branching arrows"),
    "skill-seo-optimize": ("lime to green", "magnifier with an upward arrow"),
    "skill-contract-review": ("rose to red", "contract page with a shield"),
    "skill-competitor-research": ("indigo to blue", "telescope"),
    "skill-prompt-optimize": ("purple to pink", "magic wand with a spark"),
    "skill-support-script": ("pink to rose", "support headset"),
    "skill-kb-qa": ("blue to indigo", "open book with a question mark"),
    # ---- agno 免密钥工具 ----
    "tool-calculator": ("blue to indigo", "calculator with plus minus symbols"),
    "tool-webtools": ("cyan to sky blue", "globe with a chain link"),
    "tool-hackernews": ("orange to red", "abstract triangle and square blocks"),
    "tool-duckduckgo": ("red to orange", "magnifying glass"),
    "tool-wikipedia": ("slate to gray", "open book with puzzle piece"),
    "tool-arxiv": ("red to rose", "research paper page with formula marks"),
    "tool-newspaper": ("amber to yellow", "folded newspaper"),
    "tool-csv": ("green to emerald", "spreadsheet table grid"),
    "tool-visualization": ("violet to purple", "bar chart with a trend line"),
    # ---- 办公类 MCP ----
    "mcp-lark": ("blue to cyan", "stylized wing feather"),
    "mcp-wecom": ("green to emerald", "two overlapping speech bubbles"),
    "mcp-github": ("slate to gray", "git branch node graph"),
    "mcp-notion": ("gray to slate", "rounded square with a diagonal stroke"),
    "mcp-gitlab": ("orange to amber", "three stacked triangles"),
    "mcp-playwright": ("emerald to teal", "browser window with a cursor"),
    "mcp-context7": ("indigo to violet", "document page with a spark star"),
    "mcp-filesystem": ("amber to orange", "folder"),
    # ---- 能力包（技能 + 工具 + MCP 的集合） ----
    "pack-office": ("blue to indigo", "stacked cards with a briefcase"),
    "pack-dev": ("violet to purple", "stacked cards with code brackets"),
    "pack-data": ("teal to cyan", "stacked cards with a bar chart"),
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
    except Exception:  # noqa: BLE001  PIL 不可用时保留原图
        return png_bytes


def gen_one(client: OpenAI, key: str) -> tuple[str, str]:
    bg, symbol = ICONS[key]
    out_path = os.path.join(OUT_DIR, f"{key}.png")
    if os.path.exists(out_path):
        return key, "skip(exists)"
    resp = client.images.generate(
        model=MODEL,
        prompt=STYLE.format(bg=bg, symbol=symbol),
        size="1024x1024",
        n=1,
        response_format="b64_json",
        # 网关扩展参数需经 extra_body 传递（openai SDK 严格校验签名）
        extra_body={"negative_prompt": NEGATIVE},
    )
    raw = base64.b64decode(resp.data[0].b64_json)
    with open(out_path, "wb") as f:
        f.write(_shrink(raw))
    return key, f"ok({len(raw) // 1024}KB -> {os.path.getsize(out_path) // 1024}KB)"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", default="", help="逗号分隔的 key 列表，仅生成这些")
    p.add_argument("--concurrency", type=int, default=4)
    args = p.parse_args()

    keys = [k for k in ICONS if not args.only or k in args.only.split(",")]
    os.makedirs(OUT_DIR, exist_ok=True)
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    print(f"目标 {len(keys)} 张 → {OUT_DIR}", flush=True)

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = {ex.submit(gen_one, client, k): k for k in keys}
        for fut in as_completed(futures):
            k = futures[fut]
            try:
                key, msg = fut.result()
                print(f"[OK] {key}: {msg}", flush=True)
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"[FAIL] {k}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                fail += 1
    print(f"完成：成功 {ok}，失败 {fail}", flush=True)


if __name__ == "__main__":
    main()
