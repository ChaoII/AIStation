# 「数据与集成」治理 Tab 拆出为独立页面 设计文档

> 所属：AI 集成开放平台 / 数据与集成
> 日期：2026-10-29
> 状态：设计稿（待审）

## 1. 背景与问题

「数据与集成」（菜单 `AiIntegration`，`/ai/integration`）当前是「智能问数」目录下的一个子菜单，页面 `module_ai/integration/index.vue` 顶部有 **10 个 tab**：

`表与字段 / 管道 / 指标 / 术语 / 业务概念 / 示例工程 / 数据关系图 / 筛选规则 / AI 辅助建模 / 治理`

其中「治理」tab 内部又嵌入 `GovernancePanel.vue`，**再带 8 个子 tab**：

`驾驶舱 / 权限 / 数据质量 / 数据域 / 本体对象 / 表级写回（旧版） / 交付命题 / 生命周期`

问题（用户反馈：**"tab 页面里面又套着 tab"**）：

1. **信息架构混乱**：前 9 个顶层 tab 是"围绕某个选中数据源做建模"的操作流（依赖左侧数据源列表），而「治理」是横跨全局、**不依赖具体数据源**的监管面板。把全局监管塞进操作流里，既打断主线，又让治理的 8 个子 tab 挤在右侧窄列。
2. **子 tab 冗余**：8 个治理子 tab 中，有 3 个与顶层功能/彼此重叠或已过时（详见 §3）。

## 2. 目标

- 把「治理」从 `integration/index.vue` 的顶层 tab 中**拆出**，提升为「智能问数」目录下的**独立子菜单页面**（与「数据与集成」「智能问数」平级），路由 `/ai/governance`。
- 治理独立成页后，子 tab 收敛为 **5 个核心**：驾驶舱 / 权限 / 数据质量 / 数据域 / 交付命题。
- 顶层 tab 只剩 9 个建模操作项，主线清晰。

## 3. 治理子 tab 精简依据

| 子 tab | 处理 | 依据 |
|--------|------|------|
| 驾驶舱 | 保留 | 治理总览/体检报告入口（`/governance/overview` + `report`） |
| 权限 | 保留 | ABAC 策略/矩阵/沙箱，治理独有能力（`/ai/abac/*`） |
| 数据质量 | 保留 | DQ 健康分/预警，治理独有（`/ai/dq/*`） |
| 数据域 | 保留 | 数据域管理（`/ai/domain/*`） |
| 交付命题 | 保留 | 五步交付/影子校验（`/fde/*`），业务闭环 |
| **本体对象** | **删除** | 血缘/质量只读视图，与顶层「数据关系图」（血缘）+「数据质量」（健康分）重复。血缘归「数据关系图」，质量归「数据质量」。 |
| **表级写回（旧版）** | **删除** | 代码注释自标"**旧版**…新动作请到 本体 → 动作类型"。已被本体「动作类型」取代。 |
| **生命周期** | **删除** | 纯只读对象状态计数看板（对象总数/发布/草稿/敏感/血缘），信息基本被「驾驶舱」（全局计数+DQ）+「数据质量」覆盖，无独特价值。 |

> 删除后治理页子 tab = 驾驶舱 / 权限 / 数据质量 / 数据域 / 交付命题。

## 4. 方案设计

### 4.1 前端：新建治理独立页面

- 新增 `frontend/src/views/module_ai/governance/index.vue`。
  - 复用 `GovernancePanel.vue` 作为页面主体（`<GovernancePanel />`）。
  - 外层套统一白面板外壳（照抄 `market-shell` 规范 / `app-container` 满高 flex + `el-card shadow="never"` 铺满），符合 AGENTS.md「页面外壳与框架同构」。
  - 需要把 `GovernancePanel` 的 `.gp-wrap` 从 `padding:12px` 调整为适配全宽，或在 `index.vue` 里用非 scoped 类覆盖。

### 4.2 前端：`integration/index.vue` 移除「治理」tab

- 删除 `<el-tab-pane :label="t('ai_workflow.ig_governance')" name="gov">` 及其内 `<GovernancePanel />`。
- 删除 `import GovernancePanel from "./components/GovernancePanel.vue"`（约 L1640）。
- `tab` 初始值保持 `"table"`；由于 `tab` 不再可能等于 `"gov"`，右列 `:sm="tab === 'gov' ? 24 : 16"` 等三元判断（L65-67）简化为恒常量（去掉 `gov` 分支）。

### 4.3 前端：`GovernancePanel.vue` 精简子 tab

删除 3 个 tab 分支及其关联 script：

- **`ontgov`（本体对象）**：删 `<el-tab-pane :label="t('ai_workflow.ig_govOnt')" name="ontgov">…`（约 L393-491）；script 删 `loadOntGov`（L1424）、`ontGov` 数据、`onTab` 的 `ontgov` 分支。
- **`action`（表级写回旧版）**：删 `… name="action">…`（约 L494-637）；script 删 `loadAction`（L1463）、`pendingActions`/`actionList`/`actionLogs` 数据及 approbation 相关 dialog/函数、`onTab` 的 `action` 分支。
- **`lifecycle`（生命周期）**：删 `… name="lifecycle">…`（约 L729-791）；script 删 `loadLifecycle`（L1402）、lifecycle 数据、`onTab` 的 `lifecycle` 分支。

`onTab` 收敛为：`overview / access / dq / domain / fde` 五个分支。

### 4.4 后端：菜单注册

- `backend/app/scripts/init_app.py` 的 `QUERY_GROUP_MENUS` 增加一条：
  `("治理", "AiGovernance", "/ai/governance", "module_ai/governance/index", 5, "el-icon-DataBoard")`
  - `order=5`（现有 1-4 被 数据与集成/智能问数/问数评测/报表模板 占用；治理排在「数据与集成」之后、不与既有 order 冲突）。
  - 权限沿用 `permission="module_ai:query:ask"`（QUERY_GROUP 子菜单统一此码，见 init_app.py L937/L951，无需新权限码）。
  - 幂等注册（`_ensure_ai_menus` 对 `QUERY_GROUP_MENUS` 循环 upsert，见 L921-959），存量库重启即生效，无需手工 INSERT。

### 4.5 接口

全部复用现有治理接口（均在 `module_ai/query` controller/service），无需新增/改造：
- `GET /ai/query/governance/overview`、`GET /ai/query/governance/report`
- `GET /ai/query/objects/lifecycle`（删除后不再被前端调用，保留接口不动）
- `GET /ai/query/ontology/governance`（删除后不再被前端调用，保留接口不动）
- `/ai/abac/*`、`/ai/dq/*`、`/ai/domain/*`、`/ai/query/fde/*`

> 只删前端展示，**不删后端接口**（避免影响其它消费方/测试，YAGNI 反向——减少破坏面）。

## 5. 影响面与风险评估

| 项 | 影响 |
|----|------|
| 前端新增页面 `governance/index.vue` | 新增，无破坏 |
| `integration/index.vue` 删 tab + 简布局 | 顶层 tab 少一个，左栏恒显示 |
| `GovernancePanel.vue` 删 3 子 tab | 组件被新治理页复用；原 integration 恰好也删了引用 |
| `init_app.py` 加菜单 | 幂等，重启生效 |
| i18n | 删除的子 tab key（`ig_govOnt`/`ig_govAction`/`ig_govLifecycle` 系列）可保留在语言文件（避免动多语言），仅不再引用 |

**风险点**：
- `GovernancePanel.vue` 删分支时需同步删 `onTab` 分支 + 数据 + 函数，避免残留未使用引用触发 lint。
- 治理页独立后，`GovernancePanel` 需在 `index.vue` 中包白面板外壳（原 `.gp-wrap` 仅有 `padding:12px`，独立成页时要铺满）。

## 6. 验收标准

1. 「数据与集成」顶部 tab 只剩 9 个（无「治理」），左数据源栏恒显示。
2. 侧边栏「智能问数」目录下新增「治理」子菜单，点击进入 `/ai/governance`，整页白面板铺满（非 scoped 类），与框架同构。
3. 治理页子 tab = 驾驶舱 / 权限 / 数据质量 / 数据域 / 交付命题，5 个。
4. 治理页各子 tab 数据正常（复用现有接口）。
5. 无明显残留引用/lint 错误（ruff 前端 `vue-tsc` + 后端 `ruff`）。
6. 空闲回归：`integration`/`query`/`governance` 相关既有用例通过。

## 7. 非目标

- 不改后端治理接口（只删前端展示）。
- 不引入新的权限体系，沿用 `module_ai:query:*`。
- 不动「数据与集成」其它 9 个 tab 的内容。
