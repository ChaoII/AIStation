"""协作 WS 鉴权与 presence 助手测试。"""
import json
from datetime import datetime, timedelta

from app.api.v1.module_annotation.collaboration import controller as C


def test_parse_ws_user_invalid():
    assert C.parse_ws_user(None) is None
    assert C.parse_ws_user("not-a-jwt") is None


def test_parse_ws_user_valid():
    from app.api.v1.module_system.auth.schema import JWTPayloadSchema
    from app.core.security import create_access_token

    token = create_access_token(
        JWTPayloadSchema(
            sub=json.dumps({"user_id": 7, "user_name": "alice"}),
            is_refresh=False,
            exp=datetime.now() + timedelta(minutes=5),
        )
    )
    assert C.parse_ws_user(token) == (7, "alice")


def test_presence_list_empty():
    assert C.presence_list(999999) == []
