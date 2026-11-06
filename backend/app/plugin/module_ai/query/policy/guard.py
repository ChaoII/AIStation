"""唯一网关 QueryGuard：所有问数入口的权限判定都只走 ``prepare``。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §7/§10。

调用方式（T7 接线，各入口只换 ``entry``）::

    decision = await prepare(sql=sql, principal=principal, entry="ask",
                             datasource=ds, legacy_check=legacy)
    if not decision.permit:
        raise CustomException(decision.reason)
    # ⚠️ P1 不做 SQL 改写：decision.sql 恒为空串，**不要**用它覆盖原 SQL。
    #    行/列改写由 T9 编译器产出，届时这里才变成 ``sql = decision.sql``。

三种开关（``POLICY_ENGINE``，读 ``AiQueryService._cfg()``，缺失/未知按 ``legacy``）：

| 值 | 行为 |
|---|---|
| ``legacy`` | 只做「无主体拒绝 + 星号止血 + 审计」，结论来自调用方 ``legacy_check``；**不读策略、不跑引擎** |
| ``shadow`` | 新旧都算；**旧结论生效**；结论不同（或改写不同）时写 ``ai_policy_shadow_diff`` |
| ``enforce`` | 新引擎结论生效（表级默认拒绝） |

四条硬约定（评审关注点，别改动语义）：

1. **无主体一律拒绝**：``principal is None`` → ``reason="missing principal"``，审计照写
   （``user_id`` 为 NULL，不伪造 0/匿名）。禁止 ``auth=None`` 落到 permit（P0 验收）。
2. **星号止血对三种模式都生效**：先跑 ``star.unexpanded_star``，命中敏感表即拒。
   即使 ``POLICY_ENGINE=legacy`` 也不能放行 —— 否则"切了开关才安全"，P0 等于没做。
   顺序上星号判定排在 ``legacy_check`` **之前**：旧判定放行的查询也不能带着敏感星号过去。
3. **失败语义分两种**：策略/域/敏感表清单**加载失败 → deny**（fail-closed）；
   审计写入由 ``audit`` 保证 fail-open（本模块**不再**包 try/except 吞它）；
   shadow 差异写入失败 → 只 warning（灰度期不能因为诊断表写不进去把线上查询搞挂）。
4. **域成员以库为准**：``principal.attrs["domains"]`` 由 ``repo.domain_codes_for_user``
   覆盖填充（逗号串），调用方传入的值不作数（防伪造域）。

P1 的判定粒度**只到表级**（不含 SQL 改写，列级/改写留给 T9 编译器）：

- 用 ``AiQueryService._sql_query_scope`` 取涉及的表，逐表 ``engine.decide_table``；
- 任一表拒绝 → 整体 deny，reason 带表名与策略 id；
- 全部放行 → permit，``sql=""``、``applied=()``（还没改写能力，绝不能假装改了）。

已知边界（P1，写在明处）：

- ``_sql_query_scope`` 用 ``sqlglot`` 的 ``find_all(Table)``，**会把 CTE 名也当成表**
  （``with x as (...) select * from x`` 里的 ``x``）→ enforce 下可能误拒。这正是
  shadow 阶段存在的意义：先看差异再切开关，T9 编译器按作用域重写后消失；
- 判定不缓存：每次都是「读策略 + 逐表判定」，量大后再引入带 ``scope_hash`` 的缓存（spec §9）。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.database import async_db_session_fresh
from app.core.logger import log

from .audit import sql_hash, sql_preview, write_access_log
from .engine import Decision, decide_table
from .model import sensitive_tables
from .repo import domain_codes_for_user, list_policies
from .star import unexpanded_star

if TYPE_CHECKING:  # 运行时不依赖 principal（它要连库），避免无谓的导入链
    from .principal import Principal

__all__ = ["prepare"]

#: 三态开关取值（与 spec §10 一致）。
_MODES = ("legacy", "shadow", "enforce")

#: shadow 差异写入（列宽见 ``policy.model`` 的 DDL）。
_INSERT_SHADOW_SQL = (
    "INSERT INTO ai_policy_shadow_diff"
    "(sql_hash, user_id, entry, legacy_decision, new_decision, diff_kind, "
    "policy_ids, sql_preview) "
    "VALUES(:h, :uid, :entry, :legacy, :new, :kind, :pids, :prev)"
)


# ---------------------------------------------------------------------------
# 开关
# ---------------------------------------------------------------------------
def _mode_from_cfg(cfg: dict | None) -> str:
    """配置字典 → 判定模式；缺失/空/未知一律 ``legacy``。

    未知值**回退 legacy 而不是 deny**：这是运维手滑（如 ``enforc``），不是安全事件；
    回退旧逻辑保证可用性，同时打一条 warning 让人看见。真正的失败语义
    （读不到配置 / 读不到策略）才 fail-closed。
    """
    raw = str((cfg or {}).get("policy_engine") or "").strip().lower()
    if raw in _MODES:
        return raw
    if raw:
        log.warning(f"[问数权限] POLICY_ENGINE={raw!r} 不认识，按 legacy 处理")
    return "legacy"


async def _engine_mode() -> str:
    """读进程内缓存的工程配置（``AiQueryService._cfg()``，T7 前只用于取开关）。

    函数内导入 ``service``：``service`` 会反向依赖 ``policy`` 子包，模块级导入成环。
    """
    from ..service import AiQueryService

    return _mode_from_cfg(await AiQueryService._cfg())


# ---------------------------------------------------------------------------
# 查询结构
# ---------------------------------------------------------------------------
async def _tables_of(sql: str) -> set[str]:
    """查询涉及的**表名**集合（复用既有解析器，P1 只做表级判定）。

    ``_sql_query_scope`` 解析失败会正则兜底（不放过），因此这里拿到的可能是
    正则猜出来的名字；真正的 fail-closed 兜底在 :func:`_new_decision`（空表集合时
    再确认一次语法能否解析）。
    """
    from ..service import AiQueryService

    tables, _columns = await AiQueryService._sql_query_scope(sql)
    return {str(t) for t in tables if t}


def _parsable(sql: str, dialect: str) -> bool:
    """SQL 能否被 sqlglot 解析出语法树（用于区分「无表」与「解析失败」）。"""
    try:
        import sqlglot
    except Exception:  # noqa: BLE001 - 依赖缺失按不可解析处理（fail-closed）
        return False
    try:
        trees = sqlglot.parse(sql, read=dialect)
    except Exception:  # noqa: BLE001
        return False
    return bool(trees) and all(tree is not None for tree in trees)


# ---------------------------------------------------------------------------
# 星号止血（三种模式共用）
# ---------------------------------------------------------------------------
async def _star_deny(sql: str, dialect: str) -> Decision | None:
    """敏感表 + 未展开星号 → 拒绝；无风险返回 ``None``。

    读取敏感表清单失败也拒绝（fail-closed）：判断不了有没有敏感列，就不能放行
    ``select *``——这正是 P0 要堵的那个洞。

    快路径：SQL 文本里根本没有 ``*`` 字符时，不可能存在未展开星号，直接放行
    （省掉每次问数一条 ``ai_query_asset_columns`` 查询；星号只能以字面 ``*`` 出现）。
    """
    if "*" not in (sql or ""):
        return None
    try:
        sensitive = await sensitive_tables()
        hit = unexpanded_star(sql, sensitive, dialect)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[问数权限] 敏感表清单读取失败（按拒绝处理）: err={e}")
        return Decision(False, f"敏感表清单读取失败，按拒绝处理（fail-closed）：{e}")

    if not hit:
        return None
    if hit == "*":
        # star 模块的约定：解析失败/无法判定返回 "*"，调用方必须拒绝
        return Decision(
            False, "查询中的星号无法安全解析，按拒绝处理（fail-closed，P0 止血）"
        )
    return Decision(
        False, f"敏感表 {hit} 上使用了未展开的星号（*），已拒绝（P0 止血）"
    )


# ---------------------------------------------------------------------------
# 旧判定 / 新判定
# ---------------------------------------------------------------------------
async def _legacy_decision(
    legacy_check: Callable[[], Awaitable[Decision]] | None,
) -> Decision:
    """调用方传入的旧判定；未提供视为放行（T7 接线前的过渡态）。

    **不包 try/except**：legacy 模式必须与改造前行为一致，旧判定抛的异常照旧上抛，
    网关不能把自定义错误码/提示吞成一条笼统的 deny。
    """
    if legacy_check is None:
        return Decision(True, "legacy：未提供旧判定（默认放行）")
    result = await legacy_check()
    if result is None:
        return Decision(True, "legacy：旧判定未给出结论（默认放行）")
    return result


async def _with_domains(principal: Principal) -> Principal:
    """把用户的数据域 code 填进 ``attrs["domains"]``（逗号串）。

    引擎的 ``domain`` 主体读 ``attrs["domains"]`` / ``attrs["domain"]``，不填就永远
    不命中（T8 迁移后表现为大面积拒答）。**覆盖**调用方传入的值：域成员的唯一事实
    来源是 ``ai_data_domain.members``，调用方塞进来的不能当真。
    """
    codes = await domain_codes_for_user(getattr(principal, "user_id", None))
    attrs = dict(getattr(principal, "attrs", None) or {})
    attrs["domains"] = ",".join(codes)
    return replace(principal, attrs=attrs)


class _PolicyLoadError(RuntimeError):
    """策略/域/表结构读取失败：新判定做不出来（fail-closed 由调用方落地）。"""


async def _new_decision(
    *, sql: str, principal: Principal | None, dialect: str
) -> Decision:
    """新引擎判定（表级）：逐表 ``decide_table``，任一拒绝即整体拒绝。

    超管先短路：引擎本来就会绕过，提前返回能省掉「读策略 + 读域」两次查询。

    策略/域读不到时抛 :class:`_PolicyLoadError`（已在内部 warning）：``enforce`` 据此
    deny，``shadow`` 据此**不写差异** —— 把"库坏了"记成"新引擎要拒这批用户"会污染
    灰度报告，比不记录更糟。
    """
    if principal is None:
        return Decision(False, "missing principal")
    if getattr(principal, "is_superuser", False):
        return Decision(True, "superuser bypass")

    try:
        policies = await list_policies()
        principal = await _with_domains(principal)
        tables = await _tables_of(sql)
    except Exception as e:  # noqa: BLE001
        # fail-closed：策略/域读不到就无法证明"该放行"，只能拒
        log.warning(f"[问数权限] 策略加载失败（按拒绝处理）: err={e}")
        raise _PolicyLoadError(f"策略加载失败，按拒绝处理（fail-closed）：{e}") from e

    if not tables:
        # 没有表可判定：语法能解析 = 真的不涉及表（如 select 1），放行；
        # 解析不出语法树 = 认不出查询结构，按 fail-closed 拒绝（spec §5.6）。
        if _parsable(sql, dialect):
            return Decision(True, "查询未涉及任何表，无表级策略可判定")
        return Decision(False, "无法解析查询语句，按拒绝处理（fail-closed）")

    policy_ids: list[int] = []
    for table in sorted(tables):
        d = decide_table(policies, principal, table)
        if not d.permit:
            reason = f"表 {table} 拒绝：{d.reason}"
            if d.policy_ids and "policy_ids" not in reason:
                reason += f"（policy_ids={list(d.policy_ids)}）"
            return Decision(False, reason, d.policy_ids)
        policy_ids.extend(d.policy_ids)

    return Decision(
        True,
        f"新引擎放行：{len(tables)} 张表均通过表级判定",
        tuple(dict.fromkeys(policy_ids)),
    )


# ---------------------------------------------------------------------------
# shadow 差异
# ---------------------------------------------------------------------------
def _diff_kind(*, legacy_decision: Decision, new_decision: Decision) -> str | None:
    """新旧结论的差异类型；``None`` = 没差异（不写表）。

    三种 kind 与 DDL 注释一致：``legacy_permit_new_deny`` / ``legacy_deny_new_permit``
    / ``rewrite_only``。P1 新引擎还不生成改写，因此 ``rewrite_only`` 只会在
    「旧判定自带 sql/applied 而新判定为空」时出现（T9 之后才成为常态）。
    """
    if legacy_decision.permit and not new_decision.permit:
        return "legacy_permit_new_deny"
    if not legacy_decision.permit and new_decision.permit:
        return "legacy_deny_new_permit"
    if legacy_decision.permit and new_decision.permit:
        if (legacy_decision.sql or "") != (new_decision.sql or "") or tuple(
            legacy_decision.applied
        ) != tuple(new_decision.applied):
            return "rewrite_only"
    return None


def _clip(value, limit: int) -> str:
    """按列宽截断（PG 的 ``VARCHAR(n)`` 超长会整条写失败）。"""
    return str(value or "")[:limit]


async def _record_shadow_diff(
    *,
    sql: str,
    principal: Principal | None,
    entry: str,
    legacy: Decision,
    new: Decision,
) -> None:
    """把新旧差异写进 ``ai_policy_shadow_diff``（**fail-open**）。

    用独立会话（``async_db_session_fresh``）：请求随后回滚也不能把差异一起丢掉；
    反过来，写失败只 warning —— shadow 是诊断能力，不能影响查询（旧结论已定）。
    """
    kind = _diff_kind(legacy_decision=legacy, new_decision=new)
    if not kind:
        return
    try:
        params = {
            "h": sql_hash(sql),
            "uid": getattr(principal, "user_id", None),
            "entry": _clip(entry, 32),
            "legacy": "permit" if legacy.permit else "deny",
            "new": "permit" if new.permit else "deny",
            "kind": _clip(kind, 32),
            # 落新引擎参与裁决的策略 id（到期复盘"是哪条策略翻的案"）
            "pids": "[" + ", ".join(str(int(i)) for i in new.policy_ids) + "]",
            "prev": sql_preview(sql),
        }
        async with async_db_session_fresh() as db:
            async with db.begin():
                await db.execute(text(_INSERT_SHADOW_SQL), params)
    except Exception as e:  # noqa: BLE001 - shadow 写失败不能拖垮线上
        log.warning(f"[问数权限] shadow 差异写入失败（已忽略，不影响查询）: err={e}")


# ---------------------------------------------------------------------------
# 对外唯一入口
# ---------------------------------------------------------------------------
async def prepare(
    *,
    sql: str,
    principal: Principal | None,
    entry: str,
    datasource: str,
    dialect: str = "postgres",
    legacy_check: Callable[[], Awaitable[Decision]] | None = None,
) -> Decision:
    """唯一判定入口：返回放/拒 + （将来的）改写；**内部统一写审计**。

    参数口径：

    - ``entry``：入口标记（ask/agent/app/workflow/cron/report/metric/object/export/eval），
      审计与 shadow 都用它；
    - ``datasource``：数据源标识（审计字段，不参与判定）；
    - ``dialect``：sqlglot 读方言，与 ``service.py`` 一致（默认 postgres）；
    - ``legacy_check``：旧判定（T7 传 ``validate_sql`` + ``_ont_sql_violations`` 组合）；
      ``None`` 视为旧判定放行，仅在 ``legacy`` / ``shadow`` 下会被调用。

    审计写入**不在 try/except 里**：``audit.write_access_log`` 自身保证 fail-open
    （评审裁决：不要在这里重复吞异常，否则真出问题连 warning 都看不到）。
    """
    started = time.perf_counter()

    if principal is None:
        decision = Decision(False, "missing principal")
    else:
        decision = await _prepare(
            sql=sql,
            principal=principal,
            entry=entry,
            dialect=dialect,
            legacy_check=legacy_check,
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    await write_access_log(
        principal=principal,
        entry=entry,
        datasource=datasource,
        sql=sql,
        decision="permit" if decision.permit else "deny",
        reason=decision.reason,
        policy_ids=list(decision.policy_ids),
        rewrite=list(decision.applied),
        elapsed_ms=elapsed_ms,
    )
    return decision


async def _prepare(
    *,
    sql: str,
    principal: Principal,
    entry: str,
    dialect: str,
    legacy_check: Callable[[], Awaitable[Decision]] | None,
) -> Decision:
    """三态编排（无主体已在 ``prepare`` 里短路）。"""
    # ① 星号止血：三种模式都先跑（顺序在旧判定之前，见模块 docstring 第 2 条）
    star = await _star_deny(sql, dialect)
    if star is not None:
        return star

    # ② 开关：读不到配置就无法保证合规 → fail-closed
    try:
        mode = await _engine_mode()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[问数权限] 读取 POLICY_ENGINE 失败（按拒绝处理）: err={e}")
        return Decision(False, f"无法读取判定开关，按拒绝处理（fail-closed）：{e}")

    # ③ legacy：完全不碰策略/引擎
    if mode == "legacy":
        return await _legacy_decision(legacy_check)

    # ④ enforce：新引擎结论生效
    if mode == "enforce":
        try:
            return await _new_decision(sql=sql, principal=principal, dialect=dialect)
        except _PolicyLoadError as e:
            return Decision(False, str(e))

    # ⑤ shadow：新旧都算，旧结论生效，差异落表（写失败 fail-open）
    legacy = await _legacy_decision(legacy_check)
    try:
        new = await _new_decision(sql=sql, principal=principal, dialect=dialect)
    except _PolicyLoadError as e:
        # 新引擎这轮判断不出来：不写差异（否则灰度报告会全是"库坏了"的假差异）
        log.warning(f"[问数权限] shadow 新判定不可用，本轮跳过差异记录: {e}")
        return legacy

    # 没差异就不进写函数：既省一次会话，也让「是否产生差异」这件事在编排层可测
    if _diff_kind(legacy_decision=legacy, new_decision=new):
        await _record_shadow_diff(
            sql=sql, principal=principal, entry=entry, legacy=legacy, new=new
        )
    return legacy
