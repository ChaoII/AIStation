"""问数权限：策略与数据域的**读取**层（QueryGuard 的唯一策略来源）。

为什么单独一层（而不是在 guard 里写 SQL）：

- guard 只做编排（三态、星号、审计、shadow），判定数据怎么读属于持久化细节；
- 迁移器（T8）、解释接口（T12）、缓存指纹都要读同一份策略，多一处 ``SELECT``
  就多一处 drift —— 三个调用方共用本模块。

两条约定：

1. **只读「启用且未删除」**：判定侧永远看不到禁用/软删的策略（否则停用不生效；
   ``enabled=false`` 的行若被读进来还会污染 shadow 对比结果）；
2. **不吞异常**：读库失败一律上抛，由 :mod:`guard` 统一转成 **deny（fail-closed）**。
   在这里静默返回空列表等于「没有任何 allow」→ 全表默认拒绝，看起来同样"安全"，
   但审计 reason 会变成误导性的「默认拒绝」，排查时找不到真正原因。
"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.core.database import async_db_session

from .engine import Policy

__all__ = ["domain_codes_for_user", "list_policies"]

#: 读取策略（列顺序与 :func:`_policy_row` 一一对应）。
#:
#: ``ORDER BY id`` 只为结果稳定；具体裁决顺序由 ``engine._sort_key`` 决定
#: （具体性 → priority → id），这里不要抢着排序。
_POLICY_SQL = (
    "SELECT id, effect, resource_kind, resource_code, subject_kind, subject_value, "
    "condition, columns, mask_expr, marking, priority, enabled "
    "FROM ai_policy WHERE enabled=true AND is_deleted=false ORDER BY id"
)

#: 读取数据域（``members`` 是 JSONB 数组，成员是 user id）。
_DOMAIN_SQL = (
    "SELECT code, members FROM ai_data_domain "
    "WHERE enabled=true AND is_deleted=false ORDER BY id"
)


def _text(value) -> str:
    """``None`` → 空串；其它转去空白字符串（``0`` 是合法值，不能按缺失处理）。"""
    return "" if value is None else str(value).strip()


def _as_list(value) -> list:
    """jsonb 列归一：PG/驱动可能直接给 list，也可能给 JSON 文本。"""
    if isinstance(value, (list, tuple)):
        return list(value)
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _policy_row(row) -> Policy:
    """``ai_policy`` 行 → :class:`Policy`（``columns`` 归一成小写元组）。"""
    columns = tuple(
        c for c in (_text(v).lower() for v in _as_list(row[7])) if c
    )
    return Policy(
        id=int(row[0] or 0),
        effect=_text(row[1]).lower(),
        resource_kind=_text(row[2]).lower(),
        resource_code=_text(row[3]),
        subject_kind=_text(row[4]).lower(),
        subject_value=_text(row[5]),
        condition=_text(row[6]),
        columns=columns,
        mask_expr=_text(row[8]),
        marking=_text(row[9]),
        priority=int(row[10] or 0),
        enabled=bool(row[11]),
    )


async def list_policies() -> list[Policy]:
    """``ai_policy`` 中**启用且未删除**的全部策略（判定引擎的输入）。

    策略条数是「几十条」量级（治理页手工配置 + 迁移生成），一次全量读进内存足够；
    不要按表名过滤 —— 引擎需要看到所有命中主体的策略，SQL 里的表名可能带 schema/大小写。
    """
    async with async_db_session() as db:
        rows = (await db.execute(text(_POLICY_SQL))).fetchall()
    return [_policy_row(r) for r in rows]


def _member_ids(value) -> set[str]:
    """``ai_data_domain.members`` → 成员 id 文本集合（兼容 int / str / JSON 文本）。"""
    return {_text(v) for v in _as_list(value) if _text(v)}


async def domain_codes_for_user(user_id: int | None) -> tuple[str, ...]:
    """用户所属**启用且未删除**的数据域 code（排序后返回，可复现）。

    用途：``guard.prepare`` 把它填进 ``principal.attrs["domains"]``（逗号串），
    否则 ``subject_kind=domain`` 的策略在 enforce 下永远不命中（等价于大面积拒答）。

    ``user_id`` 为空/非法时直接返回 ``()``，**不查库**：没有身份就没有域成员，
    调用方（无主体）会在更早一步被拒绝。
    """
    try:
        uid = int(user_id or 0)
    except (TypeError, ValueError):
        uid = 0
    if not uid:
        return ()

    want = str(uid)
    async with async_db_session() as db:
        rows = (await db.execute(text(_DOMAIN_SQL))).fetchall()

    codes = {
        _text(code)
        for code, members in rows
        if _text(code) and want in _member_ids(members)
    }
    return tuple(sorted(codes))
