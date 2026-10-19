"""网页解析：newspaper4k 抽正文（HTML 走 bleach 清洗），可选快照存 RustFS。"""
from __future__ import annotations

import asyncio

from app.core.logger import log


def parse_html(html: str) -> str:
    """HTML → 纯文本（保留段落换行）。"""
    import bleach
    from newspaper import Article

    try:
        article = Article("")
        article.set_html(html)
        article.parse()
        if article.text.strip():
            return article.text
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] newspaper 抽取失败，退化为 bleach 清洗：{e}")
    cleaned = bleach.clean(html, tags=["p", "br", "div", "h1", "h2", "h3", "li"], strip=True)
    return cleaned.replace("</p>", "\n").replace("<br>", "\n")


def _fetch_and_extract(url: str) -> str:
    from newspaper import Article

    article = Article(url)
    article.download()
    article.parse()
    return article.text or ""


async def parse_url(url: str, *, kb_id: int | None = None) -> tuple[str, list[int], dict]:
    """抓取网页正文；``kb_id`` 提供时把原始 HTML 快照存 RustFS。"""
    from app.utils.s3_client import s3_client

    text = await asyncio.to_thread(_fetch_and_extract, url)
    if not (text or "").strip():
        raise ValueError("网页抓取失败或无正文")
    snapshot = None
    if kb_id:
        try:
            import io
            import uuid

            html = await asyncio.to_thread(_fetch_html, url)
            key = f"knowledge_snapshots/{kb_id}/{uuid.uuid4().hex}.html"
            await asyncio.to_thread(
                s3_client.upload_fileobj, io.BytesIO(html.encode("utf-8")), key
            )
            snapshot = key
        except Exception as e:  # noqa: BLE001  快照失败不影响正文入库
            log.warning(f"[RAG] 网页快照保存失败：{e}")
    return text, [0], {"parser": "web", "url": url, "snapshot": snapshot}


def _fetch_html(url: str) -> str:
    import httpx

    response = httpx.get(url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    return response.text
