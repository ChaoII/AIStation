# 定时任务在多实例部署下的重复执行问题（结论与预案）

> 2026-10-26 评估。结论：**当前部署形态下不需要处理**；一旦水平扩容必须处理，且**只加 Redis 锁不够**。

## 现状（为什么现在不需要）

| 事实 | 证据 |
|---|---|
| 后端是单进程 | `backend/main.py` 的 `uvicorn.run(...)` 没传 `workers`，默认 1 个进程 |
| 调度器在进程内 | `app/core/ap_scheduler.py:57` `AsyncIOScheduler()`，`init_scheduler()` 里 `scheduler.start()` |
| 部署里没有后端服务 | `docker-compose.yaml` 只有 postgres / redis / zlmediakit / rustfs，后端不在编排内 |
| 已有进程内闸门 | `workspace/service.py` 的 `_RUNNING_CRONS`（同一任务串行，30 分钟自动解锁） |

单进程下，`_RUNNING_CRONS` 已经能保证"同一个定时任务不会并发跑两遍"（实测：连点两次第二次被拒；真实到点触发也只跑一次）。

## 什么时候会出问题

只要出现下面任一情况，定时任务就会**按实例数成倍执行**（每次都是真实模型调用）：

- `uvicorn --workers N`（N > 1）
- k8s / docker 起了多个 backend 副本
- 同机起两个后端进程连同一个库（例如 8001 + 8002 都开着调度器）

原因：`AsyncIOScheduler` 的作业是**每个进程各自持有**的（`SQLAlchemyJobStore` 只是把作业定义存到库里，**不会**跨进程互斥），每个进程都会到点触发自己那份。

## 预案（按推荐顺序）

### 方案 A（推荐）：调度器单实例开关

只让**一个**实例启动调度器，Web 层随便多副本。

需要动的地方（约 3–4 个文件）：

1. `app/config/setting.py`：加 `SCHEDULER_ENABLED: bool = True`（env `SCHEDULER_ENABLED`）。
2. `app/core/ap_scheduler.py::init_scheduler`：`if not settings.SCHEDULER_ENABLED: log.warning("调度器已关闭"); return`。
3. `app/scripts/init_app.py::_register_business_jobs_on_startup`：调度器关闭时跳过注册。
4. **空调度器容错**：`scheduler.get_job(...)` 在未启动的调度器上行为不可靠，仓里共有 13 处调用
   （`ap_scheduler.py` / `workspace/service.py` / `workflow/schedule_service.py` / `train/.../service.py`），
   要么统一走 `SchedulerUtil.get_job_safe(key)`（内部 try/except 返回 None），要么逐个包 try。

优点：不引入 Redis 依赖；调度器只有一个，"不重复"是结构上保证的，不靠锁。
缺点：要保证"恰好一个实例"开着它（部署约定或环境变量区分主实例）。

### 方案 B：Redis 分布式锁（方案 A 做不到时）

每次执行前抢锁，持有到结束：

```python
# 伪代码：run_scheduled_workspace_cron 入口
ok = await redis.set(f"cron:lock:{cron_id}", owner, nx=True, px=TTL_MS)
if not ok:
    return           # 别的实例在跑
try:
    ...执行...
finally:
    if await redis.get(key) == owner:   # 只删自己的锁
        await redis.delete(key)
```

注意：
- 锁必须**续租**（长任务超过 TTL 会被别的实例抢走）；
- 进程被杀后靠 TTL 兜底（别用无过期的锁）；
- 它只能防"重复执行"，**防不了** N 个进程各自注册作业带来的调度开销（可接受）。

## 决策记录

- 2026-10-26：**暂不做**。当前单进程部署，做了等于给不存在的场景写代码，还会让调度路径依赖 Redis 可用性。
- 触发条件：Web 层一旦多副本（workers > 1 或 replicas > 1），先做方案 A。
