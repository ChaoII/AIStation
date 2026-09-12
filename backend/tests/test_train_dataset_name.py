"""训练/评估数据集名称 enrich 与预测 name 搜索测试。"""


def _create_dataset(test_client, auth_headers, name: str) -> int:
    resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": name},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_train_task_dataset_name(test_client, auth_headers):
    ds_id = _create_dataset(test_client, auth_headers, "P4名称测试集")
    created = test_client.post(
        "/api/v1/train/task/create",
        json={
            "name": "P4名称测试任务",
            "framework": "ultralytics",
            "dataset_id": ds_id,
            "hyperparams": {},
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["data"]["id"]
    try:
        detail = test_client.get(
            f"/api/v1/train/task/{task_id}/detail", headers=auth_headers
        ).json()["data"]
        assert detail["dataset_name"] == "P4名称测试集"

        listing = test_client.get(
            "/api/v1/train/task/list", headers=auth_headers
        ).json()["data"]
        row = next(i for i in listing["items"] if i["id"] == task_id)
        assert row["dataset_name"] == "P4名称测试集"
    finally:
        test_client.request(
            "DELETE", "/api/v1/train/task/delete", json=[task_id], headers=auth_headers
        )
        test_client.request(
            "DELETE",
            "/api/v1/annotation/dataset/delete",
            json=[ds_id],
            headers=auth_headers,
        )


def test_eval_list_has_eval_dataset_name_key(test_client, auth_headers):
    resp = test_client.get("/api/v1/train/eval/list", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    for item in data["items"]:
        assert "eval_dataset_name" in item


def test_predict_list_accepts_name_param(test_client, auth_headers):
    resp = test_client.get(
        "/api/v1/train/predict/list?name=不存在的模型", headers=auth_headers
    )
    assert resp.status_code == 200
