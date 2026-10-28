# 嵌入域归位（资产绑定 + 开放平台收敛）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:executing-plans 逐任务实现本计划。步骤用 `- [ ]` 复选框跟踪。
> 本计划由主会话 native 执行（用户已授权「开工」）。

**Goal:** 把「嵌入」域从 AI 集成开放平台剥离，改为绑定具体 agent/工作流的资产级嵌入（聊天气泡/iframe/运行 API），开放平台收敛为纯 REST+MCP。

**Architecture:** 新增 `module_ai/asset_embed/` 子包承载整个嵌入域（公开 `/ai/embed/*` + 管理 `/ai/asset-embed/*`），新建「资产令牌」表（独立绑定 `kind+target_id`，不依赖应用），`/ai/embed/run` 改凭资产令牌鉴权；develop 移除所有嵌入相关（`EmbedRouter`、`/auth/token`、`/tokens`、`integration:embed:*`、嵌入文档/卡片/弹窗）。

**Tech Stack:** FastAPI + SQLAlchemy 2.0（后端），Vue 3 + Element Plus + Vue I18n（前端）。插件自动发现把 `module_ai/**/controller.py` 的顶层 APIRouter 并入容器前缀 `/ai`。

**Spec:** `docs/superpowers/specs/2026-10-28-embed-asset-design.md`

## Global Constraints

- 回复/注释/提交信息一律中文；提交信息 `feat/fix/refactor(asset_embed|develop|workspace): 中文描述`。
- PIP/apt 走清华源；`uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple`。
- 表一律由插件启动幂等建（`ensure_*_schema()`），**不走 alembic autogenerate**。
- 令牌库内只存 sha256 散列，明文仅签发响应返回一次。
- 鉴权失败统一 401（防令牌枚举）；`sdk.js` 无鉴权。
- 前端删除类操作（吊销令牌）必须二次确认；按钮统一 primary；操作列/更多用 remix 图标。
- 开发/测试不要开 reload；后端测试用 `PYTEST_NO_APP=1`（纯逻辑）或单文件；跑服务用 8011（`--no-reload`），前端 5183（`VITE_API_BASE_URL=http://127.0.0.1:8011`）。

## Review Focus

1. 令牌被吊销/过期后，`/ai/embed/run` 必须立即 401，不能再消费（任务 1/2 的鉴权测试覆盖）。
2. 目标资产被停用（`enabled=false`）后嵌入必须拒绝（任务 2 `get_embed_ctx` 校验 `target.enabled`）。
3. 无 `integration:embed:use` 且未签发过令牌的应用，无法再嵌入（develop 移除后无此permission，任务 3 断言 `capabilities` 不再含 `integration:embed:use`）。
4. develop 调用日志/用量不再出现 `EMBED`（任务 3 的日志过滤）。
5. 工作台卡片三种嵌入形式代码中不出现 `appkey`（任务 5 断言模板不含 appkey）。
6. 无任何鉴权的 `/ai/embed/run` 请求（缺 token）必须 401（任务 2）。

---
### Task 1: 后端资产令牌模型 + 幂等建表 + 签发/列表/吊销服务

**Files:**
- Create: `backend/app/plugin/module_ai/asset_embed/__init__.py`
- Create: `backend/app/plugin/module_ai/asset_embed/model.py`
- Create: `backend/app/plugin/module_ai/asset_embed/schema.py`
- Create: `backend/app/plugin/module_ai/asset_embed/schema_check.py`
- Create: `backend/app/plugin/module_ai/asset_embed/service.py`
- Test: `backend/tests/test_asset_embed.py`

**Interfaces:**
- Consumes: `_hash_embed_token`（develop.service，或复制到 asset_embed）
- Produces:
  - `AiAssetAccessTokenModel`（表 `ai_asset_access_tokens`，字段见 spec 5.1）
  - `AssetTokenIssueSchema{kind:str, target_id:int, ttl:int|None}`
  - `AssetEmbedService.issue_token(kind,target_id,ttl,issued_by,created_id)->dict{token,expires_in,expires_at}`
  - `AssetEmbedService.list_tokens(kind,target_id)->list[dict]`
  - `AssetEmbedService.revoke_token(token_id)->bool`
  - `ensure_asset_embed_schema()`（启动幂等建表）

- [ ] **Step 1: 写失败测试** `tests/test_asset_embed.py`：签发返回 `token`/`expires_at`；列表按 kind+target 过滤；吊销后 `revoked=True`；token 在库中只存散列（不存明文）。
- [ ] **Step 2: 运行确认失败**：`cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_asset_embed.py -q` 预期 FAIL（模块不存在）。
- [ ] **Step 3: 实现 model.py** `AiAssetAccessTokenModel(ModelMixin)`，字段：`kind(16)`、`target_id(int,index)`、`token_hash(128,unique,index)`、`issued_by(16,default admin)`、`expires_at`、`revoked(bool,default False)`、`use_count(int,default 0)`、`last_used_at(nullable)`。
- [ ] **Step 4: 实现 schema_check.py** `ensure_asset_embed_schema()`：用 `sa.inspect` 判断表存在则跳过，否则 `Base.metadata`（导入 model）`create_all` 该表；在 `module_ai/__init__.py` 启动钩子调用。
- [ ] **Step 5: 实现 service.py**：`issue_token`（`_generate_embed_token`+`_hash_embed_token`+`clamp_asset_ttl`，TTL 默认 24h/下限 60s/上限 30 天），`list_tokens`（按 kind+target 过滤，非删除），`revoke_token`（置 revoked=true）。
- [ ] **Step 6: 运行测试通过**。

### Task 2: asset_embed 公开面（/ai/embed/*）+ 资产令牌鉴权

**Files:**
- Modify: `backend/app/plugin/module_ai/asset_embed/auth.py`（新建）`controller.py`（新建）`embed.py`（新建）
- Modify: `backend/app/plugin/module_ai/develop/auth.py`（删 `EmbedContext`/`get_embed_ctx`）
- Test: `backend/tests/test_asset_embed.py`（追加鉴权用例）

**Interfaces:**
- Produces:
  - `EmbedContext{token_id:int, kind:str, target_id:int, expires_at:datetime, token_hash12:str}`
  - `get_embed_ctx(authorization: Header)->EmbedContext`（散列查资产令牌→未吊销未过期→`get_target` 存在且 enabled→累加 use_count）
  - `AssetEmbedRouter = APIRouter(prefix="/embed", tags=["AI-嵌入"])`：`GET /meta`、`POST /run`、`GET /sdk.js`
  - `EmbedService.prepare_session(ctx, sid)`（改按 `(kind,target_id,sid)` 唯一）、`run_stream`、`check_limits(redis, ctx, ip)`
- [ ] **Step 1: 写失败测试**：无 token→401；已吊销 token→401；过期 token→401；目标 `enabled=false`→401；有效 token 可过 `get_embed_ctx`。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 实现 auth.py** `EmbedContext` + `get_embed_ctx`（从 develop/auth.py 迁移并去掉 app 依赖，改为校验目标 enabled）。
- [ ] **Step 4: 实现 embed.py**：迁移 `EmbedService.get_target` / `prepare_session`（唯一约束改 `(kind,target_id,sid)`，`app_id` 置空）/ `run_stream`（审计 `method=EMBED`，`request_body` 不带 appid）/ `check_limits`。
- [ ] **Step 5: 实现 controller.py** `AssetEmbedRouter`：`/meta`（返回 name/welcome/expire_at）、`/run`（校验后 `prepare_session`+`run_stream`，workflow 走 `ui_stream_response`，else `agno_stream_response`）、`/sdk.js`（读 `asset_embed/static/ai-assistant.js`，无鉴权）。
- [ ] **Step 6: 运行测试通过**。

### Task 3: asset_embed 管理面（/ai/asset-embed/tokens）+ 移走 develop 嵌入

**Files:**
- Create: `backend/app/plugin/module_ai/asset_embed/controller.py`（追加 `AssetTokenRouter`）
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（删 `EmbedRouter`/`/auth/token`/`/tokens` 三块）
- Modify: `backend/app/plugin/module_ai/develop/auth.py`（清理嵌入 import）、`develop/service.py`（删 `list_tokens`/`revoke_token`）、`develop/capabilities.py`（删 `integration:embed:use`）、`develop/embed.py` 移除或保留转发
- Test: `backend/tests/test_develop_*.py`（更新），`backend/tests/test_asset_embed.py`

**Interfaces:**
- `AssetTokenRouter = APIRouter(prefix="/asset-embed", tags=["AI-资产嵌入"])`：`POST /tokens`（`AuthPermission(["module_ai:asset_embed:manage"])`）、`GET /tokens?kind=&target_id=`、`PUT /tokens/{id}/revoke`
- [ ] **Step 1: 写失败测试**：无 `module_ai:asset_embed:manage` 权限→403；签发/列表/吊销。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 实现 `AssetTokenRouter`** 三个端点（`AuthPermission` 鉴权；签发用 `AssetEmbedService.issue_token`）。
- [ ] **Step 4: 从 develop/controller.py 删除** `EmbedRouter` 三端点、`auth_token`、`develop_list_tokens`/`develop_mint_token`/`develop_revoke_token` 及其 import。
- [ ] **Step 5: 清理 develop/auth.py、service.py、capabilities.py** 中嵌入相关（确保 `capabilities` 不再含 `integration:embed:use`）。
- [ ] **Step 6: 注册 `module_ai:asset_embed:manage` 菜单/权限**（`develop/__init__.py` 或 `_ensure_ai_menus` 幂等）。
- [ ] **Step 7: 运行 develop + asset_embed 测试通过**。

### Task 4: 后端日志审计去 EMBED（develop 页不再显示嵌入审计）

**Files:**
- Modify: `backend/app/plugin/module_ai/develop/controller.py`（`_query_call_logs`、`_query_usage` 过滤 `method != "EMBED"`）
- Modify: `backend/app/plugin/module_ai/develop/insights.py`（若有 EMBED 统计则剔除）
- Test: `backend/tests/test_develop_insights.py`

- [ ] **Step 1: 写失败测试**：插入一条 `method=EMBED` 调用日志后，`/call-logs` 与 `/usage-report` 不含它。
- [ ] **Step 2: 运行确认失败**。
- [ ] **Step 3: 主要查询加 `method != 'EMBED'` 过滤**。
- [ ] **Step 4: 运行测试通过**。

### Task 5: 工作台卡片「嵌入」入口 + 资产嵌入弹窗（三形式）

**Files:**
- Modify: `frontend/src/views/module_ai/workspace/index.vue`（卡片「更多」加「嵌入」）
- Create: `frontend/src/views/module_ai/workspace/components/AssetEmbedDialog.vue`
- Create: `frontend/src/api/module_ai/assetEmbed.ts`（issue/list/revoke asset token）
- Test: `pnpm run type-check`

**Interfaces:**
- `AssetEmbedDialog` props `{modelValue, kind, targetId, name}`；emit `update:modelValue`
- `issueAssetToken({kind,target_id,ttl})`、`listAssetTokens({kind,target_id})`、`revokeAssetToken(id)`
- [ ] **Step 1: 写 api 层** `assetEmbed.ts` 三个函数。
- [ ] **Step 2: 创建 `AssetEmbedDialog.vue`**：头部「三种嵌入形式」`el-tabs`（聊天气泡 Script SDK / iframe / 运行 API SSE），各自代码块（用 `MarkdownRenderer` 或 `pre`+高亮），「生成令牌」+ 令牌治理表（列表/过期/吊销，吊销二次确认），**代码不含 appkey**。
- [ ] **Step 3: workspace/index.vue** 卡片「更多」下拉加「嵌入」项（`onCardMore` 加 `cmd==="embed"`，`v-hasPerm="'module_ai:asset_embed:manage'"`），打开 `AssetEmbedDialog`（`kind=it.type`, `targetId=it.id`）。
- [ ] **Step 4: `pnpm run type-check` 通过**。

### Task 6: develop 页收敛（去嵌入入口/文档/弹窗）

**Files:**
- Modify: `frontend/src/views/module_ai/develop/index.vue`
- Modify: `frontend/src/views/module_ai/develop/examples.ts`（删 `EMBED_MD`）
- Delete: `frontend/src/views/module_ai/develop/components/EmbedDialog.vue`
- Modify: `frontend/src/api/module_ai/develop.ts`（删 embed token 接口）
- Test: `pnpm run type-check`

- [ ] **Step 1: 删 develop/index.vue** 应用卡片「嵌入」按钮（109-114 tooltip + `openEmbed`/`embedVisible`/`EmbedDialog` import）、接入文档「网页嵌入」卡片（943 起）、MCP 会话页签内若有的嵌入提示。
- [ ] **Step 2: 删 `EMBED_MD`** 及文档引用；删除 `EmbedDialog.vue`。
- [ ] **Step 3: 删 api** `embed` 相关函数。
- [ ] **Step 4: `pnpm run type-check` 通过**。

### Task 7: 工作流编辑器「嵌入对话」按钮改指向

**Files:**
- Modify: `frontend/src/views/module_ai/workflow/components/WorkflowEditor.vue`（`showEmbedHint`）
- Test: `pnpm run lint`

- [ ] **Step 1: `showEmbedHint` 改为** 跳转工作台并打开该工作流的资产嵌入弹窗，删除「请前往应用管理」提示（或改用 AssetEmbedDialog）。
- [ ] **Step 2: lint/type-check 通过**。

### Task 8: i18n 键补齐

**Files:**
- Modify: `frontend/src/lang/package/zh-cn/` `en/` `zh-hant/`（`ai_*` 嵌入相关）
- [ ] **Step 1: 补 zh/en/hant** 三语言键（工作台嵌入弹窗标题/三形式/令牌/吊销/权限不足等）。
- [ ] **Step 2: type-check 通过**。

### Task 9: 联调验证 + 收尾

**Files:**
- 无（验证任务）

- [ ] **Step 1: 重启后端 8011（`--no-reload`）+ 前端 5183（`VITE_API_BASE_URL=8011`）**，等 60-90s 就绪。
- [ ] **Step 2: 浏览器验证**：工作台卡片「更多→嵌入」开弹窗、三形式代码、生成/吊销令牌；`/web/#/embed?token=` 能加载；develop 页无嵌入残留；调用日志/用量无 EMBED。
- [ ] **Step 3: 全量梳理**：`pnpm run lint`、相关 pytest 一遍。
- [ ] **Step 4: 收尾**：清理本会话起的前端/后端进程（5183/8011）。

---
## Self-Review 记录

- **Spec coverage**：spec 五~十一节均有对应任务（5.1→T1、5.2→T2、5.3→T2、5.4→T3/T5、5.5→T3、六→T5/T6/T7、七→T4、八→T1/T2/T5、九→T1~T4、十→T1/T3、十一→T9）。
- **Review Focus**：5 条已按任务落测试（吊销/过期→T2、目标停用→T2、无 embed 权限→T3、日志无 EMBED→T4、无 appkey→T5、缺 token 401→T2）。
- **Type consistency**：`AssetEmbedService.issue_token/list_tokens/revoke_token`、`get_embed_ctx`、`EmbedContext` 在 T1~T5 间一致；`AssetEmbedDialog` props 与 workspace 传参一致。
- **Proportion**：计划约与 spec 相当，代码块仅保留关键签名/值，未转写实现。
