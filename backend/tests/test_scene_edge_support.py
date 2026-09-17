"""能力↔场景可实现性回归（审计 §5）：目录标记 + 明确可操作报错。

审计列出「选了必失败」的场景（Agent 端无对应模型族实现）。此处在场景目录输出
`edge_supported` 标记，并在能力校验时给出「该场景需要模型族 X，设备仅支持 Y」。

模型族集合的来源为 `scene/contract.py` 的 `AGENT_MODEL_FAMILIES`（Agent 能力契约），
B1 批已接线 obb/iseg，故本测试同步覆盖这两个族。
"""

from app.api.v1.module_video.edge import orchestrator as orch
from app.api.v1.module_video.scene.catalog import (
    EDGE_ADVERTISED_MODEL_FAMILIES,
    SCENES,
    is_edge_implementable,
    unsupported_scene_codes,
)
from app.api.v1.module_video.scene.contract import AGENT_MODEL_FAMILIES


def test_edge_advertised_families_are_agent_reported():
    """目录宣称的模型族必须与 Agent 能力契约一致（含 B1 的 obb/iseg）。"""
    base = {"det", "cls", "face", "pedestrian_attribute", "ocr", "lpr", "tracking"}
    assert base <= AGENT_MODEL_FAMILIES
    assert {"obb", "iseg"} <= AGENT_MODEL_FAMILIES
    assert EDGE_ADVERTISED_MODEL_FAMILIES == AGENT_MODEL_FAMILIES


def test_unsupported_scene_list_is_enumerated():
    """审计 §5 列出的不可落地场景必须被准确标记。

    注：审计报告写「20 项」，原清点为 19 项；B1 接线 obb/iseg 后 OBB_DET/I_SEG
    转为可落地，故不可落地清单收敛为 17 项，下表为逐项枚举后的权威清单。
    """
    expected = {
        "ACTION_CLS", "ACTION_SKELETON", "FALL", "SMOKE_PHONE", "CLIMB", "HAND_GESTURE",
        "SEM_AREA", "SAM_SEG", "FACE_REC", "STRANGER", "FACE_ATTR",
        "FACE_ANTISPOOF", "FACE_LANDMARK", "DOC_TABLE", "BARCODE", "DEPTH_SAFE",
        "REID_TRACK",
    }
    assert set(unsupported_scene_codes()) == expected
    assert len(unsupported_scene_codes()) == 17
    assert len(SCENES) == 40
    assert len([c for c, s in SCENES.items() if is_edge_implementable(s)]) == 23
    # B1 明确解锁：obb/iseg 场景不再被能力校验拒绝
    assert "OBB_DET" not in unsupported_scene_codes()
    assert "I_SEG" not in unsupported_scene_codes()


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
    assert by_code["OBB_DET"]["edge_supported"] is True
    assert by_code["I_SEG"]["edge_supported"] is True
    assert by_code["FALL"]["edge_supported"] is False
    assert all("edge_supported" in s for s in items)
