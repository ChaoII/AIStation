"""影子表 DDL（从 service.py 拆出）：``_ensure_query_tables`` 逐条执行。"""
from __future__ import annotations

_QUERY_TABLES_SQL = (
    "CREATE TABLE IF NOT EXISTS ai_pipeline ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), source_connection VARCHAR(120), "
    "source_table VARCHAR(120), target_object VARCHAR(120), mappings JSONB DEFAULT '[]', "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "datasource VARCHAR(120), "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now())", "CREATE TABLE IF NOT EXISTS ai_pipeline_run ("
    "id BIGSERIAL PRIMARY KEY, pipeline_id BIGINT, status VARCHAR(20), message TEXT, "
    "ran_at TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false, rows INTEGER DEFAULT 0)",
    # ⚠️ 这是**问数/治理侧**的「数据域」（Data Domain：把数据表按业务主题归类，用于问数权限与治理）。
    # 它与本体页的 `ai_ont_domain`（**本体域**：本体对象的命名空间）是**两张完全不同的表**——
    # 互不可见、互不相通、不共享数据：治理面板里的「数据域」数量/内容 ≠ 本体页的「本体域」，
    # 界面上的区分见 GovernancePanel 的说明 tooltip 与本体页「本体域」侧栏标题。
    # 合并两张表会同时动权限模型与本体命名空间，属于数据迁移级改动，**不要顺手做**。
    #
    # ⚠️ 2026-11 核查确认：数据域**目前不参与问数**——既不进 prompt、也不进召回，
    # 更不参与权限（问数可查范围 = 资产白名单 `ai_query_assets.included` + ABAC 规则
    # `ai_access_rule.allowed_tables`）。它只用于治理页的归类与统计。
    # 界面文案已按此修正；若将来要接进召回/权限，改这里的同时记得同步那句文案。
    "CREATE TABLE IF NOT EXISTS ai_data_domain ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), code VARCHAR(60), description VARCHAR(255), "
    "tables JSONB DEFAULT '[]', members JSONB DEFAULT '[]', enabled BOOLEAN DEFAULT true, "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_workshop_app ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), object_table VARCHAR(120), "
    "view_type VARCHAR(20) DEFAULT 'table', columns JSONB DEFAULT '[]', "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "deleted_time TIMESTAMP, created_time TIMESTAMP DEFAULT now(), "
    "updated_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_access_rule ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), attribute VARCHAR(60) DEFAULT 'role', "
    "value VARCHAR(120), allowed_tables JSONB DEFAULT '[]', sensitive_ok BOOLEAN DEFAULT false, "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_delivery_proposition ("
    "id BIGSERIAL PRIMARY KEY, title VARCHAR(200), description TEXT, criteria TEXT, "
    "owner VARCHAR(100), step_diagnosis VARCHAR(12) DEFAULT 'todo', "
    "step_modeling VARCHAR(12) DEFAULT 'todo', step_assembly VARCHAR(12) DEFAULT 'todo', "
    "step_shadow VARCHAR(12) DEFAULT 'todo', step_handover VARCHAR(12) DEFAULT 'todo', "
    "gap JSONB DEFAULT '[]', delivery_assets JSONB DEFAULT '[]', "
    "status VARCHAR(20) DEFAULT 'open', is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now(), "
    "fde_translator VARCHAR(100) DEFAULT '', fde_data VARCHAR(100) DEFAULT '', "
    "fde_app VARCHAR(100) DEFAULT '', shadow_metric VARCHAR(120) DEFAULT '', "
    "shadow_golden VARCHAR(64) DEFAULT '', shadow_tolerance VARCHAR(32) DEFAULT '', "
    "shadow_result VARCHAR(32) DEFAULT '', shadow_actual VARCHAR(64) DEFAULT '', "
    "shadow_at TIMESTAMP)",
    # ⚠️ 与本体动作 `ai_ont_action` 是**两套**东西（2026-11 核对）：
    #   - 本表（ai_query_writeback）= 问数侧「表级写回」：直接 UPDATE 业务表某行、
    #     走 writable_cols 白名单 + 审批留痕（ai_query_writeback_log）；属历史实现，
    #     界面已标注「逐步下线」，定义在「数据与集成 → 治理 → 动作/写回」。
    #   - ai_ont_action = 本体对象上的动作：由对象页/决策中心/智能体工具
    #     （ont_action__<code>）调用，带字段白名单、规则校验、副作用与审批。
    #   **问数（NL2SQL）不会自动执行任何一方**；不要在问数链路上接 ai_ont_action。
    "CREATE TABLE IF NOT EXISTS ai_query_writeback ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), object_table VARCHAR(120), "
    "writable_cols JSONB DEFAULT '[]', validation TEXT, approve BOOLEAN DEFAULT true, "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now(), "
    "writable_by_role JSONB)",
    "CREATE TABLE IF NOT EXISTS ai_query_writeback_log ("
    "id BIGSERIAL PRIMARY KEY, action_name VARCHAR(120), object_table VARCHAR(120), "
    "object_key VARCHAR(120), params JSONB, operator VARCHAR(100), result VARCHAR(20), "
    "detail TEXT, created_time TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false)",
    "CREATE TABLE IF NOT EXISTS ai_dq_report ("
    "id BIGSERIAL PRIMARY KEY, table_name VARCHAR(120), alias VARCHAR(120), "
    "total INTEGER DEFAULT 0, score NUMERIC DEFAULT 0, completeness NUMERIC DEFAULT 0, "
    "uniqueness NUMERIC DEFAULT 0, freshness NUMERIC DEFAULT 0, issues JSONB DEFAULT '[]', "
    "checked_at TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false)",
)
