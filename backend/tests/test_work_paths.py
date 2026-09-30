"""训练链路工作目录（``paths.work_dir``）的解析规则。

这些目录是**跨进程契约**：TorchKiln 训练服务、以及 paddlex / ultralytics 的训练
容器，都要读写或挂载同一批路径（数据目录当 ``/data``、``train.log`` 之类）。
两侧算出的路径必须逐字相同，否则是静默失败——容器报 FileNotFoundError 而本项目
只看到「训练失败」，或者训练在跑但页面永远没有新日志。

所以这里钉住两条：显式配置时按配置算；**配置为空/空白时必须退回系统临时目录**。
后者尤其重要：若空串被当成有效路径，``os.path.join("", "train_output", "123")``
会退化成相对路径 ``train_output/123``，产物直接落进进程 CWD，还顺手覆盖了
历史几次"临时目录清空"事故的根因。
"""
import os
import tempfile

from app.config.setting import settings
from app.plugin.module_train.paths import shared_root, work_dir


def _with_root(monkeypatch, value):
    monkeypatch.setattr(settings, "TORKILN_SHARED_DATA_ROOT", value, raising=False)


def test_defaults_to_system_tempdir(monkeypatch):
    """未配置时与历史行为完全一致（系统临时目录）。"""
    _with_root(monkeypatch, "")
    assert shared_root() == tempfile.gettempdir()
    assert work_dir("train_output", 123) == os.path.join(
        tempfile.gettempdir(), "train_output", "123")


def test_blank_and_none_fall_back(monkeypatch):
    """空串 / None / 纯空白都必须退回，不能当有效路径用。

    少了这条，配置里留个空值就会让所有产物改写到进程 CWD 下的相对路径——
    不报错、训练照跑，但日志与数据散落在意外的地方，清理也扫不到。
    """
    for blank in ("", "   ", "\t", None):
        _with_root(monkeypatch, blank)
        assert shared_root() == tempfile.gettempdir(), f"{blank!r} 应退回临时目录"
        assert work_dir("eval_output", 7) == os.path.join(
            tempfile.gettempdir(), "eval_output", "7")


def test_configured_root_is_used_verbatim(monkeypatch):
    """配置了共享根就按它算（跨机 / 后端容器化时的前提）。"""
    _with_root(monkeypatch, "/mnt/shared")
    assert shared_root() == "/mnt/shared"
    assert work_dir("train_output", 123) == os.path.join(
        "/mnt/shared", "train_output", "123")


def test_work_dir_joins_nested_parts(monkeypatch):
    """多个片段按顺序拼接（日志路径就是 ``kind/id/name.log`` 三段）。"""
    _with_root(monkeypatch, "/mnt/shared")
    assert work_dir("train_output", 42, "train.log") == os.path.join(
        "/mnt/shared", "train_output", "42", "train.log")


def test_work_dir_accepts_int_id(monkeypatch):
    """id 传 int 也要能拼（调用点直接传 task_id，不是 str(task_id)）。"""
    _with_root(monkeypatch, "/mnt/shared")
    assert work_dir("deploy_output", 5) == os.path.join(
        "/mnt/shared", "deploy_output", "5")
