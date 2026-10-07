"""本体（Ontology）独立模块控制器：对象/属性/Link/Action 强类型元模型 + 物化。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from . import service as _svc

OntologyRouter = APIRouter(route_class=OperationLogRoute, prefix="/ontology", tags=["AI-本体"])

AuthDep = Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))]


@OntologyRouter.get("/objects", summary="本体对象类型列表")
async def list_objects(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_objects(), msg="查询成功")


@OntologyRouter.post("/object/save", summary="对象类型保存")
async def upsert_object(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_object(data)
    await _svc._log_change(str(data.get("code", "")), "object", "save", f"对象 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/object/{code}/full", summary="对象完整视图(属性/Link/Action)")
async def object_full(code: str, auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.object_full(code), msg="查询成功")


@OntologyRouter.get("/properties", summary="属性类型列表")
async def list_properties(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_properties(object_code), msg="查询成功")


@OntologyRouter.post("/property/save", summary="属性类型保存")
async def upsert_property(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_property(data)
    await _svc._log_change(str(data.get("object_code", "")), "property", "save", f"属性 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/links", summary="关联类型列表")
async def list_links(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_links(object_code or None), msg="查询成功")


@OntologyRouter.post("/link/save", summary="关联类型保存")
async def upsert_link(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_link(data)
    await _svc._log_change(str(data.get("source_object", "")), "link", "save", f"关联 {data.get('name', '')} → {data.get('target_object', '')}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/actions", summary="动作类型列表")
async def list_actions(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_actions(object_code or None), msg="查询成功")


@OntologyRouter.post("/action/save", summary="动作类型保存")
async def upsert_action(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_action(data)
    await _svc._log_change(str(data.get("object_code", "")), "action", "save", f"动作 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.delete("/remove", summary="删除(对象/属性/Link/Action)")
async def remove(kind: str, id: int, auth: AuthDep) -> JSONResponse:
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
async def publish_version(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.publish_version(str(data.get("code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已发布"))


@OntologyRouter.get("/version/list", summary="本体对象定义版本列表")
async def version_list(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_versions(object_code or None), msg="查询成功")


@OntologyRouter.post("/version/rollback", summary="本体对象定义回滚到版本")
async def rollback_version(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.rollback_version(int(data.get("version_id", 0)))
    return SuccessResponse(data=r, msg=r.get("msg", "已回滚"))


@OntologyRouter.get("/version/diff", summary="版本对比(新增/删除/变更属性)")
async def version_diff(auth: AuthDep, version_id: int = 0) -> JSONResponse:
    return SuccessResponse(data=await _svc.version_diff(int(version_id)), msg="查询成功")


@OntologyRouter.post("/materialize", summary="本体驱动表：对象+属性物化成真实表")
async def materialize(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.materialize_object(str(data.get("code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已物化"))


@OntologyRouter.get("/functions", summary="本体计算函数列表")
async def list_functions(auth: AuthDep, object_code: str = "") -> JSONResponse:
    return SuccessResponse(data=await _svc.list_functions(object_code or None), msg="查询成功")


@OntologyRouter.post("/function/save", summary="本体计算函数保存")
async def upsert_function(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_function(data)
    await _svc._log_change(str(data.get("object_code", "")), "function", "save", f"函数 {data.get('name', data.get('code'))}")
    return SuccessResponse(data=r, msg="保存成功")


@OntologyRouter.get("/capabilities", summary="本体能力列表")
async def list_capabilities(auth: AuthDep) -> JSONResponse:
    return SuccessResponse(data=await _svc.list_capabilities(), msg="查询成功")


@OntologyRouter.post("/capability/save", summary="本体能力保存")
async def upsert_capability(auth: AuthDep, data: Annotated[dict, Body()]) -> JSONResponse:
    r = await _svc.upsert_capability(data)
    return SuccessResponse(data=r, msg="保存成功")
