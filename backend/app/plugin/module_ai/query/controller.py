"""智能问数控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import (
    QueryAskRequest,
    QueryDatasourceUpsert,
    QueryFeedbackRequest,
    QueryMetricUpsert,
    QueryTermUpsert,
)
from .service import AiQueryService

AiQueryRouter = APIRouter(route_class=OperationLogRoute, prefix="/query", tags=["AI-智能问数"])


@AiQueryRouter.post("/ask", summary="智能问数")
async def ask(
    data: QueryAskRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    try:
        result = await AiQueryService.ask(
            data.question, auth, data.session_id, data.datasource
        )
    except Exception as e:  # noqa: BLE001
        return ErrorResponse(msg=str(getattr(e, "msg", e)))
    return SuccessResponse(data=result, msg="查询成功")


# ---- 指标运营 ----
@AiQueryRouter.get("/metrics/list", summary="指标列表")
async def list_metrics(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    datasource: str | None = None,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_metrics(datasource), msg="查询成功")


@AiQueryRouter.post("/metrics/save", summary="指标保存")
async def save_metric(
    data: QueryMetricUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_metric(data, auth), msg="保存成功")


@AiQueryRouter.delete("/metrics/delete", summary="指标删除")
async def delete_metrics(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_metric(ids)
    return SuccessResponse(msg="删除成功")


# ---- 术语运营 ----
@AiQueryRouter.get("/terms/list", summary="术语列表")
async def list_terms(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    datasource: str | None = None,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_terms(datasource), msg="查询成功")


@AiQueryRouter.post("/terms/save", summary="术语保存")
async def save_term(
    data: QueryTermUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_term(data, auth), msg="保存成功")


@AiQueryRouter.delete("/terms/delete", summary="术语删除")
async def delete_terms(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_term(ids)
    return SuccessResponse(msg="删除成功")


# ---- 数据源 ----
@AiQueryRouter.get("/datasources/list", summary="数据源列表")
async def list_datasources(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_datasources(), msg="查询成功")


@AiQueryRouter.post("/datasources/save", summary="数据源保存")
async def save_datasource(
    data: QueryDatasourceUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_datasource(data, auth), msg="保存成功")


@AiQueryRouter.delete("/datasources/delete", summary="数据源删除")
async def delete_datasources(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_datasource(ids)
    return SuccessResponse(msg="删除成功")


@AiQueryRouter.post("/datasources/{datasource_id}/test", summary="测试数据源连接")
async def test_datasource(
    datasource_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.test_datasource_conn(datasource_id), msg="测试完成")


@AiQueryRouter.post("/datasources/{datasource_id}/sync-schema", summary="同步数据源表结构")
async def sync_datasource_schema(
    datasource_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.sync_datasource_schema(datasource_id), msg="同步完成")


@AiQueryRouter.get("/datasources/{datasource_id}/schema", summary="数据源已同步表结构")
async def datasource_schema(
    datasource_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_ds_schema(datasource_id), msg="查询成功")


# ---- 会话/历史 ----
@AiQueryRouter.get("/sessions/list", summary="会话列表")
async def list_sessions(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_sessions(auth), msg="查询成功")


@AiQueryRouter.get("/sessions/{session_id}/messages", summary="会话消息")
async def list_messages(
    session_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_messages(session_id), msg="查询成功")


@AiQueryRouter.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_session(session_id)
    return SuccessResponse(msg="删除成功")


# ---- 反馈 ----
@AiQueryRouter.post("/feedback", summary="结果反馈")
async def feedback(
    data: QueryFeedbackRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.feedback(data.message_id, data.feedback, data.correct_sql, auth), msg="已记录")
