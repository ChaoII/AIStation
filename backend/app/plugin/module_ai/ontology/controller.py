"""本体（Ontology）独立模块控制器：对象/属性/Link/Action 强类型元模型 + 物化。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from . import decision as _dec
from . import demo as _demo
from . import indexing as _ix
from . import object_view as _ov
from . import proposal as _pr
from . import scenario as _scn
from . import security as _sec
from . import service as _svc

OntologyRouter = APIRouter(route_class=OperationLogRoute, prefix="/ontology", tags=["AI-本体"])

AuthDep = Annotated[AuthSchema, Depends(AuthPermission(["module_ai:ontology:query"]))]
"""**只读**：查看本体/实例/图谱/预览/用量。GET 一律用这个。"""

AuthEdit = Annotated[AuthSchema, Depends(AuthPermission(["module_ai:ontology:edit"]))]
"""改**定义**：对象/属性/关系/动作/函数/值类型/接口/组/场景/对象视图的 save/remove、物化、
导入、工作副本、函数试跑。**不含**对真实数据的写入。"""

AuthExecute = Annotated[AuthSchema, Depends(AuthPermission(["module_ai:ontology:execute"]))]
"""对**真实数据/外部系统**动手：动作执行与试跑、实例写回、决策执行。

与 `edit` 分开的理由：能改定义 ≠ 能对生产数据落笔（写回会进业务库/触发外部系统）。"""

AuthManage = Annotated[AuthSchema, Depends(AuthPermission(["module_ai:ontology:manage"]))]
"""治理：版本发布/回滚/审批、行级安全策略与资源 ACL、分支/提案评审、索引流水线、
清理、演示数据、决策审批与结果登记。"""


def _uid(auth: AuthSchema) -> int:
    """当前用户 id（工作副本按用户隔离）。"""
    return int(getattr(getattr(auth, "user", None), "id", 0) or 0)


@OntologyRouter.get("/objects", summary="本体对象类型列表(可按本体筛选)")
async def list_objects(auth: AuthDep, domain_code: str | None = None) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_objects(domain_code, _uid(auth)), msg="查询成功")


# ---- 本体（对象类型的顶层容器）----
@OntologyRouter.get("/domains", summary="本体列表(含对象数)")
async def list_domains(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_domains(), msg="查询成功")


@OntologyRouter.post("/domain/save", summary="本体保存")
async def upsert_domain(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_domain(data)
    await _svc._log_change(str(data.get("code", "")), "domain", "save",
                           f"本体 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.delete("/domain/remove", summary="本体删除(其下对象退回未分组)")
async def remove_domain(id: int, auth: AuthEdit) -> JSONResponse:
    r = await _svc.delete_domain(int(id))
    await _svc._log_change("", "domain", "delete",
                           f"删除本体 #{id}，{r.get('moved_objects', 0)} 个对象退回未分组")
    return SuccessResponse(data=r, msg="已删除")


@OntologyRouter.post("/domain/assign", summary="把对象类型归入本体(批量)")
async def assign_domain(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.assign_objects_to_domain(
        str(data.get("domain_code", "")), data.get("object_codes") or [])
    await _svc._log_change("", "domain", "assign",
                           f"归属 {r.get('updated', 0)} 个对象 → 本体 {data.get('domain_code', '')}")
    return SuccessResponse(data=r, msg=r.get("msg") or f"已归属 {r.get('updated', 0)} 个对象")


@OntologyRouter.post("/object/save", summary="对象类型保存")
async def upsert_object(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_object(data)
    await _svc._log_change(str(data.get("code", "")), "object", "save", f"对象 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/object/{code}/full", summary="对象完整视图(属性/Link/Action)")
async def object_full(code: str, auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.object_full(code, _uid(auth)), msg="查询成功")


@OntologyRouter.get("/object/{code}/dependents", summary="对象类型的引用方(本体内部+智能体)")
async def object_dependents(code: str, auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.object_dependents(code), msg="查询成功")


@OntologyRouter.get("/properties", summary="属性类型列表")
async def list_properties(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_properties(object_code, _uid(auth)), msg="查询成功")


@OntologyRouter.post("/property/save", summary="属性类型保存")
async def upsert_property(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_property(data)
    await _svc._log_change(str(data.get("object_code", "")), "property", "save", f"属性 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/links", summary="关联类型列表")
async def list_links(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_links(object_code or None, _uid(auth)), msg="查询成功")


@OntologyRouter.post("/link/save", summary="关联类型保存")
async def upsert_link(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_link(data)
    await _svc._log_change(str(data.get("source_object", "")), "link", "save", f"关联 {data.get('name', '')} → {data.get('target_object', '')}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/actions", summary="动作类型列表")
async def list_actions(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_actions(object_code or None, _uid(auth)), msg="查询成功")


@OntologyRouter.post("/action/save", summary="动作类型保存")
async def upsert_action(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_action(data)
    await _svc._log_change(str(data.get("object_code", "")), "action", "save", f"动作 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.delete("/remove", summary="删除(对象/属性/Link/Action)")
async def remove(kind: str, id: int, auth: AuthEdit) -> JSONResponse:
    table = {"object": "ai_ont_object", "property": "ai_ont_property",
             "link": "ai_ont_link", "action": "ai_ont_action",
             "function": "ai_ont_function"}.get(kind)
    if not table:
        return SuccessResponse(data=None, msg="非法类型")
    # 删除前取对象 code（用于留痕）
    code = ""
    try:
        row = (await _svc._exec(f"SELECT object_code FROM {table} WHERE id=:id", {"id": id})).fetchone()
        if row:
            code = row[0]
    except Exception:  # noqa: BLE001
        code = ""
    await _svc.delete_one(table, id)
    await _svc._log_change(code or "", kind, "delete", f"删除 {kind} #{id}")
    return SuccessResponse(data=None, msg="已删除")


@OntologyRouter.get("/changelog", summary="本体变更留痕")
async def changelog(auth: AuthDep, object_code: str = "", limit: int = 50) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_changelog(object_code or None, limit), msg="查询成功")


@OntologyRouter.post("/version/publish", summary="发布本体对象定义版本(快照)")
async def publish_version(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    r = await _svc.publish_version(str(data.get("code", "")), operator=int(uid or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已发布"))


@OntologyRouter.get("/version/list", summary="本体对象定义版本列表")
async def version_list(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_versions(object_code or None), msg="查询成功")


@OntologyRouter.post("/version/rollback", summary="本体对象定义回滚到版本")
async def rollback_version(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.rollback_version(int(data.get("version_id", 0)))
    return SuccessResponse(data=r, msg=r.get("msg", "已回滚"))


@OntologyRouter.get("/version/diff", summary="版本对比(新增/删除/变更属性)")
async def version_diff(auth: AuthDep, version_id: int = 0) -> JSONResponse:
    return SuccessResponse(data=await _svc.version_diff(int(version_id)), msg="查询成功")


@OntologyRouter.get("/version/pending", summary="待审批的本体发布单")
async def version_pending(
    auth: AuthDep,
) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_version_pending(), msg="查询成功")


@OntologyRouter.post("/version/approve", summary="超管批准本体发布")
async def version_approve(
    auth: AuthManage,
    data: Annotated[dict, Body()],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    r = await _svc.approve_version_publish(int(data.get("pending_id", 0)), operator=int(uid or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已批准"))


@OntologyRouter.post("/materialize", summary="本体驱动表：对象+属性物化成真实表")
async def materialize(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.materialize_object(str(data.get("code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已物化"))


# ---- 大模型自动建模（两段式：预览 → 勾选 → 精确落库）----
@OntologyRouter.post("/auto-model/preview", summary="自动建模预览（生成候选，不落库）")
async def auto_model_preview(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    """大模型对指定数据源生成「绑定型指标 / 对象标注」候选，**只预览、不落库**。

    返回的 `items` 是逐条候选；界面勾选后走 `/auto-model/apply` 精确落库。
    应用阶段**不重跑大模型** —— 重跑结果会漂移，用户勾的就不是落库的那批。
    """
    from app.plugin.module_ai.query import modeling as _modeling

    scope = str(data.get("scope") or "metrics")
    datasource = str(data.get("datasource") or "system")
    max_objects = max(1, min(int(data.get("max_objects") or 12), 50))
    offset = max(0, int(data.get("offset") or 0))
    if scope == "annotations":
        r = await _modeling.generate_annotations(
            datasource, auth, max_objects=max_objects, offset=offset, dry=True
        )
    else:
        r = await _modeling.generate_metrics(
            datasource, auth, max_objects=max_objects, dry=True, offset=offset
        )
    return SuccessResponse(data={"scope": scope, **r}, msg="分析完成")


@OntologyRouter.post("/auto-model/apply", summary="自动建模落库（只落用户勾选的候选）")
async def auto_model_apply(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    """把预览里勾选的候选精确落库（指标走 `upsert_metric`；标注走定向更新，不动数据源绑定）。"""
    from app.plugin.module_ai.query import modeling as _modeling

    scope = str(data.get("scope") or "metrics")
    datasource = str(data.get("datasource") or "system")
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        raise CustomException(msg="没有可应用的候选（items 为空）", code=400, status_code=400)
    if scope == "annotations":
        r = await _modeling.save_annotations(items)
    else:
        r = await _modeling.save_metrics(items, datasource, auth)
    return SuccessResponse(data={"scope": scope, **r}, msg=f"已落库 {r.get('saved', 0)} 条")


@OntologyRouter.get("/functions", summary="本体计算函数列表")
async def list_functions(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_functions(object_code or None, _uid(auth)), msg="查询成功")


@OntologyRouter.post("/function/save", summary="本体计算函数保存")
async def upsert_function(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_function(data, _uid(auth))
    await _svc._log_change(str(data.get("object_code", "")), "function", "save", f"函数 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.post("/function/run", summary="执行本体函数(表达式/关联聚合/外部服务/模型)")
async def run_function(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _svc.run_ontology_function(
        str(data.get("code", "")),
        data.get("args") or {},
        str(data.get("object_key", "")),
        getattr(user, "id", None),
        str(getattr(user, "name", None) or ""),
    )
    return SuccessResponse(data=r, msg=r.get("msg", "执行完成"))


@OntologyRouter.post("/function/check", summary="校验函数定义（不保存）")
async def check_function(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    errs = _svc._fe.validate_function(data or {})
    return SuccessResponse(data={"ok": not errs, "errors": errs},
                           msg="定义正确" if not errs else f"发现 {len(errs)} 处问题")


@OntologyRouter.get("/function/builtins", summary="可用的内置函数清单")
async def function_builtins(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=sorted(_svc._fe.BUILTINS), msg="查询成功")


# ---------------------------------------------------------------------------
# P4：对象权限（资源 ACL + 行策略 + 列级角色 + 权限解释）
# ---------------------------------------------------------------------------
@OntologyRouter.get("/security/row-policies", summary="行级安全策略列表")
async def list_row_policies(auth: AuthDep, object_code: str = "") -> JSONResponse:
    if not object_code:
        raise CustomException(msg="缺少 object_code")
    return SuccessResponse(data=await _sec.list_row_policies(object_code), msg="查询成功")


@OntologyRouter.post("/security/row-policy/save", summary="保存行级安全策略")
async def save_row_policy(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _sec.upsert_row_policy(data or {})
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg", "保存失败"))
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/security/row-policy/remove", summary="删除行级安全策略")
async def remove_row_policy(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _sec.remove_row_policy(int(data.get("id") or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.post("/security/policy-check", summary="校验策略表达式（不保存）")
async def check_policy(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    import ast as _ast

    expr = str(data.get("expression") or "").strip()
    if not expr:
        raise CustomException(msg="表达式为空")
    try:
        _ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise CustomException(msg=f"语法错误：{e.msg}") from e
    variables = _sec.policy_vars(expr)
    object_code = str(data.get("object_code") or "")
    unknown: list[str] = []
    if object_code:
        known = {p["code"] for p in await _svc.list_properties(object_code)}
        unknown = [v for v in variables if v not in known]
    return SuccessResponse(
        data={"ok": not unknown, "variables": variables, "unknown": unknown,
              "msg": "表达式可用" if not unknown else f"引用了不存在的属性：{'、'.join(unknown)}"},
        msg="校验完成")


@OntologyRouter.get("/security/resource-acl", summary="本体资源的权限（view/edit/manage 角色）")
async def get_resource_acl(auth: AuthDep, resource_kind: str = "",
                           resource_code: str = "") -> JSONResponse:
    if not resource_kind or not resource_code:
        raise CustomException(msg="缺少 resource_kind / resource_code")
    acl = await _sec.get_resource_acl(resource_kind, resource_code)
    return SuccessResponse(
        data=acl or {"view_roles": [], "edit_roles": [], "manage_roles": [],
                     "inherited": True},
        msg="查询成功")


@OntologyRouter.post("/security/resource-acl/save", summary="保存本体资源权限")
async def save_resource_acl(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _sec.set_resource_acl(
        str(data.get("resource_kind", "")), str(data.get("resource_code", "")),
        data.get("view_roles") or [], data.get("edit_roles") or [],
        data.get("manage_roles") or [])
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg", "保存失败"))
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/security/resource-acl/clear", summary="清除资源权限（恢复公开）")
async def clear_resource_acl(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _sec.clear_resource_acl(str(data.get("resource_kind", "")),
                                      str(data.get("resource_code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已恢复"))


@OntologyRouter.get("/security/overview", summary="对象类型的安全概览（Security 标签页）")
async def security_overview(auth: AuthDep, object_code: str = "") -> JSONResponse:
    if not object_code:
        raise CustomException(msg="缺少 object_code")
    rows = await _svc.list_objects(None)
    obj = next((o for o in rows if o.get("code") == object_code), None)
    props = await _svc.list_properties(object_code)
    col_restricted = [
        {"code": p["code"], "name": p.get("name"), "roles": p.get("roles") or []}
        for p in props if p.get("roles")
    ]
    return SuccessResponse(data={
        "object_code": object_code,
        "object_name": (obj or {}).get("name"),
        "acl": await _sec.get_resource_acl("object", object_code) or {
            "view_roles": [], "edit_roles": [], "manage_roles": [], "inherited": True},
        "row_policies": await _sec.list_row_policies(object_code),
        "policy_properties": await _sec.policy_properties(object_code),
        "column_restricted": col_restricted,
        "column_total": len(props),
        "policy_expression_hint": "如 dept_id == user.attribute('dept') 或 user.role('ADMIN')",
        "hardening_hint": await _sec.policy_property_hardening_hint(object_code),
    }, msg="查询成功")


@OntologyRouter.get("/security/explain", summary="解释某人能否看到某对象（Check access）")
async def explain_access(auth: AuthDep, object_code: str = "", object_key: str = "",
                         user_id: int = 0) -> JSONResponse:
    """不传 user_id 时用当前登录者；传了则代查（等价官方的 Check access 面板）。"""
    target = int(user_id or 0) or _uid(auth)
    p = await _sec.load_principal(target)
    r = await _sec.explain_access(object_code, object_key or None, p)
    return SuccessResponse(data=r, msg="查询成功")


@OntologyRouter.post("/security/enforce-preview", summary="预览某用户对某对象的读权限与可见列")
async def enforce_preview(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    target = int(data.get("user_id") or 0) or _uid(auth)
    p = await _sec.load_principal(target)
    object_code = str(data.get("object_code", ""))
    if not object_code:
        raise CustomException(msg="缺少 object_code")
    return SuccessResponse(data={
        "principal": p.as_dict(),
        "visible_columns": sorted(await _sec.visible_properties(object_code, p)),
        "hidden_columns": await _sec.hidden_properties(object_code, p),
        "policy_filtered": bool([x for x in await _sec.list_row_policies(object_code)
                                 if x["enabled"]]),
    }, msg="查询成功")


@OntologyRouter.get("/security/resource-kinds", summary="本体资源种类枚举")
async def security_resource_kinds(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=[{"value": k, "label": _sec.ONT_RESOURCE_LABEL.get(k, k)}
                                 for k in _sec.ONT_RESOURCE_KINDS], msg="查询成功")


@OntologyRouter.get("/security/subjects", summary="可选主体（角色/用户），供权限配置下拉用")
async def security_subjects(auth: AuthDep) -> JSONResponse:
    roles = [{"code": r[1], "name": r[0]} for r in
             (await _svc._exec("SELECT name, code FROM sys_role WHERE is_deleted=false "
                               "ORDER BY id", {})).fetchall() if r[1]]
    users = [{"id": r[0], "name": r[1] or r[2], "username": r[2]} for r in
             (await _svc._exec("SELECT id, name, COALESCE(username,'') FROM sys_user "
                               "WHERE is_deleted=false ORDER BY id", {})).fetchall()]
    return SuccessResponse(data={"roles": roles, "users": users}, msg="查询成功")


# ---------------------------------------------------------------------------
# P3：决策数据 + 决策谱系
# ---------------------------------------------------------------------------
@OntologyRouter.get("/decisions", summary="决策列表")
async def list_decisions(auth: AuthDep, status: str = "", object_code: str = "",
                         made_by: str = "", category: str = "", keyword: str = "",
                         limit: int = 200) -> JSONResponse:
    data = await _dec.list_decisions(status or None, object_code or None,
                                     made_by or None, category or None,
                                     keyword or None, limit)
    return SuccessResponse(data=data, msg="查询成功")


@OntologyRouter.get("/decision/{code}", summary="决策详情（含选项/依据/影响）")
async def get_decision(auth: AuthDep, code: str) -> JSONResponse:
    d = await _dec.get_decision(code)
    if not d:
        raise CustomException(msg="决策不存在")
    return SuccessResponse(data=d, msg="查询成功")


@OntologyRouter.post("/decision/save", summary="新建/修改决策")
async def save_decision(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _dec.upsert_decision(data, _uid(auth),
                                   str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/decision/remove", summary="删除决策")
async def remove_decision(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _dec.remove_decision(str(data.get("code", "")), _uid(auth))
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.post("/decision/decide", summary="拍板（批准/否决）")
async def decide_decision(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _dec.decide(str(data.get("code", "")), bool(data.get("approve", True)),
                          str(data.get("note", "")), _uid(auth),
                          str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/decision/execute", summary="执行决策（走动作七道闸并自动捕获下游影响）")
async def execute_decision(auth: AuthExecute, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _dec.execute_decision(str(data.get("code", "")), _uid(auth),
                                    str(getattr(user, "name", None) or ""),
                                    bool(data.get("approve", False)),
                                    principal=await _sec.load_principal(_uid(auth)))
    return SuccessResponse(data=r, msg=r.get("msg", "已执行"))


@OntologyRouter.post("/decision/outcome", summary="记录决策的事后结果")
async def decision_outcome(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _dec.record_outcome(str(data.get("code", "")), data.get("outcome") or {},
                                  str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已记录"))


@OntologyRouter.get("/decision-lineage/{code}", summary="决策谱系（上游依据 + 下游影响，可递归）")
async def decision_lineage(auth: AuthDep, code: str, depth: int = 3) -> JSONResponse:
    r = await _dec.decision_lineage(code, depth)
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg", "查询失败"))
    return SuccessResponse(data=r, msg="查询成功")


@OntologyRouter.get("/decision-graph", summary="决策谱系图（节点/边）")
async def decision_graph(auth: AuthDep, status: str = "", limit: int = 60) -> JSONResponse:
    return SuccessResponse(data=await _dec.decision_graph(status or None, limit),
                           msg="查询成功")


@OntologyRouter.get("/decision-stats", summary="决策统计")
async def decision_stats(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _dec.decision_stats(), msg="查询成功")


@OntologyRouter.post("/decision/init-object-type", summary="把「决策」注册为本体对象类型")
async def init_decision_object_type(auth: AuthEdit) -> JSONResponse:
    r = await _dec.ensure_decision_object_type()
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.get("/capabilities", summary="本体能力列表")
async def list_capabilities(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_capabilities(), msg="查询成功")


@OntologyRouter.post("/capability/save", summary="本体能力保存")
async def upsert_capability(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_capability(data)
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/analyze", summary="本体深度建模分析")
async def analyze_ontology(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.analyze_ontology(), msg="查询成功")


@OntologyRouter.post("/enrich", summary="业务语义回填(注释→业务名/枚举, 真实外键→Link)")
async def enrich_semantics(auth: AuthEdit) -> JSONResponse:
    r = await _svc.enrich_ontology_semantics()
    if not r.get("ok"):
        return SuccessResponse(data=r, msg=r.get("msg", "回填失败"))
    o, p, lk = r["objects"], r["properties"], r["links"]
    await _svc._log_change("", "ontology", "enrich",
                           f"回填：对象命名 {o['renamed']}，属性 {p['described']}"
                           f"（枚举 {p['enum_parsed']}），关系 {lk['created']}")
    return SuccessResponse(
        data=r,
        msg=(f"已回填：对象命名 {o['renamed']}/{o['total']}，属性 {p['described']} 条"
             f"（其中枚举 {p['enum_parsed']}），新增关系 {lk['created']} 条"))


@OntologyRouter.post("/seed-examples", summary="写入本体示例能力(函数+对象动作)")
async def seed_examples(auth: AuthEdit) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    r = await _svc.seed_ontology_examples(operator=int(uid or 0))
    fn, ac = r["functions"], r["actions"]
    return SuccessResponse(
        data=r,
        msg=(f"示例能力已就绪：函数 +{len(fn['added'])}、动作 +{len(ac['added'])}"
             f"（已存在的跳过：函数 {len(fn['skipped'])}、动作 {len(ac['skipped'])}）"
             f"，关系名规整 {r['links_renamed']} 条"))


@OntologyRouter.post("/action/execute", summary="执行本体动作(提交条件+值类型+白名单+审批门禁+规则+副作用)")
async def execute_ontology_action(auth: AuthExecute, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    operator = str(getattr(user, "name", None) or getattr(user, "id", None) or "")
    uid = getattr(user, "id", None)
    r = await _svc.execute_ontology_action(
        code=str(data.get("code", "")),
        object_key=str(data.get("object_key", "")),
        params=data.get("params") or {},
        operator=operator,
        # P0-2：**不接受**请求体里的 approve。原先直接取 data["approve"]，
        # 任何持 execute 权限的人在 body 里带 approve=true 就能自我批准，
        # 审批门禁形同虚设（且不产生 pending 单、事后无痕迹）。
        # 需审批的动作一律落待审批单，由管理员走 /action/approve 批准。
        approve=False,
        user_id=uid,
        # P4：按调用者权限门控（少了这一句，权限在 HTTP 路径上就是不生效的）
        principal=await _sec.load_principal(uid),
        # P5：在场景内执行则只暂存、不写真实表
        scenario_code=str(data.get("scenario", "")),
    )
    return SuccessResponse(data=r, msg=r.get("msg", "已执行"))


@OntologyRouter.post("/action/approve", summary="批准待审批的本体动作（P0-2 修复后唯一批准入口）")
async def approve_ontology_action(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    """管理员批准一条待审批的本体动作：读回待审批单里的执行载荷，原样回放执行。

    待审批单由 ``/action/execute`` 生成（``ai_query_writeback_log.result='pending'``）。
    ``approve`` 参数**只能**从这里传入（AuthManage），不能由执行入口的请求体携带。
    """
    user = getattr(auth, "user", None)
    operator = str(getattr(user, "name", None) or getattr(user, "id", None) or "")
    uid = getattr(user, "id", None)
    r = await _svc.approve_pending_action(
        int(data.get("approval_id", 0)), operator=operator, user_id=uid,
        principal=await _sec.load_principal(uid))
    return SuccessResponse(data=r, msg=r.get("msg", "已批准"))


@OntologyRouter.post("/action/test-run", summary="试运行本体动作（评估提交条件/规则/副作用，不写库）")
async def test_run_action(auth: AuthExecute, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _svc.plan_ontology_action(
        str(data.get("code", "")),
        str(data.get("object_key", "")),
        data.get("params") or {},
        getattr(user, "id", None),
        str(getattr(user, "name", None) or ""),
    )
    return SuccessResponse(data=r, msg="试运行完成（未写入任何数据）")


# ---- 工作副本（改动先入草稿，Save 才落库）----
@OntologyRouter.get("/wip", summary="工作副本：改动清单 + 审核结果")
async def list_wip(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.review_wip(_uid(auth)), msg="查询成功")


@OntologyRouter.post("/wip/stage", summary="工作副本：暂存一条改动")
async def stage_wip(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.stage_change(
        _uid(auth),
        str(data.get("kind", "")),
        str(data.get("action", "update")),
        data.get("data") or {},
        str(data.get("target_key") or ""),
    )
    return SuccessResponse(data=r, msg="已暂存（尚未落库）")


@OntologyRouter.post("/wip/discard", summary="工作副本：丢弃全部改动")
async def discard_wip(auth: AuthEdit) -> JSONResponse:
    n = await _svc.discard_wip(_uid(auth))
    return SuccessResponse(data={"discarded": n}, msg=f"已丢弃 {n} 处改动")


@OntologyRouter.post("/wip/save", summary="工作副本：保存全部改动（含错误/破坏性校验）")
async def save_wip(auth: AuthEdit, data: Annotated[dict, Body()] = None) -> JSONResponse:
    r = await _svc.save_wip(_uid(auth), str((data or {}).get("confirm_name") or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/wip/restore/{version_id}", summary="工作副本：把恢复历史版本暂存为改动")
async def stage_restore(version_id: int, auth: AuthEdit) -> JSONResponse:
    # 必须是 **POST**：它**有副作用**（往工作副本里暂存一条改动）。原先声明成 GET 有两个后果：
    # ① 前端按 POST 调 → 405（「恢复」按钮点了必失败）；② GET 只要求只读权限 ⇒
    # 只读用户也能暂存改动（越权写入）。
    vs = await _svc.list_versions()
    v = next((x for x in vs if x["id"] == version_id), None)
    if not v:
        return SuccessResponse(data={"ok": False}, msg="版本不存在")
    r = await _svc.stage_change(
        _uid(auth), "object", "restore",
        {"code": v["object_code"], "version": v["version"], "version_id": version_id},
        target_key=f"{v['object_code']}@restore",
    )
    return SuccessResponse(data=r, msg=f"已把「恢复到 v{v['version']}」暂存，点保存后生效")


# ---- 导入 / 导出 ----
@OntologyRouter.get("/export", summary="导出本体定义为 JSON")
async def export_ontology(auth: AuthDep, domain_code: str | None = None) -> JSONResponse:
    return SuccessResponse(data=await _svc.export_ontology(domain_code), msg="导出成功")


@OntologyRouter.post("/import", summary="导入本体定义（默认入工作副本）")
async def import_ontology(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    payload = data.get("payload") or {}
    mode = str(data.get("mode") or "stage")
    r = await _svc.import_ontology(payload, _uid(auth), mode)
    return SuccessResponse(
        data=r,
        msg=(f"已导入并暂存 {r.get('staged', 0)} 项，点保存后生效"
             if mode != "apply" else f"已直接导入 {r.get('applied', 0)} 项"))


# ---- 用量 / 清理 ----
@OntologyRouter.get("/usage", summary="本体用量（读数/写入/交互）")
async def ontology_usage(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.ontology_usage(object_code or None), msg="查询成功")


@OntologyRouter.get("/cleanup", summary="清理建议（弃用/删除候选）")
async def cleanup(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.cleanup_suggestions(), msg="查询成功")


# ---- 实例层（Object Explorer / Vertex / Object Views）----
# P4：读路径都要带调用者主体，按行策略过滤 + 按属性角色掩列
async def _principal(auth) -> "_sec.Principal":
    return await _sec.load_principal(_uid(auth))


@OntologyRouter.get("/instances/{code}", summary="实例搜索：真实数据行")
async def instance_search(
    code: str, auth: AuthDep, keyword: str = "", limit: int = 50, offset: int = 0,
    filters: str = "", scenario: str = "",
) -> JSONResponse:
    import json as _json

    try:
        flt = _json.loads(filters) if filters else {}
    except Exception:  # noqa: BLE001
        flt = {}
    return SuccessResponse(
        data=await _svc.instance_search(code, keyword, flt, limit, offset,
                                        principal=await _principal(auth),
                                        scenario_code=scenario),
        msg="查询成功")


@OntologyRouter.get("/instance/{code}/{key}", summary="单个实例：属性+关系+动作")
async def instance_get(code: str, key: str, auth: AuthDep,
                       scenario: str = "") -> JSONResponse:
    return SuccessResponse(
        data=await _svc.instance_get(code, key, principal=await _principal(auth),
                                     scenario_code=scenario),
        msg="查询成功")


@OntologyRouter.get("/instance/{code}/{key}/pivot", summary="沿关系跳转到关联实例")
async def instance_pivot(
    code: str, key: str, auth: AuthDep, link_id: int = 0, limit: int = 50
) -> JSONResponse:
    if not link_id:
        return SuccessResponse(data={"ok": False, "msg": "缺少 link_id", "items": []}, msg="参数缺失")
    return SuccessResponse(
        data=await _svc.instance_pivot(code, key, link_id, limit,
                                       principal=await _principal(auth)),
        msg="查询成功")


@OntologyRouter.post("/instance/graph", summary="实例层图（Search Around 多步扩展）")
async def instance_graph(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.instance_graph(
        str(data.get("object_code", "")),
        str(data.get("key", "")),
        data.get("link_ids") or None,
        int(data.get("depth") or 1),
        int(data.get("limit") or 120),
        principal=await _principal(auth),
    )
    return SuccessResponse(data=r, msg=r.get("msg", "查询成功"))


@OntologyRouter.post("/instance/writeback", summary="属性写回（Writeback，需开启可编辑）")
async def instance_writeback(auth: AuthExecute, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    operator = str(getattr(user, "name", None) or getattr(user, "id", None) or "")
    r = await _svc.writeback_instance(
        str(data.get("object_code", "")), str(data.get("key", "")),
        data.get("props") or {}, operator, principal=await _principal(auth))
    return SuccessResponse(data=r, msg=r.get("msg", "已写回"))


# ---- P5：对象类型组 ----
@OntologyRouter.get("/groups", summary="对象类型组列表")
async def list_groups(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_groups(), msg="查询成功")


@OntologyRouter.post("/group/save", summary="对象类型组保存（含成员）")
async def save_group(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    return SuccessResponse(data=await _svc.upsert_group(data), msg="已保存")


@OntologyRouter.delete("/group/remove", summary="删除对象类型组")
async def remove_group(auth: AuthEdit, id: int) -> JSONResponse:
    await _svc.delete_group(id)
    return SuccessResponse(data=None, msg="已删除")


# ---- P5：值类型 ----
@OntologyRouter.get("/value-types", summary="值类型列表（含引用数）")
async def list_value_types(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_value_types(), msg="查询成功")


@OntologyRouter.post("/value-type/save", summary="值类型保存")
async def save_value_type(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    return SuccessResponse(data=await _svc.upsert_value_type(data, _uid(auth)), msg="已保存")


@OntologyRouter.delete("/value-type/remove", summary="删除值类型（有引用则拒绝）")
async def remove_value_type(auth: AuthEdit, id: int) -> JSONResponse:
    r = await _svc.delete_value_type(id, _uid(auth))
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.post("/value-type/validate", summary="按值类型约束校验一个值")
async def validate_value(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.validate_value(str(data.get("code", "")), data.get("value"))
    return SuccessResponse(data=r, msg="校验完成" if r.get("ok") else "校验未通过")


# ---- P5：共享属性 ----
@OntologyRouter.get("/shared-properties", summary="共享属性列表（含引用数）")
async def list_shared_properties(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_shared_properties(), msg="查询成功")


@OntologyRouter.post("/shared-property/save", summary="共享属性保存（同步元数据到引用方）")
async def save_shared_property(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    return SuccessResponse(data=await _svc.upsert_shared_property(data, _uid(auth)), msg="已保存")


@OntologyRouter.delete("/shared-property/remove", summary="删除共享属性（有引用则拒绝）")
async def remove_shared_property(auth: AuthEdit, id: int) -> JSONResponse:
    r = await _svc.delete_shared_property(id)
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


# ---- P5：接口 ----
@OntologyRouter.get("/interfaces", summary="接口列表（含实现者）")
async def list_interfaces(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_interfaces(), msg="查询成功")


@OntologyRouter.post("/interface/save", summary="接口保存")
async def save_interface(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    return SuccessResponse(data=await _svc.upsert_interface(data), msg="已保存")


@OntologyRouter.delete("/interface/remove", summary="删除接口（有实现者则拒绝）")
async def remove_interface(auth: AuthEdit, id: int) -> JSONResponse:
    r = await _svc.delete_interface(id)
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.post("/interface/impls", summary="设置接口实现者（不满足约束会被拒绝）")
async def set_interface_impls(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.set_interface_impls(
        str(data.get("code", "")), data.get("object_codes") or [])
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.get("/interface/check", summary="接口实现合规检查")
async def check_interface(auth: AuthDep, code: str = "", object_code: str = "") -> JSONResponse:
    if code and object_code:
        return SuccessResponse(data=await _svc.check_interface_impl(code, object_code), msg="检查完成")
    return SuccessResponse(data=await _svc.check_all_interface_impls(), msg="检查完成")


# ---- P5：派生属性 ----
@OntologyRouter.get("/derived/issues", summary="派生属性配置问题扫描")
async def derived_issues(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.derived_issues(), msg="查询成功")


@OntologyRouter.post("/derived/compute", summary="计算派生属性的值")
async def compute_derived(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.compute_derived(
        str(data.get("object_code", "")), str(data.get("key", "")),
        str(data.get("property", "")), data.get("limit"))
    return SuccessResponse(data=r, msg=r.get("msg", "已计算"))


# ---- P5：通用引用检查 ----
@OntologyRouter.get("/references", summary="引用检查（删除前看谁在用）")
async def references(auth: AuthDep, kind: str, code: str) -> JSONResponse:
    return SuccessResponse(data=await _svc.reference_check(kind, code), msg="查询成功")


# ---------------------------------------------------------------------------
# P5：场景（沙箱式 what-if；差异叠加、可对比、可单事务合并）
# ---------------------------------------------------------------------------
@OntologyRouter.get("/scenarios", summary="场景列表")
async def list_scenarios(auth: AuthDep, status: str = "", limit: int = 200) -> JSONResponse:
    return SuccessResponse(data=await _scn.list_scenarios(status or None, limit),
                           msg="查询成功")


@OntologyRouter.get("/scenario/{code}", summary="场景详情（含编辑与差异）")
async def get_scenario(auth: AuthDep, code: str) -> JSONResponse:
    s = await _scn.get_scenario(code)
    if not s:
        raise CustomException(msg="场景不存在")
    return SuccessResponse(data=s, msg="查询成功")


@OntologyRouter.post("/scenario/save", summary="新建/修改场景")
async def save_scenario(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    who = str(getattr(user, "name", None) or "")
    if data.get("code"):
        r = await _scn.update_scenario(str(data["code"]), data)
    else:
        r = await _scn.create_scenario(data, who)
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/scenario/apply", summary="合并场景到主本体（单事务，失败全回滚）")
async def apply_scenario(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _scn.apply_scenario(str(data.get("code", "")), _uid(auth),
                                  str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/scenario/discard", summary="丢弃场景")
async def discard_scenario(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _scn.discard_scenario(str(data.get("code", "")),
                                    str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/scenario/duplicate", summary="复制场景（连同其编辑）")
async def duplicate_scenario(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _scn.duplicate_scenario(str(data.get("code", "")),
                                      str(data.get("name", "")),
                                      str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/scenario/remove", summary="删除场景")
async def remove_scenario(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _scn.remove_scenario(str(data.get("code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.get("/scenario/{code}/diff", summary="场景相对基线的差异")
async def scenario_diff(auth: AuthDep, code: str) -> JSONResponse:
    r = await _scn.scenario_diff(code)
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg", "查询失败"))
    return SuccessResponse(data=r, msg="查询成功")


@OntologyRouter.post("/scenario/compare", summary="多场景并排对比")
async def compare_scenarios(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _scn.compare_scenarios(data.get("codes") or [])
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg", "对比失败"))
    return SuccessResponse(data=r, msg=r.get("msg", "对比完成"))


@OntologyRouter.post("/scenario/expire", summary="清理过期场景（官方默认寿命 31 天）")
async def expire_scenarios(auth: AuthEdit) -> JSONResponse:
    r = await _scn.expire_scenarios()
    return SuccessResponse(data=r, msg=r.get("msg", "已清理"))


# ---------------------------------------------------------------------------
# A) 对象视图（对齐官方 object-views）
# ---------------------------------------------------------------------------
@OntologyRouter.get("/object-views", summary="对象视图列表")
async def list_object_views(auth: AuthDep, object_code: str = "",
                            form_factor: str = "") -> JSONResponse:
    return SuccessResponse(data=await _ov.list_views(object_code or None, form_factor),
                           msg="查询成功")


@OntologyRouter.get("/object-view/{code}", summary="对象视图详情（含版本）")
async def get_object_view(auth: AuthDep, code: str) -> JSONResponse:
    v = await _ov.get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    return SuccessResponse(data=v, msg="查询成功")


@OntologyRouter.get("/object-view/standard/{object_code}", summary="标准视图（自动生成）")
async def standard_object_view(auth: AuthDep, object_code: str,
                               form_factor: str = "full") -> JSONResponse:
    return SuccessResponse(data=await _ov.standard_view(object_code, form_factor),
                           msg="查询成功")


@OntologyRouter.get("/object-view/render/{code}/{object_key}", summary="按视图渲染某个对象")
async def render_object_view(auth: AuthDep, code: str, object_key: str,
                             scenario: str = "") -> JSONResponse:
    r = await _ov.render_view(code, object_key, principal=await _principal(auth),
                              scenario_code=scenario)
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg", "渲染失败"))
    return SuccessResponse(data=r, msg="查询成功")


@OntologyRouter.post("/object-view/save", summary="新建/修改对象视图")
async def save_object_view(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    who = str(getattr(user, "name", None) or "")
    if data.get("code") and data.get("_mode") != "create":
        exist = await _ov.get_view(str(data["code"]))
        if exist:
            r = await _ov.update_view(str(data["code"]), data, who)
            return SuccessResponse(data=r, msg=r.get("msg", "已保存"))
    r = await _ov.create_view(data, who)
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/object-view/default", summary="设为默认视图")
async def set_default_object_view(auth: AuthEdit,
                                  data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ov.set_default_view(str(data.get("code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已设置"))


@OntologyRouter.post("/object-view/remove", summary="删除对象视图")
async def remove_object_view(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ov.remove_view(str(data.get("code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.get("/object-view/{code}/versions", summary="视图版本历史")
async def object_view_versions(auth: AuthDep, code: str) -> JSONResponse:
    return SuccessResponse(data=await _ov.list_view_versions(code), msg="查询成功")


@OntologyRouter.post("/object-view/restore", summary="回滚到某个视图版本")
async def restore_object_view(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _ov.restore_view_version(str(data.get("code", "")),
                                       int(data.get("version") or 0),
                                       str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已回滚"))


@OntologyRouter.post("/object-view/sync-defaults", summary="给所有对象类型补齐默认视图")
async def sync_default_object_views(auth: AuthEdit) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _ov.sync_default_views(str(getattr(user, "name", None) or "system"))
    return SuccessResponse(data=r, msg=r.get("msg", "已补齐"))


@OntologyRouter.get("/object-view-meta", summary="视图 widget 类型元数据")
async def object_view_meta(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data={
        "form_factors": [{"value": k, "label": _ov.ONT_FORM_FACTOR_LABEL[k]}
                         for k in _ov.ONT_FORM_FACTORS],
        "widgets": [{"value": t, "label": _ov.ONT_WIDGET_LABEL[t],
                     "category": _ov.ONT_WIDGET_CATEGORY.get(t, "layout"),
                     "category_label": _ov.ONT_WIDGET_CATEGORY_LABEL.get(
                         _ov.ONT_WIDGET_CATEGORY.get(t, "layout"), "布局")}
                    for t in _ov.ONT_WIDGET_TYPES],
        "categories": [{"value": k, "label": v}
                       for k, v in _ov.ONT_WIDGET_CATEGORY_LABEL.items()],
        "max_tabs": _ov.MAX_TABS, "max_widgets": _ov.MAX_WIDGETS_PER_TAB,
    }, msg="查询成功")


# ---------------------------------------------------------------------------
# B) 索引（对齐官方 object-indexing）
# ---------------------------------------------------------------------------
@OntologyRouter.get("/indexes", summary="索引列表")
async def list_indexes(auth: AuthDep, object_code: str = "",
                       status: str = "") -> JSONResponse:
    return SuccessResponse(data=await _ix.list_indexes(object_code or None, status),
                           msg="查询成功")


@OntologyRouter.get("/index/summary", summary="索引总览")
async def index_summary(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _ix.index_summary(), msg="查询成功")


@OntologyRouter.post("/index/save", summary="新建/修改索引定义")
async def save_index(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ix.upsert_index(data)
    return SuccessResponse(data=r, msg=r.get("msg", "已保存"))


@OntologyRouter.post("/index/build", summary="构建索引（真的建库索引）")
async def build_index(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ix.build_index(int(data.get("id") or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/index/build-all", summary="构建某对象类型/全部的待建索引")
async def build_all_indexes(auth: AuthManage,
                            data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ix.build_all(str(data.get("object_code") or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/index/retry", summary="执行到期的自动重试")
async def retry_indexes(auth: AuthManage) -> JSONResponse:
    r = await _ix.retry_due_indexes()
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/index/remove", summary="删除索引")
async def remove_index(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ix.remove_index(int(data.get("id") or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已删除"))


@OntologyRouter.post("/index/mark-stale", summary="把某对象类型的索引标记为过期")
async def mark_index_stale(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ix.mark_stale(str(data.get("object_code") or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.get("/index/suggest/{object_code}", summary="索引建议")
async def suggest_indexes(auth: AuthDep, object_code: str) -> JSONResponse:
    return SuccessResponse(data=await _ix.suggest_indexes(object_code), msg="查询成功")


@OntologyRouter.post("/index/apply-suggestions", summary="按建议批量建索引并构建")
async def apply_index_suggestions(auth: AuthManage,
                                  data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ix.apply_suggestions(str(data.get("object_code") or ""),
                                    bool(data.get("only_high", True)))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


# ---------------------------------------------------------------------------
# C) 分支 / 提案（对齐官方 ontologies-proposals）
# ---------------------------------------------------------------------------
@OntologyRouter.get("/branches", summary="分支列表")
async def list_branches(auth: AuthDep, status: str = "") -> JSONResponse:
    return SuccessResponse(data=await _pr.list_branches(status), msg="查询成功")


@OntologyRouter.get("/branch/{code}", summary="分支详情（含改动与提案）")
async def get_branch(auth: AuthDep, code: str) -> JSONResponse:
    b = await _pr.get_branch(code)
    if not b:
        raise CustomException(msg="分支不存在")
    return SuccessResponse(data=b, msg="查询成功")


@OntologyRouter.post("/branch/create", summary="创建分支（自动生成提案）")
async def create_branch(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.create_branch(str(data.get("title") or ""),
                                str(data.get("description") or ""),
                                str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已创建"))


@OntologyRouter.post("/branch/save", summary="在分支上暂存一处定义改动")
async def save_on_branch(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.save_on_branch(str(data.get("branch_code") or ""),
                                 str(data.get("kind") or ""),
                                 str(data.get("action") or "update"),
                                 data.get("data") or {},
                                 str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已暂存"))


@OntologyRouter.get("/proposals", summary="提案列表（按官方标签页过滤）")
async def list_proposals(auth: AuthDep, tab: str = "") -> JSONResponse:
    user = getattr(auth, "user", None)
    who = str(getattr(user, "name", None) or "")
    return SuccessResponse(data={"items": await _pr.list_proposals(tab, who),
                                 "tabs": [{"value": t, "label": _pr.ONT_PROPOSAL_TAB_LABEL[t]}
                                          for t in _pr.ONT_PROPOSAL_TABS],
                                 "stages": [{"value": s, "label": _pr.ONT_PROPOSAL_STAGE_LABEL[s]}
                                            for s in _pr.ONT_PROPOSAL_STAGES]},
                           msg="查询成功")


@OntologyRouter.get("/proposal/{code}", summary="提案详情（任务/评论/变更记录）")
async def get_proposal(auth: AuthDep, code: str) -> JSONResponse:
    p = await _pr.get_proposal(code)
    if not p:
        raise CustomException(msg="提案不存在")
    return SuccessResponse(data=p, msg="查询成功")


@OntologyRouter.post("/proposal/request-review", summary="请求审查（通知审查者）")
async def request_review(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.request_review(str(data.get("code") or ""),
                                 data.get("reviewers") or [],
                                 str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已请求"))


@OntologyRouter.post("/proposal/review-task", summary="批准/拒绝一个任务")
async def review_task(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.review_task(int(data.get("task_id") or 0),
                              bool(data.get("approve", True)),
                              str(getattr(user, "name", None) or ""),
                              str(data.get("note") or ""), _uid(auth))
    if not r.get("ok"):
        return SuccessResponse(data=r, msg=r.get("msg", "未通过"))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/proposal/review-all", summary="批量批准/拒绝所有待审任务")
async def review_all(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.review_all(str(data.get("code") or ""),
                             bool(data.get("approve", True)),
                             str(getattr(user, "name", None) or ""), _uid(auth))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/proposal/merge", summary="合并提案到主本体")
async def merge_proposal(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.merge_proposal(str(data.get("code") or ""),
                                 str(getattr(user, "name", None) or ""), _uid(auth))
    return SuccessResponse(data=r, msg=r.get("msg", "已处理"))


@OntologyRouter.post("/proposal/close", summary="关闭提案（不可重新打开）")
async def close_proposal(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.close_proposal(str(data.get("code") or ""),
                                 str(getattr(user, "name", None) or ""))
    return SuccessResponse(data=r, msg=r.get("msg", "已关闭"))


@OntologyRouter.post("/proposal/discard-task", summary="丢弃某个任务的改动")
async def discard_proposal_task(auth: AuthManage,
                                data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _pr.discard_task(int(data.get("task_id") or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已丢弃"))


@OntologyRouter.post("/proposal/comment", summary="在提案/任务下留言")
async def proposal_comment(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    r = await _pr.comment(str(data.get("code") or ""), str(data.get("body") or ""),
                          str(getattr(user, "name", None) or ""),
                          int(data.get("task_id") or 0))
    return SuccessResponse(data=r, msg=r.get("msg", "已留言"))


@OntologyRouter.get("/proposal/{code}/changelog", summary="提案变更记录")
async def proposal_changelog(auth: AuthDep, code: str) -> JSONResponse:
    return SuccessResponse(data=await _pr.proposal_changelog(code), msg="查询成功")


# ---------------------------------------------------------------------------
# D) 演示数据：一键载入 / 一键清除（每页都有东西可看）
# ---------------------------------------------------------------------------
@OntologyRouter.get("/demo/status", summary="演示数据状态")
async def demo_status(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _demo.demo_status(), msg="查询成功")


@OntologyRouter.get("/demo/report", summary="演示数据在各页面的可见内容")
async def demo_report(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _demo.demo_report(), msg="查询成功")


@OntologyRouter.post("/demo/load", summary="载入演示数据")
async def demo_load(auth: AuthManage, data: Annotated[dict, Body()]) -> JSONResponse:
    user = getattr(auth, "user", None)
    who = str(getattr(user, "name", None) or "admin")
    r = await _demo.load_demo(who, bool(data.get("force", False)))
    if not r.get("ok"):
        return SuccessResponse(data=r, msg=r.get("msg", "未载入"))
    return SuccessResponse(data=r, msg=r.get("msg", "已载入"))


@OntologyRouter.post("/demo/clear", summary="清除演示数据（只删登记过的）")
async def demo_clear(auth: AuthManage) -> JSONResponse:
    r = await _demo.clear_demo()
    return SuccessResponse(data=r, msg=r.get("msg", "已清除"))


@OntologyRouter.post("/object-view/share", summary="设置视图共享方式（跟随对象类型 / 按角色）")
async def share_object_view(auth: AuthEdit, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _ov.share_view(str(data.get("code") or ""),
                             str(data.get("share_mode") or "inherit"),
                             data.get("share_roles") or [])
    return SuccessResponse(data=r, msg=r.get("msg", "已设置"))


@OntologyRouter.get("/object-view/{code}/link", summary="生成视图深链（可带对象）")
async def object_view_link(auth: AuthDep, code: str, object_key: str = "") -> JSONResponse:
    r = await _ov.view_link(code, object_key)
    return SuccessResponse(data=r, msg=r.get("msg", "已生成"))


@OntologyRouter.get("/object-view-meta/filters", summary="筛选算子元数据")
async def object_view_filter_meta(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=[{"value": o, "label": _ov.ONT_FILTER_OP_LABEL[o]}
                                 for o in _ov.ONT_FILTER_OPS], msg="查询成功")
