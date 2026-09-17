"""B3 叶子测试：face_match / stranger（人脸底库余弦比对）与 prompt_segment（交互分割）。

契约（Agent 侧并行实现）：
- face_rec：``objects[].embedding = [float, ...]``（L2 归一化，512/1024 维，新增字段）；
- sam：归一化 bbox 对象 + ``label="segment"``（无新增事件字段）。

所有缺失/非法输入一律不命中且不抛异常（延续既有 fail-closed 约定）。
"""
from app.api.v1.module_video.edge.consumer import normalize_edge_event
from app.api.v1.module_video.face_gallery.store import face_gallery_store
from app.api.v1.module_video.inference.service import _match_conditions, explain_conditions

# 3 维单位向量，便于手算余弦（1.0 / 0.0 / -1.0）
E_Y = [1.0, 0.0, 0.0]
E_X = [0.0, 1.0, 0.0]
E_NEG = [-1.0, 0.0, 0.0]

GALLERY = [
    {"id": 1, "name": "张三", "person_no": "A001", "model_key": "w600k_r50", "embedding": E_Y},
    {"id": 2, "name": "李四", "person_no": "A002", "model_key": "w600k_r50", "embedding": E_X},
]
# 单条目底库：用于验证「最大相似度」之外的纯算子语义（避免第二条目抬高最大值）
G_Y = [{"id": 1, "name": "张三", "embedding": E_Y}]


def _det(embedding=None, label="face", conf=0.9, cx=0.5, cy=0.5):
    """构造一条归一化人脸检测框；embedding 为 None 时不携带。"""
    d = {
        "label": label,
        "confidence": conf,
        "bbox": {"x": cx - 0.05, "y": cy - 0.05, "width": 0.1, "height": 0.1},
    }
    if embedding is not None:
        d["embedding"] = embedding
    return d


def _eval(leaf, dets, gallery=None):
    return _match_conditions(leaf, dets, face_gallery=gallery)


FACE_MATCH = {"subject": "face_match", "op": "gte", "value": 0.6}
STRANGER = {"subject": "stranger", "op": "lt", "value": 0.6}


# ------------------------------------------------------------------ face_match
def test_face_match_hit_and_miss():
    assert _eval(FACE_MATCH, [_det(E_Y)], GALLERY) is True  # cos=1.0
    assert _eval(FACE_MATCH, [_det(E_X)], GALLERY) is True  # cos=1.0（命中李四）
    assert _eval(FACE_MATCH, [_det(E_NEG)], GALLERY) is False  # cos=-1.0


def test_face_match_threshold_can_be_unnormalized():
    """未归一化向量也按余弦（整体缩放不敏感），阈值判定不受模长影响。"""
    assert _eval(FACE_MATCH, [_det([3.0, 0.0, 0.0])], G_Y) is True
    assert _eval(FACE_MATCH, [_det([0.1, 0.9, 0.0])], G_Y) is False


def test_face_match_operators_are_configurable():
    assert _eval({"subject": "face_match", "op": "gt", "value": 1.0}, [_det(E_Y)], G_Y) is False
    assert _eval({"subject": "face_match", "op": "gte", "value": 1.0}, [_det(E_Y)], G_Y) is True
    # 反向检测 vs 底库 E_Y → 余弦 -1.0
    assert _eval({"subject": "face_match", "op": "lte", "value": -1.0}, [_det(E_NEG)], G_Y) is True
    assert _eval({"subject": "face_match", "op": "lt", "value": -0.5}, [_det(E_NEG)], G_Y) is True
    assert _eval({"subject": "face_match", "op": "eq", "value": 1.0}, [_det(E_Y)], G_Y) is True


def test_face_match_empty_gallery_fails_closed():
    assert _eval(FACE_MATCH, [_det(E_Y)], []) is False
    # 走进程内缓存：显式清空，避免受其他用例（底库 API）留下的缓存影响
    face_gallery_store.clear()
    assert _eval(FACE_MATCH, [_det(E_Y)], None) is False


def test_face_match_without_embedding_fails_closed():
    assert _eval(FACE_MATCH, [_det()], GALLERY) is False
    assert _eval(FACE_MATCH, [], GALLERY) is False
    assert _eval(FACE_MATCH, ["dirty"], GALLERY) is False


def test_face_match_dimension_mismatch_fails_closed():
    """跨模型/不同维度的特征不可比（避免误判命中）。"""
    assert _eval(FACE_MATCH, [_det([1.0, 0.0])], GALLERY) is False


def test_face_match_invalid_embedding_fails_closed():
    assert _eval(FACE_MATCH, [_det([])], GALLERY) is False
    assert _eval(FACE_MATCH, [_det([1.0, "x", 0.0])], GALLERY) is False
    assert _eval(FACE_MATCH, [_det([float("nan"), 0.0, 0.0])], GALLERY) is False
    assert _eval(FACE_MATCH, [_det([0.0, 0.0, 0.0])], GALLERY) is False  # 零向量


def test_face_match_invalid_op_or_value_fails_closed():
    assert _eval({"subject": "face_match", "value": 0.6}, [_det(E_Y)], GALLERY) is False
    assert _eval({"subject": "face_match", "op": ">=", "value": 0.6}, [_det(E_Y)], GALLERY) is False
    assert _eval({"subject": "face_match", "op": "gte", "value": "x"}, [_det(E_Y)], GALLERY) is False


def test_face_match_label_region_and_confidence_filters():
    assert _eval({**FACE_MATCH, "min_confidence": 0.95}, [_det(E_Y, conf=0.9)], GALLERY) is False
    assert _eval({**FACE_MATCH, "min_confidence": 0.5}, [_det(E_Y, conf=0.9)], GALLERY) is True
    assert _eval({**FACE_MATCH, "min_confidence": "x"}, [_det(E_Y)], GALLERY) is False
    assert _eval({**FACE_MATCH, "label": "person"}, [_det(E_Y)], GALLERY) is False
    square = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert _eval({**FACE_MATCH, "region": square}, [_det(E_Y, cx=0.5, cy=0.5)], GALLERY) is True
    assert _eval({**FACE_MATCH, "region": square}, [_det(E_Y, cx=0.9, cy=0.9)], GALLERY) is False


# -------------------------------------------------------------------- stranger
def test_stranger_hit_and_miss():
    """op=lt：低于阈值＝未命中底库（陌生人）。"""
    assert _eval(STRANGER, [_det(E_NEG)], GALLERY) is True
    assert _eval(STRANGER, [_det(E_Y)], GALLERY) is False


def test_stranger_empty_gallery_and_no_embedding_fail_closed():
    """无底库无法判定陌生人；无特征同样不命中。"""
    assert _eval(STRANGER, [_det(E_NEG)], []) is False
    assert _eval(STRANGER, [_det()], GALLERY) is False


def test_face_match_store_default_path_and_similarity():
    """未显式传底库时读取进程内缓存（face_rec 事件 → 叶子命中的端到端形态）。"""
    try:
        face_gallery_store.replace(GALLERY)
        assert _eval(FACE_MATCH, [_det(E_X)]) is True
        assert _eval(STRANGER, [_det(E_NEG)]) is True
        face_gallery_store.clear()
        assert _eval(FACE_MATCH, [_det(E_X)]) is False
    finally:
        face_gallery_store.clear()


def test_face_match_detail_is_explainable():
    ok, hits = explain_conditions(FACE_MATCH, [_det(E_Y)], face_gallery=GALLERY)
    assert ok is True
    assert hits[0]["subject"] == "face_match"
    assert "face sim 1.00" in hits[0]["detail"]
    ok2, hits2 = explain_conditions(FACE_MATCH, [_det(E_NEG)], face_gallery=GALLERY)
    assert ok2 is False and hits2 == []


# ------------------------------------------------------------------ 事件透传
def test_normalize_edge_event_passes_embedding():
    """objects 分支必须透传 embedding（face_rec 新增字段）。"""
    ev = {
        "event_id": "b3-1",
        "camera_id": 7,
        "objects": [
            {
                "label": "face",
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "embedding": E_Y,
            }
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert det["embedding"] == E_Y


def test_normalize_edge_event_merges_embedding_into_existing_detections():
    """同时含 detections 与 objects 时，embedding 按索引并入。"""
    ev = {
        "event_id": "b3-2",
        "camera_id": 7,
        "detections": [{"label": "face", "confidence": 0.9, "bbox": {}}],
        "objects": [
            {
                "label": "face",
                "confidence": 0.9,
                "bbox": {},
                "embedding": E_X,
            }
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert det["embedding"] == E_X


def test_face_rec_default_rule_matches_edge_emitted_embedding():
    """FACE_REC 默认规则须命中 face_rec 事件实际形态（bbox + embedding）。"""
    from app.api.v1.module_video.scene.catalog import get_scene
    from app.api.v1.module_video.scene.compile import compile_rule

    scene = get_scene("FACE_REC")
    rule = compile_rule("FACE_REC", {"similarity_threshold": 0.6}, scene.default_rule)
    ev = {
        "camera_id": 7,
        "objects": [
            {
                "label": "face",
                "confidence": 0.95,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "embedding": E_X,
            }
        ],
    }
    dets = normalize_edge_event(ev)["detections"]
    assert _eval(rule, dets, GALLERY) is True
    assert _eval(rule, [_det(E_NEG)], GALLERY) is False


# -------------------------------------------------------------- prompt_segment
def _seg(label="segment", conf=0.9, x=0.4, y=0.4, w=0.2, h=0.2):
    return {
        "label": label,
        "confidence": conf,
        "bbox": {"x": x, "y": y, "width": w, "height": h},
    }


def test_prompt_segment_exists_without_point():
    leaf = {"subject": "prompt_segment", "label": "segment"}
    assert _eval(leaf, [_seg()]) is True
    assert _eval(leaf, [_seg(label="person")]) is False
    assert _eval(leaf, []) is False


def test_prompt_segment_point_containment():
    leaf = {"subject": "prompt_segment", "label": "segment", "point": [[0.5, 0.5], [0.6, 0.6]]}
    assert _eval(leaf, [_seg(x=0.4, y=0.4)]) is True  # 框 0.4~0.6 含 (0.5,0.5)
    assert _eval(leaf, [_seg(x=0.0, y=0.0)]) is False  # 框 0~0.2 不含提示点
    # 扁平单点写法同样支持
    assert _eval({**leaf, "point": [0.5, 0.5]}, [_seg(x=0.4, y=0.4)]) is True
    # 多提示点：任一落在框内即命中
    assert _eval({**leaf, "point": [[0.9, 0.9], [0.5, 0.5]]}, [_seg(x=0.4, y=0.4)]) is True


def test_prompt_segment_invalid_point_fails_closed():
    for bad in ("bad", [], [[0.5]], [[0.5, "x"]], 123):
        assert _eval({"subject": "prompt_segment", "point": bad}, [_seg()]) is False, bad


def test_prompt_segment_confidence_and_region_filters():
    assert _eval({"subject": "prompt_segment", "min_confidence": 0.95}, [_seg(conf=0.9)]) is False
    assert _eval({"subject": "prompt_segment", "min_confidence": 0.5}, [_seg(conf=0.9)]) is True
    square = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
    assert _eval({"subject": "prompt_segment", "region": square}, [_seg(x=0.4, y=0.4)]) is True
    assert _eval({"subject": "prompt_segment", "region": square}, [_seg(x=0.9, y=0.9)]) is False
    # 缺 bbox 时无法判定点包含 → 不命中
    assert _eval({"subject": "prompt_segment", "point": [0.5, 0.5]}, [{"label": "segment"}]) is False


def test_sam_seg_default_rule_matches_edge_emitted_shape():
    """SAM_SEG 默认规则（注入提示点后）须命中 sam 事件实际形态。"""
    from app.api.v1.module_video.scene.catalog import get_scene
    from app.api.v1.module_video.scene.compile import compile_rule

    scene = get_scene("SAM_SEG")
    # 未配置提示点：仅要求存在 label=segment 的分割目标
    default_rule = compile_rule("SAM_SEG", {}, scene.default_rule)
    assert _eval(default_rule, [_seg()]) is True
    assert _eval(default_rule, [_seg(label="person")]) is False
    # 配置提示点：要求点落在分割框内
    with_point = compile_rule(
        "SAM_SEG", {"prompt_point": [[0.5, 0.5], [0.6, 0.6]]}, scene.default_rule
    )
    assert _eval(with_point, [_seg(x=0.4, y=0.4)]) is True
    assert _eval(with_point, [_seg(x=0.0, y=0.0)]) is False


def test_prompt_segment_detail_is_explainable():
    ok, hits = explain_conditions(
        {"subject": "prompt_segment", "label": "segment", "point": [[0.5, 0.5]]}, [_seg()]
    )
    assert ok is True
    assert hits[0]["subject"] == "prompt_segment"
    assert "segment" in hits[0]["detail"]
