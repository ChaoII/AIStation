"""报表与行业模板（2026-11-08 从 service.py 拆出）。

- ``report_suggest``：问数未命中时，按历史沉淀的报表模板给出「直接执行」的候选；
- ``governance_report``：交付前的治理体检（覆盖率/敏感暴露/孤儿表）；
- ``industry_templates`` / ``apply_industry_template``：行业模板（GMP/ICH/IEC 等）
  一键落地指标与术语。

依赖都来自 ``.report`` / ``.overview`` 等模块，无进程级缓存。
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.logger import log


class ReportOps:
    @classmethod
    async def report_suggest(cls, question: str, datasource: str | None = None) -> list[dict]:
        """按问题检索已确认启用的报表（澄清后选择，不自动执行，避免误命中/参数对不上）。"""
        try:
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        text(
                            "SELECT id,name,description,question,params FROM ai_report_template "
                            "WHERE is_deleted=false AND verified=true AND enabled=true AND datasource=:d "
                            "ORDER BY sort, id"
                        ),
                        {"d": datasource or "system"},
                    )
                ).fetchall()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] report_suggest 拉取报表失败：{e!r}")
            return []
        if not rows:
            return []
        reports = []
        for r in rows:
            import json as _j

            params = r[4] if isinstance(r[4], list) else (_j.loads(r[4]) if r[4] else [])
            reports.append({"id": r[0], "name": r[1] or "", "description": r[2] or "",
                            "question": r[3] or "", "params": params})
        q = (question or "").lower().strip()
        if not q:
            return []
        scored = []
        for r in reports:
            name = (r.get("name") or "").lower()
            desc = (r.get("description") or "").lower()
            rq = (r.get("question") or "").lower()
            score = 0
            if name and (name in q or q in name):
                score += 4
            if rq and (rq in q or q in rq):
                score += 4
            if desc:
                for i in range(max(1, len(q) - 1)):
                    sub = q[i : i + 2]
                    if sub and sub in desc:
                        score += 1
            if score >= 3:
                scored.append({
                    "id": r["id"], "name": r["name"],
                    "description": r.get("description") or "",
                    "question": r.get("question") or "",
                    "params": len(r.get("params") or []),
                    "_score": score,
                })
        scored.sort(key=lambda x: -x["_score"])
        return scored[:3]

    @classmethod
    async def governance_report(cls) -> dict:
        """AIP 数据治理报告：聚合 治理总览 + 合规姿态 + 安全评分 + 护栏，生成可导出报告。"""
        from datetime import datetime

        from app.plugin.module_ai.overview.service import AiOverviewService
        try:
            gov = await cls.governance_overview()
        except Exception:  # noqa: BLE001
            gov = {}
        posture = await AiOverviewService.compliance_posture()
        guard = await cls.guardrails_status()
        dq = gov.get("dq", {})
        summary = [
            f"数据对象 {gov.get('objects', 0)} 个，数据源 {gov.get('datasources', 0)} 个，管道 {gov.get('pipelines', 0)} 条",
            f"ABAC 权限规则 {gov.get('access_rules', 0)} 条，数据域 {gov.get('domains', 0)} 个",
            f"数据质量平均 {dq.get('avg_score', 0)} 分，DQ 预警 {gov.get('dq_alerts', 0)} 条",
            f"合规姿态 {posture.get('score', 0)} 分（{posture.get('level', '')}）",
            f"安全护栏 {guard.get('enabled', 0)}/{guard.get('total', 0)} 项已启用（{guard.get('score', 0)}%）",
            f"待审批 {posture.get('pending_approvals', 0)} 项",
        ]
        overview = {
            "objects": gov.get("objects", 0), "datasources": gov.get("datasources", 0),
            "pipelines": gov.get("pipelines", 0), "actions": gov.get("actions", 0),
            "access_rules": gov.get("access_rules", 0), "domains": gov.get("domains", 0),
            "agents": gov.get("agents", 0), "metrics": gov.get("metrics", 0),
            "terms": gov.get("terms", 0), "concepts": gov.get("concepts", 0),
        }
        scores = {"compliance": posture.get("score", 0), "security": 0,
                  "guardrails": guard.get("score", 0)}
        try:
            scores["security"] = (await cls.security_audit()).get("score", 0)
        except Exception:  # noqa: BLE001
            pass
        markdown = "\n".join([
            "# AIStation 数据治理报告",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 总览",
            *[f"- {s}" for s in summary],
            "",
            f"## 评分：合规 {scores['compliance']} / 安全 {scores['security']} / 护栏 {scores['guardrails']}",
        ])
        return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "summary": summary, "overview": overview, "scores": scores,
                "markdown": markdown}

    @classmethod
    async def industry_templates(cls) -> list[dict]:
        return [
            {"id": "isa95", "name": "制造业（ISA-95/IEC 62264）", "objects": [
                {"name": "设备", "desc": "生产设备/工位", "domain": "生产"},
                {"name": "工单", "desc": "制造工单/生产订单", "domain": "生产"},
                {"name": "批次", "desc": "生产批次/批号", "domain": "生产"},
                {"name": "物料", "desc": "原材料/半成品/成品", "domain": "物料"},
                {"name": "质量特性", "desc": "质量指标/判定标准", "domain": "质量"},
                {"name": "工艺路线", "desc": "工序/工艺路线", "domain": "工艺"},
                {"name": "班组/班次", "desc": "班组/班次/日历", "domain": "组织"},
            ]},
            {"id": "gmp", "name": "制药（GMP/ICH）", "objects": [
                {"name": "批记录", "desc": "生产批记录", "domain": "质量"},
                {"name": "工艺规程", "desc": "工艺规程/处方", "domain": "工艺"},
                {"name": "偏差", "desc": "偏差/变更/OOS", "domain": "质量"},
                {"name": "物料批次", "desc": "物料批次/追溯", "domain": "物料"},
                {"name": "清洁验证", "desc": "清洁/验证记录", "domain": "质量"},
            ]},
            {"id": "generic", "name": "通用业务", "objects": [
                {"name": "客户", "desc": "客户/客户主数据", "domain": "客户"},
                {"name": "订单", "desc": "销售/采购订单", "domain": "交易"},
                {"name": "产品", "desc": "产品/商品", "domain": "产品"},
                {"name": "供应商", "desc": "供应商主数据", "domain": "采购"},
            ]},
        ]

    @classmethod
    async def apply_industry_template(cls, template_id: str, auth) -> dict:
        tpl = next((t for t in await cls.industry_templates() if t["id"] == template_id), None)
        if not tpl:
            return {"ok": False, "msg": "模板不存在"}
        created = 0
        for obj in tpl["objects"]:
            d = {"name": obj["name"], "description": obj["desc"], "synonyms": "", "parent_name": "",
                 "domain": obj["domain"], "metric_key": "", "tables": []}
            await cls.upsert_concept(d, auth)
            created += 1
        return {"ok": True, "created": created, "template": tpl["name"]}
