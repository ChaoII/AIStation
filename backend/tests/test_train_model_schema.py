"""测试模型仓库/版本双表结构和编辑更新契约。"""
import time

from app.plugin.module_train.model import TrainModel, TrainModelRepo
from app.plugin.module_train.schema import ModelUpdateSchema


def test_train_model_repo_table_declared():
    assert TrainModelRepo.__tablename__ == "train_model_repos"
    assert "name" in TrainModelRepo.__table__.columns


def test_train_model_has_repo_id_column():
    assert "repo_id" in TrainModel.__table__.columns


def test_model_update_schema_keeps_status():
    """status 未显式传入时应被 exclude_none 剔除；传入时应保留。"""
    assert ModelUpdateSchema().model_dump(exclude_none=True) == {}
    data = ModelUpdateSchema(status="released", annotation_dataset_id=3).model_dump(exclude_none=True)
    assert data == {"status": "released", "annotation_dataset_id": 3}


def test_model_update_persists_status(test_client, auth_headers):
    """编辑模型 status/描述后应落库，详情接口可回显。"""
    headers = auth_headers
    name = f"pytest_status_{int(time.time())}"
    created = test_client.post(
        "/api/v1/train/model/create",
        json={"name": name, "framework": "ultralytics"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    model_id = created.json()["data"]["id"]
    try:
        resp = test_client.put(
            f"/api/v1/train/model/update/{model_id}",
            json={"status": "released", "description": "状态落库测试"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        detail = test_client.get(f"/api/v1/train/model/detail/{model_id}", headers=headers)
        assert detail.status_code == 200, detail.text
        data = detail.json()["data"]
        assert data["status"] == "released"
        assert data["description"] == "状态落库测试"
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/train/model/delete",
            json=[model_id],
            headers=headers,
        )
