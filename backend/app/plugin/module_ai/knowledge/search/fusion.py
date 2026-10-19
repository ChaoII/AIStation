"""混合检索融合：RRF（默认）与归一化加权（显式权重时）。

RRF（Reciprocal Rank Fusion）只依赖排名，不依赖各引擎分数尺度，也不会因为
某一路缺失而惩罚命中项；加权融合则兼容既有「向量/全文权重」语义。
"""
from __future__ import annotations


def rrf(lists: list[list[dict]], k: int = 60) -> list[dict]:
    """多路结果按排名倒数融合：``score = Σ 1/(k + rank)``。"""
    scores: dict[int, float] = {}
    info: dict[int, dict] = {}
    order: dict[int, int] = {}
    for rows in lists:
        for rank, row in enumerate(rows, start=1):
            cid = int(row["chunk_id"])
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in info:
                info[cid] = row
                order[cid] = len(order)
    fused = [
        {**info[cid], "engine": "hybrid", "score": round(score, 4)}
        for cid, score in scores.items()
    ]
    fused.sort(key=lambda item: (-item["score"], order[int(item["chunk_id"])]))
    return fused


def _normalize(rows: list[dict]) -> dict[int, float]:
    """按本路最高分归一化（最高分为 0 时该路贡献 0）。"""
    if not rows:
        return {}
    top = max(float(row.get("score") or 0.0) for row in rows)
    if top <= 0:
        return {int(row["chunk_id"]): 0.0 for row in rows}
    return {int(row["chunk_id"]): float(row.get("score") or 0.0) / top for row in rows}


def weighted(lists: list[list[dict]], weights: list[float]) -> list[dict]:
    """归一化加权融合（缺失侧贡献 0）。"""
    info: dict[int, dict] = {}
    order: dict[int, int] = {}
    combined: dict[int, float] = {}
    for rows, weight in zip(lists, weights, strict=False):
        norm = _normalize(rows)
        for row in rows:
            cid = int(row["chunk_id"])
            if cid not in info:
                info[cid] = row
                order[cid] = len(order)
            combined[cid] = combined.get(cid, 0.0) + norm.get(cid, 0.0) * float(weight)
    fused = [
        {**info[cid], "engine": "hybrid", "score": round(score, 4)}
        for cid, score in combined.items()
    ]
    fused.sort(key=lambda item: (-item["score"], order[int(item["chunk_id"])]))
    return fused
