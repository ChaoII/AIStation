"""看门狗与占用统计：回收「任务已不在进行中」却仍占着 GPU / 端口的记录。

为什么需要
----------
正常路径在任务终止时（``_execute`` 的 finally）就会 :func:`~.alloc.release`。
但这些情况不会执行到：容器被 ``kill -9``、机器断电、finally 块本身抛异常、
后端进程崩溃。届时只能等占用键的 24h TTL——对单卡机器而言等于**被占死两天**。

判据只看**任务状态**，不猜容器死活：``pending``/``running`` 一律保留
（``pending`` 可能是正在排队等卡的，它已经占着资源），其余（success /
failed / cancelled / 任务已不存在）一律回收。
"""

from __future__ import annotations

from app.core.logger import log

from . import _store
from ._store import K_GPU, K_PORT, LOCAL, LOCAL_GPUS, LOCAL_PORTS

#: 仍在进行中、因此**不该**回收资源的状态
ALIVE_STATUSES = ("pending", "running")


async def busy_task_count() -> int:
    """当前占用着 GPU 的**任务数**（给排队中的任务显示"前面有几个人"）。

    按 GPU 认领键的**去重 task_id** 计数，而不是按键数——一个任务占多张卡时
    只算一次，否则显示的排队长度会随卡的分配方式跳动。Redis 不可用时退回
    进程内字典，只能反映本进程（这时提示语会自然少一些，不会报错）。
    """
    rd = await _store.redis_or_none()
    if rd is None:
        return len(set(LOCAL_GPUS.values()))
    try:
        owners: set[str] = set()
        async for key in rd.scan_iter(match=f"{K_GPU}*", count=200):
            val = await rd.get(key)
            if val:
                owners.add(val.decode() if isinstance(val, bytes) else str(val))
        return len(owners)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] 统计占用任务数失败: {e}")
        return len(set(LOCAL_GPUS.values()))


async def cleanup_redis_by_task(task_id: int, rd) -> None:
    """按 task_id 清掉 Redis 上的残留占用（进程重启后本地记录已丢时用）。"""
    if rd is None:
        return
    try:
        for prefix in (K_PORT, K_GPU):
            async for key in rd.scan_iter(match=f"{prefix}*", count=200):
                if await rd.get(key) == str(task_id):
                    await rd.delete(key)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] 清理任务 {task_id} 的残留占用失败: {e}")


async def reap_stale() -> int:
    """回收「任务已不在进行中」却仍占着 GPU / 端口的记录，返回回收条数。"""
    from app.core.database import async_db_session

    from .alloc import release

    rd = await _store.redis_or_none()
    stale: list[int] = []
    if rd is not None:
        try:
            for prefix in (K_PORT, K_GPU):
                async for key in rd.scan_iter(match=f"{prefix}*", count=200):
                    val = await rd.get(key)
                    if val and val.isdigit():
                        stale.append(int(val))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[gpu_pool] 看门狗扫描占用失败: {e}")
            return 0
    else:
        stale = list(LOCAL_PORTS.values()) + list(LOCAL_GPUS.values())
    # 去重，并排除本进程内仍然活跃的
    candidates = {t for t in stale if t not in LOCAL}
    if not candidates:
        return 0

    try:
        async with async_db_session() as db:
            from sqlalchemy import select

            from app.plugin.module_train.model import TrainTask

            rows = (await db.execute(
                select(TrainTask.id, TrainTask.status).where(
                    TrainTask.id.in_(list(candidates))))).all()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] 看门狗查任务状态失败: {e}")
        return 0

    alive = {int(i) for i, s in rows if str(getattr(s, "value", s)) in ALIVE_STATUSES}
    reaped = 0
    for tid in sorted(candidates - alive):
        await release(tid)
        log.warning(
            f"[gpu_pool] 看门狗：任务 {tid} 已是终态或已不存在，却仍占着资源，已回收"
            f"（容器被强杀或后端崩溃过）")
        reaped += 1
    return reaped
