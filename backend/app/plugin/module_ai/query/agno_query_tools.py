"""Agno 问数工具集：把工程化能力打包为 Agent 可自主调用的工具。

让 LLM Agent 自己决策何时调用：
- search_schema：按问题取相关表/字段上下文（含指标/术语/关联/示例）
- get_fewshots：取与问题相关的正确 SQL 示例
- check_cost：EXPLAIN 预估查询代价（帮助模型避免超重查询）
- semantic_search：纯向量语义检索命中的表（Agno 语义层）
- table_metadata：指定表的元数据标注（描述/业务域/业务场景/字段敏感/关联）
"""
from __future__ import annotations

import re

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


async def kg_search(question: str) -> str:
    """用知识图谱(表/字段/关联/业务域/指标/术语)遍历召回相关表、字段与联表路径。"""
    from .agno_kg import _ensure, kg_explore

    log.warning("[QUERY_TOOL] 模型调用了 kg_search，question={}", question)
    try:
        await _ensure()
        return kg_explore(question)
    except Exception as e:  # noqa: BLE001
        return f"知识图谱检索失败：{e}"


async def list_metrics() -> str:
    """列出系统可用的统计指标（key/名称/描述），辅助确定问题是否为指标查询。"""
    from .service import SYSTEM_DS, AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 list_metrics")
    try:
        ms = await AiQueryService.list_metrics(SYSTEM_DS)
        return "\n".join(f"- {m['key']}: {m['name']}({m['description']})" for m in ms if m["enabled"])
    except Exception as e:  # noqa: BLE001
        return f"获取指标失败：{e}"


async def list_terms() -> str:
    """列出系统已配置的业务术语（术语→指标/字段映射）。"""
    from .service import SYSTEM_DS, AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 list_terms")
    try:
        ts = await AiQueryService.list_terms(SYSTEM_DS)
        return "\n".join(f"- {t['term']} -> {t.get('metric_key') or t.get('field_path')}" for t in ts) or "暂无术语"
    except Exception as e:  # noqa: BLE001
        return f"获取术语失败：{e}"


async def search_history(question: str) -> str:
    """检索历史沉淀的正确「问题→SQL」样例（含反馈自动策展），供参考写法。"""
    from .service import SYSTEM_DS, AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 search_history，question={}", question)
    try:
        egs = await AiQueryService._dynamic_fewshots(question, SYSTEM_DS)
        return "\n".join(f"问：{e['q']}\nSQL：{e['sql']}" for e in egs) or "暂无历史样例"
    except Exception as e:  # noqa: BLE001
        return f"检索历史样例失败：{e}"


#: 常见中文业务词 → 数据库精确值（证据值映射）
_VALUE_SYNONYMS = {
    "在线": "ONLINE", "上线": "ONLINE", "运行中": "RUNNING", "运行": "RUNNING",
    "离线": "OFFLINE", "下线": "OFFLINE", "失败": "ERROR", "错误": "ERROR", "异常": "ERROR",
    "成功": "SUCCESS", "停止": "STOPPED", "暂停": "STOPPED", "进行中": "in_progress",
    "已完成": "completed", "完成": "completed", "待处理": "PENDING", "处理中": "PROCESSING",
    "预警": "WARNING", "严重": "SEVERE", "高": "HIGH", "中": "MEDIUM", "低": "LOW",
    "启用": "true", "禁用": "false", "是": "true", "否": "false",
}


async def resolve_value(term: str) -> str:
    """把自然语言的取值（如「在线/离线/运行中」）解析为数据库字段的精确枚举值。"""
    from .service import AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 resolve_value，term={}", term)
    try:
        schema = await AiQueryService._system_schema()
        # 收集所有列的枚举取值
        cands: dict[str, str] = {}  # 精确值 -> 出现位置
        for t, labels in schema.items():
            for lab in labels:
                m = re.search(r"【取值:([^】]+)】", lab)
                if not m:
                    continue
                for v in m.group(1).split(","):
                    v = v.strip()
                    if v and v not in cands:
                        cands[v] = f"{t}.{lab.split('(')[0]}"
        t = (term or "").strip()
        hits: list[str] = []
        tl = t.lower()
        for v, where in cands.items():
            if tl and (tl in v.lower() or v.lower() in tl):
                hits.append(f"{v}(在 {where})")
        syn = _VALUE_SYNONYMS.get(t)
        if syn and not any(h.startswith(syn) for h in hits):
            hits.append(f"{syn}(同义词映射)")
        if not hits and t:
            return (f"未找到「{t}」对应的精确枚举值。常见枚举："
                    + ", ".join(list(cands)[:20]))
        return "建议使用的精确值：" + "；".join(hits[:12])
    except Exception as e:  # noqa: BLE001
        return f"解析取值失败：{e}"


async def find_join_path(source: str, target: str) -> str:
    """查找两张表之间的关联字段（可 JOIN 路径），用知识图谱的字段关联边遍历。"""
    from .service import AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 find_join_path，source={} target={}", source, target)
    try:
        schema = await AiQueryService._system_schema()
        # 提取所有 表.字段 -> 表.字段 关联
        rel_re = re.compile(r"【关联:([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)】")
        rels: list[tuple[str, str, str, str]] = []  # (s_t,s_c,d_t,d_c)
        for t, labels in schema.items():
            for lab in labels:
                col = lab.split("(")[0]
                m = rel_re.search(lab)
                if m:
                    rels.append((t, col, m.group(1), m.group(2)))
        src, dst = (source or "").strip(), (target or "").strip()
        direct = [r for r in rels if (r[0] == src and r[2] == dst) or (r[0] == dst and r[2] == src)]
        out = []
        for r in direct:
            out.append(f"{r[0]}.{r[1]} = {r[2]}.{r[3]}")
        if out:
            return f"表 {src} 与 {dst} 可直接关联：" + "；".join(out[:6])
        # 间接：A.字段 关联到 C.字段，C 与 dst 同表/再关联
        via = set()
        for r in rels:
            if r[0] == src or r[2] == src:
                via.add((r[0], r[1]))
        out2 = []
        for r in rels:
            if (r[2] == dst or r[0] == dst) and (r[0], r[1]) in via:
                out2.append(f"{src} 经 {r[0]}.{r[1]} / {r[2]}.{r[3]} 关联到 {dst}")
        return (f"表 {src} 与 {dst} 无直接关联字段。"
                + ("；".join(out2[:6]) if out2 else "，请确认表名或改用表间实体关系。"))
    except Exception as e:  # noqa: BLE001
        return f"查找关联失败：{e}"


async def explain_column(table: str, column: str) -> str:
    """返回指定表某字段的说明：类型/中文描述/关联/枚举取值/敏感。"""
    from .service import AiQueryService

    log.warning("[QUERY_TOOL] 模型调用了 explain_column，table={} column={}", table, column)
    try:
        schema = await AiQueryService._system_schema()
        for lab in (schema.get((table or "").strip()) or []):
            if lab.split("(")[0] == (column or "").strip():
                return f"{table}.{column}：{lab}"
        return f"未找到 {table}.{column}"
    except Exception as e:  # noqa: BLE001
        return f"查询字段说明失败：{e}"


async def run_sql(sql: str) -> str:
    """执行一条只读 SELECT，返回结果（前 N 行）或错误信息，供模型执行-自修复（execution-guided）。

    模型生成候选 SQL 后调用本工具验证：成功返回结果行；报错（列/语法/JOIN）返回错误，
    Agno 会把该错误插回上下文，模型据此修正 SQL 再调用，直至成功或放弃。
    """
    from .service import _execute_sql, _system_allowed, validate_sql

    log.warning("[QUERY_TOOL] 模型调用了 run_sql，sql={}", (sql or "")[:200])
    sql = (sql or "").strip()
    try:
        safe = validate_sql(sql, await _system_allowed())
    except Exception as e:  # noqa: BLE001
        return f"SQL 不合法：{e}"
    try:
        res = await _execute_sql(safe)
    except Exception as e:  # noqa: BLE001
        return f"执行失败：{e}"
    cols = res.get("columns") or []
    rows = res.get("rows") or []
    txt = "\n".join(" | ".join(str(v) for v in r) for r in rows[:20]) or "（空结果）"
    return f"执行成功，共 {len(rows)} 行。列：{', '.join(cols)}。\n{txt}"


# ---------------------------------------------------------------------------
# 结合 Agno 原生 SQLTools（官方 SQL 工具）：list_tables / describe_table 用 Agno 官方实现；
# run_sql_query 重写为「本体白名单只读执行」，复用项目同步 engine + _system_allowed() 白名单，
# 让问数用 Agno 官方 SQL 工具，同时安全性（只读 + 白名单）不可绕过。
# ---------------------------------------------------------------------------
def _build_agno_sql_tools():
    from agno.tools.sql import SQLTools

    from app.core.database import engine as _engine

    class _SafeSqlTools(SQLTools):
        """Agno 官方 SQL 工具，但 run_sql_query 强制走本体白名单只读执行（安全）。"""

        async def run_sql_query(self, query: str, limit: int = 1000) -> str:  # type: ignore[override]
            """执行一条经本体白名单校验的只读 SELECT，返回结果（前 20 行）或错误信息。

            Args:
                query (str): 待执行的 SELECT SQL。
                limit (int, optional): 返回行数上限，默认 1000。
            Returns:
                str: 执行结果或错误信息。报错时模型应据此修正 SQL 再调用。
            """
            from .service import _execute_sql, _system_allowed, validate_sql

            log.warning("[QUERY_TOOL] 模型调用了 agno_sql_run_sql_query，sql={}", (query or "")[:200])
            q = (query or "").strip()
            if not q:
                return "SQL 为空"
            try:
                safe = validate_sql(q, await _system_allowed())
            except Exception as e:  # noqa: BLE001
                return f"SQL 不合法：{e}"
            try:
                res = await _execute_sql(safe)
            except Exception as e:  # noqa: BLE001
                return f"执行失败：{e}"
            cols = res.get("columns") or []
            rows = res.get("rows") or []
            txt = "\n".join(" | ".join(str(v) for v in r) for r in rows[:20]) or "（空结果）"
            return f"执行成功，共 {len(rows)} 行。列：{', '.join(cols)}。\n{txt}"

    return _SafeSqlTools(
        db_engine=_engine,
        enable_list_tables=False,
        enable_describe_table=False,
        enable_run_sql_query=True,
    )


#: Agno 官方 SQL 工具（list_tables/describe_table 官方实现 + run_sql_query 白名单只读）
AGNO_SQL_TOOLS = _build_agno_sql_tools()


#: 注册进 Agent 的工具集合（可同时传给 Agent(tools=...)）
QUERY_TOOLS = [
    search_schema, get_fewshots, check_cost, semantic_search, table_metadata,
    kg_search, list_metrics, list_terms, search_history,
    resolve_value, find_join_path, explain_column,
]
