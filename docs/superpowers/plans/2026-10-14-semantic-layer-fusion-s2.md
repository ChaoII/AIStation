# 语义层融合 · S2（指标进对象查询执行层 + 流式接指标）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让「指标」成为对象查询执行层的一等实体：LLM 生成的 IR 可直接**引用指标**（而非重造聚合口径），绑定型指标由本体实例层**确定性执行**；并让流式 `ask_stream` 也走指标快路径。

**Architecture:** 在 `object_query.py` 的 `ObjectQueryIR` 增加 `metric` 节点，`render_ir_prompt` 注入「绑定到候选对象的指标」，`validate_ir` 用指标白名单收敛；`object_exec.execute_ir` 对绑定型指标（`object_code+property_code+agg_fn`）走 `instance_aggregate`（支持任意数据源）；`_object_query_path` 串联三者并把对象查询**放开到自定义数据源**；`ask_stream` 在对象查询之前插入指标快路径。

**Tech Stack:** FastAPI + SQLAlchemy async（asyncpg）+ PostgreSQL/SQLite；pytest（`backend/tests/`，`asyncio.run` 惯例）。

**Spec:** `docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md`（§2.2、§4.2、§4.3）

## Global Constraints

- 回复/注释/文档一律**中文**；提交信息 `feat(query): 中文描述`。
- LLM 一律走 agno（`_ir_llm`/`_get_runtime`），不新增直连。
- **严格降级**：对象查询任何环节失败返回 `None`，由调用方回退 NL2SQL（绝不因新路径失败而答不出）。
- IR 的 object/field/link/metric **必须**来自「授权 ∩ 检索命中」清单，越界剔除。
- 绑定型指标口径由「对象属性 + 聚合」确定性推导，**不写 SQL**；模板型指标仍走既有 `sql_template`。
- 测试库是 SQLite：测试用 `asyncio.run` 包普通 `def test_*`；跨方言勿用 `information_schema`。
- `PYTEST_NO_APP=1` 可快测纯逻辑（`object_query.py` 无 IO）。

## Review Focus

1. **指标越界不得放行**：IR 里 `metric` 不在白名单时必须剔除（或整条降级），否则会执行未授权口径。
2. **绑定型指标缺字段**：`object_code/property_code/agg_fn` 任一为空 → 视为**模板型**，不得当绑定型执行。
3. **自定义数据源下对象查询**：放开后必须仍受对象 `datasource_id` 与 schema 白名单约束，不能跨库越权。
4. **流式降级**：`ask_stream` 指标快路径失败必须继续走对象/NL2SQL 流式，不能中断 SSE。
5. **空指标列表**：无绑定指标时行为与改造前**完全一致**（回归）。

---

### Task 1: `ObjectQueryIR` 支持 `metric` 节点 + 校验收敛

**Files:**
- Modify: `backend/app/plugin/module_ai/query/object_query.py`（`ObjectQueryIR` :40-88、`validate_ir` :151-298）
- Test: `backend/tests/test_query_object_metric_ir.py`（新建，`PYTEST_NO_APP=1` 可跑）

**Interfaces:**
- Produces: `ObjectQueryIR.metric: str`（+ `to_dict`/`from_dict`）；`validate_ir(ir, allowed, max_traverse_depth=1, metrics=None)`，其中 `metrics` 为 `dict[str, dict]`（key→指标字典）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_object_metric_ir.py
from app.plugin.module_ai.query.object_query import ObjectQueryIR, parse_ir, validate_ir


def _allowed():
    return {"coal_batch": {"name": "入厂煤批次", "fields": {"FUELKINDNAME": {"name": "煤种"}},
                           "links": {}, "metrics": {"batch_count": {"name": "批次量"}}}}


def test_ir_metric_roundtrip():
    ir = ObjectQueryIR.from_dict({"object": "coal_batch", "metric": "batch_count"})
    assert ir.metric == "batch_count"
    assert ir.to_dict()["metric"] == "batch_count"


def test_validate_keeps_known_metric():
    ir, reasons = validate_ir(parse_ir('{"object":"coal_batch","metric":"batch_count"}'),
                              _allowed(),
                              metrics={"batch_count": {"key": "batch_count", "object_code": "coal_batch"}})
    assert ir is not None and ir.metric == "batch_count"


def test_validate_drops_unknown_metric():
    ir, reasons = validate_ir(parse_ir('{"object":"coal_batch","metric":"nope","filters":[{"field":"FUELKINDNAME","op":"eq","value":"原煤"}]}'),
                              _allowed(),
                              metrics={"batch_count": {"key": "batch_count", "object_code": "coal_batch"}})
    assert ir is not None and ir.metric == ""
    assert any("指标" in r for r in reasons)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_ir.py -q`
Expected: FAIL（`ObjectQueryIR` 无 `metric`）

- [ ] **Step 3: 实现**

- `ObjectQueryIR` 增字段 `metric: str = ""`；`to_dict` 增 `"metric": self.metric`；`from_dict` 增 `metric=str(d.get("metric") or "").strip()`。
- `validate_ir(..., metrics=None)`：在 `spec = allowed[code]` 后，处理 `ir.metric`：
  - 空 → 跳过；
  - 非空 → 在 `metrics`（key→dict）里查，且其 `object_code`（若有）应等于 `code`；找不到则 `reasons.append("指标 X 不在可用范围，已忽略")` 且 `ir.metric=""`。
- 末尾「没有可执行条件」判定增补 `or ir.metric`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_ir.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/object_query.py backend/tests/test_query_object_metric_ir.py
git commit -m "feat(query): 对象查询 IR 支持指标节点"
```

---

### Task 2: `render_ir_prompt` 注入绑定指标 + `build_allowed` 带指标

**Files:**
- Modify: `backend/app/plugin/module_ai/query/object_query.py`（`render_ir_prompt` :301-363、`build_allowed` :366-393）
- Test: `backend/tests/test_query_object_metric_prompt.py`（新建）

**Interfaces:**
- Consumes: `ObjectQueryIR.metric`（Task 1）
- Produces: `render_ir_prompt(question, allowed, max_objects=8, max_traverse_depth=1, metrics=None)`（新增 `metrics` 形参，渲染「可用指标」块 + 输出格式加 `metric`）；`build_allowed(objects, props_by_code, links_by_code, metrics_by_object=None)`（给每个对象挂 `spec["metrics"]`）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_object_metric_prompt.py
from app.plugin.module_ai.query.object_query import build_allowed, render_ir_prompt


def test_prompt_injects_metrics():
    allowed = build_allowed(
        [{"code": "coal_batch", "name": "入厂煤批次"}],
        {"coal_batch": [{"code": "FUELKINDNAME", "name": "煤种", "prop_type": "string", "options": []}]},
        {"coal_batch": []},
        metrics_by_object={"coal_batch": [{"key": "batch_count", "name": "批次量", "agg_fn": "count",
                                           "property_code": "", "bound_dimensions": ["FUELKINDNAME"]}]},
    )
    assert "batch_count" in allowed["coal_batch"]["metrics"]
    p = render_ir_prompt("各煤种的批次量", allowed, metrics={"batch_count": {"key": "batch_count"}})
    assert "batch_count" in p and '"metric"' in p
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_prompt.py -q`
Expected: FAIL（`build_allowed` 无 `metrics_by_object` / prompt 无指标）

- [ ] **Step 3: 实现**

- `build_allowed(..., metrics_by_object=None)`：`out[code]["metrics"] = {m["key"]: m for m in (metrics_by_object or {}).get(code, [])}`。
- `render_ir_prompt(..., metrics=None)`：在每个对象行下追加一行「可用指标：`key(名称,聚合=count,维度=…)`」；输出格式 JSON 增 `"metric": "指标key（可选，优先用它而不是自己拼聚合）"`；硬性要求补一条「有可用指标且问题就是要该指标时，填 `metric`」。
- 保持既有行为：`metrics` 为空时输出与改造前一致（回归）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_prompt.py tests/test_query_object.py -q`
Expected: PASS（新测试 + 既有对象查询测试不回归）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/object_query.py backend/tests/test_query_object_metric_prompt.py
git commit -m "feat(query): IR 提示词与词表注入绑定指标"
```

---

### Task 3: `execute_ir` 消费绑定型指标（走 `instance_aggregate`）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/object_exec.py`（`execute_ir` :322-414）
- Test: `backend/tests/test_query_object_metric_exec.py`（新建）

**Interfaces:**
- Consumes: `ObjectQueryIR.metric`（Task 1）
- Produces: `execute_ir(ir, principal=None, metrics=None)`（新增 `metrics: dict[str, dict]`）。绑定型（`object_code+property_code+agg_fn` 且 `property_code` 可空仅限 count）→ `ont.instance_aggregate(object_code, group_by=..., aggs=[{fn: agg_fn, prop: property_code}])`；非绑定型 → `{"ok": False, "error": "指标 X 非绑定型，交由模板快路径"}`（降级）。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_object_metric_exec.py
import asyncio


def test_execute_ir_metric_uses_instance_aggregate(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import object_exec as oe
        from app.plugin.module_ai.query.object_query import ObjectQueryIR
        from app.plugin.module_ai.ontology import service as ont

        seen = {}

        async def _fake_agg(object_code, group_by="", aggs=None, filters=None, limit=50,
                            principal=None, scenario_code=""):
            seen.update(object_code=object_code, group_by=group_by, aggs=aggs)
            return {"ok": True, "series": [{"label": "原煤", "value": 85}],
                    "rows": [["原煤", 85]], "group_by": group_by}

        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        ir = ObjectQueryIR.from_dict({"object": "coal_batch", "metric": "batch_count",
                                      "group_by": [{"field": "FUELKINDNAME", "alias": "煤种"}]})
        metrics = {"batch_count": {"key": "batch_count", "object_code": "coal_batch",
                                   "property_code": "", "agg_fn": "count",
                                   "name": "批次量"}}
        r = await oe.execute_ir(ir, principal=None, metrics=metrics)
        return r, seen

    r, seen = asyncio.run(_go())
    assert r["ok"] is True
    assert seen["object_code"] == "coal_batch" and seen["aggs"][0]["fn"] == "count"
    assert seen["group_by"] == "FUELKINDNAME"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_exec.py -q`
Expected: FAIL（`execute_ir` 无 `metrics` 形参 / 不处理 metric）

- [ ] **Step 3: 实现**

在 `execute_ir` 开头（`meta` 校验后、派生属性之前）插入 metric 分支：
```python
    if ir.metric:
        m = (metrics or {}).get(ir.metric) or {}
        obj = str(m.get("object_code") or "")
        prop = str(m.get("property_code") or "")
        fn = str(m.get("agg_fn") or "")
        if not (obj and fn) or (fn != "count" and not prop):
            return {"ok": False, "error": f"指标 {ir.metric} 非绑定型，降级"}
        gb = ir.group_by[0]["field"] if ir.group_by else ""
        a = {"fn": fn}
        if prop:
            a["prop"] = prop
        r = await ont.instance_aggregate(obj, group_by=gb, aggs=[a],
                                         filters=_filters_to_layer(ir.filters) or None,
                                         limit=ir.limit, principal=principal)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("msg") or "指标聚合失败"}
        col = (ir.group_by[0].get("alias") if ir.group_by else "") or (gb or "合计")
        val = m.get("name") or f"{fn}({prop or '*'})"
        return {"ok": True, "columns": [col, val],
                "rows": [[_safe(x) for x in row] for row in (r.get("rows") or [])],
                "shape": "metric-agg", "note": f"指标 {ir.metric} 口径"}
```
（`ont` 已在 `execute_ir` 内导入；`_filters_to_layer`/`_safe` 同模块已有。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_exec.py tests/test_query_object_multihop.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/object_exec.py backend/tests/test_query_object_metric_exec.py
git commit -m "feat(query): 对象查询执行绑定型指标（instance_aggregate）"
```

---

### Task 4: `_object_query_path` 串联指标 + 放开自定义数据源

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py`
  - `_allowed_objects_for_query`（:6140）：新增 `datasource` 形参；按数据源过滤对象（系统库用现有 `_allowed_for_user`，自定义源用对象的 `datasource_id`）；给候选对象挂**绑定指标**。
  - `_object_query_path`（:6488）：删除 `if datasource not in (SYSTEM_DS, None): return None`；把 `metrics` 透传给 `render_ir_prompt`/`validate_ir`/`execute_ir`。
- Test: `backend/tests/test_query_object_metric_path.py`（新建）

**Interfaces:**
- Consumes: Task 1/2/3 的接口
- Produces: `_allowed_objects_for_query(question, auth, max_objects=8, datasource=SYSTEM_DS) -> dict`（每个 `spec` 可含 `metrics`）；`_object_query_path` 支持 `datasource=ds:{id}`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_object_metric_path.py
import asyncio


def test_object_query_path_not_blocked_for_custom_ds(monkeypatch):
    """自定义数据源不再被无条件 return None（应进入对象查询尝试）。"""
    async def _go():
        from app.plugin.module_ai.query import service as S
        from types import SimpleNamespace

        calls = {"allowed": 0}

        async def _fake_cfg():
            return {}
        async def _fake_allowed(question, auth, max_objects=8, datasource="system"):
            calls["allowed"] += 1
            return {}
        monkeypatch.setattr(S.AiQueryService, "_cfg", classmethod(lambda cls: _fake_cfg()))
        monkeypatch.setattr(S.AiQueryService, "_allowed_objects_for_query",
                            classmethod(lambda cls, q, a, max_objects=8, datasource="system":
                                        _fake_allowed(q, a, max_objects, datasource)))
        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        ans = await S.AiQueryService._object_query_path("各煤种批次量", 1, "ds:4", auth)
        return ans, calls

    ans, calls = asyncio.run(_go())
    # 没有可用对象 → 仍返回 None，但**已尝试**（说明未被 datasource 早退挡住）
    assert ans is None
    assert calls["allowed"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_path.py -q`
Expected: FAIL（`_allowed_objects_for_query` 无 `datasource` 形参 → TypeError，或早退未调用）

- [ ] **Step 3: 实现**

- `_allowed_objects_for_query(cls, question, auth, max_objects=8, datasource=SYSTEM_DS)`：
  - 系统库：维持现有 `_allowed_for_user` 过滤。
  - 自定义源：把 `ds:{id}` 解析出 id，保留 `o.get("datasource_id")==id` 的对象（`semantic_context` 的 objects 需含 `datasource_id`，缺则用 `_object_spec_for` 的 `_instance_meta` 判定）。
  - 给 `out[code]` 挂绑定指标：`await cls.list_metrics(datasource)` 里 `object_code==code` 的指标，注入 `spec["metrics"]`。
- `_object_query_path`：删早退；`metrics_list = await cls.list_metrics(datasource)`；`metrics_map = {m["key"]: m for m in metrics_list}`；`allowed = await cls._allowed_objects_for_query(..., datasource=datasource)`；`render_ir_prompt(..., metrics=metrics_map)`；`validate_ir(..., metrics=metrics_map)`；`execute_ir(ir, principal, metrics=metrics_map)`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_object_metric_path.py tests/test_query_object_e2e.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/service.py backend/tests/test_query_object_metric_path.py
git commit -m "feat(query): 对象查询串联指标并放开自定义数据源"
```

---

### Task 5: 流式 `ask_stream` 接指标快路径

**Files:**
- Modify: `backend/app/plugin/module_ai/query/service.py`（`ask_stream` :6947+，在对象查询块**之前**插入）
- Test: `backend/tests/test_query_stream_metric.py`（新建）

**Interfaces:**
- Consumes: `_match_metric`（:1144）、`_execute_metric`（:992）、`_is_listing_question`、`_wants_grouping`
- Produces: `ask_stream` 命中指标时产出 `{"type":"result","path":"fast",...}` + `{"type":"done","path":"fast"}` 并 `return`；未命中则维持原对象/NL2SQL 流式。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_stream_metric.py
import asyncio


def test_stream_hits_metric_fast_path(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import service as S
        from types import SimpleNamespace

        async def _fake_seed():
            return None
        async def _fake_sess(sid, title, auth):
            return {"id": 1}
        async def _fake_metrics(datasource=None):
            return [{"key": "batch_count", "name": "批次量", "agg": "count",
                     "datasource": "system", "sql_template": "SELECT 1 AS 数值",
                     "params": [], "cache_ttl": 0}]
        async def _fake_terms(datasource=None):
            return []
        async def _fake_exec(metric, params, auth=None):
            return {"sql": "SELECT 1", "columns": ["数值"], "rows": [[1]], "took_ms": 1}
        async def _fake_save(*a, **k):
            return {"id": 1}

        monkeypatch.setattr(S.AiQueryService, "ensure_system_seed",
                            classmethod(lambda cls: _fake_seed()))
        monkeypatch.setattr(S.AiQueryService, "get_or_create_session",
                            classmethod(lambda cls, sid, t, a: _fake_sess(sid, t, a)))
        monkeypatch.setattr(S.AiQueryService, "list_metrics",
                            classmethod(lambda cls, datasource=None: _fake_metrics(datasource)))
        monkeypatch.setattr(S.AiQueryService, "list_terms",
                            classmethod(lambda cls, datasource=None: _fake_terms(datasource)))
        monkeypatch.setattr(S, "_execute_metric", _fake_exec)
        monkeypatch.setattr(S.AiQueryService, "_save_message",
                            classmethod(lambda cls, *a, **k: _fake_save(*a, **k)))
        monkeypatch.setattr(S.AiQueryService, "_maybe_rewrite",
                            classmethod(lambda cls, q, sid, ds: _fake_q(q)))
        monkeypatch.setattr(S, "_match_metric", lambda q, m, t: m[0])
        monkeypatch.setattr(S, "_is_listing_question", lambda q: False)
        monkeypatch.setattr(S, "_wants_grouping", lambda q: False)

        async def _fake_q(q):
            return q
        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        evs = []
        async for ev in S.AiQueryService.ask_stream("批次量", auth, session_id=1):
            evs.append(ev)
        return evs

    evs = asyncio.run(_go())
    paths = [e.get("path") for e in evs if e.get("type") in ("result", "done")]
    assert "fast" in paths
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_stream_metric.py -q`
Expected: FAIL（流式无指标快路径）

- [ ] **Step 3: 实现**

在 `ask_stream` 的 `question = await cls._maybe_rewrite(...)` 之后、对象查询块之前插入：
```python
        # 指标快路径（对齐 ask）：确定性、零 LLM；命中即流式返回
        if not _is_listing_question(question):
            metrics = await cls.list_metrics(datasource)
            terms = await cls.list_terms(datasource)
            metric = _match_metric(question, metrics, terms)
            if metric and metric.get("agg") != "group" and _wants_grouping(question):
                metric = None
            if metric:
                try:
                    params = _build_params(metric, question)
                    res = await _execute_metric(metric, params, auth)
                    msg = await cls._save_message(
                        sess["id"], question, path="fast", datasource=metric["datasource"],
                        sql=res["sql"], columns=res["columns"], rows=res["rows"],
                        result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0),
                        summary=cls._summarize(metric, res))
                    yield {"type": "result", "path": "fast",
                           "columns": res["columns"], "rows": res["rows"],
                           "summary": msg.get("summary") or ""}
                    yield {"type": "done", "path": "fast", "session_id": sess["id"]}
                    return
                except Exception as e:  # noqa: BLE001
                    log.warning("[query] 流式指标快路径失败，降级：[{}] {}",
                                type(e).__name__, str(e)[:120])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_stream_metric.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/service.py backend/tests/test_query_stream_metric.py
git commit -m "feat(query): 流式问数接入指标快路径"
```

---

## Self-Review

**1. Spec 覆盖**：§2.2（指标绑定被消费）→ Task 3/4；§4.2（指标进对象查询 + 自定义数据源）→ Task 1/2/3/4；§4.3（流式接指标）→ Task 5。
**2. Step 扫描**：每步单一动作、有可验证结果；实现步骤给签名与关键分支，未转写整文件。
**3. 类型一致**：`metrics` 统一为 `dict[str, dict]`（key→指标字典），贯穿 Task 1/2/3/4；`ObjectQueryIR.metric` 为 `str`。
**4. Review Focus 对应**：①越界剔除→Task 1 `test_validate_drops_unknown_metric`；②绑定型缺字段→Task 3 分支判定；③自定义源约束→Task 4 按 `datasource_id` 过滤；④流式降级→Task 5 try/except；⑤空指标回归→Task 2/3 保留既有路径。
**5. 比例**：plan 与 spec 相称，代码块以签名/断言/关键分支为主。
