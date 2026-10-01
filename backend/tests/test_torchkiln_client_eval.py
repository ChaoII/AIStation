"""``TorchKilnClient`` 的评估 HTTP 通路测试。

为什么这些方法要带 ``kind`` 参数而不是写两套
--------------------------------------------
TorchKiln 侧训练与评估是两个 REST 命名空间（``/api/v1/train/jobs`` 与
``/api/v1/eval/jobs``），但**生命周期完全同构**——同一个 JobManager、同一套队列、
同一份指标契约，差异只在提交时的 ``kind`` 与「评估必须有 ``weights_path``」。

所以这里用一张 ``_PREFIX`` 表换前缀。若写成两套方法（``get_eval_job`` /
``get_train_job``…），半年后必然出现「改了训练忘了评估」——这类漂移在
``eval_scheduler`` 与 ``predict_executor`` 上已经各发生过一次。

⚠️ 兼容性硬要求：``kind`` 必须**带默认值**，否则 20 多个既有训练调用点全要改，
而收益只是让 diff 变大。

（项目未装 pytest-asyncio；异步测试一律用 ``asyncio.run`` 包在同步测试里。）
"""

import asyncio
import json

import pytest

from app.plugin.module_train.torchkiln_client import TorchKilnClient, _jobs_path


def _run(coro):
    return asyncio.run(coro)


async def _collect(aiter):
    return [ev async for ev in aiter]


# ---------------------------------------------------------------------------
# 路径选择
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind,expect", [
    ("train", "/api/v1/train/jobs/job_1"),
    ("eval", "/api/v1/eval/jobs/job_1"),
])
def test_jobs_path_per_kind(kind, expect):
    assert _jobs_path(kind, "job_1") == expect


@pytest.mark.parametrize("kind", ["", None, "unknown", "predict"])
def test_jobs_path_falls_back_to_train(kind):
    """未知 kind 退回 train，而不是拼出必然 404 的路径。

    退回 train 的后果是「查到的是训练作业」，看起来像 bug；拼出
    ``/api/v1/unknown/jobs`` 的后果是 404，看起来也像 bug——但前者至少有迹可循
    （能拿到数据、能查日志），后者直接什么都拿不到。
    """
    assert _jobs_path(kind, "job_1").startswith("/api/v1/train/jobs")


def test_jobs_path_without_job_id_is_collection():
    assert _jobs_path("eval") == "/api/v1/eval/jobs"
    assert _jobs_path("train") == "/api/v1/train/jobs"


# ---------------------------------------------------------------------------
# 签名兼容性
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "get_job", "cancel_job", "metrics", "logs", "artifacts",
    "stream_metrics", "stream_logs",
])
def test_kind_has_default(name):
    """``kind`` 必须有默认值——否则既有训练调用点全部要改。"""
    import inspect

    sig = inspect.signature(getattr(TorchKilnClient, name))
    assert "kind" in sig.parameters, f"{name} 缺 kind 参数"
    assert sig.parameters["kind"].default == "train"


def test_list_jobs_kind_is_optional_filter():
    """``list_jobs`` 的 kind 语义是「过滤」不是「选前缀」，所以默认 None。

    None = 返回全部种类（训练端点不该预设 kind=train，否则调用方想看全部作业
    还得自己合并两个前缀）。
    """
    import inspect

    sig = inspect.signature(TorchKilnClient.list_jobs)
    assert sig.parameters["kind"].default is None


# ---------------------------------------------------------------------------
# 请求形状（假传输层断言打到了哪个 URL）
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._p


class _FakeTransport:
    """记录所有请求，按需返回预设响应。

    必须实现 ``get``/``post``/``stream`` 三个入口——``httpx.AsyncClient`` 的
    ``get``/``post`` 是便捷包装。**它不是 transport**，所以只实现 ``request``
    的话客户端根本走不到那里。
    """

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload or {}
        self.lines = []

    def _record(self, method, url, kw):
        self.calls.append((method, url, kw))
        return _Resp(self.payload)

    async def get(self, url, **kw):
        return self._record("GET", url, kw)

    async def post(self, url, **kw):
        return self._record("POST", url, kw)

    async def request(self, method, url, **kw):
        return self._record(method, url, kw)

    def stream(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_e):
        return False

    async def aiter_lines(self):
        for ln in self.lines:
            yield ln

    async def aread(self):
        return b""

    @property
    def status_code(self):
        return 200


def _client(fake):
    c = TorchKilnClient(base_url="http://svc", token="t")
    c._client = fake
    c._stream_client = fake
    return c


def test_submit_eval_job_posts_to_eval_endpoint():
    fake = _FakeTransport({"job_id": "j1", "status": "queued"})
    _run(_client(fake).submit_eval_job(
        {"kind": "eval", "weights_path": "/m/b.pth"},
        idempotency_key="k1", user_id=7))

    method, url, kw = fake.calls[0]
    assert method == "POST"
    assert url == "/api/v1/eval/jobs"
    assert kw["json"]["weights_path"] == "/m/b.pth"
    # 幂等头必须带上——超时重试/服务重启后重提不该重复排队烧卡
    assert kw["headers"]["Idempotency-Key"] == "k1"
    assert kw["headers"]["X-User-Id"] == "7"


def test_get_job_uses_eval_path_when_kind_eval():
    fake = _FakeTransport({"job_id": "j1"})
    _run(_client(fake).get_job("j1", kind="eval"))
    assert fake.calls[0][1] == "/api/v1/eval/jobs/j1"


def test_metrics_uses_eval_path_and_reads_items():
    fake = _FakeTransport({"items": [{"type": "eval", "main_value": 0.5}]})
    got = _run(_client(fake).metrics("j1", kind="eval"))

    assert fake.calls[0][1] == "/api/v1/eval/jobs/j1/metrics"
    assert got == [{"type": "eval", "main_value": 0.5}]


def test_list_jobs_sends_kind_filter():
    fake = _FakeTransport({"total": 0, "items": []})
    _run(_client(fake).list_jobs(kind="eval"))
    assert fake.calls[0][2]["params"]["kind"] == "eval"


def test_list_jobs_omits_kind_when_not_given():
    """不给 kind 时不传该参数——服务端会把缺失与空串当不同输入。"""
    fake = _FakeTransport({"total": 0, "items": []})
    _run(_client(fake).list_jobs())
    assert "kind" not in fake.calls[0][2]["params"]


def test_cancel_job_uses_eval_path():
    fake = _FakeTransport({"job_id": "j1", "status": "cancelled"})
    _run(_client(fake).cancel_job("j1", kind="eval"))
    assert fake.calls[0][1] == "/api/v1/eval/jobs/j1/cancel"


def test_logs_and_artifacts_use_eval_path():
    fake = _FakeTransport({"lines": ["a"], "items": []})
    c = _client(fake)
    _run(c.logs("j1", kind="eval"))
    _run(c.artifacts("j1", kind="eval"))
    urls = [x[1] for x in fake.calls]
    assert "/api/v1/eval/jobs/j1/logs" in urls
    assert "/api/v1/eval/jobs/j1/artifacts" in urls


def test_train_paths_unchanged():
    """既有训练调用的 URL 必须与改动前**逐字相同**。"""
    fake = _FakeTransport({"items": [], "lines": [], "total": 0})
    c = _client(fake)
    _run(c.get_job("j1"))
    _run(c.cancel_job("j1"))
    _run(c.metrics("j1"))
    _run(c.logs("j1"))
    _run(c.artifacts("j1"))
    _run(c.list_jobs())
    urls = [x[1] for x in fake.calls]
    assert urls == [
        "/api/v1/train/jobs/j1",
        "/api/v1/train/jobs/j1/cancel",
        "/api/v1/train/jobs/j1/metrics",
        "/api/v1/train/jobs/j1/logs",
        "/api/v1/train/jobs/j1/artifacts",
        "/api/v1/train/jobs",
    ]


# ---------------------------------------------------------------------------
# 指标契约的语义
# ---------------------------------------------------------------------------


def test_stream_metrics_surfaces_eval_and_end_events():
    """评估的指标序列是 ``eval`` -> ``end``，没有 ``step``。

    消费方（未来的 eval_scheduler）应该只认这两个类型，别再去找 ``step``。
    """
    fake = _FakeTransport()
    fake.lines = [
        "event: eval",
        "data: " + json.dumps({"type": "eval", "seq": 0, "main_value": 0.0,
                               "metrics": {"box_mAP50": 0.0}}),
        "",
        "event: end",
        "data: " + json.dumps({"type": "end", "seq": 1, "exit_reason": "finished"}),
        "",
    ]
    got = _run(_collect(_client(fake).stream_metrics("j1", kind="eval")))

    assert [g.get("type") for g in got] == ["eval", "end"]
    assert got[0]["metrics"]["box_mAP50"] == 0.0
    assert got[1]["exit_reason"] == "finished"
    # SSE 走的是**绝对** URL（客户端自己拼 base_url + path），所以按后缀匹配
    assert fake.calls[0][1].endswith("/api/v1/eval/jobs/j1/metrics/stream")


def test_stream_metrics_tolerates_bad_json():
    """坏行跳过，不让消费方整体崩——SSE 里混进非 JSON 是常见的。"""
    fake = _FakeTransport()
    fake.lines = [
        "data: not-json",
        "",
        "data: " + json.dumps({"type": "eval", "main_value": 0.1}),
        "",
    ]
    got = _run(_collect(_client(fake).stream_metrics("j1", kind="eval")))
    assert [g.get("type") for g in got] == ["eval"]
