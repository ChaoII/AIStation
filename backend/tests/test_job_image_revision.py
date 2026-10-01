"""job 镜像守卫的「期望修订号自动推导」测试。

为什么自动推导而不是硬编码
--------------------------
硬编码意味着**每次 TorchKiln 提交后都要改配置或重建镜像**，而漏改的后果与
「忘了重建镜像」完全一样：守卫天天误报 -> 大家习惯性忽略 -> 等于没有守卫。

自动读本地 TorchKiln 仓库的 HEAD 没有这个维护负担，所以它是默认路径；
``TORKILN_EXPECTED_REVISION`` 只是给「部署机上没有 TorchKiln 源码」的场景
准备的显式出口。
"""
import subprocess

import pytest

from app.config.setting import settings
from app.plugin.module_train import tk_job_container as tkjc


@pytest.fixture(autouse=True)
def _restore_settings():
    """每个用例都恢复设置——改全局 settings 会漏到别的测试。"""
    rev, path = settings.TORKILN_EXPECTED_REVISION, settings.TORKILN_REPO_PATH
    yield
    settings.TORKILN_EXPECTED_REVISION, settings.TORKILN_REPO_PATH = rev, path


# ---------------------------------------------------------------------------
# local_torchkiln_revision
# ---------------------------------------------------------------------------


def test_returns_none_when_path_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", "")
    assert tkjc.local_torchkiln_revision() is None


def test_returns_none_when_path_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path / "nope"))
    assert tkjc.local_torchkiln_revision() is None


def test_returns_none_when_not_a_git_repo(monkeypatch, tmp_path):
    """非 git 目录：git 会非零退出 -> None（跳过版本检查，而不是判过期）。"""
    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path))
    assert tkjc.local_torchkiln_revision() is None


def test_reads_real_git_head(monkeypatch, tmp_path):
    """起一个真 git 仓库，验证读出来的就是 HEAD。"""
    import os

    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    run("add", ".")
    run("commit", "-qm", "first")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          cwd=tmp_path, capture_output=True,
                          text=True).stdout.strip()

    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path))
    assert tkjc.local_torchkiln_revision() == head
    assert len(head) >= 6
    assert os.path.isdir(tmp_path)


def test_returns_none_when_git_missing(monkeypatch, tmp_path):
    """git 不可用 -> None，而不是抛异常。

    守卫跑在作业启动的关键路径上，抛异常会把「无法检查版本」变成「作业失败」。
    """
    def boom(*a, **kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path))
    assert tkjc.local_torchkiln_revision() is None


def test_returns_none_on_timeout(monkeypatch, tmp_path):
    def timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="git", timeout=10)

    monkeypatch.setattr(subprocess, "run", timeout)
    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path))
    assert tkjc.local_torchkiln_revision() is None


def test_returns_none_on_empty_stdout(monkeypatch, tmp_path):
    class _R:
        returncode = 0
        stdout = "   \n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path))
    assert tkjc.local_torchkiln_revision() is None


def test_dirty_worktree_does_not_block(monkeypatch, tmp_path):
    """有未提交改动时**照样**返回 HEAD。

    本地开发构建带改动是常态。若因此判过期，检查会天天误报——那等于没有检查。
    """
    import os

    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    run("add", ".")
    run("commit", "-qm", "first")
    (tmp_path / "a.txt").write_text("dirty", encoding="utf-8")   # 未提交

    monkeypatch.setattr(settings, "TORKILN_REPO_PATH", str(tmp_path))
    assert tkjc.local_torchkiln_revision() is not None
    assert os.path.isdir(tmp_path)


# ---------------------------------------------------------------------------
# expected_revision 的优先级
# ---------------------------------------------------------------------------


def test_explicit_config_wins(monkeypatch):
    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "pinned123")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: "autoread")
    assert tkjc.expected_revision() == "pinned123"


def test_falls_back_to_auto_read(monkeypatch):
    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: "autoread")
    assert tkjc.expected_revision() == "autoread"


def test_blank_config_treated_as_unset(monkeypatch):
    """空白字符串算「没配」，不能当成期望一个空修订号。"""
    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "   ")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: "autoread")
    assert tkjc.expected_revision() == "autoread"


def test_none_when_nothing_available(monkeypatch):
    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: None)
    assert tkjc.expected_revision() is None


# ---------------------------------------------------------------------------
# 与守卫的衔接
# ---------------------------------------------------------------------------


def test_guard_uses_auto_revision_by_default(monkeypatch):
    """不传 expect_revision 时走自动推导，并据此判过期。"""
    import asyncio

    class _C:
        async def healthz(self):
            return {"job_kinds": ["train", "eval", "predict"],
                    "code_revision": "old111"}

    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: "new222")

    with pytest.raises(tkjc.StaleJobImage) as ei:
        asyncio.run(tkjc.assert_image_current(_C(), need_kinds=("eval",)))
    assert "old111" in str(ei.value) and "new222" in str(ei.value)


def test_guard_skips_version_when_auto_unavailable(monkeypatch):
    """自动读不到时**跳过**版本检查，而不是误判过期。

    「天天误报的守卫等于没有守卫」——能力检查仍然拦得住「忘了重建」。
    """
    import asyncio

    class _C:
        async def healthz(self):
            return {"job_kinds": ["train", "eval"], "code_revision": "whatever"}

    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: None)

    info = asyncio.run(tkjc.assert_image_current(_C(), need_kinds=("eval",)))
    assert info["code_revision"] == "whatever"


def test_guard_still_blocks_by_capability_without_revision(monkeypatch):
    """即使完全没法查版本，能力检查仍必须拦得住。"""
    import asyncio

    class _C:
        async def healthz(self):
            return {"ok": True}

    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: None)

    with pytest.raises(tkjc.StaleJobImage):
        asyncio.run(tkjc.assert_image_current(_C(), need_kinds=("predict",)))


def test_explicit_arg_overrides_auto(monkeypatch):
    """显式传入的 ``expect_revision`` 优先于配置与磁盘。

    构造：镜像自报 ``from_arg``，而配置说 ``from_config``、磁盘说 ``from_disk``。
    显式传 ``from_arg`` 时必须**放行**——若实现里忽略了这个参数、
    偷偷回落到 ``expected_revision()``，这条就会失败。
    """
    import asyncio

    class _C:
        async def healthz(self):
            return {"job_kinds": ["train", "eval"], "code_revision": "from_arg"}

    monkeypatch.setattr(settings, "TORKILN_EXPECTED_REVISION", "from_config")
    monkeypatch.setattr(tkjc, "local_torchkiln_revision", lambda: "from_disk")

    info = asyncio.run(tkjc.assert_image_current(
        _C(), need_kinds=("eval",), expect_revision="from_arg"))
    assert info["code_revision"] == "from_arg"

    # 同一场景不传显式参数时，应当按配置（from_config）判为不符
    with pytest.raises(tkjc.StaleJobImage) as ei:
        asyncio.run(tkjc.assert_image_current(_C(), need_kinds=("eval",)))
    assert "from_config" in str(ei.value)


# ---------------------------------------------------------------------------
# 三条链路都不再硬传配置值
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fname", [
    "torchkiln_executor.py", "eval_scheduler.py", "predict_executor.py",
])
def test_executors_pass_none_not_config_value(fname):
    """三条链路都应传 ``expect_revision=None``（走自动推导）。

    硬传 ``settings.TORKILN_EXPECTED_REVISION or None`` 会让「自动推导」这条
    默认路径永远不生效——配置为空时它退化成 None，恰好也走得通，但一旦有人
    只改了配置不重建镜像，行为就和文档说的不一致了。
    """
    import pathlib

    src = (pathlib.Path(tkjc.__file__).parent / fname).read_text(encoding="utf-8")
    assert "expect_revision=None" in src, f"{fname} 应传 expect_revision=None"
    assert "TORKILN_EXPECTED_REVISION" not in src, (
        f"{fname} 不该直接读 TORKILN_EXPECTED_REVISION——那是 expected_revision() 的职责")
