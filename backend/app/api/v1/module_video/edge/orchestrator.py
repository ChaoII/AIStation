"""布控任务编排：能力校验 → 编译 Agent TaskConfig → 经控制面下发/启停。

spec: docs/superpowers/specs/2026-09-12-cloud-edge-visual-analysis-design.md §5/§6
"""
from sqlalchemy import func, select

from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel
from app.api.v1.module_video.edge.agent_client import EdgeAgentClient
from app.api.v1.module_video.edge.model import EdgeDeviceModel
from app.api.v1.module_video.edge.service import capability_satisfies
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
    "SEG": "seg",
    "CLASSIFY": "cls",
    "CLASS": "cls",
    "OBB": "obb",
}


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


def build_agent_task_config(task, camera, algorithm, events: dict | None = None) -> dict:
    """把 task/camera/algorithm 编译为 spec §6 的 Agent TaskConfig（纯函数）。"""
    runtime_config = getattr(algorithm, "runtime_config", None) or {}
    preset_params = getattr(algorithm, "preset_params", None) or {}
    runtime_overrides = getattr(task, "runtime_overrides", None) or {}
    params_overrides = getattr(task, "params_overrides", None) or {}

    merged_runtime = {**runtime_config, **runtime_overrides}
    merged_params = {**preset_params, **params_overrides}

    confidence = merged_params.get("confidence_threshold", merged_params.get("conf_threshold", 0.45))
    input_size = merged_params.get("input_size") or merged_runtime.get("input_size") or [640, 640]
    labels = merged_params.get("labels") or []
    alarm_interval = merged_params.get("alarm_interval_sec") or merged_runtime.get("alarm_interval_sec") or 30

    # 场景目录：PED_ATTR 编译为 det+cls pipeline，其余保持单模型条目
    scene = get_scene(getattr(algorithm, "scene_type", "") or "")
    base_model = {
        "name": algorithm.name,
        "backend": merged_runtime.get("backend") or "trt",
        "device": merged_runtime.get("device") or "gpu",
        "labels": labels,
        "input_size": input_size,
        "confidence_threshold": confidence,
    }
    if scene is not None and scene.code == "PED_ATTR":
        models = [{
            **base_model,
            "type": "pedestrian_attribute",
            "det_url": algorithm.model_path or "",
            "cls_url": merged_params.get("cls_path") or merged_runtime.get("cls_path") or "",
            "attributes": merged_params.get("attributes") or [],
            "cls_threshold": merged_params.get("cls_threshold", 0.5),
            "password": merged_runtime.get("model_password") or "",
        }]
    elif scene is not None and scene.code in ("OCR_TEXT", "METER_OCR"):
        # OCR 场景编译为 det+cls+rec 三模型 pipeline，路径取覆盖合并后的参数/运行配置
        models = [{
            **base_model,
            "type": "ocr",
            "det_url": algorithm.model_path or "",
            "cls_url": merged_params.get("cls_path") or merged_runtime.get("cls_path") or "",
            "rec_url": merged_params.get("rec_path") or merged_runtime.get("rec_path") or "",
            "dict_url": merged_params.get("dict_path") or merged_runtime.get("dict_path") or "",
            "password": merged_runtime.get("model_password") or "",
        }]
    else:
        models = [{**base_model, "type": _resolve_model_type(algorithm), "url": algorithm.model_path or ""}]

    return {
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
        "roi": _normalize_roi(getattr(task, "detect_region", None)),
        "sensitivity": task.sensitivity if task.sensitivity is not None else 50,
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
        """
        runtime = getattr(algorithm, "runtime_config", None) or {}
        scene = get_scene(getattr(algorithm, "scene_type", "") or "")
        if scene is not None:
            requirement = {
                "model_families": scene.model_families,
                "backend": runtime.get("backend") or "trt",
                "running_channels": running_channels,
            }
        else:
            requirement = {
                "model_family": _resolve_model_type(algorithm),
                "backend": runtime.get("backend") or "trt",
                "running_channels": running_channels,
            }
        return capability_satisfies(capabilities, requirement)

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

        config = build_agent_task_config(task, camera, algorithm, events=build_events(task.camera_id, device.code if device is not None else "local"))
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
