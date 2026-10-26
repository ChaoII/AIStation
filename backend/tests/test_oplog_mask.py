"""操作日志敏感字段脱敏：password/token/secret 等键在请求/响应体中被掩码。"""
from app.core.router_class import _mask_sensitive


def test_mask_sensitive_masks_secret_keys_and_keeps_others():
    data = {
        "username": "admin",
        "password": "secretpwd",
        "new_password": "x",
        "user": {"api_key": "abc"},
        "items": [{"token": "t"}, {"name": "ok"}],
        "geometry": {"width": 10},
        "appid": "ai_demo",
    }
    out = _mask_sensitive(data)
    assert out["password"] == "****"
    assert out["new_password"] == "****"
    assert out["user"]["api_key"] == "****"
    assert out["items"][0]["token"] == "****"
    # 非敏感字段原样保留
    assert out["username"] == "admin"
    assert out["items"][1]["name"] == "ok"
    assert out["geometry"]["width"] == 10
    assert out["appid"] == "ai_demo"


def test_mask_sensitive_lists_and_primitives():
    assert _mask_sensitive([{"password": "p"}, 1, "s"]) == [{"password": "****"}, 1, "s"]
    assert _mask_sensitive("plain") == "plain"
    assert _mask_sensitive(123) == 123
    assert _mask_sensitive(None) is None
