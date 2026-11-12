"""软删除口径：**确定性**地给业务表补 `"ISDELETED" = false`。

为什么不放进提示词
------------------
2026-11 实测（3 组 × 78 题配对）：
  - 提示词规则「有 ISDELETED 列就默认排除」把准确率从 0.8846 拉到 0.8985~0.9103，
    但**它自己两轮之间就翻转 5 题**（baseline 是 0 题）；
  - 收益（1~2 题）小于自身抖动（5 题）→ 统计上不成立。
  - 而"排序规则"那条两轮零变化，纯属白占 token。

结论：口径这种**确定的规则**不该交给模型去"记得"，应该由代码保证。
模型只要生成 SQL，剩下的由这里改写 —— 0 token、100% 稳定、可单测。

同一套规则也用于金标（`scripts/apply_softdelete_policy.py` 直接 import 本模块），
避免"金标一套、运行时另一套"。
"""
from __future__ import annotations

from .filtering import softdelete_rules

#: 问句在问"删除"本身：此时**不能**把 `= false` 塞进去，否则问的就是反的。
#: 词表以 ``filtering.DEFAULT_FILTER_RULES["softdelete"]["deletion_hints"]`` 为唯一来源，
#: 这里只做别名导出（历史调用方按这个名字引用），避免两处各写一份。
DELETION_HINTS = tuple(softdelete_rules(None)["deletion_hints"])


def asks_about_deletion(question: str, hints: list[str] | None = None) -> bool:
    """问句是否在问"已删除/删除"（含"排除已删除"这种要求过滤的表述）。

    ``hints`` 可由数据源配置覆盖（``filter_rules.softdelete.deletion_hints``）：
    不同业务的说法不一样（作废/注销/失效…），不该写死在代码里。
    """
    q = question or ""
    words = hints or softdelete_rules(None)["deletion_hints"]
    return any(h and h in q for h in words)


def inject_softdelete(sql: str, del_tables: set[str],
                      column: str = "ISDELETED") -> tuple[str, list[str]]:
    """给每个 SELECT 各自直接引用的软删表补 `ISDELETED = false`。

    返回 ``(新 SQL, 被注入的标识符列表)``；无可注入时原样返回。

    ⚠️ 两个 sqlglot 的坑（都踩过）：
    1. `.where()` 返回**副本**，`replace()` 对根节点是空操作 —— 只写
       `sel.where(...)` 会"看起来成功、SQL 一点没变"；
    2. 必须**逐 SELECT** 注入：`UNION ALL` 的两个分支、CTE、子查询各自作用域，
       只动最外层会把条件加到错的地方（或生成非法 SQL）。
    """
    if not sql or not del_tables:
        return sql, []
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # 没装 sqlglot 时不做改写（调用方已有正则校验兜底）
        return sql, []

    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        return sql, []

    hit: list[str] = []
    for sel in list(parsed.find_all(exp.Select)):
        conds = []
        for t in sel.find_all(exp.Table):
            # 只要**直接属于这个 SELECT** 的表（子查询里的归它自己的 SELECT 管）
            if t.find_ancestor(exp.Select) is not sel:
                continue
            if t.name.upper() not in del_tables:
                continue
            ident = t.alias_or_name
            conds.append(exp.EQ(
                this=exp.Column(this=exp.Identifier(this=column, quoted=True),
                                table=exp.Identifier(this=ident, quoted=True)),
                expression=exp.false(),
            ))
            hit.append(ident)
        if not conds:
            continue
        cond = conds[0]
        for c in conds[1:]:
            cond = exp.and_(cond, c)
        old = sel.args.get("where")
        sel.set("where", exp.Where(this=exp.and_(old.this, cond) if old else cond))
    if not hit:
        return sql, []
    return parsed.sql(dialect="postgres"), hit


def apply_softdelete_policy(question: str, sql: str, schema_map: dict | None,
                            rules: dict | None = None) -> tuple[str, list[str]]:
    """纯逻辑：按数据源规则给人写的/SQL 补软删条件，返回 ``(SQL, 命中标识符)``。

    规则来源 = ``ai_query_datasources.filter_rules.softdelete``（缺省即 ``ISDELETED``）：
    - ``column``：软删列名（不同库可能叫 IS_DELETED / DEL_FLAG）；
    - ``deletion_hints``：问句里出现这些词时**不动**（问的就是已删除）。
    """
    cfg = softdelete_rules(rules)
    column = cfg["column"]
    if not sql or asks_about_deletion(question, cfg["deletion_hints"]):
        return sql, []
    flat = sql.replace(" ", "").upper()
    if column.replace(" ", "").upper() in flat:
        return sql, []
    want = f"{column}(".upper()
    del_tables = {
        str(t).upper() for t, labels in (schema_map or {}).items()
        if any(str(lab).upper().startswith(want) for lab in (labels or []))
    }
    if not del_tables:
        return sql, []
    return inject_softdelete(sql, del_tables, column)


async def rewrite_generated_sql(question: str, sql: str, datasource: str) -> str:
    """问数入口用：读数据源配置 + schema，补软删条件；**任何异常都返回原 SQL**。

    为什么收口到这里（2026-11-12）：`execute_ops` 与 `assetio_ops` 各有一份**逐字重复**的实现，
    改一处忘另一处就是"两个入口口径不同"。现在配置（列名/提示词）在数据源里维护，
    代码只留一份执行逻辑。
    """
    from app.core.logger import log

    try:
        from . import service as _svc

        rules = None
        try:
            ds_id = int(str(datasource).split(":")[-1])
            ds = await _svc.AiQueryService._load_ds(ds_id)
            rules = getattr(ds, "filter_rules", None)
        except Exception:  # noqa: BLE001 - 配置读不到就用默认
            rules = None
        schema_map = await _svc.AiQueryService._ds_schema_map(datasource)
        new_sql, hit = apply_softdelete_policy(question, sql, schema_map, rules)
        if hit:
            log.info("[query] 软删除口径改写：表 {}（{} 处）",
                     "/".join(sorted(set(hit))[:3]), len(hit))
        return new_sql
    except Exception as e:  # noqa: BLE001 - 改写是增强，失败不影响答数
        log.warning(f"[query] 软删除口径改写失败（用原 SQL）: {str(e)[:100]}")
        return sql
