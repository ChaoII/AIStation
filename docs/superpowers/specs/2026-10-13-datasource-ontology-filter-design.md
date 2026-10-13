# 数据源表/字段筛选 · 元数据标注 · 多本体 · UI 重构 — 设计

- 日期：2026-10-13
- 模块：数据与集成（`module_ai/integration`）→ 智能问数（`module_ai/query`）+ 本体（`module_ai/ontology`）
- 状态：设计待评审

## 1. 背景与目标

用户在「数据与集成」中录入数据源（如燃煤业务库 `ezdcs_pg`，已同步 331 张表），需要对表与字段做筛选与元数据标注，并据此生成本体。当前存在：
- 系统表/审计字段无统一自动判定规则；
- 导入本体时会把审计字段一并导入为属性；
- 字段元数据缺少「枚举」；
- 集成页 UI（左侧数据源 table、表/字段 tab）观感差。

目标：为**每个数据源**提供独立的表/字段筛选规则，自动打标（业务 vs 系统/审计），支持元数据标注（含枚举），可从筛选后的表/字段**导入为多套本体之一**，并重构集成页 UI；用「燃煤业务库」数据源跑通全流程生成本体。

## 2. 现状（已具备 / 缺口）

### 已具备
- 数据源 CRUD + 连接测试 + `introspect_schema` 拉取表/字段（含 PG 中文注释），存 `ai_query_schema`。
- 表级元数据 `ai_query_assets`：`alias/domain/description/business_scenarios/included/object_enabled/object_key_col/object_name_col/object_icon`。
- 字段级元数据 `ai_query_asset_columns`：`description/business_scenarios/related_table/related_field/included/sensitive`。
- 表→`ai_ont_object`、字段→`ai_ont_property` 导入（`import_ds_table_as_ontology` / `_import_ont_table_core`），并物化建表 `ont_{table}`。
- 多套本体：`ai_ont_domain` + `ai_ont_object.domain_code`；`/ai/ontology/domain/*` 接口。
- 语义回填 `enrich_ontology_semantics`：补中文名、解析枚举（`prop_type='enum'` + `options`）、真实外键→`ai_ont_link`（排除审计字段）。

### 缺口
1. 无统一的「系统表 vs 业务表」自动判定（仅分散名单 `SYSTEM_ALLOWED_TABLES` / `_ONT_IMPORT_EXCLUDE`）。
2. 导入本体时审计字段（`is_deleted/created_id/updated_id/deleted_id/tenant_id/created_by/updated_by/created_time/updated_time/deleted_time`）会被导入为本体属性（仅 FK→Link 时排除）。
3. `ai_query_asset_columns` 无枚举字段。
4. 集成页仅用单表导入；批量导入接口后端已有但前端未用。

## 3. 设计

### 3.1 每个数据源独立的筛选规则（每源独立配置）
- `ai_query_datasources` 新增字段 `filter_rules JSONB`，结构：
  ```jsonc
  {
    "enabled": true,                    // 是否启用自动打标
    "system_table": {                   // 系统/技术表判定
      "prefixes": ["SYS_", "FUEL_", "VIEW_", "V_"],
      "keywords": ["_BAK", "_temp", "_bak", "log", "_log", "history", "_history"],
      "exact": ["alembic_version", "apscheduler_jobs", "__EFMigrationsHistory"],
      "regex": ""                        // 可选自定义正则（命中即系统表）
    },
    "audit_fields": [                    // 审计/技术字段判定（名称匹配）
      "is_deleted","deleted_time","created_time","updated_time","deleted_id",
      "created_id","updated_id","tenant_id","created_by","updated_by"
    ]
  }
  ```
- 无配置时用「缺省内置规则」（同上内置集合），每个源可覆盖。

### 3.2 表/字段打标与元数据
- `ai_query_assets` 新增 `is_system BOOLEAN DEFAULT false`（是否系统/技术表）。
- `ai_query_asset_columns` 新增 `is_audit BOOLEAN DEFAULT false`（是否审计/技术字段）、`enum JSONB DEFAULT '[]'`（枚举/选项）。
- 同步/重同步时（`sync_datasource_schema` / `sync_assets`）按该源 `filter_rules` 对表打 `is_system`、对字段打 `is_audit`；`ai_query_schema.columns` 每个元素增加 `is_audit` 标记。
- 字段元数据保留既有 `description/business_scenarios/related_table/related_field/included/sensitive`，新增 `enum`。
- 「是否业务对象」沿用 `ai_query_assets.object_enabled/object_key_col/object_name_col`。

### 3.3 多本体导入（复制到目标本体域）
- 新增目标域参数：导入函数支持 `domain_code`，把表导入为指定本体域的对象（`ai_ont_object.domain_code`）。
- **先全导再手动剔**：导入时**全量**导入（含系统表/审计字段），但：
  - `ai_ont_object` 新增 `is_business BOOLEAN DEFAULT true`：由系统表/技术表导入的对象置 `false`（导入时按 `is_system` 来源赋值）。
  - `ai_ont_property` 新增 `is_business BOOLEAN DEFAULT true`：由审计/技术字段导入的属性置 `false`（导入时按 `is_audit` 来源赋值）。
  - 界面提供筛选/动作：「只看业务对象/属性」开关、「一键剔除非业务对象 / 剔除审计属性」（实际删除），并支持逐项手动调整（如把某系统表改标为业务、或删除某个业务属性）。
- 导入后跑 `enrich_ontology_semantics`（补中文名/枚举/外键关系）。

### 3.4 UI 重构
- **左侧数据源**：由 `el-table` 改为**纵向列表**（仿「本体」左侧导航：条目含图标、名称、类型/表数徽标；选中高亮、可新增/编辑/删除/测试连接；空态友好）。
- **「表与字段」tab 重构**：
  - 表清单：搜索 + 「只看业务表 / 隐藏系统表」开关 + 表名/中文名/字段数/系统标记。
  - 选中表 → 表元数据表单（中文名、业务域、描述、业务场景、主键列、显示名列、是否业务对象、系统标记）+ 字段清单（搜索 + 「只看业务字段 / 隐藏审计字段」开关 + 字段中文名/类型/关联表/关联字段/枚举/纳入/敏感/审计标记），就地编辑保存。
  - 全部使用 Element Plus 标准组件与 `--el-*` 变量，样式对齐项目既有页面。

### 3.5 后端接口改动
- `POST /ai/query/datasources/save`：`QueryDatasourceUpsert` 增 `filter_rules`。
- `POST /ai/query/datasources/{id}/sync-schema`：按 `filter_rules` 打标（`is_system`/`is_audit`）。
- `GET /ai/query/datasources/{id}/schema`：返回含 `is_system`/字段 `is_audit`。
- `POST /ai/query/assets/save` / `POST /ai/query/assets/column/save`：支持 `is_system`/`is_audit`/`enum`。
- `POST /ai/query/ontology/import-from-ds`（单表）与 `/ontology/import-from-ds/batch`（批量）：支持 `domain_code` 目标域。
- 本体域：复用现有 `POST /ai/ontology/domain/save` 建域（本次建 `fuel_business` / 燃煤业务库）。

## 4. 全流程（燃煤业务库跑通）

1. 为数据源 `ezdcs_pg`（燃煤业务库）配置 `filter_rules`（或使用缺省内置规则）。
2. 重新同步 schema → 表打 `is_system`、字段打 `is_audit`。
3. 前端表清单筛选业务表、字段筛选业务字段。
4. 对关键业务表/字段标注元数据（中文名、业务场景、枚举、关联表/字段、是否纳入、是否敏感）。
5. 建本体域：`/ai/ontology/domain/save` → code=`fuel_business`、name=`燃煤业务库`。
6. 将筛选保留的表批量导入为 `fuel_business` 域对象/属性（届时可剔除系统表/审计字段）。
7. 跑 `enrich_ontology_semantics` 回填（中文名/枚举/外键关系）。
8. 在本体页切到 `燃煤业务库` 域查看图谱与对象/属性。

## 5. 测试

- 后端：`filter_rules` 打标单测（表名前缀/关键词/exact/regex、审计字段集合）；`import_ds_table_as_ontology` 带 `domain_code` 生成对象归属正确；`enum` 元数据保存/读取。
- 前端：`vue-tsc`、eslint。
- 端到端：燃煤业务库同步→筛选→标注→建域→导入→回填→图谱展示。

## 6. 验收标准

1. 每个数据源可独立配置表/字段筛选规则，同步后表带 `is_system`、字段带 `is_audit` 标记。
2. 集成页左侧为纵向列表（仿本体），「表与字段」tab 可「只看业务/隐藏系统或审计」筛选，元数据（含枚举）可就地编辑。
3. 能从数据源表/字段导入到一个**新本体域**（`fuel_business`），导入后在界面上可剔除系统表/审计字段；本体页该域内对象/属性/图谱正常。
4. 燃煤业务库全流程跑通，生成本体图谱。
