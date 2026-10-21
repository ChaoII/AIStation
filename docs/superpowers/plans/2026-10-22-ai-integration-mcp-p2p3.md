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

- [ ] 步骤 1：写失败测试 `test_registry_register_and_lookup`、`test_registry_rejects_duplicate_code`、`test_capabilities_for_filters_by_perm`
- [ ] 步骤 2：跑 `uv run pytest tests/test_develop_registry.py -q`，确认 FAIL
- [ ] 步骤 3：实现 `registry.py`
- [ ] 步骤 4：跑测试确认 PASS
- [ ] 步骤 5：提交 `feat(ai): 开放平台能力注册表`

### 任务 2：数据归属列（迁移 + 模型 + service 过滤）

**文件**
- 修改：`backend/app/plugin/module_ai/agent/model.py`（`AiAgentModel` 增 `source_app_id`）、`backend/app/plugin/module_ai/agent/service.py`（`list_agents(source_app_id=None)`、`get_agent(agent_id, source_app_id=None)`、`create(data, auth, source_app_id=None)`）
- 修改：`backend/app/plugin/module_train/model.py`（`TrainTask` 增 `source_app_id`）、`backend/app/plugin/module_train/service.py`（`list_tasks(params)` 支持 `source_app_id`、`get_task(task_id, source_app_id=None)`、`create_task(data, auth, source_app_id=None)`）
- 新建：`backend/app/alembic/versions/2026_10_22_ai_open_resource_owner.py`
- 测试：`backend/tests/test_open_resource_owner.py`

**接口**
- 产出：两表新增可空列 `source_app_id Integer`（FK `ai_integration_apps.id`，`NULL` = 内部用户创建）；service 的新可选参数默认 `None` = 不过滤（内部页面行为不变）。

- [ ] 步骤 1：写失败测试：带 `source_app_id` 的 Agent 只能被同 `source_app_id` 查到；不同 app 查为 None；`list_agents(source_app_id=1)` 不返回 `source_app_id=None` 的内部 Agent
- [ ] 步骤 2：跑测试确认 FAIL
- [ ] 步骤 3：加模型列 + service 参数 + 手写迁移（`down_revision` = 当前 head；`has_column` 判断防重放）
- [ ] 步骤 4：跑测试 + `uv run pytest tests/test_embed_migration.py -q` 确认 PASS
- [ ] 步骤 5：提交 `feat(ai): Agent/训练任务支持 source_app_id 归属`

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

- [ ] 步骤 1：写失败测试：无凭证 401；未授权能力 403 且 `call_logs.status=denied`；未注册 code 404；成功调用写 `method=REST`、`status=success`、`request_body` 不含 appkey
- [ ] 步骤 2：跑测试确认 FAIL
- [ ] 步骤 3：实现 `openapi.py` 与两个端点（端点用 `Depends(get_app_api_auth)`）
- [ ] 步骤 4：跑测试确认 PASS
- [ ] 步骤 5：提交 `feat(ai): 开放 REST 能力调用端点`

### 任务 4：agent 品类 handler

**文件**
- 新建：`backend/app/plugin/module_ai/develop/handlers/__init__.py`、`handlers/agents.py`
- 测试：`backend/tests/test_develop_agents.py`

**接口**
- 产出：`def register_agent_capabilities() -> None`，注册 `agent.list` / `agent.get` / `agent.create` / `agent.update` / `agent.delete`，perm 分别 `integration:agent:{query,query,create,update,delete}`，`mcp_tool` 为 `agent_list` / `agent_get` / `agent_create` / `agent_update` / `agent_delete`。
- handler 签名统一 `async def handler(*, app_ctx: AppContext, payload: dict) -> Any`；创建时 `source_app_id=app_ctx.app_id`；读/改/删一律带 `source_app_id=app_ctx.app_id` 过滤；`auth` 传 `SimpleNamespace(user=None)` 并显式传 `created_id=None`（开放面资源无平台用户）。

- [ ] 步骤 1：写失败测试：创建后 `source_app_id == app.id`；另一 app 读/删同 id → 404；`agent.list` 只含本 app 的 Agent
- [ ] 步骤 2：跑测试确认 FAIL
- [ ] 步骤 3：实现 `handlers/agents.py` 并在 `develop/__init__.py` 导入时注册
- [ ] 步骤 4：跑测试确认 PASS
- [ ] 步骤 5：提交 `feat(ai): 开放面 Agent 能力`

### 任务 5：chat / bot 品类 handler

**文件**
- 新建：`backend/app/plugin/module_ai/develop/handlers/chat.py`
- 测试：`backend/tests/test_develop_chat.py`

**接口**
- 产出：`register_chat_capabilities()` 注册 `chat.send`（perm `integration:chat:send`）、`chat.sessions`（`integration:chat:query`）、`chat.messages`（`integration:chat:query`）、`bot.use`（`integration:bot:use`）。
- `chat.send` payload：`{kind: "agent"|"app"|"workflow", target_id: int, message: str, sid: str | None}`；实现方式：复用 `AiAgentService.run_ui_stream` / `run_app_ui_stream` / `AiWorkflowService.run_ui_stream` 的帧流，**聚合成非流式回复**：收集 `UiMessageStream` 的 `data-delta`/`text-delta` 文本与 Agno 帧的 `RunContent.content`，取最终文本 + `session_id` 返回 `{reply, session_id, kind, target_id}`；`sid` 与嵌入会话复用同一 `prepare_session` 绑定逻辑（不同 app 的 sid 隔离）。
- `chat.sessions` / `chat.messages`：仅返回本 app（`source_app_id = app.id`）的会话与消息。
- `bot.use` payload：`{app_id: int, message: str}`（AI 应用），内部走 `run_app_ui_stream` 聚合成回复。

- [ ] 步骤 1：写失败测试：`chat.send` 目标为 e2e 无模型工作流时返回 `reply` 且写审计；`chat.sessions` 不返回内部会话；`bot.use` 缺 `integration:bot:use` → 403
- [ ] 步骤 2：跑测试确认 FAIL
- [ ] 步骤 3：实现 `handlers/chat.py`（帧聚合函数 `async def _collect_reply(frames) -> str`）
- [ ] 步骤 4：跑测试确认 PASS
- [ ] 步骤 5：提交 `feat(ai): 开放面对话与机器人能力`

### 任务 6：train 品类 handler

**文件**
- 新建：`backend/app/plugin/module_ai/develop/handlers/train.py`
- 测试：`backend/tests/test_develop_train.py`

**接口**
- 产出：`register_train_capabilities()` 注册 `train.list` / `train.get` / `train.create` / `train.start` / `train.stop`，perm `integration:train:{query,query,create,start,stop}`。
- `train.create` payload：`{name, framework, dataset_id, annotation_task_id?, base_model_id?, hyperparams?}` → `TrainService.create_task(TrainTaskCreateSchema(...), auth=SimpleNamespace(user=None), source_app_id=app_ctx.app_id)`；先 `retired.ensure_active`。
- `train.start` / `train.stop`：仅允许 `source_app_id = app.id` 的任务，否则 404；`start` 调 `scheduler.start_training`。

- [ ] 步骤 1：写失败测试：创建后归属正确；跨 app 读/停 → 404；退场框架 → 400 文案含「已退场」
- [ ] 步骤 2：跑测试确认 FAIL
- [ ] 步骤 3：实现 `handlers/train.py`
- [ ] 步骤 4：跑测试确认 PASS
- [ ] 步骤 5：提交 `feat(ai): 开放面训练任务能力`

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

- [ ] 步骤 1：写失败测试：不带 Authorization → 401；带正确凭证 initialize 握手返回 `serverInfo.name`；`tools/list` 只含该 app 授权的能力；调用 `agent_list` 写 `call_logs(method=MCP)` 且 `mcp_sessions.tool_calls` 递增
- [ ] 步骤 2：跑测试确认 FAIL
- [ ] 步骤 3：实现 `mcp_server.py` 与挂载（lifespan 内 `async with server.session_manager.run():`）
- [ ] 步骤 4：跑测试确认 PASS；`curl -H "Authorization: Bearer ..." -X POST /api/v1/ai/develop-api/mcp` 冒烟
- [ ] 步骤 5：提交 `feat(ai): MCP Server（Streamable HTTP）`

### 任务 8：前端接入文档与能力清单

**文件**
- 修改：`frontend/src/views/module_ai/develop/index.vue`（接入文档页签：REST 调用示例、MCP 端点与 `mcp.json` 配置示例、能力清单表；「即将开放」标记删除）
- 修改：`frontend/src/views/module_ai/develop/components/EmbedDialog.vue`（如需展示 MCP 端点则加一行只读文本，保持框架样式）
- 测试：无自动化；用 Playwright 截图 + 计算样式探测（见 `AGENTS.md` §5）

- [ ] 步骤 1：改写文档页签（表格 `border stripe`、代码块沿用既有样式）
- [ ] 步骤 2：`pnpm run type-check` + eslint/stylelint/prettier
- [ ] 步骤 3：无头浏览器截图（文档页签有数据态/空态、MCP 会话页签）+ 计算样式探测与参照页数值比对
- [ ] 步骤 4：提交 `docs(ai): 接入文档补齐 REST/MCP 示例与能力清单`

### 任务 9：全量自查

- [ ] 步骤 1：`uv run pytest -q -n 4`（全量）与前端 `type-check`、lint
- [ ] 步骤 2：真实冒烟：起后端 → 用 appid/appkey 调 `POST /ai/develop-api/capabilities/agent.create`、`agent.list`，再用 MCP 客户端（或裸 HTTP initialize + tools/call）跑一次工具调用；管理端确认调用日志与 MCP 会话两页签有记录
- [ ] 步骤 3：截图归档到 `.openchamber/screenshots/`，逐张读图对照框架页面
- [ ] 步骤 4：更新 spec 的里程碑状态与本计划的执行记录；提交
