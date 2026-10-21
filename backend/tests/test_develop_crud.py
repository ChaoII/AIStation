# tests/test_develop_crud.py
#
# 覆盖 AI 集成开放平台「应用」的纯逻辑（appid/appkey）与 CRUD / 鉴权（verify_appkey）。
# 说明：项目未启用 pytest-asyncio，故 DB 用例统一沿用本仓库「asyncio.run 包一层」的
# 既有写法（参照 test_mcp_runtime.py），并使用 test_client 夹具确保应用生命周期
# （建表）已被触发；PYTEST_NO_APP=1 时这些用例会被自动 skip。
#
# 关键断言：
# - appkey 只在 create/reset 返回一次明文，列表/详情绝不出现 appkey_hash 或明文；
# - verify_appkey 对「禁用/过期」应用一律返回 None。
import asyncio
import hashlib

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.develop.schema import DevelopCreateSchema, DevelopUpdateSchema
from app.plugin.module_ai.develop.service import DevelopService, _generate_appid, _hash_appkey


class _User:  # 兼容 auth.user.id / auth.user.is_superuser
    id = 1
    is_superuser = True


class _Auth:  # 轻量 auth 桩，避免依赖完整 AuthSchema 构造
    user = _User()


def _run(coro):
    """在独立事件循环里执行异步协程（本仓库无 pytest-asyncio 的统一写法）。"""
    return asyncio.run(coro)


def test_generate_appid_format_and_uniqueness():
    ids = {_generate_appid() for _ in range(1000)}
    assert all(i.startswith("ai_") and len(i) == 11 for i in ids)
    assert len(ids) == 1000  # 无明显重复/易混淆


def test_hash_appkey_sha256():
    assert _hash_appkey("abc") == hashlib.sha256(b"abc").hexdigest()
    assert _hash_appkey("abc") != _hash_appkey("abd")


def test_create_app_returns_plaintext_key_once(test_client):
    res = _run(DevelopService.create_app(
        DevelopCreateSchema(name="demo", capabilities=["integration:agent:create"]), _Auth()))
    assert res["appid"].startswith("ai_")
    assert res["appkey"] and len(res["appkey"]) >= 32
    assert "appkey_hash" not in res
    # 再查库：哈希存在，但无明文
    row = _run(DevelopService.get_app(res["id"]))
    assert "appkey_hash" not in row and "appkey" not in row


def test_duplicate_name_rejected(test_client):
    _run(DevelopService.create_app(DevelopCreateSchema(name="dup"), _Auth()))
    with pytest.raises(CustomException):
        _run(DevelopService.create_app(DevelopCreateSchema(name="dup"), _Auth()))


def test_reset_appkey_old_fails_new_works(test_client):
    created = _run(DevelopService.create_app(DevelopCreateSchema(name="r"), _Auth()))
    old = created["appkey"]
    reset = _run(DevelopService.reset_appkey(created["id"], _Auth()))
    assert reset["appkey"] != old
    assert _run(DevelopService.verify_appkey(created["appid"], old)) is None
    assert _run(DevelopService.verify_appkey(created["appid"], reset["appkey"])) is not None


def test_disabled_or_expired_app_auth_fails(test_client):
    from datetime import datetime, timedelta

    c = _run(DevelopService.create_app(DevelopCreateSchema(
        name="e", expire_at=datetime.now() - timedelta(days=1)), _Auth()))
    assert _run(DevelopService.verify_appkey(c["appid"], c["appkey"])) is None
    _run(DevelopService.toggle_app(c["id"], False, _Auth()))
    assert _run(DevelopService.verify_appkey(c["appid"], c["appkey"])) is None


def test_create_with_enabled_false_fails_auth(test_client):
    """创建时显式 ``enabled=False``：应用应立刻禁用，verify_appkey 返回 None。"""
    c = _run(DevelopService.create_app(
        DevelopCreateSchema(name="off", enabled=False), _Auth()))
    assert c["enabled"] is False
    assert _run(DevelopService.verify_appkey(c["appid"], c["appkey"])) is None


def test_update_app_honors_enabled(test_client):
    """编辑弹窗的启用开关应生效：update_app 显式改 enabled 会改变可鉴权状态。"""
    c = _run(DevelopService.create_app(DevelopCreateSchema(name="toggle-upd"), _Auth()))
    # 初始启用，可校验通过
    assert _run(DevelopService.verify_appkey(c["appid"], c["appkey"])) is not None
    # 通过 update_app 关闭（模拟编辑弹窗关闭「启用」）
    _run(DevelopService.update_app(c["id"], DevelopUpdateSchema(enabled=False), _Auth()))
    assert _run(DevelopService.verify_appkey(c["appid"], c["appkey"])) is None
    # 再重新启用
    _run(DevelopService.update_app(c["id"], DevelopUpdateSchema(enabled=True), _Auth()))
    assert _run(DevelopService.verify_appkey(c["appid"], c["appkey"])) is not None
