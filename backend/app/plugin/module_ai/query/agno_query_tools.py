"""Agno 问数工具集：把工程化能力打包为 Agent 可自主调用的工具。

让 LLM Agent 自己决策何时调用：
- search_schema：按问题取相关表/字段上下文（schema 链接）
- get_fewshots：取与问题相关的正确 SQL 示例
- check_cost：EXPLAIN 预估查询代价（帮助模型避免超重查询）
"""
from __future__ import annotations

from app.core.logger import log


async def search_schema(question: str) -> str:
    """按问题返回相关的可查询表与字段（含指标/术语/中文描述/关联/示例），供生成 SQL 使用。"""
    from .service import SYSTEM_DS, AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 search_schema，question={}", question)
    try:
        metrics = await AiQueryService.list_metrics(SYSTEM_DS)
        terms = await AiQueryService.list_terms(SYSTEM_DS)
        ctx = await AiQueryService._build_schema_context(question, SYSTEM_DS, metrics, terms)
        # 截断到合理长度，避免上下文爆炸；tool_call_limit 已兜底防循环
        return ctx[:12000]
    except Exception as e:  # noqa: BLE001
        return f"获取表结构失败：{e}"


async def get_fewshots(question: str) -> str:
    """按问题返回相关的「问题→正确 SQL」示例，供参考写法。"""
    from .service import SYSTEM_DS, AiQueryService

    try:
        egs = await AiQueryService._dynamic_fewshots(question, SYSTEM_DS)
        return "\n".join(f"问：{e['q']}\nSQL：{e['sql']}" for e in egs) or "暂无示例"
    except Exception as e:  # noqa: BLE001
        return f"获取示例失败：{e}"


async def check_cost(sql: str) -> str:
    """EXPLAIN 预估一个 SELECT 查询的结果行数（越大越耗资源）。"""
    from .service import AiQueryService

    try:
        rows = await AiQueryService._explain_rows(sql)
        return f"预计返回 {rows} 行"
    except Exception as e:  # noqa: BLE001
        return f"无法预估代价：{e}"


#: 注册进 Agent 的工具集合（可同时传给 Agent(tools=...)）
QUERY_TOOLS = [search_schema, get_fewshots, check_cost]
