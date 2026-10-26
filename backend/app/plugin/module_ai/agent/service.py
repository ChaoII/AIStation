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

from .model import AiAgentModel

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
        "source_app_id": getattr(a, "source_app_id", None),
        "uuid": a.uuid,
        "created_time": a.created_time,
        "updated_time": a.updated_time,
    }


def _reply_text(v: str, n: int = 46) -> str:
    """组员的回话压成一行气泡文本；接口报错给人话。"""
    t = " ".join((v or "").split())
    low = t.lower()
    if "incorrect api key" in low or "unauthorized" in low or "invalid api key" in low:
        return "（没接上，接口鉴权失败）"
    if low.startswith("error") or "traceback" in low:
        return "（没接上，报错了）"
    return t if len(t) <= n else t[:n] + "…"


def got_names(targs) -> str:
    """把 delegate 工具参数里的成员标识拼成一个可 in 判断的字符串。"""
    try:
        parts = []
        for v in (targs or {}).values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, (list, tuple)):
                parts.extend(str(x) for x in v)
        return " ".join(parts)
    except Exception:  # noqa: BLE001
        return ""


async def _office_caps(
    row: dict, user_id: int | None, query_text: str
) -> dict:
    """装配办公室成员/组长的**真实能力**（与 Agent 运行台同一套链路）。

    - ``tool_ids``：平台自定义工具 / HTTP 工具 → 包装成 agno ``Function``
      （``agno_tools.dynamic.build_dynamic_tools``，执行走 ``_run_app_tool``）
    - ``skill_ids``：平台技能 → agno ``Skills``（脚本落临时目录，运行后清理）
    - ``knowledge_ids``：知识库 → 检索结果注入指令（RAG，与运行台一致）
    - ``mcp_ids``：用户自己的 MCP 服务器 → ``MCPTools``（连不上就跳过）

    返回 ``{"extra_tools": [...], "skills": ..., "kb": "...", "cleanup": fn|None}``。
    任何一项失败都只降级为「只有平台业务工具」，不影响派活本身。
    """
    out: dict = {"extra_tools": [], "skills": None, "kb": "", "cleanup": None}
    cleanups: list = []

    # 自定义 / HTTP 工具
    try:
        names = list(row.get("tool_ids") or [])
        if names:
            from app.plugin.module_ai.agno_tools.dynamic import build_dynamic_tools
            from app.plugin.module_ai.apps.service import _build_app_tools, _run_app_tool

            schemas, http_tools = await _build_app_tools(names)

            async def _dispatch(name: str, args: dict, uid: int | None):
                return await _run_app_tool(name, args, uid, http_tools)

            out["extra_tools"].extend(build_dynamic_tools(schemas, _dispatch))
    except Exception:  # noqa: BLE001
        pass

    # MCP 服务器
    try:
        if row.get("mcp_ids"):
            from app.plugin.module_ai.mcp.service import McpService
            from app.plugin.module_ai.mcp.tools import build_mcp_tools

            servers = await McpService.enabled_servers(row["mcp_ids"], user_id)
            out["extra_tools"].extend(build_mcp_tools(servers))
    except Exception:  # noqa: BLE001
        pass

    # 技能
    try:
        if row.get("skill_ids"):
            from app.plugin.module_ai.skill.agno_skills import build_agno_skills
            from app.plugin.module_ai.skill.service import AiSkillService

            bound = await AiSkillService.get_skills_by_ids(row["skill_ids"])
            skills, cleanup = build_agno_skills(bound)
            out["skills"] = skills
            if cleanup:
                cleanups.append(cleanup)
    except Exception:  # noqa: BLE001
        pass

    # 知识库（RAG）
    try:
        if row.get("knowledge_ids") and (query_text or "").strip():
            from app.plugin.module_ai.knowledge.service import retrieve as kb_retrieve

            out["kb"] = await kb_retrieve(row["knowledge_ids"], query_text, top_k=4) or ""
    except Exception:  # noqa: BLE001
        pass

    if cleanups:

        def _cleanup() -> None:
            for fn in cleanups:
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass

        out["cleanup"] = _cleanup
    return out


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
    # 智能体
    # ---------------------------------------------------------------- #
    @classmethod
    async def list_agents(
        cls, category_id: int | None = None, source_app_id: int | None = None
    ) -> list[dict]:
        """列出智能体。

        Args:
            category_id: 可选，按分类过滤。
            source_app_id: 可选，按**开放平台归属应用**过滤；传入时只返回该应用
                创建的智能体（内部用户创建的 ``source_app_id`` 为 ``None``，不会混入）。
        """
        async with async_db_session() as db:
            stmt = select(AiAgentModel).where(AiAgentModel.is_deleted.is_(False))
            if category_id is not None:
                stmt = stmt.where(AiAgentModel.category_id == category_id)
            if source_app_id is not None:
                stmt = stmt.where(AiAgentModel.source_app_id == source_app_id)
            rows = (
                await db.execute(
                    stmt.order_by(AiAgentModel.order.asc(), AiAgentModel.id.desc())
                )
            ).scalars().all()
            return [_to_dict(a) for a in rows]

    # ---------------------------------------------------------------- #
    @classmethod
    async def office_view(cls, active_minutes: int = 10) -> list[dict]:
        """AI 办公室：返回在岗智能体 + 运行状态 + 组长标记。

        状态口径（没有独立运行时状态表，用调用日志推导）：
        - 近 ``active_minutes`` 分钟内有 ``usage=agent`` 的调用 → ``busy``（工作中）
        - 否则 → ``idle``（在岗待命）
        - 停用/删除的智能体不返回（不占工位）

        组长（leader）：角色名含 主控/调度/组长/leader 的第一个；没有就取 ``order`` 最小的。
        办公室里的任务流转、汇报口径都以组长为起点/终点。

        取数一律走 ``logs_center``（``ai_call_logs`` 的读 owner），不直读表。
        """
        from datetime import datetime, timedelta

        last: dict[int, datetime] = {}
        try:
            from app.plugin.module_ai.logs_center.service import AiLogService

            last = await AiLogService.last_active_by_app("agent")
        except Exception:  # noqa: BLE001
            last = {}
        act: dict[int, dict] = {}
        try:
            from . import office_activity as _oa

            act = await _oa.active()
        except Exception:  # noqa: BLE001
            act = {}

        agents = [a for a in await cls.list_agents() if a.get("enabled")]
        now = datetime.now()
        window = timedelta(minutes=active_minutes)

        import re

        leader_id = None
        for a in agents:
            if re.search(r"主控|调度|组长|leader|总管", a.get("agent_role") or "", re.I):
                leader_id = a["id"]
                break
        if leader_id is None and agents:
            leader_id = agents[0]["id"]

        out: list[dict] = []
        for a in agents:
            t = last.get(a["id"])
            live = act.get(a["id"])
            busy = bool(t and (now - t) < window) or bool(live)
            out.append(
                {
                    "id": a["id"],
                    "name": a.get("agent_name") or a.get("name") or f"#{a['id']}",
                    "role": a.get("agent_role") or "",
                    "status": (
                        "error"
                        if (live or {}).get("status") == "error"
                        else ("busy" if busy else "idle")
                    ),
                    "is_leader": a["id"] == leader_id,
                    "task": (live or {}).get("task") or "",
                    "last_active": t.strftime("%Y-%m-%d %H:%M:%S") if t else None,
                    "category_id": a.get("category_id"),
                    "model_id": a.get("model_id"),
                }
            )
        return out

    @classmethod
    async def office_summary(cls) -> dict:
        """今日办公室简报：派活次数 / 参与人数 / 谁最忙 / 平均耗时。

        数据源是 ``ai_call_logs``（办公室的派活都记 ``usage=team|agent``），
        所以刷新、重开页面都还在，不依赖前端内存。
        """
        from datetime import datetime

        from app.plugin.module_ai.logs_center.service import AiLogService

        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        # 调用日志只由 logs_center 读（职责边界见 tests/test_call_logs_ownership.py）
        team_stats = await AiLogService.stats_by_app("team", since=start)
        agent_stats = await AiLogService.stats_by_app("agent", since=start)
        rows = [
            {"app_id": aid, "usage": "team", "n": v["runs"], "avg_ms": v["avg_latency"]}
            for aid, v in team_stats.items()
        ] + [
            {"app_id": aid, "usage": "agent", "n": v["runs"], "avg_ms": v["avg_latency"]}
            for aid, v in agent_stats.items()
        ]

        from app.plugin.module_ai.logs_center import run_steps as _rs

        try:
            runs_stats = await _rs.today_stats()
        except Exception as e:  # noqa: BLE001 统计失败不影响简报
            from app.core.logger import log as _log

            _log.warning(f"[office] 今日派活统计失败：{str(e)[:120]}")
            runs_stats = {"total": 0, "errors": 0, "error_rate": 0.0, "avg_ms": 0, "last_time": None}

        view = await cls.office_view()
        names = {a["id"]: a["name"] for a in view}

        total = sum(int(r["n"]) for r in rows)
        team = sum(int(r["n"]) for r in rows if r["usage"] == "team")
        agent = sum(int(r["n"]) for r in rows if r["usage"] == "agent")
        errors = sum(
            int(v.get("errors") or 0)
            for v in list(team_stats.values()) + list(agent_stats.values())
        )
        people = len({r["app_id"] for r in rows if r["app_id"]})
        avg_ms = 0
        if total:
            avg_ms = int(sum(float(r["avg_ms"] or 0) * int(r["n"]) for r in rows) / total)
        lasts = list((await AiLogService.last_active_by_app("team", since=start)).values())
        lasts += list((await AiLogService.last_active_by_app("agent", since=start)).values())
        last = max(lasts, default=None)

        per: dict[int, int] = {}
        for r in rows:
            if r["app_id"]:
                per[r["app_id"]] = per.get(r["app_id"], 0) + int(r["n"])
        top = sorted(
            (
                {"id": aid, "name": names.get(aid) or f"#{aid}", "count": n}
                for aid, n in per.items()
            ),
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        return {
            "date": start.strftime("%Y-%m-%d"),
            "total": total,
            "team": team,
            "agent": agent,
            "people": people,
            "avg_ms": avg_ms,
            "errors": errors,
            "error_rate": round(errors * 100 / total, 1) if total else 0.0,
            # 顶部统计条用的「派活」口径（按 run 聚合，和任务列表一致）
            "runs": runs_stats,
            "last_time": last.strftime("%H:%M") if last else None,
            "top": top,
        }

    @classmethod
    async def office_dispatch(cls, text: str, user_id: int | None = None) -> dict:
        """把一句话交给「组长」：用 agno ``Team(mode=coordinate)`` 派活并汇总口径。

        - 组长 = ``office_view`` 里 ``is_leader`` 的那个；组员 = 其余在岗智能体。
        - 走 agno 原生 Team：组长负责拆解/分派/汇总，成员只做自己那一段。
        - 调用日志记 ``usage="team"``、``app_id=组长 id``，办公室据此把组长点亮。
        """
        import time as _t

        if not text or not text.strip():
            return {"ok": False, "msg": "任务不能为空"}

        view = await cls.office_view()
        if not view:
            return {"ok": False, "msg": "办公室里没有在岗智能体"}
        leader = next((a for a in view if a.get("is_leader")), view[0])
        members = [a for a in view if a["id"] != leader["id"]]
        if not members:
            return {"ok": False, "msg": "只有组长，没有可派的组员"}

        # 每个 agent 的绑定能力（工具/技能/知识库/MCP）在 list_agents 的完整行里
        rows = {a["id"]: a for a in await cls.list_agents()}
        cleanups: list = []

        from agno.team import Team
        from agno.team.mode import TeamMode

        from app.plugin.module_ai.agno_tools.agent_factory import build_agent
        from app.plugin.module_ai.models.service import AiModelService
        from app.plugin.module_ai.overview.service import AiOverviewService

        async def _mk(a: dict):
            runtime = None
            try:
                if a.get("model_id"):
                    # 绑了具体模型就必须用它；模型被删/停用时不回退 env（否则会拿一个
                    # 无关的全局 key 去跑，报「鉴权失败」，把这个 agent 的配置问题藏起来）
                    runtime = await AiModelService.get_runtime_model(
                        model_id=a["model_id"], allow_env_fallback=False
                    )
                else:
                    runtime = await AiModelService.get_runtime_model()
            except Exception:  # noqa: BLE001
                runtime = None
            if runtime is None:
                # 模型被删 / 没绑可用的提供商：别让他上场（Team 会用空 model 跑出鉴权错误）
                from app.core.logger import logger

                logger.warning(
                    f"[office] 跳过「{a.get('name')}」：model_id={a.get('model_id')} 取不到运行模型"
                )
                return None
            # 该智能体绑定的真实能力：自定义工具 / 技能 / 知识库 / MCP
            caps = await _office_caps(rows.get(a["id"]) or {}, user_id, text)
            if caps["cleanup"]:
                cleanups.append(caps["cleanup"])
            instr = [
                f"你是「{a['name']}」，岗位：{a.get('role') or '通用'}。",
                "只做组长交给你的那一小段，并且**直接给出可用的结果**"
                "（一句结论 / 一个清单 / 一段文字）。",
                "需要系统数据时必须调用工具取数，禁止编造。",
                "问数量/统计时优先用 ai_query 或 get_*_overview 这类汇总工具；"
                "list_* 只用来确认「有没有/叫什么」，别拉全表（上限 50 行）。",
                "同一个工具拿到结果就往下走，不要反复重试同一个问题（最多换一种问法试一次）。",
                "不要复述任务、不要说明你打算怎么做、不要向用户提问、不要下最终结论。",
                "如果你确实做不到，就明确回一句「无法完成：原因」。",
            ]
            if caps["kb"]:
                instr.append(
                    "## 参考知识库\n"
                    "以下是检索到的相关资料，回答时优先引用，并在合适处标注来源：\n"
                    f"{caps['kb']}"
                )
            return build_agent(
                model_config=runtime,
                name=a["name"],
                description=a.get("role") or a["name"],
                instructions=instr,
                extra_tools=caps["extra_tools"] or None,
                skills=caps["skills"],
                user_id=user_id,
                tool_call_limit=3,
            )

        member_agents = []
        for m in members:
            member_agents.append(await _mk(m))

        # Team 本身也要模型（组长用来拆解/汇总）；不传会空跑返回空内容
        leader_runtime = None
        try:
            if leader.get("model_id"):
                leader_runtime = await AiModelService.get_runtime_model(model_id=leader["model_id"])
            else:
                leader_runtime = await AiModelService.get_runtime_model()
        except Exception:  # noqa: BLE001
            leader_runtime = None

        from app.plugin.module_ai.agno_tools.agent_factory import build_model

        # 上下文延续：最近几轮问答压成一段，写进组长指令（追问不用从头说）
        try:
            from . import office_memory as _om

            _hist = await _om.recent(user_id, limit=3)
            _hist_text = _om.as_prompt(_hist)
        except Exception:  # noqa: BLE001
            _hist_text = ""

        # 会话延续：同一个办公室（同一用户）沿用同一个 agno Team 会话，
        # 追问「那占比呢」时组长还记着上一轮派了谁、给了什么结论。
        # 运行态放 agno 自己的 sqlite（不占业务连接池），不可用时降级为无记忆。
        team_kwargs: dict = {}
        try:
            from app.plugin.module_ai.agno_tools.db import get_agno_db

            _adb = get_agno_db()
            if _adb is not None:
                team_kwargs = {
                    "db": _adb,
                    "session_id": f"office-team-{user_id or 0}",
                    "add_history_to_context": True,
                    "num_history_runs": 3,
                }
        except Exception:  # noqa: BLE001
            team_kwargs = {}
        if user_id:
            team_kwargs["user_id"] = str(user_id)

        _leader_instructions = [
            "你是这个 AI 办公室的组长，负责接活、派活、汇总。",
            "",
            "工作方式：",
            "1) 先判断：一句话能答的直接答；需要不同专长的，必须用 delegate_task_to_members "
            "派给对应组员，不要自己替他们做。",
            "2) 派活时写清交付要求：要什么、什么格式、多少字以内。",
            "3) **必须等组员返回具体内容后再汇总**。组员返回空或明显没做完时，"
            "重新派一次并说明上次的问题（最多重派一次）。",
            "4) 汇总只写最终结论，不罗列过程；用到谁的产出就标一句是谁给的。",
            "5) 组员最终仍没给出内容，就在结论里明确写「某某未返回」，"
            "**禁止编造成员没有提供的内容**。",
            "6) 用户通常**不会点名**让谁做（例如只说「帮我查一下本周各渠道订单量」）。"
            "这时你要根据每个组员的岗位描述**自己判断派给谁**，不要反问用户「派给谁」，"
            "也不要把所有组员都派一遍；只有用户明确点名时才按他说的派。",
            "7) 派活前先看一眼组员列表里的岗位（数据查询 / 文档写作 / 协作办公…），"
            "选最匹配的那一个；确实没人能做，就自己回答并在结论里说明。",
            "8) **一次只派一个人**：每轮只发一个 delegate_task_to_member，拿到他的结果后"
            "再决定下一步。像「先查数据、再写总结」这种有依赖的，必须把**具体数字/内容**"
            "写进下一次派活里；不要把两个人同时派出去（那样写总结的人手里没数据）。",
        ]
        if _hist_text:
            _leader_instructions.append(_hist_text)
            _leader_instructions.append(
                "遇到「刚才那个」「上面说的」这类追问，先用上面的历史回答，不要再说看不到上下文。"
            )

        team = Team(
            members=member_agents,
            model=build_model(leader_runtime),
            mode=TeamMode.coordinate,
            name=leader["name"],
            description=f"AI 办公室组长：{leader['name']}",
            tool_call_limit=4,
            **team_kwargs,
            instructions=_leader_instructions,
        )

        t0 = _t.perf_counter()
        ok, err, content = True, None, ""

        from . import office_activity as _oa

        brief = text.strip().replace("\n", " ")[:60]
        await _oa.mark(leader["id"], task=f"派单：{brief}", leader_id=leader["id"], ttl_seconds=300)
        name2id = {m["name"]: m["id"] for m in members if m.get("name")}
        chunks: list[str] = []
        # 平台业务工具（list_datasets 等）按 ContextVar 注入用户，工具内再做数据权限
        from app.plugin.module_ai.agno_tools.business import (
            reset_user_context,
            set_user_context,
        )

        _uid_token = set_user_context(user_id)
        try:
            res = team.arun(text, stream=True)
            if hasattr(res, "__aiter__"):
                async for ev in res:
                    # 成员事件带 agent_name（实测），优先按名字精确匹配；再退回文本扫描
                    ev_name = getattr(ev, "agent_name", None)
                    hit_ids = set()
                    if ev_name and ev_name in name2id:
                        hit_ids.add(name2id[ev_name])
                    else:
                        blob = ""
                        for attr in ("agent_name", "tool", "task", "content"):
                            v = getattr(ev, attr, None)
                            if v is not None:
                                blob += str(v)
                        if blob:
                            for nm, mid in name2id.items():
                                if nm and nm in blob:
                                    hit_ids.add(mid)
                    for mid in hit_ids:
                        await _oa.mark(
                            mid, task=f"组长派单：{brief}",
                            leader_id=leader["id"], ttl_seconds=180,
                        )
                    etype = str(getattr(ev, "event", "") or type(ev).__name__)
                    if "Content" in etype:
                        c = getattr(ev, "content", None)
                        if isinstance(c, str) and c:
                            chunks.append(c)
                content = "".join(chunks).strip()
            else:
                resp = await res
                content = getattr(resp, "content", None) or str(resp)
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
            _failed = True
        finally:
            reset_user_context(_uid_token)
            for _fn in cleanups:
                try:
                    _fn()
                except Exception:  # noqa: BLE001
                    pass

        await AiOverviewService.add_log(
            leader["name"],
            "team",
            int((_t.perf_counter() - t0) * 1000),
            "success" if ok else "error",
            err,
            app_id=leader["id"],
            user_id=user_id,
        )

        # 落一条会话：办公室里的派活也要能事后追溯（工作台可见）
        session_id = None
        try:
            from app.plugin.module_ai.sessions.service import (
                AiSessionService,
                persist_session_exchange,
            )

            title = f"[办公室] {text.strip()[:40]}"
            sess = await AiSessionService.create(title, app_id=leader["id"], user_id=user_id)
            session_id = sess.get("id")
            if ok and content:
                await persist_session_exchange(
                    session_id, text, content, app_id=leader["id"], user_id=user_id
                )
        except Exception as e:  # noqa: BLE001
            from app.core.logger import logger

            logger.warning(f"[office] 写入派活会话失败: {str(e)[:120]}")

        return {
            "ok": ok,
            "leader": leader["name"],
            "members": [m["name"] for m in members],
            "content": content,
            "error": err,
            "session_id": session_id,
        }

    @classmethod
    async def office_dispatch_stream(cls, text: str, user_id: int | None = None):
        """组长派活的**流式版**：把 Team 运行中「谁派给谁、谁回了什么」实时吐出来。

        为什么单独一个流式入口：办公室要的是"看得到沟通"——组长点名、组员回话，
        都必须发生在**运行过程中**，而不是结束后一次性返回。非流式版
        （``office_dispatch``）保持不动，供脚本/测试用。

        产出帧（dict）：
        - ``{"type": "start", "leader": ..., "members": [...]}``
        - ``{"type": "delegate", "from": 组长, "to": 组员, "task": "..."}``
        - ``{"type": "reply", "from": 组员, "text": "..."}``
        - ``{"type": "done", "ok": bool, "content": ..., "session_id": id}``
        """
        import json as _json
        import time as _t

        if not text or not text.strip():
            yield {"type": "done", "ok": False, "error": "任务不能为空"}
            return

        view = await cls.office_view()
        if not view:
            yield {"type": "done", "ok": False, "error": "办公室里没有在岗智能体"}
            return
        leader = next((a for a in view if a.get("is_leader")), view[0])
        members = [a for a in view if a["id"] != leader["id"]]
        if not members:
            yield {"type": "done", "ok": False, "error": "只有组长，没有可派的组员"}
            return

        # 每个 agent 的绑定能力（工具/技能/知识库/MCP）在 list_agents 的完整行里
        rows = {a["id"]: a for a in await cls.list_agents()}
        cleanups: list = []

        from agno.team import Team
        from agno.team.mode import TeamMode

        from app.plugin.module_ai.agno_tools.agent_factory import build_agent, build_model
        from app.plugin.module_ai.logs_center import tool_calls as _tc
        from app.plugin.module_ai.models.service import AiModelService
        from app.plugin.module_ai.overview.service import AiOverviewService

        from . import office_activity as _oa
        from . import office_memory as _om

        async def _mk(a: dict):
            runtime = None
            try:
                if a.get("model_id"):
                    # 绑了具体模型就必须用它；模型被删/停用时不回退 env（否则会拿一个
                    # 无关的全局 key 去跑，报「鉴权失败」，把这个 agent 的配置问题藏起来）
                    runtime = await AiModelService.get_runtime_model(
                        model_id=a["model_id"], allow_env_fallback=False
                    )
                else:
                    runtime = await AiModelService.get_runtime_model()
            except Exception:  # noqa: BLE001
                runtime = None
            if runtime is None:
                # 模型被删 / 没绑可用的提供商：别让他上场（Team 会用空 model 跑出鉴权错误）
                from app.core.logger import logger

                logger.warning(
                    f"[office] 跳过「{a.get('name')}」：model_id={a.get('model_id')} 取不到运行模型"
                )
                return None
            # 该智能体绑定的真实能力：自定义工具 / 技能 / 知识库 / MCP
            caps = await _office_caps(rows.get(a["id"]) or {}, user_id, text)
            if caps["cleanup"]:
                cleanups.append(caps["cleanup"])
            instr = [
                f"你是「{a['name']}」，岗位：{a.get('role') or '通用'}。",
                "只做组长交给你的那一小段，并且**直接给出可用的结果**"
                "（一句结论 / 一个清单 / 一段文字）。",
                "需要系统数据时必须调用工具取数，禁止编造。",
                "不要复述任务、不要说明你打算怎么做、不要向用户提问、不要下最终结论。",
                "如果你确实做不到，就明确回一句「无法完成：原因」。",
            ]
            if caps["kb"]:
                instr.append(
                    "## 参考知识库\n"
                    "以下是检索到的相关资料，回答时优先引用，并在合适处标注来源：\n"
                    f"{caps['kb']}"
                )
            return build_agent(
                model_config=runtime,
                name=a["name"],
                description=a.get("role") or a["name"],
                instructions=instr,
                extra_tools=caps["extra_tools"] or None,
                skills=caps["skills"],
                user_id=user_id,
                tool_call_limit=3,
            )

        member_agents = []
        usable: list[dict] = []
        for m in members:
            built = await _mk(m)
            if built is None:
                continue
            member_agents.append(built)
            usable.append(m)
        members = usable
        if not members:
            yield {"type": "done", "ok": False, "error": "组员都没有可用的模型配置"}
            return
        leader_runtime = None
        try:
            if leader.get("model_id"):
                leader_runtime = await AiModelService.get_runtime_model(model_id=leader["model_id"])
            else:
                leader_runtime = await AiModelService.get_runtime_model()
        except Exception:  # noqa: BLE001
            leader_runtime = None
        if leader_runtime is None:
            yield {"type": "done", "ok": False, "error": "组长没有可用的模型配置"}
            return

        # agno 原生会话（能落盘就用；落不了也不影响下面的提示词记忆）
        team_kwargs: dict = {}
        try:
            from app.plugin.module_ai.agno_tools.db import get_agno_db

            _adb = get_agno_db()
            if _adb is not None:
                team_kwargs = {
                    "db": _adb,
                    "session_id": f"office-team-{user_id or 0}",
                    "add_history_to_context": True,
                    "num_history_runs": 3,
                }
        except Exception:  # noqa: BLE001
            team_kwargs = {}
        if user_id:
            team_kwargs["user_id"] = str(user_id)

        # 上下文延续：最近几轮问答压成一段写进组长指令（追问才接得上）
        try:
            _hist = await _om.recent(user_id, limit=3)
        except Exception:  # noqa: BLE001
            _hist = []
        _hist_text = _om.as_prompt(_hist)

        _leader_instructions = [
            "你是这个 AI 办公室的组长，负责接活、派活、汇总。",
            "",
            "工作方式：",
            "1) 先判断：一句话能答的直接答；需要不同专长的，必须用 delegate_task_to_members "
            "派给对应组员，不要自己替他们做。",
            "2) 派活时写清交付要求：要什么、什么格式、多少字以内。",
            "3) **必须等组员返回具体内容后再汇总**。组员返回空或明显没做完时，"
            "重新派一次并说明上次的问题（最多重派一次）。",
            "4) 汇总只写最终结论，不罗列过程；用到谁的产出就标一句是谁给的。",
            "5) 组员最终仍没给出内容，就在结论里明确写「某某未返回」，"
            "**禁止编造成员没有提供的内容**。",
        ]
        if _hist_text:
            _leader_instructions.append(_hist_text)
            _leader_instructions.append(
                "遇到「刚才那个」「上面说的」这类追问，先用上面的历史回答，"
                "不要再声称看不到上下文。"
            )

        team = Team(
            members=member_agents,
            model=build_model(leader_runtime),
            mode=TeamMode.coordinate,
            name=leader["name"],
            description=f"AI 办公室组长：{leader['name']}",
            tool_call_limit=4,
            **team_kwargs,
            instructions=_leader_instructions,
        )

        brief = text.strip().replace("\n", " ")[:60]
        await _oa.mark(leader["id"], task=f"派单：{brief}", leader_id=leader["id"], ttl_seconds=300)

        # 执行步骤（对话式时间线）：一次派活 = 一个 run_id
        import uuid as _uuid

        from app.plugin.module_ai.logs_center import run_steps as _rs

        run_id = _uuid.uuid4().hex
        step = {"seq": 0}

        async def _step(kind: str, title: str, who: str | None = None, wid: int | None = None,
                        detail: str | None = None, ms: int | None = None, ok: bool = True):
            await _rs.add(run_id, step["seq"], kind, title, wid, who, detail, ms, ok)
            step["seq"] += 1

        await _step("plan", f"收到任务：{brief}", leader["name"], leader["id"], detail=text.strip()[:500])
        yield {
            "type": "start",
            "run_id": run_id,
            "leader": leader["name"],
            "members": [m["name"] for m in members],
            "memory": bool(_hist_text),
        }

        name2id = {m["name"]: m["id"] for m in members if m.get("name")}
        buffers: dict[str, str] = {m["name"]: "" for m in members if m.get("name")}
        replied: set[str] = set()
        chunks: list[str] = []
        ok, err = True, None
        t0 = _t.perf_counter()

        def _clip(v: str, n: int = 42) -> str:
            v = " ".join((v or "").split())
            return v if len(v) <= n else v[:n] + "…"

        # 平台业务工具（list_datasets 等）按 ContextVar 注入用户，工具内再做数据权限
        from app.plugin.module_ai.agno_tools.business import (
            reset_user_context,
            set_user_context,
        )

        _uid_token = set_user_context(user_id)
        _completed = False          # 流跑完才置 True；没跑完说明被中断了
        _failed = False             # 抛异常（不是被取消）：收尾步骤由下面的 error 分支写
        # 组员在 Team 里跑的时候，agno 不会替我们记调用日志（只有组长那条 usage=team），
        # 于是日志面板里一次多人协作只看到 1 行。这里按成员 run 的起止自己记一条 usage=agent。
        _member_t0: dict[str, float] = {}
        _member_model = {a["id"]: (a.get("model_name") or a["name"]) for a in view}
        try:
            async for ev in team.arun(text, stream=True):
                etype = str(getattr(ev, "event", "") or type(ev).__name__).lower()
                agent_name = getattr(ev, "agent_name", None)
                tool = getattr(ev, "tool", None)
                tname = str(getattr(tool, "tool_name", "") or "").lower()
                content = getattr(ev, "content", None)

                # 0) 工具执行记录：每完成一次工具调用写一行（大屏时间线用）
                if "tool_call_completed" in etype or "toolcallcompleted" in etype:
                    tool = getattr(ev, "tool", None)
                    tname = getattr(tool, "tool_name", None)
                    if tname:
                        dur = None
                        metrics = getattr(tool, "metrics", None)
                        if metrics is not None:
                            d0 = getattr(metrics, "duration", None)
                            if d0 is not None:
                                try:
                                    dv = float(d0)
                                    dur = int(dv * 1000) if dv < 100 else int(dv)
                                except Exception:  # noqa: BLE001
                                    dur = None
                        who = getattr(ev, "agent_name", None) or leader["name"]
                        await _tc.record(
                            name2id.get(who) or leader["id"],
                            who,
                            tname,
                            getattr(tool, "tool_args", None),
                            dur,
                            not bool(getattr(tool, "tool_call_error", False)),
                        )
                        # 真实工具调用也进执行过程（执行人 → 工具名 + 参数），
                        # 这样时间线里能看到 list_datasets / web_fetch 这类实际动作
                        _targs = getattr(tool, "tool_args", None) or {}
                        _tres = str(getattr(tool, "result", "") or "")[:1500]
                        _tok = not bool(getattr(tool, "tool_call_error", False))
                        await _step(
                            "tool",
                            str(tname),
                            who,
                            name2id.get(who) or leader["id"],
                            detail=_json.dumps(
                                {"tool": tname, "args": _targs, "result": _tres},
                                ensure_ascii=False,
                                default=str,
                            ),
                            ms=dur or 0,
                            ok=_tok,
                        )
                        # 同一个动作实时推给前端：面板/大屏不用等这一轮结束
                        yield {
                            "type": "tool",
                            "from": who,
                            "tool": tname,
                            "args": _targs,
                            "result": _tres,
                            "ms": dur or 0,
                            "ok": _tok,
                        }

                # 1) 组长派活：实测 Team 委派时不发 tool_call_started，而是直接
                #    起一个「成员 run」——带 agent_name 的 runstarted 就是点名那一刻。
                if "runstarted" in etype and agent_name in name2id:
                    _member_t0[agent_name] = _t.perf_counter()
                    # 委派本身也算一次工具调用（Team 不会为它发 tool 事件），记进时间线
                    await _tc.record(
                        leader["id"], leader["name"], "delegate_task_to_member",
                        {"member": agent_name, "task": _clip(brief, 40)}, 0, True,
                    )
                    import json as _json

                    await _step(
                        "tool", f"派活 → {agent_name}", leader["name"], leader["id"],
                        detail=_json.dumps(
                            {"tool": "delegate_task_to_member",
                             "args": {"member": agent_name, "task": _clip(brief, 200)}},
                            ensure_ascii=False,
                        ),
                        ms=0,
                    )
                    yield {
                        "type": "delegate",
                        "from": leader["name"],
                        "to": agent_name,
                        "task": _clip(brief, 16),
                    }
                    await _oa.mark(
                        name2id[agent_name], task=f"组长派单：{brief}",
                        leader_id=leader["id"], ttl_seconds=300,
                    )

                # 1.5) 组员这一轮跑完/失败：补一条调用日志（usage=agent, app_id=组员）
                if agent_name in name2id and ("runcompleted" in etype or "runerror" in etype):
                    _t0 = _member_t0.pop(agent_name, None)
                    if _t0 is not None:
                        _ms = int((_t.perf_counter() - _t0) * 1000)
                        _mid = name2id[agent_name]
                        await AiOverviewService.add_log(
                            model_name=_member_model.get(_mid, agent_name),
                            usage="agent",
                            latency_ms=_ms,
                            result="success" if "runcompleted" in etype else "error",
                            error=None if "runcompleted" in etype else str(content or "")[:300],
                            app_id=_mid,
                            user_id=user_id,
                        )

                # 2) 组员回话：**等这一轮跑完再冒**（完整口径）
                #
                # 以前是"攒够 18 字就先冒一句"，实测两个问题：
                # ① 短回复会被 RunCompleted 的整段回放再拼一遍 → "…。…。"（翻倍）；
                # ② 长回复在 18 字处就发出去且再不更新 → 气泡/面板永远是半句
                #    （"数据集总数为 273 个。模型总数为 " 就断了）。
                # 现在统一在 runcompleted 事件发一次完整文本，并清空缓冲，
                # 同一个人被派第二次也能正常再冒一句。
                if agent_name in name2id:
                    # 工具事件也会带 content（"list_datasets() completed in …"），
                    # 不能当回话累积，否则成员"说"的全是工具日志
                    if "tool" not in etype and isinstance(content, str) and content:
                        if "runcompleted" in etype:
                            # RunCompleted 带的是整段回放（deltas 已经拼过），只在没 delta 时兜底
                            if not buffers[agent_name].strip():
                                buffers[agent_name] = content
                        else:
                            buffers[agent_name] += content
                    if "runcompleted" in etype and buffers[agent_name].strip():
                        full = _reply_text(buffers[agent_name])
                        if full:
                            await _step(
                                "reply", f"{agent_name} 回话", agent_name,
                                name2id[agent_name], detail=full[:600],
                            )
                            yield {"type": "reply", "from": agent_name, "text": full}
                        buffers[agent_name] = ""
                        replied.add(agent_name)
                # 3) 组员报错（模型/接口问题）：气泡里给他一句人话
                if "runerror" in etype and agent_name in name2id and agent_name not in replied:
                    replied.add(agent_name)
                    buffers[agent_name] = ""
                    yield {"type": "reply", "from": agent_name, "text": "（没接上，接口报错）"}

                # 3) 组长自己的产出（最终口径，用于弹窗）
                if "content" in etype and isinstance(content, str) and content:
                    if not agent_name or agent_name == leader["name"] or agent_name not in name2id:
                        # 同理：RunCompleted 是整段回放，deltas 已经攒过，别再拼一遍
                        if "runcompleted" in etype and chunks:
                            pass
                        else:
                            chunks.append(content)
            _completed = True
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        finally:
            reset_user_context(_uid_token)
            for _fn in cleanups:
                try:
                    _fn()
                except Exception:  # noqa: BLE001
                    pass
            if not _completed and not _failed:
                # 页面关掉 / 点了停止：生成器被取消，收尾代码跑不到，
                # 任务列表里就会永远显示"进行中"。这里补一条收尾步骤兜底。
                # 注意：生成器收尾阶段不能 await（会被 GeneratorExit 打断），
                # 只能起一个后台任务去写。
                import asyncio as _aio

                try:
                    _aio.create_task(
                        _step(
                            "error", "已中断", leader["name"], leader["id"],
                            detail="页面关闭或点了停止，这一轮没有跑完", ok=False,
                        )
                    )
                except Exception:  # noqa: BLE001
                    pass

        # 没来得及发的回话，收尾补上
        for nm, buf in buffers.items():
            if nm in replied or not buf.strip():
                continue
            yield {"type": "reply", "from": nm, "text": _reply_text(buf)}

        content_text = "".join(chunks).strip()
        if not ok:
            try:
                await _oa.mark(
                    leader["id"],
                    task=f"执行失败：{(err or '')[:40]}",
                    status="error",
                    ttl_seconds=180,
                )
            except Exception:  # noqa: BLE001
                pass
        await AiOverviewService.add_log(
            leader["name"],
            "team",
            int((_t.perf_counter() - t0) * 1000),
            "success" if ok else "error",
            err,
            app_id=leader["id"],
            user_id=user_id,
        )

        session_id = None
        try:
            from app.plugin.module_ai.sessions.service import (
                AiSessionService,
                persist_session_exchange,
            )

            sess = await AiSessionService.create(
                f"[办公室] {text.strip()[:40]}", app_id=leader["id"], user_id=user_id
            )
            session_id = sess.get("id")
            if ok and content_text:
                await persist_session_exchange(
                    session_id, text, content_text, app_id=leader["id"], user_id=user_id
                )
        except Exception as e:  # noqa: BLE001
            from app.core.logger import logger

            logger.warning(f"[office] 写入派活会话失败: {str(e)[:120]}")

        await _step(
            "summary" if ok else "error",
            "组长汇总" if ok else "执行失败",
            leader["name"], leader["id"],
            detail=(content_text or err or "")[:800],
        )
        if ok and content_text:
            try:
                await _om.add(user_id, text, content_text)
            except Exception:  # noqa: BLE001
                pass

        yield {
            "type": "done",
            "run_id": run_id,
            "ok": ok,
            "leader": leader["name"],
            "content": content_text,
            "error": err,
            "session_id": session_id,
        }

    @classmethod
    async def office_dispatch_one(cls, agent_id: int, text: str, user_id: int | None = None) -> dict:
        """点名派活：只让指定的智能体干活（不走 Team），结果直接回给用户。

        与 ``office_dispatch`` 的区别：那是"交给组长协调"，这是"直接找某个人"。
        日志记 ``usage="agent"`` + ``app_id=该 agent``，办公室据此点亮他。
        """
        import time as _t

        if not text or not text.strip():
            return {"ok": False, "msg": "任务不能为空"}

        agent = await cls.get_agent(agent_id)
        if not agent:
            return {"ok": False, "msg": "智能体不存在"}

        from app.plugin.module_ai.agno_tools.agent_factory import build_agent
        from app.plugin.module_ai.models.service import AiModelService
        from app.plugin.module_ai.overview.service import AiOverviewService

        from . import office_activity as _oa

        runtime = None
        try:
            if agent.get("model_id"):
                runtime = await AiModelService.get_runtime_model(model_id=agent["model_id"])
            else:
                runtime = await AiModelService.get_runtime_model()
        except Exception:  # noqa: BLE001
            runtime = None

        name = agent.get("agent_name") or f"#{agent_id}"
        brief = text.strip().replace("\n", " ")[:60]
        await _oa.mark(agent_id, task=f"派单：{brief}", ttl_seconds=240)

        # 点名派活同样带上该智能体绑定的真实能力（工具/技能/知识库/MCP）
        caps = await _office_caps(agent, user_id, text)
        instr = [
            f"你是「{name}」，岗位：{agent.get('agent_role') or '通用'}。",
            "直接给出可用的结果，不要复述任务、不要反问。",
            "需要系统数据时必须调用工具取数，禁止编造。",
        ]
        if caps["kb"]:
            instr.append(
                "## 参考知识库\n"
                "以下是检索到的相关资料，回答时优先引用，并在合适处标注来源：\n"
                f"{caps['kb']}"
            )

        ag = build_agent(
            model_config=runtime,
            name=name,
            description=agent.get("agent_role") or name,
            instructions=instr,
            extra_tools=caps["extra_tools"] or None,
            skills=caps["skills"],
            user_id=user_id,
        )

        # 执行步骤：单独派活也有完整时间线（plan → 工具 → summary）
        import json as _json
        import uuid as _uuid

        from app.plugin.module_ai.logs_center import run_steps as _rs

        run_id = _uuid.uuid4().hex
        step = {"seq": 0}

        async def _step(kind: str, title: str, detail: str | None = None,
                        ms: int | None = None, ok_step: bool = True):
            await _rs.add(run_id, step["seq"], kind, title, agent_id, name, detail, ms, ok_step)
            step["seq"] += 1

        await _step("plan", f"收到任务：{brief}", detail=text.strip()[:500])

        t0 = _t.perf_counter()
        ok, err, content = True, None, ""
        from app.plugin.module_ai.agno_tools.business import (
            reset_user_context,
            set_user_context,
        )

        _uid_token = set_user_context(user_id)
        try:
            parts: list[str] = []
            # stream_events=True：把工具调用也吐出来，单独派活才有工具级时间线
            async for ev in ag.arun(text, stream=True, stream_events=True):
                etype = str(getattr(ev, "event", "") or type(ev).__name__).lower()
                if "toolcallcompleted" in etype:
                    tool = getattr(ev, "tool", None)
                    tname = getattr(tool, "tool_name", None)
                    if tname:
                        await _step(
                            "tool",
                            str(tname),
                            detail=_json.dumps(
                                {
                                    "tool": tname,
                                    "args": getattr(tool, "tool_args", None) or {},
                                    "result": str(getattr(tool, "result", "") or "")[:1500],
                                },
                                ensure_ascii=False,
                                default=str,
                            ),
                            ok_step=not bool(getattr(tool, "tool_call_error", False)),
                        )
                c = getattr(ev, "content", None)
                if "content" in etype and isinstance(c, str) and c:
                    parts.append(c)
            content = "".join(parts).strip()
        except Exception as e:  # noqa: BLE001
            ok, err = False, str(e)
        finally:
            reset_user_context(_uid_token)
            if caps["cleanup"]:
                try:
                    caps["cleanup"]()
                except Exception:  # noqa: BLE001
                    pass

        await _step(
            "summary" if ok else "error",
            "执行结果" if ok else "执行失败",
            detail=(content or err or "")[:800],
            ok_step=ok,
        )
        if not content and ok:
            content = "（没有返回内容）"

        await AiOverviewService.add_log(
            name,
            "agent",
            int((_t.perf_counter() - t0) * 1000),
            "success" if ok else "error",
            err,
            app_id=agent_id,
            user_id=user_id,
        )

        session_id = None
        try:
            from app.plugin.module_ai.sessions.service import (
                AiSessionService,
                persist_session_exchange,
            )

            sess = await AiSessionService.create(
                f"[办公室] {text.strip()[:40]}", app_id=agent_id, user_id=user_id
            )
            session_id = sess.get("id")
            if ok and content:
                await persist_session_exchange(
                    session_id, text, content, app_id=agent_id, user_id=user_id
                )
        except Exception as e:  # noqa: BLE001
            from app.core.logger import logger

            logger.warning(f"[office] 写入派活会话失败: {str(e)[:120]}")

        return {
            "ok": ok,
            "agent": name,
            "content": content,
            "error": err,
            "session_id": session_id,
        }

    @classmethod
    async def get_agent(cls, agent_id: int, source_app_id: int | None = None) -> dict | None:
        """按主键取智能体；``source_app_id`` 非空时校验归属，不匹配返回 ``None``。"""
        async with async_db_session() as db:
            a = await db.get(AiAgentModel, agent_id)
            if not a or a.is_deleted:
                return None
            if source_app_id is not None and a.source_app_id != source_app_id:
                return None
            return _to_dict(a)

    @classmethod
    async def create(cls, data, auth, source_app_id: int | None = None) -> dict:
        """创建智能体；``source_app_id`` 非空表示由开放平台应用创建（归属打标）。"""
        uid = getattr(getattr(auth, "user", None), "id", None)
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
                source_app_id=source_app_id,
                created_id=uid,
                updated_id=uid,
            )
            await _validate_agent_bindings(
                db,
                tool_ids=data.tool_ids or [],
                skill_ids=data.skill_ids or [],
                knowledge_ids=data.knowledge_ids or [],
                mcp_ids=getattr(data, "mcp_ids", None) or [],
                user_id=uid,
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
                user_id=getattr(getattr(auth, "user", None), "id", None),
            )
            a.updated_id = getattr(getattr(auth, "user", None), "id", None)
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
        from app.plugin.module_ai.assistant.agno_service import (
            agno_error_frame,
            ui_stream_to_agno,
        )

        agent = await cls.get_agent(agent_id)
        if not agent or not agent.get("enabled"):
            # 没有 agent 也要产出终止帧，保持协议一致（Agno 原生 RunError）
            yield agno_error_frame("智能体不存在或未启用")
            return

        # 委托工作流：引擎产 UI Message Stream 帧（编排语义），此处转译为 Agno 原生事件
        # （本端点契约 = Agno 帧，前端 AgnoChatTransport 只认 Run* 事件）。会话已由
        # 工作流引擎自行落库，finally 不再重复落。
        delegated = False
        if agent.get("workflow_id"):
            from app.plugin.module_ai.workflow.service import AiWorkflowService

            delegated = True
            async for frame in ui_stream_to_agno(
                AiWorkflowService.run_ui_stream(
                    agent["workflow_id"], ui_messages, auth, variables, session_id
                )
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

        t0 = time.perf_counter()
        uid = getattr(getattr(auth, "user", None), "id", None)
        user_text = last_user_text(ui_messages)
        # Guardrail：输入安全校验（空/超长/提示注入）
        _gap = _agent_guardrail(user_text)
        if _gap:
            yield agno_error_frame(_gap)
            return
        state: dict = {
            "assistant_text": "", "reply": "", "tool_calls": [],
            "action": None, "report_id": None, "error": None,
        }
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
                yield agno_error_frame(state["error"])
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
            yield agno_error_frame(f"运行失败：{e}")
        finally:
            u = state.get("usage") or {}
            await AiOverviewService.add_log(
                agent.get("agent_name", ""),
                "agent",
                int((time.perf_counter() - t0) * 1000),
                "success" if state["error"] is None else "error",
                state["error"],
                app_id=agent_id,
                user_id=uid,
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                cost=u.get("cost", 0.0),
            )
            # 委托工作流时会话已由引擎落库：跳过，防重复 user 消息
            if not delegated:
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
