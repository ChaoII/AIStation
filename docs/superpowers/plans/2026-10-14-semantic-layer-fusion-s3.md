# 语义层融合 · S3（大模型自动建模管线）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用**大模型（agno）**对数据源（燃煤库 `ds:4`）的语义自动建模：生成**绑定型指标**（当前仅 4 个，而对象有 336 个）+ **对象/属性标注**，并对口径**执行验证**后幂等落库，补齐「指标几乎为 0、标注参差」的缺口。

**Architecture:** 新增 `query/modeling.py`：agno LLM 调用（复用 `_ir_runtime` 模型解析）+ 提示词/容错解析（复用 `eval_generate` 的解析思路）+ **口径执行验证**（绑定型指标走 `instance_aggregate`，非退化才收录）+ 幂等落库（`AiQueryService.upsert_metric` / `ontology.upsert_object|upsert_property`）。一次性脚本 `scripts/_auto_model.py` 触发；`--annotate` / `--metrics` 分步。

**Tech Stack:** FastAPI + SQLAlchemy async；**agno**（`Agent` + `OpenAILike`）；pytest（`backend/tests/`）。

**Spec:** `docs/superpowers/specs/2026-10-14-semantic-layer-fusion-design.md`（§3）

## Global Constraints

- 回复/注释/文档一律**中文**；提交信息 `feat(query): 中文描述`。
- **LLM 一律走 agno**（`_ir_runtime()` + `build_headers` + `Agent`），**禁止** `AsyncOpenAI` 直连（`eval_generate.call_llm` 是历史遗留，S3 不复用其调用方式，只复用其**纯解析函数**思路）。
- 建模产出必须**幂等**（`upsert_metric` 按 `(datasource,key)`、`upsert_object/property` 按 code），可反复跑。
- 绑定型指标口径由「对象属性 + 聚合」推导，**执行验证**（能跑通且结果非空/非退化）才落库。
- 不改 `ask()` 降级骨架；不动既有评测模块行为。
- 测试库是 SQLite：`asyncio.run` 包普通 `def test_*`；LLM 在测试中一律 **mock**（不真调）。

## Review Focus

1. **LLM 输出不可解析**：模型常带围栏/解释/截断 → 解析必须容错（复用 `_salvage_objects` 思路），解析空不得抛异常。
2. **指标口径跑不通**：绑定的 `object_code/property_code` 可能不存在 → 验证失败必须**跳过并计数**，不得落库坏指标。
3. **退化口径**：生成 `count(*)` 全表计数等无区分度指标 → 应过滤（复用 `is_degenerate_result` 思路）。
4. **幂等重跑**：同 key 重复生成不得产生重复指标/属性。
5. **数据源隔离**：生成必须限定在目标数据源（`ds:4`）的对象与表，不得跨库。

---

### Task 1: 建模 LLM 调用（走 agno）+ 容错 JSON 解析

**Files:**
- Create: `backend/app/plugin/module_ai/query/modeling.py`
- Test: `backend/tests/test_query_modeling_llm.py`（新建，纯逻辑/桩）

**Interfaces:**
- Produces:
  - `async def model_llm(prompt: str, *, max_tokens: int = 4000, timeout: int = 120) -> str`（走 agno；失败返回 `""` 不抛）
  - `def parse_json_objects(text: str) -> list[dict]`（容错：围栏/噪声/截断配平，复用思路）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_modeling_llm.py
from app.plugin.module_ai.query.modeling import parse_json_objects


def test_parse_plain_json_array():
    assert parse_json_objects('[{"a":1},{"a":2}]') == [{"a": 1}, {"a": 2}]


def test_parse_fenced_and_noisy():
    t = '说明如下：\n```json\n{"metrics":[{"key":"k1"}]}\n```\n完毕'
    out = parse_json_objects(t)
    assert {"key": "k1"} in out


def test_parse_truncated_salvages_complete_objects():
    t = '[{"key":"k1","name":"甲"},{"key":"k2","name":"乙"},{"key":"k3","na'
    out = parse_json_objects(t)
    assert {"key": "k1", "name": "甲"} in out
    assert {"key": "k2", "name": "乙"} in out


def test_parse_garbage_returns_empty():
    assert parse_json_objects("这是一段没有 JSON 的话") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_modeling_llm.py -q`
Expected: FAIL（`modeling` 模块不存在）

- [ ] **Step 3: 实现**

`modeling.py`：
- `parse_json_objects(text)`：去 ``` 围栏 → 优先取 `[...]` 数组 → 再取 `{...}` 里的**第一个列表值**或裸对象 → 兜底按花括号配平扫描救回完整对象（照搬 `eval_generate._salvage_objects` 的逻辑，作为本模块私有实现，避免耦合）。
- `model_llm(prompt, max_tokens=4000, timeout=120)`：`runtime = await AiQueryService._ir_runtime()`；`OpenAILike(id=..., base_url=..., api_key=..., temperature=0.0, max_tokens=..., timeout=..., default_headers=build_headers(...))`；`Agent(model=model, telemetry=False).arun(prompt)` 取 `resp.content`；异常 → `log.warning` + 返回 `""`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_modeling_llm.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/modeling.py backend/tests/test_query_modeling_llm.py
git commit -m "feat(query): 建模 LLM 调用（agno）与容错解析"
```

---

### Task 2: 绑定型指标生成（prompt + 解析 + 口径验证）

**Files:**
- Modify: `backend/app/plugin/module_ai/query/modeling.py`
- Test: `backend/tests/test_query_modeling_metrics.py`（新建）

**Interfaces:**
- Consumes: `AiQueryService.list_metrics`、`ontology._instance_meta`
- Produces:
  - `def build_metric_prompt(objects: list[dict]) -> str`（objects = `[{code,name,table,fields:[{code,name,type}]}]`）
  - `def parse_metrics(text: str, valid_objects: dict) -> list[dict]`（返回 `[{key,name,description,object_code,property_code,agg_fn,bound_dimensions}]`；过滤 object_code 不在 valid_objects 的项、key 非法字符的项）
  - `async def verify_metric(metric: dict) -> dict`（绑定型走 `ontology.instance_aggregate`，返回 `{ok, rows, reason}`）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_modeling_metrics.py
import asyncio

from app.plugin.module_ai.query.modeling import parse_metrics, verify_metric


def test_parse_metrics_filters_unknown_object_and_bad_key():
    valid = {"coal_batch": {"fields": [{"code": "FUELKINDNAME"}]}}
    text = ('[{"key":"coal_batch_count","name":"入厂批次数","object_code":"coal_batch",'
            '"property_code":"","agg_fn":"count","bound_dimensions":["FUELKINDNAME"]},'
            '{"key":"x y","name":"坏","object_code":"coal_batch","agg_fn":"count"},'
            '{"key":"ghost","name":"幽灵","object_code":"nope","agg_fn":"count"}]')
    out = parse_metrics(text, valid)
    keys = [m["key"] for m in out]
    assert "coal_batch_count" in keys and "ghost" not in keys and "x y" not in keys


def test_verify_metric_ok(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.ontology import service as ont

        async def _fake_agg(object_code, group_by="", aggs=None, filters=None, limit=50,
                            principal=None, scenario_code=""):
            return {"ok": True, "series": [{"label": "a", "value": 3}], "rows": [["a", 3]]}

        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        return await M.verify_metric({"object_code": "coal_batch", "property_code": "",
                                      "agg_fn": "count", "bound_dimensions": []})

    r = asyncio.run(_go())
    assert r["ok"] is True


def test_verify_metric_rejects_when_aggregate_fails(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.ontology import service as ont

        async def _fake_agg(*a, **k):
            return {"ok": False, "msg": "字段不在表里"}

        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        return await M.verify_metric({"object_code": "coal_batch", "property_code": "NOPE",
                                      "agg_fn": "count", "bound_dimensions": []})

    r = asyncio.run(_go())
    assert r["ok"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_modeling_metrics.py -q`
Expected: FAIL（`parse_metrics`/`verify_metric` 未定义）

- [ ] **Step 3: 实现**

- `build_metric_prompt(objects)`：列出对象（code/name/表/字段）→ 要求 LLM 产出**绑定型指标** JSON `{"metrics":[{key,name,description,object_code,property_code,agg_fn,bound_dimensions}]}`，`key` 用 `{object_code}_{agg}_{property}` 风格、`agg_fn∈{count,sum,avg,min,max}`、`property_code` 为可聚合数值字段（count 可空）。
- `parse_metrics(text, valid_objects)`：`parse_json_objects` → 逐项清洗：`object_code` 必须在 `valid_objects`；`key` 必须 `^[A-Za-z0-9_]+$`；`agg_fn` 必须在白名单；非 count 必须有 `property_code`。
- `verify_metric(metric)`：构造 `principal=await security.load_principal(None)`（匿名）或 superuser；调用 `ont.instance_aggregate(object_code, group_by=(首维 or ""), aggs=[{fn,prop}])`；`ok=True` 且 `rows` 非空**且非退化**（复用 `eval_metrics.is_degenerate_result`）→ `{ok:True,...}`，否则 `{ok:False, reason}`。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_modeling_metrics.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/modeling.py backend/tests/test_query_modeling_metrics.py
git commit -m "feat(query): 绑定型指标生成与口径验证"
```

---

### Task 3: 生成→验证→幂等落库（`generate_metrics`）+ 触发脚本

**Files:**
- Modify: `backend/app/plugin/module_ai/query/modeling.py`
- Create: `backend/scripts/_auto_model.py`
- Test: `backend/tests/test_query_modeling_generate.py`（新建）

**Interfaces:**
- Consumes: Task 1/2 的函数；`AiQueryService.upsert_metric`；`semantic_context`/`ontology._instance_meta`
- Produces: `async def generate_metrics(datasource: str, auth, max_objects: int = 12) -> dict`（返回 `{parsed, verified, saved, rejected, reasons}`）；`async def collect_objects(datasource: str, max_objects: int) -> list[dict]`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_modeling_generate.py
import asyncio


def test_generate_metrics_mock_llm_and_save(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M
        from app.plugin.module_ai.query import service as S

        async def _fake_collect(datasource, max_objects):
            return [{"code": "coal_batch", "name": "入厂煤批次", "table": "T",
                     "fields": [{"code": "FUELKINDNAME", "name": "煤种", "type": "string"}]}]

        async def _fake_llm(prompt, **k):
            return ('[{"key":"coal_batch_count","name":"入厂批次数","object_code":"coal_batch",'
                    '"property_code":"","agg_fn":"count","bound_dimensions":[]}]')

        async def _fake_verify(metric):
            return {"ok": True, "rows": [["x", 3]]}

        saved = {}

        async def _fake_upsert(data, auth):
            saved["key"] = data.key
            return {"key": data.key}

        monkeypatch.setattr(M, "collect_objects", _fake_collect)
        monkeypatch.setattr(M, "model_llm", _fake_llm)
        monkeypatch.setattr(M, "verify_metric", _fake_verify)
        monkeypatch.setattr(S.AiQueryService, "upsert_metric", _fake_upsert)
        from types import SimpleNamespace

        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        return await M.generate_metrics("ds:4", auth, max_objects=5), saved

    out, saved = asyncio.run(_go())
    assert out["saved"] == 1
    assert saved.get("key") == "coal_batch_count"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_modeling_generate.py -q`
Expected: FAIL（`generate_metrics`/`collect_objects` 未定义）

- [ ] **Step 3: 实现**

- `collect_objects(datasource, max_objects)`：取该数据源的对象（`semantic_context` 过滤 `datasource_id`）+ 每个对象的字段（`ontology._instance_meta` 的 `props`），组装 `[{code,name,table,fields}]`（`max_objects` 截断）。
- `generate_metrics(datasource, auth, max_objects)`：`objects=collect_objects` → `model_llm(build_metric_prompt(objects))` → `parse_metrics(text, {o['code']:o})` → 逐个 `verify_metric` → 通过者 `upsert_metric(SimpleNamespace(datasource=..., key=..., ..., object_code=..., property_code=..., agg_fn=..., bound_dimensions=...))`；统计 `{parsed,verified,saved,rejected,reasons}`。
- `scripts/_auto_model.py`：`--metrics`（默认）跑 `generate_metrics`，打印统计；`--dry` 只生成不落库。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_query_modeling_generate.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/modeling.py backend/scripts/_auto_model.py backend/tests/test_query_modeling_generate.py
git commit -m "feat(query): 指标生成-验证-落库管线与脚本"
```

---

### Task 4: 对象/属性标注生成（LLM 补中文名/描述/枚举）+ 落库

**Files:**
- Modify: `backend/app/plugin/module_ai/query/modeling.py`
- Test: `backend/tests/test_query_modeling_annotate.py`（新建）

**Interfaces:**
- Produces:
  - `def build_annotate_prompt(objects: list[dict]) -> str`
  - `def parse_annotations(text: str, valid_objects: dict) -> list[dict]`（`[{object_code, object_name, description, fields:[{code,name,options}]}]`）
  - `async def generate_annotations(datasource: str, auth, max_objects: int = 12) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_query_modeling_annotate.py
from app.plugin.module_ai.query.modeling import parse_annotations


def test_parse_annotations_filters_unknown_object():
    valid = {"coal_batch": {"fields": [{"code": "FUELKINDNAME"}]}}
    text = ('[{"object_code":"coal_batch","object_name":"入厂煤批次","description":"入厂煤批次记录",'
            '"fields":[{"code":"FUELKINDNAME","name":"煤种","options":[]}]},'
            '{"object_code":"ghost","object_name":"幽灵","fields":[]}]')
    out = parse_annotations(text, valid)
    assert len(out) == 1 and out[0]["object_code"] == "coal_batch"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_modeling_annotate.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

- `build_annotate_prompt`：要求 LLM 给每个对象/字段补**简明中文名**与**一句话业务描述**，字段如有明确枚举给出 `options`。
- `parse_annotations(text, valid_objects)`：`parse_json_objects` → 过滤 `object_code` 不在 `valid_objects`；字段 code 必须在对象字段里。
- `generate_annotations(datasource, auth, max_objects)`：`collect_objects` → LLM → parse → 落库：`ontology.upsert_object({"code":..,"name":..,"description":..})`（**只覆盖 name/description**，不传 `backing_table`/`datasource_id` 以免误改）、`ontology.upsert_property({"object_code","code","name","options"})`；统计。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && $env:PYTEST_NO_APP=1; .venv/Scripts/python.exe -m pytest tests/test_query_modeling_annotate.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/query/modeling.py backend/tests/test_query_modeling_annotate.py
git commit -m "feat(query): 对象/属性标注自动生成"
```

---

### Task 5: 真跑建模（燃煤库 ds:4）并验证

**Files:**
- Modify: `backend/scripts/_auto_model.py`（加 `--annotate` / `--all`）
- Test: 手动验证（无自动测试；LLM 依赖真实模型）

**Interfaces:**
- Consumes: Task 3/4 的 `generate_metrics` / `generate_annotations`

- [ ] **Step 1: 补脚本参数**

`_auto_model.py`：`--metrics`（默认）/`--annotate`/`--all`（两者都跑）/`--dry`（不落库）；输出各阶段统计（parsed/verified/saved/rejected）。

- [ ] **Step 2: 真跑（燃煤库 ds:4）**

Run: `cd backend && $env:ENVIRONMENT="dev"; .venv/Scripts/python.exe scripts/_auto_model.py --all`
Expected: 打印生成的指标/标注统计；无异常。

- [ ] **Step 3: 验证落库**

Run: 查询 `ai_query_metrics` 的绑定型指标数（应 > 4）、`ai_ont_object` 的中文名是否有更新。
Expected: 绑定型指标数增加；对象名更规范。

- [ ] **Step 4: 幂等重跑**

Run: 再跑一次 `--all` → 指标数不重复增长（`upsert_metric` 按 `(datasource,key)`）。
Expected: 数量稳定。

- [ ] **Step 5: 提交**

```bash
git add backend/scripts/_auto_model.py
git commit -m "chore(query): 自动建模脚本支持 annotate/all/dry"
```

---

## Self-Review

**1. Spec 覆盖**：§3.1（筛表/标注/建关系/生成指标）→ T2/T4（标注+指标；关系生成留 S3.5，规则 `infer_asset_relations` 已有）；§3.2（复用 LLM 管线骨架）→ T1；§3.3（落库/幂等）→ T3/T4/T5。
**2. Step 扫描**：每步单一动作、有可验证结果；实现给签名与关键分支。
**3. 类型一致**：`parse_json_objects -> list[dict]`、`parse_metrics(text, valid_objects) -> list[dict]`、`verify_metric(metric) -> {ok,rows,reason}` 贯穿 T1–T4。
**4. Review Focus 对应**：①容错解析→T1 4 个测试；②口径跑不通→T2 `verify_metric_rejects_when_aggregate_fails`；③退化口径→T2 verify 内 `is_degenerate_result`；④幂等→T3/T5 重跑；⑤数据源隔离→T3 `collect_objects` 按 `datasource_id` 过滤。
**5. 比例**：plan 与 spec 相称，代码块以签名/断言/关键分支为主。

> **说明**：关系自动生成（LLM 识别 FK）本计划暂用现有规则 `infer_asset_relations`（`service.py:4975`）兜底，S3.5 再补 LLM 关系提案；这样 S3 聚焦「指标 + 标注」两个最大缺口，可独立验证。
