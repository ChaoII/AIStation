"""对象权限：本体资源的 ACL + 对象数据的单元格级安全。

对齐官方 `object-permissioning`：

- **两层授权**：*"We can conceptualize the Ontology's authorization structure on these two
  levels: **ontology resources**, and **objects and links**."*
  → 资源层 = 对象/关系/动作/函数等**模式**的 view/edit/manage；数据层 = 实例的单元格级安全。

- **单元格级安全**：*"Both approaches support cell-level security, which is a combination of
  row and column level security."*
  → 行级 = 对象安全策略（策略表达式）；列级 = 属性安全策略（标记/角色）。

- **看类型与看数据是两件事**：*"To see an object type, you must have View permissions on the
  object type, but do not need View permissions for the backing datasource."*

- **读时生效**：*"Granular row and column controls ... filter what a user can read. These controls
  do not extend to downstream outputs or exports."* → 我们只在读路径上过滤，不做下游传播。

**与官方的差异（诚实说明）**：官方用 Compass 项目做资源权限，我们没有文件系统，
因此实现官方文档里并列的**旧模型「Ontology roles」**（viewer/editor/owner）。
角色列表为空 = 公开（保持既有数据的行为不变）。
"""
from __future__ import annotations

import ast
import operator as op
import re
from dataclasses import dataclass, field
from typing import Any

from . import service as _svc

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
#: 本体资源种类（模式层）
ONT_RESOURCE_KINDS = ("object", "link", "action", "function", "interface",
                      "value_type", "shared_property")
ONT_RESOURCE_LABEL = {
    "object": "对象类型", "link": "关系类型", "action": "动作类型",
    "function": "函数", "interface": "接口", "value_type": "值类型",
    "shared_property": "共享属性",
}

#: 行策略效果
ONT_POLICY_EFFECTS = ("allow", "deny")

#: 用户命名空间上允许访问的属性（其它一律拒绝）
_USER_ATTRS = ("id", "name", "username", "dept", "dept_id", "superuser")

#: 策略表达式可用的内置函数
POLICY_BUILTINS: dict[str, Any] = {
    "len": len,
    "str": str,
    "int": lambda x: int(float(x)),
    "float": float,
    "lower": lambda s: str(s).lower(),
    "upper": lambda s: str(s).upper(),
    "contains": lambda hay, needle: str(needle) in str(hay),
    "startswith": lambda s, p: str(s).startswith(str(p)),
    "endswith": lambda s, p: str(s).endswith(str(p)),
    "any": any,
    "all": all,
    "min": min,
    "max": max,
}


class PolicyError(ValueError):
    """策略表达式错误。"""


# ---------------------------------------------------------------------------
# 主体（Principal）
# ---------------------------------------------------------------------------
@dataclass
class Principal:
    """访问主体：人（或代表人的 Agent）。"""

    user_id: int = 0
    username: str = ""
    name: str = ""
    is_superuser: bool = False
    role_codes: list[str] = field(default_factory=list)
    role_ids: list[int] = field(default_factory=list)
    dept_id: int | None = None
    dept_code: str = ""
    attributes: dict = field(default_factory=dict)
    anonymous: bool = False

    def has_role(self, *codes: str) -> bool:
        want = {str(c).strip() for c in codes if str(c).strip()}
        mine = {str(c) for c in self.role_codes} | {str(i) for i in self.role_ids}
        return bool(want & mine)

    def attr(self, name: str) -> Any:
        """取用户属性。支持官方 ``user.userAttribute('x')`` 的等价写法。"""
        key = str(name or "").strip()
        if key in ("dept", "dept_id"):
            return self.dept_id
        if key == "dept_code":
            return self.dept_code
        if key == "id":
            return self.user_id
        if key == "name":
            return self.name
        if key == "username":
            return self.username
        if key == "superuser":
            return self.is_superuser
        if key == "roles":
            return list(self.role_codes)
        if key in self.attributes:
            return self.attributes[key]
        return None

    def as_dict(self) -> dict:
        return {
            "user_id": self.user_id, "username": self.username, "name": self.name,
            "is_superuser": self.is_superuser, "roles": list(self.role_codes),
            "role_ids": list(self.role_ids), "dept_id": self.dept_id,
            "dept_code": self.dept_code, "anonymous": self.anonymous,
        }


#: 匿名主体（没有登录上下文时使用；默认**不授权**任何受限资源）
ANONYMOUS = Principal(anonymous=True)


async def load_principal(user_id: int | None) -> Principal:
    """按用户 ID 装载主体（角色 + 部门）。"""
    uid = int(user_id or 0)
    if not uid:
        return ANONYMOUS
    row = (await _svc._exec(
        "SELECT id,COALESCE(username,''),COALESCE(name,''),COALESCE(is_superuser,false),dept_id "
        "FROM sys_user WHERE id=:u AND is_deleted=false", {"u": uid})).fetchone()
    if not row:
        return ANONYMOUS
    p = Principal(user_id=int(row[0]), username=row[1], name=row[2],
                  is_superuser=bool(row[3]), dept_id=row[4])
    try:
        rs = await _svc._exec(
            "SELECT r.id, r.code FROM sys_user_roles ur JOIN sys_role r ON r.id=ur.role_id "
            "WHERE ur.user_id=:u", {"u": uid})
        for rid, code in rs.fetchall():
            p.role_ids.append(int(rid))
            if code:
                p.role_codes.append(str(code))
    except Exception:  # noqa: BLE001
        pass
    if p.dept_id:
        try:
            d = (await _svc._exec("SELECT COALESCE(name,'') FROM sys_dept WHERE id=:d",
                                  {"d": p.dept_id})).fetchone()
            p.dept_code = d[0] if d else ""
        except Exception:  # noqa: BLE001
            p.dept_code = ""
    return p


# ---------------------------------------------------------------------------
# 资源层 ACL
# ---------------------------------------------------------------------------
async def get_resource_acl(resource_kind: str, resource_code: str) -> dict | None:
    r = await _svc._exec(
        "SELECT view_roles, edit_roles, manage_roles FROM ai_ont_resource_acl "
        "WHERE resource_kind=:k AND resource_code=:c",
        {"k": resource_kind, "c": resource_code})
    row = r.fetchone()
    if not row:
        return None
    return {"view_roles": _svc._json_list(row[0]),
            "edit_roles": _svc._json_list(row[1]),
            "manage_roles": _svc._json_list(row[2])}


def _role_match(required: list, p: Principal) -> bool:
    """角色列表为空 = 不限制；超管总是通过。"""
    if not required:
        return True
    if p.is_superuser:
        return True
    return p.has_role(*[str(x) for x in required])


async def can_view_resource(resource_kind: str, resource_code: str,
                            p: Principal) -> tuple[bool, str]:
    acl = await get_resource_acl(resource_kind, resource_code)
    if not acl:
        return True, "该资源未配置权限，默认可见"
    if _role_match(acl["view_roles"], p):
        return True, "命中查看角色"
    return False, f"需要以下角色之一才能查看：{'、'.join(map(str, acl['view_roles']))}"


async def can_edit_resource(resource_kind: str, resource_code: str,
                            p: Principal) -> tuple[bool, str]:
    acl = await get_resource_acl(resource_kind, resource_code)
    if not acl:
        return True, "该资源未配置权限，默认可编辑"
    if _role_match(acl["edit_roles"], p):
        return True, "命中编辑角色"
    ok_v, _ = await can_view_resource(resource_kind, resource_code, p)
    if not ok_v:
        return False, f"需要以下角色之一才能编辑：{'、'.join(map(str, acl['edit_roles']))}"
    return False, f"需要以下角色之一才能编辑：{'、'.join(map(str, acl['edit_roles']))}"


async def can_manage_resource(resource_kind: str, resource_code: str,
                              p: Principal) -> tuple[bool, str]:
    acl = await get_resource_acl(resource_kind, resource_code)
    if not acl:
        return True, "该资源未配置权限，默认可管理"
    if _role_match(acl["manage_roles"], p):
        return True, "命中管理角色"
    return False, f"需要以下角色之一才能管理：{'、'.join(map(str, acl['manage_roles']))}"


async def set_resource_acl(resource_kind: str, resource_code: str,
                           view_roles: list, edit_roles: list,
                           manage_roles: list) -> dict:
    if resource_kind not in ONT_RESOURCE_KINDS:
        return {"ok": False, "msg": f"资源种类不支持：{resource_kind}"}
    import json

    have = (await _svc._exec(
        "SELECT id FROM ai_ont_resource_acl WHERE resource_kind=:k AND resource_code=:c",
        {"k": resource_kind, "c": resource_code})).fetchone()
    params = {"k": resource_kind, "c": resource_code,
              "v": json.dumps(view_roles or [], ensure_ascii=False),
              "e": json.dumps(edit_roles or [], ensure_ascii=False),
              "m": json.dumps(manage_roles or [], ensure_ascii=False)}
    if have:
        await _svc._exec_write(
            "UPDATE ai_ont_resource_acl SET view_roles=:v, edit_roles=:e, manage_roles=:m "
            "WHERE resource_kind=:k AND resource_code=:c", params)
    else:
        await _svc._exec_write(
            "INSERT INTO ai_ont_resource_acl(resource_kind,resource_code,view_roles,"
            "edit_roles,manage_roles) VALUES (:k,:c,:v,:e,:m)", params)
    return {"ok": True, "msg": "资源权限已保存"}


async def clear_resource_acl(resource_kind: str, resource_code: str) -> dict:
    await _svc._exec_write(
        "DELETE FROM ai_ont_resource_acl WHERE resource_kind=:k AND resource_code=:c",
        {"k": resource_kind, "c": resource_code})
    return {"ok": True, "msg": "已恢复为默认（公开）"}


# ---------------------------------------------------------------------------
# 行级策略
# ---------------------------------------------------------------------------
class _PolicyUser:
    """策略表达式里的 ``user`` 命名空间。

    只暴露白名单成员，避免表达式触达任意对象。
    """

    __slots__ = ("_p",)

    def __init__(self, p: Principal) -> None:
        object.__setattr__(self, "_p", p)

    @property
    def id(self) -> int:
        return self._p.user_id

    @property
    def name(self) -> str:
        return self._p.name

    @property
    def username(self) -> str:
        return self._p.username

    @property
    def dept(self) -> Any:
        return self._p.dept_id

    @property
    def dept_id(self) -> Any:
        return self._p.dept_id

    @property
    def superuser(self) -> bool:
        return self._p.is_superuser

    def role(self, code: str) -> bool:
        return self._p.has_role(str(code))

    def attribute(self, name: str) -> Any:
        """等价官方 ``user.userAttribute('x')``。"""
        return self._p.attr(str(name))

    def __repr__(self) -> str:  # pragma: no cover - 便于调试
        return f"<PolicyUser {self._p.username or self._p.user_id}>"


_BINOPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
           ast.Mod: op.mod}
_CMP = {ast.Eq: op.eq, ast.NotEq: op.ne, ast.Lt: op.lt, ast.LtE: op.le,
        ast.Gt: op.gt, ast.GtE: op.ge}


def policy_vars(expr: str) -> list[str]:
    """策略表达式里引用的**对象属性名**（排除 ``user`` 与内置函数）。

    这些就是官方所说的 "policy properties" —— 被权限策略引用的属性，
    编辑它们会改变可见性，因此需要更高的编辑权限。
    """
    try:
        tree = ast.parse(expr or "", mode="eval")
    except SyntaxError:
        return []
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id not in POLICY_BUILTINS and n.id != "user":
            out.add(n.id)
    return sorted(out)


def eval_policy(expr: str, props: dict, p: Principal) -> bool:
    """求值一条行级策略：``props`` 是对象实例的属性，``p`` 是访问主体。

    表达式语言示例：
    - ``dept_id == user.attribute('dept')``
    - ``region in user.attribute('regions')``
    - ``user.role('ADMIN') or owner == user.name``
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise PolicyError(f"策略语法错误：{e.msg}") from e
    user = _PolicyUser(p)

    def _ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "user":
                return user
            if node.id in props:
                return props[node.id]
            if node.id in POLICY_BUILTINS:
                raise PolicyError(f"{node.id} 是函数，需要写成 {node.id}(...)")
            # 对象没有这个属性时按 None 处理（避免一条策略因缺列而整表不可见）
            return None
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "user":
                if node.attr in _USER_ATTRS:
                    return getattr(user, node.attr)
                raise PolicyError(f"user 上没有属性 {node.attr}")
            raise PolicyError("只允许访问 user 命名空间上的属性")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and f.value.id == "user":
                if f.attr not in ("role", "attribute"):
                    raise PolicyError(f"user 上不允许调用 {f.attr}")
                if node.keywords:
                    raise PolicyError("user 方法不支持关键字参数")
                return getattr(user, f.attr)(*[_ev(a) for a in node.args])
            if isinstance(f, ast.Name):
                fn = POLICY_BUILTINS.get(f.id)
                if fn is None:
                    raise PolicyError(f"未知函数：{f.id}")
                return fn(*[_ev(a) for a in node.args])
            raise PolicyError("只允许调用白名单函数")
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not _ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -_ev(node.operand)
            raise PolicyError("不支持的一元运算")
        if isinstance(node, ast.BoolOp):
            vals = [_ev(v) for v in node.values]
            return all(vals) if isinstance(node.op, ast.And) else any(vals)
        if isinstance(node, ast.Compare):
            left = _ev(node.left)
            for o, c in zip(node.ops, node.comparators, strict=False):
                right = _ev(c)
                if isinstance(o, ast.In):
                    if not _safe_in(left, right):
                        return False
                elif isinstance(o, ast.NotIn):
                    if _safe_in(left, right):
                        return False
                elif type(o) in _CMP:
                    if not _CMP[type(o)](left, right):
                        return False
                else:
                    raise PolicyError("不支持的比较运算")
                left = right
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return [_ev(e) for e in node.elts]
        if isinstance(node, ast.Subscript):
            return _ev(node.value)[_ev(node.slice)]
        raise PolicyError("策略里不支持的写法")

    return bool(_ev(tree))


def _safe_in(left: Any, right: Any) -> bool:
    """``in`` 运算：右边为空/非容器时返回 False，不抛异常。"""
    if right is None:
        return False
    try:
        return left in right
    except TypeError:
        return False


async def list_row_policies(object_code: str) -> list[dict]:
    r = await _svc._exec(
        "SELECT id,object_code,COALESCE(name,''),COALESCE(description,''),COALESCE(expression,''),"
        "COALESCE(effect,'allow'),enabled,COALESCE(priority,0) "
        "FROM ai_ont_row_policy WHERE object_code=:c ORDER BY priority, id", {"c": object_code})
    return [{"id": x[0], "object_code": x[1], "name": x[2], "description": x[3],
             "expression": x[4], "effect": x[5], "enabled": bool(x[6]),
             "priority": int(x[7] or 0),
             "variables": policy_vars(x[4])} for x in r.fetchall()]


async def upsert_row_policy(data: dict) -> dict:
    object_code = (data.get("object_code") or "").strip()
    if not object_code:
        return {"ok": False, "msg": "缺少对象类型"}
    expr = (data.get("expression") or "").strip()
    if not expr:
        return {"ok": False, "msg": "策略表达式必填"}
    effect = str(data.get("effect") or "allow")
    if effect not in ONT_POLICY_EFFECTS:
        return {"ok": False, "msg": f"效果只能是 {'/'.join(ONT_POLICY_EFFECTS)}"}
    # 保存前先校验表达式能编译、且引用的都是真实属性
    try:
        ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return {"ok": False, "msg": f"策略语法错误：{e.msg}"}
    props = await _svc.list_properties(object_code)
    known = {p["code"] for p in props}
    unknown = [v for v in policy_vars(expr) if v not in known]
    if unknown:
        return {"ok": False,
                "msg": f"策略引用了不存在的属性：{'、'.join(unknown)}"}
    # 语法通过还不够：还要真跑一遍，才能拦住 user.password 这类语义错误
    try:
        eval_policy(expr, dict.fromkeys(known), ANONYMOUS)
    except PolicyError as e:
        return {"ok": False, "msg": f"策略表达式不可用：{e}"}
    params = {"oc": object_code, "n": data.get("name", ""), "d": data.get("description", ""),
              "e": expr, "ef": effect, "en": bool(data.get("enabled", True)),
              "pr": int(data.get("priority") or 0)}
    if data.get("id"):
        await _svc._exec_write(
            "UPDATE ai_ont_row_policy SET name=:n, description=:d, expression=:e, effect=:ef, "
            "enabled=:en, priority=:pr WHERE id=:id", {**params, "id": data["id"]})
        return {"ok": True, "id": data["id"], "msg": "策略已保存"}
    r = await _svc._exec_write(
        "INSERT INTO ai_ont_row_policy(object_code,name,description,expression,effect,enabled,"
        "priority) VALUES (:oc,:n,:d,:e,:ef,:en,:pr) RETURNING id", params)
    return {"ok": True, "id": r.scalar(), "msg": "策略已保存"}


async def remove_row_policy(policy_id: int) -> dict:
    await _svc._exec_write("DELETE FROM ai_ont_row_policy WHERE id=:i", {"i": int(policy_id)})
    return {"ok": True, "msg": "策略已删除"}


async def policy_properties(object_code: str) -> list[str]:
    """被启用的行策略引用到的属性（官方 policy properties）。"""
    out: set[str] = set()
    for pol in await list_row_policies(object_code):
        if pol["enabled"]:
            out.update(pol["variables"])
    return sorted(out)


async def row_allows(object_code: str, props: dict, p: Principal) -> tuple[bool, str]:
    """行级判定。

    规则：
    - 超管直接通过
    - 没有任何**启用的 allow 策略** → 通过（未配置即公开，保持既有数据行为）
    - 命中任一 deny → 拒绝
    - 有 allow 策略时，必须命中至少一条
    """
    if p.is_superuser:
        return True, "超级管理员不受行级策略限制"
    policies = [x for x in await list_row_policies(object_code) if x["enabled"]]
    if not policies:
        return True, "该对象类型未配置行级策略"
    allows = [x for x in policies if x["effect"] == "allow"]
    denies = [x for x in policies if x["effect"] == "deny"]
    for pol in denies:
        try:
            if eval_policy(pol["expression"], props, p):
                return False, f"命中拒绝策略「{pol['name'] or pol['expression']}」"
        except PolicyError as e:
            return False, f"拒绝策略求值失败（按拒绝处理）：{e}"
    if not allows:
        return True, "只有拒绝策略，且未命中"
    for pol in allows:
        try:
            if eval_policy(pol["expression"], props, p):
                return True, f"命中允许策略「{pol['name'] or pol['expression']}」"
        except PolicyError:
            continue
    return False, f"未命中任何允许策略（共 {len(allows)} 条）"


# ---------------------------------------------------------------------------
# 列级安全（属性 roles）
# ---------------------------------------------------------------------------
async def visible_properties(object_code: str, p: Principal) -> set[str]:
    """该主体能读取的属性编码集合。"""
    props = await _svc.list_properties(object_code)
    if p.is_superuser:
        return {x["code"] for x in props}
    out: set[str] = set()
    for x in props:
        roles = [str(r) for r in (x.get("roles") or [])]
        if not roles or p.has_role(*roles):
            out.add(x["code"])
    return out


async def hidden_properties(object_code: str, p: Principal) -> list[dict]:
    """该主体看不到的属性（含所需角色，供"为什么看不到"解释）。"""
    props = await _svc.list_properties(object_code)
    if p.is_superuser:
        return []
    out = []
    for x in props:
        roles = [str(r) for r in (x.get("roles") or [])]
        if roles and not p.has_role(*roles):
            out.append({"code": x["code"], "name": x.get("name"),
                        "required_roles": roles})
    return out


def mask_props(props: dict, visible: set[str]) -> dict:
    """按可见属性掩掉不可读的列。"""
    return {k: v for k, v in (props or {}).items() if k in visible}


async def mask_instance(object_code: str, props: dict, p: Principal) -> dict:
    return mask_props(props, await visible_properties(object_code, p))


# ---------------------------------------------------------------------------
# 组合判定：能不能看这条数据
# ---------------------------------------------------------------------------
async def can_read_instance(object_code: str, props: dict, p: Principal) -> tuple[bool, str]:
    """读一条对象实例：需要「资源可见」+「行策略通过」。"""
    ok_v, why_v = await can_view_resource("object", object_code, p)
    if not ok_v:
        return False, f"无权查看对象类型 {object_code}：{why_v}"
    return await row_allows(object_code, props, p)


async def filter_instances(object_code: str, rows: list[dict], p: Principal,
                           key_field: str = "key") -> dict:
    """按行策略过滤一批实例，并掩掉不可读的列。

    返回 ``{"rows": [...], "hidden_columns": [...], "dropped": n, "limited": bool}``。
    官方强调这是**读时生效**的过滤，不改变底层数据。
    """
    vis = await visible_properties(object_code, p)
    kept: list[dict] = []
    dropped = 0
    for r in rows or []:
        props = r.get("props") if isinstance(r.get("props"), dict) else r
        ok, _why = await row_allows(object_code, props or {}, p)
        if not ok:
            dropped += 1
            continue
        item = dict(r)
        if isinstance(item.get("props"), dict):
            item["props"] = mask_props(item["props"], vis)
        kept.append(item)
    hidden = [x["code"] for x in await hidden_properties(object_code, p)]
    return {"rows": kept, "hidden_columns": hidden, "dropped": dropped,
            "visible_columns": sorted(vis)}


# ---------------------------------------------------------------------------
# 动作 / 关系的编辑权限（官方明确的两条规则）
# ---------------------------------------------------------------------------
async def check_action_allowed(action: dict, p: Principal) -> tuple[bool, str]:
    """官方：*"For actions: You must hold edit permissions on the action type and on all
    ontology resource types edited by the action."*
    """
    code = action.get("code") or ""
    ok, why = await can_edit_resource("action", code, p)
    if not ok:
        return False, f"动作 {code}：{why}"
    target = action.get("object_code") or ""
    if target:
        ok2, why2 = await can_edit_resource("object", target, p)
        if not ok2:
            return False, f"动作要改的对象类型 {target}：{why2}"
    return True, "具备动作及其编辑对象类型的权限"


async def check_link_allowed(link: dict, p: Principal) -> tuple[bool, str]:
    """官方：*"For links: You must hold edit permissions on both the link type and the linked
    object types."*
    """
    code = link.get("code") or ""
    ok, why = await can_edit_resource("link", code, p)
    if not ok:
        return False, f"关系 {code}：{why}"
    for side in ("from_object", "to_object"):
        oc = link.get(side) or ""
        if not oc:
            continue
        ok2, why2 = await can_edit_resource("object", oc, p)
        if not ok2:
            return False, f"关系涉及的对象类型 {oc}：{why2}"
    return True, "具备关系及其两端对象类型的权限"


async def can_edit_property(object_code: str, property_code: str, p: Principal) -> tuple[bool, str]:
    """编辑某个属性。

    官方的三种策略里，**被权限策略引用的属性**（policy property）需要更高权限——
    因为改它等于改可见性。我们等价为：需要对象类型的 **manage** 权限。

    注意：本平台默认「未配置 ACL = 公开」，因此只有当该对象类型**确实配置了
    manage_roles** 时，这条限制才有抓手；否则仅提示加固建议（见
    ``policy_property_hardening_hint``）。
    """
    ok, why = await can_edit_resource("object", object_code, p)
    if not ok:
        return False, why
    pol_props = await policy_properties(object_code)
    if property_code in pol_props:
        acl = await get_resource_acl("object", object_code)
        if acl and acl.get("manage_roles"):
            ok_m, why_m = await can_manage_resource("object", object_code, p)
            if not ok_m:
                return False, (f"属性 {property_code} 被权限策略引用（policy property），"
                               f"修改它会影响可见性，因此需要管理权限：{why_m}")
    return True, "具备编辑权限"


async def policy_property_hardening_hint(object_code: str) -> str:
    """策略属性未被额外保护时的加固提示（官方 edit-policy-property 的等价物）。"""
    pol_props = await policy_properties(object_code)
    if not pol_props:
        return ""
    acl = await get_resource_acl("object", object_code)
    if acl and acl.get("manage_roles"):
        return ""
    return (f"属性 {'、'.join(pol_props)} 被行级策略引用，改动会影响可见性；"
            "但该对象类型尚未配置「管理角色」，因此当前任何具备编辑权限的人都能改它。"
            "建议在安全页配置管理角色以加固。")


# ---------------------------------------------------------------------------
# 权限解释（对齐官方的 Security 页 / Check access 面板）
# ---------------------------------------------------------------------------
async def explain_access(object_code: str, object_key: str | None,
                         p: Principal) -> dict:
    """解释「为什么这个人能/不能看到这个对象」。

    这是官方 *"the Security tab displays the required permissions ... the Check access panel"*
    的等价物——把判定过程摊开，而不是只给一个 true/false。
    """
    steps: list[dict] = []
    ok_v, why_v = await can_view_resource("object", object_code, p)
    steps.append({"step": "对象类型可见性", "ok": ok_v, "detail": why_v})
    if not ok_v:
        return {"allowed": False, "steps": steps, "principal": p.as_dict()}

    hidden = await hidden_properties(object_code, p)
    steps.append({"step": "列级安全（不可读属性）", "ok": True,
                  "detail": f"{len(hidden)} 个属性不可读" if hidden else "全部属性可读",
                  "hidden": hidden})

    if object_key:
        props = {}
        try:
            inst = await _svc.instance_get(object_code, str(object_key))
            if inst.get("ok"):
                props = inst.get("props") or {}
        except Exception:  # noqa: BLE001
            props = {}
        if props:
            ok_r, why_r = await row_allows(object_code, props, p)
            steps.append({"step": "行级安全", "ok": ok_r, "detail": why_r})
            pol_props = await policy_properties(object_code)
            steps.append({"step": "策略属性（编辑需管理权限）", "ok": True,
                          "detail": "、".join(pol_props) if pol_props else "无"})
            return {"allowed": ok_r, "steps": steps, "principal": p.as_dict(),
                    "visible_columns": sorted(await visible_properties(object_code, p))}
        steps.append({"step": "行级安全", "ok": False,
                      "detail": f"对象 {object_key} 不存在或无权访问"})
        return {"allowed": False, "steps": steps, "principal": p.as_dict()}

    policies = await list_row_policies(object_code)
    steps.append({"step": "行级策略", "ok": True,
                  "detail": f"{len([x for x in policies if x['enabled']])} 条启用中"
                            if policies else "未配置行级策略（全部可见）",
                  "policies": policies})
    return {"allowed": True, "steps": steps, "principal": p.as_dict(),
            "visible_columns": sorted(await visible_properties(object_code, p))}


# ---------------------------------------------------------------------------
# 策略 → SQL：把行级权限**下推**到任意查询（含聚合 / join）
#
# 为什么需要：`eval_policy` 是逐行在 Python 里求值的，只适用于点查；
# 一旦查询里有 GROUP BY / JOIN / 聚合，外面套一层 WHERE 是**错的**
# （过滤必须发生在聚合之前）。所以要把策略翻译成等价的 SQL 布尔表达式，
# 让数据库在聚合前就把不该看的行去掉。
# ---------------------------------------------------------------------------
def _sql_lit(v: Any) -> str:
    """把 Python 值安全地转成 SQL 字面量。"""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


#: 内置函数 → SQL 函数（只映射语义完全一致的；其余返回 None 走 fail-safe）
_FN_SQL = {"len": "LENGTH", "lower": "LOWER", "upper": "UPPER",
           "trim": "TRIM", "abs": "ABS", "round": "ROUND"}

_CMP_SQL = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=",
            ast.Gt: ">", ast.GtE: ">="}
_BIN_SQL = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}


def policy_to_sql(expr: str, p: Principal, cols: set[str],
                  quote: str = '"') -> str | None:
    """把一条行级策略翻译成等价 SQL 布尔表达式；**翻不了返回 None**（调用方需 fail-safe）。

    - 对象列 → SQL 列引用（``quote`` 是标识符引号，Postgres/SQLite 用 ``"``）
    - ``user.*`` → 在 Python 里求值成**常量**（每个用户一份，不随行变化）
    - 引用了表里不存在的列 → 返回 None（不猜，交给调用方兜底）
    """
    if not expr or not expr.strip():
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    user = _PolicyUser(p)

    def _user_const(node: ast.AST) -> Any:
        """把 user 相关表达式在 Python 里求值成常量。"""
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "user" \
                    and node.attr in _USER_ATTRS:
                return getattr(user, node.attr)
            raise PolicyError("只允许 user 命名空间")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and f.value.id == "user" and f.attr in ("role", "attribute"):
                if node.keywords:
                    raise PolicyError("不支持关键字参数")
                return getattr(user, f.attr)(*[_ev(a) for a in node.args])
            raise PolicyError("只允许 user 方法")
        raise PolicyError("不是 user 表达式")

    def _is_user(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id == "user") or (
            isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "user") or (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "user")

    def _has_col(node: ast.AST) -> bool:
        """表达式里是否引用了对象列（决定内置函数是"求值"还是"下推成 SQL"）。"""
        for x in ast.walk(node):
            if isinstance(x, ast.Name) and x.id != "user" and x.id in cols:
                return True
        return False

    def _ev(node: ast.AST) -> Any:
        """Python 求值（只用于 user 子表达式与内置函数）。"""
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id == "user":
                return user
            if node.id in POLICY_BUILTINS:
                raise PolicyError("函数需写成 fn(...)")
            return None
        if _is_user(node):
            return _user_const(node)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = POLICY_BUILTINS.get(node.func.id)
            if fn is None:
                raise PolicyError(f"未知函数 {node.func.id}")
            return fn(*[_ev(a) for a in node.args])
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return [_ev(x) for x in node.elts]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_ev(node.operand)
        raise PolicyError("不支持")

    def _sql(node: ast.AST) -> str:
        # user.* 与内置函数调用 → 常量
        if _is_user(node):
            return _sql_lit(_user_const(node))
        if isinstance(node, ast.Constant):
            return _sql_lit(node.value)
        if isinstance(node, ast.Name):
            if node.id not in cols:
                raise PolicyError(f"列 {node.id} 不在表里")
            return f"{quote}{node.id}{quote}"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname not in POLICY_BUILTINS:
                raise PolicyError(f"未知函数 {fname}")
            # 参数里含对象列 → 下推成 SQL 函数；全常量 → 直接求值成字面量
            if any(_has_col(a) for a in node.args):
                if fname == "contains" and len(node.args) == 2:
                    return (f"({_sql(node.args[0])} LIKE '%' || "
                            f"{_sql(node.args[1])} || '%')")
                if fname == "str" and len(node.args) == 1:
                    return f"CAST({_sql(node.args[0])} AS TEXT)"
                fn = _FN_SQL.get(fname)
                if not fn:
                    raise PolicyError(f"函数 {fname} 无法下推到 SQL")
                return f"{fn}({', '.join(_sql(a) for a in node.args)})"
            return _sql_lit(_ev(node))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_SQL:
            return f"({_sql(node.left)} {_BIN_SQL[type(node.op)]} {_sql(node.right)})"
        if isinstance(node, ast.BoolOp):
            sep = " AND " if isinstance(node.op, ast.And) else " OR "
            return "(" + sep.join(_sql(v) for v in node.values) + ")"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"(NOT {_sql(node.operand)})"
        if isinstance(node, ast.Compare):
            parts: list[str] = []
            left = node.left
            for op, right in zip(node.ops, node.comparators, strict=False):
                if type(op) in _CMP_SQL:
                    parts.append(f"{_sql(left)} {_CMP_SQL[type(op)]} {_sql(right)}")
                elif isinstance(op, (ast.In, ast.NotIn)):
                    vals = _ev(right)
                    if isinstance(vals, str):
                        vals = [vals]
                    if not isinstance(vals, (list, tuple, set)):
                        raise PolicyError("in 右侧不是可枚举值")
                    items = ", ".join(_sql_lit(x) for x in vals) or "NULL"
                    kw = "IN" if isinstance(op, ast.In) else "NOT IN"
                    parts.append(f"{_sql(left)} {kw} ({items})")
                else:
                    raise PolicyError("不支持的比较运算")
                left = right
            return "(" + " AND ".join(parts) + ")"
        raise PolicyError(f"不支持的语法：{type(node).__name__}")

    try:
        body = tree.body
        # 整条都是 user.* 常量表达式（**且不引用任何对象列**）→ 直接求值成 TRUE/FALSE。
        # 注意：必须排除含列的表达式，否则 `contains(name,'x')` 会被当成常量求值成 FALSE。
        if (_is_user(body) or (isinstance(body, ast.Call)
                               and isinstance(body.func, ast.Name))) \
                and not _has_col(body):
            return _sql_lit(bool(_ev(body)))
        return _sql(body)
    except PolicyError:
        return None
    except Exception:  # noqa: BLE001
        return None


async def row_filter_sql(object_code: str, principal: Principal,
                         cols: set[str], quote: str = '"') -> dict:
    """给一个对象类型算出「行级过滤 SQL」。

    返回 ``{"ok", "where", "mode", "reason"}``：
    - ``ok=True`` 且 ``where`` 非空 → 用它过滤
    - ``ok=True`` 且 ``where`` 为空 → 无需过滤（全部可见）
    - ``ok=False`` → **翻不了策略，调用方必须 fail-safe（拒绝或退化为键集过滤）**
    """
    if principal is not None and getattr(principal, "is_superuser", False):
        return {"ok": True, "where": "", "mode": "superuser", "reason": "超级管理员直通"}
    rows = await list_row_policies(object_code)
    enabled = [r for r in rows if r.get("enabled")]
    if not enabled:
        return {"ok": True, "where": "", "mode": "no_policy", "reason": "未配置启用的策略"}

    allows, denies = [], []
    for r in enabled:
        sql = policy_to_sql(str(r.get("expression") or ""), principal, cols, quote)
        if sql is None:
            return {"ok": False, "where": "", "mode": "untranslatable",
                    "reason": f"策略「{r.get('name') or r.get('id')}」无法翻译成 SQL，"
                              f"为安全起见不做改写"}
        (denies if r.get("effect") == "deny" else allows).append(sql)
    if not allows:
        # 只有拒绝策略：默认全可见，再排除命中的
        where = " AND ".join(f"NOT {d}" for d in denies)
        return {"ok": True, "where": where, "mode": "deny_only", "reason": "仅拒绝策略"}
    where = "(" + " OR ".join(allows) + ")"
    if denies:
        where += " AND " + " AND ".join(f"NOT {d}" for d in denies)
    return {"ok": True, "where": where, "mode": "allow",
            "reason": f"{len(allows)} 条允许 / {len(denies)} 条拒绝"}


#: 本体物化表的引用（ont_xxx）。**别名必须排除 SQL 关键字**，
#: 否则 `FROM ont_x GROUP BY ...` 会把 `GROUP` 当成别名（真实踩过）。
_SQL_KEYWORDS = {
    "group", "order", "where", "join", "left", "right", "inner", "outer", "full",
    "cross", "on", "using", "limit", "offset", "having", "union", "select", "from",
    "as", "and", "or", "not", "in", "is", "null", "case", "when", "then", "else",
    "end", "by", "asc", "desc", "with", "distinct", "all", "any", "exists", "into",
    "values", "set", "returning", "lateral", "natural", "window", "over", "partition",
}
#: 别名不能是 SQL 关键字，否则 `FROM ont_x GROUP BY ...` 会把 GROUP 当成别名
#: **并被正则吃掉**，生成 `... AS ont_x BY status` 这种坏 SQL（真实踩过）。
_KW_ALT = "|".join(sorted(_SQL_KEYWORDS))
_ALIAS = rf"(?!(?:{_KW_ALT})\b)[A-Za-z_][A-Za-z0-9_]*"
_ONT_TABLE_RE = re.compile(
    rf"\bont_([A-Za-z0-9_]+)\b(?:\s+(?:AS\s+)?({_ALIAS}))?", re.IGNORECASE)
_FROM_JOIN_RE = re.compile(
    rf"\b(FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)\b(?:\s+(?:AS\s+)?({_ALIAS}))?",
    re.IGNORECASE)


async def _table_owner_map() -> dict[str, str]:
    """真实表名 → 对象类型 code。

    注意：本体对象的支撑表**不一定**叫 ``ont_{code}``：
    由数据源支撑的对象（如 `video_cameras`）支撑表就是它自己。
    历史上问数白名单按 ``ont_{code}`` 拼、实例层按 ``backing_table`` 取，
    两套命名不一致（问数因此查不到这些对象）。这里两种都收进来。
    """
    from . import service as _svc

    out: dict[str, str] = {}
    try:
        rows = (await _svc._exec(
            "SELECT code, COALESCE(backing_table,'') FROM ai_ont_object "
            "WHERE is_deleted=false", {})).fetchall()
    except Exception:  # noqa: BLE001
        return out
    for code, bt in rows:
        if code:
            out[f"ont_{code}"] = code
        if bt:
            out[bt] = code
        elif code:
            out.setdefault(code, code)
    return out


async def secure_sql(sql: str, principal: Principal) -> dict:
    """把任意 SQL 里引用的**本体对象支撑表**改写成「已按行级/列级策略过滤的子查询」。

    这是"问数复用本体权限"的核心：问数生成的 SQL 是运行时任意形状的
    （聚合 / 分组 / join），外面套一层 WHERE 是**错的**——过滤必须发生在聚合之前。
    因此把表引用整体替换成

        (SELECT <可见列> FROM <表> WHERE <策略>) AS <别名>

    这样无论外层怎么聚合、怎么 join，受限行都已经在子查询里被去掉了。

    返回 ``{"ok", "sql", "rewritten", "denied", "note"}``；
    ``ok=False`` 表示**有策略但翻不了**，调用方必须 fail-safe（我们选择拒绝执行）。
    """
    from . import service as _svc

    if not sql:
        return {"ok": True, "sql": sql, "rewritten": [], "denied": [],
                "note": "空语句"}
    if principal is not None and getattr(principal, "is_superuser", False):
        return {"ok": True, "sql": sql, "rewritten": [], "denied": [],
                "note": "超级管理员，不做改写"}

    owner = await _table_owner_map()
    if not owner:
        return {"ok": True, "sql": sql, "rewritten": [], "denied": [],
                "note": "库里没有本体对象，无需改写"}

    quote = '"'
    rewritten: list[dict] = []
    denied: list[dict] = []
    built: dict[str, tuple[str, str]] = {}   # 表名 → (子查询, 默认别名)

    # 先扫一遍 SQL 里出现的、属于本体对象的表
    for m in _FROM_JOIN_RE.finditer(sql):
        table, raw_alias = m.group(2), m.group(3)
        code = owner.get(table) or owner.get(table.lower())
        if not code or table in built:
            continue
        meta = await _svc._instance_meta(code)
        if not meta or meta.get("error") or not meta.get("materialized"):
            continue
        cols = set(meta.get("real_cols") or set())
        rf = await row_filter_sql(code, principal, cols, quote)
        if not rf.get("ok"):
            denied.append({"table": table, "object": code, "reason": rf.get("reason")})
            continue
        where = rf.get("where") or ""
        if not where:
            continue  # 该表无需过滤
        vis = await visible_properties(code, principal)
        sel = ("*" if not vis
               else ", ".join(f"{quote}{c}{quote}" for c in sorted(vis) if c in cols))
        if not sel:
            denied.append({"table": table, "object": code, "reason": "所有列均不可见"})
            continue
        built[table] = (f'(SELECT {sel} FROM "{table}" WHERE {where})', raw_alias or table)
        rewritten.append({"table": table, "object": code, "alias": raw_alias or table,
                          "mode": rf.get("mode"), "reason": rf.get("reason"),
                          "visible_columns": len(vis) if vis else "all"})

    if denied:
        return {"ok": False, "sql": sql, "rewritten": rewritten, "denied": denied,
                "note": "存在无法安全改写的表，已拒绝执行（fail-safe）"}
    if not built:
        return {"ok": True, "sql": sql, "rewritten": [], "denied": [],
                "note": "未命中任何带策略的本体表，无需改写"}

    def _sub(mt: re.Match) -> str:
        kw, table, raw = mt.group(1), mt.group(2), mt.group(3)
        if table not in built:
            return mt.group(0)
        sub, al = built[table]
        return f"{kw} {sub} AS {raw or al}"

    return {"ok": True, "sql": re.sub(_FROM_JOIN_RE, _sub, sql),
            "rewritten": rewritten, "denied": [],
            "note": f"已改写 {len(rewritten)} 张本体表（行级/列级过滤已下推到子查询）"}
