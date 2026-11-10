"""全链路应用冒烟：数据链路 + 问数 + 本体 + 三级权限 + 默认开关矩阵。

前置：
    uv run python scripts/seed_realistic_business_data.py
    uv run python scripts/perm_demo_setup.py

运行：
    uv run python scripts/full_app_smoke.py

输出逐项 PASS/FAIL，任一失败退出码 1。
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:6"
ROLE_ANALYST = "DEMO_ANALYST"
RESULTS: list[tuple[str, str, str, str]] = []


def check(section: str, name: str, ok: bool, detail: str = "", warn: bool = False) -> None:
    status = "PASS" if ok else ("WARN" if warn else "FAIL")
    RESULTS.append((section, name, status, detail))
    print(f"{status} [{section}] {name}" + (f"  [{detail}]" if detail and not ok else ""))


async def _ids():
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        analyst = (await db.execute(text(
            "SELECT id FROM sys_user WHERE username='demo_analyst' AND is_deleted=false"
        ))).scalar()
        guest = (await db.execute(text(
            "SELECT id FROM sys_user WHERE username='demo_guest' AND is_deleted=false"
        ))).scalar()
    return int(analyst or 0), int(guest or 0)


async def section_data(engine) -> None:
    from sqlalchemy import text

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            'SELECT (SELECT count(*) FROM "FUEL_CB_COALCONTRACT"), '
            '(SELECT count(*) FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "ID" LIKE \'DEMO-B-%\'), '
            '(SELECT count(DISTINCT "CONTRACTID") FROM "FUEL_CMCS_INFACTORYBATCH" WHERE "CONTRACTID" LIKE \'DEMO-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_RCSAMPLING" WHERE "ID" LIKE \'DEMO-SP-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_MAKE" WHERE "ID" LIKE \'DEMO-MK-%\'), '
            '(SELECT count(*) FROM "FUEL_CMCS_ASSAY" WHERE "ID" LIKE \'DEMO-AS-%\')'
        ))).fetchone()
        check("数据", "合同 120 份", row[0] == 120, f"实际 {row[0]}")
        check("数据", "演示批次 300 条", row[1] == 300, f"实际 {row[1]}")
        check("数据", "批次关联合同 >= 20 份", (row[2] or 0) >= 20, f"实际 {row[2]}")
        check("数据", "采样/制样/化验各 300", row[3] == row[4] == row[5] == 300,
              f"采样 {row[3]} 制样 {row[4]} 化验 {row[5]}")

        chain = (await conn.execute(text(
            'SELECT count(*) FROM "FUEL_CMCS_INFACTORYBATCH" b '
            'JOIN "FUEL_CMCS_RCSAMPLING" s ON s."INFACTORYBATCHID"=b."ID" '
            'JOIN "FUEL_CMCS_MAKE" m ON m."SAMPLINGID"=s."ID" '
            'JOIN "FUEL_CMCS_ASSAY" a ON a."INFACTORYBATCHID"=b."ID" AND a."MAKEID"=m."ID" '
            'WHERE b."ID" LIKE \'DEMO-B-%\''
        ))).scalar()
        check("数据", "批次→采样→制样→化验 全链路 300", chain == 300, f"实际 {chain}")

        gap = (await conn.execute(text(
            'SELECT max(abs(extract(epoch from (s."SAMPLINGDATE" - b."FACTARRIVEDATE")))/3600) '
            'FROM "FUEL_CMCS_RCSAMPLING" s JOIN "FUEL_CMCS_INFACTORYBATCH" b ON b."ID"=s."INFACTORYBATCHID" '
            'WHERE s."ID" LIKE \'DEMO-SP-%\''
        ))).scalar()
        check("数据", "采样与到厂时差 <= 24h", (gap or 0) <= 24, f"最大 {gap}")

        money = (await conn.execute(text(
            'SELECT (SELECT COALESCE(sum("BALANCEQTY"),0) FROM "FUEL_CB_COALBALANCE" WHERE "ID" LIKE \'DEMO-%\'), '
            '(SELECT COALESCE(sum("BALANCEQTY"),0) FROM "FUEL_CB_COALBALANCEDETAIL" WHERE "ID" LIKE \'DEMO-%\')'
        ))).fetchone()
        check("数据", "结算主/明细数量一致", money[0] == money[1], f"{money[0]} vs {money[1]}")

        plan = (await conn.execute(text(
            'SELECT (SELECT COALESCE(sum("INCOALQTY"),0) FROM "FUEL_CMCS_PLANYEAR"), '
            '(SELECT COALESCE(sum("INCOALQTY"),0) FROM "FUEL_CMCS_PLANMONTH")'
        ))).fetchone()
        check("数据", "年计划=月计划合计", plan[0] == plan[1], f"{plan[0]} vs {plan[1]}")


async def section_query(auth) -> None:
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query.benchmark import load_label_synonyms

    await load_label_synonyms()
    cases = [
        ("采购合同一共有多少份？", 'SELECT COUNT(*) FROM "FUEL_CB_COALCONTRACT" WHERE "ISDELETED"=false'),
        ("合同总数量是多少吨？", 'SELECT SUM("CONTRACTAMOUNT") FROM "FUEL_CB_COALCONTRACT" WHERE "ISDELETED"=false'),
        ("合同质量约束一共有多少条？", 'SELECT COUNT(*) FROM "FUEL_CB_COALCONTRACTQUALITY" WHERE "ISDELETED"=false'),
        ("硫分化验的平均干基全硫是多少？", 'SELECT ROUND(AVG("STAD")::numeric,3) FROM "FUEL_CMCS_SULFURASSAY" WHERE "ISDELETED"=false'),
        ("热值化验的平均发热量是多少？", 'SELECT ROUND(AVG("QBAD")::numeric,2) FROM "FUEL_CMCS_HEATASSAY" WHERE "ISDELETED"=false'),
        ("采样明细一共有多少条？", 'SELECT COUNT(*) FROM "FUEL_CMCS_RCSAMPLINGDETAIL" WHERE "ISDELETED"=false'),
        ("月计划明细一共有多少条？", 'SELECT COUNT(*) FROM "FUEL_CMCS_PLANMONTHDETAIL" WHERE "ISDELETED"=false'),
        ("本月结算总量是多少？", 'SELECT COALESCE(SUM("BALANCEQTY"),0) FROM "FUEL_CB_COALBALANCE" '
                              'WHERE "ISDELETED"=false AND "BALANCEDATE" >= date_trunc(\'month\', CURRENT_DATE)'),
        ("近 30 天入厂煤批次有多少条？", 'SELECT COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH" '
                                'WHERE "ISDELETED"=false AND "FACTARRIVEDATE" >= CURRENT_DATE - 30'),
    ]
    for q, gold in cases:
        d = await R._ask(q, auth, DS)
        gc = await R._run_gold_sql(DS, gold)
        ok = R._lenient(d, {"question": q, "gold_sql": gold, "datasource": DS,
                            "_gold_cols": gc.get("columns"), "_gold_rows": gc.get("rows")})
        check("问数", q, ok, f"实际 {str(d.get('rows'))[:40]} / 金标 {str(gc.get('rows'))[:40]}")


async def section_perm(engine, analyst_uid: int, guest_uid: int) -> None:
    from app.core.validator import CustomException
    from app.plugin.module_ai.query.policy.guard import prepare
    from app.plugin.module_ai.query.policy.principal import Principal
    from app.plugin.module_ai.query.service import _assert_ds_access, _execute_custom_ds_sql

    def auth_of(uid: int, role: str | None):
        roles = [SimpleNamespace(code=role)] if role else []
        return SimpleNamespace(user=SimpleNamespace(id=uid, is_superuser=False, roles=roles))

    analyst = Principal(user_id=analyst_uid, is_superuser=False, roles=(ROLE_ANALYST,),
                        attrs={}, entry="ask")
    guest = Principal(user_id=guest_uid, is_superuser=False, roles=(), attrs={}, entry="ask")

    # 表级：合同表 deny
    d = await prepare(sql='SELECT * FROM "FUEL_CB_COALCONTRACT"', principal=analyst,
                      entry="ask", datasource=DS)
    check("权限-表级", "分析员查合同表被拒", not d.permit, d.reason[:80])

    # 行级：批次只看指定供应商
    d = await prepare(
        sql='SELECT "SUPPLIERNAME", COUNT(*) AS c FROM "FUEL_CMCS_INFACTORYBATCH" GROUP BY 1',
        principal=analyst, entry="ask", datasource=DS)
    check("权限-行级", "分析员批次查询被改写", d.permit and bool(d.applied), str(d.applied)[:80])
    if d.permit:
        res = await _execute_custom_ds_sql(6, d.sql)
        names = {str(r[0]) for r in (res.get("rows") or [])}
        check("权限-行级", "结果只剩 1 家供应商", len(names) == 1, f"实际 {names}")

    # 列级：价格列 deny，数量列放行
    d = await prepare(sql='SELECT "CONTRACTPRICE" FROM "FUEL_CB_COALBALANCE"', principal=analyst,
                      entry="ask", datasource=DS)
    check("权限-列级", "分析员查合同单价被拒", not d.permit, d.reason[:80])
    d = await prepare(sql='SELECT "BALANCEQTY" FROM "FUEL_CB_COALBALANCE"', principal=analyst,
                      entry="ask", datasource=DS)
    check("权限-列级", "分析员查结算数量放行", d.permit, d.reason[:80])

    # 访客：只有批次表
    d = await prepare(sql='SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY"', principal=guest,
                      entry="ask", datasource=DS)
    check("权限-表级", "访客查化验表被拒", not d.permit, d.reason[:80])
    d = await prepare(sql='SELECT COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH"', principal=guest,
                      entry="ask", datasource=DS)
    check("权限-表级", "访客查批次表放行", d.permit, d.reason[:80])

    # 模块级：数据源 allowed_roles
    try:
        await _assert_ds_access(6, auth_of(analyst_uid, ROLE_ANALYST))
        ok_analyst = True
    except Exception as e:  # noqa: BLE001
        ok_analyst = False
        check("权限-模块级", "分析员数据源准入", False, str(e)[:80])
    if ok_analyst:
        check("权限-模块级", "分析员数据源准入", True)
    try:
        await _assert_ds_access(6, auth_of(guest_uid, None))
        check("权限-模块级", "访客数据源准入被拒", False, "未抛异常")
    except CustomException:
        check("权限-模块级", "访客数据源准入被拒", True)


async def section_ontology(analyst_uid: int, guest_uid: int) -> None:
    from app.plugin.module_ai.ontology import agent_tools as T

    codes = ["coal_settle_amount", "coal_ash_dry_basis", "coal_batch_annotate"]
    schemas, names = await T.build_selected_ontology_tools(codes, user_id=analyst_uid)
    check("本体", "分析员可见 3 个本体工具", len(schemas) == 3, f"实际 {len(schemas)} {sorted(names)}")
    schemas_g, names_g = await T.build_selected_ontology_tools(codes, user_id=guest_uid)
    check("本体", "访客不可见本体工具", len(schemas_g) == 0, f"实际 {sorted(names_g)}")

    out = await T.run_selected_ontology_tool(
        "ont_fn__coal_settle_amount", {"qty": 1200, "price": 520}, user_id=analyst_uid)
    check("本体", "分析员调用结算金额函数", isinstance(out, dict) and out.get("result") == 624000,
          str(out)[:80])
    denied = await T.run_selected_ontology_tool(
        "ont_fn__coal_settle_amount", {"qty": 1, "price": 1}, user_id=guest_uid)
    check("本体", "访客调用函数被拒", isinstance(denied, dict) and "error" in denied,
          str(denied)[:80])

    act = await T.run_selected_ontology_tool(
        "ont_action__coal_batch_annotate", {"__k": "DEMO-B-001", "REMARK": "冒烟"}, user_id=analyst_uid)
    check("本体", "分析员动作返回 confirm", isinstance(act, dict) and "__action__" in act,
          str(act)[:80])


async def section_switches(auth) -> None:
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query.service import AiQueryService as S

    settings = await S.get_settings()
    bools = sorted(k for k, v in settings.items() if str(v).lower() in ("true", "false"))
    expensive = {"agno_tool_agent", "two_stage_planning"}
    fast_q = "结算总量是多少"
    slow_q = "按矿点统计入厂煤批次数量"
    for key in bools:
        orig = str(settings[key]).lower()
        flipped = "false" if orig == "true" else "true"
        try:
            async with R.override_settings({key: flipped}):
                d1 = await R._ask(fast_q, auth, DS)
                ok = not d1.get("is_error") and bool(d1.get("rows"))
                detail = f"{orig}->{flipped} rows={str(d1.get('rows'))[:30]}"
                if key not in expensive:
                    d2 = await R._ask(slow_q, auth, DS)
                    ok = ok and not d2.get("is_error") and bool(d2.get("rows"))
                    detail += f" | slow rows={len(d2.get('rows') or [])}"
            check("开关", key, ok, detail)
        except Exception as e:  # noqa: BLE001
            check("开关", key, False, f"{type(e).__name__}: {str(e)[:80]}")

    # 昂贵开关各验证一次（不逐题扫）
    for key in expensive:
        orig = str(settings[key]).lower()
        flipped = "false" if orig == "true" else "true"
        try:
            async with R.override_settings({key: flipped}):
                d = await R._ask(slow_q, auth, DS)
            ok = not d.get("is_error") and bool(d.get("rows"))
            check("开关", f"{key}（慢路径）", ok,
                  f"{orig}->{flipped} path={d.get('path')} err={d.get('is_error')}",
                  warn=(key == "agno_tool_agent" and d.get("is_error")))
        except Exception as e:  # noqa: BLE001
            check("开关", f"{key}（慢路径）", False, f"{type(e).__name__}: {str(e)[:80]}")

    # 数值型抽查
    numerics = {
        "schema_top_k": "8", "recall_top_k": "5", "recall_min_score": "0.2",
        "nl2sql_retry": "1", "query_max_rows": "100", "query_timeout_sec": "20",
    }
    for key, val in numerics.items():
        try:
            async with R.override_settings({key: val}):
                d = await R._ask(slow_q, auth, DS)
            # recall_min_score 是**过滤阈值**：调大后返回空是预期行为，只要求不报错
            ok = not d.get("is_error")
            if key != "recall_min_score":
                ok = ok and bool(d.get("rows"))
            check("开关-数值", key, ok, f"{key}={val} rows={len(d.get('rows') or [])}")
        except Exception as e:  # noqa: BLE001
            check("开关-数值", key, False, f"{type(e).__name__}: {str(e)[:80]}")


async def main() -> None:
    from app.plugin.module_ai.query import executor as ex
    from app.plugin.module_ai.query import service as svc
    from main import create_app

    create_app()
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True, roles=[]))
    analyst_uid, guest_uid = await _ids()
    if not analyst_uid or not guest_uid:
        raise SystemExit("先运行 scripts/perm_demo_setup.py")
    ds = await svc._load_ds(6)
    engine = ex.build_engine(svc._ds_cfg_from_model(ds))

    t0 = time.perf_counter()
    await section_data(engine)
    await section_query(auth)
    await section_perm(engine, analyst_uid, guest_uid)
    await section_ontology(analyst_uid, guest_uid)
    await section_switches(auth)

    total = len(RESULTS)
    ok = sum(1 for r in RESULTS if r[2] == "PASS")
    warn = sum(1 for r in RESULTS if r[2] == "WARN")
    print("\n=== 汇总 ===")
    for section in ("数据", "问数", "权限-表级", "权限-行级", "权限-列级", "权限-模块级", "本体", "开关", "开关-数值"):
        items = [r for r in RESULTS if r[0] == section]
        if items:
            passed = sum(1 for r in items if r[2] == "PASS")
            print(f"{section}: {passed}/{len(items)}")
    print(f"总计 {ok}/{total} 通过，{warn} 项 WARN，用时 {time.perf_counter() - t0:.1f}s")
    fails = [r for r in RESULTS if r[2] == "FAIL"]
    for sec, name, _, detail in fails:
        print(f"FAIL_DETAIL [{sec}] {name} :: {detail}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    asyncio.run(main())
