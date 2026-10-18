"""工作流运行取消：信号通道、引擎中断点、运行状态映射。

覆盖：
- 取消信号内存往返与 Redis 广播（多 worker 场景）；
- 引擎在**节点边界**停下并抛 WorkflowCancelled；
- 引擎在**流式节点中间**逐帧中断（_stream 包装）；
- 运行状态推导（含"被中断"必须记为 cancelled，不能混成 success）。
"""
import asyncio

import pytest

from app.plugin.module_ai.streaming import UiMessageStream
from app.plugin.module_ai.workflow import cancel as cancel_mod
from app.plugin.module_ai.workflow.engine import WorkflowCancelled, WorkflowEngine


class _FakeRedis:
    """最小 Redis 替身：只实现取消信号用到的 get/set/delete。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None):  # noqa: A003
        self.store[key] = value

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


def _engine(**kw) -> WorkflowEngine:
    graph = kw.pop("graph", {
        "nodes": [{"id": "n1", "type": "start", "data": {}}],
        "edges": [],
    })
    state = kw.pop("state", None)
    return WorkflowEngine(
        graph=graph, variables={}, messages=[], ms=UiMessageStream(),
        state=state if state is not None else {}, **kw
    )


# ---------------------------- 信号通道 ---------------------------- #

def test_cancel_signal_local_roundtrip():
    """无 Redis 时，内存集合即可完成 请求→查询→清理。"""

    async def _run():
        await cancel_mod.clear_cancel("k-local")
        assert await cancel_mod.is_cancelled("k-local") is False
        await cancel_mod.request_cancel("k-local")
        assert await cancel_mod.is_cancelled("k-local") is True
        await cancel_mod.clear_cancel("k-local")
        assert await cancel_mod.is_cancelled("k-local") is False

    asyncio.run(_run())


def test_cancel_signal_broadcasts_via_redis():
    """Redis 通道：本地集合被清空（模拟另一个 worker 的进程）后仍能读到取消。"""

    async def _run():
        r = _FakeRedis()
        await cancel_mod.request_cancel("k-redis", redis=r)
        # 模拟"另一个 worker"：清掉本进程内存，只靠 Redis
        cancel_mod._LOCAL.discard("k-redis")
        assert await cancel_mod.is_cancelled("k-redis", redis=r) is True
        # 命中后会回填内存，后续免往返
        assert "k-redis" in cancel_mod._LOCAL

        await cancel_mod.clear_cancel("k-redis", redis=r)
        cancel_mod._LOCAL.discard("k-redis")
        assert await cancel_mod.is_cancelled("k-redis", redis=r) is False

    asyncio.run(_run())


def test_cancel_signal_survives_redis_failure():
    """Redis 写失败不得抛错（降级为内存），否则取消接口会 500。"""

    class _Boom:
        async def set(self, *a, **k):
            raise RuntimeError("redis down")

        async def get(self, *a, **k):
            raise RuntimeError("redis down")

    async def _run():
        r = _Boom()
        await cancel_mod.clear_cancel("k-boom")
        await cancel_mod.request_cancel("k-boom", redis=r)  # 不应抛
        assert await cancel_mod.is_cancelled("k-boom", redis=r) is True  # 内存兜住
        await cancel_mod.clear_cancel("k-boom")

    asyncio.run(_run())


# ---------------------------- 引擎中断点 ---------------------------- #

def test_engine_stops_at_node_boundary():
    """已请求取消时，引擎在节点边界产出 cancelled 帧并抛 WorkflowCancelled。"""

    async def _run():
        await cancel_mod.clear_cancel("k-node")
        await cancel_mod.request_cancel("k-node")
        eng = _engine(cancel_key="k-node")
        frames: list[str] = []
        with pytest.raises(WorkflowCancelled):
            async for f in eng.run():
                frames.append(f)
        await cancel_mod.clear_cancel("k-node")
        return frames

    frames = asyncio.run(_run())
    assert any('"status": "cancelled"' in f for f in frames), frames


def test_engine_stream_interrupts_mid_node():
    """_stream 逐帧检查：取消后**不再透传下一帧**并立即抛错（流式节点可被中断）。"""

    async def _gen():
        yield "frame-1"
        yield "frame-2"
        yield "frame-3"

    async def _run():
        await cancel_mod.clear_cancel("k-stream")
        eng = _engine(cancel_key="k-stream")
        got: list[str] = []
        # 收到第一帧后再请求取消 → 第二帧应被拦截
        with pytest.raises(WorkflowCancelled):
            async for f in eng._stream(_gen()):
                got.append(f)
                await cancel_mod.request_cancel("k-stream")
        await cancel_mod.clear_cancel("k-stream")
        return got

    assert asyncio.run(_run()) == ["frame-1"]


def test_engine_without_cancel_key_never_cancels():
    """未配置 cancel_key（如单节点调试）时不应有任何取消行为。"""

    async def _run():
        eng = _engine()
        assert await eng._cancelled() is False
        return [f async for f in eng.run()]

    frames = asyncio.run(_run())
    assert frames, "无取消配置时应正常跑完"


def test_engine_reraises_cancel_during_node(monkeypatch):
    """节点执行途中被取消：必须**上抛** WorkflowCancelled，不得被当成节点失败记 error。

    回归守卫：引擎按节点的 ``except Exception`` 曾把 WorkflowCancelled 吞掉，
    结果取消被记成 error、节点还被重试——表现为「点了停止但记录显示失败」。
    """

    async def _fake_llm(node):
        yield "frame-1"
        yield "frame-2"

    async def _run():
        await cancel_mod.clear_cancel("k-node2")
        state: dict = {}
        eng = _engine(
            graph={
                "nodes": [{"id": "s", "type": "start", "data": {}},
                          {"id": "l", "type": "llm", "data": {}}],
                "edges": [{"source": "s", "target": "l"}],
            },
            state=state,
            cancel_key="k-node2",
        )
        monkeypatch.setattr(eng, "_exec_llm", _fake_llm)
        with pytest.raises(WorkflowCancelled):
            async for _ in eng.run():
                # 收到第一帧后请求取消 → 第二帧被 _stream 拦截并上抛
                await cancel_mod.request_cancel("k-node2")
        await cancel_mod.clear_cancel("k-node2")
        return state

    state = asyncio.run(_run())
    assert state.get("error") is None, f"取消不得被记成节点失败：{state}"
    assert state.get("cancelled") is None  # 由调用方（service）负责标记


def test_reconcile_stale_runs_marks_only_old_running(test_client):
    """启动兜底：超龄 ``running`` 记 cancelled；新近的 ``running`` 不动。

    为什么按时间阈值：多 worker 下别的进程可能正在正常跑，不能一启动就把所有
    running 清掉（会误伤活着的运行）。进程重启导致的僵尸记录才会超龄。
    """
    from datetime import datetime, timedelta

    from app.core.database import async_db_session
    from app.plugin.module_ai.workflow.model import AiWorkflowRunLogModel
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    async def _go():
        async with async_db_session.begin() as db:
            old_row = AiWorkflowRunLogModel(workflow_id=1, status="running", duration_ms=0)
            fresh_row = AiWorkflowRunLogModel(workflow_id=1, status="running", duration_ms=0)
            db.add(old_row)
            db.add(fresh_row)
            await db.flush()
            old_id, fresh_id = old_row.id, fresh_row.id
            old_row.created_time = datetime.now() - timedelta(hours=2)  # 模拟僵尸记录
        n = await AiWorkflowService.reconcile_stale_runs()
        async with async_db_session() as db:
            old_status = (await db.get(AiWorkflowRunLogModel, old_id)).status
            fresh_status = (await db.get(AiWorkflowRunLogModel, fresh_id)).status
        async with async_db_session.begin() as db:  # 清理测试数据
            for i in (old_id, fresh_id):
                r = await db.get(AiWorkflowRunLogModel, i)
                if r:
                    await db.delete(r)
        return n, old_status, fresh_status

    n, old_status, fresh_status = asyncio.run(_go())
    assert old_status == "cancelled"
    assert fresh_status == "running"
    assert n >= 1


# ---------------------------- 立即中断（任务级取消） ---------------------------- #

def test_run_ui_stream_interrupts_silent_node_immediately(monkeypatch):
    """节点**长时间不产帧**时，取消也必须立即生效（不能等下一帧）。

    背景：取消原来只在引擎里**逐帧**检查；节点若在等 LLM 思考或做非流式调用（几十秒
    不产帧），「停止」要等第一个 token 才生效——用户点了停止却没反应。修法是把引擎放进
    独立任务，取消时直接 ``cancel()`` 该任务（打断 await）。本用例锁住「静默期也能秒停」。
    """
    import time

    from app.plugin.module_ai.workflow.service import AiWorkflowService as S

    graph = {
        "nodes": [{"id": "s", "type": "start", "data": {}},
                  {"id": "l", "type": "llm", "data": {}}],
        "edges": [{"source": "s", "target": "l"}],
    }

    async def _silent_llm(self, node):
        entered.append(node.get("id"))
        await asyncio.sleep(30)  # 静默：30 秒内不产任何帧
        yield "never"

    async def _get_workflow(cls, workflow_id):
        return {"graph": graph, "enabled": True}

    async def _start_run(cls, workflow_id, payload, uid):
        return 4242  # 假运行记录 id

    finished: list = []
    entered: list = []

    async def _finish_run(cls, log_id, status, payload, error, trace, duration_ms):
        finished.append((log_id, status, error))

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(S, "get_workflow", classmethod(_get_workflow))
    monkeypatch.setattr(S, "_start_run", classmethod(_start_run))
    monkeypatch.setattr(S, "_finish_run", classmethod(_finish_run))
    monkeypatch.setattr(WorkflowEngine, "_exec_llm", _silent_llm)
    monkeypatch.setattr(
        "app.plugin.module_ai.overview.service.AiOverviewService.add_log", _noop
    )
    monkeypatch.setattr(
        "app.plugin.module_ai.sessions.service.persist_session_exchange", _noop
    )

    class _Auth:
        class user:  # noqa: N801
            id = 1

    async def _run():
        await cancel_mod.clear_cancel(4242)
        frames: list[str] = []
        t0 = time.perf_counter()
        async for f in S.run_ui_stream(
            1, [{"role": "user", "parts": [{"text": "hi"}]}], _Auth()
        ):
            frames.append(f)
            # 等 LLM 节点**已开始**（它随即进入 30s 静默）再请求取消：
            # 取消落在节点边界就测不到"静默期中断"了（那时引擎本来就会停）
            if '"nodeId": "l"' in f and '"status": "running"' in f:
                await asyncio.sleep(0.3)
                await cancel_mod.request_cancel(4242)
        await cancel_mod.clear_cancel(4242)
        return frames, time.perf_counter() - t0

    frames, elapsed = asyncio.run(asyncio.wait_for(_run(), timeout=10))

    assert entered == ["l"], f"静默节点必须真的被执行到（否则测的是真 LLM）：{entered}"
    assert elapsed < 5, f"静默节点未被立即打断（耗时 {elapsed:.1f}s，节点要睡 30s）"
    assert finished and finished[-1][1] == "cancelled", finished
    assert any('"status": "cancelled"' in f for f in frames), (
        "被中断的节点必须补一个 cancelled 帧，否则前端轨迹一直显示「执行中」"
    )
    assert any('"type": "finish"' in f for f in frames), "取消后仍须正常收尾（终止帧）"


# ---------------------------- 运行状态映射 ---------------------------- #

def test_run_status_mapping():
    """状态推导：成功/失败/取消/HITL 挂起/被中断（未置 finished）。"""
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    f = AiWorkflowService._run_status
    assert f({"finished": True}) == "success"
    assert f({"finished": True, "error": "boom"}) == "error"
    assert f({"cancelled": True}) == "cancelled"
    assert f({"finished": True, "halted": True}) == "pending"
    # 未置 finished = 被中断（客户端断连/任务被取消）→ 必须记 cancelled 而非 success
    assert f({}) == "cancelled"
    # 取消优先于 error：用户主动停止不应被记成失败
    assert f({"cancelled": True, "error": "x"}) == "cancelled"
