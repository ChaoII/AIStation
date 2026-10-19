"""MinerU MCP(SSE) 解析：把扫描件/图片/PDF 转 Markdown（含页码与图片）。

已实测服务：``http://172.168.100.146:8100/sse``（``mineru-processor 1.28.1``），
工具 ``process_document`` 支持 ``return_md / return_content_list / return_images``。
"""
from __future__ import annotations

import base64
import json
import re
from html import unescape as _unescape

from app.core.logger import log

from ..config import rag_config


def _html_table_to_markdown(table_html: str) -> str:
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
    md_rows: list[list[str]] = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        md_rows.append(
            [
                _unescape(re.sub(r"<[^>]+>", " ", cell)).replace("|", "\\|").strip()
                for cell in cells
            ]
        )
    if not md_rows:
        return ""
    width = max(len(row) for row in md_rows)
    md_rows = [row + [""] * (width - len(row)) for row in md_rows]

    def _fmt(row: list[str]) -> str:
        return "| " + " | ".join(row) + " |"

    lines = [_fmt(md_rows[0]), "| " + " | ".join(["---"] * width) + " |"]
    lines.extend(_fmt(row) for row in md_rows[1:])
    return "\n".join(lines)


def html_tables_to_markdown(markdown: str) -> str:
    """MinerU 的表格是 HTML → 转 Markdown 管道表；其余标签剥离。"""
    value = re.sub(
        r"<table[^>]*>.*?</table>",
        lambda m: _html_table_to_markdown(m.group(0)),
        markdown or "",
        flags=re.DOTALL,
    )
    return _unescape(re.sub(r"<[^>]+>", " ", value))


def page_offsets_from_content_list(content_list: list[dict], text: str) -> list[int]:
    """从 ``content_list`` 的 ``page_idx`` 推导每页起始字符偏移。"""
    pages: dict[int, list[str]] = {}
    for item in content_list or []:
        try:
            page = int(item.get("page_idx"))
        except (TypeError, ValueError):
            continue
        piece = item.get("text") or item.get("table_body") or ""
        if isinstance(item.get("table_body"), str):
            piece = re.sub(r"<[^>]+>", " ", item["table_body"])
        if piece and str(piece).strip():
            pages.setdefault(page, []).append(str(piece).strip())
    if not pages:
        return [0]
    offsets: list[int] = []
    cursor = 0
    for index in range(max(pages) + 1):
        offsets.append(cursor)
        cursor += len("\n".join(pages.get(index, []))) + 1
    return offsets


def _tool_args(filename: str, data: bytes, *, with_images: bool) -> dict:
    return {
        "file_content": base64.b64encode(data).decode("utf-8"),
        "filename": filename or "document.pdf",
        "mode": "sync",
        "backend": rag_config.mineru_backend,
        "parse_method": rag_config.mineru_parse_method,
        "lang_list": list(rag_config.mineru_lang_list),
        "return_md": True,
        "return_content_list": True,
        "return_images": bool(with_images),
        "image_analysis": False,
    }


async def parse_via_mineru(
    filename: str, data: bytes, *, kb_id: int | None = None, with_images: bool = True
) -> tuple[str, list[int], dict] | None:
    """调用 MinerU 解析；服务不可用/返回异常时返回 ``None`` 并记录原因。"""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    url = rag_config.mineru_url
    timeout = float(rag_config.mineru_timeout)
    try:
        async with sse_client(url, timeout=timeout, sse_read_timeout=timeout) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "process_document", _tool_args(filename, data, with_images=with_images)
                )
                text = "".join(
                    part.text for part in result.content if getattr(part, "text", None)
                )
                payload = json.loads(text) if text else {}
                if payload.get("status") != "ok":
                    log.warning(f"[RAG] MinerU 解析失败：{str(payload)[:300]}")
                    return None
                body = payload.get("result") or {}
                markdown = html_tables_to_markdown(
                    body.get("markdown") or body.get("md_content") or ""
                ).strip()
                if not markdown:
                    log.warning("[RAG] MinerU 返回成功但无 markdown")
                    return None
                content_list = body.get("content_list")
                if isinstance(content_list, str):
                    try:
                        content_list = json.loads(content_list)
                    except json.JSONDecodeError:
                        content_list = []
                offsets = page_offsets_from_content_list(content_list or [], markdown)
                return markdown, offsets, {
                    "parser": "mineru",
                    "pages": len(offsets),
                    "images": len(body.get("images") or []),
                }
    except Exception as e:  # noqa: BLE001
        log.error(f"[RAG] MinerU MCP 调用失败 {url}：{e}")
        return None
