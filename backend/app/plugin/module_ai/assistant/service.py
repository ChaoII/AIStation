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


async def _load_tool_schemas() -> list[dict]:
    """取启用工具的合并 schema（system/agno/http）。

    仅在查询**异常**（DB/schema 加载失败）时回退内置静态列表；查询成功但为空
    （管理员禁用了全部工具）时必须返回 ``[]``，不得重新暴露内置工具。
    """
    from app.plugin.module_ai.tools_catalog.service import get_enabled_tool_schemas

    try:
        return await get_enabled_tool_schemas()
    except Exception:  # noqa: BLE001  数据库异常不应阻断对话
        return TOOL_SCHEMAS


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


async def run_agent_ui_stream(
    *,
    client,
    runtime: dict,
    messages: list[dict],
    tool_schemas: list[dict] | None,
    dispatch,
    ms,
    user_id: int | None,
    state: dict,
    max_rounds: int = MAX_ROUNDS,
):
    """共享的 function calling 流式循环：助手 /stream 与应用运行台复用同一实现。

    - ``dispatch(name, args, user_id)`` 由调用方注入（内置注册表或应用 HTTP 工具派发）。
    - ``state`` 为可变状态字典，含 assistant_text / reply / tool_calls / action /
      report_id / error；``assistant_text`` 跨轮累加所有 text delta。
    - 仅依赖传入的 ``UiMessageStream``，产出的 SSE 帧与既有实现保持逐字节一致。
    """
    for _ in range(max_rounds):
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
            state["error"] = f"大模型调用失败：{e}"
            yield ms.error(state["error"])
            yield ms.data(
                "finish",
                {
                    "reply": "",
                    "tool_calls": state["tool_calls"],
                    "action": state["action"],
                    "report_id": state["report_id"],
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
                state["assistant_text"] += delta.content
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
            state["reply"] = content
            yield ms.data(
                "finish",
                {
                    "reply": content,
                    "tool_calls": state["tool_calls"],
                    "action": state["action"],
                    "report_id": state["report_id"],
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
            result = await dispatch(name, args, user_id)
            if isinstance(result, dict):
                if result.get("__action__"):
                    state["action"] = result["__action__"]
                if result.get("__report_id__"):
                    state["report_id"] = result["__report_id__"]
            state["tool_calls"].append({"name": name, "args": args, "result": result})
            yield ms.tool(s["id"], name, args=args, output=result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": s["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                }
            )

    reply = "工具调用次数已达上限，请缩小问题范围后重试。"
    state["assistant_text"] += reply
    state["reply"] = reply
    yield ms.text(reply)
    yield ms.text_end()
    yield ms.data(
        "finish",
        {
            "reply": reply,
            "tool_calls": state["tool_calls"],
            "action": state["action"],
            "report_id": state["report_id"],
        },
    )
    yield ms.finish()
    yield ms.done()


async def run_assistant(message: str, auth) -> dict:
    runtime = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    if not runtime:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")

    from openai import AsyncOpenAI

    from app.plugin.module_ai.provider.service import build_headers
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    client = AsyncOpenAI(
        base_url=runtime["base_url"],
        api_key=runtime["api_key"] or "sk-none",
        default_headers=build_headers(
            runtime["base_url"], runtime.get("extra_headers"), "aistation-assistant"
        ),
    )
    tool_schemas = await _load_tool_schemas()
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
                tools=tool_schemas,
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
            result = await dispatch_tool(name, args, user_id)
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


def last_user_text(ui_messages: list[dict]) -> str:
    """取最后一条 user 消息的纯文本，用于会话落库。"""
    for m in reversed(extract_openai_messages(ui_messages)):
        if m["role"] == "user":
            return m["content"]
    return ""


async def run_assistant_ui_stream(
    ui_messages: list[dict], auth, session_id: int | None = None
):
    """AI SDK UI Message Stream 版助手：reasoning/text/tool/finish 分片。

    整个生成器体包裹在 ``try/except/finally`` 中：无论正常结束、模型/工具异常还是
    客户端中断，只要传入了 ``session_id``，已产出的 user/assistant 文本都会在
    ``finally`` 中落库；中途异常也会补发 error + data-finish + finish + [DONE]，
    保证流始终有终止帧且会话行不丢失（``persist_session_exchange`` 内部已吞掉异常）。
    """
    from openai import AsyncOpenAI

    from app.plugin.module_ai.provider.service import build_headers
    from app.plugin.module_ai.sessions.service import persist_session_exchange
    from app.plugin.module_ai.streaming import UiMessageStream
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    ms = UiMessageStream()
    user_text = last_user_text(ui_messages)
    user_id = getattr(getattr(auth, "user", None), "id", None)
    # 累积流出的 assistant 文本：即使中途异常，finally 也能落下已产出的内容
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
        runtime = (
            await AiModelService.get_runtime_model("chat")
            or await AiModelService.get_runtime_model()
        )
        if not runtime:
            yield ms.error("未配置大模型，请在 AI 管理→模型配置 中添加并启用")
            # 终止分支统一补发 data-finish 结束帧，保持协议一致
            yield ms.data(
                "finish", {"reply": "", "tool_calls": [], "action": None, "report_id": None}
            )
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
        tool_schemas = await _load_tool_schemas()

        async for frame in run_agent_ui_stream(
            client=client,
            runtime=runtime,
            messages=messages,
            tool_schemas=tool_schemas,
            dispatch=dispatch_tool,
            ms=ms,
            user_id=user_id,
            state=state,
        ):
            yield frame
    except Exception as e:  # noqa: BLE001
        # 中途异常（工具/解析/网络）也要补发终止帧，避免 SSE 悬空
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
        # 无论正常/异常/客户端中断，都尝试落库；无 session_id 时内部直接返回。
        # persist_session_exchange 已吞异常，保证不会从 finally 抛出。
        await persist_session_exchange(
            session_id, user_text, state["assistant_text"], user_id=user_id
        )
