# AI 域概念重命名迁移方案

> 目标：消除 AIStation AI 域中**同名不同物 / 一名多义**的概念混淆，使命名与 Palantir Foundry / Ontology / AIP 的语义对齐。
> 原则：**先文案、后接口、最后（可选）表名**；每一步可独立回滚，不破坏现有功能与数据。
> 本文只描述方案，不改代码。

---

## 0. 背景

概念审查（2026-10）发现 AI 域存在 7 组「同名不同物 / 一名多义」：

| # | 混淆点 | 现状 |
|---|--------|------|
| 1 | `action` 两套 | `ai_action`（问数表级写回，`/ai/query/action/*`）与 `ai_ont_action`（本体动作类型，`/ai/ontology/actions`），共用 `ai_action_log` |
| 2 | `Object Type` 两套 | `ai_ont_object`（本体对象类型）与 `ai_query_assets.object_enabled`（问数派生对象） |
| 3 | `kg` 两套 | `ai_query_kg_relation`（数据 schema 图）与 `ai_knowledge_entities/relations`（GraphRAG 知识图谱） |
| 4 | 「报表」两套 | `ai_query_reports`（报表模板，`/ai/query/reports`）与 `ai_reports`（AI 报告，`/ai/report/*`） |
| 5 | 「评测」两套 | `/ai/query/eval/*`（问数评测）与 `/ai/overview/eval*`（AI 能力评测） |
| 6 | 「会话」两套 | `ai_sessions`/`ai_messages`（助手）与 `ai_query_sessions`/`ai_query_messages`（问数） |
| 7 | 「沙箱」两套 | `access_walkthrough`（权限预览）与 `ai_ont_scenario`（本体场景） |

**已修（本轮）**：`本体/概念` → 业务概念；`Autopilot/Guardrails` → 治理巡检/治理检查；`FDE` 注释去借词。

---

## 1. 命名对照表（目标终态）

| 概念 | 目标命名 | 物理表（不改） | 规范接口 | 前端入口 |
|------|----------|----------------|----------|----------|
| 本体对象类型 | **Object Type** | `ai_ont_object` | `/ai/ontology/objects` | 本体 |
| 本体动作类型 | **Action Type** | `ai_ont_action` | `/ai/ontology/actions` | 本体 → 动作 |
| 表级写回（旧） | **Legacy Write-back** | `ai_action` | `/ai/query/action/*`（deprecated） | 治理 → 表级写回（旧版） |
| 动作审计 | **Action Audit Log** | `ai_action_log` | — | 治理 → 动作审批（审计） |
| 数据关系图 | **Data Graph** | `ai_query_kg_relation` | `/ai/query/assets/kg/*` | 数据与集成 → 血缘 |
| 知识图谱 | **Knowledge Graph** | `ai_knowledge_entities`/`_relations` | `/ai/knowledge/*` | 知识库 |
| 报表模板 | **Report Template** | `ai_query_reports` | `/ai/query/reports` | 智能问数 → 自定义报表 |
| AI 报告 | **AI Report** | `ai_reports` | `/ai/report/*` | AI 控制台 / 独立页（待定） |
| 问数评测 | **Query Eval** | `ai_eval_*` | `/ai/query/eval/*` | 问数评测 |
| AI 能力评测 | **Capability Eval** | `ai_eval_bench*` | `/ai/overview/eval*` | AI 控制台 → 评测 |
| 助手会话 | **Assistant Session** | `ai_sessions`/`ai_messages` | `/ai/sessions` | AI 助手浮窗 |
| 问数会话 | **Query Session** | `ai_query_sessions`/`ai_query_messages` | `/ai/query/sessions/*` | 智能问数 |
| 权限预览 | **Check Access** | `access_walkthrough` | `/ai/query/access/preview*` | 治理 → 权限 |
| 本体场景 | **Scenario** | `ai_ont_scenario` | `/ai/ontology/scenarios` | 本体 → 场景 |

> **约定**：物理表名一律不改（改名成本/风险远高于收益，且表名是"实现细节"）。所有统一只发生在**接口路径、前端文案、代码常量、文档**四层。

---

## 2. 迁移策略（三阶段，逐阶段可回滚）

### 阶段 P0 — 文案层（零风险，建议立即执行）

只改**中文文案 / 后端 summary / 代码注释**，不动任何路径、表名、字段。

- 前端：tab 标题、按钮、空态、提示语。
- 后端：`controller.py` 的 `summary=`、`service.py` 的 docstring、`init_app.py` 的菜单 `name`。
- 验收：全仓 `grep` 不再出现歧义旧词（除历史注释说明）。

**可逆性**：完全可逆（纯文本）。

### 阶段 P1 — 接口别名层（中风险）

为每个"应改名"的接口**新增规范路径**，旧路径保留并标记 deprecated（`summary="(deprecated) ..."`），前端切到新路径。旧路径至少保留 2 个版本。

- 后端：新增 `@AiQueryRouter.get("/<new-path>")`，其函数体与旧函数共用 service；旧路由加 deprecated 标记。
- 前端：`api/module_ai/*.ts` 切新路径（一次改完）。
- 验收：旧路径仍可用（回归测试断言 200）；新路径全部可用；前端无旧路径引用。

**可逆性**：可逆（删新路径 + 前端回滚）。

### 阶段 P2 — 表名层（高风险，默认不做）

物理重命名表：`ALTER TABLE ... RENAME TO ...` + Alembic 迁移 + 全链路回归。

- **默认不做**：仅在"表名已对外暴露/被外部系统引用"时才值得。
- 若做：必须一次性完成（迁移链 + 模型 + 原生 SQL + 测试 DDL + 迁移测试），并准备回滚脚本。
- 验收：全量测试通过 + 迁移在空库/存量库均可重放。

**可逆性**：低（需备份 + 回滚脚本）。

---

## 3. 逐项方案

### 3.1 `action` 两套 → 本体动作为唯一「动作类型」

**问题**：两处都能"定义/执行动作"，用户不知在哪定义；且共用审计表。

**方案**
- **P0 文案**：
  - 治理面板「动作审批」tab 标题 → **「表级写回（旧版）」**，加 `el-alert`：*"新动作请到 本体 → 动作类型 定义；此处为历史表级写回，逐步下线。"*
  - 本体「动作」页面标题 → **「动作类型（Action Type）」**。
- **P1 接口**：
  - `/ai/query/action/*` 全部加 `summary` 前缀 `(deprecated) `。
  - 新增 `/ai/query/writeback/*` 作为规范路径（语义化），前端治理面板切到新路径。
- **P2（可选终态）**：把 `ai_action` 的数据迁移为 `ai_ont_action`（method=update + writable_cols），下线 `ai_action`。
- 涉及文件：`backend/app/plugin/module_ai/query/controller.py`、`service.py`、`frontend/src/views/module_ai/integration/components/GovernancePanel.vue`、`frontend/src/api/module_ai/query.ts`。

### 3.2 `Object Type` 两套 → 本体为唯一对象类型源

**问题**：`ai_ont_object` 与 `ai_query_assets.object_enabled` 并存，问数对象无软删/无权限/无动作。

**方案**
- **P0 文案**：问数「表与字段」的"纳入对象"开关文案 → **「纳入本体对象（生成 ObjectType）」**。
- **P1 接口**：问数侧"设为对象"改调本体 `POST /ai/ontology/objects`（或既有 `import-from-ds`），`ai_query_assets.object_enabled` 转为**只读派生**（由本体对象反查）。
- **P2（可选）**：删除 `object_enabled` 直出对象的查询路径（`service.list_objects`），统一由本体供给。
- 涉及文件：`query/service.py`（`list_objects`/`import_*`）、`integration/index.vue`、`ontology/service.py`。

### 3.3 `kg` 两套 → 数据关系图 / 知识图谱

**方案（仅 P0 文案 + P1 接口别名）**
- 数据与集成「血缘」tab 文案 → **「数据关系图（Data Graph）」**；其内说明"数据侧关系图 ≠ 本体类型层图"。
- 知识库页面文案 → **「知识图谱（Knowledge Graph）」**。
- 接口：`/ai/query/assets/kg/*` 保持不变（已是 assets 命名空间，语义可接受）；`/ai/knowledge/*` 保持。
- 涉及文件：`integration/index.vue`（tab 标题/注释）、`knowledge/index.vue`。

### 3.4 「报表」两套 → 报表模板 / AI 报告

**方案**
- P0 文案：`/ai/query/reports` 菜单/页头 → **「报表模板」**；`ai_reports` 相关 → **「AI 报告」**。
- P1：`AiReport` 菜单目前下线（`REMOVED_ROUTE_NAMES`）。二选一：
  - (a) 保持下线，AI 报告仅由 AI 控制台生成（现状）；
  - (b) 恢复为独立「AI 报告」页，接口 `/ai/report/*` 不变。
- 涉及文件：`init_app.py`（菜单名）、`query/reports.vue`、`overview/index.vue`。

### 3.5 「评测」两套 → 问数评测 / AI 能力评测

**方案（仅 P0 文案）**
- `/ai/eval` 页头 → **「问数评测（Query Eval）」**。
- AI 控制台内评测区块 → **「AI 能力评测（Capability Eval）」**。
- 接口路径保持。
- 涉及文件：`eval/index.vue`、`overview/index.vue`。

### 3.6 「会话」两套 → 助手会话 / 问数会话

**方案（仅 P0 注释 + 常量命名）**
- 接口路径已天然区分（`/ai/sessions` vs `/ai/query/sessions`），保持。
- 代码常量/类型名：`session.ts` 注释明确"助手会话"；`query.ts` 明确"问数会话"。
- 表名不改。

### 3.7 「沙箱」两套 → 权限预览 / 场景

**方案（仅 P0 文案）**
- 治理面板我已加的「权限沙箱」→ 改名 **「权限预览（Check Access）」**。
- 本体「场景（Scenario）」保持。
- 涉及文件：`GovernancePanel.vue`。

---

## 4. 风险与回滚

| 阶段 | 风险 | 缓解 | 回滚 |
|------|------|------|------|
| P0 文案 | 极低（可能遗漏引用） | 全仓 grep 校验 | `git revert` |
| P1 接口别名 | 前端漏切/新路径回归 | 旧路径保留 + 回归测试断言旧路径仍 200 | 删新路径 + 前端回滚 |
| P2 表名 | 迁移链断裂、原生 SQL 漏改 | 迁移测试（空库 + 存量库重放）+ 备份 | 回滚脚本 + 备份恢复 |

**硬性约束**
- 每阶段单独提交，提交信息含阶段前缀（`refactor(ai,naming-P0): ...`）。
- P1 前先补**旧路径仍可用的回归测试**。
- 不做 P2 时，在 `docs` 与表注释中登记"物理表名与概念名映射"，避免后续误解。

---

## 5. 优先级与工作量

| 项 | 阶段 | 工作量 | 建议 |
|----|------|--------|------|
| action 文案 + deprecated 标记 | P0/P1 | 0.5 天 | **先做**（最误导） |
| Object Type 收敛 | P1 | 1 天 | 次做（涉及行为变更） |
| kg / 报表 / 评测 / 会话 / 沙箱 文案 | P0 | 0.5 天 | 一并做（纯文案） |
| 接口别名层（统一） | P1 | 1 天 | 视需要 |
| 表名迁移 | P2 | 3–5 天 | **暂不做** |

---

## 6. 验收标准

1. 全仓 `grep` 歧义旧词（"本体/概念"、"AIP Autopilot"、"护栏"、"FDE 复用"等）为零（历史注释除外）。
2. 前端所有 tab/页头/空态文案与本文「目标命名」一致。
3. P1 若执行：旧接口路径仍返回 200（回归测试），新路径全部可用，前端无旧路径引用。
4. 后端测试全绿（`uv run pytest -q -n 4`），前端 `type-check` 无**新增**错误。
5. 文档与表注释登记「物理表名 ↔ 概念名」映射。
