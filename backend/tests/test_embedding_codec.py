"""人脸嵌入紧凑编码（f16b64）测试：跨仓契约、解码正确性、向后兼容、体积上界。

契约（与 Agent 侧 ``application/aistation_agent/event_bus.cpp`` 对齐）：
- ``objects[].embedding_encoding = "f16b64"``；
- ``objects[].embedding`` = base64(小端 IEEE-754 float16 序列)；
- 无 ``embedding_encoding`` 且 ``embedding`` 为数值数组 = 旧格式原始 float 向量（透传）；
- Agent 侧按置信度 Top-N（默认 8）限制携带嵌入的对象数，约束最坏事件体积。

黄金向量 ``ADgAtAA8AAAANA==`` 为 ``[0.5, -0.25, 1.0, 0.0, 0.25]`` 的
Python ``struct.pack('<5e', ...)`` + base64 结果，同时被 Agent 侧 C++ 用例锁定，
用于跨语言（C++ ↔ Python）编码一致性对拍。
"""
import base64
import json
import math
import struct

import pytest

from app.api.v1.module_video.edge.consumer import normalize_edge_event
from app.api.v1.module_video.edge.embedding_codec import (
    F16_B64,
    MAX_EMBEDDING_DIM,
    MAX_EMBEDDINGS_PER_EVENT,
    decode_embedding,
    encode_embedding_f16_b64,
)
from app.api.v1.module_video.inference.service import _match_conditions

GOLDEN_VEC = [0.5, -0.25, 1.0, 0.0, 0.25]
GOLDEN_B64 = "ADgAtAA8AAAANA=="

E_X = [0.0, 1.0, 0.0]
GALLERY = [{"id": 1, "name": "李四", "embedding": E_X}]


def _unit_512(seed: int) -> list[float]:
    """确定性伪随机 512-d 单位向量（避免依赖 numpy，保证可复现）。"""
    state = seed
    vals: list[float] = []
    for _ in range(512):
        state = (1103515245 * state + 12345) % (2**31)
        vals.append((state / 2**31) * 2.0 - 1.0)
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb)


# ------------------------------------------------------------------- 编码
def test_encode_matches_cross_language_golden():
    """黄金向量对拍：C++/Python 编码必须逐字节一致。"""
    assert encode_embedding_f16_b64(GOLDEN_VEC) == GOLDEN_B64
    # 独立验证黄金串确由标准库 struct + base64 生成
    assert base64.b64encode(struct.pack("<5e", *GOLDEN_VEC)).decode() == GOLDEN_B64


def test_decode_golden_returns_float32_vector():
    assert decode_embedding(GOLDEN_B64, F16_B64) == pytest.approx(GOLDEN_VEC, abs=1e-3)


def test_512d_round_trip_preserves_cosine():
    """512-d 编码-解码后余弦相似度必须接近 1（float16 精度损失可接受）。"""
    vec = _unit_512(7)
    decoded = decode_embedding(encode_embedding_f16_b64(vec), F16_B64)
    assert decoded is not None and len(decoded) == 512
    assert _cosine(vec, decoded) > 0.9999


# ------------------------------------------------------------------- 解码失败
def test_decode_rejects_invalid_inputs():
    assert decode_embedding("", F16_B64) is None
    assert decode_embedding("not-base64!!", F16_B64) is None
    assert decode_embedding("ADgA", F16_B64) is None  # base64 合法但字节数为奇数
    assert decode_embedding(GOLDEN_B64, None) is None  # 字符串但未声明编码
    assert decode_embedding(GOLDEN_B64, "f32b64") is None  # 未知编码
    assert decode_embedding(123, F16_B64) is None
    assert decode_embedding(None, F16_B64) is None
    # NaN/Inf 编码后必须被拒（避免污染相似度计算）
    nan_b64 = base64.b64encode(struct.pack("<2e", float("nan"), 1.0)).decode()
    inf_b64 = base64.b64encode(struct.pack("<2e", float("inf"), 1.0)).decode()
    assert decode_embedding(nan_b64, F16_B64) is None
    assert decode_embedding(inf_b64, F16_B64) is None


# ------------------------------------------------------------------- 向后兼容
def test_decode_raw_float_array_pass_through():
    """旧格式（原始数值数组、无编码声明）必须原样透传。"""
    assert decode_embedding([1, 0, 0], None) == [1.0, 0.0, 0.0]
    assert decode_embedding([0.5, -0.25], "") == [0.5, -0.25]
    # 声明了编码却给数组 → 契约不一致，拒绝
    assert decode_embedding([1.0, 0.0], F16_B64) is None
    # 数组含非数值/非有限值 → 拒绝
    assert decode_embedding([1.0, "x"], None) is None
    assert decode_embedding([float("nan")], None) is None
    assert decode_embedding([], None) is None


# ------------------------------------------------------- 事件归一化集成
def test_normalize_edge_event_decodes_f16b64():
    ev = {
        "event_id": "enc-1",
        "camera_id": 7,
        "objects": [
            {
                "label": "face",
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "embedding": encode_embedding_f16_b64(E_X),
                "embedding_encoding": F16_B64,
            }
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert det["embedding"] == pytest.approx(E_X, abs=1e-3)


def test_normalize_edge_event_merges_decoded_f16b64_into_detections():
    ev = {
        "event_id": "enc-2",
        "camera_id": 7,
        "detections": [{"label": "face", "confidence": 0.9, "bbox": {}}],
        "objects": [
            {
                "label": "face",
                "confidence": 0.9,
                "bbox": {},
                "embedding": encode_embedding_f16_b64(E_X),
                "embedding_encoding": F16_B64,
            }
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert det["embedding"] == pytest.approx(E_X, abs=1e-3)


def test_normalize_edge_event_keeps_raw_float_array_backward_compatible():
    ev = {
        "event_id": "enc-3",
        "objects": [
            {"label": "face", "confidence": 0.9, "bbox": {}, "embedding": E_X},
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert det["embedding"] == E_X


def test_decoded_embedding_reaches_face_match_leaf():
    """端到端：f16b64 事件 → normalize → face_match 命中底库。"""
    ev = {
        "camera_id": 7,
        "objects": [
            {
                "label": "face",
                "confidence": 0.95,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "embedding": encode_embedding_f16_b64(E_X),
                "embedding_encoding": F16_B64,
            }
        ],
    }
    dets = normalize_edge_event(ev)["detections"]
    leaf = {"subject": "face_match", "op": "gte", "value": 0.6}
    assert _match_conditions(leaf, dets, face_gallery=GALLERY) is True


# ------------------------------------------------- 云侧二次上限（防御性）
def test_normalize_rejects_oversize_embedding_dimension():
    """超过维度上限的嵌入必须被丢弃（不信任 Agent 载荷大小）。"""
    huge = [0.1] * (MAX_EMBEDDING_DIM + 1)
    ev = {
        "event_id": "huge-dim",
        "objects": [{"label": "face", "confidence": 0.9, "bbox": {}, "embedding": huge}],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert "embedding" not in det
    # 上限内的向量仍正常保留
    ok = [0.1] * MAX_EMBEDDING_DIM
    ev2 = {
        "event_id": "ok-dim",
        "objects": [{"label": "face", "confidence": 0.9, "bbox": {}, "embedding": ok}],
    }
    assert "embedding" in normalize_edge_event(ev2)["detections"][0]


def test_normalize_caps_embeddings_per_event_by_confidence():
    """单事件嵌入对象数超上限时按置信度保留 Top-N，其余仅丢弃嵌入字段。"""
    total = MAX_EMBEDDINGS_PER_EVENT + 5
    objects = [
        {"label": "face", "confidence": i / 100.0, "bbox": {}, "embedding": E_X}
        for i in range(total)
    ]
    dets = normalize_edge_event({"event_id": "many", "objects": objects})["detections"]
    assert len(dets) == total  # 检测对象本身不得被删除
    kept = [d for d in dets if "embedding" in d]
    assert len(kept) == MAX_EMBEDDINGS_PER_EVENT
    # 保留的是置信度最高的那些（丢弃了最低的 5 个）
    assert min(d["confidence"] for d in kept) == pytest.approx(5 / 100.0)


def test_normalize_small_event_embeddings_untouched():
    """未超限的正常事件不受二次上限影响。"""
    objects = [
        {"label": "face", "confidence": 0.9, "bbox": {}, "embedding": E_X}
        for _ in range(3)
    ]
    dets = normalize_edge_event({"event_id": "small", "objects": objects})["detections"]
    assert all("embedding" in d for d in dets)


# ------------------------------------------------------------- 体积上界
def test_payload_size_bounded_by_encoding_and_cap():
    """24 张脸的原始 float32 事件 ≈ 250 KB；f16b64 + Top-8 后应 < 16 KB。"""
    vecs = [_unit_512(i) for i in range(24)]
    raw_bytes = sum(len(json.dumps(v, separators=(",", ":"))) for v in vecs)
    assert raw_bytes > 240 * 1024  # 原始体积确认问题存在

    per_face = len(encode_embedding_f16_b64(vecs[0]))
    assert per_face == 1368  # base64(512*2 bytes)

    # 模拟 Agent 侧 Top-N=8 编码后的事件（含 24 个 bbox 对象的其它字段）
    objects = []
    for i, v in enumerate(vecs):
        obj = {
            "label": "face",
            "label_id": 0,
            "confidence": 0.9,
            "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        }
        if i < 8:
            obj["embedding"] = encode_embedding_f16_b64(v)
            obj["embedding_encoding"] = F16_B64
        objects.append(obj)
    payload = json.dumps(
        {"event_id": "size", "camera_id": 1, "schema_version": 2, "objects": objects},
        separators=(",", ":"),
    )
    assert len(payload) < 16 * 1024
