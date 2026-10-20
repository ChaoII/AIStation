# P7 顶点：保存视图 + 图模板 + 时间轴 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给本体图谱加「保存视图 + 图模板 + 时间轴」三能力：把当前图配置存起来、可分享/版本化，并按实例时间属性做时间滑块过滤。

**Architecture:** 后端新增 `graph_view.py` 模块，完全复刻 `object_view.py` 的 raw-SQL + `service._exec/_exec_write` 模式，路由挂到 `/api/v1/ai/ontology/graph-views/*`；新增两张表 `ai_ont_graph_view`/`ai_ont_graph_view_version`（经 `service._ONT_TABLES_SQL` 运行时建表，无 Alembic）。前端在 `OntGraphWorkspace` 顶部加「保存视图/模板」控制区，在对象探索实例图加「时间轴」面板，均用 Element Plus 组件。

**Tech Stack:** FastAPI + raw SQL（asyncpg/SQLAlchemy 会话，`service._exec/_exec_write`）+ Vue 3 + Element Plus + Cytoscape（GraphCanvas）。

**Spec:** `docs/superpowers/specs/2026-10-20-ontology-p7-graph-views-design.md`

## Global Constraints

- 后端写库一律经 `from . import service as _svc` 下的 `_svc._exec(sql, params)`（查）/ `_svc._exec_write(sql, params)`（写）；业务错误用 `app.core.exceptions.CustomException(msg=...)`；变更留痕用 `_svc._log_change(<domain_code>, "graph_view", <action>, <detail>)`。
- 表一律前缀 `ai_ont_*`，无 Alembic 迁移，建表走 `service._ONT_TABLES_SQL`（PG SQL）；测试建表走 `backend/tests/_ont_ddl.py` 的 `ONT_DDL`（SQLite）。新表必须**同时**加进两处，否则 `missing_from_ddl` 回归测试失败。
- 权限码：读 = `module_ai:ontology:query`（`AuthDep`），写 = `module_ai:ontology:edit`（`AuthEdit`）。
- 时间属性判定 `base_type ∈ {"date", "datetime"}`（对齐 `function_engine.ONT_VALUE_TYPES`）。
- `state` 固定字段：`{ layout, theme, onlyConnected, physicsMode, shortestMode, multiSelect, search, selected: string[], zoom: number, pan: {x, y} }`。
- 前端：复用 Element Plus 组件与 `--el-*` 变量，禁自造主题外壳；写操作按钮带 `v-hasPerm="'module_ai:ontology:edit'"`；删除/移除类必须 `ElMessageBox.confirm` 二次确认。
- 提交信息用 `feat(ontology): 中文描述`；代码注释用中文。

## Review Focus

- `state` 缺失或非法 JSON → 回退默认图，不报错（Task 2 测试）。
- `share_mode='inherit'` 且 `share_roles` 空 → 跟随域权限；列表只返回可见（Task 4 测试）。
- 保存视图时 `domain_code` 为空（未选域）→ 拒绝（`CustomException`）（Task 2 测试）。
- `timeline_props` 无候选 → 返回 `[]`，前端显示「无可用于时间轴的属性」（Task 5 测试 + Task 8 前端）。
- 模板 `domain_code=''` 全局、saved 按域 → `list_views` 按 `kind` 过滤正确（Task 2 测试）。
- 版本回滚后 `version` 自增且 `state` 还原（Task 3 测试）。

---

### Task 1: 后端表结构（`ai_ont_graph_view` + `ai_ont_graph_view_version`）

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/service.py`（`_ONT_TABLES_SQL` 追加 2 条）
- Modify: `backend/tests/_ont_ddl.py`（`ONT_DDL` 追加 2 条 SQLite DDL）
- Create: `backend/tests/test_graph_view.py`（含模块级建表 fixture + 表存在性测试）

**Interfaces:**
- Consumes: 无（仅建表）。
- Produces: 表 `ai_ont_graph_view`、`ai_ont_graph_view_version` 可被后续 `graph_view.py` 读写。

- [ ] **Step 1: 在 `_ont_ddl.ONT_DDL` 追加两张表（SQLite）**

```python
"ai_ont_graph_view": "CREATE TABLE IF NOT EXISTS ai_ont_graph_view (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT DEFAULT '', description TEXT DEFAULT '', graph_kind TEXT DEFAULT 'saved', domain_code TEXT DEFAULT '', state TEXT DEFAULT '{}', filters TEXT DEFAULT '[]', share_roles TEXT DEFAULT '[]', share_mode TEXT DEFAULT 'inherit', status TEXT DEFAULT 'experimental', visibility TEXT DEFAULT 'normal', created_by TEXT DEFAULT '', is_default INTEGER DEFAULT 0, version INTEGER DEFAULT 1, created_time TEXT, updated_time TEXT, is_deleted INTEGER DEFAULT 0)",
"ai_ont_graph_view_version": "CREATE TABLE IF NOT EXISTS ai_ont_graph_view_version (id INTEGER PRIMARY KEY AUTOINCREMENT, view_code TEXT, version INTEGER, state TEXT DEFAULT '{}', note TEXT DEFAULT '', created_by TEXT DEFAULT '', created_time TEXT)",
```

- [ ] **Step 2: 在 `service._ONT_TABLES_SQL` 追加对应 PG DDL（`BIGSERIAL`/`JSONB`/`TIMESTAMP`）**

对齐 `ai_ont_object_view` 的写法；`code VARCHAR(160) NOT NULL, graph_kind VARCHAR(16) DEFAULT 'saved', domain_code VARCHAR(80) DEFAULT '', state JSONB DEFAULT '{}', filters JSONB DEFAULT '[]', share_roles JSONB DEFAULT '[]', share_mode VARCHAR(16) DEFAULT 'inherit', is_default BOOLEAN DEFAULT false, version INTEGER DEFAULT 1` + 通用审计列（`status/visibility/created_by/created_time/updated_time/is_deleted`）。

- [ ] **Step 3: 写表存在性测试**

```python
# test_graph_view.py
import pytest, _ont_ddl
from app.plugin.module_ai.ontology import service as _svc

@pytest.fixture(scope="module", autouse=True)
async def _ddl():
    # 复刻 test_object_view_index_proposal.py 的建表 fixture：遍历 _ont_ddl.ONT_DDL.values() 建表
    ...

async def test_graph_view_tables_exist():
    r = await _svc._exec("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('ai_ont_graph_view','ai_ont_graph_view_version')")
    names = {row[0] for row in r.fetchall()}
    assert names == {"ai_ont_graph_view", "ai_ont_graph_view_version"}
```

- [ ] **Step 4: 运行确认通过 + `missing_from_ddl` 回归**

Run: `uv run pytest tests/test_graph_view.py -q`（断言表存在）
Run: `uv run pytest tests/test_object_view_index_proposal.py -q -k missing_from_ddl`（新表在 DDL 里有对应，无缺失）
Expected: 均 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/ontology/service.py backend/tests/_ont_ddl.py backend/tests/test_graph_view.py
git commit -m "feat(ontology): 新增 ai_ont_graph_view 两表结构与测试建表"
```

---

### Task 2: `graph_view.py` 核心 CRUD（create/list/get/update/remove）

**Files:**
- Create: `backend/app/plugin/module_ai/ontology/graph_view.py`
- Test: `backend/tests/test_graph_view.py`（追加 `TestGraphViewCRUD`）

**Interfaces:**
- Consumes: `service._exec/_exec_write/_json_list/_json_dict/_log_change`、`CustomException`。
- Produces:
  - `_j(v: Any) -> str`
  - `_row_to_view(row) -> dict`（JSON 列反序列化：`state/filters/share_roles`）
  - `async def list_views(domain_code: str = "", kind: str = "") -> list[dict]`
  - `async def get_view(code: str) -> dict | None`
  - `async def create_view(data: dict, actor: str = "") -> dict`
  - `async def update_view(code: str, data: dict, actor: str = "") -> dict`
  - `async def remove_view(code: str) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# TestGraphViewCRUD
async def test_create_and_get_view():
    r = await _gv.create_view({
        "name": "默认图", "graph_kind": "saved", "domain_code": "fuel_business",
        "state": {"layout": "cose", "theme": "default", "selected": [], "zoom": 1, "pan": {"x": 0, "y": 0}},
    }, actor="admin")
    assert r["ok"] is True
    v = await _gv.get_view(r["code"])
    assert v["state"]["layout"] == "cose"
    assert v["domain_code"] == "fuel_business"

async def test_create_view_requires_domain():
    with pytest.raises(CustomException):
        await _gv.create_view({"name": "x", "graph_kind": "saved", "domain_code": ""})

async def test_list_views_filters_by_kind():
    await _gv.create_view({"name": "A", "graph_kind": "saved", "domain_code": "d1"})
    await _gv.create_view({"name": "B", "graph_kind": "template", "domain_code": ""})
    saved = await _gv.list_views(domain_code="d1", kind="saved")
    assert [x["name"] for x in saved] == ["A"]
    tpl = await _gv.list_views(kind="template")
    assert [x["name"] for x in tpl] == ["B"]

async def test_update_and_remove_view():
    v = await _gv.create_view({"name": "C", "graph_kind": "saved", "domain_code": "d1"})
    up = await _gv.update_view(v["code"], {"state": {"layout": "grid"}})
    assert (await _gv.get_view(v["code"]))["state"]["layout"] == "grid"
    await _gv.remove_view(v["code"])
    assert await _gv.get_view(v["code"]) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_graph_view.py -q`（`from .graph_view import ...` 报模块不存在）
Expected: FAIL

- [ ] **Step 3: 实现 `graph_view.py`**

实现文件名/签名如上。要点：
- `_j` 复刻 `object_view._j`（`json.dumps(..., ensure_ascii=False, default=...)` 处理 datetime/Decimal）。
- `_row_to_view` 对 `state/filters/share_roles` 用 `_svc._json_list/_json_dict` 反序列化；state 缺失回退 `{}`。
- `create_view`：`domain_code` 为空且 `graph_kind='saved'` 时抛 `CustomException("保存视图必须归属某个本体域")`；`code` 为空生成 `f"gv_{uuid4().hex[:12]}"`；校验 `code` 唯一（重复抛 `CustomException`）；写 `INSERT` 后用 `_svc._log_change(domain_code, "graph_view", "create", f"视图 {code}")`。
- `update_view`：只更新传入的非空字段 + 自增 `version`（`version=version+1`）并写 `updated_time=now()`；state 缺失用现有值。
- `list_views`：`WHERE is_deleted=false`，按 `domain_code`、`kind` 过滤；返回 `_row_to_view` 列表。
- `get_view`：按 `code` + `is_deleted=false` 取单个；`remove_view` 置 `is_deleted=true`。

- [ ] **Step 4: 运行通过**

Run: `uv run pytest tests/test_graph_view.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/ontology/graph_view.py backend/tests/test_graph_view.py
git commit -m "feat(ontology): graph_view 核心增删改查"
```

---

### Task 3: 版本管理与默认（versions/restore/set-default）

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/graph_view.py`
- Test: `backend/tests/test_graph_view.py`（追加 `TestGraphViewVersion`、`TestGraphViewDefault`）

**Interfaces:**
- Consumes: Task 2 的 `get_view`、`_j`、`_svc._exec_write/_log_change`。
- Produces:
  - `async def list_versions(code: str) -> list[dict]`
  - `async def restore_version(code: str, version: int, actor: str = "") -> dict`
  - `async def set_default(code: str, domain_code: str = "") -> dict`

- [ ] **Step 1: 写失败测试**

```python
async def test_version_bump_and_restore():
    v = await _gv.create_view({"name": "V", "graph_kind": "saved", "domain_code": "d1",
                               "state": {"layout": "cose"}})
    await _gv.update_view(v["code"], {"state": {"layout": "grid"}})
    await _gv.update_view(v["code"], {"state": {"layout": "concentric"}})
    vers = await _gv.list_versions(v["code"])
    assert len(vers) == 2 and vers[0]["version"] == 2   # 只有 update 才快照
    await _gv.restore_version(v["code"], 1)
    assert (await _gv.get_view(v["code"]))["state"]["layout"] == "cose"

async def test_set_default_unique_per_domain():
    a = await _gv.create_view({"name": "A", "graph_kind": "saved", "domain_code": "d1"})
    b = await _gv.create_view({"name": "B", "graph_kind": "saved", "domain_code": "d1"})
    await _gv.set_default(a["code"], "d1")
    await _gv.set_default(b["code"], "d1")
    views = await _gv.list_views(domain_code="d1", kind="saved")
    assert sum(1 for x in views if x["is_default"]) == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_graph_view.py -q -k "Version or Default"`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现**

- `update_view` 里每次写成功即插入 `ai_ont_graph_view_version`（`view_code, version, state, note, created_by`），并把主表 `version=version+1`。
- `list_versions`：`SELECT ... FROM ai_ont_graph_view_version WHERE view_code=:c ORDER BY version DESC`。
- `restore_version(code, version)`：找到该版本 `state`，`UPDATE ai_ont_graph_view SET state=:s, version=version+1`（并插入新版本快照），返回 `{ok, version}`。
- `set_default(code, domain_code)`：先把同 `domain_code` 全部 `is_default=false`，再置目标 `is_default=true`。

- [ ] **Step 4: 运行通过**

Run: `uv run pytest tests/test_graph_view.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/ontology/graph_view.py backend/tests/test_graph_view.py
git commit -m "feat(ontology): graph_view 版本快照/回滚/默认"
```

---

### Task 4: 分享与权限（share/can_view/list_shared/link）

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/graph_view.py`
- Test: `backend/tests/test_graph_view.py`（追加 `TestGraphViewShare`、`TestGraphViewPermission`）

**Interfaces:**
- Consumes: `get_view`、`_svc._exec_write/_exec/_log_change`。
- Produces:
  - `async def share_view(code: str, share_mode: str, roles: list | None = None) -> dict`
  - `async def can_view_view(code: str, principal) -> tuple[bool, str]`
  - `async def list_shared_views(principal) -> list[dict]`
  - `async def view_link(code: str, base: str = "#/ai/ontology") -> dict`

- [ ] **Step 1: 写失败测试**

```python
class _P:  # 假 principal：c 是 code 集合
    def __init__(self, roles): self.roles = set(roles)

async def test_share_and_can_view():
    v = await _gv.create_view({"name": "S", "graph_kind": "saved", "domain_code": "d1"})
    await _gv.share_view(v["code"], "roles", ["role_a"])
    ok, _ = await _gv.can_view_view(v["code"], _P(["role_a"]))
    assert ok is True
    ok2, _ = await _gv.can_view_view(v["code"], _P(["role_z"]))
    assert ok2 is False

async def test_inherit_follows_domain(monkeypatch):
    # share_mode='inherit'（默认）且无 roles → 走域权限（true），实现按「非 roles 即公开可见」处理
    v = await _gv.create_view({"name": "I", "graph_kind": "saved", "domain_code": "d1"})
    ok, _ = await _gv.can_view_view(v["code"], _P([]))   # inherit 且空 roles → 可见
    assert ok is True
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_graph_view.py -q -k "Share or Permission"`
Expected: FAIL

- [ ] **Step 3: 实现**

- `share_view(code, share_mode, roles)`：`UPDATE ai_ont_graph_view SET share_mode=:m, share_roles=:r`，`_log_change`。
- `can_view_view(code, principal)`：`share_mode='roles'` 时，`principal.roles ∩ share_roles` 非空才可见；`share_mode='inherit'`（默认）时 true（跟随域，域权限由前端/其它层承担，此处不重复判定）。返回 `(bool, reason)`。
- `list_shared_views(principal)`：可见视图 = `share_mode='roles'` 且 `principal.roles ∩ share_roles` 非空，或 `share_mode='inherit'`。
- `view_link(code, base)`：返回 `{url: f"{base}/graph-view?view={code}"}`（与对象视图 `view_url` 一致风格）。

- [ ] **Step 4: 运行通过**

Run: `uv run pytest tests/test_graph_view.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/ontology/graph_view.py backend/tests/test_graph_view.py
git commit -m "feat(ontology): graph_view 分享/权限/深链"
```

---

### Task 5: 时间属性候选端点（`timeline_props`）

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/graph_view.py`
- Test: `backend/tests/test_graph_view.py`（追加 `TestGraphViewTimelineProps`）

**Interfaces:**
- Consumes: `_svc._exec`。
- Produces: `async def timeline_props(domain_code: str = "") -> list[dict]`。

- [ ] **Step 1: 写失败测试**

```python
async def test_timeline_props_returns_date_props():
    # 预置：某域对象 ai_ont_object 下 ai_ont_property 有一条 base_type='datetime'
    await _gv.timeline_props()  # 至少不抛错，返回 list
    props = await _gv.timeline_props("d1")
    assert isinstance(props, list)
    assert all(p["base_type"] in ("date", "datetime") for p in props)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_graph_view.py -q -k TimelineProps`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现**

```python
async def timeline_props(domain_code: str = "") -> list[dict]:
    sql = ("SELECT o.code, o.name, p.code, p.name, p.base_type "
           "FROM ai_ont_object o JOIN ai_ont_property p ON p.object_code = o.code "
           "WHERE p.is_deleted = false AND p.base_type IN ('date','datetime')")
    params = {}
    if domain_code:
        sql += " AND o.domain_code = :d"; params["d"] = domain_code
    rows = await _svc._exec(sql, params)
    return [{"object_code": r[0], "object_name": r[1], "prop_code": r[2],
             "prop_name": r[3], "base_type": r[4]} for r in rows.fetchall()]
```

- [ ] **Step 4: 运行通过**

Run: `uv run pytest tests/test_graph_view.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/ontology/graph_view.py backend/tests/test_graph_view.py
git commit -m "feat(ontology): 时间轴属性候选端点 timeline_props"
```

---

### Task 6: controller 路由接入（`/graph-views/*`）

**Files:**
- Modify: `backend/app/plugin/module_ai/ontology/controller.py`
- Modify: `backend/tests/test_graph_view.py`（追加 `TestGraphViewRoutes`）

**Interfaces:**
- Consumes: `graph_view` 模块全部函数；`AuthDep`/`AuthEdit`；`_principal`；`_uid`。
- Produces: `GET/POST` 路由 `/api/v1/ai/ontology/graph-views/*`。

- [ ] **Step 1: 写失败测试（路由注册 + 简单调用）**

```python
async def test_graph_view_routes_registered():
    from app.api.v1.module_ai.ontology import controller as _c
    routes = [getattr(r.path, "path", r.path) for r in _c.OntologyRouter.routes]
    assert any("/graph-views" in str(p) for p in routes)
    assert any("graph-views/{code}/versions" in str(p) for p in routes)
    assert any("graph-views/timeline-props" in str(p) for p in routes)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_graph_view.py -q -k Routes`
Expected: FAIL

- [ ] **Step 3: 在 `controller.py` 接入路由（对齐 `object-views` 惯例）**

用 `graph_view as _gv` 导入。路由（前缀 `OntologyRouter` 已含 `/api/v1/ai/ontology`）：
- `GET /graph-views`（AuthDep）→ `_gv.list_views(domain_code, kind)`
- `GET /graph-views/{code}`（AuthDep）→ `_gv.get_view(code)`
- `POST /graph-views/save`（AuthEdit）→ `_gv.create_view(data, _uid(auth))`
- `POST /graph-views/update`（AuthEdit）→ `_gv.update_view(code, data, _uid(auth))`
- `POST /graph-views/default`（AuthEdit）→ `_gv.set_default(code, domain_code)`
- `POST /graph-views/remove`（AuthEdit）→ `_gv.remove_view(code)`
- `GET /graph-views/{code}/versions`（AuthDep）→ `_gv.list_versions(code)`
- `POST /graph-views/restore`（AuthEdit）→ `_gv.restore_version(code, version, _uid(auth))`
- `POST /graph-views/share`（AuthEdit）→ `_gv.share_view(code, share_mode, share_roles)`
- `GET /graph-views/{code}/link`（AuthDep）→ `_gv.view_link(code)`
- `GET /graph-views/shared`（AuthDep）→ `_gv.list_shared_views(await _principal(auth))`
- `GET /graph-views/timeline-props`（AuthDep）→ `_gv.timeline_props(domain_code)`

- [ ] **Step 4: 运行通过**

Run: `uv run pytest tests/test_graph_view.py -q`
Expected: PASS（含 Routes 测试）

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/ontology/controller.py backend/tests/test_graph_view.py
git commit -m "feat(ontology): 接入 /graph-views 路由与权限"
```

---

### Task 7: 前端 API + 图工作区「保存视图/模板」控制区

**Files:**
- Modify: `frontend/src/api/module_ai/ontology.ts`（追加 graph-view API 函数，命名 `getGraphViewList/getGraphViewDetail/createGraphView/saveGraphView/updateGraphView/shareGraphView/getGraphViewVersions/restoreGraphView/removeGraphView/setDefaultGraphView/getGraphViewLink/getTimelineProps`）
- Modify: `frontend/src/views/module_ai/knowledge/GraphCanvas.vue`（新增 `getViewport`/`setViewport` 并加入 `defineExpose`）
- Modify: `frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue`（顶部工具栏加「视图/模板」控制区）
- Test: `frontend/src/views/module_ai/ontology/components/__tests__/graphView.spec.ts`（若有构建；否则用 type-check + eslint）

**Interfaces:**
- Consumes: 后端 `/graph-views/*` 端点；`useOntologyData`/图工作区现有 `state`。
- Produces: 图工作区可保存/加载/分享/版本化当前图；模板可创建/还原。

- [ ] **Step 1: 在 `ontology.ts` 追加 API 函数**（返回 `request.post/get` 的封禁式调用，对齐文件内既有函数风格）
- [ ] **Step 2: 在 `GraphCanvas.vue` 增加视口读写**（`defineExpose` 目前无 viewport 方法；`zoom(level)` 是缩放倍率、无 `pan`）

```ts
function getViewport() {
  return { zoom: cy.zoom(), pan: { x: cy.pan().x, y: cy.pan().y } };
}
function setViewport(v: { zoom: number; pan: { x: number; y: number } }) {
  if (v && typeof v.zoom === "number") cy.viewport({ zoom: v.zoom, pan: v.pan || { x: 0, y: 0 } });
}
// defineExpose 追加 getViewport, setViewport
```

- [ ] **Step 3: 在 `OntGraphWorkspace.vue` 顶部工具栏加控制区**

先 `useOntologyData()` 解构 `currentDomain`（现只解构了 `scopedObjects/scopedLinks`）。用 `el-dropdown`（「视图」/「模板」）+ `el-dialog`（保存命名 + `el-form`）。收集当前 `state`：
```ts
const collectState = () => ({
  layout: layout.value, theme: theme.value, onlyConnected: onlyConnected.value,
  physicsMode: physicsMode.value, shortestMode: shortestMode.value, multiSelect: multiSelect.value,
  search: search.value, selected: [...selectedNames.value],
  ...(graphRef.value?.getViewport?.() ?? { zoom: 1, pan: { x: 0, y: 0 } }),
})
```
保存→`createGraphView({name, description, graph_kind, domain_code: currentDomain, state})`；加载：拉 `getGraphViewList(domain_code, kind)` 下拉，选后把 `state` 写回图工作区（layout/theme/onlyConnected/... + `graphRef.value?.setLayout?.(state.layout)`，渲染后 `nextTick`/`setTimeout` 再 `graphRef.value?.setViewport?.({ zoom, pan })`，因布局为异步）；模板入口 `graph_kind='template', domain_code:''`。分享 `shareGraphView`、版本 `getGraphViewVersions`/`restoreGraphView`、设默认 `setDefaultGraphView`、删除 `removeGraphView`（`ElMessageBox.confirm`）。

- [ ] **Step 4: 运行校验**

Run: `cd frontend && pnpm run type-check`（通过）
Run: `npx eslint src/views/module_ai/ontology/components/OntGraphWorkspace.vue src/views/module_ai/knowledge/GraphCanvas.vue src/api/module_ai/ontology.ts`（干净）

- [ ] **Step 5: 无头浏览器验证**：选域→改布局/主题→保存→切走→加载还原 state；从模板一键还原。
- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/module_ai/ontology.ts frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue
git commit -m "feat(ontology): 图工作区保存视图/模板控制区"
```

---

### Task 8: 前端时间轴面板（对象探索实例图）

**Files:**
- Modify: `frontend/src/views/module_ai/ontology/index.vue`（对象探索面板加「时间轴」可折叠面板）
- Modify: `frontend/src/api/module_ai/ontology.ts`（`getTimelineProps` 已在 Task 7）
- Test: `type-check` + `eslint` + 无头验证

**Interfaces:**
- Consumes: `getTimelineProps(domain_code)`；实例图节点（`/instance/graph` 多步扩展）。
- Produces: 时间轴面板选时间属性 + 双滑块，图上淡化范围外实例节点。

- [ ] **Step 1: 在对象探索面板加时间轴 `el-card`**
- [ ] **Step 2: 下拉选时间属性**（`getTimelineProps(domain_code)`；空则显示「无可用于时间轴的属性」）+ `el-slider range` 双滑块选范围
- [ ] **Step 3: 图上淡化**：实例节点若其选中时间属性值不在 `[start, end]`，则加低透明度样式；复用现有节点样式机制，新增「时间过滤淡化集合」。时间值读取失败不做淡化、保持原样。
- [ ] **Step 4: 校验 + 无头验证**：选属性+滑块→实例节点按范围淡化
- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/module_ai/ontology/index.vue frontend/src/api/module_ai/ontology.ts
git commit -m "feat(ontology): 对象探索时间轴面板与滑块过滤"
```

---

### Task 9: 回归 + 文档更新

**Files:**
- Modify: `docs/ontology-gap-analysis.md`（P7 排期打勾 + 7.1 计数变动）
- Modify: `docs/superpowers/plans/2026-10-20-ontology-p0-ui-plan.md`（P7 引用）

**Interfaces:**
- 无（收尾）。

- [ ] **Step 1: 后端回归**：`uv run pytest tests/test_graph_view.py tests/test_object_view_index_proposal.py -q` 全绿；`tests/test_ontology*.py` 无回归。
- [ ] **Step 2: 前端回归**：`cd frontend && pnpm run type-check` 通过；本体相关测试不回归。
- [ ] **Step 3: 更新 `docs/ontology-gap-analysis.md`**：排期表 P7 打勾；`vertex` 计数 ✅4→✅6（或按实现调整）；7.1 计数表同步。
- [ ] **Step 4: Commit**

```bash
git add docs/ontology-gap-analysis.md docs/superpowers/plans/2026-10-20-ontology-p0-ui-plan.md
git commit -m "docs(ontology): P7 完成度与计数更新"
```
