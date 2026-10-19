"""检索评测指标：Recall@K / Precision@K / MRR / NDCG@K。

输入均为 chunk id 列表；``expected`` 为金标准相关集合（二值增益）。
"""
from __future__ import annotations

import math


def _hits(retrieved: list[int], expected: set[int], k: int) -> int:
    return len(set(retrieved[:k]) & expected)


def recall_at_k(retrieved: list[int], expected: list[int], k: int) -> float:
    gold = set(expected or [])
    if not gold:
        return 0.0
    return _hits(retrieved, gold, k) / len(gold)


def precision_at_k(retrieved: list[int], expected: list[int], k: int) -> float:
    denom = max(1, int(k))
    return _hits(retrieved, set(expected or []), k) / denom


def mrr(retrieved: list[int], expected: list[int]) -> float:
    gold = set(expected or [])
    if not gold:
        return 0.0
    for position, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in gold:
            return 1.0 / position
    return 0.0


def ndcg_at_k(retrieved: list[int], expected: list[int], k: int) -> float:
    gold = set(expected or [])
    if not gold:
        return 0.0
    dcg = 0.0
    for position, chunk_id in enumerate(retrieved[:k], start=1):
        if chunk_id in gold:
            dcg += 1.0 / math.log2(position + 1)
    ideal = sum(
        1.0 / math.log2(position + 1)
        for position in range(1, min(len(gold), int(k)) + 1)
    )
    if ideal <= 0:
        return 0.0
    return dcg / ideal


def evaluate_items(items: list[dict], k: int = 5) -> dict:
    """批量计算平均指标；``items`` 元素为 ``{"retrieved": [...], "expected": [...]}``。"""
    if not items:
        return {"recall": 0.0, "precision": 0.0, "mrr": 0.0, "ndcg": 0.0, "n": 0}
    recalls, precisions, mrrs, ndcgs = [], [], [], []
    for item in items:
        retrieved = [int(x) for x in item.get("retrieved") or []]
        expected = [int(x) for x in item.get("expected") or []]
        recalls.append(recall_at_k(retrieved, expected, k))
        precisions.append(precision_at_k(retrieved, expected, k))
        mrrs.append(mrr(retrieved, expected))
        ndcgs.append(ndcg_at_k(retrieved, expected, k))
    count = len(items)
    return {
        "recall": round(sum(recalls) / count, 4),
        "precision": round(sum(precisions) / count, 4),
        "mrr": round(sum(mrrs) / count, 4),
        "ndcg": round(sum(ndcgs) / count, 4),
        "n": count,
    }
