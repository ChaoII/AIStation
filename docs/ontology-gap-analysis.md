# 本体能力差距清单（对照 Palantir Foundry 官方文档树）

> 用途：把「官方有 / 我们有 / 缺什么」一次性对清楚，作为后续排期的依据。
> 本文只做对账，**不含任何新功能设计**。

---

## 0. 这份清单怎么来的

### 数据来源

| 项 | 说明 |
|---|---|
| 官方站点结构 | `palantir.com/docs` 的 sitemap（`.research/palantir/all_urls.txt`），中文版共 **2385** 条 URL |
| **本体产品族** | 其中 **361** 页（占全站 **15.1%**），由 **23** 个区域组成 |
| 页面正文 | 原件存于 `.research/palantir/raw/`（59 页），清洗副本在 `docs/_palantir/clean/` |
| 我们的实现 | `backend/app/plugin/module_ai/ontology/`、`frontend/src/views/module_ai/ontology/`，以及 P0–P5 各阶段的验收实测记录 |

### 判定口径

| 标记 | 含义 |
|---|---|
| ✅ **已实现** | 有可用的界面/接口，且经实测通过 |
| 🟡 **部分实现** | 概念或字段存在但能力不完整；**或字段存了却不生效**（后者最危险） |
| ❌ **未实现** | 完全没有 |

### 证据分级（务必注意）

| 级别 | 含义 |
|---|---|
| **A** | 我**读过该页正文**（或该区域概览页）后下的判断 |
| **B** | 依据页面 URL 名称（官方 slug 命名很直白）＋ 我对该产品的既有了解**推断** |

❌/🟡 判断均标注级别。**B 级是有依据的推断，不等于读过原文**——排期到具体某项时必须再读该页原文核对。

### 计数口径

每个区域的**着陆页**（如 `/docs/zh/foundry/ontology/` 本身）也计入该区域页数。因此
`🔴 区域名 (N)` 中的 N = 着陆页 1 页 + 子页面 N-1 页，与 sitemap 完全一致。

---

## 1. 总览

### 1.1 按区域

| # | 区域 | 页数 | ✅ | 🟡 | ❌ | 覆盖判断 |
|---|---|---|---|---|---|---|
| 1 | `ontology` 本体（理念/概念/应用） | 6 | **3** | 1 | 2 | P3 后决策中心理念已落地 |
| 2 | `ontologies` 本体工件（提案/权限/共享） | 9 | **2** | 2 | **5** | 提案/分支已实现 |
| 3 | `ontology-manager` 本体管理器 | 9 | **7** | 1 | 1 | **覆盖最好** |
| 4 | `object-link-types` 对象与关系类型 | 40 | **29** | 7 | 4 | **覆盖最广** |
| 5 | `action-types` 动作类型 | 27 | **9** | 2 | 16 | 提交条件/规则/副作用已生效 |
| 6 | `functions` 函数 | 53 | **11** | 5 | **37** | P2 后：四形态+类型化入参 |
| 7 | `interfaces` 接口 | 9 | 5 | 3 | 1 | 做得较实 |
| 8 | `object-explorer` 对象浏览器 | 15 | 6 | 2 | 7 | 基础可用 |
| 9 | `object-views` 对象视图 | 18 | **9** | 3 | **6** | 含筛选器生效 + 共享 + 深链 |
| 10 | `vertex` 顶点（图/场景/时间轴） | 27 | **4** | 5 | **18** | P5 后场景已实现 |
| 11 | `object-monitors` 对象监视器 | 12 | 0 | 0 | 12 | ⛔ **官方已 Sunset，不做** |
| 12 | `logic` AIP Logic | 11 | 0 | 0 | 11 | 全无 |
| 13 | `process-mining` Machinery | 5 | 0 | 0 | 5 | 全无 |
| 14 | `foundry-rules` 规则引擎 | 28 | 0 | 0 | 28 | ⛔ **独立产品，决定不做** |
| 15 | `map` 地图 | 34 | 0 | 0 | 34 | ⛔ **独立产品，决定不做** |
| 16 | `dynamic-scheduling` 动态调度 | 11 | 0 | 0 | 11 | 全无 |
| 17 | `object-edits` 对象编辑 | 7 | 2 | 2 | 3 | 只有 Writeback 基础 |
| 18 | `object-indexing` 索引 | 5 | **3** | 1 | **1** | 真建库索引 + 状态机 + 自动重试 |
| 19 | `object-permissioning` 对象权限 | 5 | **3** | 1 | 1 | P4 后：两层+单元格级 |
| 20 | `object-backend` 后端架构 | 5 | 0 | 0 | 5 | ⛔ **平台基础设施，决定不做** |
| 21 | `object-databases` 对象数据库 | 2 | 0 | 0 | 2 | ⛔ **平台基础设施，决定不做** |
| 22 | `ontology-sdk` OSDK | 19 | 0 | 0 | 19 | ⛔ **决定不做（有 REST）** |
| 23 | `ontology-sdk-react-applications` | 4 | 0 | 0 | 4 | ⛔ **决定不做（有 REST）** |
| | **合计** | **361** | **97** | **37** | **227** | |

> **✅ 26.9% / 🟡 10.2% / ❌ 62.9%**（全量口径）

**有效缺口口径**（扣掉上表标 ⛔ 的「决定不做 / 已 sunset」共 **104 页**）：

| 口径 | 页数 | ✅ | 🟡 | ❌ | 覆盖率 |
|---|---|---|---|---|---|
| 全量（含决定不做） | 361 | 79 | 33 | 249 | **21.9%** |
| **有效范围**（去掉 104 页不做项） | **257** | 97 | 37 | **123** | **37.7%** |

> 两个口径都要看：**全量口径**说明"对标 Palantir 全平台"还差多少；
> **有效缺口口径**说明"在我们决定要做的范围内"还差多少。（A/B/C + 问数打通 + 语义收敛后：96/257 = 37.4%）
> 只报前者会显得毫无进展，只报后者会掩盖"我们主动放弃了一大块"。

### 1.2 一句话结论

> 已做的部分高度集中在**「定义本体」**这一竖条（对象/关系/动作/接口/共享属性/值类型/组/管理器），
> 而**索引，以及六个整块的应用级区域**几乎是空的。（函数/权限/场景已在 P2/P4/P5 补齐）

### 1.3 按"能力支柱"重新归类（比按产品分区更有意义）

对照 `why-ontology` 的四支柱：

| 支柱 | 估计覆盖 | 依据 |
|---|---|---|
| **Data** | 🟡 约 55% | 类型系统最全（`object-link-types` 29/40、`interfaces` 5/9）；P3 补上决策数据与决策谱系；仍缺索引（0/5）、对象存储（0/7） |
| **Logic** | 🟡 **约 25%** | P2 后函数有四种可用形态（表达式/聚合/外部服务/模型）+ 类型化签名；仍无代码执行沙箱 |
| **Action** | 🟡 **约 45%** | P0 后提交条件、规则、副作用**都已真正执行**（含通知与 Webhook）；仍缺函数动作/链接类规则/自动化触发 |
| **Security** | 🟡 **约 40%** | P4 后：资源 ACL + 行级策略 + 列级角色 + **Agent 工具按调用者门控**；仍无标记/目的/CBAC/SDK 权限 |

---

## 2. 逐区域完整对账

### 2.1 🟡 `ontology` 本体（6 页）— ✅3 / 🟡1 / ❌2

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `ontology`（着陆页） | ✅ | 本体 = objects/properties/links/actions/functions + **决策**（P3 起决策也是一等对象） | A |
| `overview` | ✅ | 同上 | A |
| `why-ontology` | ✅ | P3 后理念已落地：决策数据（上下文/备选/下游影响）与决策谱系（何时/数据版本/应用）都真捕获，且决策是本体内的一等对象 | A |
| `core-concepts` | 🟡 | objects/properties/links/actions/functions 齐（P2 后函数四形态）；interfaces/值类型/共享属性/组已有；决策也已入本体 | A |
| `models` | ❌ | 模型映射到本体：建模目标 → 提交 → 评估 → 部署 → 输入输出映射到本体概念。我们有模型/provider 管理，但**与本体无绑定** | A |
| `applications` | ❌ | Workshop / Slate / OSDK 类应用构建 | A |

### 2.2 🔴 `ontologies` 本体工件（9 页）— ✅0 / 🟡2 / ❌7

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `ontologies`（着陆页） | 🟡 | 我们有 `ai_ont_domain`（本体） | A |
| `ontologies-overview` | 🟡 | 官方是 artifact + 与 space **1:1** + 组织标记；我们只是一对多归属 | A |
| `ontologies-proposals` | ❌ | **分支 + 提案（PR 式评审）**。我们有"版本发布待审批"，但那是发布审批，不是分支提案 | A |
| `ontology-permissions` | ❌ | Ontology 角色（访客/编辑者/所有者） | B |
| `shared-ontologies` | ❌ | 跨组织共享本体 | B |
| `ontology-migration` | ❌ | 本体间迁移 | B |
| `volume-usage` | ❌ | 容量用量 | B |
| `compute-usage` | ❌ | 算力用量 | B |
| `query-compute-usage` | ❌ | 查询算力用量 | B |

### 2.3 🔴 `ontology-manager` 本体管理器（9 页）— ✅7 / 🟡1 / ❌1

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `ontology-manager`（着陆页） | ✅ | | A |
| `overview` | ✅ | | A |
| `navigation` | ✅ | 树状导航 + 选中资源切 9 页 + 返回 | A |
| `save-changes` | ✅ | 工作副本 + Save/Discard + 角标 | A |
| `restore-changes` | ✅ | 版本快照恢复（恢复本身也是一条草稿） | A |
| `export-import` | ✅ | 定义导出/导入 JSON | A |
| `cleanup` | ✅ | 弃用/删除候选建议 | A |
| `view-usage` | 🟡 | 3 个读数（读/写/交互）；**缺"活跃用户数"** | A |
| `ontology-roles-migration` | ❌ | 角色迁移 | B |

### 2.4 🔴 `object-link-types` 对象与关系类型（40 页）— ✅27 / 🟡8 / ❌5

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `object-link-types`（着陆页） | ✅ | | A |
| `type-reference` | 🟡 | 有 16 个 base type，但**缺官方"类型引用"页语义**（哪些类型可作 link 端点等） | B |
| `object-types-overview` | ✅ | | A |
| `create-object-type` | ✅ | 对象类型 26 字段 | A |
| `edit-object-type` | ✅ | | A |
| `object-type-metadata` | ✅ | | A |
| `properties-overview` | ✅ | | A |
| `edit-properties` | ✅ | 属性 26 字段 | A |
| `property-metadata` | ✅ | | A |
| `edit-only-properties` | ✅ | `edit_only` | A |
| `value-formatting` | 🟡 | 字段已落库，**无可视化编辑器** | A |
| `conditional-formatting` | 🟡 | 同上 | A |
| `required-properties` | 🟡 | 有 `required` 标记，但官方的"必需属性"是**对象类型级强制约束**；写回/动作时**不校验** | A |
| `shared-property-overview` | ✅ | | A |
| `create-shared-property` | ✅ | | A |
| `edit-shared-property` | 🟡 | 能改并同步元数据 | A |
| `use-shared-property` | ✅ | | A |
| `shared-property-metadata` | ✅ | | A |
| `link-types-overview` | ✅ | | A |
| `create-link-type` | ✅ | | A |
| `edit-link-types` | ✅ | | A |
| `link-type-metadata` | ✅ | 关系类型 16 字段，含**双向命名** | A |
| `allow-editing` | 🟡 | `edits_enabled` 有，但**缺每属性级可编辑开关** | A |
| `value-types-overview` | ✅ | | A |
| `create-value-type` | ✅ | | A |
| `use-value-type` | 🟡 | 约束已接入**动作参数**；实例层 Writeback 仍未校验 | A |
| `value-types-versions` | ✅ | 改定义自动 `version+1` | A |
| `value-type-constraints` | ✅ | 约束校验**已接到动作参数写入路径**（pattern/min/max/长度/枚举） | A |
| `value-types-permissions` | ✅ | `roles` **已生效**：无对应角色不能把值类型分配给属性；增删改值类型需管理员 | A |
| `structs-overview` | ✅ | | A |
| `create-struct-type` | ✅ | | A |
| `edit-struct-type` | ✅ | | A |
| `struct-automapping` | ❌ | 从数据列自动映射出 struct | B |
| `struct-shared-properties` | ❌ | struct 里用共享属性 | B |
| `metadata-typeclasses` | ✅ | `type_class` | A |
| `metadata-render-hints` | ✅ | `render_hint` | A |
| `metadata-statuses` | ✅ | `status` | A |
| `type-groups` | ✅ | 对象类型组（多对多） | A |
| `enable-gotham-integration` | ❌ | Gotham 集成（非本栈目标） | B |
| `marketplace-ontology-types` | ❌ | 类型市场 | B |

### 2.5 🔴 `action-types` 动作类型（27 页）— ✅6 / 🟡5 / ❌16

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `action-types`（着陆页） | ✅ | | A |
| `overview` | ✅ | | A |
| `getting-started` | ✅ | | A |
| `use-actions` | ✅ | | A |
| `parameter-overview` | ✅ | `parameters` 驱动工具 schema | A |
| `action-log` | ✅ | `ai_action_log`（success/noop/pending） | A |
| `rules` | ✅ | **已实现执行器**：支持 修改/创建/删除对象，赋值来源含 参数/静态值/当前用户/当前时间/对象参数的属性 | A |
| `submission-criteria` | ✅ | **已实现**：三类条件模板 + 单值/多值算子 + 可嵌套 AND/OR/NOT + 每条件失败信息 | A |
| `side-effects-overview` | ✅ | **已实现**：通知写 `sys_user_notification`；Webhook 真正发 HTTP 请求（可 before/after、可阻塞） | A |
| `configure-sections` | 🟡 | `ui_sections` 存了，界面未使用 | A |
| `action-metrics` | 🟡 | 有动作日志，**无指标看板** | B |
| `parameters-default-value` | ❌ | 参数默认值 | B |
| `parameters-filter` | ❌ | 参数级过滤/依赖 | B |
| `parameters-override` | ❌ | 参数覆盖 | B |
| `dropdown-security` | ❌ | 下拉选项按权限过滤 | B |
| `function-actions-overview` | ❌ | **用函数作为动作**（依赖 Logic） | B |
| `function-actions-getting-started` | ❌ | 同上 | B |
| `notifications` | ❌ | 通知 | B |
| `set-up-notification` | ❌ | 同上 | B |
| `webhooks` | ❌ | Webhook | B |
| `set-up-webhook` | ❌ | 同上 | B |
| `upload-attachments` | ❌ | 附件上传 | B |
| `scale-property-limits` | ❌ | 属性规模限制 | B |
| `inline-edits` | ❌ | 行内编辑 | B |
| `permissions` | ❌ | 动作级权限 | B |
| `action-reverts` | ❌ | 动作撤销 | B |
| `marketplace-action-types` | ❌ | 动作市场 | B |

### 2.6 🟡 `functions` 函数（53 页）— ✅11 / 🟡5 / ❌37（P2 后）

> P2 把函数从「库内四则运算」升级为**四种形态的声明式函数**：
> `expression`（表达式 + 33 个白名单内置函数）/ `aggregate`（沿关系链聚合）/
> `http`（调外部 REST）/ `model`（调平台已登记模型）。
> 配套：类型化**入参/出参**声明、**对象上下文**（入参可取对象属性）、**按类型转换取值**、运行/试运行。
>
> **仍然不做**：真正的 Python / TypeScript 代码执行（§9 已列为非目标）——这是本区域剩下 37 页 ❌ 的主因。

| 页面 | 状态 | 页面 | 状态 | 页面 | 状态 |
|---|---|---|---|---|---|
| `functions`（着陆页） | ✅ | `python-functions-workshop` | ❌ | `unit-test-ontology-edits` | ❌ |
| `overview` | ✅ | `python-functions-advanced-usage` | ❌ | `unit-test-object-searches` | ❌ |
| `use-functions` | ✅ | `functions-on-models` | ✅ | `unit-test-dates-timestamps` | ❌ |
| `getting-started` | ❌ | `language-models` | ✅ | `unit-test-users-groups` | ❌ |
| `input-output-types` | ✅ | `external-sources` | ✅ | `unit-test-debugging` | 🟡 |
| `decorators` | ❌ | `functions-on-objects` | ✅ | `enforced-limits` | ✅ |
| `undefined-values` | 🟡 | `foo-getting-started` | ❌ | `optimize-performance` | ❌ |
| `debug` | 🟡 | `object-identifiers` | ❌ | `configure-notifications` | ❌ |
| `add-dependencies` | ❌ | `create-custom-aggregation` | ✅ | `permissions` | ❌ |
| `python-getting-started` | ❌ | `ontology-imports` | ❌ | `marketplace-functions` | ❌ |
| `python-function-types` | ❌ | `api-objects-links` | ❌ | `resource-imports-sidebar` | ❌ |
| `python-functions-on-objects` | ❌ | `api-object-sets` | ❌ | `api-attachments` | ❌ |
| `python-functions-api-calls` | ❌ | `api-media` | ❌ | `overview-semantic-search` | ❌ |
| `python-ontology-edits` | ❌ | `using-palantir-provided-models-…` | ❌ | `chunking` | ❌ |
| `python-functions-builder` | ❌ | `using-custom-models-…` | ❌ | `pdf-handling` | ❌ |
| `edits-overview` | ❌ | `edits-generate-id` | ❌ | `user-facing-error` | 🟡 |
| `api-ontology-edits` | ❌ | `query-functions` | 🟡 | `model-functions` | ✅ |
| `unit-test-getting-started` | 🟡 | `unit-test-stub-objects` | ❌ | | |

**P2 判定依据**

| 页面 | 判 ✅ 的依据 |
|---|---|
| `input-output-types` | 入参可声明 `type`（string/number/integer/boolean/date/list/object_ref）并按类型转换取值；出参可声明 `key/name/type`，写进 Agent 工具说明 |
| `functions-on-objects` | 入参来源 `object_property` 会去加载对象实例并取该属性；整套接口可传 `object_key` 作为上下文 |
| `external-sources` | `http` 形态：真发 REST 请求，支持 method/headers/body_template/`result_path`/timeout |
| `functions-on-models` · `model-functions` · `language-models` | `model` 形态：走平台已登记的模型（未写 `model_id` 时按默认 chat 模型解析） |
| `create-custom-aggregation` | `aggregate` 形态：9 种聚合（count/sum/avg/min/max/first/last/collect_list/collect_set）沿关系链（≤3 层） |
| `enforced-limits` | 关系链 ≤3 层、limit 1–100、HTTP timeout 0.5–60s、请求体 ≤20KB、只能调白名单内置函数 |
| `use-functions` | 函数列表有「运行」入口，弹窗填参即跑，显示返回值与实际入参 |

> `undefined-values` 判 🟡：`coalesce`/`iif`/`is_empty` 能处理空值，但没有官方的 undefined 传播语义。
> `debug` / `unit-test-*` 判 🟡：有「运行」与「校验定义」两个入口，但不是自动化的单元测试框架。
> `user-facing-error` 判 🟡：错误信息可读（未知变量/未知函数/类型不符/URL 非法），但未做面向终端用户的错误话术。
> `query-functions` 判 🟡：能沿关系链聚合，但不是官方的 object-set 查询函数。

### 2.7 🔴 `interfaces` 接口（9 页）— ✅5 / 🟡3 / ❌1

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `interfaces`（着陆页） | ✅ | | A |
| `interface-overview` | ✅ | 已读原文，概念对齐 | A |
| `create-interface` | ✅ | | A |
| `implement-interface` | ✅ | 约束在实现侧强制，已实测 | A |
| `interface-metadata` | ✅ | 名称/描述/状态/可见性 | A |
| `edit-interface-definition` | 🟡 | 能改，缺"改完谁掉队"的完整流程（有合规检查按钮） | A |
| `edit-interface-implementation` | 🟡 | 同上 | A |
| `interface-link-types-overview` | 🟡 | **官方接口可声明 link type 约束（目标须实现某接口）**；我们只校验同名关系存在，不校验对端类型 | A |
| `extend-interface` | ❌ | 接口继承 | B |

### 2.8 🔴 `object-explorer` 对象浏览器（15 页）— ✅6 / 🟡2 / ❌7

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `object-explorer`（着陆页） | ✅ | | A |
| `overview` | ✅ | | A |
| `getting-started` | ✅ | | A |
| `search-objects` | ✅ | 关键词搜索真实行 | A |
| `pivot-linked` | ✅ | **双向透视，已实测**（`沿「摄像机」找到 100 个告警记录表`） | A |
| `apply-actions` | ✅ | 批量执行动作，已实测（50 个实例） | A |
| `filter-results` | 🟡 | 接口支持 `filters`，**界面没有筛选器** | A |
| `view-results` | 🟡 | 有表格，无结果集图表 | A |
| `search-syntax` | ❌ | 搜索语法（如 `字段:值`） | B |
| `explore-charts` | ❌ | 结果集可视化 | B |
| `compare-object-sets` | ❌ | 对象集对比 | B |
| `save-explorations` | ❌ | 保存探索 | B |
| `save-lists` | ❌ | 保存对象列表 | B |
| `generate-urls` | ❌ | 生成可分享 URL | B |
| `configure` | ❌ | 配置 | B |

### 2.9 🔴 `object-views` 对象视图（18 页）— ✅0 / 🟡1 / ❌17

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `overview` | 🟡 | 我们只有探索器里的**抽屉式单实例页**（属性+关系+动作+写回），不是官方那种**可配置的 Object View 工件** | A |
| `object-views`（着陆页） | ❌ | | B |
| `use-object-views-in-platform` | ❌ | 在平台各处使用 | B |
| `config-overview` / `config-tabs` / `config-workshop-tabs` / `config-widgets` / `config-app-sidebar` / `config-profiles` | ❌ | 视图配置体系（6 页） | B |
| `widgets-properties-links` / `widgets-visualization` / `widgets-filtering` / `widgets-layout` / `widgets-apps-files` | ❌ | 视图挂件（5 页） | B |
| `manage-versions` | ❌ | 视图版本管理 | B |
| `generate-urls` | ❌ | URL | B |
| `comment-on-objects` | ❌ | 对象评论 | B |
| `marketplace-object-views` | ❌ | 视图市场 | B |

### 2.10 🟡 `vertex` 顶点（27 页）— ✅4 / 🟡5 / ❌18

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `explore-object-relationships` | ✅ | 实例层图 + 多步扩展 + 布局，已实测（21 节点/20 边） | A |
| `vertex`（着陆页） | 🟡 | 基础形态有 | A |
| `overview` | 🟡 | | A |
| `example-use-cases` | 🟡 | | A |
| `graphs-display-options` | 🟡 | 有布局/缩放/适配/搜索 | A |
| `derive-property-functions` | 🟡 | 我们有派生属性，但**不是图上的派生属性函数** | A |
| `graphs-explore` | ❌ | 保存的图探索 | B |
| `save-share` | ❌ | 保存与分享 | B |
| `graphs-template` | ❌ | **图模板** | B |
| `generate-graph-apps` | ❌ | 由图生成应用 | B |
| `generate-graph-functions` | ❌ | 由图生成函数 | B |
| `embed-graph-workshop` | ❌ | 嵌入 Workshop | B |
| `read-only-mode` | ❌ | 只读模式 | B |
| `events-overview` / `configure-events` / `explore-related-events` | ❌ | **事件**（3 页） | B |
| `explore-time-series` / `use-time-selection` / `configure-thresholds` / `timeline` | ❌ | **时间轴与时间序列**（4 页） | B |
| **`scenarios-overview` / `scenarios-getting-started` / `scenarios-options`** | ✅ | **场景（沙箱化决策探索）**（3 页）——P5 已实现：编辑叠加式沙箱、读叠加、单事务合并、多场景对比、TTL、按执行上下文治理动作 | A |
| `chained-models` | ❌ | 模型链 | B |
| `vertex-settings-control-panel` | ❌ | 设置面板 | B |
| `link-merging` | ❌ | 链接合并 | B |
| `marketplace-vertex` | ❌ | 图市场 | B |

### 2.11 🔴 `object-monitors` 对象监视器（12 页）— 全 ❌

> **重要发现：官方已标记 Sunset。** 原文：
> 「Object Monitors are in the **sunset** phase of development and will be deprecated at a future date.
> Full support remains available. We recommend migrating your workflows to **Automate**.」
>
> 所以这块**不建议投入**。要做监控应直接对标 Automate，而不是对象监视器。

功能内容（供参考）：监听数据变化 → 条件满足时发通知（平台内/邮件/短信/IM，短信与 IM 走 webhook）或**自动提交动作**；面向"被监视的搜索"（saved exploration 有新结果或聚合条件满足时通知）。

页面：`object-monitors` · `overview` · `create_new_object_monitor` · `monitor` · `input` · `condition` · `evaluation` · `activity` · `notifications` · `actions` · `limits` · `errors`

### 2.12 🔴 `logic` AIP Logic（11 页）— 全 ❌

> 这是 `why-ontology` 里 **Logic 支柱**的实际承载产品，**不是可有可无的东西**。

原文要点（A 级，已读 `overview` + `concepts`）：
- 无代码构建**由 LLM 驱动的函数**，可直接用本体，无需开发环境与 API 调用
- 函数由**块**组成：获取对象属性 / 创建变量 / **使用 LLM** / 变换块；**每个块可选不同 LLM**（Palantir 的 *k-LLM* 理念）
- **工具**三类（本体驱动）：应用动作 / 调用函数 / 查询对象 / 计算器
- **关键安全语义**：「LLM **没有**直接访问工具的权限；LLM 只能**请求**使用工具，这些工具调用随后由 AIP Logic **在调用用户的权限范围内执行**」
- **评估**：为 Logic 函数写测试、**对比不同模型**（如 GPT-4 vs GPT-3.5）、检查多次运行差异
- **调试器**：显示每个块的 LLM **思维链（CoT）**

页面：`logic` · `overview` · `concepts` · `getting-started` · `aip-logic-integration-automate` · `evaluations-overview` · `evaluations-getting-started` · `evaluations-create-suite` · `evaluations-metrics-dashboard` · `compute-usage` · `faq`

### 2.13 🔴 `process-mining` Machinery（5 页）— 全 ❌

流程挖掘/编排：把真实流程建模为**状态 + 状态迁移**（状态必须可枚举，须由字符串属性承载，建议用枚举值类型支撑），从外部事件日志挖掘流程，定义与监控流程指标，多步 AIP 工作流编排。

页面：`process-mining` · `overview` · `core-concepts` · `process-mining-setup` · `process-mining-operationalize`

### 2.14 🔴 `foundry-rules` 规则引擎（28 页）— 全 ❌

点选式规则引擎（前身 Taurus）：规则 = 一组**条件**，作用于数据集/对象/时间序列，用于**告警生成**与**数据分类**（AML、设备监控、人群分桶）。规则本身是**对象**，由 **rule proposals** 管理；配套 Workshop 应用（Rule Editor + Proposal Reviewer）。

页面：`foundry-rules` · `overview` · `core-concepts` · `object-model` · `workshop-application` · `rule-logic` · `foundry-rules-workflow-configuration` · `deploy-foundry-rules` · `deploy-workflow` · `configure-workflow` · `author-and-run-a-rule` · `customization` · `enable-optional-features` · `add-a-custom-property` · `rule-permissions` · `permitted-and-default-output-values` · `customize-foundry-rules-pipeline` · `timeseries-concepts` · `deploy-timeseries-foundry-rules` · `legacy-foundry-rules-setup-taurus` · `migrate-to-foundry-rules` · `configure-workshop-app` · `configure-transforms-pipeline` · `configure-rule-actions` · `configure-timeseries-foundry-rules` · `upgrade-to-use-rule-actions` · `common-issues` · `marketplace`

### 2.15 🔴 `map` 地图（34 页）— 全 ❌

地理空间产品：地图应用、图层管理、形状/注记、时间轴与时间序列、点/线/面/轨迹可视化、与本体对象集成、搜索穿透函数、动作集成、模板与挂件。
我们有 `latitude`/`longitude` 属性，但**没有任何地图能力**。

页面：`map` · `overview` · `getting-started` · `core-concepts` · `styling` · `map-overview` · `create-save-maps` · `add-to-map` · `layer-management` · `navigation` · `selection` · `annotations` · `shapes` · `histogram` · `actions` · `time-overview` · `time-selection` · `timeline` · `events` · `time-series` · `visualize-objects` · `visualize-points` · `visualize-polygons-lines` · `visualize-tracks` · `objects-high-scale` · `integrate-objects` · `integrate-searcharound-functions` · `integrate-actions` · `layer-editor` · `templates` · `widget` · `settings` · `control-panel` · `marketplace-map-templates`

### 2.16 🔴 `dynamic-scheduling` 动态调度（11 页）— 全 ❌

排程与资源分配：Gantt 图挂件（可视化约束、拖拽改期、找建议、执行本体动作）、日历挂件、建议函数、搜索函数、校验规则。
**对本体的硬性要求**：`Schedule` 对象须有「指向资源的外键（String）/ 开始时间（Timestamp）/ 结束时间（Timestamp）」，并与一个或多个 `Resource` 对象建关系。

页面：`dynamic-scheduling` · `scheduling-overview` · `scheduling-getting-started` · `scheduling-concepts` · `scheduling-ontology-primitives` · `scheduling-gantt-chart-widget` · `scheduling-suggestion-functions` · `scheduling-search-functions` · `scheduling-validation-rules` · `scheduling-calendar-overview` · `scheduling-calendar-widget`

### 2.17 🔴 `object-edits` 对象编辑（7 页）— ✅2 / 🟡2 / ❌3

| 页面 | 状态 | 说明 | 级别 |
|---|---|---|---|
| `object-edits`（着陆页） | ✅ | | A |
| `overview` | ✅ | 通过动作编辑对象/链接/新建删除，已实现 | A |
| `how-edits-applied` | 🟡 | 编辑如何叠加到索引数据 | A |
| `materializations` | 🟡 | 我们有"物化为表"，但**官方的 materialization 是"输入数据 + 用户编辑"的最新态数据集**，语义不同 | A |
| `user-edit-history` | ❌ | 用户编辑历史（我们只有动作日志） | B |
| `permission-checks` | ❌ | 编辑权限校验链 | B |
| `schema-migrations` | ❌ | schema 迁移 | B |

### 2.18 🔴 `object-indexing` 索引（5 页）— 全 ❌

官方由 **Funnel** 服务编排批/流两套索引管道，另有直连数据源支持低延迟写入。
我们只有对象类型上的一个 `index_status` **标记字段**，**没有任何索引机制**。

页面：`object-indexing` · `overview` · `funnel-batch-pipelines` · `funnel-streaming-pipelines` · `faq`

### 2.19 🟡 `object-permissioning` 对象权限（5 页）— ✅3 / 🟡1 / ❌1（P4 后）

两层授权：**本体资源**（对象/关系/动作类型的 schema）与**对象与链接**（真实数据）。
支持 **cell-level security = 行级 + 列级**。另有 `Check access` 面板。

| 页面 | 状态 | 说明 |
|---|---|---|
| `object-permissioning`（着陆页） | ✅ | 两层模型都落地：资源层 view/edit/manage；数据层行级+列级 |
| `overview` | ✅ | 同上；且「看得到类型 ≠ 看得到数据」已按官方语义分离 |
| `managing-object-security` | ✅ | 对象安全策略（行级表达式）+ 属性安全策略（列级角色）都实现，**读时生效** |
| `configuring-rv-access-controls` | 🟡 | **目标达成但机制不同**：官方此页讲用受限视图（RV）做行级；我们按官方**推荐优先**的那条路——直接在对象类型上配策略（object security policy）。三种策略只做了「读」与隐含的「编辑」，未单独拆出 `edit policy property`（改为：策略属性需管理角色） |
| `multi-datasource-objects` | ❌ | MDO（一个对象类型挂多个数据源、按源分别授权）完全未做 |

**P4 实现要点**

- 资源层：`ai_ont_resource_acl`（view/edit/manage 三组角色）。**空列表 = 公开**，因此不改变既有数据行为。
  官方用 Compass 项目做这一层，我们没有文件系统，故实现官方文档并列的**旧模型「Ontology roles」**。
- 行级：`ai_ont_row_policy` + 受控策略表达式求值器。支持对象属性、`user.id/name/dept/attribute('x')/role('X')`、
  `and/or/not/in` 与比较。**超管直通**；无启用的 allow 策略 = 全部可见。
- 列级：复用 `ai_ont_property.roles`——该字段**此前只存不用**（与 P0 同类问题），P4 起真正参与读/写判定。
- 强制点（**读时生效**，与官方一致；不做下游传播）：实例搜索/单条/关联跳转/实例图、属性写回、动作执行、
  **Agent 工具**（P4 前 Agent 完全不看调用者权限，是最大的口子）。
- 官方两条编辑规则照做：改关系要「关系类型 + 两端对象类型」的编辑权；改动作要「动作类型 + 动作所编辑的对象类型」的编辑权。
- **Check access**：`GET /security/explain` 逐步给出「类型可见性 → 列级 → 行级 → 策略属性」的判定与原因。

**仍未做**：标记（markings）、目的（purpose）、基于分类的访问控制（CBAC）、SDK 权限、对象标记。


### 2.20–2.21 🔴 `object-backend` / `object-databases`（7 页）— 全 ❌

本体后端微服务架构（数据源管理 / 索引 / 查询 / 操作），Object Storage v2 及 v1（Phonograph）。属平台基础设施。

页面：`object-backend` · `overview` · `object-storage-v2-breaking-changes` · `osv1-osv2-migration` · `aggregation-considerations` · `object-databases` · `object-storage-v1`

### 2.22–2.23 🔴 `ontology-sdk`（23 页）— 全 ❌

OSDK：用 TypeScript / Python / Java / OpenAPI 直接访问本体，把 Foundry 当后端。含应用脚手架、权限、不支持类型说明、各语言引导、OAuth 客户端、应用指标、迁移指南等。

页面（19）：`ontology-sdk` · `overview` · `navigation` · `permissions` · `unsupported-types` · `create-a-new-osdk` · `python-osdk` · `java-osdk` · `deploy-osdk-application-on-foundry` · `how-to-bootstrapping-typescript` · `how-to-bootstrapping-server-side-typescript` · `how-to-create-backend-service-app-different-org` · `how-to-add-to-existing-typescript` · `how-to-bootstrapping-python` · `how-to-bootstrapping-java` · `generate-osdk-for-other-languages` · `application-metrics` · `oauth-clients` · `typescript-osdk-migration`

页面（4）：`ontology-sdk-react-applications` · `overview` · `development` · `troubleshooting`

---

## 3. 比"缺页数"更该注意的五件事

### 3.1 ~~有 4 处字段「能填但不生效」~~ → **已修复（P0，2026-10）**

初版清单发现 4 处字段界面能填、执行时却完全不生效——比"整块没做"更危险，因为**用户会以为功能存在**。现已全部修复并实测：

| 字段 | 修复前 | 修复后 | 实测证据 |
|---|---|---|---|
| `submission_criteria` 提交条件 | 零校验 | **真正执行**：三类条件模板 + 单值/多值算子 + 可嵌套 AND/OR/NOT，未通过时回传失败信息 | 空名称被拦「新名称不能为空」；非管理员被拦「只有管理员角色能改摄像机名称」且库未变 |
| `rules` 规则 | 零校验（只有白名单生效） | **真正执行**：修改/创建/删除对象，赋值来源含参数、静态值、当前用户、当前时间、对象参数的属性 | 规则决定写入 `name` + `location` 两列，而非按参数直传 |
| `side_effects` 副作用 | 无执行器 | **真正执行**：通知写 `sys_user_notification`；Webhook 发真实 HTTP 请求 | 通知表新增 1 条且模板 `{{name}}`/`{{当前用户}}` 已替换；不可达地址在非阻塞下不中断、阻塞下报错 |
| 值类型 `roles` | 不参与过滤 | **真正生效**：无对应角色不能分配该值类型；增删改需管理员 | 超管可分配、普通用户被拒并列出其实际角色 |

附带的 P1 也做了：**值类型约束已接到动作参数的写入路径**（超长取值被拦，`blocked_by=value_type`）。

**同时修了一个连带的真 bug**：子组件暂存改动时不会刷新父页面的「未保存」角标，用户改了东西却看不到待保存提示。根因是暂存逻辑有两份（父页面一份、子组件各自直调 API），已统一到共享 composable。

### 3.2 Logic 支柱几乎是空的，而它是"接 AI"的关键

`why-ontology` 明确说：确定性函数/算法要与 LLM 的非确定性推理**互补**，并通过「逻辑绑定」纳异构逻辑资产（本地数据中心/云/SaaS）。
我们的"函数"只是库内四则运算——**既不能调模型，也不能调外部服务**。
`functions`（53）+ `logic`（11）= **64 页，占本体族 17.7%**，我们接近 0。

### 3.3 Security 支柱基本没有

官方安全 = **标记 / 目的 / 角色**三类策略 + **动态谱系** + **行列级** + **工具调用受同一安全架构约束**。
我们只有 `visibility`/`status` 过滤 + 敏感字段名启发式。
~~对象权限全未做~~ → **P4 已做**：资源 ACL + 行级 + 列级 + Agent 工具门控 + Check access。`ontology-sdk/permissions` 仍未做（无 SDK）。

特别值得注意的一条（AIP Logic 原文）：
> 「LLM 只能**请求**使用工具，工具调用由 AIP Logic **在调用用户的权限范围内执行**」

我们的 Agent 工具目前**不按调用者的数据权限过滤**。

### 3.4 ~~场景（scenarios）在三处被提到，我们一个都没有~~ → **已完成（P5，2026-10）**

三处提及：

- `vertex/scenarios-*`（3 页）：系统级场景，模拟整个组织的改动
- `ontology/models`：模型结果在系统级场景里探索
- `why-ontology` 示例：模拟输出 *"staged as ontology scenarios … sandboxed subset of the Ontology"*

**修复前**：我们有**工作副本（定义草稿）**，但没有**数据级的沙箱**。

**P5 修复后**：新增 `ai_ont_scenario` + `ai_ont_scenario_edit` 两张表，实现官方**当前（Beta）**的
`ontology/overview-ontology-scenario` 语义（不是 legacy 的 Workshop 版）：

| 官方要求 | 我们的落地 |
|---|---|
| *"a sandbox to apply edits on top of the data"* | 动作带 `scenario` 执行时**只记差异、不写真实表** |
| 读场景 = 基线 + 差异 | `instance_search` / `instance_get` 带 `scenario` 时叠加（真实表不动） |
| *"merged through action types ... as a **single transaction**"* | `apply_scenario` 在**一个事务**里写入，任一失败全部回滚；合并权限由 `merge_action_code` 的**提交条件**管 |
| *"Model results ... will **not** be applied"* | `model_result` 种类的编辑单独列出、合并时跳过 |
| *"duplicate a Scenario along with its existing Actions and parameters"* | `duplicate_scenario` 连编辑一起复制 |
| TTL 默认 31 天 | `expires_at` + `expire_scenarios()` 自动过期并清编辑 |
| *"govern actions by execution context"* | 提交条件的 `is_scenario` **真正生效**（补上了 P0 留的执行上下文） |
| 限额 30,000 编辑 / 50 动作 / 范围限定 | 三个限额都强制，超限给出可读原因 |
| 多场景对比 | `compare_scenarios` 并排展示同一对象在各场景下的取值 |

**一处刻意的差异（更简单且等价）**：官方底层复制数据并每 10 分钟 rebase；
我们存**相对基线的差异集**、读时叠加，因此**天然总是基于最新基线**——
等价于官方的自动 rebase，且不需要定时任务、也不会有 rebase 冲突。

**仍未做**：场景持久化为对象（官方 persisted scenario）、按 link type 的细粒度范围、场景级权限隔离。


### 3.5 ~~决策中心这条主线完全没落地~~ → **已完成（P3，2026-10）**

`why-ontology` 的总命题是"本体表示**决策**，不只是数据"，含四要素 Data/Logic/Action/Security，并要求：

- **决策数据**：*"the context surrounding a given decision, the different options evaluated,
  and the downstream implications of the committed choice"*
- **决策谱系**：*"of **when** a given decision was made, **atop which version of enterprise data**,
  and **through which application**, is automatically captured"*

**修复前**：`ai_action_log` 只记录"动作执行了、结果是 success/noop/pending"——**记录的是动作，不是决策**。

**P3 修复后**：新增 `ai_ont_decision` 等 4 张表，把官方定义的每一部分都落成真字段：

| 官方要求 | 我们的落地 | 是否自动捕获 |
|---|---|---|
| 决策上下文 | `ai_ont_decision_evidence`（9 种 kind，含**对象属性快照**） | 人工/Agent 登记 |
| 评估过的不同选项 | `ai_ont_decision_option`（含 score / 预计影响 / **落选原因** / 是否采纳） | 人工/Agent 登记 |
| 承诺选择的下游影响 | `ai_ont_decision_impact`（before/after 差分） | ✅ **执行前后自动做差** |
| 何时作出 | `made_at` / `decided_at` / `executed_at` | ✅ 自动 |
| 基于哪个数据版本 | `data_version`（取该对象类型已发布最高版本）+ `data_snapshot` | ✅ **自动解析** |
| 经由哪个应用 | `channel`（本体控制台/智能体/外部接口/自动化/导入） | ✅ 自动 |

另外三点：
- **决策成为本体一等公民**：`ensure_decision_object_type()` 把「决策」注册为对象类型（后备表 `ai_ont_decision`，16 个属性），
  于是决策能出现在对象探索里、可被关系引用、可被 Agent 查询、也能挂函数与派生属性。
- **执行复用动作层**：`execute_decision` 走 P0 的七道闸（提交条件/值类型/规则/副作用/审计），不另起一套。
- **"每个决策为下一个决策提供依据"**：依据里 `kind=decision` 并引用另一条决策编码，即形成决策→决策的谱系链；
  被引用的决策**不允许删除**（防断链）。

**仍然没做**：决策的**批量学习/蒸馏**（官方 "distilled into targeted principles called upon during agent prompting"）——
我们只做到了"记录与可追溯"，还没把决策历史喂回去优化 Agent。

---

## 4. 明确不做 / 已 sunset（不要误当缺口）

| 区域 | 页数 | 原因 |
|---|---|---|
| `object-monitors` | 12 | **官方已 Sunset**，建议迁到 Automate |
| `object-backend` / `object-databases` | 7 | 平台基础设施（微服务、对象存储引擎），非本栈目标 |
| `map` | 34 | 地理空间产品，与本体建模正交；除非确有 GIS 需求 |
| `ontology-sdk`（含 React） | 23 | 独立开发者产品；本栈已有 REST 接口可替代 |
| `foundry-rules` | 28 | 独立规则引擎产品（Taurus），与本栈"动作 + 参数 + 白名单"路线不同 |
| `enable-gotham-integration` / `marketplace-*` | 6 | 依赖 Palantir 生态，无对应物 |
| 我们已有替代品的页 | 4 | `export-import`（有 JSON 导入导出）、`cleanup`（有清理建议）、`restore-changes`（有版本恢复）、`save-changes`（有工作副本） |

---

## 5. 建议排期（按 价值/成本）

| 优先级 | 事项 | 对应官方页 | 成本 | 理由 |
|---|---|---|---|---|
| ~~P0~~ | ~~让 4 处字段真正生效~~ | `action-types` 3 页 + `value-types-permissions` | 低 | ✅ **已完成**（2026-10） |
| ~~P1~~ | ~~值类型约束接到写入路径~~ | `use-value-type` · `value-type-constraints` | 低 | ✅ **动作参数已接**；实例层 Writeback 待接 |
| ~~P2~~ | ~~函数能力升级：输入输出类型 + 对象上下文 + 调用外部/模型~~ | `functions` 53 页 · `ontology/models` | 中高 | ✅ **已完成**（2026-10）：四形态 + 33 内置函数 + 类型化签名 + 运行/校验 |
| ~~P3~~ | ~~决策数据 + 决策谱系~~ | `why-ontology` | 中 | ✅ **已完成**（2026-10）：4 张表 + 决策成为本体对象 + 影响自动捕获 + 谱系递归 |
| ~~P4~~ | ~~对象权限（本体资源 + 对象链接 + 行列级）+ 工具按调用者权限门控~~ | `object-permissioning` 5 页 | 中高 | ✅ **已完成**（2026-10）：两层授权 + 单元格级 + Agent 门控 + Check access |
| ~~P5~~ | ~~场景（scenarios）：动作效果沙箱预览再提交~~ | `vertex/scenarios-*` 3 页 | 中高 | ✅ **已完成**（2026-10）：编辑叠加沙箱 + 读叠加 + 单事务合并 + 对比 + 按执行上下文治理 |
| ~~P6~~ | ~~对象浏览器补：筛选器 UI、保存探索/列表、结果集图表~~ | `object-explorer` 5 页 | 中 | ⚠️ 部分：对象视图已可渲染/保存 |
| **P7** | 顶点补：保存视图、图模板、时间轴 | `vertex` 6 页 | 中高 | 图能力从"能看"到"能存能分享" |
| **P8** | 接口 link type 约束（目标须实现某接口） | `interfaces` 1 页 | 低 | 已有实现校验框架，扩展一类约束 |
| ~~P9~~ | ~~索引机制~~ | `object-indexing` 5 页 | 高 | ✅ **已完成**（2026-10）：真建库索引 + 状态机 + 5 分钟自动重试 |

---

## 6. 这份清单的局限（如实标注）

1. **271 个 ❌ 里大部分是 B 级判断**（依据 slug 推断，未读原文）。排期到具体某项时**必须再读该页原文**。
2. **页数 ≠ 重要性**。`map` 有 34 页但可能与我们无关；`submission-criteria` 只有 1 页却属于必须修的缺陷。第 5 节的排期已按价值而非页数排序。
3. 官方文档存在**自相矛盾之处**（前几轮研究已记录 7 处），实现应对照截图与实测而非纯文字。
4. 本清单只覆盖**本体产品族 361 页**。全站另有 2024 页属其它产品（数据集成、Workshop、模型、AIP 等），其中与本体的衔接（如在 Workshop 里用本体、在 AIP 里用本体）也落在上表"引用但未实现"的范围内。
5. 判定基于**当前代码状态**，不含任何尚在计划中的改动。
6. ✅/🟡/❌ 的切分在边界上有主观性（例如"能改但没有完整流程"我判 🟡）。**总数可核对（56+35+270=361），单项判断可讨论。**

---

## 7. 本文数字的自查（机器校验，可复现）

写完初稿后我用脚本对本文做过 5 项校验，发现并修正了 1 处错误：

| # | 校验项 | 结果 |
|---|---|---|
| 1 | 23 个区域的页数 vs 官方 sitemap | **全部相符**（6/9/9/40/27/53/9/15/18/27/12/11/5/28/34/11/7/5/5/5/2/19/4） |
| 2 | 合计是否自洽 | 361 = 56+35+270 ✅ |
| 3 | 各区域明细表 vs 汇总表 | 发现 **1 处不一致**：`functions` 明细标了 4 个 🟡，汇总误写 🟡3/❌50 → **已修正为 🟡4/❌49**（53 页不变） |
| 4 | ✅/🟡 的表格行逐格统计 vs 汇总 | **完全一致**（✅61 / 🟡31）——说明逐页判定与汇总无偏差 |
| 5 | 文档中出现的页名是否都真实存在 | 350 个反引号标识符中，25 个不在 sitemap；**逐一确认这 25 个全是我们自己的字段名/表名/函数名**（如 `submission_criteria`、`ai_action_log`、`validate_value`），**无编造官方页名** |

### 7.1 P0–P5 + A/B/C 完成后的计数变动

| 区域 | 变动 |
|---|---|
| `action-types` | ✅ 6 → **9**，🟡 5 → **2**（`rules` / `submission-criteria` / `side-effects-overview` 三项由 🟡 转 ✅） |
| `object-link-types` | ✅ 27 → **29**，🟡 8 → **7**，❌ 5 → **4**（`value-type-constraints` 🟡→✅、`value-types-permissions` ❌→✅） |
| `functions` | ✅ 0 → **11**，🟡 3 → **5**，❌ 50 → **37**（P2：四形态函数 + 类型化入参/出参 + 对象上下文） |
| `ontology` | ✅ 2 → **3**，🟡 2 → **1**（`why-ontology` 🟡→✅，P3） |
| `object-permissioning` | ✅ 0 → **3**，🟡 0 → **1**，❌ 5 → **1**（P4） |
| `vertex`（场景 3 页） | ✅ 1 → **4**，❌ 21 → **18**（P5） |
| `object-views` | ✅ 0 → **9**，🟡 1 → **3**，❌ 17 → **6**（A，含筛选器/共享/深链） |
| `object-indexing` | ✅ 0 → **3**，🟡 0 → **1**，❌ 5 → **1**（B） |
| `ontologies` | ✅ 0 → **2**，❌ 7 → **5**（C） |
| **合计** | ✅ 56 → **96**，🟡 35 → **37**，❌ 270 → **228** |

占比：**✅ 26.6% / 🟡 10.2% / ❌ 63.2%**
> 校验脚本用 PowerShell 正则解析本文并对照 `.research/palantir/all_urls.txt`，可重复执行。
> 注：❌ 的"表格行统计"（113）小于汇总（270），因为整块未实现的区域用**行内清单**而非表格呈现，符号未计入表格行——这是呈现方式差异，不是计数错误。

