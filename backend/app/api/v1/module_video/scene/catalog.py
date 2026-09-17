"""任务类型目录（场景注册表）——单一事实源。

每个场景定义：所需模型 pipeline、参数 schema、默认规则、所需边缘能力。
对齐 spec: docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md §3/§4。
"""
from dataclasses import dataclass, field

from . import contract
from .leaves import LEAF_CAPABILITIES


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
    # 是否依赖「边缘把分类结果写入事件」这一事件契约（SCENE_CLS/DEFECT_CLS/NO_MASK）。
    # 契约未落地时默认规则永不命中，故据实置灰（见 scene/contract.py）。
    requires_classification: bool = False
    # 是否依赖「边缘把姿态关键点写入事件」这一事件契约（FALL/CLIMB/SMOKE_PHONE/HAND_GESTURE）。
    # 契约未落地时 keypoint_geometry 叶子读不到关键点，故据实置灰（见 scene/contract.py）。
    requires_keypoints: bool = False
    # 是否依赖「边缘把人脸属性/活体分数写入事件」（FACE_ATTR/FACE_ANTISPOOF）。
    # 契约未落地时 attribute 叶子读不到分数，故据实置灰（见 scene/contract.py）。
    requires_attributes: bool = False
    # 是否依赖「边缘把深度值写入事件」（DEPTH_SAFE）。契约未落地时 distance 叶子读不到
    # depth，故据实置灰（见 scene/contract.py）。
    requires_depth: bool = False
    # 已知限制说明（如叶子规则未实现）：与阻断原因一并展示，避免「选了却不知为何不命中」。
    limitations: list[str] = field(default_factory=list)
    # 依赖的云端外部资产（如 face_gallery/reid_gallery）；缺失时据实置灰并给原因。
    required_assets: list[str] = field(default_factory=list)


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
# 姿态几何：fall 的倾斜角阈值（度，0=直立 90=水平）→ keypoint_geometry.value（rule=fall）
_ANGLE_THRESHOLD = {"key": "angle_threshold", "type": "float", "default": 60.0, "label": "倾斜角阈值(度)"}
# 姿态几何：smoke_phone 的腕-头归一化距离阈值 → keypoint_geometry.value（rule=smoke_phone）
_HAND_DIST = {"key": "hand_head_distance", "type": "float", "default": 0.15, "label": "手-头距离阈值"}
# 人脸关键点：face_landmark 的最少有效关键点数（分数 >= 0.3 视为有效）
_MIN_KP = {"key": "min_keypoints", "type": "int", "default": 5, "label": "最少关键点数"}
_MAX_MOVE = {"key": "max_move", "type": "float", "default": 0.02, "label": "最大位移(归一化)"}
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
    [_POLY, _SECONDS, _MAX_MOVE, _CONF],
    # static 时序叶子（已实现）：某真实轨迹存在 >= min_sec（取 dwell_sec 默认 10）且
    # 相对首帧最大位移 <= max_move（默认 0.02）→ 判定为遗留/静止物。
    # region 由任务参数在运行时注入，默认规则不写符号化占位。
    {"op": "and", "children": [{"subject": "static", "min_sec": 10}]},
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
    [_POLY, _LABELS],
    # 分类叶子（classification）求值器未实现，暂退化为 object_present（区域内目标出现判定）；
    # labels 参数经编译层注入该叶子。但纯分类结果当前被 Agent 丢弃（不进入事件），
    # 故据实置灰（requires_classification），待分类事件契约落地后自动解锁。
    {"op": "and", "children": [{"subject": "object_present"}]},
    False, "整图/区域场景分类（依赖边缘分类结果进入事件，当前暂不可配置）",
    requires_classification=True,
))

_add(SceneDef(
    "DEFECT_CLS", "缺陷/异常分类", "classification", "DEFECT_CLS", ["cls"], [_CLS],
    [_POLY, _LABELS],
    # 同 SCENE_CLS：分类叶子未实现，退化为 object_present，且依赖分类结果进入事件。
    {"op": "and", "children": [{"subject": "object_present"}]},
    False, "缺陷/异常类别判定（依赖边缘分类结果进入事件，当前暂不可配置）",
    requires_classification=True,
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
    [_POLY, _CONF, _ANGLE_THRESHOLD],
    # keypoint_geometry(rule=fall) 已实现：躯干（肩中点↔髋中点）与竖直方向夹角
    # >= angle_threshold（默认 60°）判为跌倒。region 由 roi 参数运行时注入，
    # 默认规则不写符号化占位（符号引用无法被求值器解析）。
    {"op": "and", "children": [
        {"subject": "keypoint_geometry", "rule": "fall", "op": ">=", "value": 60.0}
    ]},
    True, "关键点几何判定跌倒",
    requires_keypoints=True,
))

_add(SceneDef(
    "SMOKE_PHONE", "抽烟/打电话", "pose", "SMOKE_PHONE", ["pose"], [_DET, _POSE],
    [_POLY, _CONF, _MIN_SEC, _HAND_DIST],
    # keypoint_geometry(rule=smoke_phone) 已实现：腕（9/10）到头参照（鼻→双耳→双眼）
    # 最小归一化距离 <= hand_head_distance（默认 0.15）；min_sec 为可选持续性抑制
    # （要求存在已持续 >= min_sec 的活跃轨迹，复用时序轨迹状态）。
    {"op": "and", "children": [
        {"subject": "keypoint_geometry", "rule": "smoke_phone", "min_sec": 5}
    ]},
    True, "手-头几何 + 持续时长",
    requires_keypoints=True,
))

_add(SceneDef(
    "CLIMB", "攀爬/翻越", "pose", "CLIMB", ["pose"], [_DET, _POSE],
    [_POLY, _LINE, _CONF],
    # keypoint_geometry(rule=climb) 已实现：躯干中心位于绊线（line 参数运行时注入）上方
    # 判为攀爬；无 line 时回退高度阈值 value（缺省 0.5，越小越高）。
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "climb"}]},
    True, "关键点高度/越线判定攀爬",
    requires_keypoints=True,
))

_add(SceneDef(
    "NO_MASK", "未戴口罩", "classification", "NO_MASK", ["det", "cls"], [_DET, _CLS],
    [_POLY, _CONF, _LABELS],
    {"op": "and", "children": [{"subject": "object_present", "label": "no_mask"}]},
    False, "人体/人脸口罩佩戴判定（依赖边缘分类结果进入事件，当前暂不可配置）",
    requires_classification=True,
))

_add(SceneDef(
    "HAND_GESTURE", "手势", "pose", "HAND_GESTURE", ["hand"], [_DET, _POSE],
    [_POLY, _CONF, _LABELS],
    # keypoint_geometry(rule=gesture) 为「已声明但未实现」的桩：缺 21 点手部关键点模型
    # （hand 族权重未补齐），恒不命中 —— 保留默认规则以便契约就绪后直接生效，
    # 同时用 limitations 明确告知用户「本场景当前不会命中」。
    {"op": "and", "children": [{"subject": "keypoint_geometry", "rule": "gesture"}]},
    True, "21 手部关键点手势识别",
    requires_keypoints=True,
    limitations=["gesture 规则未实现（缺 21 点手部关键点模型/权重），当前不会命中"],
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
    # region_ratio 叶子（B2b）：sem 模型输出整帧对象 attributes={类别: 面积占比}，
    # 默认规则判「某类别占比 >= 0.5」。区域由任务 ROI 在边缘侧参与占比计算，云端不重算，
    # 故默认规则不写符号化 region（符号引用无法被求值器解析）。
    {"op": "and", "children": [{"subject": "region_ratio", "op": "ge", "value": 0.5}]},
    False, "区域类别占比判定",
))

_add(SceneDef(
    "SAM_SEG", "交互分割", "seg", "SAM_SEG", ["sam"], [_ISEG],
    [{"key": "prompt_point", "type": "point", "label": "提示点"}, _CONF],
    # prompt_segment 叶子（B3）：sam 以归一化 bbox 对象承载分割结果（label="segment"，
    # 无新增事件字段）。提示点（prompt_point 参数）在运行时由编译层注入 point，
    # 要求点落在分割框内；缺省只要求存在分割目标。默认规则不写符号化 point。
    {"op": "and", "children": [{"subject": "prompt_segment", "label": "segment"}]},
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
    "FACE_REC", "人脸识别", "face", "FACE_REC", ["face", "face_rec"], [_FACE_DET, _FACE_REC],
    [_POLY, _CONF, {"key": "similarity_threshold", "type": "float", "default": 0.6, "label": "相似度阈值"}],
    # face_match 叶子（B3）：检测特征与云端人脸底库的最大余弦相似度 >= similarity_threshold
    # 判为命中；底库为空/无 embedding 时不命中（fail-closed），默认规则写数值阈值，
    # 运行时由 similarity_threshold 参数经编译层注入覆盖。
    {"op": "and", "children": [{"subject": "face_match", "op": "gte", "value": 0.6}]},
    False, "人脸检测 + 特征比对识别",
    required_assets=["face_gallery"],
))

_add(SceneDef(
    "STRANGER", "陌生人", "face", "STRANGER", ["face", "face_rec"], [_FACE_DET, _FACE_REC],
    [_POLY, _CONF, {"key": "similarity_threshold", "type": "float", "default": 0.6, "label": "相似度阈值"}],
    # stranger 叶子（B3）：与 face_match 同源相似度、配 op=lt —— 低于阈值即未命中底库；
    # 底库为空时同样不命中（fail-closed：无底库无法判定陌生人）。
    {"op": "and", "children": [{"subject": "stranger", "op": "lt", "value": 0.6}]},
    False, "未命中底库判定陌生人",
    required_assets=["face_gallery"],
))

_add(SceneDef(
    "FACE_ATTR", "性别/年龄", "face", "FACE_ATTR", ["face", "face_attr"], [_FACE_DET, _FACE_ATTR],
    [_CLS_THR],
    # 复用 attribute 叶子（B2a）：Agent face_attr 事件发射 {"gender_male":..,"age_young":..}，
    # 默认按 gender_male >= cls_threshold（默认 0.5）判定；field 名必须与 Agent 发射名一致。
    {"op": "and", "children": [
        {"subject": "attribute", "field": "gender_male", "op": "ge", "value": 0.5}
    ]},
    False, "人脸性别/年龄属性识别",
    requires_attributes=True,
))

_add(SceneDef(
    "FACE_ANTISPOOF", "活体", "face", "FACE_ANTISPOOF", ["face", "face_as"], [_FACE_DET, _FACE_AS],
    [{"key": "liveness_threshold", "type": "float", "default": 0.5, "label": "活体阈值"}],
    # 复用 attribute 叶子（B2a）：Agent face_as 事件发射 {"liveness":..}；
    # 分数低于 liveness_threshold → 判为非活体并告警（fail-closed：缺分数不命中）。
    {"op": "and", "children": [
        {"subject": "attribute", "field": "liveness", "op": "lt", "value": 0.5}
    ]},
    False, "人脸活体检测（非活体告警）",
    requires_attributes=True,
))

_add(SceneDef(
    "FACE_LANDMARK", "人脸关键点", "face", "FACE_LANDMARK", ["face", "face_landmark"],
    [_FACE_DET, _FACE_LMK],
    [_POLY, _MIN_KP],
    # keypoint_geometry(rule=face_landmark)（B2b）：对象关键点中「分数 >= 0.3 的有效点数」
    # >= min_keypoints（默认 5）判为检出人脸关键点；region 由 roi 参数运行时注入。
    {"op": "and", "children": [
        {"subject": "keypoint_geometry", "rule": "face_landmark", "op": ">=", "value": 5}
    ]},
    False, "人脸 106 关键点检测",
    requires_keypoints=True,
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
    # 数值上下限（原 min_value/max_value）求值器无对应叶子，已从参数表移除，避免「界面可填但无效」；
    # 恢复条件：新增支持 min/max 的数值比较叶子后，按本目录参数键重新登记。
    [_POLY, _CONF],
    # 求值器只识别 text_match 叶子的 regex：默认匹配数字文本（含小数）。
    {"op": "and", "children": [{"subject": "text_match", "regex": "[0-9]+(?:\\.[0-9]+)?"}]},
    False, "仪表数字读数判定（读数上下限未实现，默认仅识别数字文本）",
))

_add(SceneDef(
    "DOC_TABLE", "文档/表格", "doc", "DOC_TABLE", ["doc"], [_OCR, _CLS],
    [_POLY],
    # 事件契约（B2b）：doc 模型把版式/表格结构摘要写入 objects[].text；云端复用已实现的
    # text_match 叶子判「识别到任意非空文本」。原 extract_table 参数无求值器/边缘消费方，
    # 已移除（避免「界面可填但无效」，同 METER_OCR 读数上下限处理）。
    {"op": "and", "children": [{"subject": "text_match", "regex": ".+"}]},
    False, "文档版式/表格结构解析",
))

_add(SceneDef(
    "BARCODE", "条码/二维码", "other", "BARCODE", ["barcode"], [_OCR],
    [_POLY, {"key": "code_list", "type": "list", "label": "码值名单"}],
    # code_match 叶子（B2b）：解码结果复用 objects[].text；op=in 与 code_list 精确比对，
    # 名单为空（默认）时识别到任意非空码值即命中。
    {"op": "and", "children": [{"subject": "code_match", "op": "in"}]},
    False, "条码/二维码识别",
))

# ── §3.7 其他 ──────────────────────────────
_add(SceneDef(
    "DEPTH_SAFE", "安全距离", "other", "DEPTH_SAFE", ["depth"], [_DEPTH],
    [_POLY, {"key": "distance_threshold", "type": "float", "default": 1.0, "label": "距离阈值(米)"}],
    # distance 叶子（B2a）：任一检测的 depth（米）< distance_threshold → 过近告警；
    # region 由 roi 参数运行时注入，默认规则不写符号化占位。
    {"op": "and", "children": [{"subject": "distance", "op": "lt", "value": 1.0}]},
    False, "深度估计安全距离判定",
    requires_depth=True,
))

_add(SceneDef(
    "REID_TRACK", "跨镜重识别", "tracking", "REID_TRACK", ["reid"], [_DET, _REID],
    [_POLY, {"key": "similarity_threshold", "type": "float", "default": 0.6, "label": "相似度阈值"}],
    # TODO(SP4): reid_match 依赖跨镜轨迹/时序关联，求值器尚未实现，保留占位规则。
    {"op": "and", "children": [{"subject": "reid_match", "op": "gte", "value": "similarity_threshold"}]},
    True, "跨相机行人重识别关联",
    required_assets=["reid_gallery"],
))

_add(SceneDef(
    "DEPLOY_TRACK", "通用跟踪", "tracking", "DEPLOY_TRACK", ["det"], [_DET, _TRACK],
    [_POLY, _CONF, _LABELS],
    # track 时序叶子（已实现）：存在至少一条活跃的真实轨迹（携带有效 track_id）即命中；
    # region 由任务参数在运行时注入，默认规则不写符号化占位。
    {"op": "and", "children": [{"subject": "track"}]},
    True, "通用多目标跟踪",
))


def get_scene(code: str) -> SceneDef | None:
    """按场景码获取定义，缺失返回 None。"""
    return SCENES.get(code)


# 边缘 Agent 默认构建上报的模型族（规范名）。真实来源为 ``scene/contract.py`` 的
# ``AGENT_MODEL_FAMILIES``（对齐 ModelDeploy `application/aistation_agent/capability.cpp`）。
# 仅由这些族构成的场景才能在边缘落地；其余场景（pose/face_rec/...）Agent 端尚无实现，
# 目录对用户可见但「选了必失败」，故据此标记 `edge_supported` 供前端置灰。
EDGE_ADVERTISED_MODEL_FAMILIES: frozenset[str] = contract.AGENT_MODEL_FAMILIES


def scene_missing_families(scene: SceneDef) -> list[str]:
    """场景所需、但 Agent 契约未声明的规范模型族（去重、稳定顺序）。"""
    return [f for f in contract.canonical_families(scene.model_families) if f not in contract.AGENT_MODEL_FAMILIES]


def scene_missing_assets(scene: SceneDef) -> list[str]:
    """场景所需、但云端尚未具备的外部资产（去重、稳定顺序）。"""
    out: list[str] = []
    for asset in scene.required_assets or []:
        key = str(asset).strip().lower()
        if key and not contract.has_asset(key) and key not in out:
            out.append(key)
    return out


def is_edge_implementable(scene: SceneDef) -> bool:
    """场景所需模型族是否全部为边缘 Agent 契约声明的族。"""
    return not scene_missing_families(scene)


def _iter_rule_leaves(rule: dict):
    """深度遍历条件树，产出所有叶子节点（含 subject 的节点）。"""
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


def unimplemented_default_leaves(scene: SceneDef) -> list[str]:
    """默认规则里引用了、但求值器尚未实现的叶子 subject（去重排序）。"""
    bad = {
        leaf["subject"]
        for leaf in _iter_rule_leaves(scene.default_rule)
        if not (LEAF_CAPABILITIES.get(leaf["subject"]) or {}).get("implemented")
    }
    return sorted(bad)


def scene_blockers(scene: SceneDef) -> list[str]:
    """数据驱动的不可配置原因清单（按 模型族 → 外部资产 → 事件契约 → 叶子 → 已知限制）。

    每个原因均由「场景声明 vs 契约/实现状态」推导，新增能力位后自动收敛；前端可逐条展示。
    """
    blockers: list[str] = []
    missing_families = scene_missing_families(scene)
    if missing_families:
        blockers.append(f"缺模型族：{', '.join(missing_families)}")
    missing_assets = scene_missing_assets(scene)
    if missing_assets:
        labels = "、".join(contract.asset_label(a) for a in missing_assets)
        blockers.append(f"缺外部资产：{labels}")
    if scene.requires_classification and not contract.supports_event_feature("classification"):
        blockers.append("分类结果未进入边缘事件（等待 Agent 分类契约落地）")
    if scene.requires_keypoints and not contract.supports_event_feature("keypoints"):
        blockers.append("关键点未进入边缘事件（等待 Agent 姿态契约落地）")
    if scene.requires_attributes and not contract.supports_event_feature("face_attributes"):
        blockers.append("人脸属性分数未进入边缘事件（等待 Agent face_attr/face_as 契约落地）")
    if scene.requires_depth and not contract.supports_event_feature("depth"):
        blockers.append("深度值未进入边缘事件（等待 Agent depth 契约落地）")
    unimplemented = unimplemented_default_leaves(scene)
    if unimplemented:
        blockers.append(f"缺求值器叶子：{', '.join(unimplemented)}")
    if scene.limitations:
        blockers.append(f"已知限制：{'；'.join(scene.limitations)}")
    return blockers


def scene_configurability(scene: SceneDef) -> tuple[bool, str]:
    """场景在当前云端 + 边缘 Agent 契约下是否「可配置（选中即可保存成功）」。

    四类硬性条件缺一不可（均由 ``scene_blockers`` 数据驱动推导）：
    1. 所需模型族均已由边缘 Agent 上报（否则下发必被拒）；
    2. 所需外部资产已具备（如人脸/跨镜底库）；
    3. 依赖分类/关键点事件契约的场景，Agent 已把对应结果写入事件；
    4. 默认规则引用的求值器叶子均已实现（否则编译层必 400）。

    返回 ``(可配置, 原因)``；可配置时原因为空串。不可配置的原因直接展示给用户，
    避免出现「界面上能选、点保存必然失败」的误导陷阱。
    """
    blockers = scene_blockers(scene)
    return (not blockers), "；".join(blockers)


def scene_hints(scene: SceneDef, *, face_gallery_count: int | None = None) -> list[str]:
    """场景的「可配置但需注意」操作提示（非阻断，与 ``scene_blockers`` 互补）。

    与阻断原因的区别：这些场景可正常选中并保存成功，但运行期存在前置条件。
    当前仅人脸底库：底库为空时 FACE_REC/STRANGER 恒不命中，需在 UI 提示先录入底库
    （底库即使为空也不再是硬阻断——表与 API 已就绪，属数据就绪型依赖）。
    缺省 ``face_gallery_count=None``（未查库）时不产生提示，避免误导。
    """
    assets = {str(a).strip().lower() for a in (scene.required_assets or [])}
    if "face_gallery" not in assets or face_gallery_count is None:
        return []
    if face_gallery_count <= 0:
        return ["人脸底库为空：启用本场景后不会命中，请先录入底库特征"]
    return []


def configurable_scene_codes() -> list[str]:
    """当前可配置（前端可选中并保存成功）的场景码列表。"""
    return [code for code, scene in SCENES.items() if scene_configurability(scene)[0]]


def unsupported_scene_codes() -> list[str]:
    """当前边缘 Agent 未实现（拒绝下发）的场景码列表（诊断/测试用）。"""
    return [code for code, scene in SCENES.items() if not is_edge_implementable(scene)]


def list_scenes(category: str | None = None) -> list[SceneDef]:
    """列出场景定义，可按 category 过滤。"""
    items = list(SCENES.values())
    if category:
        items = [s for s in items if s.category == category]
    return items
