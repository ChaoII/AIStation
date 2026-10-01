"""框架标识归一化：把枚举成员 / 字符串统一成裸小写值（如 "paddlex"）。"""

from __future__ import annotations

#: ``framework`` 被填成整个镜像名/标签时，镜像名对应的**框架值**。
#:
#: 历史脏数据里出现过这种情况（多半是某处把 ``docker_image`` 误赋给了 framework）：
#: ``ultralytics/ultralytics:latest``、``paddlex/paddlex:cpu``。不做归一的话
#: ``ensure_active`` 认不出来会**放行**，退场框架就能绕过守卫——这正是守卫要拦的事。
#:
#: 键是**不含标签**的镜像名，所以比较前会先剥掉 ``:tag`` / ``@digest``；
#: 用白名单而不是「按冒号切一刀」：后者会把值里含冒号的正常标识切坏。
_IMAGE_TAG_TO_FRAMEWORK = {
    "ultralytics/ultralytics": "ultralytics",
    "paddlex/paddlex": "paddlex",
    "pytorch/paddle": "paddlex",
}


def framework_value(framework: object | None) -> str:
    """返回框架的规范化字符串值。

    需要同时接受三种形态，因为它们在项目里**同时存在**：

    - 枚举成员 ``TrainFramework.PADDLEX`` -> ``"paddlex"``（取 ``.value``）
    - 枚举**成员名**字符串 ``"PADDLEX"`` -> ``"paddlex"``
      ⚠️ PG 的 ``SAEnum(TrainFramework)`` 存的是**成员名**（大写），从库里读回来
      就是这种裸字符串，**不是**枚举成员。直接 ``== TrainFramework.PADDLEX`` 比较
      恒为 False，会静默走错分支——本项目踩过这个坑，故这里统一做成员名还原。
    - 形如 ``"TrainFramework.PADDLEX"`` 的限定名 -> ``"paddlex"``
    - ``"ultralytics/ultralytics:latest"`` 这类**镜像标签** -> ``"ultralytics"``
      （历史脏数据里出现过这种写法，见下方 ``_IMAGE_TAG_TO_FRAMEWORK``）
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
    # 3) 镜像名/标签归一：先剥掉 ":tag"/"@digest"，再查白名单。
    #    无标签的也要查——"paddlex/paddlex" 这种写法在脏数据里出现过。
    bare = text.split("@", 1)[0].split(":", 1)[0]
    if bare in _IMAGE_TAG_TO_FRAMEWORK:
        return _IMAGE_TAG_TO_FRAMEWORK[bare]
    # 4) 裸成员名（"PADDLEX" / "TORKILN"）按 TrainFramework 还原
    if text and not hasattr(framework, "value"):
        try:
            from .model import TrainFramework

            member = TrainFramework[text.upper()]
            return str(member.value)
        except (KeyError, ImportError, AttributeError):
            pass
    return text
