"""框架标识归一化 + 过滤条件构造。"""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table

from app.plugin.module_train.framework_utils import framework_filter, framework_value
from app.plugin.module_train.model import TrainFramework

#: 测试用的假表——``framework_filter`` 只关心列对象，不需要真表。
_md = MetaData()
_fake = Table(
    "fake_framework_table",
    _md,
    Column("id", Integer),
    Column("framework", String(16)),
)


def test_framework_value_from_enum():
    assert framework_value(TrainFramework.TORKILN) == "torchkiln"


def test_framework_value_from_plain_string():
    assert framework_value("paddlex") == "paddlex"
    # ULTRALYTICS 的枚举成员已随数据一并删除，但裸成员名字符串仍要能归一——
    # PG 的 SAEnum 按成员名反序列化，历史脏数据里就是这个形态。
    assert framework_value("ULTRALYTICS") == "ultralytics"


def test_framework_value_from_repr_like_string():
    assert framework_value("TrainFramework.TORKILN") == "torchkiln"


def test_framework_value_none_is_empty():
    assert framework_value(None) == ""


# ------------------------------------------------- 退场框架的脏写法也要能归一


@pytest.mark.parametrize(
    "raw",
    [
        "ultralytics/ultralytics:latest",
        "ultralytics/ultralytics",
        "paddlex/paddlex:cpu",
        "pytorch/paddle",
    ],
)
def test_framework_value_normalises_image_tags(raw):
    """``framework`` 被误填成整个镜像名/标签时要能还原成框架值。

    历史脏数据里出现过这种写法（多半是某处把 ``docker_image`` 赋给了 framework）。
    不归一的话 ``ensure_active`` 会**放行**，退场框架就能绕过守卫——而绕过守卫
    正是这层守卫唯一要拦的事。
    """
    value = framework_value(raw)
    assert value in ("ultralytics", "paddlex"), f"{raw} 未被归一，得到 {value!r}"


# ------------------------------------------------------------ 过滤条件构造


def test_framework_filter_returns_none_for_retired_framework():
    """退场框架值必须返回 ``None``（短路空结果），**绝不能**变成一个 SQL 条件。

    这是删掉枚举成员后才暴露的坑：把 ``'paddlex'`` 直接丢给 ``SAEnum`` 列，PG 会
    报 ``invalid input value for enum trainframework: "paddlex"``，接口层就是 500。
    退场前 ``TrainFramework('paddlex')`` 还能拿到成员，五个列表端点因此「碰巧能跑」。
    """
    assert framework_filter(_fake.c.framework, "paddlex") is None
    assert framework_filter(_fake.c.framework, "PADDLEX") is None
    assert framework_filter(_fake.c.framework, "ultralytics") is None
    assert framework_filter(_fake.c.framework, "paddlex/paddlex:cpu") is None


def test_framework_filter_returns_none_for_garbage():
    """完全瞎写的值也按空结果处理，而不是把脏值丢给数据库。"""
    assert framework_filter(_fake.c.framework, "完全不存在的框架") is None


def test_framework_filter_returns_none_for_empty():
    """空值表示"不按框架筛"，返回 None 让调用方跳过该条件。"""
    assert framework_filter(_fake.c.framework, None) is None
    assert framework_filter(_fake.c.framework, "") is None


@pytest.mark.parametrize("raw", ["torchkiln", "TORKILN", "TorchKiln"])
def test_framework_filter_accepts_current_framework(raw):
    """当前框架的各种书写形式都要能生成真正的 SQL 条件。"""
    cond = framework_filter(_fake.c.framework, raw)
    assert cond is not None, f"{raw!r} 应当被接受为过滤条件"
    assert "torchkiln" in str(cond.compile(compile_kwargs={"literal_binds": True}))


def test_framework_filter_accepts_enum_member():
    """枚举成员本身（从库里读出来就是这个形态）也要能生成条件。"""
    assert framework_filter(_fake.c.framework, TrainFramework.TORKILN) is not None
