"""软删同码重建测试：边缘设备软删后仍占用 code 唯一键，同码重建应恢复软删行而非 500。"""
from uuid import uuid4

from fastapi.testclient import TestClient


def test_recreate_edge_device_with_soft_deleted_code(
    test_client: TestClient, auth_headers: dict
) -> None:
    code = f"edge-recreate-{uuid4().hex[:8]}"
    payload = {
        "name": "同码重建设备",
        "code": code,
        "capabilities": {"model_families": ["det"], "backends": ["ort"], "max_channels": 4},
    }

    # 1) 先正常创建
    created = test_client.post("/api/v1/video/edge/create", json=payload, headers=auth_headers)
    assert created.status_code == 200, created.text
    edge_id = created.json()["data"]["id"]

    # 2) 软删除（软删行仍占用 code 唯一键）
    deleted = test_client.request(
        "DELETE", "/api/v1/video/edge/delete", json=[edge_id], headers=auth_headers
    )
    assert deleted.status_code == 200, deleted.text

    # 断言软删已生效：列表（默认过滤 is_deleted）不应再出现该 code
    listed_after_delete = test_client.get(
        "/api/v1/video/edge/list",
        params={"code": code, "page_no": 1, "page_size": 50},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert code not in [i["code"] for i in listed_after_delete]

    # 3) 同码重建：应恢复软删行并成功返回设备，而不是 UniqueViolationError/500
    recreated = test_client.post("/api/v1/video/edge/create", json=payload, headers=auth_headers)
    assert recreated.status_code == 200, recreated.text
    body = recreated.json()["data"]
    assert body["code"] == code
    assert body["name"] == payload["name"]

    # 4) 重建后应重新可见
    listed_after_recreate = test_client.get(
        "/api/v1/video/edge/list",
        params={"code": code, "page_no": 1, "page_size": 50},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert code in [i["code"] for i in listed_after_recreate]
