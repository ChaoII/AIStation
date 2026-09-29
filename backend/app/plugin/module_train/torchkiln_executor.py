"""TorchKiln 训练执行器。

与 ultralytics / PaddleX 执行器的**根本区别**
--------------------------------------------
后两者由本项目自己 ``run_container`` 起容器、自己 tail 日志、再用正则从日志里抠指标。
这个执行器什么都不做——只把声明式 ``JobSpec`` 交给 TorchKiln 服务，然后消费它推回来的流：

  日志流 -> 广播到前端 WebSocket（**仅排查用，不解析指标**）
  指标流 -> 原样落 ``TrainTask.metrics_log`` + 广播给前端 SSE 订阅者

好处：
  - **超参零映射**：点分键直通 ``-o Key.Sub=value``，加模型不用改本项目
  - **指标走契约**：来自 ``metrics.jsonl``，不再受日志格式/stdout 缓冲影响
  - **单一排队点**：GPU 排队与容器生命周期在服务端，本项目不抢 GPU 信号量
    （两边都排队 = 双队列 + 队头阻塞）

⚠️ 两条通道是互补而非重复：指标/日志用 SSE（实时、可断点续传），
**状态机用轮询**（``GET /jobs/{id}`` 永远可查，SSE 断线不影响状态收敛）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import traceback
from datetime import datetime

from sqlalchemy import update

from app.config.setting import settings
from app.core.database import async_db_session
from app.plugin.module_train.framework_utils import framework_value
from app.plugin.module_train.model import TrainStatus, TrainTask
from app.plugin.module_train.task_executor import TaskExecutor
from app.plugin.module_train.torchkiln_client import (
    EVENT_BEST,
    EVENT_END,
    EVENT_EVAL,
    EVENT_STEP,
    TorchKilnClient,
    TorchKilnError,
    TorchKilnUnavailable,
    build_job_spec,
    probe_service,
)

log = logging.getLogger(__name__)

#: 服务状态 -> 本项目 TrainStatus。queued 也算 RUNNING（业务上已"开始"）
_STATUS_MAP = {
    "queued": TrainStatus.RUNNING,
    "running": TrainStatus.RUNNING,
    "succeeded": TrainStatus.SUCCESS,
    "failed": TrainStatus.FAILED,
    "cancelled": TrainStatus.CANCELLED,
}

#: 作业 id 存在 hyperparams 的这个键下（``__`` 前缀，用户表单不会渲染）
JOB_ID_KEY = "__tk_job_id"

#: 指标落库批量阈值：step 级指标很密，逐条 UPDATE 会把 Postgres 打满
_FLUSH_EVERY = 40
_FLUSH_SECONDS = 3.0
#: metrics_log 行数上限，超出保留末尾（不限制会涨到几十 MB）
_MAX_METRIC_ROWS = 5000

#: 指标流订阅者（前端 SSE 端点）。key = task_id
_metric_subscribers: dict[int, list[asyncio.Queue]] = {}


# ---------------------------------------------------------------- 订阅（SSE 扇出）
def subscribe_metrics(task_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=4096)
    _metric_subscribers.setdefault(task_id, []).append(q)
    return q


def unsubscribe_metrics(task_id: int, q: asyncio.Queue) -> None:
    lst = _metric_subscribers.get(task_id)
    if lst and q in lst:
        lst.remove(q)
        if not lst:
            _metric_subscribers.pop(task_id, None)


def publish_metric(task_id: int, event: dict) -> None:
    for q in list(_metric_subscribers.get(task_id, ())):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                q.get_nowait()   # 丢最旧，给新数据腾位置
                q.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


# ---------------------------------------------------------------- 持久化
def get_job_id(hyperparams: dict | None) -> str | None:
    return (hyperparams or {}).get(JOB_ID_KEY)


async def set_job_id(task_id: int, job_id: str) -> None:
    """把作业 id 持久化，供服务/本项目重启后重新接管。"""
    async with async_db_session.begin() as db:
        row = await db.get(TrainTask, task_id)
        if row is None:
            return
        hp = dict(row.hyperparams or {})
        hp[JOB_ID_KEY] = job_id
        row.hyperparams = hp


async def load_metrics_rows(task_id: int) -> list[dict]:
    async with async_db_session() as db:
        task = await db.get(TrainTask, task_id)
        return list(task.metrics_log or []) if task else []


async def save_metrics(task_id: int, rows: list[dict]) -> None:
    """整体覆盖写 ``metrics_log``。

    指标流是**单写者**，所以覆盖写比 UPDATE 安全（避免读-改-写竞态）。
    """
    payload = rows[-_MAX_METRIC_ROWS:] if len(rows) > _MAX_METRIC_ROWS else rows
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainTask).where(TrainTask.id == task_id)
            .values(metrics_log=payload)
        )


async def broadcast_line(task_id: int, line: str) -> None:
    """把一行日志广播到前端 WebSocket（复用训练日志通道）。"""
    from app.plugin.module_train.ws import broadcast_log

    try:
        await broadcast_log(task_id, line)
    except Exception as e:  # noqa: BLE001
        log.debug("广播日志失败 task=%s: %s", task_id, e)


# ---------------------------------------------------------------- 执行器
class TorchKilnExecutor(TaskExecutor):
    """TorchKiln 训练执行器（HTTP 客户端形态）。"""

    name = "torchkiln_train"
    task_kind = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    #: 不占用本项目 GPU 信号量——排队是 TorchKiln 服务的职责（单一排队点）
    _concurrency = 8

    @classmethod
    def _recover_row_applies(cls, row) -> bool:
        return framework_value(getattr(row, "framework", None)) == "torchkiln"

    # ------------------------------------------------------------ 组装
    @staticmethod
    def _model_name(task) -> str:
        hp = task.hyperparams or {}
        name = hp.get("model") or hp.get("model_name")
        if not name:
            raise ValueError("hyperparams.model 未指定 TorchKiln 模型名")
        return str(name)

    @staticmethod
    def _task_type(task) -> str:
        hp = task.hyperparams or {}
        return str(hp.get("task_type") or "detection").lower()

    @classmethod
    def _build_spec(cls, task, data_dir: str) -> dict:
        """``TrainTask.hyperparams`` -> 服务端 ``JobSpec``（声明式）。

        约定的 ``hyperparams`` 结构::

            {
              "model": "yolov8n-det",            # 必填，TorchKiln 的 Global.model_name
              "task_type": "detection",           # 仅影响数据导出格式
              "params": {"Global.epoch_num": 100},  # 点分键，原样透传给 -o
              "seed": 1024,
              "resources": {"gpu_memory_gb": 12, "shm_size": "4g"},
              "train_ratio": 0.8
            }
        """
        hp = task.hyperparams or {}
        dataset = {"data_dir": data_dir}
        for key, fname in (("train_list", "train.txt"), ("val_list", "val.txt")):
            p = os.path.join(data_dir, fname)
            if os.path.isfile(p):
                dataset[key] = p
        resources = dict(hp.get("resources") or {})
        resources.setdefault("gpu", 1)
        # DataLoader worker>0 时不给 shm 会 BUS error
        resources.setdefault("shm_size", "4g")
        labels = {"aistation_task_id": str(task.id), "aistation_task_name": str(task.name or "")}
        if task.annotation_task_id:
            labels["annotation_task_id"] = str(task.annotation_task_id)
        return build_job_spec(
            model_name=cls._model_name(task),
            params=hp.get("params") or {},
            dataset=dataset,
            resources=resources,
            seed=hp.get("seed"),
            labels=labels,
        )

    # ------------------------------------------------------------ 指标换算
    @staticmethod
    def _row_from_event(ev: dict) -> dict | None:
        """``metrics.jsonl`` 事件 -> ``metrics_log`` 行。"""
        etype = ev.get("type")
        if etype == EVENT_STEP:
            row = {
                "_kind": EVENT_STEP,
                "epoch": ev.get("epoch"),
                "global_step": ev.get("global_step"),
                "loss": ev.get("loss"),
                "lr": ev.get("lr"),
                "ips": ev.get("ips"),
                "mem_reserved": ev.get("mem_reserved"),
            }
            for k, v in (ev.get("comps") or {}).items():
                if isinstance(v, (int, float)):
                    row[k] = v
            return row
        if etype in (EVENT_EVAL, EVENT_BEST):
            row = {"_kind": etype, "best": etype == EVENT_BEST or None}
            row["epoch"] = ev.get("epoch")
            row["global_step"] = ev.get("global_step")
            row["main_indicator"] = ev.get("main_indicator")
            row["main_indicator_mode"] = ev.get("main_indicator_mode")
            row["main_value"] = ev.get("main_value")
            if ev.get("fps") is not None:
                row["fps"] = ev["fps"]
            # metrics 子对象摊平，前端按 {epoch, 指标名: 值} 取值
            for k, v in (ev.get("metrics") or {}).items():
                if isinstance(v, (int, float)):
                    row[k] = v
            return row
        if etype == EVENT_END:
            return {
                "_kind": EVENT_END,
                "exit_reason": ev.get("exit_reason"),
                "epoch": ev.get("epoch"),
                "main_indicator": ev.get("main_indicator"),
                "main_value": ev.get("main_value"),
                "duration_sec": ev.get("duration_sec"),
            }
        return None

    @staticmethod
    def _summarize(rows: list[dict]) -> tuple[dict | None, dict | None]:
        """挑 best / last。

        主指标**从事件里读**（TorchKiln 的 ``main_indicator`` 随任务变：
        mAP50-95 / acc / hmean / RMSE…），不再像以前那样为每个框架维护一张
        硬编码映射表——这正是接自研平台的收益。
        """
        main_indicator = None
        mode = "max"
        for r in rows:
            if r.get("main_indicator"):
                main_indicator = r["main_indicator"]
                mode = str(r.get("main_indicator_mode") or "max").lower()
                break
        evals = [r for r in rows if r.get("_kind") == EVENT_EVAL and r.get("epoch")]
        if not evals:
            return None, (rows[-1] if rows else None)

        def score(r: dict):
            if main_indicator and isinstance(r.get(main_indicator), (int, float)):
                return float(r[main_indicator])
            v = r.get("main_value")
            return float(v) if isinstance(v, (int, float)) else None

        scored = [(s, r) for s, r in ((score(r), r) for r in evals) if s is not None]
        if not scored:
            return None, evals[-1]
        best = (min if mode == "min" else max)(scored, key=lambda x: x[0])[1]
        return best, evals[-1]

    # ------------------------------------------------------------ 主流程
    @classmethod
    async def _execute(cls, task_id: int):
        if not settings.TORKILN_ENABLED:
            await cls._mark_status(
                task_id, TrainStatus.FAILED, progress=0,
                error_log="TorchKiln 接入已关闭（setting.TORKILN_ENABLED=False）",
                finished_at=datetime.now())
            return

        export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
        data_dir = os.path.join(export_dir, "data")
        try:
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return
                hp = dict(task.hyperparams or {})
                dataset_id = task.dataset_id
                annotation_task_id = task.annotation_task_id
                existing_job = get_job_id(hp)
                spec = cls._build_spec(task, data_dir)
                train_ratio = float(hp.get("train_ratio", 0.8))
                task_type = cls._task_type(task)

            async with TorchKilnClient() as client:
                job_id = await cls._ensure_job(
                    client, task_id, data_dir, spec,
                    dataset_id=dataset_id,
                    annotation_task_id=annotation_task_id,
                    train_ratio=train_ratio,
                    task_type=task_type,
                    existing_job=existing_job,
                )
                await cls._pump(client, task_id, job_id)

        except TorchKilnUnavailable as e:
            # 服务不可达：保持 RUNNING 等 recover_orphans 重试，**不误判失败**
            log.warning("[torchkiln] 服务不可达，任务 %s 保持运行态待重试: %s", task_id, e)
            await broadcast_line(task_id, f"[torchkiln] 服务不可达，稍后重试: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            # 记录完整堆栈：只留 str(e) 会丢掉"哪个文件哪一行调用出错"，
            # 排查时只能靠猜（本项目就曾因此被 task_type 形参问题绕了很久）
            log.exception("[torchkiln] task %s failed", task_id)
            await cls._mark_status(
                task_id, TrainStatus.FAILED,
                error_log=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                finished_at=datetime.now())

    @classmethod
    async def _ensure_job(cls, client, task_id: int, data_dir: str, spec: dict,
                          dataset_id: int, annotation_task_id: int | None,
                          train_ratio: float, task_type: str,
                          existing_job: str | None) -> str:
        """拿到一个作业 id：优先接管已有作业，否则导数据 + 提交。"""
        if existing_job:
            try:
                info = await client.get_job(existing_job)
            except TorchKilnError as e:
                await broadcast_line(
                    task_id, f"[torchkiln] 原作业 {existing_job} 不可达（{e}），改为新建")
            else:
                await broadcast_line(
                    task_id,
                    f"[torchkiln] 接管已有作业 {existing_job}（状态 {info.get('status')}）")
                return existing_job

        await broadcast_line(task_id, f"[torchkiln] 准备训练数据 -> {data_dir}")
        from app.plugin.module_train.exporter import prepare_training_data_for_task

        # 数据布局与 ultralytics（YOLO）一致：images/<split> + labels/<split>；
        # torchkiln_index=True 额外生成 TorchKiln 需要的 train.txt / val.txt 索引。
        # ⚠️ task_type 走 framework 前缀（``yolo-<type>``）——这是 _export_core 既有的
        #    约定（``framework.startswith("yolo-")`` 时用它推导任务类型），
        #    prepare_training_data_for_task 没有 task_type 形参。
        export_framework = f"yolo-{task_type}" if task_type not in ("detection", "detect") else "ultralytics"
        await prepare_training_data_for_task(
            dataset_id, task_id, export_framework, data_dir,
            annotation_task_id=annotation_task_id,
            train_ratio=train_ratio,
            torchkiln_index=True,
        )
        await broadcast_line(task_id, f"[torchkiln] 提交作业（模型 {spec['model_name']}）")
        created = await client.submit_job(
            spec, idempotency_key=f"aistation-train-{task_id}")
        job_id = created["job_id"]
        await set_job_id(task_id, job_id)
        await broadcast_line(
            task_id, f"[torchkiln] 作业已受理 {job_id}"
                     f"（幂等命中={created.get('idempotent_hit')}）")
        return job_id

    @classmethod
    async def _pump(cls, client, task_id: int, job_id: str):
        """启动两条流，等终态，收敛本项目状态。"""
        # 接管场景先把历史指标补齐，避免曲线从零开始
        rows: list[dict] = list(await load_metrics_rows(task_id))
        last_seq = -1
        for ev in await client.metrics(job_id, offset=-1, limit=20000):
            if isinstance(ev.get("seq"), int):
                last_seq = max(last_seq, ev["seq"])
            row = cls._row_from_event(ev)
            if row:
                rows.append(row)
        if rows:
            await save_metrics(task_id, rows)

        metrics_task = asyncio.ensure_future(
            cls._consume_metrics(client, task_id, job_id, last_seq, rows))
        logs_task = asyncio.ensure_future(cls._consume_logs(client, task_id, job_id))
        try:
            final = await cls._await_terminal(client, task_id, job_id)
        finally:
            for t in (metrics_task, logs_task):
                t.cancel()
            await asyncio.gather(metrics_task, logs_task, return_exceptions=True)

        # 收尾再拉一次，确保 end 事件入库（流可能刚好被取消在前一条）
        final_rows = list(await load_metrics_rows(task_id))
        if not any(r.get("_kind") == EVENT_END for r in final_rows):
            for ev in await client.metrics(job_id, offset=-1, limit=20000):
                row = cls._row_from_event(ev)
                if row:
                    final_rows.append(row)
            if final_rows:
                await save_metrics(task_id, final_rows)

        best, last = cls._summarize(final_rows)
        status = _STATUS_MAP.get(str(final.get("status")), TrainStatus.FAILED)
        reason = final.get("exit_reason")
        err = final.get("error")
        if status == TrainStatus.FAILED and not err:
            err = f"TorchKiln 作业失败（exit_reason={reason}）"
        await cls._mark_status(
            task_id, status,
            metrics_log=final_rows or None,
            best_metrics=best or None,
            last_metrics=last or None,
            progress=100,
            error_log=err if status == TrainStatus.FAILED else None,
            finished_at=datetime.now(),
        )

    # ------------------------------------------------------------ 两条流
    @classmethod
    async def _consume_logs(cls, client, task_id: int, job_id: str):
        try:
            async for line in client.stream_logs(job_id, tail=200):
                await broadcast_line(task_id, line)
        except asyncio.CancelledError:
            raise
        except TorchKilnError as e:
            log.warning("[torchkiln] 日志流中断: %s", e)
            await broadcast_line(task_id, f"[torchkiln] 日志流中断: {e}")

    @classmethod
    async def _consume_metrics(cls, client, task_id: int, job_id: str,
                               last_seq: int, rows: list[dict]):
        pending = 0
        loop = asyncio.get_event_loop()
        last_flush = loop.time()
        try:
            async for ev in client.stream_metrics(job_id, offset=last_seq):
                if ev.get("__end__"):
                    break
                seq = ev.get("seq")
                if isinstance(seq, int):
                    if seq <= last_seq:
                        continue
                    last_seq = seq
                publish_metric(task_id, ev)
                row = cls._row_from_event(ev)
                if row:
                    rows.append(row)
                    pending += 1
                now = loop.time()
                if pending >= _FLUSH_EVERY or (now - last_flush) >= _FLUSH_SECONDS:
                    await save_metrics(task_id, rows)
                    pending = 0
                    last_flush = now
        except asyncio.CancelledError:
            raise
        except TorchKilnError as e:
            log.warning("[torchkiln] 指标流中断: %s", e)
        finally:
            try:
                if rows:
                    await save_metrics(task_id, rows)
            except Exception as e:  # noqa: BLE001
                log.warning("[torchkiln] 指标落库失败: %s", e)

    @classmethod
    async def _await_terminal(cls, client, task_id: int, job_id: str,
                              poll_seconds: float = 5.0) -> dict:
        """轮询到终态（取消请求也在这里被翻译成服务端的 cancel）。"""
        while True:
            if cls._registry.get(task_id, {}).get("cancel"):
                await broadcast_line(task_id, "[torchkiln] 收到停止请求，转发取消")
                try:
                    return await client.cancel_job(job_id)
                except TorchKilnError as e:
                    log.warning("[torchkiln] 取消失败: %s", e)
                    return {"status": "cancelled", "exit_reason": "cancelled"}
            info = await client.get_job(job_id)
            status = str(info.get("status"))
            if status in ("succeeded", "failed", "cancelled"):
                return info
            await asyncio.sleep(poll_seconds)


# ---------------------------------------------------------------- 对外辅助
async def service_status() -> dict:
    """训练服务可用性（前端"训练"页展示，避免点了开始才报错）。"""
    return await probe_service()


def executor_info() -> dict:
    return {
        "executor": TorchKilnExecutor.name,
        "url": settings.TORKILN_SERVICE_URL,
        "enabled": bool(settings.TORKILN_ENABLED),
        "has_token": bool(settings.TORKILN_SERVICE_TOKEN),
    }
