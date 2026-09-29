"""框架标识归一化：把枚举成员 / 字符串统一成裸小写值（如 "paddlex"）。"""

from __future__ import annotations


def framework_value(framework: object | None) -> str:
    """返回框架的规范化字符串值。

    需要同时接受三种形态，因为它们在项目里**同时存在**：

    - 枚举成员 ``TrainFramework.PADDLEX`` -> ``"paddlex"``（取 ``.value``）
    - 枚举**成员名**字符串 ``"PADDLEX"`` -> ``"paddlex"``
      ⚠️ PG 的 ``SAEnum(TrainFramework)`` 存的是**成员名**（大写），从库里读回来
      就是这种裸字符串，**不是**枚举成员。直接 ``== TrainFramework.PADDLEX`` 比较
      恒为 False，会静默走错分支——本项目踩过这个坑，故这里统一做成员名还原。
    - 形如 ``"TrainFramework.PADDLEX"`` 的限定名 -> ``"paddlex"``
    - ``None`` 返回空串
    """
    if framework is None:
        return ""
    # 1) 枚举成员：取 .value
    value = getattr(framework, "value", framework)
    text = str(value)
    # 2) 限定名去前缀
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.lower()
    # 3) 裸成员名（"PADDLEX" / "ULTRALYTICS" / "TORKILN"）按 TrainFramework 还原
    if text and not hasattr(framework, "value"):
        try:
            from .model import TrainFramework

            member = TrainFramework[text.upper()]
            return str(member.value)
        except (KeyError, ImportError, AttributeError):
            pass
    return text
