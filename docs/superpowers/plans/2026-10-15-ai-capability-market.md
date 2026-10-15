# AI 能力市场实施计划

> **For agentic workers:** 使用 superpowers:executing-plans 按任务逐项执行。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 建成统一 AI 能力市场（工具/技能/MCP/插件），支持安装、个人维护、提交审核、点对点分享，并能集成进 Agent。

**Architecture:** 市场为橱窗层（`ai_market_items` 统一表 + payload 快照），安装=复制成真实资产（`ai_tools`/`ai_skills`/`ai_mcp_servers`/`ai_plugins`），Agent 绑定几乎零侵入；新增 Python 脚本工具（AST 白名单沙箱）与 MCP（agno 原生 MCPTools）两个能力。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic；Vue3 + Element Plus；agno 3.0.6（MCPTools）；`mcp`/`fastmcp` 新依赖（清华源）。

**Spec:** `docs/superpowers/specs/2026-10-15-ai-capability-market-design.md`

## Global Constraints

- 优势域全中文：注释、提交信息 `feat(ai-market): 中文描述`。
- 后端新模块放 `backend/app/plugin/module_ai/`（自动发现，前缀 `/ai/...`）；master 分支勿 `git add -A`（工作区有无关脏文件）。
- 所有列表接口权限 `Depends(AuthPermission([...]))`；写操作沿用 `OperationLogRoute`。
- 表模型继承：市场/分享/关系表 `ModelMixin`；个人资产 `ModelMixin, UserMixin`（按 `created_id` 过滤）。
- 测试效率：`PYTEST_NO_APP=1` 跑纯逻辑；单文件跑；全量 `uv run pytest -q -n 4`（勿 -n 8）。
- 新依赖：`mcp>=2.1.0,<3.0.0`、`fastmcp>=4.0.0,<5`，走 `https://pypi.tuna.tsinghua.edu.cn/simple`；提交信息注明国内源。
- 前端只允许 Element Plus + `--el-*` 变量；删除/覆盖类操作必须二次确认；弹窗尺寸常用档位。

## Review Focus

1. 脚本沙箱：源码含 `__import__`/`eval`/`open`/`os` 必须被拒（不是运行时报错，而是创建时校验失败）→ Task 6 测试。
2. 安装幂等：同一用户重复安装同一商品不得复制出两条真实记录（已装则返回已有）→ Task 2 测试。
3. 审核越权：非 `module_ai:market:review` 用户 POST review 必须 403（且列表为空）→ Task 3 测试。
4. 分享可见性：用户 C 不能读取 A→B 的分享（列表按 from/to 过滤）→ Task 4 测试。
5. MCP 运行时缺服务器配置时 Agent 正常降级（mcp_ids 为空/指向已禁用服务器不报错）→ Task 8 测试。

---

### Task 1: 数据模型与迁移

**Files:**
- Create: `backend/app/plugin/module_ai/market/model.py`
- Create: `backend/app/plugin/module_ai/mcp/model.py`
- Create: `backend/app/plugin/module_ai/plugins/model.py`
- Modify: `backend/app/plugin/module_ai/tools_catalog/model.py`（加 `code`/`timeout`）
- Modify: `backend/app/plugin/module_ai/agent/model.py`（加 `mcp_ids` JSONB）
- Test: `backend/tests/test_market_models.py`

**Interfaces:**
- Produces: `AiMarketItemModel`（表 `ai_market_items`：asset_type/name/description/icon/category/tags/version/owner_id/is_official/featured/status/payload/source_id/install_count/favorite_count/audit_remark/audit_user/audit_time）、`AiMarketRelationModel`（`ai_market_relations`：user_id/item_id/kind）、`AiMarketShareModel`（`ai_market_shares`：item_id/from_user_id/to_user_id/status/message）、`AiMcpServerModel`（`ai_mcp_servers`：name/transport/command/args/env/url/headers/auth_type/enabled/description）、`AiPluginModel`（`ai_plugins`：key/label/kind/config/config_schema/enabled）；`AiToolModel.kind` 运行时值 `script` 且含 `code`/`timeout`；`AiAgentModel.mcp_ids`。

- [ ] **Step 1: 写模型文件**（五个 model.py，按 Interfaces 字段；MarketItem/Relation/Share 继承 `ModelMixin`，Mcp/Plugin 继承 `ModelMixin, UserMixin`）
- [ ] **Step 2: 注册模型**——在 `market/mcp/plugins` 各建 `__init__.py` 并确保 `app/plugin/module_ai` 能被 discover（子目录自动发现自含 controller 时不需手工 import；若为纯模型需在 slice 的 controller/service 引用）
- [ ] **Step 3: 生成并检查 Alembic 迁移**

Run: `cd backend && uv run main.py revision --env=dev`（随后查看 versions 下新文件，确认含 5 张新表 + ai_tools 增列 + ai_agents 增列），再 `uv run main.py upgrade --env=dev`
Expected: upgrade 成功无报错；`\d ai_market_items` 可查到字段。

- [ ] **Step 4: 写模型测试**（表存在、字段类型、kind 默认值）
- [ ] **Step 5: 跑测试 + Commit**

```bash
cd backend && uv run pytest tests/test_market_models.py -q
cd D:\AIStation && git add backend/app/plugin/module_ai/market backend/app/plugin/module_ai/mcp backend/app/plugin/module_ai/plugins backend/app/plugin/module_ai/tools_catalog/model.py backend/app/plugin/module_ai/agent/model.py backend/alembic/versions backend/tests/test_market_models.py
git commit -m "feat(ai-market): 新增市场/MCP/插件数据模型与迁移"
```

### Task 2: 市场查询/安装/收藏 API

**Files:**
- Create: `backend/app/plugin/module_ai/market/schema.py`
- Create: `backend/app/plugin/module_ai/market/service.py`
- Create: `backend/app/plugin/module_ai/market/controller.py`
- Test: `backend/tests/test_market_install.py`

**Interfaces:**
- Consumes: Task 1 模型。
- Produces: `GET /ai/market/home`、`GET /ai/market/items?type=&category=&keyword=`、`GET /ai/market/items/{id}`、`POST /ai/market/items/{id}/install`、`POST/DELETE /ai/market/items/{id}/favorite`。
  - `install` 服务函数签名：`async def install_item(item_id, user, db) -> dict`，返回 `{installed: bool, real_id: int, exists: bool}`；按 asset_type 复制 payload 到真实表（tool→ai_tools name 加后缀或用户已有同名则复用、skill→ai_skills、mcp→ai_mcp_servers、plugin→ai_plugins），幂等（relations kind=installed 已存在则直接返回 exists=true）。

- [ ] **Step 1: 先写失败测试**（`test_market_install.py`：安装工具商品 → ai_tools 出现一条；重复安装 → 只有一条；未登录安装 401）
- [ ] **Step 2: 实现 schema/service/controller**（安装复制逻辑按 Interfaces；home 聚合 featured+approved 前 8 条 + categories 计数）
- [ ] **Step 3: 跑测试**
- [ ] **Step 4: 手测接口（curl 带 token）**：`GET /api/v1/ai/market/items` 返回 200
- [ ] **Step 5: Commit**（信息 `feat(ai-market): 市场查询/安装/收藏 API`）

### Task 3: 提交/审核/下架/精选 API

**Files:**
- Modify: `backend/app/plugin/module_ai/market/service.py`、`controller.py`
- Test: `backend/tests/test_market_review.py`

**Interfaces:**
- Produces: `POST /ai/market/submit`（body: asset_type/source_id/name/description/icon/category/version → 快照 payload，status=pending，owner_id=当前用户）、`GET /ai/market/mine`（我的真实资产 + 关联 market 状态）、`POST /ai/market/items/{id}/withdraw`、`GET /ai/market/review/list?status=pending`、`POST /ai/market/review`（body: id/action/remark，仅 `module_ai:market:review` 权限）、`POST /ai/market/items/{id}/feature`。
  - 提交时校验 source 归属（created_id==当前用户）与名称非空。

- [ ] **Step 1: 失败测试**（非 review 权限 403；审核通过后 status=approved 且 install 可用；驳回带 remark；withdraw 后不可安装）
- [ ] **Step 2: 实现**
- [ ] **Step 3: 跑测试**
- [ ] **Step 4: Commit**

### Task 4: 点对点分享 API

**Files:**
- Modify: `market/service.py`、`market/controller.py`
- Test: `backend/tests/test_market_share.py`

**Interfaces:**
- Produces: `POST /ai/market/shares/share`（item_id/to_user_id/message；to_user 是否存在校验；不允许分享给自己）、`GET /ai/market/shares?dir=in|out&status=`、`POST /ai/market/shares/{id}/accept`（复制资产给接收方+status=accepted）、`POST /ai/market/shares/{id}/reject`。
  - 可见性：dir=in 仅 to_user_id==user；dir=out 仅 from_user_id==user。

- [ ] **Step 1: 失败测试**（C 看不到 A→B 分享；接受后 B 获得资产；拒绝后状态 rejected；分享给自己 400）
- [ ] **Step 2: 实现**
- [ ] **Step 3: 跑测试 + Commit**（`feat(ai-market): 点对点分享 API`）

### Task 5: 自定义 Python 脚本工具

**Files:**
- Create: `backend/app/plugin/module_ai/tools_catalog/script_executor.py`
- Modify: `tools_catalog/service.py`（create/update 支持 kind=script；dispatch 增加 script 分支）、`tools_catalog/controller.py`（`POST /ai/tools/{id}/test-script`）
- Test: `backend/tests/test_script_tool.py`

**Interfaces:**
- Produces: `ScriptExecutor.validate(code) -> None|error`（AST 白名单：仅允许 import 白名单 {json,math,re,datetime,random,statistics,collections,itertools,functools,typing}；禁止 dunder 访问、eval/exec/compile/open/__import__、with/async/await）；`ScriptExecutor.run(code, args, timeout=10) -> dict`（受限 globals + sys.settrace 指令计数超时）；`def run(args: dict) -> dict` 为入口约定。
- `POST /ai/tools/{id}/test-script` body `{args}` → 返回 `{ok, result|error}`。

- [ ] **Step 1: 失败测试**（合法脚本 `def run(args): return {"sum": args["a"]+args["b"]}` 通过并返回；含 `import os` / `__import__` / `open(` / `eval(` 创建校验拒绝；死循环超时抛错）
- [ ] **Step 2: 实现 script_executor.py + service 接线**
- [ ] **Step 3: 跑测试**
- [ ] **Step 4: Commit**（`feat(ai-market): 自定义 Python 脚本工具与沙箱`）

### Task 6: MCP 配置 CRUD + 连接测试

**Files:**
- Create: `backend/app/plugin/module_ai/mcp/schema.py`、`service.py`、`controller.py`
- Test: `backend/tests/test_mcp.py`

**Interfaces:**
- Produces: `GET /ai/mcp`（按 created_id 过滤）、`POST /ai/mcp`（name 唯一校验）、`PUT /ai/mcp/{id}`、`DELETE /ai/mcp/{id}`、`POST /ai/mcp/{id}/toggle`、`POST /ai/mcp/{id}/test`（stdio 校验 command 存在；sse/http 用 httpx GET url 探测 200/4xx 视为可达）。
  - 服务函数：`async def test_mcp(server, db) -> dict {reachable, detail}`。

- [ ] **Step 1: 失败测试**（CRUD 正常；name 重复 400；test 对不可达 url 返回 reachable=false 不抛异常）
- [ ] **Step 2: 实现**
- [ ] **Step 3: 跑测试 + Commit**

### Task 7: MCP 运行时装配 + 依赖安装

**Files:**
- Modify: `backend/app/plugin/module_ai/agent/service.py`（run_ui_stream 中按 mcp_ids 装配）、`backend/app/plugin/module_ai/agno_tools/agent_factory.py`（`build_agent(..., mcp_tools=None)`）、`backend/app/plugin/module_ai/assistant/agno_service.py`（生命周期 connect/disconnect）
- Modify: `backend/pyproject.toml`（+mcp、+fastmcp）
- Test: `backend/tests/test_mcp_runtime.py`

**Interfaces:**
- Produces: `build_mcp_tools(servers: list[dict]) -> list[MCPTools]`（按 transport 配置 MCPTools），`close_mcp_tools(tools)`。
  - 降级：mcp_ids 为空或服务器 disabled/配置缺失 → 返回空列表，不影响原有运行。

- [ ] **Step 1: 安装依赖**（`cd backend && uv add mcp fastmcp --index-url https://pypi.tuna.tsinghua.edu.cn/simple`；若 resolver 冲突改 `pip install mcp fastmcp --no-deps` 手工补缺；验证 `python -c "import mcp, fastmcp"`）
- [ ] **Step 2: 失败测试**（mock MCPTools：`build_mcp_tools([])` 返回 []；含 disabled 服务器仅返回可用者）
- [ ] **Step 3: 实现 agent_factory/agno_service 接线（agent service 传入 servers）**
- [ ] **Step 4: 跑测试 + Commit**（`feat(ai-market): Agent 接入 MCP 能力（agno MCPTools）`）

### Task 8: AI 能力插件（表 + 内置执行器）

**Files:**
- Create: `backend/app/plugin/module_ai/plugins/schema.py`、`service.py`、`controller.py`、`plugin_executor.py`
- Modify: `agent/service.py`（按 ai_plugins 启用 key 注入提示/工具——MVP：拼入 system prompt 说明 + 提供 `web_fetch`/`table_export` 两个轻执行器）
- Test: `backend/tests/test_plugins.py`

**Interfaces:**
- Produces: `GET/POST/PUT/DELETE /ai/plugins`、`POST /ai/plugins/{id}/toggle`；`PLUGIN_EXECUTORS = {"web_fetch": fn, "table_export": fn}`；内置 key 预置（seed 或首次启动 INSERT：web_fetch/table_export/email_send/report_generate/data_pipeline，后三者 status 标注 `executor_ready=false`）。

- [ ] **Step 1: 失败测试**（内置 key 预置存在；web_fetch 执行器返回内容；未实现 key 标记 executor_ready=false）
- [ ] **Step 2: 实现**
- [ ] **Step 3: 跑测试 + Commit**

### Task 9: 菜单/权限种子

**Files:**
- Modify: `backend/app/scripts/data/sys_menu.json`（或 AI 菜单种子所在文件，按现状定位：`init_app.py`/`sys_menu.json`）
- Modify: `backend/app/scripts/data/` 对应角色-菜单关联种子

- [ ] **Step 1: 定位 AI 菜单种子文件**（`grep "智能体" backend/app/scripts`）
- [ ] **Step 2: 添加「能力市场」「MCP 管理」菜单 + `module_ai:market:*` 权限码 + 绑定 admin 角色**
- [ ] **Step 3: 空库种子验证**（可选：docker 起新库太重——改为断言种子 JSON 解析通过 + 文档说明存量库用菜单管理 UI）
- [ ] **Step 4: Commit**（`feat(ai-market): 菜单与权限种子`）

### Task 10: 前端 API 封装

**Files:**
- Create: `frontend/src/api/module_ai/market.ts`、`frontend/src/api/module_ai/mcp.ts`、`frontend/src/api/module_ai/plugins.ts`
- Modify: `frontend/src/api/module_ai/tool.ts`（+testScript）、`frontend/src/api/module_ai/agent.ts`（mcp_ids 透传）

- [ ] **Step 1: 按后端接口名封装（getMarketHome/getMarketList/getMarketDetail/installMarketItem/favoriteMarket/submitMarketItem/withdrawMarketItem/getMyAssets/getMarketShares/shareMarketItem/acceptShare/rejectShare/getReviewList/reviewMarketItem/setFeatured；getMcpList/createMcp/updateMcp/deleteMcp/testMcp/toggleMcp；getPluginList/...；testScript）**
- [ ] **Step 2: type-check**（`pnpm run type-check` 过滤本文件）
- [ ] **Step 3: Commit**（`feat(ai-market): 前端市场 API 封装`）

### Task 11: 市场首页（形态参考截图）

**Files:**
- Create: `frontend/src/views/module_ai/market/index.vue`
- Create: `frontend/src/views/module_ai/market/components/MarketCard.vue`、`MarketDetailDrawer.vue`

- [ ] **Step 1: 页面结构**：精选大卡横排（图标/名称/描述/安装数/收藏/「+」）+ 类型 tabs（全部/工具/技能/MCP/插件）+ 分类 tabs + 4 列网格 + 搜索框
- [ ] **Step 2: 交互**：安装（二次确认）、收藏、详情抽屉（描述/作者/版本/标签/安装收藏按钮）
- [ ] **Step 3: 浏览器走查 + 截图对比风格**（与既有 module_ai 页面一致性；`--el-*` 变量）
- [ ] **Step 4: type-check + Commit**（`feat(ai-market): 能力市场首页`）

### Task 12: 我的资产 + 提交市场 + 分享入口

**Files:**
- Create: `frontend/src/views/module_ai/market/mine.vue`
- Modify: `views/module_ai/market/index.vue`（导航）

- [ ] **Step 1: 类型 tabs + 列表（名称/类型/分类/版本/启用/市场状态 tag/操作：编辑·提交市场·分享·删除）**
- [ ] **Step 2: 提交弹窗**（名称/分类/图标/描述/版本 → 校验后提交，状态 pending；二次确认提交）
- [ ] **Step 3: 分享弹窗**（选择用户 + 留言；用户选择用后端用户搜索接口——若无可先用用户名精确输入）
- [ ] **Step 4: type-check + Commit**（`feat(ai-market): 我的资产与提交/分享`）

### Task 13: 分享给我 + 审核中心

**Files:**
- Create: `frontend/src/views/module_ai/market/shared.vue`
- Create: `frontend/src/views/module_ai/market/review.vue`

- [ ] **Step 1: shared.vue**（待处理/已处理 tabs；接收=二次确认，拒绝=确认；接收后出现在我的资产）
- [ ] **Step 2: review.vue**（待审核/已审核 tabs；通过/驳回带意见；精选开关；仅 review 权限显示——`v-hasPerm`）
- [ ] **Step 3: type-check + Commit**（`feat(ai-market): 分享接收与审核中心`）

### Task 14: MCP 管理页 + 工具页脚本表单 + Agent MCP 多选

**Files:**
- Create: `frontend/src/views/module_ai/mcp/index.vue`
- Modify: `frontend/src/views/module_ai/tool/index.vue`（脚本工具 form：类型切换 HTTP/脚本、代码 textarea + 试运行按钮）
- Modify: `frontend/src/views/module_ai/agent/index.vue`（agents 表单加 MCP 多选 `mcp_ids`；列表加 MCP tag）

- [ ] **Step 1: mcp/index.vue**（CRUD 弹窗：transport 单选（stdio 显示命令/参数/env；sse/http 显示 url+headers+auth）+ 测试连接按钮 + 启用开关）
- [ ] **Step 2: tool/index.vue 脚本表单 + 试运行**
- [ ] **Step 3: agent/index.vue MCP 多选**
- [ ] **Step 4: type-check + 浏览器走查 + Commit**（`feat(ai-market): MCP 管理、脚本工具表单与 Agent 绑定`）

### Task 15: 全量验证与收尾

- [ ] **Step 1: 后端全量测试**：`cd backend && uv run pytest -q -n 4`（关注新增用例全绿；既有失败若与本次相关必须修）
- [ ] **Step 2: 前端 lint/type-check**：`pnpm run type-check && pnpm run lint`（只保证本次新文件无错误；既有报错不动）
- [ ] **Step 3: E2E 走查**：管理员审核一条技能 → 用户市场安装 → Agent 绑定 → 对话调用（浏览器）
- [ ] **Step 4: 文档**：更新 `docs/`（部署说明：存量库菜单添加步骤、脚本工具风险说明）
- [ ] **Step 5: 最终 Commit**（`feat(ai-market): 完成能力市场全链路`）
