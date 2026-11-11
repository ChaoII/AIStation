"""数据权限评测：表级 / 行级 / 列级 / 模块级 + 端到端问数 + 泄漏检查。

前置：scripts/perm_demo_setup.py（demo_analyst / demo_guest / 策略 / ACL）。
运行：uv run python scripts/eval_permissions.py
退出码：有失败或数据泄漏 → 1。
"""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:6"
ROLE = "DEMO_ANALYST"
RESULTS: list[tuple[str, str, bool, str]] = []


def check(section: str, name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((section, name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + f"[{section}] {name}" + (f"  [{detail}]" if detail and not ok else ""))


def auth_of(uid: int, role: str | None):
    roles = [SimpleNamespace(code=role)] if role else []
    return SimpleNamespace(user=SimpleNamespace(id=uid, is_superuser=False, roles=roles))


async def ids():
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        a = (await db.execute(text("SELECT id FROM sys_user WHERE username='demo_analyst'"))).scalar()
        g = (await db.execute(text("SELECT id FROM sys_user WHERE username='demo_guest'"))).scalar()
    return int(a or 0), int(g or 0)


async def main() -> None:
    from app.core.validator import CustomException
    from app.plugin.module_ai.query.policy.guard import prepare
    from app.plugin.module_ai.query.policy.principal import Principal
    from app.plugin.module_ai.query.service import AiQueryService as S
    from app.plugin.module_ai.query.service import _assert_ds_access
    from main import create_app

    create_app()
    a_uid, g_uid = await ids()
    if not a_uid or not g_uid:
        raise SystemExit("先运行 scripts/perm_demo_setup.py")
    analyst = auth_of(a_uid, ROLE)
    guest = auth_of(g_uid, None)
    p_analyst = Principal(user_id=a_uid, is_superuser=False, roles=(ROLE,), attrs={}, entry="ask")
    p_guest = Principal(user_id=g_uid, is_superuser=False, roles=(), attrs={}, entry="ask")

    # ---------- 端到端问数 ----------
    async def ask(q: str, auth) -> dict:
        # 慢路径偶发模型超时：权限断言允许重试一次，避免把"超时"误判成"权限错误"
        last: dict = {"is_error": True, "answer": "not run", "rows": None}
        for _ in range(2):
            try:
                d = await S.ask(q, auth, None, DS)
            except Exception as e:  # noqa: BLE001
                d = {"is_error": True, "answer": str(e), "rows": None}
            if not d.get("is_error"):
                return d
            last = d
        return last

    d = await ask("按供应商统计入厂煤批次数量", analyst)
    rows = d.get("rows") or []
    names = {str(r[0]) for r in rows if r}
    check("行级", "分析员只看到 1 家供应商", len(names) == 1 and not d.get("is_error"),
          f"实际 {names} err={d.get('is_error')}")
    check("行级", "行级过滤没有放回其它供应商", all("山煤" in n for n in names), f"实际 {names}")

    d = await ask("燃煤合同一共有多少份", analyst)
    check("表级", "分析员查合同表被拒", d.get("is_error") and "拒绝" in str(d.get("answer")),
          str(d.get("answer"))[:80])
    check("表级", "被拒题没有返回数据", not d.get("rows"), f"rows={d.get('rows')}")

    d = await ask("合同数量合计是多少", analyst)
    check("表级-快路径", "快路径指标不绕过表权限", d.get("is_error") and not d.get("rows"),
          f"path={d.get('path')} rows={d.get('rows')}")

    d = await ask("结算主表的平均合同单价是多少", analyst)
    ans = str(d.get("answer") or "")
    check("列级", "分析员查结算单价被列策略拒绝", d.get("is_error") and "列" in ans and "contractprice" in ans.lower(),
          ans[:90])
    check("列级", "列拒绝没有返回价格", not d.get("rows"), f"rows={d.get('rows')}")

    d = await ask("结算总量是多少", analyst)
    check("列级", "分析员查结算总量放行", not d.get("is_error") and bool(d.get("rows")),
          f"err={d.get('is_error')} rows={d.get('rows')}")

    # ---------- 网关级（不经过 LLM，稳定断言） ----------
    d = await prepare(
        sql='SELECT "SUPPLIERNAME", COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH" GROUP BY 1',
        principal=p_analyst, entry="ask", datasource=DS)
    sql = " ".join(str(d.sql or "").split())
    check("行级-网关", "编译后 SQL 含供应商过滤", d.permit and "SUPPLIERNAME" in sql and "where" in sql.lower(),
          sql[:140])
    d = await prepare(sql='SELECT * FROM "FUEL_CB_COALCONTRACT"', principal=p_analyst, entry="ask", datasource=DS)
    check("表级-网关", "合同表 deny", not d.permit, d.reason[:80])
    d = await prepare(sql='SELECT "CONTRACTPRICE" FROM "FUEL_CB_COALBALANCE"', principal=p_analyst,
                      entry="ask", datasource=DS)
    check("列级-网关", "价格列 deny", not d.permit and "contractprice" in d.reason.lower(), d.reason[:80])
    d = await prepare(sql='SELECT "BALANCEQTY" FROM "FUEL_CB_COALBALANCE"', principal=p_analyst,
                      entry="ask", datasource=DS)
    check("列级-网关", "数量列 allow", d.permit, d.reason[:80])
    d = await prepare(sql='SELECT COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH"', principal=p_guest,
                      entry="ask", datasource=DS)
    # 访客在 ds:6 的模块级已被拒；网关层单独验证表 allow
    check("表级-网关", "访客批次表 allow（网关）", d.permit, d.reason[:80])
    d = await prepare(sql='SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY"', principal=p_guest, entry="ask", datasource=DS)
    check("表级-网关", "访客化验表 deny（网关）", not d.permit, d.reason[:80])

    # ---------- 模块级 ----------
    try:
        await _assert_ds_access(6, analyst)
        check("模块级", "分析员可进 ds:6", True)
    except Exception as e:  # noqa: BLE001
        check("模块级", "分析员可进 ds:6", False, str(e)[:80])
    try:
        await _assert_ds_access(6, guest)
        check("模块级", "访客被 ds:6 拒绝", False, "未抛异常")
    except CustomException:
        check("模块级", "访客被 ds:6 拒绝", True)

    total = len(RESULTS)
    ok = sum(1 for *_, p, _ in RESULTS if p)
    leaks = [r for r in RESULTS if r[0] in ("表级", "列级") and "没有返回" in r[1] and not r[2]]
    print(f"\n=== 权限评测：{ok}/{total} 通过，数据泄漏 {len(leaks)} 项 ===")
    for sec, name, passed, detail in RESULTS:
        if not passed:
            print(f"FAIL_DETAIL [{sec}] {name} :: {detail}")
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
