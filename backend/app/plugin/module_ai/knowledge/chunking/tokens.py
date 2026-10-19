"""token 计数与按 token 窗切分（tiktoken 估算，失败退化为字符估算）。"""
from __future__ import annotations

from functools import lru_cache

_FALLBACK_RATIO = 2  # 1 token ≈ 2 个中文字符（仅作退化估算）


@lru_cache(maxsize=1)
def _encoding():
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """估算 token 数；tiktoken 不可用时按字符数折半。"""
    value = text or ""
    if not value:
        return 0
    try:
        return len(_encoding().encode(value))
    except Exception:  # noqa: BLE001
        return max(1, len(value) // _FALLBACK_RATIO)


def split_by_tokens(text: str, max_tokens: int, overlap: int = 0) -> list[str]:
    """按 token 窗切分文本（``overlap`` 为 token 数）。"""
    value = text or ""
    if not value.strip():
        return []
    limit = max(1, int(max_tokens))
    step = max(1, limit - max(0, int(overlap)))
    try:
        tokens = _encoding().encode(value)
        pieces = [
            _encoding().decode(tokens[i : i + limit])
            for i in range(0, len(tokens), step)
            if tokens[i : i + limit]
        ]
        if len(pieces) > 1 and not pieces[-1].strip():
            pieces.pop()
        return pieces
    except Exception:  # noqa: BLE001  tiktoken 不可用：按字符近似
        char_limit = limit * _FALLBACK_RATIO
        char_step = step * _FALLBACK_RATIO
        return [
            value[i : i + char_limit]
            for i in range(0, len(value), char_step)
            if value[i : i + char_limit].strip()
        ]
