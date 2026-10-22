# AI 集成开放平台 P2（开放 REST）+ P3（MCP Server）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实施。步骤用 `- [ ]` 勾选跟踪。

**目标**：把平台 AI 能力（Agent / 对话 / 训练任务）以**统一能力注册表**暴露为两态出口——开放 REST 与 MCP Server（Streamable HTTP），全部走既有六步鉴权管道（凭证 → 权限 → 配额/限流 → 执行 → 审计），并按 `source_app_id` 做数据归属。

**架构**：新增 `develop/registry.py`（能力元数据 + 分发，纯逻辑）与 `develop/handlers/`（每品类一个 handler 模块，复用既有 service）；开放面新增 `POST /ai/develop-api/capabilities/{code}` 与 `GET /ai/develop-api/capabilities`；MCP 面用官方 SDK `mcp.server.mcpserver.MCPServer` 挂 `/ai/develop-api/mcp`，ASGI 包装层把 `Bearer appid:appkey` 解析为 `AppContext` 存 ContextVar，工具即注册表条目。

**技术栈**：FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + Alembic（手写迁移）+ `mcp>=2.1,<3`（实测 2.3.0）+ pytest。

**Spec**：`docs/superpowers/specs/2026-10-21-ai-integration-open-platform-design.md`（§3.1 品类、§6 认证管道、§7 注册表、§8 归属、§11 验收）

## 全局约束（每个任务都适用）

- **禁匿名**：任何开放端点缺凭证 → 401，文案统一「鉴权失败」，不泄露失败原因。
- **权限点单一真源**：`develop/capabilities.py`；新能力必须归入既有品类（train/agent/chat/bot/embed），不得自造品类码。
- **审计**：每次调用（成功/拒绝/异常）写 `ai_integration_call_logs`；`method` = `REST` / `MCP`；`request_body` 不得含 appkey / access_token 明文。
- **归属**：开放面创建的 Agent / 训练任务必须写 `source_app_id`；开放面的查询与写操作**只能**作用于 `source_app_id = 本 app` 的资源（内部用户创建的资源对开放面不可见、不可改）。
- **MCP 实现物**：`mcp` 2.x 已把 `FastMCP` 更名为 `MCPServer`（`mcp/server/fastmcp.py` 是导入即抛的占位模块）。实现用 `from mcp.server.mcpserver import MCPServer`，文档与接入说明中注明与 spec「FastMCP」的对应关系。
- **挂载 MCP**：不能直接 `app.mount()` 子 Starlette（会丢其 lifespan）。做法：先调一次 `mcp.streamable_http_app()` 触发 session manager 创建，再在 FastAPI lifespan 里 `async with mcp.session_manager.run():`，并 `app.mount("/ai/develop-api/mcp", StreamableHTTPASGIApp(mcp.session_manager))`。
- **训练框架守卫**：创建训练任务前必须 `retired.ensure_active(framework, action="训练")`。
- **前端样式**：遵守 `AGENTS.md` §5（面板外壳 + 表格 `border stripe` + 计算样式探测）。

## Review Focus（spec 暗示、但任务测试必须显式钉住的输入/失败模式）

1. **越权访问他人 app 的资源**：用 A 应用的 appid 读/改 B 应用创建的 Agent 或训练任务 —— 期望 404/403，绝不返回数据。
2. **缺权限点调用能力**：应用只有 `integration:chat:send`，调 `train.create` —— 期望 403 + denied 审计。
3. **appkey 泄漏到审计/日志/响应**：调用日志、MCP 会话行、错误响应中不得出现 appkey 或 access_token 明文。
4. **MCP 未鉴权握手**：不带 `Authorization` 调 `/ai/develop-api/mcp` —— 期望 401（不是 500、不是正常 JSON-RPC 响应）。
5. **同一 appid 的 MCP 会话审计**：工具调用写 `call_logs(method=MCP)`、连接写 `mcp_sessions`，且 `tool_calls` 计数随调用累加。

---

### 任务 1：能力注册表（纯逻辑）

**文件**
- 新建：`backend/app/plugin/module_ai/develop/registry.py`
- 测试：`backend/tests/test_develop_registry.py`

**接口**
- 产出：
  - `@dataclass(frozen=True) Capability`：`code: str`（`"agent.list"`）、`category: str`、`perm: str`、`name: str`、`description: str`、`input_schema: dict`、`returns: str`、`handler: Callable[..., Awaitable[Any]]`、`mcp_tool: str | None`、`rest: bool = True`。
  - `register(cap: Capability) -> None`（重复 code 抛 `ValueError`）
  - `get_capability(code: str) -> Capability | None`
  - `all_capabilities() -> list[Capability]`
  - `capabilities_for(perms: set[str]) -> list[Capability]`（按 `perm in perms` 过滤，按 category+code 排序）

- [x] 步骤 1：写失败测试 `test_registry_register_and_lookup`、`test_registry_rejects_duplicate_code`、`test_capabilities_for_filters_by_perm`
- [x] 步骤 2：跑 `uv run pytest tests/test_develop_registry.py -q`，确认 FAIL
- [x] 步骤 3：实现 `registry.py`
- [x] 步骤 4：跑测试确认 PASS
- [x] 步骤 5：提交 `feat(ai): 开放平台能力注册表`

### 任务 2：数据归属列（迁移 + 模型 + service 过滤）

**文件**
- 修改：`backend/app/plugin/module_ai/agent/model.py`（`AiAgentModel` 增 `source_app_id`）、`backend/app/plugin/module_ai/agent/service.py`（`list_agents(source_app_id=None)`、`get_agent(agent_id, source_app_id=None)`、`create(data, auth, source_app_id=None)`）
- 修改：`backend/app/plugin/module_train/model.py`（`TrainTask` 增 `source_app_id`）、`backend/app/plugin/module_train/service.py`（`list_tasks(params)` 支持 `source_app_id`、`get_task(task_id, source_app_id=None)`、`create_task(data, auth, source_app_id=None)`）
- 新建：`backend/app/alembic/versions/2026_10_22_ai_open_resource_owner.py`
- 测试：`backend/tests/test_open_resource_owner.py`

**接口**
- 产出：两表新增可空列 `source_app_id Integer`（FK `ai_integration_apps.id`，`NULL` = 内部用户创建）；service 的新可选参数默认 `None` = 不过滤（内部页面行为不变）。

- [x] 步骤 1：写失败测试：带 `source_app_id` 的 Agent 只能被同 `source_app_id` 查到；不同 app 查为 None；`list_agents(source_app_id=1)` 不返回 `source_app_id=None` 的内部 Agent
- [x] 步骤 2：跑测试确认 FAIL
- [x] 步骤 3：加模型列 + service 参数 + 手写迁移（`down_revision` = 当前 head；`has_column` 判断防重放）
- [x] 步骤 4：跑测试 + `uv run pytest tests/test_embed_migration.py -q` 确认 PASS
- [x] 步骤 5：提交 `feat(ai): Agent/训练任务支持 source_app_id 归属`

### 任务 3：开放 REST 调用端点（统一入口）

**文件**
- 新建：`backend/app/plugin/module_ai/develop/openapi.py`（管道执行 + 审计，供 REST 与 MCP 共用）
- 修改：`backend/app/plugin/module_ai/develop/controller.py`（`GET /develop-api/capabilities`、`POST /develop-api/capabilities/{code}`）
- 测试：`backend/tests/test_develop_openapi.py`

**接口**
- 产出：
  - `async def invoke_capability(ctx: AppContext, code: str, payload: dict, *, method: str, redis=None, request_path: str | None = None) -> Any`
    流程：查注册表（无 → 404）→ `require_app_perm(ctx, cap.perm)`（403 + denied 审计）→ 配额/限流（429）→ `cap.handler(app_ctx=ctx, payload=payload)` → 成功审计（`latency_ms`/`result_summary`）。
  - `async def audit_call(ctx: AppContext, *, category, capability, method, status, error=None, latency_ms=0, result_summary=None, request_body=None, request_path=None, session_id=None, transport=None, client_info=None) -> None`（内部按 `ctx.app_id` 取 ORM 行后调 `DevelopService.log_call`）

- [x] 步骤 1：写失败测试：无凭证 401；未授权能力 403 且 `call_logs.status=denied`；未注册 code 404；成功调用写 `method=REST`、`status=success`、`request_body` 不含 appkey
- [x] 步骤 2：跑测试确认 FAIL
- [x] 步骤 3：实现 `openapi.py` 与两个端点（端点用 `Depends(get_app_api_auth)`）
- [x] 步骤 4：跑测试确认 PASS
- [x] 步骤 5：提交 `feat(ai): 开放 REST 能力调用端点`

### 任务 4：agent 品类 handler

**文件**
- 新建：`backend/app/plugin/module_ai/develop/handlers/__init__.py`、`handlers/agents.py`
- 测试：`backend/tests/test_develop_agents.py`

**接口**
- 产出：`def register_agent_capabilities() -> None`，注册 `agent.list` / `agent.get` / `agent.create` / `agent.update` / `agent.delete`，perm 分别 `integration:agent:{query,query,create,update,delete}`，`mcp_tool` 为 `agent_list` / `agent_get` / `agent_create` / `agent_update` / `agent_delete`。
- handler 签名统一 `async def handler(*, app_ctx: AppContext, payload: dict) -> Any`；创建时 `source_app_id=app_ctx.app_id`；读/改/删一律带 `source_app_id=app_ctx.app_id` 过滤；`auth` 传 `SimpleNamespace(user=None)` 并显式传 `created_id=None`（开放面资源无平台用户）。

- [x] 步骤 1：写失败测试：创建后 `source_app_id == app.id`；另一 app 读/删同 id → 404；`agent.list` 只含本 app 的 Agent
- [x] 步骤 2：跑测试确认 FAIL
- [x] 步骤 3：实现 `handlers/agents.py` 并在 `develop/__init__.py` 导入时注册
- [x] 步骤 4：跑测试确认 PASS
- [x] 步骤 5：提交 `feat(ai): 开放面 Agent 能力`

### 任务 5：chat / bot 品类 handler

**文件**
- 新建：`backend/app/plugin/module_ai/develop/handlers/chat.py`
- 测试：`backend/tests/test_develop_chat.py`

**接口**
- 产出：`register_chat_capabilities()` 注册 `chat.send`（perm `integration:chat:send`）、`chat.sessions`（`integration:chat:query`）、`chat.messages`（`integration:chat:query`）、`bot.use`（`integration:bot:use`）。
- `chat.send` payload：`{kind: "agent"|"app"|"workflow", target_id: int, message: str, sid: str | None}`；实现方式：复用 `AiAgentService.run_ui_stream` / `run_app_ui_stream` / `AiWorkflowService.run_ui_stream` 的帧流，**聚合成非流式回复**：收集 `UiMessageStream` 的 `data-delta`/`text-delta` 文本与 Agno 帧的 `RunContent.content`，取最终文本 + `session_id` 返回 `{reply, session_id, kind, target_id}`；`sid` 与嵌入会话复用同一 `prepare_session` 绑定逻辑（不同 app 的 sid 隔离）。
- `chat.sessions` / `chat.messages`：仅返回本 app（`source_app_id = app.id`）的会话与消息。
- `bot.use` payload：`{app_id: int, message: str}`（AI 应用），内部走 `run_app_ui_stream` 聚合成回复。

- [x] 步骤 1：写失败测试：`chat.send` 目标为 e2e 无模型工作流时返回 `reply` 且写审计；`chat.sessions` 不返回内部会话；`bot.use` 缺 `integration:bot:use` → 403
- [x] 步骤 2：跑测试确认 FAIL
- [x] 步骤 3：实现 `handlers/chat.py`（帧聚合函数 `async def _collect_reply(frames) -> str`）
- [x] 步骤 4：跑测试确认 PASS
- [x] 步骤 5：提交 `feat(ai): 开放面对话与机器人能力`

### 任务 6：train 品类 handler

**文件**
- 新建：`backend/app/plugin/module_ai/develop/handlers/train.py`
- 测试：`backend/tests/test_develop_train.py`

**接口**
- 产出：`register_train_capabilities()` 注册 `train.list` / `train.get` / `train.create` / `train.start` / `train.stop`，perm `integration:train:{query,query,create,start,stop}`。
- `train.create` payload：`{name, framework, dataset_id, annotation_task_id?, base_model_id?, hyperparams?}` → `TrainService.create_task(TrainTaskCreateSchema(...), auth=SimpleNamespace(user=None), source_app_id=app_ctx.app_id)`；先 `retired.ensure_active`。
- `train.start` / `train.stop`：仅允许 `source_app_id = app.id` 的任务，否则 404；`start` 调 `scheduler.start_training`。

- [x] 步骤 1：写失败测试：创建后归属正确；跨 app 读/停 → 404；退场框架 → 400 文案含「已退场」
- [x] 步骤 2：跑测试确认 FAIL
- [x] 步骤 3：实现 `handlers/train.py`
- [x] 步骤 4：跑测试确认 PASS
- [x] 步骤 5：提交 `feat(ai): 开放面训练任务能力`

### 任务 7：MCP Server（Streamable HTTP）

**文件**
- 新建：`backend/app/plugin/module_ai/develop/mcp_server.py`
- 修改：`backend/app/scripts/init_app.py`（lifespan 中启动 session manager + `app.mount("/ai/develop-api/mcp", ...)`）
- 测试：`backend/tests/test_develop_mcp.py`

**接口**
- 产出：
  - `CURRENT_APP_CTX: ContextVar[AppContext | None]`
  - `class McpAuthMiddleware`（ASGI）：解析 `Authorization: Bearer appid:appkey`（复用 `_parse_bearer` + `DevelopService.verify_appkey`），失败直接回 `401 {"detail":"鉴权失败"}`；成功设 `CURRENT_APP_CTX`，并写 `mcp_sessions` 行（首次连接），响应结束后更新 `ended_at`/`duration_s`/`tool_calls`。
  - `build_mcp_server() -> MCPServer`：为每个 `mcp_tool` 非空的注册能力用 `@server.tool(name=..., description=...)` 注册一个工具，工具内 `ctx = CURRENT_APP_CTX.get()`（None → 401 语义错误），调 `invoke_capability(..., method="MCP", transport="streamable-http")`。
  - `def mcp_asgi_app() -> Starlette`：`server.streamable_http_app()` + 中间件包装。

- [x] 步骤 1：写失败测试：不带 Authorization → 401；带正确凭证 initialize 握手返回 `serverInfo.name`；`tools/list` 只含该 app 授权的能力；调用 `agent_list` 写 `call_logs(method=MCP)` 且 `mcp_sessions.tool_calls` 递增
- [x] 步骤 2：跑测试确认 FAIL
- [x] 步骤 3：实现 `mcp_server.py` 与挂载（lifespan 内 `async with server.session_manager.run():`）
- [x] 步骤 4：跑测试确认 PASS；`curl -H "Authorization: Bearer ..." -X POST /api/v1/ai/develop-api/mcp` 冒烟
- [x] 步骤 5：提交 `feat(ai): MCP Server（Streamable HTTP）`

### 任务 8：前端接入文档与能力清单

**文件**
- 修改：`frontend/src/views/module_ai/develop/index.vue`（接入文档页签：REST 调用示例、MCP 端点与 `mcp.json` 配置示例、能力清单表；「即将开放」标记删除）
- 修改：`frontend/src/views/module_ai/develop/components/EmbedDialog.vue`（如需展示 MCP 端点则加一行只读文本，保持框架样式）
- 测试：无自动化；用 Playwright 截图 + 计算样式探测（见 `AGENTS.md` §5）

- [x] 步骤 1：改写文档页签（表格 `border stripe`、代码块沿用既有样式）
- [x] 步骤 2：`pnpm run type-check` + eslint/stylelint/prettier
- [x] 步骤 3：无头浏览器截图（文档页签有数据态/空态、MCP 会话页签）+ 计算样式探测与参照页数值比对
- [x] 步骤 4：提交 `docs(ai): 接入文档补齐 REST/MCP 示例与能力清单`

### 任务 9：全量自查

- [x] 步骤 1：`uv run pytest -q -n 4`（全量）与前端 `type-check`、lint
- [x] 步骤 2：真实冒烟：起后端 → 用 appid/appkey 调 `POST /ai/develop-api/capabilities/agent.create`、`agent.list`，再用 MCP 客户端（或裸 HTTP initialize + tools/call）跑一次工具调用；管理端确认调用日志与 MCP 会话两页签有记录
- [x] 步骤 3：截图归档到 `.openchamber/screenshots/`，逐张读图对照框架页面
- [x] 步骤 4：更新 spec 的里程碑状态与本计划的执行记录；提交
---

## 执行记录（2026-10-22）

全部 9 个任务已实施并提交（分支 `groovy-hedgehog`）：

| 提交 | 内容 |
|------|------|
| `dbcff2c6` | 能力注册表（元数据+分发，纯逻辑） |
| `d021d6f7` | `source_app_id` 归属（模型 + service 过滤参数 + 手写迁移 `b7c8d9e0f1a2`） |
| `f0bfe2f5` | 开放 REST 统一入口 `POST /ai/develop-api/capabilities/{code}` + `GET /ai/develop-api/capabilities`（按授权过滤）+ agent 能力 |
| `39b544b1` | ruff 修正 |
| `7cf09218` | chat / bot / train 能力（聚合回复、会话归属隔离、退场框架守卫、ValueError→400） |
| `61b38444` | MCP Server（Streamable HTTP） |
| `d8eff7e9` | 接入文档补齐 REST/MCP 真实示例 + 开放能力清单（`GET /ai/develop/capabilities`） |
| `4d526a78` | MCP 端点改精确路由（修 307 丢头） |

### 与计划的偏差（均已验证）

1. **FastMCP → MCPServer**：`mcp` 2.3.0 已把 `FastMCP` 更名为 `MCPServer`，实现用 `mcp.server.mcpserver.MCPServer`（spec 中的「FastMCP」对应物），并在 spec 与模块 docstring 注明。
2. **挂载方式**：`app.mount()` 会让 `/ai/develop-api/mcp` 回 307 到 `.../mcp/`（POST 307 会丢自定义头，很多 MCP 客户端不跟随），改为 `Route` 精确匹配；该问题在真实 HTTP 冒烟时才暴露（TestClient 默认跟随重定向，掩盖了它）。
3. **工具调用计数**：MCP 传输层可能在自己的任务里执行工具，整数型 ContextVar 的改动无法回传中间件 → 改为 dict 计数对象。
4. **工具错误语义**：handler 的 `CustomException` 转成 SDK `ToolError`，客户端看到 `[10403] 无权限操作`，而不是笼统的 `Error executing tool`（返回 `result.isError=true`，符合 MCP 语义）。
5. **`tools/list` 按授权过滤**：以子类覆写 `list_tools`（SDK 无 middleware 钩子）。
6. **多加了 1 个管理面端点** `GET /ai/develop/capabilities`（全量能力清单，接入文档表格数据源）。
7. **DNS-rebinding 保护关闭**：SDK 默认只允许 localhost Host，而本端点是服务端↔服务端调用且部署 Host 是真实域名；鉴权仍由 Bearer 强制。

### 验证证据

- 新增/相关测试 **37 个全绿**：`test_develop_registry`(7) + `test_open_resource_owner`(5) + `test_develop_openapi`(7) + `test_develop_chat`(4) + `test_develop_train`(3) + `test_develop_mcp`(5) + 既有嵌入 6 个文件。
- **全量**：`3109 passed / 6 failed / 38 skipped`；6 个失败均为既有问题（`_embed_agno` 旧符号、RAG 嵌入/问数/规则 e2e 环境类），已在**基线 `d00eb685` 的独立 worktree 复现同样的失败**，与本次改动无关。
- **真实 HTTP 冒烟**（uvicorn + SQLite）：未鉴权 401 → initialize 200（拿到 `mcp-session-id`）→ `tools/list` 只含授权工具 → `tools/call agent_create` 落 `source_app_id` → `call_logs(method=MCP)=2`、`mcp_sessions` 1 行 `tool_calls=2`。
- **UI 计算样式探测**：外壳 padding 12px / 边框 1px / 圆角 4px / 白底，与「能力市场」逐项相等；4 个页签内所有表格 `el-table--border` 齐全、无横向溢出。
- 截图归档：`.openchamber/screenshots/p2-docs-rest.png`、`p2-docs-capabilities.png`、`p2-mcp-sessions.png`、`p2-logs-mcp.png`。

---

## 第二轮深挖与补强（2026-10-22 晚）

### 功能逻辑缺陷（已修）

| 问题 | 修复 |
|------|------|
| `chat.send` / `bot.use` 无超时，目标卡住会长期占用连接与并发槽 | 增加 `OPEN_API_CHAT_TIMEOUT_SECONDS`（默认 120s），超时返回 504 明确文案并写 failed 审计 |
| 开放面 `train.create` 不校验数据集，能建出指向不存在数据集的悬空任务 | 创建前校验 `annotation_dataset` 存在且未删除（404） |
| 开放面 `agent.delete` 是物理删除却无确认 | 要求 `confirm=true`，否则 400；MCP 工具 schema 同步要求该字段 |
| MCP 会话 `close_reason` 存协议方法名（tools/call） | 存中文原因（工具调用/握手完成/…），前端 `transport` 也中文化 |
| 审批入参存的是审计用截断体（长文本被截到 200 字） | 审批单独保存**完整入参**（仅剔除凭证键），并加单测钉住 |
| 审批门禁在参数校验之前，非法请求会被排进审批队列 | 入队前按能力 JSON Schema 校验（jsonschema），失败 400 |
| 审批可重复处理（拒绝后仍能被批准并执行） | 审批接口与 service 双重校验 `status == pending` |
| 迁移 revision 与既有 `c8d9e0f1a2b3` 撞号导致迁移链成环（应用启动 SystemExit） | 改用 `d9e0f1a2b3c4`；新增「迁移链只能有一个 head」回归测试 |

### 缺失功能（已补）

- **敏感调用审批流**（spec 提出「关键动作可审批」，此前完全未实现）：应用 `requires_approval` + 能力 `requires_approval`（`agent.delete`、`train.create/start/stop`）→ 先落 `ai_integration_approvals`（pending，不执行）→ 管理端「调用审批」页签批准后以原应用身份执行并回写结果 / 拒绝只记意见。权限点 `module_ai:develop:approve` 启动时幂等补齐。
- **配额与审批 UI**：应用表单新增「需人工审批」开关与「按日调用配额」（agent/chat/train/bot/embed 五类，0/空=不限），此前后端支持但页面无法配置。
- **日志/会话中文化**：出海口、状态、传输方式全部中文；日志表新增「待审批」状态色。
- **窄屏（1024）适配**：操作列在 <1280 不再 `fixed=right`，避免固定列盖住状态标签；表单弹窗限高 88vh + 内部滚动。

### 仍待办（下一轮候选）

1. 调用统计概览（今日调用/成功率/平均耗时/Top 能力/按天趋势）。
2. 调用日志时间范围过滤、详情抽屉、导出。
3. 管理端「能力试调」（选应用 + 能力 + JSON 入参直接调开放面）。
4. 审批通知（待审批提醒/超时自动拒绝）、配额用量可视化。
5. MCP 资源/提示词（resources/prompts）暴露。
6. `train.create` 对标注任务 / 基础模型的存在性校验。

---

## 第三轮：可观测性与自测能力（2026-10-22 夜）

### 新增后端

- `GET /ai/develop/stats?days=7`：今日调用/成功率/平均耗时/待审批 + 最近 N 天趋势 + Top 能力 + 应用与审批计数（`insights.py`，`func.date()` 分组，SQLite/PG 通用）。
- `GET /ai/develop/apps/{id}/usage`：某应用当日按品类调用次数（与 `app.quota` 一起用于「今日已用」）。
- `GET /ai/develop/call-logs/export`：按当前筛选导出 CSV（UTF-8 BOM，≤5000 行）。
- `POST /ai/develop/apps/{id}/try`：管理端能力试调——以应用身份执行一次能力，**跳过审批门禁**但仍校验权限、限流并写审计（`request_path=/try/{code}`）。
- `GET /ai/develop/call-logs` 新增 `start_time` / `end_time`（`YYYY-MM-DD HH:mm:ss`，非法格式 400）。
- `train.create` 增补：标注任务 / 基础模型存在性校验（此前只校验数据集）。

### 新增前端

- 调用日志页签顶部：4 张统计卡（`el-card`）+ 7 天迷你柱状趋势 + Top 能力标签（`el-row/el-col`，无图表库依赖）。
- 日志筛选新增「时间范围」（`el-date-picker` datetimerange）与「导出 CSV」；行点击打开详情抽屉（时间/应用/能力/出海口/状态/耗时/Tokens/路径/错误 + 请求参数 + 结果摘要）。
- 应用行新增「试调」：选能力（按 `input_schema.required` 自动生成 JSON 模板）→ 发送 → 展示响应/错误，并刷新日志与统计。
- 应用表单配额项显示「今日已用」，配额改为 2 列网格（避免窄列换行）。

### 验证

- 新增 `tests/test_develop_insights.py`（6 项）：统计字段与计数、时间范围真的生效（未来起始时间返回空）、CSV 头与内容、用量与配额、试调跳过审批且写 `/try/` 审计、未知能力 404 / 无权 403。
- 真实 UI 走查（1440 + 1024）：统计卡 7 次 / 100% / 12ms、趋势与 Top 能力、详情抽屉、试调真实创建 Agent（响应含 id/agent_name）、配额「今日 6 / 5 / 1」；截图归档 `p2-logs-stats.png`、`p2-log-detail.png`、`p2-try-dialog.png`、`p2-try-result.png`、`p2-app-form-quota.png`。

### 剩余（仍未做）

1. 审批通知与超时自动处理。
2. 凭证到期提醒（数据已在 `stats.apps.expiring_soon`，UI 未展示）。
3. MCP 的 resources/prompts 暴露。
4. 试调参数校验提示可再友好（目前错误以文本回显）。

---

## 第四轮：提醒、通知与 MCP 资源面（2026-10-23）

分支策略：**先不整合**（用户决定），继续在 `groovy-hedgehog` 上迭代。

### ① 凭证到期提醒（前端补展示）

- 后端 `stats.apps` 新增 `expiring: [{id, name, expire_at}]`（≤7 天，最多 5 条）与精确计数 `expiring_soon`。
- 应用页签挂载即加载统计；有临期应用时顶部出黄色 `el-alert`（标题=数量与处置建议，正文=应用名与到期时间）；列表「到期时间」7 天内到期显示橙色（`text-warn`）。

### ② 审批通知与超时自动关闭

- **站内通知**：`ApprovalService.create` 落 pending 后给**超级管理员（role_id=1）**发站内通知（`NotificationService.create_notification`，best-effort，失败只记日志）；实测铃铛出现未读红点。
- **超时自动关闭**：`expire_stale_approvals(hours=None)`（模块级无参，可被 APScheduler 直接调度）把超过 `APPROVAL_PENDING_TTL_HOURS`（新设置，默认 24h）的 pending 置为 `expired` + 意见「审批超过 N 小时未处理，系统自动关闭」+ 逐条写 `status=expired` 审计；事务提交后按 id 重取审计字段（避免访问过期行属性）。
- **注册**：`_register_business_jobs_on_startup` 增加 `ai_develop_cron:expire_approvals`（interval 10 分钟，`SchedulerUtil.sync_business_jobs` 按自己前缀，单模块失败不阻断启动）。
- 前端审批状态增加「已过期」徽标（`expired` → info），状态筛选同步可用。

### ③ MCP resources / prompts 暴露

- 资源 `aistation://capabilities`（application/json）：返回**当前凭证已授权**的能力清单（能力码/权限点/MCP 工具名/入参 schema），无上下文时按鉴权失败处理。
- 提示词 `platform_guide`（平台能力接入引导）：说明「工具即能力、敏感操作会 pending_approval、appkey 只放服务端」，并带入当前 appid。
- 二者都经传输层 `Bearer appid:appkey` 中间件鉴权，与工具同一条管道。

### ④ 试调错误富化

- `POST /apps/{id}/try` 不再把业务错误吞成 400 通用响应，直接抛统一 envelope（404 能力不存在 / 403 无权限 / 400 参数），与开放面语义一致；前端试调面板显示 `错误 [错误码] 文案`。

### 验证

- 新增/扩充用例：审批**超时关闭+审计+关闭后不可再批准**、**新鲜 pending 不受影响**、**待审批触发站内通知**、**stats 到期列表**、**MCP resources/list+read 只含授权能力**、**MCP prompts/list+get 含 appid** —— 共 9+7+7 = 与既有用例同轮全绿（单文件 14 passed / 9 passed）。
- UI 走查（1440）：应用页签临期横幅（1 个应用 7 天内到期 + 应用名与时间）、到期时间橙色、审批页「已过期」徽标 + 意见 + 仅剩「详情」、**右上角站内通知红点 1**；截图归档 `p2-apps-expiring.png`、`p2-approvals-expired.png`。

---

## 第五轮：通知可外发、日志可保留、MCP 会话可限（2026-10-23）

### 新增设置（`app/config/setting.py`）

| 键 | 默认 | 说明 |
|----|------|------|
| `APPROVAL_NOTIFY_CHANNELS` | `""` | 审批外部通道（`email,webhook,sms`，逗号分隔；空=仅站内）。复用告警模块 `app/utils/notification.py` 的 `_send_{channel}` |
| `OPEN_AUDIT_BODY_LIMIT` | `200` | 审计 request_body 单字段截断上限（夹紧 100..2000；排查期可调大） |
| `CALL_LOG_RETENTION_DAYS` | `180` | 调用日志 + MCP 会话保留天数（0=永不清理；审批行不清理） |
| `MCP_MAX_SESSIONS` | `64` | Streamable HTTP 同时在线会话上限 |
| `MCP_SESSION_IDLE_TIMEOUT` | `600` | MCP 空闲会话回收（秒） |

### ① 审批通知可外发

- `_build_approval_alarm(row)`：把审批行适配成既有告警通道认识的 `(alarm, rule)` 结构（**复用而非重写**邮件正文/签名/重试）；通道白名单 `email/webhook/sms`（`ws_push` 是告警大屏广播，不并入）。
- `_notify_external(row)`：按 `APPROVAL_NOTIFY_CHANNELS` 逐通道调用，配置读系统参数 `ai_approval_notify_{channel}`（JSON，坏 JSON 跳过该通道），SMTP/Webhook 基础参数沿用既有 `notify_smtp_*` / `notify_webhook_*`；单通道失败只记 warning。
- 与站内通知并列挂进 `ApprovalService.create`，都 best-effort。
- 审批页签提示文案补齐配置说明（外发开关 + 参数键名 + 24h 自动关闭）。

### ② 审计体上限可配 + 日志保留清理

- `_sanitize_body` 改走 `_body_limit()`（settings 夹紧）；
- `purge_integration_logs(days=None)`：按 `CALL_LOG_RETENTION_DAYS` 删超期 `ai_integration_call_logs` + `ai_integration_mcp_sessions`（审批行保留，合规留痕），返回删除行数；
- 调度新增 `ai_develop_cron:purge_logs`（interval 24h）。

### ③ MCP 会话保护

- `streamable_http_app(...)` 显式传 `max_sessions` / `session_idle_timeout`（不再吃 SDK 默认），测试断言设置键与源码引用。

### 验证

- 新增用例：告警字段映射、默认关闭不外发、email 通道被正确调用且 cfg 来自参数、坏 JSON 跳过、审计上限默认/夹紧、日志清理「超期删+未超期留+days=0 不清」、MCP 会话参数——三文件合并 **30 passed**。
- 前端 eslint/prettier/type-check 全绿；ruff 全绿。

---

## 第六轮：审批内联操作、时间快捷预设、MCP 协议面写清、用量报告（2026-10-23）

### ① 审批详情内联「批准 / 拒绝」

- 详情弹窗 footer 在 `status=pending` 时直接给出「拒绝」（plain danger）与「批准并执行」（primary），带 `module_ai:develop:approve` 权限；
- 复用列表的 `onReviewApproval`（二次确认 → 关详情 → 刷新列表），少一次「回列表找按钮」。

### ② 日志时间范围快捷预设

- 时间范围选择器旁加「今天 / 近 7 天 / 近 30 天」按钮组：填 `logFilter.range`（当天或 N 天前的 00:00 → 现在）并立即查询。

### ③ MCP 协议面写进接入文档 + 握手断言

- 接入文档 MCP 卡片补标准方法说明：`initialize` / `ping` / tools·resources·prompts 的 list/get/read，JSON-RPC 2.0（协议版本 2025-06-18，Streamable HTTP，JSON 响应）；
- 新增 `test_mcp_initialize_advertises_standard_capabilities`：握手响应 `capabilities` 必须声明 tools / resources / prompts 三面。

### ④ 用量报告（按应用，近 N 天）

- 后端 `GET /ai/develop/usage-report?days=1..90`（`insights.usage_report`）：按应用聚合 调用/成功/成功率/配额超限/被限流/Top 能力（`quota_hits` = denied 且错误含「配额」，`rate_limited` = 含「频繁」），已删除应用回退显示名；
- 前端新页签「用量报告」：近 7/30/90 天切换 + 8 列 `border stripe` 表格；
- **口径统一**：成功率 = 成功 / 全部调用（含 pending/denied），与日志页「今日概览」保持一致，避免同屏两种成功率算法（自查发现并修正）。

### 验证

- 新用例：用量报告按应用聚合与 Top、配额超限计数（含口径断言 0 成功=0.0）、MCP 握手三面能力——与既有用例合并 **10 passed（insights）+ MCP 7 passed**；ruff / eslint / prettier / type-check 全绿。
- UI 走查（1440）：用量页签数据正确（8 调用/100%/Top 能力）、审批详情 footer `关闭/拒绝/批准并执行`、时间快捷填入 `2026-10-16 00:00:00 → 现在`；三张表全部 `border`、无横向溢出（1168/1168）；截图归档 `p2-usage-report.png`、`p2-approval-detail-actions.png`、`p2-logs-quick-range.png`。
- 备注：并行跑全量 + UI 时 `test_simple_metrics_read::test_detail_metrics_log_materialized` 再次因 xdist 分发失败，单跑该文件 **6 passed**（既有顺序依赖测试，非回归）。
