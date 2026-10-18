from datetime import datetime
from typing import Any


class TimeUtil:
    """
    时间格式化工具类
    """

    DEFAULT_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    @classmethod
    def object_format_datetime(cls, obj: Any) -> Any:
        """
        格式化对象中的 datetime 属性为默认字符串格式。

        参数:
        - obj (Any): 输入对象。

        返回:
        - Any: 格式化后的对象。
        """
        for attr in dir(obj):
            if not attr.startswith("_"):  # 跳过私有属性
                value = getattr(obj, attr)
                if isinstance(value, datetime):
                    setattr(obj, attr, value.strftime(cls.DEFAULT_DATETIME_FORMAT))
        return obj

    @classmethod
    def list_format_datetime(cls, lst: list[Any]) -> list[Any]:
        """
        格式化列表内每个对象的 datetime 属性。

        参数:
        - lst (List[Any]): 对象列表。

        返回:
        - list[Any]: 格式化后的对象列表。
        """
        return [cls.object_format_datetime(obj) for obj in lst]

    @classmethod
    def format_datetime_dict_list(cls, dicts: list[dict]) -> list[dict]:
        """
        递归格式化字典列表中的 datetime 值为默认字符串格式。

        参数:
        - dicts (list[dict]): 字典列表。

        返回:
        - list[dict]: 格式化后的字典列表。
        """

        def _format_value(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: _format_value(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_format_value(item) for item in value]
            if isinstance(value, datetime):
                return value.strftime(cls.DEFAULT_DATETIME_FORMAT)
            return value

        return [_format_value(item) for item in dicts]
