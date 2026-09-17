"""能力↔场景可实现性回归（审计 §5）：目录标记 + 明确可操作报错。

审计列出「选了必失败」的场景（Agent 端无对应模型族实现）。此处在场景目录输出
`edge_supported` 标记，并在能力校验时给出「该场景需要模型族 X，设备仅支持 Y」。

模型族集合的来源为 `scene/contract.py` 的 `AGENT_MODEL_FAMILIES`（Agent 能力契约），
B1 批已接线 obb/iseg，故本测试同步覆盖这两个族。
"""

import os
import pathlib
import re

import pytest

from app.api.v1.module_video.edge import orchestrator as orch
from app.api.v1.module_video.edge.service import capability_satisfies
from app.api.v1.module_video.scene.catalog import (
    EDGE_ADVERTISED_MODEL_FAMILIES,
    SCENES,
    is_edge_implementable,
    unsupported_scene_codes,
)
from app.api.v1.module_video.scene.contract import (
    AGENT_MODEL_FAMILIES,
    canonical_pipeline_type,
)

# Agent `application/aistation_agent/capability.cpp::detect_capabilities()` 上报的族（逐项枚举）。
# 若工作区可读 ModelDeploy 仓库，下方对拍测试会直接解析该文件，防止本常量与 Agent 漂移。
_AGENT_REPORTED_FAMILIES = {
    "det", "cls", "face", "pedestrian_attribute", "ocr", "lpr", "tracking", "obb", "iseg",
}


def _read_agent_capability_families() -> set[str] | None:
    """从 ModelDeploy 的 capability.cpp 解析上报族集合（仓库不可读时返回 None）。"""
    for base in (os.environ.get("MODELDEPLOY_DIR", ""), r"E:\CLionProjects\ModelDeploy"):
        if not base:
            continue
        path = pathlib.Path(base) / "application" / "aistation_agent" / "capability.cpp"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"json families\s*=\s*json::array\(\{([^}]*)\}\)", text)
        assert m, "capability.cpp 未匹配到 model_families 数组，解析规则需更新"
        return {s.strip().strip('"') for s in m.group(1).split(",") if s.strip()}
    return None


def test_agent_capability_reported_families_match_contract():
    """跨仓一致：云契约族集合 = Agent 上报族集合（枚举常量，无 obb/iseg 漂移）。"""
    assert AGENT_MODEL_FAMILIES == _AGENT_REPORTED_FAMILIES
    assert {"obb", "iseg"} <= AGENT_MODEL_FAMILIES


def test_agent_capability_cpp_has_no_family_drift():
    """直接解析 Agent capability.cpp 对拍（无该仓库时跳过，CI 亦安全）。"""
    actual = _read_agent_capability_families()
    if actual is None:
        pytest.skip("ModelDeploy 仓库不可读，跳过 capability.cpp 对拍")
    assert actual == _AGENT_REPORTED_FAMILIES, (
        f"Agent 上报族与云契约枚举不一致：AgentOnly={sorted(actual - _AGENT_REPORTED_FAMILIES)}, "
        f"CloudOnly={sorted(_AGENT_REPORTED_FAMILIES - actual)}"
    )
    assert actual == set(AGENT_MODEL_FAMILIES)


def test_pipeline_type_aliases_cover_agent_normalization():
    """pipeline type 规范名与 Agent normalize_model_type 接受集对齐（seg/iseg/obb）。"""
    assert canonical_pipeline_type("obb") == "obb"
    assert canonical_pipeline_type("iseg") == "iseg"
    assert canonical_pipeline_type("seg") == "iseg"
    assert canonical_pipeline_type("instance_seg") == "iseg"


def test_capability_satisfies_normalizes_legacy_family_names():
    """设备上报旧族名 face_detection 时，对规范族 face 的要求不得误拒。"""
    caps = {"model_families": ["face_detection"], "backends": ["ort"], "max_channels": 4}
    ok, reason = capability_satisfies(caps, {"model_families": ["face"]})
    assert ok is True, reason
    ok2, reason2 = capability_satisfies(caps, {"model_family": "face"})
    assert ok2 is True, reason2


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
