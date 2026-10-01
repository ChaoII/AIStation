"""预测链路的 TorchKiln 契约测试。

背景
----
2026-10 抽 ``job_runner`` 时顺手给预测链路补了 e2e，一跑就暴露出**三个从未被发现的
bug**——这条链路自接入 TorchKiln 起就没跑通过，只是此前没有 e2e 覆盖：

1. ``build_predict_cmd`` 照着 ``tkiln val`` 的样子拼 ``-o Global.pretrained_model=...``，
   而 ``tkiln predict`` 是 argparse 风格（``--weights``/``--input``）→ 容器内
   argparse 直接报「the following arguments are required」。
2. 数据集导出传的是 ``framework.value``（``"torchkiln"``）而不是布局名
   ``YOLO_LAYOUT``（``"ultralytics"``）→ ``_export_core`` 抛「不支持的导出框架」。
3. ``resolve_predict_tk_config`` 拿 ``TrainModel.repo_id``（仓库 id）去比
   ``TrainTask.model_repo_id``（实测存的是**版本行 id**）→ 永远匹配不到，
   恒返回 None。

以及两个「静默丢结果 / 同名覆盖」的结果收集坑（见 ``collect_result_images``）。

2026-10 追加：预测也改走了 HTTP 作业通路，因此**删除了** ``build_predict_cmd``
（命令改由 TorchKiln 服务侧的 ``build_predict_argv`` 拼）。下面 2、3 两组测试
对应当时暴露的三个 bug，仍然有效；命令形状的断言已迁到 TorchKiln 侧。

这里把契约钉住，防止再漂回去。真实链路验证靠 ``%TEMP%\\e2e_jobrunner.py``。
"""

import os
from types import SimpleNamespace

import pytest

from app.plugin.module_train import predict_executor as pe
from app.plugin.module_train.predict_executor import (
    build_predict_spec,
    collect_result_images,
    resolve_predict_tk_config,
)

# ---------------------------------------------------------------------------
# 2. 数据集导出必须传布局名 YOLO_LAYOUT，不能传 framework.value
# ---------------------------------------------------------------------------


def test_yolo_layout_is_not_framework_value():
    """守住「布局名 ≠ 框架名」这个区分。

    ``_export_core`` 按**目录布局名**分发；``framework.value`` 在 TorchKiln 下是
    ``"torchkiln"``，直接传进去就是「不支持的导出框架」。
    """
    from app.plugin.module_train.exporter import YOLO_LAYOUT

    assert YOLO_LAYOUT == "ultralytics"
    assert YOLO_LAYOUT != "torchkiln"


def test_exporter_rejects_framework_name_as_layout(tmp_path, monkeypatch):
    """把 ``framework.value`` 当布局名传，导出层必须报错而不是猜。

    注意 ``_export_core`` 在分发**之前**有一道``if not images: return`` 守卫，
    所以这里必须先桩出非空图片集，否则会在到达框架分发前就静默返回——
    那正是历史上「传错布局名却看不出原因」的一部分。
    """
    from app.plugin.module_train.exporters import dispatch

    class _Scalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _Res:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _Scalars(self._rows)

    class _Sess:
        async def execute(self, _stmt):
            return _Res([SimpleNamespace(id=1, file_path="a.jpg")])

        async def get(self, *_a):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_e):
            return False

    monkeypatch.setattr(dispatch, "async_db_session", lambda: _Sess())

    with pytest.raises(Exception, match="不支持的导出框架"):
        _run(dispatch._export_core(123, 456, "torchkiln", str(tmp_path)))


# ---------------------------------------------------------------------------
# 3. 反查训练任务：按**版本行 id** 匹配，不是仓库 id
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeSession:
    """记录每次查询的 ``model_repo_id`` 匹配值，按匹配结果返回训练任务。"""

    def __init__(self, model_row, task, match_on):
        self._model_row = model_row
        self._task = task
        self._match_on = match_on
        self.queried: list = []

    async def get(self, _model, row_id):
        return self._model_row

    async def execute(self, stmt):
        # 从 where 条件里取出比较的值
        value = stmt.whereclause.right.value
        self.queried.append(value)
        return _FakeResult(self._task if value == self._match_on else None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _patch_session(monkeypatch, session):
    """把 ``async_db_session`` 换成返回假 session 的上下文管理器。"""
    monkeypatch.setattr(pe, "async_db_session", lambda: session)


def test_resolve_config_matches_version_row_id(monkeypatch):
    """``model_id`` 是版本行 id，``TrainTask.model_repo_id`` 存的也是版本行 id。

    这是修 bug #3 的核心断言：原来拿仓库 id 去比，永远匹配不到。
    """
    model_row = SimpleNamespace(id=140, repo_id=19)
    task = SimpleNamespace(framework="TORKILN", hyperparams={"model": "yolo11-seg"})
    session = _FakeSession(model_row, task, match_on=140)
    _patch_session(monkeypatch, session)

    cfg = _run(resolve_predict_tk_config(140))

    assert cfg == "yolo11-seg"
    # 第一个查询必须是版本行 id，不能是仓库 id
    assert session.queried[0] == 140


def test_resolve_config_falls_back_to_repo_id(monkeypatch):
    """万一某些老数据真把仓库 id 存进了 model_repo_id，用 repo_id 兜一次。"""
    model_row = SimpleNamespace(id=140, repo_id=19)
    task = SimpleNamespace(framework="TORKILN", hyperparams={"model": "yolo11-seg"})
    session = _FakeSession(model_row, task, match_on=19)
    _patch_session(monkeypatch, session)

    assert _run(resolve_predict_tk_config(140)) == "yolo11-seg"
    assert 140 in session.queried and 19 in session.queried


def test_resolve_config_returns_none_when_model_missing(monkeypatch):
    """模型行不存在：返回 None，不该抛。"""
    session = _FakeSession(None, None, match_on=0)
    _patch_session(monkeypatch, session)
    assert _run(resolve_predict_tk_config(999)) is None


def test_resolve_config_none_when_no_task(monkeypatch):
    """找不到产出该模型的训练任务：返回 None（上层会给出可读报错）。"""
    model_row = SimpleNamespace(id=140, repo_id=19)
    session = _FakeSession(model_row, None, match_on=0)
    _patch_session(monkeypatch, session)
    assert _run(resolve_predict_tk_config(140)) is None


def test_resolve_config_rejects_non_torchkiln_task(monkeypatch):
    """产出该模型的训练任务是退场框架 → 不给配置名。"""
    model_row = SimpleNamespace(id=140, repo_id=19)
    task = SimpleNamespace(framework="ULTRALYTICS", hyperparams={"model": "yolov8"})
    session = _FakeSession(model_row, task, match_on=140)
    _patch_session(monkeypatch, session)
    assert _run(resolve_predict_tk_config(140)) is None


# ---------------------------------------------------------------------------
# 4. 结果收集：递归 + 相对路径作标识
# ---------------------------------------------------------------------------


def _write(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def test_collect_walks_nested_dirs(tmp_path):
    """真实布局是 images/train、images/val —— 只扫顶层会得到空结果。"""
    _write(str(tmp_path / "images" / "train" / "a.jpg"))
    _write(str(tmp_path / "images" / "val" / "b.jpg"))

    rels = [rel for rel, _abs in collect_result_images(str(tmp_path))]
    assert rels == ["images/train/a.jpg", "images/val/b.jpg"]


def test_collect_uses_relative_path_to_avoid_name_collision(tmp_path):
    """``images/train/a.jpg`` 与 ``images/val/a.jpg`` 必须是两个不同标识。

    用 basename 当 key 时后者会静默覆盖前者，表现为「结果数对不上」。
    """
    _write(str(tmp_path / "images" / "train" / "same.jpg"))
    _write(str(tmp_path / "images" / "val" / "same.jpg"))

    rels = [rel for rel, _abs in collect_result_images(str(tmp_path))]
    assert len(rels) == 2
    assert len(set(rels)) == 2


def test_collect_skips_non_images(tmp_path):
    """日志、yaml、txt 不算结果图。"""
    _write(str(tmp_path / "a.jpg"))
    _write(str(tmp_path / "predict.log"))
    _write(str(tmp_path / "data.yaml"))
    _write(str(tmp_path / "notes.txt"))

    rels = [rel for rel, _abs in collect_result_images(str(tmp_path))]
    assert rels == ["a.jpg"]


def test_collect_is_deterministic(tmp_path):
    """顺序稳定：同一份产出两次收集结果必须一致（便于回归比对）。"""
    for n in ("c", "a", "b"):
        _write(str(tmp_path / n / f"{n}.jpg"))

    first = [rel for rel, _ in collect_result_images(str(tmp_path))]
    second = [rel for rel, _ in collect_result_images(str(tmp_path))]
    assert first == second == ["a/a.jpg", "b/b.jpg", "c/c.jpg"]


def test_collect_empty_dir(tmp_path):
    """空目录：空列表，不抛（上层据此不上传、不打包）。"""
    assert collect_result_images(str(tmp_path)) == []


def test_collect_abs_paths_exist(tmp_path):
    """返回的绝对路径必须真实存在，否则上传会炸。"""
    p = _write(str(tmp_path / "images" / "train" / "a.jpg"))
    _rel, abs_path = collect_result_images(str(tmp_path))[0]
    assert os.path.isfile(abs_path)
    assert abs_path == p


# ---------------------------------------------------------------------------


def _run(coro):
    """跑协程（集中放这里，便于将来换事件循环策略）。"""
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 5. 作业 spec 组装（HTTP 通路的接缝）
# ---------------------------------------------------------------------------


def test_predict_spec_shape():
    spec = build_predict_spec(
        config_path="configs/yolo/yolo11-seg.yml",
        weights_path="/workspace/model/best_accuracy.pth",
        input_dir="/workspace/source",
        params={"Global.conf": 0.25},
        resources={"gpu": 1, "gpu_memory_gb": 6},
    )
    assert spec["kind"] == "predict"
    assert spec["config_path"] == "configs/yolo/yolo11-seg.yml"
    assert spec["weights_path"] == "/workspace/model/best_accuracy.pth"
    assert spec["input_dir"] == "/workspace/source"
    assert spec["params"] == {"Global.conf": 0.25}
    assert spec["resources"] == {"gpu": 1, "gpu_memory_gb": 6}


def test_predict_spec_uses_input_dir_not_dataset():
    """⚠️ 关键区分：预测用 ``input_dir``，**不是** ``dataset.data_dir``。

    预测不吃 YOLO 清单。放混的话 TorchKiln 会去找 ``val.txt`` 并报「找不到
    清单」——与真实原因（这里根本没清单）完全无关的错误信息。
    """
    spec = build_predict_spec("c.yml", "/w/m/b.pth", "/w/source")
    assert "input_dir" in spec
    assert "dataset" not in spec


def test_predict_spec_omits_resources_when_absent():
    assert "resources" not in build_predict_spec("c.yml", "/w/m/b.pth", "/w/source")


def test_predict_spec_omits_params_when_absent():
    assert build_predict_spec("c.yml", "/w/m/b.pth", "/w/source")["params"] == {}


def test_predict_spec_paths_are_posix():
    """路径不能带反斜杠——平台在 Windows 上而容器是 Linux。"""
    from app.plugin.module_train import tk_job_container as tkjc

    spec = build_predict_spec(
        "c.yml",
        tkjc.container_path("model", "best.pth"),
        tkjc.container_path("source"),
    )
    blob = f"{spec['weights_path']} {spec['input_dir']}"
    assert "\\" not in blob, f"路径里有反斜杠: {blob}"


# ---------------------------------------------------------------------------
# 6. 指标契约读取
# ---------------------------------------------------------------------------


class _FakePredictClient:
    """只实现 ``metrics()``——``_read_metrics`` 只需要这一个方法。"""

    def __init__(self, events):
        self._events = events
        self.kwargs = None

    async def metrics(self, job_id, offset=-1, limit=5000, kind="train"):
        self.kwargs = {"offset": offset, "limit": limit, "kind": kind}
        return list(self._events)


def _read(events):
    import asyncio

    from app.plugin.module_train.predict_executor import PredictExecutor

    c = _FakePredictClient(events)
    return asyncio.run(PredictExecutor._read_metrics(c, "job_x")), c


def test_read_metrics_picks_counters():
    got, _c = _read([
        {"type": "predict", "seq": 0, "images_total": 19, "images_done": 19,
         "elapsed_sec": 44.976, "output_dir": "/workspace/jobs/job_1/predict_results"},
        {"type": "end", "seq": 1, "exit_reason": "finished"},
    ])
    assert got["images_total"] == 19
    assert got["images_done"] == 19
    assert got["elapsed_sec"] == 44.976
    assert got["output_dir"].endswith("predict_results")


def test_read_metrics_has_no_accuracy_metrics():
    """⚠️ 预测**没有** ground truth，契约里不该出现精度指标。

    哪天这里出现 mAP，说明有人往契约里塞了编造的数据——因为页面上看起来
    「预测效果 0.87」会让人以为模型真的有那么准。
    """
    got, _c = _read([
        {"type": "predict", "seq": 0, "images_total": 3, "images_done": 3},
    ])
    for k in got:
        assert "mAP" not in k and "map" not in k.lower()
        assert k in ("images_total", "images_done", "elapsed_sec", "output_dir")


def test_read_metrics_ignores_end_event():
    got, _c = _read([
        {"type": "predict", "seq": 0, "images_done": 5},
        {"type": "end", "seq": 1, "exit_reason": "finished", "elapsed_sec": 1.0},
    ])
    assert got == {"images_done": 5}


def test_read_metrics_none_when_no_predict_event():
    """没有 predict 事件 → None。上层据此不上传任何结果。"""
    assert _read([{"type": "end", "seq": 0, "exit_reason": "finished"}])[0] is None


def test_read_metrics_none_on_empty():
    assert _read([])[0] is None


def test_read_metrics_uses_predict_namespace():
    """必须带 ``kind="predict"``——job_id 全局唯一，查错命名空间不会 404，
    只会安静地拿到另一个作业的信息。"""
    _got, c = _read([])
    assert c.kwargs["kind"] == "predict"


def test_read_metrics_skips_none_values():
    got, _c = _read([
        {"type": "predict", "seq": 0, "images_total": None, "images_done": 7},
    ])
    assert "images_total" not in got
    assert got["images_done"] == 7
