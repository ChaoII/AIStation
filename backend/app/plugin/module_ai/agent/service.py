"""智能体服务：CRUD、分类与运行（绑定工作流或回退模型+提示词+工具）。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.knowledge.model import AiKnowledgeBaseModel
from app.plugin.module_ai.mcp.model import AiMcpServerModel
from app.plugin.module_ai.skill.model import AiSkillModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel

from .model import AiAgentCategoryModel, AiAgentModel

# 输入护栏（Guardrail，平台层）：空/超长/提示注入基础检测。返回 None 表示通过，否则返回错误文案。
_MAX_INPUT_LEN = 20000
_INJECTION_PATTERNS = (
    "忽略以上指令", "忽略之前的所有", "ignore all previous", "ignore the above",
    "你是", "system prompt", "system 提示", "你已经不是", "假装", "扮演系统",
    "你的系统提示是", "disregard", "now act as", "bypass", "jailbreak",
)


def _agent_guardrail(text: str) -> str | None:
    if not text or not text.strip():
        return "输入不能为空"
    if len(text) > _MAX_INPUT_LEN:
        return f"输入过长（{len(text)} 字符，上限 {_MAX_INPUT_LEN}）"
    low = text.lower()
    for p in _INJECTION_PATTERNS:
        if p in low:
            return "检测到疑似提示注入/越权指令，已拦截"
    return None


async def _validate_agent_bindings(
    db,
    *,
    tool_ids: list[str] | None = None,
    skill_ids: list[int] | None = None,
    knowledge_ids: list[int] | None = None,
    mcp_ids: list[int] | None = None,
    user_id: int,
) -> None:
    """校验智能体绑定的资产，防止跨用户绑定与绑定不存在资产。

    - ``tool_ids``（平台共享，按名）：须存在、未删、启用；
    - ``skill_ids`` / ``knowledge_ids``（共享）：须存在、未删；
    - ``mcp_ids``（用户私有）：须存在、未删、``created_id == 当前用户``。
    """
    if tool_ids:
        rows = (
            await db.execute(
                select(AiToolModel.name).where(
                    AiToolModel.name.in_(tool_ids),
                    AiToolModel.is_deleted.is_(False),
                    AiToolModel.enabled.is_(True),
                )
            )
        ).scalars().all()
        missing = [n for n in tool_ids if n not in rows]
        if missing:
            raise CustomException(msg=f"绑定的工具不存在或未启用：{', '.join(missing)}")
    if skill_ids:
        rows = (
            await db.execute(
                select(AiSkillModel.id).where(
                    AiSkillModel.id.in_(skill_ids),
                    AiSkillModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        missing = [i for i in skill_ids if i not in rows]
        if missing:
            raise CustomException(msg=f"绑定的技能不存在：{missing}")
    if knowledge_ids:
        rows = (
            await db.execute(
                select(AiKnowledgeBaseModel.id).where(
                    AiKnowledgeBaseModel.id.in_(knowledge_ids),
                    AiKnowledgeBaseModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        missing = [i for i in knowledge_ids if i not in rows]
        if missing:
            raise CustomException(msg=f"绑定的知识库不存在：{missing}")
    if mcp_ids:
        rows = (
            await db.execute(
                select(AiMcpServerModel.id, AiMcpServerModel.created_id).where(
                    AiMcpServerModel.id.in_(mcp_ids),
                    AiMcpServerModel.is_deleted.is_(False),
                )
            )
        ).all()
        owner_map = {r[0]: r[1] for r in rows}
        bad = [i for i in mcp_ids if i not in owner_map or owner_map[i] != user_id]
        if bad:
            raise CustomException(msg=f"绑定的 MCP 服务器不存在或不属于当前用户：{bad}")


def _to_dict(a: AiAgentModel) -> dict:
    return {
        "id": a.id,
        "agent_name": a.agent_name,
        "category_id": a.category_id,
        "agent_role": a.agent_role or "",
        "description": a.description or "",
        "model_id": a.model_id,
        "prompt_id": a.prompt_id,
        "temperature": a.temperature,
        "workflow_id": a.workflow_id,
        "tool_ids": a.tool_ids or [],
        "skill_ids": a.skill_ids or [],
        "knowledge_ids": a.knowledge_ids or [],
        "mcp_ids": a.mcp_ids or [],
        "query_enabled": getattr(a, "query_enabled", False),
        "query_datasource": getattr(a, "query_datasource", None) or "system",
        "capabilities": getattr(a, "capabilities", None) or [],
        "input_schema": a.input_schema,
        "avatar": a.avatar or "",
        "color": a.color or "",
        "markdown": a.markdown,
        "enabled": a.enabled,
        "order": a.order or 0,
        "uuid": a.uuid,
        "created_time": a.created_time,
        "updated_time": a.updated_time,
    }


def _cat_dict(c: AiAgentCategoryModel) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "parent_id": c.parent_id,
        "sort": c.sort or 0,
    }


class AiAgentService:

    @classmethod
    async def count_agents(cls) -> int:
        """未删除的智能体数量（控制台/看板跨模块取数入口，不暴露模型）。"""
        async with async_db_session() as db:
            return int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(AiAgentModel)
                        .where(AiAgentModel.is_deleted.is_(False))
                    )
                ).scalar()
                or 0
            )

    @classmethod
    async def agent_templates(cls) -> list[dict]:
        """Agent 市场模板：预置常用 Agent，一键创建。"""
        return [
            {"key": "query_assistant", "name": "问数助手", "role": "数据问数助手",
             "description": "可对系统数据进行自然语言问数（本体驱动）",
             "query_enabled": True, "query_datasource": "system",
             "capabilities": ["query", "grounding"], "prompt": "你是数据问数助手，回答数据问题。"},
            {"key": "knowledge_assistant", "name": "知识库助手", "role": "知识库问答助手",
             "description": "基于知识库回答（RAG）",
             "query_enabled": False, "capabilities": ["knowledge"],
             "prompt": "你是知识库问答助手，基于知识库内容回答。"},
            {"key": "general_assistant", "name": "通用助手", "role": "通用 AI 助手",
             "description": "通用对话助手",
             "query_enabled": False, "capabilities": [],
             "prompt": "你是通用 AI 助手。"},
        ]

    @classmethod
    async def create_from_template(cls, key: str, name: str, auth) -> dict:
        """从模板一键创建 Agent。"""
        from types import SimpleNamespace as SN
        tpl = next((t for t in await cls.agent_templates() if t["key"] == key), None)
        if not tpl:
            raise ValueError("模板不存在")
        data = SN(
            agent_name=name or tpl["name"], category_id=None,
            agent_role=tpl.get("role") or "", description=tpl.get("description") or "",
            model_id=None, prompt_id=None, temperature=0.3, workflow_id=None,
            tool_ids=[], skill_ids=[], knowledge_ids=[],
            query_enabled=tpl.get("query_enabled", False),
            query_datasource=tpl.get("query_datasource", "system"),
            input_schema={}, avatar="", color="", markdown=False, enabled=True, order=0,
        )
        return await cls.create(data, auth)

    # ---------------------------------------------------------------- #
    # 分类
    # ---------------------------------------------------------------- #
    @classmethod
    async def list_categories(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiAgentCategoryModel)
                    .where(AiAgentCategoryModel.is_deleted.is_(False))
                    .order_by(AiAgentCategoryModel.sort.asc(), AiAgentCategoryModel.id.asc())
                )
            ).scalars().all()
            return [_cat_dict(c) for c in rows]

    @classmethod
    async def create_category(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            c = AiAgentCategoryModel(
                name=data.name,
                parent_id=data.parent_id,
                sort=data.sort or 0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(c)
            await db.flush()
            return _cat_dict(c)

    @classmethod
    async def update_category(cls, cat_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            c = await db.get(AiAgentCategoryModel, cat_id)
            if not c or c.is_deleted:
                return None
            for key in ("name", "parent_id", "sort"):
                if getattr(data, key) is not None:
                    setattr(c, key, getattr(data, key))
            c.updated_id = auth.user.id
            await db.flush()
            return _cat_dict(c)

    @classmethod
    async def delete_category(cls, cat_id: int) -> None:
        async with async_db_session.begin() as db:
            c = await db.get(AiAgentCategoryModel, cat_id)
            if c:
                await db.delete(c)

    # ---------------------------------------------------------------- #
    # 智能体
    # ---------------------------------------------------------------- #
    @classmethod
    async def list_agents(cls, category_id: int | None = None) -> list[dict]:
        async with async_db_session() as db:
            stmt = select(AiAgentModel).where(AiAgentModel.is_deleted.is_(False))
            if category_id is not None:
                stmt = stmt.where(AiAgentModel.category_id == category_id)
            rows = (
                await db.execute(
                    stmt.order_by(AiAgentModel.order.asc(), AiAgentModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(a) for a in rows]

    @classmethod
    async def get_agent(cls, agent_id: int) -> dict | None:
        async with async_db_session() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a or a.is_deleted:
                return None
            return _to_dict(a)

    @classmethod
    async def create(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            a = AiAgentModel(
                agent_name=data.agent_name,
                category_id=data.category_id,
                agent_role=data.agent_role or "",
                description=getattr(data, "description", None),
                model_id=data.model_id,
                prompt_id=data.prompt_id,
                temperature=data.temperature,
                workflow_id=data.workflow_id,
                tool_ids=data.tool_ids or [],
                skill_ids=data.skill_ids or [],
                knowledge_ids=data.knowledge_ids or [],
                mcp_ids=getattr(data, "mcp_ids", None) or [],
                capabilities=getattr(data, "capabilities", None) or [],
                query_enabled=data.query_enabled,
                query_datasource=data.query_datasource or "system",
                input_schema=data.input_schema,
                avatar=data.avatar or "",
                color=data.color or "",
                markdown=data.markdown,
                enabled=data.enabled,
                order=data.order or 0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            await _validate_agent_bindings(
                db,
                tool_ids=data.tool_ids or [],
                skill_ids=data.skill_ids or [],
                knowledge_ids=data.knowledge_ids or [],
                mcp_ids=getattr(data, "mcp_ids", None) or [],
                user_id=auth.user.id,
            )
            db.add(a)
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def update(cls, agent_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a or a.is_deleted:
                return None
            for key in (
                "agent_name", "category_id", "agent_role", "description", "model_id",
                "prompt_id", "temperature", "workflow_id", "tool_ids", "skill_ids",
                "knowledge_ids", "mcp_ids", "query_enabled", "query_datasource", "input_schema",
                "capabilities", "avatar", "color", "markdown", "enabled", "order",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(a, key, val)
            await _validate_agent_bindings(
                db,
                tool_ids=data.tool_ids if getattr(data, "tool_ids", None) is not None else None,
                skill_ids=data.skill_ids if getattr(data, "skill_ids", None) is not None else None,
                knowledge_ids=data.knowledge_ids if getattr(data, "knowledge_ids", None) is not None else None,
                mcp_ids=data.mcp_ids if getattr(data, "mcp_ids", None) is not None else None,
                user_id=auth.user.id,
            )
            a.updated_id = auth.user.id
            await db.flush()
            return _to_dict(a)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for aid in ids:
                a = await db.get(AiAgentModel, aid)
                if a:
                    await db.delete(a)

    @classmethod
    async def batch_status(cls, ids: list[int], enabled: bool, auth) -> int:
        """批量启用/停用智能体。"""
        async with async_db_session.begin() as db:
            count = 0
            for aid in ids:
                a = await db.get(AiAgentModel, aid)
                if a and not a.is_deleted:
                    a.enabled = enabled
                    a.updated_id = getattr(getattr(auth, "user", None), "id", None)
                    count += 1
            return count

    @classmethod
    async def install_skill(cls, agent_id: int, skill_id: int, auth) -> bool | None:
        """把技能关联到智能体并返回 True；智能体不存在返回 None。"""
        async with async_db_session.begin() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a:
                return None
            skills = list(a.skill_ids or [])
            if skill_id not in skills:
                skills.append(skill_id)
            a.skill_ids = skills
            a.updated_id = getattr(getattr(auth, "user", None), "id", None)
        return True

    @classmethod
    async def uninstall_skill(cls, agent_id: int, skill_id: int, auth) -> bool | None:
        """移除智能体上的技能并返回 True；智能体不存在返回 None。"""
        async with async_db_session.begin() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a:
                return None
            skills = list(a.skill_ids or [])
            if skill_id in skills:
                skills.remove(skill_id)
            a.skill_ids = skills
            a.updated_id = getattr(getattr(auth, "user", None), "id", None)
        return True

    @classmethod
    async def run_ui_stream(
        cls,
        agent_id: int,
        ui_messages: list[dict],
        auth,
        variables: dict | None = None,
        session_id: int | None = None,
    ) -> AsyncIterator[str]:
        """运行智能体：绑定工作流则走编排引擎，否则回退模型+提示词+工具。"""
        agent = await cls.get_agent(agent_id)
        if not agent or not agent.get("enabled"):
            # 没有 agent 也要产出终止帧，保持协议一致
            from app.plugin.module_ai.streaming import UiMessageStream

            ms = UiMessageStream()
            empty_finish = {"reply": "", "tool_calls": [], "action": None, "report_id": None}
            yield ms.start()
            yield ms.error("智能体不存在或未启用")
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
            return

        if agent.get("workflow_id"):
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            async for frame in AiWorkflowService.run_ui_stream(
                agent["workflow_id"], ui_messages, auth, variables, session_id
            ):
                yield frame
            return

        # 回退：复用应用运行逻辑（模型+提示词+工具）

        from app.plugin.module_ai.apps.service import _build_app_tools, _merge_variables
        from app.plugin.module_ai.assistant.service import (
            SYSTEM_PROMPT,
            last_user_text,
        )
        from app.plugin.module_ai.models.service import AiModelService
        from app.plugin.module_ai.overview.service import AiOverviewService
        from app.plugin.module_ai.prompts.service import AiPromptService, render_prompt
        from app.plugin.module_ai.sessions.service import persist_session_exchange
        from app.plugin.module_ai.streaming import UiMessageStream

        ms = UiMessageStream()
        t0 = time.perf_counter()
        uid = getattr(getattr(auth, "user", None), "id", None)
        user_text = last_user_text(ui_messages)
        # Guardrail：输入安全校验（空/超长/提示注入）
        _gap = _agent_guardrail(user_text)
        if _gap:
            yield ms.start()
            yield ms.error(_gap)
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
            return
        empty_finish = {"reply": "", "tool_calls": [], "action": None, "report_id": None}
        state: dict = {
            "assistant_text": "", "reply": "", "tool_calls": [],
            "action": None, "report_id": None, "error": None,
        }
        yield ms.start()
        try:
            system_prompt = SYSTEM_PROMPT
            if agent.get("prompt_id"):
                prompt = await AiPromptService.get_prompt(agent["prompt_id"])
                if prompt:
                    values = _merge_variables(agent.get("input_schema"), variables)
                    rendered = render_prompt(prompt.get("blocks"), values)
                    if rendered:
                        system_prompt = rendered

            # 注入绑定技能：构建 agno Skills 实例（脚本落临时目录，由 agno run_script 执行）
            agno_skills = None
            skill_cleanup = None
            if agent.get("skill_ids"):
                from app.plugin.module_ai.skill.agno_skills import build_agno_skills
                from app.plugin.module_ai.skill.service import AiSkillService

                bound = await AiSkillService.get_skills_by_ids(agent["skill_ids"])
                agno_skills, skill_cleanup = build_agno_skills(bound)

            # 注入启用的能力插件说明（平台级开关，如网页抓取/表格导出）
            try:
                from app.plugin.module_ai.plugins.service import PluginService

                plugins = await PluginService.enabled_plugins()
                if plugins:
                    plugin_lines = [
                        f"- {p['label']}（{p['key']}）：{p['description']}"
                        for p in plugins
                    ]
                    system_prompt = (
                        f"{system_prompt}\n\n## 已启用能力插件\n"
                        "平台已启用以下能力插件，在合适场景可使用：\n" + "\n".join(plugin_lines)
                    )
            except Exception:  # noqa: BLE001  插件说明注入失败不影响运行
                pass

            # 选中的本体函数/动作编码（直接选择即授予，无「能力」抽象）
            ont_codes = agent.get("capabilities") or []

            # 注入知识库检索上下文（RAG，阶段3）
            if agent.get("knowledge_ids"):
                from app.plugin.module_ai.knowledge.service import retrieve as kb_retrieve

                kb_context = await kb_retrieve(
                    agent["knowledge_ids"], user_text, top_k=5
                )
                if kb_context:
                    system_prompt = (
                        f"{system_prompt}\n\n"
                        "## 参考知识库\n"
                        "以下是检索到的相关知识，回答时优先引用并在合适处以 [来源] 标注：\n"
                        f"{kb_context}"
                    )

            runtime = None
            if agent.get("model_id"):
                runtime = await AiModelService.get_runtime_model(model_id=agent["model_id"])
            if not runtime:
                runtime = await AiModelService.get_runtime_model()
            if not runtime:
                state["error"] = "未配置大模型，请在 AI 管理→模型配置 中添加并启用"
                yield ms.error(state["error"])
                yield ms.data("finish", empty_finish)
                yield ms.finish()
                yield ms.done()
                return

            tool_names = list(agent.get("tool_ids") or [])
            # query_enabled：自动纳入问数 + 对象 grounding 工具
            if agent.get("query_enabled"):
                if "ai_query" not in tool_names:
                    tool_names.append("ai_query")
                if "resolve_object" not in tool_names:
                    tool_names.append("resolve_object")
            tool_schemas, http_tools = await _build_app_tools(tool_names)
            # 本体工具：① 接地（list_ontology，让 Agent 了解对象模型）；② 选中的本体函数/动作
            from app.plugin.module_ai.ontology.agent_tools import (
                ONTOLOGY_TOOL_SCHEMAS,
                build_selected_ontology_tools,
            )

            grounding = [
                s for s in ONTOLOGY_TOOL_SCHEMAS if s["function"]["name"] == "list_ontology"
            ]
            # P4：按调用者权限过滤本体工具（看不到的资源不生成工具）
            _uid = getattr(getattr(auth, "user", None), "id", None)
            sel_schemas, sel_names = await build_selected_ontology_tools(ont_codes, _uid)
            tool_schemas = list(tool_schemas) + grounding + sel_schemas

            async def _dispatch(name: str, args: dict, user_id: int | None):
                from app.plugin.module_ai.ontology.agent_tools import (
                    ONTOLOGY_TOOL_NAMES,
                    run_ontology_tool,
                    run_selected_ontology_tool,
                )

                if name in ONTOLOGY_TOOL_NAMES:
                    return await run_ontology_tool(name, args, user_id)
                if name in sel_names:
                    return await run_selected_ontology_tool(name, args, user_id)
                from app.plugin.module_ai.apps.service import _run_app_tool

                return await _run_app_tool(name, args, user_id, http_tools)

            # 设置当前 Agent 的问数数据源/场景上下文，供 ai_query 工具读取
            from app.plugin.module_ai.assistant.tools import QUERY_DS_CONTEXT

            ds_token = QUERY_DS_CONTEXT.set(agent.get("query_datasource") or "system")
            # MCP 工具：按 Agent 绑定的 mcp_ids 取用户自己的启用服务器（失败降级）
            mcp_tools: list = []
            if agent.get("mcp_ids"):
                from app.plugin.module_ai.mcp.service import McpService
                from app.plugin.module_ai.mcp.tools import build_mcp_tools

                servers = await McpService.enabled_servers(agent["mcp_ids"], uid)
                mcp_tools = build_mcp_tools(servers)
            try:
                from app.plugin.module_ai.assistant.agno_service import run_agno_tool_stream

                async for frame in run_agno_tool_stream(
                    model_config=runtime,
                    system_prompt=system_prompt,
                    tool_schemas=tool_schemas,
                    dispatch=_dispatch,
                    user_text=user_text,
                    user_id=uid,
                    session_id=session_id,
                    name="aistation_agent",
                    description=f"AIStation 智能体：{agent.get('agent_name') or '智能体'}",
                    mcp_tools=mcp_tools or None,
                    state=state,
                    skills=agno_skills,
                ):
                    yield frame
            finally:
                if skill_cleanup:
                    skill_cleanup()  # 删除技能脚本临时目录
                QUERY_DS_CONTEXT.reset(ds_token)
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)
            yield ms.error(f"运行失败：{e}")
            yield ms.data("finish", empty_finish)
            yield ms.finish()
            yield ms.done()
        finally:
            await AiOverviewService.add_log(
                agent.get("agent_name", ""),
                "agent",
                int((time.perf_counter() - t0) * 1000),
                "success" if state["error"] is None else "error",
                state["error"],
                app_id=agent_id,
                user_id=uid,
            )
            await persist_session_exchange(
                session_id, user_text, state["assistant_text"],
                app_id=agent_id, user_id=uid,
            )

    # ---------------------------------------------------------------- #
    # Agent 编排运行看板
    # ---------------------------------------------------------------- #
    @classmethod
    async def agent_dashboard(cls) -> dict:
        """Agent 编排运行看板：每个 Agent 的运行量/错误率/延迟 + 绑定工具技能能力矩阵。"""
        stats: dict[int, dict] = {}
        try:
            # 经 logs_center 的取数接口，不直读 ai_call_logs（守卫见 test_call_logs_ownership）
            from app.plugin.module_ai.logs_center.service import AiLogService
            stats = await AiLogService.stats_by_app("agent")
        except Exception:  # noqa: BLE001
            stats = {}
        agents = await cls.list_agents()
        out = []
        for a in agents:
            s = stats.get(a["id"], {"runs": 0, "errors": 0, "avg_latency": 0})
            out.append({
                "id": a["id"], "name": a["agent_name"], "role": a["agent_role"] or "",
                "enabled": a["enabled"], "workflow_id": a["workflow_id"],
                "tools": len(a["tool_ids"] or []), "skills": len(a["skill_ids"] or []),
                "knowledge": len(a["knowledge_ids"] or []),
                "capabilities": a.get("capabilities") or [],
                "runs": s["runs"], "errors": s["errors"], "avg_latency": s["avg_latency"],
                "error_rate": round(s["errors"] / s["runs"], 4) if s["runs"] else 0,
            })
        return {"agents": out, "total_agents": len(out),
                "enabled_agents": sum(1 for x in out if x["enabled"]),
                "total_runs": sum(x["runs"] for x in out)}

    # ---------------------------------------------------------------- #
    # 多智能体协作编排
    # ---------------------------------------------------------------- #
    @classmethod
    async def orchestrate(cls, question: str) -> dict:
        """多智能体协作编排（AIP Multi-Agent）：分解问题为子任务，按本体能力匹配可参与智能体。"""
        agents = await cls.list_agents()
        q = (question or "")

        # capabilities 同时承载「功能标志」与「本体能力编码」：
        # 任何不属于功能标志的条目，都视为该智能体挂载了本体函数/动作，即具备数据问答能力。
        feature_flags = {"query", "grounding", "knowledge", "general"}

        def _has_ontology_cap(caps: list[str]) -> bool:
            return any(c not in feature_flags for c in caps)

        intent = (
            "query" if any(k in q for k in ("多少", "统计", "数据", "个数", "数量", "分析", "表", "查询", "列出", "哪些", "几", "告警", "摄像头", "订单"))
            else "knowledge" if any(k in q for k in ("知识", "文档", "说明", "什么是", "介绍", "制度", "规范"))
            else "general"
        )
        if intent == "query":
            steps = [
                {"task": "解析问题并确定数据源/业务域范围", "capability": "query"},
                {"task": "映射本体对象与字段，生成并执行数据检索", "capability": "query"},
                {"task": "校验结果，汇总生成自然语言回答", "capability": "query"},
            ]
        elif intent == "knowledge":
            steps = [
                {"task": "检索相关知识库片段（RAG）", "capability": "knowledge"},
                {"task": "基于知识库回答并标注来源", "capability": "knowledge"},
            ]
        else:
            steps = [
                {"task": "理解意图并确定回答策略", "capability": "general"},
                {"task": "生成回答（可调用工具增强）", "capability": "general"},
            ]
        matched = []
        for a in agents:
            if not a.get("enabled"):
                continue
            caps_now = [str(c).lower() for c in (a.get("capabilities") or [])]
            if intent == "query" and (
                "query" in caps_now or "grounding" in caps_now or _has_ontology_cap(caps_now)
            ):
                matched.append({"id": a["id"], "name": a["agent_name"],
                                "role": a["agent_role"] or "", "match": "query"})
            elif intent == "knowledge" and "knowledge" in caps_now:
                matched.append({"id": a["id"], "name": a["agent_name"],
                                "role": a["agent_role"] or "", "match": "knowledge"})
        return {"intent": intent, "question": q, "steps": steps, "agents_involved": matched}
