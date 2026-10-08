"""数据治理能力 → Agent 工具（阶段2）。

把治理域（数据质量 DQ / 数据域 / 血缘影响 / 权限策略 / 治理概览）暴露为 Agent 可按需
调用的工具，与本体工具同构（OpenAI function schema + 派发器），由 agent 运行时并入
工具集。能力模型见 ``docs/ai-agent-capability-model.md``。
"""
from __future__ import annotations

from typing import Any


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


GOVERNANCE_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "governance_overview",
            "description": "数据治理概览：数据域 / 访问策略 / 数据质量健康分等汇总",
            "parameters": _obj({}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_quality",
            "description": "数据质量：给定表名则检查该表，否则返回整体 DQ 概览",
            "parameters": _obj({"table_name": {"type": "string", "description": "可选：目标表"}}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_quality_alert",
            "description": "数据质量预警：风险表（健康分低于阈值）及其下游影响",
            "parameters": _obj({}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_data_domains",
            "description": "列出数据域及归属对象（数据隔离/治理）",
            "parameters": _obj({}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_lineage",
            "description": "数据血缘：mode=full 返回完整血缘（表→字段/指标/对象/管道/术语）；mode=impact 返回下游影响",
            "parameters": _obj(
                {
                    "table_name": {"type": "string", "description": "目标表名"},
                    "mode": {"type": "string", "enum": ["full", "impact"], "description": "默认 full"},
                },
                ["table_name"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_access_rules",
            "description": "列出数据访问策略（ABAC 权限规则）",
            "parameters": _obj({}),
        },
    },
]

GOVERNANCE_TOOL_NAMES: set[str] = {s["function"]["name"] for s in GOVERNANCE_TOOL_SCHEMAS}


async def run_governance_tool(name: str, args: dict, user_id: int | None = None) -> Any:
    """数据治理工具派发。"""
    from app.plugin.module_ai.query.service import AiQueryService as Q

    args = args or {}
    try:
        if name == "governance_overview":
            return await Q.governance_overview()
        if name == "data_quality":
            table = (args.get("table_name") or "").strip()
            return await (Q.dq_run(table) if table else Q.dq_overview())
        if name == "data_quality_alert":
            return await Q.dq_alert()
        if name == "list_data_domains":
            return await Q.list_domains()
        if name == "data_lineage":
            table = (args.get("table_name") or "").strip()
            if not table:
                return {"error": "缺少表名"}
            mode = (args.get("mode") or "full").strip()
            return await (Q.impact_analysis(table) if mode == "impact" else Q.lineage(table))
        if name == "list_access_rules":
            return await Q.list_access_rules()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    return {"error": f"未知治理工具：{name}"}
