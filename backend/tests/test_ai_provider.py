"""提供商 CRUD 与脱敏。"""


def test_provider_crud(test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/providers/create",
        json={
            "name": "pytest-provider",
            "protocol": "openai",
            "base_url": "https://example.com/v1",
            "api_key": "sk-provider-1234567890",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    try:
        lst = test_client.get("/api/v1/ai/providers/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == pid)
        assert "api_key" not in row
        assert row["api_key_masked"].startswith("sk-p")

        upd = test_client.put(
            f"/api/v1/ai/providers/update/{pid}",
            json={"name": "pytest-provider-2"},
            headers=auth_headers,
        )
        assert upd.status_code == 200
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/providers/delete", json=[pid], headers=auth_headers
        )
