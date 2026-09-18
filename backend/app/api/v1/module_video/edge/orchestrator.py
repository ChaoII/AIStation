"""布控任务编排：能力校验 → 编译 Agent TaskConfig → 经控制面下发/启停。

spec: docs/superpowers/specs/2026-09-12-cloud-edge-visual-analysis-design.md §5/§6
"""
import math

from sqlalchemy import func, select

from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel
from app.api.v1.module_video.edge.agent_client import EdgeAgentClient
from app.api.v1.module_video.edge.model import EdgeDeviceModel
from app.api.v1.module_video.edge.service import capability_satisfies
from app.api.v1.module_video.scene import contract
from app.api.v1.module_video.scene.catalog import get_scene
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import logger

# ModelDeploy 内置模型族关键词映射（默认 det）
_MODEL_TYPE_KEYWORDS: dict[str, str] = {
    "FACE": "face",
    "OCR": "ocr",
    "LPR": "lpr",
    "PLATE": "lpr",
    "POSE": "pose",
    "BEHAVIOR": "pose",
    # 与 Agent 上报族名对齐：细分实例分割规范名为 iseg（Agent normalize_model_type 兼容 seg/iseg）
    "SEG": "iseg",
    "CLASSIFY": "cls",
    "CLASS": "cls",
    "OBB": "obb",
}

# 设备上报后端时的偏好顺序：未显式指定时取设备可用后端中此顺序最优者
_BACKEND_PREFERENCE: tuple[str, ...] = ("trt", "ort", "mnn", "ncnn", "sophgo")
# 视为「自动协商」的占位值（前后端模板均可用它表示交由云端/设备决定）
_AUTO_VALUES: frozenset[str] = frozenset({"", "auto", "default"})
# 旧前端模板 runtime.engine → 规范后端名（模板迁移期兼容；仅作偏好，不作硬要求）
_ENGINE_TO_BACKEND: dict[str, str] = {
    "tensorrt": "trt",
    "trt": "trt",
    "onnxruntime": "ort",
    "ort": "ort",
    "mnn": "mnn",
    "ncnn": "ncnn",
    "sophgo": "sophgo",
}


def _first_present(mapping: dict, *keys: str):
    """按顺序返回第一个非空值；全为空返回 None。"""
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _normalize_backend(value) -> str | None:
    """把后端名/旧引擎名归一化；auto/空返回 None（表示未指定）。"""
    if value is None:
        return None
    name = str(value).strip().lower()
    if name in _AUTO_VALUES:
        return None
    return _ENGINE_TO_BACKEND.get(name, name)


def resolve_backend(runtime: dict | None, capabilities: dict | None = None) -> str:
    """协商推理后端：显式 `backend`（硬要求）> 旧 `engine`（偏好）> 设备上报 > 默认。

    - `runtime.backend` 非空且非 auto：原样返回，是否可用交由能力校验判定（硬要求）。
    - 旧模板 `runtime.engine`：仅作偏好，设备不支持时回退到设备可用后端；避免旧模板
      硬编码 tensorrt 使 ort-only Agent 的默认下发路径必然被拒（审计 §1.1 BLOCKER）。
    - 无设备上报（本机 Agent）时回退 `settings.EDGE_DEFAULT_BACKEND`。
    """
    runtime = runtime or {}
    caps = capabilities or {}
    available = [str(b).strip().lower() for b in (caps.get("backends") or []) if str(b).strip()]

    explicit = _normalize_backend(runtime.get("backend"))
    if explicit:
        return explicit

    legacy = _normalize_backend(runtime.get("engine"))
    if legacy and (not available or legacy in available):
        return legacy
    if legacy:
        logger.warning(
            f"[边缘编排] 旧运行时 engine={legacy} 设备不支持，按设备可用后端回退：{available}"
        )

    for preferred in _BACKEND_PREFERENCE:
        if preferred in available:
            return preferred
    if available:
        return available[0]
    return str(getattr(settings, "EDGE_DEFAULT_BACKEND", "ort") or "ort")


def resolve_device(runtime: dict | None, capabilities: dict | None = None) -> str:
    """协商推理设备：显式 `device`（硬）> 设备平台 > 旧 `gpu.enabled` > 默认。

    有设备上报平台时以平台为准（避免旧模板 `gpu.enabled=true` 把 CPU 设备误判为 GPU）；
    无设备上报（本机 Agent）时退回旧模板的 `gpu.enabled`，保持既有行为。
    """
    runtime = runtime or {}
    explicit = runtime.get("device")
    if explicit is not None and str(explicit).strip().lower() not in _AUTO_VALUES:
        return str(explicit).strip().lower()
    platform = str(((capabilities or {}).get("hardware") or {}).get("platform") or "").strip().lower()
    if platform:
        return "gpu" if platform in ("nvidia", "jetson") else "cpu"
    gpu = runtime.get("gpu")
    if isinstance(gpu, dict) and isinstance(gpu.get("enabled"), bool):
        return "gpu" if gpu["enabled"] else "cpu"
    return str(getattr(settings, "EDGE_DEFAULT_DEVICE", "cpu") or "cpu")


def resolve_input_size(params: dict | None, runtime: dict | None) -> list[int]:
    """协商输入分辨率：`input_size` 列表 > 旧 `input_width/height`（params 优先）。"""
    params, runtime = params or {}, runtime or {}
    size = _first_present(params, "input_size") or _first_present(runtime, "input_size")
    if isinstance(size, (list, tuple)) and len(size) >= 2:
        try:
            return [int(size[0]), int(size[1])]
        except (TypeError, ValueError):
            pass
    width = _first_present(params, "input_width") or _first_present(runtime, "input_width")
    height = _first_present(params, "input_height") or _first_present(runtime, "input_height")
    try:
        if width is not None and height is not None:
            return [int(width), int(height)]
    except (TypeError, ValueError):
        pass
    return [640, 640]


# 单事件嵌入对象数上限：人脸（face_rec）与跨镜（reid）共用。与 Agent
# `EventMeta::max_embeddings`（`application/aistation_agent/event_bus.hpp`，
# 常量 kMaxEmbeddingsPerEvent=8）缺省对齐。
# **两侧约定语义（跨仓一致，勿单方漂移）**：
#   - 顶层键名 `max_embeddings`（与 alarm_interval_sec/heartbeat_sec 同层）；
#   - 缺省 8；夹紧到 [0, 64]；`<= 0` 表示**禁用嵌入**（对象仍上报，只是不带 embedding）；
#   - Agent `config_adapter.cpp: out->max_embeddings = clamp(j.value("max_embeddings", 8), 0, 64)`
#     与本函数逐字同口径；`EventBus::apply_embedding_cap` 按 `<=0` 直接清空嵌入。
_DEFAULT_MAX_EMBEDDINGS = 8
# 云侧允许下发的上限（防御异常配置把上行事件放大；Agent 侧还有自身 Top-N 兜底）
_MAX_EMBEDDINGS_LIMIT = 64


def resolve_max_embeddings(params: dict | None, runtime: dict | None, scene) -> int | None:
    """协商单事件嵌入 Top-N 上限；无需下发的场景返回 None（保持既有 TaskConfig 不变）。

    - 显式 `max_embeddings`（params 优先于 runtime）→ 取整并夹到 [0, 64]（0=禁用嵌入）；
    - 未显式配置、但场景声明携带嵌入的模型族（``face_rec`` 人脸 / ``reid`` 跨镜）→ 下发缺省 8；
    - 其余场景不产生该键（Agent 缺省 8，行为等价），保证既有任务配置逐字段兼容。
    """
    # 注意：0 是合法值（禁用嵌入），不能用 `or` 串联（会把 0 当作缺省丢弃）
    raw = _first_present(params or {}, "max_embeddings")
    if raw is None:
        raw = _first_present(runtime or {}, "max_embeddings")
    if raw is None:
        families = contract.canonical_families(getattr(scene, "model_families", []) or []) if scene else []
        if not ({"face_rec", "reid"} & set(families)):
            return None
        return _DEFAULT_MAX_EMBEDDINGS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_EMBEDDINGS
    return max(0, min(_MAX_EMBEDDINGS_LIMIT, value))


def resolve_prompt_point(params: dict | None, runtime: dict | None) -> list[float] | None:
    """解析 SAM_SEG 提示点（归一化 ``[x, y]``）；未配置/非法返回 None。

    兼容编排/画布可能给出的三种写法：``[[x,y], ...]``（取首点）、``[x,y]``、``{"x":..,"y":..}``。
    Agent 侧读**顶层** `prompt_point`（`config_adapter.cpp`）并回退给 sam/iseg 模型条目；
    坐标钳制到 [0,1]（与 Agent 侧一致）。
    """
    raw = _first_present(params or {}, "prompt_point") or _first_present(runtime or {}, "prompt_point")
    if raw is None:
        return None
    x = y = None
    if isinstance(raw, dict):
        x, y = raw.get("x"), raw.get("y")
    elif isinstance(raw, (list, tuple)) and raw:
        first = raw[0]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            x, y = first[0], first[1]
        elif len(raw) >= 2:
            x, y = raw[0], raw[1]
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(fx) and math.isfinite(fy)):
        return None
    return [max(0.0, min(1.0, fx)), max(0.0, min(1.0, fy))]


def sensitivity_to_conf(sensitivity, base: float = 0.5) -> float:
    """灵敏度(0-100) → 置信度阈值；公式与本地 `inference.worker.sensitivity_to_conf` 一致。"""
    try:
        value = max(0, min(100, int(sensitivity)))
    except (TypeError, ValueError):
        value = 50
    return max(0.05, min(0.95, base * (1 - (value - 50) / 100.0)))


def resolve_confidence(params: dict | None, sensitivity=None) -> float:
    """协商置信度阈值：显式阈值 > 由任务灵敏度推导（与本地 worker 同语义）。"""
    params = params or {}
    raw = _first_present(params, "confidence_threshold", "conf_threshold", "confidence")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    return sensitivity_to_conf(50 if sensitivity is None else sensitivity)


def _resolve_model_type(algorithm) -> str:
    """由算法运行配置或算法类型推断 ModelDeploy 模型族，缺省 det。"""
    runtime = getattr(algorithm, "runtime_config", None) or {}
    explicit = runtime.get("task_type") or runtime.get("model_type")
    if explicit:
        return str(explicit)
    algo_type = str(getattr(algorithm, "algorithm_type", "") or "").upper()
    for keyword, model_type in _MODEL_TYPE_KEYWORDS.items():
        if keyword in algo_type:
            return model_type
    return "det"


def _normalize_roi(region: dict | list | None) -> list:
    """把 detect_region 归一化为点集 [[x,y], ...]；支持 points 列表或 x1y1x2y2。"""
    if not region:
        return []
    if isinstance(region, list):
        return region
    points = region.get("points")
    if points:
        return points
    x1, y1, x2, y2 = region.get("x1"), region.get("y1"), region.get("x2"), region.get("y2")
    if None not in (x1, y1, x2, y2):
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return []


def _resolve_stream_url(task, camera) -> str:
    """按分析码流取 RTSP 地址，缺省回退 ZLM FLV。"""
    stream_type = (getattr(task, "stream_type", None) or "SUB").upper()
    main = getattr(camera, "rtsp_url_main", None)
    sub = getattr(camera, "rtsp_url_sub", None)
    stream_url = ((main if stream_type == "MAIN" else sub) or "").strip()
    stream_id = getattr(camera, "stream_id", None)
    if not stream_url and stream_id:
        stream_url = f"{settings.ZLM_BASE_URL}/live/{stream_id}.live.flv"
    return stream_url


def normalize_broker_scheme(url: str) -> str:
    """把 MQTT Broker 地址统一为 paho 可识别的 tcp:// 或 ssl://。

    Agent 用 paho，只认 tcp:// 与 ssl://；aiomqtt 侧由 parse_mqtt_broker 解析。
    空串原样返回；未知 scheme 原样返回，交由实现/运维纠正。
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("mqtts://"):
        return "ssl://" + raw[len("mqtts://"):]
    if raw.startswith("mqtt://"):
        return "tcp://" + raw[len("mqtt://"):]
    if "://" not in raw:
        return "tcp://" + raw
    return raw


# pipeline 中不产生 models[] 条目的角色：跟踪由顶层 tracking 配置承载（见 build_agent_task_config）
_TRACKING_ROLE = "tracking"


def _build_pedestrian_attribute_model(base_model: dict, algorithm, merged_params: dict, merged_runtime: dict) -> dict:
    """PED_ATTR：目录 pipeline 声明 det+cls 两角色，Agent 侧合并为单条 pedestrian_attribute。"""
    return {
        **base_model,
        "type": "pedestrian_attribute",
        "det_url": algorithm.model_path or "",
        "cls_url": merged_params.get("cls_path") or merged_runtime.get("cls_path") or "",
        "attributes": merged_params.get("attributes") or [],
        "cls_threshold": merged_params.get("cls_threshold", 0.5),
        "password": merged_runtime.get("model_password") or "",
    }


def _build_ocr_model(base_model: dict, algorithm, merged_params: dict, merged_runtime: dict) -> dict:
    """OCR：单条 ocr 条目展开 det/cls/rec/dict 子模型路径（Agent config_adapter 的 ocr 分支）。"""
    return {
        **base_model,
        "type": "ocr",
        "det_url": algorithm.model_path or "",
        "cls_url": merged_params.get("cls_path") or merged_runtime.get("cls_path") or "",
        "rec_url": merged_params.get("rec_path") or merged_runtime.get("rec_path") or "",
        "dict_url": merged_params.get("dict_path") or merged_runtime.get("dict_path") or "",
        "password": merged_runtime.get("model_password") or "",
    }


def _build_lpr_model(base_model: dict, algorithm, merged_params: dict, merged_runtime: dict) -> dict:
    """LPR：单条 lpr 条目展开 det/rec 两子模型路径（Agent config_adapter 的 lpr 分支）。"""
    return {
        **base_model,
        "type": "lpr",
        "det_url": algorithm.model_path or "",
        "rec_url": merged_params.get("rec_path") or merged_runtime.get("rec_path") or "",
        "password": merged_runtime.get("model_password") or "",
    }


# 目录 model_families 中「Agent 单条复合模型」的家族 → 构造器。
# 与 pipeline 角色解耦：PED_ATTR 的 pipeline 是 [det, cls]，但 Agent 模型 type 为 pedestrian_attribute，
# 故必须按家族显式登记，避免逐角色展开成两条而与 Agent 契约不符。
_COMPOUND_FAMILY_BUILDERS = {
    "pedestrian_attribute": _build_pedestrian_attribute_model,
}


def _build_face_rec_models(
    base_model: dict, algorithm, merged_params: dict, merged_runtime: dict
) -> list[dict]:
    """FACE_REC/STRANGER：显式产出 ``face_detection`` + ``face_rec`` 两条复合管线模型。

    背景（B3 遗留）：Agent 的 face_rec 是「检测（SCRFD）+ 嵌入」复合模型，原先依赖
    「同任务中另有一条 face_detection 条目」自动补齐检测器（``config_adapter.cpp`` 的
    `shared_face_det` 回退）。云端这里把该关系**显式化**：face_rec 条目直接携带
    ``det_url``（检测器）与 ``url``/``rec_url``（嵌入模型），不再依赖兄弟条目。

    - 检测器：``face_det_path``/``face_det_url``/``det_path``/``det_url``，缺省算法主模型；
    - 嵌入：``face_rec_path``/``face_rec_url``/``embedding_path``/``embedding_url``/
      ``rec_path``/``rec_url``，缺省算法主模型（与既有 ``_resolve_role_model_url`` 口径一致）。
    兼容性：两 url 均缺省时与原「face_detection=主模型 + face_rec=主模型」一致；
    Agent 对 face_rec 条目的 ``det_url`` 解析已支持，故行为不变。
    """
    primary = algorithm.model_path or ""
    det_url = (
        _first_present(merged_params, "face_det_path", "face_det_url", "det_path", "det_url")
        or _first_present(merged_runtime, "face_det_path", "face_det_url", "det_path", "det_url")
        or primary
    )
    rec_url = (
        _first_present(
            merged_params,
            "face_rec_path", "face_rec_url", "embedding_path", "embedding_url",
            "rec_path", "rec_url",
        )
        or _first_present(
            merged_runtime,
            "face_rec_path", "face_rec_url", "embedding_path", "embedding_url",
            "rec_path", "rec_url",
        )
        or primary
    )
    return [
        {**base_model, "type": "face_detection", "url": det_url},
        {
            **base_model,
            "type": "face_rec",
            "url": rec_url,
            "det_url": det_url,
            "rec_url": rec_url,
        },
    ]


# 「多角色 pipeline → 多条显式模型条目」的复合族构造器（返回值即完整 models 列表）。
# face_rec：目录 pipeline 为 [face_detection, face_rec]，Agent 侧 face_rec 为复合类型，
# 但需显式携带检测器路径，故在此整体构造（而非逐角色展开）。
_COMPOUND_PIPELINE_BUILDERS = {
    "face_rec": _build_face_rec_models,
}

# 单条 pipeline 条目本身即「Agent 复合模型类型」的 type → 构造器（子模型 url 需展开）。
_SINGLE_MODEL_BUILDERS = {
    "ocr": _build_ocr_model,
    "lpr": _build_lpr_model,
}


def _resolve_role_model_url(
    model_type: str, role: str, merged_params: dict, merged_runtime: dict, primary_url: str
) -> str:
    """解析次级角色的模型路径：显式 `<type>_path`/`<type>_url` 或 `<role>_path`/`<role>_url`。

    缺省回退算法主模型路径（而非空串）：保证该角色始终被下发，不静默丢弃；权重不适配时
    由 Agent 加载阶段显式报错，而非云端少下一个模型导致场景「看似可配置、实际不生效」。
    """
    for key in (f"{model_type}_path", f"{model_type}_url", f"{role}_path", f"{role}_url"):
        value = _first_present(merged_params, key) or _first_present(merged_runtime, key)
        if value:
            return str(value)
    return primary_url


def _build_scene_models(scene, algorithm, merged_params: dict, merged_runtime: dict, base_model: dict) -> list[dict]:
    """按目录 pipeline **逐角色**下发模型（复合家族合并为单条）。

    - 无场景：保持既有「按算法类型关键词推断单模型」行为（INTRUSION 等保持 det）；
    - 复合家族（pedestrian_attribute）：pipeline 的 det+cls 合并为单条复合模型；
    - 其余：遍历 pipeline 每个条目产出模型，`tracking` 角色由顶层 tracking 承载不产出条目。

    关键不变量：目录声明的任何非 tracking 角色都不会被丢弃（type 取目录已规范化的
    pipeline[].type，Agent `normalize_model_type` 可识别）；新增家族（obb/iseg/sem/depth/
    face_*/doc/barcode）无需新增分支即自动下发，杜绝「多角色管线退回单 det」的静默缺陷。
    """
    primary_url = algorithm.model_path or ""
    if scene is None:
        return [{**base_model, "type": _resolve_model_type(algorithm), "url": primary_url}]

    families = contract.canonical_families(scene.model_families)
    # 复合管线族（face_rec）：整体构造多条显式模型条目（优先于单条复合族判定）
    compound_pipeline = next((f for f in families if f in _COMPOUND_PIPELINE_BUILDERS), None)
    if compound_pipeline is not None:
        return _COMPOUND_PIPELINE_BUILDERS[compound_pipeline](
            base_model, algorithm, merged_params, merged_runtime
        )

    compound = next((f for f in families if f in _COMPOUND_FAMILY_BUILDERS), None)
    if compound is not None:
        return [_COMPOUND_FAMILY_BUILDERS[compound](base_model, algorithm, merged_params, merged_runtime)]

    models: list[dict] = []
    for entry in scene.pipeline:
        model_type = contract.canonical_pipeline_type(entry["type"])
        if model_type == _TRACKING_ROLE:
            continue
        builder = _SINGLE_MODEL_BUILDERS.get(model_type)
        if builder is not None:
            models.append(builder(base_model, algorithm, merged_params, merged_runtime))
            continue
        # 管线首条为主模型（url=algorithm.model_path）；次级角色按约定键解析，缺省回退主模型路径。
        url = primary_url if not models else _resolve_role_model_url(
            model_type, entry.get("role") or "", merged_params, merged_runtime, primary_url
        )
        models.append({**base_model, "type": model_type, "url": url})
    return models


def build_agent_task_config(task, camera, algorithm, events: dict | None = None, capabilities: dict | None = None) -> dict:
    """把 task/camera/algorithm 编译为 spec §6 的 Agent TaskConfig（纯函数）。

    `capabilities` 为目标设备上报的能力清单：用于协商推理后端/设备，未显式指定时从中取值。
    后端/设备/输入分辨率/置信度均同时兼容新旧键（见 resolve_backend/resolve_device/
    resolve_input_size/resolve_confidence），保证前端 `runtime.engine`/`gpu`/`input_width`
    等旧键与规范键 `backend`/`device`/`input_size`/`confidence_threshold` 均能生效。
    """
    runtime_config = getattr(algorithm, "runtime_config", None) or {}
    preset_params = getattr(algorithm, "preset_params", None) or {}
    runtime_overrides = getattr(task, "runtime_overrides", None) or {}
    params_overrides = getattr(task, "params_overrides", None) or {}

    merged_runtime = {**runtime_config, **runtime_overrides}
    merged_params = {**preset_params, **params_overrides}

    # 置信度：显式阈值优先，缺省由任务灵敏度推导（顶层不再下发 Agent 不读的 sensitivity）
    confidence = resolve_confidence(merged_params, getattr(task, "sensitivity", None))
    input_size = resolve_input_size(merged_params, merged_runtime)
    labels = merged_params.get("labels") or []
    alarm_interval = merged_params.get("alarm_interval_sec") or merged_runtime.get("alarm_interval_sec") or 30
    backend = resolve_backend(merged_runtime, capabilities)
    device = resolve_device(merged_runtime, capabilities)

    # 目标跟踪：来源 runtime_config/preset_params 的 tracking，任务级覆盖已并入 merged_*；
    # 缺省关闭，algorithm 缺省 bytetrack（见 SP4 跟踪契约 spec §4）。
    tracking_cfg = merged_runtime.get("tracking") or merged_params.get("tracking") or {}
    tracking = {
        "enabled": bool(tracking_cfg.get("enabled", False)),
        "algorithm": tracking_cfg.get("algorithm") or "bytetrack",
    }

    # 场景目录驱动：按 pipeline 逐角色下发模型（复合家族合并为单条），不再逐场景硬编码分支
    scene = get_scene(getattr(algorithm, "scene_type", "") or "")
    base_model = {
        "name": algorithm.name,
        "backend": backend,
        "device": device,
        "labels": labels,
        "input_size": input_size,
        "confidence_threshold": confidence,
    }
    models = _build_scene_models(scene, algorithm, merged_params, merged_runtime, base_model)

    config = {
        "task_id": task.id,
        "tenant": merged_runtime.get("tenant") or "default",
        "algorithm_type": getattr(algorithm, "algorithm_type", "") or "",
        "scene_type": getattr(algorithm, "scene_type", "") or "",
        "camera": {
            "id": camera.id,
            "name": camera.name,
            "url": _resolve_stream_url(task, camera),
            "transport": merged_runtime.get("transport") or "tcp",
        },
        "models": models,
        "tracking": tracking,
        "roi": _normalize_roi(getattr(task, "detect_region", None)),
        # 注：不再下发顶层 `sensitivity`（Agent 全程不读，见审计 §1.3）；该旋钮已通过
        # resolve_confidence 折算进 models[].confidence_threshold，对边缘真正生效。
        "schedule": getattr(task, "schedule_json", None) or {},
        "alarm_interval_sec": int(alarm_interval),
        "events": events or {},
        "decoder": merged_runtime.get("decoder") or {"hw_accel": "cuda", "device_only": True},
        "encoder": merged_runtime.get("encoder") or {"codec": "h264_nvenc", "format": "flv", "bitrate_kbps": 2500},
        "preview": {
            "enabled": bool(getattr(settings, "EDGE_PREVIEW_ENABLED", True)),
            "format": "snapshot",
        },
    }

    # 嵌入 Top-N 上限（face_rec 人脸 / reid 跨镜共用；仅这两类场景或显式配置时下发；
    # 键名对齐 Agent 顶层读取，语义见 resolve_max_embeddings 的约定）
    max_embeddings = resolve_max_embeddings(merged_params, merged_runtime, scene)
    if max_embeddings is not None:
        config["max_embeddings"] = max_embeddings
    # 交互分割提示点（SAM_SEG 的 prompt_point → Agent 顶层；模型条目缺省回退使用）
    prompt_point = resolve_prompt_point(merged_params, merged_runtime)
    if prompt_point is not None:
        config["prompt_point"] = prompt_point
    return config


def build_events(camera_id: int, edge_code: str) -> dict:
    """按视频分析模式构造事件通道参数（云端 HTTP 回调 / 边缘 MQTT）。

    MQTT：broker scheme 归一化为 paho 可识别形式；client_id 每边缘唯一；
    账号密码按 settings 下发。两分支均携带内联快照配置。
    """
    snapshot = {
        "enabled": bool(getattr(settings, "MQTT_SNAPSHOT_ENABLED", True)),
        "inline": bool(getattr(settings, "MQTT_SNAPSHOT_INLINE", True)),
        "quality": int(getattr(settings, "MQTT_SNAPSHOT_QUALITY", 75)),
        "max_width": int(getattr(settings, "MQTT_SNAPSHOT_MAX_WIDTH", 640)),
    }
    buffer = {"dir": "./events_buffer", "max_mb": 512}
    if settings.VIDEO_ANALYSIS_MODE == "cloud_edge":
        prefix = getattr(settings, "MQTT_TOPIC_PREFIX", "aistation/default/edge").rstrip("/")
        base = f"{prefix}/{edge_code}".rstrip("/")
        return {
            "transport": "mqtt",
            "mqtt": {
                "broker": normalize_broker_scheme(getattr(settings, "MQTT_BROKER_URL", "")),
                "topic_prefix": base,
                "topic": f"{base}/camera/{camera_id}/detect",
                "qos": int(getattr(settings, "MQTT_QOS", 1)),
                "client_id": f"aistation-agent-{edge_code}",
                "username": getattr(settings, "MQTT_USERNAME", "") or "",
                "password": getattr(settings, "MQTT_PASSWORD", "") or "",
            },
            "buffer": buffer,
            "snapshot": snapshot,
        }
    return {
        "transport": "http",
        "http": {
            "url": f"http://127.0.0.1:{settings.SERVER_PORT}{settings.ROOT_PATH}/video/algorithm/detection/callback",
            "token": settings.INFERENCE_CALLBACK_TOKEN,
        },
        "buffer": buffer,
        "snapshot": snapshot,
    }


class EdgeOrchestrator:
    """布控任务到边缘 Agent 的编排器。"""

    @staticmethod
    async def _load_task(task_id: int) -> AlgorithmTaskModel:
        async with async_db_session() as session:
            stmt = select(AlgorithmTaskModel).where(
                AlgorithmTaskModel.id == task_id,
                AlgorithmTaskModel.is_deleted.is_(False),
            )
            task = (await session.execute(stmt)).scalar_one_or_none()
        if not task:
            raise LookupError(f"算法任务不存在: {task_id}")
        return task

    @staticmethod
    async def _load_device(device_id: int) -> EdgeDeviceModel:
        async with async_db_session() as session:
            stmt = select(EdgeDeviceModel).where(
                EdgeDeviceModel.id == device_id,
                EdgeDeviceModel.is_deleted.is_(False),
            )
            device = (await session.execute(stmt)).scalar_one_or_none()
        if not device:
            raise CustomException(msg=f"边缘设备不存在: {device_id}", code=404, status_code=404)
        return device

    @classmethod
    async def _resolve_target(cls, task) -> tuple[str | None, EdgeDeviceModel | None]:
        """解析目标任务的控制面地址与所属设备；无则返回 (None, None) 以回退本地 worker。"""
        if getattr(task, "edge_device_id", None):
            device = await cls._load_device(task.edge_device_id)
            control_url = (device.control_url or "").strip()
            if not control_url:
                raise CustomException(msg=f"边缘设备未配置控制面地址: {device.code}", code=400, status_code=400)
            return control_url, device
        local_url = (settings.EDGE_LOCAL_CONTROL_URL or "").strip()
        return (local_url or None), None

    @staticmethod
    def _check_capability(capabilities: dict, algorithm, running_channels: int = 0) -> tuple[bool, str]:
        """校验设备能力是否满足该算法的模型族/后端/剩余路数。

        算法归属场景目录时，要求设备具备该场景所需的**全部**模型族（如 PED_ATTR
        需 pedestrian_attribute，仅靠 _resolve_model_type 会被误映射为 det 而放行）；
        无场景时回退到按算法推断的单一模型族，保持既有行为。
        后端取协商结果（显式 backend > 旧 engine > 设备上报），避免默认值恒为 trt
        而 ort-only Agent 被判为「设备不支持后端 trt」。
        """
        runtime = getattr(algorithm, "runtime_config", None) or {}
        scene = get_scene(getattr(algorithm, "scene_type", "") or "")
        backend = resolve_backend(runtime, capabilities)
        if scene is not None:
            requirement = {
                "model_families": scene.model_families,
                "backend": backend,
                "running_channels": running_channels,
            }
        else:
            requirement = {
                "model_family": _resolve_model_type(algorithm),
                "backend": backend,
                "running_channels": running_channels,
            }
        ok, reason = capability_satisfies(capabilities, requirement)
        if not ok and scene is not None:
            # 场景级失败给出可操作原因：所需模型族 vs 设备实际上报
            return False, f"该场景 {scene.code} 无法在该设备落地：{reason}"
        return ok, reason

    @staticmethod
    async def _count_running(device_id: int, exclude_id: int) -> int:
        async with async_db_session() as session:
            stmt = (
                select(func.count())
                .select_from(AlgorithmTaskModel)
                .where(
                    AlgorithmTaskModel.edge_device_id == device_id,
                    AlgorithmTaskModel.status == "RUNNING",
                    AlgorithmTaskModel.id != exclude_id,
                    AlgorithmTaskModel.is_deleted.is_(False),
                )
            )
            return int((await session.execute(stmt)).scalar() or 0)

    @staticmethod
    async def _update_status(task_id: int, status: str, error_log: str | None = None) -> None:
        async with async_db_session.begin() as session:
            stmt = select(AlgorithmTaskModel).where(AlgorithmTaskModel.id == task_id)
            task = (await session.execute(stmt)).scalar_one_or_none()
            if task:
                task.status = status
                task.error_log = error_log

    @classmethod
    async def start_task(cls, task_id: int) -> dict:
        """取任务→能力校验→编译→下发→启动→更新状态。

        返回 `delegated=False` 表示未配置边缘/本机 Agent，调用方应回退本地 worker。
        """
        task = await cls._load_task(task_id)
        camera = task.camera
        algorithm = task.algorithm
        if not camera:
            raise ValueError("任务未关联摄像头")
        if not algorithm:
            raise ValueError("任务未关联算法")

        control_url, device = await cls._resolve_target(task)
        if not control_url:
            return {
                "task_id": task_id,
                "status": "SKIPPED",
                "delegated": False,
                "message": "未配置边缘设备/本机 Agent，回退本地 worker",
            }

        if device is not None:
            running = await cls._count_running(device.id, exclude_id=task_id)
            ok, reason = cls._check_capability(device.capabilities, algorithm, running)
            if not ok:
                await cls._update_status(task_id, "ERROR", reason)
                raise CustomException(msg=f"边缘设备能力不足: {reason}", code=400, status_code=400)

        config = build_agent_task_config(
            task,
            camera,
            algorithm,
            events=build_events(task.camera_id, device.code if device is not None else "local"),
            capabilities=getattr(device, "capabilities", None) if device is not None else None,
        )
        secret = device.secret if device is not None else settings.EDGE_CONTROL_TOKEN
        client = EdgeAgentClient(control_url, secret)

        try:
            await client.dispatch(config)
            await client.start(task_id)
        except CustomException as e:
            await cls._update_status(task_id, "ERROR", e.msg)
            raise

        await cls._update_status(task_id, "RUNNING", None)
        logger.info(f"[边缘编排] 已下发并启动: task_id={task_id} control={control_url}")
        return {"task_id": task_id, "status": "RUNNING", "delegated": True, "message": "已下发并启动"}

    @classmethod
    async def stop_task(cls, task_id: int) -> dict:
        """停止边缘任务；`delegated=False` 表示应回退本地 worker。"""
        task = await cls._load_task(task_id)
        control_url, device = await cls._resolve_target(task)
        if not control_url:
            return {
                "task_id": task_id,
                "status": "SKIPPED",
                "delegated": False,
                "message": "未配置边缘设备/本机 Agent，回退本地 worker",
            }

        secret = device.secret if device is not None else settings.EDGE_CONTROL_TOKEN
        client = EdgeAgentClient(control_url, secret)
        try:
            await client.stop(task_id)
        except CustomException as e:
            await cls._update_status(task_id, "ERROR", e.msg)
            raise

        await cls._update_status(task_id, "STOPPED", None)
        logger.info(f"[边缘编排] 已停止: task_id={task_id} control={control_url}")
        return {"task_id": task_id, "status": "STOPPED", "delegated": True, "message": "已停止"}

    @classmethod
    async def delete_task(cls, task_id: int) -> dict:
        """删除边缘 Agent 侧任务；无边缘设备时不做任何操作（保持旧行为）。

        尽力而为：解析目标或 Agent 删除失败只记录日志并返回 SKIPPED，
        不向上抛出，以便调用方继续删除 DB 记录。
        """
        try:
            task = await cls._load_task(task_id)
            control_url, device = await cls._resolve_target(task)
        except Exception as e:  # noqa: BLE001 - 清理失败不应阻断 DB 删除
            logger.warning(f"[边缘编排] 解析边缘目标失败，跳过 Agent 删除: task_id={task_id} {e}")
            return {"task_id": task_id, "status": "SKIPPED", "delegated": False, "message": f"跳过: {e}"}

        # 本地 Agent / 无设备路径不触碰 Agent，回退旧行为
        if device is None or not control_url:
            return {"task_id": task_id, "status": "SKIPPED", "delegated": False, "message": "无边缘设备，跳过 Agent 删除"}

        client = EdgeAgentClient(control_url, device.secret)
        try:
            await client.delete(task_id)
        except Exception as e:  # noqa: BLE001 - 边缘清理失败仅告警
            msg = getattr(e, "msg", str(e))
            logger.warning(f"[边缘编排] 删除 Agent 任务失败（忽略）: task_id={task_id} {msg}")
            return {"task_id": task_id, "status": "SKIPPED", "delegated": True, "message": f"Agent 删除失败: {msg}"}

        logger.info(f"[边缘编排] 已删除 Agent 侧任务: task_id={task_id} control={control_url}")
        return {"task_id": task_id, "status": "DELETED", "delegated": True, "message": "已删除"}
