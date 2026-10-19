"""分块：定长/段落/句子（历史）+ 标题树 + token 口径 + 父子块。

``chunk_text`` 的行为与历史实现完全一致（回归依赖它）；``chunk_drafts``
在同样的分块结果上补充字符位置与页码，并支持标题树 / token / 父子块。
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

from .tokens import estimate_tokens, split_by_tokens


@dataclass
class ChunkDraft:
    """一个待入库的分块（含溯源位置与预算信息）。"""

    content: str
    char_start: int
    char_end: int
    page: int | None = None
    token_count: int = 0
    is_parent: bool = False
    parent_index: int | None = None
    meta: dict = field(default_factory=dict)


def chunk_text(
    text: str, chunk_size: int = 500, overlap: int = 50, strategy: str = "fixed"
) -> list[str]:
    """分块：fixed(定长+重叠) / paragraph(按段落) / sentence(按句子) / heading。"""
    text = (text or "").strip()
    if not text:
        return []
    if strategy == "heading":
        from .heading import split_heading_sections

        out: list[str] = []
        for heading, section, _start in split_heading_sections(text):
            pieces = _split_section(section, chunk_size, overlap)
            prefix = f"【{heading}】\n" if heading else ""
            out.extend([prefix + piece for piece in pieces])
        return out
    if strategy == "paragraph":
        paras = re.split(r"\n\s*\n", text)
        out = []
        for p in paras:
            p = p.strip()
            if p:
                if len(p) > chunk_size:
                    out.extend(_fixed_chunk(p, chunk_size, overlap))
                else:
                    out.append(p)
        return out
    if strategy == "sentence":
        sents = re.split(r"(?<=[。！？!?；;])", text)
        out = []
        buf = ""
        for s in sents:
            s = s.strip()
            if not s:
                continue
            if len(buf) + len(s) > chunk_size and buf:
                out.append(buf.strip())
                buf = ""
            buf += s
        if buf.strip():
            out.append(buf.strip())
        if len(out) > 1 and len(out[-1]) <= overlap:
            out.pop()
        return out
    return _fixed_chunk(text, chunk_size, overlap)


def _fixed_chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    for i in range(0, len(text), step):
        piece = text[i : i + chunk_size].strip()
        if piece:
            chunks.append(piece)
    if len(chunks) > 1 and len(chunks[-1]) <= overlap:
        chunks.pop()
    return chunks


def _split_section(section: str, chunk_size: int, overlap: int) -> list[str]:
    """节内切分：优先按段落，超长段落再定长切。"""
    if len(section) <= chunk_size:
        return [section.strip()] if section.strip() else []
    out: list[str] = []
    for p in re.split(r"\n\s*\n", section):
        p = p.strip()
        if not p:
            continue
        out.extend(_fixed_chunk(p, chunk_size, overlap) if len(p) > chunk_size else [p])
    return out


def _locate(text: str, pieces: list[str], base: int) -> list[tuple[int, int]]:
    """在原文中定位每块（找不到时退化为顺序游标）。"""
    cursor = 0
    spans: list[tuple[int, int]] = []
    for piece in pieces:
        if not piece:
            continue
        idx = text.find(piece, cursor)
        if idx < 0:
            stripped = piece.strip()
            idx = text.find(stripped, cursor) if stripped else -1
        if idx < 0:
            idx = cursor
        end = idx + len(piece.strip() or piece)
        spans.append((base + idx, base + end))
        cursor = max(cursor, idx + 1)
    return spans


def _page_of(page_offsets: list[int] | None, char_start: int) -> int | None:
    if not page_offsets:
        return None
    return max(0, bisect.bisect_right(page_offsets, char_start) - 1)


def _to_drafts(
    text: str,
    pieces: list[str],
    *,
    page_offsets: list[int] | None,
    base: int = 0,
) -> list[ChunkDraft]:
    spans = _locate(text, pieces, base)
    drafts: list[ChunkDraft] = []
    for piece, (start, end) in zip(pieces, spans, strict=False):
        drafts.append(
            ChunkDraft(
                content=piece,
                char_start=start,
                char_end=end,
                page=_page_of(page_offsets, start),
                token_count=estimate_tokens(piece),
            )
        )
    return drafts


def chunk_drafts(
    text: str,
    *,
    strategy: str = "fixed",
    chunk_size: int = 500,
    overlap: int = 50,
    unit: str = "char",
    page_offsets: list[int] | None = None,
    parent_child: bool = False,
    parent_size: int = 2048,
) -> list[ChunkDraft]:
    """分块并返回带位置/页码的草稿；可选父子块（父块在前，子块指向父块下标）。"""
    raw = text or ""
    base = len(raw) - len(raw.lstrip())
    if unit == "token":
        pieces = split_by_tokens(raw.strip(), chunk_size, overlap)
    else:
        pieces = chunk_text(raw, chunk_size, overlap, strategy)
    drafts = _to_drafts(raw, pieces, page_offsets=page_offsets, base=base)
    if not parent_child:
        return drafts

    # 父块：标题节（heading）或定长滑窗；子块在父块内再切
    parents: list[ChunkDraft] = []
    if strategy == "heading":
        from .heading import split_heading_sections

        for heading, section, start in split_heading_sections(raw.strip()):
            content = (f"【{heading}】\n" if heading else "") + section.strip()
            parents.append(
                ChunkDraft(
                    content=content,
                    char_start=base + start,
                    char_end=base + start + len(section.strip()),
                    page=_page_of(page_offsets, base + start),
                    token_count=estimate_tokens(content),
                    is_parent=True,
                )
            )
    else:
        window = max(1, int(parent_size))
        for offset in range(0, len(raw.strip()), window):
            content = raw.strip()[offset : offset + window]
            if not content.strip():
                continue
            parents.append(
                ChunkDraft(
                    content=content,
                    char_start=base + offset,
                    char_end=base + offset + len(content),
                    page=_page_of(page_offsets, base + offset),
                    token_count=estimate_tokens(content),
                    is_parent=True,
                )
            )

    children: list[ChunkDraft] = []
    for p_index, parent in enumerate(parents):
        for child in _to_drafts(
            parent.content,
            chunk_text(parent.content, chunk_size, overlap,
                       "paragraph" if strategy != "heading" else "heading"),
            page_offsets=page_offsets,
            base=parent.char_start,
        ):
            child.is_parent = False
            child.parent_index = p_index
            children.append(child)
    return parents + children
