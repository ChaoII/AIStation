"""时序规则叶子状态存储（dwell / count_window / absence）。

设计要点：
- 优先复用应用的 Redis 配置（``settings.REDIS_*``）；未启用/连接失败时降级为
  进程内字典 + 线程锁，保证单测与无 Redis 环境可用。
- 观测键：``ai:temporal:{camera_id}:{alarm_type}:{label}:{scope}`` 的 hash，
  field 为 ``{track_key}\x1ffirst`` / ``{track_key}\x1flast``（轨迹首次/最近出现时间）。
  ``track_key``：有 ``track_id`` 用 ``t:{id}``，否则用 ``e:{ts}``（按事件计数）。
- 区域观测按 ``scope=region_fingerprint(region)`` 分桶，无区域使用 ``all``，
  避免不同区域的时序状态互相串扰。
- 时间由调用方注入（事件 ts），逻辑完全由入参决定，便于确定性测试。
"""
import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone

from app.config.setting import settings

log = logging.getLogger(__name__)

KEY_PREFIX = "ai:temporal"
_SCOPE_ALL = "all"
_SEP = "\x1f"
_FIRST = "first"
_LAST = "last"
_POS_P = "pos_p"  # 上一次观测中心 "x,y"
_POS_C = "pos_c"  # 当前观测中心 "x,y"
_ABSENT_MARK = "__absent__"
# 无 label（或仅给 labels 列表）时 absence 标记使用的聚合标签
ABSENT_ALL = "__all__"
_TTL_SEC = 24 * 3600  # 观测状态保留一天，防止 Redis 键无限增长


def _to_float(raw) -> float | None:
    """尽力转 float；None/布尔/非数值返回 None。"""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _center(d) -> tuple[float, float] | None:
    """取检测框中心 (x + w/2, y + h/2)；bbox 缺失/非法返回 None。"""
    if not isinstance(d, dict):
        return None
    bbox = d.get("bbox")
    if not isinstance(bbox, dict):
        return None
    x = _to_float(bbox.get("x"))
    y = _to_float(bbox.get("y"))
    w = _to_float(bbox.get("width"))
    h = _to_float(bbox.get("height"))
    if None in (x, y, w, h):
        return None
    return (x + w / 2.0, y + h / 2.0)


def _ser_pos(pos: tuple[float, float]) -> str:
    """位置序列化为 "x,y"（保留 6 位小数，避免浮点噪声）。"""
    return f"{round(pos[0], 6)},{round(pos[1], 6)}"


def _parse_pos(raw) -> tuple[float, float] | None:
    """解析位置："x,y" 字符串或 [x, y] 序列；非法返回 None。"""
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        x = _to_float(raw[0])
        y = _to_float(raw[1])
        return None if x is None or y is None else (x, y)
    if not isinstance(raw, str):
        return None
    parts = raw.split(",")
    if len(parts) != 2:
        return None
    x = _to_float(parts[0])
    y = _to_float(parts[1])
    return None if x is None or y is None else (x, y)


def to_epoch(ts) -> float:
    """把事件时间戳归一化为 epoch 秒；缺失/非法回退到当前时间。

    支持 int/float 秒、数字字符串、ISO8601（含 ``Z``）。绝不抛异常。
    """
    if isinstance(ts, bool):
        return time.time()
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        s = ts.strip()
        if s:
            num = _to_float(s)
            if num is not None:
                return num
            try:
                iso = s[:-1] + "+00:00" if s[-1] in ("Z", "z") else s
                dt = datetime.fromisoformat(iso)
            except ValueError:
                return time.time()
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
    return time.time()


def region_fingerprint(region) -> str | None:
    """归一化多边形区域的指纹，用于状态分桶；无/非法区域返回 None。"""
    if not isinstance(region, (list, tuple)) or len(region) < 3:
        return None
    pts = []
    for point in region:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        x = _to_float(point[0])
        y = _to_float(point[1])
        if x is None or y is None:
            return None
        pts.append([round(x, 6), round(y, 6)])
    raw = json.dumps(pts, separators=(",", ":"), ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


class TemporalStore:
    """时序观测状态存储：优先 Redis，失败/未启用时降级进程内字典。"""

    def __init__(self, prefer_redis: bool = True, redis_client=None) -> None:
        self._prefer_redis = prefer_redis
        self._lock = threading.Lock()
        self._memory: dict[str, dict[str, float]] = {}
        self._memory_meta: dict[str, float] = {}
        # 内存降级路径的过期时间（monotonic 秒）；与 Redis 路径 _TTL_SEC 语义一致，防无界增长
        self._memory_expiry: dict[str, float] = {}
        # 允许测试注入 Redis 客户端（如 fakeredis），绕过全局配置
        self._redis = redis_client
        self._redis_failed = False
        # Redis 故障冷却截止时间（monotonic）：冷却期内直接走内存，避免每条事件都阻塞超时
        self._redis_cooldown_until = 0.0

    # ------------------------------------------------------------- 后端选择
    def _mark_redis_failed(self, exc: Exception) -> None:
        """标记 Redis 不可用并进入冷却；冷却结束后会自动重连（不再永久降级）。"""
        self._redis = None
        if not self._redis_failed:
            log.warning(f"时序状态 Redis 不可用，暂降级为进程内存储（将自动重试恢复）: {exc}")
        self._redis_failed = True
        cooldown = float(getattr(settings, "TEMPORAL_REDIS_COOLDOWN_SEC", 10.0) or 10.0)
        self._redis_cooldown_until = time.monotonic() + max(0.0, cooldown)

    def _get_redis(self):
        """惰性创建 Redis 客户端；失败进入冷却并返回 None，冷却后可自动恢复。"""
        if self._redis is not None:
            return self._redis
        if not self._prefer_redis or not settings.REDIS_ENABLE:
            return None
        if self._redis_failed and time.monotonic() < self._redis_cooldown_until:
            return None
        # 冷却结束：尝试重连；成功则清除降级标记（多 worker 部署下恢复共享状态）
        try:
            if getattr(settings, "TESTING", False):
                import fakeredis

                self._redis = fakeredis.FakeStrictRedis(decode_responses=True)
            else:
                import redis

                # 超时必须短（默认 0.5s）：该调用在事件处理热路径上，长超时会阻塞事件循环
                timeout = float(getattr(settings, "TEMPORAL_REDIS_TIMEOUT", 0.5) or 0.5)
                self._redis = redis.Redis.from_url(
                    settings.REDIS_URI,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=timeout,
                    socket_timeout=timeout,
                )
                self._redis.ping()
            self._redis_failed = False
            self._redis_cooldown_until = 0.0
        except Exception as e:
            self._mark_redis_failed(e)
        return self._redis

    def _memory_ttl(self) -> float:
        """内存降级状态的 TTL（秒）。"""
        return float(getattr(settings, "TEMPORAL_MEMORY_TTL_SEC", _TTL_SEC) or _TTL_SEC)

    def _evict_memory_locked(self) -> None:
        """清理过期的内存状态；调用方需持有 ``self._lock``。"""
        now = time.monotonic()
        for key in [k for k, exp in self._memory_expiry.items() if exp <= now]:
            self._memory_expiry.pop(key, None)
            self._memory.pop(key, None)
            self._memory_meta.pop(key, None)

    @staticmethod
    def _key(camera_id, alarm_type, label, scope: str) -> str:
        return f"{KEY_PREFIX}:{camera_id}:{alarm_type}:{label}:{scope}"

    @staticmethod
    def _field(track_id, ts: float) -> str:
        num = _to_float(track_id)
        if num is not None:
            return f"t:{int(num)}"
        return f"e:{ts}"

    def _read_hash_nolock(self, key: str) -> dict:
        """不加锁读取；调用方需自行持有 ``self._lock``。"""
        rd = self._get_redis()
        if rd is not None:
            try:
                return dict(rd.hgetall(key) or {})
            except Exception as e:
                self._mark_redis_failed(e)
        self._evict_memory_locked()
        return dict(self._memory.get(key, {}))

    def _read_hash(self, key: str) -> dict:
        with self._lock:
            return self._read_hash_nolock(key)

    def _write_hash_nolock(self, key: str, mapping: dict) -> None:
        """不加锁写入；调用方需自行持有 ``self._lock``。"""
        rd = self._get_redis()
        if rd is not None:
            try:
                if mapping:
                    rd.hset(key, mapping=mapping)
                    rd.expire(key, _TTL_SEC)
                return
            except Exception as e:
                self._mark_redis_failed(e)
        self._evict_memory_locked()
        self._memory.setdefault(key, {}).update(mapping)
        self._memory_expiry[key] = time.monotonic() + self._memory_ttl()

    def _write_hash(self, key: str, mapping: dict) -> None:
        with self._lock:
            self._write_hash_nolock(key, mapping)

    # ----------------------------------------------------------------- 观测
    def observe(self, camera_id, alarm_type, detections, ts, scope: str = _SCOPE_ALL) -> None:
        """把一次事件的检测写入状态；脏输入安全跳过，绝不抛异常。"""
        now = _to_float(ts)
        if now is None:
            return
        if not isinstance(detections, (list, tuple)):
            return
        scope = scope or _SCOPE_ALL
        grouped: dict[str, dict[str, float]] = {}
        positions: dict[str, dict[str, tuple[float, float]]] = {}
        for d in detections:
            if not isinstance(d, dict):
                continue
            label = d.get("label")
            if not isinstance(label, str):
                label = ""
            field = self._field(d.get("track_id"), now)
            grouped.setdefault(label, {})[field] = now
            center = _center(d)
            if center is not None:
                positions.setdefault(label, {}).setdefault(field, center)
        for label, fields in grouped.items():
            key = self._key(camera_id, alarm_type, label, scope)
            self._observe_locked(key, fields, positions.get(label, {}))

    def _observe_locked(self, key: str, fields: dict[str, float],
                        positions: dict[str, tuple[float, float]] | None = None) -> None:
        """在同一把锁内完成读-改-写；位置推进 prev <- 旧 cur，cur <- 新中心。"""
        positions = positions or {}
        with self._lock:
            current = self._read_hash_nolock(key)
            mapping: dict[str, float] = {}
            for field, value in fields.items():
                prev_first = _to_float(current.get(field + _SEP + _FIRST))
                prev_last = _to_float(current.get(field + _SEP + _LAST))
                mapping[field + _SEP + _FIRST] = value if prev_first is None else min(prev_first, value)
                mapping[field + _SEP + _LAST] = value if prev_last is None else max(prev_last, value)

                pos = positions.get(field)
                # 位置只在「更新的观测时间戳」推进：同一事件被多条规则重复观测时
                # （同 scope 共享观测）不得二次推进，否则 prev==cur 使 line_cross 永不命中；
                # 乱序到达的更早事件也不得让位置回退。
                newer = prev_last is None or value > prev_last
                if pos is not None and newer:
                    old_cur = _parse_pos(current.get(field + _SEP + _POS_C))
                    if old_cur is not None:
                        mapping[field + _SEP + _POS_P] = _ser_pos(old_cur)
                    mapping[field + _SEP + _POS_C] = _ser_pos(pos)
            self._write_hash_nolock(key, mapping)

    # ----------------------------------------------------------------- 查询
    def _keys(self, camera_id, alarm_type, label, scope: str) -> list[str]:
        base = f"{KEY_PREFIX}:{camera_id}:{alarm_type}:"
        suffix = f":{scope}"
        rd = self._get_redis()
        if rd is not None:
            pattern = f"{base}{label if label is not None else '*'}{suffix}"
            try:
                return list(rd.scan_iter(match=pattern))
            except Exception as e:
                self._mark_redis_failed(e)
        target = f"{base}{label}{suffix}" if label is not None else None
        with self._lock:
            self._evict_memory_locked()
            keys = []
            for k in list(self._memory.keys()):
                if not k.startswith(base) or not k.endswith(suffix):
                    continue
                if target is not None and k != target:
                    continue
                keys.append(k)
            return keys

    def query(self, camera_id, alarm_type, label=None, scope: str = _SCOPE_ALL):
        """返回 ``{track_key: (first_seen, last_seen)}``；label=None 聚合该维度全部标签。"""
        scope = scope or _SCOPE_ALL
        out: dict[str, tuple[float, float]] = {}
        for key in self._keys(camera_id, alarm_type, label, scope):
            h = self._read_hash(key)
            firsts: dict[str, float] = {}
            lasts: dict[str, float] = {}
            for k, v in h.items():
                if not isinstance(k, str):
                    continue
                if k.endswith(_SEP + _FIRST):
                    val = _to_float(v)
                    if val is not None:
                        firsts[k[: -len(_SEP + _FIRST)]] = val
                elif k.endswith(_SEP + _LAST):
                    val = _to_float(v)
                    if val is not None:
                        lasts[k[: -len(_SEP + _LAST)]] = val
            for field, first in firsts.items():
                last = lasts.get(field)
                if last is not None:
                    out[field] = (first, last)
        return out

    def query_multi(self, camera_ids, alarm_type, label=None, scope: str = _SCOPE_ALL):
        """跨相机聚合读取：返回 ``{(camera_id, track_key): (first_seen, last_seen)}``。

        跨相机 track_id 独立，故键含 camera_id 前缀；调用方自行决定是否复用 track_id。
        纯只读：逐相机调用 ``query()`` 合并，不引入任何跨相机写路径。
        """
        scope = scope or _SCOPE_ALL
        out: dict[tuple[int, str], tuple[float, float]] = {}
        for cam in camera_ids or []:
            for field, rng in self.query(cam, alarm_type, label, scope).items():
                out[(int(cam), field)] = rng
        return out

    def query_positions(self, camera_id, alarm_type, label=None, scope: str = _SCOPE_ALL):
        """返回 ``{track_key: (prev_xy | None, cur_xy)}``；label=None 聚合全部标签。"""
        scope = scope or _SCOPE_ALL
        out: dict[str, tuple[tuple[float, float] | None, tuple[float, float] | None]] = {}
        for key in self._keys(camera_id, alarm_type, label, scope):
            h = self._read_hash(key)
            prevs: dict[str, tuple[float, float]] = {}
            curs: dict[str, tuple[float, float]] = {}
            for k, v in h.items():
                if not isinstance(k, str):
                    continue
                if k.endswith(_SEP + _POS_C):
                    p = _parse_pos(v)
                    if p is not None:
                        curs[k[: -len(_SEP + _POS_C)]] = p
                elif k.endswith(_SEP + _POS_P):
                    p = _parse_pos(v)
                    if p is not None:
                        prevs[k[: -len(_SEP + _POS_P)]] = p
            for field, cur in curs.items():
                out[field] = (prevs.get(field), cur)
        return out

    # ------------------------------------------------------------- absence 标记
    @staticmethod
    def _absent_key(camera_id, alarm_type, label, scope: str) -> str:
        return f"{KEY_PREFIX}:{camera_id}:{alarm_type}:{_ABSENT_MARK}:{scope}:{label}"

    def get_absent_fired(self, camera_id, alarm_type, label, scope: str = _SCOPE_ALL) -> float | None:
        """读取 absence 上次触发时间；无记录返回 None。"""
        scope = scope or _SCOPE_ALL
        key = self._absent_key(camera_id, alarm_type, label, scope)
        rd = self._get_redis()
        if rd is not None:
            try:
                return _to_float(rd.get(key))
            except Exception as e:
                self._mark_redis_failed(e)
        with self._lock:
            self._evict_memory_locked()
            return self._memory_meta.get(key)

    def set_absent_fired(self, camera_id, alarm_type, label, scope: str, ts: float) -> None:
        """记录 absence 本次触发时间，用于同一节流窗口内不重复告警。"""
        scope = scope or _SCOPE_ALL
        key = self._absent_key(camera_id, alarm_type, label, scope)
        rd = self._get_redis()
        if rd is not None:
            try:
                rd.setex(key, _TTL_SEC, str(float(ts)))
                return
            except Exception as e:
                self._mark_redis_failed(e)
        with self._lock:
            self._evict_memory_locked()
            self._memory_meta[key] = float(ts)
            self._memory_expiry[key] = time.monotonic() + self._memory_ttl()

    # ----------------------------------------------------------------- 维护
    def reset(self) -> None:
        """清空内存与 Redis 中本 store 写入的状态（测试用）。"""
        with self._lock:
            self._memory.clear()
            self._memory_meta.clear()
            self._memory_expiry.clear()
        rd = self._get_redis()
        if rd is not None:
            try:
                for k in rd.scan_iter(match=f"{KEY_PREFIX}:*"):
                    rd.delete(k)
            except Exception as e:
                log.warning(f"时序状态清理失败: {e}")


# 进程级单例：规则评估默认使用它
temporal_store = TemporalStore()
