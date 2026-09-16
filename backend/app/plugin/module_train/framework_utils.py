"""框架标识归一化：把枚举成员 / 字符串统一成裸小写值（如 "paddlex"）。"""


def framework_value(framework: object | None) -> str:
    """返回框架的规范化字符串值。

    - 枚举成员取其 ``value``（``TrainFramework.PADDLEX`` -> ``"paddlex"``）
    - 形如 ``"TrainFramework.PADDLEX"`` 的去前缀后小写
    - ``None`` 返回空串
    """
    if framework is None:
        return ""
    value = getattr(framework, "value", framework)
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()
