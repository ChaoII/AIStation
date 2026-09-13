# AI 管理 UI/IA 整治 + Agno 精选工具 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AI 管理收敛为 6 个统一风格的页面（智能助手为唯一交互入口），工具中心改为 el-card 卡片并接入 Agno 精选内置工具（参数自动识别 + 可加参数）。

**Architecture:** 前端删除多余页面并统一为 `PageSearch`（上）+ `PageContent`/`el-card`（下）+ `EnhancedDialog`；后端保留全部路由/表，仅改菜单注册与前端下线；`ai_tools` 增加 `source`/`config`，新增 `agno_tools` 子模块惰性实例化 Agno toolkit、用签名生成 OpenAI schema 并按 source 分派执行。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2；Agno 2.5.8（已装）；Vue 3 + Element Plus；`ai@7`/`@ai-sdk/vue@4`（已装，勿新增依赖）。

**Spec:** `docs/superpowers/specs/2026-09-13-ai-platform-ui-overhaul-design.md`

## Global Constraints

- 后端不新增依赖；`cd backend && uv run pytest -q` 全绿；改动文件 `uv run ruff check` clean；中文注释。
- 前端**不新增依赖**；`pnpm type-check` 新增/改动文件 0 错误（项目 16 个 pre-existing 错误不要动）；目标文件 eslint/prettier clean。
- AI 页面只用 Element Plus 组件与 `--el-*`；布局用 `el-row/el-col`（勿用自定义 CSS Grid）；页面**单一根元素**。
- 列表页统一：顶部整行 `PageSearch` + 下方 `PageContent`（表格）或 `el-card` 卡片；搜索永远在列表上方。
- 工具卡片使用 `el-card`，含 `#header`（`el-avatar` + 名称 + 标签）、body（简介）、`#footer`（开关 + 配置）。
- 菜单/权限由 `init_app.py::_ensure_ai_menus` 运行时补齐；新列经 `_ensure_missing_columns`（含 SQLite 分支）。
- 不改 AI SDK UI Message Stream 协议、模型/提示词/应用/会话既有数据结构。
- 提交 `feat(ai)/fix(ai)/refactor(ai)/docs(ai): 中文描述`；禁止 `git add -A`。
- 删除前端页面前先 `rg` 确认无残留引用（含 `router`、`api`）。

---

### Task 1: 信息架构收敛（菜单 6 项 + 下线 5 个页面）

**Files:**
- Modify: `backend/app/scripts/init_app.py`（`_ensure_ai_menus`、`AI_BUTTON_PERMS`）
- Delete: `frontend/src/views/module_ai/overview/`、`playground/`、`provider/`、`report/`、`memory/`
- Delete: `frontend/src/api/module_ai/overview.ts`、`provider.ts`、`report.ts`（先 `rg` 确认无引用）
- Test: `backend/tests/test_ai_menus.py`；`frontend/e2e/ai-menu.spec.ts`（替换 `ai-console.spec.ts`）

**Interfaces:**
- Produces: AI 菜单最终集合 = `智能助手/模型配置/提示词/工具中心/AI应用/调用日志`；父菜单 `redirect=/ai/chat`；removed 页面 `hidden=True`。

- [ ] **Step 1: 改 `_ensure_ai_menus`**

把 `pages` 列表改为只创建保留页（去掉 overview/provider/report/playground）：

```python
pages = [
    ("模型配置", "AiModel", "/ai/model", "module_ai/model/index", "module_ai:model:query", 10),
    ("提示词", "AiPrompt", "/ai/prompt", "module_ai/prompt/index", "module_ai:prompt:query", 13),
    ("工具中心", "AiTool", "/ai/tool", "module_ai/tool/index", "module_ai:tool:query", 14),
    ("AI应用", "AiApp", "/ai/app", "module_ai/app/index", "module_ai:app:query", 15),
    ("调用日志", "AiLogs", "/ai/logs", "module_ai/logs/index", "module_ai:assistant:query", 16),
]
```
父菜单 `redirect` 固定 `/ai/chat`；对以下 route_name 执行 `hidden=True`（存量库已有行的隐藏；新库本就不创建）：

```python
REMOVED_ROUTE_NAMES = ["AiOverview", "AiPlayground", "AiProvider", "AiReport", "Memory"]
await db.execute(update(MenuModel).where(MenuModel.route_name.in_(REMOVED_ROUTE_NAMES)).values(hidden=True))
```
`chat` 保持 `hidden=False`（`update(... component_path=="module_ai/chat/index").values(hidden=False)`）。`AI_BUTTON_PERMS` 去掉 `module_ai:provider:*` 与 `module_ai:report:*`。

- [ ] **Step 2: 后端测试 `test_ai_menus.py`**

用 `test_client`/直接调用 `_ensure_ai_menus()` 后查 `sys_menu`：`AiOverview/AiPlayground/AiProvider/AiReport/Memory` 均 `hidden=True`；`AiModel/AiPrompt/AiTool/AiApp/AiLogs` 存在且 `hidden=False`；父菜单 `redirect=="/ai/chat"`。

- [ ] **Step 3: 删除前端页面与 API**

先 `rg "module_ai/overview|module_ai/playground|module_ai/provider|module_ai/report|module_ai/memory|api/module_ai/(overview|provider|report)" frontend/src` 确认引用；删除目录/文件。`AiAssistant` 悬浮球若引用 `report`/`overview` API 需同步改。

- [ ] **Step 4: E2E**

删除 `frontend/e2e/ai-console.spec.ts`（其断言 overview/playground 已下线）；新增 `frontend/e2e/ai-menu.spec.ts`：登录后断言 AI 子菜单只含 6 项且「控制台/运行台/提供商/AI报告/会话记忆」不出现。

- [ ] **Step 5: 验证 + 提交**

Run: `cd backend && uv run pytest tests/test_ai_menus.py -q && uv run ruff check app/scripts/init_app.py`；`cd frontend && pnpm type-check && pnpm e2e e2e/ai-menu.spec.ts`
```bash
git add backend/app/scripts/init_app.py backend/tests/test_ai_menus.py frontend/src/views/module_ai frontend/src/api/module_ai frontend/e2e
git commit -m "feat(ai): AI 菜单收敛为 6 项并下线控制台/运行台/提供商/报告/会话记忆"
```

---

### Task 2: 智能助手（输入框铺满 + 去 Agno WS + 应用标签）

**Files:**
- Modify: `frontend/src/views/module_ai/chat/components/ChatInput.vue`
- Modify: `frontend/src/views/module_ai/chat/index.vue`
- Modify: `frontend/src/views/module_ai/chat/components/ChatNavbar.vue`
- Modify: `frontend/src/composables/ai/useAiChat.ts`（若需 getter 支持 app 切换；Task 6 已支持 computed getter，确认即可）
- Test: `frontend/e2e/ai-chat.spec.ts`

**Interfaces:**
- Consumes: 运行流 `/ai/assistant/stream`（无 app）与 `/ai/apps/{id}/run/stream`（有 app）；`getAiAppDetail`。
- Produces: 助手页顶部可关闭「应用：X」标签。

- [ ] **Step 1: `ChatInput.vue` 样式修复**

删除 `max-width: 800px; margin: 0 auto`；`input-container` 改为紧凑一行布局：

```scss
.input-wrapper { padding: 12px 16px; }            // 铺满，不再居中限宽
.input-container {
  display: flex; align-items: flex-end; gap: 8px;
  padding: 8px 12px; border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-overlay);
}
.message-input :deep(.el-textarea__inner) { padding: 0; border: none; box-shadow: none; background: transparent; resize: none; }
.input-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
```
删除 `.input-footer` 的独立占位（按钮移入 `.input-container` 右侧）；删除 `.input-hint` 行；`placeholder` 改为 `输入消息…（Enter 发送 / Shift+Enter 换行）`（去掉「FA助手」）；`autosize { minRows: 1, maxRows: 6 }` 保留。

- [ ] **Step 2: 去掉 Agno WS，改为运行时流**

`chat/index.vue`：删除 `ws`/`connectWebSocket`/`disconnectWebSocket`/`toggleConnection`/`handleWebSocketMessage`/`connectionStatus`/`isConnected` 及 `onMounted/onUnmounted` 的 WS 调用；`ChatInput` 不再传 `:disabled="!isConnected"`（始终可用）。消息渲染保持 `chat.messages` → `displayMessages`。`ChatNavbar` 移除连接/重连控件，保留 新建会话 / 清空 / 会话栏收起。

- [ ] **Step 3: app_id 运行**

```ts
const route = useRoute();
const appId = ref<number | null>(route.query.app_id ? Number(route.query.app_id) : null);
const appName = ref("");
watch(() => route.query.app_id, async (v) => {
  appId.value = v ? Number(v) : null; appName.value = "";
  if (appId.value) { const r = await getAiAppDetail(appId.value); appName.value = r.data?.data?.name || ""; }
}, { immediate: true });

const chat = useAiChat(() => ({
  path: appId.value ? `/ai/apps/${appId.value}/run/stream` : "/ai/assistant/stream",
  body: () => ({ session_id: currentSessionId.value }),
}));
```
`ChatNavbar` 增加 prop `appName`，非空时渲染可关闭 `el-tag`（关闭 → `router.replace({ path: "/ai/chat" })` 并 `appId=null`）。`handleNewSession` 不清除 appId。

- [ ] **Step 4: E2E `ai-chat.spec.ts`**

断言输入框铺满（宽度接近容器，> 600px）、placeholder 含「输入消息」、无「FA助手」；`/#/ai/chat?app_id=<不存在id>` 不崩溃（标签可能不显示）。

- [ ] **Step 5: 验证 + 提交**

Run: `cd frontend && pnpm type-check && pnpm e2e e2e/ai-chat.spec.ts`
```bash
git add frontend/src/views/module_ai/chat frontend/src/composables/ai/useAiChat.ts frontend/e2e/ai-chat.spec.ts
git commit -m "fix(ai): 智能助手输入框铺满/去 Agno WS/支持应用标签运行"
```

---

### Task 3: 列表页 CRUD 规范化（模型/提示词/应用/日志）

**Files:**
- Modify: `frontend/src/views/module_ai/model/index.vue`（去提供商下拉）
- Modify: `frontend/src/views/module_ai/prompt/index.vue`（列表 + 全屏画布弹窗）
- Modify: `frontend/src/views/module_ai/app/index.vue`（标准 CRUD + 运行）
- Modify: `frontend/src/views/module_ai/logs/index.vue`（确认标准）
- Test: `frontend/e2e/ai-model.spec.ts`、`ai-prompt.spec.ts`、`ai-app.spec.ts`、`ai-logs.spec.ts`

**Interfaces:**
- Consumes: 现有 API（`model.ts`/`prompt.ts`/`app.ts`/`logs.ts`）。
- Produces: 各页统一「上搜索、下列表/卡片」。

- [ ] **Step 1: 模型配置**

删除「提供商」`el-select`/`providerOptions`/`getAiProviderList` 调用；表单保留 `name/model/base_url/api_key/usage/capabilities_text/context_window/temperature/max_tokens/enabled/is_default/description/extra_headers_text`。确保 `PageSearch`（name/model）在上、`PageContent` 在下。

- [ ] **Step 2: 提示词改列表 + 画布弹窗**

页面结构：`PageSearch`（名称/分类）+ `PageContent`（列：名称/分类/版本/启用/操作）+ `EnhancedDialog`（`fullscreen`）承载现有三栏画布（块拖拽/编辑/变量+预览）。新增/编辑打开弹窗，保存调用 `createAiPrompt`/`updateAiPrompt`；列表行「编辑」拉 `getAiPromptDetail` 回填。

- [ ] **Step 3: AI应用**

`PageSearch`（名称/启用）+ `PageContent`（列：图标/名称/模型/提示词/工具数/输出格式/启用/操作）+ `EnhancedDialog` 表单（模型/提示词/工具多选/输出格式/入参 JSON）。操作列「运行」→ `router.push({ path: "/ai/chat", query: { app_id: row.id } })`。

- [ ] **Step 4: 调用日志**

确认 `PageSearch`（用途 chat/app、结果、关键字）+ `PageContent` 分页表格；移除任何内联搜索/工具栏。

- [ ] **Step 5: E2E + 验证 + 提交**

更新 4 个 E2E：各页断言 `.app-container`、搜索表单在表格上方（用 DOM 顺序或 `.el-form` 先于 `.el-table`）、新增按钮可见。
Run: `cd frontend && pnpm type-check && pnpm e2e e2e/ai-model.spec.ts e2e/ai-prompt.spec.ts e2e/ai-app.spec.ts e2e/ai-logs.spec.ts`
```bash
git add frontend/src/views/module_ai frontend/e2e
git commit -m "refactor(ai): 列表页统一为搜索在上/列表在下，模型去提供商，提示词改列表+画布弹窗"
```

---

### Task 4: 后端 `ai_tools` 扩展 + Agno 精选工具注册/解析/执行

**Files:**
- Modify: `backend/app/plugin/module_ai/tools_catalog/model.py`（`source`、`config`）
- Modify: `backend/app/plugin/module_ai/tools_catalog/schema.py`、`service.py`、`controller.py`
- Create: `backend/app/plugin/module_ai/agno_tools/__init__.py`、`registry.py`、`service.py`
- Modify: `backend/app/plugin/module_ai/assistant/service.py`（共享循环按 source 分派）
- Modify: `backend/app/scripts/init_app.py`（`_ensure_missing_columns` 补 `ai_tools.source/config`；调用 `_ensure_agno_tools()`）
- Modify: `backend/app/scripts/initialize.py`（无需改，模型已在）
- Test: `backend/tests/test_agno_tools.py`、扩展 `backend/tests/test_ai_tools.py`

**Interfaces:**
- Produces:
  - `AiToolModel.source: str`（`system`|`agno`|`http`）、`AiToolModel.config: dict|None`。
  - `agno_tools.registry.AGNO_CATALOG: list[dict]`：`{key, title, module, class_name, requires, config_fields, group, risk, description}`。
  - `agno_tools.service.get_tool_specs() -> list[dict]`（含 `ready`/`reason`/`config_fields`）。
  - `agno_tools.service.build_openai_schema(spec) -> dict`、`execute(spec, args, config) -> object`。
  - `tools_catalog.service.AiToolService.get_enabled_tool_schemas()` 合并 system/agno/http；`dispatch_tool(name, args, user_id, config=None)`。

- [ ] **Step 1: 模型/迁移/schema**

`model.py` 增 `source: Mapped[str] = mapped_column(String(16), default="system")`、`config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)`。`init_app.py::_ensure_missing_columns` 的 `new_columns` 增：
```python
"ai_tools": [("source", "VARCHAR(16) DEFAULT 'system'"), ("config", "JSONB")],
```
存量 HTTP 工具迁移：`UPDATE ai_tools SET source='http' WHERE kind='http' AND (source IS NULL OR source='system')`（放在 `_ensure_missing_columns` 后）。

- [ ] **Step 2: Agno 精选注册表 `registry.py`**

```python
AGNO_CATALOG = [
    {"key": "calculator", "title": "计算器", "module": "agno.tools.calculator", "class_name": "CalculatorTools", "requires": None, "config_fields": [], "group": "基础", "risk": "low", "description": "加减乘除、阶乘、开方等基础运算"},
    {"key": "csv_toolkit", "title": "CSV 工具", "module": "agno.tools.csv_toolkit", "class_name": "CsvTools", "requires": "duckdb", "config_fields": [], "group": "数据", "risk": "low"},
    {"key": "visualization", "title": "图表可视化", "module": "agno.tools.visualization", "class_name": "VisualizationTools", "requires": "matplotlib", "config_fields": [], "group": "数据", "risk": "low"},
    {"key": "webtools", "title": "网页工具", "module": "agno.tools.webtools", "class_name": "WebTools", "requires": None, "config_fields": [], "group": "网络", "risk": "low"},
    {"key": "hackernews", "title": "HackerNews", "module": "agno.tools.hackernews", "class_name": "HackerNewsTools", "requires": None, "config_fields": [], "group": "资讯", "risk": "low"},
    {"key": "python", "title": "Python 执行", "module": "agno.tools.python", "class_name": "PythonTools", "requires": None, "config_fields": [], "group": "高级", "risk": "high"},
    {"key": "shell", "title": "Shell 执行", "module": "agno.tools.shell", "class_name": "ShellTools", "requires": None, "config_fields": [], "group": "高级", "risk": "high"},
    {"key": "tavily", "title": "Tavily 搜索", "module": "agno.tools.tavily", "class_name": "TavilyTools", "requires": "tavily-python", "config_fields": [{"key": "api_key", "label": "API Key", "secret": True, "required": True}], "group": "网络", "risk": "low"},
    {"key": "serpapi", "title": "SerpAPI 搜索", "module": "agno.tools.serpapi", "class_name": "SerpApiTools", "requires": "google-search-results", "config_fields": [{"key": "api_key", "label": "API Key", "secret": True, "required": True}], "group": "网络", "risk": "low"},
    {"key": "duckduckgo", "title": "DuckDuckGo 搜索", "module": "agno.tools.duckduckgo", "class_name": "DuckDuckGoTools", "requires": "ddgs", "config_fields": [], "group": "网络", "risk": "low"},
    {"key": "wikipedia", "title": "维基百科", "module": "agno.tools.wikipedia", "class_name": "WikipediaTools", "requires": "wikipedia", "config_fields": [], "group": "网络", "risk": "low"},
    {"key": "openweather", "title": "城市天气", "module": "agno.tools.openweather", "class_name": "OpenWeatherTools", "requires": None, "config_fields": [{"key": "api_key", "label": "API Key", "secret": True, "required": True}], "group": "网络", "risk": "low"},
    {"key": "newspaper", "title": "新闻抓取", "module": "agno.tools.newspaper", "class_name": "NewspaperTools", "requires": "newspaper3k", "config_fields": [], "group": "资讯", "risk": "low"},
    {"key": "arxiv", "title": "arXiv 论文", "module": "agno.tools.arxiv", "class_name": "ArxivTools", "requires": "arxiv", "config_fields": [], "group": "资讯", "risk": "low"},
]
```
> 若某类名与 Agno 实际不符，以实现时 `dir(module)` 探测为准，但键名/字段名保持本契约。

- [ ] **Step 3: `agno_tools/service.py`**

```python
import importlib, inspect, importlib.util

def _probe(spec) -> tuple[bool, str]:
    req = spec.get("requires")
    if req and importlib.util.find_spec(req) is None:
        return False, f"缺少依赖：{req}"
    try:
        mod = importlib.import_module(spec["module"]); getattr(mod, spec["class_name"])
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)

def get_tool_specs() -> list[dict]:
    out = []
    for spec in AGNO_CATALOG:
        ready, reason = _probe(spec)
        out.append({**spec, "ready": ready, "reason": reason, "source": "agno"})
    return out

def _instantiate(spec, config: dict | None):
    mod = importlib.import_module(spec["module"])
    cls = getattr(mod, spec["class_name"])
    kwargs = {k: v for k, v in (config or {}).items()}
    return cls(**kwargs)

def build_openai_schema(spec, config=None) -> dict:
    inst = _instantiate(spec, config)
    fns = inst.functions
    props, required = {}, []
    for name, fn in fns.items():
        sig = inspect.signature(fn.entrypoint)
        for p in sig.parameters.values():
            if p.name in ("self", "kwargs", "args"): continue
            props[p.name] = {"type": "string"}
            if p.default is inspect._empty: required.append(p.name)
    return {"type": "function", "function": {"name": spec["key"], "description": spec.get("description") or spec["title"], "parameters": {"type": "object", "properties": props, "required": required}}}

async def execute(spec, args: dict, config=None) -> object:
    try:
        inst = _instantiate(spec, config)
    except Exception as e:  # noqa: BLE001
        return {"error": f"初始化失败：{e}"}
    fns = inst.functions
    # 单工具 key 对应一个 toolkit：按参数匹配同名的 function；否则返回可用函数说明
    fn = fns.get(spec["key"]) or next(iter(fns.values()), None)
    if fn is None: return {"error": "该工具集没有可用函数"}
    try:
        res = fn.entrypoint(**(args or {}))
        return res if inspect.isawaitable(res) is False else await res
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
```
> 说明：部分 toolkit 是多函数集合，`build_openai_schema` 以 toolkit key 暴露一个函数即可满足“可配置/可执行”；若需逐函数暴露，按 `fn.name` 生成多个工具行（实现时按可用性择优，但保持 `source="agno"` 与 `config_fields` 契约）。

- [ ] **Step 4: 合并 schema + 按 source 分派**

`tools_catalog/service.py`：
```python
@classmethod
async def get_enabled_tool_schemas(cls) -> list[dict]:
    schemas = []
    async with async_db_session() as db:
        rows = (await db.execute(select(AiToolModel).where(AiToolModel.is_deleted.is_(False), AiToolModel.enabled.is_(True)))).scalars().all()
    for t in rows:
        if t.source == "agno":
            from app.plugin.module_ai.agno_tools import service as agno
            spec = next((s for s in agno.get_tool_specs() if s["key"] == t.name), None)
            if spec and spec["ready"]:
                schemas.append(agno.build_openai_schema(spec, t.config))
        elif t.source == "http":
            schemas.append(build_http_schema(t))
        else:
            entry = TOOL_REGISTRY.get(t.name)
            if entry: schemas.append(entry["schema"])
    return schemas
```
`assistant/service.py` 的共享循环里，把 `_call_tool` 换成一个 dispatcher：按 `ai_tools.source` 选择 system(`_call_tool`)/agno(`agno_tools.service.execute`)/http(`execute_http_tool`)。找不到行时回退 system。

- [ ] **Step 5: 启动同步 `_ensure_agno_tools()`**

`init_app.py` 新增：遍历 `AGNO_CATALOG`，缺失则插入 `AiToolModel(name=key, source="agno", kind="agno", enabled=False, config=None, description=title)`；不覆盖已有。在 lifespan 中 `_ensure_ai_tools()` 之后调用。

- [ ] **Step 6: 测试**

`backend/tests/test_agno_tools.py`：
- `get_tool_specs()` 含 calculator 且 `ready=True`；含某 `requires` 缺失项 `ready=False, reason` 非空。
- `build_openai_schema(calculator_spec)` 的 `function.name=="calculator"`、`parameters.type=="object"`。
- `asyncio.run(execute(calculator_spec, {"expression": "1+1"}))` 或按实际签名参数执行不抛错（按签名参数传入）。
- 分派：`ai_tools` 插入 `source="agno", enabled=True` 的 calculator 行后 `get_enabled_tool_schemas()` 含 calculator。
扩展 `test_ai_tools.py`：`source`/`config` 持久化与掩码不回归。

- [ ] **Step 7: 验证 + 提交**

Run: `cd backend && uv run pytest tests/test_agno_tools.py tests/test_ai_tools.py -q && uv run ruff check app/plugin/module_ai/agno_tools app/plugin/module_ai/tools_catalog app/plugin/module_ai/assistant/service.py app/scripts/init_app.py`
```bash
git add backend/app/plugin/module_ai/agno_tools backend/app/plugin/module_ai/tools_catalog backend/app/plugin/module_ai/assistant/service.py backend/app/scripts/init_app.py backend/tests
git commit -m "feat(ai): 工具中心接入 Agno 精选工具（注册/解析/执行/按来源分派）"
```

---

### Task 5: 工具中心卡片页（el-card + 参数自动生成 + 自定义参数）

**Files:**
- Modify: `frontend/src/api/module_ai/tool.ts`（列表返回 `source`/`config_fields`/`ready`/`reason`；保存 `config`）
- Rebuild: `frontend/src/views/module_ai/tool/index.vue`
- Test: `frontend/e2e/ai-tool.spec.ts`（更新）

**Interfaces:**
- Consumes: `getAiToolList`（含 source/ready/config_fields）、`toggleAiTool`、`createAiTool`/`updateAiTool`/`deleteAiTool`/`testAiTool`。

- [ ] **Step 1: `tool.ts` 对齐字段**

列表响应包含 `source, kind, name, description, enabled, ready, reason, config_fields, config, method, url, headers, params_schema`（敏感值掩码）。

- [ ] **Step 2: 卡片网格**

单根 `.app-container`：顶部 `el-form :inline`（关键字、类型 `source`、状态 `ready`）→ `el-row :gutter="12"` + `el-col :xs="24" :sm="12" :md="8" :lg="6"`，每列一个 `el-card`：

```html
<el-card shadow="hover" class="tool-card">
  <template #header>
    <div class="tool-card__hd">
      <el-avatar :size="32" :icon="iconOf(tool)" />
      <span class="tool-card__name">{{ tool.name }}</span>
      <el-tag size="small" :type="sourceTagType(tool.source)">{{ sourceLabel(tool.source) }}</el-tag>
      <el-tag size="small" :type="tool.ready ? 'success' : 'warning'">
        {{ tool.ready ? '就绪' : `未就绪：${tool.reason || '缺少配置'}` }}
      </el-tag>
    </div>
  </template>
  <div class="tool-card__body">{{ tool.description || tool.group || '—' }}</div>
  <template #footer>
    <div class="tool-card__ft">
      <el-switch :model-value="tool.enabled" :disabled="!tool.ready" @change="(v)=>onToggle(tool,v)" />
      <el-button text type="primary" :disabled="!tool.config_fields?.length && tool.source!=='http'" @click="openConfig(tool)">配置</el-button>
      <el-button v-if="tool.source==='http'" text @click="openEdit(tool)">编辑</el-button>
      <el-button v-if="tool.source==='http'" text type="danger" @click="onDelete(tool)">删除</el-button>
    </div>
  </template>
</el-card>
```
`iconOf(tool)`：按 `group`/`source` 映射 Element Plus 图标，未知用首字符 `el-avatar`。未就绪卡片 `class="is-not-ready"`（仅 `opacity:.6`，不用自定义主题色）。

- [ ] **Step 3: 配置/新增弹窗（参数自动生成 + 自定义参数）**

`EnhancedDialog` 内：
- HTTP 工具：`name/method/url/headers(JSON)/params_schema(JSON)/enabled`（同现有表单）。
- Agno 工具：遍历 `tool.config_fields` 渲染字段；`secret:true` 用 `el-input type="password" show-password`；保存时值仍以 `****` 回显的不重写（沿用 Task 6 的 `_merge_headers` 思路，对 `config` 同样“`****`/空=保留”）。
- 「自定义参数」：`el-form` 内一个可增删的键值对列表（默认空），与自动字段合并进 `config`；提供「＋ 添加参数」按钮。
- Agno 卡片「新增」不适用（精选由后端 seeding）；「新增」按钮只创建 HTTP 工具。

- [ ] **Step 4: E2E `ai-tool.spec.ts`**

断言：`/#/ai/tool` 可见 `el-card` 卡片（≥1）、搜索表单在卡片之上、存在「配置」按钮；切换就绪卡片开关状态变化；未就绪卡片开关 disabled。

- [ ] **Step 5: 验证 + 提交**

Run: `cd frontend && pnpm type-check && pnpm e2e e2e/ai-tool.spec.ts`
```bash
git add frontend/src/api/module_ai/tool.ts frontend/src/views/module_ai/tool frontend/e2e/ai-tool.spec.ts
git commit -m "feat(ai): 工具中心改为 el-card 卡片，参数自动生成并支持自定义参数"
```

---

### Task 6: 全量回归 + 视觉验收 + 账本

**Files:**
- Modify: `.superpowers/sdd/progress.md`（追加记录；gitignored，不强制提交）
- Report: `docs/superpowers/reports/2026-09-13-ai-ui-overhaul-regression.md`

- [ ] **Step 1: 后端回归**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_ai/ app/scripts/init_app.py`

- [ ] **Step 2: 前端回归**

Run: `cd frontend && pnpm type-check && pnpm e2e`（记录 pre-existing/flaky，例如 smoke 429、dataset-to-train）。

- [ ] **Step 3: 视觉验收**

用 Playwright 截图 6 个页面（`#/ai/chat`、`#/ai/model`、`#/ai/prompt`、`#/ai/tool`、`#/ai/app`、`#/ai/logs`）到 `%TEMP%\opencode\ai-ui-shots\`，用 `vision-recognition` 核对：与 `module_system/param` 一致、搜索在列表上方、工具卡片有 header/footer/avatar、无自定义主题外壳；逐页记录结论。

- [ ] **Step 4: 报告 + 提交**

写 `docs/superpowers/reports/2026-09-13-ai-ui-overhaul-regression.md`（命令 + 结果 + 视觉结论 + 遗留），提交报告与必要修复。

---

## Self-Review

- Spec §2 菜单 6 项/下线 5 页 → Task 1；§3 智能助手 → Task 2；§4 CRUD 规范化 → Task 3；§5 工具中心数据/Agno/卡片 → Task 4+5；§7 验收 → Task 6。
- 命名一致：`source`（system/agno/http）、`config`、`AGNO_CATALOG`、`get_tool_specs`、`build_openai_schema`、`execute`、`get_enabled_tool_schemas` 全计划统一。
- 风险：Agno 类名/签名以实际探测为准（Task 4 Step 3 已说明）；删除页面须先 `rg` 清理引用避免死链；未就绪工具默认关闭并可解释原因。
