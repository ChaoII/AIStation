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


class _FakeResp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    @property
    def text(self):
        return str(self._data)

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self.data = data or {"data": [{"id": "gpt-4o"}, {"id": "text-embedding-3-small"}]}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        return _FakeResp(self.status_code, self.data)


class _FakeAsyncClientFactory:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self.data = data

    def __call__(self, *a, **kw):
        return _FakeClient(self.status_code, self.data)


def test_provider_test_and_remote(monkeypatch, test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/providers/create",
        json={
            "name": "pytest-provider-conn",
            "protocol": "openai",
            "base_url": "https://example.com/v1",
            "api_key": "sk-provider-1234567890",
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    try:
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClientFactory())
        tr = test_client.get(f"/api/v1/ai/providers/test/{pid}", headers=auth_headers)
        assert tr.status_code == 200
        assert tr.json()["data"]["ok"] is True

        rm = test_client.get(
            f"/api/v1/ai/providers/remote-models/{pid}", headers=auth_headers
        ).json()["data"]
        assert rm == ["gpt-4o", "text-embedding-3-small"]

        # 401 → 测试返回 ok=False
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClientFactory(status_code=401))
        tr2 = test_client.get(f"/api/v1/ai/providers/test/{pid}", headers=auth_headers)
        assert tr2.json()["data"]["ok"] is False
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/providers/delete", json=[pid], headers=auth_headers
        )
