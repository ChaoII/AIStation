"""旧权限规则迁移（backfill）：把「散落在四张旧表 + 代码兜底」的权限，落成显式 ``ai_policy`` 行。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §4.1。

为什么需要它：新引擎是**默认拒绝**（没有任何 allow 就拒），而存量库的可用性来自
几处"藏在代码里"的旧逻辑（``_system_allowed()`` 的全表白名单、``ai_access_rule`` 的
按角色白名单……）。直接切 enforce 会**把存量用户全锁死**。backfill 的职责就是把这些
旧逻辑搬成显式的、可审计、可删除的 allow 行。

五行映射（与 spec §4.1 逐行对应）：

===========  ===============================================================
旧机制        迁移结果
===========  ===============================================================
数据域        ``allow`` + ``subject_kind=domain``、``subject_value=<域 code>``
ABAC 规则     ``allow`` + ``subject_kind=role``、``subject_value=<角色码>``
敏感列        一条 ``deny``（同表多列合成 ``columns``）+ ``marking=sensitive``
对象行策略    物理表上的 ``allow``（``condition`` 语法对齐后搬迁）
未配置即全表  ``legacy_default_allow``：只给「不在任何数据域、也没有命中角色的
              ABAC 规则」的存量用户，逐表一条 ``subject_kind=user`` 的 allow
===========  ===============================================================

为什么兜底**按用户**而不是 ``everyone``：旧逻辑里「属于某数据域 → 只能查域内表」是
**收紧**，而新模型是 allow 并集。一条 ``everyone`` 的全表 allow 会把域隔离整体抹平 ——
enforce 当天域成员就能查全表，这是**越权**，不能靠"shadow 期人工收窄"兜底。
所以兜底只发给"旧逻辑里本来就未配置 → 全表"的那批人（``subject_kind=user``）。

为什么**每个域/规则按表拆成多行**：``ai_policy`` 一行只有一个 ``resource_code``，
引擎也是逐表匹配（``decide_table``）。一条 allow 覆盖不了表集合 —— 把表清单塞进
``columns`` 更是**错的**：``columns`` 是列，非空时表示"按列额外授予"，会让策略静默失效。

为什么 ``legacy_default_allow`` 的 ``name`` 可以重复：它的唯一性靠
``(resource_code, name)`` 这一对（判重仍走 ``ai_policy_migration``）。名字固定
（brief 要求），方便管理员一条 SQL 找到并整体下线。

三条硬约束：

1. **幂等**：写入 ``ai_policy_migration(source_table, source_id, policy_id)``，
   重复执行按 ``(source_table, source_id)`` 跳过 —— 连跑只加新增的那部分；
2. **不静默**：对象码解析不到物理表、条件里有 ``user.role(...)`` 这类引擎表达不了的
   成分、旧表读不出来……一律进返回值的 ``skipped`` 并 ``log.warning``。
   **绝不**退化成 ``resource_kind=object``（引擎只吃 table/view，等于没迁却看着像迁了）；
3. **dry_run 不写库**：连迁移表都不建（建表也是写），只报"会建多少条"。
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.logger import log

__all__ = [
    "LEGACY_DEFAULT_ALLOW_DESC",
    "LEGACY_DEFAULT_ALLOW_NAME",
    "MIGRATION_TABLE_SQL",
    "SOURCES",
    "backfill_policies",
    "ensure_migration_table",
]

#: 迁移台账：旧行 → 新策略 id。``(source_table, source_id)`` 是幂等键。
#:
#: DDL 照 **PostgreSQL** 写，执行前一律过 ``ddl_for_dialect``（SQLite 测试库翻译
#: ``BIGSERIAL`` / ``DEFAULT now()``），与 ``policy/model.py`` 的约定一致。
#: ``source_id`` 用 VARCHAR：域的粒度是「域 id + 表名」，ABAC 是「规则 id + 表名」，
#: 敏感列是「表名」，行策略是「策略 id」——统一用文本承载，避免加第二张明细表。
MIGRATION_TABLE_SQL = (
    "CREATE TABLE IF NOT EXISTS ai_policy_migration ("
    "id BIGSERIAL PRIMARY KEY, "
    "source_table VARCHAR(64) NOT NULL, "
    "source_id VARCHAR(200) NOT NULL, "
    "policy_id BIGINT, "
    "note VARCHAR(255) DEFAULT '', "
    "created_time TIMESTAMP DEFAULT now(), "
    "UNIQUE(source_table, source_id))"
)

#: 五类来源（``by_source`` 的固定键，含 0）。
SOURCES: tuple[str, ...] = (
    "ai_data_domain",
    "ai_access_rule",
    "ai_query_asset_columns",
    "ai_ont_row_policy",
    "legacy_default_allow",
)

LEGACY_DEFAULT_ALLOW_NAME = "legacy_default_allow"

#: 兜底 allow 的统一说明（控制者裁决第 2 条要求写明"确认后可删除"）。
LEGACY_DEFAULT_ALLOW_DESC = (
    "legacy_default_allow：迁移期兜底，仅限无域/无 ABAC 的存量用户；确认后可删除"
)

#: 兜底 allow 的行数上限：超过就不硬写（先让管理员把域/ABAC 配齐）。
#:
#: 为什么必须有：兜底是「用户 × 表」的笛卡尔积。dev 库 60 余个可查表 × 40 个存量用户
#: 就是 2400 行，硬写进去既难治理也会把策略表撑大；而且**行数爆炸本身就是信号**：
#: 说明域/ABAC 根本没配，应该先治理再迁移，而不是把"全员全表"写死成几百条策略。
LEGACY_DEFAULT_ALLOW_MAX_ROWS = 2000

#: ``VARCHAR(120)`` / ``VARCHAR(255)`` 的截断长度（超长在 PG 上会整条 INSERT 失败）。
_NAME_MAX = 120
_DESC_MAX = 255


# ---------------------------------------------------------------------------
# 小工具（与 repo/engine 同风格：None 才是"没有值"，0 是合法值）
# ---------------------------------------------------------------------------
def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _cut(value: str, limit: int) -> str:
    value = _text(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _as_list(value: Any) -> list:
    """JSONB 列归一：PG/驱动可能直接给 list，也可能给 JSON 文本或 None。"""
    if isinstance(value, (list, tuple)):
        return list(value)
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _dedupe(values) -> list[str]:
    """去空白 + 大小写不敏感去重（保留首次出现的写法，顺序稳定）。"""
    seen: set[str] = set()
    out: list[str] = []
    for raw in values or ():
        item = _text(raw)
        if not item or item.lower() in seen:
            continue
        seen.add(item.lower())
        out.append(item)
    return out


def _skip(skipped: list[dict], source: str, reason: str, **extra) -> None:
    """记一条"没迁成"并立刻 warning —— 迁移器的失败必须让人看得见。"""
    item = {"source": source, "reason": reason, **extra}
    skipped.append(item)
    log.warning("[问数权限][迁移] 跳过 {}：{}（{}）", source, reason, extra or "-")


def _group_users(rows) -> list[dict]:
    """``(id, is_superuser, role_code)`` 的 LEFT JOIN 结果 → 按用户聚合。

    没有角色的用户也会有一行（role_code 为 ``None``），聚合后 ``roles=[]`` ——
    这类用户恰恰是最需要兜底 allow 的（既不属域、也没有 ABAC 命中）。
    """
    grouped: dict[str, dict] = {}
    for uid, is_super, code in rows or ():
        key = _text(uid)
        if not key:
            continue
        item = grouped.setdefault(
            key, {"id": uid, "is_superuser": bool(is_super), "roles": []}
        )
        role = _text(code)
        if role and role.upper() not in {r.upper() for r in item["roles"]}:
            item["roles"].append(role)
    return list(grouped.values())


def _policy_row(
    *,
    name: str,
    description: str,
    resource_code: str,
    effect: str,
    subject_kind: str,
    subject_value: str = "",
    condition: str = "",
    columns: list[str] | None = None,
    mask_expr: str = "",
    marking: str = "",
    priority: int = 100,
    enabled: bool = True,
) -> dict:
    """一条 ``ai_policy`` 行的字段（与 ``policy.model.POLICY_TABLES_SQL`` 列名一致）。"""
    return {
        "name": _cut(name, _NAME_MAX),
        "description": _cut(description, _DESC_MAX),
        "enabled": bool(enabled),
        "priority": int(priority or 0),
        "resource_kind": "table",
        "resource_code": _text(resource_code),
        "effect": effect,
        "subject_kind": subject_kind,
        "subject_value": _text(subject_value),
        "condition": condition or "",
        "columns": list(columns or []),
        "mask_expr": mask_expr or "",
        "marking": marking or "",
    }


# ---------------------------------------------------------------------------
# 行条件语法对齐：旧表达式是 Python 语法 + ``user.*`` 取值，引擎用的是 SQL 风格占位符
# ---------------------------------------------------------------------------
#: ``user.attribute('dept')`` → ``$attr.dept``。
_ATTR_CALL_RE = re.compile(r"user\.attribute\(\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1\s*\)")
#: ``user.id`` / ``user.dept`` 这类直接取值。
_USER_DOT_RE = re.compile(r"\buser\.([A-Za-z_][A-Za-z0-9_]*)")

#: 能一一对到引擎占位符的用户属性（其余如 ``user.role(...)`` 无法表达成**行条件**）。
_USER_ATTR_MAP: dict[str, str] = {
    "id": "$user.id",
    "dept": "$attr.dept_id",
    "dept_id": "$attr.dept_id",
    "username": "$attr.username",
    "name": "$attr.name",
}


class _Unsupported(ValueError):
    """表达式里有引擎表达不了的成分。"""


def translate_condition(expression: str) -> str | None:
    """旧行策略表达式 → 引擎的行条件；**翻不了返回 ``None``**（调用方跳过并留痕）。

    只做两件事，语义一字不改：

    1. 占位符对齐：``user.attribute('dept')`` → ``$attr.dept``、``user.id`` → ``$user.id``；
    2. 比较运算符对齐：``==`` → ``=``（引擎把条件交给 SQL 编译器下推，``==`` 不是 SQL）。

    ``user.role('ADMIN')`` / ``user.superuser`` 这类**主体判定**没有对应的行条件写法
    （行条件只能看列与属性），返回 ``None`` —— 猜一个近似语义比拒绝更危险。
    """
    expr = _text(expression)
    if not expr:
        return ""
    out = _ATTR_CALL_RE.sub(lambda m: f"$attr.{m.group(2)}", expr)

    def _sub(match) -> str:
        name = match.group(1)
        mapped = _USER_ATTR_MAP.get(name)
        if mapped is None:
            raise _Unsupported(name)
        return mapped

    try:
        out = _USER_DOT_RE.sub(_sub, out)
    except _Unsupported:
        return None
    return out.replace("==", "=").strip()


# ---------------------------------------------------------------------------
# 对象码 → 物理表（控制者裁决第 1 条：必须落到 table，不许写 object）
# ---------------------------------------------------------------------------
def build_object_table_map(
    pairs: dict[str, str] | None, asset_tables: set[str] | None = None
) -> dict[str, str]:
    """``{表名: 对象 code}``（本体语义层）→ ``{对象 code: 物理表}``。

    本体对象有两种支撑表（见 ``ontology/semantic.object_table_map``）：
    数据源支撑的（表名就是业务表）与本体物化的（``ont_<code>``）。同一个 code 可能
    同时出现在两个键上，这里**优先非 ``ont_<code>`` 的那张**（它才是真实存在的表）。
    """
    out: dict[str, str] = {}
    for table, code in (pairs or {}).items():
        t, c = _text(table), _text(code)
        if not t or not c:
            continue
        cur = out.get(c)
        if cur is None or (cur == f"ont_{c}" and t != f"ont_{c}"):
            out[c] = t
    # 兜底：``ai_query_assets`` 里出现同名表/``ont_<code>`` 也能认（语义层没覆盖到的对象）
    for code in {_text(v) for v in (pairs or {}).values() if _text(v)}:
        if code in out:
            continue
        for cand in (code, f"ont_{code}"):
            if cand in (asset_tables or set()):
                out[code] = cand
                break
    return out


def resolve_object_table(
    object_code: str, code_to_table: dict[str, str], asset_tables: set[str] | None = None
) -> str:
    """解析对象码对应的物理表；解析不到返回空串（调用方必须跳过并留痕）。"""
    code = _text(object_code)
    if not code:
        return ""
    if code in code_to_table:
        return code_to_table[code]
    assets = asset_tables or set()
    for cand in (code, f"ont_{code}"):
        if cand in assets:
            return cand
    return ""


# ---------------------------------------------------------------------------
# 规划：旧行 → 待写入的策略（纯函数，便于单测；不做任何 IO）
# ---------------------------------------------------------------------------
def plan_domains(domains, skipped: list[dict]) -> list[dict]:
    """``ai_data_domain`` → 每个域 × 每张表一条 ``allow``（subject=domain）。"""
    planned: list[dict] = []
    for row in domains or ():
        did = row.get("id")
        code = _text(row.get("code"))
        name = _text(row.get("name")) or code
        tables = _dedupe(_as_list(row.get("tables")))
        if not code:
            _skip(skipped, "ai_data_domain", "域缺少 code，无法作为 subject_value", id=did)
            continue
        if not tables:
            _skip(skipped, "ai_data_domain", "域没有 tables（无表可授权）", id=did)
            continue
        for table in tables:
            planned.append(
                {
                    "source": "ai_data_domain",
                    "source_table": "ai_data_domain",
                    # 一个域多张表 → 幂等键必须带表名，否则第二张表会被判成"已迁移"
                    "source_id": f"{did}:{table.lower()}",
                    "values": _policy_row(
                        name=f"legacy_domain:{code}:{table}",
                        description=f"迁移自 ai_data_domain#{did}（{name}）：域成员可查该表",
                        resource_code=table,
                        effect="allow",
                        subject_kind="domain",
                        subject_value=code,
                    ),
                }
            )
    return planned


def plan_access_rules(rules, skipped: list[dict]) -> list[dict]:
    """``ai_access_rule`` → ``allow``（subject=role）；只支持 ``attribute=role``。

    ``sensitive_ok`` **无法**迁成"列级放行"：引擎里列 ``deny`` 优先于列 ``allow``，
    而敏感列会按现状迁成 ``everyone`` 的 deny。因此这里只把「可看的表」迁过去，
    ``sensitive_ok`` 一律进 ``skipped`` 交人工（不静默丢权限，也不写成无效策略）。
    """
    planned: list[dict] = []
    for row in rules or ():
        rid = row.get("id")
        name = _text(row.get("name")) or f"rule#{rid}"
        attr = _text(row.get("attribute")).lower()
        value = _text(row.get("value"))
        tables = _dedupe(_as_list(row.get("allowed_tables")))
        if attr != "role":
            _skip(skipped, "ai_access_rule", f"ABAC 属性 {attr or '(空)'} 不支持（仅 role）", id=rid)
            continue
        if not value:
            _skip(skipped, "ai_access_rule", "规则缺少角色码（value）", id=rid)
            continue
        if row.get("sensitive_ok"):
            _skip(
                skipped,
                "ai_access_rule",
                "sensitive_ok 需要列级放行，但引擎列 deny 优先于 allow；"
                "请迁移后人工配置掩码或调整敏感列策略",
                id=rid,
            )
        if not tables:
            _skip(skipped, "ai_access_rule", "allowed_tables 为空（无表可授权）", id=rid)
            continue
        for table in tables:
            planned.append(
                {
                    "source": "ai_access_rule",
                    "source_table": "ai_access_rule",
                    "source_id": f"{rid}:{table.lower()}",
                    "values": _policy_row(
                        name=f"legacy_abac:{value}:{table}",
                        description=f"迁移自 ai_access_rule#{rid}（{name}）：角色 {value} 可查该表",
                        resource_code=table,
                        effect="allow",
                        subject_kind="role",
                        subject_value=value,
                    ),
                }
            )
    return planned


def plan_sensitive_columns(rows, skipped: list[dict]) -> list[dict]:
    """``ai_query_asset_columns.sensitive=true`` → 每张表一条列 ``deny``（多列合并）。

    语义与现状一致：**任何人**都不能读敏感列（旧逻辑是"除非有 sensitive_ok 规则"，
    那条差异已在 :func:`plan_access_rules` 里作为 skipped 报出来）。
    ``marking=sensitive`` 供下游传播（导出/报告）识别。
    """
    grouped: dict[str, dict] = {}
    for row in rows or ():
        table = _text(row.get("table_name"))
        column = _text(row.get("column_name"))
        if not table or not column:
            _skip(skipped, "ai_query_asset_columns", "表名或列名为空", id=row.get("id"))
            continue
        key = table.lower()
        item = grouped.setdefault(key, {"table": table, "columns": []})
        item["columns"].append(column)
    planned: list[dict] = []
    for item in grouped.values():
        table = item["table"]
        columns = sorted({c.lower() for c in item["columns"]})
        planned.append(
            {
                "source": "ai_query_asset_columns",
                "source_table": "ai_query_asset_columns",
                "source_id": f"sensitive:{table.lower()}",
                "values": _policy_row(
                    name=f"legacy_sensitive:{table}",
                    description=f"迁移自 ai_query_asset_columns（sensitive=true）：{table} 的敏感列不可读",
                    resource_code=table,
                    effect="deny",
                    subject_kind="everyone",
                    columns=columns,
                    marking="sensitive",
                ),
            }
        )
    return planned


def plan_row_policies(
    rows,
    code_to_table: dict[str, str],
    asset_tables: set[str] | None,
    skipped: list[dict],
) -> list[dict]:
    """``ai_ont_row_policy`` → 物理表上的 ``allow``（``condition`` 语法对齐后搬迁）。

    三类必须跳过的情形（都会 warning + 进 ``skipped``）：

    - ``object_code`` 解析不到物理表 —— 写成 ``resource_kind=object`` 引擎根本不认，
      等于"看着迁了、其实没迁"；
    - ``effect=deny`` 且带条件 —— 新引擎的 ``deny`` 是**整表短路**（不看 condition），
      照搬会把"排除作废行"变成"整表不可查"；
    - 表达式含 ``user.role(...)`` / ``user.superuser`` 等**主体判定** —— 行条件只能看
      列与属性，猜近似语义比拒绝更危险。
    """
    planned: list[dict] = []
    for row in rows or ():
        pid = row.get("id")
        code = _text(row.get("object_code"))
        name = _text(row.get("name")) or f"policy#{pid}"
        effect = (_text(row.get("effect")) or "allow").lower()
        table = resolve_object_table(code, code_to_table, asset_tables)
        if not table:
            _skip(
                skipped,
                "ai_ont_row_policy",
                f"对象码 {code or '(空)'} 解析不到物理表（ai_query_assets / 语义层都没有）",
                id=pid,
                object_code=code,
            )
            continue
        if effect == "deny":
            _skip(
                skipped,
                "ai_ont_row_policy",
                "条件 deny 无法表达（新引擎的 deny 是整表短路、不看 condition），需人工处理",
                id=pid,
                object_code=code,
            )
            continue
        if effect != "allow":
            _skip(
                skipped, "ai_ont_row_policy", f"未知 effect：{effect}", id=pid, object_code=code
            )
            continue
        expression = _text(row.get("expression"))
        condition = translate_condition(expression)
        if condition is None:
            _skip(
                skipped,
                "ai_ont_row_policy",
                "表达式含 user.* 主体判定（user.role/user.superuser 等），引擎行条件无法表达",
                id=pid,
                object_code=code,
            )
            continue
        planned.append(
            {
                "source": "ai_ont_row_policy",
                "source_table": "ai_ont_row_policy",
                "source_id": str(pid),
                "values": _policy_row(
                    name=f"legacy_row:{code}#{pid}",
                    # 原表达式留痕：治理页/审计能对照"这条策略是从哪来的"
                    description=f"迁移自 ai_ont_row_policy#{pid}（{name}）；原表达式：{expression}",
                    resource_code=table,
                    effect="allow",
                    subject_kind="everyone",
                    condition=condition,
                    priority=int(row.get("priority") or 0),
                    enabled=bool(row.get("enabled", True)),
                ),
            }
        )
    return planned


def plan_legacy_default_allow(
    users,
    domains,
    abac_policies,
    tables,
    skipped: list[dict],
) -> list[dict]:
    """给**真正需要兜底**的用户逐表建 ``everyone``→``user`` 的 allow。

    为什么不再用 ``everyone``（越权）：旧逻辑里「属于某数据域 → 只能查域内表」是**收紧**，
    而新模型是 allow 并集 —— 一条 ``everyone`` 的全表 allow 会把域隔离整体抹平，
    enforce 当天域成员就能查全表。所以兜底**只发给**：

    - 不在任何**已迁出策略的启用数据域**成员里，且
    - 没有任何命中其角色的**已迁出策略的启用 ABAC 规则**。

    这两类用户本来就「未配置 → 全表」，给他们 ``subject_kind=user`` 的兜底才等价。
    超管不建（引擎直接 bypass，建了也是废行）。

    每张表一条（``columns`` 是列不是表，塞表清单会让策略静默失效）。
    ``(用户数 × 表数) > LEGACY_DEFAULT_ALLOW_MAX_ROWS`` 时**一条都不写**，
    只返回一条 ``skipped`` 让管理员先配域/ABAC —— 防爆比"先给上"更重要。
    """
    table_list = _dedupe(tables)
    covered: set[str] = set()

    # 域成员：只有真正迁出了 allow 的域（有 code、有 tables）才算"被覆盖"
    for dom in domains or ():
        if not _text(dom.get("code")):
            continue  # 没 code 迁不出 domain 策略 → 其成员仍需兜底（否则会被锁死）
        if not _dedupe(_as_list(dom.get("tables"))):
            continue  # 空表域在旧逻辑里也不收紧（falsy → 落到 ABAC/全表）
        covered.update(_text(uid) for uid in _as_list(dom.get("members")) if _text(uid))

    # ABAC 覆盖：按**已迁出的 role 策略**算（被跳过的规则等于没覆盖）
    covered_roles = {
        _text(item["values"].get("subject_value")).upper()
        for item in abac_policies or ()
        if _text(item["values"].get("subject_kind")) == "role"
    }
    eligible: list[str] = []
    for user in users or ():
        uid = _text(user.get("id"))
        if not uid or user.get("is_superuser"):
            continue
        if uid in covered:
            continue
        roles = {_text(r).upper() for r in (user.get("roles") or ()) if _text(r)}
        if roles & covered_roles:
            continue
        eligible.append(uid)

    total = len(eligible) * len(table_list)
    if total > LEGACY_DEFAULT_ALLOW_MAX_ROWS:
        _skip(
            skipped,
            "legacy_default_allow",
            f"legacy_default_allow rows > {LEGACY_DEFAULT_ALLOW_MAX_ROWS}，"
            f"请先配置数据域/ABAC 再迁移（本次 {len(eligible)} 用户 × "
            f"{len(table_list)} 表 = {total} 行）",
        )
        return []

    planned: list[dict] = []
    for uid in eligible:
        for table in table_list:
            planned.append(
                {
                    "source": "legacy_default_allow",
                    "source_table": "legacy_default_allow",
                    # 幂等键：用户 + 表（换用户不会互相顶掉，换表也不会被误判"已迁移"）
                    "source_id": f"{uid}:{table.lower()}",
                    "user_id": int(uid) if uid.isdigit() else None,
                    "values": _policy_row(
                        name=LEGACY_DEFAULT_ALLOW_NAME,
                        description=f"{LEGACY_DEFAULT_ALLOW_DESC}（uid={uid}）",
                        resource_code=table,
                        effect="allow",
                        subject_kind="user",
                        subject_value=uid,
                        priority=1,
                    ),
                }
            )
    return planned


# ---------------------------------------------------------------------------
# 存储层（真实的读/写都在这里；测试注入假存储替换 ``_make_store``）
# ---------------------------------------------------------------------------
class _DbStore:
    """真实的库访问：一次读出所有旧行 + 迁移台账，写入策略行与台账行。"""

    @staticmethod
    async def _rows(sql: str, params: dict | None = None) -> list[tuple]:
        async with async_db_session() as db:
            return list((await db.execute(text(sql), params or {})).fetchall())

    async def ensure_migration_table(self) -> None:
        await ensure_migration_table()

    async def load_sources(self) -> dict:
        """读全部输入。

        **单张旧表读不出来不拖垮整次迁移**：记进 ``errors``（调用方转成 ``skipped``），
        其余来源照常迁 —— 否则一张历史表缺失会让整个权限模型切不过去。
        """
        errors: list[dict] = []

        async def _safe(source: str, sql: str) -> list[tuple]:
            try:
                return await self._rows(sql)
            except Exception as e:  # noqa: BLE001
                errors.append({"source": source, "reason": f"{type(e).__name__}: {e}"[:200]})
                log.warning("[问数权限][迁移] 读取 {} 失败（跳过该来源）: {}", source, e)
                return []

        domain_rows = await _safe(
            "ai_data_domain",
            "SELECT id, name, code, tables, members FROM ai_data_domain "
            "WHERE enabled=true AND is_deleted=false ORDER BY id",
        )
        rule_rows = await _safe(
            "ai_access_rule",
            "SELECT id, name, attribute, value, allowed_tables, sensitive_ok "
            "FROM ai_access_rule WHERE enabled=true AND is_deleted=false ORDER BY id",
        )
        column_rows = await _safe(
            "ai_query_asset_columns",
            "SELECT id, table_name, column_name FROM ai_query_asset_columns "
            "WHERE sensitive=true AND is_deleted=false ORDER BY table_name, column_name",
        )
        # ``ai_ont_row_policy`` **没有 is_deleted 列**（本体侧只做物理删除），别照抄别的表
        policy_rows = await _safe(
            "ai_ont_row_policy",
            "SELECT id, object_code, name, expression, effect, priority, enabled "
            "FROM ai_ont_row_policy ORDER BY id",
        )
        asset_rows = await _safe(
            "ai_query_assets",
            "SELECT table_name FROM ai_query_assets WHERE is_deleted=false ORDER BY id",
        )
        # 兜底 allow 要按**用户**发（不能 everyone，否则抹平域隔离）：需要「用户 → 角色码」。
        # LEFT JOIN 的写法让"没有任何角色的用户"也返回一行（code 为 NULL）。
        user_rows = await _safe(
            "sys_user",
            "SELECT u.id, COALESCE(u.is_superuser,false), r.code "
            "FROM sys_user u "
            "LEFT JOIN sys_user_roles ur ON ur.user_id = u.id "
            "LEFT JOIN sys_role r ON r.id = ur.role_id "
            "WHERE u.is_deleted = false ORDER BY u.id",
        )
        # 迁移台账：首次运行（表还不存在）读不到属正常，不当错误上报
        migration_rows = (
            await self._rows("SELECT source_table, source_id FROM ai_policy_migration")
            if await _migration_table_exists()
            else []
        )

        object_table: dict[str, str] = {}
        try:
            from ...ontology import semantic

            object_table = dict(await semantic.object_table_map())
        except Exception as e:  # noqa: BLE001
            errors.append({"source": "semantic", "reason": f"对象→表映射不可用：{e}"[:200]})
            log.warning("[问数权限][迁移] 对象→表映射不可用（行策略可能整体跳过）: {}", e)

        system_tables: set[str] = set()
        try:
            from .. import service as query_service

            system_tables = set(await query_service._system_allowed())
        except Exception as e:  # noqa: BLE001
            errors.append({"source": "legacy_default_allow", "reason": f"系统白名单不可用：{e}"[:200]})
            log.warning("[问数权限][迁移] 系统白名单不可用（不建兜底 allow）: {}", e)

        return {
            "domains": [
                {
                    "id": r[0],
                    "name": r[1],
                    "code": r[2],
                    "tables": r[3],
                    "members": r[4],
                }
                for r in domain_rows
            ],
            "access_rules": [
                {
                    "id": r[0],
                    "name": r[1],
                    "attribute": r[2],
                    "value": r[3],
                    "allowed_tables": r[4],
                    "sensitive_ok": bool(r[5]),
                }
                for r in rule_rows
            ],
            "sensitive_columns": [
                {"id": r[0], "table_name": r[1], "column_name": r[2]} for r in column_rows
            ],
            "row_policies": [
                {
                    "id": r[0],
                    "object_code": r[1],
                    "name": r[2],
                    "expression": r[3],
                    "effect": r[4],
                    "priority": r[5],
                    "enabled": bool(r[6]),
                }
                for r in policy_rows
            ],
            "asset_tables": {_text(r[0]) for r in asset_rows if _text(r[0])},
            "object_table": object_table,
            "system_tables": system_tables,
            "users": _group_users(user_rows),
            "migrations": [
                {"source_table": r[0], "source_id": r[1]} for r in migration_rows
            ],
            "errors": errors,
        }

    async def insert_policy(self, values: dict) -> int:
        """插入一条策略，返回新 id（``columns`` 按 JSON 文本写，PG/SQLite 都认）。"""
        params = dict(values)
        params["columns"] = json.dumps(params.get("columns") or [], ensure_ascii=False)
        sql = (
            "INSERT INTO ai_policy (name, description, enabled, priority, resource_kind, "
            "resource_code, effect, subject_kind, subject_value, condition, columns, "
            "mask_expr, marking) VALUES (:name, :description, :enabled, :priority, "
            ":resource_kind, :resource_code, :effect, :subject_kind, :subject_value, "
            ":condition, :columns, :mask_expr, :marking) RETURNING id"
        )
        async with async_db_session.begin() as db:
            result = await db.execute(text(sql), params)
            return int(result.scalar() or 0)

    async def record_migration(
        self, source_table: str, source_id: str, policy_id: int
    ) -> None:
        async with async_db_session.begin() as db:
            await db.execute(
                text(
                    "INSERT INTO ai_policy_migration (source_table, source_id, policy_id) "
                    "VALUES (:s, :i, :p)"
                ),
                {"s": source_table, "i": source_id, "p": policy_id},
            )


def _make_store() -> _DbStore:
    """存储工厂（测试 monkeypatch 这一个函数注入内存假存储）。"""
    return _DbStore()


async def _migration_table_exists() -> bool:
    """迁移台账是否存在（dry_run 下不建表，只能探测）。"""
    try:
        from sqlalchemy import inspect as sa_inspect

        async with async_db_session() as db:
            names = await db.run_sync(
                lambda s: set(sa_inspect(s.connection()).get_table_names())
            )
        return "ai_policy_migration" in names
    except Exception:  # noqa: BLE001
        return False


async def ensure_migration_table() -> None:
    """幂等建迁移台账（**失败就抛**：台账不可用会让下次重跑出重复策略）。"""
    from ..ddl_dialect import ddl_for_dialect

    try:
        async with async_db_session.begin() as db:
            await db.execute(text(ddl_for_dialect(MIGRATION_TABLE_SQL)))
    except Exception as e:  # noqa: BLE001
        log.warning("[问数权限][迁移] 建 ai_policy_migration 失败：{}", e)
        raise


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
async def backfill_policies(dry_run: bool = False) -> dict:
    """把旧权限机制迁成显式策略（**幂等**，可反复执行）。

    返回 ``{"created": int, "skipped": [...], "by_source": {来源: 新建条数}}``：

    - ``created``：本次**新建**的策略条数（已迁移过的不计）；
    - ``skipped``：没迁成的条目（``{"source", "reason", "id"/"object_code"...}``），
      每条都配一条 ``log.warning``；
    - ``by_source``：五类来源各自新建了多少条（固定键，含 0）。
      ``legacy_default_allow`` 是唯一的结构化项：``{"users": n, "rows": m}``
      （行是「用户 × 表」的笛卡尔积，只看行数看不出影响面）。

    ``dry_run=True`` 只规划、不写库（**连迁移表都不建**），用于切 enforce 前评估影响面。
    """
    store = _make_store()
    skipped: list[dict] = []
    by_source: dict[str, Any] = dict.fromkeys(SOURCES, 0)

    if not dry_run:
        await store.ensure_migration_table()

    data = await store.load_sources()
    for err in data.get("errors") or ():
        _skip(skipped, _text(err.get("source")) or "(未知)", _text(err.get("reason")) or "读取失败")

    existing = {
        (_text(m.get("source_table")), _text(m.get("source_id")))
        for m in (data.get("migrations") or ())
    }

    domain_planned = plan_domains(data.get("domains") or (), skipped)
    abac_planned = plan_access_rules(data.get("access_rules") or (), skipped)

    asset_tables = set(data.get("asset_tables") or ())
    code_to_table = build_object_table_map(data.get("object_table") or {}, asset_tables)
    planned: list[dict] = list(domain_planned) + list(abac_planned)
    planned += plan_row_policies(
        data.get("row_policies") or (), code_to_table, asset_tables, skipped
    )
    planned += plan_sensitive_columns(data.get("sensitive_columns") or (), skipped)
    # 兜底 allow **按用户**发（everyone 会抹平域隔离）：只给"域/ABAC 都覆盖不到"的存量用户。
    # 域/ABAC 的"覆盖范围"必须用**已迁出的策略**算（被跳过的规则等于没覆盖）。
    default_planned = plan_legacy_default_allow(
        data.get("users") or (),
        data.get("domains") or (),
        abac_planned,
        data.get("system_tables") or (),
        skipped,
    )

    created = 0
    for item in planned:
        key = (item["source_table"], item["source_id"])
        if key in existing:
            continue
        existing.add(key)
        source = item["source"]
        if not dry_run:
            policy_id = await store.insert_policy(item["values"])
            await store.record_migration(key[0], key[1], policy_id)
        created += 1
        by_source[source] = by_source.get(source, 0) + 1

    # 兜底 allow 单独记账：``{"users": 覆盖/新建的用户数, "rows": 新建行数}``
    # （行是「用户 × 表」的笛卡尔积，只报行数看不出影响面）
    default_users: set = set()
    default_rows = 0
    for item in default_planned:
        key = (item["source_table"], item["source_id"])
        if key in existing:
            continue
        existing.add(key)
        if not dry_run:
            policy_id = await store.insert_policy(item["values"])
            await store.record_migration(key[0], key[1], policy_id)
        default_rows += 1
        default_users.add(item.get("source_id", "").split(":", 1)[0])
        created += 1
    by_source["legacy_default_allow"] = {
        "users": len(default_users),
        "rows": default_rows,
    }

    log.info(
        "[问数权限][迁移] {}完成：新建 {} 条，跳过 {} 条，明细 {}",
        "dry_run " if dry_run else "",
        created,
        len(skipped),
        by_source,
    )
    return {"created": created, "skipped": skipped, "by_source": by_source}
