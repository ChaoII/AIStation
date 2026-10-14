# 筛选规则工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把数据与集成页的「筛选规则」升级为可配置、可实时预览、可前后对比、可看概览、并支持大模型辅助的筛选规则工作台。

**Architecture:** 后端 `filtering.py` 增加返回「命中原因」的 `classify_tables/classify_fields`（唯一权威）；新增确定性 `rules/preview` 接口计算任意草稿规则的全量分类与汇总，另加三个走 agno 的大模型接口（生成候选规则 / 自然语言转规则 / 逐表逐字段建议）。前端新增独立 `FilterRulesWorkbench.vue` 组件，作为集成页「筛选规则」tab，内部用 `el-tabs` 分区（配置/预览/对比/概览/大模型辅助）。

**Tech Stack:** Python FastAPI + SQLAlchemy（后端，agno 调用大模型）、Vue 3 + Vite + Element Plus + echarts/vue-echarts（前端）。

**Spec:** `docs/superpowers/specs/2026-10-14-filter-rules-workbench-design.md`

## Global Constraints

- 大模型调用**必须走 agno**（平台建立在 agno 之上），复用 query 模块既有链路：`AiQueryService._get_runtime()`（`AiModelService.get_runtime_model`）+ `agno.models.openai.like.OpenAILike` + `app.plugin.module_ai.models.service.build_headers`；并在 agno **之外**用 `asyncio.wait_for` 兜底超时（对齐 `_nl2sql` 的 `nl2sql_call_timeout` 实践）。
- 回复/注释/提交信息一律中文；文档正文中文。
- 前端一律用 Element Plus 原生组件与 `--el-*` 变量，禁止自创主题/自定义字号；对齐既有页面。
- 删除类操作必须二次确认（本设计涉及「应用规则覆盖」，需确认）。
- 后端测试遵循效率约定：纯逻辑用 `PYTEST_NO_APP=1` 快速模式；涉及 app 用 `test_client`/`auth_headers` fixture。
- 字段名约定：schema 列字段名为 `name`（`list_ds_schema` 的 column 用 `c["name"]`），asset 列用 `column_name`；两者都要兼容读取。
- `filter_rules` 结构不变（`enabled` + `system_table{prefixes,keywords,exact,regex}` + `audit_fields`），向后兼容。

## Review Focus

1. **规则 `enabled=False`**：应全部放行（无表判系统、无字段判审计），且 `summary` 计数为 0。
2. **大小写不敏感**：`SYS_USER` 与 `sys_user` 判定一致，审计字段 `CREATIONTIME`/`creationtime` 均命中。
3. **非法正则**：`system_table.regex` 为非法表达式时不应抛异常，跳过该项而非导致预览失败。
4. **草稿规则未应用时**：`preview` 传入草稿规则，不影响数据源已保存规则；对比时「已保存 vs 草稿」分类正确翻转。
5. **大模型载荷**：几百表/字段样本注入 prompt 时需截断（如各 400 条样本），超时/异常返回可读错误而非 500。

---

## Phase 1 —— 确定性：规则引擎 + 预览 + 工作台（配置/预览/对比/概览）

### Task 1: 规则引擎 `classify_tables` / `classify_fields`（含命中原因）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/filtering.py`
- Modify: `backend/tests/test_query_filtering.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `classify_tables(tables: list[str], rules: dict | None = None) -> list[dict]`，每项 `{"name": str, "is_system": bool, "reason": str}`。
  - `classify_fields(fields: list[str], rules: dict | None = None) -> list[dict]`，每项 `{"name": str, "is_audit": bool, "reason": str}`。
  - `reason` 取值形如 `前缀 SYS_` / `关键词 _BAK` / `精确表名 alembic_version` / `正则 ^TMP_` / `审计字段 created_time`；未命中 `reason=""`。
  - 既有 `is_system_table`/`is_audit_field` 行为不变（可由 classify 复用）。

- [ ] **Step 1: Write failing tests** in `backend/tests/test_query_filtering.py`

```python
from app.plugin.module_ai.query.filtering import classify_tables, classify_fields

def test_classify_tables_prefix_reason():
    r = classify_tables(["SYS_USER", "video_cameras"])
    assert r[0]["is_system"] is True and r[0]["reason"] == "前缀 SYS_"
    assert r[1]["is_system"] is False and r[1]["reason"] == ""

def test_classify_tables_keyword_exact_regex():
    r = classify_tables(["T_A_BAK", "alembic_version", "TMP_X"])
    rules = {"enabled": True, "system_table": {"prefixes": [], "keywords": ["_BAK"],
             "exact": ["alembic_version"], "regex": "^TMP_"}, "audit_fields": []}
    r2 = classify_tables(["T_A_BAK", "alembic_version", "TMP_X", "ok"], rules)
    assert r2[0]["reason"] == "关键词 _BAK"
    assert r2[1]["reason"] == "精确表名 alembic_version"
    assert r2[2]["reason"] == "正则 ^TMP_"
    assert r2[3]["is_system"] is False

def test_classify_disabled_passes_all():
    rules = {"enabled": False, "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": ""}, "audit_fields": []}
    assert classify_tables(["SYS_USER"], rules)[0]["is_system"] is False

def test_classify_case_insensitive_and_bad_regex():
    rules = {"enabled": True, "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": "["}, "audit_fields": []}
    assert classify_tables(["sys_user"], rules)[0]["is_system"] is True  # 命中前缀
    assert classify_tables(["sys_user_bak_x"], rules)[0]["is_system"] is True  # 非法正则被跳过不抛异常

def test_classify_fields_reason():
    r = classify_fields(["created_time", "coal_amount"])
    assert r[0]["is_audit"] is True and r[0]["reason"] == "审计字段 created_time"
    assert r[1]["is_audit"] is False and r[1]["reason"] == ""
```

- [ ] **Step 2: Run to verify fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_query_filtering.py -q`
Expected: FAIL（`ImportError: cannot import name 'classify_tables'`）

- [ ] **Step 3: Implement `classify_tables` / `classify_fields` in `backend/app/plugin/module_ai/query/filtering.py`**

主逻辑复用 `_norm` 大小写不敏感；命中优先级：enabled→prefix→keyword→exact→regex。`classify_tables` 对每个表名调用内部单表判定并拼 reason；`classify_fields` 对每个字段名在 `audit_fields` 里做大小写不敏感精确匹配拼 reason（命中第一个即返回）。`is_system_table`/`is_audit_field` 保留原签名（内部可调用 classify 或保持原实现）。

- [ ] **Step 4: Run to verify pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_query_filtering.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_ai/query/filtering.py backend/tests/test_query_filtering.py
git commit -m "feat(query): 规则引擎支持命中原因分类 classify_tables/classify_fields"
```

### Task 2: `preview_filter_rules` 服务方法 + `rules/preview` 接口

**Files:**
- Modify: `backend/app/plugin/module_ai/query/schema.py`（新增 `FilterRulesPreviewRequest`）
- Modify: `backend/app/plugin/module_ai/query/service.py`（新增 `preview_filter_rules`）
- Modify: `backend/app/plugin/module_ai/query/controller.py`（新增路由）
- Create: `backend/tests/test_filter_rules_preview.py`

**Interfaces:**
- Consumes: `classify_tables`/`classify_fields`（Task 1）、`list_ds_schema`、`_load_ds`、`DEFAULT_FILTER_RULES`
- Produces:
  - `FilterRulesPreviewRequest(BaseModel)`: `rules: dict | None = None`
  - `AiQueryService.preview_filter_rules(datasource_id: int, rules: dict | None = None) -> dict`，返回 `{"tables": list[dict], "fields": list[dict], "summary": dict}`。
  - `summary`：`{"table_total","system_tables","business_tables","field_total","audit_fields","business_fields"}`。

- [ ] **Step 1: Write failing test** in `backend/tests/test_filter_rules_preview.py`（monkeypatch `list_ds_schema`，不依赖真实同步）

```python
from app.plugin.module_ai.query.service import AiQueryService

def test_preview_filter_rules_summary(monkeypatch):
    async def fake_load(datasource_id):
        class D: pass
        d = D(); d.filter_rules = None
        return d
    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)
    async def fake_schema(datasource_id, included_only=False):
        return [
            {"table": "SYS_USER", "comment": "", "columns": [{"name": "CREATIONTIME"}, {"name": "coal_amount"}]},
            {"table": "video_cameras", "comment": "", "columns": [{"name": "created_time"}]},
        ]
    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    import asyncio
    out = asyncio.run(AiQueryService.preview_filter_rules(4, rules=None))
    assert out["summary"]["table_total"] == 2
    assert out["summary"]["system_tables"] == 1
    assert out["summary"]["business_tables"] == 1
    assert out["summary"]["audit_fields"] == 2  # CREATIONTIME + created_time
    assert out["tables"][0]["reason"] == "前缀 SYS_"
```

- [ ] **Step 2: Run to verify fail**

Run: `PYTEST_NO_APP=1 backend\.venv\Scripts\python.exe -m pytest backend/tests/test_filter_rules_preview.py -q`
Expected: FAIL（`preview_filter_rules` 不存在）

- [ ] **Step 3: Implement `preview_filter_rules` in `service.py`**

```python
@classmethod
async def preview_filter_rules(cls, datasource_id: int, rules: dict | None = None) -> dict:
    ds = await _load_ds(datasource_id)                      # 不存在则抛 CustomException
    eff = rules or ds.filter_rules or DEFAULT_FILTER_RULES
    schema = await list_ds_schema(datasource_id)
    tables = [s["table"] for s in schema]
    fields = []
    for s in schema:
        for c in s.get("columns") or []:
            fields.append(c.get("name") or c.get("column_name"))
    t = classify_tables(tables, eff)
    f = classify_fields(fields, eff)
    summary = {
        "table_total": len(t),
        "system_tables": sum(1 for x in t if x["is_system"]),
        "business_tables": sum(1 for x in t if not x["is_system"]),
        "field_total": len(f),
        "audit_fields": sum(1 for x in f if x["is_audit"]),
        "business_fields": sum(1 for x in f if not x["is_audit"]),
    }
    return {"tables": t, "fields": f, "summary": summary}
```

- [ ] **Step 4: Add schema + controller route**

`schema.py`:
```python
class FilterRulesPreviewRequest(BaseModel):
    rules: dict | None = None
```
`controller.py`:
```python
@AiQueryRouter.post("/datasources/{datasource_id}/rules/preview", summary="筛选规则分类预览")
async def rules_preview(datasource_id: int, data: FilterRulesPreviewRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.preview_filter_rules(datasource_id, data.rules), msg="查询成功")
```

- [ ] **Step 5: Run to verify pass**

Run: `PYTEST_NO_APP=1 backend\.venv\Scripts\python.exe -m pytest backend/tests/test_filter_rules_preview.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugin/module_ai/query/schema.py backend/app/plugin/module_ai/query/service.py backend/app/plugin/module_ai/query/controller.py backend/tests/test_filter_rules_preview.py
git commit -m "feat(query): 新增筛选规则分类预览接口 rules/preview"
```

### Task 3: 前端筛选规则预览 API

**Files:**
- Modify: `frontend/src/api/module_ai/query.ts`

**Interfaces:**
- Consumes: 无
- Produces: `previewFilterRules(datasource_id: number, rules?: any) -> request(...)`（POST `.../datasources/${id}/rules/preview`）

- [ ] **Step 1: Add `previewFilterRules` in `query.ts`**（按既有 `request` 封装）

```ts
export function previewFilterRules(datasource_id: number, rules?: any) {
  return request({ url: `${API_PATH}/datasources/${datasource_id}/rules/preview`, method: "post", data: { rules } });
}
```

- [ ] **Step 2: Verify type-check**

Run: `pnpm run type-check`
Expected: 该文件无新增错误（项目现有其它文件报错可忽略）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/module_ai/query.ts
git commit -m "feat(ai-integration): 新增筛选规则预览接口调用"
```

### Task 4: 前端筛选规则工作台组件 + 集成页挂 tab

**Files:**
- Create: `frontend/src/views/module_ai/integration/components/FilterRulesWorkbench.vue`
- Modify: `frontend/src/views/module_ai/integration/index.vue`（`el-tabs` 增加 `name="rules"` 的 tab-pane，并渲染 `<FilterRulesWorkbench>`）

**Interfaces:**
- Consumes: `previewFilterRules`（Task 3）、`getDatasourceDetail`（取已保存规则）、`saveQueryDatasource`（保存草稿/应用）
- Produces: 组件 props：`datasource`（当前选中数据源对象，含 `id/name/name`）；组件内对外无返回值。
  - 内部状态：`rules`（草稿，ref）、`preview`（ref）、`savedRules`（ref，来自详情）。

- [ ] **Step 1: 创建组件骨架（四个分区 + el-tabs）** in `FilterRulesWorkbench.vue`
  - `el-tabs` 分区：`规则配置` / `实时预览` / `前后对比` / `概览`。
  - 监听 `props.datasource` 变化：`getDatasourceDetail(id)` 取 `savedRules` 初始化 `rules`，并调 `previewFilterRules(id, rules)`。
  - 规则改动（配置区任意 `@change`）触发 `refreshPreview()`：`previewFilterRules(id, rules)`。
  - 使用 Element Plus 组件与 `--el-*` 变量；尺寸 `small`。

- [ ] **Step 2: 实现「规则配置」区**
  - 启用开关、系统表前缀/关键词/精确表名（`el-select multiple filterable allow-create`）、表名正则（`el-input`）、审计字段（`el-select multiple filterable allow-create`）。
  - 顶部展示命中摘要（系统表/业务表/审计字段计数，来自 `preview.summary`）。
  - 底部「保存草稿」（`saveQueryDatasource` 带 `filter_rules=rules`，需确认）与「保存并应用」（保存后调用 `syncQueryDatasourceSchema` 重新打标）。

- [ ] **Step 3: 实现「实时预览」区**
  - 表清单（`el-table`）：表名 / 系统·业务（`el-tag`）/ 命中规则（`show-overflow-tooltip` 文本）。
  - 字段清单（`el-table`）：字段名 / 审计·业务（`el-tag`）/ 命中规则。
  - 由 `preview.tables/fields` 驱动，规则一改即刷新。

- [ ] **Step 4: 实现「前后对比」区**
  - 调 `previewFilterRules(id, savedRules)` 得「已保存」分类，与 `preview`（草稿）求差集。
  - 分组展示翻转：`表 X：业务→系统（命中 前缀 SYS_）`、`字段 Y：业务→审计`；无差异提示一致。

- [ ] **Step 5: 实现「概览」区**
  - 用 `vue-echarts`（`echarts`）画两个环形图：系统 vs 业务表数、审计 vs 业务字段数（取 `preview.summary`）。

- [ ] **Step 6: 集成页挂 tab**
  - `index.vue` 在 `el-tabs` 内、`表与字段` tab-pane 之后新增：
    ```html
    <el-tab-pane label="筛选规则" name="rules">
      <FilterRulesWorkbench v-if="curDs" :datasource="curDs" />
    </el-tab-pane>
    ```
  - `import FilterRulesWorkbench from "./components/FilterRulesWorkbench.vue";`

- [ ] **Step 7: Verify**

Run: `pnpm run type-check`
Expected: 集成页与组件无类型错误；`pnpm run lint` 无新增错误。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/module_ai/integration/components/FilterRulesWorkbench.vue frontend/src/views/module_ai/integration/index.vue
git commit -m "feat(ai-integration): 筛选规则工作台(配置/预览/对比/概览)并接入集成页tab"
```

### Task 5: 首期端到端自测（燃煤业务库）

**Files:** 无新增（验证任务）
**Interfaces:** 复用 Task 1-4 产物

- [ ] **Step 1: 后端运行**（`backend\.venv\Scripts\python.exe main.py run --env=dev`，端口 8002），前端 Vite（5181）
- [ ] **Step 2: 集成页选中「燃煤业务库」→ 切到「筛选规则」tab**，验证：
  - 实时预览显示系统/业务表、字段审计/业务及命中规则；
  - 概览图正确；
  - 修改规则（去掉 `FUEL_` 前缀）→ 预览即时变化；
  - 前后对比列出翻转项；
  - 截图供多模态自检风格一致性。
- [ ] **Step 3: Commit（如有修复）**

---

## Phase 2 —— 大模型辅助

### Task 6: 后端大模型接口（suggest / parse / classify-advise）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/schema.py`（新增 `FilterRulesSuggestRequest` / `FilterRulesParseRequest` / `FilterRulesAdviseRequest`）
- Modify: `backend/app/plugin/module_ai/query/service.py`（新增 `_llm_json` 辅助 + `suggest_filter_rules`/`parse_filter_rules`/`classify_advise`）
- Modify: `backend/app/plugin/module_ai/query/controller.py`（新增 3 路由）
- Create: `backend/tests/test_filter_rules_llm.py`

**Interfaces:**
- Consumes: `_get_runtime()`、`build_headers`、`OpenAILike`、`Agent`、`list_ds_schema`（样本）、`DEFAULT_FILTER_RULES`
- Produces:
  - `_llm_json(cls, prompt: str, temperature: float = 0.2) -> str`：构建模型并 `agent.arun`，`asyncio.wait_for` 兜底 `_cfg_int(cfg, "nl2sql_call_timeout", 90)`，返回 `resp.content`；异常抛 `CustomException(msg="大模型辅助调用失败：...")`。
  - `suggest_filter_rules(cls, datasource_id, rules=None) -> dict`：返回 `{"rules": {...}, "note": str}`。
  - `parse_filter_rules(cls, datasource_id, text: str) -> dict`：返回 `{"rules": {...}}`。
  - `classify_advise(cls, datasource_id, rules=None) -> dict`：返回 `{"system_suggest": [{name, reason}], "audit_suggest": [{name, reason}]}`。

- [ ] **Step 1: Write a unit test that mocks `_llm_json` to return a fixed JSON**，验证三个服务方法能解析并返回预期结构

```python
import asyncio
from app.plugin.module_ai.query.service import AiQueryService

def test_parse_filter_rules_extracts(monkeypatch):
    async def fake_llm(prompt, temperature=0.2):
        return '{"rules": {"enabled": true, "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": ""}, "audit_fields": ["created_time"]}}'
    monkeypatch.setattr(AiQueryService, "_llm_json", classmethod(lambda cls, p, temperature=0.2: fake_llm(p, temperature)))
    out = asyncio.run(AiQueryService.parse_filter_rules(4, "把 SYS_ 当系统表，created_time 当审计"))
    assert out["rules"]["system_table"]["prefixes"] == ["SYS_"]
```

- [ ] **Step 2: Run to verify fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_filter_rules_llm.py -q`
Expected: FAIL

- [ ] **Step 3: Implement `_llm_json` + 三个方法 in `service.py`**
  - `_llm_json`：`runtime = await cls._get_runtime()`；`model = OpenAILike(id=..., base_url=..., api_key=..., temperature=..., max_tokens=4000, timeout=60, extra_body={"reasoning_effort": "low"} or None, default_headers=build_headers(runtime["base_url"], runtime.get("extra_headers"), "aistation-query"))`；`agent = Agent(model=model, telemetry=False, instructions=...)`；`await asyncio.wait_for(agent.arun(prompt), timeout=...)`。
  - `suggest_filter_rules`：取表名/字段名样本（各截断 400），prompt 要求输出 JSON `{"rules": {...}}`；提示按命名规律归纳前缀/关键词/审计字段，且必须包含 `system_table`（prefixes/keywords/exact/regex）与 `audit_fields`。
  - `parse_filter_rules`：`{"text": ...}` → JSON `{"rules": {...}}`。
  - `classify_advise`：样本 + 规则 → JSON `{"system_suggest": [...], "audit_suggest": [...]}`。
  - 统一做 JSON 抽取（`_extract_json(str)`，容错代码块```json```包裹）。

- [ ] **Step 4: Add request models + 3 routes in `schema.py` / `controller.py`**

```python
class FilterRulesSuggestRequest(BaseModel):
    rules: dict | None = None
class FilterRulesParseRequest(BaseModel):
    text: str
class FilterRulesAdviseRequest(BaseModel):
    rules: dict | None = None
```
控制器三条：`POST /datasources/{id}/rules/suggest`、`/rules/parse`、`/rules/classify-advise`，均 `Depends(AuthPermission(["module_ai:query:ask"]))` 且包 `SuccessResponse`。

- [ ] **Step 5: Run to verify pass**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_filter_rules_llm.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/plugin/module_ai/query/schema.py backend/app/plugin/module_ai/query/service.py backend/app/plugin/module_ai/query/controller.py backend/tests/test_filter_rules_llm.py
git commit -m "feat(query): 大模型辅助筛选规则接口(suggest/parse/classify-advise)"
```

### Task 7: 前端大模型辅助 UI

**Files:**
- Modify: `frontend/src/views/module_ai/integration/components/FilterRulesWorkbench.vue`
- Modify: `frontend/src/api/module_ai/query.ts`（新增 `suggestFilterRules`/`parseFilterRules`/`classifyAdvise`）

**Interfaces:**
- Consumes: Task 6 接口；Task 4 组件状态 `rules`
- Produces: 无对外新接口

- [ ] **Step 1: 新增三个 API 函数 in `query.ts`**（GET 用 POST，`{ rules }` / `{ text }` 体）
- [ ] **Step 2: 组件加「大模型辅助」tab**
  - 三个按钮/输入：生成候选规则（`suggest`）、自然语言配置（文本输入 + `parse`）、逐表逐字段建议（`classify-advise`）。
  - 结果展示（`el-card`/`el-table`），提供「应用到草稿」按钮（把返回 `rules` 写入 `rules` 并刷新预览）。加载态用 `v-loading`。
- [ ] **Step 3: Verify**

Run: `pnpm run type-check`
Expected: 无新增错误。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/module_ai/query.ts frontend/src/views/module_ai/integration/components/FilterRulesWorkbench.vue
git commit -m "feat(ai-integration): 筛选规则工作台大模型辅助分区"
```

### Task 8: 全流程评审与修复

**Files:** 视评审结果
**Interfaces:** 无

- [ ] **Step 1: 用 284B 评审** Review Task 1-7 全部分支（重点：分类翻转对比、`enabled=False`、大小写、非法正则、大模型 JSON 容错、前端风格一致性）。
- [ ] **Step 2: 端到端**（燃煤业务库）：预览命中说明 → 去掉 `FUEL_` → 对比翻转 → 概览 → 大模型生成/自然语言/建议 → 应用 → 保存 → 同步 → `is_system` 变化。
- [ ] **Step 3: 修复评审/验证发现的问题并提交**
