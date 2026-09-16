"""规则叶子能力注册表（单一事实源）。

每个叶子描述：中文名、是否已实现、可配置参数、支持的比较算子。
求值器实际支持集见 ``inference/service.py:_match_conditions``，本注册表的
``implemented=True`` 集合必须与之逐字一致，由 ``tests/test_rule_capabilities.py``
对拍锁定（spec §4.2/§5）。
"""
from __future__ import annotations

# 逻辑组合算子（前端条件树只用 and/or，后端兼容一元 not）
LOGIC_OPS: list[str] = ["and", "or", "not"]

_CMP_OPS = [">=", ">", "<=", "<", "=="]
_ATTR_OPS = ["lt", "gt", "le", "ge", "eq"]

# 已实现 12 个叶子（对拍求值器）
LEAF_CAPABILITIES: dict[str, dict] = {
    "object_present": {
        "label": "存在目标",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "labels", "type": "list"},
            {"key": "region", "type": "polygon"},
            {"key": "min_confidence", "type": "float"},
        ],
        "ops": [],
    },
    "zone_enter": {
        "label": "进入区域",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
        ],
        "ops": [],
    },
    "count": {
        "label": "目标计数",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "value", "type": "int"},
        ],
        "ops": _CMP_OPS,
    },
    "attribute": {
        "label": "属性判定",
        "implemented": True,
        "params": [
            {"key": "field", "type": "str"},
            {"key": "value", "type": "float"},
        ],
        "ops": _ATTR_OPS,
    },
    "text_match": {
        "label": "文本正则",
        "implemented": True,
        "params": [{"key": "regex", "type": "str"}],
        "ops": [],
    },
    "ocr_label": {
        "label": "文本包含",
        "implemented": True,
        "params": [{"key": "contains", "type": "str"}],
        "ops": [],
    },
    "dwell": {
        "label": "停留时长",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "min_sec", "type": "int"},
            {"key": "track_id", "type": "int"},
        ],
        "ops": [],
    },
    "count_window": {
        "label": "滑窗计数",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "window_sec", "type": "int"},
            {"key": "value", "type": "int"},
        ],
        "ops": _CMP_OPS,
    },
    "absence": {
        "label": "持续无目标",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "gap_sec", "type": "int"},
        ],
        "ops": [],
    },
    "line_cross": {
        "label": "越线/绊线",
        "implemented": True,
        "params": [
            {"key": "line", "type": "polyline"},
            {"key": "dir", "type": "str"},
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
        ],
        "ops": [],
    },
    # 跨相机聚合叶子：仅可用于相机组作用域规则（编译层校验）
    "group_count": {
        "label": "组内目标总数",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "labels", "type": "list"},
            {"key": "window_sec", "type": "int"},
            {"key": "value", "type": "int"},
        ],
        "ops": _CMP_OPS,
    },
    "group_coverage": {
        "label": "组内覆盖比例",
        "implemented": True,
        "params": [
            {"key": "window_sec", "type": "int"},
            {"key": "value", "type": "float"},
        ],
        "ops": _CMP_OPS,
    },
    # ── 以下叶子求值器尚未实现，仅列出供前端置灰展示 ──
    "face_match": {
        "label": "人脸比对",
        "implemented": False,
        "params": [{"key": "value", "type": "float"}],
        "ops": _CMP_OPS,
    },
    "stranger": {
        "label": "陌生人",
        "implemented": False,
        "params": [{"key": "value", "type": "float"}],
        "ops": _CMP_OPS,
    },
    "liveness": {
        "label": "活体检测",
        "implemented": False,
        "params": [{"key": "value", "type": "float"}],
        "ops": _CMP_OPS,
    },
    "keypoint_geometry": {
        "label": "关键点几何",
        "implemented": False,
        "params": [
            {"key": "rule", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "line", "type": "polyline"},
            {"key": "value", "type": "float"},
        ],
        "ops": _CMP_OPS,
    },
    "region_ratio": {
        "label": "区域占比",
        "implemented": False,
        "params": [
            {"key": "region", "type": "polygon"},
            {"key": "value", "type": "float"},
        ],
        "ops": _CMP_OPS,
    },
    "distance": {
        "label": "安全距离",
        "implemented": False,
        "params": [
            {"key": "region", "type": "polygon"},
            {"key": "value", "type": "float"},
        ],
        "ops": _CMP_OPS,
    },
    "structure": {
        "label": "版面结构",
        "implemented": False,
        "params": [{"key": "op", "type": "str"}],
        "ops": [],
    },
    "code_match": {
        "label": "码值匹配",
        "implemented": False,
        "params": [{"key": "code_list", "type": "list"}],
        "ops": [],
    },
    "reid_match": {
        "label": "跨镜重识别",
        "implemented": False,
        "params": [{"key": "value", "type": "float"}],
        "ops": _CMP_OPS,
    },
    "static": {
        "label": "静止判定",
        "implemented": False,
        "params": [
            {"key": "region", "type": "polygon"},
            {"key": "value", "type": "int"},
        ],
        "ops": _CMP_OPS,
    },
    "track": {
        "label": "目标跟踪",
        "implemented": False,
        "params": [{"key": "region", "type": "polygon"}],
        "ops": [],
    },
    "prompt_segment": {
        "label": "交互分割",
        "implemented": False,
        "params": [{"key": "point", "type": "point"}],
        "ops": [],
    },
    "classification": {
        "label": "分类判定",
        "implemented": False,
        "params": [{"key": "labels", "type": "list"}],
        "ops": [],
    },
}

# 已实现叶子集合（对拍求值器支持集）
IMPLEMENTED_LEAVES: set[str] = {
    s for s, c in LEAF_CAPABILITIES.items() if c["implemented"]
}


def get_capabilities() -> dict:
    """能力接口载荷：逻辑算子 + 全部叶子描述。"""
    return {
        "logic": LOGIC_OPS,
        "leaves": [{"subject": s, **c} for s, c in LEAF_CAPABILITIES.items()],
    }
