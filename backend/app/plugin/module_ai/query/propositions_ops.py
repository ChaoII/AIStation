"""FDE 交付命题与影子校验（2026-11-08 从 service.py 拆出）。

命题 = 「某类业务结论 + 判定条件」，影子校验（``shadow_check``）拿真实数据跑一遍，
把「命题说的一定成立」变成可验证的布尔值，避免交付口径停留在文档里。
"""
from __future__ import annotations

from app.core.database import async_db_session

#: 与 service 同值（搬移期间重复定义，避免循环导入）
SYSTEM_DS = "system"


async def _execute_metric(*args, **kwargs):
    """延迟转发到 service 的实现（service 导入期未就绪；也让测试打桩继续生效）。"""
    from .service import _execute_metric as _impl

    return await _impl(*args, **kwargs)


class PropositionsOps:
    @classmethod
    async def list_propositions(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,title,description,criteria,owner,step_diagnosis,step_modeling,"
                "step_assembly,step_shadow,step_handover,gap,delivery_assets,status,created_time,"
                "fde_translator,fde_data,fde_app,shadow_metric,shadow_golden,shadow_tolerance,"
                "shadow_result,shadow_actual,shadow_at "
                "FROM ai_delivery_proposition WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "title": r[1] or "", "description": r[2] or "", "criteria": r[3] or "",
            "owner": r[4] or "", "steps": {
                "diagnosis": r[5], "modeling": r[6], "assembly": r[7], "shadow": r[8], "handover": r[9],
            },
            "gap": r[10] if isinstance(r[10], list) else (_json.loads(r[10]) if r[10] else []),
            "delivery_assets": r[11] if isinstance(r[11], list) else (_json.loads(r[11]) if r[11] else []),
            "status": r[12] or "open", "created_time": str(r[13]) if r[13] else "",
            "fde_translator": r[14] or "", "fde_data": r[15] or "", "fde_app": r[16] or "",
            "shadow_metric": r[17] or "", "shadow_golden": r[18] or "", "shadow_tolerance": r[19] or "",
            "shadow_result": r[20] or "", "shadow_actual": r[21] or "", "shadow_at": str(r[22]) if r[22] else "",
        } for r in rows]

    @classmethod
    async def upsert_proposition(cls, data: dict, auth) -> dict:
        import json as _json
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            pid = data.get("id")
            gap = _json.dumps(data.get("gap") or [], ensure_ascii=False)
            assets = _json.dumps(data.get("delivery_assets") or [], ensure_ascii=False)
            if pid:
                await db.execute(_t(
                    "UPDATE ai_delivery_proposition SET title=:t, description=:d, criteria=:c, owner=:o, "
                    "step_diagnosis=:s1, step_modeling=:s2, step_assembly=:s3, step_shadow=:s4, "
                    "step_handover=:s5, gap=:g, delivery_assets=:a, status=:st, "
                    "fde_translator=:ft, fde_data=:fd, fde_app=:fa, "
                    "shadow_metric=:sm, shadow_golden=:sg, shadow_tolerance=:stl, updated_time=now() "
                    "WHERE id=:pid"), {
                    "t": data.get("title", ""), "d": data.get("description", ""),
                    "c": data.get("criteria", ""), "o": data.get("owner", ""),
                    "s1": data.get("steps", {}).get("diagnosis", "todo"),
                    "s2": data.get("steps", {}).get("modeling", "todo"),
                    "s3": data.get("steps", {}).get("assembly", "todo"),
                    "s4": data.get("steps", {}).get("shadow", "todo"),
                    "s5": data.get("steps", {}).get("handover", "todo"),
                    "g": gap, "a": assets, "st": data.get("status", "open"), "pid": pid,
                    "ft": data.get("fde_translator", ""), "fd": data.get("fde_data", ""),
                    "fa": data.get("fde_app", ""), "sm": data.get("shadow_metric", ""),
                    "sg": data.get("shadow_golden", ""), "stl": data.get("shadow_tolerance", "")})
            else:
                res = await db.execute(_t(
                    "INSERT INTO ai_delivery_proposition(title,description,criteria,owner,step_diagnosis,"
                    "step_modeling,step_assembly,step_shadow,step_handover,gap,delivery_assets,status,"
                    "fde_translator,fde_data,fde_app,shadow_metric,shadow_golden,shadow_tolerance) "
                    "VALUES (:t,:d,:c,:o,:s1,:s2,:s3,:s4,:s5,:g,:a,:st,:ft,:fd,:fa,:sm,:sg,:stl) RETURNING id"), {
                    "t": data.get("title", ""), "d": data.get("description", ""),
                    "c": data.get("criteria", ""), "o": data.get("owner", ""),
                    "s1": data.get("steps", {}).get("diagnosis", "todo"),
                    "s2": data.get("steps", {}).get("modeling", "todo"),
                    "s3": data.get("steps", {}).get("assembly", "todo"),
                    "s4": data.get("steps", {}).get("shadow", "todo"),
                    "s5": data.get("steps", {}).get("handover", "todo"),
                    "g": gap, "a": assets, "st": data.get("status", "open"),
                    "ft": data.get("fde_translator", ""), "fd": data.get("fde_data", ""),
                    "fa": data.get("fde_app", ""), "sm": data.get("shadow_metric", ""),
                    "sg": data.get("shadow_golden", ""), "stl": data.get("shadow_tolerance", "")})
                pid = res.scalar()
        return {"id": pid}

    @classmethod
    async def shadow_check(cls, proposition_id: int) -> dict:
        """P2-① 影子运行：执行命题绑定的指标，与黄金标准比对（±容差）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT shadow_metric,shadow_golden,shadow_tolerance FROM ai_delivery_proposition WHERE id=:i"),
                {"i": proposition_id})).fetchone()
        if not row or not row[0]:
            return {"ok": False, "msg": "未配置校验指标/黄金标准"}
        metric_key, golden, tol = row[0], row[1] or "", row[2] or ""
        try:
            metrics = await cls.list_metrics(SYSTEM_DS)
            m = next((x for x in metrics if x["key"] == metric_key), None)
            if not m:
                return {"ok": False, "msg": f"指标 {metric_key} 不存在"}
            from types import SimpleNamespace as SN
            auth = SN(user=SN(id=1))
            res = await _execute_metric(m, {}, auth)
            actual = res.get("rows", [[None]])[0][0] if res.get("rows") else None
            sv = float(actual) if actual is not None else None
            gv = float(golden) if golden else None
            ok = False
            if sv is not None and gv is not None:
                if tol.endswith("%") and gv != 0:
                    ok = abs(sv - gv) / abs(gv) * 100 <= float(tol[:-1])
                elif tol.endswith("%") and gv == 0:
                    ok = sv == 0
                elif tol:
                    ok = abs(sv - gv) <= float(tol)
                else:
                    ok = sv == gv
            result = "pass" if ok else "fail"
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                await db.execute(_t(
                    "UPDATE ai_delivery_proposition SET shadow_result=:r, shadow_actual=:a, "
                    "step_shadow=:ss, shadow_at=now() WHERE id=:i"), {
                    "r": result, "a": str(actual), "ss": "done" if ok else "doing", "i": proposition_id})
            return {"ok": True, "result": result, "actual": actual, "golden": golden, "tolerance": tol}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"校验失败：{str(e)[:120]}"}

    @classmethod
    async def delete_proposition(cls, pid: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t("UPDATE ai_delivery_proposition SET is_deleted=true WHERE id=:pid"), {"pid": pid})
