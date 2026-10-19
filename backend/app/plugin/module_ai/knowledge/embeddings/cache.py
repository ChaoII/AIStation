"""进程内向量缓存：``模型 + 文本哈希 -> 向量``。

重复入库/重复查询同一段文本时不必再打网关（省时省钱），LRU 上限默认 4096 条。
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict


class EmbeddingCache:
    """最小可用的 LRU 向量缓存（线程/协程内共享，无持久化）。"""

    def __init__(self, maxsize: int = 4096) -> None:
        self._maxsize = max(1, int(maxsize))
        self._data: OrderedDict[str, list[float]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(model: str, text: str) -> str:
        digest = hashlib.sha1((text or "").encode("utf-8")).hexdigest()
        return f"{model}|{digest}"

    def get(self, model: str, text: str) -> list[float] | None:
        k = self.key(model, text)
        vec = self._data.get(k)
        if vec is None:
            self.misses += 1
            return None
        self.hits += 1
        self._data.move_to_end(k)
        return list(vec)

    def put(self, model: str, text: str, vec: list[float]) -> None:
        k = self.key(model, text)
        self._data[k] = list(vec)
        self._data.move_to_end(k)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:  # pragma: no cover - 便于调试
        return len(self._data)


embedding_cache = EmbeddingCache()
