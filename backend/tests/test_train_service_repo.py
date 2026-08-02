"""TrainService 仓库/版本 HTTP 测试。"""
from fastapi.testclient import TestClient


def _login(test_client: TestClient) -> dict:
    # X-Forwarded-For 必需：登录接口的 OperationLogRoute 会校验 request_ip，
    # TestClient 默认 client.host="testclient" 不是合法 IP，会返回 400。
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": "admin", "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_model_repo_list(test_client: TestClient):
    headers = _login(test_client)
    resp = test_client.get("/api/v1/train/model/repos?page_no=1&page_size=5", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert "items" in body["data"]
    assert "has_next" in body["data"]


def test_model_versions_list(test_client: TestClient):
    headers = _login(test_client)
    # 取第一个仓库（若迁移已执行则有数据；空库则跳过断言列表内容，仅断言结构）
    repos = test_client.get("/api/v1/train/model/repos?page_no=1&page_size=5", headers=headers).json()["data"]["items"]
    if repos:
        rid = repos[0]["id"]
        resp = test_client.get(f"/api/v1/train/model/{rid}/versions", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


def test_model_list_backcompat(test_client: TestClient):
    """旧接口 /model/list 仍可用（兼容现有前端）。"""
    headers = _login(test_client)
    resp = test_client.get("/api/v1/train/model/list?page_no=1&page_size=5", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
