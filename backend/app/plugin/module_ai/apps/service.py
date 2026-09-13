"""AI 应用服务：CRUD 与运行（AI SDK UI Message Stream）。"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from sqlalchemy import select

from app.core.database import async_db_session

from .model import AiAppModel


def _to_dict(a: AiAppModel) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "icon": a.icon or "",
        "description": a.description,
        "model_id": a.model_id,
        "prompt_id": a.prompt_id,
        "tools": a.tools or [],
        "output_format": a.output_format or "text",
        "input_schema": a.input_schema,
        "enabled": a.enabled,
        "order": a.order or 0,
        "created_time": a.created_time,
        "updated_time": a.updated_time,
    }


class AiAppService:

    @classmethod
    async def list_apps(cls) -> list[dict]:
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

    @classmethod
    async def create(cls, data, auth) -> dict:
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
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(a)
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def update(cls, app_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            a = await db.get(AiAppModel, app_id)
            if not a or a.is_deleted:
                return None
            provided = getattr(data, "model_fields_set", set())
            nullable = {"description", "model_id", "prompt_id", "input_schema"}
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


async def _build_app_tools(names: list[str] | None):
    """按应用绑定工具名解析 schema 与执行器：内置取注册表，HTTP 取启用行。"""
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY
    from app.plugin.module_ai.tools_catalog.service import (
        build_http_tool_schema,
        get_tool_by_name,
    )

    schemas: list[dict] = []
    http_tools: dict[str, object] = {}
    for name in names or []:
        entry = TOOL_REGISTRY.get(name)
        if entry:
            schemas.append(entry["schema"])
            continue
        tool = await get_tool_by_name(name)
        if tool is None or not tool.enabled or (tool.kind or "builtin") != "http":
            continue
        schemas.append(build_http_tool_schema(tool))
        http_tools[name] = tool
    return schemas, http_tools


async def _run_app_tool(name: str, args: dict, user_id: int | None, http_tools: dict) -> object:
    """派发应用工具：HTTP 工具走 execute_http_tool，其余走内置注册表。"""
    from app.plugin.module_ai.assistant.service import _call_tool
    from app.plugin.module_ai.tools_catalog.service import execute_http_tool

    tool = http_tools.get(name)
    if tool is not None:
        return await execute_http_tool(tool, args)
    return await _call_tool(name, args, user_id)


async def run_app_ui_stream(
    app_id: int,
    ui_messages: list[dict],
    auth,
    variables: dict | None = None,
) -> AsyncIterator[str]:
    """运行 AI 应用：解析应用/模型/提示词/工具，流式产出 UI Message Stream 帧。"""
    from openai import AsyncOpenAI

    from app.plugin.module_ai.assistant.service import (
        MAX_ROUNDS,
        SYSTEM_PROMPT,
        extract_openai_messages,
    )
    from app.plugin.module_ai.overview.service import AiOverviewService
    from app.plugin.module_ai.prompts.service import AiPromptService, render_prompt
    from app.plugin.module_ai.provider.service import AiModelService, build_headers
    from app.plugin.module_ai.streaming import UiMessageStream

    ms = UiMessageStream()
    t0 = time.perf_counter()
    uid = getattr(getattr(auth, "user", None), "id", None)
    model_name = "app"
    ok, err = True, None
    empty_finish = {"reply": "", "tool_calls": [], "action": None, "report_id": None}
    yield ms.start()
    try:
        app = await AiAppService.get_app(app_id)
        if not app or not app.get("enabled"):
            ok, err = False, "应用不存在或未启用"
            yield ms.error(err)
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
            return

        # 系统提示词：优先渲染绑定提示词，缺失时回退助手默认
        system_prompt = SYSTEM_PROMPT
        if app.get("prompt_id"):
            prompt = await AiPromptService.get_prompt(app["prompt_id"])
            if prompt:
                rendered = render_prompt(prompt.get("blocks"), variables or {})
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
            ok, err = False, "未配置大模型，请在 AI 管理→模型配置 中添加并启用"
            yield ms.error(err)
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
            return
        model_name = runtime.get("model") or "app"

        tool_schemas, http_tools = await _build_app_tools(app.get("tools"))
        client = AsyncOpenAI(
            base_url=runtime["base_url"],
            api_key=runtime["api_key"] or "sk-none",
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-app"
            ),
        )
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages += extract_openai_messages(ui_messages)
        tool_log: list[dict] = []
        action = None
        report_id = None

        for _ in range(MAX_ROUNDS):
            kwargs: dict = {
                "model": runtime["model"],
                "messages": messages,
                "temperature": runtime["temperature"],
                "max_tokens": runtime["max_tokens"],
                "stream": True,
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas
                kwargs["tool_choice"] = "auto"
            try:
                stream = await client.chat.completions.create(**kwargs)
            except Exception as e:  # noqa: BLE001
                ok, err = False, f"大模型调用失败：{e}"
                yield ms.error(err)
                yield ms.data(
                    "finish",
                    {
                        "reply": "",
                        "tool_calls": tool_log,
                        "action": action,
                        "report_id": report_id,
                    },
                )
                yield ms.finish()
                yield ms.done()
                return

            content = ""
            tool_calls: dict = {}
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    yield ms.reasoning(rc)
                if getattr(delta, "content", None):
                    content += delta.content
                    yield ms.text(delta.content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = tool_calls.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments

            yield ms.reasoning_end()
            yield ms.text_end()

            if not tool_calls:
                yield ms.data(
                    "finish",
                    {
                        "reply": content,
                        "tool_calls": tool_log,
                        "action": action,
                        "report_id": report_id,
                    },
                )
                yield ms.finish()
                yield ms.done()
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {
                            "id": s["id"],
                            "type": "function",
                            "function": {"name": s["name"], "arguments": s["arguments"]},
                        }
                        for s in tool_calls.values()
                    ],
                }
            )
            for s in tool_calls.values():
                name = s["name"]
                try:
                    args = json.loads(s["arguments"] or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                result = await _run_app_tool(name, args, uid, http_tools)
                if isinstance(result, dict):
                    if result.get("__action__"):
                        action = result["__action__"]
                    if result.get("__report_id__"):
                        report_id = result["__report_id__"]
                tool_log.append({"name": name, "args": args, "result": result})
                yield ms.tool(s["id"], name, args=args, output=result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": s["id"],
                        "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                    }
                )

        reply = "工具调用次数已达上限，请缩小问题范围后重试。"
        yield ms.text(reply)
        yield ms.text_end()
        yield ms.data(
            "finish",
            {"reply": reply, "tool_calls": tool_log, "action": action, "report_id": report_id},
        )
        yield ms.finish()
        yield ms.done()
    except Exception as e:  # noqa: BLE001
        ok, err = False, str(e)
        yield ms.error(f"运行失败：{e}")
        yield ms.data("finish", empty_finish)
        yield ms.finish()
        yield ms.done()
    finally:
        await AiOverviewService.add_log(
            model_name,
            "app",
            int((time.perf_counter() - t0) * 1000),
            "success" if ok else "error",
            err,
            app_id=app_id,
            user_id=uid,
        )
