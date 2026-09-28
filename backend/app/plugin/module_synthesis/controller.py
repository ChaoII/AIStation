"""数据合成模块路由（app/plugin/module_synthesis，自动发现 → /synthesis）。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission

from . import service
from .schema import PlateGenerateReq

router = APIRouter(tags=["数据合成"])

PermQuery = Annotated[AuthSchema, Depends(AuthPermission(["module_synthesis:plate:query"]))]
PermGenerate = Annotated[AuthSchema, Depends(AuthPermission(["module_synthesis:plate:generate"]))]


@router.get("/providers", summary="数据合成器列表")
async def providers(auth: PermQuery):
    return SuccessResponse(data=await service.list_providers())


@router.get("/jobs", summary="合成任务列表")
async def jobs(
    auth: PermQuery,
    page_no: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return SuccessResponse(data=await service.list_jobs(page_no, page_size))


@router.post("/license-plate/generate", summary="车牌数据合成")
async def generate(req: PlateGenerateReq, auth: PermGenerate):
    return SuccessResponse(data=await service.generate_license_plates(req, auth))


__all__ = ["router"]
