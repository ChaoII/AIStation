"""工作流服务：CRUD 与流式运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.logger import log

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
#: 取消看门狗轮询间隔（秒）：取消信号查得勤（做到「秒停」），断开每 5 次查一次
_WATCH_INTERVAL = 0.2


def _to_dict(w: AiWorkflowModel) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description or "",
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
        is_disconnected=None,
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

                # 取消看门狗（取消信号 + 客户端断开）：
                # - 取消信号每 0.2s 查一次（内存+Redis，多 worker 也能收到），
                # - 断开每 1s 查一次（BaseHTTPMiddleware 不会把 http.disconnect 透传给
                #   下游，SSE 生成器收不到断开 → 关页面后运行会白跑到底，实测断开 12s
                #   后记录仍是 running）。
                # 命中任一条件即直接 cancel 引擎任务，做到「秒停」。
                async def _watch_cancel() -> None:
                    tick = 0
                    while not engine_task.done():
                        await asyncio.sleep(_WATCH_INTERVAL)
                        tick += 1
                        try:
                            if engine.cancel_key and await is_cancelled(
                                engine.cancel_key, redis
                            ):
                                engine_task.cancel()
                                return
                            if is_disconnected is not None and tick % 5 == 0:
                                if await is_disconnected():
                                    if log_id:
                                        await request_cancel(log_id, redis)
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
                    for t in trace:
                        if t.get("status") == "running":
                            yield ms.node_status(
                                t.get("nodeId"), "cancelled", t.get("label") or t.get("nodeId")
                            )
                            t["status"] = "cancelled"
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

        from .cancel import request_cancel

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
    async def set_schedule(cls, workflow_id: int, cron: str | None, enabled: bool) -> dict:
        """保存调度配置并计算下次运行时间。"""
        from datetime import datetime

        from apscheduler.triggers.cron import CronTrigger

        next_run = None
        if enabled and cron:
            try:
                CronTrigger.from_crontab(cron)
                next_run = CronTrigger.from_crontab(cron).get_next_fire_time(None, datetime.now())
            except Exception:  # noqa: BLE001
                raise RuntimeError("cron 表达式无效")
        async with async_db_session() as db:
            row = (
                await db.execute(
                    select(AiWorkflowScheduleModel).where(
                        AiWorkflowScheduleModel.workflow_id == workflow_id
                    )
                )
            ).scalar_one_or_none()
            if not row:
                row = AiWorkflowScheduleModel(workflow_id=workflow_id)
                db.add(row)
            row.cron = cron or ""
            row.enabled = enabled
            row.next_run_time = next_run
            await db.commit()
            await db.refresh(row)
        return {"cron": row.cron, "enabled": row.enabled, "next_run_time": row.next_run_time}

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
            return {"cron": "", "enabled": False, "next_run_time": None}
        return {
            "cron": row.cron or "",
            "enabled": row.enabled,
            "next_run_time": row.next_run_time,
            "last_run_time": row.last_run_time,
        }

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

    @classmethod
    async def start_scheduler(cls) -> None:
        """后台轮询任务：每分钟检查到期调度并运行。"""
        import asyncio
        from datetime import datetime

        while True:
            try:
                now = datetime.now()
                async with async_db_session() as db:
                    rows = (
                        await db.execute(
                            select(AiWorkflowScheduleModel).where(
                                AiWorkflowScheduleModel.enabled.is_(True)
                            )
                        )
                    ).scalars().all()
                for row in rows:
                    due = row.next_run_time is None or (
                        row.next_run_time and row.next_run_time <= now
                    )
                    if due:
                        try:
                            await cls.run_schedule(row.workflow_id)
                        except Exception:  # noqa: BLE001
                            pass
                        next_run = None
                        if row.cron:
                            try:
                                from apscheduler.triggers.cron import CronTrigger

                                next_run = CronTrigger.from_crontab(row.cron).get_next_fire_time(
                                    None, datetime.now()
                                )
                            except Exception:  # noqa: BLE001
                                next_run = None
                        async with async_db_session() as db2:
                            r = await db2.get(AiWorkflowScheduleModel, row.id)
                            if r:
                                r.last_run_time = now
                                r.next_run_time = next_run
                                await db2.commit()
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(60)

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
