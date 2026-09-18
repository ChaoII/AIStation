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
# 姿态切片：Agent 侧已上报 pose。
# B2a 人脸属性/活体/深度、B2b 语义分割/人脸关键点/文档/条码、B3 交互分割/人脸特征：
# Agent 均已如实上报。
# B4 手部/跨镜：Agent（HEAD 6b5c524）已接线并如实上报 hand/reid。
# B5 视频动作/骨架动作：Agent 工作区已接线 action/action_skeleton（normalize_model_type、
# pipeline/inference_engine、capability.cpp 均更新）。
# **严格对拍**：B5 已删除临时「在途族」放行清单，云契约族集合必须与 Agent 实际上报**逐一相等**。
_AGENT_REPORTED_FAMILIES = {
    "det", "cls", "face", "pedestrian_attribute", "ocr", "lpr", "tracking", "obb", "iseg",
    "pose", "face_attr", "face_as", "depth",
    "sem", "face_landmark", "doc", "barcode",
    "sam", "face_rec",
    "hand", "reid",
    "action", "action_skeleton",
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
    """跨仓一致：云契约族集合 = Agent 上报族集合（含 B1~B5 各族）。

    严格相等（无在途放行清单）。B5 的 action/action_skeleton 已由 Agent 接线并上报，
    故 ACTION_CLS/ACTION_SKELETON 一并转为可落地（40/40）。
    """
    assert AGENT_MODEL_FAMILIES == _AGENT_REPORTED_FAMILIES
    assert {"obb", "iseg"} <= AGENT_MODEL_FAMILIES
    assert "pose" in AGENT_MODEL_FAMILIES
    assert {"face_attr", "face_as", "depth"} <= AGENT_MODEL_FAMILIES
    assert {"sem", "face_landmark", "doc", "barcode"} <= AGENT_MODEL_FAMILIES
    assert {"sam", "face_rec"} <= AGENT_MODEL_FAMILIES
    assert {"hand", "reid"} <= AGENT_MODEL_FAMILIES
    assert {"action", "action_skeleton"} <= AGENT_MODEL_FAMILIES


def test_agent_capability_cpp_has_no_family_drift():
    """直接解析 Agent capability.cpp 对拍（无该仓库时跳过，CI 亦安全）。

    B5 恢复**严格相等**：已无「在途族」放行清单，Agent 实际上报集必须与本测试枚举
    逐项相等，且等于云契约 ``AGENT_MODEL_FAMILIES``。任一方向多出/缺少都会失败，
    从而阻止云契约私自扩族或 Agent 静默漏报。
    """
    actual = _read_agent_capability_families()
    if actual is None:
        pytest.skip("ModelDeploy 仓库不可读，跳过 capability.cpp 对拍")
    assert actual == _AGENT_REPORTED_FAMILIES, (
        f"Agent 上报族与本测试枚举不一致：AgentOnly="
        f"{sorted(actual - _AGENT_REPORTED_FAMILIES)}, "
        f"EnumOnly={sorted(_AGENT_REPORTED_FAMILIES - actual)}"
    )
    assert actual == set(AGENT_MODEL_FAMILIES), (
        f"Agent 上报族与云契约不一致：AgentOnly={sorted(actual - set(AGENT_MODEL_FAMILIES))}, "
        f"ContractOnly={sorted(set(AGENT_MODEL_FAMILIES) - actual)}"
    )


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
    转为可落地；姿态切片声明 pose 族后 FALL/SMOKE_PHONE/CLIMB 亦转为可落地；
    B2a 声明 face_attr/face_as/depth 后 FACE_ATTR/FACE_ANTISPOOF/DEPTH_SAFE 亦转为可落地；
    B2b 声明 sem/face_landmark/doc/barcode 后 SEM_AREA/FACE_LANDMARK/DOC_TABLE/BARCODE 亦转为可落地；
    B3 声明 sam/face_rec 后 SAM_SEG/FACE_REC/STRANGER 亦转为可落地；
    B4 声明 hand/reid 后 HAND_GESTURE/REID_TRACK 亦转为可落地；
    B5 声明 action/action_skeleton 后 ACTION_CLS/ACTION_SKELETON 亦转为可落地，
    故不可落地清单清空（**40/40 全部可落地**）。
    """
    expected: set[str] = set()
    assert set(unsupported_scene_codes()) == expected
    assert len(unsupported_scene_codes()) == 0
    assert len(SCENES) == 40
    assert len([c for c, s in SCENES.items() if is_edge_implementable(s)]) == 40
    # B1 明确解锁：obb/iseg 场景不再被能力校验拒绝
    assert "OBB_DET" not in unsupported_scene_codes()
    assert "I_SEG" not in unsupported_scene_codes()
    # 姿态切片：pose 族已声明 → 三个姿态场景可落地（HAND_GESTURE 由 hand 族落地）
    for code in ("FALL", "SMOKE_PHONE", "CLIMB"):
        assert code not in unsupported_scene_codes()
    # B2a：face_attr/face_as/depth 族已声明 → 三个新场景可落地
    for code in ("FACE_ATTR", "FACE_ANTISPOOF", "DEPTH_SAFE"):
        assert code not in unsupported_scene_codes()
    # B2b：sem/face_landmark/doc/barcode 族已声明 → 四个新场景可落地
    for code in ("SEM_AREA", "FACE_LANDMARK", "DOC_TABLE", "BARCODE"):
        assert code not in unsupported_scene_codes()
    # B3：sam/face_rec 族已声明 → 交互分割/人脸识别/陌生人可落地
    for code in ("SAM_SEG", "FACE_REC", "STRANGER"):
        assert code not in unsupported_scene_codes()
    # B4：hand/reid 族已声明 → 手势/跨镜重识别可落地
    assert "HAND_GESTURE" not in unsupported_scene_codes()
    assert "REID_TRACK" not in unsupported_scene_codes()
    # B5：action/action_skeleton 族已上报 → 视频动作/骨架动作可落地（全部 40 个）
    assert "ACTION_CLS" not in unsupported_scene_codes()
    assert "ACTION_SKELETON" not in unsupported_scene_codes()


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
    # 姿态切片：pose 族已声明 → FALL 可落地
    assert by_code["FALL"]["edge_supported"] is True
    # B4：hand 族已声明 → HAND_GESTURE 可落地
    assert by_code["HAND_GESTURE"]["edge_supported"] is True
    # B2a：face_attr/face_as/depth 族已声明 → 三个新场景可落地
    for code in ("FACE_ATTR", "FACE_ANTISPOOF", "DEPTH_SAFE"):
        assert by_code[code]["edge_supported"] is True, code
    # B2b：sem/face_landmark/doc/barcode 族已声明 → 四个新场景可落地
    for code in ("SEM_AREA", "FACE_LANDMARK", "DOC_TABLE", "BARCODE"):
        assert by_code[code]["edge_supported"] is True, code
    # B3：sam/face_rec 族已声明 → 三个新场景可落地
    for code in ("SAM_SEG", "FACE_REC", "STRANGER"):
        assert by_code[code]["edge_supported"] is True, code
    # B4：reid 族已声明 → REID_TRACK 可落地
    assert by_code["REID_TRACK"]["edge_supported"] is True
    # B5：action/action_skeleton 族已上报 → 两个动作场景可落地
    assert by_code["ACTION_CLS"]["edge_supported"] is True
    assert by_code["ACTION_SKELETON"]["edge_supported"] is True
    assert all("edge_supported" in s for s in items)
