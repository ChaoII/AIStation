# 市场能力「安装 → 配置key → 绑定智能体 → 对话可用」链路打通 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户从市场安装的 MCP/工具/技能在智能体中心可用：安装后引导填 key+启用、智能体可绑定（含未启用 MCP）、对话能真正调用，且后端防跨用户绑定、支持 script 工具。

**Architecture:** 前端 4 处 Vue 改动（市场安装引导、我的资产联动、智能体 MCP 选择器/文案）+ 后端 2 处（智能体绑定校验、`_build_app_tools` 支持 script）。全部复用既有组件与风格，不改数据库结构。

**Tech Stack:** Vue3 + Element Plus（前端）、FastAPI + SQLAlchemy 2.0（后端）、pytest + test_client（后端测试）。

**Spec:** `docs/superpowers/specs/2026-10-16-market-install-to-agent-chain.md`

## Global Constraints

- 所有回复/注释/提交信息用中文；提交格式 `feat(market): 中文描述`。
- 前端只允许用 Element Plus 组件，禁止自定义 `font-size`，颜色/间距用 `--el-*` 变量，风格与同模块既有页面对齐。
- 后端 `CustomException`（`app.core.exceptions`）用于校验失败（msg 中文提示）。
- 前后端改动必须精确 `git add` 指定路径（工作区有大量无关脏文件，禁用 `-A`）。
- 提交前跑：后端 `ruff check` 相关文件 + 新增测试；前端 `pnpm run type-check`。
- 后端测试用 `tests/conftest.py` 的 `test_client` 会话级夹具；DB 场景用 `asyncio.run` + `async_db_session` 直连测试库。

## Review Focus

- 未启用 MCP 绑定智能体后，对话端 `enabled_servers` 会静默跳过（不报错）。行为应可预期：不报错、且该 MCP 工具不出现在对话工具里。→ 本计划不额外加提示，但 UI 已明确标注「未启用」。
- 后端校验须仅在请求**实际提供**绑定时校验（`update` 传 `None` 字段跳过），避免编辑其它字段时误拦。
- MCP 校验要判 `created_id`，防绑定他人携带密钥的服务器；工具按名、共享，仅判存在+启用。
- 前端安装「去配置」跳到「我的资产」后，若按名匹配不到已安装资产（`_unique_name` 加了后缀），应优雅回退（仅切页签、不强行打开编辑）。
- `script` 工具的 schema 由 `build_http_tool_schema` 生成，须存在 `params_schema` 且 `enabled=True` 才下发。

---

### Task 1: 后端智能体绑定校验（Spec ③）

**Files:**
- Modify: `backend/app/plugin/module_ai/agent/service.py`（新增 `_validate_agent_bindings`，并在 `create`/`update` 调用）
- Test: `backend/tests/test_agent_binding_validation.py`（新建）

**Interfaces:**
- Consumes: `db`（`AsyncSession`，来自 `async_db_session.begin()`）、`user_id:int`、请求的 `tool_ids:list[str]|None`/`skill_ids:list[int]|None`/`knowledge_ids:list[int]|None`/`mcp_ids:list[int]|None`。
- Produces: `async def _validate_agent_bindings(db, *, tool_ids=None, skill_ids=None, knowledge_ids=None, mcp_ids=None, user_id:int) -> None`（非法时 `raise CustomException(msg=中文)`）。
- 模型：`AiMcpServerModel`、`AiSkillModel`、`AiKnowledgeBaseModel`、`AiToolModel`。
- 消费方：`AiAgentService.create`（`agent/service.py:201-231`）与 `update`（`233-250`）在事务内、`flush` 前调用。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_agent_binding_validation.py
import asyncio
from types import SimpleNamespace as SN
import pytest

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.agent.service import AiAgentService
from app.plugin.module_ai.mcp.model import AiMcpServerModel


async def _insert_mcp(name, user_id, enabled=True):
    async with async_db_session.begin() as db:
        row = AiMcpServerModel(name=name, transport="streamable-http", enabled=enabled,
                               created_id=user_id, updated_id=user_id)
        db.add(row)
        await db.flush()
        return row.id


async def _create_agent(mcp_ids=None, skill_ids=None, tool_ids=None, knowledge_ids=None, uid=1):
    data = SN(
        agent_name="测试智能体", category_id=None, agent_role="", description="",
        model_id=None, prompt_id=None, temperature=None, workflow_id=None,
        tool_ids=tool_ids or [], skill_ids=skill_ids or [], mcp_ids=mcp_ids or [],
        knowledge_ids=knowledge_ids or [], capabilities=[], query_enabled=False,
        query_datasource="system", input_schema=None, avatar="", color="", markdown=True,
        enabled=True, order=0,
    )
    return await AiAgentService.create(data, auth=SN(user=SN(id=uid)))


def test_create_rejects_foreign_mcp():
    """绑定他人 MCP（created_id!=当前用户）应抛异常。"""
    fid = asyncio.run(_insert_mcp("foreign", user_id=2))
    with pytest.raises(CustomException):
        asyncio.run(_create_agent(mcp_ids=[fid], uid=1))


def test_create_accepts_own_mcp():
    """绑定自己创建的 MCP 应通过。"""
    mid = asyncio.run(_insert_mcp("own", user_id=1))
    a = asyncio.run(_create_agent(mcp_ids=[mid], uid=1))
    assert a["mcp_ids"] == [mid]


def test_create_rejects_missing_skill():
    with pytest.raises(CustomException):
        asyncio.run(_create_agent(skill_ids=[999999], uid=1))


def test_create_rejects_missing_tool():
    with pytest.raises(CustomException):
        asyncio.run(_create_agent(tool_ids=["no_such_tool"], uid=1))
```

- [ ] **Step 2: 运行，确认失败（当前未校验，前 3 个用例 fail）**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_agent_binding_validation.py -q`
Expected: `test_create_rejects_foreign_mcp` / `test_create_rejects_missing_skill` / `test_create_rejects_missing_tool` 均 **FAIL**（未抛 CustomException）；`test_create_accepts_own_mcp` 通过。

- [ ] **Step 3: 实现 `_validate_agent_bindings`**

在 `agent/service.py` 顶部补充 imports：`from sqlalchemy import select`、各模型 `AiMcpServerModel`/`AiSkillModel`/`AiKnowledgeBaseModel`/`AiToolModel`。新增模块级异步函数：

```python
async def _validate_agent_bindings(db, *, tool_ids=None, skill_ids=None,
                                   knowledge_ids=None, mcp_ids=None, user_id: int) -> None:
    """校验智能体绑定资产：MCP 须属当前用户；工具须存在且启用；技能/知识库须存在。"""
    if tool_ids:
        rows = (await db.execute(
            select(AiToolModel.name).where(
                AiToolModel.name.in_(tool_ids),
                AiToolModel.is_deleted.is_(False),
                AiToolModel.enabled.is_(True),
            )
        )).scalars().all()
        missing = [n for n in tool_ids if n not in rows]
        if missing:
            raise CustomException(msg=f"绑定的工具不存在或未启用：{', '.join(missing)}")
    if skill_ids:
        rows = (await db.execute(
            select(AiSkillModel.id).where(
                AiSkillModel.id.in_(skill_ids), AiSkillModel.is_deleted.is_(False)
            )
        )).scalars().all()
        missing = [i for i in skill_ids if i not in rows]
        if missing:
            raise CustomException(msg=f"绑定的技能不存在：{missing}")
    if knowledge_ids:
        rows = (await db.execute(
            select(AiKnowledgeBaseModel.id).where(
                AiKnowledgeBaseModel.id.in_(knowledge_ids),
                AiKnowledgeBaseModel.is_deleted.is_(False),
            )
        )).scalars().all()
        missing = [i for i in knowledge_ids if i not in rows]
        if missing:
            raise CustomException(msg=f"绑定的知识库不存在：{missing}")
    if mcp_ids:
        rows = (await db.execute(
            select(AiMcpServerModel.id, AiMcpServerModel.created_id).where(
                AiMcpServerModel.id.in_(mcp_ids),
                AiMcpServerModel.is_deleted.is_(False),
            )
        )).all()
        owner_map = {r[0]: r[1] for r in rows}
        bad = [i for i in mcp_ids if i not in owner_map or owner_map[i] != user_id]
        if bad:
            raise CustomException(msg=f"绑定的 MCP 服务器不存在或不属于当前用户：{bad}")
```

`create`（`203` 事务内，`db.add(a)` 前）调用：

```python
await _validate_agent_bindings(
    db, tool_ids=data.tool_ids or [], skill_ids=data.skill_ids or [],
    knowledge_ids=data.knowledge_ids or [], mcp_ids=getattr(data, "mcp_ids", None) or [],
    user_id=auth.user.id,
)
```

`update`（`239` 循环前）对非 `None` 的字段调用：

```python
await _validate_agent_bindings(
    db,
    tool_ids=data.tool_ids if getattr(data, "tool_ids", None) is not None else None,
    skill_ids=data.skill_ids if getattr(data, "skill_ids", None) is not None else None,
    knowledge_ids=data.knowledge_ids if getattr(data, "knowledge_ids", None) is not None else None,
    mcp_ids=data.mcp_ids if getattr(data, "mcp_ids", None) is not None else None,
    user_id=auth.user.id,
)
```

- [ ] **Step 4: 运行测试，确认全通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_agent_binding_validation.py -q`
Expected: 4 passed。

- [ ] **Step 5: 提交**

```bash
cd D:\AIStation
git add backend/app/plugin/module_ai/agent/service.py backend/tests/test_agent_binding_validation.py
git commit -m "feat(agent): 智能体绑定资产校验，防跨用户绑定与不存在资产"
```

---

### Task 2: `_build_app_tools` 支持 script 工具（Spec ④）

**Files:**
- Modify: `backend/app/plugin/module_ai/apps/service.py` `_build_app_tools`（`220-262`）
- Test: `backend/tests/test_app_build_app_tools_script.py`（新建）

**Interfaces:**
- Consumes: 既有 `_build_app_tools(names: list[str] | None) -> tuple[list[dict], dict]`。
- Produces: 无新签名；`source=="script"` 工具时，`schemas` 追加 `build_http_tool_schema(tool)` 返回的 schema。
- 消费方：`agent/service.py:run_ui_stream` 与 `apps/service.py:run_app_ui_stream` 复用本函数；`dispatch_tool` 已支持 script 执行。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_app_build_app_tools_script.py
import asyncio
from app.core.database import async_db_session
from app.plugin.module_ai.apps.service import _build_app_tools
from app.plugin.module_ai.tools_catalog.model import AiToolModel


async def _insert_script_tool(name):
    async with async_db_session.begin() as db:
        row = AiToolModel(
            name=name, kind="script", source="script", enabled=True,
            params_schema=[{"name": "q", "type": "string", "required": True}],
            code="def run(q):\n    return q", created_id=1, updated_id=1,
        )
        db.add(row)
        await db.flush()


def test_build_app_tools_script_source():
    asyncio.run(_insert_script_tool("s_weather"))
    schemas, http_tools = asyncio.run(_build_app_tools(["s_weather"]))
    assert schemas, "script 工具应产出 schema"
    assert any("s_weather" in (s.get("function") or {}).get("name", "") for s in schemas)
```

- [ ] **Step 2: 运行，确认失败**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_app_build_app_tools_script.py -q`
Expected: FAIL（schemas 为空）。

- [ ] **Step 3: 实现 script 分支**

在 `_build_app_tools` 的 `if source == "http":` 分支后追加：

```python
        if source == "script":
            schemas.append(build_http_tool_schema(tool))
```

（`build_http_tool_schema` 已在 `apps/service.py:224-228` 导入。）

- [ ] **Step 4: 运行，确认通过**

Run: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_app_build_app_tools_script.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd D:\AIStation
git add backend/app/plugin/module_ai/apps/service.py backend/tests/test_app_build_app_tools_script.py
git commit -m "feat(apps): script 源工具可被智能体/应用绑定解析"
```

---

### Task 3: 前端安装后引导（Spec ①）

**Files:**
- Modify: `frontend/src/views/module_ai/market/components/MarketBrowse.vue`
- Modify: `frontend/src/views/module_ai/market/index.vue`
- Modify: `frontend/src/views/module_ai/market/components/MarketMine.vue`

**Interfaces:**
- Consumes: `MarketItem`（含 `asset_type`/`name`/`payload`）、`installMarketItem(item.id)`、`ElMessageBox`/`ElMessage`。
- Produces: `MarketBrowse` 触发 `goConfigure` 事件 `{ asset_type: string; name: string }`；`index.vue` 维护 `mineTarget` ref 并传给 `MarketMine`；`MarketMine` 处理 target 后触发 `targetHandled` 事件。

- [ ] **Step 1: `MarketBrowse.vue` 加判定与事件**

新增 `defineEmits<{ goConfigure: [target: { asset_type: string; name: string }] }>()`；`installItem` 末尾（`loadItems()` 前）加：

```ts
const payload: any = item.payload || {};
const needsKey =
  item.asset_type === "mcp" &&
  ((payload.auth_type && payload.auth_type !== "none") ||
    JSON.stringify(payload.env || payload.args || "").includes("<"));
if (needsKey) {
  await ElMessageBox.alert(
    `「${item.name}」已安装，但需要到「我的资产」填写密钥并启用后，才能在智能体中选用。`,
    "需要配置密钥",
    { confirmButtonText: "去配置", type: "warning" }
  );
  emit("goConfigure", { asset_type: item.asset_type, name: item.name });
} else {
  ElMessage.success(`已安装「${item.name}」，可在智能体中选用`);
}
```

- [ ] **Step 2: `market/index.vue` 联动页签**

新增 `mineTarget = ref<{ asset_type: string; name: string } | null>(null)`；模板改为：

```html
<MarketBrowse @go-configure="goConfigure" />
<MarketMine :target="mineTarget" @target-handled="mineTarget = null" />
```

脚本加：`function goConfigure(t: {asset_type:string;name:string}) { activeTab.value = "mine"; mineTarget.value = t; }`

- [ ] **Step 3: `MarketMine.vue` 处理 target**

`defineProps<{ target: { asset_type: string; name: string } | null }>()`、`emit("targetHandled")`。新增 `watch(() => props.target, ...)`：非空时 `assetType.value = target.asset_type`，等 `items` 加载后按 `row.name === target.name` 找 `openEdit(row)`；找到则编辑，找不到仅提示；随后 `emit("targetHandled")`。（用 `nextTick`/后续 `load` 后匹配，`name` 配不到时容错。）

- [ ] **Step 4: 前端校验 + 浏览器核验**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
然后无头浏览器截图：装一个需密钥 MCP → 出现「需要配置密钥」弹窗 → 点「去配置」切到「我的资产」并打开其编辑弹窗。与既有页面对照风格一致。

- [ ] **Step 5: 提交**

```bash
cd D:\AIStation
git add frontend/src/views/module_ai/market/components/MarketBrowse.vue frontend/src/views/module_ai/market/index.vue frontend/src/views/module_ai/market/components/MarketMine.vue
git commit -m "feat(market): 安装需密钥MCP后引导去我的资产配置并启用"
```

---

### Task 4: 智能体 MCP 选择器（Spec ②）

**Files:**
- Modify: `frontend/src/views/module_ai/agent/index.vue:595-611`

**Interfaces:**
- Consumes: `mcpOptions`（含 `id`/`name`/`transport`/`enabled`）、`agentForm.mcp_ids`。
- Produces: 无新接口；仅改绑定 UI 与提示文案。

- [ ] **Step 1: 改 MCP 下拉（允许绑未启用 + 标记 + 文案）**

```html
<el-option
  v-for="m in mcpOptions"
  :key="m.id"
  :label="`${m.name}（${m.transport}${m.enabled ? '' : ' · 未启用'}）`"
  :value="m.id"
/>
```
hint 改为：`MCP 服务器在「能力市场 → 我的资产」配置并启用；未启用的绑定后在对话中暂不生效`

- [ ] **Step 2: 前端校验 + 浏览器核验**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
无头浏览器截图：智能体编辑表单 MCP 下拉出现未启用项（带「· 未启用」标记）且可选；提示文案指向「能力市场 → 我的资产」。

- [ ] **Step 3: 提交**

```bash
cd D:\AIStation
git add frontend/src/views/module_ai/agent/index.vue
git commit -m "feat(agent): 智能体MCP选择器允许绑定未启用服务器并修正引导文案"
```

---

## 收尾（全链路回归）

- 后端：`cd backend && .venv\Scripts\python.exe -m pytest tests/test_market_snapshot_security.py tests/test_agent_binding_validation.py tests/test_app_build_app_tools_script.py tests/test_market_share.py tests/test_market_install.py tests/test_agent_market.py -q` 全通过；`ruff check` 相关文件干净。
- 前端：`pnpm run type-check && pnpm run lint`。
- 无头浏览器走全链路：装需密钥 MCP → 引导去配置并启用 → 智能体绑定该 MCP → 点开智能体对话，确认 MCP 工具可被调用。
