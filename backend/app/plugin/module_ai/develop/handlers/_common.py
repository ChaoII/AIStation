"""开放面能力 handler —— 共享辅助（纯逻辑 + 开放面身份）。

提供开放面 handler 共用的入参校验与「开放平台服务账号」身份，避免各品类重复实现。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

#: 开放平台服务账号用户名（真实 sys_user 行，is_superuser=True）。
SERVICE_USERNAME = "openai_platform"

#: 开放面调用既有 service 时的「无平台用户」身份（仅用于不依赖用户身份的只读/查询）。
OPEN_AUTH = SimpleNamespace(user=None)

_service_user_id: int | None = None
_service_user_lock = asyncio.Lock()


async def _ensure_open_service_user() -> int:
    """幂等确保开放平台服务账号存在，返回其 ``sys_user.id``（供 created_id 等 FK 落库）。

    开放面写操作（create/update/delete/toggle）依赖 ``auth.user.id``，而平台多数 service
    直接写 ``auth.user.id``（``user=None`` → AttributeError）。故为开放面建一个真实
    ``sys_user`` 行作为服务账号（``is_superuser=True``：权限过滤不再拦截开放面全局可见）。
    按 ``username`` 唯一幂等，首次惰性建号并缓存 id。
    """
    global _service_user_id
    if _service_user_id:
        return _service_user_id
    async with _service_user_lock:
        if _service_user_id:
            return _service_user_id
        from app.api.v1.module_system.user.model import UserModel
        from app.utils.hash_bcrpy_util import PwdUtil

        async with async_db_session.begin() as db:
            row = await db.scalar(select(UserModel).where(UserModel.username == SERVICE_USERNAME))
            if row is None:
                user = UserModel(
                    username=SERVICE_USERNAME,
                    password=PwdUtil.set_password_hash(password="openapi-service"),
                    name="开放平台服务账号",
                    is_superuser=True,
                    status="0",
                )
                db.add(user)
                await db.flush()
                _service_user_id = user.id
            else:
                _service_user_id = row.id
        return _service_user_id


async def open_auth() -> SimpleNamespace:
    """开放面身份的 auth 对象：携带平台服务账号（超管），供依赖 ``auth.user.id`` 的 service 使用。

    用法：``await svc.create(data, await open_auth())``。只读/查询可继续用 ``OPEN_AUTH``。
    """
    uid = await _ensure_open_service_user()
    return SimpleNamespace(user=SimpleNamespace(id=uid, is_superuser=True))


async def create_auth(app_ctx: Any) -> SimpleNamespace:
    """按开放应用上下文决定「创建资源」所用的身份 auth 对象。

    - **B 应用**（``owner_user_id`` 非空）：以 **owner 用户**身份创建，``created_id``
      记为该用户，且默认 ``is_public=false``（仅自己可见，公开需申请）。
    - **平台级/A 应用**（owner 为空）：以**平台服务账号**身份创建，``created_id``
      为服务账号，默认 ``is_public=true``（平台共享）。

    Args:
        app_ctx: 开放应用上下文（含 ``owner_user_id``）。
    """
    owner = getattr(app_ctx, "owner_user_id", None)
    if owner is not None:
        return SimpleNamespace(
            user=SimpleNamespace(id=owner, is_superuser=False)
        )
    return await open_auth()


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


def ensure_resource_writable(app_ctx: Any, resource_created_id: int | None, label: str = "资源") -> None:
    """确保当前应用可对资源做写操作（更新/删除），否则按只读拒绝。

    写权限规则：
    - **平台级/A 应用**（``owner_user_id`` 为空）：可写（平台维护）。
    - **B 应用**（owner 非空）：仅当 ``resource_created_id == owner_user_id`` 时可写；
      其它（平台共享 / 主动公开 / 他人私有公开资源）一律**只读**，拒绝修改。

    Args:
        app_ctx: 开放应用上下文（含 ``owner_user_id``）。
        resource_created_id: 目标资源的 ``created_id``。
        label: 资源名（用于报错）。

    Raises:
        CustomException: 非平台级且非本人创建 → 只读拒绝（403）。
    """
    if app_ctx is None:
        return
    owner = getattr(app_ctx, "owner_user_id", None)
    if owner is None:
        # 平台级应用可写
        return
    if resource_created_id != owner:
        raise CustomException(
            msg=f"{label}为公开/共享资源，仅只读，允许查看；如需修改请使用自己的资源",
            code=10403,
            status_code=403,
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


# --------------------------------------------------------------------------- #
# 标准 CRUD 能力注册器（skill / tool / plugin / mcp / query / ... 共用）
# --------------------------------------------------------------------------- #
def _get_service(service_path: str, cls_name: str):
    """延迟导入 service 类。"""
    import importlib

    return getattr(importlib.import_module(service_path), cls_name)


def _get_schema(schema_path: str, schema_name: str):
    """延迟导入 schema 类。"""
    import importlib

    return getattr(importlib.import_module(schema_path), schema_name)


def _service_uid() -> int:
    """同步取服务账号 id（仅供需要显式 ``user_id`` 的 service 方法用）。

    若服务账号尚未确保（仅理论不可能，因为写路径都先走 ``open_auth``），回退 0。
    """
    return _service_user_id or 0


def register_standard_crud(
    *,
    category: str,
    domain: str,
    cls_name: str,
    service_path: str,
    schema_path: str,
    create_schema: str,
    update_schema: str,
    list_name: str,
    get_name: str,
    label: str,
    id_key: str = "id",
    delete_needs_user: bool = False,
    list_needs_user: bool = False,
    get_needs_user: bool = False,
    toggle_name: str | None = None,
    approval: bool = True,
) -> None:
    """为某资产域注册标准 CRUD（list/get/create/update/delete [+toggle]）能力。

    写操作统一用 ``await open_auth()``（平台服务账号）调用 service，避免 ``auth.user.id`` 崩；
    对按 ``user_id`` 个人隔离的 service（如 mcp），list/get/delete 传服务账号 id。
    """
    from ..registry import Capability, register

    async def _list(*, app_ctx: Any, payload: dict) -> dict:
        svc = _get_service(service_path, cls_name)
        uid = _service_uid()
        items = await getattr(svc, list_name)(uid) if list_needs_user else await getattr(svc, list_name)()
        return {"items": items, "total": len(items)}

    async def _get(*, app_ctx: Any, payload: dict) -> dict:
        svc = _get_service(service_path, cls_name)
        target = need_int(payload, id_key)
        uid = _service_uid()
        row = (
            await getattr(svc, get_name)(target, uid)
            if get_needs_user
            else await getattr(svc, get_name)(target)
        )
        if row is None:
            raise not_found(label)
        return row

    async def _create(*, app_ctx: Any, payload: dict) -> dict:
        svc = _get_service(service_path, cls_name)
        cls = _get_schema(schema_path, create_schema)
        from pydantic import ValidationError

        try:
            data = cls(**payload)
        except ValidationError as exc:
            raise bad_request(exc) from exc
        return await svc.create(data, await open_auth())

    async def _update(*, app_ctx: Any, payload: dict) -> dict:
        svc = _get_service(service_path, cls_name)
        target = need_int(payload, id_key)
        cls = _get_schema(schema_path, update_schema)
        from pydantic import ValidationError

        body = {k: v for k, v in payload.items() if k != id_key}
        try:
            data = cls(**body)
        except ValidationError as exc:
            raise bad_request(exc) from exc
        row = await svc.update(target, data, await open_auth())
        if row is None:
            raise not_found(label)
        return row

    async def _delete(*, app_ctx: Any, payload: dict) -> dict:
        svc = _get_service(service_path, cls_name)
        target = need_int(payload, id_key)
        require_confirm(payload, f"删除{label}")
        uid = _service_uid()
        if delete_needs_user:
            await svc.delete([target], uid)
        else:
            await svc.delete([target])
        return {"deleted": target}

    async def _toggle(*, app_ctx: Any, payload: dict) -> dict:
        svc = _get_service(service_path, cls_name)
        target = need_int(payload, id_key)
        enabled = bool(payload.get("enabled", True))
        row = await getattr(svc, toggle_name)(target, enabled, await open_auth())
        if row is None:
            raise not_found(label)
        return row

    defs: list[tuple] = [
        (f"{domain}.list", f"integration:{category}:query", f"{label}列表", f"列出全部{label}", {}, "items: array, total: int", _list, False, None),
    ]
    if get_name:
        defs.append(
            (f"{domain}.get", f"integration:{category}:query", f"{label}详情", f"按 ID 查询{label}", {"type": "object", "properties": {id_key: {"type": "integer"}}, "required": [id_key]}, f"{label}对象", _get, False, None)
        )
    defs.extend([
        (f"{domain}.create", f"integration:{category}:create", f"创建{label}", f"创建一个{label}", {"type": "object", "properties": {}, "additionalProperties": True}, f"{label}对象（含 id）", _create, False, None),
        (f"{domain}.update", f"integration:{category}:update", f"更新{label}", f"更新{label}", {"type": "object", "properties": {id_key: {"type": "integer"}}, "required": [id_key]}, f"更新后的{label}对象", _update, False, None),
        (f"{domain}.delete", f"integration:{category}:delete", f"删除{label}", f"删除{label}（须 confirm=true）", {"type": "object", "properties": {id_key: {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": [id_key, "confirm"]}, "deleted: int", _delete, approval, None),
    ])
    if toggle_name:
        defs.append(
            (f"{domain}.toggle", f"integration:{category}:update", f"启停{label}", f"启用/停用{label}", {"type": "object", "properties": {id_key: {"type": "integer"}, "enabled": {"type": "boolean"}}, "required": [id_key]}, f"{label}对象", _toggle, False, None)
        )
    for code, perm, name, desc, schema, returns, handler, is_approval, _ in defs:
        register(
            Capability(
                code=code,
                category=category,
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=code.replace(".", "_"),
                requires_approval=is_approval,
            )
        )
