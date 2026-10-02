"""AI 低代码工作流：CRUD、流式运行（start→llm→end）与条件分支。"""
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
