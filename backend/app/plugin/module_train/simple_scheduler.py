"""简单模式动态并发调度（子进程直调，无容器）。

与容器模式 ``gpu_pool`` 的分工
------------------------------
- ``gpu_pool``（每任务一容器）管「端口 + 整卡认领」，一个任务占一张卡；
- 本模块只关心**简单模式**（子进程）的卡上资源：按 NVML 实时显存/利用率选卡，
  允许**同卡多任务**（不取整卡锁），用 Redis 台账记录并发计数与任务占用，
  超 ``TORKILN_SIMPLE_MAX_CONCURRENT`` 时返回 None 排队。

对外的核心接口（与 plan/裁定一致）：

- ``async acquire(task_id, need_mem_gb, est_mem_gb) -> Allocation | None``：
  **非阻塞单次决策**——满足条件返回 ``Allocation``，不满足（并发满 / 无候选卡）
  返回 None；调用方（``_execute_simple``）对 None 循环轮询重试（Ruling R8）。
- ``async release(task_id)``：幂等释放（重复调用安全，不把并发计数减成负数）。
- ``def usage_snapshot() -> dict``：各卡 free/util/占用台账 + active_count
  （供测试与看板；同步读进程内镜像，不 await Redis）。
- ``async update_usage(ev)``：env 事件写环境快照、step 的 ``mem_reserved``
  回填任务台账（由 ``event_ingest.update_usage_tasks`` 接线调用）。

存储后端（沿用 ``gpu_pool._store`` 的降级语义）：Redis 优先（原子 INCR/DECR
并发门 + JSON 台账），不可用时降级到进程内字典。两种后端都必须可用
（测试会分别以 fakeredis / None 验证）。
"""
from __future__ import annotations

import contextlib
import json
import time

from app.config.setting import settings
from app.core.logger import log

from .gpu_pool import _store
from .gpu_pool import device as device_mod
from .gpu_pool.alloc import Allocation

#: Redis 键前缀（沿用 ``aist:tk:`` 风格，避免与其它模块撞键）。
K_SIMPLE_ACTIVE = "aist:tk:simple:active"
K_SIMPLE_TASK = "aist:tk:simple:"        # 前缀 + task_id -> JSON 任务台账
K_SIMPLE_ENV = "aist:tk:simple:env:"     # 前缀 + task_id -> 环境快照 JSON

#: 任务台账 TTL（兜底；正常路径在 release / 终态时主动删）。
_TASK_TTL = 24 * 3600
#: 安全系数：候选卡可用显存须 ≥ 需求 × 1.2。
_SAFETY_FACTOR = 1.2
#: 利用率硬上限：超过它绝不出手（防 OOM）。
_MAX_USED_RATIO = 0.85

#: 进程内降级后端（Redis 不可用时；平时也作为同步快照的镜像）。
_LOCAL_ACTIVE: int = 0
_LOCAL_TASKS: dict[int, dict] = {}
_LOCAL_ENV: dict[int, dict] = {}


def _max_concurrent() -> int:
    return max(1, int(settings.TORKILN_SIMPLE_MAX_CONCURRENT))


def _safe_mem(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _pick_gpu(devices: list[dict], need_gb: float) -> int | None:
    """按「free_gb ≥ 需求×1.2 且 util < 85%」选卡；余量富余优先。"""
    threshold = need_gb * _SAFETY_FACTOR
    candidates = [
        d for d in devices
        if _safe_mem(d.get("free_gb")) >= threshold
        and _safe_mem(d.get("used_ratio")) < _MAX_USED_RATIO
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda d: _safe_mem(d.get("free_gb")), reverse=True)
    return int(candidates[0]["index"])


async def acquire(task_id: int, need_mem_gb: float,
                  est_mem_gb: float) -> Allocation | None:
    """非阻塞单次资源决策：返回分配或 None（并发满/无候选卡）。

    - 先按 NVML 数据选卡（同卡多任务允许），无候选卡直接返回 None；
    - 再走并发门（超 ``TORKILN_SIMPLE_MAX_CONCURRENT`` 返回 None 排队）；
    - 成功后登记 Redis 台账 + 进程内镜像，返回 ``Allocation``。
    """
    global _LOCAL_ACTIVE
    rd = await _store.redis_or_none()
    devices = device_mod.gpu_devices()
    need = max(_safe_mem(need_mem_gb), _safe_mem(est_mem_gb))
    gpu_id = _pick_gpu(devices, need)
    if gpu_id is None:
        return None

    # 并发门：Redis 用原子 INCR/DECR（跨进程正确）；进程内用计数。
    if rd is not None:
        try:
            new_count = int(await rd.incr(K_SIMPLE_ACTIVE))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[simple_scheduler] Redis INCR 失败，降级进程内: {e}")
            new_count = _LOCAL_ACTIVE + 1
            _LOCAL_ACTIVE = new_count
        if new_count > _max_concurrent():
            if rd is not None:
                with contextlib.suppress(Exception):
                    await rd.decr(K_SIMPLE_ACTIVE)
            else:
                _LOCAL_ACTIVE = max(0, _LOCAL_ACTIVE - 1)
            return None
    else:
        if _LOCAL_ACTIVE >= _max_concurrent():
            return None
        _LOCAL_ACTIVE += 1

    entry: dict = {
        "gpu_id": gpu_id,
        "mem_reserved": _safe_mem(est_mem_gb),
        "ts": time.time(),
        "pid": 0,
    }
    if rd is not None:
        with contextlib.suppress(Exception):
            await rd.set(f"{K_SIMPLE_TASK}{task_id}", json.dumps(entry))
            await rd.expire(f"{K_SIMPLE_TASK}{task_id}", _TASK_TTL)
    # 进程内镜像：usage_snapshot（同步）与 release 判活都用它。
    _LOCAL_TASKS[task_id] = entry
    log.info(f"[simple_scheduler] 任务 {task_id} 分配到 GPU {gpu_id}")
    return Allocation(task_id=task_id, port=0, gpu_indices=[gpu_id])


async def release(task_id: int) -> None:
    """幂等释放：删任务台账、并发计数回落、清环境快照。重复调用安全。

    ⚠️ 递减判定**由 Redis 台账驱动**（del 返回 1 = 该任务在册），不依赖进程内
    ``_LOCAL_TASKS`` 镜像——后端重启后镜像为空，但恢复路径（``recover_orphans``）
    正是**跨进程**调用 ``release``，若镜像驱动会漏减 ``K_SIMPLE_ACTIVE``。
    """
    global _LOCAL_ACTIVE
    rd = await _store.redis_or_none()
    if rd is not None:
        # del 原子地同时「删除台账」与「判定是否存在」，返回被删 key 数
        deleted = 0
        with contextlib.suppress(Exception):
            deleted = int(await rd.delete(f"{K_SIMPLE_TASK}{task_id}") or 0)
        with contextlib.suppress(Exception):
            await rd.delete(f"{K_SIMPLE_ENV}{task_id}")
        if deleted:
            with contextlib.suppress(Exception):
                await rd.decr(K_SIMPLE_ACTIVE)
    else:
        if task_id in _LOCAL_TASKS:
            _LOCAL_ACTIVE = max(0, _LOCAL_ACTIVE - 1)
        _LOCAL_ENV.pop(task_id, None)
    _LOCAL_TASKS.pop(task_id, None)


async def reconcile_active() -> None:
    """把 ``K_SIMPLE_ACTIVE`` 对账为实际存活的台账 key 数量（自愈）。

    场景：INCR 后后端崩溃、或台账被 TTL 回收，但 ``K_SIMPLE_ACTIVE`` 未随
    ``release`` 回落——该键无 TTL，一个崩溃就会把并发上限永久撑满，挡住所有
    后续 simple 任务。恢复循环（``recover_orphans``）周期性调用，令计数在
    30s 内自愈。仅 Redis 可用时执行（进程内降级无此问题）；失败 log 不抛。
    """
    rd = await _store.redis_or_none()
    if rd is None:
        return
    try:
        count = 0
        async for key in rd.scan_iter(match=f"{K_SIMPLE_TASK}*"):
            skey = key if isinstance(key, str) else key.decode("utf-8", "ignore")
            # 排除 ``aist:tk:simple:active`` 自身与 ``aist:tk:simple:env:*`` 快照键，
            # 只数真正的任务台账键（``aist:tk:simple:{task_id}``）。
            if skey == K_SIMPLE_ACTIVE or skey.startswith(K_SIMPLE_ENV):
                continue
            count += 1
        await rd.set(K_SIMPLE_ACTIVE, count)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[simple_scheduler] 对账 active 计数失败: {e}")


async def record_pid(task_id: int, pid: int) -> None:
    """spawn 后把子进程 pid 写进任务台账（供 stop / recover 使用）。"""
    entry = dict(_LOCAL_TASKS.get(task_id) or {})
    entry["pid"] = int(pid)
    _LOCAL_TASKS[task_id] = entry
    rd = await _store.redis_or_none()
    if rd is not None:
        with contextlib.suppress(Exception):
            await rd.set(f"{K_SIMPLE_TASK}{task_id}", json.dumps(entry))
            await rd.expire(f"{K_SIMPLE_TASK}{task_id}", _TASK_TTL)


async def get_entry(task_id: int) -> dict | None:
    """取任务台账条目（含 pid / gpu_id）。Redis 优先，进程内镜像兜底。"""
    if task_id in _LOCAL_TASKS:
        return _LOCAL_TASKS[task_id]
    rd = await _store.redis_or_none()
    if rd is not None:
        raw = await rd.get(f"{K_SIMPLE_TASK}{task_id}")
        if raw:
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return None
    return None


async def update_usage(ev: dict) -> None:
    """更新资源台账（由 ``event_ingest.update_usage_tasks`` 接线调用）。

    - ``type == "env"``：把事件业务字段写入环境快照 ``aist:tk:simple:env:{task_id}``；
    - ``type == "step"`` 且含 ``mem_reserved``：回填任务台账的实测显存（首次校准）。

    失败一律 log 不抛（事件通道是旁路，不能拖垮训练回调）。
    """
    task_id = ev.get("task_id")
    if task_id is None:
        return
    etype = ev.get("type")
    rd = await _store.redis_or_none()
    if etype == "env":
        snapshot = {k: v for k, v in ev.items()
                    if k not in ("task_id", "seq", "ts", "type")}
        _LOCAL_ENV[int(task_id)] = snapshot
        if rd is not None:
            with contextlib.suppress(Exception):
                await rd.set(f"{K_SIMPLE_ENV}{task_id}", json.dumps(snapshot))
                await rd.expire(f"{K_SIMPLE_ENV}{task_id}", _TASK_TTL)
        return
    if etype == "step":
        mem = ev.get("mem_reserved")
        if mem is None:
            return
        entry = dict(_LOCAL_TASKS.get(int(task_id)) or {})
        if entry:
            entry["mem_reserved"] = _safe_mem(mem)
            _LOCAL_TASKS[int(task_id)] = entry
            if rd is not None:
                with contextlib.suppress(Exception):
                    await rd.set(f"{K_SIMPLE_TASK}{task_id}", json.dumps(entry))
                    await rd.expire(f"{K_SIMPLE_TASK}{task_id}", _TASK_TTL)


def usage_snapshot() -> dict:
    """各卡 free/util/占用台账 + active_count（同步，供测试与看板）。"""
    devices = device_mod.gpu_devices()
    snapshot: dict = {}
    for d in devices:
        snapshot[int(d.get("index"))] = {
            "free_gb": _safe_mem(d.get("free_gb")),
            "used_ratio": _safe_mem(d.get("used_ratio")),
            "reserved_gb": 0.0,
            "tasks": [],
        }
    for tid, entry in _LOCAL_TASKS.items():
        gpu_id = int(entry.get("gpu_id") or 0)
        card = snapshot.setdefault(gpu_id, {
            "free_gb": 0.0, "used_ratio": 0.0, "reserved_gb": 0.0, "tasks": []})
        card["reserved_gb"] += _safe_mem(entry.get("mem_reserved"))
        card["tasks"].append(int(tid))
    return {"active_count": len(_LOCAL_TASKS), "gpus": snapshot}
