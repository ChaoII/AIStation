# 本体血缘（第一步：表级）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让「改这张表会影响谁」能自动作答——用视图依赖 / 命名约定 / 使用情况 / 外键四种来源自动产生血缘，落库并接进影响分析与覆盖率接口。

**Architecture:** 新增 `query/lineage.py`（纯函数推断 + 落库重算），新表 `ai_query_lineage` 只读产出、不碰人工字段；`impact_analysis` 只增字段并由 `lineage_enabled` 开关控制；`sync_datasource_schema` 末尾幂等重算。

**Tech Stack:** FastAPI + SQLAlchemy(async) + sqlglot（已在依赖里）；插件表用 `CREATE TABLE IF NOT EXISTS`，不走 alembic。

**Spec:** `docs/superpowers/specs/2026-11-04-ontology-lineage-design.md`

## Global Constraints

- 所有代码注释、提交信息、文档一律**中文**；提交格式 `fix(ontology,query): 中文描述` / `feat(...)`。
- **不新增第三方依赖**（sqlglot 已存在）。
- 插件表用 `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`，**禁止 alembic autogenerate**。
- 问数代码**不得直连读 `ai_ont_*` 表**（`tests/test_ontology_query_bridge.py::test_query_reads_ontology_only_through_interface` 会扫源码断言）——本体敏感字段只能经 `ontology.semantic` 取。
- 任何新开关必须同时有：默认值表条目 + 设置弹窗入口 + 三语文案，否则不能合并。
- 单测默认 `PYTEST_NO_APP=1` 跑纯逻辑；需要应用的用例单独放，并接受 ~60s 固定成本。
- 血缘推断**宁缺勿错**：命名约定只收唯一匹配；解析失败跳过并计数，不抛。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `backend/app/plugin/module_ai/query/lineage.py`（新建） | `Edge` 定义、四种来源的纯函数推断、建表、重算、按表查询、覆盖率 |
| `backend/app/plugin/module_ai/query/service.py`（修改） | `sync_datasource_schema` 末尾挂钩子；`impact_analysis` 增加 `lineage` 字段 |
| `backend/app/plugin/module_ai/query/controller.py`（修改） | `POST /lineage/rebuild`、`GET /lineage/coverage` |
| `backend/tests/test_lineage.py`（新建） | 纯函数单测 + 重算/覆盖率集成 |
| `docs/superpowers/specs/2026-11-04-ontology-lineage-design.md`（修改） | 实现完成后把状态从"待评审"改成"已实现（第一步）" |

---

### Task 1: `Edge` 与命名约定推断

**Files:**
- Create: `backend/app/plugin/module_ai/query/lineage.py`
- Test: `backend/tests/test_lineage.py`

**Interfaces:**
- Produces:
  - `class Edge(NamedTuple)`：字段 `kind: str, src_table: str, src_column: str | None, dst_table: str | None, dst_column: str | None, ref_kind: str | None = None, ref_key: str | None = None, confidence: float = 1.0`
  - `infer_name_edges(columns_by_table: dict[str, set[str]]) -> list[Edge]`

- [ ] **Step 1: 写失败测试**

```python
def test_name_edges_only_unique_match():
    cols = {
        "FUEL_CMCS_INFACTORYBATCH": {"ID", "INFACTORYBATCHID", "MINENAME"},
        "FUEL_CMCS_ASSAY": {"ID", "INFACTORYBATCHID", "USERID"},
        "SYS_USER": {"ID"},
    }
    edges = infer_name_edges(cols)
    got = {(e.src_table, e.src_column, e.dst_table) for e in edges}
    # INFACTORYBATCHID 唯一匹配 FUEL_CMCS_INFACTORYBATCH
    assert ("FUEL_CMCS_ASSAY", "INFACTORYBATCHID", "FUEL_CMCS_INFACTORYBATCH") in got
    # USERID 无候选表（SYS_USER 不以 USER 结尾的唯一表）→ 不连
    assert all(e.src_column != "USERID" for e in edges)
    # 自身 ID 不连自己
    assert all(e.src_column != "ID" for e in edges)
    assert all(e.kind == "name" and e.confidence == 0.6 for e in edges)
    assert all(e.dst_column == "ID" for e in edges)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_lineage.py::test_name_edges_only_unique_match -q`
Expected: FAIL —— `ModuleNotFoundError: app.plugin.module_ai.query.lineage`

- [ ] **Step 3: 实现**

在 `lineage.py` 顶部写模块 docstring（说明四种来源与"宁缺勿错"），然后：

```python
class Edge(NamedTuple):
    kind: str
    src_table: str
    src_column: str | None
    dst_table: str | None
    dst_column: str | None
    ref_kind: str | None = None
    ref_key: str | None = None
    confidence: float = 1.0


def infer_name_edges(columns_by_table: dict[str, set[str]]) -> list[Edge]:
    """列 `XXXID` → 表名以 XXX 结尾。**只收唯一匹配**，多匹配一律丢弃。"""
```

实现要点：`c == "ID"` 跳过；`base = c[:-2].rstrip("_")`；候选表 `tn.endswith(base) and tn != base`；候选唯一才产出 `Edge("name", t, c, cand, "ID", confidence=0.6)`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/lineage.py backend/tests/test_lineage.py
git commit -m "feat(ontology): 血缘边定义 + 命名约定推断（只收唯一匹配）"
```

---

### Task 2: SQL 解析辅助（表 / 列）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/lineage.py`
- Test: `backend/tests/test_lineage.py`

**Interfaces:**
- Produces:
  - `tables_in_sql(sql: str) -> set[str]`（大写表名；解析失败返回空集）
  - `columns_used(sql: str, table: str, columns: set[str]) -> set[str]`（该 SQL 里出现过的该表列名，大写）

- [ ] **Step 1: 写失败测试**

```python
def test_tables_and_columns_from_sql():
    sql = (
        'SELECT "MINENAME", COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH" b '
        'JOIN "FUEL_CMCS_ASSAY" a ON a."INFACTORYBATCHID" = b."ID" '
        'WHERE b."ISDELETED" = false'
    )
    assert tables_in_sql(sql) == {"FUEL_CMCS_INFACTORYBATCH", "FUEL_CMCS_ASSAY"}
    cols = columns_used(sql, "FUEL_CMCS_INFACTORYBATCH", {"ID", "MINENAME", "ISDELETED", "REMARK"})
    assert cols == {"ID", "MINENAME", "ISDELETED"}

def test_bad_sql_returns_empty():
    assert tables_in_sql("this is not sql") == set()
    assert columns_used("this is not sql", "T", {"A"}) == set()
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -k sql -q`
Expected: FAIL —— `NameError: tables_in_sql is not defined`

- [ ] **Step 3: 实现**

`tables_in_sql`：`sqlglot.parse_one(sql, read="postgres")` + `find_all(exp.Table)`；任何异常返回 `set()`。
`columns_used`：先用 `re.compile(rf'\b{re.escape(c)}\b')` 在 `sql.upper()` 上匹配（第一步接受这种粗粒度；列级深度解析是第二步）。

- [ ] **Step 4: 运行确认通过**

Run: `PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(ontology): 血缘的 SQL 表/列解析辅助（解析失败返回空集）"
```

---

### Task 3: 建表 + 重算（四种来源，幂等）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/lineage.py`
- Test: `backend/tests/test_lineage.py`

**Interfaces:**
- Produces:
  - `async def ensure_lineage_table() -> None`（幂等建表与索引）
  - `async def rebuild_lineage(datasource_id: int) -> dict[str, int]`，返回 `{"fk": n, "view": n, "name": n, "usage": n, "total": n}`
- Consumes: `query.service._load_ds` / `_ds_cfg_from_model` / `_ds_code`；`query.executor.execute_select`；Task 1/2 的推断函数

- [ ] **Step 1: 写失败测试（集成，需要应用）**

```python
def test_rebuild_is_idempotent_and_has_edges(test_client):
    """跑两次条数一致；ds:4 表级覆盖 ≥ 50%（与只读探测一致）。"""
    from app.plugin.module_ai.query import lineage as L

    first = _run(L.rebuild_lineage(4))
    second = _run(L.rebuild_lineage(4))
    assert first["total"] > 500
    assert first == second                     # 幂等
    cov = _run(L.lineage_coverage("ds:4"))
    assert cov["tables_with_edges"] / cov["tables_total"] >= 0.5
```

（`_run` = 在应用事件循环里跑协程的小工具，参照 `tests/test_ontology_query_bridge.py` 的写法。）

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_lineage.py::test_rebuild_is_idempotent_and_has_edges -q`
Expected: FAIL —— `AttributeError: module ... has no attribute 'rebuild_lineage'`

- [ ] **Step 3: 实现**

- `ensure_lineage_table()`：执行 spec 第 3 节的 DDL（表 + 唯一索引 + 两个普通索引），全部 `IF NOT EXISTS`。
- `rebuild_lineage(ds_id)`：
  1. `ensure_lineage_table()`
  2. 读本地 `ai_query_schema` 得 `columns_by_table`（`columns` 是 JSONB 数组，元素是 `{"name": ...}`）
  3. 远端取外键（`information_schema.table_constraints`/`key_column_usage`/`constraint_column_usage`）与视图（`information_schema.views`）
  4. 生成四类边：`fk`（1.0）、`view`（0.9，视图与基表同名列）、`name`（Task 1）、`usage`（1.0，指标 `ai_query_metrics.sql_template` → `ref_kind="metric", ref_key=key`；报表 `ai_report_template.sql_template` → `report`；历史 `ai_query_messages.sql` → `ask, ref_key=id`）
  5. 一个事务里：`DELETE FROM ai_query_lineage WHERE datasource=:ds` → 批量 `INSERT`（按唯一索引去重：同一 `(kind, src, dst, ref)` 取最高 confidence）
  6. 失败只 `log.warning` 并返回已产出的计数，**不抛**

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -q`
Expected: PASS

- [ ] **Step 5: 真实库手工验证（写进命令输出，作为验收证据）**

Run:
```bash
PYTHONPATH=. ./.venv/Scripts/python.exe -c "import asyncio; from app.plugin.module_ai.query import lineage as L; print(asyncio.run(L.rebuild_lineage(4)))"
```
Expected: 形如 `{'fk': 16, 'view': 355, 'name': 246, 'usage': 73, 'total': 690}`，`total > 500`

- [ ] **Step 6: 提交**

```bash
git commit -am "feat(ontology): 血缘重算（fk/view/name/usage 四源 + 幂等落库）"
```

---

### Task 4: 按表查询 + 影响分析接入（开关默认关）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/lineage.py`
- Modify: `backend/app/plugin/module_ai/query/service.py`（`impact_analysis`）
- Test: `backend/tests/test_lineage.py`

**Interfaces:**
- Produces:
  - `EMPTY_LINEAGE: dict`（`{"upstream": [], "downstream": [], "used_by": [], "sensitive_columns": []}`，开关关闭时直接用同一个对象）
  - `async def lineage_for_table(datasource: str, table_name: str) -> dict`
    返回 `{"upstream": [{"table","kind","confidence"}], "downstream": [...], "used_by": [{"ref_kind","ref_key","kind"}], "sensitive_columns": [str]}`
- Consumes: `ontology.semantic.object_table_map()` / `sensitive_fields()`（**禁止直连 `ai_ont_*`**）

- [ ] **Step 1: 写失败测试**

```python
def test_impact_lineage_off_by_default(test_client):
    from app.plugin.module_ai.query.service import AiQueryService as S
    d = _run(S.impact_analysis("FUEL_CMCS_INFACTORYBATCH"))
    assert d["lineage"] == {"upstream": [], "downstream": [], "used_by": [], "sensitive_columns": []}
    assert "metrics" in d and "object_links" in d      # 旧字段不变

def test_lineage_for_table_has_downstream(test_client):
    from app.plugin.module_ai.query import lineage as L
    d = _run(L.lineage_for_table("ds:4", "FUEL_CMCS_INFACTORYBATCH"))
    assert isinstance(d["downstream"], list) and d["downstream"]
    assert all({"table", "kind", "confidence"} <= set(x) for x in d["downstream"])
```

- [ ] **Step 2: 运行确认失败**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -k lineage_for_table -q`
Expected: FAIL —— `AttributeError: lineage_for_table`

- [ ] **Step 3: 实现**

- `lineage_for_table`：按 `datasource` + `src_table` 查 `upstream`（`src_table=:t` 且 `dst_table IS NOT NULL` 的行，`dst` 作为上游）；按 `dst_table=:t` 查 `downstream`；按 `src_table=:t AND kind='usage'` 查 `used_by`；敏感列 = `ai_query_asset_columns.sensitive` ∪ 本体 `semantic.sensitive_fields()` 经 `object_table_map()` 关联。
- `impact_analysis` 末尾：
```python
ds_code = await cls._table_ds_code(table_name) or "ds:4"   # 已有静态方法，不新写推导
enabled = cls._cfg_bool(await cls._cfg(), "lineage_enabled", False)
result["lineage"] = (
    await lineage_for_table(ds_code, table_name.upper()) if enabled else EMPTY_LINEAGE
)
```
（`table_name` 归一化为大写；`_table_ds_code` 已存在于 `service.py`，返回 `"ds:4"` / `"system"` / `None`。）

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(ontology): 影响分析接入血缘（只增字段，lineage_enabled 默认关）"
```

---

### Task 5: 覆盖率 + 两个路由

**Files:**
- Modify: `backend/app/plugin/module_ai/query/lineage.py`
- Modify: `backend/app/plugin/module_ai/query/controller.py`
- Test: `backend/tests/test_lineage.py`

**Interfaces:**
- Produces:
  - `async def lineage_coverage(datasource: str) -> dict`，键：`tables_total, tables_with_edges, columns_total, columns_with_edges, by_kind`
  - `POST {prefix}/lineage/rebuild?datasource=ds:4` → `{"counts": {...}, "coverage": {...}}`
  - `GET {prefix}/lineage/coverage?datasource=ds:4` → 覆盖率

- [ ] **Step 1: 写失败测试**

```python
def test_coverage_shape(test_client):
    from app.plugin.module_ai.query import lineage as L
    c = _run(L.lineage_coverage("ds:4"))
    assert set(c) == {"tables_total", "tables_with_edges", "columns_total",
                      "columns_with_edges", "by_kind"}
    assert c["tables_total"] == 331
    assert c["columns_with_edges"] > 0

def test_routes_registered():
    from main import create_app
    paths = {getattr(r, "path", "") for r in create_app().routes}
    assert "/api/v1/ai/query/lineage/coverage" in paths
    assert "/api/v1/ai/query/lineage/rebuild" in paths
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -k coverage -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`lineage_coverage`：`tables_total/columns_total` 来自 `ai_query_schema`；`*_with_edges` 来自 `ai_query_lineage` 的 `distinct`；`by_kind` 按 `kind` 分组计数。
路由权限沿用资产同步那条（`module_ai:query:ask`）：
```python
@AiQueryRouter.post("/lineage/rebuild", summary="重算血缘")
async def lineage_rebuild(auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
                          datasource: str = "ds:4") -> JSONResponse:
```
⚠️ 路由必须注册在 `/assets/{table_name}` 这类带路径参数的**之前**，否则 `lineage` 会被当成 `{table_name}` 匹配掉（本项目踩过同类）。

- [ ] **Step 4: 运行确认通过**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_lineage.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(ontology): 血缘覆盖率接口 + 手动重算路由"
```

---

### Task 6: 同步钩子 + 开关入口 + 文案

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py`（`sync_datasource_schema` 与默认值表）
- Modify: `frontend/src/views/module_ai/query/index.vue`
- Modify: `frontend/src/lang/package/{zh-cn,zh-hant,en}/ai_logs.ts`
- Test: `backend/tests/test_query_settings_wiring.py`

**Interfaces:**
- Consumes: `lineage.rebuild_lineage`

- [ ] **Step 1: 写失败测试（守护"开关有入口且能设"）**

```python
def test_lineage_switch_declared_and_default_off():
    from app.plugin.module_ai.query.service import AiQueryService as S
    assert S._cfg_bool({}, "lineage_enabled", False) is False
    assert "lineage_enabled" in _default_keys(QUERY_DIR / "service.py")
```

- [ ] **Step 2: 运行确认失败**

Run: `PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_query_settings_wiring.py -k lineage -q`
Expected: FAIL —— 默认值表里没有该 key

- [ ] **Step 3: 实现**

1. 默认值表加 `"lineage_enabled": "false",`（注释写清：血缘已建但影响分析先不读，核对后再开）
2. `sync_datasource_schema` 末尾：
```python
    try:
        from .lineage import rebuild_lineage

        await rebuild_lineage(datasource_id)   # 血缘是增强，失败不能让同步失败
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 血缘重算失败（忽略）: {str(e)[:120]}")
```
3. 前端 `SETTING_DEFS` 加一条 `lineage_enabled`（bool），三语文案 `settingLineage` / `settingLineageTip`
4. 跑 `vue-tsc` 与 `eslint`

- [ ] **Step 4: 运行确认通过**

Run: `PYTEST_NO_APP=1 ./.venv/Scripts/python.exe -m pytest tests/test_query_settings_wiring.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(ontology): 同步后自动重算血缘 + lineage_enabled 开关入口"
```

---

### Task 7: 人工核对与收尾

**Files:**
- Modify: `docs/superpowers/specs/2026-11-04-ontology-lineage-design.md`（状态改"已实现（第一步）"，补实测数字）

- [ ] **Step 1: 核对三张表**

```bash
PYTHONPATH=. ./.venv/Scripts/python.exe -c "
import asyncio, json
from app.plugin.module_ai.query import lineage as L
for t in ('FUEL_CMCS_INFACTORYBATCH','FUEL_REPORT_DAYINOUTSTORAGE','DTXY_GYSKDGX'):
    print(t, json.dumps(asyncio.run(L.lineage_for_table('ds:4', t)), ensure_ascii=False)[:400])
"
```
人工判断：`downstream` / `used_by` 里出现的指标名是否确实是查这张表的；有误就修推断规则并重跑。

- [ ] **Step 2: 跑冒烟与相关测试**

```bash
PYTHONPATH=. ./.venv/Scripts/python.exe scripts/query_smoke.py --routing-only
./.venv/Scripts/python.exe -m pytest tests/test_lineage.py tests/test_query_settings_wiring.py tests/test_ontology_query_bridge.py -q
```
Expected: 全部通过；冒烟 exit=0

- [ ] **Step 3: 更新 spec 状态并提交**

```bash
git commit -am "docs(ontology): 血缘第一步已实现（覆盖率与核对结论）"
```

---

## Review Focus

这些是 spec 没有明说、但最容易咬人的输入/条件，每条都在对应任务里钉了测试：

1. **通用列名连错表**（`ID` / `USERID` / `CREATEDID`）→ Task 1 用"唯一匹配"挡住，并断言 `USERID` 不产生边。
2. **SQL 解析失败把整个重算打挂**（历史 3000 条里必有非标准 SQL）→ Task 2 断言返回空集、Task 3 要求失败只 warning。
3. **路由被 `{table_name}` 吃掉**（`/assets/{table_name}` 先注册会让 `/lineage/coverage` 404）→ Task 5 用实际 `app.routes` 断言两条路径都在。
4. **重复重算导致边翻倍**（没有唯一索引或先插后删）→ Task 3 断言两次结果相等。
5. **开关关着但接口变了**（影响分析旧消费方）→ Task 4 断言旧字段仍在、`lineage` 为空结构。
