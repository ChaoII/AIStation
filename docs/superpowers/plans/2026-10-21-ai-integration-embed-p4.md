# AI 集成 P4'：换票 Token 底座 + 三形态嵌入 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 落地 AI 集成开放平台 v2 的 P4'——短期 access_token 换票底座、Agent/AI 应用/工作流三形态免平台账号嵌入对话（iframe + script SDK + postMessage 全事件流）、管理端嵌入弹窗与 token 治理，并整体拆除旧 `/share` 通道。

**Architecture:** 后端在 `app/plugin/module_ai/develop/` 内扩展：新表 `ai_integration_access_tokens`（token 只存 sha256、绑 app+kind+目标）与 `ai_integration_embed_sessions`（sid→平台会话映射 + TTL），新增 `EmbedRouter`（`/ai/embed/*`，`Bearer <token>` 鉴权）与换票端点；`/embed/run` 复用三形态既有 `*_ui_stream` service（auth 传 `SimpleNamespace(user=None)` 垫片，`uid=None` 已被既有代码容忍），SSE 协议原样（agent/app 走 `agno_stream_response`、workflow 走 `ui_stream_response`）。前端新增独立公开路由 `/#/embed`（白名单替换 `/share`），自研 `EmbedChatTransport`（Bearer token + 双协议帧映射）+ widget 质感对话页；后端提供 `/ai/embed/sdk.js`。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + PostgreSQL JSONB + Redis（固定窗口限流/日配额）；Vue3 + Element Plus + Vercel AI SDK `useChat`；pytest（`PYTEST_NO_APP=1` 快速模式）。

**Spec:** `docs/superpowers/specs/2026-10-21-ai-integration-open-platform-design.md`（v2，已批准；计划从 spec 论证，执行者需同时读 spec 与本计划）

## Global Constraints

- **禁匿名铁律**：任何 `/ai/embed/*` 业务端点缺凭证/过期/吊销一律 401；appkey 永不进浏览器、不进嵌入代码、不进日志/审计。
- 所有与用户交互文本用**中文**；代码注释用中文；提交信息 `feat(ai): 中文描述` / `fix(ai): …` / `docs(ai): …`。
- 迁移**手写**：文件 `app/alembic/versions/2026_10_21_ai_integration_embed.py`，`down_revision="c9d0e1f2a3b4"`；对既有表的增删列一律 `sa.inspect(bind).has_table()/has_column()` 防护；SQLite 空库全链重放必须过（`tests/test_migration_replay.py`）。
- 权限码精确值：换票 `integration:embed:use`（经 `require_app_perm`）；管理端 `module_ai:develop:{query,create,update}`；嵌入弹窗入口 `module_ai:develop:query`。
- token 策略：`token_urlsafe(32)` 明文仅换票/签发响应返回一次；库内仅 `sha256`；换票默认 TTL 1800s、上限 86400s、下限 60s；管理端体验票固定 7200s。
- 限流：Redis 固定窗口 `INCR`+`EXPIRE 60`，`EMBED_RATE_TOKEN_PER_MIN=30` / `EMBED_RATE_IP_PER_MIN=60`（`app/config/setting.py` 新增，env 可调）；配额 `app.quota["embed"]` 按自然日，超限 429 中文文案。
- SSE 复用既有 `UI_STREAM_HEADERS`（`app/core/sse.py` 契约，含 `no-transform`/`x-accel-buffering`），禁止手抄。
- postMessage 信封：`{source:"ai-embed", version:1, event, payload}`，事件仅 7 类：`ready/user_message/reply_start/reply_delta/reply_done/error/token_expired`；下行 `{source:"ai-host", version:1, command}` 命令 `setToken/sendMessage/resize/destroy`；SDK 校验 `event.origin === webBase 的 origin`。
- 品类中文名 `embed` = **「网页嵌入」**（后端 `capabilities.py` 与前端 `develop/index.vue` 的 `CATEGORIES` 两处同步）。
- 删除/吊销类操作前端必须 `ElMessageBox.confirm` 二次确认（文案含影响范围与不可逆性），按钮带 `v-hasPerm`。
- **界面硬标准**：嵌入页与嵌入弹窗必须与平台同源（Element Plus 变量、`--el-*`，禁自造次级主题、禁零散 font-size），逐屏截图多模态核对，不达标返工；实现 UI 前先调用 `frontend-design` 技能。
- 测试效率：纯逻辑用 `PYTEST_NO_APP=1`；日常跑单文件；提交前 `uv run pytest -q -n 4`。**本 worktree 无 `backend/env/.env.dev`（被 gitignore），跑管理面集成测试前先 `$env:CAPTCHA_ENABLE="false"`**，否则 `auth_headers` fixture 登录被验证码拦截。
- 改后端后验证必须确认新代码生效（`/openapi.json` 出现新路由），不靠"端口有响应"推断；开发实例用 `--no-reload`。
- 旧通道拆除为**硬需求**：`/share` 路由、`ShareRun.vue`、`share_token` 列与相关端点/服务/测试、工作流编辑器分享 UI 全部消失。

## Review Focus

最可能咬人的输入与失败模式（每条的测试钉在对应任务里）：

1. **token 每请求校验，而非只在签发时**：过期/吊销后即便 app 正常也必须 401 —— Task 5（`test_embed_api.py`：过期行 401、吊销后 401）。
2. **auth 垫片 `uid=None` 在三形态 run 链路不炸**（`auth.user.id` 直接访问点会 AttributeError）—— Task 6（三 kind 成功路径用例 + mock 既有 run 测试写法）。
3. **sid 绑定越权**：同 app 内换目标复用 sid、或跨 app 撞 sid，必须 403 而非串会话 —— Task 6（绑定冲突用例）。
4. **token 明文不落审计**：`call_logs.request_body` 不得出现明文 token/appkey —— Task 4 与 Task 6（响应成功后查库断言）。
5. **限流/配额 429 语义**：cap=1 时第二发必须 429 且中文文案可读；配额键按日滚动 —— Task 7（两次调用断言）。
6. **SSE 响应头契约**：`/embed/run` 响应必须带 `UI_STREAM_HEADERS` 全集（代理下不缓冲）—— Task 6（响应头断言）。
7. **迁移删列与空库全链重放**：`share_token` 删除分支不得让 SQLite 重放炸掉 —— Task 3（`test_migration_replay` + 升降级往返）。
8. **旧 `/share` 失效**：拆除后端点必须 404，前端路由与白名单不残留 —— Task 1（404 断言 + type-check）。

---

### Task 1: 拆除旧 /share 通道

**Files:**
- Modify: `backend/app/plugin/module_ai/workflow/controller.py`（删 `create_share`、`share_run` 与 `AiWorkflowShareRunSchema`/`ui_stream_response` 中仅为 share 引入的部分）
- Modify: `backend/app/plugin/module_ai/workflow/service.py`（删 `generate_share_token`、`_get_by_share_token`、`share_ui_stream`，约 987-1100 行）
- Modify: `backend/app/plugin/module_ai/workflow/schema.py`（删 `AiWorkflowShareRunSchema`）
- Modify: `backend/app/plugin/module_ai/workflow/model.py`（删 `share_token` 列声明，约 36 行）
- Modify: `backend/tests/test_ai_workflow.py`（share/run 用例改为断言 404，约 1458 行起）
- Modify: `frontend/src/router/index.ts`（`/share` 路由块直接删除——`/embed` 路由由 Task 10 添加）
- Modify: `frontend/src/plugins/permission.ts:9`（白名单 `["/login", "/share"]` → `["/login"]`，`/embed` 由 Task 10 加入）
- Delete: `frontend/src/views/module_ai/workflow/ShareRun.vue`
- Modify: `frontend/src/views/module_ai/workflow/components/WorkflowEditor.vue`（删分享抽屉模板约 520-545 行与 script 中 `shareRunVisible/shareToken/shareLink/copyShareLink/copyShareEmbed/runShare/shareMessage/shareOutput/shareRunning/shareError/shareTrace/shareTraceOpen` 及 `triggerShare` 相关约 1495-1660 行；工具栏保留一个「嵌入对话」按钮，点击 `ElMessage.info("对话嵌入请前往「AI 集成 → 应用管理」，在目标应用的「嵌入」中生成代码")`）
- Modify: `docs/ontology-usage.md:1041`（敏感字段示例中移除 `ai_workflows.share_token`）
- Test: `backend/tests/test_ai_workflow.py`

**Interfaces:**
- Consumes: 无。
- Produces: 无（纯拆除）；后续任务不再存在任何 `share_token` 引用。

- [x] **Step 1: 写失败测试**

在 `tests/test_ai_workflow.py` 将原 share/run 用例改写为：

```python
def test_legacy_share_run_removed(test_client):
    r = test_client.post("/api/v1/ai/workflows/share/run", json={"token": "x", "message": "hi"})
    assert r.status_code == 404
```

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_ai_workflow.py -q -k "share"`（backend，先 `$env:CAPTCHA_ENABLE="false"`）
Expected: FAIL（端点仍存在，返回非 404）

- [x] **Step 3: 按 Files 清单删除后端与前端代码**

后端删端点/服务/Schema/model 列声明；前端删路由、白名单项、`ShareRun.vue`、编辑器分享 UI（替换为引导按钮）。

- [x] **Step 4: 跑测试确认通过 + 前端静态检查**

Run: `uv run pytest tests/test_ai_workflow.py -q` → PASS；`cd frontend && pnpm run type-check` → 0 error（确认无残留引用）。
Expected: 通过；若 type-check 报 `ShareRun`/`AiShareRun` 残留引用则回到 Step 3 补删。

- [x] **Step 5: 提交**

```bash
git add -A backend/app/plugin/module_ai/workflow backend/tests/test_ai_workflow.py frontend/src docs/ontology-usage.md
git commit -m "refactor(ai): 整体拆除旧工作流 /share 分享通道"
```

---

### Task 2: token 数据模型 + 纯逻辑服务

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/model.py`（追加两个模型）
- Modify: `backend/app/plugin/module_ai/develop/service.py`（追加 token 纯逻辑函数）
- Test: `backend/tests/test_embed_token.py`

**Interfaces:**
- Consumes: P1 的 `DevelopService`、`_hash_appkey` 同文件上下文。
- Produces（Task 3/4/5 依赖，签名精确）:
  - `class AiIntegrationAccessTokenModel(ModelMixin)`：`__tablename__="ai_integration_access_tokens"`，列 `app_id` Int FK `ai_integration_apps.id`、`appid` Str(64)、`kind` Str(16)、`target_id` Int、`token_hash` Str(128) unique+index、`expires_at` DateTime、`revoked` Bool default False、`issued_by` Str(16)、`use_count` Int default 0、`last_used_at` DateTime nullable。
  - `class AiIntegrationEmbedSessionModel(ModelMixin)`：`__tablename__="ai_integration_embed_sessions"`，列 `app_id` Int FK、`sid` Str(64)、`kind` Str(16)、`target_id` Int、`session_id` Int（映射 `ai_assistant_sessions.id`）、`expires_at` DateTime、`last_active_at` DateTime；`(app_id, sid)` 复合唯一索引。
  - `_generate_embed_token() -> str`（`secrets.token_urlsafe(32)`）
  - `_hash_embed_token(token: str) -> str`（sha256 hex）
  - `clamp_embed_ttl(ttl: int | None) -> int`（None→1800；`<60`→60；`>86400`→86400；否则原值）

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_token.py（PYTEST_NO_APP=1）
def test_embed_token_generate_and_hash():
    from app.plugin.module_ai.develop.service import _generate_embed_token, _hash_embed_token
    t = _generate_embed_token()
    assert len(t) >= 32 and ":" not in t
    assert _hash_embed_token(t) == hashlib.sha256(t.encode()).hexdigest()

def test_clamp_embed_ttl():
    from app.plugin.module_ai.develop.service import clamp_embed_ttl
    assert clamp_embed_ttl(None) == 1800
    assert clamp_embed_ttl(30) == 60
    assert clamp_embed_ttl(999999) == 86400
    assert clamp_embed_ttl(3600) == 3600

def test_access_token_model_columns():
    # 断言 token_hash unique、revoked 默认 False、(app_id, sid) 唯一索引存在
    ...
```

- [x] **Step 2: 跑测试确认失败**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_embed_token.py -q`
Expected: FAIL（ImportError）

- [x] **Step 3: 实现模型与纯函数**

按 Produces 签名在 `model.py` 追加两模型、`service.py` 追加三函数（照 `_generate_appid` 的注释风格写中文 docstring）。

- [x] **Step 4: 跑测试确认通过**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_embed_token.py -q` → PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests/test_embed_token.py
git commit -m "feat(ai): 定义嵌入 token 与嵌入会话模型及纯逻辑"
```

---

### Task 3: 手写迁移（建两表 + sessions 归属列 + 删 share_token）

**Files:**
- Create: `backend/app/alembic/versions/2026_10_21_ai_integration_embed.py`
- Modify: `backend/app/plugin/module_ai/sessions/model.py`（`AiSessionModel` 追加 `source_app_id: int | None`，FK `ai_integration_apps.id`，nullable，注释「来源集成应用ID（空=内部用户）」）
- Test: `backend/tests/test_develop_models.py`（追加列断言）、`backend/tests/test_embed_migration.py`

**Interfaces:**
- Consumes: Task 2 的两模型；当前 head `c9d0e1f2a3b4`。
- Produces: `down_revision="c9d0e1f2a3b4"`、`revision="…"`（自生成）；四段操作全部带防护：
  1. `has_table("ai_integration_access_tokens")` 为假才 `op.create_table`（Task 2 模型同名同列）；
  2. `has_table("ai_integration_embed_sessions")` 同上；
  3. `has_table("ai_assistant_sessions") and not has_column(..., "source_app_id")` 才 `op.add_column`；
  4. `has_table("ai_workflows") and has_column(..., "share_token")` 才 `op.drop_column`。
  downgrade 对称。

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_migration.py（参照 tests/test_migration_replay.py 现有夹具写法）
def test_embed_migration_upgrade_downgrade_roundtrip():
    # upgrade head → 两表存在、ai_assistant_sessions 有 source_app_id、
    # ai_workflows 无 share_token 列
    # downgrade -1 → 两表消失、source_app_id 消失、share_token 列回归
    # 再 upgrade head → 复原
```

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_embed_migration.py -q`（`$env:CAPTCHA_ENABLE="false"`）
Expected: FAIL（迁移不存在）

- [x] **Step 3: 手写迁移 + sessions 模型列**

按 Produces 四段防护实现（`sa.inspect(bind)` 判断），并给 `AiSessionModel` 加 `source_app_id`。

- [x] **Step 4: 跑测试与全链重放**

Run: `uv run pytest tests/test_embed_migration.py tests/test_migration_replay.py tests/test_develop_models.py -q`
Expected: 全 PASS（SQLite 空库重放含删列分支不炸）

- [x] **Step 5: 提交**

```bash
git add backend/app/alembic backend/app/plugin/module_ai/sessions backend/tests
git commit -m "feat(ai): 嵌入 token/会话迁移与会话归属列（含删 share_token）"
```

---

### Task 4: 换票端点 `POST /develop-api/auth/token`

**Files:**
- Create: `backend/app/plugin/module_ai/develop/embed.py`（`EmbedService`）
- Modify: `backend/app/plugin/module_ai/develop/schema.py`（`EmbedTokenIssueSchema`）
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（`OpenApiRouter` 追加端点）
- Test: `backend/tests/test_embed_exchange.py`

**Interfaces:**
- Consumes: P1 `get_app_api_auth`、`DevelopService.log_call`、`require_app_perm`；Task 2 的 `_generate_embed_token/_hash_embed_token/clamp_embed_ttl` 与模型。
- Produces（Task 5/6 依赖）:
  - `class EmbedService`（`embed.py`）:
    - `async def get_target(kind: str, target_id: int) -> dict | None` —— 返回 `{"name": str, "description": str, "enabled": bool}` 或 `None`；分派 `AiAgentService.get_agent` / `AiAppService.get_app` / `AiWorkflowService.get_workflow`（三个既有 getter，返回 dict 含 `name`/`enabled`；`description` 取不到给 `""`）。
    - `async def issue_token(app: AiIntegrationAppModel, kind: str, target_id: int, ttl: int | None, issued_by: str) -> dict` —— clamp TTL、生成+哈希入库、返回 `{"token", "expires_in", "expires_at"}`（`expires_at` 用 `DateTimeStr` 同款 `strftime` 输出）。
  - schema: `EmbedTokenIssueSchema(kind: Literal["agent","app","workflow"], target_id: int, ttl: int | None = None)`。
  - 路由：`@OpenApiRouter.post("/auth/token", summary="换票签发嵌入短期令牌")` → 依赖 `Depends(get_app_api_auth)`，体内 `require_app_perm(ctx, "integration:embed:use")`（缺权抛 403 + denied 审计），`get_target` 为 None → `CustomException(msg="嵌入目标不存在", status_code=404)`；成功 `SuccessResponse(data=…)` 并 `log_call(category="embed", capability="token.issue", method="REST", status=...)`。

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_exchange.py（test_client + auth_headers；先建含 embed 权限的 app）
def test_exchange_ok_returns_token_once_and_stores_hash(...):
    r = post("/api/v1/ai/develop-api/auth/token", headers=app_auth,
             json={"kind": "agent", "target_id": 1})
    assert r.status_code == 200
    token = r.json()["data"]["token"]
    # 库内只有 sha256：查 call_logs.request_body 与响应外的任何行不含 token 明文
def test_exchange_denied_without_embed_perm(...):  # app 无 embed 权限 → 403
def test_exchange_target_not_found(...):          # target_id=999999 → 404
def test_exchange_invalid_appkey(...):            # 错误凭证 → 401
```

（app 的创建与凭证获取复用 `test_develop_crud.py` 既有写法；无有效 agent 时用 `AiAgentService.create` 造一个或取库里已有行。）

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_embed_exchange.py -q` → Expected: FAIL（404 路由不存在）

- [x] **Step 3: 实现 `EmbedService.get_target/issue_token` 与端点**

按 Produces 签名；审计复用 `DevelopService.log_call`（app 行从 `ctx.app_id` 取，参照 `controller.py:auth_verify` 的写法）。

- [x] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_embed_exchange.py -q` → PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests/test_embed_exchange.py
git commit -m "feat(ai): 开放面换票端点签发嵌入短期 token"
```

---

### Task 5: Embed 公开面：`EmbedRouter` + token 依赖 + `/embed/meta`

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/auth.py`（追加 `EmbedContext`、`get_embed_ctx`）
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（追加顶层 `EmbedRouter`）
- Test: `backend/tests/test_embed_api.py`

**Interfaces:**
- Consumes: Task 2/4 的模型与 `EmbedService.get_target`。
- Produces（Task 6/7/8 依赖）:
  - `@dataclass EmbedContext`：`token_id: int`、`app_id: int`、`appid: str`、`kind: str`、`target_id: int`、`perms: set[str]`、`quota: dict | None`、`expires_at: datetime`、`token_hash12: str`。
  - `async def get_embed_ctx(authorization: str | None = Header(None)) -> EmbedContext` —— 解析 `Bearer <raw>`；按 `_hash_embed_token(raw)` 查 `ai_integration_access_tokens`（不存在/`revoked`/`expires_at<=now` → 401）；再取 app 行（禁用/过期 → 401）；成功时**同事务** `use_count+=1`、`last_used_at=now`；统一 401 文案「鉴权失败」（`CustomException(status_code=401)`），不区分原因。
  - `EmbedRouter = APIRouter(route_class=OperationLogRoute, prefix="/embed", tags=["AI-嵌入"])`，`@EmbedRouter.get("/meta")` → `Depends(get_embed_ctx)` + 缺 `integration:embed:use` 抛 403；返回 `SuccessResponse(data={"kind","target_id","name","welcome","expire_at"})`，`welcome = description or ""`，目标消失 → 404。
  - 页面层辅助 `def embed_status_error(status: int) -> CustomException`（可选，供 Task 6 复用 401/403 构造）。

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_api.py
def test_meta_missing_header_401(test_client): ...
def test_meta_garbage_token_401(test_client): ...        # Bearer not-a-token
def test_meta_expired_token_401(test_client, expired_token_row): ...   # 直接造 expires_at 过期行
def test_meta_revoked_token_401(test_client, revoked_token_row): ...
def test_meta_after_app_disabled_401(test_client, valid_token): ...    # app.enabled=False 后 401
def test_meta_ok_returns_target_name(test_client, valid_token): ...    # 200 且 name 非空
def test_meta_after_perm_removed_403(test_client, valid_token): ...    # 把 app.capabilities 清空后再调
def test_meta_increments_use_count(test_client, valid_token): ...      # use_count 递增、last_used_at 非空
```

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_embed_api.py -q` → Expected: FAIL（404）

- [x] **Step 3: 实现 `EmbedContext`/`get_embed_ctx`/`EmbedRouter`/`meta`**

按 Produces 签名；`EmbedRouter` 写在 `controller.py`（模块自动发现只认 `controller.py` 顶层 Router）。

- [x] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_embed_api.py -q` → PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests/test_embed_api.py
git commit -m "feat(ai): 嵌入公开面 token 鉴权依赖与 meta 端点"
```

---

### Task 6: `/embed/run` SSE 对话通道（sid 会话 + 三形态委派 + 审计）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/embed.py`（`prepare_session`、`run_stream`）
- Modify: `backend/app/plugin/module_ai/develop/schema.py`（`EmbedRunSchema`）
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（`@EmbedRouter.post("/run")`）
- Test: `backend/tests/test_embed_run.py`

**Interfaces:**
- Consumes: Task 5 `EmbedContext/get_embed_ctx`；Task 4 `EmbedService.get_target`；`AiSessionService.create/get_messages`（`sessions/service.py`，`user_id=None` 合法）；`AiAgentService.run_ui_stream(agent_id, ui_messages, auth, variables=None, session_id=None)`、`run_app_ui_stream(app_id, ui_messages, auth, variables, session_id)`、`AiWorkflowService.run_ui_stream(workflow_id, ui_messages, auth, variables, session_id, redis=None, timeout_seconds=None)`；包装器 `agno_stream_response`（照 `agent/controller.py` 的 import 来源）、`ui_stream_response`（`streaming.py`）；`DevelopService.log_call`。
- Produces:
  - schema：`EmbedRunSchema(sid: str = Field(min_length=8, max_length=64), message: str = Field(min_length=1, max_length=4000))`。
  - `async def prepare_session(ctx: EmbedContext, sid: str) -> tuple[int, bool]`：
    - 按 `(app_id, sid)` 查映射；**存在但 `kind`/`target_id` 与 ctx 不符 → `CustomException(msg="会话绑定无效", status_code=403)`**；
    - 无映射 → `AiSessionService.create(title=f"嵌入-{kind}-{target_id}", user_id=None)` + 建映射行（`expires_at=now+24h`）+ 会话行打 `source_app_id=ctx.app_id` → 返回 `(session_id, True)`；
    - 映射过期 → 新建平台会话、更新映射行（session_id/expires_at/last_active_at）→ `(new_id, True)`；未过期 → 刷新 `last_active_at` → `(session_id, False)`。
    - 返回 bool 含义 = `session_reset`（是否新建了平台会话）。
  - `async def run_stream(ctx, session_id: int, session_reset: bool, message: str, redis) -> AsyncIterator[str]`：
    1. `history = await AiSessionService.get_messages(session_id)` → `ui_messages = [{"role": m.role, "parts": m.parts} for m in history] + [{"role":"user","parts":[{"type":"text","text":message}]}]`；
    2. `auth = SimpleNamespace(user=None)`（垫片；既有代码 `getattr(getattr(auth,"user",None),"id",None)` → None）；
    3. 先 yield `UiMessageStream().data("embed", {"session_reset": session_reset})`（**首帧**），随后按 `ctx.kind` 委派：`agent→AiAgentService.run_ui_stream(ctx.target_id, ui_messages, auth, None, session_id)`、`app→run_app_ui_stream(...)`、`workflow→AiWorkflowService.run_ui_stream(ctx.target_id, ui_messages, auth, None, session_id, redis=redis)`，逐帧透传；
    4. `finally` 内审计：`log_call(category="embed", capability="run", method="EMBED", transport="sse", request_path="/run", request_body={"sid","kind","target_id","message截断80字"}, status="success"/"error", latency_ms=实测, session_id=str(session_id))`（app 行按 `ctx.app_id` 取）。
  - 路由：`@EmbedRouter.post("/run")` —— `Depends(get_embed_ctx)` → 缺 `integration:embed:use` 抛 403（并写 denied 审计）→ `prepare_session`（403 可能抛出）→ 返回 `ui_stream_response(gen)`（workflow）或 `agno_stream_response(gen)`（agent/app）。**perm/绑定/限流类错误必须在返回流之前抛出（JSON 错误），不得进 SSE。**

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_run.py（mock 层参照 tests/test_ai_workflow.py 中 run/stream 既有写法）
def test_run_missing_token_401(test_client): ...
def test_run_ok_agent_stream_has_embed_frame_and_headers(...):
    r = post("/api/v1/ai/embed/run", headers=token_auth, json={"sid": "sid-abcdefgh", "message": "你好"})
    assert r.status_code == 200
    assert r.headers.get("x-vercel-ai-ui-message-stream")   # UI_STREAM_HEADERS 契约
    assert "no-transform" in r.headers.get("cache-control", "")
    assert '"type":"data-embed"' in r.text.replace(" ", "")  # 首帧 session_reset
def test_run_ok_all_three_kinds(...):      # kind=agent/app/workflow 各一条（mock LLM/引擎）
def test_run_sid_target_conflict_403(...): # 同 app 换 target 复用同 sid → 403
def test_run_expired_token_401(...):
def test_run_writes_embed_audit(...):      # method=EMBED、category=embed、request_body 不含明文 token
def test_run_disabled_target_error_frame(...):  # 目标停用 → 流内 error 帧（既有语义）
```

- [x] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_embed_run.py -q` → Expected: FAIL（404）

- [x] **Step 3: 实现 `prepare_session`/`run_stream`/`run` 端点**

按 Produces；注意历史消息取的是**服务端会话**（`get_messages`），与 spec §9.3「请求体只带 sid+message」一致。

- [x] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_embed_run.py -q` → PASS；再跑 `uv run pytest tests/test_embed_api.py tests/test_embed_exchange.py -q` 确认无回归。

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests/test_embed_run.py
git commit -m "feat(ai): 嵌入对话流式通道复用三形态 run 服务"
```

---

### Task 7: 限流与配额（429）

**Files:**
- Modify: `backend/app/config/setting.py`（`EMBED_RATE_TOKEN_PER_MIN: int = 30`、`EMBED_RATE_IP_PER_MIN: int = 60`，置于 CAPTCHA 设置附近的独立注释段「AI 集成嵌入」）
- Modify: `backend/app/plugin/module_ai/develop/embed.py`（`check_limits`）
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（`/embed/run` 在 `prepare_session` 前调用）
- Test: `backend/tests/test_embed_limits.py`

**Interfaces:**
- Consumes: `EmbedContext`、settings。
- Produces: `async def check_limits(redis, ctx: EmbedContext, ip: str) -> None` —— redis 为空时跳过（可测降级）；固定窗口 `INCR`+`EXPIRE 60`，键 `ai:embed:rl:t:{ctx.token_hash12}` 与 `ai:embed:rl:ip:{ip or "na"}`，cap 取 settings；配额键 `ai:embed:quota:{ctx.app_id}:{YYYYMMDD}`（本地自然日）INCR，cap 取 `(ctx.quota or {}).get("embed")`（int 且 >0 才限）；超限抛 `CustomException(status_code=429)`，文案分别为「访问过于频繁，请稍后再试」「今日嵌入调用配额已用完」。

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_limits.py（自备最小 FakeRedis：incr/expire 计数桩）
def test_rate_limit_token_second_call_429(monkeypatch, ...):
    monkeypatch.setattr(settings, "EMBED_RATE_TOKEN_PER_MIN", 1)
    第一次 run → 非 429；第二次 → 429 且 msg 含「频繁」
def test_quota_daily_429(...):   # app.quota={"embed":1} → 第二次 429 且 msg 含「配额」
def test_no_redis_skips_limit(...):  # redis=None → 放行
```

- [x] **Step 2: 跑测试确认失败** → Run: `uv run pytest tests/test_embed_limits.py -q` → FAIL

- [x] **Step 3: 实现 settings 与 `check_limits` 并接入 `/embed/run`**

- [x] **Step 4: 跑测试确认通过** → PASS + 复跑 `tests/test_embed_run.py`（接入点未破坏既有用例）

- [x] **Step 5: 提交**

```bash
git add backend/app backend/tests/test_embed_limits.py
git commit -m "feat(ai): 嵌入通道 token/IP 限流与按日配额"
```

---

### Task 8: 管理端 token 治理端点（列表/体验票/吊销）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/schema.py`（`EmbedMintSchema`）
- Modify: `backend/app/plugin/module_ai/develop/service.py`（`list_tokens`、`revoke_token`）
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（`DevelopRouter` 追加 3 端点）
- Test: `backend/tests/test_embed_admin_tokens.py`

**Interfaces:**
- Consumes: Task 2/4 模型与 `issue_token`。
- Produces:
  - `GET /ai/develop/tokens?app_id=`（`AuthPermission(["module_ai:develop:query"])`）→ `{"items":[{id, kind, target_id, target_name, issued_by, expires_at, revoked, use_count, last_used_at, created_time}]}`（`target_name` 经 `EmbedService.get_target`，失效给 `"—"`；不分页，单应用 token 量小）。
  - `POST /ai/develop/tokens`（perm `create`）body `EmbedMintSchema(kind, target_id)` → `issue_token(..., ttl=7200, issued_by="admin")` → `SuccessResponse` 含一次性明文。
  - `PUT /ai/develop/tokens/{token_id}/revoke`（perm `update`）→ `revoke_token(token_id) -> bool`（False → ErrorResponse「令牌不存在」）。
  - `async def list_tokens(app_id: int) -> list[dict]`、`async def revoke_token(token_id: int) -> bool`（均在 `service.py` 的 `DevelopService` 或模块级，就近放 `DevelopService`）。

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_admin_tokens.py（admin JWT：auth_headers）
def test_mint_then_list_then_revoke_then_token_dead(...):
    mint → 明文返回一次 → list 可见行 → revoke → 该 token 调 /embed/meta 变 401
def test_tokens_list_requires_perm(...):   # 参照 tests/test_develop_admin.py 的无权限用户写法 → 403
def test_revoke_unknown_404(...):
```

- [x] **Step 2: 跑测试确认失败** → FAIL

- [x] **Step 3: 实现三端点与 service 方法**

- [x] **Step 4: 跑测试确认通过** → PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests/test_embed_admin_tokens.py
git commit -m "feat(ai): 管理面嵌入令牌列表签发与吊销"
```

---

### Task 9: SDK 静态脚本 `/ai/embed/sdk.js`

**Files:**
- Create: `backend/app/plugin/module_ai/develop/static/ai-assistant.js`
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（`@EmbedRouter.get("/sdk.js")`）
- Test: `backend/tests/test_embed_sdk.py`

**Interfaces:**
- Consumes: spec §9.7 契约（信封/7 事件/4 命令/webBase origin 校验）。
- Produces:
  - 路由 `GET /ai/embed/sdk.js` → 读 `Path(__file__).parent` 所在 `develop/static/ai-assistant.js`，`PlainTextResponse(media_type="application/javascript", headers={"Cache-Control": "no-cache"})`，**无鉴权**（静态代码、零凭证）。
  - SDK 行为（vanilla JS，IIFE，挂 `window.AiAssistant`）：
    - `init({container, token, apiBase?, webBase?, theme?})`：`apiBase` 缺省 = `document.currentScript.src` 去掉 `/embed/sdk.js` 后缀；`webBase` 缺省 = `new URL(apiBase).origin + "/web"`；创建 iframe `src = webBase + "/#/embed?token=" + encodeURIComponent(token) + (theme?.primary ? "&primary=" + encodeURIComponent(theme.primary) : "")`，样式 `border:0;width:100%;height:100%;min-height:420px;border-radius:12px`；返回句柄。
    - 上行监听 `window.message`：`event.source === iframe.contentWindow && event.origin === new URL(webBase).origin` 且信封 `source==="ai-embed"` 才处理——触发 `on(event,cb)` 已注册回调 + `window.postMessage(envelope, "*")` 再广播。
    - 句柄方法：`setToken(t)` / `sendMessage(text)` / `resize(w,h)` / `destroy()`（下行为 `{source:"ai-host",version:1,command,payload}` 发往 `iframe.contentWindow`）；`on(event, cb)` 返回退订函数。
  - 页面内注释中文说明「token 由宿主服务端换票获取，勿在前端放 appkey」。

- [x] **Step 1: 写失败测试**

```python
# tests/test_embed_sdk.py
def test_sdk_js_served(test_client):
    r = test_client.get("/api/v1/ai/embed/sdk.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "AiAssistant" in r.text and "setToken" in r.text
    assert "appkey" not in r.text.lower() or "勿在前端" in r.text  # 不得出现真实密钥字样
    assert "stew7" not in r.text  # 任何明文凭证样例不存在
```

- [x] **Step 2: 跑测试确认失败** → FAIL

- [x] **Step 3: 实现 JS 文件与端点**（按 Produces 行为清单；JS 内注释中文）

- [x] **Step 4: 跑测试确认通过** → PASS

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests/test_embed_sdk.py
git commit -m "feat(ai): 提供嵌入 script SDK 静态端点"
```

---

### Task 10: 前端嵌入页 `/#/embed`（widget UI，视觉硬标准）

**Files:**
- Create: `frontend/src/composables/ai/embedChatTransport.ts`
- Create: `frontend/src/composables/ai/useEmbedChat.ts`
- Create: `frontend/src/views/module_ai/embed/EmbedChat.vue`
- Modify: `frontend/src/router/index.ts`（`/share` 块位置替换为 `{path:"/embed", name:"AiEmbed", meta:{hidden:true,title:"对话嵌入"}, component: () => import("@/views/module_ai/embed/EmbedChat.vue")}`）
- Modify: `frontend/src/plugins/permission.ts:9`（白名单 → `["/login", "/embed"]`）

**Interfaces:**
- Consumes: `parseAgnoFrame`/`mapAgnoEvent`（`composables/ai/agnoChatTransport.ts` 既有导出，复用勿重写）；`useChat`（`@ai-sdk/vue`）返回形状参照 `composables/ai/useAiChat.ts` 的 status 映射（`ready|submitted|streaming|error` 兼容枚举）；`RichContent.vue`（`props: {content: string}`）。
- Produces:
  - `embedChatTransport.ts`：
    - `interface EmbedChatTransportOptions { path: string; base?: string; getToken: () => string; buildBody: () => Record<string, unknown>; onHttpError?: (status: number) => void; onTextDelta?: (delta: string) => void; onAuxFrame?: (type: string, data: any) => void; }`
    - `class EmbedChatTransport implements ChatTransport<UIMessage>`：`sendMessages` 内 `body = {message: 末条用户消息 text parts 拼接, ...buildBody()}`（**不含 messages[]**，上下文在服务端），header 只带 `Authorization: Bearer <getToken()>`（不带 JWT）；`!res.ok` → `onHttpError(status)` + enqueue error chunk；帧循环：`data.type` 属 AI SDK 协议（`start/text-*/reasoning-*/finish/error/start-step/finish-step`）→ **原样 enqueue**；`sources/data-embed/node-status/tool-*` → `onAuxFrame` 拦截不 enqueue；Agno `event:` 帧 → `mapAgnoEvent` 转换；`text-delta` 时回调 `onTextDelta`。
  - `useEmbedChat(options)`：组合 `useChat` + `EmbedChatTransport`，返回 `{messages, status, error, isStreaming, sendMessage, stop}`（镜像 `useAiChat` 的映射；options 含 `getToken/buildBody/id/initialMessages/onHttpError/onTextDelta/onAuxFrame`；**不提供 regenerate**）。
  - `EmbedChat.vue`（单根 div，全部弹层/覆盖收进根内——Transition 单根陷阱）：
    - 入参：`route.query.token`（缺失 → 全屏态「缺少访问凭证」，不发 ready）、`route.query.primary`（`/^#[0-9a-fA-F]{3,8}$/` 校验后注入 `--embed-primary`，缺省平台主色）。
    - 初始化：`GET /ai/embed/meta`（Bearer token）→ ready 事件 + 头部目标名；401 → 过期覆盖层 + `token_expired` 事件；403 → 「应用无网页嵌入权限」错误层 + `error(no_permission)`。
    - sid：localStorage `ai-embed:{token前6}:{kind}:{target_id}`，缺则生成 uuid；转写 transcript `{role,parts}` ↔ `UIMessage[]` 恢复 `initialMessages`。
    - postMessage：`window.parent !== window` 时发信封 `{source:"ai-embed",version:1,event,payload}`；事件接线：`ready`（meta 成功后）、`user_message`（sendMessage 包装内）、`reply_start`（status→submitted）、`reply_delta`（onTextDelta）、`reply_done`（status 回 ready 且有末条助手消息，payload `{sid, text}`）、`error`（chat.error / 网络）、`token_expired`（onHttpError 401）。下行命令监听（parent→iframe，接受 `event.source===window.parent` 的 `ai-host` 信封）：`setToken`（更新 token 引用 → 重取 meta → kind/target 变了则清 sid 与 transcript）、`sendMessage`、`resize`（忽略或最小实现）、`destroy`（关闭页内状态）。
    - `data-embed` 帧：`session_reset=true` → 清 transcript 与本地消息。
    - `sources` 帧：按「已完成回复轮次序号」存 `sourcesByTurn`，在对应助手气泡下方渲染可展开引用（`el-collapse` 或点击展开），默认收起。
    - 视觉结构（spec §9.6）：头部（目标名 + 绿点状态 +「AIStation 驱动」小字）/ 消息区（用户右侧主色气泡、助手左侧浅底气泡 + 首字母圆标，`RichContent` 渲染 markdown，流式光标）/ 输入区（自适应 textarea、Enter 发送、Shift+Enter 换行、发送中禁用、流式时「停止生成」）/ 空态欢迎语（`meta.welcome` 兜底「有什么可以帮你？」）/ 覆盖层（`el-skeleton` 初始化、过期页、429 内联提示条含「频繁/配额」文案识别、网络错误重试条）。
    - 样式：scoped + `--el-*` 变量，禁自造配色、禁零散 font-size；**实现前先调用 `frontend-design` 技能**。

- [x] **Step 1: 实现 transport 与 composable**

按 Produces 签名；帧分类逻辑写成可测纯函数 `classifyFrame(parsed): "ui" | "aux" | "agno" | "drop"` 导出（便于后续补测）。

- [x] **Step 2: 实现 `EmbedChat.vue`**

先 `frontend-design` 技能，再按视觉结构实现；单根、白名单与路由改好。

- [x] **Step 3: 静态检查**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
Expected: 0 新增 error（既有仓库级告警不计入）

- [x] **Step 4: 本地可视自检（依赖 Task 12 的运行实例；若后端未起则先做 Step 3 绿即可，视觉统一在 Task 12 验收）**

打开 `/#/embed?token=…` 截图：空态、对话态（mock 或真实 agent）、缺 token 态三屏，用多模态读图与 `module_ai/provider` 风格对照。

- [x] **Step 5: 提交**

```bash
git add frontend/src
git commit -m "feat(ai): 新增嵌入对话页与 token 鉴权流式传输层"
```

---

### Task 11: 管理端「嵌入」弹窗 + 接入文档重写 + 品类名修正

**Files:**
- Create: `frontend/src/views/module_ai/develop/components/EmbedDialog.vue`
- Modify: `frontend/src/views/module_ai/develop/index.vue`（操作列加「嵌入」按钮 + 挂载组件；`CATEGORIES.embed` 改「网页嵌入」；接入文档三卡重写）
- Modify: `frontend/src/api/module_ai/develop.ts`（追加 `getEmbedTokens/mintEmbedToken/revokeEmbedToken`，URL `/develop/tokens*`）
- Modify: `backend/app/plugin/module_ai/develop/capabilities.py`（`"embed": "网页嵌入"`）
- Modify: `backend/tests/test_develop_capabilities.py`（追加标签断言）
- Test: `backend/tests/test_develop_capabilities.py`

**Interfaces:**
- Consumes: Task 8 管理端点；目标下拉数据源 = 各形态既有 list API（`src/api/module_ai/` 下按 `getXxxList` 惯例：agent/app/workflow 三个 list 函数——实现时 grep `api/module_ai/*.ts` 取实名）。
- Produces:
  - `EmbedDialog.vue`：`defineProps<{modelValue: boolean; app: any}>` + `emit("update:modelValue")`；结构——形态 `el-radio-group`（Agent/AI 应用/工作流）→ 目标 `el-select`（filterable，切换形态重载列表，仅启用项）→「生成嵌入代码」`el-tabs`（iframe / script SDK 两页签，`el-input textarea readonly` 代码块 + 复制按钮）；代码内 token 占位 `{access_token}`；页面地址用 `webBase = location.origin + import.meta.env.BASE_URL.replace(/\/$/, "")`、`apiBase = location.origin + "/api/v1/ai"`（dev 走 vite 代理同源可用）。
  - 「体验 Token」主按钮 → `mintEmbedToken` → 一次性展示（警示条 + 明文 + 复制 + 「填入代码」按钮替换当前页签占位符）。
  - Token 列表 `el-table`（形态/目标/签发方式/过期/使用/最后使用/状态）+ 行内「吊销」（`ElMessageBox.confirm`：「吊销后该令牌立即失效，使用它的嵌入页面将无法继续对话，且不可恢复。是否继续？」按钮「吊销/取消」）+ 刷新。
  - 事件契约：7 行小表（event/时机/payload 摘要）+ 尾注「完整说明见『接入文档』页签」。
  - 按钮权限：入口 `v-hasPerm="'module_ai:develop:query'"`；体验票 `v-hasPerm="'module_ai:develop:create'"`；吊销 `v-hasPerm="'module_ai:develop:update'"`。
  - 接入文档（index.vue）：凭证说明 alert 更新为「appid:appkey 仅用于服务端换票，切勿放入网页」；REST 卡 = `auth/verify` + `auth/token` 两个 curl（删除不存在的 `/chat/send`）；MCP 卡加 `el-tag type=warning「P3 即将开放」`；嵌入卡 = 新 SDK 示例（指向真实 `/api/v1/ai/embed/sdk.js`、含 `{access_token}` 占位与换票说明）+ iframe 直嵌示例 + postMessage 事件表。
  - 后端 `CATEGORIES["embed"]="网页嵌入"`；测试 `assert CATEGORIES["embed"] == "网页嵌入"`。

- [x] **Step 1: 写失败测试（后端标签）**

```python
def test_embed_category_label_is_web_embed():
    from app.plugin.module_ai.develop.capabilities import CATEGORIES
    assert CATEGORIES["embed"] == "网页嵌入"
```
Run: `PYTEST_NO_APP=1 uv run pytest tests/test_develop_capabilities.py -q` → 新用例 FAIL

- [x] **Step 2: 后端标签修正 + 通过**

Run: 同上 → PASS

- [x] **Step 3: 实现 EmbedDialog、按钮接线、文档重写、API 函数**

- [x] **Step 4: 静态检查 + 截图自检**

Run: `pnpm run type-check && pnpm run lint` → 0 新增 error；打开应用管理弹窗截图核对（视觉标准同 Task 10）。

- [x] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/develop backend/tests frontend/src
git commit -m "feat(ai): 应用嵌入管理弹窗与接入文档重写，embed 品类正名网页嵌入"
```

---

### Task 12: 演示宿主页 + 端到端与视觉验收 + 全量回归

**Files:**
- Create: `backend/static/embed-demo.html`（第三方视角演示宿主页）
- Modify: `docs/superpowers/specs/…` 无需；接入文档页签若与实测不一致回改

**Interfaces:**
- Consumes: Task 4-11 全部产物。
- Produces: 演示页结构——顶部醒目警示「生产环境必须由服务端换票，切勿把 appkey 写进网页」；表单（apiBase 默认 `location.origin + "/api/v1/ai"`、webBase 默认 `http://127.0.0.1:5182/web` 可改、appid、appkind、target_id、appkey）；「换票并嵌入」按钮 → fetch `auth/token` → `AiAssistant.init({container:"#chat", token, apiBase, webBase, theme:{primary:"#409eff"}})`；右侧事件日志面板（`on()` 挂全部 7 事件 + window message 原始信封，逐条带时间戳）；辅助按钮：`setToken`（粘贴新票续期）、`sendMessage("你好")`、`destroy`。

- [x] **Step 1: 探测端口并启动本 worktree 实例**

```powershell
Get-NetTCPConnection -LocalPort 5181,5182,8002,8012 -State Listen -ErrorAction SilentlyContinue | Select LocalPort,OwningProcess
```
先查在跑后端的 `/openapi.json` 是否已含 `/ai/embed/run`（判断现服务是否来自本 worktree）。**仅当需要跑新代码且端口被旧实例占用时**，用空闲端口显式启动本 worktree 实例（前端 `vite --port 5182 --strictPort`，后端 `uv run main.py run --env=dev --no-reload --port 8012` 之类），`E2E_BASE_URL` 与之严格一致；不杀不改用户已有服务，结束前收尾自有进程。

- [x] **Step 2: 端到端手测清单（浏览器工具操作 + 截图）**

1. 「AI 集成」新建应用（勾 `embed:use`）→ 行内「嵌入」→ 选真实 Agent → 体验票 → 填入代码 → 复制；
2. 打开 `/static/embed-demo.html` → 换票嵌入 → 发「你好」→ 流式回复可见；
3. 事件日志按序出现 `ready → user_message → reply_start → reply_delta… → reply_done`（7 类中至少 5 类必现，`error/token_expired` 见第 5 步）；
4. `setToken` 粘贴第二张票 → 继续对话不中断（sid 延续）；
5. 吊销该 token → 页内出现过期覆盖层 + 宿主日志 `token_expired`；
6. iframe 直嵌模式（不经 sdk.js，手动 `window.addEventListener("message")` 面板）复验信封；
7. 访问旧 `/#/share?token=x` → 404/跳转，`POST /api/v1/ai/workflows/share/run` → 404；
8. 调用日志页签出现 `method=EMBED` 流水且 token 已脱敏。

- [x] **Step 3: 视觉验收（硬标准）**

逐屏截图并用多模态读图核对：嵌入页（空态/对话态/过期态/429 提示）、嵌入弹窗、接入文档新卡、演示页。标准：与平台风格同源、结构清晰、状态齐全、无贴边裁切/错位；**任何一屏不达标 → 回 Task 10/11 返工重截**。

- [x] **Step 4: 全量回归**

Run（backend，`$env:CAPTCHA_ENABLE="false"`）: `uv run pytest -q -n 4` → 0 failed；
Run（frontend）: `pnpm run type-check && pnpm run lint` → 0 新增 error。
（**不要引用历史通过记录，全部当次取证**。）

- [x] **Step 5: 提交与收尾**

```bash
git add backend/static docs frontend/src backend/app
git commit -m "feat(ai): 嵌入演示宿主页与 P4' 端到端验收"
```
确认自有临时进程已关闭、端口已释放（用户既有 5181/8002 服务不动）。

---

## 计划自审记录（写计划时已核）

1. **Spec 覆盖**：§6 认证（T4/T5）、§9.1 表（T2/T3）、§9.2 端点全集 7 个（T4/T5/T6/T9/T8）、§9.3 run（T6）、§9.4 会话（T6）、§9.5 限流配额（T7）、§9.6 嵌入页（T10）、§9.7 SDK/事件（T9/T10）、§9.8 管理 UI/文档/品类名（T11）、§9.9 拆除（T1）、§10 测试（各任务+T12）、§11 验收（T12）——无缺口。
2. **步骤扫描**：每步单一可检动作；代码块仅测试骨架与签名。
3. **类型一致**：`EmbedContext`、`EmbedService.get_target/issue_token/prepare_session/run_stream/check_limits`、`get_embed_ctx`、`clamp_embed_ttl` 各任务引用一致。
4. **Review Focus 8 条**均有对应测试任务（见各条括注）。
5. **比例**：计划以任务/接口/断言为主，无整函数实现转录。

---

## 执行记录（2026-10-22 完成）

- 全部 12 个任务完成；后端新增测试 7 个文件，最终全量 `pytest -q -n 4`：**3076 passed / 7 failed / 37 skipped**。
  7 个失败均在本次**未触碰**的模块（`test_query_recall` 引用已重构掉的 `_embed_agno` 旧符号；
  `test_rule_leaves_e2e` 等依赖视频回调共享密钥环境），与本特性无因果（改动文件清单不含这些模块）。
- 计划外修正（执行中发现，均已提交）：
  1. 迁移 revision 与旧迁移 `e2f3a4b5c6d7` 撞号成环 → 改用 `a9b8c7d6e5f4`；
  2. 删 `share_token` 列前须先删其索引（SQLite 拒绝带索引列 DROP），迁移已加守护并由真实 SQLite 往返测试锁住；
  3. SSE 审计改 fire-and-forget（客户端中断时生成器 `finally` 里 `await` 写库会挂死请求、占满并发准入槽位）；
  4. 会话归属守卫放行「`source_app_id` 非空 + 匿名调用方」的嵌入会话（否则多轮上下文写不进库）；
  5. 纯非 LLM 工作流只发 `data-finish.reply`、不发 `text-delta`，前端传输层据此合成文本 parts（否则界面无回复）。
- 环境备注（worktree 专属，均不入库）：`backend/env/.env.dev`（SQLite + 验证码关闭 + 放大连接池/闸门）、
  `frontend/.env.development`（指向 8001）、`vite.e2e.config.mts`（Node 24 下 CJS require(esm) 环的绕过）、
  `frontend/node_modules` 以 junction 指向主仓依赖。演示页实际地址：`/api/v1/static/embed-demo.html`。
