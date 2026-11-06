"""问数权限网关端到端冒烟（提交前必跑，约 5~20 秒）。

为什么需要它
------------
策略引擎、编译器、审计三块都有各自单测，但"**真的**拒了没有"只有跑一遍才知道：
2026-11 就出现过"单测全绿、真实提问全部 500"（整段替换删掉了运行时方法）。本脚本
按 spec §11 的验收口径，直接驱动**线上同一套** ``guard.prepare`` / ``compiler.rewrite``，
不经过 LLM、不依赖 HTTP 服务。

五项检查
--------
1. 无主体 → deny（P0：禁止 ``auth=None`` 落到 permit）；
2. 敏感表 ``select *`` → deny（P0 星号止血，三种模式都生效）；
3. 行策略 → 生成的 SQL 含过滤条件（临时插一条 allow，``WHERE name LIKE
   'smoke-policy-%'`` 清理，**不动真实策略**）；
4. 审计表能读到第 2 步的 deny 记录（审计链路真的落库）；
5. 无法解析的 SQL → deny（编译器 + enforce 网关各验一次，fail-closed）。

用法::

    cd backend
    uv run python scripts/query_policy_smoke.py

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

#: 行条件用 ``$attr.*``：顺带验证"属性绑定 → 生成过滤条件"这条真实链路。
SMOKE_CONDITION = "dept_id = $attr.dept_id"
SMOKE_DEPT = "7"

#: 审计里的数据源标记（便于识别、过滤冒烟产生的记录）。
DATASOURCE = "smoke:policy"

TOTAL = 5


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


async def _check_audit(sql: str) -> tuple[bool, str]:
    """④ 审计表能读到第 ② 步的 deny 记录。"""
    from app.plugin.module_ai.query.policy import audit

    want = audit.sql_hash(sql)
    rows = await audit.list_access_logs(limit=100)
    hit = next(
        (r for r in rows if r.get("sql_hash") == want and r.get("decision") == "deny"),
        None,
    )
    if hit is None:
        return False, f"最近 100 条审计里没有 sql_hash={want[:12]}… 的 deny 记录"
    return True, f"id={hit['id']} reason={str(hit.get('reason') or '')[:70]}"


async def _check_parse_fail() -> tuple[bool, str]:
    """⑤ 无法解析的 SQL → deny（编译器 + enforce 网关，两条都验）。

    ``POLICY_ENGINE`` 只作用于**本进程**（``_cfg`` 每次读取都看环境变量），
    不改库、不影响已启动的后端服务。
    """
    from app.plugin.module_ai.query.policy import compiler, repo
    from app.plugin.module_ai.query.policy.guard import prepare

    bad = "select from where (("
    principal = _principal()
    policies = await repo.list_policies()
    plan = compiler.build_plan(policies, principal, {SMOKE_TABLE: ["id"]})
    compiled = compiler.rewrite(bad, plan)
    if compiled.permit:
        return False, "编译器放过了无法解析的 SQL"

    os.environ["POLICY_ENGINE"] = "enforce"
    try:
        gateway = await prepare(
            sql=bad, principal=principal, entry="ask", datasource=DATASOURCE
        )
    finally:
        os.environ.pop("POLICY_ENGINE", None)
    if gateway.permit:
        return False, "enforce 网关放过了无法解析的 SQL"
    return True, f"compiler={compiled.reason[:50]} | guard={gateway.reason[:50]}"


def _report(index: int, title: str, ok: bool, detail: str) -> None:
    mark = "✅" if ok else "❌"
    print(f"[{index}/{TOTAL}] {title} ... {mark} {detail}")


async def main() -> int:
    started = time.perf_counter()
    _load_orm_models()

    try:
        from app.plugin.module_ai.query.policy.model import (
            ensure_policy_tables,
            sensitive_tables,
        )

        await ensure_policy_tables()
        sensitive = sorted(await sensitive_tables())
        await _cleanup()
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
            ok, detail = await _check_audit(sql_star)
        else:
            ok, detail = False, "第 ② 步未执行，没有可核对的 SQL"
        _report(4, "审计表能读到 ② 的 deny 记录", ok, detail)
        if not ok:
            problems.append(f"④ {detail}")

        ok, detail = await _check_parse_fail()
        _report(5, "无法解析的 SQL → deny", ok, detail)
        if not ok:
            problems.append(f"⑤ {detail}")
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
