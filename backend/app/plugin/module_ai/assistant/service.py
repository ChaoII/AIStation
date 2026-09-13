"""AI 助手服务：大模型 function calling 循环。"""
from __future__ import annotations

import inspect
import json

from app.core.exceptions import CustomException
from app.plugin.module_ai.provider.service import AiModelService

from .tools import TOOL_REGISTRY, TOOL_SCHEMAS

SYSTEM_PROMPT = (
    "你是 AIStation 平台的智能助手。你可以调用工具查询系统数据、生成报告、发起页面导航或提议操作。"
    "规则：1) 涉及系统数据时必须调用工具获取，禁止编造；2) 需要跳转页面时用 navigate；"
    "3) 需要生成报告时用 generate_report；4) 变更类操作只能提议（propose_*），由用户确认；"
    "5) 用简洁中文回答，取数结果可用 Markdown 表格汇总。"
)

MAX_ROUNDS = 6


async def _call_tool(name: str, args: dict, user_id: int | None) -> object:
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return {"error": f"未知工具：{name}"}
    fn = entry["fn"]
    try:
        params = inspect.signature(fn).parameters
        if "user_id" in params:
            args = {**args, "user_id": user_id}
        return await fn(**args)
    except TypeError as e:
        return {"error": f"参数错误：{e}"}
    except Exception as e:  # 工具异常不中断对话
        return {"error": str(e)}


async def run_assistant(message: str, auth) -> dict:
    runtime = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    if not runtime:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")

    from openai import AsyncOpenAI

    from app.plugin.module_ai.provider.service import build_headers

    client = AsyncOpenAI(
        base_url=runtime["base_url"],
        api_key=runtime["api_key"] or "sk-none",
        default_headers=build_headers(
            runtime["base_url"], runtime.get("extra_headers"), "aistation-assistant"
        ),
    )
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]
    tool_log: list[dict] = []
    action = None
    report_id = None
    user_id = getattr(getattr(auth, "user", None), "id", None)

    for _ in range(MAX_ROUNDS):
        try:
            resp = await client.chat.completions.create(
                model=runtime["model"],
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=runtime["temperature"],
                max_tokens=runtime["max_tokens"],
            )
        except Exception as e:
            raise CustomException(msg=f"大模型调用失败：{e}")

        msg = resp.choices[0].message
        if not getattr(msg, "tool_calls", None):
            return {
                "reply": msg.content or "",
                "tool_calls": tool_log,
                "action": action,
                "report_id": report_id,
            }

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            result = await _call_tool(name, args, user_id)
            if isinstance(result, dict):
                if result.get("__action__"):
                    action = result["__action__"]
                if result.get("__report_id__"):
                    report_id = result["__report_id__"]
            tool_log.append({"name": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                }
            )

    return {
        "reply": "工具调用次数已达上限，请缩小问题范围后重试。",
        "tool_calls": tool_log,
        "action": action,
        "report_id": report_id,
    }


def extract_openai_messages(ui_messages: list[dict]) -> list[dict]:
    """把 AI SDK UIMessage 列表转成 OpenAI messages（只取 user/assistant 的 text part）。"""
    out: list[dict] = []
    for m in ui_messages or []:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = ""
        for part in m.get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text") or ""
        if text:
            out.append({"role": role, "content": text})
    return out


async def run_assistant_ui_stream(ui_messages: list[dict], auth):
    """AI SDK UI Message Stream 版助手：reasoning/text/tool/finish 分片。"""
    from openai import AsyncOpenAI

    from app.plugin.module_ai.provider.service import build_headers
    from app.plugin.module_ai.streaming import UiMessageStream

    ms = UiMessageStream()
    runtime = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    yield ms.start()
    if not runtime:
        yield ms.error("未配置大模型，请在 AI 管理→模型配置 中添加并启用")
        yield ms.finish()
        yield ms.done()
        return

    client = AsyncOpenAI(
        base_url=runtime["base_url"],
        api_key=runtime["api_key"] or "sk-none",
        default_headers=build_headers(
            runtime["base_url"], runtime.get("extra_headers"), "aistation-assistant"
        ),
    )
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += extract_openai_messages(ui_messages)
    user_id = getattr(getattr(auth, "user", None), "id", None)
    tool_log: list[dict] = []
    action = None
    report_id = None

    for _ in range(MAX_ROUNDS):
        try:
            stream = await client.chat.completions.create(
                model=runtime["model"],
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=runtime["temperature"],
                max_tokens=runtime["max_tokens"],
                stream=True,
            )
        except Exception as e:  # noqa: BLE001
            yield ms.error(f"大模型调用失败：{e}")
            yield ms.data("finish", {"reply": "", "tool_calls": tool_log, "action": action, "report_id": report_id})
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
                {"reply": content, "tool_calls": tool_log, "action": action, "report_id": report_id},
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
            result = await _call_tool(name, args, user_id)
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

    yield ms.text("工具调用次数已达上限，请缩小问题范围后重试。")
    yield ms.text_end()
    yield ms.data(
        "finish",
        {
            "reply": "工具调用次数已达上限，请缩小问题范围后重试。",
            "tool_calls": tool_log,
            "action": action,
            "report_id": report_id,
        },
    )
    yield ms.finish()
    yield ms.done()
