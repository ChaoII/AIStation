"""问数权限：**策略管理**与**权限解释**接口（T12）。

这层只做 HTTP 编解码 + 入库前校验，判定与读取全部复用既有模块：

- 列表：``repo.list_policy_rows``（管理视图，含停用；判定侧仍走 ``repo.list_policies``）；
- 解释：``engine.decide_table`` / ``engine.decide_column`` + ``audit.list_access_logs``；
- 保存：入参先过 ``policy.compiler.validate_condition`` / ``validate_mask``
  （与执行期同一套 AST 白名单），坏策略一律 **400 且不入库**。
  为什么必须在这一层拦：策略是管理员手填的 SQL 片段，存进库后执行期才报错
  就是对**所有用户**的拒答（fail-closed），而且没人知道是哪条策略写坏了。

保存校验的硬规则（防"看起来配了、实际不生效/反而更严"）：

1. ``effect`` / ``resource_kind`` / ``subject_kind`` 必须是枚举值；
2. ``condition`` 只允许 ``allow``（行级过滤）；``deny`` / ``mask`` 带条件会被**整表**
   生效，与管理员意图不符，直接拒绝；
3. ``mask`` 必须有 ``mask_expr``；``allow`` / ``deny`` 的 ``mask_expr`` 必须为空；
4. ``subject_kind`` 非 ``everyone`` 时 ``subject_value`` 不能为空（否则这条策略
   永远匹配不到任何主体 = 白配一条）。

解释接口的身份**只从库里读**（``sys_user.is_superuser`` + 角色 + ``dept_id``）：
入参只有 ``user_id``，没有 ``is_superuser``，避免"传个 true 就成超管"。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .policy import audit, engine, repo
from .policy.compiler import validate_condition, validate_mask
from .policy.guard import _with_domains
from .policy.principal import Principal, load_principal

PolicyRouter = APIRouter(route_class=OperationLogRoute, tags=["AI-智能问数-权限策略"])

#: 与 ``policy.engine`` / ``policy.model`` 的取值保持一致（三处别各写一套）。
_EFFECTS = ("allow", "deny", "mask")
_RESOURCE_KINDS = ("table", "view")
_SUBJECT_KINDS = ("everyone", "role", "user", "attr", "domain")
#: 这些主体必须带值，``everyone`` 不需要。
_SUBJECT_WITH_VALUE = ("role", "user", "attr", "domain")

_PERM_QUERY = "module_ai:query:policy:query"
_PERM_CREATE = "module_ai:query:policy:create"
_PERM_UPDATE = "module_ai:query:policy:update"
_PERM_DELETE = "module_ai:query:policy:delete"


class PolicyUpsert(BaseModel):
    """新增/更新策略的入参（``id`` 有值 = 更新）。"""

    id: int | None = Field(default=None, description="策略 ID；有值表示更新")
    name: str = Field(default="", max_length=120, description="策略名")
    description: str = Field(default="", max_length=255, description="说明")
    enabled: bool = Field(default=True, description="是否启用")
    priority: int = Field(default=100, description="优先级（同具体性下越大越先）")
    resource_kind: str = Field(default="table", description="table / view")
    resource_code: str = Field(default="", max_length=160, description="表名 / 视图名")
    effect: str = Field(default="allow", description="allow / deny / mask")
    subject_kind: str = Field(default="everyone", description="everyone/role/user/attr/domain")
    subject_value: str = Field(default="", max_length=160, description="角色码/用户 id/属性式")
    condition: str = Field(default="", description="行级过滤条件（仅 allow）")
    columns: list[str] = Field(default_factory=list, description="列清单；空 = 整表")
    mask_expr: str = Field(default="", description="掩码表达式（仅 mask）")
    marking: str = Field(default="", max_length=60, description="标记名，如 sensitive")


class PolicyDeleteRequest(BaseModel):
    """批量删除（软删）。"""

    ids: list[int] = Field(default_factory=list, description="策略 ID 列表")


def _bad(msg: str) -> ErrorResponse:
    return ErrorResponse(msg=msg, status_code=400)


def _norm_columns(columns: list[str]) -> list[str]:
    """列清单归一：去空白、小写、去重（保序）。引擎侧同样按小写比较。"""
    out: list[str] = []
    for raw in columns or ():
        col = str(raw or "").strip().lower()
        if col and col not in out:
            out.append(col)
    return out


def _validate(payload: PolicyUpsert) -> tuple[dict, str]:
    """校验并归一化入参；返回 ``(归一后的字段, 错误原因)``（错误原因为空串 = 合法）。"""
    name = str(payload.name or "").strip()
    resource_code = str(payload.resource_code or "").strip()
    effect = str(payload.effect or "").strip().lower()
    resource_kind = str(payload.resource_kind or "").strip().lower()
    subject_kind = str(payload.subject_kind or "").strip().lower()
    subject_value = str(payload.subject_value or "").strip()
    condition = str(payload.condition or "").strip()
    mask_expr = str(payload.mask_expr or "").strip()
    marking = str(payload.marking or "").strip()
    columns = _norm_columns(payload.columns)

    if not name:
        return {}, "策略名不能为空"
    if not resource_code:
        return {}, "resource_code（表名/视图名）不能为空"
    if effect not in _EFFECTS:
        return {}, f"effect 只允许 {'/'.join(_EFFECTS)}，收到 {effect!r}"
    if resource_kind not in _RESOURCE_KINDS:
        return {}, f"resource_kind 只允许 {'/'.join(_RESOURCE_KINDS)}，收到 {resource_kind!r}"
    if subject_kind not in _SUBJECT_KINDS:
        return {}, f"subject_kind 只允许 {'/'.join(_SUBJECT_KINDS)}，收到 {subject_kind!r}"
    if subject_kind in _SUBJECT_WITH_VALUE and not subject_value:
        return {}, f"subject_kind={subject_kind} 时 subject_value 不能为空（否则永不命中）"

    if effect == "mask":
        if not mask_expr:
            return {}, "effect=mask 必须提供 mask_expr"
        error = validate_mask(mask_expr)
        if error:
            return {}, f"mask_expr 不合法：{error}"
    elif mask_expr:
        return {}, "只有 effect=mask 才能设置 mask_expr"
    else:
        mask_expr = ""

    if condition:
        if effect != "allow":
            return {}, (
                f"effect={effect} 不支持 condition：行级条件只对 allow 生效，"
                "写在 deny/mask 上会变成整表生效（与配置意图不符）"
            )
        error = validate_condition(condition)
        if error:
            return {}, f"condition 不合法：{error}"

    return {
        "name": name,
        "description": str(payload.description or "").strip()[:255],
        "enabled": bool(payload.enabled),
        "priority": int(payload.priority),
        "resource_kind": resource_kind,
        "resource_code": resource_code,
        "effect": effect,
        "subject_kind": subject_kind,
        "subject_value": subject_value[:160],
        "condition": condition,
        "columns": columns,
        "mask_expr": mask_expr,
        "marking": marking,
    }, ""


async def _require_perm(auth: AuthSchema, code: str) -> None:
    """处理器内二次校验（``save`` 需要按"有无 id"区分 create/update）。

    直接复用 :class:`AuthPermission`：超管绕过、权限集合展开、403 文案都与全局一致，
    不另写一套判定。
    """
    await AuthPermission([code])(auth)


@dataclass(frozen=True)
class _RoleCode:
    """``service._user_role_codes`` 只读 ``role.code``；库里的角色行没必要整行载入。"""

    code: str


async def principal_for_user(user_id: int) -> Principal | None:
    """按**库里的身份**构造目标用户的主体；用户不存在返回 ``None``。

    刻意不复用请求的 ``auth``：解释接口回答的是"**这个 user_id** 能看什么"，
    不是"当前登录者能看什么"。``is_superuser`` 只从 ``sys_user`` 读。

    角色用 ``AiQueryService._user_role_codes_by_id``（与其它权限判定同源），
    属性/数据域分别由 ``load_principal`` / ``guard._with_domains`` 补齐 ——
    漏掉数据域会让 ``subject_kind=domain`` 的策略在解释里"看起来没命中"。
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    if uid <= 0:
        return None

    async with async_db_session() as db:
        row = (
            await db.execute(
                text(
                    "SELECT id, is_superuser FROM sys_user "
                    "WHERE id=:u AND is_deleted=false"
                ),
                {"u": uid},
            )
        ).fetchone()
    if not row:
        return None

    from .service import AiQueryService  # 函数内导入：service 反向依赖 policy 子包

    roles = await AiQueryService._user_role_codes_by_id(uid)
    fake_auth = SimpleNamespace(
        user=SimpleNamespace(
            id=uid,
            is_superuser=bool(row[1]),
            roles=[_RoleCode(code) for code in sorted(roles)],
        )
    )
    principal = await load_principal(fake_auth, entry="explain")
    if principal is None:  # 理论上不会（上面已确认用户存在）
        return None
    return await _with_domains(principal)


def _matched_item(policy) -> dict:
    """``matched`` 的元素：治理页展示"判定时看到了哪条策略"。"""
    return {
        "id": int(policy.id or 0),
        "effect": policy.effect,
        "resource_kind": policy.resource_kind,
        "resource_code": policy.resource_code,
        "subject_kind": policy.subject_kind,
        "subject_value": policy.subject_value,
        "priority": int(policy.priority or 0),
        "columns": list(policy.columns),
    }


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
@PolicyRouter.get("/policy/list", summary="策略列表（含停用，不含软删）")
async def list_policies(
    auth: Annotated[AuthSchema, Depends(AuthPermission([_PERM_QUERY]))],
    resource_kind: str | None = None,
    resource_code: str | None = None,
) -> JSONResponse:
    rows = await repo.list_policy_rows(
        resource_kind=resource_kind or "", resource_code=resource_code or ""
    )
    return SuccessResponse(data=rows, msg="查询成功")


@PolicyRouter.post("/policy/save", summary="保存策略（新增/更新）")
async def save_policy(
    data: PolicyUpsert,
    auth: Annotated[
        AuthSchema, Depends(AuthPermission([_PERM_CREATE, _PERM_UPDATE]))
    ],
) -> JSONResponse:
    await _require_perm(auth, _PERM_UPDATE if data.id else _PERM_CREATE)

    fields, error = _validate(data)
    if error:
        return _bad(error)

    now = datetime.now()
    params = {
        **{k: v for k, v in fields.items() if k != "columns"},
        "cols": json.dumps(fields["columns"], ensure_ascii=False),
        "now": now,
    }
    async with async_db_session.begin() as db:
        if data.id:
            params["id"] = int(data.id)
            result = await db.execute(
                text(
                    "UPDATE ai_policy SET name=:name, description=:description, "
                    "enabled=:enabled, priority=:priority, resource_kind=:resource_kind, "
                    "resource_code=:resource_code, effect=:effect, "
                    "subject_kind=:subject_kind, subject_value=:subject_value, "
                    "condition=:condition, columns=:cols, mask_expr=:mask_expr, "
                    "marking=:marking, updated_time=:now "
                    "WHERE id=:id AND is_deleted=false"
                ),
                params,
            )
            if not result.rowcount:
                return _bad(f"策略 {data.id} 不存在（或已删除），无法更新")
            pid, created = int(data.id), False
        else:
            result = await db.execute(
                text(
                    "INSERT INTO ai_policy "
                    "(name, description, enabled, priority, resource_kind, resource_code, "
                    "effect, subject_kind, subject_value, condition, columns, mask_expr, "
                    "marking, created_time, updated_time, is_deleted) "
                    "VALUES (:name, :description, :enabled, :priority, :resource_kind, "
                    ":resource_code, :effect, :subject_kind, :subject_value, :condition, "
                    ":cols, :mask_expr, :marking, :now, :now, false) RETURNING id"
                ),
                params,
            )
            pid, created = int(result.scalar()), True

    return SuccessResponse(
        data={"id": pid, "created": created},
        msg="新增成功" if created else "更新成功",
    )


@PolicyRouter.post("/policy/delete", summary="删除策略（软删，可批量）")
async def delete_policies(
    data: PolicyDeleteRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission([_PERM_DELETE]))],
) -> JSONResponse:
    ids = sorted({int(i) for i in (data.ids or []) if int(i) > 0})
    deleted = 0
    if ids:
        now = datetime.now()
        async with async_db_session.begin() as db:
            for pid in ids:
                result = await db.execute(
                    text(
                        "UPDATE ai_policy SET is_deleted=true, updated_time=:now "
                        "WHERE id=:id AND is_deleted=false"
                    ),
                    {"id": pid, "now": now},
                )
                # 不存在的 id 静默跳过：批量删/重复点不该 500
                deleted += int(result.rowcount or 0)
    return SuccessResponse(data={"deleted": deleted}, msg="删除成功")


@PolicyRouter.get("/access/explain", summary="解释某用户对表/列的访问判定")
async def explain_access(
    auth: Annotated[AuthSchema, Depends(AuthPermission([_PERM_QUERY]))],
    user_id: Annotated[int, Query(description="目标用户 ID（身份只从库里读）")],
    table: Annotated[str, Query(min_length=1, description="表名 / 视图名")],
    column: Annotated[str | None, Query(description="给定时做列级判定")] = None,
) -> JSONResponse:
    principal = await principal_for_user(user_id)
    if principal is None:
        # 不伪造主体：解释接口对"库里没有这个人"只能回答拒绝（fail-closed）
        return SuccessResponse(
            data={
                "permit": False,
                "reason": f"主体不存在：user_id={user_id}（库里没有该用户，按拒绝处理）",
                "policy_ids": [],
                "matched": [],
                "attrs_missing": [],
                "superuser": False,
            },
            msg="查询成功",
        )

    policies = await repo.list_policies()
    if column:
        decision = engine.decide_column(policies, principal, table, column)
    else:
        decision = engine.decide_table(policies, principal, table)

    return SuccessResponse(
        data={
            "permit": bool(decision.permit),
            "reason": decision.reason,
            "policy_ids": [int(i) for i in decision.policy_ids],
            "matched": [
                _matched_item(p)
                for p in engine.matched_policies(policies, principal, table)
            ],
            "attrs_missing": list(engine.missing_attributes(policies, principal, table)),
            "superuser": bool(principal.is_superuser),
        },
        msg="查询成功",
    )


@PolicyRouter.get("/access/logs", summary="访问审计（最近 N 条）")
async def access_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission([_PERM_QUERY]))],
    limit: int = 100,
) -> JSONResponse:
    rows = await audit.list_access_logs(limit)
    return SuccessResponse(data=rows, msg="查询成功")
