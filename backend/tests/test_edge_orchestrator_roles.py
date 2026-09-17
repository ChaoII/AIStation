"""编排器按目录管线下发全部模型角色（修复 pose 等角色被静默丢弃）。

背景（姿态切片遗留缺陷）：``build_agent_task_config`` 原先只对单模型管线用目录规范
type，多角色管线（如 FALL 的 ``[_DET, _POSE]``）会退回 ``_resolve_model_type``（FALL→det），
**pose 模型永不下发**——与刚修复的分类「假可配置」同类。本测试锁定修复后的系统性不变量：

1. 目录中**每个场景**声明的 pipeline 角色都必须在 Agent TaskConfig 中有所承载
   （模型条目或顶层 tracking），不得静默丢弃；
2. FALL/CLIMB/SMOKE_PHONE 下发 det+pose；
3. 所有下发 type 的拼写与 Agent ``normalize_model_type`` 接受集一致；
4. DET_ZONE/PED_ATTR/OCR/LPR/FACE_DET 的既有配置逐字节不变（向后兼容）。
"""
from types import SimpleNamespace

import pytest

from app.api.v1.module_video.edge.orchestrator import build_agent_task_config
from app.api.v1.module_video.scene import contract
from app.api.v1.module_video.scene.catalog import SCENES

# Agent ``config_adapter.cpp::normalize_model_type`` 的规范名（identity 即为已规范拼写）。
# 仅列出 Agent 已明确接受的族/别名；未列出者（sem/depth/reid/face_rec 等）Agent 原样返回。
_AGENT_KNOWN_TYPES = {
    "detection", "classification", "face_detection", "pedestrian_attribute",
    "obb", "iseg", "pose", "ocr", "lpr",
}
# Agent 归一化表子集（用于把别名折成规范名后比较）
_AGENT_NORMALIZE = {
    "det": "detection",
    "detection": "detection",
    "cls": "classification",
    "classification": "classification",
    "face": "face_detection",
    "face_detection": "face_detection",
    "ped_attr": "pedestrian_attribute",
    "pedestrian_attribute": "pedestrian_attribute",
    "obb": "obb",
    "obb_det": "obb",
    "rotated_detection": "obb",
    "iseg": "iseg",
    "seg": "iseg",
    "instance_seg": "iseg",
    "instance_segmentation": "iseg",
    "pose": "pose",
    "pose_estimation": "pose",
    "keypoint": "pose",
    "keypoints": "pose",
    "keypoint_detection": "pose",
    "human_pose": "pose",
    "yolo_pose": "pose",
}

# Agent 侧以「单条复合模型条目」承载多阶段子模型的家族（目录可能声明多角色）。
# pedestrian_attribute：目录 [_DET,_CLS] → 单条 pedestrian_attribute；
# ocr/lpr：目录本身单角色且 type 即复合类型；
# face_rec：目录 [face_detection, face_rec]，云端整体构造两条显式条目（face_rec 携带 det_url）。
_COMPOUND_FAMILIES = {"pedestrian_attribute", "ocr", "lpr", "face_rec"}

# 依赖 keypoints 事件契约的姿态场景：目录 pipeline 为 [_DET, _POSE]
_POSE_SCENES = ("FALL", "CLIMB", "SMOKE_PHONE")


class _Cam:
    id = 7
    name = "北门"
    rtsp_url_sub = "rtsp://cam/7"
    stream_id = "cam7"


class _Task:
    id = 321
    camera_id = 7
    algorithm_id = 11
    stream_type = "SUB"
    detect_region = None
    sensitivity = 60
    schedule_json = None
    runtime_overrides = None
    params_overrides = None


def _algo(scene_code: str, **preset) -> SimpleNamespace:
    """构造归属目录场景的算法：scene_type=场景码，主模型路径固定。"""
    return SimpleNamespace(
        name=scene_code,
        algorithm_type=scene_code,
        scene_type=scene_code,
        model_path=f"/models/{scene_code.lower()}_primary.onnx",
        runtime_config={"backend": "ort", "device": "cpu"},
        preset_params=dict(preset),
    )


def _agent_types(cfg: dict) -> set[str]:
    """Agent 归一化后的下发模型 type 集合。"""
    return {_AGENT_NORMALIZE.get(m["type"], m["type"]) for m in cfg["models"]}


def _expected_agent_types(scene) -> set[str]:
    """从目录管线推导：该场景在 Agent 侧应有的模型 type 集合（track 由顶层承载，不计）。

    复合家族（如 PED_ATTR 的 det+cls）由单条复合模型承载，故直接以复合家族名为期望。
    """
    families = contract.canonical_families(scene.model_families)
    compound = {f for f in families if f in _COMPOUND_FAMILIES}
    if compound:
        return compound
    expected: set[str] = set()
    for entry in scene.pipeline:
        typ = contract.canonical_pipeline_type(entry["type"])
        if typ == "tracking":
            continue
        expected.add(typ)
    return expected


def test_pose_scenes_dispatch_det_and_pose():
    """FALL/CLIMB/SMOKE_PHONE 必须下发 det + pose，且 pose 取 pose_path。"""
    for code in _POSE_SCENES:
        cfg = build_agent_task_config(
            _Task(), _Cam(), _algo(code, pose_path="/models/pose.onnx"), events={}
        )
        assert cfg["scene_type"] == code
        by_type = {_AGENT_NORMALIZE.get(m["type"], m["type"]): m for m in cfg["models"]}
        assert "detection" in by_type, f"{code} 未下发 det：{by_type.keys()}"
        assert "pose" in by_type, f"{code} 未下发 pose（缺陷复现）：{by_type.keys()}"
        assert by_type["detection"]["url"].endswith("_primary.onnx")
        assert by_type["pose"]["url"] == "/models/pose.onnx"


def test_pose_without_explicit_path_still_dispatched():
    """未配置 pose_path 时仍下发 pose 角色（回退主模型路径），不得静默丢弃。"""
    cfg = build_agent_task_config(_Task(), _Cam(), _algo("FALL"), events={})
    by_type = {_AGENT_NORMALIZE.get(m["type"], m["type"]): m for m in cfg["models"]}
    assert "pose" in by_type
    assert by_type["pose"]["url"] == "/models/fall_primary.onnx"


def test_no_catalog_scene_pipeline_role_is_dropped():
    """系统性防线：目录中任何场景声明的 pipeline 角色都不得被编排器丢弃。"""
    for code, scene in SCENES.items():
        cfg = build_agent_task_config(_Task(), _Cam(), _algo(code), events={})
        emitted = _agent_types(cfg)
        expected = _expected_agent_types(scene)
        assert expected <= emitted, (
            f"{code} 丢弃管线角色：缺少 {sorted(expected - emitted)}，实际下发 {sorted(emitted)}"
        )
        # 管线含 track 角色时，必须由顶层 tracking 配置承载
        if any(entry["role"] == "track" for entry in scene.pipeline):
            assert "tracking" in cfg, f"{code} 含 track 角色但缺少顶层 tracking"


def test_no_scene_falls_back_to_single_det_for_multi_role_pipeline():
    """多角色管线不得退化为单条 det（原缺陷的直接形态）。"""
    for code, scene in SCENES.items():
        non_track = [e for e in scene.pipeline if contract.canonical_pipeline_type(e["type"]) != "tracking"]
        if len(non_track) < 2:
            continue
        if set(contract.canonical_families(scene.model_families)) & _COMPOUND_FAMILIES:
            continue
        cfg = build_agent_task_config(_Task(), _Cam(), _algo(code), events={})
        assert len(cfg["models"]) >= 2, f"{code} 多角色管线仅下发 {len(cfg['models'])} 条模型"


def test_emitted_types_use_agent_canonical_spelling():
    """下发 type 的拼写必须与 Agent normalize_model_type 接受集一致（无别名/大小写漂移）。"""
    for code in ("DET_ZONE", "OBB_DET", "I_SEG", "SCENE_CLS", "FALL", "CLIMB", "SMOKE_PHONE",
                 "PED_ATTR", "OCR_TEXT", "LPR", "FACE_DET"):
        cfg = build_agent_task_config(_Task(), _Cam(), _algo(code), events={})
        for model in cfg["models"]:
            typ = model["type"]
            assert _AGENT_NORMALIZE.get(typ, typ) == typ, f"{code} 下发非规范 type={typ}"
    # 逐族显式对拍 Agent 接受拼写
    assert _agent_types(build_agent_task_config(_Task(), _Cam(), _algo("OBB_DET"), events={})) == {"obb"}
    assert _agent_types(build_agent_task_config(_Task(), _Cam(), _algo("I_SEG"), events={})) == {"iseg"}
    assert _agent_types(build_agent_task_config(_Task(), _Cam(), _algo("SCENE_CLS"), events={})) == {"classification"}
    assert _agent_types(build_agent_task_config(_Task(), _Cam(), _algo("FALL"), events={})) == {
        "detection", "pose",
    }


# ── 向后兼容：既有可工作场景配置逐字节不变（对照修复前基准） ──
_BACKWARD_COMPAT = {
    "DET_ZONE": {
        "scene_type": "DET_ZONE",
        "models": [{
            "name": "DET_ZONE", "type": "detection", "backend": "ort", "device": "cpu",
            "labels": ["person"], "input_size": [640, 640], "confidence_threshold": 0.4,
            "url": "/models/det.onnx",
        }],
    },
    "PED_ATTR": {
        "scene_type": "PED_ATTR",
        "models": [{
            "name": "PED_ATTR", "type": "pedestrian_attribute", "backend": "ort", "device": "cpu",
            "labels": [], "input_size": [640, 640], "confidence_threshold": 0.4,
            "det_url": "/models/zhgd_det.onnx", "cls_url": "/models/zhgd_ml.onnx",
            "attributes": ["safety_helmet", "work_uniform"], "cls_threshold": 0.5, "password": "",
        }],
    },
    "OCR_TEXT": {
        "scene_type": "OCR_TEXT",
        "models": [{
            "name": "OCR_TEXT", "type": "ocr", "backend": "ort", "device": "cpu",
            "labels": [], "input_size": [960, 960], "confidence_threshold": 0.45,
            "det_url": "/models/ocr_det.onnx", "cls_url": "/models/ocr_cls.onnx",
            "rec_url": "/models/ocr_rec.onnx", "dict_url": "/models/ocr_dict.txt", "password": "",
        }],
    },
    "LPR": {
        "scene_type": "LPR",
        "models": [{
            "name": "LPR", "type": "lpr", "backend": "ort", "device": "cpu",
            "labels": [], "input_size": [640, 640], "confidence_threshold": 0.5,
            "det_url": "/models/lpr_det.onnx", "rec_url": "/models/lpr_rec.onnx", "password": "",
        }],
    },
    "FACE_DET": {
        "scene_type": "FACE_DET",
        "models": [{
            "name": "FACE_DET", "type": "face_detection", "backend": "ort", "device": "cpu",
            "labels": [], "input_size": [640, 640], "confidence_threshold": 0.5,
            "url": "/models/scrfd.onnx",
        }],
    },
}

_BACKWARD_COMPAT_ALGOS = {
    "DET_ZONE": _algo(
        "DET_ZONE", confidence_threshold=0.4, labels=["person"],
    ),
    "PED_ATTR": _algo(
        "PED_ATTR", cls_path="/models/zhgd_ml.onnx",
        attributes=["safety_helmet", "work_uniform"],
        confidence_threshold=0.4, cls_threshold=0.5,
    ),
    "OCR_TEXT": _algo(
        "OCR_TEXT", cls_path="/models/ocr_cls.onnx", rec_path="/models/ocr_rec.onnx",
        dict_path="/models/ocr_dict.txt", input_size=[960, 960],
    ),
    "LPR": _algo(
        "LPR", rec_path="/models/lpr_rec.onnx", input_size=[640, 640],
        confidence_threshold=0.5,
    ),
    "FACE_DET": _algo("FACE_DET", confidence_threshold=0.5),
}
# 主模型路径需与基准一致（_algo 默认按场景码生成，需显式覆盖）
_BACKWARD_COMPAT_MODEL_PATHS = {
    "DET_ZONE": "/models/det.onnx",
    "PED_ATTR": "/models/zhgd_det.onnx",
    "OCR_TEXT": "/models/ocr_det.onnx",
    "LPR": "/models/lpr_det.onnx",
    "FACE_DET": "/models/scrfd.onnx",
}


@pytest.mark.parametrize("code", sorted(_BACKWARD_COMPAT))
def test_existing_scene_configs_are_byte_identical(code):
    """DET_ZONE/PED_ATTR/OCR/LPR/FACE_DET 既有无回归：模型条目逐字段等于修复前基准。"""
    algo = _BACKWARD_COMPAT_ALGOS[code]
    algo.model_path = _BACKWARD_COMPAT_MODEL_PATHS[code]
    cfg = build_agent_task_config(_Task(), _Cam(), algo, events={})
    expected = _BACKWARD_COMPAT[code]
    assert cfg["scene_type"] == expected["scene_type"]
    assert cfg["models"] == expected["models"], f"{code} 下发模型与修复前不一致"


# ── face_rec 复合编排显式化（B3 遗留修复）──────────────────────────────────
_FACE_REC_SCENES = ("FACE_REC", "STRANGER")


@pytest.mark.parametrize("code", _FACE_REC_SCENES)
def test_face_rec_scenes_dispatch_explicit_compound_models(code):
    """FACE_REC/STRANGER 必须显式下发 face_detection + face_rec，且 face_rec 自带 det_url。

    修复前 face_rec 条目不携带检测器路径，依赖 Agent 从「同任务 face_detection 兄弟条目」
    补齐（隐式约定）；此处锁定显式构造，避免该隐式依赖回归。
    """
    algo = _algo(code, face_rec_path="/models/w600k_r50.onnx")
    det_primary = algo.model_path
    cfg = build_agent_task_config(_Task(), _Cam(), algo, events={})
    by_type = {m["type"]: m for m in cfg["models"]}
    assert set(by_type) == {"face_detection", "face_rec"}, by_type.keys()

    # 检测器：face_detection 条目取算法主模型（未显式 face_det_path 时的既有口径）
    assert by_type["face_detection"]["url"] == det_primary
    # face_rec 复合条目：检测器显式 + 嵌入模型显式（不再依赖兄弟条目 / 主模型回退）
    assert by_type["face_rec"]["det_url"] == det_primary
    assert by_type["face_rec"]["url"] == "/models/w600k_r50.onnx"
    assert by_type["face_rec"]["rec_url"] == "/models/w600k_r50.onnx"


@pytest.mark.parametrize("code", _FACE_REC_SCENES)
def test_face_rec_explicit_det_path_override(code):
    """显式 face_det_path 必须同时落到 face_detection.url 与 face_rec.det_url。"""
    algo = _algo(
        code, face_det_path="/models/scrfd.onnx", face_rec_path="/models/w600k.onnx"
    )
    cfg = build_agent_task_config(_Task(), _Cam(), algo, events={})
    by_type = {m["type"]: m for m in cfg["models"]}
    assert by_type["face_detection"]["url"] == "/models/scrfd.onnx"
    assert by_type["face_rec"]["det_url"] == "/models/scrfd.onnx"
