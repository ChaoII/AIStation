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

# 已实现 18 个叶子（对拍求值器）
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
    # 跟踪/静止时序叶子：读取 TemporalStore 的轨迹状态（存在时长 + 最大位移）
    "static": {
        "label": "静止判定",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "labels", "type": "list"},
            {"key": "region", "type": "polygon"},
            {"key": "min_sec", "type": "int"},
            {"key": "max_move", "type": "float"},
            {"key": "track_id", "type": "int"},
        ],
        "ops": [],
    },
    "track": {
        "label": "目标跟踪",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "labels", "type": "list"},
            {"key": "region", "type": "polygon"},
            {"key": "min_sec", "type": "int"},
        ],
        "ops": [],
    },
    # 姿态关键点几何叶子：读取 detection.keypoints（[[x,y,score],...] 归一化，COCO-17）
    # rule 语义见 inference/service.py `_keypoint_geometry_hit`：
    #   fall=躯干倾角、climb=越线/高度、smoke_phone=腕-头距离（可选 min_sec 持续）
    #   gesture=已声明但未实现（缺 21 点手部关键点模型），恒不命中。
    # op 不登记（空 ops）：缺省由 rule 决定（fall 用 >=，climb/smoke_phone 用 <=），
    # 声明非空 ops 会强制所有规则的叶子都必须带 op，反而不便。
    "keypoint_geometry": {
        "label": "关键点几何",
        "implemented": True,
        "params": [
            {"key": "rule", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "line", "type": "polyline"},
            {"key": "min_sec", "type": "int"},
            {"key": "op", "type": "str"},
            {"key": "value", "type": "float"},
        ],
        "ops": [],
    },
    # 深度安全距离叶子：读取 detection.depth（米，float；B2a 事件新增字段）。
    # op 用 lt/gt/le/ge/eq（与 attribute 叶子一致）；region 按检测框中心过滤；
    # 语义见 inference/service.py `_distance_hit`：任一检测的数值 depth 满足比较即命中，
    # depth 缺失/非法一律跳过（fail-closed）。
    "distance": {
        "label": "安全距离",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "region", "type": "polygon"},
            {"key": "value", "type": "float"},
        ],
        "ops": _ATTR_OPS,
    },
    # 语义区域占比叶子（B2b）：sem 模型输出「整帧对象 + attributes={类别: 面积占比}」，
    # 本叶子对占比按 op 与阈值比较（任一类别满足即命中）。region 不登记：占比由边缘在
    # 任务 ROI 内算好，云端无法按多边形重算（见 inference/service.py `_region_ratio_hit`）。
    "region_ratio": {
        "label": "区域占比",
        "implemented": True,
        "params": [
            {"key": "label", "type": "str"},
            {"key": "labels", "type": "list"},
            {"key": "value", "type": "float"},
        ],
        "ops": _ATTR_OPS,
    },
    # 码值匹配叶子（B2b）：条码/二维码解码结果复用 detection.text 承载。
    # op=in 时与 code_list 逐项精确比对（名单为空=识别到任意非空码值即命中）；
    # op=regex 时按正则匹配（安全执行，非法/危险模式不命中）。见 `_code_match_hit`。
    "code_match": {
        "label": "码值匹配",
        "implemented": True,
        "params": [
            {"key": "code_list", "type": "list"},
            {"key": "regex", "type": "str"},
        ],
        "ops": ["in", "regex"],
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
    "structure": {
        "label": "版面结构",
        "implemented": False,
        "params": [{"key": "op", "type": "str"}],
        "ops": [],
    },
    "reid_match": {
        "label": "跨镜重识别",
        "implemented": False,
        "params": [{"key": "value", "type": "float"}],
        "ops": _CMP_OPS,
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
