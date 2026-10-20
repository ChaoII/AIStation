"""智能问数控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from redis.asyncio.client import Redis

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission, redis_getter
from app.core.router_class import OperationLogRoute

from .schema import (
    FilterRulesAdviseRequest,
    FilterRulesParseRequest,
    FilterRulesPreviewRequest,
    FilterRulesSuggestRequest,
    QueryAskRequest,
    QueryAssetColumnUpsert,
    QueryAssetUpsert,
    QueryDatasourceUpsert,
    QueryFeedbackRequest,
    QueryFewshotUpsert,
    QueryMetricUpsert,
    QueryModelingUpsert,
    QueryPromoteRequest,
    QuerySettingUpsert,
    QueryTermUpsert,
)
from .service import AiQueryService, list_ds_schema
from .service import sync_datasource_schema as _do_sync_schema

# 注意：`test_datasource_conn` 是**模块级函数**，不是 AiQueryService 的类方法。
# 之前控制器写成 `AiQueryService.test_datasource_conn(...)`，点「测试连接」必报
# AttributeError（真实缺陷，页面上那个按钮一直是坏的）。按 sync 的写法导入。
from .service import test_datasource_conn as _do_test_conn

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
            object_code=data.object_code, object_key=data.object_key,
        )
    except Exception as e:  # noqa: BLE001
        return ErrorResponse(msg=str(getattr(e, "msg", e)))
    return SuccessResponse(data=result, msg="查询成功")


@AiQueryRouter.post("/ask/stream", summary="智能问数(流式: 思考/工具调用/结果)")
async def ask_stream(
    data: QueryAskRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> StreamingResponse:
    import json

    from app.core.sse import sse_response

    async def _gen():
        try:
            async for ev in AiQueryService.ask_stream(
                data.question, auth, data.session_id, data.datasource,
                object_code=data.object_code, object_key=data.object_key,
            ):
                yield f"event: {ev.get('type', 'message')}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'message': str(getattr(e, 'msg', e))}, ensure_ascii=False)}\n\n"

    return sse_response(_gen())


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


@AiQueryRouter.post("/metrics/promote", summary="沉淀为可复用指标(供交付复用)")
async def promote_metric(
    data: QueryPromoteRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    payload = await AiQueryService.promote_message_to_metric(
        data.message_id, data.name, data.key, auth
    )
    return SuccessResponse(data=payload, msg="已沉淀为可复用指标")


@AiQueryRouter.delete("/metrics/delete", summary="指标删除")
async def delete_metrics(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_metric(ids)
    return SuccessResponse(msg="删除成功")


# ---- 大模型自动建模（S4） ----
@AiQueryRouter.post("/modeling/metrics", summary="建模：生成绑定型指标")
async def modeling_metrics(
    data: QueryModelingUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    out = await AiQueryService.generate_modeling(
        "metrics", data.datasource, auth, max_objects=data.max_objects, dry=data.dry)
    return SuccessResponse(data=out, msg="生成完成")


@AiQueryRouter.post("/modeling/annotate", summary="建模：生成对象/属性标注")
async def modeling_annotate(
    data: QueryModelingUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    out = await AiQueryService.generate_modeling(
        "annotate", data.datasource, auth, max_objects=data.max_objects)
    return SuccessResponse(data=out, msg="生成完成")


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


@AiQueryRouter.get("/autopilot", summary="治理巡检中心(候选行动)")
async def autopilot(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.autopilot(), msg="查询成功")


@AiQueryRouter.post("/autopilot/execute", summary="执行巡检行动(敏感扫描/DQ重扫)")
async def autopilot_execute(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.autopilot_execute(
        data.get("executable", ""), data.get("table", ""), auth=auth
    )
    return SuccessResponse(data=r, msg=r.get("msg", "执行完成"))


@AiQueryRouter.get("/derived-metrics", summary="派生指标规则引擎(基础指标推导)")
async def derived_metrics(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_derived_metrics(), msg="查询成功")


@AiQueryRouter.get("/derived-metrics/compute", summary="计算派生指标值")
async def derived_metric_compute(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    key: str = "",
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.compute_derived_metric(key), msg="查询成功")


@AiQueryRouter.get("/security/audit", summary="数据安全与访问审计中心")
async def security_audit(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    limit: int = 30,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.security_audit(limit), msg="查询成功")


@AiQueryRouter.get("/derived-objects", summary="Ontology 派生对象(按域聚类+派生属性)")
async def derived_objects(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.derived_objects(), msg="查询成功")


@AiQueryRouter.post("/autopilot/auto-fix", summary="巡检自动修复调度(批量执行)")
async def autopilot_auto_fix(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.autopilot_auto_fix(), msg="执行完成")


@AiQueryRouter.get("/favorites/list", summary="Compass 收藏/引用列表")
async def favorites_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.favorites_list(auth.user.id), msg="查询成功")


@AiQueryRouter.post("/favorites/add", summary="收藏/引用")
async def favorites_add(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.favorites_add(data.get("kind", ""), data.get("ref", ""), auth.user.id)
    return SuccessResponse(data=r, msg=r.get("msg", "操作完成"))


@AiQueryRouter.post("/favorites/remove", summary="取消收藏")
async def favorites_remove(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.favorites_remove(int(data.get("id", 0)), auth.user.id)
    return SuccessResponse(data=r, msg=r.get("msg", "操作完成"))


@AiQueryRouter.get("/plugins/list", summary="AIP 插件/工具市场目录")
async def plugins_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_plugins(), msg="查询成功")


@AiQueryRouter.get("/assets/{table_name}/propagate", summary="端到端影响传播(下游表/指标)")
async def lineage_propagate(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    max_depth: int = 4,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.lineage_propagate(table_name, max_depth), msg="查询成功")


@AiQueryRouter.get("/dq-rules", summary="数据质量规则引擎(规则列表)")
async def dq_rules_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.dq_rules_list(), msg="查询成功")


@AiQueryRouter.get("/dq-rules/run", summary="执行数据质量规则(非空/唯一)")
async def dq_rules_run(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    table: str = "",
    column: str = "",
    rule_type: str = "",
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.dq_rules_run(table, column, rule_type), msg="查询成功")


@AiQueryRouter.get("/assets/{table_name}/export", summary="数据集导出(真实表数据)")
async def export_asset(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    limit: int = 100,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.export_asset(table_name, limit), msg="查询成功")


@AiQueryRouter.get("/objects/{table_name}/browse", summary="对象数据浏览器(分页)")
async def object_browse(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    page: int = 1,
    page_size: int = 20,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.object_browse(table_name, page, page_size), msg="查询成功")


@AiQueryRouter.post("/share/create", summary="数据集分享(生成分享链接)")
async def share_create(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.share_create(data.get("table", ""), auth.user.id)
    return SuccessResponse(data=r, msg="分享成功")


@AiQueryRouter.get("/share/list", summary="我的数据分享列表")
async def share_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.share_list(auth.user.id), msg="查询成功")


@AiQueryRouter.post("/share/remove", summary="撤销分享")
async def share_remove(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.share_remove(int(data.get("id", 0)), auth.user.id)
    return SuccessResponse(data=r, msg=r.get("msg", "操作完成"))


@AiQueryRouter.get("/catalog/categories", summary="Compass 数据目录分类")
async def catalog_categories(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.catalog_categories(), msg="查询成功")


@AiQueryRouter.get("/objects/relations", summary="对象关系图(边)")
async def object_relations(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.object_relations(), msg="查询成功")


@AiQueryRouter.get("/access/walkthrough", summary="数据访问沙箱/演练")
async def access_walkthrough(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    user_id: int = 0,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.access_walkthrough(user_id), msg="查询成功")


@AiQueryRouter.get("/guardrails", summary="治理检查项状态")
async def guardrails_status(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.guardrails_status(), msg="查询成功")


@AiQueryRouter.get("/governance/report", summary="AIP 数据治理报告(生成/导出)")
async def governance_report(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.governance_report(), msg="查询成功")


@AiQueryRouter.get("/assets/hotspots", summary="数据资产热点(使用排行)")
async def asset_hotspots(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.asset_hotspots(), msg="查询成功")


@AiQueryRouter.get("/objects/lifecycle", summary="对象生命周期看板")
async def object_lifecycle(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.object_lifecycle(), msg="查询成功")


@AiQueryRouter.get("/datasources/{datasource_id}/detail", summary="数据源连接详情")
async def datasource_detail(
    datasource_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.datasource_detail(datasource_id), msg="查询成功")


@AiQueryRouter.post("/datasources/{datasource_id}/rules/preview", summary="筛选规则分类预览")
async def rules_preview(
    datasource_id: int,
    data: FilterRulesPreviewRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.preview_filter_rules(datasource_id, data.rules), msg="查询成功")


@AiQueryRouter.post("/datasources/{datasource_id}/rules/suggest", summary="筛选规则生成建议")
async def rules_suggest(
    datasource_id: int,
    data: FilterRulesSuggestRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.suggest_filter_rules(datasource_id, data.rules), msg="生成成功")


@AiQueryRouter.post("/datasources/{datasource_id}/rules/parse", summary="自然语言转筛选规则")
async def rules_parse(
    datasource_id: int,
    data: FilterRulesParseRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.parse_filter_rules(datasource_id, data.text), msg="解析成功")


@AiQueryRouter.post("/datasources/{datasource_id}/rules/classify-advise", summary="逐表逐字段分类建议")
async def rules_classify_advise(
    datasource_id: int,
    data: FilterRulesAdviseRequest,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.classify_advise(datasource_id, data.rules), msg="建议成功")


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
    return SuccessResponse(data=await _do_test_conn(datasource_id), msg="测试完成")


@AiQueryRouter.post("/datasources/{datasource_id}/sync-schema", summary="同步数据源表结构")
async def sync_datasource_schema(
    datasource_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await _do_sync_schema(datasource_id), msg="同步完成")


@AiQueryRouter.get("/datasources/{datasource_id}/schema", summary="数据源已同步表结构")
async def datasource_schema(
    datasource_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await list_ds_schema(datasource_id), msg="查询成功")


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
    force: int = 0,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiQueryService.generate_asset_descriptions(auth, force=bool(force)),
        msg="生成完成",
    )


@AiQueryRouter.post("/assets/kg/rebuild", summary="重建知识图谱(清缓存+重构建)")
async def kg_rebuild(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    from .agno_kg import _reset

    data = await _reset()
    return SuccessResponse(data=data, msg="知识图谱已重建")


@AiQueryRouter.get("/assets/objects", summary="业务对象(Object Type)+Link Type列表")
async def list_objects(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_objects(), msg="查询成功")


@AiQueryRouter.post("/objects/resolve", summary="本体对象 grounding(解析实体为对象实例+关联)")
async def object_resolve(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.resolve_entity_object(str(data.get("entity", "")), str(data.get("key", "")),
                                                   user_id=auth.user.id)
    return SuccessResponse(data=r, msg="解析成功")


# ---- 交付命题工作台 ----
@AiQueryRouter.get("/fde/list", summary="交付命题列表")
async def fde_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_propositions(), msg="查询成功")


@AiQueryRouter.post("/fde/save", summary="交付命题保存(五步单/缺口/留痕)")
async def fde_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.upsert_proposition(data, auth)
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.delete("/fde/delete", summary="删除交付命题")
async def fde_delete(
    ids: list[int],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    for pid in ids:
        await AiQueryService.delete_proposition(pid)
    return SuccessResponse(data=None, msg="已删除")


@AiQueryRouter.post("/fde/shadow", summary="影子运行/黄金标准校验")
async def fde_shadow(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.shadow_check(int(data.get("proposition_id", 0)))
    return SuccessResponse(data=r, msg="校验完成")


# ---- P1·Action(写回+审计) ----
@AiQueryRouter.get("/writeback/list", summary="表级写回：动作列表")
@AiQueryRouter.get("/action/list", summary="(deprecated) 表级写回：动作列表", deprecated=True)
async def action_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_actions(), msg="查询成功")


@AiQueryRouter.post("/writeback/save", summary="表级写回：动作定义保存")
@AiQueryRouter.post("/action/save", summary="(deprecated) 表级写回：动作定义保存", deprecated=True)
async def action_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.upsert_action(data)
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.post("/writeback/execute", summary="表级写回：执行动作(写回+审计)")
@AiQueryRouter.post("/action/execute", summary="(deprecated) 表级写回：执行动作(写回+审计)", deprecated=True)
async def action_execute(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    r = await AiQueryService.execute_action(
        str(data.get("name", "")), str(data.get("object_key", "")),
        data.get("params") or {}, operator=str(uid or ""), approve=bool(data.get("approve", False)))
    return SuccessResponse(data=r, msg="执行完成")


@AiQueryRouter.get("/writeback/logs", summary="表级写回：动作审计日志")
@AiQueryRouter.get("/action/logs", summary="(deprecated) 表级写回：动作审计日志", deprecated=True)
async def action_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    limit: int = 100,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_action_logs(limit), msg="查询成功")


@AiQueryRouter.get("/writeback/pending", summary="表级写回：待审批动作")
@AiQueryRouter.get("/action/pending", summary="(deprecated) 表级写回：待审批动作", deprecated=True)
async def action_pending(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    limit: int = 50,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_pending_actions(limit), msg="查询成功")


@AiQueryRouter.get("/approval/center", summary="审批中心统一视图(动作+本体发布)")
async def approval_center(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.approval_center(), msg="查询成功")


@AiQueryRouter.post("/writeback/approve", summary="表级写回：批准动作(写回+审计)")
@AiQueryRouter.post("/action/approve", summary="(deprecated) 表级写回：批准动作(写回+审计)", deprecated=True)
async def action_approve(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    return SuccessResponse(data=await AiQueryService.approve_action(int(data.get("approval_id", 0)), str(uid or "")), msg="审批完成")


@AiQueryRouter.post("/writeback/reject", summary="表级写回：驳回动作")
@AiQueryRouter.post("/action/reject", summary="(deprecated) 表级写回：驳回动作", deprecated=True)
async def action_reject(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    return SuccessResponse(data=await AiQueryService.reject_action(int(data.get("approval_id", 0)), str(uid or "")), msg="审批完成")


# ---- P1-② 版本/血缘/影响分析/回滚 ----
@AiQueryRouter.get("/assets/{table_name}/versions", summary="资产版本历史")
async def asset_versions(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_versions(table_name), msg="查询成功")


@AiQueryRouter.post("/assets/version/rollback", summary="回滚到指定版本")
async def asset_rollback(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.rollback_version(int(data.get("version_id", 0)), auth)
    return SuccessResponse(data=r, msg=r.get("msg", "回滚完成"))


@AiQueryRouter.get("/assets/version/diff", summary="版本 diff(对比两个版本快照)")
async def asset_version_diff(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    id_a: int,
    id_b: int,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.version_diff(id_a, id_b), msg="查询成功")


@AiQueryRouter.post("/assets/{table_name}/publish", summary="数据集/对象版本发布")
async def asset_publish(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.asset_publish(table_name, int(data.get("version_id", 0)), auth)
    return SuccessResponse(data=r, msg=r.get("msg", "发布完成"))


@AiQueryRouter.get("/assets/{table_name}/releases", summary="数据发布(当前发布版本+列表)")
async def asset_releases(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.asset_releases(table_name), msg="查询成功")


@AiQueryRouter.get("/assets/{table_name}/impact", summary="影响分析(指标/关联/对象)")
async def asset_impact(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.impact_analysis(table_name), msg="查询成功")


@AiQueryRouter.post("/assets/extract-objects", summary="语义抽取/消歧：自动识别业务对象")
async def extract_objects(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.semantic_extract_objects(), msg="已抽取业务对象")


@AiQueryRouter.get("/industry/templates", summary="行业本体模板(ISA-95/GMP/通用)")
async def industry_templates(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.industry_templates(), msg="查询成功")


@AiQueryRouter.post("/industry/apply", summary="应用行业本体模板(预建标准概念)")
async def industry_apply(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.apply_industry_template(str(data.get("template_id", "")), auth)
    return SuccessResponse(data=r, msg=r.get("msg", "已应用模板"))


# ---- P3-① 数据管道(连接中心→可视化摄取/映射) ----
@AiQueryRouter.get("/pipeline/list", summary="数据管道列表")
async def pipeline_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_pipelines(), msg="查询成功")


@AiQueryRouter.get("/pipeline/graph", summary="数据管道(ELT)编排图")
async def pipeline_graph(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.pipeline_graph(), msg="查询成功")


@AiQueryRouter.post("/pipeline/save", summary="数据管道保存")
async def pipeline_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.upsert_pipeline(data)
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.post("/pipeline/run", summary="运行数据管道(拉取外部数据落库到对象)")
async def pipeline_run(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.run_pipeline(int(data.get("pipeline_id", 0)))
    return SuccessResponse(data=r, msg=r.get("msg", "已运行"))


@AiQueryRouter.post("/pipeline/data", summary="查看管道落库数据")
async def pipeline_data(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.pipeline_data(int(data.get("pipeline_id", 0)), int(data.get("limit") or 50))
    return SuccessResponse(data=r, msg="查询成功")


# ---- 召回服务（阶段1：语义单元 + 多路融合）----
@AiQueryRouter.post("/recall/rebuild", summary="重建语义召回单元")
async def rebuild_recall_units(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.rebuild_recall_units(), msg="重建完成")


@AiQueryRouter.get("/recall/probe", summary="召回探针：某问题选中了哪些表")
async def recall_probe(
    question: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    final = await AiQueryService._semantic_tables_uncached(question, None, None, None)
    return SuccessResponse(data={"question": question, "final": final}, msg="查询成功")


# ---- 自定义报表模板（一次沉淀、长期复用）----
@AiQueryRouter.get("/reports", summary="报表模板列表")
async def report_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    datasource: str | None = None,
    verified_only: bool = False,
) -> JSONResponse:
    from .report import list_reports

    return SuccessResponse(
        data=await list_reports(datasource, verified_only), msg="查询成功"
    )


@AiQueryRouter.post("/reports", summary="新增/更新报表模板")
async def report_upsert(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .report import upsert_report

    return SuccessResponse(data=await upsert_report(data, auth), msg="保存成功")


@AiQueryRouter.delete("/reports", summary="删除报表模板")
async def report_delete(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[list[int], Body()],
) -> JSONResponse:
    from .report import delete_reports

    return SuccessResponse(data={"deleted": await delete_reports(data)}, msg="已删除")


@AiQueryRouter.post("/reports/{report_id}/run", summary="执行报表模板")
async def report_run(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    report_id: int,
    data: Annotated[dict | None, Body()] = None,
) -> JSONResponse:
    from .report import run_report

    body = data or {}
    return SuccessResponse(
        data=await run_report(report_id, body.get("params"), auth), msg="执行成功"
    )


@AiQueryRouter.post("/reports/{report_id}/verify", summary="人工确认报表模板")
async def report_verify(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    report_id: int,
) -> JSONResponse:
    from .report import get_report, upsert_report

    rep = await get_report(report_id)
    if not rep:
        return ErrorResponse(msg="报表不存在")
    await upsert_report({**rep, "key": rep["key"], "verified": True}, auth)
    return SuccessResponse(data={"id": report_id, "verified": True}, msg="已确认")


# ---- 问数评测（测试集 / 运行 / 报表 / 消融）----
@AiQueryRouter.get("/eval/cases", summary="评测测试集列表")
async def eval_list_cases(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    datasource: str | None = None,
    difficulty: str | None = None,
    form: str | None = None,
    scenario: str | None = None,
) -> JSONResponse:
    from .eval_set import list_cases

    return SuccessResponse(
        data=await list_cases(datasource, difficulty, form, scenario), msg="查询成功"
    )


@AiQueryRouter.post("/eval/cases", summary="新增/更新测试题")
async def eval_upsert_case(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .eval_set import upsert_case

    return SuccessResponse(data=await upsert_case(data), msg="保存成功")


@AiQueryRouter.put("/eval/cases", summary="更新测试题（同 upsert）")
async def eval_update_case(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .eval_set import upsert_case

    return SuccessResponse(data=await upsert_case(data), msg="保存成功")


@AiQueryRouter.delete("/eval/cases", summary="删除测试题")
async def eval_delete_cases(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[list[int], Body()],
) -> JSONResponse:
    from .eval_set import delete_cases

    return SuccessResponse(data={"deleted": await delete_cases(data)}, msg="已删除")


@AiQueryRouter.post("/eval/run", summary="启动一轮评测")
async def eval_run(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict | None, Body()] = None,
) -> JSONResponse:
    from .eval_runner import start_run

    body = data or {}
    rid = start_run(
        auth, filter=body.get("filter"), mode=body.get("mode") or "full", config=body.get("config")
    )
    return SuccessResponse(data={"run_id": rid}, msg="已启动")


@AiQueryRouter.get("/eval/status", summary="评测进度")
async def eval_status(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    run_id: str | None = None,
) -> JSONResponse:
    from .eval_runner import get_status

    return SuccessResponse(data=get_status(run_id), msg="查询成功")


@AiQueryRouter.get("/eval/report", summary="评测结果（总览 + 分维度 + 逐题）")
async def eval_report(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    run_id: str,
) -> JSONResponse:
    from .eval_metrics import group_by, summarize
    from .eval_set import load_results

    rows = await load_results(run_id)
    return SuccessResponse(
        data={
            "summary": summarize(rows),
            "by_difficulty": group_by(rows, "difficulty"),
            "by_scenario": group_by(rows, "scenario"),
            "by_form": group_by(rows, "form"),
            "by_datasource": group_by(rows, "datasource"),
            # 按执行路径分组（fast=指标模板 / object=对象查询 / slow=NL2SQL）：
            # 对象查询的收益要**按路径**看，混在一起会被快路径稀释掉。
            "by_path": group_by(rows, "path"),
            "results": rows[:200],
        },
        msg="查询成功",
    )


@AiQueryRouter.post("/eval/generate", summary="生成一轮测试题（LLM 出题 + 金标执行校验）")
async def eval_generate(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .eval_generate import generate_round

    body = data or {}
    out = await generate_round(
        str(body.get("datasource") or "system"),
        str(body.get("difficulty") or "简单"),
        str(body.get("form") or "单维统计"),
        int(body.get("n") or 5),
        auth,
    )
    return SuccessResponse(data=out, msg="生成完成")


@AiQueryRouter.get("/eval/runs", summary="历史评测运行")
async def eval_runs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    limit: int = 30,
) -> JSONResponse:
    from .eval_set import list_runs

    return SuccessResponse(data=await list_runs(limit), msg="查询成功")


@AiQueryRouter.post("/eval/ablation", summary="启动消融评测")
async def eval_ablation(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict | None, Body()] = None,
) -> JSONResponse:
    from .eval_runner import start_ablation

    body = data or {}
    rid = start_ablation(auth, keys=body.get("keys"), filter=body.get("filter"))
    return SuccessResponse(data={"run_id": rid}, msg="已启动")


@AiQueryRouter.get("/eval/ablation", summary="消融对照表")
async def eval_ablation_report(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    run_id: str,
) -> JSONResponse:
    from .eval_runner import get_ablation_report

    return SuccessResponse(data=get_ablation_report(run_id), msg="查询成功")


@AiQueryRouter.post("/eval/variance", summary="启动方差评测（同一批题重复跑 N 次）")
async def eval_variance_start(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict | None, Body()] = None,
) -> JSONResponse:
    """回答"这个差异是真的吗"：跨次均值/标准差/噪声带 + 逐题翻转 + McNemar。"""
    from .eval_runner import start_variance

    body = data or {}
    rid = start_variance(auth, repeats=int(body.get("repeats") or 3), filter=body.get("filter"))
    return SuccessResponse(data={"run_id": rid}, msg="已启动")


@AiQueryRouter.get("/eval/variance", summary="方差报告")
async def eval_variance_report(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    run_id: str,
) -> JSONResponse:
    from .eval_runner import get_variance_report

    return SuccessResponse(data=get_variance_report(run_id), msg="查询成功")


# ---- P3-② Workshop 对象工作台(无代码应用) ----
@AiQueryRouter.get("/workshop/objects", summary="对象应用可选对象与字段")
async def workshop_objects(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.workshop_objects(), msg="查询成功")


@AiQueryRouter.get("/workshop/list", summary="对象应用列表")
async def workshop_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_workshop_apps(), msg="查询成功")


@AiQueryRouter.post("/workshop/save", summary="对象应用保存")
async def workshop_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.upsert_workshop_app(data)
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.post("/workshop/preview", summary="对象应用预览(读取真实数据)")
async def workshop_preview(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.workshop_preview(int(data.get("app_id", 0)), int(data.get("limit") or 50))
    return SuccessResponse(data=r, msg="预览完成")


@AiQueryRouter.delete("/workshop/delete", summary="对象应用删除")
async def workshop_delete(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    await AiQueryService.delete_workshop_app(int(data.get("id", 0)))
    return SuccessResponse(data=None, msg="删除成功")


@AiQueryRouter.post("/workshop/submit", summary="对象应用表单提交(写入对象表)")
async def workshop_submit(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.workshop_submit(int(data.get("app_id", 0)), data.get("data") or {})
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.get("/assets/{table_name}/lineage", summary="完整血缘图(表→字段/指标/对象/管道/概念)")
async def asset_lineage(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.lineage(table_name), msg="查询成功")


# ---- P3-④ ABAC 权限 ----
@AiQueryRouter.get("/access/list", summary="ABAC权限策略列表")
async def access_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_access_rules(), msg="查询成功")


@AiQueryRouter.get("/access/matrix", summary="数据域权限矩阵")
async def access_matrix(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.access_matrix(), msg="查询成功")


@AiQueryRouter.get("/access/preview", summary="权限沙箱(按用户预览可查表)")
async def access_preview(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    user_id: int = 0,
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.access_preview(user_id), msg="查询成功")


@AiQueryRouter.get("/access/preview-role", summary="按角色预览可查表")
async def access_preview_role(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    role: str = "",
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.access_preview_role(role), msg="查询成功")


@AiQueryRouter.get("/access/permission-check", summary="权限检查(用户×资源)")
async def permission_check(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    user_id: int = 0,
    table: str = "",
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.permission_check(user_id, table), msg="查询成功")


@AiQueryRouter.get("/compass/search", summary="Compass全局数据目录搜索(表/对象/指标/术语)")
async def compass_search(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    keyword: str = "",
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.compass_search(keyword), msg="查询成功")


@AiQueryRouter.get("/dq/overview", summary="数据质量(DQ)总览")
async def dq_overview(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.dq_overview(), msg="查询成功")


@AiQueryRouter.post("/dq/run", summary="数据质量(DQ)扫描单个对象")
async def dq_run(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.dq_run(str(data.get("table", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "扫描完成"))


@AiQueryRouter.post("/dq/scan", summary="显式全量扫描全部业务对象")
async def dq_scan_all(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    r = await AiQueryService.dq_scan_all()
    return SuccessResponse(data=r, msg=r.get("msg", "扫描完成"))


@AiQueryRouter.get("/dq/alert", summary="DQ质量预警+下游影响联动")
async def dq_alert(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.dq_alert(), msg="查询成功")


# ---- 数据生命周期/删除策略（Palantir Data Lifetime） ----
@AiQueryRouter.get("/dl/list", summary="数据生命周期策略列表")
async def dl_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.dl_list(), msg="查询成功")


@AiQueryRouter.post("/dl/save", summary="保存数据生命周期策略")
async def dl_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.dl_save(data), msg="保存成功")


@AiQueryRouter.delete("/dl/remove", summary="删除数据生命周期策略")
async def dl_remove(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    ids: Annotated[list[int], Body(description="ID列表")],
) -> JSONResponse:
    await AiQueryService.dl_remove(ids)
    return SuccessResponse(msg="删除成功")


# ---- P3-⑨ 数据域隔离 ----
@AiQueryRouter.get("/domain/list", summary="数据域列表")
async def domain_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_domains(), msg="查询成功")


@AiQueryRouter.post("/domain/save", summary="数据域保存")
async def domain_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.upsert_domain(data)
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.delete("/domain/remove", summary="删除数据域")
async def domain_remove(id: int, auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))]) -> JSONResponse:
    await AiQueryService.delete_domain(id)
    return SuccessResponse(data=None, msg="已删除")


@AiQueryRouter.get("/domain/objects", summary="数据域隔离视图(对象按域分组)")
async def domain_objects(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.domain_objects(), msg="查询成功")


@AiQueryRouter.get("/domain/reconcile", summary="数据域对象对账(未登记标出)")
async def domain_reconcile(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.domain_reconcile(), msg="查询成功")


# ---- P3-⑩ 治理驾驶舱 ----
# 注意：这两个接口会**创建/改写本体对象与属性**（写操作），因此权限必须是
# `module_ai:ontology:edit`，不能沿用问答的只读权限 `module_ai:query:ask`
# ——否则「能问数」就等于「能改本体」（越权写入）。
@AiQueryRouter.post("/ontology/import-from-ds", summary="数据源连接器→本体对象(把外部表结构生成本体对象)")
async def import_ds_as_ontology(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:ontology:edit"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.import_ds_table_as_ontology(
        int(data.get("datasource_id", 0)), str(data.get("table", "")),
        domain_code=str(data.get("domain_code", "")))
    return SuccessResponse(data=r, msg=r.get("msg", "已导入"))


@AiQueryRouter.post("/ontology/import-from-ds/batch", summary="数据源连接器→本体对象(批量,默认排除纯技术表)")
async def import_ds_as_ontology_batch(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:ontology:edit"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.import_ds_tables_as_ontology(
        int(data.get("datasource_id", 0)),
        tables=data.get("tables"),
        include_technical=bool(data.get("include_technical", False)),
        domain_code=str(data.get("domain_code", "")),
    )
    msg = f"已导入 {r.get('imported', 0)} 个本体对象" if r.get("ok") else r.get("msg", "导入失败")
    return SuccessResponse(data=r, msg=msg)


@AiQueryRouter.get("/governance/overview", summary="治理驾驶舱总览")
async def governance_overview(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.governance_overview(), msg="查询成功")


@AiQueryRouter.get("/ontology/governance", summary="本体对象治理(血缘+数据质量)")
async def ontology_governance(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.ontology_governance(), msg="查询成功")


@AiQueryRouter.post("/access/save", summary="ABAC权限策略保存")
async def access_save(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    r = await AiQueryService.upsert_access_rule(data)
    return SuccessResponse(data=r, msg="保存成功")


@AiQueryRouter.delete("/access/remove", summary="删除ABAC权限策略")
async def access_remove(id: int, auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))]) -> JSONResponse:
    await AiQueryService.delete_access_rule(id)
    return SuccessResponse(data=None, msg="已删除")


@AiQueryRouter.get("/assets/kg/stats", summary="统一图谱统计(节点/边/实体/关系)")
async def kg_stats(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.kg_stats(), msg="查询成功")


@AiQueryRouter.get("/assets/kg/unified", summary="统一图谱(数据schema图+知识库图)")
async def kg_unified(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    kb_id: str | None = None,
    scope: str = "all",
) -> JSONResponse:
    from .agno_kg import unified_graph

    kb = None
    if kb_id and str(kb_id).isdigit():
        kb = int(kb_id)
    data = await unified_graph(kb, schema_only=scope == "schema",
                               knowledge_only=scope == "knowledge")
    return SuccessResponse(data=data, msg="查询成功")


@AiQueryRouter.get("/assets/kg/kbs", summary="知识库列表(供统一图谱选择)")
async def kg_kbs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    items = await AiKnowledgeService.list_bases()
    return SuccessResponse(data=[{"id": b["id"], "name": b["name"]} for b in items], msg="查询成功")


@AiQueryRouter.post("/assets/kg/relation", summary="新增自定义图谱关系")
async def kg_add_relation(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .agno_kg import add_relation

    r = await add_relation(str(data.get("source", "")), str(data.get("target", "")),
                           str(data.get("rtype") or "关联"), int(data.get("weight") or 1))
    return SuccessResponse(data=r, msg="已新增关系")


@AiQueryRouter.delete("/assets/kg/relation", summary="删除自定义图谱关系")
async def kg_del_relation(
    source: str, target: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    from .agno_kg import delete_relation

    n = await delete_relation(source, target)
    return SuccessResponse(data={"deleted": n}, msg="已删除")


@AiQueryRouter.post("/assets/kg/layout", summary="保存图谱节点布局")
async def kg_save_layout(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .agno_kg import save_layout

    n = await save_layout(data.get("items") or [])
    return SuccessResponse(data={"saved": n}, msg="布局已保存")


@AiQueryRouter.post("/assets/kg/auto-link", summary="知识库实体↔schema表/字段自动打边")
async def kg_auto_link(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    from .agno_kg import auto_link_kb_schema

    n = await auto_link_kb_schema()
    return SuccessResponse(data={"linked": n}, msg="已自动打边")


@AiQueryRouter.post("/assets/kg/age-sync", summary="把schema图谱+自定义关系镜像进Apache AGE图库")
async def kg_age_sync(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    from .agno_kg import age_sync_schema_graph

    n = await age_sync_schema_graph()
    return SuccessResponse(data={"synced": n}, msg="已同步到 AGE 图库")


@AiQueryRouter.post("/assets/kg/traverse", summary="跨域多跳图查询(从节点出发经AGE图库)")
async def kg_traverse(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    from .agno_kg import traverse

    out = await traverse(str(data.get("start", "")), int(data.get("hops") or 2))
    return SuccessResponse(data=out, msg="查询成功")


# ---- 业务概念 ----
@AiQueryRouter.get("/concepts/list", summary="业务概念列表")
async def list_concepts(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.list_concepts(), msg="查询成功")


@AiQueryRouter.post("/concepts/save", summary="业务概念保存")
async def save_concept(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_concept(data, auth), msg="保存成功")


@AiQueryRouter.delete("/concepts/delete", summary="业务概念删除")
async def delete_concepts(
    ids: list[int],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_concepts(ids)
    return SuccessResponse(data=None, msg="已删除")


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


@AiQueryRouter.post("/assets/{table_name}/scan-sensitive", summary="敏感数据扫描器(识别PII/凭证并标记)")
async def scan_sensitive(
    table_name: str,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.scan_sensitive(table_name), msg="扫描完成")


@AiQueryRouter.post("/assets/save", summary="数据资产(表)保存")
async def save_query_asset(
    data: QueryAssetUpsert,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiQueryService.upsert_asset(data, auth), msg="保存成功")


@AiQueryRouter.post("/assets/batch-meta", summary="数据资产(表)批量维护中文名/业务域/描述")
async def batch_save_query_asset_meta(
    data: Annotated[dict, Body()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    r = await AiQueryService.batch_upsert_asset_meta(data.get("items") or [], auth)
    msg = f"已保存 {r.get('saved', 0)} 张表" if r.get("ok") else r.get("msg", "保存失败")
    return SuccessResponse(data=r, msg=msg)


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
    return SuccessResponse(data=await AiQueryService.list_messages(session_id, auth), msg="查询成功")


@AiQueryRouter.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(
    session_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:query:ask"]))],
) -> JSONResponse:
    await AiQueryService.delete_session(session_id, auth)
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
