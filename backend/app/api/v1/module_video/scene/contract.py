"""边缘 Agent 能力契约（场景可配置性的唯一事实源）。

场景是否「可配置」由本契约（模型族 / 事件特性 / 外部资产）+ 求值器叶子实现状态共同推导，
而非逐场景硬编码的清单。Agent 侧契约升级后，只需在下方声明对应能力位，相关场景会自动
解锁（或继续置灰）并给出数据驱动的原因，无需改动逐个场景的判断逻辑。

三个契约位及精确翻转条件：

1. ``AGENT_MODEL_FAMILIES``（模型族）：对齐 ModelDeploy
   ``application/aistation_agent/capability.cpp:detect_capabilities`` 上报的族集合。
   - B1 已接线 obb/iseg，故默认纳入；二者未落地时 OBB_DET/I_SEG 会自动置灰。
   - ``pose``：姿态切片新增。云侧契约已定稿（关键点事件 + keypoint_geometry 叶子），
     Agent 侧 capability.cpp 上报由并行姿态切片补齐；补齐前本集合比 Agent 实际上报多
     ``pose`` 一项，跨仓对拍测试按显式「在途族」清单放行（见 test_scene_edge_support.py）。
   - B2b 新增 ``sem``/``face_landmark``/``doc``/``barcode``：均复用既有事件字段
     （``attributes``/``keypoints``/``text``），Agent 侧接线并行落地中，同样按「在途族」放行。
   - 后续每落地一族（face_rec/...）在此加入，或在 Agent 改为按编译开关上报后
      改为运行时读取设备能力。

2. ``AGENT_EVENT_FEATURES``（事件特性）：Agent 事件载荷是否携带某类结果。
   - ``classification``：纯分类/属性分类结果写入事件并进入 sink。
     **已落地（B2a）**：Agent 让分类结果（整帧框 + top-1 label_name + 类别分数 attributes）
     进入事件 sink（ModelDeploy ``ff0650c``，见 ``tests/test_classification_event.cpp``），
     故此处声明 ``"classification"``，SCENE_CLS/DEFECT_CLS/NO_MASK 自动转为可配置。
    - ``keypoints``：姿态模型的关键点写入事件（``objects[].keypoints=[[x,y,score],...]``，
      归一化 0~1）。**已声明（姿态切片）**：Agent 姿态事件契约定稿（键名与归一化口径见
      ``edge/consumer.py::normalize_edge_event``），云端侧据此刻画 FALL/CLIMB/SMOKE_PHONE/
      HAND_GESTURE 的依赖；Agent 侧接线在并行切片中落地。
    - ``face_attributes``：人脸属性/活体分数写入事件 ``objects[].attributes``
      （face_attr 发射 ``{"gender_male":..,"age_young":..}``；face_as 发射 ``{"liveness":..}``）。
      **已声明（B2a）**：云端复用既有 ``attribute`` 叶子判分；Agent 侧 face_attr/face_as
      接线并行落地（模型族 ``face_attr``/``face_as`` 在途）。
    - ``depth``：深度模型输出写入事件 ``objects[].depth``（float，米）。**已声明（B2a）**：
      云端以 ``distance`` 叶子判定 DEPTH_SAFE；Agent 侧 depth 接线并行落地（族 ``depth`` 在途）。
    - 若 Agent 侧回退某契约，撤下对应能力位即会重新按原因置灰（见契约一致性测试）。

3. ``AGENT_ASSETS``（外部资产）：云端底库等非代码资产。
   - ``face_gallery``：人脸底库（FACE_REC/STRANGER）；``reid_gallery``：跨镜底库（REID_TRACK）。
   - **翻转条件（B3/B5）**：底库表 + 导入 API + Agent 装载链路就绪后在此加入。
"""
from __future__ import annotations

# 模型族别名 → 规范族名（向后兼容旧写法）。
# 规范族名与 Agent capability 上报一致（``face``）；``face_detection`` 是 Agent 侧
# 「模型 type」名，作为族别名接受，避免 scene.model_families 两套写法分裂。
FAMILY_ALIASES: dict[str, str] = {
    "face_detection": "face",
}

# 边缘参考构建上报的模型族（规范名，与 Agent capability 对齐）。
AGENT_MODEL_FAMILIES: frozenset[str] = frozenset(
    {
        "det",
        "cls",
        "face",
        "pedestrian_attribute",
        "ocr",
        "lpr",
        "tracking",
        # B1 纯接线：Agent 已支持 obb/iseg pipeline
        "obb",
        "iseg",
        # 姿态切片：关键点事件 + keypoint_geometry 叶子（Agent 侧上报并行落地中）
        "pose",
        # B2a 人脸属性/活体/深度：云侧契约先行声明，Agent 侧接线并行落地中
        "face_attr",
        "face_as",
        "depth",
        # B2b 语义分割/人脸关键点/文档/条码：事件契约复用既有字段（attributes/keypoints/text），
        # Agent 侧 capability 上报并行落地中（见 test_scene_edge_support.py 的在途族清单）。
        "sem",
        "face_landmark",
        "doc",
        "barcode",
    }
)

# Agent 事件载荷特性（见模块 docstring 的翻转条件）。
# B2a：分类结果（整帧框 + label_name + attributes）已进入边缘事件 sink，故声明 classification。
# 姿态切片：姿态关键点已进入事件契约（objects[].keypoints，归一化 0~1），故声明 keypoints。
# B2a：人脸属性/活体分数（objects[].attributes）与深度（objects[].depth，米）已定稿。
AGENT_EVENT_FEATURES: frozenset[str] = frozenset(
    {"classification", "keypoints", "face_attributes", "depth"}
)

# 云端外部资产（见模块 docstring 的翻转条件）。
AGENT_ASSETS: frozenset[str] = frozenset()

# 外部资产中文名（用于生成面向用户的置灰原因）
_ASSET_LABELS: dict[str, str] = {
    "face_gallery": "人脸底库",
    "reid_gallery": "跨镜底库",
}

# 目录 pipeline[].type 的旧写法/别名 → 规范名。
# 规范名对齐 Agent ``config_adapter.cpp:normalize_model_type``（det→detection、
# cls→classification、face→face_detection、ped_attr→pedestrian_attribute）；
# iseg 的旧写法 seg 在 Agent 侧需同时接受（见批报告 concern）。
PIPELINE_TYPE_ALIASES: dict[str, str] = {
    "det": "detection",
    "cls": "classification",
    "face": "face_detection",
    "ped_attr": "pedestrian_attribute",
    "seg": "iseg",
    "instance_seg": "iseg",
}


def canonical_family(name: str) -> str:
    """把模型族名归一化为规范写法（小写 + 去空格 + 别名解析）。"""
    key = str(name or "").strip().lower()
    return FAMILY_ALIASES.get(key, key)


def canonical_families(names) -> list[str]:
    """归一化一族名列表：去空、去重、保持稳定顺序。"""
    out: list[str] = []
    for name in names or []:
        canonical = canonical_family(name)
        if canonical and canonical not in out:
            out.append(canonical)
    return out


def has_model_family(name: str) -> bool:
    """该模型族是否已由参考 Agent 构建支持。"""
    return canonical_family(name) in AGENT_MODEL_FAMILIES


def supports_event_feature(name: str) -> bool:
    """Agent 事件载荷是否已具备该特性（如 classification）。"""
    return str(name or "").strip().lower() in AGENT_EVENT_FEATURES


def has_asset(name: str) -> bool:
    """云端是否已具备该外部资产（如 face_gallery）。"""
    return str(name or "").strip().lower() in AGENT_ASSETS


def asset_label(name: str) -> str:
    """外部资产的中文名（未知资产原样返回）。"""
    key = str(name or "").strip().lower()
    return _ASSET_LABELS.get(key, key)


def canonical_pipeline_type(name: str) -> str:
    """把 pipeline[].type 归一化为 Agent 侧规范模型 type。"""
    key = str(name or "").strip().lower()
    return PIPELINE_TYPE_ALIASES.get(key, key)
