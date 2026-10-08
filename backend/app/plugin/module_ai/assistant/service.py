"""AI 助手服务：Agno Agent 驱动，维护工具注册、RAG 与共享消息工具函数。

- ``run_assistant``：Agno Agent 驱动的非流式一轮对话（前端 /chat）。
- 工具统一由 ``agno_tools.business`` / ``agno_tools.dynamic`` 注册并经
  ``tools_catalog.dispatch_tool`` 派发，不再手写 OpenAI function calling 循环。
"""
from __future__ import annotations

import inspect
import json

from app.core.exceptions import CustomException
from app.plugin.module_ai.provider.service import AiModelService

from .tools import TOOL_REGISTRY

SYSTEM_PROMPT = (
    "你是 AIStation 平台的智能助手。你可以调用工具查询系统数据、生成报告、发起页面导航或提议操作。"
    "规则：1) 涉及系统数据时必须调用工具获取，禁止编造；2) 需要跳转页面时用 navigate；"
    "3) 需要生成报告时用 generate_report；4) 变更类操作只能提议（propose_*），由用户确认；"
    "5) 用简洁中文回答，取数结果可用 Markdown 表格汇总。"
)


async def _load_tool_schemas() -> list[dict]:
    """取启用工具的合并 schema（system/agno/http）。

    查询**异常**（DB/schema 加载失败）时返回 ``[]``（记警告），绝不回退内置
    ``TOOL_SCHEMAS``：一次 DB 抖动不应把管理员已禁用的内置工具全部重新暴露给模型。
    """
    from app.plugin.module_ai.tools_catalog.service import get_enabled_tool_schemas

    try:
        return await get_enabled_tool_schemas()
    except Exception as e:  # noqa: BLE001  数据库异常不应阻断对话
        from app.core.logger import logger

        logger.warning(f"加载启用工具 schema 失败，按无工具处理: {e}")
        return []


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


async def retrieve_kb_rag(kb_ids: list[int], query: str, top_k: int = 5) -> tuple[str, list[dict]]:
    """知识库检索（RAG）：返回 ``(注入上下文, 引用来源列表)``。

    检索或模型异常时返回 ``("", [])``，对话可安全跳过 RAG。
    """
    try:
        from app.plugin.module_ai.knowledge.service import AiKnowledgeService

        if not kb_ids or not query:
            return "", []
        results = await AiKnowledgeService.search(kb_ids, query, top_k)
        if not results:
            return "", []
        ctx = "\n\n".join(
            f"[来源: {r.get('file_name') or '未知'}] {r.get('content')}" for r in results
        )
        sources = [
            {
                "title": r.get("file_name") or "未知",
                "content": (r.get("content") or "")[:200],
                "score": r.get("score"),
                "chunkId": r.get("chunk_id"),
            }
            for r in results
        ]
        return ctx, sources
    except Exception:  # noqa: BLE001
        return "", []


async def run_assistant(message: str, auth, knowledge_ids: list[int] | None = None) -> dict:
    """用 Agno Agent 驱动一轮对话（非流式），工具调用由 Agno 统一执行。

    返回结构与既有前端/API 兼容：``reply`` / ``tool_calls`` / ``action`` /
    ``report_id`` / ``sources``。
    其中 ``reply`` 为 Agno 最终正文；``action`` / ``report_id`` 从工具结果里的
    ``__action__`` / ``__report_id__`` 提取（与旧实现一致）。
    """
    from app.plugin.module_ai.agno_tools.agent_factory import build_agent
    from app.plugin.module_ai.agno_tools.business import reset_user_context, set_user_context
    from app.plugin.module_ai.assistant.service import retrieve_kb_rag

    model_config = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    if not model_config:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")

    user_id = getattr(getattr(auth, "user", None), "id", None)
    kb_ctx, sources = "", []
    if knowledge_ids:
        kb_ctx, sources = await retrieve_kb_rag(knowledge_ids, message)

    token = set_user_context(user_id)
    try:
        agent = build_agent(model_config=model_config, user_id=user_id)
        input_text = f"【参考知识】\n{kb_ctx}\n\n问题：{message}" if kb_ctx else message
        resp = await agent.arun(
            input_text,
            stream=False,
            user_id=str(user_id) if user_id is not None else None,
            add_history_to_context=True,
        )
    finally:
        reset_user_context(token)

    reply = resp.get_content_as_string() if hasattr(resp, "get_content_as_string") else str(resp.content or "")

    # 从工具执行结果提取 action / report_id（兼容旧协议字段）
    action = None
    report_id = None
    tool_log: list[dict] = []
    for tool in (resp.tools or []):
        name = getattr(tool, "tool_name", None)
        args = getattr(tool, "tool_args", None) or {}
        result = getattr(tool, "result", None)
        try:
            if isinstance(result, str):
                result = json.loads(result)
        except (ValueError, TypeError):
            pass
        if isinstance(result, dict):
            if result.get("__action__"):
                action = result["__action__"]
            if result.get("__report_id__"):
                report_id = result["__report_id__"]
        tool_log.append({"name": name, "args": args, "result": result})

    return {
        "reply": reply,
        "tool_calls": tool_log,
        "action": action,
        "report_id": report_id,
        "sources": sources,
    }


def extract_openai_messages(ui_messages: list[dict]) -> list[dict]:
    """把 AI SDK UIMessage 列表转成 OpenAI messages（兼容 parts 文本与 content 字段）。"""
    out: list[dict] = []
    for m in ui_messages or []:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = ""
        for part in m.get("parts") or []:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text") or ""
        # 兼容直接 content 字段（测试/简易调用）
        if not text and isinstance(m.get("content"), str):
            text = m.get("content") or ""
        if text:
            out.append({"role": role, "content": text})
    return out


def last_user_text(ui_messages: list[dict]) -> str:
    """取最后一条 user 消息的纯文本，用于会话落库。"""
    for m in reversed(extract_openai_messages(ui_messages)):
        if m["role"] == "user":
            return m["content"]
    return ""
