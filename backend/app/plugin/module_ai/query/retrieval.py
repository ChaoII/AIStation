"""智能问数-分层检索（jieba 关键词 + embedding 语义 + 相关度融合）。

用于 schema linking：把 表/列/指标/术语 作为可检索单元，按问题召回最相关单元。
- 关键词层：jieba 中文分词 + 英文/数字词，词面重叠打分。
- 语义层：embedding 余弦相似度（复用 knowledge.embedding）。
- 融合：线性加权（可配置），保证同义改写与精确词都能命中。
"""
from __future__ import annotations

import re
from functools import lru_cache

# 检索权重（语义为主，关键词为辅）
SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4

_CN_RE = re.compile(r"[\u4e00-\u9fa5]+")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{1,}")


def _latin_tokens(text: str) -> list[str]:
    return [t.lower() for t in _LATIN_RE.findall(text or "")]


def _cn_chunks(text: str) -> list[str]:
    return _CN_RE.findall(text or "")


@lru_cache(maxsize=128)
def _jieba_cut(text: str) -> tuple[str, ...]:
    """jieba 中文分词（失败回退到逐字/连续块）。"""
    try:
        import jieba as _jieba

        return tuple(w for w in _jieba.lcut(text) if w.strip())
    except Exception:  # noqa: BLE001
        return tuple(_cn_chunks(text))


def tokenize(text: str) -> set[str]:
    """分词：jieba 中文 + 拉丁词。"""
    tokens = set(_latin_tokens(text))
    tokens.update(t.lower() for t in _jieba_cut(text) if len(t) >= 2)
    return tokens


def keyword_score(question: str, unit_text: str) -> float:
    """词面重叠率（基于 jieba 分词）。"""
    q = tokenize(question)
    u = tokenize(unit_text)
    if not q:
        return 0.0
    return len(q & u) / len(q)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (
        (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5) + 1e-9
    )


async def retrieve(
    question: str,
    units: list[dict],
    top_k: int = 10,
    semantic_weight: float | None = None,
) -> list[dict]:
    """分层检索：融合关键词 + 语义，返回 top-k。

    units: [{text, vector?, meta?}]；question 只向量化一次。
    """
    sw = SEMANTIC_WEIGHT if semantic_weight is None else semantic_weight
    kw = KEYWORD_WEIGHT if semantic_weight is None else (1 - semantic_weight)
    qvec: list[float] | None = None
    try:
        from app.plugin.module_ai.knowledge.embedding import embed_texts

        qvec = (await embed_texts([question]))[0]
    except Exception:  # noqa: BLE001
        qvec = None
    scored: list[tuple[float, dict]] = []
    for unit in units:
        ks = keyword_score(question, unit["text"])
        ss = _cosine(qvec, unit.get("vector")) if qvec and unit.get("vector") else 0.0
        scored.append((kw * ks + sw * ss, unit))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored[:top_k]]
