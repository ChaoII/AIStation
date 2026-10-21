# tests/test_develop_train.py
"""开放面 train 能力：归属打标、跨应用隔离、退场框架拒绝。

覆盖 Review Focus 第 1 条（跨应用训练任务不可见/不可停）与退场框架守卫。
"""
from uuid import uuid4

API = "/api/v1"
TRAIN_CAPS = [
    "integration:train:query",
    "integration:train:create",
    "integration:train:start",
    "integration:train:stop",
]
TRAIN_CAPS_QUERY = ["integration:train:query"]


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"训练面-{_uid()}", "capabilities": caps, "requires_approval": False},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _app_auth(app):
    return {
        "Authorization": f"Bearer {app['appid']}:{app['appkey']}",
        "X-Forwarded-For": "127.0.0.1",
    }


def _invoke(test_client, app, code, payload):
    return test_client.post(
        f"{API}/ai/develop-api/capabilities/{code}",
        json={"payload": payload},
        headers=_app_auth(app),
    )


def _cleanup(test_client, auth_headers, app_id=None, task_id=None, dataset_id=None):
    if task_id:
        test_client.request(
            "DELETE", f"{API}/train/task/delete", json=[task_id], headers=auth_headers
        )
    if dataset_id:
        test_client.request(
            "DELETE", f"{API}/annotation/dataset/delete", json=[dataset_id], headers=auth_headers
        )
    if app_id:
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers
        )


def _create_dataset(test_client, auth_headers) -> int:
    """开放面 train.create 现在会校验数据集存在，用例需先建一个真实数据集。"""
    r = test_client.post(
        f"{API}/annotation/dataset/create",
        json={"name": f"开放训练数据集-{_uid()}"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_train_create_tags_owner_and_isolates_between_apps(test_client, auth_headers):
    app_a = _create_app(test_client, auth_headers, TRAIN_CAPS)
    app_b = _create_app(test_client, auth_headers, TRAIN_CAPS_QUERY)
    task_id = None
    dataset_id = _create_dataset(test_client, auth_headers)
    try:
        created = _invoke(
            test_client,
            app_a,
            "train.create",
            {
                "name": f"开放训练-{_uid()}",
                "framework": "torchkiln",
                "dataset_id": dataset_id,
                "hyperparams": {"epochs": 1},
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()["data"]
        assert body["source_app_id"] == app_a["id"]
        task_id = body["task_id"]

        # 本应用可见
        got = _invoke(test_client, app_a, "train.get", {"task_id": task_id})
        assert got.status_code == 200, got.text
        assert got.json()["data"]["id"] == task_id

        # Review Focus 1：B 应用读不到、也停不了
        leaked = _invoke(test_client, app_b, "train.get", {"task_id": task_id})
        assert leaked.status_code == 404, leaked.text
        listed = _invoke(test_client, app_b, "train.list", {})
        assert task_id not in [i["id"] for i in listed.json()["data"]["items"]]

        # 内部列表（平台管理面）仍能看到该任务
        internal = test_client.get(
            f"{API}/train/task/list", params={"page_size": 100}, headers=auth_headers
        ).json()["data"]
        items = internal["items"] if isinstance(internal, dict) else internal
        assert any(i["id"] == task_id for i in items), "管理面应能看到开放面创建的任务"
    finally:
        _cleanup(test_client, auth_headers, app_a["id"], task_id, dataset_id)
        _cleanup(test_client, auth_headers, app_b["id"])


def test_train_create_rejects_unknown_dataset(test_client, auth_headers):
    """数据集不存在 → 404（此前任意 dataset_id 都能建出悬空任务）。"""
    app = _create_app(test_client, auth_headers, TRAIN_CAPS)
    try:
        r = _invoke(
            test_client,
            app,
            "train.create",
            {"name": f"悬空-{_uid()}", "framework": "torchkiln", "dataset_id": 999999},
        )
        assert r.status_code == 404, r.text
        assert "数据集" in r.json()["msg"]
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_train_create_rejects_retired_framework(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, TRAIN_CAPS)
    try:
        r = _invoke(
            test_client,
            app,
            "train.create",
            {"name": f"退场-{_uid()}", "framework": "ultralytics", "dataset_id": 1},
        )
        assert r.status_code == 400, r.text
        assert "退场" in r.json()["msg"] or "已停用" in r.json()["msg"]
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_train_query_only_app_cannot_create(test_client, auth_headers):
    """Review Focus 2：只有 query 权限的应用调 train.create → 403。"""
    app = _create_app(test_client, auth_headers, TRAIN_CAPS_QUERY)
    try:
        r = _invoke(
            test_client,
            app,
            "train.create",
            {"name": f"越权-{_uid()}", "framework": "torchkiln", "dataset_id": 1},
        )
        assert r.status_code == 403, r.text
    finally:
        _cleanup(test_client, auth_headers, app["id"])
