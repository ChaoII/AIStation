"""问数侧 LLM 结构化输出的 Pydantic 契约。

用途：交给 agno ``Agent(output_schema=...)``，由**模型原生 JSON schema**约束输出，
替代「提示词里要求 JSON + 事后手工解析」的脆弱做法（见 ``service._llm_structured``）。

设计约束：
- 字段一律给默认值，避免模型漏字段时整次调用失败（漏了就取默认，比抛错更可用）；
- 与既有提示词里的 JSON 结构**一一对应**，保证下游（``rules`` / ``metrics`` /
  ``system_suggest`` / ``columns`` 等）拿到的键名不变。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class FilterSystemTable(BaseModel):
    """系统表识别规则四要素。"""

    prefixes: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exact: list[str] = Field(default_factory=list)
    regex: str = ""


class FilterRules(BaseModel):
    """筛选规则主体（enabled + 系统表四要素 + 审计字段）。"""

    enabled: bool = True
    system_table: FilterSystemTable = Field(default_factory=FilterSystemTable)
    audit_fields: list[str] = Field(default_factory=list)


class FilterRulesOut(BaseModel):
    """``suggest_filter_rules`` / ``parse_filter_rules`` 的输出契约。"""

    rules: FilterRules = Field(default_factory=FilterRules)


class SuggestItem(BaseModel):
    """分类建议项：名称 + 中文依据。"""

    name: str
    reason: str = ""


class ClassifyAdviseOut(BaseModel):
    """``classify_advise`` 的输出契约。"""

    system_suggest: list[SuggestItem] = Field(default_factory=list)
    audit_suggest: list[SuggestItem] = Field(default_factory=list)


class MetricSuggestion(BaseModel):
    """候选指标：名称 + 可执行 SQL + 聚合类型。"""

    name: str
    sql: str = ""
    agg: str = ""


class TermSuggestion(BaseModel):
    """候选术语：口语叫法 + 类型 + 指向（指标名或 表.字段）。"""

    term: str
    type: str = ""
    target: str = ""


class MetricsTermsOut(BaseModel):
    """``suggest_metrics_terms`` 的输出契约。"""

    metrics: list[MetricSuggestion] = Field(default_factory=list)
    terms: list[TermSuggestion] = Field(default_factory=list)


class AssetDescriptionOut(BaseModel):
    """``generate_asset_descriptions`` 的单表输出契约。"""

    table: str = ""
    columns: dict[str, str] = Field(default_factory=dict)


class PlanOut(BaseModel):
    """两段式分解的**执行计划**契约（对应 ``plan.plan_prompt`` 要求的 JSON）。"""

    tables: list[str] = Field(default_factory=list)
    joins: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    window: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    order_limit: str = ""
