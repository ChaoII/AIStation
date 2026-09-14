"""边缘事件接入：MQTT 消费者与事件归一化（云边 spec §7）。

设计要点：
- `aiomqtt` **懒加载**：未安装或未启用时仅告警并直接返回，不阻塞应用启动。
- 收到事件后先按 `event_id` 去重（短时、有界、带 TTL），再归一化为
  `InferenceService.process_detection_callback` 兼容结构，复用现有告警链路。
- 连接异常指数退避重连；取消时向上抛出 `CancelledError`。
"""
import asyncio
import json
import ssl
import time
from collections import OrderedDict
from urllib.parse import urlparse

from app.config.setting import settings
from app.core.logger import logger


def normalize_edge_event(payload: dict) -> dict:
    """把 Agent 事件（spec §7）归一化为检测回调兼容结构。

    参数:
    - payload (dict): MQTT/HTTP 上报的原始事件。

    返回:
    - dict: 补充 `snapshot_path`（取 `snapshot.ref` 或已有值）、`frame_timestamp`
      （取 `ts`）与内联 `snapshot_data`（取 `snapshot.data`），其余字段原样透传。
    """
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    normalized = {
        **payload,
        "snapshot_path": snapshot.get("ref") or payload.get("snapshot_path"),
        "frame_timestamp": payload.get("frame_timestamp") or payload.get("ts"),
    }
    snapshot_data = payload.get("snapshot_data") or snapshot.get("data")
    if snapshot_data:
        normalized["snapshot_data"] = snapshot_data

    # 事件 v2：objects[] → detections[]（复用既有告警链路），并保留属性/scene_type
    objs = payload.get("objects")
    dets = normalized.get("detections")
    if isinstance(objs, list):
        if not dets:
            # 仅有 objects：由 objects 派生 detections（含属性/轨迹）
            dets = []
            for obj in objs:
                if not isinstance(obj, dict):
                    continue
                bbox = obj.get("bbox") or {}
                det = {
                    "label": obj.get("label", ""),
                    "label_id": obj.get("label_id", 0),
                    "confidence": obj.get("confidence", 0.0),
                    "bbox": bbox,
                }
                if obj.get("track_id") is not None:
                    det["track_id"] = obj["track_id"]
                if isinstance(obj.get("attributes"), dict):
                    det["attributes"] = obj["attributes"]
                # OCR 文本（事件 v2 objects[].text/text_score）需保留，供文本规则判定
                if obj.get("text") is not None:
                    det["text"] = obj["text"]
                if obj.get("text_score") is not None:
                    det["text_score"] = obj["text_score"]
                dets.append(det)
            normalized["detections"] = dets
        else:
            # 事件 v2 同时含 detections 与 objects：按索引把属性/轨迹并入 detections，
            # 避免属性随 objects 一起丢失导致属性规则永不命中。
            for i, obj in enumerate(objs):
                if i >= len(dets) or not isinstance(obj, dict):
                    continue
                if not isinstance(dets[i], dict):
                    continue
                if "attributes" not in dets[i] and isinstance(obj.get("attributes"), dict):
                    dets[i]["attributes"] = obj["attributes"]
                if "track_id" not in dets[i] and obj.get("track_id") is not None:
                    dets[i]["track_id"] = obj["track_id"]
                # OCR 文本同样按索引并入 detections，避免随 objects 一起丢失
                if "text" not in dets[i] and obj.get("text") is not None:
                    dets[i]["text"] = obj["text"]
                if "text_score" not in dets[i] and obj.get("text_score") is not None:
                    dets[i]["text_score"] = obj["text_score"]
    return normalized


def parse_mqtt_broker(url: str) -> tuple[str, int]:
    """解析 MQTT Broker 地址为 `(host, port)`。

    支持 `mqtt://host:port`、`tcp://host:port`、`mqtts://host` 或纯 `host[:port]`。
    TLS scheme 默认端口 8883，其余默认 1883；空串返回 `("", 1883)`。
    """
    raw = (url or "").strip()
    if not raw:
        return "", 1883
    if "://" not in raw:
        raw = f"mqtt://{raw}"
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    default_port = 8883 if parsed.scheme in ("mqtts", "ssl", "tls") else 1883
    return host, int(parsed.port or default_port)


def uses_mqtt_tls(url: str) -> bool:
    """判断 Broker 地址是否使用 TLS（`mqtts://` / `ssl://` / `tls://`）。

    纯 `host[:port]` 或 `mqtt://` 视为明文，返回 False。
    """
    raw = (url or "").strip()
    if not raw or "://" not in raw:
        return False
    return urlparse(raw).scheme in ("mqtts", "ssl", "tls")


def build_mqtt_tls_context(url: str) -> ssl.SSLContext | None:
    """为 TLS Broker 构造默认校验的 SSL 上下文；明文地址返回 None。

    使用 `ssl.create_default_context()`（校验服务端证书与主机名），
    对应 aiomqtt 2.x 的 `Client(tls_context=...)` 参数。
    """
    if not uses_mqtt_tls(url):
        return None
    return ssl.create_default_context()


class _Dedup:
    """短时事件去重集合：按插入顺序有界淘汰 + TTL 过期。"""

    def __init__(self, maxsize: int = 5000, ttl: float = 600.0) -> None:
        self._maxsize = max(1, int(maxsize))
        self._ttl = float(ttl)
        self._items: OrderedDict[str, float] = OrderedDict()

    def _purge(self) -> None:
        """从最旧开始清理已超过 TTL 的记录（插入序即时间序）。"""
        now = time.monotonic()
        while self._items:
            _, ts = next(iter(self._items.items()))
            if now - ts > self._ttl:
                self._items.popitem(last=False)
            else:
                break

    def seen(self, event_id: str) -> bool:
        """判断 `event_id` 是否已在保留窗口内处理过。"""
        if not event_id:
            return False
        self._purge()
        ts = self._items.get(event_id)
        return ts is not None and (time.monotonic() - ts) <= self._ttl

    def mark(self, event_id: str) -> None:
        """记录 `event_id`，并按容量上限淘汰最旧记录。"""
        if not event_id:
            return
        self._purge()
        self._items[event_id] = time.monotonic()
        self._items.move_to_end(event_id)
        while len(self._items) > self._maxsize:
            self._items.popitem(last=False)


def dedup(maxsize: int = 5000, ttl: float = 600.0) -> _Dedup:
    """创建去重集合（默认 5000 条 / 10 分钟）。"""
    return _Dedup(maxsize=maxsize, ttl=ttl)


class EdgeEventConsumer:
    """MQTT 边缘事件消费者：订阅通配主题并复用现有告警链路。"""

    def __init__(self) -> None:
        self._dedup = dedup()
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> asyncio.Task:
        """以后台任务方式启动消费者，返回该任务句柄。"""
        self._stopped = False
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        """停止消费者并等待后台任务退出。"""
        self._stopped = True
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"停止边缘事件消费者时发生异常: {e}")

    @staticmethod
    def _import_aiomqtt():
        """懒加载 aiomqtt；未安装时返回 None。"""
        try:
            import aiomqtt
        except ImportError:
            logger.warning("未安装 aiomqtt，边缘事件消费者未启动（执行 uv sync 后可用）")
            return None
        return aiomqtt

    def _build_client(self, aiomqtt, host: str, port: int, tls_context=None):
        """构造 aiomqtt.Client（仅在有用户名/密码时携带凭证，TLS 时传入上下文）。"""
        kwargs: dict = {
            "hostname": host,
            "port": port,
            "identifier": settings.MQTT_CLIENT_ID,
        }
        if settings.MQTT_USERNAME:
            kwargs["username"] = settings.MQTT_USERNAME
        if settings.MQTT_PASSWORD:
            kwargs["password"] = settings.MQTT_PASSWORD
        if tls_context is not None:
            kwargs["tls_context"] = tls_context
        return aiomqtt.Client(**kwargs)

    async def run(self) -> None:
        """连接 Broker 并持续消费；禁用/无依赖/无地址时直接返回。"""
        if not settings.MQTT_ENABLED:
            logger.debug("MQTT_ENABLED=false，边缘事件消费者未启动")
            return

        aiomqtt = self._import_aiomqtt()
        if aiomqtt is None:
            return

        host, port = parse_mqtt_broker(settings.MQTT_BROKER_URL)
        if not host:
            logger.warning("MQTT_BROKER_URL 未配置，边缘事件消费者未启动")
            return

        tls_context = build_mqtt_tls_context(settings.MQTT_BROKER_URL)
        topic = settings.MQTT_SUBSCRIBE_TOPIC
        backoff = 1
        while not self._stopped:
            try:
                async with self._build_client(aiomqtt, host, port, tls_context) as client:
                    await client.subscribe(topic, qos=int(settings.MQTT_QOS))
                    backoff = 1
                    scheme = "mqtts" if tls_context is not None else "mqtt"
                    logger.info(f"✅ 边缘事件消费者已订阅 {topic} ({scheme}://{host}:{port})")
                    async for message in client.messages:
                        await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"MQTT 事件消费者连接异常，{backoff}s 后重连: {e}")
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    raise
                backoff = min(backoff * 2, 60)

    async def _handle_message(self, message) -> None:
        """解析 MQTT 报文并交给归一化处理。"""
        try:
            data = json.loads(message.payload)
        except (ValueError, TypeError) as e:
            logger.warning(f"忽略非法边缘事件报文: {e}")
            return
        if not isinstance(data, dict):
            logger.warning("忽略非对象的边缘事件报文")
            return
        await self._process_payload(data)

    async def _process_payload(self, payload: dict) -> None:
        """去重后归一化并调用现有检测回调创建告警。"""
        event_id = str(payload.get("event_id") or "").strip()
        if event_id and self._dedup.seen(event_id):
            logger.debug(f"忽略重复边缘事件: event_id={event_id}")
            return

        from app.api.v1.module_video.inference.service import InferenceService

        event = normalize_edge_event(payload)
        try:
            result = await InferenceService.process_detection_callback(event)
        except Exception as e:
            logger.error(f"处理边缘事件失败: event_id={event_id} {e}")
            return

        if event_id:
            self._dedup.mark(event_id)
        alarm_created = result.get("alarm_created") if isinstance(result, dict) else "?"
        logger.info(
            f"边缘事件已处理: event_id={event_id} camera={event.get('camera_id')} "
            f"alarm={alarm_created}"
        )
