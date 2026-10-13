# 数据源表/字段筛选 + 多本体 + 集成页重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为每个数据源提供通用筛选规则引擎，自动对表/字段打标（业务 vs 系统/审计），支持元数据标注（含枚举），从筛选后的表/字段导入为多套本体之一，并重构集成页 UI；用燃煤业务库跑通全流程。

**Architecture:** 后端在 `module_ai/query` 增加通用筛选规则引擎（`filtering.py`）+ 数据源规则配置 + 同步打标；`ai_query_assets`/`ai_query_asset_columns` 增加打标与枚举字段；本体 `ai_ont_object`/`ai_ont_property` 增加 `is_business`，导入函数支持指定 `domain_code`。前端重构 `module_ai/integration/index.vue`（左侧数据源改纵向列表、表/字段 tab 加筛选与元数据编辑）。

**Tech Stack:** FastAPI + SQLAlchemy（运行时建表）+ Vue3 + Element Plus + TypeScript + vitest / pytest。

**Spec:** `docs/superpowers/specs/2026-10-13-datasource-ontology-filter-design.md`

## Global Constraints
- 所有回复/注释/提交信息用中文；提交用 `fix(module): 中文描述`。
- 前端样式统一 Element Plus + `--el-*` 变量，禁止自造主题色；弹窗放根节点；删除类操作必须二次确认（ElMessageBox.confirm）。
- 本体 `ai_ont_*` 无 Alembic，改表走 `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`。
- 测试效率：日常只跑相关测试文件；纯逻辑测试可用 `PYTEST_NO_APP=1`。

## Review Focus
- 规则匹配对英文缩写表名（`FUEL_CB_COALBALANCE`）与大小写（`SYS_`/`sys_`）都要命中；测试用大小写混合样本。
- 审计字段集合缺省必须包含 `is_deleted/created_time/updated_time/created_id/updated_id/deleted_id/tenant_id/created_by/updated_by`；测试用这些精确名。
- `domain_code` 为空时导入对象保持未分组（`domain_code=''`），不影响既有"数据表本体"域；测试用空值与指定域各一例。
- 导入时 `is_business` 的正确赋值：系统表→对象 `is_business=false`，审计字段→属性 `is_business=false`，业务→`true`；测试用含系统表+审计字段的表。
- 前端"隐藏系统表/审计字段"筛选只影响显示，不改变已存标记；测试用含系统表数据的组件 state。

---
### Task 1: 通用筛选规则引擎

**Files:**
- Create: `backend/app/plugin/module_ai/query/filtering.py`
- Test: `backend/tests/test_query_filtering.py`

**Interfaces:**
- Produces:
  - `DEFAULT_FILTER_RULES: dict` — 缺省规则（前缀 SYS_/FUEL_/VIEW_/V_、关键词 _BAK/_temp/log/history、精确 alembic_version/apscheduler_jobs/__EFMigrationsHistory、审计字段名集合）。
  - `is_system_table(name: str, rules: dict | None = None) -> bool`
  - `is_audit_field(name: str, rules: dict | None = None) -> bool`

- [ ] **Step 1: 写失败测试** `backend/tests/test_query_filtering.py`

```python
from app.plugin.module_ai.query.filtering import is_system_table, is_audit_field, DEFAULT_FILTER_RULES

def test_system_table_by_prefix(): assert is_system_table("SYS_USER")
def test_system_table_case(): assert is_system_table("sys_user")
def test_system_table_by_keyword(): assert is_system_table("FUEL_CMCS_X_BAK")
def test_system_table_by_exact(): assert is_system_table("alembic_version")
def test_business_table(): assert not is_system_table("video_cameras")
def test_audit_field(): assert is_audit_field("created_time")
def test_business_field(): assert not is_audit_field("coal_amount")
```

- [ ] **Step 2: 运行确认失败** `backend/.venv/Scripts/python.exe -m pytest tests/test_query_filtering.py -q`（预期 ImportError）

- [ ] **Step 3: 实现 `filtering.py`**：`DEFAULT_FILTER_RULES` 常量 + `is_system_table`/`is_audit_field`，按前缀/关键词/精确/正则匹配（大小写不敏感）；`rules=None` 时用默认。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交** `git add backend/app/plugin/module_ai/query/filtering.py backend/tests/test_query_filtering.py && git commit -m "feat(query): 通用筛选规则引擎"`

---
### Task 2: 数据源规则配置字段（model + schema + 运行时建表列）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/model.py`（`AiQueryDatasourceModel`）
- Modify: `backend/app/plugin/module_ai/query/schema.py`（`QueryDatasourceUpsert`）
- Modify: `backend/app/plugin/module_ai/query/service.py`（建表/ALTER 增加 `filter_rules` 列）
- Test: `backend/tests/test_query_datasource_filter.py`

**Interfaces:**
- Consumes: `DEFAULT_FILTER_RULES`（Task 1）
- Produces: `AiQueryDatasourceModel.filter_rules: Mapped[dict | None]`（JSONB）；`QueryDatasourceUpsert.filter_rules: dict | None = None`；数据源 upsert 时若 `filter_rules` 为空则落 DEFAULT 规则。

- [ ] **Step 1: 写测试**：新建数据源带空 `filter_rules` 后，读出 `filter_rules == DEFAULT_FILTER_RULES`。
- [ ] **Step 2: 运行确认 FAIL**。
- [ ] **Step 3: 实现**：model 加 `filter_rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)`；schema 加字段；`service.py` 建表/ALTER 加 `filter_rules JSONB DEFAULT '{}'`；`upsert_datasource` 若 `filter_rules` 空则写 `DEFAULT_FILTER_RULES`。
- [ ] **Step 4: 运行确认 PASS**（该测试需应用，用正常 pytest）。
- [ ] **Step 5: 提交**。

---
### Task 3: 同步打标 + 资产/列打标与枚举字段

**Files:**
- Modify: `backend/app/plugin/module_ai/query/model.py`（`AiQueryAssetModel` 加 `is_system`；`AiQueryAssetColumnModel` 加 `is_audit`、`enum`）
- Modify: `backend/app/plugin/module_ai/query/service.py`（`sync_datasource_schema`、`sync_assets`、`list_ds_schema`、`list_asset_columns`、`upsert_asset_column`、建表/ALTER）
- Test: `backend/tests/test_query_schema_marking.py`

**Interfaces:**
- Consumes: `is_system_table`/`is_audit_field`（Task 1）；`filter_rules`（Task 2）
- Produces: `ai_query_assets.is_system: bool`；`ai_query_asset_columns.is_audit: bool`、`ai_query_asset_columns.enum: list`；`ai_query_schema.columns[]` 元素含 `is_audit`；`list_ds_schema` 每项含 `is_system`，每列含 `is_audit`。

- [ ] **Step 1: 写测试**：给定含 `SYS_XYZ` 表 + `created_time` 字段的 schema，`list_ds_schema` 返回该表 `is_system=true`、该列 `is_audit=true`。
- [ ] **Step 2: 运行确认 FAIL**。
- [ ] **Step 3: 实现**：模型/建表/ALTER 加列；`sync_datasource_schema` 写 `ai_query_schema.columns` 时给每个字段加 `is_audit`；`sync_assets` 写 `ai_query_assets` 时按规则算 `is_system`、写 `ai_query_asset_columns` 时算 `is_audit`；`list_ds_schema`/`list_asset_columns` 带出标记；`upsert_asset_column` 支持 `enum`。
- [ ] **Step 4: 运行确认 PASS**。
- [ ] **Step 5: 提交**。

---
### Task 4: 本体对象/属性 `is_business` + 导入支持目标域

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/service.py`（建表/ALTER `ai_ont_object.is_business`、`ai_ont_property.is_business`）
- Modify: `backend/app/plugin/module_ai/query/service.py`（`import_ds_table_as_ontology`、`import_ds_tables_as_ontology`、`_import_ont_table_core` 增加 `domain_code` 与 `is_business` 赋值）
- Test: `backend/tests/test_import_ds_ontology_domain.py`

**Interfaces:**
- Consumes: `is_system_table`/`is_audit_field`（Task 1）
- Produces: `import_ds_table_as_ontology(datasource_id: int, table: str, domain_code: str = "") -> dict`；`import_ds_tables_as_ontology(datasource_id, tables=None, include_technical=False, domain_code="") -> dict`；`_import_ont_table_core(datasource_id, table, cols, table_comment="", domain_code="") -> dict`。写入对象时 `domain_code=domain_code`、`is_business=not is_system_table(table)`；属性时 `is_business=not is_audit_field(col_name)`。

- [ ] **Step 1: 写测试**：用含 `SYS_` 表 + `created_time` 字段的表导入到 `domain_code="fuel_business"`，断言对象 `is_business=false` 且 `domain_code="fuel_business"`，审计字段属性 `is_business=false`，业务字段属性 `is_business=true`。
- [ ] **Step 2: 运行确认 FAIL**。
- [ ] **Step 3: 实现**：ontology 建表/ALTER 加 `is_business BOOLEAN DEFAULT true`；导入函数透传 `domain_code`、按规则赋值 `is_business`。
- [ ] **Step 4: 运行确认 PASS**。
- [ ] **Step 5: 提交**。

---
### Task 5: 后端接口串起来（controller + 批量导入目标域）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/controller.py`、`backend/app/plugin/module_ai/query/schema.py`
- Modify: `frontend/src/api/module_ai/query.ts`
- Test: 复用 Task 2-4 测试 + 手动 API 冒烟。

- [ ] **Step 1: 实现**：`/datasources/save` 支持 `filter_rules`；`/datasources/{id}/schema` 返回 `is_system`/`is_audit`；`/ontology/import-from-ds` 与 batch 支持 `domain_code` query 参数；前端 `query.ts` 对应函数加 `domain_code`/`filter_rules` 参数。
- [ ] **Step 2: 运行相关测试 + eslint/type-check**。
- [ ] **Step 3: 提交**。

---
### Task 6: 前端集成页重构（左侧列表 + 表/字段 tab 筛选与元数据）

**Files:**
- Modify: `frontend/src/views/module_ai/integration/index.vue`
- Modify: `frontend/src/api/module_ai/query.ts`
- Test: 前端 `vue-tsc`、eslint；浏览器截图核对。

- [ ] **Step 1: 左侧数据源改纵向列表**：仿本体左侧导航（图标+名称+类型/表数徽标，选中高亮，新增/编辑/删除/测试连接；删除二次确认）。移除现有 `el-table`。
- [ ] **Step 2: 「表与字段」tab 重构**：表清单加「只看业务表/隐藏系统表」开关 + 搜索；字段清单加「只看业务字段/隐藏审计字段」开关；元数据表单增加枚举/系统标记；均用 Element Plus 标准组件。
- [ ] **Step 3: 接入导入按钮**：支持选目标本体域（下拉取 `/ai/ontology/domains`），单表/批量导入带 `domain_code`；导入后提示。
- [ ] **Step 4: 验证**：`pnpm run type-check`、`pnpm run lint` 通过；浏览器截图确认风格与项目一致。
- [ ] **Step 5: 提交**。

---
### Task 7: 燃煤业务库全流程跑通（手动端到端验证）

**Files:** 无代码改动；验证+记录。

- [ ] **Step 1: 为 `ezdcs_pg`（燃煤业务库）配置/确认 `filter_rules`**（可直接用默认规则）。
- [ ] **Step 2: 重新同步** schema，确认表带 `is_system`、字段带 `is_audit`。
- [ ] **Step 3: 前端筛选**业务表/字段，标注关键表/字段元数据（中文名、业务场景、枚举、关联表/字段、敏感）。
- [ ] **Step 4: 建本体域** `fuel_business`（燃煤业务库）：调用 `/ai/ontology/domain/save`。
- [ ] **Step 5: 批量导入**筛选保留的表到 `fuel_business` 域；界面剔除系统表/审计字段。
- [ ] **Step 6: 跑 `enrich_ontology_semantics`** 回填中文名/枚举/外键关系。
- [ ] **Step 7: 本体页切到「燃煤业务库」域**，验证对象/属性/图谱正常；截图记录。
