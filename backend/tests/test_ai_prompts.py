"""提示词工作台：CRUD 与 render_prompt。"""
from app.plugin.module_ai.prompts.service import render_prompt


def test_render_prompt_substitutes_and_preserves_unknown():
    """已定义变量被替换，未知变量原样保留，并按【类型】前缀拼接。"""
    blocks = [
        {"type": "system", "content": "你是 {{name}} 助手"},
        {"type": "instruction", "content": "回答 {{question}}，{{missing}} 原样保留"},
    ]
    out = render_prompt(blocks, {"name": "小助手", "question": "你好"})
    assert "【system】" in out
    assert "【instruction】" in out
    assert "你是 小助手 助手" in out
    assert "回答 你好，{{missing}} 原样保留" in out


def test_render_prompt_empty():
    """空块返回空串。"""
    assert render_prompt([], {}) == ""
    assert render_prompt(None, None) == ""


def test_prompt_crud(test_client, auth_headers):
    """创建 → 列表含 blocks/variables → 详情 → 更新 → 删除。"""
    r = test_client.post(
        "/api/v1/ai/prompts/create",
        json={
            "name": "pytest-prompt",
            "category": "qa",
            "blocks": [
                {"type": "system", "content": "你是 {{name}}"},
                {"type": "instruction", "content": "回答 {{question}}"},
            ],
            "variables": ["name", "question"],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    try:
        lst = test_client.get("/api/v1/ai/prompts/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == pid)
        assert row["blocks"][0]["type"] == "system"
        assert row["variables"] == ["name", "question"]
        assert row["enabled"] is True
        assert row["version"] == 1

        detail = test_client.get(f"/api/v1/ai/prompts/detail/{pid}", headers=auth_headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["name"] == "pytest-prompt"

        upd = test_client.put(
            f"/api/v1/ai/prompts/update/{pid}",
            json={
                "name": "pytest-prompt-2",
                "enabled": False,
                "blocks": [{"type": "output", "content": "仅输出 {{answer}}"}],
            },
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        body = upd.json()["data"]
        assert body["enabled"] is False
        assert body["version"] == 2
        assert body["blocks"][0]["type"] == "output"
    finally:
        dele = test_client.request(
            "DELETE", "/api/v1/ai/prompts/delete", json=[pid], headers=auth_headers
        )
        assert dele.status_code == 200, dele.text

    lst2 = test_client.get("/api/v1/ai/prompts/list", headers=auth_headers).json()["data"]
    assert all(x["id"] != pid for x in lst2)


def test_prompt_reject_invalid_block(test_client, auth_headers):
    """非法块类型应被拒绝。"""
    r = test_client.post(
        "/api/v1/ai/prompts/create",
        json={
            "name": "pytest-prompt-bad",
            "blocks": [{"type": "not-a-type", "content": "x"}],
        },
        headers=auth_headers,
    )
    assert r.status_code == 422, r.text
