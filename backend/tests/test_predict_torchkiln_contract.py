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

这里把契约钉住，防止再漂回去。真实链路验证靠 ``%TEMP%\\e2e_jobrunner.py``。
"""

import os
from types import SimpleNamespace

import pytest

from app.plugin.module_train import predict_executor as pe
from app.plugin.module_train.predict_executor import (
    build_predict_cmd,
    collect_result_images,
    resolve_predict_tk_config,
)

# ---------------------------------------------------------------------------
# 1. 命令形状：argparse 风格，不是 -o Global.xxx=
# ---------------------------------------------------------------------------


def test_predict_cmd_uses_argparse_form():
    """``tkiln predict`` 吃 ``--weights``/``--input``/``--output``，不是 ``-o``。"""
    cmd = build_predict_cmd("torchkiln", "best_accuracy.pth",
                            {"tk_config": "configs/yolo/yolo11-seg.yml"})

    assert cmd[:2] == ["tkiln", "predict"]
    for flag, value in (("--weights", "/model/best_accuracy.pth"),
                        ("--input", "/data"),
                        ("--output", "/output")):
        assert flag in cmd, f"缺少 {flag}"
        assert cmd[cmd.index(flag) + 1] == value


def test_predict_cmd_does_not_use_val_style_overrides():
    """不能出现 ``Global.pretrained_model=`` ——那是 ``tkiln val`` 的写法。

    这是修 bug #1 的核心断言：之前正是拼了这两个键，容器里 argparse 直接拒绝。
    """
    cmd = build_predict_cmd("torchkiln", "w.pth", {"tk_config": "c.yml"})
    joined = " ".join(cmd)

    assert "Global.pretrained_model" not in joined
    assert "Global.infer_dir" not in joined
    assert "Global.save_model_dir" not in joined


def test_predict_cmd_output_is_directory_not_file():
    """``/data`` 挂的是整个数据集目录，所以 ``--output`` 必须是**目录**。

    TorchKiln 侧按输入相对路径写结果图；写成文件路径会让它把 ``/output`` 当普通
    文件，目录挂载点上直接失败。
    """
    cmd = build_predict_cmd("torchkiln", "w.pth", {"tk_config": "c.yml"})
    out = cmd[cmd.index("--output") + 1]
    assert out == "/output"
    assert not out.lower().endswith((".jpg", ".jpeg", ".png"))


def test_predict_cmd_passes_config_name():
    """``-c`` 是 TorchKiln 的配置名（configs/... 的 model_name），由训练任务带下来。"""
    cmd = build_predict_cmd("torchkiln", "w.pth",
                            {"tk_config": "configs/yolo/yolo11-seg.yml"})
    assert cmd[cmd.index("-c") + 1] == "configs/yolo/yolo11-seg.yml"


def test_predict_cmd_device_maps_cpu():
    """``--device`` 用 TorchKiln 的写法；cpu 要如实传，不能被折成 cuda:0。"""
    cmd = build_predict_cmd("torchkiln", "w.pth",
                            {"tk_config": "c.yml", "device": "cpu"})
    assert cmd[cmd.index("--device") + 1] == "cpu"

    cmd = build_predict_cmd("torchkiln", "w.pth",
                            {"tk_config": "c.yml", "device": "0"})
    assert cmd[cmd.index("--device") + 1] == "cuda:0"


def test_predict_cmd_conf_iou_via_opt():
    """conf / iou 是后处理阈值，走 tkiln 的 ``-o`` 覆盖机制。"""
    cmd = build_predict_cmd("torchkiln", "w.pth",
                            {"tk_config": "c.yml", "conf": 0.4, "iou": 0.6})
    joined = " ".join(cmd)
    assert "Global.conf=0.4" in joined
    assert "Global.iou=0.6" in joined


def test_predict_cmd_rejects_retired_framework():
    """已退场框架必须在这里就报错，而不是拉错镜像。"""
    with pytest.raises(ValueError):
        build_predict_cmd("ultralytics", "best.pt", {"tk_config": "c.yml"})


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
