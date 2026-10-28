"""开放面能力 handler —— 共享辅助（纯逻辑，无 DB / HTTP）。

提供开放面 handler 共用的入参校验与「无平台用户」身份，避免各品类重复实现。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.core.exceptions import CustomException

#: 开放面调用既有 service 时的「无平台用户」身份（资源归属由 source_app_id / app_id 表达）。
OPEN_AUTH = SimpleNamespace(user=None)


def need_int(payload: dict, key: str) -> int:
    """取必填整数字段，缺失/非数字抛 400。"""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CustomException(msg=f"参数不合法：{key} 必须为整数", code=10400, status_code=400)
    return value


def optional_int(payload: dict, key: str) -> int | None:
    """取可空整数字段；``None``/缺省返回 ``None``。"""
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CustomException(msg=f"参数不合法：{key} 必须为整数", code=10400, status_code=400)
    return value


def need_str(payload: dict, key: str, *, max_len: int = 4000, allow_empty: bool = False) -> str:
    """取必填字符串字段（去空白、限长），非法抛 400。"""
    value = payload.get(key)
    if not isinstance(value, str):
        raise CustomException(msg=f"参数不合法：{key} 必须为字符串", code=10400, status_code=400)
    value = value.strip()
    if not allow_empty and not value:
        raise CustomException(msg=f"参数不合法：{key} 必须为非空字符串", code=10400, status_code=400)
    return value[:max_len]


def optional_str(payload: dict, key: str, *, max_len: int = 4000) -> str | None:
    """取可空字符串字段；``None``/缺省返回 ``None``（不去重语义）。"""
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CustomException(msg=f"参数不合法：{key} 必须为字符串", code=10400, status_code=400)
    return value.strip()[:max_len]


def need_ids(payload: dict, key: str = "ids") -> list[int]:
    """取必填整数 id 列表；缺失/非数组抛 400。"""
    value = payload.get(key)
    if not isinstance(value, list):
        raise CustomException(msg=f"参数不合法：{key} 必须为整数数组", code=10400, status_code=400)
    ids: list[int] = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, int):
            raise CustomException(msg=f"参数不合法：{key} 必须为整数数组", code=10400, status_code=400)
        ids.append(v)
    if not ids:
        raise CustomException(msg=f"参数不合法：{key} 不能为空", code=10400, status_code=400)
    return ids


def require_confirm(payload: dict, action: str = "该操作") -> None:
    """删除类操作必须显式 ``confirm=true``，避免第三方一次笔误删掉线上资源。"""
    if payload.get("confirm") is not True:
        raise CustomException(
            msg=f"{action}不可恢复：请在 payload 中传 confirm=true 明确确认", code=10400, status_code=400
        )


def bad_request(exc: Any) -> CustomException:
    """把 Pydantic 校验错误转成 400（只回第一处错误，避免泄露整份 schema）。"""
    first = exc.errors()[0] if getattr(exc, "errors", None) and exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", ()))
    msg = first.get("msg", "")
    return CustomException(
        msg=f"参数不合法：{loc} {msg}".strip(), code=10400, status_code=400
    )


def not_found(name: str = "资源") -> CustomException:
    """统一的 404（与「资源不存在」同响应，避免枚举）。"""
    return CustomException(msg=f"{name}不存在", code=10404, status_code=404)
