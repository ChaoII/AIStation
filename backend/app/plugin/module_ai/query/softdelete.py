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

#: 问句在问"删除"本身：此时**不能**把 `= false` 塞进去，否则问的就是反的
DELETION_HINTS = (
    "已删除", "删除的", "删除记录", "排除已删除", "是否删除", "作废", "被删",
)


def asks_about_deletion(question: str) -> bool:
    """问句是否在问"已删除/删除"（含"排除已删除"这种要求过滤的表述）。"""
    q = question or ""
    return any(h in q for h in DELETION_HINTS)


def inject_softdelete(sql: str, del_tables: set[str]) -> tuple[str, list[str]]:
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
                this=exp.Column(this=exp.Identifier(this="ISDELETED", quoted=True),
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
