"""标题树切分：按 Markdown 标题 / 编号标题分节，节内再递归切分。"""
from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
_NUMBERED_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)*)[\s、.]+(?P<title>.+?)\s*$")
_SPLIT_SYMBOLS = ("\n\n", "；", ";", "。")


def split_heading_sections(text: str, max_level: int = 6) -> list[tuple[str, str, int]]:
    """把文本切成 ``(标题路径, 节正文, 节起点)`` 列表。

    以第一个标题为界，之前的正文作为无标题节（``""``）返回。
    """
    lines = (text or "").splitlines(keepends=True)
    sections: list[tuple[str, str, int]] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    cursor = 0

    def flush(path_text: str) -> None:
        body = "".join(buffer).strip("\n")
        if body.strip():
            sections.append((path_text, body, start))

    for line in lines:
        matched = _HEADING_RE.match(line.rstrip("\n")) or _NUMBERED_RE.match(
            line.rstrip("\n")
        )
        if matched:
            level = (
                len(matched.group(1))
                if matched.re is _HEADING_RE
                else len(matched.group("num").split("."))
            )
            title = matched.group("title").strip()
            if level <= max_level:
                flush(" / ".join(t for _, t in stack))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
                buffer = [line]
                start = cursor
                cursor += len(line)
                continue
        buffer.append(line)
        cursor += len(line)
    flush(" / ".join(t for _, t in stack))
    return sections


def split_long_section(section: str, max_chars: int) -> list[str]:
    """节内二次切分：按分段符号递归，超长再按字符窗。"""
    text = (section or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    for symbol in _SPLIT_SYMBOLS:
        if symbol in text:
            parts = [p for p in text.split(symbol) if p.strip()]
            if len(parts) > 1:
                break
    if len(parts) <= 1:
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]
    out: list[str] = []
    buffer = ""
    for part in parts:
        piece = part + "。"
        if len(buffer) + len(piece) > max_chars and buffer:
            out.append(buffer.strip())
            buffer = ""
        if len(piece) > max_chars:
            out.extend(piece[i : i + max_chars] for i in range(0, len(piece), max_chars))
        else:
            buffer += piece
    if buffer.strip():
        out.append(buffer.strip())
    return out
