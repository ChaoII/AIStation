"""文本NER任务 classes 形状校验测试：dict（{entities, relations}）与 list 的分派。

验证：
- text_ner 任务创建/更新接受 ``{entities:[...], relations:[...]}`` 字典并持久化；
- text_ner 传 list 被拒绝（清晰错误）；
- 非文本任务传 dict 被拒绝；
- 非文本任务传 list 仍成功（无回归）。
"""
import uuid

from fastapi.testclient import TestClient


def _create_dataset(test_client: TestClient, auth_headers: dict) -> int:
    resp = test_client.post(
        "/api/v1/annotation/dataset/create",
        json={"name": f"ner-cls-{uuid.uuid4().hex[:8]}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _create_task(test_client, auth_headers, dataset_id, task_type, classes):
    return test_client.post(
        "/api/v1/annotation/task/create",
        json={
            "dataset_id": dataset_id,
            "name": f"t-{uuid.uuid4().hex[:8]}",
            "task_type": task_type,
            "classes": classes,
        },
        headers=auth_headers,
    )


def test_create_text_ner_accepts_dict_classes(test_client, auth_headers):
    """text_ner 任务：classes 为 dict {entities, relations} 应创建成功并持久化。"""
    ds_id = _create_dataset(test_client, auth_headers)
    classes = {
        "entities": [{"id": 1, "name": "人物", "color": "#409eff"}],
        "relations": [{"id": 1, "name": "隶属"}],
    }
    resp = _create_task(test_client, auth_headers, ds_id, "text_ner", classes)
    assert resp.status_code == 200, resp.text
    task = resp.json()["data"]
    assert task["task_type"] == "text_ner"
    assert task["classes"] == classes


def test_create_text_ner_rejects_list_classes(test_client, auth_headers):
    """text_ner 任务：classes 传 list 应被拒绝并给出清晰错误。"""
    ds_id = _create_dataset(test_client, auth_headers)
    resp = _create_task(test_client, auth_headers, ds_id, "text_ner", [{"name": "x"}])
    assert resp.status_code == 400, resp.text
    assert "entities" in resp.json()["msg"] or "字典" in resp.json()["msg"]


def test_create_non_text_rejects_dict_classes(test_client, auth_headers):
    """非文本任务：classes 传 dict 应被拒绝。"""
    ds_id = _create_dataset(test_client, auth_headers)
    resp = _create_task(
        test_client, auth_headers, ds_id, "detection", {"entities": [], "relations": []}
    )
    assert resp.status_code == 400, resp.text
    assert "数组" in resp.json()["msg"] or "list" in resp.json()["msg"]


def test_create_non_text_accepts_list_classes(test_client, auth_headers):
    """非文本任务：classes 传 list 应创建成功（无回归）。"""
    ds_id = _create_dataset(test_client, auth_headers)
    classes = [{"id": 1, "name": "person", "color": "#409eff"}]
    resp = _create_task(test_client, auth_headers, ds_id, "detection", classes)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["classes"] == classes


def test_update_text_ner_classes_dict(test_client, auth_headers):
    """更新 text_ner 任务的 classes 字典应成功。"""
    ds_id = _create_dataset(test_client, auth_headers)
    initial = {"entities": [{"id": 1, "name": "人物", "color": "#409eff"}], "relations": []}
    created = _create_task(test_client, auth_headers, ds_id, "text_ner", initial)
    assert created.status_code == 200, created.text
    task_id = created.json()["data"]["id"]

    new_classes = {
        "entities": [
            {"id": 1, "name": "人物", "color": "#409eff"},
            {"id": 2, "name": "地点", "color": "#67c23a"},
        ],
        "relations": [{"id": 2, "name": "位于"}],
    }
    resp = test_client.put(
        f"/api/v1/annotation/task/update/{task_id}",
        json={"classes": new_classes},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["classes"] == new_classes
