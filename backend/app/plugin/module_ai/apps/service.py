"""AI 应用服务：CRUD 与运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from sqlalchemy import func, select

from app.core.database import async_db_session

from .model import AiAppModel


def _to_dict(a: AiAppModel) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "icon": a.icon or "",
        "category_id": a.category_id,
        "description": a.description,
        "model_id": a.model_id,
        "prompt_id": a.prompt_id,
        "tools": a.tools or [],
        "output_format": a.output_format or "text",
        "input_schema": a.input_schema,
        "enabled": a.enabled,
        "order": a.order or 0,
        "app_type": a.app_type or "chat",
        "kb_id": a.kb_id,
        "workflow_id": a.workflow_id,
        "temperature": a.temperature,
        "max_tokens": a.max_tokens,
        "context_window": a.context_window,
        "system_prompt": a.system_prompt,
        "tags": a.tags or [],
        "memory": a.memory if a.memory is not None else True,
        "timeout": a.timeout or 60,
        "created_time": a.created_time,
        "updated_time": a.updated_time,
    }


async def _ensure_app_columns() -> None:
    """确保组件类型/绑定列存在（幂等，兼容旧表）。"""
    from sqlalchemy import text as _text

    from app.core.database import async_db_session as _db

    try:
        async with _db.begin() as db:
            for col, ddl in (
                ("app_type", "VARCHAR(16) DEFAULT 'chat'"),
                ("kb_id", "INTEGER"),
                ("workflow_id", "INTEGER"),
                ("temperature", "FLOAT"),
                ("max_tokens", "INTEGER"),
                ("context_window", "INTEGER"),
                ("system_prompt", "TEXT"),
                ("tags", "JSONB"),
                ("memory", "BOOLEAN DEFAULT true"),
                ("timeout", "INTEGER DEFAULT 60"),
            ):
                await db.execute(
                    _text(f"ALTER TABLE ai_apps ADD COLUMN IF NOT EXISTS {col} {ddl}")
                )
    except Exception:  # noqa: BLE001
        pass


class AiAppService:

    @classmethod
    async def count_apps(cls) -> int:
        """未删除的应用数量（控制台/看板跨模块取数入口，不暴露模型）。"""
        async with async_db_session() as db:
            return int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(AiAppModel)
                        .where(AiAppModel.is_deleted.is_(False))
                    )
                ).scalar()
                or 0
            )

    @classmethod
    async def list_apps(cls) -> list[dict]:
        await _ensure_app_columns()
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiAppModel)
                    .where(AiAppModel.is_deleted.is_(False))
                    .order_by(AiAppModel.order.asc(), AiAppModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(a) for a in rows]

    @classmethod
    async def get_app(cls, app_id: int) -> dict | None:
        async with async_db_session() as db:
            a = await db.get(AiAppModel, app_id)
            if not a or a.is_deleted:
                return None
            return _to_dict(a)

    # AIP 应用/工作流市场模板
    _TEMPLATES = [
        {"key": "data_query", "name": "问数助手", "app_type": "chat",
         "description": "自然语言问数（本体驱动）",
         "system_prompt": "你是数据问数助手，基于系统数据回答问题。", "tools": ["ai_query"]},
        {"key": "knowledge", "name": "知识问答", "app_type": "chat",
         "description": "基于知识库回答（RAG）",
         "system_prompt": "你是知识库问答助手，优先引用知识库内容。", "tools": []},
        {"key": "report", "name": "报告生成", "app_type": "report",
         "description": "AI 自动生成结构化报告",
         "system_prompt": "你是报告生成助手，输出结构化分析报告。", "tools": ["ai_query", "report_generate"]},
        {"key": "workflow", "name": "流程助手", "app_type": "workflow",
         "description": "工作流编排驱动（多步骤）", "system_prompt": "", "tools": []},
    ]

    @classmethod
    async def app_templates(cls) -> list[dict]:
        return [dict(t) for t in cls._TEMPLATES]

    @classmethod
    async def create_from_template(cls, key: str, name: str, auth) -> dict | None:
        tpl = next((t for t in cls._TEMPLATES if t["key"] == key), None)
        if not tpl:
            return None
        from types import SimpleNamespace as SN
        data = SN(name=name or tpl["name"], icon="", description=tpl.get("description") or "",
                  model_id=None, prompt_id=None, tools=tpl.get("tools") or [],
                  output_format="text", input_schema={}, enabled=True, order=0,
                  app_type=tpl.get("app_type") or "chat", kb_id=None, workflow_id=None,
                  temperature=0.3, max_tokens=None, context_window=None,
                  system_prompt=tpl.get("system_prompt") or "", tags=[], memory=True, timeout=60)
        return await cls.create(data, auth)

    @classmethod
    async def create(cls, data, auth) -> dict:
        await _ensure_app_columns()
        async with async_db_session.begin() as db:
            a = AiAppModel(
                name=data.name,
                icon=data.icon or "",
                description=data.description,
                model_id=data.model_id,
                prompt_id=data.prompt_id,
                tools=data.tools or [],
                output_format=data.output_format or "text",
                input_schema=data.input_schema,
                enabled=data.enabled,
                order=data.order or 0,
                app_type=data.app_type or "chat",
                kb_id=getattr(data, "kb_id", None),
                workflow_id=getattr(data, "workflow_id", None),
                temperature=getattr(data, "temperature", None),
                max_tokens=getattr(data, "max_tokens", None),
                context_window=getattr(data, "context_window", None),
                system_prompt=getattr(data, "system_prompt", None),
                tags=getattr(data, "tags", None) or [],
                memory=getattr(data, "memory", True),
                timeout=getattr(data, "timeout", 60) or 60,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(a)
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def update(cls, app_id: int, data, auth) -> dict | None:
        await _ensure_app_columns()
        async with async_db_session.begin() as db:
            a = await db.get(AiAppModel, app_id)
            if not a or a.is_deleted:
                return None
            provided = getattr(data, "model_fields_set", set())
            nullable = {"description", "model_id", "prompt_id", "input_schema", "kb_id", "workflow_id", "temperature", "max_tokens", "context_window", "system_prompt"}
            for key in (
                "name",
                "icon",
                "description",
                "model_id",
                "prompt_id",
                "tools",
                "output_format",
                "input_schema",
                "enabled",
                "order",
                "app_type",
                "kb_id",
                "workflow_id",
                "temperature",
                "max_tokens",
                "context_window",
                "system_prompt",
                "tags",
                "memory",
                "timeout",
            ):
                if key not in provided:
                    continue
                val = getattr(data, key)
                if val is None and key not in nullable:
                    continue
                setattr(a, key, val)
            a.updated_id = auth.user.id
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for app_id in ids:
                a = await db.get(AiAppModel, app_id)
                if a:
                    await db.delete(a)

    @classmethod
    async def batch_status(cls, ids: list[int], enabled: bool, auth) -> int:
        """批量启用/停用组件。"""
        async with async_db_session.begin() as db:
            count = 0
            for app_id in ids:
                a = await db.get(AiAppModel, app_id)
                if a and not a.is_deleted:
                    a.enabled = enabled
                    a.updated_id = getattr(getattr(auth, "user", None), "id", None)
                    count += 1
            return count


async def _build_app_tools(names: list[str] | None):
    """按应用绑定工具名解析 schema 与执行器：内置/Agno/HTTP 均须 ai_tools 行存在且启用。"""
    from app.plugin.module_ai.agno_tools import service as agno
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY
    from app.plugin.module_ai.tools_catalog.service import (
        _source_of_row,
        build_http_tool_schema,
        get_tool_by_name,
    )

    # 预取绑定工具行，先收集 HTTP 名称用于 Agno 生成名去重
    rows: dict[str, object] = {}
    for name in names or []:
        tool = await get_tool_by_name(name)
        if tool is not None:
            rows[name] = tool
    used: set[str] = set(TOOL_REGISTRY.keys())
    used.update(n for n, t in rows.items() if _source_of_row(t) == "http")

    schemas: list[dict] = []
    http_tools: dict[str, object] = {}
    for name in names or []:
        tool = rows.get(name)
        entry = TOOL_REGISTRY.get(name)
        if entry:
            # 内置工具须存在 ai_tools 行且全局启用，否则跳过（与 HTTP 工具一致）
            if tool is None or not tool.enabled:
                continue
            schemas.append(entry["schema"])
            continue
        if tool is None or not tool.enabled:
            continue
        source = _source_of_row(tool)
        if source == "agno":
            spec = agno.get_spec(tool.name)
            # 显式按 readiness 过滤：缺依赖或缺必填配置的工具不下发 schema
            if spec and agno.readiness(spec, tool.config)[0]:
                schemas.extend(agno.build_openai_schemas(spec, tool.config, used))
            continue
        if source == "http":
            schemas.append(build_http_tool_schema(tool))
            http_tools[name] = tool
        if source == "script":
            schemas.append(build_http_tool_schema(tool))
    return schemas, http_tools


async def _run_app_tool(name: str, args: dict, user_id: int | None, http_tools: dict) -> object:
    """派发应用工具：统一走工具分派器（Agno/内置/HTTP 按来源路由）。"""
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    return await dispatch_tool(name, args, user_id, db_rows=http_tools or None)


def _merge_variables(input_schema: object, variables: dict | None) -> dict:
    """合并 input_schema 默认值与调用方变量：显式变量优先，兼容两种 schema 形状。

    - JSON Schema 形状：``{"type": "object", "properties": {"x": {"default": 1}}}``
    - 扁平字典形状：``{"x": 1}``（含 ``type`` 键时按 JSON Schema 处理，不取默认值）
    非法/意外形状直接返回原变量，不报错。
    """
    values = dict(variables or {})
    if not isinstance(input_schema, dict):
        return values
    if "properties" in input_schema:
        properties = input_schema.get("properties")
        if not isinstance(properties, dict):
            return values
        for key, spec in properties.items():
            if key in values:
                continue
            if isinstance(spec, dict) and "default" in spec:
                values[key] = spec["default"]
        return values
    if "type" in input_schema:
        # 无 properties 的 JSON Schema：无默认值可合并
        return values
    for key, default in input_schema.items():
        if key not in values:
            values[key] = default
    return values


async def run_app_ui_stream(
    app_id: int,
    ui_messages: list[dict],
    auth,
    variables: dict | None = None,
    session_id: int | None = None,
) -> AsyncIterator[str]:
    """运行 AI 应用：解析应用/模型/提示词/工具，流式产出 Agno 原生事件帧。"""

    from app.plugin.module_ai.assistant.agno_service import (
        agno_error_frame,
        agno_event_frame,
        ui_stream_to_agno,
    )
    from app.plugin.module_ai.assistant.service import (
        SYSTEM_PROMPT,
        last_user_text,
    )
    from app.plugin.module_ai.models.service import AiModelService
    from app.plugin.module_ai.overview.service import AiOverviewService
    from app.plugin.module_ai.prompts.service import AiPromptService, render_prompt
    from app.plugin.module_ai.sessions.service import persist_session_exchange

    t0 = time.perf_counter()
    uid = getattr(getattr(auth, "user", None), "id", None)
    user_text = last_user_text(ui_messages)
    model_name = "app"
    # 委托工作流时会话已由引擎落库：finally 跳过，防重复 user 消息
    delegated = False
    state: dict = {
        "assistant_text": "",
        "reply": "",
        "tool_calls": [],
        "action": None,
        "report_id": None,
        "error": None,
    }
    try:
        app = await AiAppService.get_app(app_id)
        if not app or not app.get("enabled"):
            state["error"] = "应用不存在或未启用"
            yield agno_error_frame(state["error"])
            return

        # 统一组件：按类型分发运行
        app_type = app.get("app_type") or "chat"
        if app_type == "workflow" and app.get("workflow_id"):
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            delegated = True
            # 工作流引擎产 UI Message Stream 帧（编排语义），转译为本端点契约的 Agno 帧
            async for frame in ui_stream_to_agno(
                AiWorkflowService.run_ui_stream(
                    app["workflow_id"], ui_messages, auth, variables, session_id
                )
            ):
                yield frame
            return
        if app_type == "kb" and app.get("kb_id"):
            from app.plugin.module_ai.knowledge.service import AiKnowledgeService

            try:
                q = last_user_text(ui_messages)
                result = await AiKnowledgeService.ask(
                    app["kb_id"], q, top_k=6, auth=auth
                )
                ans = result.get("answer") or ""
                refs = result.get("references") or []
                state["assistant_text"] = ans
                state["reply"] = ans
                if ans:
                    yield agno_event_frame("RunContent", {"content": ans})
                if refs:
                    # 引用来源以「references」工具对呈现（前端按 ToolCall* 渲染工具卡）
                    yield agno_event_frame(
                        "ToolCallStarted",
                        {"tool": {"tool_name": "references", "tool_call_id": "refs-1", "tool_args": {}}},
                    )
                    yield agno_event_frame(
                        "ToolCallCompleted",
                        {"tool": {"tool_name": "references", "tool_call_id": "refs-1", "result": refs}},
                    )
                yield agno_event_frame("RunCompleted")
            except Exception as e:  # noqa: BLE001
                state["error"] = str(e)
                yield agno_error_frame(f"运行失败：{e}")
            return

        # 系统提示词：优先渲染绑定提示词，缺失时回退助手默认
        system_prompt = SYSTEM_PROMPT
        if app.get("prompt_id"):
            prompt = await AiPromptService.get_prompt(app["prompt_id"])
            if prompt:
                # 提示词变量 = 调用方显式变量 + input_schema 默认值（显式优先）
                values = _merge_variables(app.get("input_schema"), variables)
                rendered = render_prompt(prompt.get("blocks"), values)
                if rendered:
                    system_prompt = rendered
        if app.get("output_format") == "report":
            system_prompt += "\n\n请以 Markdown 报告形式组织最终输出。"

        # 运行时模型：优先应用绑定模型，否则默认
        runtime = None
        if app.get("model_id"):
            runtime = await AiModelService.get_runtime_model(model_id=app["model_id"])
        if not runtime:
            runtime = await AiModelService.get_runtime_model()
        if not runtime:
            state["error"] = "未配置大模型，请在 AI 管理→模型配置 中添加并启用"
            yield agno_error_frame(state["error"])
            return
        model_name = runtime.get("model") or "app"

        tool_schemas, http_tools = await _build_app_tools(app.get("tools"))

        async def _dispatch(name: str, args: dict, user_id: int | None):
            return await _run_app_tool(name, args, user_id, http_tools)

        from app.plugin.module_ai.assistant.agno_service import run_agno_tool_stream

        async for frame in run_agno_tool_stream(
            model_config=runtime,
            system_prompt=system_prompt,
            tool_schemas=tool_schemas,
            dispatch=_dispatch,
            user_text=user_text,
            user_id=uid,
            session_id=session_id,
            name="aistation_app",
            description=f"AIStation 应用：{app.get('name') or '应用'}",
            state=state,
        ):
            yield frame
    except Exception as e:  # noqa: BLE001
        state["error"] = str(e)
        yield agno_error_frame(f"运行失败：{e}")
    finally:
        u = state.get("usage") or {}
        await AiOverviewService.add_log(
            model_name,
            "app",
            int((time.perf_counter() - t0) * 1000),
            "success" if state["error"] is None else "error",
            state["error"],
            app_id=app_id,
            user_id=uid,
            prompt_tokens=u.get("prompt_tokens", 0),
            completion_tokens=u.get("completion_tokens", 0),
        )
        # 委托工作流时会话已由引擎落库：跳过，防重复 user 消息
        if not delegated:
            await persist_session_exchange(
                session_id, user_text, state["assistant_text"], app_id=app_id, user_id=uid
            )
