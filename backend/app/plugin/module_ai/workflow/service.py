"""工作流服务：CRUD 与流式运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import func, select

from app.core.database import async_db_session

from .engine import WorkflowEngine
from .model import AiWorkflowModel, AiWorkflowRunLogModel, AiWorkflowVersionModel
from .schema import AiWorkflowApproveSchema


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
        empty_finish = {"reply": "", "tool_calls": [], "action": None, "report_id": None}
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
                yield ms.data("finish", empty_finish)
                yield ms.finish()
                yield ms.done()
                return

            graph = workflow.get("graph") or {}
            openai_messages = extract_openai_messages(ui_messages)
            engine = WorkflowEngine(
                graph=graph,
                variables=variables or {},
                messages=openai_messages,
                ms=ms,
                state=state,
                user_id=uid,
            )
            async for frame in engine.run():
                yield frame
                if '"type": "node-status"' in frame:
                    try:
                        trace.append(json.loads(frame[len("data: ") :].strip()))
                    except Exception:  # noqa: BLE001
                        pass

            if state.get("halted") and state.get("pending_approval"):
                # HITL：持久化运行状态，产出审批装载帧供前端确认后调 approve 续跑
                run_id = uuid.uuid4().hex
                await cls._persist_pending(redis, run_id, workflow_id, state, uid)
                yield ms.data(
                    "finish",
                    {
                        "reply": state.get("assistant_text") or "",
                        "tool_calls": state["tool_calls"],
                        "action": state["action"],
                        "report_id": state["report_id"],
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
                    },
                )
                yield ms.finish()
                yield ms.done()
                return

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
            state["error"] = str(e)
            yield ms.error(f"运行失败：{e}")
            yield ms.data(
                "finish",
                {
                    "reply": state["assistant_text"],
                    "tool_calls": state["tool_calls"],
                    "action": state["action"],
                    "report_id": state["report_id"],
                },
            )
            yield ms.finish()
            yield ms.done()
        finally:
            await AiOverviewService.add_log(
                runtime_model_name(workflow_id),
                "workflow",
                int((time.perf_counter() - t0) * 1000),
                "success" if state["error"] is None and not state.get("halted") else "pending",
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
            await cls._log_run(
                workflow_id,
                "success" if state["error"] is None and not state.get("halted") else ("pending" if state.get("halted") else "error"),
                {"messages": ui_messages, "variables": variables or {}, "user_text": user_text},
                {"reply": state["reply"] or state["assistant_text"], "tool_calls": state["tool_calls"]},
                state["error"],
                trace,
                int((time.perf_counter() - t0) * 1000),
                uid,
            )

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
    async def _log_run(
        cls,
        workflow_id: int,
        status: str,
        run_input: dict,
        run_output: dict,
        error: str | None,
        node_trace: list,
        duration_ms: int,
        uid: int | None,
    ) -> None:
        """持久化一次工作流运行的输入/输出/报错/节点轨迹。"""
        try:
            async with async_db_session() as db:
                db.add(
                    AiWorkflowRunLogModel(
                        workflow_id=workflow_id,
                        status=status,
                        run_input=run_input,
                        run_output=run_output,
                        error=(error or "")[:1024] or None,
                        node_trace=node_trace,
                        duration_ms=duration_ms,
                        created_id=uid,
                    )
                )
                await db.commit()
        except Exception:  # noqa: BLE001 运行历史记录失败不影响主流程
            pass

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
            openai_messages = (paused.get("llm_messages") or [])[:]
            engine = WorkflowEngine(
                graph=graph,
                variables={},
                messages=openai_messages,
                ms=ms,
                state=state,
                user_id=payload.get("user_id"),
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
