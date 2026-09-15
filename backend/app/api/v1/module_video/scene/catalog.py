"""任务类型目录（场景注册表）——单一事实源。

每个场景定义：所需模型 pipeline、参数 schema、默认规则、所需边缘能力。
对齐 spec: docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md §3/§4。
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SceneDef:
    """单个任务类型（场景）定义。"""

    code: str
    name: str
    category: str            # detection/tracking/classification/pose/seg/obb/face/lpr/ocr/doc/other
    scene_type: str          # 与 code 一致（写入 TaskConfig.scene_type）
    model_families: list[str]
    pipeline: list[dict]     # [{"role":"det","type":"detection"},{"role":"cls","type":"classification"}]
    param_schema: list[dict]  # [{"key":"roi","type":"polygon"},...]
    default_rule: dict = field(default_factory=dict)
    needs_tracking: bool = False
    description: str = ""


# ── 参数 schema 片段 ──────────────────────────────
_POLY = {"key": "roi", "type": "polygon", "label": "检测区域"}
_LINE = {"key": "line", "type": "polyline", "label": "绊线"}
_CONF = {"key": "confidence_threshold", "type": "float", "default": 0.4, "label": "置信度"}
_CLS_THR = {"key": "cls_threshold", "type": "float", "default": 0.5, "label": "分类阈值"}
_TOPK = {"key": "topk", "type": "int", "default": 5, "label": "Top-K"}
_LABELS = {"key": "labels", "type": "list", "label": "目标标签"}
_COUNT = {"key": "count", "type": "int", "default": 5, "label": "数量阈值"}
_SECONDS = {"key": "dwell_sec", "type": "int", "default": 10, "label": "停留时长(秒)"}
_MIN_SEC = {"key": "min_sec", "type": "int", "default": 5, "label": "最短时长(秒)"}
_GAP_SEC = {"key": "gap_sec", "type": "int", "default": 30, "label": "无目标时长(秒)"}
_DIRECTION = {"key": "direction", "type": "str", "default": "A2B", "label": "越线方向"}
# 组聚合参数：仅相机组作用域展示并注入 group_* 叶子（编译层 PARAM_TO_LEAF 消费）。
# `scope:"group"` 供前端按作用域过滤参数表单；键名必须与 compile.py 的映射保持一致。
_GROUP_WINDOW = {"key": "group_window_sec", "type": "int", "default": 10, "label": "组聚合滑窗(秒)", "scope": "group"}
_GROUP_COUNT = {"key": "group_count", "type": "int", "default": 2, "label": "组内目标数阈值", "scope": "group"}
_GROUP_LABELS = {"key": "group_labels", "type": "list", "default": ["person"], "label": "组内目标标签", "scope": "group"}

# ── pipeline 片段 ──────────────────────────────
_DET = {"role": "det", "type": "detection"}
_CLS = {"role": "cls", "type": "classification"}
_POSE = {"role": "pose", "type": "pose"}
_ISEG = {"role": "seg", "type": "iseg"}
_SEM = {"role": "sem", "type": "sem"}
_OBB = {"role": "obb", "type": "obb"}
_DEPTH = {"role": "depth", "type": "depth"}
_TRACK = {"role": "track", "type": "tracking"}
_REID = {"role": "reid", "type": "reid"}
_FACE_DET = {"role": "face_det", "type": "face_detection"}
_FACE_REC = {"role": "face_rec", "type": "face_rec"}
_FACE_ATTR = {"role": "face_attr", "type": "face_attr"}
_FACE_AS = {"role": "face_as", "type": "face_as"}
_FACE_LMK = {"role": "face_landmark", "type": "face_landmark"}
_OCR = {"role": "ocr", "type": "ocr"}
_LPR = {"role": "lpr", "type": "lpr"}

SCENES: dict[str, SceneDef] = {}


def _add(s: SceneDef) -> None:
    SCENES[s.code] = s


# ── §3.1 目标检测类 ──────────────────────────────
_add(SceneDef(
    "DET_ZONE", "区域入侵", "detection", "DET_ZONE", ["det"], [_DET],
    [_POLY, _CONF, {**_LABELS, "default": ["person"]}, _GROUP_WINDOW, _GROUP_COUNT, _GROUP_LABELS],
    # 单事件叶子；region 缺省表示全画面（ROI 由任务参数提供，不写符号化占位）。
    {"op": "and", "children": [{"subject": "object_present", "label": "person"}]},
    False, "区域内出现目标",
))

_add(SceneDef(
    "LINE_CROSS", "越界/绊线", "tracking", "LINE_CROSS", ["det"], [_DET, _TRACK],
    [_LINE, _DIRECTION, _CONF],
    # line_cross 时序几何叶子（SP4-b 收尾已实现）：绊线由任务参数在运行时注入，
    # 默认规则不写符号化 line（与 region 同理，符号引用无法被求值器解析）。
    {"op": "and", "children": [{"subject": "line_cross", "dir": "A2B"}]},
    True, "目标轨迹穿越绊线",
))

_add(SceneDef(
    "LOITER", "徘徊/停留", "tracking", "LOITER", ["det"], [_DET, _TRACK],
    [_POLY, _MIN_SEC, _CONF],
    # dwell 时序叶子（SP4-b 已实现）：时间由事件 ts 注入，min_sec 取 _MIN_SEC 默认值 5。
    # TODO(SP4): 需检测携带 track_id 才能形成跨事件轨迹并累计停留时长；
    # region 由任务参数在运行时注入，默认规则不写符号化占位。
    {"op": "and", "children": [{"subject": "dwell", "min_sec": 5}]},
    True, "目标在区域内停留超过阈值",
))

_add(SceneDef(
    "GATHER", "聚集", "tracking", "GATHER", ["det"], [_DET, _TRACK],
    [_POLY, _COUNT, {"key": "window_sec", "type": "int", "default": 5, "label": "滑窗时长(秒)"}, _CONF,
     _GROUP_WINDOW, _GROUP_COUNT, _GROUP_LABELS],
    # count_window 时序叶子（SP4-b 已实现）：滑窗 5 秒内去重目标数 >= value(=5)。
    # TODO(SP4): 需检测携带 track_id 才能按轨迹去重（否则退化为按事件计数）；
    # region 由任务参数在运行时注入，默认规则不写符号化占位。
    {"op": "and", "children": [{"subject": "count_window", "window_sec": 5, "op": ">=", "value": 5}]},
    True, "滑窗内区域内人数超过阈值",
))

_add(SceneDef(
    "OVERCROWD", "超员", "detection", "OVERCROWD", ["det"], [_DET],
    [_POLY, _COUNT, _CONF, _GROUP_WINDOW, _GROUP_COUNT, _GROUP_LABELS],
    # 单事件计数叶子；value 取 _COUNT 默认阈值 5。
    {"op": "and", "children": [{"subject": "count", "op": ">", "value": 5}]},
    False, "区域内目标数量超过上限",
))

_add(SceneDef(
    "ABSENT", "离岗/无人", "detection", "ABSENT", ["det"], [_DET],
    [_POLY, _GAP_SEC, _CONF],
    # absence 时序叶子（SP4-b 已实现）：距最近一次出现 >= gap_sec，取 _GAP_SEC 默认值 30。
    # TODO(SP4): 需真实事件流（含区域"无目标"帧）支撑；region 由任务参数运行时注入。
    {"op": "and", "children": [{"subject": "absence", "gap_sec": 30}]},
    False, "区域内持续无目标超过阈值",
))

_add(SceneDef(
    "ILLEGAL_PARK", "车辆违停", "tracking", "ILLEGAL_PARK", ["det"], [_DET, _TRACK],
    [_POLY, _SECONDS, _CONF, {**_LABELS, "default": ["car"]}],
    # dwell 时序叶子（SP4-b 已实现）：车辆停留超时，min_sec 取 _SECONDS 默认值 10。
    # TODO(SP4): 需检测携带 track_id 形成车辆轨迹；region 由任务参数运行时注入。
    {"op": "and", "children": [{"subject": "dwell", "label": "car", "min_sec": 10}]},
    True, "车辆在区域内停留超时",
))

_add(SceneDef(
    "ABANDON", "遗留/抛洒物", "tracking", "ABANDON", ["det"], [_DET, _TRACK],
    [_POLY, _SECONDS, _CONF],
    # TODO(SP4): static 静止判定依赖时序跟踪，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "static", "region": "roi", "op": "gte", "value": "dwell_sec"}]},
    True, "目标静止超过阈值",
))

_add(SceneDef(
    "FIRE_SMOKE", "烟火", "detection", "FIRE_SMOKE", ["det"], [_DET],
    [_POLY, _CONF, {**_LABELS, "default": ["fire", "smoke"]}],
    {"op": "and", "children": [{"subject": "object_present", "label": "fire"}]},
    False, "命中烟火标签",
))

_add(SceneDef(
    "TRAFFIC_DET", "交通目标", "detection", "TRAFFIC_DET", ["det"], [_DET],
    [_POLY, _CONF, {**_LABELS, "default": ["car", "bus", "truck", "person"]}],
    {"op": "and", "children": [{"subject": "object_present", "label": "car"}]},
    False, "检测交通目标并可计数",
))

_add(SceneDef(
    "PED_ATTR", "工作服/安全帽/反光衣/安全带", "attribute", "PED_ATTR", ["pedestrian_attribute"],
    [_DET, _CLS],
    [_POLY, _CONF, _CLS_THR,
     {"key": "attributes", "type": "list", "label": "属性标签",
      "default": ["safety_helmet", "reflective_vest", "safety_rope", "work_uniform"]}],
    {"op": "and", "children": [{"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5}]},
    False, "人体检测 + 多标签属性分类",
))

# ── §3.2 分类类 ──────────────────────────────
_add(SceneDef(
    "SCENE_CLS", "场景/状态分类", "classification", "SCENE_CLS", ["cls"], [_CLS],
    [_POLY, _TOPK, _CLS_THR],
    {"op": "and", "children": [{"subject": "classification", "op": "in", "value": "labels"}]},
    False, "整图/区域场景分类",
))

_add(SceneDef(
    "DEFECT_CLS", "缺陷/异常分类", "classification", "DEFECT_CLS", ["cls"], [_CLS],
    [_POLY, _CLS_THR, _LABELS],
    {"op": "and", "children": [{"subject": "classification", "op": "in", "value": "labels"}]},
    False, "缺陷/异常类别判定",
))

_add(SceneDef(
    "ACTION_CLS", "视频动作", "classification", "ACTION_CLS", ["action"], [_CLS],
    [_POLY, {"key": "clip", "type": "int", "default": 16, "label": "片段帧数"}, _TOPK, _LABELS],
    {"op": "and", "children": [{"subject": "classification", "op": "in", "value": "labels"}]},
    False, "视频片段动作分类",
))

_add(SceneDef(
    "ACTION_SKELETON", "骨架动作", "pose", "ACTION_SKELETON", ["action_skeleton"], [_DET, _POSE, _CLS],
    [_POLY, {"key": "window", "type": "int", "default": 30, "label": "骨架窗口"}, _CONF, _LABELS],
    # TODO(SP4): 骨架序列动作依赖姿态时序跟踪，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "classification", "op": "in", "value": "labels"}]},
    True, "骨架序列动作分类",
))

# ── §3.3 姿态/行为 ──────────────────────────────
_add(SceneDef(
    "FALL", "跌倒", "pose", "FALL", ["pose"], [_DET, _POSE],
    [_POLY, _CONF, {"key": "angle_threshold", "type": "float", "default": 60.0, "label": "倾斜角阈值"}],
    # TODO(SP4): keypoint_geometry(fall) 依赖姿态时序，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "fall", "region": "roi"}]},
    True, "关键点几何判定跌倒",
))

_add(SceneDef(
    "SMOKE_PHONE", "抽烟/打电话", "pose", "SMOKE_PHONE", ["pose"], [_DET, _POSE],
    [_POLY, _CONF, _MIN_SEC],
    # TODO(SP4): keypoint_geometry(hand_head) 依赖姿态时序，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "hand_head", "op": "gte", "value": "min_sec"}]},
    True, "手-头/手-耳几何 + 持续时长",
))

_add(SceneDef(
    "CLIMB", "攀爬/翻越", "pose", "CLIMB", ["pose"], [_DET, _POSE],
    [_POLY, _LINE, _CONF],
    # TODO(SP4): keypoint_geometry(climb) 依赖姿态/越线时序，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "climb", "line": "line"}]},
    True, "关键点高度/越线判定攀爬",
))

_add(SceneDef(
    "NO_MASK", "未戴口罩", "classification", "NO_MASK", ["det", "cls"], [_DET, _CLS],
    [_POLY, _CONF, _CLS_THR, _LABELS],
    {"op": "and", "children": [{"subject": "object_present", "label": "no_mask"}]},
    False, "人体/人脸口罩佩戴判定",
))

_add(SceneDef(
    "HAND_GESTURE", "手势", "pose", "HAND_GESTURE", ["hand"], [_DET, _POSE],
    [_POLY, _CONF, _LABELS],
    # TODO(SP4): 手势依赖手部关键点时序跟踪，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "gesture", "region": "roi"}]},
    True, "21 手部关键点手势识别",
))

# ── §3.4 分割/旋转框 ──────────────────────────────
_add(SceneDef(
    "I_SEG", "实例分割", "seg", "I_SEG", ["iseg"], [_ISEG],
    [_POLY, _CONF, _LABELS],
    # 评估器尚未实现 instance 叶子；实例分割按目标出现判定（region 缺省全画面）。
    {"op": "and", "children": [{"subject": "object_present"}]},
    False, "区域内实例分割",
))

_add(SceneDef(
    "SEM_AREA", "语义区域", "seg", "SEM_AREA", ["sem"], [_SEM],
    [_POLY, {"key": "ratio", "type": "float", "default": 0.5, "label": "占比阈值"}, _LABELS],
    {"op": "and", "children": [{"subject": "region_ratio", "region": "roi", "op": "gte", "value": "ratio"}]},
    False, "区域类别占比判定",
))

_add(SceneDef(
    "SAM_SEG", "交互分割", "seg", "SAM_SEG", ["sam"], [_ISEG],
    [{"key": "prompt_point", "type": "point", "label": "提示点"}, _CONF],
    {"op": "and", "children": [{"subject": "prompt_segment", "point": "prompt_point"}]},
    False, "提示点交互式分割",
))

_add(SceneDef(
    "OBB_DET", "旋转目标", "obb", "OBB_DET", ["obb"], [_OBB],
    [_POLY, _CONF, _LABELS],
    {"op": "and", "children": [{"subject": "object_present"}]},
    False, "旋转框目标检测",
))

# ── §3.5 人脸（face pipeline） ──────────────────────────────
_add(SceneDef(
    "FACE_DET", "人脸检测", "face", "FACE_DET", ["face"], [_FACE_DET],
    [_POLY, _CONF],
    {"op": "and", "children": [{"subject": "object_present"}]},
    False, "区域内人脸检测",
))

_add(SceneDef(
    "FACE_REC", "人脸识别", "face", "FACE_REC", ["face_detection", "face_rec"], [_FACE_DET, _FACE_REC],
    [_POLY, _CONF, {"key": "similarity_threshold", "type": "float", "default": 0.6, "label": "相似度阈值"}],
    {"op": "and", "children": [{"subject": "face_match", "op": "gte", "value": "similarity_threshold"}]},
    False, "人脸检测 + 特征比对识别",
))

_add(SceneDef(
    "STRANGER", "陌生人", "face", "STRANGER", ["face_detection", "face_rec"], [_FACE_DET, _FACE_REC],
    [_POLY, _CONF, {"key": "similarity_threshold", "type": "float", "default": 0.6, "label": "相似度阈值"}],
    {"op": "and", "children": [{"subject": "face_match", "op": "lt", "value": "similarity_threshold"}]},
    False, "未命中底库判定陌生人",
))

_add(SceneDef(
    "FACE_ATTR", "性别/年龄", "face", "FACE_ATTR", ["face_detection", "face_attr"], [_FACE_DET, _FACE_ATTR],
    [_POLY, _CONF, _LABELS],
    # 评估器尚未实现性别/年龄专用叶子；暂按人脸出现判定（region 缺省全画面）。
    {"op": "and", "children": [{"subject": "object_present"}]},
    False, "人脸性别/年龄属性识别",
))

_add(SceneDef(
    "FACE_ANTISPOOF", "活体", "face", "FACE_ANTISPOOF", ["face_detection", "face_as"], [_FACE_DET, _FACE_AS],
    [_POLY, _CONF, {"key": "liveness_threshold", "type": "float", "default": 0.5, "label": "活体阈值"}],
    {"op": "and", "children": [{"subject": "liveness", "op": "lt", "value": "liveness_threshold"}]},
    False, "人脸活体检测（非活体告警）",
))

_add(SceneDef(
    "FACE_LANDMARK", "人脸关键点", "face", "FACE_LANDMARK", ["face_detection", "face_landmark"],
    [_FACE_DET, _FACE_LMK],
    [_POLY, _CONF],
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "face_landmark"}]},
    False, "人脸 106 关键点检测",
))

_add(SceneDef(
    "FACE_CROWD", "人脸计数", "face", "FACE_CROWD", ["face"], [_FACE_DET],
    [_POLY, _COUNT, _CONF],
    # 单事件计数叶子；value 取 _COUNT 默认阈值 5。
    {"op": "and", "children": [{"subject": "count", "op": ">=", "value": 5}]},
    False, "区域内人脸计数",
))

# ── §3.6 车牌 / OCR / 文档 ──────────────────────────────
_add(SceneDef(
    "LPR", "车牌识别", "lpr", "LPR", ["lpr"], [_LPR],
    [_POLY, _CONF, {"key": "plate_pattern", "type": "str", "label": "车牌正则"}],
    # 评估器尚未实现 plate_match 叶子；默认命中任意已识别车牌文本（对齐 text_match 已实现原语）
    {"op": "and", "children": [{"subject": "text_match", "regex": ".+"}]},
    False, "车牌检测 + 字符识别",
))

_add(SceneDef(
    "LPR_LIST", "车牌黑白名单", "lpr", "LPR_LIST", ["lpr"], [_LPR],
    [_POLY, _CONF, {"key": "plate_list", "type": "list", "label": "车牌名单"},
     {"key": "list_type", "type": "str", "default": "black", "label": "名单类型(black/white)"}],
    # 评估器尚未实现 plate_in_list / 名单叶子；默认命中任意已识别车牌文本
    {"op": "and", "children": [{"subject": "text_match", "regex": ".+"}]},
    False, "车牌号命中黑白名单",
))

_add(SceneDef(
    "OCR_TEXT", "通用文本", "ocr", "OCR_TEXT", ["ocr"], [_OCR],
    [_POLY, {"key": "pattern", "type": "str", "label": "文本正则"}, _CONF],
    # 评估器只识别 text_match 叶子的 regex 键（见 inference/service.py），默认即"任意非空文本"
    {"op": "and", "children": [{"subject": "text_match", "regex": ".+"}]},
    False, "通用文本检测识别",
))

_add(SceneDef(
    "METER_OCR", "仪表读数", "ocr", "METER_OCR", ["ocr"], [_OCR],
    [_POLY, {"key": "min_value", "type": "float", "label": "读数下限"},
     {"key": "max_value", "type": "float", "label": "读数上限"}],
    # 评估器尚未实现数值比较叶子；暂用 text_match 匹配数字文本（含小数）作为默认规则。
    # TODO: 后续新增专用数值比较叶子（如 subject="numeric"，支持 min/max 参数）后再切换。
    {"op": "and", "children": [{"subject": "text_match", "regex": "[0-9]+(?:\\.[0-9]+)?"}]},
    False, "仪表数字读数判定",
))

_add(SceneDef(
    "DOC_TABLE", "文档/表格", "doc", "DOC_TABLE", ["doc"], [_OCR, _CLS],
    [_POLY, {"key": "extract_table", "type": "bool", "default": True, "label": "提取表格"}],
    {"op": "and", "children": [{"subject": "structure", "op": "exists"}]},
    False, "文档版式/表格结构解析",
))

_add(SceneDef(
    "BARCODE", "条码/二维码", "other", "BARCODE", ["barcode"], [_OCR],
    [_POLY, {"key": "code_list", "type": "list", "label": "码值名单"}],
    {"op": "and", "children": [{"subject": "code_match", "op": "in", "value": "code_list"}]},
    False, "条码/二维码识别",
))

# ── §3.7 其他 ──────────────────────────────
_add(SceneDef(
    "DEPTH_SAFE", "安全距离", "other", "DEPTH_SAFE", ["depth"], [_DEPTH],
    [_POLY, {"key": "distance_threshold", "type": "float", "default": 1.0, "label": "距离阈值(米)"}],
    {"op": "and", "children": [{"subject": "distance", "op": "lt", "value": "distance_threshold"}]},
    False, "深度估计安全距离判定",
))

_add(SceneDef(
    "REID_TRACK", "跨镜重识别", "tracking", "REID_TRACK", ["reid"], [_DET, _REID],
    [_POLY, {"key": "similarity_threshold", "type": "float", "default": 0.6, "label": "相似度阈值"}],
    # TODO(SP4): reid_match 依赖跨镜轨迹/时序关联，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "reid_match", "op": "gte", "value": "similarity_threshold"}]},
    True, "跨相机行人重识别关联",
))

_add(SceneDef(
    "DEPLOY_TRACK", "通用跟踪", "tracking", "DEPLOY_TRACK", ["det"], [_DET, _TRACK],
    [_POLY, _CONF, _LABELS],
    # TODO(SP4): track 依赖多目标轨迹/时序跟踪，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "track", "region": "roi"}]},
    True, "通用多目标跟踪",
))


def get_scene(code: str) -> SceneDef | None:
    """按场景码获取定义，缺失返回 None。"""
    return SCENES.get(code)


def list_scenes(category: str | None = None) -> list[SceneDef]:
    """列出场景定义，可按 category 过滤。"""
    items = list(SCENES.values())
    if category:
        items = [s for s in items if s.category == category]
    return items
