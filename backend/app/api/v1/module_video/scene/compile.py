"""规则编译层：把场景参数展开进条件树，并校验条件的可求值性。

求值器（``inference/service.py``）只认具体数值/点列，本模块是唯一把 ``params``
落成可评估 ``conditions`` 的地方，保证前后端无口径漂移（spec §4.3/§4.4）。
"""
from __future__ import annotations

from typing import Any

from app.api.v1.module_video.scene.leaves import LEAF_CAPABILITIES

LOGIC_OPS = ("and", "or", "not")

# 参数键 -> (叶子键, 适用 subject 集合 | 单个 subject | None=所有声明该键的叶子)
PARAM_TO_LEAF: dict[str, tuple[str, Any]] = {
    "roi": ("region", None),
    "line": ("line", "line_cross"),
    "direction": ("dir", "line_cross"),
    "labels": (
        "labels",
        {"object_present", "count", "count_window", "dwell", "absence", "line_cross"},
    ),
    "confidence_threshold": ("min_confidence", "object_present"),
    "count": ("value", {"count", "count_window"}),
    "window_sec": ("window_sec", "count_window"),
    "dwell_sec": ("min_sec", "dwell"),
    "min_sec": ("min_sec", "dwell"),
    "gap_sec": ("gap_sec", "absence"),
    "pattern": ("regex", "text_match"),
    # 组叶子走独立参数键（group_* 前缀），避免破坏既有的 window_sec→count_window 等绑定
    "group_window_sec": ("window_sec", {"group_count", "group_coverage"}),
    "group_count": ("value", {"group_count", "group_coverage"}),
    "group_labels": ("labels", {"group_count"}),
    # 仅作 UI 选项、不注入叶子的参数：attributes / cls_threshold / topk / plate_pattern
    # / min_value / max_value
}

_NUMERIC_TYPES = {"int", "float"}
_POINT_LIST_TYPES = {"polygon", "polyline", "point"}

# 语义必填键（求值器硬依赖，缺省即不可求值）
_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
    "attribute": ("field", "value"),
    "text_match": ("regex",),
    "ocr_label": ("contains",),
    "count": ("value",),
    "count_window": ("window_sec", "value"),
    "dwell": ("min_sec",),
    "absence": ("gap_sec",),
    "group_count": ("window_sec", "value"),
    "group_coverage": ("window_sec", "value"),
}

# 跨相机聚合叶子：仅允许相机组作用域规则使用（相机作用域误用 → 编译报错）
_GROUP_LEAVES: set[str] = {"group_count", "group_coverage"}


class RuleCompileError(Exception):
    """条件树非法（不可求值）。"""


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _valid_points(v: Any) -> bool:
    if not isinstance(v, (list, tuple)) or len(v) < 2:
        return False
    for p in v:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return False
        if not (_is_num(p[0]) and _is_num(p[1])):
            return False
    return True


def _applicable(target: Any, subject: str) -> bool:
    if target is None:
        return True
    if isinstance(target, str):
        return target == subject
    return subject in target


def _injects(cap: dict, key: str) -> bool:
    """该叶子是否声明了此键（决定 roi=region 这类 None 绑定的适用范围）。"""
    return any(p.get("key") == key for p in cap.get("params", []))


def _validate_leaf(subject: str, leaf: dict) -> None:
    cap = LEAF_CAPABILITIES.get(subject)
    if cap is None:
        raise RuleCompileError(f"未知叶子 subject={subject!r}")
    if not cap["implemented"]:
        raise RuleCompileError(f"叶子 subject={subject!r} 尚未实现，暂不支持配置")
    ops = cap.get("ops") or []
    if ops:
        op = leaf.get("op")
        if op not in ops:
            raise RuleCompileError(f"叶子 {subject} 的 op={op!r} 不受支持，可用 {ops}")
    for p in cap["params"]:
        key, typ = p["key"], p["type"]
        if key not in leaf:
            # 非必填键：region/labels/track_id/label/labels/min_confidence 可缺省
            continue
        val = leaf[key]
        if typ in _NUMERIC_TYPES and not _is_num(val):
            raise RuleCompileError(f"叶子 {subject} 的 {key} 必须为数值，实际 {val!r}")
        if typ in _POINT_LIST_TYPES and not _valid_points(val):
            raise RuleCompileError(f"叶子 {subject} 的 {key} 必须为点列 [[x,y],...]")
    for key in _REQUIRED_KEYS.get(subject, ()):
        if key not in leaf:
            raise RuleCompileError(f"叶子 {subject} 缺少必填键 {key}")


def _compile_node(node: Any, params: dict, scope: str | None = None) -> dict:
    if not isinstance(node, dict):
        raise RuleCompileError("条件节点必须为对象")
    op = node.get("op")
    if op in LOGIC_OPS:
        kids = node.get("children") or []
        if not isinstance(kids, (list, tuple)):
            raise RuleCompileError("逻辑节点 children 必须为数组")
        return {
            "op": op,
            "children": [_compile_node(k, params, scope) for k in kids],
        }
    subject = node.get("subject")
    if not isinstance(subject, str):
        raise RuleCompileError("叶子缺少 subject")
    if scope == "camera" and subject in _GROUP_LEAVES:
        raise RuleCompileError("group_* 叶子仅可用于相机组作用域的规则")
    out = dict(node)
    cap = LEAF_CAPABILITIES.get(subject) or {}
    for pkey, (leafkey, target) in PARAM_TO_LEAF.items():
        if pkey not in params:
            # 参数缺省时保留叶子原值（如 LINE_CROSS 的 dir:"A2B"）
            continue
        if not _applicable(target, subject):
            continue
        if not _injects(cap, leafkey):
            # 该叶子未声明此键，不注入（roi=region 只给声明了 region 的叶子）
            continue
        out[leafkey] = params[pkey]
    _validate_leaf(subject, out)
    return out


def compile_rule(
    scene_type: str | None,
    params: dict | None,
    conditions: dict | None,
    *,
    scope: str | None = None,
) -> dict:
    """校验并展开条件树；空条件返回 {}（求值器视为匹配一切）。

    ``scope ∈ {"camera","group"}``：相机作用域禁止使用组聚合叶子；缺省
    ``None`` 放行（兼容未传作用域的既有调用点）。
    """
    if not conditions:
        return {}
    if not isinstance(conditions, dict):
        raise RuleCompileError("conditions 必须为对象")
    return _compile_node(conditions, params or {}, scope)
