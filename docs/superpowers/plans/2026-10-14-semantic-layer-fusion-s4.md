# 语义层融合 · S4（三处 UI + 燃煤业务评测集）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让「大模型自动建模」（S3）与「指标进对象查询」（S2）可被**使用与验收**：① 后端暴露建模 API；② 评测模块支持**按数据集运行**并生成「燃煤业务语义执行层评测集」；③ 三处前端可触发/展示（数据与集成语义建模面板、本体指标页签、问数展示指标名）。

**Architecture:** 后端在 `query/controller.py` 暴露 `modeling` 端点（复用 S3 的 `generate_metrics/generate_annotations/collect_objects`）；`eval_runner._run_once` 补 `dataset` 过滤；`eval_generate` 补 `dataset` 落库；脚本生成燃煤评测集。前端复用既有 `el-tabs`/`el-card`/`el-table` 组件，遵循项目风格（不自定义配色）。

**Tech Stack:** FastAPI + SQLAlchemy async；Vue 3 + Element Plus（`request` 封装、`useCrudList`）；pytest。

**Spec:** `docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md`（§5、§6）

## Global Constraints

- 回复/注释/文档一律**中文**；提交信息 `feat(query): 中文描述`。
- 前端**必须与既有模块风格一致**（参考 `module_system/param`）：直接用 `el-card/el-tabs/el-table/el-form/el-tag/el-button` 与 `--el-*` 变量，**禁止自造主题化外壳/自定义配色**。
- 删除/覆盖类操作必须二次确认（`ElMessageBox.confirm`）。
- LLM 一律走 agno（S3 已实现，S4 只调用）。
- 建模 API 是**写操作**，必须带权限校验（`Depends(AuthPermission([...]))`）。
- 测试库是 SQLite：`asyncio.run` 包普通 `def test_*`。

## Review Focus

1. **建模 API 的权限**：触发建模会写指标/对象，必须校验权限，且缓存失效（`_SETTINGS_CACHE`/schema 缓存）——否则前端看不到刚生成的指标。
2. **评测按数据集隔离**：`dataset` 过滤必须在 `list_cases` 与 `_run_once` 都生效；空数据集应给出明确提示而非静默 0 题。
3. **前端不改全局样式**：新增标签页/页签只用 Element Plus 组件，避免触碰 `app-container` 的 flex 布局（历史踩坑）。
4. **问数展示指示**：`metric` 为空时不得渲染空标签；对象/慢路径的行为不变。
5. **幂等**：重复触发建模不得产生重复指标（`upsert_metric` 按 key）。

---

### Task 1: 后端建模 API（触发自动建模）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/controller.py`（新增 modeling 端点）
- Modify: `backend/app/plugin/module_ai/query/service.py`（新增 `AiQueryService.generate_modeling` 包装，便于测试与缓存失效）
- Test: `backend/tests/test_query_modeling_api.py`（新建）

**Interfaces:**
- Consumes: `modeling.collect_objects(datasource, max_objects)`、`modeling.generate_metrics(datasource, auth, max_objects, dry)`、`modeling.generate_annotations(datasource, auth, max_objects)`
- Produces（控制器路径，容器前缀 `/ai/query`）：
  - `GET /ai/query/modeling/objects?datasource=ds:4` → `{objects: [...]}`
  - `POST /ai/query/modeling/metrics` body `{datasource, max_objects?, dry?}` → `{parsed, verified, saved, rejected, reasons}`
  - `POST /ai/query/modeling/annotate` body `{datasource, max_objects?}` → `{parsed, saved}`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_modeling_api.py
import asyncio


def test_generate_modeling_metrics_invalidates_cache(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.query import service as S

        async def _fake_gen(datasource, auth, max_objects=12, dry=False):
            return {"parsed": 2, "verified": 1, "saved": 1, "rejected": 1, "reasons": []}

        monkeypatch.setattr(M, "generate_metrics", _fake_gen)
        S._SETTINGS_CACHE = {"x": 1}
        out = await S.AiQueryService.generate_modeling("metrics", "ds:4", _auth())
        return out, S._SETTINGS_CACHE

    out, cache = asyncio.run(_go())
    assert out["saved"] == 1
    assert cache is None          # 生成后必须失效缓存，前端才能看到新指标


def _auth():
    from types import SimpleNamespace
    return SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_modeling_api.py -q`
Expected: FAIL（`AiQueryService.generate_modeling` 未定义）

- [ ] **Step 3: 实现**

- `service.py`：`AiQueryService.generate_modeling(kind, datasource, auth, max_objects=12, dry=False)`——`kind in ("metrics","annotate")` 分派到 `modeling.generate_metrics`/`generate_annotations`；**结束后置** `global _SETTINGS_CACHE, _SEMANTIC_INDEX, _ASSET_TMETA` 为 `None`（新指标/标注要立刻可见）。
- `controller.py`：新增 3 个端点（`GET /modeling/objects`、`POST /modeling/metrics`、`POST /modeling/annotate`），均 `Depends(AuthPermission(["module_ai:query:metric"]))`（复用既有指标权限串，若不存在则在文件顶部按同构命名）。入参用 `QueryModelingUpsert`（`datasource: str`、`max_objects: int = 12`、`dry: bool = False`，加在 `schema.py`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_modeling_api.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/controller.py backend/app/plugin/module_ai/query/service.py backend/app/plugin/module_ai/query/schema.py backend/tests/test_query_modeling_api.py
git commit -m "feat(query): 自动建模 API（指标/标注）"
```

---

### Task 2: 评测按 `dataset` 过滤 + 生成「燃煤业务语义执行层评测集」

**Files:**
- Modify: `backend/app/plugin/module_ai/query/eval_runner.py`（`_run_once` :150-160 加 `dataset`）
- Modify: `backend/app/plugin/module_ai/query/eval_generate.py`（`verify_and_save`/`generate_round` 增 `dataset` 透传）
- Create: `backend/scripts/_gen_coal_eval.py`
- Test: `backend/tests/test_query_eval_dataset.py`（新建）

**Interfaces:**
- Consumes: `eval_set.list_cases(dataset=...)`（S1 已有）、`eval_generate.generate_round`
- Produces:
  - `_run_once` 按 `flt["dataset"]` 过滤
  - `generate_round(..., dataset="")` / `verify_and_save(..., dataset="")`
  - 数据集名：`coal_semantic_v1`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_eval_dataset.py
import asyncio


def test_run_once_filters_by_dataset(monkeypatch):
    """_run_once 必须把 filter 里的 dataset 传给 list_cases。"""
    async def _go():
        from app.plugin.module_ai.query import eval_runner as R
        from app.plugin.module_ai.query import eval_set as es

        seen = {}

        async def _fake_list(**kw):
            seen.update(kw)
            return []

        monkeypatch.setattr(es, "list_cases", _fake_list)
        # 直接调用内部取题逻辑：用 start_run 会起后台任务，这里只验证过滤透传
        await R._pick_cases({"dataset": "coal_semantic_v1"}, None)
        return seen

    seen = asyncio.run(_go())
    assert seen.get("dataset") == "coal_semantic_v1"
```

> 若 `_run_once` 的取题逻辑不便抽出，则改为**新增** `_pick_cases(flt)` 纯函数（从 `_run_once` 抽出 `list_cases(...)` 调用 + dataset/limit/split 过滤），测试它。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_eval_dataset.py -q`
Expected: FAIL（`_pick_cases` 未定义）

- [ ] **Step 3: 实现**

- `eval_runner.py`：抽出 `async def _pick_cases(flt: dict, datasource_override: str | None) -> list[dict]`（含 `dataset`/`limit`/`split` 过滤），`_run_once` 改调它。
- `eval_generate.py`：`verify_and_save(cases, datasource, auth, generation_only=False, dataset="")` → `upsert_case({..., "dataset": dataset})`；`generate_round(..., dataset="")` 透传。
- `scripts/_gen_coal_eval.py`：对 `ds:4` 跑 `generate_round(..., dataset="coal_semantic_v1")` 若干轮（如 3 轮 × 10 题），打印收录统计。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_eval_dataset.py tests/test_query_eval.py -q`
Expected: PASS（新测试 + 既有评测测试不回归）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/eval_runner.py backend/app/plugin/module_ai/query/eval_generate.py backend/scripts/_gen_coal_eval.py backend/tests/test_query_eval_dataset.py
git commit -m "feat(query): 评测按数据集运行 + 生成燃煤评测集脚本"
```

---

### Task 3: 前端 API 函数（建模 + 指标列表）

**Files:**
- Modify: `frontend/src/api/module_ai/query.ts`
- Test: 无自动测试（类型检查 `pnpm run type-check`）

**Interfaces:**
- Produces: `getModelingObjects(datasource)`、`runModelingMetrics({datasource,max_objects?,dry?})`、`runModelingAnnotate({datasource,max_objects?})`（均走 `request`，长超时 120000）

- [ ] **Step 1: 实现**

在 `query.ts` 末尾按既有风格追加：
```ts
export function getModelingObjects(datasource: string) {
  return request({ url: `${API_PATH}/modeling/objects`, method: "get", params: { datasource }, timeout: 30000 });
}
export function runModelingMetrics(data: { datasource: string; max_objects?: number; dry?: boolean }) {
  return request({ url: `${API_PATH}/modeling/metrics`, method: "post", data, timeout: 180000 });
}
export function runModelingAnnotate(data: { datasource: string; max_objects?: number }) {
  return request({ url: `${API_PATH}/modeling/annotate`, method: "post", data, timeout: 180000 });
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 无新增错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/module_ai/query.ts
git commit -m "feat(query-ui): 建模 API 封装"
```

---

### Task 4: 前端「数据与集成」语义建模面板

**Files:**
- Modify: `frontend/src/views/module_ai/integration/index.vue`（在 `el-tabs` 内新增「语义建模」`el-tab-pane`）

**Interfaces:**
- Consumes: Task 3 的 API、`el-card/el-form/el-select/el-button/el-alert/el-table`

- [ ] **Step 1: 实现**

在集成页 `el-tabs` 内新增 `<el-tab-pane label="语义建模" name="modeling">`：
- `el-form`（inline）：数据源 `el-select`（复用页面已有的数据源列表 ref）+ `max_objects` `el-input-number` + 「一键生成指标」「生成标注」按钮（带 `:loading`）。
- 结果用 `el-alert` 展示 `解析/通过/拒绝`；拒绝原因用 `el-table`（列：指标 key、原因）。
- 生成**写操作**：按钮点击前 `ElMessageBox.confirm("将写入指标/标注，是否继续？")`；成功后 `ElMessage.success` + `refreshList()` 刷新指标标签页。
- 样式只用 `--el-*`，不写死字号/颜色。

- [ ] **Step 2: 类型检查 + lint**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
Expected: 无新增错误（既有 `LivePlayer.vue` 等历史 lint 错误不计）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/module_ai/integration/index.vue
git commit -m "feat(query-ui): 数据与集成新增语义建模面板"
```

---

### Task 5: 前端「本体」指标页签 + 问数展示指标名

**Files:**
- Modify: `frontend/src/views/module_ai/ontology/components/OntObjectTypeView.vue`（`TABS` :721 增「指标」页签）
- Modify: `frontend/src/views/module_ai/query/index.vue`（消息区展示 `metric` 名称）

**Interfaces:**
- Consumes: `getQueryMetrics(datasource)`（既有）、消息对象的 `metric` 字段（后端 `_answer` 已返回）

- [ ] **Step 1: 实现（本体指标页签）**

`OntObjectTypeView.vue`：`TABS` 增 `{ label: "指标", name: "metric" }`；页签内容为 `el-table`，数据 = `getQueryMetrics("ds:{datasource_id}")` 里 `object_code === 当前对象 code` 的项（列：中文名/ key / 聚合 / 维度）。空时 `el-empty`。

- [ ] **Step 2: 实现（问数展示指标名）**

`query/index.vue`：消息渲染处，当 `m.metric?.name` 存在时，在路径标签旁加一个 `el-tag`（`type="success"`）显示指标名；`metric` 为空不渲染。

- [ ] **Step 3: 类型检查 + lint**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
Expected: 无新增错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/module_ai/ontology/components/OntObjectTypeView.vue frontend/src/views/module_ai/query/index.vue
git commit -m "feat(query-ui): 本体指标页签 + 问数展示指标名"
```

---

### Task 6: 生成并跑「燃煤业务语义执行层评测集」（验收）

**Files:**
- Modify: `backend/scripts/_gen_coal_eval.py`（若 Task 2 未含运行部分）

- [ ] **Step 1: 生成评测集**

Run: `cd backend && $env:ENVIRONMENT="dev"; .venv/Scripts/python.exe scripts/_gen_coal_eval.py`
Expected: 打印 aistation 收录题数（>0）。

- [ ] **Step 2: 跑评测（基线 vs 三级降级）**

用 `eval_runner.start_run(auth, filter={"dataset":"coal_semantic_v1","datasource":"ds:4"}, config={"object_query_enabled":"true"})` 跑一轮（脚本或 `_ab_object_query.py` 同款），对比 `data_accuracy / metric_accuracy / object_rate / avg_ms`。
Expected: 产出对比数据（截图/日志留档）。

- [ ] **Step 3: 记录结论到 spec**

在 spec `§6.2` 追加「实测结果」小节（数据集名、题数、关键指标、结论）。

- [ ] **Step 4: 提交**

```bash
git add backend/scripts/_gen_coal_eval.py docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md
git commit -m "test(query): 燃煤业务语义执行层评测集与实测结论"
```

---

## Self-Review

**1. Spec 覆盖**：§5.1（本体指标页签）→ T5；§5.2（数据与集成语义建模面板）→ T4；§5.3（问数展示指标）→ T5；§6（燃煤评测集）→ T2/T6；§3 的 API 化 → T1。
**2. Step 扫描**：每步单一动作、有可验证结果。
**3. 类型一致**：`generate_modeling(kind, datasource, auth, max_objects, dry)` 在 T1 定义并被 controller 调用；`dataset` 贯穿 T2 的 `list_cases`/`generate_round`/`upsert_case`。
**4. Review Focus 对应**：①权限+缓存失效→T1 测试断言 `_SETTINGS_CACHE is None`；②数据集隔离→T2 `_pick_cases` 测试；③前端风格→T4/T5 只用 Element Plus（无自定义样式）；④空 metric 不渲染→T5 条件渲染；⑤幂等→S3 已保证 + T1 重复调用不重复。
**5. 比例**：plan 与 spec 相称；前端任务给组件与字段，不写整文件。
