"""工作流控制器：CRUD 与流式运行。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.streaming import ui_stream_response

from .schema import (
    AiWorkflowApproveSchema,
    AiWorkflowCreateSchema,
    AiWorkflowDebugNodeSchema,
    AiWorkflowRunSchema,
    AiWorkflowShareRunSchema,
    AiWorkflowStepSchema,
    AiWorkflowUpdateSchema,
    AiWorkflowVersionCreateSchema,
)
from .service import AiWorkflowService

AiWorkflowRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/workflows", tags=["AI-工作流"]
)


@AiWorkflowRouter.get("/list", summary="工作流列表")
async def list_workflows(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiWorkflowService.list_workflows(), msg="查询成功")


@AiWorkflowRouter.get("/detail/{workflow_id}", summary="工作流详情")
async def get_workflow(
    workflow_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> JSONResponse:
    data = await AiWorkflowService.get_workflow(workflow_id)
    if not data:
        return ErrorResponse(msg="工作流不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiWorkflowRouter.get("/{workflow_id}/run-logs", summary="工作流运行历史列表")
async def list_run_logs(
    workflow_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiWorkflowService.list_run_logs(workflow_id), msg="查询成功"
    )


@AiWorkflowRouter.get("/run-log/{run_id}", summary="单次运行详情")
async def get_run_log(
    run_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> JSONResponse:
    data = await AiWorkflowService.get_run_log(run_id)
    if not data:
        return ErrorResponse(msg="运行记录不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiWorkflowRouter.get("/{workflow_id}/stats", summary="工作流运行统计")
async def get_workflow_stats(
    workflow_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiWorkflowService.get_workflow_stats(workflow_id), msg="查询成功"
    )


@AiWorkflowRouter.post("/{workflow_id}/share", summary="生成/获取公开分享令牌")
async def create_share(
    workflow_id: int,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:update"]))],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    token = await AiWorkflowService.generate_share_token(workflow_id, uid)
    if token is None:
        return ErrorResponse(msg="工作流不存在")
    return SuccessResponse(data={"token": token}, msg="分享链接已生成")


@AiWorkflowRouter.post("/share/run", summary="公开分享受限运行（匿名）")
async def share_run(
    data: AiWorkflowShareRunSchema,
    request: Request,
) -> StreamingResponse:
    return ui_stream_response(
        AiWorkflowService.share_ui_stream(
            data.token, data.message, redis=request.app.state.redis
        )
    )


@AiWorkflowRouter.post("/create", summary="新增工作流")
async def create_workflow(
    data: AiWorkflowCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiWorkflowService.create(data, auth), msg="创建成功")


@AiWorkflowRouter.put("/update/{workflow_id}", summary="编辑工作流")
async def update_workflow(
    workflow_id: int,
    data: AiWorkflowUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:update"]))],
) -> JSONResponse:
    result = await AiWorkflowService.update(workflow_id, data, auth)
    if not result:
        return ErrorResponse(msg="工作流不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiWorkflowRouter.delete("/delete", summary="删除工作流")
async def delete_workflows(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:delete"]))],
) -> JSONResponse:
    await AiWorkflowService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiWorkflowRouter.post("/{workflow_id}/versions", summary="保存工作流版本")
async def save_workflow_version(
    workflow_id: int,
    data: AiWorkflowVersionCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:update"]))],
) -> JSONResponse:
    result = await AiWorkflowService.save_version(workflow_id, data, auth)
    if not result:
        return ErrorResponse(msg="工作流不存在")
    return SuccessResponse(data=result, msg="版本已保存")


@AiWorkflowRouter.get("/{workflow_id}/versions", summary="工作流版本列表")
async def list_workflow_versions(
    workflow_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiWorkflowService.list_versions(workflow_id), msg="查询成功")


@AiWorkflowRouter.post("/{workflow_id}/versions/{version_id}/rollback", summary="回滚工作流到指定版本")
async def rollback_workflow_version(
    workflow_id: int,
    version_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:update"]))],
) -> JSONResponse:
    result = await AiWorkflowService.rollback_version(workflow_id, version_id, auth)
    if not result:
        return ErrorResponse(msg="工作流或版本不存在")
    return SuccessResponse(data=result, msg="回滚成功")


@AiWorkflowRouter.post("/{workflow_id}/versions/{version_id}/publish", summary="发布工作流版本")
async def publish_workflow_version(
    workflow_id: int,
    version_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:update"]))],
) -> JSONResponse:
    result = await AiWorkflowService.publish_version(workflow_id, version_id, auth)
    if not result:
        return ErrorResponse(msg="工作流或版本不存在")
    return SuccessResponse(data=result, msg="发布成功")


@AiWorkflowRouter.post("/{workflow_id}/run/stream", summary="运行工作流（AI SDK UI Message Stream）")
async def run_workflow_stream(
    workflow_id: int,
    data: AiWorkflowRunSchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> StreamingResponse:
    return ui_stream_response(
        AiWorkflowService.run_ui_stream(
            workflow_id,
            data.messages,
            auth,
            data.variables,
            data.session_id,
            redis=request.app.state.redis,
            timeout_seconds=data.timeout_seconds,
        )
    )


@AiWorkflowRouter.post("/{workflow_id}/debug-node/stream", summary="单节点调试运行（流式）")
async def debug_node_stream(
    workflow_id: int,
    data: AiWorkflowDebugNodeSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> StreamingResponse:
    return ui_stream_response(
        AiWorkflowService.debug_node_ui_stream(
            workflow_id, data.node_id, data.variables, data.messages
        )
    )


@AiWorkflowRouter.post("/{workflow_id}/step/stream", summary="逐步执行节点（流式）")
async def step_node_stream(
    workflow_id: int,
    data: AiWorkflowStepSchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> StreamingResponse:
    return ui_stream_response(
        AiWorkflowService.step_node_ui_stream(
            workflow_id,
            data.run_id,
            data.variables,
            data.messages,
            redis=request.app.state.redis,
        )
    )


@AiWorkflowRouter.post("/{workflow_id}/approve", summary="HITL 工具审批续跑（流式）")
async def approve_workflow(
    workflow_id: int,
    data: AiWorkflowApproveSchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workflow:query"]))],
) -> StreamingResponse:
    return ui_stream_response(
        AiWorkflowService.approve_ui_stream(
            workflow_id, data, auth, redis=request.app.state.redis
        )
    )
