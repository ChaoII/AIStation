"""本体「大模型自动建模」两段式接口。

契约（这是本用例要锁住的东西）：
1. **预览不落库** —— `POST /auto-model/preview` 只生成候选（后端 `dry=True`），
   返回逐条 `items`，但**一条都不写**；
2. **只落勾选的那批** —— `POST /auto-model/apply` 精确落库传入的 items，
   **不重跑大模型**（重跑结果会漂移，用户勾的就不是落库的那批）；
3. 空 `items` → 可读 400，而不是静默 200。

大模型与数据收集都打桩（不真的调 LLM、不依赖真实数据源），断言打在
`AiQueryService.upsert_metric` 的**实际调用**上，而不是接口返回的数字。
"""
from __future__ import annotations

import json

from app.plugin.module_ai.query import modeling as M
from app.plugin.module_ai.query.service import AiQueryService

PREVIEW = "/api/v1/ai/ontology/auto-model/preview"
APPLY = "/api/v1/ai/ontology/auto-model/apply"

_FAKE_LLM_OUTPUT = json.dumps(
    [
        {
            "key": "obj_a_total",
            "name": "对象A 计数",
            "description": "按对象计数",
            "object_code": "obj_a",
            "agg_fn": "count",
            "bound_dimensions": [],
        },
        {
            "key": "obj_a_sum_x",
            "name": "对象A 求和X",
            "description": "对 x 求和",
            "object_code": "obj_a",
            "agg_fn": "sum",
            "property_code": "x",
            "bound_dimensions": ["dim1"],
        },
        # 非法：object_code 不在候选对象里 → 解析阶段就被丢掉
        {
            "key": "ghost_total",
            "name": "幽灵",
            "object_code": "not_exists",
            "agg_fn": "count",
        },
    ],
    ensure_ascii=False,
)


def _stub_modeling(monkeypatch) -> list[str]:
    """打桩大模型/对象收集/口径验证，返回记录落库调用的列表。"""

    async def fake_llm(prompt: str, **kwargs) -> str:  # noqa: ARG001
        return _FAKE_LLM_OUTPUT

    async def fake_collect(datasource: str, max_objects: int = 12, offset: int = 0):  # noqa: ARG001
        return [{"code": "obj_a", "name": "对象A", "fields": [{"code": "x", "name": "X"}]}]

    async def fake_verify(metric: dict) -> dict:  # noqa: ARG001
        return {"ok": True}

    monkeypatch.setattr(M, "model_llm", fake_llm)
    monkeypatch.setattr(M, "collect_objects", fake_collect)
    monkeypatch.setattr(M, "verify_metric", fake_verify)

    upserts: list[str] = []

    async def fake_upsert(data, auth):  # noqa: ARG001
        upserts.append(data.key)

    monkeypatch.setattr(AiQueryService, "upsert_metric", fake_upsert)
    return upserts


def test_preview_returns_items_without_writing(test_client, auth_headers, monkeypatch):
    """预览：返回候选、**不落库**。"""
    upserts = _stub_modeling(monkeypatch)

    r = test_client.post(
        PREVIEW,
        json={"datasource": "ds:1", "scope": "metrics", "max_objects": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    keys = [it["key"] for it in data["items"]]
    assert keys == ["obj_a_total", "obj_a_sum_x"], data  # 幽灵对象已被解析阶段过滤
    assert data["saved"] == 2 and data["parsed"] == 2, data
    assert upserts == [], f"预览不该落库，却调用了 {upserts}"


def test_apply_persists_only_selected_items(test_client, auth_headers, monkeypatch):
    """应用：只落**勾选的那批**，且不重跑大模型。"""
    upserts = _stub_modeling(monkeypatch)

    preview = test_client.post(
        PREVIEW,
        json={"datasource": "ds:1", "scope": "metrics", "max_objects": 5},
        headers=auth_headers,
    ).json()["data"]
    items = preview["items"]

    r = test_client.post(
        APPLY,
        json={"datasource": "ds:1", "scope": "metrics", "items": items[:1]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["saved"] == 1, r.text
    assert upserts == ["obj_a_total"], f"应只落勾选的那条，实际 {upserts}"


def test_apply_rejects_empty_items(test_client, auth_headers, monkeypatch):
    """空 items → 可读 400（不静默 200、不落库）。"""
    upserts = _stub_modeling(monkeypatch)

    r = test_client.post(
        APPLY,
        json={"datasource": "ds:1", "scope": "metrics", "items": []},
        headers=auth_headers,
    )
    assert r.status_code == 400, r.text
    assert upserts == []


_FAKE_ANNOTATE_OUTPUT = json.dumps(
    [
        {
            "object_code": "obj_a",
            "object_name": "对象A",
            "description": "业务对象 A",
            "fields": [{"code": "x", "name": "X 字段", "options": []}],
        }
    ],
    ensure_ascii=False,
)


def test_annotations_preview_does_not_write(test_client, auth_headers, monkeypatch):
    """标注分支同样遵守「预览不落库」。"""
    _stub_modeling(monkeypatch)

    async def fake_annotate_llm(prompt: str, **kwargs) -> str:  # noqa: ARG001
        return _FAKE_ANNOTATE_OUTPUT

    monkeypatch.setattr(M, "model_llm", fake_annotate_llm)

    written: list[str] = []

    async def fake_annotate_object(code: str, name: str, description: str) -> None:  # noqa: ARG001
        written.append(code)

    monkeypatch.setattr(M, "_annotate_object", fake_annotate_object)

    r = test_client.post(
        PREVIEW,
        json={"datasource": "ds:1", "scope": "annotations", "max_objects": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["parsed"] >= 1, data
    assert data["items"], data
    assert written == [], f"标注预览不该落库，却写了 {written}"

