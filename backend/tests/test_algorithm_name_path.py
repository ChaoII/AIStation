"""算法名拼入 Agent 请求路径的注入防护测试（审计 #15）。

覆盖：
- ``AlgorithmCreateSchema`` 拒绝含路径分隔符/控制字符的名称；
- 派发路径对名称做百分号编码（保留中文等非 ASCII，避免改变既有请求形状）；
- 热更新下发的 URL 路径段被编码，``/``、``?`` 等无法改变请求语义。
"""
import asyncio

import pytest
from pydantic import ValidationError

from app.api.v1.module_video.algorithm import service as algorithm_service
from app.api.v1.module_video.algorithm.schema import AlgorithmCreateSchema
from app.api.v1.module_video.algorithm.service import AlgorithmService


class _Obj:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Camera:
    id = 7
    name = "北门"
    rtsp_url_main = "rtsp://cam/7/main"
    rtsp_url_sub = "rtsp://cam/7/sub"
    stream_id = "cam7"


class _Device:
    id = 5
    code = "edge-01"
    control_url = "http://edge:19090"
    secret = "s"


def test_schema_rejects_path_separators():
    for bad in ("a/b", "a\\b", "a\nb", "a\x00b", "a\tb"):
        with pytest.raises(ValidationError):
            AlgorithmCreateSchema(name=bad, code="C", algorithm_type="DET_ZONE")


def test_schema_allows_chinese_and_spaces():
    obj = AlgorithmCreateSchema(name="区域 入侵检测", code="C", algorithm_type="DET_ZONE")
    assert obj.name == "区域 入侵检测"


def test_dispatch_encodes_dangerous_name(monkeypatch):
    """名称含保留字符时，路径段必须被百分号编码（不改动请求语义）。"""
    algorithm = _Obj(
        id=1,
        # 模拟历史遗留的非法名称（新代码已在 schema 层拒绝，但旧数据仍需安全派发）
        name="a/b?c#d",
        code="X",
        algorithm_type="DET_ZONE",
        scene_type=None,
        model_path="s3://m/x.onnx",
        version="1.0.0",
        runtime_config={},
        preset_params={},
        previous_model_path=None,
        previous_version=None,
    )
    task = _Obj(
        id=11,
        camera_id=7,
        algorithm_id=1,
        edge_device_id=5,
        stream_type="SUB",
        detect_region=None,
        sensitivity=50,
        schedule_json={},
        runtime_overrides={},
        params_overrides={},
        camera=_Camera(),
    )
    paths: list[str] = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            paths.append(path)
            return {"ok": True}

    async def _load(id, auth):
        return algorithm

    async def _list(algorithm_id):
        return [task]

    async def _resolve(t):
        return "http://edge:19090", _Device()

    from app.api.v1.module_video.edge import orchestrator

    monkeypatch.setattr(AlgorithmService, "_load_algorithm", staticmethod(_load))
    monkeypatch.setattr(AlgorithmService, "_list_referencing_tasks", staticmethod(_list))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    asyncio.run(AlgorithmService.hot_update_service(id=1, auth=None))

    assert paths == ["/api/v1/tasks/11/models/a%2Fb%3Fc%23d/update"]
    assert "/a/b" not in paths[0]
