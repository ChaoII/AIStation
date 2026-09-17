"""人脸底库的进程内缓存与余弦相似度（供 ``face_match`` / ``stranger`` 叶子求值）。

设计要点：
- ``face_match`` / ``stranger`` 在 ``inference/service.py`` 的同步求值器里执行，
  不能直接做异步 DB 查询，故底库特征维护在进程内缓存中（同 ``temporal_store`` 思路）；
- 缓存由启动生命周期 + 底库增删改接口刷新（``service.py``），跨进程不共享，
  多 worker 部署下存在最终一致延迟（见 ``refresh_face_gallery_cache`` 说明）；
- 相似度在 Python 侧算余弦（无 pgvector 依赖），复杂度 O(底库条数 × 检测数)，
  底库规模上限约数千条；升级路径见 ``docs`` 报告（pgvector 向量列 + ivfflat/hnsw 索引）。
"""
from __future__ import annotations

import math
import time
from typing import Any

#: 进程内缓存的兜底新鲜度上界（秒）。
#: 多 worker 场景优先用 Redis 版本号近实时失效；Redis 不可用或「enroll 与事务提交之间」的
#: 竞态窗口内，事件热路径最多每 TTL 秒回读一次 DB，保证跨进程变更**最终可见**（有界延迟）。
DEFAULT_CACHE_TTL_SEC = 10.0


class FaceGalleryStore:
    """进程内人脸底库缓存：持有若干 ``{id, name, person_no, model_key, embedding, dimension}``。

    多 worker 一致性：缓存自带 ``version``（对应 Redis 全局版本号）与 ``loaded_at``。
    ``sync_cache``（见 service.py）在事件热路径按「版本号变化 或 缓存超过 TTL」触发重读，
    从而让任一 worker 的录入/删除对其他 worker 尽快生效。
    """

    def __init__(self, ttl_sec: float = DEFAULT_CACHE_TTL_SEC) -> None:
        self._entries: list[dict] = []
        self._version: int = 0
        self._loaded_at: float = 0.0
        self._ttl: float = max(0.0, float(ttl_sec))

    def replace(self, entries: list[dict] | None, version: int | None = None) -> None:
        """整体替换缓存（仅保留结构合法且向量非空的条目）。

        传 ``version`` 时同步记录全局版本号；``loaded_at`` 恒更新为当前单调时钟。
        """
        cleaned: list[dict] = []
        for e in entries or []:
            if not isinstance(e, dict):
                continue
            emb = _as_vector(e.get("embedding"))
            if emb is None:
                continue
            cleaned.append({**e, "embedding": emb, "dimension": len(emb)})
        self._entries = cleaned
        self._loaded_at = time.monotonic()
        if version is not None:
            self._version = int(version)

    def clear(self) -> None:
        """清空缓存并标记未加载（测试用）。"""
        self._entries = []
        self._loaded_at = 0.0

    @property
    def version(self) -> int:
        """当前缓存对应的全局版本号。"""
        return self._version

    def mark_version(self, version: int) -> None:
        """记录缓存已同步到的全局版本号。"""
        self._version = int(version)

    def is_stale(self) -> bool:
        """缓存是否超过 TTL 未刷新（从未加载恒为 True）。"""
        if self._loaded_at <= 0.0:
            return True
        if self._ttl <= 0.0:
            return False
        return (time.monotonic() - self._loaded_at) > self._ttl

    def snapshot(self) -> list[dict]:
        """返回当前缓存快照（只读用途，勿原地修改）。"""
        return list(self._entries)

    def size(self) -> int:
        """当前底库条目数。"""
        return len(self._entries)


# 进程级单例（与 temporal_store 同思路）
face_gallery_store = FaceGalleryStore()


def _as_vector(raw: Any) -> list[float] | None:
    """把原始值规整为有限 float 列表；非法/空/含 NaN/Inf 返回 None。"""
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    out: list[float] = []
    for x in raw:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return None
        v = float(x)
        if not math.isfinite(v):
            return None
        out.append(v)
    return out


def is_valid_embedding(raw: Any) -> bool:
    """是否为合法的特征向量（非空有限 float 列表）。"""
    return _as_vector(raw) is not None


def _norm(vec: list[float]) -> float:
    """L2 范数。"""
    return math.sqrt(sum(v * v for v in vec))


def cosine_similarity(a: Any, b: Any) -> float | None:
    """两向量的余弦相似度；维度不一致/非法/零向量返回 None（fail-closed）。

    兼容「已 L2 归一化」与「未归一化」两种输入（余弦对整体缩放不敏感）。
    """
    va = _as_vector(a)
    vb = _as_vector(b)
    if va is None or vb is None or len(va) != len(vb):
        return None
    na = _norm(va)
    nb = _norm(vb)
    if na <= 0.0 or nb <= 0.0:
        return None
    dot = sum(x * y for x, y in zip(va, vb, strict=True))
    sim = dot / (na * nb)
    # 数值误差可能略微超出 [-1, 1]，裁剪以保持语义稳定
    return max(-1.0, min(1.0, sim))


def best_similarity(embedding: Any, entries: list[dict] | None) -> float | None:
    """与底库全部条目的最大余弦相似度；底库为空/无可比条目返回 None（fail-closed）。"""
    vec = _as_vector(embedding)
    if vec is None or not entries:
        return None
    best: float | None = None
    for e in entries:
        if not isinstance(e, dict):
            continue
        sim = cosine_similarity(vec, e.get("embedding"))
        if sim is None:
            continue
        if best is None or sim > best:
            best = sim
    return best
