"""工作流服务：CRUD 与流式运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.trigger_util import TriggerUtil

from .cancel import clear_cancel, is_cancelled, request_cancel
from .engine import WorkflowCancelled, WorkflowEngine
from .model import (
    AiWorkflowModel,
    AiWorkflowRunLogModel,
    AiWorkflowScheduleModel,
    AiWorkflowVersionModel,
)
from .schema import AiWorkflowApproveSchema

#: 引擎任务结束哨兵（经帧队列传给消费端）
_ENGINE_END = object()
#: 取消看门狗轮询间隔（秒）：查得勤才能做到「秒停」
_WATCH_INTERVAL = 0.2
#: 启用中的调度必须有触发表达式：空表达式 = 「已启用但永不触发」的静默失效。
#: 三处写入路径（工作台 / 工作流 / 训练）口径必须一致（同文案）。
_EMPTY_TRIGGER_MSG = "请先配置触发时间（分 时 日 月 周）"

#: 本模块在中心调度器里的作业键前缀（与 `ap_scheduler._BUSINESS_JOB_PREFIXES` 同口径）：
#: 三个模块共用一个调度器，作业键必须带自己的前缀，同步时也只能清理自己的前缀范围
#: （否则会把别的模块的定时任务一并删掉——无告警、只在下次触发时表现为「任务不再运行」）。
_JOB_PREFIX = "ai_workflow_schedule:"


def _job_key(workflow_id: int) -> str:
    """本模块在中心调度器里的作业键（`ai_workflow_schedule:{id}`）。"""
    return f"{_JOB_PREFIX}{workflow_id}"


def _resolve_trigger(
    trigger: str | None, trigger_args, legacy_cron: str | None, enabled: bool
) -> tuple[str, object | None]:
    """把请求里的触发配置解析为落库值 `(trigger, trigger_args)`。

    **字段优先**：`trigger` 显式提供（非空串）时以它为准；兼容字段 `cron` **仅在 `trigger`
    缺省时**才被解读 —— 非 cron 类型的前端仍会带上 `cron: ""`，若先看旧字段会把它误判成
    「空表达式 + 启用」而误报 400（C4 审查钉死的缺口）。

    - cron 表达式为空（未提供 / 显式空串）：**启用中** → 400（`_EMPTY_TRIGGER_MSG`，不留
      「已启用但永不触发」的静默失效）；**未启用** → `("cron", None)`（「未配置 / 清空配置」语义）；
    - 其余情况：统一层 `TriggerUtil.validate`（非法 → 400，原因原样回显）+ `normalize`
      （写入即规范化：`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）。
    """
    name = trigger.strip() if isinstance(trigger, str) else ""
    args = trigger_args if name else legacy_cron
    if not name:
        name = "cron"
    if name == "cron" and (args is None or (isinstance(args, str) and not args.strip())):
        if enabled:
            raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
        return "cron", None
    ok, reason = TriggerUtil.validate(name, args)
    if not ok:
        raise CustomException(msg=reason, code=400, status_code=400)
    return TriggerUtil.normalize(name, args)


async def run_scheduled_workflow(workflow_id: int) -> None:
    """中心调度器作业入口：按调度运行工作流，并把调度状态回写库。

    刻意用**模块级函数**（而非闭包）：`obj_to_ref` 能解析出引用，作业状态可完整序列化，
    日志里也有可读的函数名（闭包会走降级路径）。

    触发时**重新读库**确认「调度行仍启用且已配置触发」（口径同训练模块
    `run_scheduled_training`）：作业与调度行之间存在窗口期（禁用/删除请求刚提交、
    或同键替换前的最后一次触发），此时静默跳过——绝不因为一条已被停用的调度而运行工作流。
    **未配置表达式也跳过，但 `now`（立即执行）例外**：它按契约本就没有参数
    （`trigger_args` 恒为 `None`），不是「未配置」；漏掉这个例外，A9 注册上的一次性作业
    触发时会被再次拦下，作业空转。

    `next_run_time` 一律由作业回写（单一真源）：运行结束后（无论成败）都从作业读回，
    库里的值永远等于作业的值，业务侧不再自算。
    """
    async with async_db_session() as db:
        row = (
            await db.execute(
                select(AiWorkflowScheduleModel).where(
                    AiWorkflowScheduleModel.workflow_id == workflow_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            log.info(f"[workflow] 工作流 {workflow_id} 的调度已删除，跳过本次触发")
            return
        if not row.enabled or not (row.trigger_args or row.trigger == "now"):
            log.info(
                f"[workflow] 工作流 {workflow_id} 的调度已停用或未配置触发时间"
                "（且非「立即执行」），跳过本次触发"
            )
            return

    started = datetime.now(ZoneInfo(TriggerUtil.TIMEZONE))
    try:
        await AiWorkflowService.run_schedule(workflow_id)
    finally:
        await AiWorkflowService.write_back_schedule_state(workflow_id, ran_at=started)


def _to_dict(w: AiWorkflowModel) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description or "",
        "category_id": w.category_id,
        "graph": w.graph or {"nodes": [], "edges": []},
        "version": w.version or 1,
        "enabled": w.enabled,
        "created_time": w.created_time,
        "updated_time": w.updated_time,
    }


def _version_dict(v: AiWorkflowVersionModel) -> dict:
    return {
        "id": v.id,
        "workflow_id": v.workflow_id,
        "version_no": v.version_no,
        "graph": v.graph or {"nodes": [], "edges": []},
        "remark": v.remark or "",
        "published": v.published,
        "created_time": v.created_time,
    }


class AiWorkflowService:

    @classmethod
    async def count_workflows(cls) -> int:
        """未删除的工作流数量（控制台/看板跨模块取数入口，不暴露模型）。"""
        async with async_db_session() as db:
            return int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(AiWorkflowModel)
                        .where(AiWorkflowModel.is_deleted.is_(False))
                    )
                ).scalar()
                or 0
            )

    @classmethod
    async def list_workflows(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiWorkflowModel)
                    .where(AiWorkflowModel.is_deleted.is_(False))
                    .order_by(AiWorkflowModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(w) for w in rows]

    @classmethod
    async def get_workflow(cls, workflow_id: int) -> dict | None:
        async with async_db_session() as db:
            w = await db.get(AiWorkflowModel, workflow_id)
            if not w or w.is_deleted:
                return None
            return _to_dict(w)

    # AIP 工作流模板市场
    _TEMPLATES = [
        {"key": "data_analysis", "name": "数据分析流", "description": "收集数据 → 分析 → 生成报告",
         "graph": {"nodes": [{"id": "n1", "type": "tool", "label": "数据查询", "task": "查询数据"},
                             {"id": "n2", "type": "llm", "label": "分析总结", "task": "分析数据"},
                             {"id": "n3", "type": "output", "label": "生成报告", "task": "生成报告"}],
                   "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}]}},
        {"key": "review", "name": "审核流", "description": "提交 → 人工审批 → 归档",
         "graph": {"nodes": [{"id": "n1", "type": "input", "label": "提交", "task": "接收输入"},
                             {"id": "n2", "type": "approval", "label": "人工审批", "task": "审批"},
                             {"id": "n3", "type": "output", "label": "归档", "task": "归档结果"}],
                   "edges": [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}]}},
        {"key": "rag", "name": "知识问答流", "description": "检索知识库 → LLM 回答",
         "graph": {"nodes": [{"id": "n1", "type": "tool", "label": "知识检索", "task": "检索知识库"},
                             {"id": "n2", "type": "llm", "label": "LLM 回答", "task": "生成回答"}],
                   "edges": [{"source": "n1", "target": "n2"}]}},
    ]

    @classmethod
    async def workflow_templates(cls) -> list[dict]:
        return [dict(t) for t in cls._TEMPLATES]

    @classmethod
    async def create_from_template(cls, key: str, name: str, auth) -> dict | None:
        tpl = next((t for t in cls._TEMPLATES if t["key"] == key), None)
        if not tpl:
            return None
        from types import SimpleNamespace as SN
        data = SN(name=name or tpl["name"], description=tpl.get("description") or "",
                  graph=tpl.get("graph"), enabled=True)
        return await cls.create(data, auth)

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            w = AiWorkflowModel(
                name=data.name,
                description=data.description or "",
                graph=data.graph or {"nodes": [], "edges": []},
                version=1,
                enabled=data.enabled,
                # 模板创建路径传的是 SimpleNamespace（无 category_id），故用 getattr 兜底
                category_id=getattr(data, "category_id", None),
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(w)
            await db.flush()
            return _to_dict(w)

    @classmethod
    async def update(cls, workflow_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            w = await db.get(AiWorkflowModel, workflow_id)
            if not w or w.is_deleted:
                return None
            provided = getattr(data, "model_fields_set", set())
            for key in ("name", "description", "graph", "enabled"):
                if key not in provided:
                    continue
                if getattr(data, key) is None:
                    continue
                setattr(w, key, getattr(data, key))
            # 分类允许**显式清空**（clearable 下拉传来 null）：与其它字段的「None=不修改」语义区分
            if "category_id" in provided:
                w.category_id = data.category_id
            if "graph" in provided:
                w.version = (w.version or 1) + 1
            w.updated_id = auth.user.id
            await db.flush()
            return _to_dict(w)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for wid in ids:
                w = await db.get(AiWorkflowModel, wid)
                if w:
                    await db.delete(w)
                # 调度行没有 FK 级联：随工作流一并清理，并移除中心调度器里的作业。
                # 否则「已删除的工作流」会留下一条启用中的调度行 + 一个照常触发的作业
                # （幽灵作业：每次触发都空跑一遍，用户侧看不出任何东西）。
                row = (
                    await db.execute(
                        select(AiWorkflowScheduleModel).where(
                            AiWorkflowScheduleModel.workflow_id == wid
                        )
                    )
                ).scalar_one_or_none()
                if row:
                    await db.delete(row)
                cls._remove_schedule_job(wid)

    # ---------- 版本 / 发布 / 回滚 ----------
    @classmethod
    async def save_version(cls, workflow_id: int, data, auth) -> dict | None:
        """保存工作流当前 DAG 为版本快照，并推进工作流版本号。"""
        async with async_db_session.begin() as db:
            w = await db.get(AiWorkflowModel, workflow_id)
            if not w or w.is_deleted:
                return None
            latest = await db.scalar(
                select(func.max(AiWorkflowVersionModel.version_no)).where(
                    AiWorkflowVersionModel.workflow_id == workflow_id
                )
            )
            version_no = (latest or 0) + 1
            v = AiWorkflowVersionModel(
                workflow_id=workflow_id,
                version_no=version_no,
                graph=data.graph if data.graph is not None else (w.graph or {"nodes": [], "edges": []}),
                remark=data.remark or "",
                published=(version_no == 1),
                created_id=auth.user.id,
            )
            db.add(v)
            w.version = version_no
            await db.flush()
            return _version_dict(v)

    @classmethod
    async def list_versions(cls, workflow_id: int) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiWorkflowVersionModel)
                    .where(
                        AiWorkflowVersionModel.workflow_id == workflow_id,
                        AiWorkflowVersionModel.is_deleted.is_(False),
                    )
                    .order_by(AiWorkflowVersionModel.version_no.desc())
                )
            ).scalars().all()
            return [_version_dict(v) for v in rows]

    @classmethod
    async def rollback_version(cls, workflow_id: int, version_id: int, auth) -> dict | None:
        """把工作流回滚到指定版本（恢复 graph 与版本号）。"""
        async with async_db_session.begin() as db:
            w = await db.get(AiWorkflowModel, workflow_id)
            v = await db.get(AiWorkflowVersionModel, version_id)
            if not w or w.is_deleted or not v or v.workflow_id != workflow_id:
                return None
            w.graph = v.graph
            w.version = v.version_no
            w.updated_id = auth.user.id
            return _to_dict(w)

    @classmethod
    async def publish_version(cls, workflow_id: int, version_id: int, auth) -> dict | None:
        """发布指定版本为线上版本：置为已发布并同步工作流 graph/version。"""
        async with async_db_session.begin() as db:
            w = await db.get(AiWorkflowModel, workflow_id)
            v = await db.get(AiWorkflowVersionModel, version_id)
            if not w or w.is_deleted or not v or v.workflow_id != workflow_id:
                return None
            others = (
                await db.execute(
                    select(AiWorkflowVersionModel).where(
                        AiWorkflowVersionModel.workflow_id == workflow_id,
                        AiWorkflowVersionModel.published.is_(True),
                    )
                )
            ).scalars().all()
            for o in others:
                o.published = False
            v.published = True
            w.graph = v.graph
            w.version = v.version_no
            w.updated_id = auth.user.id
            return _to_dict(w)

    @classmethod
    async def run_ui_stream(
        cls,
        workflow_id: int,
        ui_messages: list[dict],
        auth,
        variables: dict | None = None,
        session_id: int | None = None,
        redis=None,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[str]:
        """运行工作流：实例化引擎并流式产出 UI Message Stream 帧。

        LLM 节点挂起待审批时（HITL），把运行状态持久化到 Redis 并产出
        ``data-finish``（含 ``awaiting_approval`` 与 ``run_id``），供前端调审批接口续跑。
        """
        from app.plugin.module_ai.assistant.service import (
            extract_openai_messages,
            last_user_text,
        )
        from app.plugin.module_ai.overview.service import AiOverviewService
        from app.plugin.module_ai.sessions.service import persist_session_exchange
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        t0 = time.perf_counter()
        uid = getattr(getattr(auth, "user", None), "id", None)
        user_text = last_user_text(ui_messages)
        trace: list = []
        log_id: int | None = None
        run_id: str | None = None
        watcher: asyncio.Task | None = None
        engine_task: asyncio.Task | None = None
        state: dict = {
            "assistant_text": "",
            "reply": "",
            "tool_calls": [],
            "action": None,
            "report_id": None,
            "error": None,
            "halted": False,
            "pending_approval": None,
        }
        yield ms.start()
        try:
            workflow = await cls.get_workflow(workflow_id)
            if not workflow or not workflow.get("enabled"):
                state["error"] = "工作流不存在或未启用"
                yield ms.error(state["error"])
            else:
                graph = workflow.get("graph") or {}
                openai_messages = extract_openai_messages(ui_messages)
                run_id = uuid.uuid4().hex
                # 先落 running 记录：历史里能看到「运行中」，且它同时是取消信号标识
                log_id = await cls._start_run(
                    workflow_id,
                    {"messages": ui_messages, "variables": variables or {},
                     "user_text": user_text},
                    uid,
                )
                if log_id:
                    # 把运行记录 id 下发给前端：它是取消运行的目标（run-log/{id}/cancel）
                    yield ms.data("run", {"run_log_id": log_id, "run_id": run_id})

                engine = WorkflowEngine(
                    graph=graph,
                    variables=variables or {},
                    messages=openai_messages,
                    ms=ms,
                    state=state,
                    user_id=uid,
                    timeout_seconds=timeout_seconds,
                    run_id=run_id,
                    cancel_key=str(log_id) if log_id else None,
                    redis=redis,
                )

                # 引擎放进**独立任务**，帧经队列转出。
                # 为什么必须这样：取消原来只在引擎里**逐帧**检查，而节点可能长时间不产帧
                # （LLM 思考期、非流式工具调用），逐帧检查要等下一帧才生效——用户点了
                # 「停止」却半天没反应（实测：静默期要等首个 token）。放进任务后，取消/
                # 断开可以**直接 cancel 这个任务**，立刻打断节点里正在进行的 await。
                queue: asyncio.Queue = asyncio.Queue()
                outcome: dict = {"kind": None}  # None=正常结束 / "cancelled" / "error"

                async def _drive_engine() -> None:
                    try:
                        async for frame in engine.run():
                            queue.put_nowait(frame)
                    except WorkflowCancelled:
                        outcome["kind"] = "cancelled"
                    except asyncio.CancelledError:
                        # 被看门狗/断开直接打断：必须记 cancelled（不能当失败）
                        outcome["kind"] = "cancelled"
                        raise
                    except Exception as e:  # noqa: BLE001
                        outcome["kind"] = "error"
                        state["error"] = str(e)
                    finally:
                        queue.put_nowait(_ENGINE_END)

                engine_task = asyncio.create_task(_drive_engine())

                # 取消看门狗：每 0.2s 查一次取消信号（内存+Redis，多 worker 也能收到），
                # 命中即**直接 cancel 引擎任务**，做到「秒停」。
                # 客户端断开不走这里：中间件已改为纯 ASGI，``http.disconnect`` 能透传到
                # StreamingResponse（``listen_for_disconnect``），生成器随即被取消，
                # 下面的 ``except (GeneratorExit, CancelledError)`` 会取消引擎任务并补写记录。
                async def _watch_cancel() -> None:
                    while not engine_task.done():
                        await asyncio.sleep(_WATCH_INTERVAL)
                        try:
                            if engine.cancel_key and await is_cancelled(
                                engine.cancel_key, redis
                            ):
                                engine_task.cancel()
                                return
                        except BaseException:  # noqa: BLE001 轮询失败即放弃（不误杀运行）
                            return

                watcher = asyncio.create_task(_watch_cancel())

                while True:
                    frame = await queue.get()
                    if frame is _ENGINE_END:
                        break
                    yield frame
                    if '"type": "node-status"' in frame:
                        try:
                            trace.append(json.loads(frame[len("data: ") :].strip()))
                        except Exception:  # noqa: BLE001
                            pass

                if outcome["kind"] == "cancelled":
                    state["cancelled"] = True
                    # 被**硬中断**时引擎来不及补 cancelled 帧（它是在 await 处被打断的），
                    # 由这里补齐：否则前端轨迹里被中断的节点会一直显示「执行中」。
                    # ⚠️ trace 是**追加**的（同一节点会有 running/success 多条），必须按节点取
                    #    **最后一条**判断当前状态；否则早已完成的节点（如「开始」）也会被补成
                    #    已取消，前端轨迹里就凭空多出一行（实测踩过）。
                    current: dict[str, dict] = {}
                    for t in trace:
                        nid = t.get("nodeId")
                        if nid:
                            current[nid] = t
                    for t in current.values():
                        if t.get("status") == "running":
                            yield ms.node_status(
                                t.get("nodeId"), "cancelled", t.get("label") or t.get("nodeId")
                            )
                    yield ms.error("运行已取消")
                elif outcome["kind"] == "error":
                    yield ms.error(f"运行失败：{state['error']}")
                elif state.get("halted") and state.get("pending_approval"):
                    # HITL：持久化运行状态，供前端审批后调 approve 续跑
                    await cls._persist_pending(redis, run_id, workflow_id, state, uid)
                else:
                    state["finished"] = True
        except (GeneratorExit, asyncio.CancelledError):
            # 客户端断开（关页面 / 前端 abort SSE）或任务被取消：此刻本任务已被取消，
            # 任何 await 都会立刻再抛，收尾写库必然丢失 → 运行记录永远停在 running
            # （实测：前端点「停止」后 abort SSE，记录卡在 running）。
            # 只能**另起任务**补写（独立任务不受本任务取消影响）。
            # 引擎现在是**独立任务**，必须显式取消，否则客户端走了它还在白跑。
            if engine_task and not engine_task.done():
                engine_task.cancel()
            if watcher:
                watcher.cancel()
            if log_id and not state.get("finished"):
                state["cancelled"] = True
                cls._finalize_run_detached(log_id, state, trace, t0, redis)
            raise
        except WorkflowCancelled:
            # 用户点了「停止」：明确区分于失败，前端提示「已取消」而非「运行失败」
            state["cancelled"] = True
            yield ms.error("运行已取消")
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)
            yield ms.error(f"运行失败：{e}")

        # ⚠️ 收尾必须放在**终止帧之前**。终止帧（finish/done）一发出，客户端就会断开，
        #    Starlette（BaseHTTPMiddleware）随即取消本任务；写在 finally 里的收尾
        #    会被取消掉——实测表现为运行记录永远停在 running（历史整条丢失）。
        status = cls._run_status(state)
        if watcher:
            watcher.cancel()  # 运行已收尾，看门狗没用了
        try:
            await AiOverviewService.add_log(
                runtime_model_name(workflow_id),
                "workflow",
                int((time.perf_counter() - t0) * 1000),
                # 调用日志只有 success/error 两类语义：取消与失败都算 error，HITL 挂起算 pending
                "success" if status == "success" else ("pending" if status == "pending" else "error"),
                state["error"],
                app_id=workflow_id,
                user_id=uid,
            )
            await persist_session_exchange(
                session_id,
                user_text,
                state["assistant_text"],
                app_id=workflow_id,
                user_id=uid,
            )
        except Exception:  # noqa: BLE001 调用日志/会话落库失败不影响结果帧
            pass
        await cls._finish_run(
            log_id,
            status,
            {"reply": state["reply"] or state["assistant_text"],
             "tool_calls": state["tool_calls"]},
            state["error"],
            trace,
            int((time.perf_counter() - t0) * 1000),
        )
        if log_id:
            await clear_cancel(log_id, redis)

        finish_payload = {
            "reply": state["reply"] or state["assistant_text"],
            "tool_calls": state["tool_calls"],
            "action": state["action"],
            "report_id": state["report_id"],
        }
        if state.get("halted") and state.get("pending_approval"):
            finish_payload.update({
                "awaiting_approval": True,
                "run_id": run_id,
                "pending_tool_calls": [
                    {
                        "toolCallId": t["toolCallId"],
                        "toolName": t["toolName"],
                        "arguments": t.get("arguments"),
                    }
                    for t in state["pending_approval"].get("pending", [])
                ],
            })
        if status == "cancelled":
            finish_payload["cancelled"] = True
        yield ms.data("finish", finish_payload)
        yield ms.finish()
        yield ms.done()

    @classmethod
    async def debug_node_ui_stream(
        cls,
        workflow_id: int,
        node_id: str,
        variables: dict | None = None,
        messages: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """单节点调试：运行指定节点（带给定变量），产出 node-status/输出帧。"""
        from app.plugin.module_ai.assistant.service import extract_openai_messages
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        yield ms.start()
        try:
            workflow = await cls.get_workflow(workflow_id)
            if not workflow:
                yield ms.error("工作流不存在或未启用")
                yield ms.finish()
                yield ms.done()
                return
            openai_messages = extract_openai_messages(messages or [])
            state: dict = {
                "assistant_text": "",
                "reply": "",
                "tool_calls": [],
                "action": None,
                "report_id": None,
                "error": None,
                "halted": False,
                "pending_approval": None,
            }
            engine = WorkflowEngine(
                graph=workflow.get("graph") or {},
                variables=variables or {},
                messages=openai_messages,
                ms=ms,
                state=state,
                user_id=None,
            )
            async for frame in engine.run_single(node_id):
                yield frame
            yield ms.finish()
            yield ms.done()
        except Exception as e:  # noqa: BLE001
            yield ms.error(f"调试失败：{e}")
            yield ms.finish()
            yield ms.done()

    @classmethod
    async def step_node_ui_stream(
        cls,
        workflow_id: int,
        run_id: str | None,
        variables: dict | None,
        messages: list[dict] | None,
        redis=None,
    ) -> AsyncIterator[str]:
        """逐步执行：每次运行一个节点（replay 式），frontier 持久化到 Redis。

        首步 ``run_id`` 为空则新建；后续带 ``run_id`` 续跑。结束时以
        ``data: step`` 帧回传 ``run_id`` 与 ``done``。
        """
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        yield ms.start()
        try:
            workflow = await cls.get_workflow(workflow_id)
            if not workflow:
                yield ms.error("工作流不存在或未启用")
                yield ms.finish()
                yield ms.done()
                return
            graph = workflow.get("graph") or {}
            if not run_id:
                run_id = uuid.uuid4().hex
                frontier = cls._new_step_frontier(variables, messages)
            else:
                frontier = await cls._load_step(redis, run_id)
                if frontier is None:
                    yield ms.error("步骤会话已失效，请重新开始")
                    yield ms.finish()
                    yield ms.done()
                    return
            engine = WorkflowEngine(
                graph=graph,
                variables=frontier.get("variables") or {},
                messages=frontier.get("messages") or [],
                ms=ms,
                state=frontier.get("state") or {},
                user_id=None,
                initial_outputs=frontier.get("outputs") or {},
                initial_visited=set(frontier.get("visited") or []),
                initial_stack=frontier.get("stack") or [],
            )
            async for frame in engine.run(budget=1):
                yield frame
            await cls._save_step(
                redis,
                run_id,
                {
                    "visited": list(engine._visited),
                    "stack": list(engine._stack),
                    "outputs": engine.outputs,
                    "state": engine.state,
                    "variables": engine.variables,
                    "messages": engine.messages,
                },
            )
            yield ms.data("step", {"run_id": run_id, "done": engine._completed})
            yield ms.finish()
            yield ms.done()
        except Exception as e:  # noqa: BLE001
            yield ms.error(f"步骤运行失败：{e}")
            yield ms.finish()
            yield ms.done()

    @staticmethod
    def _step_key(run_id: str) -> str:
        return f"ai:workflow:step:{run_id}"

    @staticmethod
    def _new_step_frontier(variables, messages) -> dict:
        return {
            "visited": [],
            "stack": [],
            "outputs": {},
            "state": {
                "assistant_text": "",
                "reply": "",
                "tool_calls": [],
                "action": None,
                "report_id": None,
                "error": None,
                "halted": False,
                "pending_approval": None,
            },
            "variables": variables or {},
            "messages": messages or [],
        }

    @staticmethod
    async def _save_step(redis, run_id: str, frontier: dict) -> None:
        if not redis:
            return
        await redis.set(
            AiWorkflowService._step_key(run_id),
            json.dumps(frontier, ensure_ascii=False, default=str),
            ex=3600,
        )

    @staticmethod
    async def _load_step(redis, run_id: str) -> dict | None:
        if not redis:
            return None
        raw = await redis.get(AiWorkflowService._step_key(run_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def _start_run(
        cls, workflow_id: int, run_input: dict, uid: int | None
    ) -> int | None:
        """运行开始时先落一条 ``running`` 记录，返回其主键（同时作为取消信号标识）。

        为什么必须先落 ``running``：只在结束时记录的话，「运行中」的运行在历史里
        完全不可见，也没有可定位的取消目标；进程崩溃/客户端断连时更是直接丢失
        （事后看不出是「中断了」还是「从没跑过」）。
        """
        try:
            async with async_db_session() as db:
                row = AiWorkflowRunLogModel(
                    workflow_id=workflow_id,
                    status="running",
                    run_input=run_input,
                    run_output=None,
                    error=None,
                    node_trace=[],
                    duration_ms=0,
                    created_id=uid,
                )
                db.add(row)
                await db.commit()
                await db.refresh(row)
                return row.id
        except Exception:  # noqa: BLE001 运行历史记录失败不影响主流程
            return None

    @classmethod
    async def _finish_run(
        cls,
        log_id: int | None,
        status: str,
        run_output: dict,
        error: str | None,
        node_trace: list,
        duration_ms: int,
    ) -> None:
        """运行结束时更新记录（``success`` / ``error`` / ``cancelled`` / ``pending``）。"""
        if not log_id:
            return
        try:
            async with async_db_session.begin() as db:
                row = await db.get(AiWorkflowRunLogModel, log_id)
                if not row:
                    return
                row.status = status
                row.run_output = run_output
                row.error = (error or "")[:1024] or None
                row.node_trace = node_trace
                row.duration_ms = duration_ms
        except Exception:  # noqa: BLE001 运行历史记录失败不影响主流程
            pass

    @staticmethod
    def _run_status(state: dict) -> str:
        """由运行态推导记录状态。

        ``finished`` 未置位说明是**被中断**（客户端断连/任务被取消）——
        此时必须记 ``cancelled``，否则会与「正常结束」混淆。
        """
        if state.get("cancelled"):
            return "cancelled"
        if state.get("error"):
            return "error"
        if state.get("halted"):
            return "pending"
        if not state.get("finished"):
            return "cancelled"
        return "success"

    @classmethod
    async def list_run_logs(cls, workflow_id: int, limit: int = 20) -> list[dict]:
        """按时间倒序返回某工作流的运行历史（不含节点轨迹，保持轻量）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiWorkflowRunLogModel)
                    .where(AiWorkflowRunLogModel.workflow_id == workflow_id)
                    .order_by(AiWorkflowRunLogModel.id.desc())
                    .limit(limit)
                )
            ).scalars().all()
        return [
            {
                "id": r.id,
                "status": r.status,
                "run_input": r.run_input,
                "run_output": r.run_output,
                "error": r.error,
                "duration_ms": r.duration_ms,
                "created_time": r.created_time,
            }
            for r in rows
        ]

    @classmethod
    async def get_run_log(cls, run_id: int) -> dict | None:
        """取单次运行完整记录（含节点轨迹）。"""
        async with async_db_session() as db:
            r = await db.get(AiWorkflowRunLogModel, run_id)
        if not r:
            return None
        return {
            "id": r.id,
            "workflow_id": r.workflow_id,
            "status": r.status,
            "run_input": r.run_input,
            "run_output": r.run_output,
            "error": r.error,
            "node_trace": r.node_trace,
            "duration_ms": r.duration_ms,
            "created_time": r.created_time,
        }

    @classmethod
    async def reconcile_stale_runs(cls, max_age_minutes: int = 30) -> int:
        """把**超龄的 ``running`` 运行**标记为 ``cancelled``，返回处理条数。

        为什么需要：运行开始时就会落 ``running`` 记录；若进程在运行途中重启/被杀，
        收尾写不进去，这条记录会**永远停在 running**（前端一直显示"运行中"）。
        启动时清一次即可。

        只清「创建时间早于 ``max_age_minutes``」的行：多 worker 下别的进程可能正在
        正常跑，按时间阈值避开误伤（单次运行不可能超过这么久——节点超时远小于它）。
        """
        from datetime import datetime, timedelta

        from sqlalchemy import select

        cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
        try:
            async with async_db_session.begin() as db:
                rows = (
                    await db.execute(
                        select(AiWorkflowRunLogModel).where(
                            AiWorkflowRunLogModel.status == "running",
                            AiWorkflowRunLogModel.created_time < cutoff,
                        )
                    )
                ).scalars().all()
                for r in rows:
                    r.status = "cancelled"
                    r.error = "运行未正常结束（进程重启或中断）"
                return len(rows)
        except Exception as e:  # noqa: BLE001 兜底清理失败不阻断启动
            log.warning(f"[workflow] 清理僵尸 running 记录失败（忽略）：{str(e)[:120]}")
            return 0

    @classmethod
    def _finalize_run_detached(cls, log_id: int, state: dict, trace: list,
                               t0: float, redis=None) -> None:
        """客户端断开/任务被取消时，**另起任务**把运行记录补写成 ``cancelled``。

        为什么不能直接 await：此刻本任务已被取消（``GeneratorExit`` /
        ``CancelledError``），任何 ``await`` 都会立刻再抛，收尾写库必然丢失。
        独立任务不受本任务取消影响，能把记录补完（尽力而为，失败只忽略）。
        """
        async def _run() -> None:
            try:
                await cls._finish_run(
                    log_id,
                    "cancelled",
                    {"reply": state.get("reply") or state.get("assistant_text") or "",
                     "tool_calls": state.get("tool_calls") or []},
                    None,
                    trace,
                    int((time.perf_counter() - t0) * 1000),
                )
                await clear_cancel(log_id, redis)
            except Exception:  # noqa: BLE001 尽力而为，不向外抛
                pass

        try:
            asyncio.create_task(_run())
        except RuntimeError:  # 事件循环已关闭：放弃补写
            pass

    @classmethod
    async def cancel_run(cls, run_id: int, redis=None) -> dict:
        """请求取消一次**运行中**的工作流。

        - 只有 ``running`` 状态可取消；已完成/已取消/失败的直接如实告知
          （避免前端提示"已停止"但其实什么都没发生）；
        - 取消信号写内存 + Redis（多 worker 广播）；引擎在**节点边界**与
          **每个流式帧**检查，因此 LLM/知识检索等流式节点可被立即中断。

        注意：取消是**请求**而非瞬时结果——接口返回后引擎会在下一个检查点停下，
        运行记录的 ``status`` 届时由运行方更新为 ``cancelled``。
        """
        from app.core.exceptions import CustomException

        async with async_db_session() as db:
            row = await db.get(AiWorkflowRunLogModel, run_id)
        if not row:
            raise CustomException(msg="运行记录不存在")
        if row.status != "running":
            return {"cancelled": False, "status": row.status,
                    "msg": f"该运行状态为 {row.status}，无需取消"}
        await request_cancel(run_id, redis)
        return {"cancelled": True, "status": "running", "msg": "已发送取消请求"}

    @classmethod
    async def get_workflow_stats(cls, workflow_id: int) -> dict:
        """聚合某工作流的运行统计（次数/成功率/耗时）。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(
                        AiWorkflowRunLogModel.status,
                        AiWorkflowRunLogModel.duration_ms,
                    ).where(AiWorkflowRunLogModel.workflow_id == workflow_id)
                )
            ).all()
        statuses = [r.status for r in rows]
        durs = [r.duration_ms or 0 for r in rows]
        n = len(statuses)
        success = statuses.count("success")
        error = statuses.count("error")
        pending = statuses.count("pending")
        return {
            "total": n,
            "success": success,
            "error": error,
            "pending": pending,
            "success_rate": round(success / n * 100, 1) if n else 0,
            "avg_ms": round(sum(durs) / n) if n else 0,
            "min_ms": min(durs) if durs else 0,
            "max_ms": max(durs) if durs else 0,
        }

    @classmethod
    async def generate_share_token(cls, workflow_id: int, uid) -> str | None:
        """为已启用工作流生成/复用公开展示令牌。"""
        async with async_db_session() as db:
            wf = await db.get(AiWorkflowModel, workflow_id)
            if not wf:
                return None
            if not wf.enabled:
                raise RuntimeError("仅启用的工作流可公开分享")
            if not wf.share_token:
                wf.share_token = uuid.uuid4().hex
                wf.updated_id = uid
                await db.commit()
                await db.refresh(wf)
            return wf.share_token

    @classmethod
    async def _get_by_share_token(cls, token: str) -> dict | None:
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiWorkflowModel).where(AiWorkflowModel.share_token == token)
                )
            ).scalar_one_or_none()
        if not row:
            return None
        return {
            "id": row.id,
            "name": row.name,
            "graph": row.graph or {"nodes": [], "edges": []},
            "enabled": row.enabled,
        }

    @classmethod
    async def share_ui_stream(
        cls, token: str, message: str, redis=None, ip: str = ""
    ) -> AsyncIterator[str]:
        """公开分享受限运行：匿名、仅白名单节点、令牌 + IP 双重限流。"""
        from app.plugin.module_ai.assistant.service import extract_openai_messages
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        yield ms.start()
        try:
            if not token:
                yield ms.error("缺少分享令牌")
                yield ms.finish()
                yield ms.done()
                return
            # 限流：令牌维度（每分钟 20 次）+ IP 维度（每分钟 30 次）
            if redis:
                async def _limit(key: str, cap: int):
                    cnt = int(await redis.incr(key))
                    if cnt == 1:
                        await redis.expire(key, 60)
                    return cnt > cap

                if await _limit(f"ai:workflow:share:rl:{token}", 20) or await _limit(
                    f"ai:workflow:share:rl:ip:{ip or 'na'}", 30
                ):
                    yield ms.error("访问过于频繁，请稍后再试")
                    yield ms.finish()
                    yield ms.done()
                    return
            wf = await cls._get_by_share_token(token)
            if not wf or not wf.get("enabled"):
                yield ms.error("分享无效或该工作流已停用")
                yield ms.finish()
                yield ms.done()
                return
            state: dict = {
                "assistant_text": "",
                "reply": "",
                "tool_calls": [],
                "action": None,
                "report_id": None,
                "error": None,
                "halted": False,
                "pending_approval": None,
            }
            openai_messages = extract_openai_messages(
                [{"role": "user", "parts": [{"type": "text", "text": message}]}]
            )
            engine = WorkflowEngine(
                graph=wf["graph"],
                variables={},
                messages=openai_messages,
                ms=ms,
                state=state,
                user_id=None,
                restricted=True,
            )
            async for frame in engine.run():
                yield frame
            yield ms.data(
                "finish",
                {
                    "reply": state["reply"] or state["assistant_text"],
                    "tool_calls": state["tool_calls"],
                    "action": state["action"],
                    "report_id": state["report_id"],
                },
            )
            yield ms.finish()
            yield ms.done()
        except Exception as e:  # noqa: BLE001
            yield ms.error(f"运行失败：{e}")
            yield ms.finish()
            yield ms.done()

    @classmethod
    async def set_schedule(cls, workflow_id: int, data, enabled: bool | None = None) -> dict:
        """保存调度配置：写入规范化后的触发配置，并同步中心调度器作业。

        请求体是 `AiWorkflowScheduleSchema`（`trigger` + `trigger_args` 四类型统一契约，
        `cron` 仅为兼容字段）；也兼容旧的「直接传 cron 字符串 + enabled」调用形态。

        写入口径（与工作台 / 训练两处一致，统一层是唯一口径）：
        - `trigger` 显式提供时以它为准；`cron` 仅在 `trigger` 缺省时解读（空串视为未提供）；
        - 先 `TriggerUtil.validate`（非法 → 400，原因原样回显）→ `normalize` → 按类型序列化落库
          （interval 落 JSON 串、date 落时间串、now 落 NULL）；
        - 未提供任何触发配置 + **启用中**：明确报错（否则会落一条「已启用但永不触发」的行，
          用户无感知）；未提供 + 未启用：视为「未配置」（清空调度），保住「关闭调度」语义；
        - **例外：库里已是 `now`（立即执行）** —— 它按契约本就没有参数（`trigger_args` 恒为
          `NULL`），不是「未配置」；只切「启用」而不带触发配置时必须保留原触发配置，
          否则 `now` 行连「重新启用」都会被 400 拦下（口径同工作台 / 训练两处）。

        启停/增改一律同步作业（启用 → 注册/替换，禁用或清空 → 移除）；`next_run_time`
        **不再自算**，而是注册后从作业读回（作业是唯一真源，两套口径必然漂移）。
        """
        if isinstance(data, str) or data is None:  # 旧调用形态：第二个位置参数就是 cron
            trigger_in, args_in, cron_in = None, None, data
            enabled_in = bool(enabled)
        else:
            trigger_in = getattr(data, "trigger", None)
            args_in = getattr(data, "trigger_args", None)
            cron_in = getattr(data, "cron", None)
            enabled_in = bool(getattr(data, "enabled", enabled))

        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiWorkflowScheduleModel).where(
                        AiWorkflowScheduleModel.workflow_id == workflow_id
                    )
                )
            ).scalar_one_or_none()
            # 未提交触发配置且库里已是「立即执行」：保留原触发配置（`now` 无参数 ≠「未配置」），
            # 而不是按「空表达式 + 启用」报 400。其余情况一律走统一层解析（含显式清空）。
            keep_now = (
                not TriggerUtil.args_provided(trigger_in, cron_in)
                and row is not None
                and (row.trigger or "cron") == "now"
            )
            if keep_now:
                trigger, trigger_args = "now", None
                stored_args = None
            else:
                trigger, trigger_args = _resolve_trigger(trigger_in, args_in, cron_in, enabled_in)
                stored_args = TriggerUtil.dump_args(trigger, trigger_args)
            if not row:
                row = AiWorkflowScheduleModel(workflow_id=workflow_id)
                db.add(row)
            row.trigger = trigger
            row.trigger_args = stored_args
            row.enabled = enabled_in
            # 先落库再注册作业：作业触发时按库里的行取状态，避免「作业已注册、库还没写」
            await db.commit()
            # 启停/增改一律同步作业；next_run_time 由作业回写（单一真源，不再自算）
            job = cls._sync_schedule_job(workflow_id, trigger, trigger_args, enabled_in)
            row.next_run_time = getattr(job, "next_run_time", None) if job else None
            await db.commit()
            await db.refresh(row)
        return cls._schedule_dict(row)

    @classmethod
    def _sync_schedule_job(cls, workflow_id: int, trigger: str, trigger_args, enabled: bool):
        """把调度行同步到中心调度器：启用 → 注册/替换作业；禁用或未配置 → 移除作业。

        返回注册后的作业（未注册时为 `None`）——`next_run_time` 从它读回，保证「作业是唯一真源」。

        **不调用 `sync_business_jobs`**：那是「按整表同步」的接口（会清理列表外的同前缀作业），
        单行增改用它会把同一模块其它工作流的作业一并删掉；单行用 `register_business_trigger`
        / `remove_business_job`（都是幂等的）。

        注册失败（脏配置 / 调度器不可用）**必须兜底**（口径同训练模块 `sync_train_schedule_job`）：
        先清掉同键残留作业（注册可能是「写了一半才失败」），再给可读错误——绝不能留下
        「已启用但没有作业」的静默失效，也不能让异常原样冒成 500。
        """
        from app.core.ap_scheduler import SchedulerUtil

        job_key = _job_key(workflow_id)
        if enabled and (trigger_args or trigger == "now"):
            try:
                return SchedulerUtil.register_business_trigger(
                    job_key,
                    trigger or "cron",
                    trigger_args,
                    run_scheduled_workflow,
                    args=(workflow_id,),
                )
            except Exception as e:  # noqa: BLE001 单行坏配置不得拖垮增改接口
                cls._remove_schedule_job(workflow_id)
                log.warning(
                    f"[workflow] 工作流 {workflow_id} 的触发配置无法注册作业，已清理残留：{e!s}"
                )
                raise CustomException(
                    msg=f"触发配置无法注册到调度器，调度未生效：{e!s}",
                    code=400,
                    status_code=400,
                ) from e
        cls._remove_schedule_job(workflow_id)
        return None

    @staticmethod
    def _remove_schedule_job(workflow_id: int) -> bool:
        """移除本模块的中心调度器作业（不存在时返回 `False`，不抛）。

        调度器不可用（未启动/已关闭）时 `remove_job` 抛的不是 `JobLookupError`：
        一并吞掉——调度器不可用不得把「保存/禁用调度」「删除工作流」的请求打成 500
        （口径同训练模块 `remove_train_schedule_job`）。
        """
        from app.core.ap_scheduler import SchedulerUtil

        try:
            return SchedulerUtil.remove_business_job(_job_key(workflow_id))
        except Exception as e:  # noqa: BLE001 调度器不可用只记日志，调用方照常继续
            log.warning(
                f"[workflow] 移除工作流 {workflow_id} 的调度作业失败（调度器不可用？）：{e!s}"
            )
            return False

    @classmethod
    async def write_back_schedule_state(
        cls, workflow_id: int, ran_at: datetime | None = None
    ) -> None:
        """把作业的 `next_run_time` 回写调度行（状态单一真源）；给了 `ran_at` 才记 `last_run_time`。

        作业执行时 APScheduler 已算好下一次触发时刻并写回作业对象，这里读回来落库——
        库里的 `next_run_time` 永远等于作业的，不再由业务侧自算。

        `ran_at` 刻意做成可选：启动期同步只回写下次运行时间，**不得**把启动时刻误记成
        「上次运行」（否则界面会把「服务重启过」显示成「任务刚跑过」）。
        """
        try:
            from app.core.ap_scheduler import scheduler

            job = scheduler.get_job(_job_key(workflow_id))
        except Exception as e:  # noqa: BLE001 调度器不可用不得让调用方 500，也不得把库里的值抹成空
            log.warning(f"[workflow] 读取工作流 {workflow_id} 的作业失败（调度器不可用？）：{e!s}")
            return
        next_run = getattr(job, "next_run_time", None) if job else None
        try:
            async with async_db_session.begin() as db:
                row = (
                    await db.execute(
                        select(AiWorkflowScheduleModel).where(
                            AiWorkflowScheduleModel.workflow_id == workflow_id
                        )
                    )
                ).scalar_one_or_none()
                if not row:
                    return
                if ran_at is not None:
                    row.last_run_time = ran_at
                row.next_run_time = next_run
        except Exception as e:  # noqa: BLE001 状态回写失败不影响本次运行结果
            log.warning(f"[workflow] 调度状态回写失败（workflow_id={workflow_id}）：{str(e)[:200]}")

    @staticmethod
    def _schedule_dict(row: AiWorkflowScheduleModel) -> dict:
        """调度配置响应。

        - `trigger_args` 按类型还原（interval 的 JSON 串 → 对象，供前端组件直接用）；
        - `trigger_describe` 为统一层人话描述（空/脏数据无法描述时为 `None`）；
        - `cron` 为兼容字段（前端 C 阶段切到 trigger/trigger_args 之前仍读它）。
        """
        trigger = row.trigger or "cron"
        raw_args = row.trigger_args or ""
        return {
            "trigger": trigger,
            "trigger_args": TriggerUtil.load_args(trigger, row.trigger_args),
            "trigger_describe": TriggerUtil.describe_args(trigger, raw_args),
            "cron": raw_args if trigger == "cron" else "",
            "enabled": row.enabled,
            "next_run_time": TriggerUtil.to_local_str(row.next_run_time),
            "last_run_time": TriggerUtil.to_local_str(row.last_run_time),
        }

    @classmethod
    async def get_schedule(cls, workflow_id: int) -> dict:
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiWorkflowScheduleModel).where(
                        AiWorkflowScheduleModel.workflow_id == workflow_id
                    )
                )
            ).scalar_one_or_none()
        if not row:
            return {
                "trigger": "cron",
                "trigger_args": "",
                "trigger_describe": None,
                "cron": "",
                "enabled": False,
                "next_run_time": None,
                "last_run_time": None,
            }
        return cls._schedule_dict(row)

    @classmethod
    async def run_schedule(cls, workflow_id: int) -> None:
        """按调度运行工作流（非流式，记录运行日志）。"""
        from app.plugin.module_ai.streaming import UiMessageStream

        workflow = await cls.get_workflow(workflow_id)
        if not workflow or not workflow.get("enabled"):
            return
        ms = UiMessageStream()
        state: dict = {
            "assistant_text": "",
            "reply": "",
            "tool_calls": [],
            "action": None,
            "report_id": None,
            "error": None,
            "halted": False,
            "pending_approval": None,
        }
        engine = WorkflowEngine(
            graph=workflow.get("graph") or {},
            variables={},
            messages=[],
            ms=ms,
            state=state,
            user_id=None,
            timeout_seconds=180,
        )
        log_id = await cls._start_run(workflow_id, {"scheduled": True}, None)
        try:
            async for _ in engine.run():
                pass
            state["finished"] = True
        except WorkflowCancelled:
            state["cancelled"] = True
        await cls._finish_run(
            log_id,
            cls._run_status(state),
            {"reply": state["reply"] or state["assistant_text"]},
            state["error"],
            [],
            0,
        )

    @staticmethod
    def _is_due(next_run_time, now) -> bool:
        """该调度是否到期（口径判定，供列表/排障与单测复用）。

        **未配置（`next_run_time is None`）不算到期** —— 那是「不执行」，不是「每分钟执行」：
        原先把它当到期，会让没配表达式的工作流每 60 秒跑一次。
        `next_run_time` 为 naive（SQLite）时按 `Asia/Shanghai` 解释，与统一层的口径一致。

        自建轮询已删除（到期运行归中心调度器的作业），本方法保留为**纯函数**口径：
        「空 next_run_time 不触发」这条语义仍是对外承诺（回写逻辑同样不得把空值当到期）。
        """
        if next_run_time is None:
            return False
        if next_run_time.tzinfo is None:
            next_run_time = next_run_time.replace(tzinfo=ZoneInfo(TriggerUtil.TIMEZONE))
        return next_run_time <= now

    @classmethod
    async def _enabled_schedule_rows(cls) -> list:
        """启用中的调度行（启动期同步与回写的唯一数据源）。

        工作流调度表没有软删除列：工作流被删除时其调度行一并删除，故这里只需按 `enabled` 过滤。
        """
        async with async_db_session() as db:
            result = await db.execute(
                select(AiWorkflowScheduleModel).where(AiWorkflowScheduleModel.enabled.is_(True))
            )
            return list(result.scalars().all())

    @staticmethod
    def _specs_of(rows: list) -> list[tuple]:
        """把启用行转成中心调度器的作业规格（5 元组，末项为传给作业函数的位置参数）。

        **一律排除 `now`**（`trigger == "now"`）：`now` 是「保存时的一次性事件」，
        统一层在**注册时**才把它算成 `DateTrigger(now + 2s)` —— 若启动期也重建，
        每次服务重启都会把它重新算成「重启后 2 秒」＝**每次重启都重跑一次**。
        （原先这里的 `or trigger == "now"` 例外正是这个 bug 的来源。）
        """
        return [
            (
                _job_key(row.workflow_id),
                row.trigger or "cron",
                row.trigger_args,
                run_scheduled_workflow,
                (row.workflow_id,),
            )
            for row in rows
            if row.trigger_args and (row.trigger or "cron") != "now"
        ]

    @classmethod
    async def collect_job_specs(cls) -> list[tuple]:
        """收集「启用且有触发表达式且非 `now`」的调度行规格，供启动期 `sync_business_jobs` 注册。

        每项为 5 元组 `(job_key, trigger, trigger_args, func, func_args)`。脏表达式不在
        这里过滤：`sync_business_jobs` 会逐条跳过并告警，不会因一行坏配置抹掉其余作业。
        """
        return cls._specs_of(await cls._enabled_schedule_rows())

    @classmethod
    async def start_scheduler(cls) -> None:
        """启动期把「启用中的调度行」同步进中心调度器（一次性，不再自建轮询）。

        到期运行与 `next_run_time` 都归中心调度器的作业：作业触发时运行工作流并回写
        `last_run_time` / `next_run_time`（单一真源）。本方法只做启动期注册（幂等），
        且**只清理本模块前缀**的残留作业——三个模块共用一个调度器，不得跨模块误删。
        **不重建 `now` 行**（规格口径见 `_specs_of`）：重建等于每次重启都重跑一次。
        """
        from app.core.ap_scheduler import SchedulerUtil

        try:
            rows = await cls._enabled_schedule_rows()
        except Exception as e:  # noqa: BLE001 启动期同步失败不得阻断启动
            log.warning(f"[workflow] 启动期读取定时调度失败（忽略）：{str(e)[:200]}")
            return

        try:
            # 同步范围只限本模块前缀：绝不清理工作台/训练的作业
            SchedulerUtil.sync_business_jobs(cls._specs_of(rows), prefixes=(_JOB_PREFIX,))
        except Exception as e:  # noqa: BLE001 注册失败不阻断启动
            log.warning(f"[workflow] 启动期注册定时调度失败（忽略）：{str(e)[:200]}")
        # 回写按「启用中的行」逐行进行（含 `now` 行：它没有作业，回写为 None）
        for row in rows:
            await cls.write_back_schedule_state(row.workflow_id)

    @staticmethod
    async def _persist_pending(redis, run_id: str, workflow_id: int, state: dict, uid) -> None:
        """把挂起的运行状态写入 Redis（供审批续跑读取）。"""
        if not redis:
            return
        try:
            from app.core.redis_crud import RedisCURD

            payload = {
                "workflow_id": workflow_id,
                "user_id": uid,
                "pending_approval": state.get("pending_approval"),
                "assistant_text": state.get("assistant_text") or "",
                "tool_calls": state.get("tool_calls") or [],
            }
            await RedisCURD(redis).set(f"ai:wf:approval:{run_id}", payload, expire=1800)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    async def _load_pending(redis, run_id: str) -> dict | None:
        """读取挂起状态（RedisCURD.get 返回 JSON 字节，需反序列化）。"""
        if not redis:
            return None
        try:
            from app.core.redis_crud import RedisCURD

            raw = await RedisCURD(redis).get(f"ai:wf:approval:{run_id}")
            if not raw:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            if isinstance(raw, str):
                return json.loads(raw)
            return raw
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def approve_ui_stream(
        cls, workflow_id: int, approve: AiWorkflowApproveSchema, auth, redis=None
    ) -> AsyncIterator[str]:
        """HITL 审批续跑：读取挂起状态，执行/拒绝工具并流式产出最终回复。"""
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        state: dict = {
            "assistant_text": "",
            "tool_calls": [],
            "action": None,
            "report_id": None,
            "error": None,
            "reply": "",
        }
        yield ms.start()
        try:
            payload = await cls._load_pending(redis, approve.run_id)
            if not payload:
                state["error"] = "审批会话不存在或已过期"
                yield ms.error(state["error"])
                yield ms.data("finish", {"reply": "", "tool_calls": []})
                yield ms.finish()
                yield ms.done()
                return

            workflow = await cls.get_workflow(workflow_id)
            if not workflow or not workflow.get("enabled"):
                state["error"] = "工作流不存在或未启用"
                yield ms.error(state["error"])
                yield ms.data("finish", {"reply": "", "tool_calls": []})
                yield ms.finish()
                yield ms.done()
                return

            paused = payload.get("pending_approval") or {}
            graph = workflow.get("graph") or {}
            engine = WorkflowEngine(
                graph=graph,
                variables={},
                messages=[],
                ms=ms,
                state=state,
                user_id=payload.get("user_id"),
                run_id=paused.get("session_id") or paused.get("run_id"),
            )
            # 恢复挂起状态供 resume_after_approval 读取 llm_messages/content
            engine.state["pending_approval"] = paused
            engine.state["assistant_text"] = payload.get("assistant_text") or ""
            node_id = paused.get("node_id")
            tool_calls = [
                {
                    "toolCallId": t["toolCallId"],
                    "toolName": t["toolName"],
                    "arguments": t.get("arguments"),
                }
                for t in (paused.get("pending") or [])
            ]
            async for frame in engine.resume_after_approval(
                node_id, tool_calls, approve.decision
            ):
                yield frame
            if redis and approve.run_id:
                from app.core.redis_crud import RedisCURD

                await RedisCURD(redis).delete(f"ai:wf:approval:{approve.run_id}")
            yield ms.data(
                "finish",
                {
                    "reply": state.get("reply") or state.get("assistant_text"),
                    "tool_calls": state["tool_calls"],
                    "action": state["action"],
                    "report_id": state["report_id"],
                },
            )
            yield ms.finish()
            yield ms.done()
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)
            yield ms.error(f"审批续跑失败：{e}")
            yield ms.data("finish", {"reply": state.get("assistant_text"), "tool_calls": []})
            yield ms.finish()
            yield ms.done()


def runtime_model_name(workflow_id: int) -> str:
    """调用日志里标识工作流（不解析模型，避免加重运行路径）。"""
    return f"workflow:{workflow_id}"
