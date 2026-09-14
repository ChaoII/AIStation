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
_IMPLEMENTED_LEAF_KEYS = {
    "attribute": "field",
    "text_match": "regex",
    "ocr_label": "contains",
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
            assert required in leaf, f"{code} 的 {subject} 叶子缺少 {required} 键"


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
