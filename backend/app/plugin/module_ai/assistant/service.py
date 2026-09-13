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
    runtime = await AiModelService.get_runtime_model()
    if not runtime:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=runtime["base_url"], api_key=runtime["api_key"] or "sk-none"
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
