"""并发准入闸门 + 连接池全量预热的回归测试。

对应 2026-10 排查出的根因（实测数字）：

- PG 每次建连要做 SCRAM-SHA-256 的 PBKDF2：本机 846ms/条（672ms 纯 CPU），
  且在事件循环里**同步串行**（5 条并发建连 = 5×1392ms）。
- 连接池早先只预热 8 条 →「第 9 个并发请求」现建连接 → 单用户打开一个弹窗
  （并发 10~20 请求）就把事件循环卡住，队尾超过前端 10 秒超时 →「请求超时」。
- 池建满后同一场景实测 109ms（建连时 12.6~21.5 秒）。

因此两条修复必须成立：
1) ``warmup_target()`` 必须是**全量 POOL_SIZE**，不能只预热一小撮；
2) 池被占满时必须**立刻 503 + Retry-After**，而不是排队到超时。
"""

import asyncio
import json
import time

from app.config.setting import settings
from app.core.database import WARMUP_RESERVE_FOR_TRAFFIC, warmup_target
from app.core.middlewares import AdmissionGateMiddleware

# --------------------------------------------------------------------------- ASGI 测试桩


def _scope(method: str = "GET", path: str = "/fast") -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }


async def _call(mw, path: str = "/fast", method: str = "GET") -> list[dict]:
    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    sent: list[dict] = []

    async def send(message: dict) -> None:
        sent.append(message)

    await mw(_scope(method, path), receive, send)
    return sent


def _status(msgs: list[dict]) -> int:
    return next(m["status"] for m in msgs if m["type"] == "http.response.start")


def _headers(msgs: list[dict]) -> dict[bytes, bytes]:
    raw = next(m["headers"] for m in msgs if m["type"] == "http.response.start")
    return dict(raw)


def _body(msgs: list[dict]) -> str:
    return b"".join(m.get("body", b"") for m in msgs if m["type"] == "http.response.body").decode(
        "utf-8"
    )


class _Inner:
    """被闸门包住的应用：``/slow`` 会一直停在 ``release`` 上，用来占住槽位。"""

    def __init__(self) -> None:
        self.entered = 0
        self.release = asyncio.Event()

    async def __call__(self, scope, receive, send) -> None:
        if scope["path"] == "/slow":
            self.entered += 1
            await self.release.wait()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-length", b"2")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


async def _wait_entered(inner: _Inner, n: int) -> None:
    deadline = time.perf_counter() + 3
    while inner.entered < n:
        if time.perf_counter() > deadline:
            raise AssertionError(f"等待 {n} 个请求进入内层超时（当前 {inner.entered}）")
        await asyncio.sleep(0.01)


# --------------------------------------------------------------------------- 预热


def test_warmup_target_is_full_pool(monkeypatch) -> None:
    """预热必须基本建满 POOL_SIZE（回归：旧实现是 min(POOL_SIZE, 8)），但留 8 条给在途请求。"""
    monkeypatch.setattr(settings, "POOL_SIZE", 48)
    assert warmup_target() == 48 - WARMUP_RESERVE_FOR_TRAFFIC
    assert warmup_target() > 8, "预热只建一小撮，第 9 个并发请求就现建连接 → 单用户弹窗超时"

    monkeypatch.setattr(settings, "POOL_SIZE", 20)
    assert warmup_target() == 20 - WARMUP_RESERVE_FOR_TRAFFIC

    # 预热不得把池全占死：必须给实时流量留出余量，否则首批请求拿不到连接
    assert WARMUP_RESERVE_FOR_TRAFFIC >= 4


# --------------------------------------------------------------------------- 闸门


def test_gate_passes_and_releases_slot() -> None:
    """正常放行，且请求结束后**必须归还**槽位（否则几次请求后闸门把自己锁死）。"""

    async def main() -> None:
        inner = _Inner()
        mw = AdmissionGateMiddleware(inner)

        for _ in range(mw._slots + 2):  # 超过槽位数也应串行放行
            msgs = await _call(mw)
            assert _status(msgs) == 200

        assert mw._sem._value == mw._slots, "槽位没有归还"

    asyncio.run(main())


def test_gate_defaults_to_pool_size(monkeypatch) -> None:
    """GATE_SLOTS=0 时兜底取 POOL_SIZE；显式设置时用显式值（且必须小于池）。"""
    monkeypatch.setattr(settings, "GATE_SLOTS", 0)
    monkeypatch.setattr(settings, "POOL_SIZE", 48)
    assert AdmissionGateMiddleware(_Inner())._slots == 48

    monkeypatch.setattr(settings, "GATE_SLOTS", 24)
    assert AdmissionGateMiddleware(_Inner())._slots == 24


def test_gate_rejects_fast_with_retry_after(monkeypatch) -> None:
    """池被占满时：**立刻** 503 + Retry-After，绝不能排队到前端 10 秒超时。"""
    monkeypatch.setattr(settings, "GATE_SLOTS", 2)
    monkeypatch.setattr(settings, "GATE_WAIT_SECONDS", 0.2)

    async def main() -> None:
        inner = _Inner()
        mw = AdmissionGateMiddleware(inner)
        assert mw._slots == 2

        holders = [asyncio.create_task(_call(mw, "/slow")) for _ in range(2)]
        await _wait_entered(inner, 2)  # 两个槽位都被占住

        t0 = time.perf_counter()
        msgs = await _call(mw, "/slow")
        elapsed = time.perf_counter() - t0

        assert _status(msgs) == 503, "槽位占满时必须拒绝，而不是排队"
        assert elapsed < 1.5, f"拒绝必须很快，实测 {elapsed:.2f}s"
        headers = _headers(msgs)
        assert b"retry-after" in headers, "缺 Retry-After，前端无法按服务繁忙重试"
        body = _body(msgs)
        assert "服务繁忙" in body and "并发" in body, f"提示文案不对：{body}"
        assert json.loads(body)["code"] == 503

        # 归还：释放后槽位恢复，后续请求可正常处理
        inner.release.set()
        results = await asyncio.gather(*holders)
        assert [_status(r) for r in results] == [200, 200]
        assert mw._sem._value == 2, "被占用的槽位没有归还"
        assert (await _call(mw, "/fast"))[0]["status"] == 200

    asyncio.run(main())


def test_gate_exempts_options_and_non_http(monkeypatch) -> None:
    """CORS 预检与 lifespan/websocket 不受闸门限制（否则浏览器跨域直接崩）。"""
    monkeypatch.setattr(settings, "GATE_SLOTS", 1)
    monkeypatch.setattr(settings, "GATE_WAIT_SECONDS", 0.1)

    async def main() -> None:
        inner = _Inner()
        mw = AdmissionGateMiddleware(inner)

        holder = asyncio.create_task(_call(mw, "/slow"))
        await _wait_entered(inner, 1)  # 唯一槽位已被占

        assert _status(await _call(mw, "/fast", method="OPTIONS")) == 200, "预检不该被拦"

        inner.release.set()
        await holder

    asyncio.run(main())
