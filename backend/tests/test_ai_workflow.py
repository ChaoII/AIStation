
"""AI 低代码工作流：CRUD、流式运行（start→llm→end）与条件分支。"""
import json
import re
import uuid
from types import SimpleNamespace

from app.plugin.module_ai.workflow.engine import render_template


def _new_name(prefix: str = "pytest_wf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class _FakeDelta:
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [SimpleNamespace(delta=delta)]


def _make_stream_client(chunks, sink):
    """假 AsyncOpenAI：返回一个异步生成器，记录每次 create 入参。"""

    class _Completions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            sink.append(kwargs)
            batch = chunks[self.calls]
            self.calls += 1

            async def _gen():
                for c in batch:
                    yield c

            return _gen()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    return _Client


def _patch_runtime(monkeypatch):
    from app.plugin.module_ai.provider.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "pytest-wf-model",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _create_workflow(test_client, auth_headers, graph=None) -> int:
    payload = {
        "name": _new_name(),
        "description": "pytest 工作流",
        "graph": graph
        or {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "end", "type": "end", "data": {"output_template": "{{q}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        },
        "enabled": True,
    }
    r = test_client.post("/api/v1/ai/workflows/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_wf(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=ids, headers=auth_headers
        )


def test_render_template():
    """模板渲染：替换变量，未知变量保留。"""
    assert render_template("你好 {{name}}", {"name": "世界"}) == "你好 世界"
    assert render_template("{{未知}}", {}) == "{{未知}}"


def test_extract_json():
    """从 LLM 输出中切出 JSON。"""
    from app.plugin.module_ai.workflow.engine import _extract_json

    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('好的，结果为 {"a": 1, "b": [1,2]} 以上') == {"a": 1, "b": [1, 2]}
    assert _extract_json("[1, 2, 3]") == [1, 2, 3]
    # 无 JSON 时原样返回
    assert _extract_json("无结果") == "无结果"


def test_extractor_node(monkeypatch):
    """参数提取：LLM 返回 JSON 字符串，解析为对象写变量。"""
    import asyncio

    from app.plugin.module_ai.workflow import engine as E

    class _Message:
        content = '{"city": "北京", "date": "2026-10-02"}'

    class _Choice:
        message = _Message()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        async def create(self, **kw):
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    async def _resolve(self, data):
        return _Client(), {"model": "m", "temperature": 0, "max_tokens": 256}, [], None

    monkeypatch.setattr(E.WorkflowEngine, "_resolve_llm_client", _resolve)

    eng = E.WorkflowEngine(
        graph={
            "nodes": [
                {
                    "id": "x",
                    "type": "extractor",
                    "data": {"schema": ["city", "date"], "output_variable": "info"},
                }
            ],
            "edges": [],
        },
        variables={},
        messages=[],
        ms=E.UiMessageStream(),
        state={},
    )
    asyncio.run(eng._exec_extractor(eng.nodes["x"]))
    assert eng.outputs["x"] == {"city": "北京", "date": "2026-10-02"}
    assert eng.variables["info"]["city"] == "北京"


def test_classifier_node(monkeypatch):
    """问题分类器：LLM 返回类别名，写入输出与变量。"""
    import asyncio

    from app.plugin.module_ai.workflow import engine as E

    class _Message:
        content = "查询"

    class _Choice:
        message = _Message()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        async def create(self, **kw):
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    async def _resolve(self, data):
        return _Client(), {"model": "m", "temperature": 0, "max_tokens": 32}, [], None

    monkeypatch.setattr(E.WorkflowEngine, "_resolve_llm_client", _resolve)

    eng = E.WorkflowEngine(
        graph={
            "nodes": [
                {"id": "c", "type": "classifier", "data": {"categories": ["查询", "操作"], "output_variable": "cat"}}
            ],
            "edges": [],
        },
        variables={},
        messages=[],
        ms=E.UiMessageStream(),
        state={},
    )
    node = eng.nodes["c"]
    asyncio.run(eng._exec_classifier(node))
    assert eng.outputs["c"] == "查询"
    assert eng.variables["cat"] == "查询"


def test_workflow_run_iteration(monkeypatch, test_client, auth_headers):
    """迭代/循环节点：遍历列表，对每项调用工具并聚合为结果数组。"""
    from app.plugin.module_ai import tools_catalog as tc

    calls: list[dict] = []

    async def _fake_dispatch(name, args, user_id, db_rows=None):
        calls.append({"name": name, "args": args})
        return {"item": args.get("id")}

    monkeypatch.setattr(tc.service, "dispatch_tool", _fake_dispatch)

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "iter",
                "type": "iteration",
                "data": {
                    "items": [1, 2, 3],
                    "tool_name": "mock_batch",
                    "args": {"id": "{{item}}"},
                    "output_variable": "results",
                },
            },
            {"id": "end", "type": "end", "data": {"output_template": "{{results}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "iter"},
            {"id": "e2", "source": "iter", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"reply"' in body
        # 每项调用一次工具，参数中 {{item}} 已渲染为对应值（模板渲染输出字符串）
        assert [c["args"]["id"] for c in calls] == ["1", "2", "3"]
        assert all(c["name"] == "mock_batch" for c in calls)
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_knowledge(monkeypatch, test_client, auth_headers):
    """独立知识节点：检索产生 sources 帧，上下文写入变量供 end 模板插值。"""
    from app.plugin.module_ai.knowledge import service as kb_service

    async def _fake_search(kb_ids, query, top_k=5):
        return [
            {
                "chunk_id": 1,
                "knowledge_base_id": 1,
                "file_name": "doc.txt",
                "content": "AIStation 是开源平台",
                "score": 0.9,
            }
        ]

    monkeypatch.setattr(kb_service.AiKnowledgeService, "search", staticmethod(_fake_search))

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "kb",
                "type": "knowledge",
                "data": {
                    "knowledge_ids": [1],
                    "query": "{{q}}",
                    "top_k": 3,
                    "output_variable": "kb",
                },
            },
            {"id": "end", "type": "end", "data": {"output_template": "{{kb}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "kb"},
            {"id": "e2", "source": "kb", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {"q": "介绍"},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"type": "sources"' in body
        assert "doc.txt" in body
        assert "AIStation 是开源平台" in body
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_http(monkeypatch, test_client, auth_headers):
    """HTTP 节点：发起外部请求并把 JSON 响应写入变量、end 模板插值。"""
    import httpx

    captured: dict = {}

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"hello": "世界"}

        text = '{"hello": "世界"}'

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def request(self, method, url, **kw):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = kw.get("json")
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "http",
                "type": "http",
                "data": {
                    "method": "POST",
                    "url": "https://example.com/api",
                    "headers": {"X-Token": "{{token}}"},
                    "body": {"q": "{{question}}"},
                    "output_variable": "resp",
                },
            },
            {"id": "end", "type": "end", "data": {"output_template": "{{resp}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "http"},
            {"id": "e2", "source": "http", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {"token": "abc", "question": "hi"},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"reply"' in body
        assert "世界" in body
        assert captured["method"] == "POST"
        assert captured["url"] == "https://example.com/api"
        # 变量渲染：{{token}}/{{question}}
        assert captured["json"] == {"q": "hi"}
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_crud(test_client, auth_headers):
    """创建 → 列表 → 详情 → 更新 → 删除。"""
    wf_id = _create_workflow(test_client, auth_headers)
    try:
        lst = test_client.get("/api/v1/ai/workflows/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == wf_id)
        assert row["graph"]["nodes"][0]["type"] == "start"

        detail = test_client.get(f"/api/v1/ai/workflows/detail/{wf_id}", headers=auth_headers)
        assert detail.status_code == 200, detail.text

        upd = test_client.put(
            f"/api/v1/ai/workflows/update/{wf_id}",
            json={"name": "pytest-wf-updated", "enabled": False},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["data"]["name"] == "pytest-wf-updated"
        assert upd.json()["data"]["enabled"] is False
        assert upd.json()["data"]["version"] >= 1
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])

    lst2 = test_client.get("/api/v1/ai/workflows/list", headers=auth_headers).json()["data"]
    assert all(x["id"] != wf_id for x in lst2)


def test_workflow_run_stream_llm(monkeypatch, test_client, auth_headers):
    """start→llm→end：LLM 节点流式产出 text-delta，结束帧完整。"""
    import openai

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "llm1",
                "type": "llm",
                "data": {"prompt": "你是助手，回答：{{q}}"},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "llm1"},
            {"id": "e2", "source": "llm1", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    sent: list[dict] = []
    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        _make_stream_client([[_FakeChunk(_FakeDelta(content="你好呀"))]], sent),
    )
    _patch_runtime(monkeypatch)

    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "打个招呼"}]}],
                "variables": {"q": "世界"},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"type": "text-delta"' in body
        assert "你好呀" in body
        assert '"type": "data-finish"' in body
        assert '"reply": "你好呀"' in body
        assert "data: [DONE]" in body

        # LLM 节点系统提示词被渲染
        system_content = sent[0]["messages"][0]["content"]
        assert "世界" in system_content
        assert "{{q}}" not in system_content
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_stream_condition(monkeypatch, test_client, auth_headers):
    """condition 分支：命中 true 走 llm_true，未命中走 llm_false。"""
    import openai

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "cond",
                "type": "condition",
                "data": {"expression": "{{v}} == 1"},
            },
            {
                "id": "llm_true",
                "type": "llm",
                "data": {"prompt": "命中真分支"},
            },
            {
                "id": "llm_false",
                "type": "llm",
                "data": {"prompt": "命中假分支"},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "cond"},
            {"id": "e2", "source": "cond", "target": "llm_true", "sourceHandle": "true"},
            {"id": "e3", "source": "cond", "target": "llm_false", "sourceHandle": "false"},
            {"id": "e4", "source": "llm_true", "target": "end"},
            {"id": "e5", "source": "llm_false", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    sent: list[dict] = []
    monkeypatch.setattr(
        openai, "AsyncOpenAI", _make_stream_client([[_FakeChunk(_FakeDelta(content="真"))]], sent)
    )
    _patch_runtime(monkeypatch)

    try:
        # v=1 → 命中 true 分支
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {"v": 1},
            },
            headers=auth_headers,
        )
        body = r.text
        assert '"reply": "真"' in body
        assert "命中真分支" in sent[0]["messages"][0]["content"]

        # v=2 → 命中 false 分支
        sent.clear()
        monkeypatch.setattr(
            openai,
            "AsyncOpenAI",
            _make_stream_client([[_FakeChunk(_FakeDelta(content="假"))]], sent),
        )
        r2 = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {"v": 2},
            },
            headers=auth_headers,
        )
        body2 = r2.text
        assert '"reply": "假"' in body2
        assert "命中假分支" in sent[0]["messages"][0]["content"]
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_tool_and_variable(monkeypatch, test_client, auth_headers):
    """variable 赋值 + tool 节点：工具结果写入变量，end 模板插值输出。"""
    from app.plugin.module_ai import tools_catalog as tc

    captured: dict = {}

    async def _fake_dispatch(name, args, user_id, db_rows=None):
        captured["name"] = name
        captured["args"] = args
        return {"ok": True, "name": name}

    monkeypatch.setattr(tc.service, "dispatch_tool", _fake_dispatch)

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "var",
                "type": "variable",
                "data": {"name": "greeting", "value": "你好"},
            },
            {
                "id": "tool",
                "type": "tool",
                "data": {
                    "tool_name": "mock_tool",
                    "args": {"q": "{{greeting}}"},
                    "output_variable": "tool_result",
                },
            },
            {"id": "end", "type": "end", "data": {"output_template": "{{tool_result}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "var"},
            {"id": "e2", "source": "var", "target": "tool"},
            {"id": "e3", "source": "tool", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"reply"' in body
        assert "ok" in body
        # 工具节点变量渲染：{{greeting}} -> 你好
        assert captured["name"] == "mock_tool"
        assert captured["args"] == {"q": "你好"}
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_code(monkeypatch, test_client, auth_headers):
    """code 节点：对输入变量做 Python 表达式转换并写回 end 输出。"""
    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "code",
                "type": "code",
                "data": {"code": "x + 1", "inputs": {"x": 5}, "output_variable": "result"},
            },
            {"id": "end", "type": "end", "data": {"output_template": "{{result}}"}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "code"},
            {"id": "e2", "source": "code", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert '"reply": "6"' in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_llm_tool_loop(monkeypatch, test_client, auth_headers):
    """LLM 节点工具循环：模型下发 tool_call → 派发工具 → 二次调用聚合最终回复。"""
    from types import SimpleNamespace

    import openai

    dispatched: list[tuple] = []

    async def _fake_build(names):
        return [
            {
                "type": "function",
                "function": {
                    "name": "mock_tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ], {}

    async def _fake_run(name, args, user_id, http_tools):
        dispatched.append((name, args))
        return {"result": "工具已执行"}

    from app.plugin.module_ai.apps import service as apps_service

    monkeypatch.setattr(apps_service, "_build_app_tools", _fake_build)
    monkeypatch.setattr(apps_service, "_run_app_tool", _fake_run)

    class _Delta:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Chunk:
        def __init__(self, delta):
            self.choices = [SimpleNamespace(delta=delta)]

    class _Completions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                async def _gen():
                    yield _Chunk(
                        _Delta(
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_1",
                                    function=SimpleNamespace(
                                        name="mock_tool", arguments='{"x":1}'
                                    ),
                                )
                            ]
                        )
                    )

                return _gen()
            msg = SimpleNamespace(content="工具已执行，这是最终回复")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    monkeypatch.setattr(openai, "AsyncOpenAI", _Client)
    _patch_runtime(monkeypatch)

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "llm1",
                "type": "llm",
                "data": {"prompt": "你好", "tools": ["mock_tool"]},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "llm1"},
            {"id": "e2", "source": "llm1", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        # 工具被派发且最终回复包含二次聚合文本
        assert dispatched and dispatched[0][0] == "mock_tool"
        assert dispatched[0][1] == {"x": 1}
        assert "工具已执行" in r.text
        assert "最终回复" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def _make_hitl_tool_client():
    """HITL 工具审批假客户端：stream 首调下发 tool_call，续跑 create 返回最终文本。"""

    class _Delta:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Chunk:
        def __init__(self, delta):
            self.choices = [SimpleNamespace(delta=delta)]

    class _Completions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            self.calls += 1
            if kwargs.get("stream"):
                async def _gen():
                    yield _Chunk(
                        _Delta(
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_1",
                                    function=SimpleNamespace(
                                        name="mock_tool", arguments=json.dumps({"x": 1})
                                    ),
                                )
                            ]
                        )
                    )

                return _gen()
            msg = SimpleNamespace(content="工具已执行，这是审批后的最终回复")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    return _Client


def _patch_hitl_tools(monkeypatch, dispatched):
    """monkeypatch 应用的工具构建/派发，记录被派发的工具。"""
    from app.plugin.module_ai.apps import service as apps_service

    async def _fake_build(names):
        return (
            [
                {
                    "type": "function",
                    "function": {
                        "name": "mock_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            {},
        )

    async def _fake_run(name, args, user_id, http_tools):
        dispatched.append((name, args))
        return {"result": "工具已执行"}

    monkeypatch.setattr(apps_service, "_build_app_tools", _fake_build)
    monkeypatch.setattr(apps_service, "_run_app_tool", _fake_run)


def _hitl_graph(require_approval=True):
    return {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "llm1",
                "type": "llm",
                "data": {"prompt": "你好", "tools": ["mock_tool"], "require_approval": require_approval},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "llm1"},
            {"id": "e2", "source": "llm1", "target": "end"},
        ],
    }


def test_workflow_run_hitl_approval(monkeypatch, test_client, auth_headers):
    """HITL 审批-通过：模型下发 tool_call 时挂起并透出审批帧，approve 后派发工具并续跑。"""
    import openai

    dispatched: list[tuple] = []
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_hitl_tool_client())
    _patch_hitl_tools(monkeypatch, dispatched)
    _patch_runtime(monkeypatch)

    wf_id = _create_workflow(test_client, auth_headers, _hitl_graph())
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        # 运行阶段透出 tool-approval 审批帧（含工具名与参数），且未派发工具
        assert '"type": "tool-approval"' in body
        assert '"toolName": "mock_tool"' in body
        assert '"arguments": {"x": 1}' in body
        assert '"awaiting_approval": true' in body
        assert dispatched == []

        run_id = re.search(r'"run_id": "([0-9a-f]{32})"', body).group(1)

        # 用户通过审批 → 派发工具并续跑生成最终回复
        r2 = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/approve",
            json={"run_id": run_id, "decision": "approve"},
            headers=auth_headers,
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.text
        assert dispatched and dispatched[0][0] == "mock_tool"
        assert dispatched[0][1] == {"x": 1}
        assert "审批后的最终回复" in body2
        assert '"type": "data-finish"' in body2
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_run_hitl_reject(monkeypatch, test_client, auth_headers):
    """HITL 审批-拒绝：不派发工具，把「用户拒绝」写入上下文并续跑生成最终回复。"""
    import openai

    dispatched: list[tuple] = []
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_hitl_tool_client())
    _patch_hitl_tools(monkeypatch, dispatched)
    _patch_runtime(monkeypatch)

    wf_id = _create_workflow(test_client, auth_headers, _hitl_graph())
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        run_id = re.search(r'"run_id": "([0-9a-f]{32})"', r.text).group(1)

        r2 = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/approve",
            json={"run_id": run_id, "decision": "reject"},
            headers=auth_headers,
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.text
        # 拒绝后工具不派发，模型仍产出最终回复
        assert dispatched == []
        assert "审批后的最终回复" in body2
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])
    """LLM 节点接入知识库 RAG：后端透出 ``sources`` 引用来源帧。"""
    import openai

    from app.plugin.module_ai.knowledge import service as kb_service

    async def _fake_search(kb_ids, query, top_k=5):
        return [
            {
                "chunk_id": 1,
                "knowledge_base_id": 1,
                "file_name": "doc.txt",
                "content": "AIStation 是开源平台",
                "score": 0.92,
            }
        ]

    monkeypatch.setattr(
        kb_service.AiKnowledgeService, "search", staticmethod(_fake_search)
    )
    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        _make_stream_client([[_FakeChunk(_FakeDelta(content="好的"))]], []),
    )
    _patch_runtime(monkeypatch)

    graph = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": []}},
            {
                "id": "llm1",
                "type": "llm",
                "data": {"prompt": "你好", "knowledge_ids": [1], "query": "{{q}}"},
            },
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "llm1"},
            {"id": "e2", "source": "llm1", "target": "end"},
        ],
    }
    wf_id = _create_workflow(test_client, auth_headers, graph)
    try:
        r = test_client.post(
            f"/api/v1/ai/workflows/{wf_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "x"}]}],
                "variables": {"q": "介绍"},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert '"type": "sources"' in r.text
        assert "doc.txt" in r.text
        assert "AIStation 是开源平台" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf_id])


def test_workflow_versions_publish_rollback(test_client, auth_headers):
    """版本：保存快照、发布、回滚到指定版本。"""
    graph_a = {
        "nodes": [{"id": "start", "type": "start", "data": {"variables": []}},
                  {"id": "end", "type": "end", "data": {"output_template": "A"}}],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }
    graph_b = {
        "nodes": [{"id": "start", "type": "start", "data": {"variables": []}},
                  {"id": "end", "type": "end", "data": {"output_template": "B"}}],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": graph_a}, headers=auth_headers).json()["data"]
    wid = wf["id"]
    try:
        r1 = test_client.post(f"/api/v1/ai/workflows/{wid}/versions",
            json={"remark": "v1"}, headers=auth_headers)
        assert r1.status_code == 200, r1.text
        v1 = r1.json()["data"]
        assert v1["version_no"] == 1 and v1["published"] is True

        test_client.put(f"/api/v1/ai/workflows/update/{wid}",
            json={"graph": graph_b}, headers=auth_headers)
        r2 = test_client.post(f"/api/v1/ai/workflows/{wid}/versions",
            json={"remark": "v2"}, headers=auth_headers)
        v2 = r2.json()["data"]
        assert v2["version_no"] == 2 and v2["published"] is False

        lst = test_client.get(f"/api/v1/ai/workflows/{wid}/versions", headers=auth_headers).json()["data"]
        assert [x["version_no"] for x in lst] == [2, 1]

        # 回滚到 v1
        rb = test_client.post(f"/api/v1/ai/workflows/{wid}/versions/{v1['id']}/rollback",
            headers=auth_headers)
        assert rb.status_code == 200, rb.text
        assert rb.json()["data"]["version"] == 1
        detail = test_client.get(f"/api/v1/ai/workflows/detail/{wid}", headers=auth_headers).json()["data"]
        assert detail["graph"]["nodes"][1]["data"]["output_template"] == "A"

        # 发布 v2
        pub = test_client.post(f"/api/v1/ai/workflows/{wid}/versions/{v2['id']}/publish",
            headers=auth_headers)
        assert pub.status_code == 200, pub.text
        assert pub.json()["data"]["version"] == 2
        lst2 = test_client.get(f"/api/v1/ai/workflows/{wid}/versions", headers=auth_headers).json()["data"]
        published = [x for x in lst2 if x["published"]]
        assert len(published) == 1 and published[0]["id"] == v2["id"]
        detail2 = test_client.get(f"/api/v1/ai/workflows/detail/{wid}", headers=auth_headers).json()["data"]
        assert detail2["graph"]["nodes"][1]["data"]["output_template"] == "B"
    finally:
        _delete_wf(test_client, auth_headers, [wid])


def test_template_node():
    """模板节点：{{变量}} 替换与 JSON 自动解析。"""
    import asyncio

    from app.plugin.module_ai.workflow.engine import UiMessageStream, WorkflowEngine

    eng = WorkflowEngine(
        graph={"nodes": [{"id": "t", "type": "template",
                          "data": {"template": "你好 {{name}}", "output_variable": "greet"}}],
               "edges": []},
        variables={"name": "世界"}, messages=[], ms=UiMessageStream(), state={},
    )
    asyncio.run(eng._exec_template(eng.nodes["t"]))
    assert eng.outputs["t"] == "你好 世界"
    assert eng.variables["greet"] == "你好 世界"

    # JSON 模板自动解析为对象
    eng2 = WorkflowEngine(
        graph={"nodes": [{"id": "t", "type": "template",
                          "data": {"template": '{"a": {{n}}}', "output_variable": "obj"}}],
               "edges": []},
        variables={"n": 1}, messages=[], ms=UiMessageStream(), state={},
    )
    asyncio.run(eng2._exec_template(eng2.nodes["t"]))
    assert eng2.outputs["t"] == {"a": 1}


def test_variable_aggregator_node():
    """变量聚合：把多个变量/字段合并为一个对象。"""
    import asyncio

    from app.plugin.module_ai.workflow.engine import UiMessageStream, WorkflowEngine

    eng = WorkflowEngine(
        graph={"nodes": [{"id": "a", "type": "variable_aggregator",
                          "data": {"fields": [
                              {"name": "city", "value": {"__var__": "city"}},
                              {"name": "date", "value": "2026"},
                          ], "output_variable": "info"}}],
               "edges": []},
        variables={"city": "北京"}, messages=[], ms=UiMessageStream(), state={},
    )
    asyncio.run(eng._exec_variable_aggregator(eng.nodes["a"]))
    assert eng.outputs["a"] == {"city": "北京", "date": "2026"}
    assert eng.variables["info"]["city"] == "北京"


def test_answer_node(test_client, auth_headers):
    """回答节点：在流程中任意位置输出文本帧。"""
    wid = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": [{"name": "q"}]}},
                {"id": "ans", "type": "answer", "data": {"output_template": "收到：{{q}}"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{assistant_text}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "ans"},
                {"id": "e2", "source": "ans", "target": "end"},
            ],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wid}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}],
                  "variables": {"q": "你好"}},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "收到：你好" in r.text
        assert '"type": "text-delta"' in r.text
        assert '"type": "node-status"' in r.text
        assert '"status": "success"' in r.text
        assert '"input":' in r.text
        assert '"output":' in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wid])


def test_workflow_sub_workflow_node(test_client, auth_headers):
    """子工作流节点：嵌套调用另一工作流并透传其回复。"""
    sub = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [{"id": "start", "type": "start", "data": {"variables": []}},
                      {"id": "end", "type": "end", "data": {"output_template": "子工作流OK"}}],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]
    parent = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "sw", "type": "sub_workflow", "data": {"workflow_id": sub["id"], "output_variable": "sub_reply"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{sub_reply}}"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "sw"},
                {"id": "e2", "source": "sw", "target": "end"},
            ],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{parent}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert '"reply": "子工作流OK"' in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [parent, sub["id"]])


def test_workflow_loop_node(test_client, auth_headers):
    """循环节点：对列表逐项运行循环体工作流并聚合。"""
    body = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [{"id": "start", "type": "start", "data": {"variables": []}},
                      {"id": "end", "type": "end", "data": {"output_template": "item={{item}}"}}],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]
    parent = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "lp", "type": "loop",
                 "data": {"items": [1, 2, 3], "body_workflow_id": body["id"],
                          "output_variable": "looped", "max_iterations": 10}},
                {"id": "end", "type": "end", "data": {"output_template": "{{looped}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "lp"},
                      {"id": "e2", "source": "lp", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{parent}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "item=1" in r.text and "item=2" in r.text and "item=3" in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [parent, body["id"]])


def test_workflow_parallel_node(test_client, auth_headers):
    """并行节点：并发运行多个分支工作流并聚合。"""
    wf_a = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [{"id": "start", "type": "start", "data": {"variables": []}},
                      {"id": "end", "type": "end", "data": {"output_template": "A结果"}}],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]
    wf_b = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [{"id": "start", "type": "start", "data": {"variables": []}},
                      {"id": "end", "type": "end", "data": {"output_template": "B结果"}}],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]
    parent = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "par", "type": "parallel",
                 "data": {"branches": [{"name": "a", "workflow_id": wf_a["id"]},
                                        {"name": "b", "workflow_id": wf_b["id"]}],
                          "output_variable": "par"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{par}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "par"},
                      {"id": "e2", "source": "par", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{parent}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "A结果" in r.text and "B结果" in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [parent, wf_a["id"], wf_b["id"]])


def test_workflow_doc_extractor(test_client, auth_headers):
    """文档提取节点：内联 HTML 源剥离为纯文本。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "doc", "type": "doc_extractor",
                 "data": {"source": "<p>你好&nbsp;<b>世界</b></p><script>var x=1;</script>",
                          "output_variable": "doctext"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{doctext}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "doc"},
                      {"id": "e2", "source": "doc", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "你好" in r.text and "世界" in r.text
        assert "var x" not in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_web_search(test_client, auth_headers):
    """网页搜索节点：请求本地 mock 搜索 API 并格式化结果。"""
    import http.server
    import json as _json
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = _json.dumps({"results": [
                {"title": "Alpha 结果", "link": "http://a", "snippet": "关于 alpha 的描述"},
                {"title": "Beta", "link": "http://b", "snippet": "beta 介绍"},
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        wf = test_client.post("/api/v1/ai/workflows/create",
            json={"name": _new_name(), "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"variables": []}},
                    {"id": "ws", "type": "web_search",
                     "data": {"query": "alpha",
                              "endpoint": f"http://127.0.0.1:{port}/search?q={{{{query}}}}",
                              "output_variable": "search"}},
                    {"id": "end", "type": "end", "data": {"output_template": "{{search}}"}},
                ],
                "edges": [{"id": "e1", "source": "start", "target": "ws"},
                          {"id": "e2", "source": "ws", "target": "end"}],
            }}, headers=auth_headers).json()["data"]["id"]
        try:
            r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
                json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
                headers=auth_headers)
            assert r.status_code == 200, r.text
            assert "Alpha 结果" in r.text and "beta 介绍" in r.text
            assert "data: [DONE]" in r.text
        finally:
            _delete_wf(test_client, auth_headers, [wf])
    finally:
        srv.shutdown()


def test_workflow_database(test_client, auth_headers):
    """数据库查询节点：对本地 sqlite 文件执行 SQL 返回行。"""
    import os
    import sqlite3
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
        conn.executemany("INSERT INTO t VALUES (?,?)", [(1, "张三"), (2, "李四")])
        conn.commit()
        conn.close()
        dsn = f"sqlite+aiosqlite:///{path}"
        wf = test_client.post("/api/v1/ai/workflows/create",
            json={"name": _new_name(), "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"variables": []}},
                    {"id": "db", "type": "database",
                     "data": {"dsn": dsn, "sql": "SELECT name FROM t WHERE id=1", "output_variable": "rows"}},
                    {"id": "end", "type": "end", "data": {"output_template": "{{rows}}"}},
                ],
                "edges": [{"id": "e1", "source": "start", "target": "db"},
                          {"id": "e2", "source": "db", "target": "end"}],
            }}, headers=auth_headers).json()["data"]["id"]
        try:
            r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
                json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
                headers=auth_headers)
            assert r.status_code == 200, r.text
            assert "张三" in r.text
            assert "data: [DONE]" in r.text
        finally:
            _delete_wf(test_client, auth_headers, [wf])
    finally:
        os.remove(path)


def test_workflow_required_start_var(test_client, auth_headers):
    """start 节点必填变量未传入时，节点运行报错。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start",
                 "data": {"variables": [{"name": "q", "type": "string", "required": True}]}},
                {"id": "end", "type": "end", "data": {"output_template": "{{q}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "缺少必填输入变量" in r.text
        assert '"status": "error"' in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_debug_node(test_client, auth_headers):
    """单节点调试：带变量运行指定节点，返回其输入/输出。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "tpl", "type": "template",
                 "data": {"template": "结果:{{q}}", "output_variable": "out"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{out}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "tpl"},
                      {"id": "e2", "source": "tpl", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/debug-node/stream",
            json={"node_id": "tpl", "variables": {"q": "你好"}},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert '"status": "success"' in r.text
        assert "结果:你好" in r.text
        assert '"input":' in r.text and '"output":' in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_run_logs(test_client, auth_headers):
    """运行后应生成运行历史记录，可列表查询。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "tpl", "type": "template", "data": {"template": "Hi {{q}}", "output_variable": "out"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{out}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "tpl"},
                      {"id": "e2", "source": "tpl", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}],
                  "variables": {"q": "你好"}},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "data: [DONE]" in r.text
        logs = test_client.get(f"/api/v1/ai/workflows/{wf}/run-logs", headers=auth_headers).json()["data"]
        assert logs, "应有运行历史记录"
        assert logs[0]["status"] == "success"
        detail = test_client.get(f"/api/v1/ai/workflows/run-log/{logs[0]['id']}", headers=auth_headers).json()["data"]
        assert detail and detail["node_trace"]
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_disabled_node(test_client, auth_headers):
    """禁用节点：运行被跳过，不产生其输出变量。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "pv", "type": "variable",
                 "data": {"name": "a", "value": "hello", "enabled": False}},
                {"id": "end", "type": "end", "data": {"output_template": "{{a}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "pv"},
                      {"id": "e2", "source": "pv", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert '"status": "skipped"' in r.text
        assert "hello" not in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_step_execution(test_client, auth_headers):
    """逐步执行：每次一个节点，frontier 续跑至结束。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": [{"name": "q"}]}},
                {"id": "v", "type": "variable", "data": {"name": "a", "value": "{{q}}"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{a}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "v"},
                      {"id": "e2", "source": "v", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        run_id = None
        seen_start = seen_var = seen_end = False
        for _ in range(5):
            r = test_client.post(f"/api/v1/ai/workflows/{wf}/step/stream",
                json={"run_id": run_id, "variables": {"q": "你好"},
                      "messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
                headers=auth_headers)
            assert r.status_code == 200, r.text
            if '"type": "node-status"' not in r.text:
                print("STEP_RESP", r.text)
            assert '"type": "node-status"' in r.text
            if "开始" in r.text:
                seen_start = True
            if "变量赋值" in r.text:
                seen_var = True
            if "结束" in r.text:
                seen_end = True
            import re as _re
            m = _re.search(r'"run_id":\s*"([^"]+)"', r.text)
            run_id = m.group(1) if m else run_id
            if '"done": true' in r.text:
                break
        assert seen_start and seen_var and seen_end, (seen_start, seen_var, seen_end)
        assert "你好" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_condition_and_or(test_client, auth_headers):
    """条件节点：多条件 AND 表达式正确路由到真/假分支。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "v", "type": "variable", "data": {"name": "a", "value": 5}},
                {"id": "c", "type": "condition", "data": {"expression": "a > 3 and a < 10"}},
                {"id": "ans", "type": "answer", "data": {"output_template": "命中"}},
                {"id": "end", "type": "end", "data": {"output_template": "未命中"}},
            ],
            "edges": [
                {"id": "e1", "source": "start", "target": "v"},
                {"id": "e2", "source": "v", "target": "c"},
                {"id": "e3", "source": "c", "target": "ans", "sourceHandle": "true"},
                {"id": "e4", "source": "c", "target": "end", "sourceHandle": "false"},
            ],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "命中" in r.text and "未命中" not in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_stats(test_client, auth_headers):
    """工作流运行统计聚合。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "end", "type": "end", "data": {"output_template": "ok"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        s = test_client.get(f"/api/v1/ai/workflows/{wf}/stats", headers=auth_headers).json()["data"]
        assert s["total"] >= 1
        assert s["success"] >= 1
        assert "success_rate" in s and "avg_ms" in s
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_share(test_client, auth_headers):
    """公开分享：生成令牌 + 匿名受限运行，高危节点被跳过。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "http", "type": "http",
                 "data": {"method": "GET", "url": "http://127.0.0.1:1/x", "output_variable": "h"}},
                {"id": "tpl", "type": "template",
                 "data": {"template": "结果", "output_variable": "out"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{out}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "http"},
                      {"id": "e2", "source": "http", "target": "tpl"},
                      {"id": "e3", "source": "tpl", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        sh = test_client.post(f"/api/v1/ai/workflows/{wf}/share", headers=auth_headers).json()["data"]
        token = sh["token"]
        assert token
        r = test_client.post("/api/v1/ai/workflows/share/run",
            json={"token": token, "message": "hi"}, headers=auth_headers)
        assert r.status_code == 200, r.text
        # 受限模式 http 节点被跳过，但模板/结束仍执行
        assert '"status": "skipped"' in r.text
        assert "结果" in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_timeout(test_client, auth_headers):
    """超时：timeout_seconds 较小且有耗时代码节点时，后续节点触发超时中止。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "code", "type": "code",
                 "data": {"code": "x=0\nwhile x < 80000000: x += 1", "inputs": {}, "output_variable": "x"}},
                {"id": "end", "type": "end", "data": {"output_template": "{{x}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "code"},
                      {"id": "e2", "source": "code", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}],
                  "timeout_seconds": 1},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "运行超时" in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_node_retry(test_client, auth_headers):
    """节点重试：retry 配置下失败节点重试后仍失败会中止（不崩溃）。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "code", "type": "code",
                 "data": {"code": "x = 1/0", "inputs": {}, "output_variable": "x", "retry": 2}},
                {"id": "end", "type": "end", "data": {"output_template": "{{x}}"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "code"},
                      {"id": "e2", "source": "code", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert '"status": "error"' in r.text
        assert "data: [DONE]" in r.text
    finally:
        _delete_wf(test_client, auth_headers, [wf])


def test_workflow_schedule(test_client, auth_headers):
    """定时调度：保存 cron 配置 + 立即运行。"""
    wf = test_client.post("/api/v1/ai/workflows/create",
        json={"name": _new_name(), "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "end", "type": "end", "data": {"output_template": "ok"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        }}, headers=auth_headers).json()["data"]["id"]
    try:
        s = test_client.put(f"/api/v1/ai/workflows/{wf}/schedule",
            json={"cron": "0 * * * *", "enabled": True}, headers=auth_headers).json()["data"]
        assert s["enabled"] is True
        assert s["cron"] == "0 * * * *"
        r = test_client.post(f"/api/v1/ai/workflows/{wf}/schedule/run", headers=auth_headers)
        assert r.status_code == 200, r.text
        # 运行日志应新增一条
        logs = test_client.get(f"/api/v1/ai/workflows/{wf}/run-logs", headers=auth_headers).json()["data"]
        assert logs and logs[0]["status"] == "success"
    finally:
        _delete_wf(test_client, auth_headers, [wf])
