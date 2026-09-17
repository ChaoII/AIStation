"""边缘事件 Redis 广播与 WebSocket 实时推送测试。

- 广播层用 fakeredis（TESTING 模式下 ``app.state.redis`` 即 fakeredis）验证真 pub/sub；
- WS 端点用 ``TestClient.websocket_connect`` 覆盖鉴权失败（4401）与 publish→转发；
- 落库→广播的接线用 monkeypatch 隔离，锁定「未落库不广播」「广播失败不阻断告警」。
"""
import asyncio
import itertools
import json
import time
from contextlib import ExitStack
from datetime import datetime, timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.v1.module_video.edge import controller as edge_controller
from app.api.v1.module_video.edge import event_bus
from app.api.v1.module_video.edge import store as edge_store
from app.api.v1.module_video.inference import service
from app.config.setting import settings

WS_PATH = "/api/v1/video/edge/event/ws"

# 视频模块限流按转发 IP 分桶：每个 WS 连接用独立 IP，避免用例间互相挤占
_IP_SEQ = itertools.count(1)


def _ws_headers() -> dict:
    n = next(_IP_SEQ)
    return {"X-Forwarded-For": f"10.30.{n // 250}.{n % 250 + 1}"}


def _token(user_id: int = 7, name: str = "alice") -> str:
    """复用项目 JWT 签发，供 WS query token 鉴权（无 Redis 在线会话）。"""
    from app.api.v1.module_system.auth.schema import JWTPayloadSchema
    from app.core.security import create_access_token

    return create_access_token(
        JWTPayloadSchema(
            sub=json.dumps({"user_id": user_id, "user_name": name}),
            is_refresh=False,
            exp=datetime.now() + timedelta(minutes=5),
        )
    )


def _alg_none_token(sub: str = '{"user_id":1,"user_name":"admin"}') -> str:
    """手工构造 alg=none 的无签名 token。"""
    import base64

    def _b64(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    payload = {"sub": sub, "is_refresh": False, "exp": 9999999999, "iss": "aistation"}
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(payload)}."


@pytest.fixture(autouse=True)
def _schema(test_client):
    """启动应用生命周期（含 fakeredis 初始化），WS 与广播共用同一实例。"""
    return test_client


@pytest.fixture
def valid_ws_token(auth_headers) -> str:
    """真实登录得到的 access_token（Redis 中有在线会话，签名/签发者均合法）。"""
    return auth_headers["Authorization"].removeprefix("Bearer ")


def _wait_until(pred, timeout: float = 3.0) -> bool:
    """轮询等待条件成立：WS 断连清理在应用事件循环内异步完成，避免时序竞态。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


# --------------------------------------------------------------- 鉴权
def test_ws_rejects_missing_token(test_client):
    """未携带 token：握手即关闭，关闭码 4401。"""
    with pytest.raises(WebSocketDisconnect) as exc:
        with test_client.websocket_connect(WS_PATH, headers=_ws_headers()):
            pass
    assert exc.value.code == 4401


def test_ws_rejects_invalid_token(test_client):
    """非法 token：关闭码 4401，且不注册任何订阅。"""
    before = event_bus.local_subscriber_count()
    with pytest.raises(WebSocketDisconnect) as exc:
        with test_client.websocket_connect(
            f"{WS_PATH}?token=not-a-jwt", headers=_ws_headers()
        ):
            pass
    assert exc.value.code == 4401
    assert event_bus.local_subscriber_count() == before


def test_ws_rejects_signed_token_without_online_session(test_client):
    """签名正确但无 Redis 在线会话（未登录/伪造 sub）必须拒绝：仅验签不够。"""
    with pytest.raises(WebSocketDisconnect) as exc:
        with test_client.websocket_connect(
            f"{WS_PATH}?token={_token()}", headers=_ws_headers()
        ):
            pass
    assert exc.value.code == 4401


def test_ws_rejects_tampered_token(test_client, valid_ws_token):
    """篡改签名后的 token 必须拒绝。"""
    tampered = valid_ws_token[:-3] + ("aaa" if valid_ws_token[-3:] != "aaa" else "bbb")
    with pytest.raises(WebSocketDisconnect) as exc:
        with test_client.websocket_connect(
            f"{WS_PATH}?token={tampered}", headers=_ws_headers()
        ):
            pass
    assert exc.value.code == 4401


def test_ws_rejects_expired_token(test_client):
    """过期 token 必须拒绝。"""
    from app.api.v1.module_system.auth.schema import JWTPayloadSchema
    from app.core.security import create_access_token

    token = create_access_token(
        JWTPayloadSchema(
            sub=json.dumps({"user_id": 1, "user_name": "admin", "session_id": "expired"}),
            is_refresh=False,
            exp=datetime.now() - timedelta(minutes=1),
        )
    )
    with pytest.raises(WebSocketDisconnect) as exc:
        with test_client.websocket_connect(
            f"{WS_PATH}?token={token}", headers=_ws_headers()
        ):
            pass
    assert exc.value.code == 4401


def test_ws_rejects_alg_none_token(test_client):
    """alg=none 的无签名 token 必须拒绝。"""
    with pytest.raises(WebSocketDisconnect) as exc:
        with test_client.websocket_connect(
            f"{WS_PATH}?token={_alg_none_token()}", headers=_ws_headers()
        ):
            pass
    assert exc.value.code == 4401


# --------------------------------------------------------------- Redis pub/sub
def test_publish_edge_event_reaches_redis_subscriber(test_client):
    """publish_edge_event 经 Redis 频道 ``ai:edge:event`` 发布，订阅者收到封装消息。"""
    redis = test_client.app.state.redis
    event_bus.set_redis(redis)

    async def _run():
        pubsub = redis.pubsub()
        await pubsub.subscribe(event_bus.EDGE_EVENT_CHANNEL)
        try:
            await event_bus.publish_edge_event({"event_id": "ev-pub", "matched": True})
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    return message
        finally:
            try:
                await pubsub.unsubscribe(event_bus.EDGE_EVENT_CHANNEL)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001 - 清理失败不影响断言
                pass
        return None

    message = asyncio.run(asyncio.wait_for(_run(), timeout=5))
    assert message is not None
    body = json.loads(message["data"])
    assert body["type"] == "event"
    assert body["data"]["event_id"] == "ev-pub"


def test_ws_receives_published_event(test_client, valid_ws_token):
    """WS 连接后发布事件，前端收到 ``{"type":"event","data":<详情>}``。"""
    with test_client.websocket_connect(
        f"{WS_PATH}?token={valid_ws_token}", headers=_ws_headers()
    ) as ws:
        asyncio.run(
            event_bus.publish_edge_event(
                {"id": 1, "event_id": "ev-live", "matched": True, "objects": []}
            )
        )
        msg = ws.receive_json()
        assert msg["type"] == "event"
        assert msg["data"]["event_id"] == "ev-live"
        assert msg["data"]["matched"] is True


# --------------------------------------------------------------- 并发上限
def test_ws_above_twenty_clients_all_connect(test_client, valid_ws_token):
    """N>20 并发订阅全部握手成功、绝不 500（审计·并发 #10）。

    旧实现复用应用 Redis 池（max_connections=POOL_SIZE=20），第 21 个订阅在建连
    阶段抛异常 → HTTP 500。现用独立订阅连接池，数量只受 EDGE_WS_MAX_CONNECTIONS 约束。
    """
    assert _wait_until(lambda: edge_controller.active_ws_count() == 0)
    with ExitStack() as stack:
        sockets = [
            stack.enter_context(
                test_client.websocket_connect(
                    f"{WS_PATH}?token={valid_ws_token}", headers=_ws_headers()
                )
            )
            for _ in range(25)
        ]
        assert len(sockets) == 25
        assert edge_controller.active_ws_count() == 25
    assert _wait_until(lambda: edge_controller.active_ws_count() == 0)


def test_ws_concurrency_limit_closes_cleanly_with_1013(
    test_client, valid_ws_token, monkeypatch
):
    """达到并发上限的订阅以 1013（稍后重试）干净关闭，绝不 500（审计·并发 #10）。"""
    monkeypatch.setattr(settings, "EDGE_WS_MAX_CONNECTIONS", 2)
    assert _wait_until(lambda: edge_controller.active_ws_count() == 0)
    with test_client.websocket_connect(
        f"{WS_PATH}?token={valid_ws_token}", headers=_ws_headers()
    ):
        with test_client.websocket_connect(
            f"{WS_PATH}?token={valid_ws_token}", headers=_ws_headers()
        ):
            with pytest.raises(WebSocketDisconnect) as exc:
                with test_client.websocket_connect(
                    f"{WS_PATH}?token={valid_ws_token}", headers=_ws_headers()
                ) as ws3:
                    # 服务端已 accept，随后以 1013 关闭；读取即抛出对应关闭码
                    ws3.receive_json()
            assert exc.value.code == 1013
    assert _wait_until(lambda: edge_controller.active_ws_count() == 0)


def test_pubsub_redis_pool_is_decoupled_from_app_pool(monkeypatch):
    """生产路径的订阅连接池按 EDGE_WS_MAX_CONNECTIONS 独立创建（审计·并发 #10）。"""
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(event_bus, "_pubsub_client", None)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "REDIS_ENABLE", True)
    monkeypatch.setattr(settings, "EDGE_WS_MAX_CONNECTIONS", 37)
    captured: dict = {}

    async def _fake_from_url(url, **kwargs):  # noqa: ARG001 - 仅捕获参数
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(redis_asyncio.Redis, "from_url", _fake_from_url)
    assert asyncio.run(event_bus.get_pubsub_redis()) is not None
    assert captured["max_connections"] == 37 + 8


def test_pubsub_redis_reuses_app_redis_in_testing(test_client):
    """TESTING 下复用应用内存 Redis（同一 fakeredis 才有真 pub/sub）。"""
    event_bus.set_redis(test_client.app.state.redis)
    assert asyncio.run(event_bus.get_pubsub_redis()) is test_client.app.state.redis


# --------------------------------------------------------------- 订阅清理
def test_local_fallback_subscription_is_cleaned(test_client, monkeypatch, valid_ws_token):
    """Redis 不可用时降级为进程内广播；断连后订阅必须注销，不得泄漏。"""

    async def _no_redis():
        return None

    monkeypatch.setattr(event_bus, "get_redis", _no_redis)

    with test_client.websocket_connect(
        f"{WS_PATH}?token={valid_ws_token}", headers=_ws_headers()
    ) as ws:
        assert event_bus.local_subscriber_count() == 1
        asyncio.run(event_bus.publish_edge_event({"event_id": "ev-local"}))
        msg = ws.receive_json()
        assert msg["type"] == "event"
        assert msg["data"]["event_id"] == "ev-local"
    # 断连后本地订阅已注销（无泄漏）；清理在应用事件循环内异步完成，故轮询等待
    assert _wait_until(lambda: event_bus.local_subscriber_count() == 0)


# --------------------------------------------------------------- 落库 → 广播接线
def _patch_store(monkeypatch, result):
    async def _fake_store(*_args, **_kwargs):
        return result

    monkeypatch.setattr(edge_store, "record_edge_event", _fake_store)


def test_persist_publishes_only_when_stored(monkeypatch):
    """未落库（空事件/重复）不得广播；落库成功才广播且仅一次。"""
    published: list = []

    async def _spy(row_id):
        published.append(row_id)

    monkeypatch.setattr(service, "_publish_edge_event", _spy)

    # 重复/空事件：record 返回 None → 不广播
    _patch_store(monkeypatch, None)
    result = asyncio.run(
        service._persist_edge_event(
            {"event_id": "ev-dup", "objects": [{"label": "person"}]},
            matched=True,
            rule_id=1,
            matched_leaves=[],
        )
    )
    assert result is None
    assert published == []

    # 落库成功：record 返回 id → 广播一次
    _patch_store(monkeypatch, 42)
    result = asyncio.run(
        service._persist_edge_event(
            {"event_id": "ev-ok", "objects": [{"label": "person"}]},
            matched=True,
            rule_id=1,
            matched_leaves=[],
        )
    )
    assert result == 42
    assert published == [42]


def test_publish_failure_does_not_break_persist(monkeypatch):
    """广播失败不得阻断告警链路：_persist_edge_event 仍返回落库 id。"""
    _patch_store(monkeypatch, 7)

    async def _boom(_row_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr(service, "_publish_edge_event", _boom)

    result = asyncio.run(
        service._persist_edge_event(
            {"event_id": "ev-boom", "objects": [{"label": "person"}]},
            matched=True,
            rule_id=1,
            matched_leaves=[],
        )
    )
    assert result == 7
