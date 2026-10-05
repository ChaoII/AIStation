"""Agno 问数工具集：把工程化能力打包为 Agent 可自主调用的工具。

让 LLM Agent 自己决策何时调用：
- search_schema：按问题取相关表/字段上下文（含指标/术语/关联/示例）
- get_fewshots：取与问题相关的正确 SQL 示例
- check_cost：EXPLAIN 预估查询代价（帮助模型避免超重查询）
- semantic_search：纯向量语义检索命中的表（Agno 语义层）
- table_metadata：指定表的元数据标注（描述/业务域/业务场景/字段敏感/关联）
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

    log.warning("[QUERY_TOOL] 模型调用了 get_fewshots，question={}", question)
    try:
        egs = await AiQueryService._dynamic_fewshots(question, SYSTEM_DS)
        return "\n".join(f"问：{e['q']}\nSQL：{e['sql']}" for e in egs) or "暂无示例"
    except Exception as e:  # noqa: BLE001
        return f"获取示例失败：{e}"


async def check_cost(sql: str) -> str:
    """EXPLAIN 预估一个 SELECT 查询的结果行数（越大越耗资源）。"""
    from .service import AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 check_cost，sql={}", sql[:200])
    try:
        rows = await AiQueryService._explain_rows(sql)
        return f"预计返回 {rows} 行"
    except Exception as e:  # noqa: BLE001
        return f"无法预估代价：{e}"


async def semantic_search(question: str) -> str:
    """用向量语义检索（Agno 语义层 + pgvector）返回与问题最相关的表名列表。"""
    from .service import SYSTEM_DS, AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 semantic_search，question={}", question)
    try:
        schema = await AiQueryService._system_schema()
        metrics = await AiQueryService.list_metrics(SYSTEM_DS)
        terms = await AiQueryService.list_terms(SYSTEM_DS)
        tables = await AiQueryService._semantic_tables(question, schema, metrics, terms)
        return "语义检索命中的表：" + (", ".join(tables) if tables else "（无）")
    except Exception as e:  # noqa: BLE001
        return f"语义检索失败：{e}"


async def table_metadata(table: str) -> str:
    """返回指定数据表的元数据标注：表描述/业务域/业务场景 + 字段业务场景/敏感/关联/枚举取值。"""
    from .service import SYSTEM_ALLOWED_TABLES, AiQueryService

    table = (table or "").strip()
    if table not in SYSTEM_ALLOWED_TABLES:
        return f"表 {table} 不在允许范围内"
    log.warning("[QUERY_TOOL] 模型调用了 table_metadata，table={}", table)
    try:
        schema = await AiQueryService._system_schema()
        tmeta = await AiQueryService._asset_tmeta()
        meta = tmeta.get(table) or {}
        lines = [f"表 {table}"]
        if meta.get("alias"):
            lines.append(f"中文名:{meta['alias']}")
        if meta.get("domain"):
            lines.append(f"业务域:{meta['domain']}")
        if meta.get("description"):
            lines.append(f"描述:{meta['description']}")
        if meta.get("business_scenarios"):
            lines.append(f"业务场景:{meta['business_scenarios']}")
        cols = schema.get(table) or []
        lines.append("字段：")
        lines.extend(f"- {c}" for c in cols)
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        return f"读取表元数据失败：{e}"


#: 注册进 Agent 的工具集合（可同时传给 Agent(tools=...)）
QUERY_TOOLS = [search_schema, get_fewshots, check_cost, semantic_search, table_metadata]
