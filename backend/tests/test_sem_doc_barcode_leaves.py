"""B2b 新叶子测试：region_ratio（语义占比）/ code_match（码值匹配）与事件字段透传。

契约（Agent 侧并行实现，复用既有事件字段）：
- sem：整帧对象 ``attributes={类别: 面积占比}`` → 云端 ``region_ratio`` 叶子比较占比；
- doc / barcode：结构摘要与解码码值均复用 ``objects[].text`` → 云端用 ``text_match`` /
  ``code_match`` 判定；
- face_landmark：``objects[].keypoints``（见 test_keypoint_geometry_leaf.py）。

所有缺失/非法输入一律不命中且不抛异常（延续既有 fail-closed 约定）。
"""
from app.api.v1.module_video.edge.consumer import normalize_edge_event
from app.api.v1.module_video.inference.service import _match_conditions, explain_conditions

SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _det(attributes=None, text=None, keypoints=None, label="object", cx=0.5, cy=0.5):
    """构造一条归一化检测框；可选字段为 None 时不携带。"""
    d = {
        "label": label,
        "confidence": 0.9,
        "bbox": {"x": cx - 0.05, "y": cy - 0.05, "width": 0.1, "height": 0.1},
    }
    if attributes is not None:
        d["attributes"] = attributes
    if text is not None:
        d["text"] = text
    if keypoints is not None:
        d["keypoints"] = keypoints
    return d


def _eval(leaf, dets):
    return _match_conditions(leaf, dets)


# ------------------------------------------------------- region_ratio（sem）
RATIO = {"subject": "region_ratio", "op": "ge", "value": 0.3}


def test_ratio_hit_and_miss():
    assert _eval(RATIO, [_det(attributes={"person": 0.35})]) is True
    assert _eval(RATIO, [_det(attributes={"person": 0.30})]) is True  # ge 含边界
    assert _eval(RATIO, [_det(attributes={"person": 0.29})]) is False


def test_ratio_operators_are_configurable():
    d = [_det(attributes={"person": 0.4})]
    assert _eval({"subject": "region_ratio", "op": "gt", "value": 0.4}, d) is False
    assert _eval({"subject": "region_ratio", "op": "gt", "value": 0.3}, d) is True
    assert _eval({"subject": "region_ratio", "op": "lt", "value": 0.5}, d) is True
    assert _eval({"subject": "region_ratio", "op": "le", "value": 0.4}, d) is True
    assert _eval({"subject": "region_ratio", "op": "eq", "value": 0.4}, d) is True


def test_ratio_any_category_without_label_filter():
    """未指定类别时对 attributes 全部键取「任一满足」。"""
    assert _eval(RATIO, [_det(attributes={"sky": 0.1, "road": 0.5})]) is True
    assert _eval(RATIO, [_det(attributes={"sky": 0.1, "road": 0.2})]) is False


def test_ratio_labels_filter_selects_categories():
    leaf = {**RATIO, "labels": ["road", "building"]}
    assert _eval(leaf, [_det(attributes={"road": 0.5, "sky": 0.9})]) is True
    assert _eval(leaf, [_det(attributes={"sky": 0.9})]) is False
    single = {**RATIO, "label": "road"}
    assert _eval(single, [_det(attributes={"road": 0.4})]) is True
    assert _eval(single, [_det(attributes={"sky": 0.9})]) is False


def test_ratio_missing_or_invalid_attributes_fails_closed():
    assert _eval(RATIO, [_det()]) is False
    assert _eval(RATIO, [_det(attributes={})]) is False
    assert _eval(RATIO, [_det(attributes={"person": "high"})]) is False
    assert _eval(RATIO, [_det(attributes={"person": float("inf")})]) is False
    assert _eval(RATIO, []) is False
    assert _eval(RATIO, ["dirty"]) is False


def test_ratio_invalid_op_or_value_fails_closed():
    assert _eval({"subject": "region_ratio", "value": 0.3}, [_det(attributes={"p": 0.9})]) is False
    assert _eval({"subject": "region_ratio", "op": ">=", "value": 0.3}, [_det(attributes={"p": 0.9})]) is False
    assert _eval({"subject": "region_ratio", "op": "ge", "value": "x"}, [_det(attributes={"p": 0.9})]) is False


def test_ratio_detail_is_explainable():
    ok, hits = explain_conditions(RATIO, [_det(attributes={"person": 0.35})])
    assert ok is True
    assert hits[0]["subject"] == "region_ratio"
    assert "ratio" in hits[0]["detail"] and "0.35" in hits[0]["detail"]
    ok2, hits2 = explain_conditions(RATIO, [_det(attributes={"person": 0.1})])
    assert ok2 is False and hits2 == []


# --------------------------------------------------------- code_match（barcode）
def test_code_match_in_list_exact():
    leaf = {"subject": "code_match", "op": "in", "code_list": ["QR-1", "QR-2"]}
    assert _eval(leaf, [_det(text="QR-1")]) is True
    assert _eval(leaf, [_det(text=" QR-2 ")]) is True  # 去空白后精确比对
    assert _eval(leaf, [_det(text="QR-3")]) is False
    assert _eval(leaf, [_det(text="QR-1-extra")]) is False


def test_code_match_empty_list_matches_any_non_empty_code():
    """未配置名单（默认）→ 识别到任意非空码值即命中。"""
    leaf = {"subject": "code_match", "op": "in"}
    assert _eval(leaf, [_det(text="ANY-CODE")]) is True
    assert _eval(leaf, [_det(text="   ")]) is False
    assert _eval(leaf, [_det()]) is False


def test_code_match_regex_op():
    leaf = {"subject": "code_match", "op": "regex", "regex": "^QR-\\d+$"}
    assert _eval(leaf, [_det(text="QR-123")]) is True
    assert _eval(leaf, [_det(text="XX-123")]) is False
    # 非法/危险正则安全处理为不命中
    assert _eval({"subject": "code_match", "op": "regex", "regex": "("}, [_det(text="QR")]) is False


def test_code_match_invalid_input_fails_closed():
    assert _eval({"subject": "code_match", "op": "eq", "code_list": ["A"]}, [_det(text="A")]) is False
    assert _eval({"subject": "code_match", "op": "in", "code_list": "A"}, [_det(text="A")]) is False
    assert _eval({"subject": "code_match", "op": "in"}, []) is False


def test_code_match_detail_is_explainable():
    leaf = {"subject": "code_match", "op": "in", "code_list": ["QR-1"]}
    ok, hits = explain_conditions(leaf, [_det(text="QR-1")])
    assert ok is True
    assert hits[0]["subject"] == "code_match"
    assert "QR-1" in hits[0]["detail"]


# ------------------------------------------------- 事件字段透传（sem/doc/barcode）
def test_normalize_edge_event_passes_attributes_keypoints_text():
    """objects 分支必须同时透传 attributes（sem/face_attr）/ keypoints（pose/landmark）/ text（ocr/doc/barcode）。"""
    ev = {
        "event_id": "b2b-1",
        "camera_id": 7,
        "objects": [
            {
                "label": "semantic",
                "confidence": 0.9,
                "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                "attributes": {"road": 0.42, "sky": 0.18},
                "keypoints": [[0.5, 0.5, 0.9]],
                "text": "QR-1",
            }
        ],
    }
    out = normalize_edge_event(ev)
    det = out["detections"][0]
    assert det["attributes"] == {"road": 0.42, "sky": 0.18}
    assert det["keypoints"] == [[0.5, 0.5, 0.9]]
    assert det["text"] == "QR-1"


def test_normalize_edge_event_merges_new_fields_into_existing_detections():
    """同时含 detections 与 objects 时，attributes/keypoints/text 按索引并入。"""
    ev = {
        "event_id": "b2b-2",
        "camera_id": 7,
        "detections": [{"label": "object", "confidence": 0.9, "bbox": {}}],
        "objects": [
            {
                "label": "object",
                "confidence": 0.9,
                "bbox": {},
                "attributes": {"road": 0.5},
                "keypoints": [[0.1, 0.1, 0.8]],
                "text": "CODE-9",
            }
        ],
    }
    det = normalize_edge_event(ev)["detections"][0]
    assert det["attributes"] == {"road": 0.5}
    assert det["keypoints"] == [[0.1, 0.1, 0.8]]
    assert det["text"] == "CODE-9"


def test_sem_default_rule_matches_edge_emitted_shape():
    """SEM_AREA 默认规则须命中 sem 事件实际形态（整帧对象 + attributes 占比）。"""
    from app.api.v1.module_video.scene.catalog import get_scene

    rule = get_scene("SEM_AREA").default_rule
    ev = {
        "camera_id": 7,
        "objects": [
            {
                "label": "semantic",
                "confidence": 1.0,
                "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
                "attributes": {"road": 0.62},
            }
        ],
    }
    assert _eval(rule, normalize_edge_event(ev)["detections"]) is True
    assert _eval(rule, [_det(attributes={"road": 0.1})]) is False


def test_doc_table_default_rule_matches_text_event():
    """DOC_TABLE 默认规则（text_match）须命中携带结构摘要文本的对象。"""
    from app.api.v1.module_video.scene.catalog import get_scene

    rule = get_scene("DOC_TABLE").default_rule
    assert _eval(rule, [_det(text="<table><tr><td>A</td></tr></table>")]) is True
    assert _eval(rule, [_det()]) is False


def test_barcode_default_rule_matches_decoded_text():
    """BARCODE 默认规则（code_match, 空名单）须命中任意非空码值。"""
    from app.api.v1.module_video.scene.catalog import get_scene

    rule = get_scene("BARCODE").default_rule
    assert _eval(rule, [_det(text="QR-1")]) is True
    assert _eval(rule, [_det()]) is False
