"""大模型配置 CRUD / 脱敏 / 默认唯一 / 运行时取用。"""
import asyncio


def _cleanup(test_client, auth_headers, ids):
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/model/delete", json=ids, headers=auth_headers
        )


def test_ai_model_crud_and_mask(test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/model/create",
        json={
            "name": "pytest-model",
            "base_url": "http://127.0.0.1:9/v1",
            "api_key": "sk-1234567890abcdef",
            "model": "deepseek-chat",
            "is_default": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    mid = r.json()["data"]["id"]
    try:
        lst = test_client.get("/api/v1/ai/model/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == mid)
        assert "api_key" not in row
        assert row["api_key_masked"].startswith("sk-1")
        assert row["is_default"] is True

        # 运行时取默认模型
        from app.plugin.module_ai.provider.service import AiModelService

        runtime = asyncio.run(AiModelService.get_runtime_model())
        assert runtime and runtime["model"] == "deepseek-chat"
        assert runtime["api_key"] == "sk-1234567890abcdef"
    finally:
        _cleanup(test_client, auth_headers, [mid])


def test_ai_model_default_unique_and_key_preserve(test_client, auth_headers):
    r1 = test_client.post(
        "/api/v1/ai/model/create",
        json={"name": "pytest-a", "base_url": "http://x", "api_key": "sk-aaaaaaaaaaaa", "model": "m1", "is_default": True},
        headers=auth_headers,
    )
    r2 = test_client.post(
        "/api/v1/ai/model/create",
        json={"name": "pytest-b", "base_url": "http://y", "api_key": "sk-bbbbbbbbbbbb", "model": "m2"},
        headers=auth_headers,
    )
    id1, id2 = r1.json()["data"]["id"], r2.json()["data"]["id"]
    try:
        d = test_client.post(f"/api/v1/ai/model/set-default/{id2}", headers=auth_headers)
        assert d.status_code == 200
        lst = test_client.get("/api/v1/ai/model/list", headers=auth_headers).json()["data"]
        defaults = [x for x in lst if x["is_default"]]
        assert len(defaults) == 1 and defaults[0]["id"] == id2

        # 更新不传 api_key，原 key 保留
        test_client.put(
            f"/api/v1/ai/model/update/{id1}",
            json={"name": "pytest-a2"},
            headers=auth_headers,
        )
        from app.plugin.module_ai.provider.service import AiModelService

        async def _get_key():
            from app.core.database import async_db_session

            m = await AiModelService.list_models()
            return next(x for x in m if x["id"] == id1)

        # 通过直接查询验证 key 未被覆盖为空
        import asyncio as _a

        from app.plugin.module_ai.provider.model import AiModelModel
        from app.core.database import async_db_session

        async def _read_key():
            async with async_db_session() as db:
                m = await db.get(AiModelModel, id1)
                return m.api_key

        assert _a.run(_read_key()) == "sk-aaaaaaaaaaaa"
    finally:
        _cleanup(test_client, auth_headers, [id1, id2])
