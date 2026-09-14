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
