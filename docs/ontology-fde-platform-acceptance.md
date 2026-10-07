# 本体驱动 + AI Grounding + FDE 交付平台 — 整体验收清单（P0 → P3-⑩）

> 定位：把 AIStation 升级为 Palantir Foundry 式「本体驱动 + AI grounding + FDE 交付 + 治理」的数据/决策平台。
> 本清单汇总 P0→P3-⑩ 全部已交付能力、验收方式与状态。每项均经**后端接口 + 前端浏览器 + 截图**验证。

## 〇、最终产品架构（Palantir Foundry 对照）

按 Foundry 分为「底座（数据准备 + 本体）」与「消费层（AIP / Agent 能力装配）」，问数作为 **Agent 能力**而非独立产品。

**AI 管理菜单（一级模块）**
| 菜单 | Foundry 对应 | 说明 |
|------|-------------|------|
| **AI 工作台** | 统一入口 | Foundry 支柱入口卡片（实时指标 + 进入） |
| **数据资产** | Semantic Layer / Data Assets | 资产目录 / 指标 / 术语 / 概念 / 图谱 / 语义抽取（底座） |
| **本体** | Ontology | 对象 / 属性 / Link / Action 强类型元模型（本体驱动） |
| **数据与集成** | Data Connection / Pipeline | 数据连接 + 数据管道（抽取/加工接入本体） |
| **无代码应用** | Workshop | 在对象上无代码构建看板/表单 |
| **治理** | Governance / Oversight | 驾驶舱 + ABAC + 数据质量 + 数据域 |
| **智能体** | AIP / Agent Studio | **能力装配（问数/接地/RAG/工具/技能/模型等开关）** |

**核心设计**：问数不再是独立模块，而是在创建/编排 Agent 时作为**能力开关**装配（Agent 卡片以徽标显示已装配能力）。平台底层只负责数据资产 / 本体 / 接入 / 治理等数据准备。

**本体（Ontology）即中枢，由一圈外围支撑/消费（Palantir 对齐）**
| 外围能力 | 状态 |
|---------|------|
| 对象/属性/Link/Action + Functions（本体计算函数） | ✅ |
| 连接 → 管道 → **真正写入本体对象表** | ✅ |
| 指标/术语/概念 + **问数注入本体语义**（`_ont_ctx_block`） | ✅ |
| **resolve 优先本体**（按对象/属性/Link 解析实例 + 关联邻居，`/objects/resolve`） | ✅ |
| **本体对象血缘 + 数据质量**（源头管道/下游/质量分，`/ontology/governance`） | ✅ |
| **ABAC 字段级 ACL**（本体属性 roles/敏感，接地按角色过滤） | ✅ |
| **本体变更留痕**（`/ontology/changelog`） | ✅ |
| **本体对象定义版本**（发布快照/列表/回滚，`/ontology/version/*`） | ✅ |
| **Agent 能力 = 本体工具**（能力注册/类型/description，Agent 从本体装配，勾选映射真实能力，运行时注入） | ✅ |
| **问数字段级 ACL**（`_ont_sql_violations` 拦截无权限本体敏感/受限属性，超管豁免） | ✅ |
| **数据源连接器 → 自动生成本体对象**（`/ontology/import-from-ds`，外部表结构→对象+属性+物化） | ✅ |
| Workshop / AIP / Agent | ✅ |

**问数/问答可见 grounding 溯源**：结果展示「使用本体 · 订单（ont_orders）」（检测 SQL 中本体表）。

**UI/UX 交付**：统一 PageHeader、能力装配卡片（实时装配流）、AI 工作台入口卡片、Agent 能力徽标、空态 `el-empty` 引导、加载骨架 `el-skeleton`、对话执行链可视化、白色卡片+灰间隔背景（对齐模型配置）、电脑端分页（`el-pagination` 固定底部）。

**核心设计（终稿）**：«Agent 的一切能力（问数/接地/知识库/技能/动作/函数）统一为「本体工具」——在本体登记、Agent 从本体装配、运行时真实调用；问数/接地/安全/治理全部以本体为单一事实源。»

**UI/UX 回归**：后端全量 **19/19 PASS**（本体对象/属性/Link/Action/函数/能力/留痕/版本/本体治理/resolve/连接器生成对象/governance/DQ/权限/域/指标/概念/管道/应用/智能体）。

**问数基准回归基线**（`scripts\run_query_benchmark.ps1`）：
- 快路径（20 题，指标语义）：语义精度 **100%**，命中率 100%，P50 141ms。
- NL2SQL（98 题，与金标数据级比对）：**94.9%**（历史最高；经「回退过度工程化 + 口径统一治理 + 示例」优化，91.4%→94.9%）；
- 分 tag 近全绿：**本体对象 100% / 本体黑话 100% / 用户 100% / 标注 100% / 窗口函数 100% / 算法任务 100% / 设备 100% / 调用日志 100% / 边缘事件 100% / 去重 100% / 合成 100% / 嵌套子查询 100% / 摄像头 100% / 单维统计 100%**；联表 93.3%、时间窗口 88.9%、多维报表 83.3%、训练 66.7%（剩余少数题 LLM 波动）。
- **关键经验（过度工程化教训）**：NL2SQL 精度上限 ≈93~95%，**"少即是多"**——叠加更多工具/上下文/规范甚至结构化输出均**实测负收益**（如结构化输出 93.9%→86.7%）。最佳配置 = **干净的 12 个自主工具（schema/fewshot/枚举/关联自主检索）+ `_extract_sql` + 口径统一（业务口径注入 schema 上下文）+ 示例**，让 LLM 在最少干涉下稳定发挥。可行工程化护栏：schema 自主检索、fewshot、自一致性、执行反馈、口径治理；**避免**不断叠加工具/长上下文/强制结构化。
- **Grounding 可观测**：问数结果返回「召回 schema（混合检索锁定的表/字段）」，前端展示「召回表」标签（悬浮显示字段）。

| UI/UX 项 | 位置 | 截图 |
|---------|------|------|
| AI 工作台（Foundry 支柱入口） | `/ai/workspace` | ✅ |
| 数据资产（PageHeader+目录+空态） | `/ai/asset` | ✅ |
| 本体（强类型建模+对象卡） | `/ai/ontology` | ✅ |
| 数据与集成（连接+管道） | `/ai/integration` | ✅ |
| 无代码应用（Workshop 应用） | `/ai/workshop` | ✅ |
| 治理（驾驶舱/权限/质量/域） | `/ai/governance` | ✅ |
| Agent Studio 能力装配（7 能力卡+装配流） | `/ai/agent` | ✅ |
| 对话运行态（执行链可视化+能力徽标） | `/ai/agent` | ✅ |

## 一、验收总览

| 阶段 | 主题 | 后端 | 前端 | 截图 | 状态 |
[Output truncated. Continue reading with offset: 9]
|------|------|------|------|------|------|
| P0 | 对象化建模 + resolve_object grounding + FDE 交付工作台 | ✅ | ✅ | ✅ | 通过 |
| P1 | Action 写回+审计 / 版本·血缘·影响·回滚 / 语义抽取→对象 | ✅ | ✅ | ✅ | 通过 |
| P2 | 影子运行/黄金标准 / 行业模板 / FDE 三角色 | ✅ | ✅ | ✅ | 通过 |
| P3-① | 数据连接中心 + 可视化管道 | ✅ | ✅ | ✅ | 通过 |
| P3-② | Workshop 无代码本体应用（看板/表单） | ✅ | ✅ | ✅ | 通过 |
| P3-④ | 完整血缘 + ABAC 权限（敏感字段管控） | ✅ | ✅ | ✅ | 通过 |
| P3-⑤ | 真正拉外部 ERP/CRM/MES 数据落库 | ✅ | ✅ | ✅ | 通过 |
| P3-⑥ | Agent Studio 无代码编排 + 试跑/工具链回放 | ✅ | ✅ | ✅ | 通过 |
| P3-⑦ | 数据质量（DQ）健康度 | ✅ | ✅ | ✅ | 通过 |
| P3-⑧ | DQ 质量预警 + 血缘影响联动 | ✅ | ✅ | ✅ | 通过 |
| P3-⑨ | 数据域隔离（多租户） | ✅ | ✅ | ✅ | 通过 |
| **P3-⑩** | **治理驾驶舱（治理总览首页）** | ✅ | ✅ | ✅ | 通过 |

## 二、后端接口回归（26/26 PASS）

登录 `admin/123456` 后以 `Bearer token` 调用，全部返回 `code=0`：

| 接口 | 结果 |
|------|------|
| `/ai/query/assets/list`（数据资产，97 项） | PASS |
| `/ai/query/assets/objects`（业务对象，19 项） | PASS |
| `/ai/query/assets/train_tasks/lineage`（完整血缘） | PASS |
| `/ai/query/assets/train_tasks/columns`（字段，27） | PASS |
| `/ai/query/assets/train_tasks/versions`（版本，5） | PASS |
| `/ai/query/assets/train_tasks/impact`（影响分析） | PASS |
| `/ai/query/action/list` / `/action/logs`（动作+审计） | PASS |
| `/ai/query/fde/list`（交付命题） | PASS |
| `/ai/query/pipeline/list`（管道，2） | PASS |
| `/ai/query/workshop/list`（对象应用） | PASS |
| `/ai/query/access/list`（ABAC 策略） | PASS |
| `/ai/query/dq/overview`（质量总览） | PASS |
| `/ai/query/dq/alert`（质量预警+影响联动） | PASS |
| `/ai/query/domain/list` / `/domain/objects`（数据域） | PASS |
| `/ai/query/industry/templates`（行业模板，3） | PASS |
| `/ai/query/datasources/list`（数据源） | PASS |
| `/ai/query/metrics/list`（指标，7）/ `terms/list`（术语，10）/ `concepts/list`（概念，14） | PASS |
| `/ai/query/assets/kg/unified`（统一图谱） | PASS |
| `/ai/query/fewshots/list`（示例，35）/ `stats` / `settings` | PASS |
| `/ai/agents/list`（智能体） | PASS |

单元测试：`backend/tests/test_query.py` **40 passed**。

## 三、逐阶段验收明细

### P0 — 对象化建模 / grounding / FDE 交付工作台
- **对象化建模**：`/ai/query/assets/objects` 返回 19 个业务对象；对象含 `object_enabled / key_col / name_col / icon`，可在「本体」tab 配置。
- **resolve_object grounding**：把「摄像头/订单」+ 关键值解析为真实对象及关联邻居，注入模型上下文。
- **FDE 交付工作台**：命题 + 五步单（业务翻译官/数据本体工程师/应用交付工程师）在「交付」tab 编辑查看。

### P1 — Action 写回+审计 / 治理
- **Action**：动作定义支持**审批门禁 + 字段白名单**，执行写回并记 `ai_action_log` 审计。
- **治理**：资产版本历史（可见 5 个版本）+ 逐版本**回滚**；影响分析（用到的指标/入向关联/对象链接）。
- **语义抽取→18 对象**：`/assets/extract-objects` 自动识别业务对象并消歧。

### P2 — 影子运行 / 行业模板 / FDE 三角色
- **影子运行/黄金标准**：`shadow_check` 比对实际结果与黄金标准、容差、通过率。
- **行业模板**：ISA-95（制造业）、GMP（制药）、通用业务，可一键 `industry/apply` 预建标准概念。
- **FDE 三角色**：业务翻译官 / 数据本体工程师 / 应用交付工程师分工。

### P3-① — 数据连接中心 + 可视化管道
- **数据连接中心**：注册外部数据源（Postgres/MySQL/SQLite/API），测试连接 + 同步结构（本次同步 108 表）。
- **管道**：源连接 → 源表 → 列映射 → 目标对象；运行同步映射列并存血缘。

### P3-② — Workshop 无代码本体应用
- 选择业务对象 + 视图类型（看板/表单）+ 展示列；**预览读取真实对象数据**。
- 实测：`摄像头监控看板` 应用预览返回真实行 `E2E 摄像头 0914144956 / OFFLINE / MAIN`。

### P3-④ — 完整血缘 + ABAC 权限
- **完整血缘**：`/assets/{table}/lineage` 串起 表→字段/指标/概念/依赖对象/入向管道。
- **ABAC**：`ai_access_rule`（属性 role/dept/domain + 值 + 允许对象 + 敏感放行）；`resolve_entity_object` 按策略剥离敏感字段，超管豁免。
- 实测：`train_tasks` 血缘返回 27 字段 + 指标 + 概念 + 依赖对象；权限 tab 建「生产部敏感放行」策略。

### P3-⑤ — 真正拉外部 ERP/CRM/MES 数据
- `run_pipeline` 按 `source_connection`（数据源 id）走 executor **真实连库**拉数并物化到 `ai_pipeline_data_{id}`。
- 实测：注册「MES生产库(Postgres)」→ 建管道（源=外部库）→ 运行拉取 **55 行**真实数据 → `pipeline/data` 查看落库数据（id/equip_name/status/location/device_type）。
- 前端管道行新增「数据」按钮查看落库结果；源连接改为「本系统/外部数据源」下拉。
- **顺带修复**：数据源「同步结构/表结构」两端点此前 404（误用类引用），已改为正确委托。

### P3-⑥ — Agent Studio 无代码编排 + 试跑
- **编排画布**：左侧积木面板（模型/提示词/工作流/工具/知识库/技能/问数）+ 中央流水线；点击积木加入画布，块内可换模型/数据源、标签可删。
- **保存落库**：汇总为 agent 绑定（tool_ids/knowledge_ids/skill_ids/query/…）经更新接口持久化。
- **试跑/工具链回放**：输入问题流式试跑，回放调用步骤（`1. ai_query`）+ 思考 + 回答。
- 实测：问数助手编排绑定模型(4)+知识库(4)+问数；试跑「一共有多少个摄像头？」回放 `ai_query` 并答「当前共有 1 个摄像头」。

### P3-⑦ — 数据质量（DQ）健康度
- **dq_run**：对业务对象扫描 完整性（名称列空值率）/ 唯一性（name、主键去重占比）/ 新鲜度（最新更新时间距今，无时间列记 0），综合分 `0.4*完整性 + 0.3*唯一性 + 0.3*新鲜度`。
- **dj_overview**：从 `ai_dq_report` 缓存读取（直查对象表，66ms，稳定不超时），未扫描对象标记。
- 实测：19 对象平均健康分 77.9、健康 6 / 风险 1；问题如「无更新时间列，新鲜度未知」「名称列 name 有 98 条重名」。

### P3-⑧ — DQ 质量预警 + 影响联动
- **dq_alert**：风险对象(健康分<60) → 血缘下游影响（依赖对象 / 指标 / 概念），组装预警清单。
- 实测：「质量预警：2 个对象健康分低于 60」；`合成`(59.8) 与 `mes_equipment`(0)，带下游影响 + 问题明细。

### P3-⑨ — 数据域隔离（多租户）
- `ai_domain`（域名+编码+描述+对象+成员用户）；`domain/objects` 按域分组、未归属对象单独列出。
- 前端「数据域」tab：域卡（对象/成员）+ 未归属对象 + 隔离说明（成员仅访问其所在域对象，ABAC 结合 domain 在解析/问数时过滤）。
- 实测：「生产域(prod)」对象 3（训练任务/告警/摄像头）、成员 `#1`；未归属 16。

### P3-⑩ — 治理驾驶舱（治理总览首页）
- **governance_overview**：一次聚合 对象/数据源/管道/动作/审计/ABAC 策略/数据域/智能体/对象应用/指标/术语/概念/质量/预警/最近管道运行。
- 前端「治理驾驶舱」全屏抽屉：8 个统计卡 + 质量环形仪表盘（健康/预警）+ 质量预警清单 + 资产语义描述表 + 最近管道运行表。
- 实测：对象 19/源 1/管道 2/策略 1/域 1/智能体 1/审计 1/健康分 77.9；预警 2（mes_equipment 0、合成 59.8）。
- **性能**：`_objects_light`（直查 `ai_query_assets` 避免 `list_assets` N+1），`dq_alert` 轻量血缘，governance_overview 从 **9s → 341ms**。

## 三、治理闭环（Oversight & Governance）

| 治理支柱 | 载体 | 阶段 |
|---------|------|------|
| 血缘 / 版本 / 影响 / 回滚 | 治理 tab | P1 / P3-④ |
| ABAC 权限（敏感字段管控） | 权限 tab | P3-④ |
| 数据质量（DQ）+ 预警联动 | 数据质量 tab | P3-⑦⑧ |
| 多租户 / 数据域隔离 | 数据域 tab | P3-⑨ |
| 真实数据接入 + 血缘 | 管道/数据源 | P3-①⑤ |

## 四、前端主要页面（浏览器截图核实）

| 页面 | 说明 |
|------|------|
| 智能问数 `/ai/query` | 新会话/指标运营/数据源/历史问题/试试问/流式思考/工具链 |
| 指标运营抽屉 | 指标/术语/数据源/资产/推荐/示例/反馈/限额/工程配置/基准/图谱/本体/交付/动作/治理/管道/应用/权限/数据质量/数据域（22 tab） |
| 治理 tab | 影响分析 + 版本历史 + 完整血缘卡片 |
| 权限 tab | ABAC 策略表格 + 敏感放行开关 |
| 管道 tab | 管道列表 + 运行 + 数据（落库弹窗） |
| 应用 tab | 对象应用列表 + 新建 + 预览（真实数据） |
| 数据质量 tab | 健康分仪表盘 + 对象进度条 + 问题明细 + 质量预警（下游影响）+ 逐对象/全量扫描 |
| 数据域 tab | 域卡（对象/成员）+ 未归属对象 |
| 治理驾驶舱 | 全屏抽屉：统计卡 + 质量环形仪表盘 + 预警 + 语义资产 + 管道运行 |
| 智能体 `/ai/agent` | Agent 网格 + 两栏对话（composer）+ Studio 编排抽屉 + 试跑回放 |

## 五、运行与验收要点

- 后端：`cd backend && uv run main.py run --env=dev`（端口 8001）；插件控制器改动后需**冷重启**（`Get-Process python,uv | Stop-Process -Force` 后重启）。
- 前端：`cd frontend && pnpm run dev`（端口 5180）；hash 路由 `http://localhost:5180/web#/ai/query`；`VITE_TIMEOUT=10000`。
- 登录：`admin / 123456`。
- 数据库：Postgres `aistation`；运行时建表 `ai_action / ai_action_log / ai_asset_version / ai_fde_proposition / ai_pipeline / ai_pipeline_run / ai_workshop_app / ai_access_rule / ai_dq_report / ai_domain / ai_pipeline_data_*`。
- 性能要点：`dq/overview` 走缓存直查（避免慢 `list_objects`）；DQ/预警/域改为切 tab 按需加载，避免挂载并发挤占连接池（此前 `QueuePool` 会因并发+OperationLogRoute 写日志耗尽）。
