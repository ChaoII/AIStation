"""本体（Ontology）独立模块：对象类型 / 属性类型 / 关联类型 / 动作类型 的强类型元模型。

对标 Palantir Ontology —— 创建对象类型**不必先有数据库表**，由元模型驱动：
定义 Object + Property 后，可通过 ``materialize_object`` 生成真实表（本体驱动表），
供问数 / Agent / Workshop / 管道 / 治理消费。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text as _t

from app.core.database import async_db_session, async_engine
from app.core.exceptions import CustomException

from . import action_engine as _ae
from . import function_engine as _fe
from . import security as _sec

# ---------------------------------------------------------------------------
# 建表入口：ai_ont_* 全部表
#
# 历史遗留：这些表此前只在开发库中手工创建，代码里没有建表语句，新环境部署会直接失败。
# 这里补齐统一的运行时建表（幂等、best-effort），并作为后续列演进的唯一入口。
# SQLite（单元测试库）不支持 BIGSERIAL / ADD COLUMN IF NOT EXISTS，由测试自身的 DDL
# 提供结构，此处失败不影响功能。
# ---------------------------------------------------------------------------
_ont_schema_ready = False

_ONT_TABLES_SQL = (
    "CREATE TABLE IF NOT EXISTS ai_ont_object ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(128) UNIQUE, name VARCHAR(160), "
    "icon VARCHAR(60) DEFAULT '', key_prop VARCHAR(80) DEFAULT '', name_prop VARCHAR(80) DEFAULT '', "
    "description TEXT DEFAULT '', enabled BOOLEAN DEFAULT true, "
    "domain_code VARCHAR(80) DEFAULT '', is_business BOOLEAN DEFAULT true, "
    "is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_property ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), name VARCHAR(160), code VARCHAR(128), "
    "prop_type VARCHAR(32) DEFAULT 'string', required BOOLEAN DEFAULT false, "
    "unique_col BOOLEAN DEFAULT false, sensitive BOOLEAN DEFAULT false, "
    "is_business BOOLEAN DEFAULT true, "
    "source_col VARCHAR(128) DEFAULT '', options JSONB DEFAULT '[]', roles JSONB DEFAULT '[]', "
    "description TEXT DEFAULT '', is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_link ("
    "id BIGSERIAL PRIMARY KEY, source_object VARCHAR(128), target_object VARCHAR(128), "
    "name VARCHAR(160) DEFAULT '', card VARCHAR(32) DEFAULT 'many_to_one', "
    "join_method VARCHAR(32) DEFAULT 'foreign_key', "
    "source_field VARCHAR(128) DEFAULT '', target_field VARCHAR(128) DEFAULT '', "
    "description TEXT DEFAULT '', is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_action ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), name VARCHAR(160), code VARCHAR(128), "
    "input_schema JSONB DEFAULT '[]', white_fields JSONB DEFAULT '[]', "
    "approval BOOLEAN DEFAULT false, target_table VARCHAR(128) DEFAULT '', "
    "method VARCHAR(16) DEFAULT 'update', description TEXT DEFAULT '', "
    "tool_description TEXT DEFAULT '', rules JSONB DEFAULT '[]', parameters JSONB DEFAULT '[]', "
    "submission_criteria JSONB DEFAULT '[]', side_effects JSONB DEFAULT '[]', "
    "ui_sections JSONB DEFAULT '[]', status VARCHAR(24) DEFAULT 'experimental', "
    "visibility VARCHAR(24) DEFAULT 'normal', "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_function ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), name VARCHAR(160), code VARCHAR(128), "
    "expr TEXT DEFAULT '', description TEXT DEFAULT '', parameters JSONB DEFAULT '[]', "
    "tool_description TEXT DEFAULT '', "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_capability ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(128) UNIQUE, name VARCHAR(160), type VARCHAR(32), "
    "description TEXT DEFAULT '', enabled BOOLEAN DEFAULT true, "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_version ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), version INTEGER, "
    "snapshot JSONB DEFAULT '{}', is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_change_log ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), kind VARCHAR(32), action VARCHAR(32), "
    "detail TEXT DEFAULT '', created_id INTEGER, is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_domain ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(80) UNIQUE, name VARCHAR(120), "
    "description VARCHAR(255) DEFAULT '', icon VARCHAR(60) DEFAULT 'el-icon-Folder', "
    "sort INTEGER DEFAULT 0, enabled BOOLEAN DEFAULT true, "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now(), "
    "updated_time TIMESTAMP DEFAULT now())",
    # 工作副本：改动先入草稿，点「保存」才落库（对齐 Palantir 的 Save / Discard）
    "CREATE TABLE IF NOT EXISTS ai_ont_wip ("
    "id BIGSERIAL PRIMARY KEY, owner_id INTEGER NOT NULL, kind VARCHAR(24) NOT NULL, "
    "action VARCHAR(16) NOT NULL, target_key VARCHAR(160) DEFAULT '', "
    "data JSONB DEFAULT '{}', created_time TIMESTAMP DEFAULT now())",
    # ---- P5 高级类型系统 ----
    # 对象类型组：跨对象类型的多对多分组（官方 Object type groups）
    "CREATE TABLE IF NOT EXISTS ai_ont_group ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(80) UNIQUE, name VARCHAR(160), "
    "description TEXT DEFAULT '', color VARCHAR(32) DEFAULT '', sort INTEGER DEFAULT 0, "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_group_member ("
    "id BIGSERIAL PRIMARY KEY, group_id BIGINT, object_code VARCHAR(128), "
    "created_time TIMESTAMP DEFAULT now())",
    # 值类型：语义包装（邮箱/URL/UUID…）+ 约束 + 版本 + 权限
    "CREATE TABLE IF NOT EXISTS ai_ont_value_type ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(80) UNIQUE, name VARCHAR(160), "
    "base_type VARCHAR(40) DEFAULT 'string', description TEXT DEFAULT '', "
    "constraints JSONB DEFAULT '{}', version INTEGER DEFAULT 1, roles JSONB DEFAULT '[]', "
    "status VARCHAR(24) DEFAULT 'experimental', visibility VARCHAR(24) DEFAULT 'normal', "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    # 共享属性：定义一次、多类型引用；只共享元数据，不共享数据
    "CREATE TABLE IF NOT EXISTS ai_ont_shared_property ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(128) UNIQUE, name VARCHAR(160), "
    "prop_type VARCHAR(32) DEFAULT 'string', base_type VARCHAR(40) DEFAULT 'string', "
    "api_name VARCHAR(160) DEFAULT '', description TEXT DEFAULT '', "
    "value_type_code VARCHAR(80) DEFAULT '', constraints JSONB DEFAULT '{}', "
    "status VARCHAR(24) DEFAULT 'experimental', visibility VARCHAR(24) DEFAULT 'normal', "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    # 接口：定义 + 实现关系（对象类型实现接口）
    "CREATE TABLE IF NOT EXISTS ai_ont_interface ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(80) UNIQUE, name VARCHAR(160), "
    "description TEXT DEFAULT '', required_properties JSONB DEFAULT '[]', "
    "required_links JSONB DEFAULT '[]', required_actions JSONB DEFAULT '[]', "
    "status VARCHAR(24) DEFAULT 'experimental', visibility VARCHAR(24) DEFAULT 'normal', "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_interface_impl ("
    "id BIGSERIAL PRIMARY KEY, interface_code VARCHAR(80), object_code VARCHAR(128), "
    "created_time TIMESTAMP DEFAULT now())",
    # ---- P3 决策数据（对齐 why-ontology：决策数据 = 上下文 + 评估过的选项 + 下游影响）----
    "CREATE TABLE IF NOT EXISTS ai_ont_decision ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(120) UNIQUE, title VARCHAR(200), "
    "description TEXT DEFAULT '', status VARCHAR(24) DEFAULT 'proposed', "
    "category VARCHAR(60) DEFAULT '', "
    # 决策关于哪个对象
    "object_code VARCHAR(128) DEFAULT '', object_key VARCHAR(200) DEFAULT '', "
    # 承诺的选择：由哪个动作执行 + 参数
    "action_code VARCHAR(120) DEFAULT '', params JSONB DEFAULT '{}', "
    "rationale TEXT DEFAULT '', "
    # 决策谱系三要素：何时 / 基于哪个数据版本 / 经由哪个应用
    "data_version INTEGER DEFAULT 0, data_snapshot JSONB DEFAULT '{}', "
    "channel VARCHAR(60) DEFAULT 'ontology', "
    "made_by VARCHAR(120) DEFAULT '', made_at TIMESTAMP DEFAULT now(), "
    "decided_by VARCHAR(120) DEFAULT '', decided_at TIMESTAMP, decision_note TEXT DEFAULT '', "
    "executed_at TIMESTAMP, execution_id BIGINT DEFAULT 0, "
    # 事前预期 / 事后结果
    "expected_impact JSONB DEFAULT '{}', outcome JSONB DEFAULT '{}', "
    "superseded_by VARCHAR(120) DEFAULT '', tags JSONB DEFAULT '[]', "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now(), "
    "updated_time TIMESTAMP DEFAULT now())",
    # 评估过的不同选项
    "CREATE TABLE IF NOT EXISTS ai_ont_decision_option ("
    "id BIGSERIAL PRIMARY KEY, decision_code VARCHAR(120), code VARCHAR(120), "
    "label VARCHAR(200) DEFAULT '', description TEXT DEFAULT '', "
    "params JSONB DEFAULT '{}', score NUMERIC, "
    "projected_impact JSONB DEFAULT '{}', chosen BOOLEAN DEFAULT false, "
    "reject_reason TEXT DEFAULT '', created_time TIMESTAMP DEFAULT now())",
    # 决策上下文（上游依据）
    "CREATE TABLE IF NOT EXISTS ai_ont_decision_evidence ("
    "id BIGSERIAL PRIMARY KEY, decision_code VARCHAR(120), "
    "kind VARCHAR(32) DEFAULT 'object', ref VARCHAR(240) DEFAULT '', "
    "label VARCHAR(240) DEFAULT '', value JSONB DEFAULT '{}', "
    "created_time TIMESTAMP DEFAULT now())",
    # 下游影响
    "CREATE TABLE IF NOT EXISTS ai_ont_decision_impact ("
    "id BIGSERIAL PRIMARY KEY, decision_code VARCHAR(120), "
    "kind VARCHAR(32) DEFAULT 'object_changed', ref VARCHAR(240) DEFAULT '', "
    "label VARCHAR(240) DEFAULT '', before JSONB DEFAULT '{}', after JSONB DEFAULT '{}', "
    "note TEXT DEFAULT '', auto BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    # ---- P4 对象权限 ----
    # 本体资源 ACL（模式层：对象/关系/动作/函数… 的 view/edit/manage）
    "CREATE TABLE IF NOT EXISTS ai_ont_resource_acl ("
    "id BIGSERIAL PRIMARY KEY, resource_kind VARCHAR(32), resource_code VARCHAR(128), "
    "view_roles JSONB DEFAULT '[]', edit_roles JSONB DEFAULT '[]', "
    "manage_roles JSONB DEFAULT '[]', created_time TIMESTAMP DEFAULT now(), "
    "UNIQUE(resource_kind, resource_code))",
    # 行级安全策略（对象实例级）
    "CREATE TABLE IF NOT EXISTS ai_ont_row_policy ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), name VARCHAR(160) DEFAULT '', "
    "description TEXT DEFAULT '', expression TEXT DEFAULT '', "
    "effect VARCHAR(8) DEFAULT 'allow', enabled BOOLEAN DEFAULT true, "
    "priority INTEGER DEFAULT 0, created_time TIMESTAMP DEFAULT now())",
    # ---- P5 场景（对齐官方 Ontology scenarios：沙箱式编辑叠加，可对比、可合并）----
    "CREATE TABLE IF NOT EXISTS ai_ont_scenario ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(120) UNIQUE, name VARCHAR(200) DEFAULT '', "
    "description TEXT DEFAULT '', status VARCHAR(24) DEFAULT 'active', "
    # 基于哪个本体版本；合并动作（官方：场景通过动作类型合并）
    "base_version INTEGER DEFAULT 0, merge_action_code VARCHAR(120) DEFAULT '', "
    # 场景允许编辑的范围（官方：创建合并动作时选定 Object types / Link types）
    "scope JSONB DEFAULT '{}', "
    "created_by VARCHAR(120) DEFAULT '', created_time TIMESTAMP DEFAULT now(), "
    "expires_at TIMESTAMP, applied_at TIMESTAMP, applied_by VARCHAR(120) DEFAULT '', "
    "edit_count INTEGER DEFAULT 0, action_codes JSONB DEFAULT '[]', "
    "is_persisted BOOLEAN DEFAULT false, scenario_object_key VARCHAR(200) DEFAULT '', "
    "is_deleted BOOLEAN DEFAULT false)",
    # 场景内的编辑：场景 = 相对基线数据的「差异集」
    "CREATE TABLE IF NOT EXISTS ai_ont_scenario_edit ("
    "id BIGSERIAL PRIMARY KEY, scenario_code VARCHAR(120), object_code VARCHAR(128), "
    "object_key VARCHAR(200) DEFAULT '', "
    "kind VARCHAR(24) DEFAULT 'modify', "
    "before JSONB DEFAULT '{}', after JSONB DEFAULT '{}', "
    "action_code VARCHAR(120) DEFAULT '', created_time TIMESTAMP DEFAULT now())",
    # ---- A) 对象视图（对齐官方 object-views：Standard/Configured + Full/Panel + tabs→widgets）----
    "CREATE TABLE IF NOT EXISTS ai_ont_object_view ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), code VARCHAR(160), "
    "name VARCHAR(200) DEFAULT '', description TEXT DEFAULT '', "
    "view_type VARCHAR(16) DEFAULT 'configured', "
    # full=完整视图；panel=面板视图（供其它应用嵌入）
    "form_factor VARCHAR(16) DEFAULT 'full', "
    "is_default BOOLEAN DEFAULT false, "
    # 官方：默认视图跟随对象类型自动更新，一旦被编辑就转为 user-managed
    "is_managed BOOLEAN DEFAULT false, "
    "tabs JSONB DEFAULT '[]', version INTEGER DEFAULT 1, "
    # 保存的筛选器（官方 widgets-filtering：筛选器可保存并复用）
    "filters JSONB DEFAULT '[]', "
    # 共享角色（空 = 跟随对象类型权限，官方语义）
    "share_roles JSONB DEFAULT '[]', share_mode VARCHAR(16) DEFAULT 'inherit', "
    "status VARCHAR(24) DEFAULT 'experimental', visibility VARCHAR(24) DEFAULT 'normal', "
    "created_by VARCHAR(120) DEFAULT '', created_time TIMESTAMP DEFAULT now(), "
    "updated_time TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false)",
    "CREATE TABLE IF NOT EXISTS ai_ont_object_view_version ("
    "id BIGSERIAL PRIMARY KEY, view_code VARCHAR(160), version INTEGER, "
    "tabs JSONB DEFAULT '[]', note TEXT DEFAULT '', "
    "created_by VARCHAR(120) DEFAULT '', created_time TIMESTAMP DEFAULT now())",
    # ---- B) 索引（对齐官方 object-indexing：Funnel 流水线状态 + 构建/重试）----
    "CREATE TABLE IF NOT EXISTS ai_ont_index ("
    "id BIGSERIAL PRIMARY KEY, object_code VARCHAR(128), "
    "prop_code VARCHAR(128) DEFAULT '', "
    "index_kind VARCHAR(24) DEFAULT 'property', "
    "status VARCHAR(24) DEFAULT 'not_started', "
    "pipeline_kind VARCHAR(24) DEFAULT 'batch', "
    "index_name VARCHAR(160) DEFAULT '', row_count INTEGER DEFAULT 0, "
    "size_bytes BIGINT DEFAULT 0, build_count INTEGER DEFAULT 0, "
    "last_built_at TIMESTAMP, last_error TEXT DEFAULT '', "
    "auto_retry_at TIMESTAMP, enabled BOOLEAN DEFAULT true, "
    "created_time TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false)",
    # ---- C) 分支 / 提案（对齐官方 ontologies-proposals）----
    "CREATE TABLE IF NOT EXISTS ai_ont_branch ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(160) UNIQUE, name VARCHAR(200) DEFAULT '', "
    "description TEXT DEFAULT '', status VARCHAR(24) DEFAULT 'active', "
    "base_version INTEGER DEFAULT 0, created_by VARCHAR(120) DEFAULT '', "
    "created_time TIMESTAMP DEFAULT now(), merged_at TIMESTAMP, "
    "merged_by VARCHAR(120) DEFAULT '', is_deleted BOOLEAN DEFAULT false)",
    "CREATE TABLE IF NOT EXISTS ai_ont_branch_change ("
    "id BIGSERIAL PRIMARY KEY, branch_code VARCHAR(160), resource_kind VARCHAR(24), "
    "resource_code VARCHAR(160), change_kind VARCHAR(24) DEFAULT 'update', "
    "before JSONB DEFAULT '{}', after JSONB DEFAULT '{}', "
    "created_by VARCHAR(120) DEFAULT '', created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_proposal ("
    "id BIGSERIAL PRIMARY KEY, code VARCHAR(160) UNIQUE, branch_code VARCHAR(160), "
    "title VARCHAR(240) DEFAULT '', description TEXT DEFAULT '', "
    "stage VARCHAR(24) DEFAULT 'preparing', "
    "reviewers JSONB DEFAULT '[]', created_by VARCHAR(120) DEFAULT '', "
    "created_time TIMESTAMP DEFAULT now(), review_requested_at TIMESTAMP, "
    "merged_at TIMESTAMP, merged_by VARCHAR(120) DEFAULT '', "
    "closed_at TIMESTAMP, closed_by VARCHAR(120) DEFAULT '', "
    "is_deleted BOOLEAN DEFAULT false)",
    "CREATE TABLE IF NOT EXISTS ai_ont_proposal_task ("
    "id BIGSERIAL PRIMARY KEY, proposal_code VARCHAR(160), resource_kind VARCHAR(24), "
    "resource_code VARCHAR(160), resource_name VARCHAR(200) DEFAULT '', "
    "change_kind VARCHAR(24) DEFAULT 'update', "
    "before JSONB DEFAULT '{}', after JSONB DEFAULT '{}', "
    "status VARCHAR(24) DEFAULT 'pending', reviewed_by VARCHAR(120) DEFAULT '', "
    "reviewed_at TIMESTAMP, review_note TEXT DEFAULT '', "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_ont_proposal_comment ("
    "id BIGSERIAL PRIMARY KEY, proposal_code VARCHAR(160), task_id INTEGER DEFAULT 0, "
    "author VARCHAR(120) DEFAULT '', body TEXT DEFAULT '', "
    "created_time TIMESTAMP DEFAULT now())",
    # 演示数据登记表（精确记录建了什么，清除时按登记删，不靠名字猜）
    "CREATE TABLE IF NOT EXISTS ai_ont_demo ("
    "id BIGSERIAL PRIMARY KEY, kind VARCHAR(40), ref VARCHAR(200), "
    "label VARCHAR(240) DEFAULT '', created_time TIMESTAMP DEFAULT now())",
)

# 列演进：新增列一律在此追加，幂等
#
# P1 类型元数据完备 —— 对齐 Palantir 官方元数据参考表：
#   对象类型 14 项 / 属性 13 项 / 关系类型 11 项 / 动作类型（含 9 个配置页）
_ONT_ALTER_SQL = (
    "ALTER TABLE ai_ont_object_view ADD COLUMN IF NOT EXISTS filters JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_object_view ADD COLUMN IF NOT EXISTS share_roles JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_object_view ADD COLUMN IF NOT EXISTS share_mode VARCHAR(16) DEFAULT 'inherit'",
    # ---- 对象类型 ----
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS domain_code VARCHAR(80) DEFAULT ''",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS is_business BOOLEAN DEFAULT true",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS plural_name VARCHAR(160) DEFAULT ''",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS api_name VARCHAR(120) DEFAULT ''",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS aliases JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS status VARCHAR(24) DEFAULT 'experimental'",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS visibility VARCHAR(24) DEFAULT 'normal'",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS index_status VARCHAR(24) DEFAULT 'not_started'",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS edits_enabled BOOLEAN DEFAULT false",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS datasource_id INTEGER",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS backing_table VARCHAR(160) DEFAULT ''",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS point_of_contact VARCHAR(120) DEFAULT ''",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS contributors JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_object ADD COLUMN IF NOT EXISTS rid VARCHAR(160) DEFAULT ''",
    # ---- 属性 ----
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS api_name VARCHAR(120) DEFAULT ''",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS base_type VARCHAR(40) DEFAULT ''",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS title_key BOOLEAN DEFAULT false",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS visibility VARCHAR(24) DEFAULT 'normal'",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS edit_only BOOLEAN DEFAULT false",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS value_formatting JSONB DEFAULT '{}'",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS conditional_formatting JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS render_hint VARCHAR(60) DEFAULT ''",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS type_class VARCHAR(60) DEFAULT ''",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS status VARCHAR(24) DEFAULT 'experimental'",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS is_business BOOLEAN DEFAULT true",
    # ---- 关系类型 ----
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS join_method VARCHAR(32) DEFAULT 'foreign_key'",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS api_name VARCHAR(120) DEFAULT ''",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS source_name VARCHAR(160) DEFAULT ''",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS source_plural_name VARCHAR(160) DEFAULT ''",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS target_name VARCHAR(160) DEFAULT ''",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS target_plural_name VARCHAR(160) DEFAULT ''",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS status VARCHAR(24) DEFAULT 'experimental'",
    "ALTER TABLE ai_ont_link ADD COLUMN IF NOT EXISTS visibility VARCHAR(24) DEFAULT 'normal'",
    # ---- 动作类型 ----
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS tool_description TEXT DEFAULT ''",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS rules JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS parameters JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS submission_criteria JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS side_effects JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS ui_sections JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS status VARCHAR(24) DEFAULT 'experimental'",
    "ALTER TABLE ai_ont_action ADD COLUMN IF NOT EXISTS visibility VARCHAR(24) DEFAULT 'normal'",
    # ---- 函数 ----
    "ALTER TABLE ai_ont_function ADD COLUMN IF NOT EXISTS parameters JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_function ADD COLUMN IF NOT EXISTS tool_description TEXT DEFAULT ''",
    # 函数形态（expression/aggregate/http/model）、出参声明、各形态配置
    "ALTER TABLE ai_ont_function ADD COLUMN IF NOT EXISTS kind VARCHAR(24) DEFAULT 'expression'",
    "ALTER TABLE ai_ont_function ADD COLUMN IF NOT EXISTS outputs JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_function ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}'",
    # ---- P5：属性上的共享引用 / 派生配置 / 内联 struct ----
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS shared_code VARCHAR(128) DEFAULT ''",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS derived JSONB DEFAULT '{}'",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS struct_fields JSONB DEFAULT '[]'",
    "ALTER TABLE ai_ont_property ADD COLUMN IF NOT EXISTS value_type_code VARCHAR(80) DEFAULT ''",
)

# 枚举取值（对齐官方，供前端下拉与后端校验共用）
ONT_STATUS = ("active", "experimental", "deprecated")
ONT_VISIBILITY = ("normal", "prominent", "hidden")
ONT_INDEX_STATUS = ("success", "failed", "not_started")
ONT_JOIN_METHOD = ("foreign_key", "dataset", "object_type")
ONT_CARDINALITY = ("one_to_one", "one_to_many", "many_to_one", "many_to_many")
# 官方 base type（属性基类型）常用集合
ONT_BASE_TYPE = (
    "string", "boolean", "byte", "short", "integer", "long", "float", "double",
    "decimal", "date", "timestamp", "time", "geohash", "geoshape", "attachment", "media_reference",
)


def _json_list(v) -> list:
    """把 JSONB / TEXT 列安全解析成 list。"""
    if isinstance(v, list):
        return v
    if not v:
        return []
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _json_dict(v) -> dict:
    """把 JSONB / TEXT 列安全解析成 dict。"""
    if isinstance(v, dict):
        return v
    if not v:
        return {}
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def derive_api_name(code: str) -> str:
    """由编码推导官方风格的 API name（PascalCase）。

    video_cameras -> VideoCameras
    alarm_record  -> AlarmRecord
    """
    if not code:
        return ""
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", code) if p]
    if not parts:
        return ""
    return "".join(p[:1].upper() + p[1:] for p in parts)[:100]


def derive_base_type(prop_type: str, code: str = "") -> str:
    """由我们的 prop_type 推导官方 base type。"""
    pt = (prop_type or "string").lower()
    if pt == "number":
        # 计数/主键类列给整数，其余给双精度
        return "long" if (code.endswith("_id") or code.endswith("_count") or code == "id") else "double"
    if pt == "boolean":
        return "boolean"
    if pt in ("date", "datetime", "timestamp"):
        return "timestamp"
    if pt == "time":
        return "time"
    if pt in ("json", "enum", "object_ref", "string"):
        return "string"
    return "string"


def derive_plural_name(name: str) -> str:
    """中文名不做复数变化，英文名追加 s。"""
    n = (name or "").strip()
    if not n:
        return ""
    if re.search(r"[\u4e00-\u9fff]", n):
        return n
    return n if n.endswith("s") else f"{n}s"


async def _ensure_ontology_schema() -> None:
    """确保 ai_ont_* 全部表与新增列存在（幂等、best-effort）。"""
    global _ont_schema_ready
    if _ont_schema_ready:
        return
    for sql in _ONT_TABLES_SQL + _ONT_ALTER_SQL:
        try:
            async with async_db_session.begin() as db:
                await db.execute(_t(sql))
        except Exception:  # noqa: BLE001
            pass
    _ont_schema_ready = True


# ---------------------------------------------------------------------------
# 元模型 CRUD
# ---------------------------------------------------------------------------
async def _exec(sql: str, params: dict | None = None):
    await _ensure_ontology_schema()
    async with async_db_session() as db:
        return await db.execute(_t(sql), params or {})


async def _exec_write(sql: str, params: dict | None = None):
    await _ensure_ontology_schema()
    async with async_db_session.begin() as db:
        return await db.execute(_t(sql), params or {})


# ---------------------------------------------------------------------------
# 本体（Ontology Domain）：对象类型的顶层容器
#
# 一个「本体」= 一组业务上同源的对象类型（如 数据表本体 / 业务本体 / 出入场本体）。
# 表结构与 ai_ont_object.domain_code 走运行时建表（本项目 ai_ont_* 无 Alembic 迁移）。
# ---------------------------------------------------------------------------
_domain_schema_ready = False


async def _ensure_domain_schema() -> None:
    """保留旧入口：ai_ont_domain 建表与 ai_ont_object.domain_code 均已并入统一建表入口。"""
    global _domain_schema_ready
    if _domain_schema_ready:
        return
    await _ensure_ontology_schema()
    _domain_schema_ready = True


async def list_domains() -> list[dict]:
    """本体列表（含各自的对象类型数量）。"""
    await _ensure_domain_schema()
    async with async_db_session() as db:
        rows = (await db.execute(_t(
            "SELECT id,code,name,description,icon,sort,enabled FROM ai_ont_domain "
            "WHERE is_deleted=false ORDER BY sort,id"))).fetchall()
        cnt_rows = (await db.execute(_t(
            "SELECT COALESCE(domain_code,''), count(*) FROM ai_ont_object "
            "WHERE is_deleted=false GROUP BY COALESCE(domain_code,'')"))).fetchall()
    counts = {r[0]: int(r[1] or 0) for r in cnt_rows}
    return [{
        "id": r[0], "code": r[1] or "", "name": r[2] or "", "description": r[3] or "",
        "icon": r[4] or "el-icon-Folder", "sort": r[5] or 0, "enabled": bool(r[6]),
        "object_count": counts.get(r[1] or "", 0),
    } for r in rows]


async def upsert_domain(data: dict) -> dict:
    """新建/编辑本体（code 唯一，冲突则更新并复活）。"""
    await _ensure_domain_schema()
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code or not name:
        raise CustomException(msg="本体编码与名称必填")
    params = {"c": code, "n": name, "d": data.get("description", "") or "",
              "i": data.get("icon", "el-icon-Folder") or "el-icon-Folder",
              "s": int(data.get("sort", 0) or 0)}
    async with async_db_session.begin() as db:
        if data.get("id"):
            await db.execute(_t(
                "UPDATE ai_ont_domain SET code=:c, name=:n, description=:d, icon=:i, sort=:s, "
                "updated_time=now() WHERE id=:id"), {**params, "id": data["id"]})
            return {"id": data["id"], "code": code}
        r = await db.execute(_t(
            "INSERT INTO ai_ont_domain(code,name,description,icon,sort,enabled,is_deleted) "
            "VALUES (:c,:n,:d,:i,:s,true,false) "
            "ON CONFLICT (code) DO UPDATE SET name=:n, description=:d, icon=:i, sort=:s, "
            "is_deleted=false, updated_time=now() RETURNING id"), params)
        return {"id": r.scalar(), "code": code}


async def delete_domain(id: int) -> dict:
    """软删本体；其下对象退回「未分组」，不删对象本身。"""
    await _ensure_domain_schema()
    async with async_db_session.begin() as db:
        row = (await db.execute(_t(
            "SELECT code FROM ai_ont_domain WHERE id=:id AND is_deleted=false"), {"id": id})).fetchone()
        code = (row[0] if row else "") or ""
        await db.execute(_t(
            "UPDATE ai_ont_domain SET is_deleted=true, updated_time=now() WHERE id=:id"), {"id": id})
        moved = 0
        if code:
            res = await db.execute(_t(
                "UPDATE ai_ont_object SET domain_code='', updated_time=now() "
                "WHERE COALESCE(domain_code,'')=:c AND is_deleted=false"), {"c": code})
            moved = res.rowcount or 0
    return {"ok": True, "moved_objects": moved}


async def assign_objects_to_domain(domain_code: str, object_codes: list[str]) -> dict:
    """把一批对象类型归入指定本体（domain_code 传空 = 退回未分组）。"""
    await _ensure_domain_schema()
    codes = [c for c in (object_codes or []) if c]
    if not codes:
        return {"ok": False, "msg": "未选择对象"}
    from sqlalchemy import bindparam

    stmt = _t(
        "UPDATE ai_ont_object SET domain_code=:d, updated_time=now() "
        "WHERE code IN :codes AND is_deleted=false").bindparams(bindparam("codes", expanding=True))
    async with async_db_session.begin() as db:
        res = await db.execute(stmt, {"d": (domain_code or ""), "codes": codes})
    return {"ok": True, "updated": res.rowcount or 0}


async def list_objects_ungrouped_count() -> int:
    """未分组对象数（左侧「未分组」用）。"""
    await _ensure_domain_schema()
    r = await _exec(
        "SELECT count(*) FROM ai_ont_object WHERE is_deleted=false AND COALESCE(domain_code,'')=''")
    return int(r.scalar() or 0)


# ---------------------------------------------------------------------------
# 业务语义回填：把「库表结构清单」升级成「业务本体」
#
# 数据源导入只带了表/列名（ai_query_schema 缓存里的 comment 为空），于是对象叫
# video_cameras、属性描述是占位符。本函数直接读 pg_catalog 的真实元数据：
#   表注释   → 对象业务名（如 摄像机表）
#   列注释   → 属性业务名 + 枚举选项
#   真实外键 → Link（剔除 created_id/updated_id/deleted_id 等审计列）
#
# 幂等且尊重人工编辑：只在值仍是自动生成物时才覆盖
#   （对象名 == 编码、属性名 == 列名、描述是「来自 …」占位、prop_type 还不是 enum）。
# ---------------------------------------------------------------------------
_ENUM_RE = re.compile(r"[:：]\s*([^:：]{2,120})$")
_ENUM_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5-]{1,20}$")
_AUDIT_COLS = ("created_id", "updated_id", "deleted_id", "tenant_id", "created_by", "updated_by")
# 列默认值表达式：数据源采集曾把它们误当注释写进 description（如 nextval('x_id_seq')/now()）
_NOISE_DESC_RE = re.compile(
    r"^(?:nextval\(|now\(\)|current_timestamp|timezone\(|array\[|'[^']*'::|\d+$|true$|false$)",
    re.IGNORECASE)


def _is_auto_desc(desc: str | None) -> bool:
    """描述是否仍是自动生成物：空、占位符「来自 …」、或被误当注释的列默认值表达式。"""
    d = (desc or "").strip()
    if not d or d.startswith("来自 "):
        return True
    return bool(_NOISE_DESC_RE.match(d))


def _parse_enum_options(comment: str) -> list[str]:
    """解析列注释里的枚举：「设备类型: IP_CAMERA/GB28181/NVR/ONVIF」→ [...]。拿不准就返回空。"""
    if not comment:
        return []
    m = _ENUM_RE.search(comment.strip())
    if not m:
        return []
    tokens = [t.strip() for t in m.group(1).split("/")]
    if len(tokens) < 2 or not all(_ENUM_TOKEN_RE.match(t) for t in tokens):
        return []
    return tokens


def _comment_label(comment: str) -> str:
    """注释冒号前的中文标签（「设备类型: A/B」→「设备类型」）；无冒号时返回原注释。"""
    c = (comment or "").strip()
    for sep in (":", "："):
        if sep in c:
            head = c.split(sep, 1)[0].strip()
            if 0 < len(head) <= 60:
                return head
    return c


async def enrich_ontology_semantics() -> dict:
    """从数据库真实元数据回填本体业务语义：对象名 / 属性名+枚举 / 关系 Link。"""
    await _ensure_domain_schema()
    try:
        async with async_db_session() as db:
            table_comment = {r[0]: (r[1] or "").strip() for r in (await db.execute(_t(
                "SELECT c.relname, obj_description(c.oid,'pg_class') FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='r' AND n.nspname='public'"))).fetchall()}
            col_comment = {(r[0], r[1]): (r[2] or "").strip() for r in (await db.execute(_t(
                "SELECT c.relname, a.attname, col_description(a.attrelid,a.attnum) "
                "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='r' AND n.nspname='public' AND a.attnum>0 AND NOT a.attisdropped"
            ))).fetchall()}
            uniq_cols = {(r[0], r[1]) for r in (await db.execute(_t(
                "SELECT c.relname, a.attname FROM pg_index i "
                "JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
                "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=ANY(i.indkey) "
                "WHERE n.nspname='public' AND i.indisunique"))).fetchall()}
            fks = (await db.execute(_t(
                "SELECT t.relname, a.attname, ft.relname, fa.attname FROM pg_constraint c "
                "JOIN pg_class t ON t.oid=c.conrelid JOIN pg_class ft ON ft.oid=c.confrelid "
                "JOIN pg_namespace n ON n.oid=t.relnamespace "
                "JOIN LATERAL unnest(c.conkey, c.confkey) WITH ORDINALITY AS k(ca, pa, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.ca "
                "JOIN pg_attribute fa ON fa.attrelid=ft.oid AND fa.attnum=k.pa "
                "WHERE c.contype='f' AND n.nspname='public' "
                "AND a.attname NOT IN ('created_id','updated_id','deleted_id','tenant_id',"
                "'created_by','updated_by')"))).fetchall()
            objs = (await db.execute(_t(
                "SELECT id,code,name,COALESCE(key_prop,'id'),COALESCE(name_prop,'name'),"
                "COALESCE(api_name,'') FROM ai_ont_object WHERE is_deleted=false"))).fetchall()
            props = (await db.execute(_t(
                "SELECT id,object_code,name,code,prop_type,description FROM ai_ont_property"
            ))).fetchall()
            have_links = {(r[0], r[1], r[2]) for r in (await db.execute(_t(
                "SELECT source_object,target_object,COALESCE(source_field,'') FROM ai_ont_link "
                "WHERE is_deleted=false"))).fetchall()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"读取库元数据失败（仅支持 PostgreSQL 数据源）：{str(e)[:120]}"}

    obj_codes = {r[1] for r in objs}
    obj_renamed = 0
    obj_desc_filled = 0
    obj_no_comment = 0
    obj_updates: list[tuple[str, dict]] = []
    for oid, code, name, _kp, _np, _api in objs:
        cm = table_comment.get(code, "")
        if not cm:
            obj_no_comment += 1
            continue
        sets, params = [], {"id": oid}
        if not name or name == code:
            sets.append("name=:n")
            params["n"] = cm
            obj_renamed += 1
        sets.append("description=:d")
        params["d"] = cm
        obj_desc_filled += 1
        obj_updates.append((f"UPDATE ai_ont_object SET {', '.join(sets)} WHERE id=:id", params))

    prop_renamed = 0
    prop_described = 0
    enum_parsed = 0
    noise_cleared = 0
    prop_updates: list[tuple[str, dict]] = []
    enum_updates: list[dict] = []
    for pid, ocode, pname, pcode, ptype, pdesc in props:
        if ocode not in obj_codes:
            continue
        cm = col_comment.get((ocode, pcode), "")
        label = _comment_label(cm) or pcode
        opts = _parse_enum_options(cm)
        is_auto_name = (not pname) or pname == pcode
        is_auto_desc = _is_auto_desc(pdesc)
        if opts and (ptype or "") != "enum":
            enum_updates.append({"id": pid, "n": label, "d": cm,
                                 "o": json.dumps(opts, ensure_ascii=False)})
            enum_parsed += 1
            if is_auto_name:
                prop_renamed += 1
            if is_auto_desc:
                prop_described += 1
            continue
        # 有注释就写注释；没注释时，把被误当注释的列默认值清掉，别让技术噪声留在本体里
        new_name = label if (is_auto_name and cm) else pname
        new_desc = cm if cm else ("" if is_auto_desc else pdesc)
        if new_name != pname or new_desc != pdesc:
            prop_updates.append(
                ("UPDATE ai_ont_property SET name=:n, description=:d WHERE id=:id",
                 {"id": pid, "n": new_name, "d": new_desc}))
            if new_name != pname:
                prop_renamed += 1
            if new_desc != pdesc:
                if cm:
                    prop_described += 1
                else:
                    noise_cleared += 1

    link_rows = []
    for child, ccol, parent, pcol in fks:
        if child not in obj_codes or parent not in obj_codes:
            continue
        if (child, parent, ccol) in have_links:
            continue
        parent_name = table_comment.get(parent, "") or parent
        link_rows.append({
            "s": child, "t": parent, "n": parent_name,
            "c": "one_to_one" if (child, ccol) in uniq_cols else "many_to_one",
            "sf": ccol, "tf": pcol, "d": f"{child}.{ccol} → {parent}.{pcol}",
        })

    # ---- P1：回填空缺的官方元数据（幂等，只填空、不覆盖人工值） ----
    obj_meta: list[dict] = []
    for oid, code, name, _kp, _np2, api in objs:
        cm = table_comment.get(code, "")
        label = cm or name or code
        obj_meta.append({
            "id": oid,
            "pn": derive_plural_name(label),
            "api": api or derive_api_name(code),
            "bt": code,
            "rid": f"ri.ontology.main.object-type.{code}",
            "ist": "success" if code in table_comment else "not_started",
        })
    # 标题键：把与对象 name_prop 同名的属性标记为 title_key
    title_codes = {(r[1], r[4]) for r in objs}  # (object_code, name_prop)
    prop_meta: list[dict] = []
    for pid, ocode, _pname, pcode, ptype, _pdesc in props:
        if ocode not in obj_codes:
            continue
        prop_meta.append({
            "id": pid,
            "api": derive_api_name(pcode),
            "bt": derive_base_type(ptype, pcode),
            "tk": (ocode, pcode) in title_codes,
        })
    # 关系：补 API 名。关系名多为中文，去掉非 ASCII 后会退化甚至撞名，
    # 因此按候选序列取名：名称 → 两端对象 → 两端对象+源字段，仍冲突则追加序号。
    link_meta: list[dict] = []
    used_link_api = {r[0] for r in (await _exec(
        "SELECT api_name FROM ai_ont_link WHERE is_deleted=false AND COALESCE(api_name,'')<>''"))}
    for lr in (await _exec(
            "SELECT id,name,source_object,target_object,COALESCE(source_field,'') FROM ai_ont_link "
            "WHERE is_deleted=false AND COALESCE(api_name,'')=''")):
        by_name = derive_api_name(lr[1] or "")
        src, tgt, fld = (derive_api_name(lr[2] or ""), derive_api_name(lr[3] or ""),
                         derive_api_name(lr[4] or ""))
        cands = ([by_name] if len(by_name) >= 3 else []) + [src + tgt, src + tgt + fld]
        api = next((c for c in cands if c and c not in used_link_api), cands[-1])
        base, n = api, 2
        while api in used_link_api:
            api = f"{base}{n}"
            n += 1
        api = api[:100]
        used_link_api.add(api)
        link_meta.append({"id": lr[0], "api": api})

    async with async_db_session.begin() as db:
        for sql, params in obj_updates:
            await db.execute(_t(sql), params)
        for sql, params in prop_updates:
            await db.execute(_t(sql), params)
        for params in enum_updates:
            await db.execute(_t(
                "UPDATE ai_ont_property SET name=:n, description=:d, prop_type='enum', options=:o "
                "WHERE id=:id"), params)
        if obj_meta:
            await db.execute(_t(
                "UPDATE ai_ont_object SET "
                "plural_name=CASE WHEN COALESCE(plural_name,'')='' THEN :pn ELSE plural_name END, "
                "api_name=CASE WHEN COALESCE(api_name,'')='' THEN :api ELSE api_name END, "
                "backing_table=CASE WHEN COALESCE(backing_table,'')='' THEN :bt ELSE backing_table END, "
                "rid=CASE WHEN COALESCE(rid,'')='' THEN :rid ELSE rid END, "
                "index_status=CASE WHEN COALESCE(index_status,'not_started')='not_started' "
                "THEN :ist ELSE index_status END WHERE id=:id"), obj_meta)
        if prop_meta:
            await db.execute(_t(
                "UPDATE ai_ont_property SET "
                "api_name=CASE WHEN COALESCE(api_name,'')='' THEN :api ELSE api_name END, "
                "base_type=CASE WHEN COALESCE(base_type,'')='' THEN :bt ELSE base_type END, "
                "title_key=:tk WHERE id=:id"), prop_meta)
        if link_meta:
            await db.execute(_t("UPDATE ai_ont_link SET api_name=:api WHERE id=:id"), link_meta)
        if link_rows:
            await db.execute(_t(
                "INSERT INTO ai_ont_link(source_object,target_object,name,card,source_field,"
                "target_field,description,is_deleted) VALUES (:s,:t,:n,:c,:sf,:tf,:d,false)"),
                link_rows)

    renamed_links = await normalize_link_names()
    # 敏感字段自动标记：只用人工勾选是不够的（实测 1479 个属性一个都没勾）
    sensitive_marked = 0
    sens_props = await list_properties()
    for p in sens_props:
        if is_sensitive_like(p["code"]) and not p.get("sensitive"):
            await _exec_write("UPDATE ai_ont_property SET sensitive=true WHERE id=:id", {"id": p["id"]})
            sensitive_marked += 1
    return {
        "ok": True,
        "objects": {"total": len(objs), "renamed": obj_renamed,
                    "no_comment": obj_no_comment, "desc_filled": obj_desc_filled,
                    "meta_filled": len(obj_meta)},
        "properties": {"described": prop_described, "renamed": prop_renamed,
                       "enum_parsed": enum_parsed, "noise_cleared": noise_cleared,
                       "meta_filled": len(prop_meta), "sensitive_marked": sensitive_marked},
        "links": {"created": len(link_rows), "renamed": renamed_links,
                  "fk_total": len(fks),
                  "skipped_outside": len(fks) - len(link_rows)},
    }


def _strip_table_suffix(name: str) -> str:
    """「摄像机表」→「摄像机」：关系名读起来像业务名词，而不是表名。"""
    n = (name or "").strip()
    return n[:-1] if len(n) > 2 and n.endswith("表") else n


async def normalize_link_names() -> int:
    """把关系名统一成业务语义（父对象的业务名去掉「表」后缀）。"""
    async with async_db_session() as db:
        rows = (await db.execute(_t(
            "SELECT id,target_object,name FROM ai_ont_link WHERE is_deleted=false"))).fetchall()
        objs = {r[0]: (r[1] or "").strip() for r in (await db.execute(_t(
            "SELECT code,name FROM ai_ont_object WHERE is_deleted=false"))).fetchall()}
    updates = []
    for lid, tgt, nm in rows:
        if tgt not in objs:
            continue
        want = _strip_table_suffix(objs[tgt]) or tgt
        if want != (nm or ""):
            updates.append({"id": lid, "n": want})
    if updates:
        async with async_db_session.begin() as db:
            for u in updates:
                await db.execute(_t("UPDATE ai_ont_link SET name=:n WHERE id=:id"), u)
    return len(updates)


# ---------------------------------------------------------------------------
# 示例能力（函数 / 对象动作）：让本体一上手就有能用的东西
#
# 函数是**纯算术计算器**：调用方传入数值参数，用受限表达式求值
#   （见 agent_tools._safe_eval：只支持算术/比较/布尔，无函数调用、无属性访问），
#   所以 expr 里只能出现「参数名」和数字。
# 动作是**写回定义**：声明目标表、可写字段白名单、是否需审批，由 execute_ontology_action 执行。
# ---------------------------------------------------------------------------
_EXAMPLE_FUNCTIONS: list[dict] = [
    {"object_code": "video_alarm_rules", "code": "alarm_suppress_minutes",
     "name": "告警抑制窗口（分钟）", "expr": "interval_seconds / 60",
     "description": "参数：interval_seconds=规则的抑制间隔秒数"},
    {"object_code": "video_alarm_rules", "code": "rule_daily_alarms",
     "name": "规则日均告警量", "expr": "alarm_count / days",
     "description": "参数：alarm_count=区间内告警条数，days=区间天数"},
    {"object_code": "video_alarm_records", "code": "alarm_response_minutes",
     "name": "告警响应时长（分钟）", "expr": "(confirm_ts - alarm_ts) / 60",
     "description": "参数：confirm_ts=确认时间戳(秒)，alarm_ts=告警时间戳(秒)"},
    {"object_code": "video_alarm_records", "code": "alarm_confirm_rate",
     "name": "告警确认率（%）", "expr": "confirmed / total * 100",
     "description": "参数：confirmed=已确认条数，total=告警总条数"},
    {"object_code": "video_cameras", "code": "cam_online_rate",
     "name": "摄像机在线率（%）", "expr": "online_count / total_count * 100",
     "description": "参数：online_count=在线路数，total_count=总路数"},
    {"object_code": "video_record_plans", "code": "record_storage_gb",
     "name": "单路录像占用（GB/天）", "expr": "bitrate_mbps * 3600 * hours / 8 / 1024",
     "description": "参数：bitrate_mbps=码率(Mbps)，hours=每日录像小时数"},
    {"object_code": "video_edge_devices", "code": "edge_load_pct",
     "name": "边缘节点负载（%）", "expr": "used / capacity * 100",
     "description": "参数：used=已用路数，capacity=额定路数"},
    {"object_code": "annotation_task", "code": "annotate_left_units",
     "name": "标注剩余工作量", "expr": "total - total * progress / 100",
     "description": "参数：total=总标注量，progress=当前进度(%)"},
    {"object_code": "train_tasks", "code": "train_eta_hours",
     "name": "训练预计剩余（小时）", "expr": "elapsed_hours * (100 - progress) / progress",
     "description": "参数：elapsed_hours=已用时长(小时)，progress=当前进度(%)，progress 需 > 0"},
    {"object_code": "train_evals", "code": "eval_improve_pct",
     "name": "指标提升幅度（%）", "expr": "(new_score - base_score) / base_score * 100",
     "description": "参数：new_score=本次指标，base_score=基线指标"},
]

_EXAMPLE_ACTIONS: list[dict] = [
    {"object_code": "video_cameras", "code": "cam_rename", "name": "修改摄像机名称",
     "target_table": "video_cameras", "method": "update", "white_fields": ["name"],
     "input_schema": [{"key": "name", "label": "新名称", "type": "string", "required": True}],
     "approval": False, "description": "写回 video_cameras.name"},
    {"object_code": "video_cameras", "code": "cam_mark_offline", "name": "标记摄像机离线",
     "target_table": "video_cameras", "method": "update",
     "white_fields": ["status", "stream_status", "reachable"],
     "input_schema": [{"key": "status", "label": "状态", "type": "string", "required": True},
                      {"key": "stream_status", "label": "流状态", "type": "string"},
                      {"key": "reachable", "label": "是否可达", "type": "boolean"}],
     "approval": False, "description": "运维排障：把摄像机置为离线/不可达"},
    {"object_code": "video_alarm_records", "code": "alarm_confirm", "name": "确认告警",
     "target_table": "video_alarm_records", "method": "update",
     "white_fields": ["status", "confirm_user", "confirm_time"],
     "input_schema": [{"key": "status", "label": "状态", "type": "string", "required": True},
                      {"key": "confirm_user", "label": "确认人", "type": "string"},
                      {"key": "confirm_time", "label": "确认时间", "type": "date"}],
     "approval": False, "description": "值班确认告警，写回状态/确认人/确认时间"},
    {"object_code": "video_alarm_records", "code": "alarm_mark_false", "name": "标记告警误报",
     "target_table": "video_alarm_records", "method": "update",
     "white_fields": ["status", "description"],
     "input_schema": [{"key": "status", "label": "状态", "type": "string", "required": True},
                      {"key": "description", "label": "误报原因", "type": "string"}],
     "approval": True, "description": "影响算法评估口径，需审批"},
    {"object_code": "video_alarm_rules", "code": "rule_toggle", "name": "启停告警规则",
     "target_table": "video_alarm_rules", "method": "update", "white_fields": ["status"],
     "input_schema": [{"key": "status", "label": "状态", "type": "string", "required": True}],
     "approval": True, "description": "启停布控规则会直接影响告警量，需审批"},
    {"object_code": "video_edge_devices", "code": "edge_toggle", "name": "启停边缘设备",
     "target_table": "video_edge_devices", "method": "update", "white_fields": ["status"],
     "input_schema": [{"key": "status", "label": "状态", "type": "string", "required": True}],
     "approval": True, "description": "上下线边缘节点，需审批"},
    {"object_code": "video_record_plans", "code": "plan_toggle", "name": "启停录像计划",
     "target_table": "video_record_plans", "method": "update", "white_fields": ["status"],
     "input_schema": [{"key": "status", "label": "状态", "type": "string", "required": True}],
     "approval": True, "description": "启停录像会改变存储占用，需审批"},
]


async def seed_ontology_examples(operator: int = 0) -> dict:
    """写入一批可直接使用的本体示例能力：函数（纯算术）+ 对象动作（写回定义）。

    幂等：按 code 判断是否已存在，存在即跳过，不覆盖人工修改。
    """
    await _ensure_domain_schema()
    async with async_db_session() as db:
        objs = {r[0] for r in (await db.execute(_t(
            "SELECT code FROM ai_ont_object WHERE is_deleted=false"))).fetchall()}
        have_fns = {r[0] for r in (await db.execute(_t(
            "SELECT code FROM ai_ont_function WHERE is_deleted=false"))).fetchall()}
        have_acts = {r[0] for r in (await db.execute(_t(
            "SELECT code FROM ai_ont_action WHERE is_deleted=false"))).fetchall()}

    fn_added, fn_skipped = [], []
    for f in _EXAMPLE_FUNCTIONS:
        if f["object_code"] not in objs or f["code"] in have_fns:
            fn_skipped.append(f["code"])
            continue
        await upsert_function(dict(f))
        fn_added.append(f["code"])
        await _log_change(f["object_code"], "function", "example_created",
                          f"新增示例函数「{f['name']}」= {f['expr']}")

    act_added, act_skipped = [], []
    for a in _EXAMPLE_ACTIONS:
        if a["object_code"] not in objs or a["code"] in have_acts:
            act_skipped.append(a["code"])
            continue
        await upsert_action(dict(a))
        act_added.append(a["code"])
        await _log_change(a["object_code"], "action", "example_created",
                          f"新增示例动作「{a['name']}」→ {a['target_table']}"
                          f"（可写 {'/'.join(a['white_fields'])}"
                          f"{'，需审批' if a.get('approval') else ''}）")

    renamed = await normalize_link_names()
    if fn_added or act_added:
        await _log_change("", "ontology", "seed_examples",
                          f"示例能力落库：函数 {len(fn_added)} 个、动作 {len(act_added)} 个")
    return {"ok": True,
            "functions": {"added": fn_added, "skipped": fn_skipped},
            "actions": {"added": act_added, "skipped": act_skipped},
            "links_renamed": renamed}


async def _instance_props(object_code: str, key: str) -> dict:
    """取实例当前属性（场景叠加用；失败返回空 dict，不抛）。"""
    if not object_code or not key:
        return {}
    try:
        inst = await instance_get(object_code, str(key))
        return dict((inst or {}).get("props") or {}) if inst.get("ok") else {}
    except Exception:  # noqa: BLE001
        return {}


async def _actor_context(user_id: int | None = None, user_name: str = "",
                         is_scenario: bool = False) -> Any:
    """构造动作提交者上下文（含角色），供提交条件里的「当前用户 / 所属组」使用。

    ``is_scenario`` 对应官方的执行上下文：提交条件可区分「在场景内执行」与
    「对主本体执行」，从而给场景内更宽松的条件。
    """
    ctx = _ae.ActorContext(user_id=int(user_id or 0), user_name=user_name or "",
                           is_scenario=bool(is_scenario))
    if ctx.user_id:
        try:
            r = await _exec(
                "SELECT r.id, r.name FROM sys_user_roles ur "
                "JOIN sys_role r ON r.id = ur.role_id WHERE ur.user_id=:u", {"u": ctx.user_id})
            for row in r.fetchall():
                ctx.role_ids.append(int(row[0]))
                if row[1]:
                    ctx.role_codes.append(str(row[1]))
        except Exception:  # noqa: BLE001
            pass
    return ctx


async def _lookup_param_property(param_defs: dict, action_object: str,
                                 param_name: str, prop: str) -> Any:
    """解析「对象参数的属性」：参数值是某对象的 key，取它的某个属性。

    对象类型优先取参数声明里的 ``object``，没有则退回动作自己的对象类型。
    """
    pd = param_defs.get(param_name) or {}
    obj_code = str(pd.get("object") or pd.get("object_code") or "").strip() or action_object
    meta = await _instance_meta(obj_code)
    if not meta or meta.get("error") or not meta.get("materialized"):
        return None
    if prop not in meta["real_cols"]:
        return None
    table = _safe_ident(meta["table"])
    kc = _safe_ident(meta["key_prop"])
    try:
        r = await _exec(f'SELECT "{_safe_ident(prop)}" FROM "{table}" WHERE {_cast_text(_q(kc))} = :k',
                        {"k": str(pd.get("_key_value", ""))})
        row = r.fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


async def _build_resolver(criteria: list | None, rules: list | None, action: dict,
                          params: dict) -> Any:
    """预先解析所有「对象参数的属性」引用，返回一个同步 resolver 给纯函数引擎用。"""
    param_defs = {}
    for p in action.get("parameters") or []:
        if isinstance(p, dict) and p.get("key"):
            pd = dict(p)
            pd["_key_value"] = params.get(p["key"])
            param_defs[str(p["key"])] = pd

    refs: set[tuple[str, str]] = set()

    def walk(nodes: Any) -> None:
        for n in nodes or []:
            if not isinstance(n, dict):
                continue
            for side in ("left", "right"):
                s = n.get(side)
                if isinstance(s, dict) and s.get("kind") == "parameter" and s.get("property"):
                    refs.add((str(s.get("value") or ""), str(s["property"])))
            walk(n.get("children") or n.get("conditions"))

    walk(criteria)
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        for a in r.get("assignments") or []:
            if isinstance(a, dict) and str(a.get("source")) == "object_parameter_property":
                refs.add((str(a.get("parameter") or a.get("value") or ""),
                          str(a.get("object_property") or "")))

    cache: dict[tuple[str, str], Any] = {}
    for pname, prop in refs:
        if pname and prop:
            cache[(pname, prop)] = await _lookup_param_property(
                param_defs, action.get("object_code") or "", pname, prop)

    def _resolver(param_name: str, prop: str) -> Any:
        return cache.get((param_name, prop))

    return _resolver


async def _validate_params_by_value_type(action: dict, params: dict) -> list[str]:
    """按参数声明的值类型校验取值（值类型约束此前只存不用，这里真正接上）。"""
    errs: list[str] = []
    for p in action.get("parameters") or []:
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "")
        vtc = str(p.get("value_type") or p.get("value_type_code") or "")
        if not key or not vtc or key not in params:
            continue
        try:
            r = await validate_value(vtc, params[key])
        except Exception:  # noqa: BLE001
            continue
        if not r.get("ok"):
            errs.append(f"参数「{p.get('label') or key}」不满足值类型 {vtc}：{'；'.join(r.get('errors') or [])}")
    return errs


async def _log_action_result(action_name: str, table: str, object_key: str, params: dict,
                             operator: str, result: str, detail: str) -> int:
    async with async_db_session.begin() as db:
        res = await db.execute(_t(
            "INSERT INTO ai_action_log(action_name,object_table,object_key,params,operator,"
            "result,detail) VALUES (:n,:t,:k,:p,:o,:r,:d) RETURNING id"),
            {"n": action_name, "t": table, "k": str(object_key),
             "p": json.dumps(params, ensure_ascii=False), "o": operator or "",
             "r": result, "d": detail[:500]})
        return int(res.scalar() or 0)


async def _fire_side_effects(effects: list[dict], table: str, object_key: str) -> dict:
    """真正执行副作用：通知写 sys_user_notification，Webhook 发 HTTP 请求。"""
    sent: list[dict] = []
    errors: list[str] = []
    for e in effects:
        if e["type"] == "notification":
            try:
                for uid in e["recipients"]:
                    async with async_db_session.begin() as db:
                        await db.execute(_t(
                            "INSERT INTO sys_user_notification(user_id,title,content,type,module,"
                            "module_id,is_read,created_time) "
                            "VALUES (:u,:t,:c,'ontology_action',:m,:mid,false,now())"),
                            {"u": uid, "t": e["title"][:128], "c": e["content"],
                             "m": e["module"][:32], "mid": e.get("module_id")})
                sent.append({"type": "notification", "recipients": len(e["recipients"])})
            except Exception as ex:  # noqa: BLE001
                errors.append(f"通知发送失败：{str(ex)[:80]}")
        else:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=e["timeout"]) as client:
                    resp = await client.request(
                        e["method"], e["url"], headers=e["headers"], json=e["body"])
                sent.append({"type": "webhook", "url": e["url"], "status": resp.status_code})
            except Exception as ex:  # noqa: BLE001
                reason = str(ex) or type(ex).__name__
                msg = f"Webhook {e['url']} 调用失败：{reason[:100]}"
                if e.get("blocking"):
                    errors.append(msg)
                else:
                    sent.append({"type": "webhook", "url": e["url"], "error": msg})
    return {"sent": sent, "errors": errors}


async def plan_ontology_action(code: str, object_key: str, params: dict,
                               user_id: int | None = None,
                               user_name: str = "") -> dict:
    """试运行：评估提交条件、解析规则与副作用，**不写库**。

    对齐官方的 test run：给定一组参数，看这条动作会不会被拦、会产生什么编辑、会发什么副作用。
    """
    # 试运行要测「当前正在编辑的配置」，所以叠加该用户的工作副本
    act = await _find_action(code, user_id)
    if not act:
        return {"ok": False, "msg": f"本体动作 {code} 不存在"}
    ctx = await _actor_context(user_id, user_name or operator_name(user_id))
    resolver = await _build_resolver(act.get("submission_criteria"), act.get("rules"), act, params)
    crit = _ae.evaluate_criteria(act.get("submission_criteria"), ctx, params, resolver,
                                 with_trace=True)
    rules = _ae.plan_rules(act.get("rules"), ctx, params, resolver)
    effects = _ae.plan_side_effects(act.get("side_effects"), ctx, params, resolver)
    vt_errs = await _validate_params_by_value_type(act, params)
    return {
        "ok": True,
        "action": {"code": act["code"], "name": act.get("name"),
                   "approval": bool(act.get("approval"))},
        "actor": {"user_id": ctx.user_id, "user_name": ctx.user_name,
                  "roles": ctx.role_codes, "role_ids": ctx.role_ids},
        "params": params,
        "criteria": crit,
        "criteria_used": bool(act.get("submission_criteria")),
        "rules": rules,
        "rules_used": bool(act.get("rules")),
        "value_type_errors": vt_errs,
        "side_effects": effects,
        "side_effects_used": bool(act.get("side_effects")),
        "would_submit": bool(crit["ok"] and not rules["errors"] and not effects["errors"]
                            and not vt_errs),
    }


def operator_name(user_id: int | None) -> str:
    return ""


async def _find_action(code: str, owner_id: int | None = None) -> dict | None:
    """查找动作定义。

    ``owner_id`` 传入时会叠加该用户的工作副本——试运行要用**当前正在编辑的配置**，
    而不是上一次保存的版本。
    """
    acts = await list_actions(None, owner_id)
    return next((a for a in acts if a.get("code") == code or a.get("name") == code), None)


async def execute_ontology_action(code: str, object_key: str, params: dict,
                                  operator: str = "", approve: bool = False,
                                  user_id: int | None = None,
                                  principal: Any = None,
                                  scenario_code: str = "") -> dict:
    """执行本体动作。

    闸门顺序（对齐官方）：
    0. **权限**（P4）—— 对动作类型及其编辑的对象类型都要有编辑权限
    1. **提交条件**（submission criteria）—— 未通过则带着失败信息拒绝
    2. **值类型约束**（参数取值是否符合其声明的值类型）
    3. **白名单 / 规则合法性**
    4. **审批门禁**（需审批时落待审批单，不写库）
    5. 执行**规则**（未配置规则时回退到 target_table + 白名单的旧路径）
    6. 执行**副作用**（通知 / Webhook）
    7. 审计留痕（提交条件结果、规则、副作用一并记录）

    本体动作（ai_ont_action）与问数模块的动作（ai_action）各管一套定义，
    但**共用同一张审计表 ai_action_log**。
    """
    act = await _find_action(code)
    if not act:
        return {"ok": False, "msg": f"本体动作 {code} 不存在"}
    table = (act.get("target_table") or "").strip()
    method = (act.get("method") or "update").lower()
    act_name = act.get("name") or code
    rules = act.get("rules") or []
    effects = act.get("side_effects") or []

    # ---- 0) 权限 ----
    # 官方：*"For actions: You must hold edit permissions on the action type and on all
    # ontology resource types edited by the action."*
    if principal is not None:
        ok_a, why_a = await _sec.check_action_allowed(act, principal)
        if not ok_a:
            await _log_action_result(act_name, table, object_key, params, operator,
                                     "rejected", f"权限不足：{why_a}")
            return {"ok": False, "denied": True, "blocked_by": "permission", "msg": why_a}

    # ---- 1) 提交条件 ----
    # P5：在场景内执行时，提交条件的执行上下文会看到 is_scenario=True
    ctx = await _actor_context(user_id, operator, is_scenario=bool(scenario_code))
    resolver = await _build_resolver(act.get("submission_criteria"), rules, act, params)
    crit = _ae.evaluate_criteria(act.get("submission_criteria"), ctx, params, resolver)
    if not crit["ok"]:
        await _log_action_result(act_name, table, object_key, params, operator, "rejected",
                                 "提交条件未满足：" + "；".join(crit["failures"]))
        return {"ok": False, "blocked_by": "submission_criteria",
                "failures": crit["failures"],
                "msg": "不满足提交条件：" + "；".join(crit["failures"])}

    # ---- 2) 值类型约束 ----
    vt_errs = await _validate_params_by_value_type(act, params)
    if vt_errs:
        await _log_action_result(act_name, table, object_key, params, operator, "rejected",
                                 "值类型校验未通过：" + "；".join(vt_errs))
        return {"ok": False, "blocked_by": "value_type", "failures": vt_errs,
                "msg": "取值不符合值类型约束：" + "；".join(vt_errs)}

    # ---- 3) 白名单 / 规则 ----
    plan = _ae.plan_rules(rules, ctx, params, resolver) if rules else None
    if plan and plan["errors"]:
        return {"ok": False, "blocked_by": "rules", "failures": plan["errors"],
                "msg": "规则配置有误：" + "；".join(plan["errors"])}

    if rules:
        edits = list(plan["edits"]) if plan else []
        if not edits:
            return {"ok": False, "msg": "规则没有产生任何编辑"}
    else:
        # 兼容旧路径：未配置规则时按 target_table + 白名单执行 update
        if not table:
            return {"ok": False, "msg": "该动作未配置写回目标表，也没有配置规则"}
        if method != "update":
            return {"ok": False, "msg": f"未配置规则时只支持 update 写回（当前为 {method}）"}
        writable = [(w.get("key") if isinstance(w, dict) else w)
                    for w in (act.get("white_fields") or [])]
        writable = [w for w in writable if w]
        cols = [c for c in (params or {}) if c not in ("id", "object_key")]
        if not cols:
            return {"ok": False, "msg": "未提供任何要写入的字段"}
        bad = [c for c in cols if c not in writable]
        if bad:
            await _log_action_result(act_name, table, object_key, params, operator, "rejected",
                                     f"字段不在白名单：{','.join(bad)}")
            return {"ok": False, "blocked_by": "white_fields",
                    "msg": f"以下字段不在动作白名单内：{','.join(bad)}"}
        edits = [{"rule": "modify_object", "assignments": {c: params[c] for c in cols}}]

    if not object_key and any(e["rule"] in ("modify_object", "delete_object") for e in edits):
        return {"ok": False, "msg": "缺少对象关键值（目标行 id）"}

    # ---- 4) 审批门禁 ----
    if act.get("approval") and not approve:
        pid = await _log_action_result(act_name, table, object_key, params, operator,
                                       "pending", "待审批（本体动作）")
        return {"ok": False, "needs_approval": True, "approval_id": pid,
                "msg": "该本体动作需人工审批后执行（已生成待审批单）"}

    # ---- 5) 执行规则 ----
    applied: list[str] = []
    total_rows = 0
    if scenario_code:
        # P5：在场景内执行 —— **不写真实表**，只把差异记进场景。
        # 官方：*"all edits ... exist only within that scenario's isolated sandbox.
        # These edits do not affect the main Ontology."*
        from . import scenario as _sc

        ok_s, why_s = await _sc.in_scope(scenario_code, act.get("object_code") or "")
        if not ok_s:
            return {"ok": False, "blocked_by": "scenario_scope", "msg": why_s}
        before = await _instance_props(act.get("object_code") or "", object_key)
        for e in edits:
            rtype, assigns = e["rule"], (e.get("assignments") or {})
            kind = {"modify_object": "modify", "create_object": "create",
                    "delete_object": "delete"}.get(rtype)
            if not kind:
                continue
            if kind == "create":
                after = dict(assigns)
            elif kind == "delete":
                after = {}
            else:
                after = {**before, **assigns}
            r = await _sc.record_edit(scenario_code, act.get("object_code") or "",
                                      object_key, kind,
                                      before if kind == "modify" else {},
                                      after, code)
            if not r.get("ok"):
                return {"ok": False, "blocked_by": "scenario_limit", "msg": r.get("msg")}
            applied.append(f"{rtype}(场景内)")
            total_rows += 1
        await _log_action_result(act_name, table, object_key, params, operator, "staged",
                                 f"场景 {scenario_code} 内暂存：{'、'.join(applied)}")
        return {
            "ok": True, "scenario": scenario_code, "rows": total_rows,
            "rules_applied": applied, "staged": True,
            "before": before,
            "after": ({**before, **{k: v for e in edits for k, v in (e.get("assignments") or {}).items()}}
                      if not any(e["rule"] == "delete_object" for e in edits) else {}),
            "msg": f"已在场景内暂存（未写入真实数据）：{'、'.join(applied)}",
        }
    try:
        for e in edits:
            rtype = e["rule"]
            assigns = e.get("assignments") or {}
            if rtype == "modify_object":
                if not assigns:
                    continue
                sets = ", ".join(f'"{_safe_ident(c)}" = :{c}' for c in assigns)
                async with async_db_session.begin() as db:
                    res = await db.execute(
                        _t(f'UPDATE "{table}" SET {sets} WHERE {_cast_text(_q("id"))} = :__k'),
                        {**assigns, "__k": str(object_key)})
                    total_rows += int(res.rowcount or 0)
                applied.append(f"modify_object({len(assigns)} 列)")
            elif rtype == "create_object":
                if not assigns:
                    return {"ok": False, "msg": "create_object 规则没有任何赋值"}
                cols_ = ", ".join(f'"{_safe_ident(c)}"' for c in assigns)
                ph = ", ".join(f":{c}" for c in assigns)
                async with async_db_session.begin() as db:
                    await db.execute(_t(f'INSERT INTO "{table}" ({cols_}) VALUES ({ph})'), assigns)
                    total_rows += 1
                applied.append("create_object")
            elif rtype == "delete_object":
                async with async_db_session.begin() as db:
                    res = await db.execute(
                        _t(f'DELETE FROM "{table}" WHERE {_cast_text(_q("id"))} = :__k'),
                        {"__k": str(object_key)})
                    total_rows += int(res.rowcount or 0)
                applied.append("delete_object")
    except Exception as e:  # noqa: BLE001
        await _log_action_result(act_name, table, object_key, params, operator, "failed",
                                 f"规则执行失败：{str(e)[:200]}")
        return {"ok": False, "msg": f"规则执行失败：{str(e)[:120]}"}

    # ---- 6) 副作用（区分 before/after）----
    fx_plan = _ae.plan_side_effects(effects, ctx, params, resolver) if effects else {"effects": []}
    if fx_plan["effects"]:
        fx = await _fire_side_effects(fx_plan["effects"], table, object_key)
    else:
        fx = {"sent": [], "errors": []}
    if fx["errors"]:
        await _log_action_result(act_name, table, object_key, params, operator, "partial",
                                 "编辑已应用，但副作用失败：" + "；".join(fx["errors"]))
        return {"ok": False, "applied": applied, "rows": total_rows,
                "side_effect_errors": fx["errors"],
                "msg": "编辑已应用，但副作用失败：" + "；".join(fx["errors"])}

    # ---- 7) 审计 ----
    detail = (f"ontology_action={code} {table}#{object_key} 规则={'、'.join(applied) or '无'} "
              f"提交条件={'通过' if act.get('submission_criteria') else '未配置'} "
              f"副作用={json.dumps(fx['sent'], ensure_ascii=False) if fx['sent'] else '无'}")
    await _log_action_result(act_name, table, object_key, params, operator,
                             "success" if total_rows else "noop", detail)
    return {
        "ok": True, "rows": total_rows, "rules_applied": applied,
        "side_effects": fx["sent"],
        "warnings": (plan or {}).get("warnings", []),
        "msg": "已写回并留痕"
               + (f"（{len(fx['sent'])} 项副作用已执行）" if fx["sent"] else ""),
    }


async def can_assign_value_type(vt_code: str, user_id: int | None) -> tuple[bool, str]:
    """能否把某值类型「分配」给属性。

    官方语义（`value-types-permissions`）：有 space 的 View 权限即可分配；
    值类型上的 ``roles`` 就是"哪些角色可以分配它"。列表为空 = 不限制。
    """
    code = (vt_code or "").strip()
    if not code:
        return True, ""
    r = await _exec("SELECT roles FROM ai_ont_value_type WHERE code=:c AND is_deleted=false",
                    {"c": code})
    row = r.fetchone()
    if not row:
        return False, f"值类型 {code} 不存在"
    allowed = [str(x) for x in _json_list(row[0])]
    if not allowed:
        return True, ""
    ctx = await _actor_context(user_id)
    mine = set(ctx.role_codes) | {str(x) for x in ctx.role_ids}
    if mine & set(allowed):
        return True, ""
    if await _is_superuser(user_id):
        return True, ""
    return False, (f"值类型 {code} 仅限角色 {'、'.join(allowed)} 使用，"
                   f"当前用户的角色为 {'、'.join(sorted(mine)) or '（无）'}")


async def can_manage_value_types(user_id: int | None) -> bool:
    """能否增删改值类型（官方：需要 space 的 Editor 或 Owner）。"""
    if await _is_superuser(user_id):
        return True
    ctx = await _actor_context(user_id)
    # 我们的等价物：拥有任意"管理员"语义角色
    return any("管理" in c or "admin" in c.lower() for c in ctx.role_codes)


async def list_objects(domain_code: str | None = None, owner_id: int | None = None) -> list[dict]:
    """对象类型列表；``domain_code`` 传入时只返回该本体下的对象（None = 全部）。

    ``owner_id`` 传入时叠加该用户的工作副本（草稿改动可见但未落库）。
    """
    await _ensure_domain_schema()
    async with async_db_session() as db:
        sql = ("SELECT id,code,name,icon,key_prop,name_prop,description,enabled,"
               "COALESCE(domain_code,''),COALESCE(plural_name,''),COALESCE(api_name,''),"
               "aliases,COALESCE(status,'experimental'),COALESCE(visibility,'normal'),"
               "COALESCE(index_status,'not_started'),edits_enabled,datasource_id,"
               "COALESCE(backing_table,''),COALESCE(point_of_contact,''),contributors,"
               "COALESCE(rid,''),COALESCE(is_business,true) "
               "FROM ai_ont_object WHERE is_deleted=false")
        params: dict = {}
        if domain_code is not None:
            sql += " AND COALESCE(domain_code,'')=:dc"
            params["dc"] = domain_code
        rows = (await db.execute(_t(sql + " ORDER BY id DESC"), params)).fetchall()
        # DQ 健康分（该对象物化表对应 ai_dq_report）
        dq = {}
        try:
            dr = (await db.execute(_t(
                "SELECT table_name, score FROM ai_dq_report WHERE is_deleted=false"))).fetchall()
            dq = {x[0]: (float(x[1]) if x[1] is not None else None) for x in dr}
        except Exception:  # noqa: BLE001
            dq = {}
        # ---- 批量统计：一次聚合查询替代每对象 4 次 N+1 计数 ----
        prop_cnt = {x[0]: int(x[1]) for x in (await db.execute(_t(
            "SELECT object_code, count(*) FROM ai_ont_property WHERE is_deleted=false GROUP BY object_code"))).fetchall()}
        sens_cnt = {x[0]: int(x[1]) for x in (await db.execute(_t(
            "SELECT object_code, count(*) FROM ai_ont_property WHERE sensitive=true AND is_deleted=false GROUP BY object_code"))).fetchall()}
        act_cnt = {x[0]: int(x[1]) for x in (await db.execute(_t(
            "SELECT object_code, count(*) FROM ai_ont_action WHERE is_deleted=false GROUP BY object_code"))).fetchall()}
        link_cnt: dict[str, int] = {}
        for x in (await db.execute(_t(
                "SELECT source_object, count(*) FROM ai_ont_link WHERE is_deleted=false GROUP BY source_object"))).fetchall():
            link_cnt[x[0]] = link_cnt.get(x[0], 0) + int(x[1])
        for x in (await db.execute(_t(
                "SELECT target_object, count(*) FROM ai_ont_link WHERE is_deleted=false GROUP BY target_object"))).fetchall():
            link_cnt[x[0]] = link_cnt.get(x[0], 0) + int(x[1])
    out = []
    for r in rows:
        code = r[1]
        out.append({
            "id": r[0], "code": code, "name": r[2], "icon": r[3] or "el-icon-Box",
            "key_prop": r[4] or "id", "name_prop": r[5] or "name",
            "description": r[6] or "", "enabled": bool(r[7]), "domain_code": r[8] or "",
            "plural_name": r[9] or "", "api_name": r[10] or "",
            "aliases": _json_list(r[11]),
            "status": r[12] or "experimental", "visibility": r[13] or "normal",
            "index_status": r[14] or "not_started", "edits_enabled": bool(r[15]),
            "datasource_id": r[16], "backing_table": r[17] or "",
            "point_of_contact": r[18] or "", "contributors": _json_list(r[19]),
            "rid": r[20] or "",
            "is_business": bool(r[21]),
            "property_count": prop_cnt.get(code, 0),
            "link_count": link_cnt.get(code, 0),
            "action_count": act_cnt.get(code, 0),
            "sensitive_count": sens_cnt.get(code, 0),
            "dq_score": dq.get(code),
        })
    return await wip_overlay(owner_id, "object", out, "id", "code")


async def _dq_score(code: str):
    r = await _exec("SELECT score FROM ai_dq_report WHERE table_name=:c AND is_deleted=false", {"c": code})
    v = r.scalar()
    return float(v) if v is not None else None


async def _sensitive_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_property WHERE object_code=:c AND sensitive=true AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def _prop_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_property WHERE object_code=:c AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def _link_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_link WHERE (source_object=:c OR target_object=:c) AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def _action_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_action WHERE object_code=:c AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def upsert_object(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="对象编码必填")
    await _ensure_domain_schema()
    dc = (data.get("domain_code") or "") if data.get("domain_code") is not None else None
    # 官方必填：ID(code) / Display name / Plural display name / API name / 至少一个属性 + 主键与标题键
    name = (data.get("name") or "").strip()
    plural = (data.get("plural_name") or "").strip() or (f"{name}s" if name else "")
    api_name = (data.get("api_name") or "").strip() or derive_api_name(code)
    status = data.get("status") or "experimental"
    visibility = data.get("visibility") or "normal"
    if status not in ONT_STATUS:
        raise CustomException(msg=f"状态取值非法：{status}")
    if visibility not in ONT_VISIBILITY:
        raise CustomException(msg=f"可见性取值非法：{visibility}")
    common = {
        "n": name or code, "i": data.get("icon", "el-icon-Box"),
        "k": data.get("key_prop", "id"), "np": data.get("name_prop", "name"),
        "d": data.get("description", ""), "e": bool(data.get("enabled", True)),
        "pn": plural, "api": api_name, "al": json.dumps(data.get("aliases") or [], ensure_ascii=False),
        "st": status, "vi": visibility,
        "dx": data.get("datasource_id"), "bt": data.get("backing_table", "") or code,
        "poc": data.get("point_of_contact", ""),
        "ctb": json.dumps(data.get("contributors") or [], ensure_ascii=False),
        "ed": bool(data.get("edits_enabled")),
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_object SET name=:n, icon=:i, key_prop=:k, name_prop=:np, "
            "description=:d, enabled=:e, domain_code=COALESCE(:dc, domain_code), "
            "plural_name=:pn, api_name=:api, aliases=:al, status=:st, visibility=:vi, "
            "datasource_id=:dx, backing_table=:bt, point_of_contact=:poc, contributors=:ctb, "
            "edits_enabled=:ed, updated_time=now() WHERE id=:id",
            {**common, "dc": dc, "id": data["id"]})
        return {"id": data["id"]}
    try:
        # 同编码可能存在于软删除的行里（code 有唯一约束）：复活并覆盖，而不是报"已存在"
        exist = (await _exec(
            "SELECT id FROM ai_ont_object WHERE code=:c", {"c": code})).fetchone()
        if exist:
            await _exec_write(
                "UPDATE ai_ont_object SET name=:n, icon=:i, key_prop=:k, name_prop=:np, "
                "description=:d, enabled=:e, domain_code=:dc, plural_name=:pn, api_name=:api, "
                "aliases=:al, status=:st, visibility=:vi, datasource_id=:dx, backing_table=:bt, "
                "point_of_contact=:poc, contributors=:ctb, edits_enabled=:ed, "
                "is_deleted=false, updated_time=now() WHERE id=:id",
                {**common, "dc": dc or "", "id": exist[0]})
            return {"id": exist[0], "code": code, "revived": True}
        r = await _exec_write(
            "INSERT INTO ai_ont_object(code,name,icon,key_prop,name_prop,description,enabled,domain_code,"
            "plural_name,api_name,aliases,status,visibility,datasource_id,backing_table,point_of_contact,"
            "contributors,edits_enabled) "
            "VALUES (:c,:n,:i,:k,:np,:d,:e,:dc,:pn,:api,:al,:st,:vi,:dx,:bt,:poc,:ctb,:ed) RETURNING id",
            {**common, "c": code, "dc": dc or ""})
        return {"id": r.scalar(), "code": code}
    except Exception as e:  # noqa: BLE001
        if "duplicate" in str(e).lower():
            raise CustomException(msg=f"对象编码 {code} 已存在")
        raise CustomException(msg=f"保存失败：{str(e)[:80]}")


_PROP_COLS = ("SELECT id,object_code,name,code,prop_type,required,unique_col,sensitive,source_col,"
              "options,description,roles,COALESCE(api_name,''),COALESCE(base_type,''),title_key,"
              "COALESCE(visibility,'normal'),edit_only,value_formatting,conditional_formatting,"
              "COALESCE(render_hint,''),COALESCE(type_class,''),COALESCE(status,'experimental'),"
              "COALESCE(shared_code,''),derived,struct_fields,COALESCE(value_type_code,''),"
              "COALESCE(is_business,true) "
              "FROM ai_ont_property ")


async def list_properties(object_code: str = "", owner_id: int | None = None) -> list[dict]:
    """列出属性。object_code 为空时列出全部（供「属性」资源清单页使用）。"""
    if object_code:
        r = await _exec(_PROP_COLS + "WHERE object_code=:c AND is_deleted=false ORDER BY id",
                        {"c": object_code})
    else:
        r = await _exec(_PROP_COLS + "WHERE is_deleted=false ORDER BY object_code,id")
    rows = r.fetchall()
    out = [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3], "prop_type": x[4],
            "required": bool(x[5]), "unique_col": bool(x[6]), "sensitive": bool(x[7]),
            "source_col": x[8] or "", "options": _json_list(x[9]),
            "description": x[10] or "", "roles": _json_list(x[11]),
            "api_name": x[12] or "", "base_type": x[13] or "",
            "title_key": bool(x[14]), "visibility": x[15] or "normal",
            "edit_only": bool(x[16]), "value_formatting": _json_dict(x[17]),
            "conditional_formatting": _json_list(x[18]),
            "render_hint": x[19] or "", "type_class": x[20] or "",
            "status": x[21] or "experimental",
            # ---- P5 ----
            "shared_code": x[22] or "", "derived": _json_dict(x[23]),
            "struct_fields": _json_list(x[24]), "value_type_code": x[25] or "",
            "is_business": bool(x[26])} for x in rows]
    out = await wip_overlay(owner_id, "property", out, "id", "code")
    if object_code:
        out = [p for p in out if p.get("object_code") == object_code]
    return out


async def upsert_property(data: dict, actor_id: int | None = None) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="属性编码/对象编码必填")
    visibility = data.get("visibility") or "normal"
    if visibility not in ONT_VISIBILITY:
        raise CustomException(msg=f"可见性取值非法：{visibility}")
    # 值类型的 roles 在这里真正生效：没有对应角色就不能把它分配给属性
    vtc = (data.get("value_type_code") or "").strip()
    if vtc:
        ok, why = await can_assign_value_type(vtc, actor_id)
        if not ok:
            raise CustomException(msg=why)
    # 派生属性的三条硬限制（≤3 层 / limit 1–100 / 不能依赖派生）
    if (data.get("type_class") or "") == "derived":
        derr = await validate_derived(data)
        if derr:
            raise CustomException(msg="派生属性配置有误：" + "；".join(derr))
    common = {
        "n": data.get("name", code), "p": data.get("prop_type", "string"),
        "r": bool(data.get("required")), "u": bool(data.get("unique_col")),
        "s": bool(data.get("sensitive")), "sc": data.get("source_col", ""),
        "o": json.dumps(data.get("options") or [], ensure_ascii=False),
        "d": data.get("description", ""),
        "roles": json.dumps(data.get("roles") or [], ensure_ascii=False),
        "api": (data.get("api_name") or "").strip() or derive_api_name(code),
        "bt": data.get("base_type", ""),
        "tk": bool(data.get("title_key")), "vi": visibility,
        "eo": bool(data.get("edit_only")),
        "vf": json.dumps(data.get("value_formatting") or {}, ensure_ascii=False),
        "cf": json.dumps(data.get("conditional_formatting") or [], ensure_ascii=False),
        "rh": data.get("render_hint", ""), "tc": data.get("type_class", ""),
        "st": data.get("status") or "experimental",
        # ---- P5 ----
        "shc": data.get("shared_code", ""),
        "dv": json.dumps(data.get("derived") or {}, ensure_ascii=False),
        "sf": json.dumps(data.get("struct_fields") or [], ensure_ascii=False),
        "vtc": data.get("value_type_code", ""),
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_property SET name=:n, prop_type=:p, required=:r, unique_col=:u, "
            "sensitive=:s, source_col=:sc, options=:o, description=:d, roles=:roles, "
            "api_name=:api, base_type=:bt, title_key=:tk, visibility=:vi, edit_only=:eo, "
            "value_formatting=:vf, conditional_formatting=:cf, render_hint=:rh, type_class=:tc, "
            "status=:st, shared_code=:shc, derived=:dv, struct_fields=:sf, value_type_code=:vtc "
            "WHERE id=:id",
            {**common, "id": data["id"]})
        return {"id": data["id"]}
    # 没给 id 时按 (对象类型, 属性编码) 做真正的「upsert」。
    # 早先这里是无脑 INSERT：调用方只要不带 id 就会静默产生**重复属性行**，
    # 而重复行会让权限判定（如属性 roles）读到互相矛盾的值。
    if not data.get("id"):
        exist = (await _exec(
            "SELECT id FROM ai_ont_property WHERE object_code=:oc AND code=:c "
            "AND is_deleted=false", {"oc": obj, "c": code})).fetchone()
        if exist:
            await _exec_write(
                "UPDATE ai_ont_property SET name=:n, prop_type=:p, required=:r, unique_col=:u, "
                "sensitive=:s, source_col=:sc, options=:o, description=:d, roles=:roles, "
                "api_name=:api, base_type=:bt, title_key=:tk, visibility=:vi, edit_only=:eo, "
                "value_formatting=:vf, conditional_formatting=:cf, render_hint=:rh, "
                "type_class=:tc, status=:st, shared_code=:shc, derived=:dv, struct_fields=:sf, "
                "value_type_code=:vtc WHERE id=:id",
                {**common, "id": exist[0]})
            return {"id": exist[0]}
    r = await _exec_write(
        "INSERT INTO ai_ont_property(object_code,name,code,prop_type,required,unique_col,sensitive,"
        "source_col,options,description,roles,api_name,base_type,title_key,visibility,edit_only,"
        "value_formatting,conditional_formatting,render_hint,type_class,status,shared_code,derived,"
        "struct_fields,value_type_code) "
        "VALUES (:oc,:n,:c,:p,:r,:u,:s,:sc,:o,:d,:roles,:api,:bt,:tk,:vi,:eo,:vf,:cf,:rh,:tc,:st,"
        ":shc,:dv,:sf,:vtc) RETURNING id",
        {**common, "oc": obj, "c": code})
    return {"id": r.scalar()}


_LINK_COLS = ("SELECT id,source_object,target_object,name,card,source_field,target_field,description,"
              "COALESCE(join_method,'foreign_key'),COALESCE(api_name,''),COALESCE(source_name,''),"
              "COALESCE(source_plural_name,''),COALESCE(target_name,''),COALESCE(target_plural_name,''),"
              "COALESCE(status,'experimental'),COALESCE(visibility,'normal') FROM ai_ont_link ")


async def list_links(object_code: str | None = None, owner_id: int | None = None) -> list[dict]:
    if object_code:
        r = await _exec(_LINK_COLS + "WHERE (source_object=:c OR target_object=:c) AND is_deleted=false ORDER BY id",
                        {"c": object_code})
    else:
        r = await _exec(_LINK_COLS + "WHERE is_deleted=false ORDER BY id")
    rows = r.fetchall()
    out = [{"id": x[0], "source_object": x[1], "target_object": x[2], "name": x[3], "card": x[4],
            "source_field": x[5] or "", "target_field": x[6] or "", "description": x[7] or "",
            "join_method": x[8] or "foreign_key", "api_name": x[9] or "",
            "source_name": x[10] or "", "source_plural_name": x[11] or "",
            "target_name": x[12] or "", "target_plural_name": x[13] or "",
            "status": x[14] or "experimental", "visibility": x[15] or "normal"} for x in rows]
    out = await wip_overlay(owner_id, "link", out, "id", "name")
    if object_code:
        out = [lk for lk in out
               if lk.get("source_object") == object_code or lk.get("target_object") == object_code]
    return out


async def upsert_link(data: dict) -> dict:
    if not (data.get("source_object") and data.get("target_object")):
        raise CustomException(msg="源/目标对象必填")
    card = data.get("card", "many_to_one")
    if card not in ONT_CARDINALITY:
        raise CustomException(msg=f"基数取值非法：{card}")
    join_method = data.get("join_method", "foreign_key")
    if join_method not in ONT_JOIN_METHOD:
        raise CustomException(msg=f"连接方式取值非法：{join_method}")
    # 官方约束：many-to-many 必须由连接表数据集支撑
    if card == "many_to_many" and join_method != "dataset":
        raise CustomException(msg="多对多关系必须使用「连接表 Dataset」连接方式")
    common = {
        "s": data["source_object"], "t": data["target_object"], "n": data.get("name", ""),
        "c": card, "sf": data.get("source_field", ""), "tf": data.get("target_field", ""),
        "d": data.get("description", ""), "jm": join_method,
        "api": (data.get("api_name") or "").strip() or derive_api_name(data.get("name", "")),
        "sn": data.get("source_name", ""), "spn": data.get("source_plural_name", ""),
        "tn": data.get("target_name", ""), "tpn": data.get("target_plural_name", ""),
        "st": data.get("status") or "experimental",
        "vi": data.get("visibility") or "normal",
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_link SET source_object=:s, target_object=:t, name=:n, card=:c, "
            "source_field=:sf, target_field=:tf, description=:d, join_method=:jm, api_name=:api, "
            "source_name=:sn, source_plural_name=:spn, target_name=:tn, target_plural_name=:tpn, "
            "status=:st, visibility=:vi WHERE id=:id",
            {**common, "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write(
        "INSERT INTO ai_ont_link(source_object,target_object,name,card,source_field,target_field,"
        "description,join_method,api_name,source_name,source_plural_name,target_name,"
        "target_plural_name,status,visibility) "
        "VALUES (:s,:t,:n,:c,:sf,:tf,:d,:jm,:api,:sn,:spn,:tn,:tpn,:st,:vi) RETURNING id",
        common)
    return {"id": r.scalar()}


_ACT_COLS = ("SELECT id,object_code,name,code,input_schema,white_fields,approval,target_table,method,"
             "description,COALESCE(tool_description,''),rules,parameters,submission_criteria,"
             "side_effects,ui_sections,COALESCE(status,'experimental'),"
             "COALESCE(visibility,'normal') FROM ai_ont_action ")


async def list_actions(object_code: str | None = None, owner_id: int | None = None) -> list[dict]:
    if object_code:
        r = await _exec(_ACT_COLS + "WHERE object_code=:c AND is_deleted=false ORDER BY id",
                        {"c": object_code})
    else:
        r = await _exec(_ACT_COLS + "WHERE is_deleted=false ORDER BY id")
    rows = r.fetchall()
    out = [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3],
            "input_schema": _json_list(x[4]), "white_fields": _json_list(x[5]),
            "approval": bool(x[6]), "target_table": x[7] or "", "method": x[8] or "update",
            "description": x[9] or "",
            # tool_description 是供 AI 作工具描述的一等字段（对齐官方）
            "tool_description": x[10] or "",
            "rules": _json_list(x[11]), "parameters": _json_list(x[12]),
            "submission_criteria": _json_list(x[13]), "side_effects": _json_list(x[14]),
            "ui_sections": _json_list(x[15]), "status": x[16] or "experimental",
            "visibility": x[17] or "normal"} for x in rows]
    out = await wip_overlay(owner_id, "action", out, "id", "code")
    if object_code:
        out = [a for a in out if a.get("object_code") == object_code]
    return out


async def upsert_action(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="动作编码/对象编码必填")
    common = {
        "n": data.get("name", code),
        # 显式传入 parameters 时同步生成 input_schema（工具 JSON Schema 的来源）
        "i": json.dumps(data.get("input_schema") or data.get("parameters") or [], ensure_ascii=False),
        "w": json.dumps(data.get("white_fields") or [], ensure_ascii=False),
        "a": bool(data.get("approval")), "t": data.get("target_table", ""),
        "m": data.get("method", "update"), "d": data.get("description", ""),
        "td": data.get("tool_description", ""),
        "rl": json.dumps(data.get("rules") or [], ensure_ascii=False),
        "pm": json.dumps(data.get("parameters") or [], ensure_ascii=False),
        "sc": json.dumps(data.get("submission_criteria") or [], ensure_ascii=False),
        "se": json.dumps(data.get("side_effects") or [], ensure_ascii=False),
        "us": json.dumps(data.get("ui_sections") or [], ensure_ascii=False),
        "st": data.get("status") or "experimental",
        "vi": data.get("visibility") or "normal",
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_action SET name=:n, input_schema=:i, white_fields=:w, approval=:a, "
            "target_table=:t, method=:m, description=:d, tool_description=:td, rules=:rl, "
            "parameters=:pm, submission_criteria=:sc, side_effects=:se, ui_sections=:us, "
            "status=:st, visibility=:vi WHERE id=:id",
            {**common, "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write(
        "INSERT INTO ai_ont_action(object_code,name,code,input_schema,white_fields,approval,"
        "target_table,method,description,tool_description,rules,parameters,submission_criteria,"
        "side_effects,ui_sections,status,visibility) "
        "VALUES (:oc,:n,:c,:i,:w,:a,:t,:m,:d,:td,:rl,:pm,:sc,:se,:us,:st,:vi) RETURNING id",
        {**common, "oc": obj, "c": code})
    return {"id": r.scalar()}


async def _log_change(object_code: str, kind: str, action: str, detail: str = "", created_id: int = 0) -> None:
    """本体变更留痕（对象/属性/Link/Action/函数 增删改）。"""
    try:
        await _exec_write(
            "INSERT INTO ai_ont_change_log(object_code,kind,action,detail,created_id) VALUES (:o,:k,:a,:d,:uid)",
            {"o": object_code or "-", "k": kind, "a": action, "d": detail[:250] or "", "uid": created_id or 0})
    except Exception:  # noqa: BLE001
        pass


async def list_changelog(object_code: str | None = None, limit: int = 50) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,object_code,kind,action,detail,created_id,created_time FROM ai_ont_change_log "
                        "WHERE object_code=:c AND is_deleted=false ORDER BY id DESC LIMIT :n",
                        {"c": object_code, "n": limit})
    else:
        r = await _exec("SELECT id,object_code,kind,action,detail,created_id,created_time FROM ai_ont_change_log "
                        "WHERE is_deleted=false ORDER BY id DESC LIMIT :n", {"n": limit})
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "kind": x[2], "action": x[3],
             "detail": x[4] or "", "created_id": x[5], "created_time": str(x[6]) if x[6] else ""} for x in rows]


async def delete_one(table: str, id: int) -> None:
    await _exec_write(f"UPDATE {table} SET is_deleted=true WHERE id=:id", {"id": id})


# ---------------------------------------------------------------------------
# 工作副本（Working copy）
#
# 对齐 Palantir Ontology Manager：所有改动先进「工作副本」，右上角 Save 才落库；
# Discard 丢弃。读取时把草稿叠加到结果上，因此界面上能立刻看到改动，但库里没有。
# ---------------------------------------------------------------------------
_WIP_KINDS = ("object", "property", "link", "action", "function",
              "group", "value_type", "shared_property", "interface")
_WIP_KIND_LABEL = {
    "object": "对象类型",
    "property": "属性",
    "link": "关系类型",
    "action": "动作类型",
    "function": "函数",
    "group": "对象类型组",
    "value_type": "值类型",
    "shared_property": "共享属性",
    "interface": "接口",
}


def _wip_key(kind: str, data: dict) -> str:
    """草稿的唯一键：对象/属性/关系/动作/函数 各取自己的标识。"""
    if kind == "link":
        return str(data.get("id") or f"{data.get('source_object')}->{data.get('target_object')}:{data.get('source_field', '')}")
    if kind == "property":
        return str(data.get("id") or f"{data.get('object_code')}.{data.get('code')}")
    return str(data.get("id") or data.get("code") or "")


async def list_wip(owner_id: int) -> list[dict]:
    r = await _exec(
        "SELECT id,kind,action,target_key,data,created_time FROM ai_ont_wip "
        "WHERE owner_id=:o ORDER BY id", {"o": int(owner_id or 0)})
    out = []
    for x in r.fetchall():
        out.append({
            "id": x[0], "kind": x[1], "action": x[2], "target_key": x[3] or "",
            "data": _json_dict(x[4]), "created_time": str(x[5]) if x[5] else "",
        })
    return out


async def stage_change(owner_id: int, kind: str, action: str, data: dict,
                       target_key: str = "") -> dict:
    """暂存一条改动。

    同 kind + target_key 的 update 会覆盖前一条（避免同一实体堆积多条草稿）；
    create 之后又 delete → 直接互相抵消，不留下无意义草稿。
    """
    owner = int(owner_id or 0)
    if kind not in _WIP_KINDS:
        raise CustomException(msg=f"未知的本体资源类型：{kind}")
    if action not in ("create", "update", "delete", "restore"):
        raise CustomException(msg=f"未知的改动类型：{action}")
    data = data or {}
    key = target_key or _wip_key(kind, data)
    if not key:
        raise CustomException(msg="改动缺少标识（id 或 code）")

    existing = await _exec(
        "SELECT id,action FROM ai_ont_wip WHERE owner_id=:o AND kind=:k AND target_key=:t ORDER BY id",
        {"o": owner, "k": kind, "t": key})
    rows = existing.fetchall()
    # create 后又 delete → 抵消
    if rows and rows[0][1] == "create" and action == "delete":
        await _exec_write("DELETE FROM ai_ont_wip WHERE owner_id=:o AND kind=:k AND target_key=:t",
                          {"o": owner, "k": kind, "t": key})
        return {"ok": True, "canceled": True, "target_key": key}
    # 同实体只保留最后一条草稿
    if rows:
        await _exec_write("DELETE FROM ai_ont_wip WHERE owner_id=:o AND kind=:k AND target_key=:t",
                          {"o": owner, "k": kind, "t": key})
        # 原本是 create，后续 update 仍算 create
        if rows[0][1] == "create" and action == "update":
            action = "create"
    await _exec_write(
        "INSERT INTO ai_ont_wip(owner_id,kind,action,target_key,data) VALUES (:o,:k,:a,:t,:d)",
        {"o": owner, "k": kind, "a": action, "t": key,
         "d": json.dumps(data, ensure_ascii=False)})
    return {"ok": True, "target_key": key, "action": action}


async def discard_wip(owner_id: int) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_wip WHERE owner_id=:o", {"o": int(owner_id or 0)})
    n = r.scalar() or 0
    await _exec_write("DELETE FROM ai_ont_wip WHERE owner_id=:o", {"o": int(owner_id or 0)})
    return int(n)


def _apply_wip(items: list[dict], kind: str, ops: list[dict], id_key: str = "id",
               code_key: str = "code") -> list[dict]:
    """把工作副本叠加到读取结果上：删除 → 过滤；更新 → 合并；新建 → 追加。"""
    mine = [o for o in ops if o.get("kind") == kind]
    if not mine:
        return items
    out = [dict(x) for x in items]
    for op in mine:
        d = op.get("data") or {}
        key = op.get("target_key") or ""
        hit = None
        for x in out:
            if str(x.get(id_key) or "") == key or str(x.get(code_key) or "") == key:
                hit = x
                break
        if op["action"] == "delete":
            if hit is not None:
                out.remove(hit)
        elif op["action"] in ("update", "create"):
            if hit is not None:
                hit.update(d)
            else:
                out.insert(0, dict(d))
    return out


async def wip_overlay(owner_id: int | None, kind: str, items: list[dict],
                      id_key: str = "id", code_key: str = "code") -> list[dict]:
    """便捷包装：有草稿才查库叠加。"""
    if not owner_id:
        return items
    try:
        ops = await list_wip(int(owner_id))
    except Exception:  # noqa: BLE001
        return items
    return _apply_wip(items, kind, ops, id_key, code_key)


def _review_wip(ops: list[dict], objects: list[dict], props: list[dict],
                actions: list[dict] | None = None, functions: list[dict] | None = None) -> dict:
    """审核草稿：errors 阻塞保存；warnings 不阻塞；destructive 需输入实体名确认。"""
    errors: list[str] = []
    warnings: list[str] = []
    destructive: list[dict] = []
    obj_codes = {o["code"] for o in objects}
    prop_keys = {(p.get("object_code"), p.get("code")) for p in props}
    act_codes = {a["code"] for a in (actions or [])}
    fn_codes = {f["code"] for f in (functions or [])}
    staged_obj_codes = {
        (o.get("data") or {}).get("code")
        for o in ops if o["kind"] == "object" and o["action"] in ("create", "update")
    }
    seen: set[tuple[str, str]] = set()

    for op in ops:
        kind, action = op["kind"], op["action"]
        d = op.get("data") or {}
        label = _WIP_KIND_LABEL.get(kind, kind)
        name = d.get("name") or d.get("code") or op.get("target_key") or ""

        # 同一资源重复暂存
        sig = (kind, str(op.get("target_key") or ""))
        if sig in seen:
            errors.append(f"{label}「{name}」暂存了多条改动，请先丢弃后重试")
        seen.add(sig)

        if action == "delete":
            destructive.append({"kind": kind, "name": name, "reason": f"删除{label}"})
            continue
        if action == "restore":
            destructive.append({
                "kind": kind, "name": name,
                "reason": f"把{label}恢复到历史版本 v{d.get('version')}（会覆盖当前定义）",
            })
            continue

        if kind == "object":
            if not (d.get("code") or "").strip():
                errors.append("对象类型缺少编码")
            if not (d.get("name") or "").strip():
                errors.append(f"对象类型「{d.get('code')}」缺少显示名")
            if action == "create" and (d.get("code") or "") in obj_codes:
                errors.append(f"对象类型编码 {d.get('code')} 已存在，请改为编辑而不是新建")
            if not (d.get("api_name") or "").strip():
                warnings.append(f"对象类型「{name}」未填 API 名（将自动推导）")
            if not (d.get("description") or "").strip():
                warnings.append(f"对象类型「{name}」未填描述")
            if not d.get("key_prop"):
                warnings.append(f"对象类型「{name}」未指定主键属性")
        elif kind == "property":
            oc = (d.get("object_code") or "").strip()
            if not (d.get("code") or "").strip() or not (d.get("name") or "").strip():
                errors.append("属性缺少显示名或属性 ID")
            if oc and oc not in obj_codes and oc not in staged_obj_codes:
                errors.append(f"属性「{name}」所属对象类型 {oc} 不存在")
            if oc and (oc, d.get("code")) in prop_keys and action == "create":
                errors.append(f"对象类型 {oc} 下已存在属性 {d.get('code')}")
        elif kind == "link":
            s, t = (d.get("source_object") or "").strip(), (d.get("target_object") or "").strip()
            if not s or not t:
                errors.append("关系类型缺少源/目标对象类型")
            if s and s not in obj_codes and s not in staged_obj_codes:
                warnings.append(f"关系类型「{name}」的源对象类型 {s} 不存在")
            if t and t not in obj_codes and t not in staged_obj_codes:
                warnings.append(f"关系类型「{name}」的目标对象类型 {t} 不存在")
            if d.get("card") == "many_to_many" and d.get("join_method") != "dataset":
                errors.append(f"关系类型「{name}」是多对多，必须使用「连接表 Dataset」")
        elif kind == "action":
            if not (d.get("code") or "").strip() or not (d.get("name") or "").strip():
                errors.append("动作类型缺少动作名或编码")
            if action == "create" and (d.get("code") or "") in act_codes:
                errors.append(f"动作编码 {d.get('code')} 已存在，请改为编辑")
            if not (d.get("object_code") or "").strip():
                errors.append(f"动作类型「{name}」未指定作用对象类型")
            if not (d.get("target_table") or "").strip():
                warnings.append(f"动作类型「{name}」未指定写回目标表")
            if not (d.get("white_fields") or []):
                warnings.append(f"动作类型「{name}」未配置可写字段白名单，执行时会放行所有字段")
            if not (d.get("tool_description") or "").strip():
                warnings.append(f"动作类型「{name}」未填 Tool description，Agent 将回退使用普通描述")
            # 提交条件 / 规则 / 副作用：配置有误在保存前就拦住
            pkeys = {str(p.get("key")) for p in (d.get("parameters") or [])
                     if isinstance(p, dict) and p.get("key")}
            pkeys |= {(w if isinstance(w, str) else w.get("key"))
                      for w in (d.get("white_fields") or [])}
            pkeys = {k for k in pkeys if k}
            errors += _ae.validate_criteria(d.get("submission_criteria"), pkeys)
            errors += _ae.validate_rules(d.get("rules"), pkeys)
            errors += _ae.validate_side_effects(d.get("side_effects"))
            if d.get("side_effects") and not d.get("rules") and not (d.get("target_table") or "").strip():
                warnings.append(f"动作类型「{name}」只配了副作用，没有编辑规则或写回目标表")
        elif kind == "function":
            if not (d.get("code") or "").strip() or not (d.get("name") or "").strip():
                errors.append("函数缺少函数名或编码")
            if action == "create" and (d.get("code") or "") in fn_codes:
                errors.append(f"函数编码 {d.get('code')} 已存在，请改为编辑")
            # 函数定义交给函数引擎校验（表达式变量/内置函数/聚合配置/URL/模型等）
            for e in _fe.validate_function(d):
                errors.append(f"函数「{name}」：{e}")

    # 破坏性变更：改主键 / 改属性类型（仅当草稿**确实带了**该字段且与现状不同才算）
    for op in ops:
        if op["action"] != "update":
            continue
        d = op.get("data") or {}
        if op["kind"] == "object":
            if not d.get("key_prop"):
                continue  # 部分更新，未涉及主键
            old = next((o for o in objects if o["code"] == d.get("code")), None)
            if old and (old.get("key_prop") != d.get("key_prop")):
                destructive.append({
                    "kind": "object", "name": d.get("name") or d.get("code"),
                    "reason": f"修改主键属性（{old.get('key_prop')} → {d.get('key_prop')}）",
                })
        if op["kind"] == "property":
            if not d.get("prop_type"):
                continue
            old = next((p for p in props
                        if p.get("object_code") == d.get("object_code")
                        and p.get("code") == d.get("code")), None)
            if old and old.get("prop_type") != d.get("prop_type"):
                destructive.append({
                    "kind": "property", "name": d.get("name") or d.get("code"),
                    "reason": f"修改属性类型（{old.get('prop_type')} → {d.get('prop_type')}）",
                })
    return {"errors": errors, "warnings": warnings, "destructive": destructive}


async def _lite_props() -> list[dict]:
    """轻量属性查询：仅取审核所需的 (object_code, code, prop_type) 三列。

    审核草稿（/wip）不需要 options/roles/value_formatting 等大 JSONB 字段，
    全量 list_properties() 会对 8522 行逐个 json.loads 六个 JSONB 列，导致
    /wip 逼近甚至超过前端超时阈值。这里只查关键列，几毫秒即回。
    """
    r = await _exec(
        "SELECT object_code, code, prop_type FROM ai_ont_property "
        "WHERE is_deleted=false ORDER BY object_code,id")
    return [{"object_code": x[0], "code": x[1], "prop_type": x[2] or ""} for x in r.fetchall()]


async def review_wip(owner_id: int) -> dict:
    """审核工作副本，返回 errors / warnings / destructive 与改动清单。"""
    ops = await list_wip(owner_id)
    if not ops:
        # 没有待审核改动时不需要全量加载对象/属性/动作/函数，
        # 否则每次进本体页 /wip 都会触发慢查询导致请求超时。
        return {"count": 0, "changes": [], "errors": [], "warnings": [], "destructive": []}
    objects = await list_objects()
    # 审核只用到属性的 (object_code, code, prop_type) 三列，不要走全量
    # list_properties()（会解析 6 个 JSONB 字段）；只查需要的关键列，
    # 否则属性量大（实测 8522 条）时 /wip 会超过前端超时阈值。
    props = await _lite_props()
    actions = await list_actions()
    funcs = await list_functions()
    rv = _review_wip(ops, objects, props, actions, funcs)
    return {
        "count": len(ops),
        "changes": [
            {
                "kind": o["kind"], "action": o["action"],
                "label": _WIP_KIND_LABEL.get(o["kind"], o["kind"]),
                "name": (o.get("data") or {}).get("name")
                or (o.get("data") or {}).get("code") or o.get("target_key"),
            }
            for o in ops
        ],
        **rv,
    }


async def save_wip(owner_id: int, confirm_name: str = "") -> dict:
    """保存工作副本：有 errors 拒绝；有破坏性改动且未输入正确实体名也拒绝。"""
    ops = await list_wip(owner_id)
    if not ops:
        return {"ok": True, "applied": 0, "msg": "没有待保存的改动"}
    objects = await list_objects()
    props = await list_properties()
    actions = await list_actions()
    funcs = await list_functions()
    rv = _review_wip(ops, objects, props, actions, funcs)
    if rv["errors"]:
        return {"ok": False, "applied": 0, "errors": rv["errors"],
                "msg": f"有 {len(rv['errors'])} 处错误，无法保存"}
    if rv["destructive"]:
        names = {d["name"] for d in rv["destructive"] if d.get("name")}
        if (confirm_name or "").strip() not in names:
            return {
                "ok": False, "applied": 0, "destructive": rv["destructive"],
                "msg": ("存在破坏性改动，需输入实体名称确认"
                        + (f"（可输入：{'、'.join(sorted(names))}）" if names else "")),
            }

    # 依赖顺序：先建对象 → 再属性/关系/动作/函数 → 最后删除
    order = {"object": 0, "property": 1, "link": 1, "action": 1, "function": 1}
    creates = [o for o in ops if o["action"] != "delete"]
    deletes = [o for o in ops if o["action"] == "delete"]
    creates.sort(key=lambda o: order.get(o["kind"], 9))

    applied = 0
    failed: list[str] = []
    for op in creates + deletes:
        kind, action, d = op["kind"], op["action"], op.get("data") or {}
        try:
            if action == "restore":
                res = await rollback_version(int(d.get("version_id") or 0))
                if not res.get("ok"):
                    raise CustomException(msg=res.get("msg") or "恢复失败")
            elif action == "delete":
                # 新类型走各自的删除入口，以便做引用检查（不能绕过）
                if kind == "value_type":
                    res = await delete_value_type(int(d.get("id") or 0), owner_id)
                    if not res.get("ok"):
                        raise CustomException(msg=res.get("msg") or "无法删除值类型")
                elif kind == "shared_property":
                    res = await delete_shared_property(int(d.get("id") or 0))
                    if not res.get("ok"):
                        raise CustomException(msg=res.get("msg") or "无法删除共享属性")
                elif kind == "interface":
                    res = await delete_interface(int(d.get("id") or 0))
                    if not res.get("ok"):
                        raise CustomException(msg=res.get("msg") or "无法删除接口")
                elif kind == "group":
                    await delete_group(int(d.get("id") or 0))
                    await _log_change("", kind, "delete", f"删除对象类型组 #{d.get('id')}")
                else:
                    eid = await _resolve_entity_id(kind, d)
                    if not eid:
                        raise CustomException(msg="找不到要删除的记录（id 与 code 均未匹配）")
                    await remove_entity(kind, eid)
            elif kind == "object":
                await upsert_object(d)
            elif kind == "property":
                await upsert_property(d, owner_id)
            elif kind == "link":
                await upsert_link(d)
            elif kind == "action":
                await upsert_action(d)
            elif kind == "function":
                await upsert_function(d, owner_id)
            elif kind == "group":
                await upsert_group(d)
            elif kind == "value_type":
                await upsert_value_type(d, owner_id)
            elif kind == "shared_property":
                await upsert_shared_property(d, owner_id)
            elif kind == "interface":
                await upsert_interface(d)
            applied += 1
        except Exception as e:  # noqa: BLE001
            failed.append(f"{_WIP_KIND_LABEL.get(kind, kind)}「{d.get('name') or d.get('code')}」：{e}")

    if not failed:
        await _exec_write("DELETE FROM ai_ont_wip WHERE owner_id=:o", {"o": int(owner_id or 0)})
    return {
        "ok": not failed, "applied": applied, "failed": failed,
        "msg": f"已保存 {applied} 处改动" + (f"，{len(failed)} 处失败" if failed else ""),
    }


# ---------------------------------------------------------------------------
# 导入 / 导出（本体定义 JSON）
#
# 官方明确声明「不要依赖导出的 schema」，这里同样标注为不稳定：
# 仅保证同版本内可导回，跨版本不保证兼容。
# ---------------------------------------------------------------------------
async def export_ontology(domain_code: str | None = None) -> dict:
    """导出本体定义为 JSON（对象类型 + 属性 + 关系 + 动作 + 函数）。"""
    objects = await list_objects(domain_code)
    codes = {o["code"] for o in objects}
    props = [p for p in await list_properties() if p["object_code"] in codes]
    links = [lk for lk in await list_links() if lk["source_object"] in codes and lk["target_object"] in codes]
    actions = [a for a in await list_actions() if a["object_code"] in codes]
    funcs = [f for f in await list_functions() if f["object_code"] in codes]
    return {
        "format": "aistation.ontology/v1",
        "exported_at": "",
        "domain_code": domain_code or "",
        "counts": {"objects": len(objects), "properties": len(props), "links": len(links),
                   "actions": len(actions), "functions": len(funcs)},
        "objects": objects, "properties": props, "links": links,
        "actions": actions, "functions": funcs,
    }


async def import_ontology(payload: dict, owner_id: int = 0, mode: str = "stage") -> dict:
    """导入本体定义。

    ``mode='stage'``：写入工作副本，由用户确认后 Save（默认，安全）；
    ``mode='apply'``：直接落库（需调用方自行确认）。
    """
    if not isinstance(payload, dict) or "objects" not in payload:
        raise CustomException(msg="导入内容不是合法的本体定义（缺少 objects）")
    objects = payload.get("objects") or []
    props = payload.get("properties") or []
    links = payload.get("links") or []
    actions = payload.get("actions") or []
    funcs = payload.get("functions") or []

    if mode == "apply":
        n = 0
        for o in objects:
            await upsert_object(o)
            n += 1
        for p in props:
            await upsert_property(p)
            n += 1
        for lk in links:
            await upsert_link(lk)
            n += 1
        for a in actions:
            await upsert_action(a)
            n += 1
        for f in funcs:
            await upsert_function(f)
            n += 1
        return {"ok": True, "mode": "apply", "applied": n}

    for o in objects:
        await stage_change(owner_id, "object", "update" if o.get("id") else "create", o)
    for p in props:
        await stage_change(owner_id, "property", "update" if p.get("id") else "create", p)
    for lk in links:
        await stage_change(owner_id, "link", "update" if lk.get("id") else "create", lk)
    for a in actions:
        await stage_change(owner_id, "action", "update" if a.get("id") else "create", a)
    for f in funcs:
        await stage_change(owner_id, "function", "update" if f.get("id") else "create", f)
    total = len(objects) + len(props) + len(links) + len(actions) + len(funcs)
    return {"ok": True, "mode": "stage", "staged": total}


# ---------------------------------------------------------------------------
# 用量与清理
# ---------------------------------------------------------------------------
async def ontology_usage(object_code: str | None = None) -> dict:
    """本体用量：读数（Agent 工具调用）/ 写入（动作执行）/ 交互（本体页改动）。

    数据来自既有日志表，不额外埋点：
    - 读数：``ai_call_logs`` 中工具名以 ont_fn__ / ont_action__ / list_ontology 开头的调用
    - 写入：``ai_action_log`` 中动作执行记录
    - 交互：``ai_ont_change_log`` 中定义改动记录
    """
    read_where = ("WHERE (tool_name LIKE 'ont_fn__%' OR tool_name LIKE 'ont_action__%' "
                  "OR tool_name = 'list_ontology')")
    reads = 0
    try:
        reads = int((await _exec(f"SELECT count(*) FROM ai_call_logs {read_where}")).scalar() or 0)
    except Exception:  # noqa: BLE001
        reads = 0
    writes = 0
    try:
        if object_code:
            writes = int((await _exec(
                "SELECT count(*) FROM ai_action_log WHERE object_table=:c AND is_deleted=false",
                {"c": object_code})).scalar() or 0)
        else:
            writes = int((await _exec(
                "SELECT count(*) FROM ai_action_log WHERE is_deleted=false")).scalar() or 0)
    except Exception:  # noqa: BLE001
        writes = 0
    edits = 0
    try:
        if object_code:
            edits = int((await _exec(
                "SELECT count(*) FROM ai_ont_change_log WHERE object_code=:c AND is_deleted=false",
                {"c": object_code})).scalar() or 0)
        else:
            edits = int((await _exec(
                "SELECT count(*) FROM ai_ont_change_log WHERE is_deleted=false")).scalar() or 0)
    except Exception:  # noqa: BLE001
        edits = 0
    return {
        "object_code": object_code or "",
        "reads": reads, "writes": writes, "edits": edits,
        "note": "读数=Agent 工具调用次数；写入=动作执行次数；交互=本体定义改动次数",
    }


async def cleanup_suggestions() -> list[dict]:
    """清理建议：弃用 / 删除候选（由既有字段派生，不做假数据）。"""
    objects = await list_objects()
    out: list[dict] = []
    for o in objects:
        code = o["code"]
        prop_n = o.get("property_count") or 0
        link_n = o.get("link_count") or 0
        act_n = o.get("action_count") or 0
        fn_n = await _fn_count(code)
        if prop_n == 0:
            out.append({"object_code": code, "object_name": o.get("name"), "level": "high",
                        "action": "deprecate", "reason": "没有任何属性，无法承载数据"})
        elif link_n == 0 and act_n == 0 and fn_n == 0:
            out.append({"object_code": code, "object_name": o.get("name"), "level": "medium",
                        "action": "deprecate", "reason": "未参与任何关系，也没有动作/函数，疑似孤岛"})
        if (o.get("status") or "") == "deprecated":
            out.append({"object_code": code, "object_name": o.get("name"), "level": "low",
                        "action": "delete", "reason": "已标记为 deprecated，可考虑删除"})
    return out


async def _fn_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_function WHERE object_code=:c AND is_deleted=false",
                    {"c": code})
    return int(r.scalar() or 0)


_ONT_TABLE_OF = {
    "object": "ai_ont_object",
    "property": "ai_ont_property",
    "link": "ai_ont_link",
    "action": "ai_ont_action",
    "function": "ai_ont_function",
    "group": "ai_ont_group",
    "value_type": "ai_ont_value_type",
    "shared_property": "ai_ont_shared_property",
    "interface": "ai_ont_interface",
}


async def _resolve_entity_id(kind: str, d: dict) -> int:
    """删除草稿可能只带 code（前端列表行不一定带 id），这里兜底按 code 反查 id。"""
    eid = int(d.get("id") or 0)
    if eid:
        return eid
    table = _ONT_TABLE_OF.get(kind)
    code = (d.get("code") or "").strip()
    if not table or not code:
        return 0
    try:
        if kind == "property":
            row = (await _exec(
                f"SELECT id FROM {table} WHERE object_code=:o AND code=:c AND is_deleted=false",
                {"o": d.get("object_code", ""), "c": code})).fetchone()
        elif kind == "link":
            row = (await _exec(
                f"SELECT id FROM {table} WHERE name=:c AND is_deleted=false", {"c": code})).fetchone()
        else:
            row = (await _exec(
                f"SELECT id FROM {table} WHERE code=:c AND is_deleted=false", {"c": code})).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return 0


async def remove_entity(kind: str, entity_id: int) -> None:
    """删除一条本体资源（软删）+ 留痕。供保存工作副本与删除接口共用。"""
    table = _ONT_TABLE_OF.get(kind)
    if not table or not entity_id:
        raise CustomException(msg=f"非法删除请求：{kind}#{entity_id}")
    code = ""
    try:
        row = (await _exec(f"SELECT object_code FROM {table} WHERE id=:id", {"id": entity_id})).fetchone()
        if row:
            code = row[0] or ""
    except Exception:  # noqa: BLE001
        code = ""
    await delete_one(table, entity_id)
    await _log_change(code, kind, "delete", f"删除 {kind} #{entity_id}")


# ---------------------------------------------------------------------------
# 实例层（Object Explorer / Vertex / Object Views）
#
# 与类型层（ai_ont_* 定义）的区别：
#   类型层图 = 对象类型之间的 Link type（Schema）
#   实例层图 = 真实数据行之间按 Link type 连出来的边（Vertex / Search Around）
#
# 关系是有方向的，因此遍历必须双向：
#   - 本对象是 source（如 video_cameras.group_id → video_camera_groups.id）：正向取目标行
#   - 本对象是 target（如 video_alarm_records.camera_id → video_cameras.id）：反向取来源行
# ---------------------------------------------------------------------------
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 敏感字段名启发式：即便本体里没勾 sensitive，也**永远不允许写回**。
# 这是兜底防线——只靠人工勾选 sensitive 是不够的（实测 1479 个属性里一个都没勾）。
# 注意 `token` 有歧义：`access_token` 是凭据，`max_tokens` 只是配置，故排除后者。
_SECRET_WORDS = re.compile(
    r"(password|passwd|pwd|secret|api_?key|private_?key|credential|salt|signature|"
    r"access_?key|session_?id)",
    re.I,
)
_TOKEN_WORDS = re.compile(r"token", re.I)
# 这些不是密钥，是配额/上限类配置，以及「分词器」这类模型名
_TOKEN_NOT_SECRET = re.compile(
    r"(max_?tokens?|min_?tokens?|num_?tokens?|token_?(limit|count|size|budget|quota|length)"
    r"|tokenizer_?(model|name|path|type|dir))",
    re.I,
)


def is_sensitive_like(code: str) -> bool:
    """字段名是否像敏感信息（写回时一律拒绝，界面按敏感展示）。"""
    c = code or ""
    if _SECRET_WORDS.search(c):
        return True
    if _TOKEN_WORDS.search(c):
        return not _TOKEN_NOT_SECRET.search(c)
    return False


def _q(name: str) -> str:
    """把标识符包成双引号（避免在 f-string 里嵌套同类引号）。"""
    return chr(34) + name + chr(34)


def _dialect() -> str:
    """当前数据库方言名（postgresql / sqlite / mysql …）。"""
    try:
        return async_engine.dialect.name
    except Exception:  # noqa: BLE001
        return "postgresql"


def _cast_text(expr: str) -> str:
    """把表达式转成文本，**跨方言**。

    不要直接写 ``"col"::text`` —— 那是 Postgres 专属，SQLite 会报
    ``unrecognized token: ":"``、MySQL 也不认。实例层（读/写/权限/场景）大量用到，
    因此统一走这里。
    """
    d = _dialect()
    if d == "postgresql":
        return f"{expr}::text"
    if d == "mysql":
        return f"CAST({expr} AS CHAR)"
    return f"CAST({expr} AS TEXT)"


def _ilike() -> str:
    """不区分大小写的 LIKE，跨方言。SQLite/MySQL 用 LIKE 即可（默认不区分大小写）。"""
    return "ILIKE" if _dialect() == "postgresql" else "LIKE"


def _safe_ident(name: str) -> str:
    """标识符白名单校验：表名/列名只允许 ASCII 字母数字下划线，防注入。"""
    n = (name or "").strip()
    if not _IDENT.match(n):
        raise CustomException(msg=f"非法标识符：{name}")
    return n


async def _table_columns(table: str) -> set[str]:
    """真实表当前存在的列（用于剔除本体里已失效的属性）。

    **不要用 information_schema**：那是 Postgres/MySQL 专属，SQLite 上没有，
    会让"物化"判定在本项目支持的 SQLite 环境下**永远为假**（历史上就被
    ``except: return set()`` 藏住了）。这里统一走 SQLAlchemy 反射，跨方言可用。
    """
    if not table or not _IDENT.match(table):
        return set()
    try:
        from sqlalchemy import inspect as _inspect

        async with async_db_session() as db:
            cols = await db.run_sync(
                lambda s: {c["name"] for c in _inspect(s.connection()).get_columns(table)})
        return set(cols or set())
    except Exception:  # noqa: BLE001
        return set()


async def _instance_meta(code: str) -> dict:
    """实例层查询所需的对象元信息：支撑表、主键、标题、真实存在的列。"""
    r = await _exec(
        "SELECT code,name,key_prop,name_prop,COALESCE(backing_table,''),edits_enabled "
        "FROM ai_ont_object WHERE code=:c AND is_deleted=false", {"c": code})
    row = r.fetchone()
    if not row:
        return {}
    table = row[4] or row[0]
    if not _IDENT.match(table or ""):
        return {"error": f"对象 {code} 的支撑表名不合法：{table}"}
    props = await list_properties(code)
    real_cols = await _table_columns(table)
    cols = [p["code"] for p in props if p["code"] in real_cols and _IDENT.match(p["code"])]
    key_prop = row[2] or "id"
    if key_prop not in real_cols:
        # 主键不在表里（如未物化）→ 退回 id
        key_prop = "id" if "id" in real_cols else (cols[0] if cols else "")
    name_prop = row[3] or ""
    if name_prop not in real_cols:
        name_prop = ""
    return {
        "code": row[0], "name": row[1], "table": table, "key_prop": key_prop,
        "name_prop": name_prop, "edits_enabled": bool(row[5]),
        "props": props, "cols": cols, "real_cols": real_cols,
        "materialized": bool(real_cols),
    }


def _row_to_instance(meta: dict, row: object, columns: list[str]) -> dict:
    """把一行真实数据转成实例对象（只带本体里声明过的属性）。"""
    out = {c: row[i] for i, c in enumerate(columns)}
    key = meta.get("key_prop")
    label = ""
    np_ = meta.get("name_prop")
    if np_ and np_ in out and out[np_] is not None:
        label = str(out[np_])
    if not label and key in out and out[key] is not None:
        label = f"{meta.get('name') or meta.get('code')} #{out[key]}"
    return {
        "key": str(out.get(key)) if out.get(key) is not None else "",
        "label": label,
        "object_code": meta["code"],
        "object_name": meta.get("name") or meta["code"],
        "props": out,
    }


async def instance_search(object_code: str, keyword: str = "", filters: dict | None = None,
                          limit: int = 50, offset: int = 0,
                          principal: Any = None,
                          scenario_code: str = "") -> dict:
    """实例搜索：在对象类型的支撑表里按关键词/字段过滤真实行。"""
    meta = await _instance_meta(object_code)
    if not meta:
        return {"ok": False, "msg": "对象类型不存在", "items": [], "total": 0}
    if meta.get("error"):
        return {"ok": False, "msg": meta["error"], "items": [], "total": 0}
    if not meta["materialized"]:
        return {"ok": False, "msg": "该对象类型尚未物化为数据表，无法浏览实例",
                "items": [], "total": 0, "columns": []}

    table = _safe_ident(meta["table"])
    cols = [_safe_ident(c) for c in meta["cols"]]
    if not cols:
        return {"ok": False, "msg": "该对象类型没有可展示的属性", "items": [], "total": 0}
    collist = ",".join(f'"{c}"' for c in cols)

    where: list[str] = []
    params: dict = {}
    kw = (keyword or "").strip()
    if kw:
        # 关键词在标题属性（或前 6 个文本列）上做 ILIKE
        cands = [meta["name_prop"]] if meta["name_prop"] else []
        cands = [c for c in cands if c in cols] or cols[:6]
        parts = [f'COALESCE({_cast_text(_q(_safe_ident(c)))},\'\') {_ilike()} :kw' for c in cands]
        where.append("(" + " OR ".join(parts) + ")")
        params["kw"] = f"%{kw}%"
    for k, v in (filters or {}).items():
        if k not in cols or v in (None, ""):
            continue
        col = _safe_ident(k)
        if isinstance(v, dict):  # {op: ..., value: x}
            op = str(v.get("op") or "eq")
            val = v.get("value")
            # 算子词表必须与对象视图的筛选器（object_view.ONT_FILTER_OPS）一致，
            # 否则同一套条件在视图里配了、到底层却落到 eq 分支，静默筛不出东西。
            if op in ("like", "contains"):
                where.append(f'COALESCE({_cast_text(_q(col))},\'\') {_ilike()} :f_{col}')
                params[f"f_{col}"] = f"%{val}%"
            elif op in ("gt", "gte", "lt", "lte"):
                sign = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
                where.append(f'"{col}" {sign} :f_{col}')
                params[f"f_{col}"] = val
            elif op == "ne":
                where.append(f'"{col}" != :f_{col}')
                params[f"f_{col}"] = val
            elif op == "is_empty":
                where.append(f'("{col}" IS NULL OR {_cast_text(_q(col))} = \'\')')
            elif op == "not_empty":
                where.append(f'("{col}" IS NOT NULL AND {_cast_text(_q(col))} != \'\')')
            else:
                where.append(f'"{col}" = :f_{col}')
                params[f"f_{col}"] = val
        else:
            where.append(f'"{col}" = :f_{col}')
            params[f"f_{col}"] = v
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    kc = _safe_ident(meta["key_prop"])

    total = int((await _exec(
        f'SELECT count(*) FROM "{table}" {wsql}', params)).scalar() or 0)
    lim = max(1, min(int(limit or 50), 500))
    off = max(0, int(offset or 0))
    r = await _exec(
        f'SELECT {collist} FROM "{table}" {wsql} ORDER BY "{kc}" LIMIT :_lim OFFSET :_off',
        {**params, "_lim": lim, "_off": off})
    rows = r.fetchall()
    items = [_row_to_instance(meta, x, cols) for x in rows]

    # 可选的过滤字段（供前端做筛选器）
    filter_cols = [
        {"code": p["code"], "name": p["name"], "prop_type": p["prop_type"],
         "options": p.get("options") or []}
        for p in meta["props"] if p["code"] in cols
    ]
    total_before = total
    sec_meta: dict = {}
    if scenario_code:
        # P5：场景叠加 —— 读的是「基线数据 + 场景差异」，真实表不受影响
        from . import scenario as _sc

        items = await _sc.overlay_edits(scenario_code, object_code, items)
        total = len(items)
        sec_meta["scenario"] = scenario_code
        sec_meta["scenario_overlay"] = True
    if principal is not None:
        # 读时生效：先按行策略过滤，再掩掉不可读的列
        sec = await _sec.filter_instances(object_code, items, principal)
        items = sec["rows"]
        hidden = set(sec["hidden_columns"])
        cols = [c for c in cols if c not in hidden]
        filter_cols = [c for c in filter_cols if c.get("code") not in hidden]
        sec_meta = {"policy_filtered": True, "dropped_by_policy": sec["dropped"],
                    "hidden_columns": sorted(hidden), "total_before_policy": total_before,
                    "total_note": "行级策略在读时过滤，翻页总数按本页实际可见条数计"}
        total = len(items)
    return {"ok": True, "items": items, "total": total, "columns": cols,
            "columns_meta": filter_cols, "offset": off, "limit": lim,
            "object_code": meta["code"], "object_name": meta.get("name"),
            "key_prop": meta["key_prop"], "edits_enabled": meta["edits_enabled"],
            **sec_meta}


async def instance_get(object_code: str, key: str, principal: Any = None,
                       scenario_code: str = "") -> dict:
    """取单个实例：全部属性 + 可用链接（含对端数量）+ 可执行动作。"""
    meta = await _instance_meta(object_code)
    if not meta or meta.get("error"):
        return {"ok": False, "msg": (meta or {}).get("error") or "对象类型不存在"}
    if not meta["materialized"]:
        return {"ok": False, "msg": "该对象类型尚未物化为数据表"}
    table = _safe_ident(meta["table"])
    cols = [_safe_ident(c) for c in meta["cols"]]
    kc = _safe_ident(meta["key_prop"])
    collist = ",".join(f'"{c}"' for c in cols)
    r = await _exec(f'SELECT {collist} FROM "{table}" WHERE {_cast_text(_q(kc))} = :k', {"k": str(key)})
    row = r.fetchone()
    if not row:
        return {"ok": False, "msg": f"实例 {key} 不存在"}
    inst = _row_to_instance(meta, row, cols)
    inst["ok"] = True
    inst["edits_enabled"] = meta["edits_enabled"]

    # 该对象类型参与的所有关系（双向都要列出来）
    rels = await list_links(object_code)
    links = []
    for lk in rels:
        outgoing = lk["source_object"] == object_code
        other = lk["target_object"] if outgoing else lk["source_object"]
        links.append({
            "id": lk["id"], "name": lk["name"], "direction": "out" if outgoing else "in",
            "direction_label": "指向" if outgoing else "被引用",
            "other_object": other, "other_label": await _object_name(other),
            "card": lk["card"], "api_name": lk.get("api_name") or "",
        })
    acts = await list_actions(object_code)
    props_meta = [
        {"code": p["code"], "name": p["name"], "prop_type": p["prop_type"],
         # 敏感 = 本体标记 或 字段名像敏感信息（两条任一成立都按敏感处理）
         "sensitive": bool(p.get("sensitive")) or is_sensitive_like(p["code"]),
         "edit_only": bool(p.get("edit_only")),
         "visibility": p.get("visibility") or "normal", "base_type": p.get("base_type") or ""}
        for p in meta["props"] if p["code"] in set(cols)
    ]
    sec_meta: dict = {}
    if scenario_code:
        # P5：场景叠加 —— 基线数据 + 场景差异；场景内被删的对象按不存在处理
        from . import scenario as _sc

        if await _sc.is_deleted_in_scenario(scenario_code, object_code, key):
            return {"ok": False, "msg": "该对象在场景内已被删除",
                    "scenario": scenario_code, "scenario_deleted": True}
        merged = await _sc.overlay_instance(scenario_code, object_code, key,
                                            inst.get("props") or {})
        if merged != (inst.get("props") or {}):
            inst["props"] = merged
            sec_meta["scenario"] = scenario_code
            sec_meta["scenario_overlay"] = True
    if principal is not None:
        # 先判行级（不可读直接拒绝），再掩列级
        ok_r, why_r = await _sec.row_allows(object_code, inst.get("props") or {}, principal)
        if not ok_r:
            return {"ok": False, "msg": f"无权查看该实例：{why_r}",
                    "denied": True, "reason": why_r}
        vis = await _sec.visible_properties(object_code, principal)
        inst["props"] = _sec.mask_props(inst.get("props") or {}, vis)
        hidden = sorted({p["code"] for p in props_meta} - vis)
        props_meta = [p for p in props_meta if p["code"] in vis]
        sec_meta = {"hidden_columns": hidden,
                    "row_policy_ok": True, "row_policy_reason": why_r}
    return {
        **inst,
        "properties_meta": props_meta,
        "links": links,
        "actions": [
            {"code": a["code"], "name": a["name"], "approval": bool(a.get("approval")),
             "white_fields": a.get("white_fields") or [], "method": a.get("method") or "update"}
            for a in acts
        ],
        **sec_meta,
    }


async def _object_name(code: str) -> str:
    try:
        r = await _exec("SELECT name FROM ai_ont_object WHERE code=:c AND is_deleted=false", {"c": code})
        row = r.fetchone()
        return (row[0] if row else "") or code
    except Exception:  # noqa: BLE001
        return code


def _json_safe(v: Any) -> Any:
    """把查询结果转成可 JSON 序列化的值。"""
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return v


async def instance_aggregate(object_code: str, group_by: str = "",
                             aggs: list[dict] | None = None,
                             filters: dict | None = None,
                             limit: int = 50,
                             principal: Any = None,
                             scenario_code: str = "") -> dict:
    """**带权限的聚合**：按字段分组统计。

    为什么必须有它：`instance_search` 只能点查；而图表的聚合是直接拼 SQL 的，
    **绕过了行级策略**（本体自己的 `_render_chart` 就踩了这个洞）。
    聚合的过滤必须发生在 GROUP BY **之前**，所以这里走
    ``security.row_filter_sql`` 把策略下推成 WHERE。

    ``aggs`` 形如 ``[{"fn": "count"}, {"fn": "sum", "prop": "amount"}]``；
    默认 ``count(*)``。
    """
    from . import security as _sec

    meta = await _instance_meta(object_code)
    if not meta or meta.get("error"):
        return {"ok": False, "msg": f"对象类型 {object_code} 不可用"}
    if not meta.get("materialized"):
        return {"ok": False, "msg": "对象类型未物化，无法统计"}
    table = _safe_ident(meta["table"])
    cols = set(meta.get("real_cols") or set())

    # 行级过滤（下推到聚合之前）
    rf = await _sec.row_filter_sql(object_code, principal, cols)
    if not rf.get("ok"):
        return {"ok": False, "blocked_by": "row_policy", "msg": rf.get("reason")}
    where = rf.get("where") or ""

    # 列级过滤：不可见的列既不能分组也不能聚合
    vis = await _sec.visible_properties(object_code, principal)
    if vis:
        gb = _safe_ident(group_by) if group_by in vis else ""
        if group_by and not gb:
            return {"ok": False, "blocked_by": "column_policy",
                    "msg": f"分组字段 {group_by} 对当前身份不可见"}
    else:
        gb = _safe_ident(group_by) if group_by else ""

    parts: list[str] = []
    if gb:
        parts.append(f'{_cast_text(_q(gb))} AS k')
    for a in (aggs or [{"fn": "count"}]):
        fn = str(a.get("fn") or "count").lower()
        if fn not in ("count", "sum", "avg", "min", "max"):
            return {"ok": False, "msg": f"不支持的聚合 {fn}"}
        prop = str(a.get("prop") or "")
        if prop:
            if vis and prop not in vis:
                return {"ok": False, "blocked_by": "column_policy",
                        "msg": f"字段 {prop} 对当前身份不可见"}
            if prop not in cols:
                return {"ok": False, "msg": f"字段 {prop} 不在表里"}
            parts.append(f'{fn}("{_safe_ident(prop)}") AS v')
        else:
            parts.append(f"{fn}(*) AS v")
    if not parts:
        parts.append("count(*) AS v")

    lim = max(1, min(int(limit or 50), 1000))
    sql = f'SELECT {", ".join(parts)} FROM "{table}"'
    if where:
        sql += f" WHERE {where}"
    if gb:
        sql += " GROUP BY 1 ORDER BY 2 DESC"
    sql += f" LIMIT {lim}"
    try:
        rows = (await _exec(sql, {})).fetchall()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "msg": f"聚合失败：{str(e)[:120]}"}
    series = [{"label": (r[0] if gb else "合计"), "value": r[1]} for r in rows]
    return {"ok": True, "object_code": object_code, "group_by": gb,
            "row_policy_applied": bool(where), "row_policy_mode": rf.get("mode"),
            "columns_restricted": bool(vis),
            "series": series, "count": len(series),
            "rows": [[_json_safe(r[0]), _json_safe(r[1])] for r in rows]}


async def instance_pivot(object_code: str, key: str, link_id: int, limit: int = 50,
                        principal: Any = None) -> dict:
    """沿一条关系从某个实例跳到关联实例（Search Around 的一步）。

    关系有方向，两个方向都要支持：
    - 本对象是 source：用本行 source_field 的值去匹配 target 行的 target_field
    - 本对象是 target：用本行主键去匹配 source 行的 source_field（反向遍历）
    """
    lk = next((x for x in await list_links() if x["id"] == int(link_id)), None)
    if not lk:
        return {"ok": False, "msg": "关系不存在", "items": []}
    if object_code not in (lk["source_object"], lk["target_object"]):
        return {"ok": False, "msg": "该关系与本对象类型无关", "items": []}
    outgoing = lk["source_object"] == object_code
    other_code = lk["target_object"] if outgoing else lk["source_object"]
    other_field = lk["target_field"] if outgoing else lk["source_field"]
    my_field = lk["source_field"] if outgoing else lk["target_field"]

    mine = await _instance_meta(object_code)
    other = await _instance_meta(other_code)
    if not mine.get("materialized") or not other.get("materialized"):
        return {"ok": False, "msg": "任一侧的对象类型尚未物化，无法跳转", "items": []}
    if my_field not in mine["real_cols"] or other_field not in other["real_cols"]:
        return {"ok": False, "msg": f"关系字段不存在（{my_field} / {other_field}）", "items": []}

    my_table, other_table = _safe_ident(mine["table"]), _safe_ident(other["table"])
    my_kc = _safe_ident(mine["key_prop"])
    mf, of = _safe_ident(my_field), _safe_ident(other_field)
    src = (await _exec(f'SELECT "{mf}" FROM "{my_table}" WHERE {_cast_text(_q(my_kc))} = :k',
                       {"k": str(key)})).fetchone()
    if not src or src[0] is None:
        return {"ok": True, "items": [], "total": 0, "link": lk, "other_object": other_code,
                "msg": "该实例在这条关系上没有关联值"}
    cols = [_safe_ident(c) for c in other["cols"]]
    collist = ",".join(f'"{c}"' for c in cols)
    lim = max(1, min(int(limit or 50), 500))
    r = await _exec(
        f'SELECT {collist} FROM "{other_table}" WHERE "{of}" = :v LIMIT :_lim',
        {"v": src[0], "_lim": lim})
    items = [_row_to_instance(other, x, cols) for x in r.fetchall()]
    sec_meta: dict = {}
    if principal is not None:
        # 关联对象同样要过权限：否则能从"看得见的对象"跳到"看不见的对象"
        sec = await _sec.filter_instances(other_code, items, principal)
        items = sec["rows"]
        sec_meta = {"policy_filtered": True, "dropped_by_policy": sec["dropped"],
                    "hidden_columns": sec["hidden_columns"]}
    return {"ok": True, "items": items, "total": len(items), "link": lk,
            "other_object": other_code, "other_name": other.get("name"),
            "direction": "out" if outgoing else "in", **sec_meta}


async def instance_graph(object_code: str, key: str, link_ids: list[int] | None = None,
                         depth: int = 1, limit: int = 120,
                         principal: Any = None) -> dict:
    """实例层图：以真实数据行为节点、关系为边，支持多步扩展（Search Around）。

    返回 GraphCanvas 约定的 {nodes:[{id,name,etype,weight}], edges:[{source,target,rtype,weight}]}。
    """
    root = await instance_get(object_code, key)
    if not root.get("ok"):
        return {"ok": False, "msg": root.get("msg") or "实例不存在", "nodes": [], "edges": []}
    rels = await list_links(object_code)
    use = [lk for lk in rels if (not link_ids or lk["id"] in set(link_ids))]
    if not use:
        return {"ok": True, "nodes": [{"id": root["key"], "name": root["label"],
                                       "etype": object_code, "weight": 1}],
                "edges": [], "msg": "该对象类型没有可扩展的关系"}

    max_depth = max(1, min(int(depth or 1), 3))
    cap = max(10, min(int(limit or 120), 400))
    # 节点按 (object_code, key) 去重；边按 (源,目标,关系) 去重
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    truncated = False

    def _nid(code: str, k: str) -> str:
        # GraphCanvas 以 name 作为节点身份，故这里把 id 与显示名都带上
        return f"{code}:{k}"

    def _add(inst: dict) -> str:
        nid = _nid(inst["object_code"], inst["key"])
        if nid not in nodes:
            nodes[nid] = {"id": nid, "name": inst["label"], "etype": inst["object_code"],
                          "weight": 1, "object_code": inst["object_code"], "key": inst["key"]}
        return nid

    root_id = _add(root)
    frontier = [(object_code, root["key"], root_id)]
    for _ in range(max_depth):
        nxt: list[tuple[str, str, str]] = []
        for code, k, nid in frontier:
            for lk in await list_links(code):
                if use and lk["id"] not in {x["id"] for x in use}:
                    continue
                if len(nodes) >= cap:
                    truncated = True
                    break
                piv = await instance_pivot(code, k, lk["id"], limit=40, principal=principal)
                if not piv.get("ok"):
                    continue
                for inst in piv["items"][:20]:
                    tid = _add(inst)
                    ekey = f"{nid}|{tid}|{lk['id']}|{piv['direction']}"
                    edges.setdefault(ekey, {
                        "source": nid, "target": tid,
                        "rtype": lk["name"] or f"{lk['source_object']}→{lk['target_object']}",
                        "weight": 1, "link_id": lk["id"],
                        "direction": piv["direction"],
                    })
                    if (inst["object_code"], inst["key"], tid) not in [
                        (a, b, c) for a, b, c in nxt
                    ]:
                        nxt.append((inst["object_code"], inst["key"], tid))
            if truncated:
                break
        frontier = nxt
        if not frontier or truncated:
            break

    return {
        "ok": True, "root": root_id, "nodes": list(nodes.values()),
        "edges": list(edges.values()), "truncated": truncated,
        "object_code": object_code, "key": str(key),
        "msg": f"{len(nodes)} 个实例、{len(edges)} 条关系边"
               + ("（已达上限，仅显示部分）" if truncated else ""),
    }


async def writeback_instance(object_code: str, key: str, props: dict,
                             operator: str = "", principal: Any = None) -> dict:
    """属性写回（Writeback）：直接改真实数据表的列。

    仍然走门禁：
    1. 对象类型必须开启 `edits_enabled`
    2. 只能写"本体里声明的、非 edit_only、非 sensitive"的属性
    3. **（P4）** 具备对象类型的编辑权限；写"策略属性"需要管理权限；
       不能写自己都读不到的列（否则是隐蔽提权）
    4. 全部留痕（ai_action_log + ai_ont_change_log）
    """
    meta = await _instance_meta(object_code)
    if not meta or meta.get("error"):
        return {"ok": False, "msg": (meta or {}).get("error") or "对象类型不存在"}
    if not meta["edits_enabled"]:
        return {"ok": False, "msg": f"对象类型「{meta.get('name')}」未开启可编辑（Writeback）"}
    if not meta["materialized"]:
        return {"ok": False, "msg": "该对象类型尚未物化为数据表"}

    if principal is not None:
        # 行级：不能改自己看不到的那一行
        cur = await instance_get(object_code, str(key), principal=principal)
        if not cur.get("ok"):
            return {"ok": False, "msg": cur.get("msg") or "无权访问该实例",
                    "denied": True}
        # 列级：逐列判定（编辑权限 + 策略属性 + 可读性）
        vis = await _sec.visible_properties(object_code, principal)
        for col in (props or {}):
            if col not in vis:
                return {"ok": False, "denied": True,
                        "msg": f"无权写入属性 {col}：该属性对当前用户不可读"}
            ok_e, why_e = await _sec.can_edit_property(object_code, col, principal)
            if not ok_e:
                return {"ok": False, "denied": True, "msg": f"无权写入属性 {col}：{why_e}"}

    editable = {
        p["code"] for p in meta["props"]
        if p["code"] in meta["real_cols"]
        and not p.get("edit_only")
        and not p.get("sensitive")
        and not is_sensitive_like(p["code"])
    }
    target = {k: v for k, v in (props or {}).items() if k in editable}
    if not target:
        rejected = [k for k in (props or {}) if is_sensitive_like(k)]
        if rejected:
            return {"ok": False, "msg": f"字段 {', '.join(rejected)} 被识别为敏感字段，禁止写回"}
        return {"ok": False, "msg": "没有可写的属性（需在本体里声明且未标记为仅动作填充/敏感）"}
    kc = _safe_ident(meta["key_prop"])
    table = _safe_ident(meta["table"])
    sets = ", ".join(f'"{_safe_ident(c)}" = :{c}' for c in target)
    params = {**target, "_k": str(key)}
    try:
        await _exec_write(f'UPDATE "{table}" SET {sets} WHERE {_cast_text(_q(kc))} = :_k', params)
    except Exception as e:  # noqa: BLE001
        await _log_action(meta["code"], str(key), "属性写回", "failed",
                          f"写入失败：{str(e)[:120]}", operator)
        return {"ok": False, "msg": f"写入失败：{str(e)[:120]}"}
    detail = "、".join(f"{k}={v}" for k, v in target.items())
    await _log_action(meta["code"], str(key), "属性写回", "success", detail, operator)
    await _log_change(meta["code"], "object", "writeback", f"实例 #{key} 写回：{detail}")
    return {"ok": True, "msg": f"已写回 {len(target)} 个属性并留痕", "written": list(target)}


async def _log_action(object_code: str, object_key: str, action_name: str,
                      result: str, detail: str, operator: str) -> None:
    """写 ai_action_log（动作执行 / 属性写回统一留痕）。"""
    try:
        await _exec_write(
            "INSERT INTO ai_action_log(object_table,object_key,action_name,result,detail,operator) "
            "VALUES (:t,:k,:a,:r,:d,:o)",
            {"t": object_code, "k": object_key, "a": action_name,
             "r": result, "d": detail, "o": operator})
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# P5 高级类型系统
#
# 六件事：对象类型组 / 值类型 / 共享属性 / 接口 / Struct / 派生属性
# 共同原则：每种类型都要能定义、编辑、删除，**删除前做引用检查**，不能留下悬空引用。
# ---------------------------------------------------------------------------
ONT_TYPE_CLASS = ("value", "shared", "struct", "derived")
ONT_STATUS_SET = set(ONT_STATUS)

# 官方派生属性的 9 种聚合
ONT_AGGREGATIONS = (
    ("count", "计数"),
    ("sum", "求和"),
    ("avg", "平均"),
    ("min", "最小"),
    ("max", "最大"),
    ("first", "第一条"),
    ("last", "最后一条"),
    ("collect_list", "收集为列表"),
    ("collect_set", "收集去重集合"),
)
_AGG_VALUES = {x[0] for x in ONT_AGGREGATIONS}
DERIVED_MAX_HOPS = 3
DERIVED_DEFAULT_LIMIT = 10
DERIVED_MAX_LIMIT = 100


# ---------------------------------------------------------------------------
# 对象类型组（跨对象类型的多对多分组）
# ---------------------------------------------------------------------------
async def list_groups() -> list[dict]:
    r = await _exec("SELECT id,code,name,description,COALESCE(color,''),sort FROM ai_ont_group "
                    "WHERE is_deleted=false ORDER BY sort,id")
    groups = [{"id": x[0], "code": x[1], "name": x[2], "description": x[3] or "",
               "color": x[4] or "", "sort": x[5] or 0, "members": []} for x in r.fetchall()]
    if not groups:
        return []
    m = await _exec("SELECT group_id,object_code FROM ai_ont_group_member ORDER BY id")
    by_id = {g["id"]: g for g in groups}
    for gid, ocode in m.fetchall():
        if gid in by_id:
            by_id[gid]["members"].append(ocode)
    for g in groups:
        g["member_count"] = len(g["members"])
    return groups


async def upsert_group(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="组编码必填")
    if not (data.get("name") or "").strip():
        raise CustomException(msg="组显示名必填")
    common = {"n": data.get("name"), "d": data.get("description", ""),
              "c": data.get("color", ""), "s": int(data.get("sort") or 0)}
    if data.get("id"):
        gid = int(data["id"])
        await _exec_write("UPDATE ai_ont_group SET name=:n, description=:d, color=:c, sort=:s "
                          "WHERE id=:id", {**common, "id": gid})
    else:
        exist = (await _exec("SELECT id FROM ai_ont_group WHERE code=:c", {"c": code})).fetchone()
        if exist:
            gid = int(exist[0])
            await _exec_write("UPDATE ai_ont_group SET name=:n, description=:d, color=:c, sort=:s, "
                              "is_deleted=false WHERE id=:id", {**common, "id": gid})
        else:
            gid = (await _exec_write(
                "INSERT INTO ai_ont_group(code,name,description,color,sort) "
                "VALUES (:c,:n,:d,:col,:s) RETURNING id",
                {"c": code, "n": common["n"], "d": common["d"],
                 "col": common["c"], "s": common["s"]})).scalar()
    if isinstance(data.get("members"), list):
        await set_group_members(int(gid), data["members"])
    return {"id": int(gid)}


async def set_group_members(group_id: int, object_codes: list[str]) -> int:
    await _exec_write("DELETE FROM ai_ont_group_member WHERE group_id=:g", {"g": int(group_id)})
    n = 0
    for oc in object_codes or []:
        oc = str(oc or "").strip()
        if not oc:
            continue
        await _exec_write("INSERT INTO ai_ont_group_member(group_id,object_code) VALUES (:g,:o)",
                          {"g": int(group_id), "o": oc})
        n += 1
    return n


async def delete_group(group_id: int) -> None:
    await _exec_write("DELETE FROM ai_ont_group_member WHERE group_id=:g", {"g": int(group_id)})
    await _exec_write("UPDATE ai_ont_group SET is_deleted=true WHERE id=:g", {"g": int(group_id)})


# ---------------------------------------------------------------------------
# 值类型（语义包装 + 约束 + 版本 + 权限）
# ---------------------------------------------------------------------------
async def list_value_types() -> list[dict]:
    r = await _exec(
        "SELECT id,code,name,COALESCE(base_type,'string'),description,constraints,"
        "COALESCE(version,1),roles,COALESCE(status,'experimental'),COALESCE(visibility,'normal') "
        "FROM ai_ont_value_type WHERE is_deleted=false ORDER BY code")
    rows = r.fetchall()
    out = []
    for x in rows:
        refs = await value_type_refs(x[1])
        out.append({"id": x[0], "code": x[1], "name": x[2], "base_type": x[3],
                    "description": x[4] or "", "constraints": _json_dict(x[5]),
                    "version": x[6] or 1, "roles": _json_list(x[7]),
                    "status": x[8] or "experimental", "visibility": x[9] or "normal",
                    "ref_count": len(refs), "refs": refs})
    return out


async def value_type_refs(code: str) -> list[dict]:
    """谁引用了这个值类型（属性 / 共享属性）。"""
    out = []
    try:
        r = await _exec("SELECT object_code,code,name FROM ai_ont_property "
                        "WHERE value_type_code=:c AND is_deleted=false", {"c": code})
        out += [{"kind": "属性", "where": f"{x[0]}.{x[1]}", "name": x[2]} for x in r.fetchall()]
        r2 = await _exec("SELECT code,name FROM ai_ont_shared_property "
                         "WHERE value_type_code=:c AND is_deleted=false", {"c": code})
        out += [{"kind": "共享属性", "where": x[0], "name": x[1]} for x in r2.fetchall()]
    except Exception:  # noqa: BLE001
        pass
    return out


async def upsert_value_type(data: dict, actor_id: int | None = None) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="值类型编码必填")
    if not (data.get("name") or "").strip():
        raise CustomException(msg="值类型显示名必填")
    # 官方：增改值类型需要 space 的 Editor/Owner；我们等价为超管或管理类角色
    if actor_id and not await can_manage_value_types(actor_id):
        raise CustomException(msg="只有管理员角色可以创建或修改值类型")
    common = {
        "n": data.get("name"), "bt": data.get("base_type") or "string",
        "d": data.get("description", ""),
        "cs": json.dumps(data.get("constraints") or {}, ensure_ascii=False),
        "rl": json.dumps(data.get("roles") or [], ensure_ascii=False),
        "st": data.get("status") or "experimental",
        "vi": data.get("visibility") or "normal",
    }
    if data.get("id"):
        # 改约束/类型即视为新版本（官方：值类型带版本）
        await _exec_write(
            "UPDATE ai_ont_value_type SET name=:n, base_type=:bt, description=:d, "
            "constraints=:cs, roles=:rl, status=:st, visibility=:vi, version=COALESCE(version,1)+1 "
            "WHERE id=:id", {**common, "id": data["id"]})
        return {"id": data["id"], "versioned": True}
    exist = (await _exec("SELECT id FROM ai_ont_value_type WHERE code=:c", {"c": code})).fetchone()
    if exist:
        await _exec_write(
            "UPDATE ai_ont_value_type SET name=:n, base_type=:bt, description=:d, constraints=:cs, "
            "roles=:rl, status=:st, visibility=:vi, version=COALESCE(version,1)+1, is_deleted=false "
            "WHERE id=:id", {**common, "id": exist[0]})
        return {"id": int(exist[0]), "versioned": True}
    r = await _exec_write(
        "INSERT INTO ai_ont_value_type(code,name,base_type,description,constraints,roles,status,"
        "visibility,version) VALUES (:c,:n,:bt,:d,:cs,:rl,:st,:vi,1) RETURNING id",
        {**common, "c": code})
    return {"id": r.scalar()}


async def delete_value_type(vt_id: int, actor_id: int | None = None) -> dict:
    if actor_id and not await can_manage_value_types(actor_id):
        return {"ok": False, "msg": "只有管理员角色可以删除值类型"}
    row = (await _exec("SELECT code FROM ai_ont_value_type WHERE id=:i AND is_deleted=false",
                       {"i": int(vt_id)})).fetchone()
    if not row:
        return {"ok": False, "msg": "值类型不存在"}
    refs = await value_type_refs(row[0])
    if refs:
        return {"ok": False, "msg": f"仍有 {len(refs)} 处引用，无法删除",
                "refs": refs[:10]}
    await _exec_write("UPDATE ai_ont_value_type SET is_deleted=true WHERE id=:i", {"i": int(vt_id)})
    return {"ok": True, "msg": "已删除"}


async def validate_value(vt_code: str, value: Any) -> dict:
    """按值类型的约束校验一个值（供实例层/动作参数校验复用）。"""
    r = await _exec("SELECT code,name,base_type,constraints FROM ai_ont_value_type "
                    "WHERE code=:c AND is_deleted=false", {"c": vt_code})
    row = r.fetchone()
    if not row:
        return {"ok": False, "msg": f"值类型 {vt_code} 不存在"}
    cs = _json_dict(row[3])
    errs: list[str] = []
    opts = cs.get("options")
    if isinstance(opts, list) and opts and str(value) not in [str(o) for o in opts]:
        errs.append(f"取值必须是 {opts} 之一")
    pat = cs.get("pattern")
    if pat:
        try:
            if not re.search(str(pat), str(value)):
                errs.append(f"不匹配模式 {pat}")
        except re.error:
            errs.append(f"值类型的正则无效：{pat}")
    num = None
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = None
    for key, label in (("min", "不小于"), ("max", "不大于")):
        lim = cs.get(key)
        if lim is not None and num is not None:
            bad = (num < float(lim)) if key == "min" else (num > float(lim))
            if bad:
                errs.append(f"数值必须{label} {lim}")
    ln = len(str(value)) if value is not None else 0
    if cs.get("min_length") is not None and ln < int(cs["min_length"]):
        errs.append(f"长度不小于 {cs['min_length']}")
    if cs.get("max_length") is not None and ln > int(cs["max_length"]):
        errs.append(f"长度不大于 {cs['max_length']}")
    return {"ok": not errs, "errors": errs, "value_type": row[0], "name": row[1]}


# ---------------------------------------------------------------------------
# 共享属性（定义一次、多类型引用；只共享元数据，不共享数据）
# ---------------------------------------------------------------------------
async def list_shared_properties() -> list[dict]:
    r = await _exec(
        "SELECT id,code,name,COALESCE(prop_type,'string'),COALESCE(base_type,'string'),"
        "COALESCE(api_name,''),description,COALESCE(value_type_code,''),constraints,"
        "COALESCE(status,'experimental'),COALESCE(visibility,'normal') "
        "FROM ai_ont_shared_property WHERE is_deleted=false ORDER BY code")
    out = []
    for x in r.fetchall():
        refs = await shared_property_refs(x[1])
        out.append({"id": x[0], "code": x[1], "name": x[2], "prop_type": x[3],
                    "base_type": x[4], "api_name": x[5] or derive_api_name(x[1]),
                    "description": x[6] or "", "value_type_code": x[7] or "",
                    "constraints": _json_dict(x[8]), "status": x[9] or "experimental",
                    "visibility": x[10] or "normal",
                    "ref_count": len(refs), "refs": refs})
    return out


async def shared_property_refs(code: str) -> list[dict]:
    r = await _exec("SELECT object_code,code,name FROM ai_ont_property "
                    "WHERE shared_code=:c AND is_deleted=false", {"c": code})
    return [{"kind": "属性", "where": f"{x[0]}.{x[1]}", "name": x[2]} for x in r.fetchall()]


async def upsert_shared_property(data: dict, actor_id: int | None = None) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="共享属性编码必填")
    if not (data.get("name") or "").strip():
        raise CustomException(msg="共享属性显示名必填")
    vtc = (data.get("value_type_code") or "").strip()
    if vtc:
        ok = (await _exec("SELECT 1 FROM ai_ont_value_type WHERE code=:c AND is_deleted=false",
                          {"c": vtc})).fetchone()
        if not ok:
            raise CustomException(msg=f"值类型 {vtc} 不存在")
        allowed, why = await can_assign_value_type(vtc, actor_id)
        if not allowed:
            raise CustomException(msg=why)
    common = {
        "n": data.get("name"), "p": data.get("prop_type") or "string",
        "bt": data.get("base_type") or "string",
        "api": (data.get("api_name") or "").strip() or derive_api_name(code),
        "d": data.get("description", ""), "vtc": vtc,
        "cs": json.dumps(data.get("constraints") or {}, ensure_ascii=False),
        "st": data.get("status") or "experimental",
        "vi": data.get("visibility") or "normal",
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_shared_property SET name=:n, prop_type=:p, base_type=:bt, api_name=:api, "
            "description=:d, value_type_code=:vtc, constraints=:cs, status=:st, visibility=:vi "
            "WHERE id=:id", {**common, "id": data["id"]})
        await _sync_shared_to_refs(code, common)
        return {"id": data["id"]}
    exist = (await _exec("SELECT id FROM ai_ont_shared_property WHERE code=:c", {"c": code})).fetchone()
    if exist:
        await _exec_write(
            "UPDATE ai_ont_shared_property SET name=:n, prop_type=:p, base_type=:bt, api_name=:api, "
            "description=:d, value_type_code=:vtc, constraints=:cs, status=:st, visibility=:vi, "
            "is_deleted=false WHERE id=:id", {**common, "id": exist[0]})
        await _sync_shared_to_refs(code, common)
        return {"id": int(exist[0])}
    r = await _exec_write(
        "INSERT INTO ai_ont_shared_property(code,name,prop_type,base_type,api_name,description,"
        "value_type_code,constraints,status,visibility) "
        "VALUES (:c,:n,:p,:bt,:api,:d,:vtc,:cs,:st,:vi) RETURNING id",
        {**common, "c": code})
    return {"id": r.scalar()}


async def _sync_shared_to_refs(shared_code: str, common: dict) -> int:
    """共享属性的元数据改动，同步到所有引用它的属性上（只同步元数据）。"""
    try:
        r = await _exec_write(
            "UPDATE ai_ont_property SET prop_type=:p, base_type=:bt, value_type_code=:vtc "
            "WHERE shared_code=:c AND is_deleted=false",
            {"p": common["p"], "bt": common["bt"], "vtc": common["vtc"], "c": shared_code})
        return int(getattr(r, "rowcount", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0


async def delete_shared_property(sp_id: int) -> dict:
    row = (await _exec("SELECT code FROM ai_ont_shared_property WHERE id=:i AND is_deleted=false",
                       {"i": int(sp_id)})).fetchone()
    if not row:
        return {"ok": False, "msg": "共享属性不存在"}
    refs = await shared_property_refs(row[0])
    if refs:
        return {"ok": False, "msg": f"仍有 {len(refs)} 个对象类型引用它，无法删除",
                "refs": refs[:10]}
    await _exec_write("UPDATE ai_ont_shared_property SET is_deleted=true WHERE id=:i",
                      {"i": int(sp_id)})
    return {"ok": True, "msg": "已删除"}


# ---------------------------------------------------------------------------
# 接口（定义 + 对象类型实现 + 实现侧强制约束）
# ---------------------------------------------------------------------------
async def list_interfaces() -> list[dict]:
    r = await _exec(
        "SELECT id,code,name,description,required_properties,required_links,required_actions,"
        "COALESCE(status,'experimental'),COALESCE(visibility,'normal') "
        "FROM ai_ont_interface WHERE is_deleted=false ORDER BY code")
    impl = await _exec("SELECT interface_code,object_code FROM ai_ont_interface_impl ORDER BY id")
    by_code: dict[str, list[str]] = {}
    for ic, oc in impl.fetchall():
        by_code.setdefault(ic, []).append(oc)
    out = []
    for x in r.fetchall():
        impls = by_code.get(x[1], [])
        out.append({
            "id": x[0], "code": x[1], "name": x[2], "description": x[3] or "",
            "required_properties": _json_list(x[4]), "required_links": _json_list(x[5]),
            "required_actions": _json_list(x[6]), "status": x[7] or "experimental",
            "visibility": x[8] or "normal", "implementations": impls,
            "impl_count": len(impls),
        })
    return out


async def upsert_interface(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="接口编码必填")
    if not (data.get("name") or "").strip():
        raise CustomException(msg="接口显示名必填")
    common = {
        "n": data.get("name"), "d": data.get("description", ""),
        "rp": json.dumps(data.get("required_properties") or [], ensure_ascii=False),
        "rl": json.dumps(data.get("required_links") or [], ensure_ascii=False),
        "ra": json.dumps(data.get("required_actions") or [], ensure_ascii=False),
        "st": data.get("status") or "experimental",
        "vi": data.get("visibility") or "normal",
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_interface SET name=:n, description=:d, required_properties=:rp, "
            "required_links=:rl, required_actions=:ra, status=:st, visibility=:vi WHERE id=:id",
            {**common, "id": data["id"]})
        return {"id": data["id"]}
    exist = (await _exec("SELECT id FROM ai_ont_interface WHERE code=:c", {"c": code})).fetchone()
    if exist:
        await _exec_write(
            "UPDATE ai_ont_interface SET name=:n, description=:d, required_properties=:rp, "
            "required_links=:rl, required_actions=:ra, status=:st, visibility=:vi, is_deleted=false "
            "WHERE id=:id", {**common, "id": exist[0]})
        return {"id": int(exist[0])}
    r = await _exec_write(
        "INSERT INTO ai_ont_interface(code,name,description,required_properties,required_links,"
        "required_actions,status,visibility) VALUES (:c,:n,:d,:rp,:rl,:ra,:st,:vi) RETURNING id",
        {**common, "c": code})
    return {"id": r.scalar()}


async def set_interface_impls(iface_code: str, object_codes: list[str]) -> dict:
    """设置接口的实现者；设置前逐个校验约束（约束在实现侧强制）。"""
    iface = next((x for x in await list_interfaces() if x["code"] == iface_code), None)
    if not iface:
        return {"ok": False, "msg": "接口不存在"}
    await _exec_write("DELETE FROM ai_ont_interface_impl WHERE interface_code=:c", {"c": iface_code})
    added, rejected = [], []
    for oc in object_codes or []:
        chk = await check_interface_impl(iface_code, str(oc))
        if not chk["ok"]:
            rejected.append({"object_code": oc, "missing": chk["missing"]})
            continue
        await _exec_write("INSERT INTO ai_ont_interface_impl(interface_code,object_code) "
                          "VALUES (:c,:o)", {"c": iface_code, "o": oc})
        added.append(oc)
    return {"ok": not rejected, "added": added, "rejected": rejected,
            "msg": (f"已让 {len(added)} 个对象类型实现该接口"
                    + (f"，{len(rejected)} 个不满足约束被拒绝" if rejected else ""))}


async def check_interface_impl(iface_code: str, object_code: str) -> dict:
    """校验某对象类型是否满足接口要求（属性/关系/动作三类）。"""
    iface = next((x for x in await list_interfaces() if x["code"] == iface_code), None)
    if not iface:
        return {"ok": False, "missing": {"msg": "接口不存在"}}
    props = await list_properties(object_code)
    p_codes = {p["code"] for p in props}
    p_codes |= {p.get("shared_code") for p in props if p.get("shared_code")}
    base_types = {p.get("base_type") for p in props}

    links = await list_links(object_code)
    l_names = {(lk.get("api_name") or "") for lk in links}
    l_names |= {(lk.get("name") or "") for lk in links}

    acts = await list_actions(object_code)
    a_codes = {a["code"] for a in acts}

    missing: dict[str, list] = {}
    miss_props = []
    for rp in iface["required_properties"]:
        if not isinstance(rp, dict):
            continue
        key = rp.get("code") or ""
        if key and key not in p_codes:
            miss_props.append(f"{rp.get('name') or key}（{key}）")
        elif rp.get("base_type") and rp["base_type"] not in base_types and key not in p_codes:
            miss_props.append(f"{key} 的 base type 应为 {rp['base_type']}")
    if miss_props:
        missing["properties"] = miss_props

    miss_links = [
        f"{rl.get('name') or rl.get('api_name')}"
        for rl in iface["required_links"]
        if isinstance(rl, dict) and (rl.get("api_name") or "") and rl["api_name"] not in l_names
        and (rl.get("name") or "") not in l_names
    ]
    if miss_links:
        missing["links"] = miss_links

    miss_acts = [
        f"{ra.get('name') or ra.get('code')}"
        for ra in iface["required_actions"]
        if isinstance(ra, dict) and (ra.get("code") or "") and ra["code"] not in a_codes
    ]
    if miss_acts:
        missing["actions"] = miss_acts

    return {"ok": not missing, "missing": missing, "interface": iface_code,
            "object_code": object_code}


async def check_all_interface_impls() -> list[dict]:
    """所有接口实现的合规检查（改完接口后看看谁会掉队）。"""
    out = []
    for iface in await list_interfaces():
        for oc in iface["implementations"]:
            chk = await check_interface_impl(iface["code"], oc)
            if not chk["ok"]:
                out.append({"interface": iface["code"], "interface_name": iface["name"],
                            "object_code": oc, "missing": chk["missing"]})
    return out


async def delete_interface(if_id: int) -> dict:
    row = (await _exec("SELECT code FROM ai_ont_interface WHERE id=:i AND is_deleted=false",
                       {"i": int(if_id)})).fetchone()
    if not row:
        return {"ok": False, "msg": "接口不存在"}
    impls = (await _exec("SELECT count(*) FROM ai_ont_interface_impl WHERE interface_code=:c",
                         {"c": row[0]})).scalar() or 0
    if impls:
        return {"ok": False, "msg": f"仍有 {impls} 个对象类型实现它，请先解除实现"}
    await _exec_write("UPDATE ai_ont_interface SET is_deleted=true WHERE id=:i", {"i": int(if_id)})
    return {"ok": True, "msg": "已删除"}


# ---------------------------------------------------------------------------
# 派生属性（源类型 = 关联对象，经 link 链 + 聚合）
# ---------------------------------------------------------------------------
async def validate_derived(prop: dict) -> list[str]:
    """校验派生属性配置，返回错误列表。

    官方限制：**派生属性不能依赖另一个派生属性**。
    """
    errs: list[str] = []
    d = prop.get("derived") or {}
    if not d:
        return ["派生属性必须配置 derived（源对象 / 关系链 / 聚合）"]
    src = (d.get("source_object") or "").strip()
    if not src:
        errs.append("缺少源对象类型（source_object）")
    elif not (await _exec("SELECT 1 FROM ai_ont_object WHERE code=:c AND is_deleted=false",
                          {"c": src})).fetchone():
        errs.append(f"源对象类型 {src} 不存在")
    agg = (d.get("aggregation") or "").strip()
    if agg not in _AGG_VALUES:
        errs.append(f"聚合方式非法：{agg}（可用：{'、'.join(sorted(_AGG_VALUES))}）")
    path = d.get("link_path") or []
    if not isinstance(path, list) or not path:
        errs.append("缺少关系链（link_path）")
    elif len(path) > DERIVED_MAX_HOPS:
        errs.append(f"关系链最多 {DERIVED_MAX_HOPS} 层，当前 {len(path)} 层")
    else:
        for lid in path:
            lk = next((x for x in await list_links() if x["id"] == int(lid or 0)), None)
            if not lk:
                errs.append(f"关系链里的关系 #{lid} 不存在")
    lim = d.get("limit", DERIVED_DEFAULT_LIMIT)
    try:
        lim_i = int(lim)
    except (TypeError, ValueError):
        lim_i = DERIVED_DEFAULT_LIMIT
    if lim_i < 1 or lim_i > DERIVED_MAX_LIMIT:
        errs.append(f"collection limit 必须在 1–{DERIVED_MAX_LIMIT} 之间，当前 {lim_i}")

    # 关键限制：聚合用的属性不能是派生属性
    field = (d.get("property") or "").strip()
    if field:
        target_props = await list_properties(src)
        target = next((p for p in target_props if p["code"] == field), None)
        if not target:
            errs.append(f"源对象 {src} 上没有属性 {field}")
        elif (target.get("type_class") or "") == "derived":
            errs.append(f"派生属性不能依赖另一个派生属性（{field} 本身是派生属性）")
    elif agg not in ("count",):
        errs.append(f"聚合方式 {agg} 需要指定要聚合的属性（property）")
    return errs


async def compute_derived(object_code: str, key: str, prop_code: str,
                          limit: int | None = None) -> dict:
    """实际计算一个派生属性的值：沿关系链取关联实例，再按聚合方式汇总。"""
    props = await list_properties(object_code)
    prop = next((p for p in props if p["code"] == prop_code), None)
    if not prop or (prop.get("type_class") or "") != "derived":
        return {"ok": False, "msg": f"{prop_code} 不是派生属性"}
    d = prop.get("derived") or {}
    path = d.get("link_path") or []
    agg = d.get("aggregation") or "count"
    field = d.get("property") or ""
    cap = int(limit or d.get("limit") or DERIVED_DEFAULT_LIMIT)
    cap = max(1, min(cap, DERIVED_MAX_LIMIT))

    cur_code, cur_key = object_code, str(key)
    collected: list[dict] = []
    for i, lid in enumerate(path):
        piv = await instance_pivot(cur_code, cur_key, int(lid), limit=cap * 5)
        if not piv.get("ok"):
            return {"ok": False, "msg": piv.get("msg") or "关系链遍历失败", "at_hop": i + 1}
        items = piv.get("items") or []
        if i == len(path) - 1:
            collected = items[:cap]
        elif items:
            cur_code = piv["other_object"]
            cur_key = items[0]["key"]
        else:
            collected = []
            break

    vals = [it["props"].get(field) for it in collected] if field else []
    if agg == "count":
        val: Any = len(collected)
    else:
        nums = []
        for v in vals:
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                continue
        if agg == "sum":
            val = sum(nums) if nums else None
        elif agg == "avg":
            val = (sum(nums) / len(nums)) if nums else None
        elif agg == "min":
            val = min(nums) if nums else None
        elif agg == "max":
            val = max(nums) if nums else None
        elif agg == "first":
            val = vals[0] if vals else None
        elif agg == "last":
            val = vals[-1] if vals else None
        elif agg == "collect_list":
            val = vals
        elif agg == "collect_set":
            seen, uniq = set(), []
            for v in vals:
                if v not in seen:
                    seen.add(v)
                    uniq.append(v)
            val = uniq
        else:
            val = None
    return {"ok": True, "property": prop_code, "aggregation": agg, "field": field,
            "hops": len(path), "matched": len(collected), "limit": cap, "value": val}


async def derived_issues() -> list[dict]:
    """全量扫描派生属性的配置问题（供健康检查使用）。"""
    out = []
    for p in await list_properties():
        if (p.get("type_class") or "") != "derived":
            continue
        errs = await validate_derived(p)
        if errs:
            out.append({"object_code": p["object_code"], "code": p["code"],
                        "name": p["name"], "errors": errs})
    return out


# ---------------------------------------------------------------------------
# 引用检查（删除任何类型前先看谁在用）
# ---------------------------------------------------------------------------
async def reference_check(kind: str, code: str) -> dict:
    """通用引用检查：返回引用方列表，供删除前拦截。"""
    refs: list[dict] = []
    if kind == "value_type":
        refs = await value_type_refs(code)
    elif kind == "shared_property":
        refs = await shared_property_refs(code)
    elif kind == "interface":
        r = await _exec("SELECT object_code FROM ai_ont_interface_impl WHERE interface_code=:c",
                        {"c": code})
        refs = [{"kind": "对象类型", "where": x[0], "name": await _object_name(x[0])}
                for x in r.fetchall()]
    elif kind == "group":
        g = (await _exec("SELECT id FROM ai_ont_group WHERE code=:c AND is_deleted=false",
                         {"c": code})).fetchone()
        if g:
            r = await _exec("SELECT object_code FROM ai_ont_group_member WHERE group_id=:g",
                            {"g": g[0]})
            refs = [{"kind": "组成员", "where": x[0], "name": await _object_name(x[0])}
                    for x in r.fetchall()]
    return {"kind": kind, "code": code, "count": len(refs), "refs": refs}


# ---------------------------------------------------------------------------
# 本体对象定义版本：快照 + 列表 + 回滚（本体定义同资产一样可版本化）
# ---------------------------------------------------------------------------
async def _is_superuser(user_id) -> bool:
    """判断用户是否超管（用于本体发布/回滚等高危操作校验）。"""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = 0
    if not uid:
        return False
    try:
        r = await _exec("SELECT is_superuser FROM sys_user WHERE id=:id AND is_deleted=false", {"id": uid})
        row = r.fetchone()
        return bool(row and row[0])
    except Exception:  # noqa: BLE001
        return False


async def _do_publish(object_code: str) -> dict:
    """真正快照发布对象定义到新版本 + 写发布留痕。"""
    obj = await object_full(object_code)
    if not obj.get("ok"):
        return {"ok": False, "msg": "对象不存在"}
    snapshot = {
        "object": {k: obj[k] for k in ("code", "name", "icon", "key_prop", "name_prop", "description")},
        "properties": obj["properties"], "links": obj["links"],
        "actions": obj["actions"], "functions": await list_functions(object_code),
    }
    async with async_db_session() as db:
        from sqlalchemy import text as _t
        n = (await db.execute(_t(
            "SELECT coalesce(max(version),0) FROM ai_ont_version WHERE object_code=:c AND is_deleted=false"),
            {"c": object_code})).scalar() or 0
        n += 1
    import json as _json
    r = await _exec_write("INSERT INTO ai_ont_version(object_code,version,snapshot) VALUES (:c,:v,:s) RETURNING id",
                          {"c": object_code, "v": n, "s": _json.dumps(snapshot, ensure_ascii=False)})
    await _log_change(object_code, "version", "publish", f"发布版本 v{n}")
    return {"ok": True, "id": r.scalar(), "version": n}


async def publish_version(object_code: str, operator: int = 0) -> dict:
    """发布本体对象版本：超管直接发布；非超管 → 落待审批，超管批准后真正发布。"""
    operator = int(operator or 0)
    if operator and not await _is_superuser(operator):
        # 非超管：写待审批留痕，返回审批单
        import json as _json
        detail = _json.dumps({"action": "publish", "object_code": object_code, "operator": operator})
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "INSERT INTO ai_ont_change_log(object_code,kind,action,detail,created_id) "
                "VALUES (:o,'version','version_pending',:d,0) RETURNING id"),
                {"o": object_code, "d": detail})
            cid = res.scalar()
        return {"ok": False, "needs_approval": True, "pending_id": int(cid or 0),
                "msg": "发布需超管审批，已生成审批单"}
    return await _do_publish(object_code)


async def list_version_pending(limit: int = 50) -> list[dict]:
    """待审批的本体发布单（changelog action='version_pending'）。"""
    import json as _json
    r = await _exec("SELECT id,object_code,detail,created_time FROM ai_ont_change_log "
                    "WHERE action='version_pending' AND is_deleted=false ORDER BY id DESC LIMIT :n", {"n": limit})
    rows = r.fetchall()
    out = []
    for x in rows:
        detail = x[2]
        try:
            d = _json.loads(detail) if isinstance(detail, str) else (detail or {})
        except Exception:  # noqa: BLE001
            d = {}
        out.append({"id": x[0], "object_code": x[1], "detail": d, "created_time": str(x[3]) if x[3] else ""})
    return out


async def approve_version_publish(pending_id: int, operator: int = 0) -> dict:
    """超管批准本体发布：真正发布 + 更新审批单为 approved。"""
    operator = int(operator or 0)
    if operator and not await _is_superuser(operator):
        return {"ok": False, "msg": "仅超管可批准本体发布"}
    rv = (await _exec("SELECT object_code FROM ai_ont_change_log WHERE id=:i AND action='version_pending' AND is_deleted=false",
                      {"i": pending_id})).fetchone()
    if not rv:
        return {"ok": False, "msg": "审批单不存在或已处理"}
    code = rv[0]
    res = await _do_publish(code)
    await _exec_write("UPDATE ai_ont_change_log SET action='version_approved' WHERE id=:i", {"i": pending_id})
    return {"ok": res.get("ok", False), "version": res.get("version"), "msg": res.get("msg", "已批准发布")}


async def version_diff(version_id: int) -> dict:
    """版本对比：某版本快照的属性 vs 当前定义，返回 新增/删除/变更 属性。"""
    import json as _json
    rv = (await _exec("SELECT object_code,snapshot FROM ai_ont_version WHERE id=:id AND is_deleted=false",
                      {"id": version_id})).fetchone()
    if not rv:
        return {"ok": False, "msg": "版本不存在"}
    code, snap_raw = rv[0], rv[1]
    snap = snap_raw if isinstance(snap_raw, dict) else _json.loads(snap_raw)
    cur = await object_full(code)
    cur_props = {p["code"]: p for p in cur.get("properties", [])}
    old_props = {p["code"]: p for p in snap.get("properties", [])}
    added = [c for c in cur_props if c not in old_props]
    removed = [c for c in old_props if c not in cur_props]
    changed = []
    for c in old_props:
        if c in cur_props:
            o, n = old_props[c], cur_props[c]
            if (o.get("prop_type") != n.get("prop_type")) or (bool(o.get("sensitive")) != bool(n.get("sensitive"))):
                changed.append(c)
    return {"ok": True, "object_code": code, "added": added, "removed": removed, "changed": changed}


async def list_versions(object_code: str | None = None) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,object_code,version,created_time FROM ai_ont_version "
                        "WHERE object_code=:c AND is_deleted=false ORDER BY version DESC", {"c": object_code})
    else:
        r = await _exec("SELECT id,object_code,version,created_time FROM ai_ont_version "
                        "WHERE is_deleted=false ORDER BY id DESC")
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "version": x[2], "created_time": str(x[3]) if x[3] else ""} for x in rows]


async def rollback_version(version_id: int) -> dict:
    """把本体定义回滚到指定版本快照。"""
    import json as _json
    rv = (await _exec("SELECT object_code,snapshot FROM ai_ont_version WHERE id=:id AND is_deleted=false",
                      {"id": version_id})).fetchone()
    if not rv:
        return {"ok": False, "msg": "版本不存在"}
    code, snap_raw = rv[0], rv[1]
    snap = snap_raw if isinstance(snap_raw, dict) else _json.loads(snap_raw)
    ob = snap.get("object") or {}
    # 恢复对象主字段
    await _exec_write("UPDATE ai_ont_object SET name=:n, icon=:i, key_prop=:k, name_prop=:np, description=:d "
                      "WHERE code=:c", {"n": ob.get("name", code), "i": ob.get("icon", "el-icon-Box"),
                                        "k": ob.get("key_prop", "id"), "np": ob.get("name_prop", "name"),
                                        "d": ob.get("description", ""), "c": code})
    # 清空并重建 属性/Link/Action/函数
    await _exec_write("UPDATE ai_ont_property SET is_deleted=true WHERE object_code=:c", {"c": code})
    await _exec_write("UPDATE ai_ont_link SET is_deleted=true WHERE source_object=:c OR target_object=:c", {"c": code})
    await _exec_write("UPDATE ai_ont_action SET is_deleted=true WHERE object_code=:c", {"c": code})
    await _exec_write("UPDATE ai_ont_function SET is_deleted=true WHERE object_code=:c", {"c": code})
    for p in snap.get("properties", []):
        await upsert_property({"object_code": code, "name": p.get("name"), "code": p.get("code"),
                               "prop_type": p.get("prop_type", "string"), "required": p.get("required"),
                               "unique_col": p.get("unique_col"), "sensitive": p.get("sensitive"),
                               "source_col": p.get("source_col", ""), "options": p.get("options", []),
                               "roles": p.get("roles", []), "description": p.get("description", "")})
    for lk in snap.get("links", []):
        await upsert_link({"source_object": lk.get("source_object"), "target_object": lk.get("target_object"),
                           "name": lk.get("name"), "card": lk.get("card", "many_to_one"),
                           "source_field": lk.get("source_field", ""), "target_field": lk.get("target_field", ""),
                           "description": lk.get("description", "")})
    for a in snap.get("actions", []):
        await upsert_action({"object_code": code, "name": a.get("name"), "code": a.get("code"),
                             "input_schema": a.get("input_schema", []), "white_fields": a.get("white_fields", []),
                             "approval": a.get("approval"), "target_table": a.get("target_table", ""),
                             "method": a.get("method", "update"), "description": a.get("description", "")})
    for f in snap.get("functions", []):
        await upsert_function({"object_code": code, "name": f.get("name"), "code": f.get("code"),
                               "expr": f.get("expr", ""), "description": f.get("description", "")})
    await _log_change(code, "version", "rollback", f"回滚到版本 {rv[2] if len(rv) > 2 else ''}")
    return {"ok": True, "msg": f"已回滚到版本快照 {snap.get('object', {}).get('name', code)}"}


# ---------------------------------------------------------------------------
# 本体计算函数（Palantir Functions）：对象上的可复用计算，被问数/AIP 复用
# ---------------------------------------------------------------------------
_FN_COLS = ("SELECT id,object_code,name,code,expr,description,parameters,"
            "COALESCE(tool_description,''),COALESCE(kind,'expression'),outputs,config "
            "FROM ai_ont_function ")


async def list_functions(object_code: str | None = None, owner_id: int | None = None) -> list[dict]:
    if object_code:
        r = await _exec(_FN_COLS + "WHERE object_code=:c AND is_deleted=false ORDER BY id",
                        {"c": object_code})
    else:
        r = await _exec(_FN_COLS + "WHERE is_deleted=false ORDER BY id")
    rows = r.fetchall()
    out = [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3],
            "expr": x[4] or "", "description": x[5] or "",
            # 入参声明：让函数从「纯算术表达式」升级为可向 Agent 声明入参的能力
            "parameters": _json_list(x[6]),
            "tool_description": x[7] or "",
            # P2：函数形态与出参
            "kind": x[8] or "expression", "outputs": _json_list(x[9]),
            "config": _json_dict(x[10])} for x in rows]
    out = await wip_overlay(owner_id, "function", out, "id", "code")
    if object_code:
        out = [f for f in out if f.get("object_code") == object_code]
    return out


async def upsert_function(data: dict, actor_id: int | None = None) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="函数编码/对象编码必填")
    kind = str(data.get("kind") or "expression")
    # 函数定义在保存前先校验（未知变量 / 未知内置函数 / 聚合配置 / URL 等）
    errs = _fe.validate_function({**data, "kind": kind})
    if errs:
        raise CustomException(msg="函数定义有误：" + "；".join(errs))
    common = {
        "n": data.get("name", code), "e": data.get("expr", ""),
        "d": data.get("description", ""),
        "pm": json.dumps(data.get("parameters") or [], ensure_ascii=False),
        "td": data.get("tool_description", ""),
        "k": kind,
        "ou": json.dumps(data.get("outputs") or [], ensure_ascii=False),
        "cf": json.dumps(data.get("config") or {}, ensure_ascii=False),
    }
    if data.get("id"):
        await _exec_write(
            "UPDATE ai_ont_function SET name=:n, expr=:e, description=:d, parameters=:pm, "
            "tool_description=:td, kind=:k, outputs=:ou, config=:cf WHERE id=:id",
            {**common, "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write(
        "INSERT INTO ai_ont_function(object_code,name,code,expr,description,parameters,"
        "tool_description,kind,outputs,config) "
        "VALUES (:oc,:n,:c,:e,:d,:pm,:td,:k,:ou,:cf) RETURNING id",
        {**common, "oc": obj, "c": code})
    return {"id": r.scalar()}


async def run_ontology_function(code: str, args: dict, object_key: str = "",
                                user_id: int | None = None, user_name: str = "") -> dict:
    """执行本体函数（四种形态统一入口）。"""
    fn = next((f for f in await list_functions(None) if f.get("code") == code), None)
    if not fn:
        return {"ok": False, "msg": f"本体函数 {code} 不存在"}
    ctx = _fe.FunctionContext(
        object_code=fn.get("object_code") or "",
        object_key=str(object_key or ""),
        user_id=int(user_id or 0),
        user_name=user_name or "",
    )
    r = await _fe.run_function(
        fn, args, ctx,
        object_loader=_load_object_props,
        aggregate_runner=_run_function_aggregate,
        model_runner=_run_function_model,
    )
    r["code"] = code
    r["name"] = fn.get("name")
    r["kind"] = fn.get("kind") or "expression"
    if r.get("ok"):
        r["msg"] = f"函数 {fn.get('name') or code} 执行完成"
    return r


async def _load_object_props(object_code: str, object_key: str) -> dict:
    """给「对象属性」类入参加载实例属性。"""
    inst = await instance_get(object_code, object_key)
    return (inst.get("props") or {}) if inst.get("ok") else {}


async def _run_function_aggregate(cfg: dict, values: dict) -> Any:
    """函数的关联聚合形态：沿关系链聚合（复用派生属性的逻辑）。"""
    path = cfg.get("link_path") or []
    agg = str(cfg.get("aggregation") or "count")
    field = str(cfg.get("property") or "")
    cap = max(1, min(int(cfg.get("limit") or 10), 100))
    src = str(cfg.get("source_object") or "")
    # 起点：显式传入的 key，或对象上下文
    start_code = str(cfg.get("from_object") or "")
    start_key = str(values.get("object_key") or values.get("__key") or "")
    if not start_code or not start_key:
        return None
    cur_code, cur_key = start_code, start_key
    collected: list[dict] = []
    for i, lid in enumerate(path):
        piv = await instance_pivot(cur_code, cur_key, int(lid), limit=cap * 5)
        if not piv.get("ok"):
            return None
        items = piv.get("items") or []
        if i == len(path) - 1:
            collected = items[:cap]
        elif items:
            cur_code, cur_key = piv["other_object"], items[0]["key"]
        else:
            collected = []
            break
    vals = [it["props"].get(field) for it in collected] if field else []
    if agg == "count":
        return len(collected)
    nums = []
    for v in vals:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if agg == "sum":
        return sum(nums) if nums else None
    if agg == "avg":
        return (sum(nums) / len(nums)) if nums else None
    if agg == "min":
        return min(nums) if nums else None
    if agg == "max":
        return max(nums) if nums else None
    if agg == "first":
        return vals[0] if vals else None
    if agg == "last":
        return vals[-1] if vals else None
    if agg == "collect_list":
        return vals
    if agg == "collect_set":
        seen, uniq = set(), []
        for v in vals:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        return uniq
    void_src = src  # 保留字段用于可读性
    return {"_unused": void_src} if False else None


async def _run_function_model(cfg: dict, values: dict) -> str:
    """函数的模型调用形态：走平台已登记的模型。"""
    prompt = _fe.interp(str(cfg.get("prompt") or ""), values)
    system = _fe.interp(str(cfg.get("system") or ""), values)
    model_id = cfg.get("model_id")
    return await call_registered_model(int(model_id) if model_id else None, system, prompt,
                                       float(cfg.get("temperature") or 0.2))


async def call_registered_model(model_id: int | None, system: str, prompt: str,
                                temperature: float = 0.2) -> str:
    """调用平台登记的模型（与问数模块同一套运行时解析与请求头）。

    官方 functions-on-models 的等价物：把模型当成函数的一个执行后端。
    """
    from app.plugin.module_ai.models.service import AiModelService, build_headers

    runtime = await AiModelService.get_runtime_model("chat", model_id) \
        or await AiModelService.get_runtime_model()
    if not runtime:
        raise CustomException(msg="未配置可用的大模型，请在 AI 管理 → 模型配置 中添加并启用")
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=runtime["base_url"], api_key=runtime["api_key"] or "sk-none",
            default_headers=build_headers(runtime["base_url"], runtime.get("extra_headers"),
                                          "aistation-ontfn"),
        )
    except Exception as e:  # noqa: BLE001
        raise CustomException(msg=f"大模型客户端不可用：{str(e)[:120]}") from e
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    try:
        resp = await client.chat.completions.create(
            model=runtime["model"], messages=msgs,
            temperature=max(0.0, min(float(temperature or 0.2), 2.0)),
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        raise CustomException(msg=f"模型调用失败：{(str(e) or type(e).__name__)[:140]}") from e


# ---------------------------------------------------------------------------
# 依赖：某对象类型被谁引用（供对象类型 Overview 的 Dependents 分区）
# ---------------------------------------------------------------------------
async def object_dependents(code: str) -> dict:
    """统计某对象类型的引用方：本体内部（关系/动作/函数）+ 外部（智能体）。

    智能体侧：``ai_agents.capabilities`` 同时承载功能标志与本体能力编码，
    这里只取与本体函数/动作编码相交的部分作为真实依赖。
    """
    await _ensure_domain_schema()
    funcs = await list_functions(code)
    acts = await list_actions(code)
    rels = await list_links(code)
    fn_codes = {f["code"] for f in funcs}
    act_codes = {a["code"] for a in acts}
    ont_codes = fn_codes | act_codes

    agents: list[dict] = []
    if ont_codes:
        try:
            rows = (await _exec(
                "SELECT id,agent_name,capabilities FROM ai_agents WHERE is_deleted=false")).fetchall()
            for r in rows:
                caps = _json_list(r[2])
                hit = sorted({str(c) for c in caps if str(c) in ont_codes})
                if hit:
                    agents.append({"id": r[0], "name": r[1] or "", "matched": hit})
        except Exception:  # noqa: BLE001
            agents = []

    return {
        "object_code": code,
        "agents": agents,
        "functions": [{"code": f["code"], "name": f["name"]} for f in funcs],
        "actions": [{"code": a["code"], "name": a["name"]} for a in acts],
        "links": [
            {
                "id": lk["id"],
                "name": lk["name"],
                "other": lk["target_object"] if lk["source_object"] == code else lk["source_object"],
            }
            for lk in rels
        ],
        "total": len(agents) + len(funcs) + len(acts) + len(rels),
    }


# ---------------------------------------------------------------------------
# 本体能力（Palantir：能力可挂在本体上，Agent 从本体装配能力）
# ---------------------------------------------------------------------------
_CAP_ONTOLOGY_TYPES = {"function", "action", "grounding"}
_CAP_TOOL_TYPES = {"query", "governance"}


def _cap_meta(t: str) -> tuple[str, str]:
    """能力 type → (source, kind)。source: ontology/platform；kind: tool/component。"""
    t = (t or "generic").lower()
    if t in _CAP_ONTOLOGY_TYPES:
        return "ontology", "tool"
    if t in _CAP_TOOL_TYPES:
        return "platform", "tool"
    return "platform", "component"


async def list_capabilities() -> list[dict]:
    r = await _exec("SELECT id,code,name,type,description,enabled FROM ai_ont_capability "
                    "WHERE is_deleted=false ORDER BY id DESC")
    rows = r.fetchall()
    out = []
    for x in rows:
        source, kind = _cap_meta(x[3])
        out.append({"id": x[0], "code": x[1], "name": x[2], "type": x[3],
                    "description": x[4] or "", "enabled": bool(x[5]),
                    "source": source, "kind": kind})
    return out


async def upsert_capability(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="能力编码必填")
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_capability SET name=:n, type=:t, description=:d, enabled=:e WHERE id=:id",
                          {"n": data.get("name", code), "t": data.get("type", "generic"),
                           "d": data.get("description", ""), "e": bool(data.get("enabled", True)), "id": data["id"]})
        return {"id": data["id"]}
    try:
        r = await _exec_write("INSERT INTO ai_ont_capability(code,name,type,description,enabled) "
                              "VALUES (:c,:n,:t,:d,:e) RETURNING id",
                              {"c": code, "n": data.get("name", code), "t": data.get("type", "generic"),
                               "d": data.get("description", ""), "e": bool(data.get("enabled", True))})
        return {"id": r.scalar()}
    except Exception as e:  # noqa: BLE001
        if "duplicate" in str(e).lower():
            raise CustomException(msg=f"能力编码 {code} 已存在")
        raise CustomException(msg=f"保存失败：{str(e)[:80]}")


# ---------------------------------------------------------------------------
# 本体驱动表：把对象 + 属性物化成真实表（Palantir「本体驱动数据」）
# ---------------------------------------------------------------------------
async def materialize_object(code: str) -> dict:
    obj = (await _exec("SELECT code,name FROM ai_ont_object WHERE code=:c AND is_deleted=false", {"c": code})).fetchone()
    if not obj:
        return {"ok": False, "msg": f"对象 {code} 不存在"}
    props = await list_properties(code)
    if not props:
        return {"ok": False, "msg": "对象没有属性，无法物化"}
    table = f"ont_{code}"
    col_map = []
    cols_ddl = []
    for p in props:
        t = p["prop_type"]
        col_map.append({"prop": p["code"], "col": p["code"], "type": t})
        pg = "TEXT"
        if t == "number":
            pg = "NUMERIC"
        elif t == "date":
            pg = "TIMESTAMP"
        elif t == "boolean":
            pg = "BOOLEAN"
        elif t == "object_ref" or t == "enum":
            pg = "TEXT"
        cols_ddl.append(f'"{p["code"]}" {pg}')
    ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (id BIGSERIAL PRIMARY KEY, {", ".join(cols_ddl)})'
    async with async_db_session() as db:
        await db.execute(_t(ddl))
    return {"ok": True, "table": table, "columns": [c["col"] for c in col_map],
            "msg": f"对象 {code} 已物化为表 {table}"}


async def object_full(code: str, owner_id: int | None = None) -> dict:
    obj = (await _exec("SELECT code,name,icon,key_prop,name_prop,description FROM ai_ont_object "
                       "WHERE code=:c AND is_deleted=false", {"c": code})).fetchone()
    if not obj:
        # 可能只存在于工作副本里（新建未保存）
        ops = await list_wip(int(owner_id or 0)) if owner_id else []
        hit = next((o for o in ops
                    if o["kind"] == "object" and o["action"] == "create"
                    and (o.get("data") or {}).get("code") == code), None)
        if not hit:
            return {"ok": False, "msg": "对象不存在"}
        d = hit["data"]
        return {"ok": True, "code": d.get("code"), "name": d.get("name"),
                "icon": d.get("icon"), "key_prop": d.get("key_prop"),
                "name_prop": d.get("name_prop"), "description": d.get("description", ""),
                "properties": await list_properties(code, owner_id),
                "links": await list_links(code, owner_id),
                "actions": await list_actions(code, owner_id)}
    return {"ok": True, "code": obj[0], "name": obj[1], "icon": obj[2], "key_prop": obj[3], "name_prop": obj[4],
            "description": obj[5], "properties": await list_properties(code, owner_id),
            "links": await list_links(code, owner_id), "actions": await list_actions(code, owner_id)}


# ---------------------------------------------------------------------------
# 本体深度建模分析（连通性 / 中心度 / 主键缺失 / 关系完备性）
# ---------------------------------------------------------------------------
async def analyze_ontology() -> dict:
    """对本体元模型做关系图分析并给出建模建议（纯读现有模型，零迁移）。"""
    from collections import Counter, defaultdict

    objs = (await _exec("SELECT code,name FROM ai_ont_object WHERE is_deleted=false")).fetchall()
    props = (await _exec("SELECT object_code,required,unique_col FROM ai_ont_property WHERE is_deleted=false")).fetchall()
    links = (await _exec("SELECT source_object,target_object,card FROM ai_ont_link WHERE is_deleted=false")).fetchall()
    acts = (await _exec("SELECT object_code FROM ai_ont_action WHERE is_deleted=false")).fetchall()

    obj_codes = [r[0] for r in objs]
    obj_name = {r[0]: r[1] for r in objs}
    degree = defaultdict(lambda: {"in": 0, "out": 0})
    for s, t, _c in links:
        if s:
            degree[s]["out"] += 1
        if t:
            degree[t]["in"] += 1
    pk_obj = {p[0] for p in props if p[1] or p[2]}          # required/unique 视为主键候选
    no_pk = [c for c in obj_codes if c not in pk_obj]
    isolated = [c for c in obj_codes if degree[c]["in"] == 0 and degree[c]["out"] == 0]
    card_dist = Counter((lk[2] or "many_to_one") for lk in links)

    adj = defaultdict(set)
    for s, t, _c in links:
        adj[s].add(t)
        adj[t].add(s)
    seen, comps = set(), []
    for c in obj_codes:
        if c in seen:
            continue
        stack, comp = [c], []
        seen.add(c)
        while stack:
            n = stack.pop()
            comp.append(n)
            for m in adj[n]:
                if m in obj_codes and m not in seen:
                    seen.add(m)
                    stack.append(m)
        comps.append(comp)

    centrality = sorted(obj_codes, key=lambda c: degree[c]["in"] + degree[c]["out"], reverse=True)
    top = [{"code": c, "name": obj_name.get(c, c),
            "degree": degree[c]["in"] + degree[c]["out"],
            "in": degree[c]["in"], "out": degree[c]["out"]} for c in centrality[:8]]

    recs = []
    if no_pk:
        recs.append(f"{len(no_pk)} 个对象缺少主键/必填属性，建议补充唯一或必填属性")
    if isolated:
        recs.append(f"{len(isolated)} 个对象无任何关系，建议接入关系或标记为非业务对象")
    if len(comps) > 1:
        recs.append(f"关系图存在 {len(comps)} 个连通分量，建议打通孤立对象")
    if recs:
        recs.append("可对中心度高的对象优先定义动作与治理规则")
    else:
        recs.append("本体关系结构良好，无显著缺口")

    n_links = len(links)
    n_objs = len(obj_codes)
    return {
        "objects": n_objs, "properties": len(props), "links": n_links, "actions": len(acts),
        "isolated": len(isolated), "no_pk": len(no_pk), "components": len(comps),
        "density": round((2 * n_links / (n_objs * (n_objs - 1))), 4) if n_objs > 1 else 0,
        "card_dist": dict(card_dist),
        "top_central": top,
        "recommendations": recs,
        "nodes": [{"code": c, "name": obj_name.get(c, c),
                   "degree": degree[c]["in"] + degree[c]["out"],
                   "isolated": c in isolated} for c in obj_codes],
        "edges": [{"source": s, "target": t, "card": (c or "many_to_one")} for s, t, c in links],
    }
