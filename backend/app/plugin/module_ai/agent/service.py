"""智能体服务：CRUD、分类与运行（绑定工作流或回退模型+提示词+工具）。"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from sqlalchemy import select

from app.core.database import async_db_session

from .model import AiAgentCategoryModel, AiAgentModel


async def _cap_names(caps: list[str]) -> list[str]:
    """本体能力 code → name（供 Agent 运行时注入能力上下文）。"""
    if not caps:
        return []
    try:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT code,name FROM ai_ont_capability WHERE code = ANY(:codes) AND is_deleted=false"),
                {"codes": caps})).fetchall()
        m = {r[0]: r[1] for r in rows}
        return [m.get(c, c) for c in caps]
    except Exception:  # noqa: BLE001
        return caps


async def _cap_types(caps: list[str]) -> set[str]:
    """本体能力 code → type（驱动工具分组：governance 等）。"""
    if not caps:
        return set()
    try:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            rows = (
                await db.execute(
                    _t(
                        "SELECT type FROM ai_ont_capability WHERE code = ANY(:codes) AND is_deleted=false"
                    ),
                    {"codes": caps},
                )
            ).fetchall()
        return {str(r[0]) for r in rows if r[0]}
    except Exception:  # noqa: BLE001
        return set()


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

            # 注入绑定技能内容（技能广场，skill_type=instruction 直接并入系统提示词）
            if agent.get("skill_ids"):
                from app.plugin.module_ai.skill.service import AiSkillService

                skills = await AiSkillService.get_skills_by_ids(agent["skill_ids"])
                skill_blocks = []
                for sk in skills:
                    if sk.get("content"):
                        skill_blocks.append(
                            f"### 技能：{sk.get('name')}\n{sk.get('content')}"
                        )
                if skill_blocks:
                    system_prompt = (
                        f"{system_prompt}\n\n"
                        "## 可调用技能\n"
                        "以下是已绑定技能的使用说明，在合适场景按说明执行：\n"
                        + "\n\n".join(skill_blocks)
                    )

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
                ):
                    yield frame
            finally:
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
        from sqlalchemy import func as _f
        from sqlalchemy import select as _sel
        stats: dict[int, dict] = {}
        try:
            from app.plugin.module_ai.overview.model import AiCallLogModel
            async with async_db_session() as db:
                rows = (await db.execute(
                    _sel(AiCallLogModel.app_id, _f.count().label("n"),
                         _f.count().filter(AiCallLogModel.result == "error").label("e"),
                         _f.avg(AiCallLogModel.latency_ms).label("lat"))
                    .where(AiCallLogModel.usage == "agent",
                           AiCallLogModel.app_id.isnot(None),
                           AiCallLogModel.is_deleted.is_(False))
                    .group_by(AiCallLogModel.app_id)
                )).fetchall()
            for r in rows:
                stats[int(r[0])] = {"runs": int(r[1] or 0), "errors": int(r[2] or 0),
                                    "avg_latency": int(r[3] or 0)}
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
