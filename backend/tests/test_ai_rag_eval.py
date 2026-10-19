"""评测指标与运行测试。"""
import asyncio
import uuid


def _run(coro):
    return asyncio.run(coro)


def _wait_task(task_id: int, limit: int = 40) -> dict:
    from app.plugin.module_ai.knowledge import tasks
    from app.plugin.module_ai.knowledge.tasks import worker

    for _ in range(limit):
        cur = _run(tasks.get_task(task_id))
        if cur and cur["status"] in ("succeeded", "failed", "canceled"):
            return cur
        _run(worker.run_worker(max_iterations=1))
    return _run(tasks.get_task(task_id))


def test_metrics_hand_computed():
    from app.plugin.module_ai.knowledge.eval import metrics

    retrieved = [3, 1, 2]
    expected = [1, 2]
    assert metrics.recall_at_k(retrieved, expected, 2) == 0.5
    assert metrics.precision_at_k(retrieved, expected, 2) == 0.5
    assert metrics.mrr(retrieved, expected) == 0.5
    assert round(metrics.ndcg_at_k(retrieved, expected, 3), 4) == 0.6934


def test_metrics_degenerate_inputs():
    from app.plugin.module_ai.knowledge.eval import metrics

    assert metrics.recall_at_k([], [1], 5) == 0.0
    assert metrics.mrr([], []) == 0.0
    assert metrics.recall_at_k([1], [], 5) == 0.0
    assert metrics.evaluate_items([], 5)["n"] == 0


def test_eval_end_to_end(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = test_client.post(
        "/api/v1/ai/knowledge/bases/create",
        json={"name": f"pytest_eval_{uuid.uuid4().hex[:8]}", "enabled": True},
        headers=auth_headers,
    ).json()["data"]["id"]
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "e.txt", "content": "智能体编排说明"},
            headers=auth_headers,
        )
        chunks = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        chunk_id = chunks[0]["id"]

        eval_set = test_client.post(
            "/api/v1/ai/knowledge/eval/sets",
            json={"name": "回归集", "kb_ids": [kb_id]},
            headers=auth_headers,
        ).json()["data"]
        item = test_client.post(
            f"/api/v1/ai/knowledge/eval/sets/{eval_set['id']}/items",
            json={"query": "智能体", "expected_chunk_ids": [chunk_id]},
            headers=auth_headers,
        )
        assert item.status_code == 200, item.text

        started = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/eval/run",
            json={"set_id": eval_set["id"], "config": {"top_k": 3, "use_rerank": False}},
            headers=auth_headers,
        )
        assert started.status_code == 200, started.text
        task_id = started.json()["data"]["task_id"]
        assert _wait_task(task_id)["status"] == "succeeded"

        runs = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/eval/runs", headers=auth_headers
        ).json()["data"]
        assert runs and runs[0]["status"] == "succeeded"
        assert runs[0]["metrics"]["n"] == 1
        assert 0.0 <= runs[0]["metrics"]["recall"] <= 1.0
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/knowledge/bases/delete",
            json=[kb_id],
            headers=auth_headers,
        )
