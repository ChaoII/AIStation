"""job 镜像过期检查（``tk_job_container.assert_image_current``）的行为测试。

为什么需要这个检查
------------------
2026-10 连续两次踩到「改了 TorchKiln 代码但忘了重建 job 镜像」：

1. 加了 ``/api/v1/eval/jobs`` 端点后没重建 → 评估提交作业直接 **404 Not Found**，
   看起来像「服务有问题」；
2. 给 ``MetricSink`` 加 ``predict()`` 后没重建 → 实跑报
   **``AttributeError: 'MetricSink' object has no attribute 'predict'``**，
   而此时 19 张结果图**已经写完**了——产物齐了、状态却是失败。

两种报错都指向离真实原因很远的地方。所以让服务在 ``/healthz`` 自报代码身份与
``job_kinds``，平台在**提交作业之前**用一次 GET 拦住它。
"""

import asyncio

import pytest

from app.plugin.module_train import tk_job_container as tkjc
from app.plugin.module_train.tk_job_container import StaleJobImage


class _FakeClient:
    """只实现 ``healthz()``——``assert_image_current`` 只需要这一个方法。"""

    def __init__(self, payload):
        self._payload = payload

    async def healthz(self):
        return dict(self._payload)


def _run(payload, **kw):
    return asyncio.run(tkjc.assert_image_current(_FakeClient(payload), **kw))


# ---------------------------------------------------------------------------
# 能力检查（最要紧的一条：不依赖任何配置）
# ---------------------------------------------------------------------------


def test_missing_kind_is_rejected():
    """镜像不支持本次要用的种类 → 抛 StaleJobImage，并说清怎么修。"""
    with pytest.raises(StaleJobImage) as ei:
        _run({"job_kinds": ["train"]}, need_kinds=("eval",))
    msg = str(ei.value)
    assert "eval" in msg
    # 必须给出可执行的动作，而不只是「不支持」
    assert "build-image.ps1" in msg


def test_missing_multiple_kinds_listed_sorted():
    with pytest.raises(StaleJobImage) as ei:
        _run({"job_kinds": ["train"]}, need_kinds=("predict", "eval"))
    msg = str(ei.value)
    assert "eval" in msg and "predict" in msg
    # 列表要排序，否则同样的情况每次报错顺序不同，没法 grep
    assert msg.index("eval") < msg.index("predict")


def test_old_image_missing_predict_is_rejected():
    """这正是踩过的那次：镜像里有 eval 端点、没有 predict 端点。"""
    with pytest.raises(StaleJobImage) as ei:
        _run({"job_kinds": ["train", "eval"]}, need_kinds=("predict",))
    assert "predict" in str(ei.value)


def test_all_kinds_present_passes():
    info = _run({"job_kinds": ["train", "eval", "predict"],
                 "code_revision": "abc1234"},
                need_kinds=("eval",))
    assert info["code_revision"] == "abc1234"


def test_extra_kinds_are_fine():
    """镜像支持的种类比需要的多，不该报错（向前兼容）。"""
    _run({"job_kinds": ["train", "eval", "predict", "export"]},
         need_kinds=("eval",))


def test_absent_job_kinds_is_rejected():
    """老镜像的 ``/healthz`` 没有 ``job_kinds`` 字段 → 不能当成「支持一切」。

    放行的后果就是退回现状：提交后收404。这条守卫的价值正在于此。
    """
    with pytest.raises(StaleJobImage):
        _run({"ok": True}, need_kinds=("eval",))


# ---------------------------------------------------------------------------
# 版本检查（可选，取决于 TORKILN_EXPECTED_REVISION）
# ---------------------------------------------------------------------------


def test_revision_mismatch_is_rejected():
    with pytest.raises(StaleJobImage) as ei:
        _run({"job_kinds": ["train", "eval"], "code_revision": "old9999"},
             need_kinds=("eval",), expect_revision="new1234")
    msg = str(ei.value)
    assert "old9999" in msg and "new1234" in msg


def test_revision_match_passes():
    _run({"job_kinds": ["train", "eval"], "code_revision": "abc1234"},
         need_kinds=("eval",), expect_revision="abc1234")


def test_unknown_revision_skips_version_check():
    """镜像自报 ``unknown``（不是用 build-image.ps1 构建的）→ 不据此判过期。

    只按能力判。否则所有非本脚本构建的镜像都会一律被判过期，检查就成了噪音，
    大家只会习惯性忽略它——那等于没有检查。
    """
    _run({"job_kinds": ["train", "eval"], "code_revision": "unknown"},
         need_kinds=("eval",), expect_revision="abc1234")


def test_no_expect_revision_skips_version_check():
    _run({"job_kinds": ["train"], "code_revision": "whatever"},
         need_kinds=("train",))


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------


def test_stale_image_is_a_runtime_error():
    """必须是 RuntimeError —— 上层的 ``except Exception`` 才接得住，
    而它**不该**被当成 TorchKilnError（那类错误会被翻译成「服务不可达」，
    导致重试而不是立刻报出「镜像过期」）。"""
    assert issubclass(StaleJobImage, RuntimeError)


def test_error_message_names_the_problem():
    """文案必须出现「镜像」两个字——用户扫日志时找的就是这个词。"""
    with pytest.raises(StaleJobImage) as ei:
        _run({"job_kinds": ["train"]}, need_kinds=("eval",))
    assert "镜像" in str(ei.value)


# ---------------------------------------------------------------------------
# 三条链路都接上了检查
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fname,kind", [
    ("torchkiln_executor.py", "train"),
    ("eval_scheduler.py", "eval"),
    ("predict_executor.py", "predict"),
])
def test_all_three_executors_call_the_guard(fname, kind):
    """三条链路都必须在提交作业前调 ``assert_image_current``。

    只加两条很容易——而漏掉的那条恰好就是没踩过坑、看起来没问题的那条。
    """
    import pathlib

    src = pathlib.Path(tkjc.__file__).parent / fname
    text = src.read_text(encoding="utf-8")
    assert "assert_image_current(" in text, f"{fname} 没接镜像检查"
    assert f'need_kinds=("{kind}",)' in text, f"{fname} 的 need_kinds 不是 {kind}"


@pytest.mark.parametrize("fname", [
    "torchkiln_executor.py", "eval_scheduler.py", "predict_executor.py",
])
def test_guard_runs_before_job_submission(fname):
    """检查必须在 ``submit_*_job`` **之前**。

    放在提交之后就没有意义了：症状（404/AttributeError）已经发生，而且
    ``predict`` 那种还会在结果图写完之后才炸。
    """
    import pathlib

    text = (pathlib.Path(tkjc.__file__).parent / fname).read_text(encoding="utf-8")
    i_guard = text.index("assert_image_current(")
    submits = [text.index(m) for m in
               ("submit_job(", "submit_eval_job(", "submit_predict_job(",
                "_ensure_job(", "_submit(") if m in text]
    assert submits, f"{fname} 里找不到提交调用"
    assert i_guard < min(submits), (
        f"{fname}: 镜像检查在提交之后才跑——那时症状已经发生了")


@pytest.mark.parametrize("fname", [
    "torchkiln_executor.py", "eval_scheduler.py", "predict_executor.py",
])
def test_guard_is_inside_client_context(fname):
    """检查必须落在 ``async with TorchKilnClient(...)`` **块内**。

    插在块外会引用到尚未绑定的 ``client``（ruff 的 F821 能抓到，但那是静态的；
    这里守住结构本身，免得下次重构又把位置挪错）。
    """
    import pathlib

    text = (pathlib.Path(tkjc.__file__).parent / fname).read_text(encoding="utf-8")
    i_with = text.index("async with TorchKilnClient(")
    i_guard = text.index("assert_image_current(")
    assert i_guard > i_with, f"{fname}: 检查在 async with 之前——client 还不存在"


# ---------------------------------------------------------------------------
# TorchKiln 服务侧的自报内容
# ---------------------------------------------------------------------------


def test_healthz_reports_code_identity_and_kinds():
    """服务必须自报这两项——否则平台侧的检查无从判断。"""
    import inspect
    import pathlib
    import sys

    root = pathlib.Path(r"D:\TorchKiln")
    if not (root / "service").is_dir():
        pytest.skip("找不到 TorchKiln 仓库（本仓库的测试不必依赖它）")
    sys.path.insert(0, str(root))
    from service.main import create_app

    src = inspect.getsource(create_app)
    assert "code_revision" in src
    assert "job_kinds" in src
    # 必须是 healthz 而不是只挂在某个带鉴权的端点上：平台侧要在起完容器后
    # 用**一次不带鉴权的 GET** 判断（/healthz 本来就不要求 token）
    assert '"/healthz"' in src


def test_supported_job_kinds_comes_from_dispatch_table():
    """``job_kinds`` 必须从 ``_ARGV_BUILDERS`` 推导，不能读 ``JOB_KINDS`` 常量。

    前者是「这份代码真的能跑什么」，后者是「协议允许什么」。加了新种类但忘了
    重建镜像时，两者会不一致——报出去的必须是前者，否则守卫形同虚设。
    """
    import sys
    from pathlib import Path

    root = Path(r"D:\TorchKiln")
    if not (root / "service").is_dir():
        pytest.skip("找不到 TorchKiln 仓库")
    sys.path.insert(0, str(root))
    from service.runner import supported_job_kinds
    from service.schemas import JOB_KINDS

    assert set(supported_job_kinds()) == set(JOB_KINDS)
    # 关键：删掉一个构造器后，supported 就该少一个（证明它不是读常量）
    import service.runner as runner

    saved = runner._ARGV_BUILDERS.pop("predict")
    try:
        assert "predict" not in supported_job_kinds()
        assert "predict" in JOB_KINDS, "常量里仍有 predict（这正是两者会不一致的原因）"
    finally:
        runner._ARGV_BUILDERS["predict"] = saved
