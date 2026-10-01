"""训练进度推算 + SSE 响应契约的回归测试。

这两处以前都没有测试守着，实际缺陷也正是从这里漏出去的：

- ``TrainTask.progress`` 只在启动写 0、收尾写 100，**训练全程不动**，
  列表页进度条因此恒为 0%；
- SSE 响应头少一个 ``Content-Encoding: identity``，整条实时流被 GZip 中间件
  压成"不推送"（zlib 在流式响应上会一直缓冲到流关闭）。

所以这里锁的是**行为**，不是实现细节：SSE 那组直接驱动真实端点函数，
不复制一份生成器逻辑（复制了就测不到线上那份代码了）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.core.sse import SSE_RESPONSE_HEADERS, sse_response
from app.plugin.module_train.torchkiln_executor import progress_from_rows


class TestProgressFromRows:
    """``progress`` 由 epoch/total_epochs 推算。"""

    def test_step_row(self):
        assert progress_from_rows([{"_kind": "step", "epoch": 3, "total_epochs": 60}]) == 5

    def test_empty_returns_none(self):
        assert progress_from_rows([]) is None

    def test_best_row_without_total_epochs_returns_none(self):
        """``_kind="best"`` 的行**不带** total_epochs——不能拿它当分母。"""
        assert progress_from_rows([{"_kind": "best", "epoch": 5}]) is None

    def test_skips_trailing_best_row_and_uses_earlier_step(self):
        rows = [
            {"_kind": "step", "epoch": 7, "total_epochs": 60},
            {"_kind": "best", "epoch": 8},
        ]
        assert progress_from_rows(rows) == 12

    def test_zero_denominator_returns_none(self):
        """分母为 0 不能除——否则前端会显示 Infinity/NaN。"""
        assert progress_from_rows([{"_kind": "step", "epoch": 3, "total_epochs": 0}]) is None

    @pytest.mark.parametrize(
        ("epoch", "total", "expected"),
        [
            (10, 1, 100),    # 前端曾因此显示 1000%
            (61, 60, 100),   # 超界
            (0, 60, 0),
            (60, 60, 100),
        ],
    )
    def test_clamped_to_0_100(self, epoch, total, expected):
        assert progress_from_rows([{"epoch": epoch, "total_epochs": total}]) == expected

    def test_non_int_types_ignored(self):
        """epoch 可能是字符串或 None，不能直接参与除法。"""
        assert progress_from_rows([{"epoch": "3", "total_epochs": 60}]) is None
        assert progress_from_rows([{"epoch": None, "total_epochs": 60}]) is None


class TestSSEHeaders:
    """SSE 响应头：少任何一个，实时流都不工作。"""

    def test_declares_identity_to_bypass_gzip(self):
        # 这是整条修复的关键：命中 starlette GZipResponder 的透传分支。
        # 缺了它，zlib 会把整个 SSE 流压在内部缓冲里直到流关闭——
        # 实测 229 帧共约 14KB，gzip 下 62 秒只发出 10 字节 gzip 头。
        assert SSE_RESPONSE_HEADERS["Content-Encoding"] == "identity"

    def test_proxy_buffering_disabled(self):
        assert "no-transform" in SSE_RESPONSE_HEADERS["Cache-Control"]
        assert SSE_RESPONSE_HEADERS["X-Accel-Buffering"] == "no"

    def test_response_actually_carries_the_headers(self):
        async def gen():
            yield "data: hi\n\n"

        resp = sse_response(gen())
        got = {k.decode().lower(): v.decode() for k, v in resp.raw_headers}
        assert got["content-type"].startswith("text/event-stream")
        assert got["content-encoding"] == "identity"
        assert got["x-accel-buffering"] == "no"
        assert "no-transform" in got["cache-control"]


class _FakeRequest:
    """最小 Request 替身：端点只用 ``is_disconnected()``。"""

    async def is_disconnected(self) -> bool:
        return False


def _drain(response) -> str:
    """把 StreamingResponse 的 body 迭代器跑完，返回拼接文本。

    跑不完就说明流挂死了——那正是本组用例要防的回归，所以给一个硬超时。
    """

    async def run():
        chunks = []
        async for piece in response.body_iterator:
            chunks.append(piece if isinstance(piece, str) else piece.decode())
        return "".join(chunks)

    try:
        return asyncio.run(asyncio.wait_for(run(), timeout=5))
    except TimeoutError:
        pytest.fail("SSE 生成器没有收流（终态作业会永远挂死）")


class TestSSEEndpoint:
    """直接驱动真实端点 ``stream_task_metrics``。"""

    def test_terminal_task_replays_end_then_closes(self, monkeypatch):
        """终态作业：补发历史 → 补一帧 end → **自己收流**。

        以前没有终态判断，流会一直挂在 ``while True`` 上等一个永远不会来的
        ``end``（实测 62 秒一帧不到，连接直到客户端超时才断）。
        """
        from app.plugin.module_train import controller as ctrl
        from app.plugin.module_train import torchkiln_executor as te

        rows = [
            {"seq": 0, "_kind": "step", "epoch": 1, "total_epochs": 3, "loss": 1.0},
            {"seq": 1, "_kind": "end", "epoch": 3, "total_epochs": 3},
        ]

        async def fake_rows(_task_id):
            return list(rows)

        async def fake_terminal(_task_id):
            return True

        def _boom(_task_id):
            raise AssertionError("终态作业不应进入订阅等待（会挂死）")

        monkeypatch.setattr(te, "load_metrics_rows", fake_rows)
        monkeypatch.setattr(te, "task_is_terminal", fake_terminal, raising=False)
        monkeypatch.setattr(te, "subscribe_metrics", _boom)

        resp = asyncio.run(ctrl.stream_task_metrics(123, _FakeRequest(), -1, None))
        text = _drain(resp)

        assert "retry: 3000" in text
        assert "event: metric" in text
        assert "event: end" in text
        assert '"replayed": true' in text
        # 响应头必须带 identity，否则上面这些帧到浏览器已被 GZip 吞掉
        got = {k.decode().lower(): v.decode() for k, v in resp.raw_headers}
        assert got["content-encoding"] == "identity"

    def test_offset_skips_already_consumed_rows(self, monkeypatch):
        """offset 断点续传：只补 seq>offset 的历史，不重发旧数据。"""
        from app.plugin.module_train import controller as ctrl
        from app.plugin.module_train import torchkiln_executor as te

        rows = [
            {"seq": 0, "_kind": "step", "epoch": 1, "total_epochs": 3},
            {"seq": 1, "_kind": "step", "epoch": 2, "total_epochs": 3},
            {"seq": 2, "_kind": "end", "epoch": 3, "total_epochs": 3},
        ]

        async def fake_rows(_task_id):
            return list(rows)

        async def fake_terminal(_task_id):
            return True

        def _boom(_task_id):
            raise AssertionError("不应进入订阅等待")

        monkeypatch.setattr(te, "load_metrics_rows", fake_rows)
        monkeypatch.setattr(te, "task_is_terminal", fake_terminal, raising=False)
        monkeypatch.setattr(te, "subscribe_metrics", _boom)

        resp = asyncio.run(ctrl.stream_task_metrics(123, _FakeRequest(), 1, None))
        text = _drain(resp)

        # offset 的语义是「最后已消费的 seq」，所以 seq<=1 都不再补发
        assert '"seq": 0' not in text
        assert '"seq": 1' not in text
        assert '"seq": 2' in text
        # 帧数可数：恰好 1 条 metric（seq 2）+ 1 条 end
        assert text.count("event: metric") == 1

    def test_end_payload_carries_final_metrics(self, monkeypatch):
        """补发的 end 帧要带上最后一帧指标，前端才有终值可画。"""
        from app.plugin.module_train import controller as ctrl
        from app.plugin.module_train import torchkiln_executor as te

        end_row = {"seq": 9, "_kind": "end", "epoch": 30, "total_epochs": 30,
                   "main_value": 0.78, "exit_reason": "finished"}

        async def fake_rows(_task_id):
            return [end_row]

        async def fake_terminal(_task_id):
            return True

        def _boom(_task_id):
            raise AssertionError("不应进入订阅等待")

        monkeypatch.setattr(te, "load_metrics_rows", fake_rows)
        monkeypatch.setattr(te, "task_is_terminal", fake_terminal, raising=False)
        monkeypatch.setattr(te, "subscribe_metrics", _boom)

        resp = asyncio.run(ctrl.stream_task_metrics(123, _FakeRequest(), -1, None))
        text = _drain(resp)
        payload = json.loads(text.split("event: end", 1)[1].split("data: ", 1)[1].strip())
        assert payload["_kind"] == "end"
        assert payload["main_value"] == 0.78
        assert payload["exit_reason"] == "finished"
        assert payload["seq"] == 9
