"""审计字段落库测试：创建训练仓库后 created_id/updated_id 非空。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_model_repo_create_sets_audit_fields(test_client: TestClient, auth_headers: dict):
    name = f"audit-{uuid4().hex[:8]}"
    created = test_client.post(
        "/api/v1/train/model/repos",
        json={"name": name, "framework": "ultralytics"},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text

    listing = test_client.get(
        "/api/v1/train/model/list", params={"name": name, "page_no": 1, "page_size": 5},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert listing, "新建的模型版本应能在 /model/list 查询到"
    row = listing[0]
    assert row["created_id"] is not None
    assert row["updated_id"] is not None
