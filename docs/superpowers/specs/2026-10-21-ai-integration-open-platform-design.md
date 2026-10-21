# AI 集成开放平台·设计文档

- 日期：2026-10-21
- 状态：待评审
- 范围：新增「AI 集成」子系统，把平台的 AI 能力（训练任务 / Agent / 消息 / 聊天机器人 / 嵌入）以开放接口（REST + MCP Server + 嵌入 SDK）暴露给第三方，用 **appid / appkey** 鉴权并按**能力品类权限**控制
- 参考模型：**企业微信（WeCom）AI 开放能力 / MCP 集成**

---

## 1. 背景与目标

平台目前 `module_ai`（AI 管理）已具备：Agent、AI 应用、聊天/助手（SSE 流式）、知识库 RAG、模型与供应商、能力市场、MCP 客户端管理；`module_train` 具备训练任务（OCR/PaddleX/YOLO）、评估、预测。但**这些能力只能由平台内部登录用户通过 RBAC 权限访问**，无法被第三方系统程序化调用。

目标：搭建一个「AI 集成开放平台」，让**外部系统**申请 `appid/appkey`，通过 **REST API / MCP Server / 嵌入 SDK** 三种形态调用平台 AI 能力，且**按 appid 的能力品类权限**控制，做到权限隔离、关键动作可审批、授权可到期、调用全审计。

### 1.1 成功标准
- 第三方用 `appid:appkey` 即可调用：创建训练任务、创建 Agent、发消息、聊天机器人对话。
- 第三方能把 Agent/聊天机器人 **iframe 嵌入自家站点**（对齐 BSIAP 的 `/embed` / `/public` 机制）。
- 每个 app 的能力被**按品类权限**限制，超出权限的调用被拒绝并记录。
- 所有 app 调用可审计、可追溯、可配额。

---

## 2. 参考模型：企业微信 MCP 集成

企业微信 5.0.10 开放了 CLI 与 MCP 能力，其设计要点如下，直接作为我们的参考基准：

| 企业微信 | 我们的实现 |
|---------|-----------|
| 企业微信后台创建「智能机器人（AI Bot）」 | 「AI 集成」菜单创建「集成应用（app）」 |
| **Bot ID + Secret**（凭据） | **appid + appkey** |
| 按**品类（category）**授权：`doc / msg / contact / schedule / todo / meeting` | 按能力品类授权：`train / agent / chat / bot / embed` |
| 工具命名 `{category}__{method}`（如 `msg__send_message`） | 如 `train__create_task`、`agent__create`、`chat__send_message` |
| 远程 MCP（Streamable HTTP），按品类拉取对应 Server | 平台作为 MCP Server（`mcp` 官方 `FastMCP` + Streamable HTTP） |
| 安全四要素：**人员权限与 AI 权限隔离、关键动作人工审批、授权有效期、全量审计可追溯** | 同四要素落地 |

> 参考来源：企业微信「AI 开放能力」页、企业微信 5.0.10 开放 CLI 与 MCP 公告、`wecom-mcp` 社区实现。企业微信的接入流程是「创建 AI Bot → 获取 Bot ID/Secret → 在后台为 Bot 开启各品类授权 → Agent 通过 Bot ID/Secret 以 MCP 方式调用」。

---

## 3. 整体架构与分解

采用**独立数据域 + 三态出口 + 统一能力注册表**。整个系统分解为 4 个子项目，按依赖顺序推进，每个子项目独立走「spec → plan → 实现 → 验证」。

```
┌───────────────────────────────────────────────────────────┐
│                 AI 集成开放平台（module_ai/develop/）        │
│                                                             │
│  内部管理面（RBAC 鉴权，/ai/develop/*）                      │
│    ├─ 集成应用管理（app CRUD、appid/appkey、权限点、配额）    │
│    ├─ 调用日志 / 审计 / 统计                               │
│    └─ 授权有效期 / 审批配置                                │
│                                                             │
│  开放数据面（appid/appkey 鉴权）                             │
│    ├─ REST API     /ai/develop-api/*                      │
│    ├─ MCP Server   /ai/develop-api/mcp （Streamable HTTP） │
│    └─ 嵌入 SDK     /embed/* + /public/*                  │
│                                                             │
│  统一能力注册表（capability registry，方案 A）               │
│    每个能力条目：能力码 / 权限码 / 参数schema / REST路由 /    │
│    MCP工具定义 / handler → 复用现有 service                  │
└───────────────────────────────────────────────────────────┘
```

### 3.1 能力品类（首批对外）

| 品类 | 权限点示例 | 能力 |
|------|-----------|------|
| `train` | `integration:train:create/query/start/stop` | 创建训练任务、查询/启动/停止、查状态与日志 |
| `agent` | `integration:agent:create/query/update/delete` | 创建/查询/编辑/删除 Agent |
| `chat` | `integration:chat:send/query` | 发消息（非流式/流式）、会话管理 |
| `bot` | `integration:bot:use` | 聊天机器人对话（调用 app 可用的 bot 实例） |
| `embed` | `integration:embed:use` | 把 Agent/聊天机器人 iframe 嵌入第三方站点 |

> 权限点定义在前端勾选、后端校验，独立于系统内部 `module_ai:*` RBAC 权限，实现「人员权限与 AI 权限隔离」。

### 3.2 子项目分解与顺序

| 阶段 | 子项目 | 范围 | 依赖 |
|------|--------|------|------|
| **P1** | 集成应用凭证与权限（底座） | `ai_integration_apps` 表、appid/appkey 生成/重置/启停/到期、按品类权限点、appid/appkey 鉴权依赖、调用审计表、前端「AI 集成」菜单 | 无 |
| **P2** | 开放 REST API（能力暴露） | 对外端点：创建训练任务/创建 Agent/发消息/聊天/查状态；appid 鉴权+权限校验+数据归属（app 租户）+限流+审计；统一能力注册表 | P1 |
| **P3** | MCP Server（协议暴露） | 平台作为 MCP Server（`FastMCP` + Streamable HTTP），把能力注册表暴露为 MCP tools；appid/appkey 走 MCP header 鉴权 | P2 |
| **P4** | 嵌入能力（对齐 BSIAP） | `/embed/*` + `/public/*` 免登录路由；app 维度 embed token；`<script>`/iframe 嵌入 SDK；`postMessage` 业务数据回传 | P1 |

> 可选项 P5：治理度量（tokens 消耗统计、配额告警、开发者文档/样例代码生成）。

---

## 4. 命名与路由（重要：避让已占用菜单）

`/ai/integration`（route_name `AiIntegration`，菜单「数据与集成」，组件 `module_ai/integration/index`）**已被智能问数数据源集成占用**。本新功能必须避让。

**最终命名：**

| 项 | 值 | 说明 |
|----|----|------|
| 菜单名 | 「AI 集成」 | 用户要求 |
| 路由 | `/ai/develop` | 避开 `/ai/integration` |
| route_name | `AiDevelop` | 唯一 |
| 前端组件 | `module_ai/develop/index.vue` | 单页 + 页签（应用管理 / 调用日志） |
| 后端模块 | `app/plugin/module_ai/develop/` | 自动发现，容器前缀 `/ai` |
| 内部管理面 | `DevelopRouter`（`/ai/develop`，`AuthPermission(["module_ai:develop:*"])`） | RBAC |
| 开放数据面 | `OpenApiRouter`（`/ai/develop-api`，`get_app_api_auth`） | appid/appkey |

> ⚠️ 若后续需要在「AI 控制台」之外再放一个菜单入口，需同步登记 route_name 与按钮权限（见 §8.3 菜单种子）。

---

## 5. 统一能力注册表（方案 A）

REST / MCP / 嵌入三态共用同一套能力 handler，避免逻辑重复。注册表只做**元数据 + 分发**，不重写业务（handler 直接复用现有 service）。

每个能力条目（`integration/capabilities.py` 中定义）：

```python
class Capability:
    code: str                 # "train.create_task"
    perm: str                 # "integration:train:create"
    category: str             # "train"
    name: str                 # 中文名
    description: str
    input_schema: dict        # JSON Schema（校验入参）
    returns: str              # 返回结构说明
    handler: Callable         # 实际调用现有 service 的异步函数
    requires_approval: bool   # 是否需要人工审批（高危动作）
    mcp: dict                 # MCP 工具定义（name/description/参数）
    rest: dict                # REST 路由模板（method/path）
```

- **REST**：`OpenApiRouter` 通过注册表生成路由，handler 注入 `app`（appid 上下文）。
- **MCP**：P3 用 `FastMCP` 把注册表里 `mcp` 定义批量 `@mcp.tool()`，handler 同样注入 `app`。
- **嵌入**：P4 复用能力注册表的「认证 + 归属」逻辑。

### 5.1 统一层注入（一次注入，三态共享）
每个开放入口经过 `get_app_api_auth` 得到 `AppContext(app_id, app, perms, quota)`。之后：
1. 校验该能力 `perm` 是否在 app 的权限点内（否则 403）；
2. 若 `requires_approval`，进入审批流程（P2/P3；P1 只存标记）；
3. 校验配额/有效期；
4. 调用 handler（内层把资源 `app_id` 归属到该 app）；
5. 写调用审计 `ai_integration_call_logs`。

---

## 6. P1 详细设计：集成应用凭证与权限

### 6.1 数据模型（手写 Alembic 迁移）

> 本项目 dev 库有 400+ 历史/影子表（`ont_*`），`autogenerate` 会产生无关 DROP，**迁移必须手写**（参考 `2026_10_15_ai_market_models.py` 模式）。插件表增列前用 `sa.inspect(bind).has_table()` 判断，保证空库/全链重放（SQLite 回归）可用。

#### `ai_integration_apps`（集成应用主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 主键 |
| `uuid` | String(64) | 全局唯一 |
| `appid` | String(64) | **公开标识**，全局唯一（`ai_` 前缀，如 `ai_ab12cd`），用于鉴权与展示 |
| `appkey_hash` | String(128) | **appkey 的哈希**（sha256），不存明文；创建/重置时一次性返回明文 |
| `name` | String(128) | 应用名（唯一） |
| `description` | String(255) | 描述 |
| `status` | String(16) | `enabled` / `disabled`（禁用后拒绝鉴权） |
| `expire_at` | DateTime | 授权到期时间；空=长期 |
| `capabilities` | JSONB | 权限点数组（`["integration:agent:create", ...]`） |
| `quota` | JSONB | 配额（如 `{"train": 10, "chat": 1000}`，空=不限制） |
| `requires_approval` | Boolean | 高危动作是否需人工审批（默认 true） |
| `source_type` | String(16) | 归属来源：`admin`（平台管理员创建）/ 预留 |
| `last_call_at` | DateTime | 最近调用时间（用于展示） |
| `call_count` | Integer | 累计调用次数 |
| `ModelMixin/UserMixin` | - | 复用 `created_id`/`updated_id` 等审计 |

#### `ai_integration_call_logs`（调用审计表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer PK | 主键 |
| `app_id` | Integer FK | 关联 `ai_integration_apps.id` |
| `appid` | String(64) | 冗余展示 |
| `category` | String(16) | 能力品类（`train/agent/chat/bot/embed`） |
| `capability` | String(64) | 能力码 |
| `method` | String(16) | `REST` / `MCP` / `EMBED` |
| `request_path` | String(255) | 请求路径 |
| `request_body` | JSONB | 入参（脱敏） |
| `status` | String(16) | `success` / `denied` / `error` |
| `error` | String(255) | 错误信息 |
| `latency_ms` | Integer | 耗时 |
| `cost_tokens` | Integer | token 消耗（P2 起填） |
| `result_summary` | String(512) | 结果摘要（如资源 id） |
| `MappedBase` | - | 仅 `id`/`created_time`，无软删（审计只增不改） |

### 6.2 appid/appkey 生成

- `appid`：`ai_` + 8 位随机（去易混淆字符），创建后不可变。
- `appkey`：32 位随机串，**仅在创建/重置时返回一次明文**，数据库只存 `sha256`。
- 重置：新 appkey 覆盖旧哈希，旧 appkey 立即失效（返回一次明文）。

### 6.3 鉴权流程（`get_app_api_auth`）

开放数据面所有入口用 `Depends(get_app_api_auth)`：

1. 从 `Authorization: Bearer <appid>:<appkey>` 解析出 `appid` + `appkey`；
2. 查 `ai_integration_apps`（`appid == ...` 且 `status == enabled`）；
3. 校验 `expire_at` 未过期；
4. 计算 `sha256(appkey)` 与 `appkey_hash` 比对（`hmac.compare_digest` 防时序攻击）；
5. 命中 → 返回 `AppContext(app_id, app, perms=set(capabilities), quota)`；
6. 失败 → 401（不区分"不存在"与"密钥错"，避免枚举）。

```python
def get_app_api_auth(
    authorization: str = Header(...),   # "Bearer <appid>:<appkey>"
) -> AppContext: ...
```

> 说明：`Authorization: Bearer <appid>:<appkey>` 同时适用于 REST 与 MCP header（P3）；`appkey` 不进日志、不进 URL。短期 `access_token` 换取（更贴近微信 access_token 模型）作为 **P5 增强**，P1 不做。

### 6.4 权限点与校验

- 权限点统一命名 `integration:<category>:<action>`，并在 `capabilities.py`/常量中**集中定义**（单一事实来源）。
- app 行 `capabilities` 存勾选的权限点数组。
- 每个开放能力校验 `perm in app.perms`，否则 `403` + 审计 `denied`。

### 6.5 数据归属（app 租户，跨 P1–P4）

- 资源（训练任务 / Agent / 消息 / 会话 / 嵌入 token）落 `source_app_id`（Integer FK `ai_integration_apps.id`，可空，空=内部用户创建）。
- P2 起在**创建路径**统一打上 `source_app_id`，并**只允许 app 访问自己创建的资源**（查询/更新按 `source_app_id` 过滤）。
- 这一「归属域」字段是跨子项目的约定，P1 定义约定与常量，P2/P3 逐步落到 train/agent/chat。

### 6.6 审计与统计

- 每次开放调用写 `ai_integration_call_logs`（成功/拒绝/异常都写）。
- `ai_integration_apps` 维护 `last_call_at` / `call_count` 供列表展示。

### 6.7 前端「AI 集成」菜单

单页 `module_ai/develop/index.vue`，页签：
- **应用管理**：列表（`useCrudList`）+ 新建/编辑弹窗（`EnhancedDialog`）+ 详情查看 appid/appkey（明文一次性）+ 重置 appkey + 启用/禁用 + 到期时间 + 权限点勾选（`el-checkbox-group`）+ 配额。所有删除/重置类操作**二次确认**。
- **调用日志**：列表（按 appid/品类/状态/时间过滤），只读。
- **接入文档**：展示 REST / MCP / 嵌入三种接入方式与示例代码（静态）。

样式遵循既有模块（参照 `module_ai/provider`、`module_system/param`），复用 `--el-*` 变量，禁止自造主题化外壳。

### 6.8 菜单 / 权限种子（幂等）

在 `init_app.py` 新增 `_ensure_develop_menus()`（参照 `_ensure_ai_menus` 模式），**启动时幂等补齐**：
- 父目录：AI 下新增子菜单「AI 集成」（`route_name=AiDevelop`、`/ai/develop`、`module_ai/develop/index`、`module_ai:develop:query`）；
- 按钮权限（type=3）：`module_ai:develop:{create,update,delete,reset,query}`；
- 存量库重启即生效，无需手工 INSERT；空库种子数据无需改（`_ensure_*` 只补缺失）。

---

## 7. 测试方案（P1）

- **纯逻辑测试（快速模式）**：appid 生成、appkey 哈希/校验、权限点校验、到期判断、鉴权依赖（`PYTEST_NO_APP=1`，不构造应用）。
- **DB 相关**：`ai_integration_apps` / `ai_integration_call_logs` 建表与 CRUD（复用既有 DB 测试设施）。
- **鉴权集成**：`/ai/develop-api` 端点用有效/无效 appid/appkey、过期、禁用、超权限 各场景校验返回 200/401/403。
- **迁移**：`upgrade`/`downgrade` 往返；空库全链重放（SQLite 回归）不因插件表报错。

---

## 8. 里程碑与验收

- **P1 验收**：能在「AI 集成」菜单创建应用并拿到 appid/appkey；用 appid/appkey 调用开放端点鉴权通过/拒绝正确；调用可审计；权限点/到期/禁用生效。
- **P2 验收**：能用 appid 调用「创建训练任务/创建 Agent/发消息/聊天」，资源归属对应 app，超出权限被拒。
- **P3 验收**：第三方把平台配为 MCP Server，用 appid/appkey 作为 header，通过 MCP 调用上述工具。
- **P4 验收**：第三方站点 iframe 嵌入 Agent/聊天机器人，免登录可对话，业务数据经 `postMessage` 回传。

---

## 9. 待办 / 风险

- **命名冲突**：已避让 `/ai/integration`；若未来出现其它 AI 集成语义，需先复核本说明。
- **迁移手写**：谨防 `autogenerate` 触发无关 DROP。
- **appkey 保管**：明文仅一次返回；前端展示时需引导及时保存，避免二次打开仍可见（建议只展示"已重置"提示）。
- **鉴权模型**：`Bearer appid:appkey` 直传简单，但 appkey 会在每次请求中出现；若需更高安全，P5 提供短期 `access_token` 换取（对齐微信模型），P1 不引入。
