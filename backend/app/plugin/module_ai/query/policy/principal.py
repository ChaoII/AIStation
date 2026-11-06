"""统一访问主体（Principal）：问数权限判定的唯一输入。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §3。

一个 Principal 只描述「**谁**在**哪个入口**访问」：

- ``user_id`` / ``is_superuser`` / ``roles``：身份与角色。角色复用
  ``service._user_role_codes(auth)``（读 ``auth.user.roles``），不再另写一套查询；
- ``attrs``：行级条件用的用户属性（目前只有 ``dept_id``，值为字符串）。
  属性读不到时返回空字典 —— 判定侧按「缺属性」处理（fail-closed），
  绝不能因为读属性失败就把整条查询放行或否掉；
- ``entry``：入口标记（ask/agent/app/workflow/cron/report/metric/object/export/eval），
  审计表 ``ai_query_access_log.entry`` 直接用它。

``auth`` 为空（agent / app / workflow / cron 等非请求上下文）一律返回 ``None``：
判定侧按「missing principal」拒绝，不要在这里伪造一个匿名身份。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from app.core.database import async_db_session
from app.core.logger import log

#: 用户属性来源表。
_USER_TABLE = "sys_user"

#: 需要从 ``sys_user`` 读取的属性列（只读判定要用的列，不把手机号等敏感字段带进内存）。
_ATTR_COLUMNS = ("dept_id",)


@dataclass(frozen=True)
class Principal:
    """访问主体：一次问数请求（或一次调度执行）的身份快照。"""

    user_id: int | None
    is_superuser: bool
    roles: tuple[str, ...]
    attrs: dict[str, str]
    entry: str


def _role_codes(auth) -> tuple[str, ...]:
    """角色码：复用 ``service._user_role_codes``，归一成**有序元组**。

    集合顺序不稳定，元组用于下游做 ``scope_hash``（角色序不能每次变）与相等判断；
    空角色码（``code`` 为空）直接丢掉，避免策略里出现无意义的 ``""`` 主体。
    函数内导入 ``service``：``service`` 会反向依赖 ``policy`` 子包，模块级导入会成环。
    """
    from .. import service

    return tuple(sorted(str(c) for c in service._user_role_codes(auth) if c))


async def _load_attrs(uid: int) -> dict[str, str]:
    """读取判定所需的用户属性；列不存在或查询失败都返回 ``{}``（不抛）。

    两种降级刻意区分：

    - **列不存在**：老库没补 ``dept_id``，属于合法降级，静默返回 ``{}``；
    - **其它异常**：记一条 ``log.warning`` 再返回 ``{}`` —— 不吞掉"库真的坏了"这个信号。
    """
    try:
        async with async_db_session() as db:
            cols = await db.run_sync(
                lambda s: {c["name"] for c in sa_inspect(s.connection()).get_columns(_USER_TABLE)}
            )
            if any(c not in cols for c in _ATTR_COLUMNS):
                return {}
            row = (
                await db.execute(
                    text(f"SELECT {', '.join(_ATTR_COLUMNS)} FROM {_USER_TABLE} WHERE id=:u"),
                    {"u": uid},
                )
            ).fetchone()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[问数权限] 读取用户属性失败（按无属性处理）: user_id={uid}, err={e}")
        return {}
    if not row:
        return {}
    return {c: str(v) for c, v in zip(_ATTR_COLUMNS, row, strict=False) if v is not None}


async def load_principal(auth, entry: str = "ask") -> Principal | None:
    """按鉴权上下文装载主体；没有可用身份时返回 ``None``。

    ``is_superuser`` 取 ``auth.user.is_superuser``（与既有 ``_assert_ds_access`` 同源），
    超管**不跳过** ``attrs`` 加载：审计与 explain 要看完整主体（部门等）。
    """
    user = getattr(auth, "user", None) if auth is not None else None
    try:
        uid = int(getattr(user, "id", 0) or 0)
    except (TypeError, ValueError):
        uid = 0
    if not uid:
        return None
    return Principal(
        user_id=uid,
        is_superuser=bool(getattr(user, "is_superuser", False)),
        roles=_role_codes(auth),
        attrs=await _load_attrs(uid),
        entry=entry,
    )
