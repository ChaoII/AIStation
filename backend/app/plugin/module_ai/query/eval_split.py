"""留出法（held-out）：把评测题按**近义分组**切 A/B，近义题必须同集。

为什么必须做：错题沉淀成 few-shot 后，如果评测题里有它的**近义题**，
模型就能从"近义题的答案"抄 → 分数虚高（实测：完全相同题已加防泄漏闸，
但近义题仍泄漏，如四条「每个供应商的矿点占比…」）。
正确协议：**只用 A 半的错题沉淀 → 在 B 半上评测**。
"""
from __future__ import annotations


def _grams(text: str) -> set[str]:
    """中文二元组 + 英文/数字词，用于近义判定。"""
    import re

    t = (text or "").lower()
    zh = re.sub(r"[^\u4e00-\u9fff]+", " ", t)
    out: set[str] = set()
    for part in zh.split():
        for i in range(len(part) - 1):
            out.add(part[i : i + 2])
    out |= set(re.findall(r"[a-z0-9_]{2,}", t))
    return out


def similarity(a: str, b: str) -> float:
    """Jaccard 相似度（二元组集合）。"""
    ga, gb = _grams(a), _grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def assign_splits(questions: list[str], threshold: float = 0.35) -> dict[str, str]:
    """近义分组后**交替**分到 A/B；同组必然同集。返回 ``{问题: 'A'|'B'}``。

    阈值取 0.35（偏低=更保守）：实测「每个供应商的矿点**数量**占全部矿点数量…」与
    「每个供应商**关联的矿点记录数**占全部供应商矿点关联记录数…」的 Jaccard ≈ 0.39，
    这类改写必须同集，否则模型仍能从"近义题的答案"抄。
    交替（而不是"整组塞 A"）是为了让 A/B 两半的形式分布尽量均衡。
    """
    qs = [str(q or "") for q in (questions or [])]
    parent = list(range(len(qs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(len(qs)):
        for j in range(i + 1, len(qs)):
            if similarity(qs[i], qs[j]) >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(len(qs)):
        groups.setdefault(find(i), []).append(i)

    # **贪心均衡**：大组优先，塞给当前题数较少的一边。
    # （交替分配在"组很大"时会失衡：实测 A=105/B=66，形式分布也偏。）
    out: dict[str, str] = {}
    counts = {"A": 0, "B": 0}
    for idxs in sorted(groups.values(), key=lambda g: (-len(g), g[0])):
        tag = "A" if counts["A"] <= counts["B"] else "B"
        counts[tag] += len(idxs)
        for i in idxs:
            out[qs[i]] = tag
    return out
