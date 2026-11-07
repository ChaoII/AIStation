"""上下文投影：把「模型能看到的表/列」按主体权限裁剪。

生成前裁剪和生成后拦截是两件事：
- 生成后拦截（guard）保证安全，但用户要等一轮才知道没权限；
- 生成前裁剪（本模块）让模型根本看不到无权表列，少一轮、也不泄露 schema。

规则与执行期完全一致（同一份策略 + 同一个引擎）：
- 表：`deny` / 无 `allow` → 不出现；
- 列：`deny` → 不出现；`mask` → 出现但标注「脱敏」；
- 超管 → 全量（不做裁剪）。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from app.plugin.module_ai.query.policy.principal import Principal


@dataclass(frozen=True)
class ContextScope:
    """裁剪结果：可见表、每张表的可见列、被脱敏的列。"""

    tables: tuple[str, ...]
    columns: dict[str, tuple[str, ...]]
    masked: dict[str, tuple[str, ...]]
    restricted: bool


async def build_context_scope(
    principal: Principal | None,
    tables: list[str],
    columns_by_table: dict[str, list[str]],
) -> ContextScope:
    """按主体策略裁剪表与列。

    参数:
    - principal: 主体；`None`（后台/评测等）时不做裁剪，保持旧行为。
    - tables: 候选表名（通常是检索命中的表）。
    - columns_by_table: 表 -> 列名列表。

    返回:
    - ContextScope: 可见表与列；`restricted=False` 表示没有发生裁剪。
    """
    all_tables = tuple(tables)
    all_cols = {t: tuple(columns_by_table.get(t) or ()) for t in tables}
    empty = ContextScope(tables=all_tables, columns=all_cols, masked={}, restricted=False)

    if principal is None or principal.is_superuser:
        return empty

    # 延迟导入：避免 service <-> policy 的循环依赖
    from app.plugin.module_ai.query.policy import engine, repo

    policies = await repo.list_policies()
    if not policies:
        # 没有任何策略时与 legacy 语义一致：不裁剪（执行期默认拒绝由 guard 负责）
        return empty

    domains = await repo.domain_codes_for_user(principal.user_id)
    if domains:
        principal = dataclasses.replace(
            principal, attrs={**principal.attrs, "domains": ",".join(domains)}
        )

    kept: list[str] = []
    cols_out: dict[str, tuple[str, ...]] = {}
    masked_out: dict[str, tuple[str, ...]] = {}
    restricted = False
    for table in tables:
        decision = engine.decide_table(policies, principal, table)
        if not decision.permit:
            restricted = True
            continue
        kept.append(table)
        visible: list[str] = []
        masked: list[str] = []
        for col in columns_by_table.get(table) or []:
            cd = engine.decide_column(policies, principal, table, col)
            if not cd.permit:
                restricted = True
                continue
            visible.append(col)
            if any("mask" in a for a in cd.applied):
                masked.append(col)
                restricted = True
        cols_out[table] = tuple(visible)
        if masked:
            masked_out[table] = tuple(masked)

    return ContextScope(
        tables=tuple(kept),
        columns=cols_out,
        masked=masked_out,
        restricted=restricted or len(kept) != len(tables),
    )


def scope_signature(principal: Principal | None) -> str:
    """上下文缓存 key 的主体指纹：不同主体不能复用同一份提示词。"""
    if principal is None:
        return ""
    roles = ",".join(sorted(principal.roles))
    attrs = ",".join(f"{k}={v}" for k, v in sorted(principal.attrs.items()))
    return f"{principal.user_id}|{roles}|{attrs}"
