"""能力↔场景可实现性回归（审计 §5）：目录标记 + 明确可操作报错。

审计列出「选了必失败」的场景（Agent 端无对应模型族实现）。此处在场景目录输出
`edge_supported` 标记，并在能力校验时给出「该场景需要模型族 X，设备仅支持 Y」。
"""
from app.api.v1.module_video.edge import orchestrator as orch
from app.api.v1.module_video.scene.catalog import (
    EDGE_ADVERTISED_MODEL_FAMILIES,
    SCENES,
    is_edge_implementable,
    unsupported_scene_codes,
)


def test_edge_advertised_families_are_agent_reported():
    caps = {"det", "cls", "face", "pedestrian_attribute", "ocr", "lpr", "tracking"}
    assert EDGE_ADVERTISED_MODEL_FAMILIES == caps


def test_unsupported_scene_list_is_enumerated():
    """审计 §5 列出的不可落地场景必须被准确标记。

    注：审计报告写「20 项」，实际清点为 19 项（目录共 40 个场景，21 个可落地）；
    下表为逐项枚举后的权威清单。
    """
    expected = {
        "ACTION_CLS", "ACTION_SKELETON", "FALL", "SMOKE_PHONE", "CLIMB", "HAND_GESTURE",
        "I_SEG", "SEM_AREA", "SAM_SEG", "OBB_DET", "FACE_REC", "STRANGER", "FACE_ATTR",
        "FACE_ANTISPOOF", "FACE_LANDMARK", "DOC_TABLE", "BARCODE", "DEPTH_SAFE",
        "REID_TRACK",
    }
    assert set(unsupported_scene_codes()) == expected
    assert len(unsupported_scene_codes()) == 19
    assert len(SCENES) == 40
    assert len([c for c, s in SCENES.items() if is_edge_implementable(s)]) == 21


def test_scene_capability_failure_is_actionable():
    class _PoseAlg:
        runtime_config = {}
        scene_type = "FALL"
        algorithm_type = "FALL"

    caps = {"model_families": ["det", "cls"], "backends": ["ort"], "max_channels": 4}
    ok, reason = orch.EdgeOrchestrator._check_capability(caps, _PoseAlg(), 0)
    assert ok is False
    assert "FALL" in reason and "pose" in reason and "det" in reason


def test_scene_catalog_api_marks_edge_support(test_client, auth_headers):
    resp = test_client.get("/api/v1/video/scene/catalog", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    by_code = {s["code"]: s for s in items}
    assert by_code["DET_ZONE"]["edge_supported"] is True
    assert by_code["FALL"]["edge_supported"] is False
    assert all("edge_supported" in s for s in items)
