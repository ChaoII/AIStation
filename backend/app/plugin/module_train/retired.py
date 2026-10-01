"""已退场训练框架的统一守卫。

``ULTRALYTICS`` / ``PADDLEX`` 两个框架都已**彻底**移除，项目只剩自研的 TorchKiln：

1. 执行通路（训练、评估、预测、部署、格式转换导出）全部下线；
2. 历史数据按**显式 id 白名单**删净（不是模式匹配猜——本项目曾因用
   ``storage_path LIKE '%task_%'`` 误删 12 个真实用户模型）；
3. PG 枚举 ``trainframework`` 已 ``ALTER TYPE`` 移除那两个值；
4. Python ``TrainFramework`` 的枚举成员也已删除。

**顺序不可颠倒**：先删数据 → 再改 PG 枚举 → 最后删成员。反过来会撞上
``SAEnum`` 按**成员名**反序列化的坑——类型里还有值、代码里成员已删时，读那一列
直接报 ``invalid input value for enum``，整个模型列表页打不开。

但**仍要挡住新建入口**：请求体里的 ``framework`` 是字符串，客户端能传任意值，
枚举本身拦不住。``RETIRED_FRAMEWORKS`` 因此仍列着这两个名字——它们在这里只是
"拒绝名单"，不是可用的框架。

为什么值得单独一个模块：评估、预测、部署、导出四条链路都要挡一次，而提示文案必须
一致——用户点「评估」看到「框架已退场」，点「部署」也该看到同一句话，而不是四种
措辞、或者某一处漏了导致跑了半天报个奇怪的错。
"""

from __future__ import annotations

#: 已退场的框架（裸小写值，与 framework_value 对齐）。
#: 注意 "ultralytics" 在这里**只是拒绝名单**，不是布局标识符——
#: 目录布局那个同名字符串由 ``exporters.common.YOLO_LAYOUT`` 持有，两者无关。
RETIRED_FRAMEWORKS = ("ultralytics", "paddlex")

#: 唯一在用的框架
ACTIVE_FRAMEWORK = "torchkiln"


def is_retired(framework: object | None) -> bool:
    """该框架的执行通路是否已退场。"""
    from .framework_utils import framework_value

    return framework_value(framework) in RETIRED_FRAMEWORKS


def retired_message(framework: object | None, action: str = "执行") -> str:
    """给用户看的退场提示（``action`` 如「评估」「部署」）。

    必须说清三件事，缺一条用户就会误判：

    1. **框架已退场**——不说的话用户以为是配置错了或系统有 bug；
    2. **改用什么**——只说"不支持"等于把问题推回给用户；
    3. **历史数据已经不在了**——这条最要紧。之前这里写的是「历史模型仍可查看、
       权重仍可下载」，在历史数据删净之后就成了**假承诺**：用户会去列表里翻，翻不到
       然后以为系统坏了。宁可说得更狠，也不要留个做不到的指望。

    ``action`` 决定主语：建训练任务/定时训练时是"任务"而非"模型"，
    所以主语统一用「训练框架」而不写死"该模型的"。
    """
    from .framework_utils import framework_value

    shown = framework_value(framework) or str(framework)
    return (
        f"训练框架 {shown} 已退场，无法{action}。"
        f"平台已统一改用自研训练平台 TorchKiln，请用 TorchKiln 重新训练后再{action}。"
        f"（该框架的历史模型与训练记录已随退场一并清理，如需旧权重请从备份中找回。）"
    )


def ensure_active(framework: object | None, action: str = "执行") -> None:
    """框架已退场则抛异常；否则放行。"""
    if is_retired(framework):
        raise _RetiredFramework(retired_message(framework, action))


class _RetiredFramework(Exception):
    """已退场框架。单独一个类型，便于调用方精确捕获并给出 4xx 而不是 500。"""
