# tests/test_embed_sdk.py
"""SDK 静态端点：公开可取、零凭证、契约标记齐全。"""
API = "/api/v1"


def test_sdk_js_served_publicly_without_secret(test_client):
    r = test_client.get(f"{API}/ai/embed/sdk.js")
    assert r.status_code == 200, r.text
    assert "javascript" in r.headers["content-type"]
    text = r.text
    # 契约标记：入口、事件、下行命令
    for marker in ("AiAssistant", "init", "setToken", "sendMessage", "ai-host", "ai-embed"):
        assert marker in text, marker
    # 只允许「安全警示语」里出现 appkey 字样，不得出现任何真实/示例密钥或凭证头
    assert "stew7" not in text
    assert "Authorization" not in text
