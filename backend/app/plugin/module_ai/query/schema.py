"""智能问数 pydantic 校验模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MetricParam(BaseModel):
    key: str
    label: str = ""
    type: str = "value"  # value / date / date_range / entity
    from_: str | None = None  # 来源（如实体表/字典）


class MetricDimension(BaseModel):
    key: str
    label: str = ""
    field: str = ""
    type: str = "string"


class QueryMetricUpsert(BaseModel):
    datasource: str = "system"
    key: str
    name: str
    description: str = ""
    sql_template: str
    params: list[dict] = Field(default_factory=list)
    dimensions: list[dict] = Field(default_factory=list)
    agg: str = "count"
    unit: str = ""
    permission_tag: str = ""
    enabled: bool = True
    sort: int = 0
    cache_ttl: int = 0


class QueryTermUpsert(BaseModel):
    datasource: str = "system"
    term: str
    metric_key: str = ""
    field_path: str = ""
    type: str = "term"


class QueryPromoteRequest(BaseModel):
    """FDE 复用闭环：把一条已验证问答沉淀为可复用指标。"""

    message_id: int
    name: str = ""
    key: str = ""


class QueryDatasourceUpsert(BaseModel):
    name: str
    code: str
    type: str = "postgres"
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""
    read_only: bool = True
    default: bool = False
    enabled: bool = True
    allowed_roles: list[str] = Field(default_factory=list)
    filter_rules: dict | None = None
    remark: str = ""


class QueryAskRequest(BaseModel):
    question: str
    session_id: int | None = None
    datasource: str | None = None  # 未指定则自动判定
    stream: bool = False
    force_slow: bool = False  # True 则跳过快路径模板，强制走 LLM 生成 SQL（评测用）


class QueryFeedbackRequest(BaseModel):
    message_id: int
    feedback: str  # up / down
    correct_sql: str | None = None


class QueryFewshotUpsert(BaseModel):
    datasource: str = "system"
    question: str
    sql: str
    enabled: bool = True


class QueryAssetUpsert(BaseModel):
    table_name: str
    alias: str = ""
    domain: str = ""
    description: str = ""
    business_scenarios: str = ""
    included: bool = True
    remark: str = ""
    # P0·对象化
    object_enabled: bool = False
    object_key_col: str = "id"
    object_name_col: str = "name"
    object_icon: str = "el-icon-Box"


class QueryAssetColumnUpsert(BaseModel):
    table_name: str
    column_name: str
    description: str = ""
    business_scenarios: str = ""
    related_table: str = ""
    related_field: str = ""
    included: bool = True
    sensitive: bool = False
    enum: list | None = None  # 枚举/选项（如燃煤类型 [低硫,高硫]）


class QuerySettingUpsert(BaseModel):
    key: str
    value: str = ""
    remark: str = ""


class QueryRunRequest(BaseModel):
    """直接用指标/数据源执行（调试用）。"""

    metric_key: str | None = None
    datasource: str | None = None
    sql: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
