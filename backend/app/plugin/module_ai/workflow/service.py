"""工作流服务：CRUD 与流式运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from sqlalchemy import select

from app.core.database import async_db_session

from .engine import WorkflowEngine
from .model import AiWorkflowModel


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

    @classmethod
    async def run_ui_stream(
        cls,
        workflow_id: int,
        ui_messages: list[dict],
        auth,
        variables: dict | None = None,
        session_id: int | None = None,
    ) -> AsyncIterator[str]:
        """运行工作流：实例化引擎并流式产出 UI Message Stream 帧。"""
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
                "success" if state["error"] is None else "error",
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


def runtime_model_name(workflow_id: int) -> str:
    """调用日志里标识工作流（不解析模型，避免加重运行路径）。"""
    return f"workflow:{workflow_id}"
