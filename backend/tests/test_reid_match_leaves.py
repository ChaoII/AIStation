"""B4 叶子测试：reid_match（跨镜底库余弦比对）与底库 kind 隔离。

契约（Agent 侧并行实现）：
- reid 模型输出 ``objects[].embedding = [float, ...]``（256 维，L2 归一化，
  ``embedding_encoding="f16b64"``）——与 face_rec 的 embedding 是**同一事件字段**；
- 云端靠底库 ``kind`` 区分用途：face_match/stranger 只查 ``kind="face"``、
  reid_match 只查 ``kind="reid"``，两类嵌入严格隔离（不靠字段区分）。

所有缺失/非法输入一律不命中且不抛异常（延续既有 fail-closed 约定）。
"""
from app.api.v1.module_video.edge.consumer import normalize_edge_event
from app.api.v1.module_video.edge.embedding_codec import encode_embedding_f16_b64
from app.api.v1.module_video.face_gallery.store import face_gallery_store
from app.api.v1.module_video.inference.service import _match_conditions, explain_conditions

# 3 维单位向量，便于手算余弦（1.0 / 0.0 / -1.0）
E_Y = [1.0, 0.0, 0.0]
E_X = [0.0, 1.0, 0.0]
E_NEG = [-1.0, 0.0, 0.0]

REID_GALLERY = [
    {"id": 11, "name": "行人甲", "person_no": "P001", "kind": "reid",
     "model_key": "osnet_x1_0", "embedding": E_Y},
    {"id": 12, "name": "行人乙", "person_no": "P002", "kind": "reid",
     "model_key": "osnet_x1_0", "embedding": E_X},
]
FACE_GALLERY = [
    {"id": 21, "name": "张三", "kind": "face", "model_key": "w600k_r50", "embedding": E_Y},
]
# 同一向量在两类底库各一条：用于锁定 kind 隔离（不得互相命中）
MIXED = FACE_GALLERY + REID_GALLERY


def _det(embedding=None, label="person", conf=0.9, cx=0.5, cy=0.5):
    """构造一条归一化检测框；embedding 为 None 时不携带。"""
    d = {
        "label": label,
        "confidence": conf,
        "bbox": {"x": cx - 0.05, "y": cy - 0.05, "width": 0.1, "height": 0.1},
    }
    if embedding is not None:
        d["embedding"] = embedding
    return d


def _eval(leaf, dets, gallery=None):
    return _match_conditions(leaf, dets, reid_gallery=gallery)


REID_MATCH = {"subject": "reid_match", "op": "gte", "value": 0.6}


# ------------------------------------------------------------------ reid_match
def test_reid_match_hit_and_miss():
    assert _eval(REID_MATCH, [_det(E_Y)], REID_GALLERY) is True  # cos=1.0
    assert _eval(REID_MATCH, [_det(E_X)], REID_GALLERY) is True  # cos=1.0（命中乙）
    assert _eval(REID_MATCH, [_det(E_NEG)], REID_GALLERY) is False  # cos=-1.0


def test_reid_match_threshold_and_operators_are_configurable():
    # 单条目底库（仅 E_Y）才能观测到纯算子语义（避免第二条目抬高最大值）
    single = [REID_GALLERY[0]]
    assert _eval({"subject": "reid_match", "op": "gt", "value": 1.0}, [_det(E_Y)], single) is False
    assert _eval({"subject": "reid_match", "op": "gte", "value": 1.0}, [_det(E_Y)], single) is True
    # 反向检测（余弦 -1.0）
    assert _eval({"subject": "reid_match", "op": "lte", "value": -1.0}, [_det(E_NEG)], single) is True
    assert _eval({"subject": "reid_match", "op": "lt", "value": -0.5}, [_det(E_NEG)], single) is True


def test_reid_match_fail_closed_cases():
    # 空底库 / 无 embedding / 脏检测 / 非法 op / 非法 value / 维度不可比
    assert _eval(REID_MATCH, [_det(E_Y)], []) is False
    assert _eval(REID_MATCH, [_det()], REID_GALLERY) is False
    assert _eval(REID_MATCH, [], REID_GALLERY) is False
    assert _eval(REID_MATCH, ["dirty"], REID_GALLERY) is False
    assert _eval({"subject": "reid_match", "value": 0.6}, [_det(E_Y)], REID_GALLERY) is False
    assert _eval({"subject": "reid_match", "op": ">=", "value": 0.6}, [_det(E_Y)], REID_GALLERY) is False
    assert _eval({"subject": "reid_match", "op": "gte", "value": "x"}, [_det(E_Y)], REID_GALLERY) is False
    assert _eval(REID_MATCH, [_det([1.0, 0.0])], REID_GALLERY) is False  # 维度不一致
    assert _eval(REID_MATCH, [_det([])], REID_GALLERY) is False
    assert _eval(REID_MATCH, [_det([0.0, 0.0, 0.0])], REID_GALLERY) is False  # 零向量


def test_reid_match_label_region_and_confidence_filters():
    assert _eval({**REID_MATCH, "min_confidence": 0.95}, [_det(E_Y, conf=0.9)], REID_GALLERY) is False
    assert _eval({**REID_MATCH, "min_confidence": 0.5}, [_det(E_Y, conf=0.9)], REID_GALLERY) is True
    assert _eval({**REID_MATCH, "label": "car"}, [_det(E_Y)], REID_GALLERY) is False
    square = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert _eval({**REID_MATCH, "region": square}, [_det(E_Y, cx=0.5, cy=0.5)], REID_GALLERY) is True
    assert _eval({**REID_MATCH, "region": square}, [_det(E_Y, cx=0.9, cy=0.9)], REID_GALLERY) is False


def test_reid_match_detail_is_explainable():
    ok, hits = explain_conditions(REID_MATCH, [_det(E_Y)], reid_gallery=REID_GALLERY)
    assert ok is True
    assert hits[0]["subject"] == "reid_match"
    assert "reid sim 1.00" in hits[0]["detail"]
    ok2, hits2 = explain_conditions(REID_MATCH, [_det(E_NEG)], reid_gallery=REID_GALLERY)
    assert ok2 is False and hits2 == []


# ------------------------------------------------------------- kind 底库隔离
def test_face_and_reid_galleries_are_isolated():
    """缓存内人脸（kind=face，E_Y）与跨镜（kind=reid，E_X）两类底库严格隔离。

    ``face_match`` 只读 ``snapshot(kind="face")``、``reid_match`` 只读 ``snapshot(kind="reid")``，
    故同一事件 embedding 不可能跨类型误命中（不靠 embedding 字段区分）。
    """
    try:
        face_gallery_store.replace(
            [
                {"id": 21, "name": "张三", "kind": "face", "embedding": E_Y},
                {"id": 11, "name": "行人", "kind": "reid", "embedding": E_X},
            ]
        )
        face_leaf = {"subject": "face_match", "op": "gte", "value": 0.6}
        # face 叶子：E_Y 命中（人脸底库），E_X 不命中（E_X 属跨镜底库）
        assert _match_conditions(face_leaf, [_det(E_Y)]) is True
        assert _match_conditions(face_leaf, [_det(E_X)]) is False
        # reid 叶子：E_X 命中（跨镜底库），E_Y 不命中（E_Y 属人脸底库）
        assert _match_conditions(REID_MATCH, [_det(E_X)]) is True
        assert _match_conditions(REID_MATCH, [_det(E_Y)]) is False
    finally:
        face_gallery_store.clear()


def test_store_default_path_filters_by_kind():
    """未显式传底库时读进程内缓存，且按 kind 过滤（缓存混合两类也不串味）。"""
    try:
        face_gallery_store.replace(MIXED)
        face_leaf = {"subject": "face_match", "op": "gte", "value": 0.6}
        # face 叶子读缓存只看到 kind=face 的 E_Y，不含 reid 的 E_X
        assert _match_conditions(face_leaf, [_det(E_Y)]) is True
        assert _match_conditions(face_leaf, [_det(E_X)]) is False
        # reid 叶子读缓存只看到 kind=reid，命中 E_X 不命中 E_Y 之外？E_Y 也在 reid 底库
        assert _match_conditions(REID_MATCH, [_det(E_X)]) is True
    finally:
        face_gallery_store.clear()


# ------------------------------------------------- 事件透传（f16b64 与 reid）
def test_normalize_edge_event_decodes_reid_f16b64_embedding():
    """reid 以 f16b64 上报的 embedding 必须被解码为 float 向量（与人脸同字段）。"""
    ev = {
        "event_id": "b4-1",
        "camera_id": 7,
        "objects": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "embedding": encode_embedding_f16_b64(E_Y),
                "embedding_encoding": "f16b64",
            }
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert len(det["embedding"]) == 3
    assert abs(det["embedding"][0] - 1.0) < 1e-3
    assert abs(det["embedding"][1]) < 1e-3


# ------------------------------------------------ 维度无关（Agent 实测 512-d）
# Agent 报告：提供的 OSNet x0.25 实测输出 **512 维**（非下载方案预估的 256 维）。
# 云侧 reid_match / 底库必须**维度无关**：只要求两向量等长，按实际长度比对/存储。
REID_512_A = [1.0] + [0.0] * 511
REID_512_B = [0.0, 1.0] + [0.0] * 510
REID_GALLERY_512 = [
    {"id": 31, "name": "512维行人", "kind": "reid", "embedding": REID_512_A},
]


def test_reid_match_is_dimension_agnostic_for_512d():
    """512 维向量（OSNet 实测维度）必须与 3 维用例同语义命中/不命中。"""
    assert len(REID_512_A) == 512
    assert _eval(REID_MATCH, [_det(REID_512_A)], REID_GALLERY_512) is True  # cos=1
    assert _eval(REID_MATCH, [_det(REID_512_B)], REID_GALLERY_512) is False  # cos=0
    # 512 维检测 vs 3 维底库 → 维度不可比，fail-closed（不得因维度差异误命中或抛异常）
    assert _eval(REID_MATCH, [_det(REID_512_A)], REID_GALLERY) is False


def test_reid_gallery_stores_actual_512_dimension():
    """底库按实际向量长度记录 dimension（512），不硬编码 256。"""
    try:
        face_gallery_store.replace(
            [{"id": 31, "name": "512维行人", "kind": "reid", "embedding": REID_512_A}]
        )
        entries = face_gallery_store.snapshot(kind="reid")
        assert len(entries) == 1
        assert entries[0]["dimension"] == 512
        # 未显式传底库时，reid 叶子读取缓存亦维度无关
        assert _match_conditions(REID_MATCH, [_det(REID_512_A)]) is True
    finally:
        face_gallery_store.clear()


def test_reid_track_default_rule_matches_edge_emitted_shape():
    """REID_TRACK 默认规则须命中 reid 事件实际形态（bbox + embedding）。"""
    from app.api.v1.module_video.scene.catalog import get_scene
    from app.api.v1.module_video.scene.compile import compile_rule

    scene = get_scene("REID_TRACK")
    rule = compile_rule("REID_TRACK", {"similarity_threshold": 0.6}, scene.default_rule)
    ev = {
        "camera_id": 7,
        "objects": [
            {
                "label": "person",
                "confidence": 0.95,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "embedding": E_X,
            }
        ],
    }
    dets = normalize_edge_event(ev)["detections"]
    assert _eval(rule, dets, REID_GALLERY) is True
    assert _eval(rule, [_det(E_NEG)], REID_GALLERY) is False
