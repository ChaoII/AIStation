"""异常响应脱敏测试（审计 #8 余项：verbose error leakage）。

覆盖：
- 非 DEBUG（生产）下，数据库/请求校验异常的响应不再携带原始异常文本或请求体；
- DEBUG（开发）下仍保留明细，便于联调；
- 参数校验接口集成验证：生产下 data 为 null。
"""
from app.config.setting import settings
from app.core.exceptions import _safe_error_data


def test_safe_error_data_redacts_outside_debug(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    assert _safe_error_data("数据库连接失败：password=xxx") is None
    assert _safe_error_data({"username": "admin", "password": "123456"}) is None


def test_safe_error_data_keeps_detail_in_debug(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    assert _safe_error_data("boom") == "boom"
    assert _safe_error_data([1, 2]) == [1, 2]


def test_validation_error_redacts_body_in_prod(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    resp = test_client.post(
        "/api/v1/video/edge/create",
        headers=auth_headers,
        json={"code": "no-name", "secret": "leaked-secret"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("data") is None
    assert "leaked-secret" not in resp.text


def test_validation_error_keeps_body_in_debug(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    resp = test_client.post(
        "/api/v1/video/edge/create",
        headers=auth_headers,
        json={"code": "no-name"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("data") is not None
