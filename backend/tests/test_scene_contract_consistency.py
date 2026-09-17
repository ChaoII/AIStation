"""场景目录 ↔ 能力契约 ↔ 编译层一致性回归（系统性防线）。

对应审计「UI 可选但后端必拒」这类缺陷：

1. 目录标记为「可配置（configurable）」的场景，默认规则必须能通过 ``compile_rule``——
   即运维在界面上能选中的场景一定能保存成功；
2. 不可配置场景必须给出数据驱动的中文原因（缺族/缺资产/缺分类契约/缺叶子）；
3. 目录参数必须被编译层或边缘任务配置构造消费，不允许「界面上能填、实际无效果」；
4. 默认规则引用的叶子必须已登记，且实现状态与编译层的接受/拒绝行为一致。
"""

import re

from app.api.v1.module_video.scene import contract
from app.api.v1.module_video.scene.catalog import (
    SCENES,
    configurable_scene_codes,
    get_scene,
    is_edge_implementable,
    scene_blockers,
    scene_configurability,
    scene_missing_assets,
    unimplemented_default_leaves,
)
from app.api.v1.module_video.scene.compile import (
    MODEL_CONFIG_PARAMS,
    PARAM_TO_LEAF,
    TEXT_MATCH_DERIVED_PARAMS,
    RuleCompileError,
    compile_rule,
)
from app.api.v1.module_video.scene.leaves import LEAF_CAPABILITIES

# 依赖「分类结果进入边缘事件」契约的三个场景（B2a 契约已落地，现应可配置）
_CLASSIFICATION_SCENES = {"SCENE_CLS", "DEFECT_CLS", "NO_MASK"}

# 依赖「姿态关键点进入边缘事件」契约的场景（姿态切片 + 手部 21 点手势，现应可配置）
_KEYPOINT_SCENES = {"FALL", "CLIMB", "SMOKE_PHONE", "HAND_GESTURE"}

# 依赖「人脸属性/活体分数进入边缘事件」契约的场景（B2a 契约已声明，现应可配置）
_ATTRIBUTE_SCENES = {"FACE_ATTR", "FACE_ANTISPOOF"}

# 依赖「深度值进入边缘事件」契约的场景（B2a 契约已声明，现应可配置）
_DEPTH_SCENES = {"DEPTH_SAFE"}

# B2b：语义区域占比 / 码值匹配 走新叶子或既有 text_match
_RATIO_SCENES = {"SEM_AREA"}
_CODE_SCENES = {"BARCODE"}
_TEXT_SCENES = {"DOC_TABLE"}
# B2b：人脸关键点复用 keypoint_geometry（rule=face_landmark）+ keypoints 事件契约
_LANDMARK_SCENES = {"FACE_LANDMARK"}

# B3：人脸底库比对（依赖云端 face_gallery 资产 + face_rec 模型族）
_FACE_MATCH_SCENES = {"FACE_REC", "STRANGER"}
# B3：交互分割（sam 族 + prompt_segment 叶子）
_SAM_SCENES = {"SAM_SEG"}
# B4：跨镜重识别（reid 族 + reid_gallery 资产 + reid_match 叶子）
_REID_SCENES = {"REID_TRACK"}


def _iter_leaves(rule: dict):
    """深度遍历规则条件树，产出所有叶子节点（非逻辑算子节点）。"""
    stack = [rule]
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        if node.get("op") in ("and", "or", "not"):
            stack.extend(node.get("children") or [])
            continue
        if "subject" in node:
            yield node


def _default_params(scene) -> dict:
    """目录声明的参数默认值（模拟前端按 schema 初值保存）。"""
    return {p["key"]: p["default"] for p in scene.param_schema if p.get("default") is not None}


def test_configurable_scenes_compile_default_rule():
    """凡目录允许选中的场景，默认规则必须可编译（可保存）。"""
    checked: list[str] = []
    for code, scene in SCENES.items():
        ok, reason = scene_configurability(scene)
        if not ok:
            assert reason, f"{code} 不可配置但未给出原因"
            continue
        # 不应抛 RuleCompileError（回归：SCENE_CLS/DEFECT_CLS 曾必然 400）
        compile_rule(code, _default_params(scene), scene.default_rule)
        checked.append(code)
    # static/track 叶子实现后 ABANDON/DEPLOY_TRACK 可选；B1 接线后 OBB_DET/I_SEG 可选；
    # B2a 分类事件契约落地后 SCENE_CLS/DEFECT_CLS/NO_MASK 亦转为可配置；
    # 姿态切片 keypoint_geometry 落地后 FALL/CLIMB/SMOKE_PHONE 亦转为可配置
    # （HAND_GESTURE 因 hand 族未上报 + gesture 规则未实现，仍置灰）。
    # B2b sem/face_landmark/doc/barcode 族声明后 SEM_AREA/FACE_LANDMARK/DOC_TABLE/BARCODE 亦可选。
    assert {"ABANDON", "DEPLOY_TRACK", "OBB_DET", "I_SEG"} <= set(checked)
    assert _CLASSIFICATION_SCENES <= set(checked)
    assert _KEYPOINT_SCENES <= set(checked)
    assert _ATTRIBUTE_SCENES <= set(checked)
    assert _DEPTH_SCENES <= set(checked)
    assert (_RATIO_SCENES | _CODE_SCENES | _TEXT_SCENES | _LANDMARK_SCENES) <= set(checked)
    # B3：B3 人脸底库/交互分割场景转为可配置
    assert (_FACE_MATCH_SCENES | _SAM_SCENES) <= set(checked)
    # B4：hand/reid 族 + reid_gallery 资产就绪 → HAND_GESTURE/REID_TRACK 转为可配置
    assert _KEYPOINT_SCENES <= set(checked)
    assert _REID_SCENES <= set(checked)
    assert set(checked) == set(configurable_scene_codes())
    assert len(checked) == 38


def test_unconfigurable_scenes_reason_mentions_cause():
    """置灰场景必须给出可操作原因（指明缺失模型族/资产/分类契约/叶子）。"""
    for code, scene in SCENES.items():
        ok, reason = scene_configurability(scene)
        if ok:
            assert reason == ""
            continue
        assert reason, code
        assert scene_blockers(scene), code
        missing_fams = [
            f
            for f in contract.canonical_families(scene.model_families)
            if f not in contract.AGENT_MODEL_FAMILIES
        ]
        missing_assets = scene_missing_assets(scene)
        gated = scene.requires_classification and not contract.supports_event_feature(
            "classification"
        )
        keypoint_gated = scene.requires_keypoints and not contract.supports_event_feature(
            "keypoints"
        )
        attr_gated = scene.requires_attributes and not contract.supports_event_feature(
            "face_attributes"
        )
        depth_gated = scene.requires_depth and not contract.supports_event_feature("depth")
        bad = unimplemented_default_leaves(scene)
        # 每个原因类别都必须落在 reason 文本中，保证前端提示可操作
        if missing_fams:
            assert any(f in reason for f in missing_fams), f"{code}: {reason}"
        if missing_assets:
            assert any(contract.asset_label(a) in reason for a in missing_assets), f"{code}: {reason}"
        if gated:
            assert "分类" in reason, f"{code}: {reason}"
        if keypoint_gated:
            assert "关键点" in reason, f"{code}: {reason}"
        if attr_gated:
            assert "属性" in reason, f"{code}: {reason}"
        if depth_gated:
            assert "深度" in reason, f"{code}: {reason}"
        if bad:
            assert any(leaf in reason for leaf in bad), f"{code}: {reason}"


def test_abandon_and_deploy_track_are_configurable_now():
    """static/track 叶子实现后，ABANDON/DEPLOY_TRACK 必须可配置（不再置灰）。"""
    for code in ("ABANDON", "DEPLOY_TRACK"):
        ok, reason = scene_configurability(SCENES[code])
        assert ok is True, f"{code} 仍不可配置：{reason}"


def test_classification_scenes_configurable_after_contract_lands():
    """B2a 分类事件契约已落地：三个分类场景必须可配置且默认规则可编译。

    与 Agent 侧 ``tests/test_classification_event.cpp`` 对拍——该测试证明分类模型产出的
    整帧框 + top-1 label 事件能被云端 ``object_present`` 叶子命中（无 label 命中 / label 相等命中）。
    """
    assert contract.supports_event_feature("classification") is True
    for code in _CLASSIFICATION_SCENES:
        scene = SCENES[code]
        assert scene.requires_classification is True, code
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 分类契约已落地却仍置灰：{reason}"
        compile_rule(code, _default_params(scene), scene.default_rule)


def test_classification_scenes_re_gate_without_contract(monkeypatch):
    """机制锁定：撤下分类契定位后，三个场景必须重新按「分类」原因置灰。"""
    monkeypatch.setattr(contract, "AGENT_EVENT_FEATURES", frozenset())
    try:
        for code in _CLASSIFICATION_SCENES:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 分类契约撤销后不应仍可配置"
            assert "分类" in reason, f"{code}: {reason}"
    finally:
        monkeypatch.undo()


def test_keypoint_scenes_configurable_after_contract_lands():
    """姿态契约已声明：FALL/CLIMB/SMOKE_PHONE 必须可配置且默认规则可编译为 keypoint_geometry。"""
    assert contract.supports_event_feature("keypoints") is True
    assert "pose" in contract.AGENT_MODEL_FAMILIES
    for code in _KEYPOINT_SCENES:
        scene = SCENES[code]
        assert scene.requires_keypoints is True, code
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 姿态契约已声明却仍置灰：{reason}"
        out = compile_rule(code, _default_params(scene), scene.default_rule)
        leaves = list(_iter_leaves(out))
        assert leaves and all(leaf["subject"] == "keypoint_geometry" for leaf in leaves), code


def test_keypoint_scenes_re_gate_without_contract(monkeypatch):
    """机制锁定：撤下 keypoints 事件特性后，三个姿态场景必须重新按「关键点」原因置灰。"""
    monkeypatch.setattr(contract, "AGENT_EVENT_FEATURES", frozenset())
    try:
        for code in _KEYPOINT_SCENES:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 关键点契约撤销后不应仍可配置"
            assert "关键点" in reason, f"{code}: {reason}"
    finally:
        monkeypatch.undo()


def test_face_and_depth_scenes_configurable_after_contract_lands():
    """B2a：人脸属性/活体/深度契约已声明 → FACE_ATTR/FACE_ANTISPOOF/DEPTH_SAFE 可配置且可编译。

    - FACE_ATTR/FACE_ANTISPOOF 复用既有 attribute 叶子（field 取 Agent 实际发射的属性名）；
    - DEPTH_SAFE 使用新增 distance 叶子（读取 detection.depth）。
    """
    assert contract.supports_event_feature("face_attributes") is True
    assert contract.supports_event_feature("depth") is True
    assert {"face_attr", "face_as", "depth"} <= contract.AGENT_MODEL_FAMILIES
    for code in _ATTRIBUTE_SCENES:
        scene = SCENES[code]
        assert scene.requires_attributes is True, code
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 人脸属性契约已声明却仍置灰：{reason}"
        out = compile_rule(code, _default_params(scene), scene.default_rule)
        leaves = list(_iter_leaves(out))
        assert leaves and all(leaf["subject"] == "attribute" for leaf in leaves), code
    for code in _DEPTH_SCENES:
        scene = SCENES[code]
        assert scene.requires_depth is True, code
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 深度契约已声明却仍置灰：{reason}"
        out = compile_rule(code, _default_params(scene), scene.default_rule)
        leaves = list(_iter_leaves(out))
        assert leaves and all(leaf["subject"] == "distance" for leaf in leaves), code


def test_face_and_depth_scenes_re_gate_without_contract(monkeypatch):
    """机制锁定：撤下属性/深度事件特性后，对应场景必须重新按原因置灰。"""
    monkeypatch.setattr(contract, "AGENT_EVENT_FEATURES", frozenset())
    try:
        for code in _ATTRIBUTE_SCENES:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 属性契约撤销后不应仍可配置"
            assert "属性" in reason, f"{code}: {reason}"
        for code in _DEPTH_SCENES:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 深度契约撤销后不应仍可配置"
            assert "深度" in reason, f"{code}: {reason}"
    finally:
        monkeypatch.undo()


def test_sem_landmark_doc_barcode_configurable_after_contract_lands():
    """B2b：sem/face_landmark/doc/barcode 族已声明 → 四个场景可配置且默认规则可编译。

    - SEM_AREA 用 region_ratio 叶子（读取 sem 整帧对象的 attributes 占比）；
    - FACE_LANDMARK 用 keypoint_geometry(rule=face_landmark) + keypoints 事件契约；
    - DOC_TABLE 复用 text_match（doc 结构摘要走 objects[].text）；
    - BARCODE 用 code_match（解码结果走 objects[].text）。
    """
    assert {"sem", "face_landmark", "doc", "barcode"} <= contract.AGENT_MODEL_FAMILIES
    expected = {
        "SEM_AREA": "region_ratio",
        "FACE_LANDMARK": "keypoint_geometry",
        "DOC_TABLE": "text_match",
        "BARCODE": "code_match",
    }
    for code, subject in expected.items():
        scene = SCENES[code]
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 契约已声明却仍置灰：{reason}"
        out = compile_rule(code, _default_params(scene), scene.default_rule)
        leaves = list(_iter_leaves(out))
        assert leaves and all(leaf["subject"] == subject for leaf in leaves), code
    # FACE_LANDMARK 依赖关键点事件契约，须显式声明，才能在契约回退时重新置灰
    assert SCENES["FACE_LANDMARK"].requires_keypoints is True
    assert contract.supports_event_feature("keypoints") is True
    # FACE_LANDMARK 的 min_keypoints 必须注入 keypoint_geometry.value（界面可填即生效）
    out = compile_rule("FACE_LANDMARK", {"min_keypoints": 8}, SCENES["FACE_LANDMARK"].default_rule)
    assert out["children"][0]["value"] == 8
    # SEM_AREA 的 ratio 必须注入 region_ratio.value
    out = compile_rule("SEM_AREA", {"ratio": 0.2}, SCENES["SEM_AREA"].default_rule)
    assert out["children"][0]["value"] == 0.2
    # BARCODE 的 code_list 必须注入 code_match.code_list
    out = compile_rule("BARCODE", {"code_list": ["QR-1"]}, SCENES["BARCODE"].default_rule)
    assert out["children"][0]["code_list"] == ["QR-1"]


def test_face_landmark_re_gates_without_keypoint_contract(monkeypatch):
    """机制锁定：撤下 keypoints 事件特性后，FACE_LANDMARK 必须重新按「关键点」原因置灰。"""
    monkeypatch.setattr(contract, "AGENT_EVENT_FEATURES", frozenset())
    try:
        ok, reason = scene_configurability(SCENES["FACE_LANDMARK"])
        assert ok is False
        assert "关键点" in reason, reason
    finally:
        monkeypatch.undo()


def test_sem_doc_barcode_stay_grayed_without_families(monkeypatch):
    """机制锁定：撤下 B2b 模型族后，三个场景必须重新按「缺模型族」置灰。"""
    monkeypatch.setattr(
        contract,
        "AGENT_MODEL_FAMILIES",
        contract.AGENT_MODEL_FAMILIES - {"sem", "doc", "barcode"},
    )
    try:
        for code, fam in (("SEM_AREA", "sem"), ("DOC_TABLE", "doc"), ("BARCODE", "barcode")):
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 撤下族后不应仍可配置"
            assert fam in reason, f"{code}: {reason}"
    finally:
        monkeypatch.undo()


def test_face_attr_uses_agent_emitted_attribute_names():
    """默认规则 field 必须与 Agent 实际发射的属性名一致（gender_male / liveness）。"""
    attr_leaf = SCENES["FACE_ATTR"].default_rule["children"][0]
    assert attr_leaf["subject"] == "attribute"
    assert attr_leaf["field"] == "gender_male"
    # attribute 叶子登记算子为 ge/le（非 gte/lte），默认规则必须可编译
    assert attr_leaf["op"] == "ge"
    compile_rule("FACE_ATTR", {}, SCENES["FACE_ATTR"].default_rule)

    as_leaf = SCENES["FACE_ANTISPOOF"].default_rule["children"][0]
    assert as_leaf["subject"] == "attribute"
    assert as_leaf["field"] == "liveness"
    assert as_leaf["op"] == "lt"
    compile_rule("FACE_ANTISPOOF", {}, SCENES["FACE_ANTISPOOF"].default_rule)


def test_face_antispoof_injects_liveness_threshold():
    """FACE_ANTISPOOF 的 liveness_threshold → attribute.value（界面可填即生效）。"""
    scene = get_scene("FACE_ANTISPOOF")
    out = compile_rule("FACE_ANTISPOOF", {"liveness_threshold": 0.7}, scene.default_rule)
    leaf = out["children"][0]
    assert leaf["subject"] == "attribute"
    assert leaf["field"] == "liveness"
    assert leaf["op"] == "lt"
    assert leaf["value"] == 0.7


def test_depth_safe_injects_distance_threshold_and_roi():
    """DEPTH_SAFE 的 distance_threshold → distance.value，roi → region（界面可填即生效）。"""
    scene = get_scene("DEPTH_SAFE")
    roi = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    out = compile_rule(
        "DEPTH_SAFE", {"roi": roi, "distance_threshold": 2.5}, scene.default_rule
    )
    leaf = out["children"][0]
    assert leaf["subject"] == "distance"
    assert leaf["op"] == "lt"
    assert leaf["value"] == 2.5
    assert leaf["region"] == roi


def test_hand_gesture_configurable_after_hand_family_and_gesture():
    """hand 族 + 21 点 gesture 规则落地 → HAND_GESTURE 可配置且默认规则可编译。"""
    scene = SCENES["HAND_GESTURE"]
    assert contract.has_model_family("hand") is True
    assert scene.requires_keypoints is True
    ok, reason = scene_configurability(scene)
    assert ok is True, f"HAND_GESTURE 契约已就绪却仍置灰：{reason}"
    assert scene_blockers(scene) == []
    out = compile_rule("HAND_GESTURE", _default_params(scene), scene.default_rule)
    leaf = out["children"][0]
    assert leaf["subject"] == "keypoint_geometry"
    assert leaf["rule"] == "gesture"
    # gesture 参数必须可注入（界面可填即生效）
    out2 = compile_rule("HAND_GESTURE", {"gesture": "victory"}, scene.default_rule)
    assert out2["children"][0]["gesture"] == "victory"


def test_hand_gesture_re_gates_without_hand_family(monkeypatch):
    """机制锁定：撤下 hand 族后 HAND_GESTURE 必须重新按「缺模型族」置灰。"""
    monkeypatch.setattr(
        contract, "AGENT_MODEL_FAMILIES", contract.AGENT_MODEL_FAMILIES - {"hand"}
    )
    try:
        ok, reason = scene_configurability(SCENES["HAND_GESTURE"])
        assert ok is False
        assert "hand" in reason, reason
    finally:
        monkeypatch.undo()


def test_fall_default_rule_injects_angle_threshold_and_roi():
    """FALL 的 angle_threshold → keypoint_geometry.value，roi → region（界面可填即生效）。"""
    scene = get_scene("FALL")
    roi = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    out = compile_rule("FALL", {"roi": roi, "angle_threshold": 45.0}, scene.default_rule)
    leaf = out["children"][0]
    assert leaf["subject"] == "keypoint_geometry"
    assert leaf["rule"] == "fall"
    assert leaf["op"] == ">="
    assert leaf["value"] == 45.0
    assert leaf["region"] == roi


def test_climb_default_rule_injects_line():
    """CLIMB 的 line → keypoint_geometry.line（绊线由任务参数运行时注入）。"""
    scene = get_scene("CLIMB")
    line = [[0.0, 0.5], [1.0, 0.5]]
    out = compile_rule("CLIMB", {"line": line}, scene.default_rule)
    leaf = out["children"][0]
    assert leaf["subject"] == "keypoint_geometry"
    assert leaf["rule"] == "climb"
    assert leaf["line"] == line


def test_smoke_phone_default_rule_injects_min_sec_and_distance():
    """SMOKE_PHONE 的 min_sec / hand_head_distance 必须注入叶子（否则界面可填但无效）。"""
    scene = get_scene("SMOKE_PHONE")
    out = compile_rule(
        "SMOKE_PHONE", {"min_sec": 8, "hand_head_distance": 0.1}, scene.default_rule
    )
    leaf = out["children"][0]
    assert leaf["subject"] == "keypoint_geometry"
    assert leaf["rule"] == "smoke_phone"
    assert leaf["min_sec"] == 8
    assert leaf["value"] == 0.1


def test_obb_iseg_use_canonical_pipeline_types():
    """B1：OBB_DET/I_SEG 默认规则可编译，且 pipeline type 与 Agent 归一化名一致。"""
    assert get_scene("OBB_DET").pipeline[0]["type"] == "obb"
    assert get_scene("I_SEG").pipeline[0]["type"] == "iseg"
    for code in ("OBB_DET", "I_SEG"):
        ok, reason = scene_configurability(SCENES[code])
        assert ok is True, f"{code} 应可配置：{reason}"
        out = compile_rule(code, _default_params(SCENES[code]), SCENES[code].default_rule)
        leaves = list(_iter_leaves(out))
        assert leaves and all(leaf["subject"] == "object_present" for leaf in leaves), code


def test_all_scene_pipeline_types_are_canonical():
    """目录 pipeline[].type 必须已是 Agent 侧规范名（别名已解析）。"""
    for code, scene in SCENES.items():
        for entry in scene.pipeline:
            typ = entry["type"]
            assert contract.canonical_pipeline_type(typ) == typ, (
                f"{code} pipeline type={typ} 非规范名"
            )


def test_face_family_is_canonical_with_legacy_alias():
    """族名统一为 face；face_detection 作为旧别名仍被接受（向后兼容）。"""
    for code in ("FACE_DET", "FACE_REC", "STRANGER", "FACE_ATTR", "FACE_ANTISPOOF", "FACE_LANDMARK", "FACE_CROWD"):
        families = SCENES[code].model_families
        assert "face_detection" not in families, f"{code} 仍使用旧族名 face_detection"
        assert "face" in families, code
        assert contract.canonical_families(families).count("face") == 1, code

    # 旧别名解析：声明 face_detection 的场景应等价于 face（可落地）
    from app.api.v1.module_video.scene.catalog import SceneDef

    legacy = SceneDef(
        "LEGACY_FACE", "旧族名场景", "face", "LEGACY_FACE", ["face_detection"], [],
        [], {}, False, "",
    )
    assert is_edge_implementable(legacy) is True
    assert contract.canonical_family("FACE_DETECTION") == "face"
    assert contract.canonical_families(["face_detection", "face"]) == ["face"]


def test_required_assets_gate_scenes_with_reason():
    """底库资产就绪时对应场景转为可配置；撤下资产后据实按「缺外部资产」置灰。

    B3 后人脸底库（face_gallery）已具备，FACE_REC/STRANGER 转为可配置；
    B4 后跨镜底库（reid_gallery）随 ``kind`` 列复用同一张表，REID_TRACK 亦转为可配置。
    """
    assert contract.has_asset("face_gallery") is True
    assert contract.has_asset("reid_gallery") is True
    for code in ("FACE_REC", "STRANGER"):
        scene = SCENES[code]
        assert scene.required_assets == ["face_gallery"], code
        assert scene_configurability(scene)[0] is True, code
        assert "缺外部资产" not in "；".join(scene_blockers(scene)), code

    reid = SCENES["REID_TRACK"]
    assert reid.required_assets == ["reid_gallery"]
    assert scene_configurability(reid)[0] is True
    assert "缺外部资产" not in "；".join(scene_blockers(reid))


def test_reid_track_re_gates_without_asset(monkeypatch):
    """机制锁定：撤下 reid_gallery 资产后 REID_TRACK 重新按「跨镜底库」置灰。"""
    monkeypatch.setattr(contract, "AGENT_ASSETS", contract.AGENT_ASSETS - {"reid_gallery"})
    try:
        ok, reason = scene_configurability(SCENES["REID_TRACK"])
        assert ok is False
        assert "跨镜底库" in reason, reason
    finally:
        monkeypatch.undo()


def test_face_gallery_empty_is_hint_not_blocker():
    """底库为空只作为运行期提示，不再是硬阻断（表/API 已就绪）。"""
    from app.api.v1.module_video.scene.catalog import scene_hints

    for code in ("FACE_REC", "STRANGER"):
        scene = SCENES[code]
        assert scene_hints(scene, face_gallery_count=0) == [
            "人脸底库为空：启用本场景后不会命中，请先录入底库特征"
        ]
        # 底库非空 / 未查库时不产生提示
        assert scene_hints(scene, face_gallery_count=3) == []
        assert scene_hints(scene, face_gallery_count=None) == []
    # B4：跨镜底库为空同样只提示（非阻断）
    reid = SCENES["REID_TRACK"]
    assert scene_hints(reid, reid_gallery_count=0) == [
        "跨镜底库为空：启用本场景后不会命中，请先录入跨镜底库特征"
    ]
    assert scene_hints(reid, reid_gallery_count=2) == []
    assert scene_hints(reid, reid_gallery_count=None) == []
    # 不依赖底库的场景恒无提示
    assert scene_hints(SCENES["DET_ZONE"], face_gallery_count=0) == []
    assert scene_hints(SCENES["DET_ZONE"], reid_gallery_count=0) == []


def test_face_and_sam_scenes_configurable_after_b3():
    """B3：face_rec/sam 族 + face_gallery 资产就绪 → 三个场景可配置且默认规则可编译。

    - FACE_REC 用 face_match(gte)；STRANGER 用 stranger(lt)；
    - SAM_SEG 用 prompt_segment（标签 segment，提示点经参数注入）。
    """
    assert {"sam", "face_rec"} <= contract.AGENT_MODEL_FAMILIES
    assert contract.has_asset("face_gallery") is True
    expected = {"FACE_REC": "face_match", "STRANGER": "stranger", "SAM_SEG": "prompt_segment"}
    for code, subject in expected.items():
        scene = SCENES[code]
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 契约已就绪却仍置灰：{reason}"
        out = compile_rule(code, _default_params(scene), scene.default_rule)
        leaves = list(_iter_leaves(out))
        assert leaves and all(leaf["subject"] == subject for leaf in leaves), code
    # 相似度阈值 / 提示点必须可注入（界面可填即生效）
    out = compile_rule("FACE_REC", {"similarity_threshold": 0.7}, SCENES["FACE_REC"].default_rule)
    assert out["children"][0]["value"] == 0.7
    out = compile_rule(
        "SAM_SEG",
        {"prompt_point": [[0.5, 0.5], [0.6, 0.6]]},
        SCENES["SAM_SEG"].default_rule,
    )
    assert out["children"][0]["point"] == [[0.5, 0.5], [0.6, 0.6]]


def test_reid_track_configurable_after_b4():
    """B4：reid 族 + reid_gallery 资产 + reid_match 叶子就绪 → REID_TRACK 可配置且可编译。

    底库类型 kind 将跨镜底库与人脸底库隔离；similarity_threshold 必须注入 reid_match.value。
    """
    assert "reid" in contract.AGENT_MODEL_FAMILIES
    assert contract.has_asset("reid_gallery") is True
    scene = SCENES["REID_TRACK"]
    ok, reason = scene_configurability(scene)
    assert ok is True, f"REID_TRACK 契约已就绪却仍置灰：{reason}"
    out = compile_rule("REID_TRACK", _default_params(scene), scene.default_rule)
    leaves = list(_iter_leaves(out))
    assert leaves and all(leaf["subject"] == "reid_match" for leaf in leaves)
    # 相似度阈值可注入
    out2 = compile_rule("REID_TRACK", {"similarity_threshold": 0.75}, scene.default_rule)
    assert out2["children"][0]["value"] == 0.75


def test_reid_track_re_gates_without_family(monkeypatch):
    """机制锁定：撤下 reid 族后 REID_TRACK 必须重新按「缺模型族」置灰。"""
    monkeypatch.setattr(
        contract, "AGENT_MODEL_FAMILIES", contract.AGENT_MODEL_FAMILIES - {"reid"}
    )
    try:
        ok, reason = scene_configurability(SCENES["REID_TRACK"])
        assert ok is False
        assert "reid" in reason, reason
    finally:
        monkeypatch.undo()


def test_face_match_scenes_re_gate_without_family_or_asset(monkeypatch):
    """机制锁定：撤下 face_rec 族或 face_gallery 资产后，FACE_REC/STRANGER 必须重新置灰。"""
    monkeypatch.setattr(
        contract, "AGENT_MODEL_FAMILIES", contract.AGENT_MODEL_FAMILIES - {"face_rec"}
    )
    try:
        for code in _FACE_MATCH_SCENES:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 撤下族后不应仍可配置"
            assert "face_rec" in reason, f"{code}: {reason}"
    finally:
        monkeypatch.undo()
    monkeypatch.setattr(contract, "AGENT_ASSETS", frozenset())
    try:
        for code in _FACE_MATCH_SCENES:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is False, f"{code} 撤下底库后不应仍可配置"
            assert "人脸底库" in reason, f"{code}: {reason}"
    finally:
        monkeypatch.undo()


def test_sam_seg_re_gates_without_family(monkeypatch):
    """机制锁定：撤下 sam 族后，SAM_SEG 必须重新按「缺模型族」置灰。"""
    monkeypatch.setattr(
        contract, "AGENT_MODEL_FAMILIES", contract.AGENT_MODEL_FAMILIES - {"sam"}
    )
    try:
        ok, reason = scene_configurability(SCENES["SAM_SEG"])
        assert ok is False
        assert "sam" in reason, reason
    finally:
        monkeypatch.undo()


def test_configurable_scene_params_are_consumed():
    """可配置场景声明的每个参数都必须被「编译层」或「边缘任务配置构造」消费。"""
    consumed = set(PARAM_TO_LEAF) | set(TEXT_MATCH_DERIVED_PARAMS) | set(MODEL_CONFIG_PARAMS)
    for code in configurable_scene_codes():
        scene = SCENES[code]
        for param in scene.param_schema:
            assert param["key"] in consumed, (
                f"{code} 参数 {param['key']} 未被编译层/任务配置消费（界面可填但无效果）"
            )


def test_default_rule_leaves_registered_and_flag_consistent():
    """默认规则叶子必须已登记，且实现标记与编译层的接受/拒绝行为一致。"""
    for scene in SCENES.values():
        for leaf in _iter_leaves(scene.default_rule):
            subject = leaf.get("subject")
            assert subject in LEAF_CAPABILITIES, f"{scene.code} 引用未登记叶子 {subject}"
            try:
                compile_rule(scene.code, {}, leaf)
                compiled = True
            except RuleCompileError:
                compiled = False
            assert compiled is LEAF_CAPABILITIES[subject]["implemented"], (
                f"{scene.code} 叶子 {subject} 实现标记与编译行为不一致"
            )


def test_sem_area_roi_uses_task_level_detect_region():
    """SEM_AREA 的 ROI 走任务级 detect_region（Agent 裁剪推理帧后算占比），不声明场景 roi 参数。

    逐项验证（端到端）：
    - 目录不再声明 `roi` 场景参数（region_ratio 叶子不支持 region，声明了会被编译层静默忽略）；
    - region_ratio 叶子参数里确实没有 `region`；
    - `task.detect_region` 仍被编译进 TaskConfig.roi（Agent `infer_group.effective_roi` 据此裁剪）。
    """
    from types import SimpleNamespace

    from app.api.v1.module_video.edge.orchestrator import build_agent_task_config
    from app.api.v1.module_video.scene.leaves import LEAF_CAPABILITIES

    scene = get_scene("SEM_AREA")
    assert "roi" not in {p["key"] for p in scene.param_schema}
    assert "region" not in {p["key"] for p in LEAF_CAPABILITIES["region_ratio"]["params"]}

    roi = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]

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
        detect_region = {"points": roi}
        sensitivity = 60
        schedule_json = None
        runtime_overrides = None
        params_overrides = None

    algo = SimpleNamespace(
        name="SEM_AREA",
        algorithm_type="SEM_AREA",
        scene_type="SEM_AREA",
        model_path="/models/sem.onnx",
        runtime_config={"backend": "ort", "device": "cpu"},
        preset_params={"ratio": 0.5},
    )
    cfg = build_agent_task_config(_Task(), _Cam(), algo, events={})
    assert cfg["roi"] == roi


def test_catalog_api_exposes_configurability(test_client, auth_headers):
    """目录接口必须同时暴露 `configurable`、结构化 `blockers` 与置灰原因。"""
    resp = test_client.get("/api/v1/video/scene/catalog", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    by_code = {s["code"]: s for s in items}
    # B2a 分类契约已落地 → 三个分类场景须转为可配置且无置灰原因
    for code in _CLASSIFICATION_SCENES:
        assert by_code[code]["configurable"] is True, code
        assert by_code[code]["unsupported_reason"] == "", code
        assert by_code[code]["blockers"] == [], code
    assert by_code["ABANDON"]["configurable"] is True
    assert by_code["DEPLOY_TRACK"]["configurable"] is True
    assert by_code["OBB_DET"]["configurable"] is True
    assert by_code["I_SEG"]["configurable"] is True
    # B3：人脸底库/交互分割就绪 → FACE_REC/STRANGER/SAM_SEG 转为可配置
    for code in ("FACE_REC", "STRANGER", "SAM_SEG"):
        assert by_code[code]["configurable"] is True, code
        assert by_code[code]["blockers"] == [], code
    # B4：hand/reid 族 + 跨镜底库就绪 → HAND_GESTURE/REID_TRACK 转为可配置
    for code in ("HAND_GESTURE", "REID_TRACK"):
        assert by_code[code]["configurable"] is True, code
        assert by_code[code]["blockers"] == [], code
    # 底库为空时给出运行期提示（非阻断）；本条 e2e 库底库为空
    assert any("底库为空" in h for h in by_code["FACE_REC"]["hints"])
    assert any("跨镜底库为空" in h for h in by_code["REID_TRACK"]["hints"])
    # 仍不可配置的场景：模型族未就绪 → 必须给出置灰原因
    assert by_code["ACTION_CLS"]["configurable"] is False
    assert by_code["ACTION_CLS"]["unsupported_reason"]
    assert any("action" in b for b in by_code["ACTION_CLS"]["blockers"])
    assert all("configurable" in s and "blockers" in s and "hints" in s for s in items)


def test_scene_cls_default_rule_degrades_to_object_present():
    """SCENE_CLS/DEFECT_CLS 默认规则退化为 object_present，且 labels 参数被注入。"""
    for code in ("SCENE_CLS", "DEFECT_CLS"):
        scene = get_scene(code)
        out = compile_rule(code, {"labels": ["fire"]}, scene.default_rule)
        leaf = out["children"][0]
        assert leaf["subject"] == "object_present"
        assert leaf["labels"] == ["fire"]


def test_lpr_plate_pattern_injected_into_text_match():
    """LPR 的 plate_pattern 必须落到 text_match.regex（此前被静默忽略）。"""
    scene = get_scene("LPR")
    out = compile_rule("LPR", {"plate_pattern": "京A"}, scene.default_rule)
    leaf = out["children"][0]
    assert leaf["subject"] == "text_match"
    assert leaf["regex"] == "京A"
    assert re.search(leaf["regex"], "京A12345")
    assert not re.search(leaf["regex"], "沪B00001")


def test_lpr_list_black_and_white_regex_semantics():
    """LPR_LIST 的黑/白名单必须转成等价 regex 语义（此前名单形同虚设）。"""
    scene = get_scene("LPR_LIST")
    black = compile_rule(
        "LPR_LIST", {"plate_list": ["京A12345"], "list_type": "black"}, scene.default_rule
    )
    rx = black["children"][0]["regex"]
    assert re.search(rx, "京A12345")
    assert not re.search(rx, "沪B00001")

    white = compile_rule(
        "LPR_LIST", {"plate_list": ["京A12345"], "list_type": "white"}, scene.default_rule
    )
    wx = white["children"][0]["regex"]
    assert re.search(wx, "沪B00001")
    assert not re.search(wx, "京A12345")


def test_lpr_list_plate_special_chars_are_escaped():
    """名单字面量须转义，避免被当作正则元字符（如 ``.`` 误匹配任意字符）。"""
    scene = get_scene("LPR_LIST")
    out = compile_rule("LPR_LIST", {"plate_list": ["A.B"]}, scene.default_rule)
    rx = out["children"][0]["regex"]
    assert re.search(rx, "A.B")
    assert not re.search(rx, "AXB")


def test_meter_ocr_numeric_range_params_removed():
    """METER_OCR 的读数上下限（无求值器支持）必须从参数表移除，避免误导。"""
    keys = {p["key"] for p in get_scene("METER_OCR").param_schema}
    assert "min_value" not in keys and "max_value" not in keys


def test_keypoint_scenes_configurable_and_dispatch_pose():
    """可配置 ⇔ 可下发一致：FALL/CLIMB/SMOKE_PHONE 必须可配置且编排层真正下发 pose。

    修复前这三个场景「可配置/可编译」但多角色管线退回单 det，pose 永不下发（姿态切片遗留
    「假可配置」）。本用例把「可配置」与「确实下发 pose」绑定，防止二者再次脱节。
    """
    from types import SimpleNamespace

    from app.api.v1.module_video.edge.orchestrator import build_agent_task_config

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
        sensitivity = 50
        schedule_json = None
        runtime_overrides = None
        params_overrides = None

    # 仅人体姿态三场景走 det+pose 管线（HAND_GESTURE 用 hand 管线，见 B4 用例）
    for code in ("FALL", "CLIMB", "SMOKE_PHONE"):
        scene = SCENES[code]
        ok, reason = scene_configurability(scene)
        assert ok is True, f"{code} 应可配置：{reason}"
        algo = SimpleNamespace(
            name=code, algorithm_type=code, scene_type=code,
            model_path=f"/models/{code.lower()}_primary.onnx",
            runtime_config={"backend": "ort", "device": "cpu"},
            preset_params={"pose_path": "/models/pose.onnx"},
        )
        cfg = build_agent_task_config(_Task(), _Cam(), algo, events={})
        types = {m["type"] for m in cfg["models"]}
        assert {"detection", "pose"} <= types, f"{code} 未下发 det+pose：{types}"

    # B4：HAND_GESTURE 可配置且真正下发 det+hand（不再退回单 det）
    scene = SCENES["HAND_GESTURE"]
    ok, reason = scene_configurability(scene)
    assert ok is True, f"HAND_GESTURE 应可配置：{reason}"
    algo = SimpleNamespace(
        name="HAND_GESTURE", algorithm_type="HAND_GESTURE", scene_type="HAND_GESTURE",
        model_path="/models/hand_primary.onnx",
        runtime_config={"backend": "ort", "device": "cpu"},
        preset_params={"hand_path": "/models/hand.onnx"},
    )
    cfg = build_agent_task_config(_Task(), _Cam(), algo, events={})
    types = {m["type"] for m in cfg["models"]}
    assert {"detection", "hand"} <= types, f"HAND_GESTURE 未下发 det+hand：{types}"
