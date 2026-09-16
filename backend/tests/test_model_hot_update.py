"""模型热更新/回滚接口测试（SP6-c Task 4）。

覆盖：
- AlgorithmModel 新增 previous_model_path/previous_version 两列与输出 Schema；
- 算法更新时模型变更才记录 previous_*（无关字段不写）；
- hot-update 枚举引用任务、逐任务下发、成功/部分失败汇总（不再改写 previous_*）；
- EdgeAgentClient 调用异常被捕获计入 failed（不向上抛出）；
- rollback 交换 previous_* 并按旧模型下发；
- 无可回滚版本 → 400。
"""
import asyncio

import pytest

from app.api.v1.module_video.algorithm import service as algorithm_service
from app.api.v1.module_video.algorithm.model import AlgorithmModel
from app.api.v1.module_video.algorithm.schema import AlgorithmOutSchema, AlgorithmUpdateSchema
from app.api.v1.module_video.algorithm.service import AlgorithmService
from app.api.v1.module_video.edge import orchestrator
from app.core.exceptions import CustomException


class _Obj:
    """极简属性容器，替代真实 ORM 对象，避免单测依赖数据库。"""

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


def _make_task(task_id: int, edge_device_id: int | None = 5) -> _Obj:
    return _Obj(
        id=task_id,
        camera_id=7,
        algorithm_id=1,
        edge_device_id=edge_device_id,
        stream_type="SUB",
        detect_region=None,
        sensitivity=50,
        schedule_json={},
        runtime_overrides={},
        params_overrides={},
        camera=_Camera(),
    )


def _make_algorithm(**overrides) -> _Obj:
    base = {
        "id": 1,
        "name": "入侵检测",
        "code": "INTRUSION",
        "algorithm_type": "INTRUSION",
        "scene_type": None,
        "model_path": "s3://m/v2.onnx",
        "version": "2.0.0",
        "runtime_config": {"backend": "trt", "device": "gpu"},
        "preset_params": {"conf_threshold": 0.45},
        "previous_model_path": None,
        "previous_version": None,
    }
    base.update(overrides)
    return _Obj(**base)


def _install(monkeypatch, algorithm, tasks, persist=None):
    """装好算法加载/任务枚举/持久化/边缘目标解析等桩，返回记录容器。"""

    async def _load(id, auth):
        return algorithm

    async def _list(algorithm_id):
        return tasks

    async def _persist(algorithm_id, values, auth):
        if persist is not None:
            persist.append((algorithm_id, values))

    async def _resolve(task):
        return "http://edge:19090", _Device()

    monkeypatch.setattr(AlgorithmService, "_load_algorithm", staticmethod(_load))
    monkeypatch.setattr(AlgorithmService, "_list_referencing_tasks", staticmethod(_list))
    monkeypatch.setattr(AlgorithmService, "_persist_algorithm_fields", staticmethod(_persist))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))


def _install_crud(monkeypatch, algorithm, updates, loads=None):
    """装好 AlgorithmCRUD 桩：读取返回给定算法，更新记录并写回算法对象。"""

    class _FakeCRUD:
        def __init__(self, auth=None):
            pass

        async def get_by_id_crud(self, id):
            if loads is not None:
                loads.append(id)
            return algorithm

        async def update(self, id, data):
            values = data if isinstance(data, dict) else data.model_dump(exclude_unset=True)
            updates.append((id, values))
            for key, value in values.items():
                setattr(algorithm, key, value)
            return algorithm

    monkeypatch.setattr(algorithm_service, "AlgorithmCRUD", _FakeCRUD)


def test_previous_columns_in_model_and_schema():
    """新增两列可空，且输出 Schema 暴露两字段。"""
    col_path = AlgorithmModel.__table__.c.previous_model_path
    col_ver = AlgorithmModel.__table__.c.previous_version
    assert col_path.nullable is True
    assert col_path.type.length == 512
    assert col_ver.nullable is True
    assert col_ver.type.length == 32
    assert "previous_model_path" in AlgorithmOutSchema.model_fields
    assert "previous_version" in AlgorithmOutSchema.model_fields


def test_list_referencing_tasks_filters_by_algorithm(monkeypatch):
    """引用任务枚举按 algorithm_id 过滤，且排除软删除。"""
    seen: list[str] = []
    rows = [_make_task(11)]

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return rows

    class _Session:
        async def execute(self, stmt):
            seen.append(str(stmt))
            return _Result()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(algorithm_service, "async_db_session", lambda: _Session())

    result = asyncio.run(AlgorithmService._list_referencing_tasks(1))

    assert result == rows
    assert "video_algorithm_tasks" in seen[0]
    assert "algorithm_id" in seen[0]
    assert "is_deleted" in seen[0]


def test_hot_update_enumerates_and_dispatches(monkeypatch):
    """枚举全部引用任务并逐任务下发（热更新本身不再改写 previous_*）。"""
    algorithm = _make_algorithm()
    tasks = [_make_task(11), _make_task(22)]
    persist: list = []
    calls: list = []

    class _FakeClient:
        def __init__(self, control_url, secret):
            calls.append(("init", control_url, secret))

        async def _request(self, method, path, json=None):
            calls.append((method, path, json))
            return {"ok": True, "generation": 1}

    _install(monkeypatch, algorithm, tasks, persist=persist)
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(AlgorithmService.hot_update_service(id=1, auth=None))

    assert result == {"succeeded": [11, 22], "failed": []}
    posts = [c for c in calls if c[0] == "POST"]
    assert [c[1] for c in posts] == [
        "/api/v1/tasks/11/models/入侵检测/update",
        "/api/v1/tasks/22/models/入侵检测/update",
    ]
    # 载荷与编排编译出的模型条目同形（name/url 一致）
    assert posts[0][2]["name"] == "入侵检测"
    assert posts[0][2]["url"] == "s3://m/v2.onnx"
    # 热更新只下发，不再写 previous_*（记录职责移至算法更新路径）
    assert persist == []
    assert algorithm.previous_model_path is None
    assert algorithm.previous_version is None


def test_update_model_path_records_previous_model_path(monkeypatch):
    """更新 model_path 时把旧值记入 previous_model_path；version 未变则不动 previous_version。"""
    algorithm = _make_algorithm(model_path="s3://m/v2.onnx", version="2.0.0")
    updates: list = []
    _install_crud(monkeypatch, algorithm, updates)

    result = asyncio.run(
        AlgorithmService.update_algorithm_service(
            id=1, data=AlgorithmUpdateSchema(algorithm_type="INTRUSION", model_path="s3://m/v3.onnx"), auth=None
        )
    )

    assert updates == [
        (
            1,
            {
                "algorithm_type": "INTRUSION",
                "model_path": "s3://m/v3.onnx",
                "previous_model_path": "s3://m/v2.onnx",
            },
        )
    ]
    assert result["previous_model_path"] == "s3://m/v2.onnx"
    assert result["previous_version"] is None
    assert result["model_path"] == "s3://m/v3.onnx"


def test_update_version_records_only_previous_version(monkeypatch):
    """仅更新 version 时只记录 previous_version。"""
    algorithm = _make_algorithm(model_path="s3://m/v2.onnx", version="2.0.0")
    updates: list = []
    _install_crud(monkeypatch, algorithm, updates)

    asyncio.run(
        AlgorithmService.update_algorithm_service(
            id=1, data=AlgorithmUpdateSchema(algorithm_type="INTRUSION", version="3.0.0"), auth=None
        )
    )

    assert updates == [
        (1, {"algorithm_type": "INTRUSION", "version": "3.0.0", "previous_version": "2.0.0"})
    ]
    assert algorithm.previous_model_path is None
    assert algorithm.previous_version == "2.0.0"


def test_update_unrelated_field_does_not_touch_previous(monkeypatch):
    """更新无关字段（description）不影响 previous_*。"""
    algorithm = _make_algorithm(
        previous_model_path="s3://m/v1.onnx", previous_version="1.0.0"
    )
    updates: list = []
    _install_crud(monkeypatch, algorithm, updates)

    asyncio.run(
        AlgorithmService.update_algorithm_service(
            id=1, data=AlgorithmUpdateSchema(algorithm_type="INTRUSION", description="新描述"), auth=None
        )
    )

    assert updates == [(1, {"algorithm_type": "INTRUSION", "description": "新描述"})]
    assert algorithm.previous_model_path == "s3://m/v1.onnx"
    assert algorithm.previous_version == "1.0.0"


def test_update_same_model_path_does_not_record_previous(monkeypatch):
    """传入值与库中相同（未真正变化）时不记录 previous_*。"""
    algorithm = _make_algorithm(model_path="s3://m/v2.onnx", version="2.0.0")
    updates: list = []
    _install_crud(monkeypatch, algorithm, updates)

    asyncio.run(
        AlgorithmService.update_algorithm_service(
            id=1,
            data=AlgorithmUpdateSchema(algorithm_type="INTRUSION", model_path="s3://m/v2.onnx", version="2.0.0"),
            auth=None,
        )
    )

    assert updates == [
        (1, {"algorithm_type": "INTRUSION", "model_path": "s3://m/v2.onnx", "version": "2.0.0"})
    ]
    assert algorithm.previous_model_path is None
    assert algorithm.previous_version is None


def test_flow_update_hot_update_rollback_restores_previous(monkeypatch):
    """update → hot-update（仅下发）→ rollback 真正恢复到变更前的版本。"""
    algorithm = _make_algorithm(model_path="s3://m/v2.onnx", version="2.0.0")
    tasks = [_make_task(11)]
    updates: list = []
    payloads: list = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            payloads.append(json)
            return {"ok": True, "generation": 1}

    async def _list(algorithm_id):
        return tasks

    async def _resolve(task):
        return "http://edge:19090", _Device()

    _install_crud(monkeypatch, algorithm, updates)
    monkeypatch.setattr(AlgorithmService, "_list_referencing_tasks", staticmethod(_list))
    monkeypatch.setattr(orchestrator.EdgeOrchestrator, "_resolve_target", staticmethod(_resolve))
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    # ① 用户把算法改为新版本 → 旧值记入 previous_*
    asyncio.run(
        AlgorithmService.update_algorithm_service(
            id=1,
            data=AlgorithmUpdateSchema(algorithm_type="INTRUSION", model_path="s3://m/v3.onnx", version="3.0.0"),
            auth=None,
        )
    )
    assert algorithm.model_path == "s3://m/v3.onnx"
    assert algorithm.previous_model_path == "s3://m/v2.onnx"
    assert algorithm.previous_version == "2.0.0"

    # ② 热更新仅下发新版本，不改写 previous_*
    snapshot = list(updates)
    result = asyncio.run(AlgorithmService.hot_update_service(id=1, auth=None))
    assert result == {"succeeded": [11], "failed": []}
    assert payloads[-1]["url"] == "s3://m/v3.onnx"
    assert updates == snapshot
    assert algorithm.previous_model_path == "s3://m/v2.onnx"
    assert algorithm.previous_version == "2.0.0"

    # ③ 回滚 → 当前值回到更新前；previous_* 变为热更新期间在用的版本
    asyncio.run(AlgorithmService.rollback_service(id=1, auth=None))
    assert algorithm.model_path == "s3://m/v2.onnx"
    assert algorithm.version == "2.0.0"
    assert algorithm.previous_model_path == "s3://m/v3.onnx"
    assert algorithm.previous_version == "3.0.0"
    assert payloads[-1]["url"] == "s3://m/v2.onnx"


def test_hot_update_on_algorithm_with_empty_previous_leaves_them_empty(monkeypatch):
    """算法无 previous_* 时热更新仍保持为空（不凭空写入）。"""
    algorithm = _make_algorithm(previous_model_path=None, previous_version=None)
    persist: list = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            return {"ok": True, "generation": 1}

    _install(monkeypatch, algorithm, [_make_task(11)], persist=persist)
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    asyncio.run(AlgorithmService.hot_update_service(id=1, auth=None))

    assert persist == []
    assert algorithm.previous_model_path is None
    assert algorithm.previous_version is None


def test_hot_update_partial_failure_is_isolated(monkeypatch):
    """单任务失败（异常或 ok=false）计入 failed，不影响其余任务。"""
    algorithm = _make_algorithm()
    tasks = [_make_task(11), _make_task(22), _make_task(33)]

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            if "/tasks/22/" in path:
                raise CustomException(msg="边缘 Agent 返回错误 404", code=502, status_code=502)
            if "/tasks/33/" in path:
                return {"ok": False, "error": "模型自检失败"}
            return {"ok": True, "generation": 1}

    _install(monkeypatch, algorithm, tasks)
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(AlgorithmService.hot_update_service(id=1, auth=None))

    assert result["succeeded"] == [11]
    assert [f["task_id"] for f in result["failed"]] == [22, 33]
    assert "404" in result["failed"][0]["error"]
    assert "自检失败" in result["failed"][1]["error"]


def test_rollback_swaps_previous_and_dispatches_old_model(monkeypatch):
    """rollback 交换 previous_* 与当前值，并按恢复后的旧模型下发。"""
    algorithm = _make_algorithm(
        model_path="s3://m/v2.onnx",
        version="2.0.0",
        previous_model_path="s3://m/v1.onnx",
        previous_version="1.0.0",
    )
    tasks = [_make_task(11)]
    persist: list = []
    payloads: list = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            payloads.append(json)
            return {"ok": True, "generation": 2}

    _install(monkeypatch, algorithm, tasks, persist=persist)
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(AlgorithmService.rollback_service(id=1, auth=None))

    assert result == {"succeeded": [11], "failed": []}
    assert algorithm.model_path == "s3://m/v1.onnx"
    assert algorithm.version == "1.0.0"
    assert algorithm.previous_model_path == "s3://m/v2.onnx"
    assert algorithm.previous_version == "2.0.0"
    assert persist == [
        (
            1,
            {
                "model_path": "s3://m/v1.onnx",
                "version": "1.0.0",
                "previous_model_path": "s3://m/v2.onnx",
                "previous_version": "2.0.0",
            },
        )
    ]
    assert payloads[0]["url"] == "s3://m/v1.onnx"


def test_rollback_without_previous_raises_400(monkeypatch):
    """无 previous_* 时回滚返回 400。"""
    algorithm = _make_algorithm(previous_model_path=None, previous_version=None)
    _install(monkeypatch, algorithm, [])

    with pytest.raises(CustomException) as exc:
        asyncio.run(AlgorithmService.rollback_service(id=1, auth=None))

    assert exc.value.code == 400


def test_hot_update_unknown_algorithm_raises_404(monkeypatch):
    """算法不存在时返回 404。"""

    async def _load(id, auth):
        return None

    monkeypatch.setattr(AlgorithmService, "_load_algorithm", staticmethod(_load))

    with pytest.raises(CustomException) as exc:
        asyncio.run(AlgorithmService.hot_update_service(id=999, auth=None))

    assert exc.value.code == 404


def test_rollback_all_failed_compensates_db_and_raises(monkeypatch):
    """回滚下发全部失败：还原 DB 交换并抛出可操作错误（避免 DB/Agent 静默不一致）。"""
    algorithm = _make_algorithm(
        model_path="s3://m/v2.onnx",
        version="2.0.0",
        previous_model_path="s3://m/v1.onnx",
        previous_version="1.0.0",
    )
    tasks = [_make_task(11), _make_task(22)]
    persist: list = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            raise CustomException(msg="边缘 Agent 不可达", code=502, status_code=502)

    _install(monkeypatch, algorithm, tasks, persist=persist)
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    with pytest.raises(CustomException) as exc:
        asyncio.run(AlgorithmService.rollback_service(id=1, auth=None))

    assert exc.value.code == 502
    # 第一次写：交换；第二次写：补偿还原（回到当前值 v2/2.0.0）
    assert [p[1]["model_path"] for p in persist] == ["s3://m/v1.onnx", "s3://m/v2.onnx"]
    assert persist[-1][1] == {
        "model_path": "s3://m/v2.onnx",
        "version": "2.0.0",
        "previous_model_path": "s3://m/v1.onnx",
        "previous_version": "1.0.0",
    }


def test_retry_dispatch_only_requested_tasks(monkeypatch):
    """重试下发只针对指定失败任务，返回同一 succeeded/failed 结构。"""
    algorithm = _make_algorithm()
    tasks = [_make_task(11), _make_task(22), _make_task(33)]
    paths: list = []

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def _request(self, method, path, json=None):
            paths.append(path)
            if "/tasks/33/" in path:
                return {"ok": False, "error": "模型自检失败"}
            return {"ok": True, "generation": 1}

    _install(monkeypatch, algorithm, tasks)
    monkeypatch.setattr(algorithm_service, "EdgeAgentClient", _FakeClient)

    result = asyncio.run(AlgorithmService.retry_dispatch_service(id=1, task_ids=[11, 33], auth=None))

    assert result["succeeded"] == [11]
    assert [f["task_id"] for f in result["failed"]] == [33]
    assert len(paths) == 2  # 未重试未指定的 22
    assert all("/tasks/22/" not in p for p in paths)


def test_retry_dispatch_unknown_tasks_raises_400(monkeypatch):
    algorithm = _make_algorithm()
    _install(monkeypatch, algorithm, [_make_task(11)])

    with pytest.raises(CustomException) as exc:
        asyncio.run(AlgorithmService.retry_dispatch_service(id=1, task_ids=[999], auth=None))

    assert exc.value.code == 400
