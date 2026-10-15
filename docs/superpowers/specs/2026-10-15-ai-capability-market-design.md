# AI 能力市场设计（工具 / 技能 / MCP / 插件）

> 日期：2026-10-15 ｜ 状态：待评审 ｜ 范围：后端 plugin/module_ai + 前端 module_ai

## 1. 背景与目标

平台已有智能体（Agent）、技能（Skill）、零代码 HTTP 工具（Tool）、AI 应用、工作流等能力，
但缺少统一的**能力市场**：用户无法发现/安装/维护/分享能力资产，也无法使用 MCP 与 Python 代码工具。

本次建设目标：

1. **市场**：统一的 AI 能力市场，商品四类——工具（Tool）、技能（Skill）、MCP 服务器、AI 能力插件（Plugin）；
   首页样式参考「技能市场」：顶部精选卡片 + 分类/类型筛选 + 商品网格。
2. **自定义工具**：新增 **Python 代码工具**（受限沙箱执行），保留现有零代码 HTTP 工具。
3. **MCP 能力**：新增 MCP 服务器配置（stdio / sse / streamable-http），Agent 可绑定并使用其工具。
4. **安装**：用户可从市场安装（下载）任意资产到「我的资产」，安装后可集成进自己的 Agent。
5. **提交与审核**：个人维护自己的资产，可**提交分享到市场**（管理员审核通过后公开）。
6. **用户间分享**：可将自己的资产（或其市场条目）**分享给指定用户**，接收方确认后获得该资产。

## 2. 范围边界（YAGNI）

**做**：四类资产统一市场、Python 工具、MCP 配置与运行时接入、安装/收藏、提交-审核、点对点分享、
Agent 绑定 MCP 与市场资产、管理员审核页、市场/我的/分享给我/审核四个前端页面、权限控制。

**不做**（明确排除）：
- 支付/订阅/积分；商品评论；版本历史（仅保留 `version` 展示字段）；
- 平台代码级插件（`module_*` 目录式插件）的安装/卸载（仍需部署重启，市场仅作 AI 能力插件）；
- 跨租户市场（市场资产为**全租户公开**，由管理员管控；个人资产遵循租户隔离）；
- 沙箱外的任意代码执行（Python 工具仅受限环境）。

## 3. 现状与差距

| 能力 | 现状 | 差距 |
|------|------|------|
| Agent | `ai_agents`，绑定 `tool_ids`(工具名数组)/`skill_ids`(技能id)/`workflow_id`/`knowledge_ids`/`capabilities` | 无 MCP 绑定列；运行时无 MCP 装配 |
| 技能 | `ai_skills`，广场卡片（分类/精选/安装数），仅文本注入 system prompt | 无发布/审核/分享；`skill_type=custom` 无执行器 |
| 工具 | `ai_tools`（builtin/http），`TOOL_REGISTRY` 内置工具；Agno 精选目录 `AGNO_CATALOG` | 无 Python 代码工具 |
| MCP | 完全无实现；agno 3.0.6 原生支持（需 `mcp`+`fastmcp` 依赖） | 需装依赖、建表、配置页、运行时接入 |
| 插件 | `GET /ai/query/plugins/list` 硬编码 5 条 AIP 插件声明 | 无表、无安装、无执行 |
| 分享 | 工作流匿名 token、本体角色共享 | 无用户点对点分享 |
| 审核 | `ai_action_log` 状态机（pending/approved/rejected）可参考 | 无「发布-审核」统一机制 |

## 4. 架构总览

### 4.1 核心原则：市场资产 ⊂ 真实表，安装 = 复制

- 市场是**入口/橱窗**，不是存储。每个市场商品对应一份真实资产记录：
  - 工具 → `ai_tools`（名称唯一，Agent 按工具名绑定，运行时走现有 `dispatch_tool`）
  - 技能 → `ai_skills`（Agent 按 id 绑定）
  - MCP → 新表 `ai_mcp_servers`（Agent 按 id 绑定，新增 `ai_agents.mcp_ids`）
  - 插件 → 新表 `ai_plugins`（Agent 按 id 绑定，运行时按 `plugin.key` 分发执行器）
- **安装 = 把市场商品的 payload 复制成一份自己的真实记录**（`ai_tools`/`ai_skills`/`ai_mcp_servers`/`ai_plugins`），
  安装计数 +1。这样 Agent 绑定/运行时**零侵入**（除 MCP 需新增装配）。
- **提交市场 = 把自己的真实记录快照为市场商品**（status=pending），管理员审核通过后公开。

### 4.2 统一市场表（一条表，四类型）

`ai_market_items`（`ModelMixin` + 手工 owner 字段）：

| 字段 | 类型 | 说明 |
|------|------|------|
| asset_type | String(16) | `tool` / `skill` / `mcp` / `plugin` |
| name | String(128) | 商品名（同类型内唯一，未审核不冲突校验放业务层） |
| description | Text | 描述 |
| icon | String(255) | 图标 URL 或内置图标 key |
| category | String(32) | 市场分类（与前端分类 tabs 对齐） |
| tags | JSONB | 标签数组 |
| version | String(16) | 版本（展示） |
| owner_id | Integer | 提交人（内置官方资产为 NULL） |
| is_official | Boolean | 平台内置（管理员可打标） |
| featured | Boolean | 精选（管理员可打标） |
| status | String(16) | `draft` / `pending` / `approved` / `rejected` / `offline` |
| payload | JSONB | 真实资产快照（按 asset_type 不同结构，见 5.3） |
| source_id | Integer | 提交时来源真实记录 id（仅记录，不强制同步） |
| install_count / favorite_count | Integer | 冗余统计 |
| audit_remark | String(255) | 审核意见 |
| audit_user / audit_time | Integer + DateTime | 审核人/时间 |

关联表：

- `ai_market_relations`：`(user_id, item_id, kind)`，kind ∈ `installed` / `favorited`（安装/收藏关系 + 防重复）
- `ai_market_shares`：`(item_id, from_user_id, to_user_id, status, message, created_time)`，
  status ∈ `pending` / `accepted` / `rejected`

### 4.3 个人资产与市场关系状态机

```
个人资产(真实表) --提交--> market pending --管理员通过--> approved --(公开可安装)
                                     |--驳回--> rejected（可改后重提）
市场商品 --下架--> offline
安装：approved 商品 --install--> 复制为我的真实资产 + installed 关系
分享：我的市场商品/personal资产 --share 给 user--> pending --接收--> 复制为对方资产 + accepted
```

### 4.4 权限模型

权限码（`module_ai:market:*`，沿用项目 `权限码:动作` 体系，注册进 sys_menu 权限）：

| 权限码 | 说明 |
|--------|------|
| `module_ai:market:query` | 浏览市场（所有登录用户） |
| `module_ai:market:install` | 安装/收藏 |
| `module_ai:market:submit` | 提交市场 / 管理自己的资产提交 |
| `module_ai:market:share` | 点对点分享 / 接收分享 |
| `module_ai:market:review` | 审核（仅管理员角色授予） |

- 管理员判定：`is_superuser` 或持有 `module_ai:market:review` 权限（沿用 `AuthPermission` 依赖）。
- 数据隔离：个人「我的资产」按 `created_id` 过滤（现有表有 UserMixin 但未使用，本次补上按 created_id 过滤）；
  市场公开数据所有租户可见；`ai_market_shares` 仅 from/to 双方可见。

## 5. 各模块详细设计

### 5.1 自定义 Python 工具（新）

- `ai_tools.kind` 增加值 `script`；新增列 `code`（Text，Python 源码）、`timeout`（Int，默认 10s）。
- **沙箱**（`app/plugin/module_ai/tools_catalog/script_executor.py`）：
  1. AST 白名单校验：禁止 `Import/ImportFrom`（白名单 `json/math/re/datetime/random/statistics/collections/itertools/functools/typing`）；
    禁止访问任何 `__*__`（dunder）、`eval/exec/compile/open/__import__/getattr(动态)`；
    禁止 `with`/`async`/`await`/`lambda`（限制复杂度）；禁止属性 `open/read/write` 敏感调用。
  2. 受限命名空间：`builtins` 精简白名单（len/str/int/float/bool/list/dict/tuple/set/range/enumerate/zip/map/filter/sorted/sum/min/max/abs/round/print→logger、type、isinstance、Exception 等）；
  3. 指令计数超时：`sys.settrace` 统计行指令，超 `timeout` 抛错（Windows 无 signal.alarm，需用 trace 或线程 + 检查，选 trace）；
  4. 约定：脚本通过 `def run(args: dict) -> dict` 暴露入口，返回值 JSON 可序列化。
- 接口：`POST /ai/tools` 支持 `kind=script`；新增 `POST /ai/tools/{id}/test-script`（试运行）；`GET /ai/tools` 列表带 kind 过滤。
- 权限：创建/编辑 script 工具额外要求 `module_ai:tool:create` + 页面明示「代码工具在服务器受限环境执行」；
  管理员可禁用某用户的 script 工具（`enabled` 外，加 `script_allowed` 全局开关配置，默认开）。

### 5.2 MCP（新）

- 新表 `ai_mcp_servers`（`ModelMixin, UserMixin`）：`name`(唯一)、`transport`(`stdio`/`sse`/`streamable-http`)、
  `command`+`args`(JSONB)+`env`(JSONB)（stdio）、`url`（sse/http）、`headers`(JSONB)、`auth_type`(`none`/`bearer`/`custom`)、
  `enabled`、`description`。
- `ai_agents` 新增列 `mcp_ids`（JSONB list[int]）——Alembic 迁移。
- 运行时装配（`assistant/agno_service.py` + `agno_tools/agent_factory.py`）：
  - `build_agent` 接收 `mcp_tools: list[agno.tools.mcp.MCPTools]`；
  - agent run 前按 `agent.mcp_ids` 加载服务器配置 → 创建 `MCPTools`（lazy connect）→ 传给 `build_agent`；
  - run 结束后 `close()` 断开（stdio 子进程回收）。
- 依赖：`mcp>=2.1.0,<3.0.0`、`fastmcp>=4.0.0,<5`（agno 3.0.6 已声明该区间；按 AGENTS.md 走清华镜像安装并更新 pyproject/uv.lock，提交信息注明）。
- 前端：`/ai/mcp` 管理页（列表 + 弹窗表单）；Agent 表单加 MCP 多选。

### 5.3 市场 payload 结构（按 asset_type）

| 类型 | payload |
|------|---------|
| tool | `{ kind: "script"\|"http", code?, method?, url?, headers?, params_schema? }` |
| skill | `{ content, skill_type, category }` |
| mcp | `{ transport, command?, args?, env?, url?, headers?, auth_type? }` |
| plugin | `{ key, label, kind, config_schema?, entry? }` |

说明：插件为「AI 能力插件」——内置处理器注册表（web_fetch/table_export/email_send/report_generate/data_pipeline），
市场商品绑定 `key`；安装后 `ai_plugins` 记录 `key`，Agent 运行时按 key 启用处理器（web_fetch/download 复用现有实现；
未实现的 key 仅允许声明并给出「能力未实现」提示，不阻塞市场功能上线）。

### 5.4 API 一览（统一 prefix `/ai/market`，权限按 4.4）

| 接口 | 说明 |
|------|------|
| `GET /ai/market/home` | 首页聚合（精选 + 推荐 + 分类列表） |
| `GET /ai/market/items` | 列表（type/category/keyword/status=approved/分页） |
| `GET /ai/market/items/{id}` | 详情 |
| `POST /ai/market/items/{id}/install` | 安装（复制 payload → 真实表） |
| `POST /ai/market/items/{id}/favorite` / `DELETE .../favorite` | 收藏/取消 |
| `GET /ai/market/mine` | 我的资产（真实表聚合：工具/技能/MCP/插件，含各自 market 状态） |
| `POST /ai/market/submit` | 提交我的资产为市场商品（body: asset_type+source_id+payload 快照）→ pending |
| `POST /ai/market/items/{id}/withdraw` | 撤回（approved → offline；pending → draft） |
| `GET /ai/market/shares?dir=in\|out&status=` | 分享收/发列表 |
| `POST /ai/market/shares/share` | 发起分享（item_id, to_user_id, message） |
| `POST /ai/market/shares/{id}/accept` / `reject` | 接收（复制资产）/拒绝 |
| `GET /ai/market/review/list` | 待审核列表（review 权限） |
| `POST /ai/market/review` | 审核通过/驳回（body: id, action: approve/reject, remark） |
| `POST /ai/market/items/{id}/feature` | 精选/取消（review 权限） |

MCP 接口 prefix `/ai/mcp`：标准 CRUD + `POST /ai/mcp/{id}/test`（连接探测）。
自定义工具：`POST /ai/tools/{id}/test-script`（试运行）。

### 5.5 前端页面（参考技能市场截图）

- `/ai/market`（能力市场，替换/并列现有技能广场入口）：
  - 顶部「精选能力」：大卡片横排（图标+名称+描述+安装量+收藏+「+ 安装」角标）
  - 类型 tabs：全部 / 工具 / 技能 / MCP / 插件；分类 tabs（对齐内容分类：办公协同/开发工具/效率工具/内容创作/信息资讯/教育学习/数据分析/网站部署/生活服务/商业运营/知识与学习 等，用 `category`）
  - 商品网格 4 列：图标+名称+描述+安装/收藏数+「+」按钮；点击开详情抽屉（描述/版本/作者/标签 + 安装/收藏）
- `/ai/market/mine`（我的资产）：类型 tabs + 列表（名称/分类/版本/启用/市场状态 tag/操作：编辑、提交市场、分享给用户、删除）
- `/ai/market/shared`（分享给我）：待处理/已处理 tabs，接收/拒绝
- `/ai/market/review`（审核中心，review 权限）：待审核/已审核 tabs，通过/驳回 + 意见
- `/ai/mcp`：MCP 服务器 CRUD 页（列表 + 弹窗：名称/传输方式/命令/URL/鉴权/启用 + 测试连接按钮）
- 工具管理页（`module_ai/tool`）：增加「Python 工具」表单（代码编辑器 + 试运行 + 错误提示），与 HTTP 工具并存
- Agent 表单：新增 MCP 多选（`mcp_ids`）；工具/技能多选不变（市场安装后自动出现在可选列表）
- 菜单：AI 管理下新增「能力市场」「MCP 管理」；`sys_menu.json` 种子 + 存量库需管理员用菜单管理 UI 添加（文档说明）

### 5.6 安全设计

- 脚本工具：AST 白名单 + 受限 builtins + 指令计数超时 + 非超级用户创建需 `script_allowed` 开关；日志记录每次执行（输入/输出截断）。
- MCP：仅连接用户配置的地址（存在 SSRF 风险 → 禁止内网段？MVP 不做网络白名单，页面提示「仅添加可信服务器」；鉴权头支持 bearer/custom）。
- 分享/审核：全部走 `AuthPermission`；分享仅 from/to 可见；安装复制 payload 时校验 status=approved。
- 所有写操作沿用 `OperationLogRoute`（自动操作审计）。

## 6. 技术依赖与迁移

- 新增依赖：`mcp`、`fastmcp`（清华镜像，`uv add --index-url https://pypi.tuna.tsinghua.edu.cn/simple`；若 resolver 冲突则 `pip install --no-deps` 手工补传递依赖，提交信息注明）。
- Alembic：新增 `ai_market_items` / `ai_market_relations` / `ai_market_shares` / `ai_mcp_servers` / `ai_plugins` 五表；
  `ai_tools` 加 `code`/`timeout`/`kind` 值扩展；`ai_agents` 加 `mcp_ids`。
- 种子：`sys_menu.json` 增市场/MCP 菜单与权限码；`sys_menu` 存量库用菜单管理 UI（文档说明）。

## 7. 测试策略

- 后端单测：脚本工具沙箱（白名单/超时/非法 import 拒绝）、MCP 配置校验、市场状态机（提交→审核→安装→分享→接收）、权限（非管理员不能 review）、安装复制幂等。
- 前端 type-check + 手动走查：市场首页/安装/我的资产/提交/审核/分享接收/Agent 绑定 MCP。
- E2E（可选）：管理员审核一条技能 → 用户安装 → Agent 绑定运行。

## 8. 里程碑（实施计划拆分）

| 阶段 | 内容 | 交付 |
|------|------|------|
| M1 | 后端基座：五表迁移 + 市场/分享/审核/安装 API + 权限 | 后端可测 |
| M2 | 自定义 Python 工具：ai_tools 扩展 + 沙箱执行器 + test-script | 后端可测 |
| M3 | MCP：ai_mcp_servers + Agent mcp_ids + 运行时装配 + 依赖安装 | Agent 可用 MCP |
| M4 | 前端：市场/我的/分享/审核四页 + 工具页脚本表单 + MCP 页 + Agent 表单 | 全流程可用 |
| M5 | 菜单权种子 + 文档 + 全量测试 + 修缺 | 上线 |

## 9. 已知风险

- 脚本工具沙箱并非强隔离（同进程），仅防误用不防恶意；文档明示，默认仅管理员/受信用户可建。
- MCP stdio 子进程生命周期管理较复杂，先以 streamable-http/sse 为主要形态，stdio 提供基础支持。
- 存量 `sys_menu` 无市场菜单：按项目惯例新库种子生效，存量库需菜单管理 UI 添加（属既有流程）。
