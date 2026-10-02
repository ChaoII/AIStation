"""工作流服务：CRUD 与流式运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import func, select

from app.core.database import async_db_session

from .engine import WorkflowEngine
from .model import AiWorkflowModel, AiWorkflowVersionModel
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
