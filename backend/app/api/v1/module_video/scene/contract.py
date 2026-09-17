"""边缘 Agent 能力契约（场景可配置性的唯一事实源）。

场景是否「可配置」由本契约（模型族 / 事件特性 / 外部资产）+ 求值器叶子实现状态共同推导，
而非逐场景硬编码的清单。Agent 侧契约升级后，只需在下方声明对应能力位，相关场景会自动
解锁（或继续置灰）并给出数据驱动的原因，无需改动逐个场景的判断逻辑。

三个契约位及精确翻转条件：

1. ``AGENT_MODEL_FAMILIES``（模型族）：对齐 ModelDeploy
   ``application/aistation_agent/capability.cpp:detect_capabilities`` 上报的族集合。
   - B1 已接线 obb/iseg，故默认纳入；二者未落地时 OBB_DET/I_SEG 会自动置灰。
   - 后续每落地一族（pose/face_rec/...）在此加入，或在 Agent 改为按编译开关上报后
     改为运行时读取设备能力。

2. ``AGENT_EVENT_FEATURES``（事件特性）：Agent 事件载荷是否携带某类结果。
   - ``classification``：纯分类/属性分类结果写入事件并进入 sink。
   - 当前不声明：Agent 明确丢弃纯 classification 结果（``pipeline.cpp:419-430``），
     分类结果无 label_name/attributes/text，故 SCENE_CLS/DEFECT_CLS/NO_MASK 永不命中。
   - **翻转条件（B2）**：Agent 让分类结果（label_name/attributes）进入事件 sink 后，
     在此加入 ``"classification"``，上述三个场景即自动转为可配置。

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
    }
)

# Agent 事件载荷特性（见模块 docstring 的翻转条件）。
AGENT_EVENT_FEATURES: frozenset[str] = frozenset()

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
