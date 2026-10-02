"""智能体服务：CRUD、分类与运行（绑定工作流或回退模型+提示词+工具）。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from sqlalchemy import select

from app.core.database import async_db_session

from .model import AiAgentCategoryModel, AiAgentModel


def _to_dict(a: AiAgentModel) -> dict:
    return {
        "id": a.id,
        "agent_name": a.agent_name,
        "category_id": a.category_id,
        "agent_role": a.agent_role or "",
        "description": a.description or "",
        "model_id": a.model_id,
        "prompt_id": a.prompt_id,
        "temperature": a.temperature,
        "workflow_id": a.workflow_id,
        "tool_ids": a.tool_ids or [],
        "knowledge_ids": a.knowledge_ids or [],
        "input_schema": a.input_schema,
        "avatar": a.avatar or "",
        "color": a.color or "",
        "markdown": a.markdown,
        "enabled": a.enabled,
        "order": a.order or 0,
        "uuid": a.uuid,
        "created_time": a.created_time,
        "updated_time": a.updated_time,
    }


def _cat_dict(c: AiAgentCategoryModel) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "parent_id": c.parent_id,
        "sort": c.sort or 0,
    }


class AiAgentService:

    # ---------------------------------------------------------------- #
    # 分类
    # ---------------------------------------------------------------- #
    @classmethod
    async def list_categories(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiAgentCategoryModel)
                    .where(AiAgentCategoryModel.is_deleted.is_(False))
                    .order_by(AiAgentCategoryModel.sort.asc(), AiAgentCategoryModel.id.asc())
                )
            ).scalars().all()
            return [_cat_dict(c) for c in rows]

    @classmethod
    async def create_category(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            c = AiAgentCategoryModel(
                name=data.name,
                parent_id=data.parent_id,
                sort=data.sort or 0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(c)
            await db.flush()
            return _cat_dict(c)

    @classmethod
    async def update_category(cls, cat_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            c = await db.get(AiAgentCategoryModel, cat_id)
            if not c or c.is_deleted:
                return None
            for key in ("name", "parent_id", "sort"):
                if getattr(data, key) is not None:
                    setattr(c, key, getattr(data, key))
            c.updated_id = auth.user.id
            await db.flush()
            return _cat_dict(c)

    @classmethod
    async def delete_category(cls, cat_id: int) -> None:
        async with async_db_session.begin() as db:
            c = await db.get(AiAgentCategoryModel, cat_id)
            if c:
                await db.delete(c)

    # ---------------------------------------------------------------- #
    # 智能体
    # ---------------------------------------------------------------- #
    @classmethod
    async def list_agents(cls, category_id: int | None = None) -> list[dict]:
        async with async_db_session() as db:
            stmt = select(AiAgentModel).where(AiAgentModel.is_deleted.is_(False))
            if category_id is not None:
                stmt = stmt.where(AiAgentModel.category_id == category_id)
            rows = (
                await db.execute(
                    stmt.order_by(AiAgentModel.order.asc(), AiAgentModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(a) for a in rows]

    @classmethod
    async def get_agent(cls, agent_id: int) -> dict | None:
        async with async_db_session() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a or a.is_deleted:
                return None
            return _to_dict(a)

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            a = AiAgentModel(
                agent_name=data.agent_name,
                category_id=data.category_id,
                agent_role=data.agent_role or "",
                description=getattr(data, "description", None),
                model_id=data.model_id,
                prompt_id=data.prompt_id,
                temperature=data.temperature,
                workflow_id=data.workflow_id,
                tool_ids=data.tool_ids or [],
                knowledge_ids=data.knowledge_ids or [],
                input_schema=data.input_schema,
                avatar=data.avatar or "",
                color=data.color or "",
                markdown=data.markdown,
                enabled=data.enabled,
                order=data.order or 0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(a)
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def update(cls, agent_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a or a.is_deleted:
                return None
            for key in (
                "agent_name", "category_id", "agent_role", "description", "model_id",
                "prompt_id", "temperature", "workflow_id", "tool_ids", "knowledge_ids",
                "input_schema", "avatar", "color", "markdown", "enabled", "order",
            ):
                if getattr(data, key) is not None:
                    setattr(a, key, getattr(data, key))
            a.updated_id = auth.user.id
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for aid in ids:
                a = await db.get(AiAgentModel, aid)
                if a:
                    await db.delete(a)

    @classmethod
    async def run_ui_stream(
        cls,
        agent_id: int,
        ui_messages: list[dict],
        auth,
        variables: dict | None = None,
        session_id: int | None = None,
    ) -> AsyncIterator[str]:
        """运行智能体：绑定工作流则走编排引擎，否则回退模型+提示词+工具。"""
        agent = await cls.get_agent(agent_id)
        if not agent or not agent.get("enabled"):
            # 没有 agent 也要产出终止帧，保持协议一致
            from app.plugin.module_ai.streaming import UiMessageStream

            ms = UiMessageStream()
            empty_finish = {"reply": "", "tool_calls": [], "action": None, "report_id": None}
            yield ms.start()
            yield ms.error("智能体不存在或未启用")
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
            return

        if agent.get("workflow_id"):
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            async for frame in AiWorkflowService.run_ui_stream(
                agent["workflow_id"], ui_messages, auth, variables, session_id
            ):
                yield frame
            return

        # 回退：复用应用运行逻辑（模型+提示词+工具）
        from openai import AsyncOpenAI

        from app.plugin.module_ai.apps.service import _build_app_tools, _merge_variables
        from app.plugin.module_ai.assistant.service import (
            SYSTEM_PROMPT,
            extract_openai_messages,
            last_user_text,
            run_agent_ui_stream,
        )
        from app.plugin.module_ai.overview.service import AiOverviewService
        from app.plugin.module_ai.prompts.service import AiPromptService, render_prompt
        from app.plugin.module_ai.provider.service import AiModelService, build_headers
        from app.plugin.module_ai.sessions.service import persist_session_exchange
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        t0 = time.perf_counter()
        uid = getattr(getattr(auth, "user", None), "id", None)
        user_text = last_user_text(ui_messages)
        empty_finish = {"reply": "", "tool_calls": [], "action": None, "report_id": None}
        state: dict = {
            "assistant_text": "", "reply": "", "tool_calls": [],
            "action": None, "report_id": None, "error": None,
        }
        yield ms.start()
        try:
            system_prompt = SYSTEM_PROMPT
            if agent.get("prompt_id"):
                prompt = await AiPromptService.get_prompt(agent["prompt_id"])
                if prompt:
                    values = _merge_variables(agent.get("input_schema"), variables)
                    rendered = render_prompt(prompt.get("blocks"), values)
                    if rendered:
                        system_prompt = rendered

            runtime = None
            if agent.get("model_id"):
                runtime = await AiModelService.get_runtime_model(model_id=agent["model_id"])
            if not runtime:
                runtime = await AiModelService.get_runtime_model()
            if not runtime:
                state["error"] = "未配置大模型，请在 AI 管理→模型配置 中添加并启用"
                yield ms.error(state["error"])
                yield ms.data("finish", empty_finish)
                yield ms.finish()
                yield ms.done()
                return

            tool_schemas, http_tools = await _build_app_tools(agent.get("tool_ids"))
            client = AsyncOpenAI(
                base_url=runtime["base_url"],
                api_key=runtime["api_key"] or "sk-none",
                default_headers=build_headers(
                    runtime["base_url"], runtime.get("extra_headers"), "aistation-agent"
                ),
            )
            messages: list[dict] = [{"role": "system", "content": system_prompt}]
            messages += extract_openai_messages(ui_messages)

            async def _dispatch(name: str, args: dict, user_id: int | None):
                from app.plugin.module_ai.apps.service import _run_app_tool

                return await _run_app_tool(name, args, user_id, http_tools)

            async for frame in run_agent_ui_stream(
                client=client,
                runtime=runtime,
                messages=messages,
                tool_schemas=tool_schemas,
                dispatch=_dispatch,
                ms=ms,
                user_id=uid,
                state=state,
            ):
                yield frame
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)
            yield ms.error(f"运行失败：{e}")
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
        finally:
            await AiOverviewService.add_log(
                agent.get("agent_name", ""),
                "agent",
                int((time.perf_counter() - t0) * 1000),
                "success" if state["error"] is None else "error",
                state["error"],
                app_id=agent_id,
                user_id=uid,
            )
            await persist_session_exchange(
                session_id, user_text, state["assistant_text"],
                app_id=agent_id, user_id=uid,
            )
