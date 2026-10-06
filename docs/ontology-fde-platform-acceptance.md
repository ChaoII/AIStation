# 本体驱动 + AI Grounding + FDE 交付平台 — 整体验收清单（P0 → P3-⑥）

> 定位：把 AIStation 升级为 Palantir Foundry 式「本体驱动 + AI grounding + FDE 交付 + 治理」的数据/决策平台。
> 本清单汇总 P0→P3-⑥ 全部已交付能力、验收方式与状态。每项均经**后端接口 + 前端浏览器 + 截图**验证。

## 一、验收总览

| 阶段 | 主题 | 后端 | 前端 | 截图 | 状态 |
|------|------|------|------|------|------|
| P0 | 对象化建模 + resolve_object grounding + FDE 交付工作台 | ✅ | ✅ | ✅ | 通过 |
| P1 | Action 写回+审计 / 版本·血缘·影响·回滚 / 语义抽取→对象 | ✅ | ✅ | ✅ | 通过 |
| P2 | 影子运行/黄金标准 / 行业模板 / FDE 三角色 | ✅ | ✅ | ✅ | 通过 |
| P3-① | 数据连接中心 + 可视化管道 | ✅ | ✅ | ✅ | 通过 |
| P3-② | Workshop 无代码本体应用（看板/表单） | ✅ | ✅ | ✅ | 通过 |
| P3-④ | 完整血缘 + ABAC 权限（敏感字段管控） | ✅ | ✅ | ✅ | 通过 |
| P3-⑤ | 真正拉外部 ERP/CRM/MES 数据落库 | ✅ | ✅ | ✅ | 通过 |
| P3-⑥ | Agent Studio 无代码编排 + 试跑/工具链回放 | ✅ | ✅ | ✅ | 通过 |

## 二、后端接口回归（22/22 PASS）

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

## 四、前端主要页面（浏览器截图核实）

| 页面 | 说明 |
|------|------|
| 智能问数 `/ai/query` | 新会话/指标运营/数据源/历史问题/试试问/流式思考/工具链 |
| 指标运营抽屉 | 指标/术语/数据源/资产/推荐/示例/反馈/限额/工程配置/基准/图谱/本体/交付/动作/治理/管道/应用/权限（19 tab） |
| 治理 tab | 影响分析 + 版本历史 + 完整血缘卡片 |
| 权限 tab | ABAC 策略表格 + 敏感放行开关 |
| 管道 tab | 管道列表 + 运行 + 数据（落库弹窗） |
| 应用 tab | 对象应用列表 + 新建 + 预览（真实数据） |
| 智能体 `/ai/agent` | Agent 网格 + 两栏对话（composer）+ Studio 编排抽屉 + 试跑回放 |

## 五、运行与验收要点

- 后端：`cd backend && uv run main.py run --env=dev`（端口 8001）；插件控制器改动后需**冷重启**（`Get-Process python,uv | Stop-Process -Force` 后重启）。
- 前端：`cd frontend && pnpm run dev`（端口 5180）；hash 路由 `http://localhost:5180/web#/ai/query`。
- 登录：`admin / 123456`。
- 数据库：Postgres `aistation`；运行时建表 `ai_action / ai_action_log / ai_asset_version / ai_fde_proposition / ai_pipeline / ai_pipeline_run / ai_workshop_app / ai_access_rule / ai_pipeline_data_*`。
