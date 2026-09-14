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
        # 允许测试注入 Redis 客户端（如 fakeredis），绕过全局配置
        self._redis = redis_client
        self._redis_failed = False

    # ------------------------------------------------------------- 后端选择
    def _get_redis(self):
        """惰性创建 Redis 客户端；失败则永久降级内存并返回 None。"""
        if self._redis is not None:
            return self._redis
        if not self._prefer_redis or not settings.REDIS_ENABLE:
            return None
        if self._redis_failed:
            return None
        try:
            if getattr(settings, "TESTING", False):
                import fakeredis

                self._redis = fakeredis.FakeStrictRedis(decode_responses=True)
            else:
                import redis

                self._redis = redis.Redis.from_url(
                    settings.REDIS_URI,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=settings.POOL_TIMEOUT,
                    socket_timeout=settings.POOL_TIMEOUT,
                )
                self._redis.ping()
        except Exception as e:
            log.warning(f"时序状态 Redis 不可用，降级为进程内存储: {e}")
            self._redis = None
            self._redis_failed = True
        return self._redis

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
                log.warning(f"时序状态读取失败，降级内存: {e}")
                self._redis = None
                self._redis_failed = True
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
                log.warning(f"时序状态写入失败，降级内存: {e}")
                self._redis = None
                self._redis_failed = True
        self._memory.setdefault(key, {}).update(mapping)

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
                if pos is not None:
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
                log.warning(f"时序状态扫描失败，降级内存: {e}")
                self._redis = None
                self._redis_failed = True
        target = f"{base}{label}{suffix}" if label is not None else None
        with self._lock:
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

    # ----------------------------------------------------------------- 维护
    def reset(self) -> None:
        """清空内存与 Redis 中本 store 写入的状态（测试用）。"""
        with self._lock:
            self._memory.clear()
        rd = self._get_redis()
        if rd is not None:
            try:
                for k in rd.scan_iter(match=f"{KEY_PREFIX}:*"):
                    rd.delete(k)
            except Exception as e:
                log.warning(f"时序状态清理失败: {e}")


# 进程级单例：规则评估默认使用它
temporal_store = TemporalStore()
