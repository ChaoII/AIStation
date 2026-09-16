"""布控任务编排测试：TaskConfig 编译、能力校验、Agent 客户端错误包装。"""
import asyncio

import httpx
import pytest

from app.api.v1.module_video.edge.orchestrator import (
    EdgeOrchestrator,
    build_agent_task_config,
)


class _Cam:
    id = 7
    name = "北门"
    rtsp_url_sub = "rtsp://cam/7"
    stream_id = "cam7"


class _Alg:
    name = "入侵检测"
    algorithm_type = "INTRUSION"
    model_path = "s3://m/det.onnx"
    runtime_config = {"backend": "trt", "device": "gpu"}
    preset_params = {"conf_threshold": 0.45}


class _Task:
    id = 123
    camera_id = 7
    algorithm_id = 1
    stream_type = "SUB"
    detect_region = {"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}
    sensitivity = 60
    schedule_json = {"days": [0, 1], "start": "08:00", "end": "18:00"}


def test_build_task_config_basic():
    cfg = build_agent_task_config(_Task(), _Cam(), _Alg(), events={"transport": "http", "http": {"url": "http://cloud/cb", "token": "t"}})
    assert cfg["task_id"] == 123
    assert cfg["camera"]["url"].startswith("rtsp://")
    assert cfg["models"][0]["type"] in ("det", "detection")
    assert cfg["roi"][0][0] == 0.1
    assert cfg["events"]["transport"] == "http"


def test_build_task_config_roi_from_xyxy():
    class _TaskBox(_Task):
        detect_region = {"x1": 0.2, "y1": 0.3, "x2": 0.8, "y2": 0.9}

    cfg = build_agent_task_config(_TaskBox(), _Cam(), _Alg(), events={})
    assert cfg["roi"] == [[0.2, 0.3], [0.8, 0.3], [0.8, 0.9], [0.2, 0.9]]
    assert cfg["models"][0]["backend"] == "trt"
    assert cfg["models"][0]["confidence_threshold"] == 0.45


def test_capability_path_rejects_unsupported():
    caps = {"model_families": ["ocr"], "backends": ["trt"], "max_channels": 4}
    ok, reason = EdgeOrchestrator._check_capability(caps, _Alg(), running_channels=0)
    assert ok is False
    assert reason


def test_capability_path_accepts_supported():
    caps = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = EdgeOrchestrator._check_capability(caps, _Alg(), running_channels=1)
    assert ok is True
    assert reason == ""


class _TaskWithRefs(_Task):
    camera = _Cam()
    algorithm = _Alg()


def test_start_task_capability_failure_marks_error(monkeypatch):
    from app.api.v1.module_video.edge import orchestrator
    from app.core.exceptions import CustomException

    class _Dev:
        id = 5
        code = "edge-01"
        control_url = "http://edge:19090"
        secret = "s"
        capabilities = {"model_families": ["ocr"], "backends": ["trt"], "max_channels": 4}

    async def _load_task(task_id):
        return _TaskWithRefs()

    async def _resolve(task):
        return "http://edge:19090", _Dev()

    async def _count(device_id, exclude_id):
        return 0

    marked = {}

    async def _update(task_id, status, error_log=None):
        marked["status"] = status
        marked["error_log"] = error_log

    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_load_task", staticmethod(_load_task))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_count_running", staticmethod(_count))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_update_status", staticmethod(_update))

    with pytest.raises(CustomException) as exc:
        asyncio.run(orchestrator.EdgeOrchestrator.start_task(123))
    assert "能力" in exc.value.msg
    assert marked["status"] == "ERROR"
    assert marked["error_log"]


def test_start_task_dispatches_and_marks_running(monkeypatch):
    from app.api.v1.module_video.edge import orchestrator

    class _Dev:
        id = 5
        code = "edge-01"
        control_url = "http://edge:19090"
        secret = "s"
        capabilities = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}

    calls = []

    class _FakeClient:
        def __init__(self, control_url, secret):
            calls.append(("init", control_url, secret))

        async def dispatch(self, config):
            calls.append(("dispatch", config))
            return {}

        async def start(self, task_id):
            calls.append(("start", task_id))
            return {}

    async def _load_task(task_id):
        return _TaskWithRefs()

    async def _resolve(task):
        return "http://edge:19090", _Dev()

    async def _count(device_id, exclude_id):
        return 0

    marked = {}

    async def _update(task_id, status, error_log=None):
        marked["status"] = status

    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_load_task", staticmethod(_load_task))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_count_running", staticmethod(_count))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_update_status", staticmethod(_update))
    monkeypatch.setattr(orchestrator, "EdgeAgentClient", _FakeClient)
    monkeypatch.setattr(orchestrator, "build_events", lambda camera_id, edge_code: {"transport": "http"})

    result = asyncio.run(orchestrator.EdgeOrchestrator.start_task(123))
    assert result["delegated"] is True
    assert result["status"] == "RUNNING"
    assert calls[1][0] == "dispatch"
    assert calls[1][1]["task_id"] == 123
    assert calls[2] == ("start", 123)
    assert marked["status"] == "RUNNING"


def test_delete_task_invokes_agent_delete_for_edge_device(monkeypatch):
    from app.api.v1.module_video.edge import orchestrator

    class _Dev:
        id = 5
        code = "edge-01"
        control_url = "http://edge:19090"
        secret = "s"

    calls = []

    class _FakeClient:
        def __init__(self, control_url, secret):
            calls.append(("init", control_url, secret))

        async def delete(self, task_id):
            calls.append(("delete", task_id))
            return {}

    async def _load_task(task_id):
        return _TaskWithRefs()

    async def _resolve(task):
        return "http://edge:19090", _Dev()

    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_load_task", staticmethod(_load_task))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(orchestrator, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(orchestrator.EdgeOrchestrator.delete_task(123))
    assert calls == [("init", "http://edge:19090", "s"), ("delete", 123)]
    assert result["delegated"] is True


def test_delete_task_skips_when_no_device(monkeypatch):
    from app.api.v1.module_video.edge import orchestrator

    calls = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            calls.append("init")

        async def delete(self, task_id):
            calls.append("delete")

    async def _load_task(task_id):
        return _TaskWithRefs()

    async def _resolve(task):
        return None, None

    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_load_task", staticmethod(_load_task))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(orchestrator, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(orchestrator.EdgeOrchestrator.delete_task(123))
    assert calls == []
    assert result["delegated"] is False


def test_delete_task_ignores_agent_error(monkeypatch):
    from app.api.v1.module_video.edge import orchestrator
    from app.core.exceptions import CustomException

    class _Dev:
        id = 5
        code = "edge-01"
        control_url = "http://edge:19090"
        secret = "s"

    class _FakeClient:
        def __init__(self, control_url, secret):
            pass

        async def delete(self, task_id):
            raise CustomException(msg="边缘 Agent 请求失败", code=502, status_code=502)

    async def _load_task(task_id):
        return _TaskWithRefs()

    async def _resolve(task):
        return "http://edge:19090", _Dev()

    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_load_task", staticmethod(_load_task))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(orchestrator, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(orchestrator.EdgeOrchestrator.delete_task(123))
    assert result["status"] == "SKIPPED"


def test_agent_client_wraps_http_error(monkeypatch):
    from app.api.v1.module_video.edge.agent_client import EdgeAgentClient
    from app.core.exceptions import CustomException

    async def _boom(self, method, url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "request", _boom)
    client = EdgeAgentClient("http://edge:19090", "sec")
    with pytest.raises(CustomException) as exc:
        asyncio.run(client.dispatch({"task_id": 1}))
    assert "Agent" in exc.value.msg or "边缘" in exc.value.msg
