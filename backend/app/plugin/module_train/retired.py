"""已退场训练框架的统一守卫。

Ultralytics / PaddleX 的执行通路已整体移除，但库里仍留着它们的历史数据
（92 个模型、37 个训练任务，以及少量评估/预测记录）。这些行必须**读得出**，
所以 ``TrainFramework`` 的枚举成员与 PG 枚举值都保留着；但任何要**执行**
它们的入口都必须在这里被挡住。

为什么值得单独一个模块：评估、预测、部署、导出四条链路都要挡一次，而提示
文案必须一致——用户点"评估"看到"框架已退场"，点"部署"也该看到同一句话，
而不是四种措辞、或者某一处漏了导致跑了半天报个奇怪的错。
"""

from __future__ import annotations

#: 已退场、但历史数据仍需保留可读性的框架（裸小写值，与 framework_value 对齐）
RETIRED_FRAMEWORKS = ("ultralytics", "paddlex")

#: 唯一在用的框架
ACTIVE_FRAMEWORK = "torchkiln"


def is_retired(framework: object | None) -> bool:
    """该框架的执行通路是否已退场。"""
    from .framework_utils import framework_value

    return framework_value(framework) in RETIRED_FRAMEWORKS


def retired_message(framework: object | None, action: str = "执行") -> str:
    """给用户看的退场提示（``action`` 如「评估」「部署」）。

    必须说清四件事，缺一条用户就会误判：

    1. **框架已退场**——不说的话用户以为是配置错了或系统有 bug；
    2. **是哪个框架**——历史数据里这行不带框架名，用户对不上是哪批；
    3. **改用什么**——只说"不支持"等于把问题推回给用户；
    4. **历史数据怎么办**——不说的话用户会以为连模型记录、权重下载都没了，
       从而放弃那些还有价值的产物。

    ``action`` 决定主语：建训练任务/定时训练时是"任务"而非"模型"，
    所以主语统一用「训练框架」而不写死"该模型的"。
    """
    from .framework_utils import framework_value

    shown = framework_value(framework) or str(framework)
    return (
        f"训练框架 {shown} 已退场，无法{action}。"
        f"平台已统一改用自研训练平台 TorchKiln，请用 TorchKiln 重新训练后再{action}。"
        f"（历史模型与训练记录仍可查看，原始权重文件仍可正常下载。）"
    )


def ensure_active(framework: object | None, action: str = "执行") -> None:
    """框架已退场则抛异常；否则放行。"""
    if is_retired(framework):
        raise _RetiredFramework(retired_message(framework, action))


class _RetiredFramework(Exception):
    """已退场框架。单独一个类型，便于调用方精确捕获并给出 4xx 而不是 500。"""
