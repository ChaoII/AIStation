"""问数权限网关端到端冒烟（提交前必跑，约 5~20 秒）。

为什么需要它
------------
策略引擎、编译器、审计三块都有各自单测，但"**真的**拒了没有"只有跑一遍才知道：
2026-11 就出现过"单测全绿、真实提问全部 500"（整段替换删掉了运行时方法）。本脚本
按 spec §11 的验收口径，直接驱动**线上同一套** ``guard.prepare`` / ``compiler.rewrite``，
不经过 LLM、不依赖 HTTP 服务。

八项检查
--------
1. 无主体 → deny（P0：禁止 ``auth=None`` 落到 permit）；
2. 敏感表 ``select *`` → deny（P0 星号止血，三种模式都生效）；
3. 行策略 → 生成的 SQL 含过滤条件（临时插一条 allow，``WHERE name LIKE
   'smoke-policy-%'`` 清理，**不动真实策略**）；
4. 审计表能读到第 2 步**本次新写**的 deny 记录（先记 ``max(id)`` 水位，只认
   ``id > 水位`` —— 审计 append-only，只按 hash 找会被历史行假通过）；
5. 无法解析的 SQL → deny（编译器必须**因解析失败**拒）。

6~8 是 **enforce 真实链路**（Step 1 起编译器已接线）：

6. ``condition`` → ``prepare`` 返回的 ``decision.sql`` 含 ``WHERE``；
7. 列 ``deny`` → 查询被拒（不让读受限列）；
8. ``mask`` → 投影被替换成掩码表达式。

6~8 用 ``ds:4`` 的**真实表**（表/列取自已同步的 ``ai_query_schema``），只驱动
``guard.prepare``，不连远端库、不执行 SQL；临时策略同样以 ``smoke-policy-%`` 前缀
首尾清理。

用法::

    cd backend
    uv run python scripts/query_policy_smoke.py

    # 自检第 4 项不是假通过：注入审计写入失败，预期冒烟失败（退出码 1）
    uv run python scripts/query_policy_smoke.py --simulate-audit-failure

退出码非 0 即失败，可直接接进提交前钩子。

说明
----
- 需要**数据库**（``backend/env/.env.dev`` 的 PG；worktree 里先拷环境文件），
  不需要起后端服务；连不上库会在 10 秒内明确报错并退出 1；
- 审计表是 append-only 的**真实判定记录**，本脚本**不删**自己产生的审计行
  （手工删审计等于篡改留痕）。它们可用 ``datasource='smoke:policy'`` 区分；
- 唯一写入的配置数据是临时策略，首尾各清一次（``smoke-policy-%``）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime

# 让 ``python scripts/xxx.py`` 也能 import ``app.*``：脚本模式只把 **scripts/** 放进
# sys.path，backend 根目录不在里面（conftest 里也是同样的处理）。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Windows 控制台默认 GBK，打 ✅/❌ 会 UnicodeEncodeError 直接把脚本炸掉
# （判定结论反而没打印出来）。统一按 UTF-8 输出，编码不支持的字符替换而非抛错。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 非终端/被重定向时没有 reconfigure
        pass

# 必须在 import app.* 之前设置：Settings 用 ``.env.{ENVIRONMENT}`` 定位环境文件，
# 未设置时读不到 ``env/.env.dev``，会退回默认 MySQL 配置（连不上，且报错很绕）。
os.environ.setdefault("ENVIRONMENT", "dev")

#: 临时策略名前缀（清理条件 ``LIKE 'smoke-policy-%'``）。
SMOKE_NAME = "smoke-policy-row-filter"
SMOKE_LIKE = "smoke-policy-%"

#: 行策略作用在**不存在的表**上：check 3 只走 编译器（不执行 SQL），
#: 用假表名可以保证"就算这行策略漏删，也影响不到任何真实查询"。
SMOKE_TABLE = "smoke_policy_table"

#: enforce 检查用**真实表**（ds:4 的已同步表；不执行 SQL，只编译）。
SMOKE_DS = "ds:4"
SMOKE_REAL_TABLE = "DTXY_PMXX"

#: 行条件用 ``$attr.*``：顺带验证"属性绑定 → 生成过滤条件"这条真实链路。
SMOKE_CONDITION = "dept_id = $attr.dept_id"
SMOKE_DEPT = "7"

#: 审计里的数据源标记（便于识别、过滤冒烟产生的记录）。
DATASOURCE = "smoke:policy"

TOTAL = 8


def _principal(*, user_id: int | None = 101, attrs: dict | None = None):
    """构造一个非超管主体（冒烟不依赖登录态）。"""
    from app.plugin.module_ai.query.policy.principal import Principal

    return Principal(
        user_id=user_id,
        is_superuser=False,
        roles=(),
        attrs=dict(attrs or {}),
        entry="ask",
    )


def _load_orm_models() -> None:
    """先导入 ``UserModel``：策略/设置模型的关系（created_by/updated_by）指向它。

    不构造应用也能用（省掉 20 秒路由发现）；缺了它 mapper 配置直接
    ``InvalidRequestError: expression 'UserModel' failed to locate a name``。
    """
    from app.api.v1.module_system.user.model import UserModel  # noqa: F401


async def _cleanup() -> int:
    """删掉本脚本的临时策略（首尾各跑一次，防上次中途崩溃留垃圾）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        result = await db.execute(
            text("DELETE FROM ai_policy WHERE name LIKE :p"), {"p": SMOKE_LIKE}
        )
        return int(result.rowcount or 0)


async def _max_audit_id() -> int:
    """审计表当前最大 id（**水位**）。

    审计是 append-only 的：同一 SQL 历史上已经有同 ``sql_hash`` 的 deny 行，
    只按 hash 找会让"本次写失败"也 ✅。第 ④ 项必须断言存在 ``id > 水位`` 的新行。
    """
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        return int(
            (
                await db.execute(
                    text("SELECT COALESCE(MAX(id), 0) FROM ai_query_access_log")
                )
            ).scalar()
            or 0
        )


async def _insert_smoke_policy() -> int:
    """插一条 allow + 行条件的临时策略（表名是假的，只给编译器用）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    now = datetime.now()
    async with async_db_session.begin() as db:
        result = await db.execute(
            text(
                "INSERT INTO ai_policy "
                "(name, description, enabled, priority, resource_kind, resource_code, "
                "effect, subject_kind, subject_value, condition, columns, mask_expr, "
                "marking, created_time, updated_time, is_deleted) "
                "VALUES (:name, :desc, true, 50, 'table', :code, 'allow', 'everyone', "
                "'', :cond, :cols, '', '', :now, :now, false) RETURNING id"
            ),
            {
                "name": SMOKE_NAME,
                "desc": "问数权限冒烟临时策略（scripts/query_policy_smoke.py）",
                "code": SMOKE_TABLE,
                "cond": SMOKE_CONDITION,
                # jsonb 列按纯文本 JSON 传参（与 audit 写 jsonb 的做法一致）
                "cols": json.dumps([], ensure_ascii=False),
                "now": now,
            },
        )
        return int(result.scalar())


async def _check_no_principal() -> tuple[bool, str]:
    """① 无主体 → deny。"""
    from app.plugin.module_ai.query.policy.guard import prepare

    decision = await prepare(
        sql="select 1", principal=None, entry="ask", datasource=DATASOURCE
    )
    return (not decision.permit, decision.reason)


async def _check_star_deny(table: str) -> tuple[bool, str, str]:
    """② 敏感表 ``select *`` → deny；返回 (ok, 说明, 被检查的 SQL)。"""
    from app.plugin.module_ai.query.policy.guard import prepare

    sql = f"select * from {table}"
    decision = await prepare(
        sql=sql, principal=_principal(), entry="ask", datasource=DATASOURCE
    )
    return (not decision.permit, decision.reason, sql)


async def _check_row_filter(policy_id: int) -> tuple[bool, str]:
    """③ 行策略 → 生成的 SQL 含过滤条件（``build_plan`` + ``rewrite``）。"""
    from app.plugin.module_ai.query.policy import compiler, repo

    policies = await repo.list_policies()
    if not any(p.id == policy_id for p in policies):
        return False, f"临时策略 {policy_id} 没有被 repo.list_policies() 读到（enabled/软删口径有问题）"

    principal = _principal(attrs={"dept_id": SMOKE_DEPT})
    plan = compiler.build_plan(policies, principal, {SMOKE_TABLE: ["id", "dept_id"]})
    if not plan.row_filters.get(SMOKE_TABLE):
        return False, f"访问计划里没有 {SMOKE_TABLE} 的行过滤条件"
    decision = compiler.rewrite(f"select id, dept_id from {SMOKE_TABLE}", plan)
    if not decision.permit:
        return False, f"编译器拒绝了合法查询：{decision.reason}"

    sql = " ".join(str(decision.sql or "").split())
    want = f"dept_id = '{SMOKE_DEPT}'"
    if want not in sql:
        return False, f"生成的 SQL 不含行过滤条件 {want!r}：{sql[:200]}"
    return True, sql[:160]


async def _insert_policy(
    name: str,
    *,
    resource_code: str,
    effect: str = "allow",
    condition: str = "",
    columns=None,
    mask_expr: str = "",
    priority: int = 50,
) -> int:
    """插一条临时策略（统一前缀，首尾清理）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    now = datetime.now()
    async with async_db_session.begin() as db:
        result = await db.execute(
            text(
                "INSERT INTO ai_policy "
                "(name, description, enabled, priority, resource_kind, resource_code, "
                "effect, subject_kind, subject_value, condition, columns, mask_expr, "
                "marking, created_time, updated_time, is_deleted) "
                "VALUES (:name, :desc, true, :prio, 'table', :code, :effect, 'everyone', "
                "'', :cond, :cols, :mask, '', :now, :now, false) RETURNING id"
            ),
            {
                "name": name,
                "desc": "问数权限冒烟临时策略（scripts/query_policy_smoke.py）",
                "prio": priority,
                "code": resource_code,
                "effect": effect,
                "cond": condition,
                "cols": json.dumps(columns or [], ensure_ascii=False),
                "mask": mask_expr,
                "now": now,
            },
        )
        return int(result.scalar())


async def _real_table() -> tuple[str, list[str]]:
    """挑一张 ds:4 的真实表与它的列（只读本地已同步的 ``ai_query_schema``）。

    优先 ``DTXY_PMXX``（冒烟环境实测有数据、列名稳定）；不存在时按名字排序取第一张
    非敏感、至少两列的表。返回空 = 环境没有可用的真实表元数据。
    """
    from app.plugin.module_ai.query.policy.model import sensitive_tables, table_columns

    sensitive = {s.lower() for s in await sensitive_tables()}
    got = await table_columns(SMOKE_DS, [SMOKE_REAL_TABLE])
    if got.get(SMOKE_REAL_TABLE):
        return SMOKE_REAL_TABLE, got[SMOKE_REAL_TABLE]

    from app.plugin.module_ai.query.service import AiQueryService as Q

    schema = await Q._ds_schema_map(SMOKE_DS)
    for table in sorted(schema):
        if table.lower() in sensitive:
            continue
        cols = await table_columns(SMOKE_DS, [table])
        columns = cols.get(table) or []
        if len(columns) >= 2:
            return table, columns
    return "", []


def _pick_text_column(columns: list[str]) -> str:
    """掩码测试优先用已知文本列（``left(col, 3)`` 在数字列上会报类型错）。"""
    for name in ("VARIETY", "NAME", "COALTYPE", "CTYPE", "REMARK", "TOOLTIP"):
        for col in columns:
            if str(col).upper() == name:
                return col
    return columns[0] if columns else ""


async def _prepare_enforce(sql: str, *, dialect: str = "postgres"):
    """在**本进程内**以 enforce 模式驱动网关（不改库、不影响已启动服务）。"""
    from app.plugin.module_ai.query.policy.guard import prepare

    os.environ["POLICY_ENGINE"] = "enforce"
    try:
        return await prepare(
            sql=sql,
            principal=_principal(),
            entry="ask",
            datasource=SMOKE_DS,
            dialect=dialect,
        )
    finally:
        os.environ.pop("POLICY_ENGINE", None)


async def _check_enforce_row_filter(table: str, columns: list[str]) -> tuple[bool, str]:
    """⑥ enforce + condition → 编译后的 SQL 含 WHERE。"""
    await _cleanup()
    condition_col = columns[0]
    await _insert_policy(
        "smoke-policy-enforce-row",
        resource_code=table,
        condition=f"{condition_col} IS NOT NULL",
    )
    other = columns[1] if len(columns) > 1 else columns[0]
    decision = await _prepare_enforce(f'SELECT "{condition_col}", "{other}" FROM "{table}"')
    if not decision.permit:
        return False, f"enforce 拒绝了带 allow 的查询：{decision.reason}"
    sql = " ".join(str(decision.sql or "").split())
    if "where" not in sql.lower():
        return False, f"编译后的 SQL 不含 WHERE：{sql[:200]}"
    if condition_col.lower() not in sql.lower():
        return False, f"WHERE 里没有条件列 {condition_col}：{sql[:200]}"
    if not decision.applied:
        return False, "applied 为空（审计会以为没有施加改写）"
    return True, sql[:160]


async def _check_enforce_column_deny(table: str, columns: list[str]) -> tuple[bool, str]:
    """⑦ enforce + 列 deny → 查询被拒。"""
    await _cleanup()
    await _insert_policy("smoke-policy-enforce-allow", resource_code=table)
    denied = columns[1] if len(columns) > 1 else columns[0]
    await _insert_policy(
        "smoke-policy-enforce-deny",
        resource_code=table,
        effect="deny",
        columns=[denied],
    )
    decision = await _prepare_enforce(f'SELECT "{denied}" FROM "{table}"')
    if decision.permit:
        return False, f"deny 列 {denied} 仍被放行（列策略没生效）"
    if denied.lower() not in decision.reason.lower():
        return False, f"拒绝了，但原因没说清是哪一列：{decision.reason}"
    return True, decision.reason[:160]


async def _check_enforce_mask(table: str, columns: list[str]) -> tuple[bool, str]:
    """⑧ enforce + mask → 投影被替换成掩码表达式。"""
    await _cleanup()
    await _insert_policy("smoke-policy-enforce-allow", resource_code=table)
    masked = _pick_text_column(columns)
    await _insert_policy(
        "smoke-policy-enforce-mask",
        resource_code=table,
        effect="mask",
        columns=[masked],
        mask_expr=f"left({masked}, 3)",
    )
    decision = await _prepare_enforce(f'SELECT "{masked}" FROM "{table}"')
    if not decision.permit:
        return False, f"enforce 拒绝了合法查询：{decision.reason}"
    sql = " ".join(str(decision.sql or "").split())
    if "left(" not in sql.lower():
        return False, f"投影没有被掩码替换：{sql[:200]}"
    if not any(str(item.get("mask") or "") for item in decision.applied):
        return False, f"applied 里没有 mask：{decision.applied}"
    return True, sql[:160]


async def _check_audit(sql: str, min_id: int) -> tuple[bool, str]:
    """④ 审计表能读到第 ② 步**本次新写**的 deny 记录（``id > min_id``）。"""
    from app.plugin.module_ai.query.policy import audit

    want = audit.sql_hash(sql)
    rows = await audit.list_access_logs(limit=100)
    hit = next(
        (
            r
            for r in rows
            if r.get("sql_hash") == want
            and r.get("decision") == "deny"
            and int(r.get("id") or 0) > int(min_id)
        ),
        None,
    )
    if hit is None:
        return False, (
            f"水位 {min_id} 之后没有该 SQL（hash={want[:12]}…）的 deny 记录 —— "
            "审计可能没写进去（或被历史行假通过）"
        )
    return True, f"id={hit['id']} (> 水位 {min_id}) reason={str(hit.get('reason') or '')[:60]}"


async def _check_parse_fail() -> tuple[bool, str]:
    """⑤ 无法解析的 SQL → deny（编译器 + enforce 网关各验一次）。

    坏 SQL 用 ``select (((``：正则兜底（``from|join <name>``）也提不出表名，因此
    走的是「无法解析 → fail-closed」这条语义。老版本用 ``select from where ((``，
    正则猜出表 ``where`` → 实际是"表未覆盖 → 默认拒绝"，**没验到解析失败**（Important 4）。

    Step 1 起 enforce 已接线编译器，网关这一侧必须与编译器同口径：reason 含「解析」。
    """
    from app.plugin.module_ai.query.policy import compiler, repo
    from app.plugin.module_ai.query.policy.guard import prepare

    bad = "select ((("
    principal = _principal()
    policies = await repo.list_policies()
    plan = compiler.build_plan(policies, principal, {SMOKE_TABLE: ["id"]})
    compiled = compiler.rewrite(bad, plan)
    if compiled.permit:
        return False, "编译器放过了无法解析的 SQL"
    if "解析" not in compiled.reason:
        return False, f"编译器拒绝了，但不是因为解析失败：{compiled.reason}"

    os.environ["POLICY_ENGINE"] = "enforce"
    try:
        gateway = await prepare(
            sql=bad, principal=principal, entry="ask", datasource=DATASOURCE
        )
    finally:
        os.environ.pop("POLICY_ENGINE", None)
    if gateway.permit:
        return False, "enforce 网关放过了无法解析的 SQL"
    if "解析" not in gateway.reason:
        return False, (
            "enforce 网关拒绝了，但不是因为解析失败："
            f"{gateway.reason}"
        )
    return True, f"compiler={compiled.reason[:40]} | guard={gateway.reason[:40]}"


def _report(index: int, title: str, ok: bool, detail: str) -> None:
    mark = "✅" if ok else "❌"
    print(f"[{index}/{TOTAL}] {title} ... {mark} {detail}")


async def main() -> int:
    ap = argparse.ArgumentParser(description="问数权限网关端到端冒烟")
    ap.add_argument(
        "--simulate-audit-failure",
        action="store_true",
        help=(
            "自检第 ④ 项不是假通过：把审计写入换成空操作（只影响本进程），"
            "预期冒烟**失败**（退出码 1）且第 ④ 项报错"
        ),
    )
    args = ap.parse_args()

    started = time.perf_counter()
    _load_orm_models()

    if args.simulate_audit_failure:
        # ``guard`` 在模块导入时就绑定了 ``write_access_log``，必须打在 guard 上
        # （打 ``audit.write_access_log`` 不会生效 —— 这正是要验证的写入路径）。
        from app.plugin.module_ai.query.policy import guard

        async def _drop_audit(**_kwargs) -> None:  # noqa: ANN003
            return None

        guard.write_access_log = _drop_audit
        print("⚠️  已注入审计写入失败（自检模式，预期本次冒烟失败）")

    try:
        from app.plugin.module_ai.query.policy.model import (
            ensure_policy_tables,
            sensitive_tables,
        )

        await ensure_policy_tables()
        sensitive = sorted(await sensitive_tables())
        await _cleanup()
        # 水位必须记在**所有可能写审计的步骤之前**：审计 append-only，
        # 历史同 hash 行会让"本次没写"看起来也成功（Important 3）。
        watermark = await _max_audit_id()
    except Exception as e:  # noqa: BLE001
        print(f"❌ 无法连接数据库 / 初始化策略表：{type(e).__name__}: {e}")
        print("   本脚本不需要 HTTP 服务，但需要可用的数据库：")
        print("   - 确认 PG 在跑、backend/env/.env.dev 存在（worktree 里先拷一份）；")
        print("   - 连不上时不做任何写入，直接退出 1。")
        return 1

    problems: list[str] = []
    policy_id = 0
    try:
        ok, detail = await _check_no_principal()
        _report(1, "无主体 → deny", ok, detail)
        if not ok:
            problems.append(f"① 无主体被放行：{detail}")

        if not sensitive:
            _report(2, "敏感表 select * → deny", False, "库里没有 sensitive 字段，无法验证")
            problems.append("② 没有敏感表（先同步资产 / 标记 sensitive 列）")
            sql_star = ""
        else:
            table = sensitive[0]
            ok, detail, sql_star = await _check_star_deny(table)
            _report(2, f"敏感表 {table} 的 select * → deny", ok, detail)
            if not ok:
                problems.append(f"② 星号止血失效（{table}）：{detail}")

        policy_id = await _insert_smoke_policy()
        ok, detail = await _check_row_filter(policy_id)
        _report(3, "行策略 → 生成的 SQL 含过滤条件", ok, detail)
        if not ok:
            problems.append(f"③ {detail}")

        if sql_star:
            ok, detail = await _check_audit(sql_star, watermark)
        else:
            ok, detail = False, "第 ② 步未执行，没有可核对的 SQL"
        _report(4, f"审计表能读到 ② 的新增 deny 记录（id > {watermark}）", ok, detail)
        if not ok:
            problems.append(f"④ {detail}")

        ok, detail = await _check_parse_fail()
        _report(5, "无法解析的 SQL → deny", ok, detail)
        if not ok:
            problems.append(f"⑤ {detail}")

        # ---- 6~8：enforce 真实链路（ds:4 真实表，只编译不执行）--------------
        table, columns = await _real_table()
        if not table:
            _report(6, "enforce 行策略 → SQL 含 WHERE", False,
                    f"{SMOKE_DS} 没有可用的真实表元数据（先同步 ai_query_schema）")
            problems.append("⑥ 缺少 ds:4 真实表元数据，无法验证 enforce")
        else:
            ok, detail = await _check_enforce_row_filter(table, columns)
            _report(6, f"enforce 行策略 → SQL 含 WHERE（{table}）", ok, detail)
            if not ok:
                problems.append(f"⑥ {detail}")

            ok, detail = await _check_enforce_column_deny(table, columns)
            _report(7, f"enforce 列 deny → 拒绝（{table}）", ok, detail)
            if not ok:
                problems.append(f"⑦ {detail}")

            ok, detail = await _check_enforce_mask(table, columns)
            _report(8, f"enforce mask → 投影被替换（{table}）", ok, detail)
            if not ok:
                problems.append(f"⑧ {detail}")
    finally:
        if policy_id:
            removed = await _cleanup()
            print(f"   清理临时策略：{removed} 条（name LIKE {SMOKE_LIKE!r}）")

    elapsed = time.perf_counter() - started
    print()
    if problems:
        print(f"❌ 权限网关冒烟未通过（{len(problems)} 项，{elapsed:.1f}s）：")
        for item in problems:
            print("   -", item)
        return 1
    print(f"✅ 权限网关冒烟通过（{TOTAL}/{TOTAL}，{elapsed:.1f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
