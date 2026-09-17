"""场景目录 ↔ 能力注册表 ↔ 编译层一致性回归（系统性防线）。

对应审计「UI 可选但后端必拒」这类缺陷：

1. 目录标记为「可配置（configurable）」的场景，默认规则必须能通过 ``compile_rule``——
   即运维在界面上能选中的场景一定能保存成功；
2. 不可配置场景必须给出中文原因（前端据此置灰并提示，而非静默失败）；
3. 目录参数必须被编译层或边缘任务配置构造消费，不允许「界面上能填、实际无效果」；
4. 默认规则引用的叶子必须已登记，且实现状态与编译层的接受/拒绝行为一致。
"""

import re

from app.api.v1.module_video.scene.catalog import (
    EDGE_ADVERTISED_MODEL_FAMILIES,
    SCENES,
    configurable_scene_codes,
    get_scene,
    scene_configurability,
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
    # 4 个「族够但叶子缺」场景的两条修复路径都收敛：
    # SCENE_CLS/DEFECT_CLS 改为可编译默认规则 → 可选；ABANDON/DEPLOY_TRACK 的
    # static/track 叶子实现后 → 可选（不再置灰）。
    assert {"SCENE_CLS", "DEFECT_CLS", "ABANDON", "DEPLOY_TRACK"} <= set(checked)
    assert set(checked) == set(configurable_scene_codes())
    assert len(checked) >= 21


def test_unconfigurable_scenes_reason_mentions_cause():
    """置灰场景必须给出可操作原因（指明缺失模型族或缺实现叶子）。"""
    for code, scene in SCENES.items():
        ok, reason = scene_configurability(scene)
        if ok:
            continue
        assert reason, code
        missing_fams = [
            f for f in scene.model_families if f not in EDGE_ADVERTISED_MODEL_FAMILIES
        ]
        if missing_fams:
            assert any(f in reason for f in missing_fams), f"{code}: {reason}"
        else:
            bad = unimplemented_default_leaves(scene)
            assert bad and any(leaf in reason for leaf in bad), f"{code}: {reason}"


def test_abandon_and_deploy_track_are_configurable_now():
    """static/track 叶子实现后，ABANDON/DEPLOY_TRACK 必须可配置（不再置灰）。"""
    for code in ("ABANDON", "DEPLOY_TRACK"):
        ok, reason = scene_configurability(SCENES[code])
        assert ok is True, f"{code} 仍不可配置：{reason}"


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
    """目录接口必须同时暴露 `configurable` 与置灰原因，供前端诚实置灰。"""
    resp = test_client.get("/api/v1/video/scene/catalog", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    by_code = {s["code"]: s for s in items}
    assert by_code["SCENE_CLS"]["configurable"] is True
    assert by_code["ABANDON"]["configurable"] is True
    assert by_code["DEPLOY_TRACK"]["configurable"] is True
    # 仍不可配置的场景：模型族未实现 → 必须给出置灰原因
    assert by_code["FACE_REC"]["configurable"] is False
    assert by_code["FACE_REC"]["unsupported_reason"]
    assert all("configurable" in s for s in items)


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
