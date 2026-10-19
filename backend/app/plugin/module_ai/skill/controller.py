"""技能广场控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AiSkillCreateSchema, AiSkillImportSchema, AiSkillUpdateSchema
from .service import AiSkillService

AiSkillRouter = APIRouter(route_class=OperationLogRoute, prefix="/skills", tags=["AI-技能"])


@AiSkillRouter.get("/list", summary="技能列表")
async def list_skills(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:query"]))],
    category: str | None = None,
    skill_type: str | None = None,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiSkillService.list_skills(category, skill_type), msg="查询成功"
    )


@AiSkillRouter.get("/categories", summary="技能分类统计")
async def skill_categories(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiSkillService.categories(), msg="查询成功")


@AiSkillRouter.get("/detail/{skill_id}", summary="技能详情")
async def get_skill(
    skill_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:query"]))],
) -> JSONResponse:
    data = await AiSkillService.get_skill(skill_id)
    if not data:
        return ErrorResponse(msg="技能不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiSkillRouter.post("/create", summary="新增技能")
async def create_skill(
    data: AiSkillCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiSkillService.create(data, auth), msg="创建成功")


@AiSkillRouter.post("/import", summary="导入技能（粘贴 SKILL.md）")
async def import_skill(
    data: AiSkillImportSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:create"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiSkillService.import_skill(data, auth),
        msg="导入成功（默认停用，请检查后启用）",
    )


@AiSkillRouter.post("/import-zip", summary="导入技能（上传 Zip 包）")
async def import_skill_zip(
    file: Annotated[UploadFile, File(description="技能 Zip 包（含 SKILL.md）")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:create"]))],
    category: Annotated[str | None, Form(description="导入分类")] = None,
    source: Annotated[str | None, Form(description="来源标注")] = "SkillHub",
) -> JSONResponse:
    content = await file.read()
    return SuccessResponse(
        data=await AiSkillService.import_skill_zip(
            content, file.filename, category, source, auth
        ),
        msg="导入成功（默认停用，请检查后启用）",
    )


@AiSkillRouter.put("/update/{skill_id}", summary="编辑技能")
async def update_skill(
    skill_id: int,
    data: AiSkillUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:update"]))],
) -> JSONResponse:
    result = await AiSkillService.update(skill_id, data, auth)
    if not result:
        return ErrorResponse(msg="技能不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiSkillRouter.delete("/delete", summary="删除技能")
async def delete_skills(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:delete"]))],
) -> JSONResponse:
    await AiSkillService.delete(ids, auth.user.id)
    return SuccessResponse(msg="删除成功")


@AiSkillRouter.put("/batch/status", summary="批量启用/停用技能")
async def batch_skill_status(
    body: dict,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:update"]))],
) -> JSONResponse:
    ids = [int(x) for x in (body.get("ids") or [])]
    enabled = bool(body.get("enabled"))
    count = await AiSkillService.batch_status(ids, enabled, auth)
    return SuccessResponse(
        data={"count": count}, msg=f"已{'启用' if enabled else '停用'} {count} 个技能"
    )


@AiSkillRouter.put("/toggle/{skill_id}", summary="切换精选")
async def toggle_featured(
    skill_id: int,
    featured: Annotated[bool, Query()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:update"]))],
) -> JSONResponse:
    result = await AiSkillService.toggle_featured(skill_id, featured, auth)
    if not result:
        return ErrorResponse(msg="技能不存在")
    return SuccessResponse(data=result, msg="修改成功")
