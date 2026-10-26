"""智能体控制器：分类 + 实体 CRUD + 流式运行。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.assistant.agno_service import agno_stream_response

from .schema import (
    AiAgentCreateSchema,
    AiAgentRunSchema,
    AiAgentSkillBindSchema,
    AiAgentUpdateSchema,
)
from .service import AiAgentService

AiAgentRouter = APIRouter(route_class=OperationLogRoute, prefix="/agents", tags=["AI-智能体"])


# Agent 市场（模板一键创建）
@AiAgentRouter.get("/templates", summary="Agent 市场模板列表")
async def agent_templates(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.agent_templates(), msg="查询成功")


@AiAgentRouter.post("/create-from-template", summary="从模板一键创建 Agent")
async def create_from_template(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    a = await AiAgentService.create_from_template(str(data.get("key", "")), str(data.get("name", "")), auth)
    return SuccessResponse(data=a, msg="创建成功")


# ---------------------------------------------------------------- #
# 智能体
# ---------------------------------------------------------------- #
@AiAgentRouter.get("/list", summary="智能体列表")
async def list_agents(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
    category_id: int | None = None,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiAgentService.list_agents(category_id), msg="查询成功"
    )


@AiAgentRouter.get("/office", summary="AI 办公室：在岗智能体与运行状态")
async def office_agents(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.office_view(), msg="查询成功")


@AiAgentRouter.post("/office/dispatch", summary="AI 办公室：把任务交给组长（agno Team 协同）")
async def office_dispatch(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:dispatch"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    return SuccessResponse(
        data=await AiAgentService.office_dispatch(str(data.get("text") or ""), uid),
        msg="已交给组长",
    )


@AiAgentRouter.get("/office/runs", summary="AI 办公室：任务列表（按天筛选 + 分页，可点开看步骤）")
async def office_runs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:query"]))],
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
    date: Annotated[str | None, Query(description="只看某一天 YYYY-MM-DD")] = None,
    days: Annotated[int, Query(ge=1, le=365, description="不传 date 时看最近几天")] = 30,
    agent_name: Annotated[str | None, Query(description="只看参与过该成员的派活")] = None,
    status: Annotated[str | None, Query(description="ok / error / running")] = None,
) -> JSONResponse:
    from app.plugin.module_ai.logs_center.run_steps import list_runs

    return SuccessResponse(
        data=await list_runs(page_no, page_size, date, days, agent_name, status),
        msg="查询成功",
    )


@AiAgentRouter.post("/office/memory/clear", summary="AI 办公室：清空上下文记忆（最近几轮问答）")
async def office_memory_clear(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:dispatch"]))],
) -> JSONResponse:
    from app.plugin.module_ai.agent import office_memory

    uid = getattr(getattr(auth, "user", None), "id", None)
    await office_memory.clear(uid)
    return SuccessResponse(msg="已清空")


@AiAgentRouter.get("/office/steps", summary="AI 办公室：执行步骤时间线（规划/工具/回话/汇总）")
async def office_steps(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:query"]))],
    run_id: Annotated[str | None, Query(description="一次派活的 run_id")] = None,
    agent_id: Annotated[int | None, Query(description="只看某个人")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="条数")] = 60,
) -> JSONResponse:
    from app.plugin.module_ai.logs_center.run_steps import list_steps

    return SuccessResponse(data=await list_steps(run_id, agent_id, limit), msg="查询成功")


@AiAgentRouter.get("/office/summary", summary="AI 办公室：今日简报（派活次数/参与人数/谁最忙）")
async def office_summary(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.office_summary(), msg="查询成功")


@AiAgentRouter.post("/office/dispatch/stream", summary="AI 办公室：组长派活（流式：谁派给谁、谁回了什么）")
async def office_dispatch_stream(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:dispatch"]))],
    data: Annotated[dict, Body()],
):
    """SSE 帧：``data: {"type": "delegate" | "reply" | "start" | "done", ...}``。

    办公室据此在运行过程中弹出「组长 → 组员」的对话气泡，而不是等结束后一次性亮。
    """
    import json

    uid = getattr(getattr(auth, "user", None), "id", None)
    text = str(data.get("text") or "")

    async def _gen():
        try:
            async for frame in AiAgentService.office_dispatch_stream(text, uid):
                yield f"data: {json.dumps(frame, ensure_ascii=False, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield "data: " + json.dumps(
                {"type": "done", "ok": False, "error": str(e)[:200]}, ensure_ascii=False
            ) + "\n\n"

    from app.core.sse import sse_response

    return sse_response(_gen(), extra_headers={"Connection": "keep-alive"})


@AiAgentRouter.post("/office/dispatch/{agent_id}", summary="AI 办公室：点名给某个智能体派活")
async def office_dispatch_one(
    agent_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:dispatch"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    uid = getattr(getattr(auth, "user", None), "id", None)
    return SuccessResponse(
        data=await AiAgentService.office_dispatch_one(agent_id, str(data.get("text") or ""), uid),
        msg="已派给他",
    )


@AiAgentRouter.get("/dashboard", summary="Agent 编排运行看板(运行量/错误率/延迟+绑定矩阵)")
async def agent_dashboard(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiAgentService.agent_dashboard(), msg="查询成功"
    )


@AiAgentRouter.post("/orchestrate", summary="多智能体协作编排(分解问题+匹配智能体)")
async def agent_orchestrate(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiAgentService.orchestrate(data.get("question", "")), msg="查询成功"
    )


@AiAgentRouter.get("/detail/{agent_id}", summary="智能体详情")
async def get_agent(
    agent_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    data = await AiAgentService.get_agent(agent_id)
    if not data:
        return ErrorResponse(msg="智能体不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiAgentRouter.post("/create", summary="新增智能体")
async def create_agent(
    data: AiAgentCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.create(data, auth), msg="创建成功")


@AiAgentRouter.put("/update/{agent_id}", summary="编辑智能体")
async def update_agent(
    agent_id: int,
    data: AiAgentUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    result = await AiAgentService.update(agent_id, data, auth)
    if not result:
        return ErrorResponse(msg="智能体不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiAgentRouter.delete("/delete", summary="删除智能体")
async def delete_agents(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:delete"]))],
) -> JSONResponse:
    await AiAgentService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiAgentRouter.put("/batch/status", summary="批量启用/停用智能体")
async def batch_agent_status(
    body: dict,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    ids = [int(x) for x in (body.get("ids") or [])]
    enabled = bool(body.get("enabled"))
    count = await AiAgentService.batch_status(ids, enabled, auth)
    return SuccessResponse(
        data={"count": count}, msg=f"已{'启用' if enabled else '停用'} {count} 个智能体"
    )


@AiAgentRouter.post("/{agent_id}/install-skill", summary="安装技能到智能体")
async def install_skill(
    agent_id: int,
    data: AiAgentSkillBindSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    ok = await AiAgentService.install_skill(agent_id, data.skill_id, auth)
    if ok is None:
        return ErrorResponse(msg="智能体不存在")
    from app.plugin.module_ai.skill.service import AiSkillService

    await AiSkillService.bump_install([data.skill_id], 1)
    return SuccessResponse(msg="安装成功")


@AiAgentRouter.post("/{agent_id}/uninstall-skill", summary="卸载智能体上的技能")
async def uninstall_skill(
    agent_id: int,
    data: AiAgentSkillBindSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    ok = await AiAgentService.uninstall_skill(agent_id, data.skill_id, auth)
    if ok is None:
        return ErrorResponse(msg="智能体不存在")
    from app.plugin.module_ai.skill.service import AiSkillService

    await AiSkillService.bump_install([data.skill_id], -1)
    return SuccessResponse(msg="卸载成功")


@AiAgentRouter.post("/{agent_id}/run/stream", summary="运行智能体（Agno 原生事件流）")
async def run_agent_stream(
    agent_id: int,
    data: AiAgentRunSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> StreamingResponse:
    return agno_stream_response(
        AiAgentService.run_ui_stream(
            agent_id, data.messages, auth, data.variables, data.session_id
        )
    )
