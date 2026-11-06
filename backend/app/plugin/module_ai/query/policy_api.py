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
import re
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
from app.core.logger import log
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

#: ``attr`` 主体的写法：``属性名==值`` / ``属性名=值`` / ``属性名:值``，**不许有空格/引号**。
#:
#: 为什么要卡死：引擎的 ``_ATTR_SUBJECT`` 允许 ``dept_id = 3`` 这种宽松写法，但那条
#: 正则匹配出的值会带前后空白，属性比对永远失败 = 策略"配了永不生效"。保存期直接拒绝，
#: 比让管理员在治理页猜"为什么没生效"好。
_ATTR_SUBJECT_VALUE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:==|=|:)[^\s'\"]+$")

#: ``user`` 主体的值必须是正整数用户 id（``admin`` 这种账号名永远匹配不到）。
_USER_SUBJECT_VALUE = re.compile(r"^[1-9][0-9]*$")

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


#: 可写字段（``_FIELDS``）。顺序固定，用于「合并现值 + 本次改动」的完整策略校验。
_FIELDS = (
    "name",
    "description",
    "enabled",
    "priority",
    "resource_kind",
    "resource_code",
    "effect",
    "subject_kind",
    "subject_value",
    "condition",
    "columns",
    "mask_expr",
    "marking",
)


def _validate(
    payload: PolicyUpsert, existing: dict | None = None
) -> tuple[dict, set[str], str]:
    """校验并归一化；返回 ``(归一字段, 本次要写的字段, 错误原因)``。

    **更新走部分更新**（Important 1）：只写请求里实际出现的字段
    （``payload.model_fields_set``），其余列保持库里现值。历史缺陷是 UPDATE 写所有列，
    而 ``PolicyUpsert`` 又给了 ``effect="allow"`` / ``subject_kind="everyone"`` /
    ``marking=""`` 默认值 —— 只传 ``{id,name,resource_code}`` 就会把一条 deny 静默
    改成 allow、把 role:analyst 改成 everyone、并清掉 ``marking``（顺带关掉星号止血）。

    校验必须按「库里现值 + 本次改动」**合并后的完整策略**做：只传 ``effect="mask"``
    时，``mask_expr`` 可能来自库里；只传 ``name`` 时，也不能拿空 ``mask_expr`` 去
    误判一条合法的 mask 策略。
    """
    update = existing is not None
    provided = set(payload.model_fields_set) - {"id"} if update else set(_FIELDS)
    merged: dict = {key: existing.get(key) for key in _FIELDS} if update else {}
    dumped = payload.model_dump()
    for key in provided:
        merged[key] = dumped.get(key)

    name = str(merged.get("name") or "").strip()
    resource_code = str(merged.get("resource_code") or "").strip()
    effect = str(merged.get("effect") or "").strip().lower()
    resource_kind = str(merged.get("resource_kind") or "").strip().lower()
    subject_kind = str(merged.get("subject_kind") or "").strip().lower()
    subject_value = str(merged.get("subject_value") or "").strip()
    condition = str(merged.get("condition") or "").strip()
    mask_expr = str(merged.get("mask_expr") or "").strip()
    marking = str(merged.get("marking") or "").strip()
    columns = _norm_columns(merged.get("columns") or [])

    empty: set[str] = set()
    if not name:
        return {}, empty, "策略名不能为空"
    if not resource_code:
        return {}, empty, "resource_code（表名/视图名）不能为空"
    if effect not in _EFFECTS:
        return {}, empty, f"effect 只允许 {'/'.join(_EFFECTS)}，收到 {effect!r}"
    if resource_kind not in _RESOURCE_KINDS:
        return {}, empty, f"resource_kind 只允许 {'/'.join(_RESOURCE_KINDS)}，收到 {resource_kind!r}"
    if subject_kind not in _SUBJECT_KINDS:
        return {}, empty, f"subject_kind 只允许 {'/'.join(_SUBJECT_KINDS)}，收到 {subject_kind!r}"
    if subject_kind in _SUBJECT_WITH_VALUE and not subject_value:
        return {}, empty, f"subject_kind={subject_kind} 时 subject_value 不能为空（否则永不命中）"
    if subject_kind == "user" and not _USER_SUBJECT_VALUE.match(subject_value):
        return {}, empty, (
            f"subject_kind=user 的 subject_value 必须是用户 id 数字，收到 {subject_value!r}"
        )
    if subject_kind == "attr" and not _ATTR_SUBJECT_VALUE.match(subject_value):
        return {}, empty, (
            "subject_kind=attr 的 subject_value 必须写成「属性名==值」且**不含空格/引号**"
            f"（如 dept_id==3），收到 {subject_value!r}"
        )

    if effect == "mask":
        if not mask_expr:
            return {}, empty, "effect=mask 必须提供 mask_expr"
        if not columns:
            return {}, empty, (
                "effect=mask 必须指定 columns：空列清单 = 整表所有列都被掩码，"
                "几乎不会是配置本意（真要整表请逐列列出）"
            )
        error = validate_mask(mask_expr)
        if error:
            return {}, empty, f"mask_expr 不合法：{error}"
    elif mask_expr:
        return {}, empty, "只有 effect=mask 才能设置 mask_expr"

    if condition:
        if effect != "allow":
            return {}, empty, (
                f"effect={effect} 不支持 condition：行级条件只对 allow 生效，"
                "写在 deny/mask 上会变成整表生效（与配置意图不符）"
            )
        error = validate_condition(condition)
        if error:
            return {}, empty, f"condition 不合法：{error}"

    fields = {
        "name": name,
        "description": str(merged.get("description") or "").strip()[:255],
        "enabled": bool(merged.get("enabled")),
        "priority": int(merged.get("priority") or 0),
        "resource_kind": resource_kind,
        "resource_code": resource_code,
        "effect": effect,
        "subject_kind": subject_kind,
        "subject_value": subject_value[:160],
        "condition": condition,
        "columns": columns,
        "mask_expr": mask_expr,
        "marking": marking,
    }
    return fields, provided, ""


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


async def _active_role_codes(uid: int) -> set[str]:
    """用户**启用中**的角色码（``status='0'`` 且未软删）。

    不复用 ``AiQueryService._user_role_codes_by_id``：那个只滤 ``is_deleted``，
    停用角色仍会返回；而真正的权限判定（``AuthPermission``）只认
    ``role.status == "0"``。两套口径会让解释接口显示 permit、线上却 403（Important 2）。

    读角色失败按"没有角色"处理（fail-closed）：解释接口宁可少给权限，
    也不能凭一条读不到的记录告诉管理员"他能看"。
    """
    try:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT r.code FROM sys_role r "
                        "JOIN sys_user_roles ur ON ur.role_id=r.id "
                        "WHERE ur.user_id=:u AND r.is_deleted=false AND r.status='0'"
                    ),
                    {"u": uid},
                )
            ).fetchall()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[问数权限] explain 读取用户角色失败（按无角色处理）: user_id={uid}, err={e}")
        return set()
    return {str(r[0]) for r in rows if r[0]}


async def principal_for_user(user_id: int) -> tuple[Principal | None, str]:
    """按**库里的身份**构造目标用户的主体；不可用时返回 ``(None, 拒绝原因)``。

    刻意不复用请求的 ``auth``：解释接口回答的是"**这个 user_id** 能看什么"，
    不是"当前登录者能看什么"。``is_superuser`` 只从 ``sys_user`` 读。

    与真实链路对齐（Important 2）：

    - **停用账号**：``get_current_user`` 直接 401，解释接口也必须 deny；
    - **停用角色**：只有 ``status='0'`` 的角色参与主体匹配（``AuthPermission`` 口径）。

    属性/数据域分别由 ``load_principal`` / ``guard._with_domains`` 补齐 ——
    漏掉数据域会让 ``subject_kind=domain`` 的策略在解释里"看起来没命中"。
    """
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None, f"主体不存在：user_id={user_id!r} 不是合法用户 id（按拒绝处理）"
    if uid <= 0:
        return None, f"主体不存在：user_id={uid}（按拒绝处理）"

    async with async_db_session() as db:
        row = (
            await db.execute(
                text(
                    "SELECT id, is_superuser, status FROM sys_user "
                    "WHERE id=:u AND is_deleted=false"
                ),
                {"u": uid},
            )
        ).fetchone()
    if not row:
        return None, f"主体不存在：user_id={uid}（库里没有该用户，按拒绝处理）"

    status = str(row[2] if row[2] is not None else "0")
    if status != "0":
        return None, f"账号已停用：user_id={uid}（停用账号不参与任何访问判定，按拒绝处理）"

    roles = await _active_role_codes(uid)
    fake_auth = SimpleNamespace(
        user=SimpleNamespace(
            id=uid,
            is_superuser=bool(row[1]),
            roles=[_RoleCode(code) for code in sorted(roles)],
        )
    )
    principal = await load_principal(fake_auth, entry="explain")
    if principal is None:  # 理论上不会（上面已确认用户存在）
        return None, f"主体不存在：user_id={uid}（按拒绝处理）"
    return await _with_domains(principal), ""


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

    existing = None
    if data.id:
        existing = await repo.get_policy_row(int(data.id))
        if existing is None:
            return _bad(f"策略 {data.id} 不存在（或已删除），无法更新")

    fields, write_keys, error = _validate(data, existing)
    if error:
        return _bad(error)

    now = datetime.now()
    async with async_db_session.begin() as db:
        if data.id:
            # 只写本次请求真正出现的列（``write_keys``）；其余列保持库里现值。
            writes = {key: fields[key] for key in write_keys if key != "columns"}
            assignments = [f"{col}=:{col}" for col in writes]
            if "columns" in write_keys:
                writes["cols"] = json.dumps(fields["columns"], ensure_ascii=False)
                assignments.append("columns=:cols")
            assignments.append("updated_time=:now")
            result = await db.execute(
                text(
                    f"UPDATE ai_policy SET {', '.join(assignments)} "
                    "WHERE id=:id AND is_deleted=false"
                ),
                {**writes, "id": int(data.id), "now": now},
            )
            if not result.rowcount:
                return _bad(f"策略 {data.id} 不存在（或已删除），无法更新")
            pid, created = int(data.id), False
        else:
            params = {
                **{k: v for k, v in fields.items() if k != "columns"},
                "cols": json.dumps(fields["columns"], ensure_ascii=False),
                "now": now,
            }
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
    principal, identity_reason = await principal_for_user(user_id)
    if principal is None:
        # 不伪造主体：用户不存在/已停用 → 只能回答拒绝（fail-closed），
        # 且 reason 要写明是"没有这个人"还是"账号已停用"（治理页据此排查）。
        return SuccessResponse(
            data={
                "permit": False,
                "reason": identity_reason,
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
