"""人脸嵌入的紧凑编码/解码（``f16b64``）。

背景与契约（与 Agent 侧 ``event_bus.cpp`` 对齐）：
- 原始 float32 数组每张脸约 10.7 KB（512-d），24 张脸的上行事件约 250 KB，
  会触碰边缘 MQTT 链路的 broker/带宽限制；
- 紧凑编码：``objects[].embedding`` = base64(小端 IEEE-754 float16 序列)，
  并新增兄弟字段 ``objects[].embedding_encoding = "f16b64"``；
- 512-d 编码后 1368 字符 = 1,368 B（约原始体积的 1/7）；Agent 侧再按置信度
  Top-N（默认 8）限制携带嵌入的对象数，24 张脸的实测事件体积从 ~235 KB 降到 19,925 B；
- 向后兼容：无 ``embedding_encoding`` 且 ``embedding`` 为数值数组时，视为旧格式
  的原始 float 向量，原样透传（旧 Agent / 手工上报）。
"""
from __future__ import annotations

import base64
import math
import struct
from typing import Any

#: 紧凑编码标识：base64(小端 IEEE-754 float16)
F16_B64 = "f16b64"

#: 单条嵌入维度上限（云侧二次防御）：覆盖 512/1024/2048，拒绝异常/恶意超大数组，
#: 避免单事件解析出数百 MB 的向量拖垮内存或 DB（Agent 正常产出远小于此）。
MAX_EMBEDDING_DIM = 4096
#: 单事件携带嵌入的对象数上限（云侧二次防御）：Agent 侧另有 Top-N 默认 8，
#: 此处对「旧固件/手工上报/buggy 边缘」兜底，超出部分按置信度保留 Top-N。
MAX_EMBEDDINGS_PER_EVENT = 64


def encode_embedding_f16_b64(vec: Any) -> str:
    """把 float 序列编码为 ``f16b64``（base64 小端 float16）；空序列返回空串。"""
    values = [float(x) for x in vec]
    if not values:
        return ""
    return base64.b64encode(struct.pack(f"<{len(values)}e", *values)).decode("ascii")


def decode_embedding(raw: Any, encoding: Any = None) -> list[float] | None:
    """把事件里的 ``embedding`` 还原为 float 向量；非法输入返回 None（fail-closed）。

    - ``encoding == "f16b64"``：``raw`` 为 base64 字符串 → 解码并校验有限性；
    - ``encoding`` 为空：``raw`` 为数值数组 → 原样透传（向后兼容）；
    - 其余组合（未知编码、类型不匹配、非法 base64、NaN/Inf）→ None。
    """
    if isinstance(raw, str):
        if encoding != F16_B64 or not raw:
            return None
        try:
            data = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError):
            return None
        if not data or len(data) % 2 != 0:
            return None
        count = len(data) // 2
        try:
            values = list(struct.unpack(f"<{count}e", data))
        except struct.error:
            return None
        if any(not math.isfinite(v) for v in values):
            return None
        return values
    if isinstance(raw, (list, tuple)):
        if encoding:
            # 声明了编码却是数组：契约不一致，拒绝
            return None
        out: list[float] = []
        for x in raw:
            if isinstance(x, bool) or not isinstance(x, (int, float)):
                return None
            v = float(x)
            if not math.isfinite(v):
                return None
            out.append(v)
        return out or None
    return None
