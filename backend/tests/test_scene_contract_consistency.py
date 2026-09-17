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

# 因「分类结果未进入边缘事件」而暂不可配置的三个场景（契约翻转后自动解锁）
_CLASSIFICATION_GATED = {"SCENE_CLS", "DEFECT_CLS", "NO_MASK"}


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
    # SCENE_CLS/DEFECT_CLS/NO_MASK 因分类事件契约未落地而据实置灰（不再「假可配置」）。
    assert {"ABANDON", "DEPLOY_TRACK", "OBB_DET", "I_SEG"} <= set(checked)
    assert _CLASSIFICATION_GATED.isdisjoint(checked)
    assert set(checked) == set(configurable_scene_codes())
    assert len(checked) == 20


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
        bad = unimplemented_default_leaves(scene)
        # 每个原因类别都必须落在 reason 文本中，保证前端提示可操作
        if missing_fams:
            assert any(f in reason for f in missing_fams), f"{code}: {reason}"
        if missing_assets:
            assert any(contract.asset_label(a) in reason for a in missing_assets), f"{code}: {reason}"
        if gated:
            assert "分类" in reason, f"{code}: {reason}"
        if bad:
            assert any(leaf in reason for leaf in bad), f"{code}: {reason}"


def test_abandon_and_deploy_track_are_configurable_now():
    """static/track 叶子实现后，ABANDON/DEPLOY_TRACK 必须可配置（不再置灰）。"""
    for code in ("ABANDON", "DEPLOY_TRACK"):
        ok, reason = scene_configurability(SCENES[code])
        assert ok is True, f"{code} 仍不可配置：{reason}"


def test_classification_scenes_gated_until_agent_event_contract():
    """SCENE_CLS/DEFECT_CLS/NO_MASK 必须显式声明依赖分类事件并据实置灰。"""
    for code in _CLASSIFICATION_GATED:
        scene = SCENES[code]
        assert scene.requires_classification is True, code
        ok, reason = scene_configurability(scene)
        assert ok is False, f"{code} 在分类契约未落地时不应可配置"
        assert "分类" in reason, f"{code}: {reason}"


def test_classification_scenes_flip_when_contract_lands(monkeypatch):
    """模拟 Agent 分类事件契约落地：三个场景应自动转为可配置（锁定翻转行为）。"""
    monkeypatch.setattr(contract, "AGENT_EVENT_FEATURES", frozenset({"classification"}))
    try:
        for code in _CLASSIFICATION_GATED:
            ok, reason = scene_configurability(SCENES[code])
            assert ok is True, f"{code} 契约落地后仍不可配置：{reason}"
            compile_rule(code, _default_params(SCENES[code]), SCENES[code].default_rule)
    finally:
        monkeypatch.undo()


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
    """缺底库场景必须据实置灰并在原因中标注资产（缺底库，而非静默失败）。"""
    for code, asset_label in (("FACE_REC", "人脸底库"), ("STRANGER", "人脸底库"), ("REID_TRACK", "跨镜底库")):
        scene = SCENES[code]
        assert scene.required_assets, code
        assert not contract.has_asset(scene.required_assets[0]), code
        blockers = "；".join(scene_blockers(scene))
        assert "缺外部资产" in blockers and asset_label in blockers, f"{code}: {blockers}"


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


def test_catalog_api_exposes_configurability(test_client, auth_headers):
    """目录接口必须同时暴露 `configurable`、结构化 `blockers` 与置灰原因。"""
    resp = test_client.get("/api/v1/video/scene/catalog", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    by_code = {s["code"]: s for s in items}
    # 分类契约未落地 → 三个分类场景须置灰并给原因
    for code in _CLASSIFICATION_GATED:
        assert by_code[code]["configurable"] is False, code
        assert by_code[code]["unsupported_reason"], code
        assert by_code[code]["blockers"], code
    assert by_code["ABANDON"]["configurable"] is True
    assert by_code["DEPLOY_TRACK"]["configurable"] is True
    assert by_code["OBB_DET"]["configurable"] is True
    assert by_code["I_SEG"]["configurable"] is True
    # 仍不可配置的场景：模型族/资产未就绪 → 必须给出置灰原因
    assert by_code["FACE_REC"]["configurable"] is False
    assert by_code["FACE_REC"]["unsupported_reason"]
    assert any("底库" in b for b in by_code["FACE_REC"]["blockers"])
    assert all("configurable" in s and "blockers" in s for s in items)


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
