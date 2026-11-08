"""唯一网关 QueryGuard：所有问数入口的权限判定都只走 ``prepare``。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §7/§10。

调用方式（T7 接线，各入口只换 ``entry``）::

    decision = await prepare(sql=sql, principal=principal, entry="ask",
                             datasource=ds, legacy_check=legacy)
    if not decision.permit:
        raise CustomException(decision.reason)
    # enforce 下 decision.sql 是**编译后的可执行 SQL**（行过滤 + 列投影/掩码）；
    # legacy / shadow 下它为空（执行原 SQL），调用方按「非空才用」处理。

三种开关（``POLICY_ENGINE``，读 ``AiQueryService._cfg()``，缺失/未知按 ``legacy``）：

| 值 | 行为 |
|---|---|
| ``legacy`` | 只做「无主体拒绝 + 星号止血 + 审计」，结论来自调用方 ``legacy_check``；**不读策略、不跑引擎** |
| ``shadow`` | 新旧都算；**旧结论生效**；结论不同（或改写不同）时写 ``ai_policy_shadow_diff`` |
| ``enforce`` | 新引擎判定 + **SQL 编译改写**；执行方（``_execute_one``）用 ``decision.sql`` |

``enforce`` 的判定链（任何一步失败一律 deny，不抛、不降级放行）：

1. 读策略 + 主体（含数据域）→ 查询涉及的真实表；
2. 读列元数据（``policy.model.table_columns``；系统库 / 自定义源各走各的）；
3. **视图**（有 ``resource_kind=view`` 策略的表）按血缘做**单层**映射
   （``views.resolve_view_policies``）；映射不到就拒绝，不伪造过滤；
4. ``compiler.build_plan`` → ``compiler.rewrite``；编译拒绝（含解析失败、
   条件/掩码不合法、表未被策略覆盖）都转成 ``Decision(False, ...)``；
5. 放行时 ``decision.sql`` 是**可执行 SQL**（行过滤已下推、掩码已投影替换），
   ``decision.applied`` 是**实际施加**的改写（审计与 shadow 都读它）。

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

判定粒度（enforce）：

- 用 ``AiQueryService._sql_query_scope`` 取涉及的表，读列元数据后交给编译器；
- 编译器按作用域识别真实表，逐表下推行条件、逐列施加 deny/mask；
- 任一表/列被拒 → 整体 deny，reason 带表名/列名与策略 id；
- 列表级策略（``condition`` / ``mask_expr``）在编译期生效，执行的是编译后的 SQL。

已知边界（写在明处）：

- ``_sql_query_scope`` 用 ``sqlglot`` 的 ``find_all(Table)``，**会把 CTE 名也当成表**
  （``with x as (...) select * from x`` 里的 ``x``）→ enforce 下可能误拒（fail-closed，
  不会放行未覆盖的表）；
- 视图只做**单层**血缘映射（``lineage_for_table`` 的 ``kind=view`` 上游），不做递归；
- 判定不缓存：每次都是「读策略 + 逐表判定」，量大后再引入带 ``scope_hash`` 的缓存（spec §9）。
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.database import async_db_session_fresh
from app.core.logger import log

from .audit import sql_hash, sql_preview, write_access_log
from .compiler import DENIED_ALL, AccessPlan, build_plan, rewrite
from .engine import (
    Decision,
    _table_key,
    matched_policies,
)
from .model import sensitive_tables, table_columns
from .repo import domain_codes_for_user, list_policies
from .star import unexpanded_star
from .views import resolve_view_policies

if TYPE_CHECKING:  # 运行时不依赖 principal（它要连库），避免无谓的导入链
    from .principal import Principal

__all__ = ["prepare"]

#: 三态开关取值（与 spec §10 一致）。
_MODES = ("legacy", "shadow", "enforce")

#: shadow 差异写入（列宽见 ``policy.model`` 的 DDL）。
_INSERT_SHADOW_SQL = (
    "INSERT INTO ai_policy_shadow_diff"
    "(sql_hash, user_id, entry, legacy_decision, new_decision, diff_kind, "
    "policy_ids, sql_preview, rewrite) "
    "VALUES(:h, :uid, :entry, :legacy, :new, :kind, :pids, :prev, :rw)"
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
async def _tables_of(sql: str, dialect: str = "postgres") -> set[str]:
    """查询涉及的**表名**集合（按数据源方言解析）。

    MySQL 的反引号 / SQLite 的方括号只有用对应 dialect 读才认得；固定 postgres
    会解析失败 → 表集合为空 → 跳过整条编译链路（Step 1 复审 C1 的 fail-open）。
    """
    from ..service import AiQueryService

    tables, _columns = await AiQueryService._sql_query_scope(sql, dialect)
    return {str(t) for t in tables if t}


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


async def _view_fragment(
    table: str, datasource: str, policies, principal
) -> AccessPlan | None:
    """表是**视图**时，按血缘从基表策略推导一份补充计划（单层）。

    「是不是视图」**以血缘为准**（上游存在 ``kind=view`` 边），不看
    ``resource_kind`` —— 管理员可能只给基表配策略、视图名也没建策略，靠 view 类型
    推断会漏掉整段映射。表名统一走 ``_table_key``（大小写/schema 不敏感）：
    本库真实表名是大写，直接用原始大小写比较会让 ``FROM "V"`` 静默跳过（C2）。

    血缘读取失败**上抛**（enforce 转 deny）：不能把"读不到"当成"没有上游"。
    基表策略先按主体过滤（``matched_policies``）再交给 ``resolve_view_policies``
    —— 那个函数的契约是"已按主体筛过"。
    """
    table_key = _table_key(table)
    if not table_key:
        return None

    from .. import service as _svc
    from ..lineage import lineage_for_table

    ds = str(datasource or "").strip()
    if not ds or ds == "system":
        # 系统库的血缘按「表所属数据源」存（实测是 ds:4）；查不到就退回原值。
        try:
            ds = await _svc.AiQueryService._table_ds_code(table) or ds
        except Exception as e:  # noqa: BLE001 - 血缘不可用不能拖垮判定
            log.warning(f"[问数权限] 读取表所属数据源失败（血缘降级）: {e}")

    payload = await lineage_for_table(ds or "system", table.upper(), strict=True)
    entries = [
        item
        for item in (payload.get("upstream") or [])
        if str(item.get("kind") or "").lower() == "view" and item.get("table")
    ]
    if not entries:
        return None

    base_tables: list[str] = []
    for item in entries:
        base = _table_key(item.get("table"))
        if base and base not in base_tables:
            base_tables.append(base)

    candidates = []
    for base in base_tables:
        candidates.extend(matched_policies(policies, principal, base))
    fragment, _tier = resolve_view_policies(table_key, {table_key: entries}, candidates)
    return fragment


def _merge_plan(plan: AccessPlan, fragment: AccessPlan | None) -> AccessPlan:
    """把视图补充片段叠加到视图自身的计划上（只收紧、不放宽）。

    - ``denied``：并集（``DENIED_ALL`` 天然覆盖全表）；
    - ``row_filters``：两边都有时 ``AND`` 连接（都通过编译期白名单校验）；
    - ``allowed_columns``：取交集（``None`` = 无元数据，保持未知，不冒进展开）；
    - ``masked``：同一列不同掩码 → 无法判定，整表拒绝。
    """
    if fragment is None:
        return plan

    row_filters = dict(plan.row_filters)
    for table, condition in (fragment.row_filters or {}).items():
        if not condition:
            continue
        current = row_filters.get(table)
        row_filters[table] = (
            f"({current}) AND ({condition})" if current else condition
        )

    allowed_columns = dict(plan.allowed_columns)
    for table, columns in (fragment.allowed_columns or {}).items():
        if columns is None or table not in allowed_columns:
            continue
        current = allowed_columns[table]
        if current is None:
            continue
        keep = {str(c).lower() for c in columns}
        allowed_columns[table] = tuple(c for c in current if str(c).lower() in keep)

    masked: dict[str, dict[str, str]] = {
        table: dict(items) for table, items in (plan.masked or {}).items()
    }
    denied: dict[str, set[str]] = {
        table: set(items) for table, items in (plan.denied or {}).items()
    }
    for table, items in (fragment.masked or {}).items():
        current = masked.setdefault(table, {})
        for column, expr in items.items():
            if column in current and current[column] != expr:
                denied.setdefault(table, set()).add(DENIED_ALL)
            else:
                current[column] = expr
    for table, items in (fragment.denied or {}).items():
        denied.setdefault(table, set()).update(items)

    policy_ids = tuple(dict.fromkeys((*plan.policy_ids, *fragment.policy_ids)))
    return AccessPlan(
        row_filters=row_filters,
        allowed_columns=allowed_columns,
        masked=masked,
        denied={table: frozenset(items) for table, items in denied.items()},
        policy_ids=policy_ids,
        deny_reason=plan.deny_reason or fragment.deny_reason,
    )


async def _new_decision(
    *, sql: str, principal: Principal | None, dialect: str, datasource: str = "system"
) -> Decision:
    """新引擎判定：策略 + 列元数据 → 访问计划 → **编译后的可执行 SQL**。

    超管先短路：引擎本来就会绕过，提前返回能省掉「读策略 + 读域 + 读元数据」几轮查询。

    策略/域/元数据读不到时抛 :class:`_PolicyLoadError`（已在内部 warning）：
    ``enforce`` 据此 deny，``shadow`` 据此**不写差异** —— 把"库坏了"记成
    "新引擎要拒这批用户"会污染灰度报告，比不记录更糟。

    编译拒绝（解析失败 / 非 SELECT / 条件或掩码不合法 / 表未被计划覆盖）本身是
    ``Decision(False, ...)``，不抛异常；这里统一把 ``plan.policy_ids`` 带出去，
    便于审计追问"是哪条策略拒的"。
    """
    if principal is None:
        return Decision(False, "missing principal")
    if getattr(principal, "is_superuser", False):
        # 超管不受策略约束，但仍返回 SQL：执行侧要照常补 `validate_sql`
        # （只读/单语句/LIMIT），不能因为"旁路"就跳过只读检查。
        return Decision(True, "superuser bypass", sql=sql)

    try:
        policies = await list_policies()
        principal = await _with_domains(principal)
        tables = await _tables_of(sql, dialect)
        # enforce 的元数据必须 strict：读不到 ≠ 没有列级限制（C3 fail-open）
        columns = await table_columns(datasource, tables, strict=True) if tables else {}
    except Exception as e:  # noqa: BLE001
        # fail-closed：策略/域/元数据读不到就无法证明"该放行"，只能拒
        log.warning(f"[问数权限] 策略加载失败（按拒绝处理）: err={e}")
        raise _PolicyLoadError(f"策略加载失败，按拒绝处理（fail-closed）：{e}") from e

    # 元数据键按真实大小写，SQL 里的表名大小写不保证一致 → 大小写不敏感对齐
    lookup = {str(name).lower(): cols for name, cols in (columns or {}).items()}
    metadata = {table: lookup.get(str(table).lower(), []) for table in tables}

    # ⚠️ 不再有「取不到表就直接放行」的捷径：一律走 build_plan + rewrite。
    # 空表计划会让 `select 1` 正常放行，而 Command/非 SELECT/多语句由 rewrite 拒绝
    # （C1：否则 `vacuum` / MySQL 反引号取不到表时会跳过整条只读/列策略检查）。
    plan = build_plan(policies, principal, metadata)

    # 视图：单层血缘映射（失败/映射不到时由编译器的「表不在计划内/整表拒绝」兜底；
    # 血缘读取失败会抛异常 → 上面/调用方按 deny 处理）
    for table in sorted(tables):
        fragment = await _view_fragment(table, datasource, policies, principal)
        if fragment is not None:
            plan = _merge_plan(plan, fragment)

    decision = rewrite(sql, plan, dialect=dialect)
    if not decision.permit:
        reason = decision.reason
        if plan.policy_ids and not any(
            str(pid) in reason for pid in plan.policy_ids
        ):
            reason += f"（policy_ids={list(plan.policy_ids)}）"
        return Decision(False, reason, plan.policy_ids)
    return Decision(
        True,
        decision.reason,
        plan.policy_ids,
        decision.sql,
        decision.applied,
    )


# ---------------------------------------------------------------------------
# shadow 差异
# ---------------------------------------------------------------------------
def _diff_kind(*, legacy_decision: Decision, new_decision: Decision) -> str | None:
    """新旧结论的差异类型；``None`` = 没差异（不写表）。

    三种 kind 与 DDL 注释一致：``legacy_permit_new_deny`` / ``legacy_deny_new_permit``
    / ``rewrite_only``。``rewrite_only`` 覆盖两种情况：

    - 两边都放行但**新引擎多出/改变了改写**（``applied`` 不同）—— T9 之后这就是
      "用户的行被静默藏掉"这类变更，必须被 shadow 抓到；
    - 两边都放行且改写不同（T9 起常见）。

    ⚠️ 只比较 ``applied``，**不比较整条 SQL 文本**：enforce 产出的编译 SQL 必然
    与原 SQL 有格式差异（引号/函数大小写），拿它比会让每一条查询都变成
    ``rewrite_only``，差异表被噪声灌满、真正的"多了一层过滤"反而看不见。
    旧逻辑不产出改写（``applied=()``），所以只要新引擎真的施加了改写就记录。
    """
    if legacy_decision.permit and not new_decision.permit:
        return "legacy_permit_new_deny"
    if not legacy_decision.permit and new_decision.permit:
        return "legacy_deny_new_permit"
    if legacy_decision.permit and new_decision.permit:
        if tuple(legacy_decision.applied) != tuple(new_decision.applied):
            return "rewrite_only"
    return None


def _clip(value, limit: int) -> str:
    """按列宽截断（PG 的 ``VARCHAR(n)`` 超长会整条写失败）。"""
    return str(value or "")[:limit]


def _json_array(value) -> str:
    """追加写 jsonb 列：序列化成 JSON 文本（与 ``audit`` 同口径）。

    失败退回 ``"[]"``：差异行本身的"谁/哪条 SQL/什么结论"更重要，不能因为某个
    表达式节点不可序列化就整条丢掉。
    """
    try:
        return json.dumps(list(value or ()), ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return "[]"


def _shadow_rewrite(new: Decision) -> list[dict]:
    """新引擎本次**实际施加**的改写清单（``{"row": ...}`` / ``{"mask": ...}``）。

    只读 ``applied``：enforce 的编译结果里 ``sql`` 是整条可执行 SQL，把它塞进
    ``rewrite`` 会让 ``rewrite_only`` 差异只剩一句"整条 SQL 变了"，失去解释力；
    没有改写就是空数组（与审计同一口径）。
    """
    return [dict(item) for item in new.applied]


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
            # 新增的行过滤/掩码：rewrite_only 差异的解释全靠这一列
            "rw": _json_array(_shadow_rewrite(new)),
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
    compile_sql: str | None = None,
    legacy_check: Callable[[], Awaitable[Decision]] | None = None,
) -> Decision:
    """唯一判定入口：返回放/拒 + （enforce 下的）可执行 SQL；**内部统一写审计**。

    参数口径：

    - ``entry``：入口标记（ask/agent/app/workflow/cron/report/metric/object/export/eval），
      审计与 shadow 都用它；
    - ``datasource``：数据源标识（审计字段，不参与判定）；
    - ``dialect``：sqlglot 读方言，与 ``service.py`` 一致（默认 postgres）；
    - ``compile_sql``：**编译器输入**。系统库传「本体安全改写后的 SQL」——这样
      编译器产出的 SQL 里同时含本体行过滤与策略行过滤，执行侧不用再套一次
      ``_secure_ont_sql``（避免二次改写把带引号表名漏掉）。为空时退回 ``sql``；
      审计/星号止血仍用**原始** ``sql``（legacy 行为不变）；
    - ``legacy_check``：旧判定（T7 传 ``validate_sql`` + ``_ont_sql_violations`` 组合）；
      ``None`` 视为旧判定放行，仅在 ``legacy`` / ``shadow`` 下会被调用。

    审计写入**不在 try/except 里**：``audit.write_access_log`` 自身保证 fail-open
    （评审裁决：不要在这里重复吞异常，否则真出问题连 warning 都看不到）。

    唯一例外是**判定过程抛异常**（T7 评审 Important）：``legacy_check`` 里的白名单校验 /
    ``_allowed_for_user`` / 字段级 ACL 都可能抛 ``CustomException``，异常会直接穿出
    ``_prepare``。若不在那里补一条审计，这些**拒绝**一条痕迹都没有（审计成了"只有放行
    和引擎判定才有记录"）。处置：写一条 ``deny``（reason 带异常类型与摘要）后**原样
    re-raise** —— 异常类型/文案是调用方与前端依赖的，绝不能被替换或吞掉。
    """
    started = time.perf_counter()

    if principal is None:
        # 无用户身份（定时任务/嵌入聊天）→ 看是否配置了服务主体；没配就拒绝
        principal = await _service_principal(entry)
    if principal is None:
        decision, applied = Decision(False, "missing principal"), []
    else:
        try:
            decision, applied = await _prepare(
                sql=sql,
                principal=principal,
                entry=entry,
                datasource=datasource,
                dialect=dialect,
                compile_sql=compile_sql,
                legacy_check=legacy_check,
            )
        except Exception as exc:  # noqa: BLE001 - CancelledError 是 BaseException，不捕
            # 先落"判定异常"这条 deny 审计，再把**原异常**原样抛出。
            # 审计自身若再抛（正常实现不会，它内部已 fail-open），也只 warning：
            # 审计设施的问题不能顶替掉真正的判定异常，否则调用方看到的是假错误。
            elapsed_err = int((time.perf_counter() - started) * 1000)
            try:
                await write_access_log(
                    principal=principal,
                    entry=entry,
                    datasource=datasource,
                    sql=sql,
                    decision="deny",
                    reason=f"判定异常：{type(exc).__name__}: {exc}",
                    policy_ids=[],
                    rewrite=[],
                    elapsed_ms=elapsed_err,
                )
            except Exception as audit_err:  # noqa: BLE001
                log.warning(
                    f"[问数权限] 判定异常时写审计失败（已忽略，原异常照旧抛出）: "
                    f"err={audit_err}"
                )
            raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    await write_access_log(
        principal=principal,
        entry=entry,
        datasource=datasource,
        sql=sql,
        decision="permit" if decision.permit else "deny",
        reason=decision.reason,
        policy_ids=list(decision.policy_ids),
        # 只记**实际施加**的改写：enforce 的编译改写由 ``_prepare`` 带出（applied），
        # legacy / shadow 执行的是原 SQL，所以恒为 ``[]``。
        rewrite=list(applied),
        elapsed_ms=elapsed_ms,
    )
    return decision



async def _service_principal(entry: str):
    """配置了 ``service_principal_user_id`` 时，用它当无身份通道的主体。

    默认空 = 不启用（与 P0「无主体即拒绝」一致）。只给调度/嵌入这类确实没有用户的通道用，
    且仍按该用户**当前**的权限判定（停用/删除即拒绝）。
    """
    try:
        from app.plugin.module_ai.query.service import AiQueryService as S

        cfg = await S._cfg()
        raw = str(cfg.get("service_principal_user_id") or "").strip()
        if not raw:
            return None
        from .principal import load_principal_by_id

        return await load_principal_by_id(int(raw), entry=entry)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[问数权限] 服务主体解析失败（按无主体处理）: {e}")
        return None


async def _prepare(
    *,
    sql: str,
    principal: Principal,
    entry: str,
    datasource: str,
    dialect: str,
    compile_sql: str | None = None,
    legacy_check: Callable[[], Awaitable[Decision]] | None,
) -> tuple[Decision, list[dict]]:
    """三态编排（无主体已在 ``prepare`` 里短路）。

    返回 ``(生效结论, 实际施加的改写)``：第二项只给审计，shadow / legacy 恒为空。
    """
    # ① 星号止血：三种模式都先跑（顺序在旧判定之前，见模块 docstring 第 2 条）
    star = await _star_deny(sql, dialect)
    if star is not None:
        return star, []

    # ② 开关：读不到配置就无法保证合规 → fail-closed
    try:
        mode = await _engine_mode()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[问数权限] 读取 POLICY_ENGINE 失败（按拒绝处理）: err={e}")
        return Decision(False, f"无法读取判定开关，按拒绝处理（fail-closed）：{e}"), []

    # ③ legacy：完全不碰策略/引擎（行为必须与改造前一致）
    if mode == "legacy":
        return await _legacy_decision(legacy_check), []

    # ④ enforce：策略 + 列元数据 → 编译改写；**任何异常都 deny**（不抛、不放行）
    if mode == "enforce":
        try:
            decision = await _new_decision(
                sql=compile_sql or sql,
                principal=principal,
                dialect=dialect,
                datasource=datasource,
            )
        except _PolicyLoadError as e:
            log.warning(f"[问数权限] enforce 策略加载失败（按拒绝处理）: {e}")
            return Decision(False, str(e)), []
        except Exception as e:  # noqa: BLE001 - 编译/引擎异常一律 fail-closed
            log.opt(exception=True).warning(
                f"[问数权限] enforce 判定异常（按拒绝处理）: err={e}"
            )
            return Decision(
                False, f"策略判定失败，按拒绝处理（fail-closed）：{e}"
            ), []
        # C1.3：enforce 放行却没有编译 SQL → 执行原 SQL 会跳过全部改写，必须拒。
        # 显式超管旁路除外（引擎语义：超管不受策略约束，沿用原 SQL）。
        if decision.permit and not decision.sql and not principal.is_superuser:
            log.warning(
                "[问数权限] enforce 放行但编译产物为空（按拒绝处理）："
                f"user_id={principal.user_id}"
            )
            return Decision(
                False,
                "策略引擎未产出可执行 SQL，按拒绝处理（fail-closed；"
                "执行原 SQL 会跳过行/列策略与只读检查）",
                decision.policy_ids,
            ), []
        applied = [dict(item) for item in decision.applied] if decision.permit else []
        return decision, applied

    # ⑤ shadow：新旧都算，旧结论生效，差异落表（写失败 fail-open）
    legacy = await _legacy_decision(legacy_check)
    try:
        new = await _new_decision(
            sql=compile_sql or sql,
            principal=principal,
            dialect=dialect,
            datasource=datasource,
        )
    except _PolicyLoadError as e:
        # 新引擎这轮判断不出来：不写差异（否则灰度报告会全是"库坏了"的假差异）
        log.warning(f"[问数权限] shadow 新判定不可用，本轮跳过差异记录: {e}")
        return legacy, []
    except Exception as e:  # noqa: BLE001
        # 灰度期诊断能力出问题，绝不能把旧逻辑本来放行的查询打成失败。
        # 同样用 ``except Exception``（CancelledError 继续上抛）。
        log.opt(exception=True).warning(
            f"[问数权限] policy engine error（shadow 跳过本轮差异记录）: err={e}"
        )
        return legacy, []

    # 没差异就不进写函数：既省一次会话，也让「是否产生差异」这件事在编排层可测
    if _diff_kind(legacy_decision=legacy, new_decision=new):
        await _record_shadow_diff(
            sql=sql, principal=principal, entry=entry, legacy=legacy, new=new
        )
    return legacy, []
