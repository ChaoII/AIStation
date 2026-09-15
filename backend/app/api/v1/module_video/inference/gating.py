"""规则灰度 gating：时间段 → 黑名单 → 白名单 → 比例（稳定哈希分桶）。

设计要点：
- 任何非法/缺失输入一律 fail-open（视为生效），避免灰度配置错误导致规则静默失效。
- 分桶用 ``zlib.crc32``（跨进程稳定），**禁止** Python 内置 ``hash()``。
- 时间段语义与边缘 ``aistation::parse_schedule``/``schedule_active`` 保持一致：
  ``{"slots": [{"day": 0-6, "start": 0-24, "end": 0-24}]}``，``day`` 以 ISO 周一为 0，
  窗口为 ``[start, end)``（start 含、end 不含），空/缺失 slots = 全天生效。

时区假设：``now`` 为事件 epoch 秒，统一按 **UTC** 推导 ISO 星期与小时
（边缘侧 ``schedule_active_now`` 使用本机 ``localtime``；云端以 UTC 为准，部署时需
保证边缘时区与云端一致）。
"""
import logging
import zlib
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _as_id_list(value) -> list[int]:
    """把配置值归一化为正整数相机 id 列表；非法（非列表/含非正整数）→ 空列表。"""
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            return []
        result.append(item)
    return result


def _schedule_active(schedule, now: float) -> bool:
    """时间段是否命中；空/缺失/非法容器视为全天生效（fail-open）。

    与边缘 ``aistation::parse_schedule`` + ``schedule_active`` 对齐：
    逐 slot 校验 ``day ∈ [0,6]``、``end > start``，命中 ``day == iso_day`` 且
    ``start <= hour < end`` 即生效；存在 slots 但无一命中 → 跳过。
    """
    if not isinstance(schedule, dict):
        return True
    slots = schedule.get("slots")
    if not isinstance(slots, list) or not slots:
        return True

    # UTC 推导：ISO 星期（周一=0）与小时
    moment = datetime.fromtimestamp(now, tz=timezone.utc)
    iso_day = moment.weekday()
    hour = moment.hour

    for slot in slots:
        if not isinstance(slot, dict):
            continue
        try:
            day = int(slot.get("day", -1))
            start = min(24, max(0, int(slot.get("start", 0))))
            end = min(24, max(0, int(slot.get("end", 24))))
        except (TypeError, ValueError):
            continue
        if day < 0 or day > 6:
            continue
        if end <= start:
            continue
        if day == iso_day and start <= hour < end:
            return True
    return False


def _bucket_hit(rule_id, camera_id, percent: int) -> bool:
    """稳定哈希分桶：``crc32("{rule_id}:{camera_id}") % 100 < percent``。"""
    key = f"{rule_id}:{camera_id}".encode()
    return (zlib.crc32(key) % 100) < percent


def rule_active_now(schedule, rollout, camera_id, now, *, rule_id=None) -> tuple[bool, str]:
    """规则此刻对该相机是否生效；返回 ``(生效?, 原因)``。

    原因取值：``schedule`` | ``blacklist`` | ``whitelist`` | ``rollout_zero`` |
    ``rollout_all`` | ``rollout_bucket`` | ``all``。
    优先级：时间段 → 黑名单 → 白名单（强制生效）→ 比例（稳定哈希分桶）。
    任何非法/缺失输入按“生效”处理（fail-open）。
    """
    # 1. 时间段（优先于名单与比例）
    if not _schedule_active(schedule, now):
        return False, "schedule"

    if not isinstance(rollout, dict) or not rollout:
        return True, "all"

    # 2. 黑名单（优先于白名单）→ 3. 白名单强制生效
    whitelist = _as_id_list(rollout.get("whitelist"))
    blacklist = _as_id_list(rollout.get("blacklist"))
    if camera_id is not None and camera_id in blacklist:
        return False, "blacklist"
    if camera_id is not None and camera_id in whitelist:
        return True, "whitelist"

    # 4. 比例：非法/越界 → fail-open；0=不生效，100=全量，其余分桶
    percent = rollout.get("percent")
    if percent is None:
        return True, "all"
    if isinstance(percent, bool) or not isinstance(percent, int):
        log.warning(f"灰度 percent 非法（{percent!r}），fail-open 视为生效")
        return True, "all"
    if percent < 0 or percent > 100:
        log.warning(f"灰度 percent 越界（{percent}），fail-open 视为生效")
        return True, "all"
    if percent == 0:
        return False, "rollout_zero"
    if percent >= 100:
        return True, "rollout_all"
    return _bucket_hit(rule_id, camera_id, percent), "rollout_bucket"
