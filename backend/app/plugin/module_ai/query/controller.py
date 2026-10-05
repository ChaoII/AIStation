"""智能问数控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission, redis_getter
from app.core.router_class import OperationLogRoute

from .schema import (
    QueryAskRequest,
    QueryAssetColumnUpsert,
    QueryAssetUpsert,
    QueryDatasourceUpsert,
    QueryFeedbackRequest,
    QueryFewshotUpsert,
    QueryMetricUpsert,
    QuerySettingUpsert,
    QueryTermUpsert,
)
from .service import AiQueryService

AiQueryRouter = APIRouter(route_class=OperationLogRoute, prefix="/query", tags=["AI-智能问数"])


@AiQueryRouter.post("/ask", summary="智能问数")
async def ask(
    data: QueryAskRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    redis: Annotated[Redis, Depends(redis_getter)],
) -> JSONResponse:
    try:
        result = await AiQueryService.ask(
            data.question, auth, data.session_id, data.datasource,
            redis=redis, force_slow=data.force_slow,
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
@AiQueryRouter.get("/datasources/roles", summary="可授权角色列表")
async def list_query_roles(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_roles(), msg="查询成功")


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


# ---- 数据资产目录 ----
@AiQueryRouter.post("/assets/sync", summary="同步数据资产目录")
async def sync_query_assets(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.sync_assets(auth), msg="同步完成")


@AiQueryRouter.get("/assets/list", summary="数据资产(表)列表")
async def list_query_assets(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_assets(), msg="查询成功")


@AiQueryRouter.post("/assets/generate-desc", summary="LLM 生成表/字段中文描述")
async def generate_asset_desc(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.generate_asset_descriptions(auth), msg="生成完成")


@AiQueryRouter.post("/assets/suggest", summary="LLM 推荐业务指标/术语")
async def suggest_assets(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.suggest_metrics_terms(auth), msg="推荐完成")


@AiQueryRouter.post("/assets/infer-relations", summary="自动推断字段关联")
async def infer_asset_relations(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.infer_asset_relations(auth), msg="已推断关联")


@AiQueryRouter.get("/assets/{table_name}/columns", summary="数据资产(字段)列表")
async def list_asset_columns(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_asset_columns(table_name), msg="查询成功")


@AiQueryRouter.post("/assets/save", summary="数据资产(表)保存")
async def save_query_asset(
    data: QueryAssetUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_asset(data, auth), msg="保存成功")


@AiQueryRouter.post("/assets/column/save", summary="数据资产(字段)保存")
async def save_query_asset_column(
    data: QueryAssetColumnUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_asset_column(data, auth), msg="保存成功")


# ---- 示例工程（few-shot）----
@AiQueryRouter.get("/fewshots/list", summary="NL2SQL 示例列表")
async def list_fewshots(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    datasource: str | None = None,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_fewshots(datasource), msg="查询成功")


@AiQueryRouter.post("/fewshots/save", summary="NL2SQL 示例保存")
async def save_fewshot(
    data: QueryFewshotUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_fewshot(data, auth), msg="保存成功")


@AiQueryRouter.delete("/fewshots/delete", summary="NL2SQL 示例删除")
async def delete_fewshots(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_fewshot(ids)
    return SuccessResponse(msg="删除成功")


# ---- 使用统计 / 设置 ----
@AiQueryRouter.get("/stats", summary="问数使用统计")
async def query_stats(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.stats(), msg="查询成功")


@AiQueryRouter.get("/settings", summary="问数限额配置")
async def query_settings(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.get_settings(), msg="查询成功")


@AiQueryRouter.post("/settings/save", summary="问数限额保存")
async def save_query_setting(
    data: QuerySettingUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiQueryService.save_setting(data.key, data.value, data.remark, auth),
        msg="保存成功",
    )


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


# ---- 基准测试（UI 入口）----
@AiQueryRouter.post("/benchmark/run", summary="运行智能问数基准测试")
async def benchmark_run(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    from .benchmark_runner import start_run

    run_id = start_run(getattr(auth.user, "id", None))
    return SuccessResponse(data={"run_id": run_id}, msg="已启动基准测试，请轮询状态")


@AiQueryRouter.get("/benchmark/status", summary="查询基准测试进度")
async def benchmark_status(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    run_id: str | None = None,
) -> JSONResponse:
    from .benchmark_runner import get_status

    if not run_id:
        return ErrorResponse(msg="缺少 run_id 参数")
    st = get_status(run_id)
    if not st:
        return ErrorResponse(msg="基准运行不存在或已过期")
    return SuccessResponse(data=st, msg="查询成功")
