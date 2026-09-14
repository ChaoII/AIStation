"""场景注册表（任务类型目录）测试。"""
from fastapi.testclient import TestClient

from app.api.v1.module_video.scene.catalog import SCENES, get_scene, list_scenes

# spec §3 规定的完整场景集合（40 个），用于防止场景被静默删除
_EXPECTED_SCENE_CODES = (
    "DET_ZONE", "LINE_CROSS", "LOITER", "GATHER", "OVERCROWD", "ABSENT",
    "ILLEGAL_PARK", "ABANDON", "FIRE_SMOKE", "TRAFFIC_DET", "PED_ATTR",
    "SCENE_CLS", "DEFECT_CLS", "ACTION_CLS", "ACTION_SKELETON",
    "FALL", "SMOKE_PHONE", "CLIMB", "NO_MASK", "HAND_GESTURE",
    "I_SEG", "SEM_AREA", "SAM_SEG", "OBB_DET",
    "FACE_DET", "FACE_REC", "STRANGER", "FACE_ATTR", "FACE_ANTISPOOF",
    "FACE_LANDMARK", "FACE_CROWD",
    "LPR", "LPR_LIST", "OCR_TEXT", "METER_OCR", "DOC_TABLE", "BARCODE",
    "DEPTH_SAFE", "REID_TRACK", "DEPLOY_TRACK",
)


def test_catalog_contains_full_spec_set():
    """目录必须完整覆盖 spec §3 的 40 个场景，防止静默删除。"""
    assert len(SCENES) >= 40
    assert set(SCENES) == set(_EXPECTED_SCENE_CODES)


def test_catalog_contains_core_scenes():
    for code in ("DET_ZONE", "LINE_CROSS", "GATHER", "PED_ATTR", "OCR_TEXT", "LPR", "FACE_REC"):
        assert code in SCENES, code
        assert SCENES[code].name and SCENES[code].scene_type


def test_ped_attr_pipeline_and_params():
    s = get_scene("PED_ATTR")
    assert s is not None
    assert s.model_families == ["pedestrian_attribute"]
    roles = {p["role"] for p in s.pipeline}
    assert roles == {"det", "cls"}
    keys = {p["key"] for p in s.param_schema}
    assert {"attributes", "roi", "confidence_threshold", "cls_threshold"} <= keys
    assert s.needs_tracking is False


def test_list_scenes_filter_by_category():
    tracks = list_scenes(category="tracking")
    assert all(x.category == "tracking" for x in tracks)
    assert list_scenes()  # 非空


def test_get_scene_missing():
    assert get_scene("NOPE") is None


def _iter_rule_leaves(rule: dict):
    """深度遍历规则条件树，产出所有叶子节点（非逻辑算子节点）。"""
    stack = [rule]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        op = node.get("op")
        if op in ("and", "or", "not"):
            stack.extend(node.get("children") or [])
            continue
        yield node


def test_default_rules_text_match_leaves_use_regex_key():
    """目录默认规则的 text_match 叶子必须携带 regex 键，与推理评估器保持一致。

    评估器 `_match_conditions` 只读取 `leaf.get("regex")`，若目录误用 op/value
    写法则默认规则永远无法命中；本测试防止该不一致回归。
    """
    checked = 0
    for scene in SCENES.values():
        for leaf in _iter_rule_leaves(scene.default_rule):
            if leaf.get("subject") != "text_match":
                continue
            checked += 1
            assert "regex" in leaf, f"{scene.code} 的 text_match 叶子缺少 regex 键"
            # 旧式 op/value 写法不会被评估器识别，必须禁止
            assert "op" not in leaf, f"{scene.code} 的 text_match 叶子不应带 op 键"
            assert "value" not in leaf, f"{scene.code} 的 text_match 叶子不应带 value 键"
    # 非空守卫：至少校验到 OCR_TEXT 与 METER_OCR 两处，避免测试空跑
    assert checked >= 2


# 推理评估器已实现的叶子 subject → 必填键（见 inference/service.py:_match_conditions）
# 值为 None 表示该叶子没有必填键。
_IMPLEMENTED_LEAF_KEYS = {
    "attribute": "field",
    "text_match": "regex",
    "ocr_label": "contains",
    "object_present": None,
    "zone_enter": None,
    "count": "value",
    # SP4-b 时序叶子：依赖跨事件状态（inference/temporal.py），时间由事件 ts 注入
    "dwell": "min_sec",
    "count_window": "window_sec",
    "absence": "gap_sec",
    "line_cross": None,
}

# 各叶子受求值器支持的比较算子（与 inference/service.py 保持一致）
_LEAF_OPS = {
    "attribute": {"lt", "gt", "le", "ge", "eq"},
    "count": {">=", ">", "<=", "<", "=="},
    "count_window": {">=", ">", "<=", "<", "=="},
}


def test_lpr_default_rules_use_implemented_leaves():
    """LPR/LPR_LIST 默认规则叶子必须落到评估器已实现的 subject，并携带对应必填键。"""
    for code in ("LPR", "LPR_LIST"):
        scene = get_scene(code)
        assert scene is not None
        leaves = list(_iter_rule_leaves(scene.default_rule))
        assert leaves, f"{code} 默认规则应至少含一个叶子"
        for leaf in leaves:
            subject = leaf.get("subject")
            assert subject in _IMPLEMENTED_LEAF_KEYS, f"{code} 使用未实现叶子 subject={subject!r}"
            required = _IMPLEMENTED_LEAF_KEYS[subject]
            if required is not None:
                assert required in leaf, f"{code} 的 {subject} 叶子缺少 {required} 键"


def test_face_det_default_rule_uses_implemented_leaf():
    """FACE_DET 默认规则必须落到评估器已实现的 object_present 叶子。"""
    scene = get_scene("FACE_DET")
    assert scene is not None
    leaves = list(_iter_rule_leaves(scene.default_rule))
    assert leaves, "FACE_DET 默认规则应至少含一个叶子"
    assert [leaf.get("subject") for leaf in leaves] == ["object_present"]
    for leaf in leaves:
        assert leaf.get("subject") in _IMPLEMENTED_LEAF_KEYS


def test_default_rules_implemented_leaves_are_evaluable():
    """凡使用已实现叶子（object_present/zone_enter/count/attribute/text_match/ocr_label）
    的默认规则，都必须与求值器键名/算子/取值完全一致，确保可直接评估：

    - subject 必须在已实现集合内；
    - 该叶子的必填键必须存在；
    - region 不得是符号化字符串（必须省略，或为合法多边形点列）；
    - attribute/count 的 op 必须受支持，value 必须为数值。
    """
    checked: set[str] = set()
    for scene in SCENES.values():
        for leaf in _iter_rule_leaves(scene.default_rule):
            subject = leaf.get("subject")
            if subject not in _IMPLEMENTED_LEAF_KEYS:
                continue
            checked.add(subject)
            required = _IMPLEMENTED_LEAF_KEYS[subject]
            if required is not None:
                assert required in leaf, f"{scene.code} 的 {subject} 叶子缺少 {required} 键"
            region = leaf.get("region")
            assert not isinstance(region, str), (
                f"{scene.code} 的 {subject} 叶子不应使用符号化 region={region!r}"
            )
            if region is not None:
                assert isinstance(region, (list, tuple)) and len(region) >= 3, (
                    f"{scene.code} 的 {subject} 叶子 region 必须是多边形点列"
                )
            if subject in _LEAF_OPS:
                assert leaf.get("op") in _LEAF_OPS[subject], (
                    f"{scene.code} 的 {subject} 叶子 op={leaf.get('op')!r} 不受求值器支持"
                )
            if subject in ("attribute", "count", "count_window"):
                value = leaf.get("value")
                assert isinstance(value, (int, float)) and not isinstance(value, bool), (
                    f"{scene.code} 的 {subject} 叶子 value 必须为数值，实际 {value!r}"
                )
    # 非空守卫：核心叶子（含时序叶子）至少各有场景覆盖，避免测试空跑
    assert {"object_present", "count", "attribute", "text_match"} <= checked
    assert {"dwell", "count_window", "absence", "line_cross"} <= checked


def test_line_cross_default_rule_uses_line_cross_leaf():
    """LINE_CROSS 默认规则必须落到已实现的 line_cross 叶子，且不写符号化 line。"""
    scene = get_scene("LINE_CROSS")
    assert scene is not None
    leaves = list(_iter_rule_leaves(scene.default_rule))
    assert [leaf.get("subject") for leaf in leaves] == ["line_cross"]
    for leaf in leaves:
        assert not isinstance(leaf.get("line"), str), "line 不得为符号化字符串"
        assert leaf.get("dir", "A2B") in ("A2B", "B2A", "both")


def test_temporal_default_rules_use_temporal_leaves():
    """时序场景默认规则必须落到 SP4-b 已实现的时序叶子。

    - LOITER / ILLEGAL_PARK → dwell；
    - ABSENT → absence；
    - GATHER → count_window（滑窗去重计数）。
    时序叶子依赖跨事件状态（需检测携带 track_id 形成轨迹），因此默认规则不得再写
    符号化 region（如 "roi"）或字符串阈值（如 "min_sec"）——评估器只认数值键。
    """
    expected = {
        "LOITER": "dwell",
        "ILLEGAL_PARK": "dwell",
        "ABSENT": "absence",
        "GATHER": "count_window",
    }
    for code, subject in expected.items():
        scene = get_scene(code)
        assert scene is not None, code
        leaves = list(_iter_rule_leaves(scene.default_rule))
        assert leaves, f"{code} 默认规则应至少含一个叶子"
        assert [leaf.get("subject") for leaf in leaves] == [subject], code


def test_gather_param_schema_uses_window_sec():
    """GATHER 滑窗参数必须与规则口径一致（window_sec / 秒），不得再用帧数 window。"""
    scene = get_scene("GATHER")
    assert scene is not None
    keys = {p["key"] for p in scene.param_schema}
    assert "window_sec" in keys
    assert "window" not in keys
    param = next(p for p in scene.param_schema if p["key"] == "window_sec")
    assert param["default"] == 5
    leaf = next(iter(_iter_rule_leaves(scene.default_rule)))
    assert leaf.get("subject") == "count_window"
    assert leaf.get("window_sec") == param["default"]


def test_catalog_api_lists_and_filters_category(test_client: TestClient, auth_headers: dict):
    resp = test_client.get("/api/v1/video/scene/catalog", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == len(SCENES)

    resp = test_client.get(
        "/api/v1/video/scene/catalog?category=tracking", headers=auth_headers
    )
    items = resp.json()["data"]["items"]
    assert items and all(i["category"] == "tracking" for i in items)


def test_catalog_api_detail_and_missing_404(test_client: TestClient, auth_headers: dict):
    resp = test_client.get("/api/v1/video/scene/catalog/PED_ATTR", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["code"] == "PED_ATTR"

    resp = test_client.get("/api/v1/video/scene/catalog/NOPE", headers=auth_headers)
    assert resp.status_code == 404
