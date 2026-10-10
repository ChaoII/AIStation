"""问数召回服务：语义单元构建 + 多路召回通道 + RRF 融合。

设计见 ``docs/superpowers/specs/2026-10-10-query-recall-service-design.md``。

本模块以**纯函数**为主（接收显式数据、无 IO），便于单测；
取数据的副作用（DB / 本体 / 嵌入）留在 ``service.py`` 的 ``_recall_*`` 薄包装里。
"""
from __future__ import annotations

#: 各召回通道默认权重（RRF 只用**排名**，权重决定通道影响力）。
#: 本体强信号（别名/同义词/属性名）最可信 → 权重最高；
#: 关键词次之（中文注释是业务语义）；对象名命中较泛 → 由向量/关键词兜底。
DEFAULT_WEIGHTS: dict[str, float] = {
    "vector": 1.0,
    "keyword": 0.8,
    "ontology": 1.2,
    "entity": 0.6,
}

#: RRF 平滑常数（业界常用 60，避免头部排名过度主导）。
RRF_K = 60


def fuse_rrf(
    channels: dict[str, list[str]],
    weights: dict[str, float] | None = None,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """多路召回结果按 RRF（Reciprocal Rank Fusion）融合。

    参数:
    - channels: ``{通道名: [表名(按相关度降序)]}``。
    - weights: 覆盖默认权重的部分字典。
    - k: RRF 平滑常数。

    返回:
    - ``[(表名, 分数)]``，按分数降序；同分时按表名字典序，保证**确定性**。

    公式: ``score(t) = Σ_c weight_c / (k + rank_c(t))``，``rank`` 从 1 起。
    未知通道权重按 0 处理（即忽略）；同一张表被多路命中时**累加**而非重复。
    """
    merged_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        merged_weights.update(weights)

    scores: dict[str, float] = {}
    for name, tables in (channels or {}).items():
        weight = merged_weights.get(name, 0.0)
        if weight <= 0:
            continue
        for rank, table in enumerate(tables or [], start=1):
            if not table:
                continue
            scores[table] = scores.get(table, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
