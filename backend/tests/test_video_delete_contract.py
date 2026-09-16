"""视频模块删除接口契约测试：裸数组可用，包裹对象 422。"""
from fastapi.testclient import TestClient


def test_delete_accepts_raw_array(test_client: TestClient, auth_headers: dict):
    resp = test_client.request(
        "DELETE", "/api/v1/video/algorithm/delete", json=[999999], headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


def test_delete_rejects_wrapped_object(test_client: TestClient, auth_headers: dict):
    resp = test_client.request(
        "DELETE", "/api/v1/video/algorithm/delete", json={"ids": [999999]}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_algorithm_detail_missing_returns_404(test_client: TestClient, auth_headers: dict):
    resp = test_client.get("/api/v1/video/algorithm/detail/999999", headers=auth_headers)
    assert resp.status_code == 404
