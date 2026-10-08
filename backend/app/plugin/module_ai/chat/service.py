import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from agno.session.team import TeamSession

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_system.dept.service import DeptService
from app.common.request import PaginationService
from app.core.exceptions import CustomException
from app.core.logger import log

from .crud import ChatSessionCRUD
from .schema import (
    ChatQuerySchema,
    ChatSessionCreateSchema,
    ChatSessionQueryParam,
    ChatSessionUpdateSchema,
)
from .utils import AgnoFactory


async def _format_session_data(session: TeamSession, auth: AuthSchema | None = None) -> dict[str, Any]:
    """格式化会话数据，添加前端需要的字段"""
    if hasattr(session, 'to_dict'):
        session_dict = session.to_dict()
    else:
        session_dict = {
            'session_id': getattr(session, 'session_id', ''),
            'agent_id': getattr(session, 'agent_id', None),
            'team_id': getattr(session, 'team_id', None),
            'workflow_id': getattr(session, 'workflow_id', None),
            'user_id': getattr(session, 'user_id', None),
            'session_data': getattr(session, 'session_data', None),
            'agent_data': getattr(session, 'agent_data', None),
            'team_data': getattr(session, 'team_data', None),
            'workflow_data': getattr(session, 'workflow_data', None),
            'metadata': getattr(session, 'metadata', None),
            'runs': getattr(session, 'runs', []),
            'summary': getattr(session, 'summary', None),
            'created_at': getattr(session, 'created_at', None),
            'updated_at': getattr(session, 'updated_at', None),
        }

    session_data = session_dict.get("session_data") or {}
    runs = session_dict.get("runs") or []
    messages = _extract_messages(runs)

    # 从 session_data 中获取 session_name 作为标题
    session_name = session_data.get("session_name") if session_data else None

    result = {
        **session_dict,
        "id": session_dict.get("session_id"),
        "title": session_name or session_dict.get("session_id", "")[:8] or "未命名会话",
        "created_time": _unix_to_datetime(session_dict.get("created_at")),
        "updated_time": _unix_to_datetime(session_dict.get("updated_at")),
        "message_count": len(messages),
        "messages": messages,
    }

    # 如果有 auth，查询部门名称
    if auth and session_dict.get("team_id"):
        try:
            team_id = session_dict.get("team_id")
            if isinstance(team_id, str):
                dept_name = await DeptService.get_dept_detail_service(auth=auth, id=int(team_id))
                result["team_name"] = dept_name.get("name")
            elif isinstance(team_id, int):
                dept_name = await DeptService.get_dept_detail_service(auth=auth, id=team_id)
                result["team_name"] = dept_name.get("name")
            else:
                result["team_name"] = None
        except Exception:
            result["team_name"] = None
    else:
        result["team_name"] = None

    # 如果 summary 是 SessionSummary 对象，提取 summary 字段
    summary = session_dict.get("summary")
    if summary:
        if isinstance(summary, dict):
            result["summary"] = summary.get("summary") or summary.get("summary")
        else:
            result["summary"] = str(summary)

    return result


def _unix_to_datetime(timestamp: int | None) -> str | None:
    """将Unix时间戳转换为日期时间字符串"""
    if timestamp is None:
        return None
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return None


def _extract_messages(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 runs 中提取消息"""
    messages = []
    if not runs:
        return messages
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_messages = run.get("messages", [])
        if run_messages and isinstance(run_messages, list):
            for msg in run_messages:
                if isinstance(msg, dict):
                    role = msg.get("role")
                    if role in ("user", "assistant"):
                        messages.append({
                            "id": msg.get("id"),
                            "role": role,
                            "content": msg.get("content", ""),
                            "created_at": msg.get("created_at"),
                        })
    return messages


def _fmt_ai_session(sess: dict, auth: AuthSchema | None = None, include_messages: bool = False) -> dict[str, Any]:
    """把 `ai_sessions` / `ai_messages` 的行格式化成 /chat 前端兼容的会话字典。"""
    out: dict[str, Any] = {
        "id": sess.get("id"),
        "session_id": str(sess.get("id")),
        "title": sess.get("title") or "",
        "message_count": sess.get("message_count") or 0,
        "created_time": sess.get("created_time"),
        "updated_time": sess.get("updated_time"),
        "team_name": None,
    }
    if include_messages:
        out["messages"] = [
            {
                "id": str(m.get("id")),
                "role": m.get("role"),
                "content": "".join(
                    p.get("text", "") for p in (m.get("parts") or []) if isinstance(p, dict)
                ),
                "created_at": None,
            }
            for m in (sess.get("messages") or [])
        ]
    return out


class ChatService:
    """聊天会话管理模块服务层"""

    @classmethod
    async def chat_query(
        cls, query: ChatQuerySchema, auth: AuthSchema
    ) -> AsyncGenerator[str, None]:
        """
        处理聊天查询并流式返回文本片段。

        参数:
        - query (ChatQuerySchema): 用户消息与会话等查询参数。
        - auth (AuthSchema): 当前用户认证信息。

        返回:
        - AsyncGenerator[str, None]: 逐段输出的回复文本。
        """
        try:
            # 创建 CRUD 实例获取数据库连接
            crud = ChatSessionCRUD(auth)

            # 获取或创建会话
            session_id = query.session_id
            if not session_id:
                # 创建新会话
                import uuid
                session_id = str(uuid.uuid4())
                session: TeamSession | None = await crud.create_crud(
                    data=ChatSessionCreateSchema(title="新对话")
                )
                if not session:
                    raise CustomException(msg="创建会话失败")
                session_id = session.session_id

            # 创建 AgnoFactory 实例并创建 Team，传入数据库连接
            agno_factory = AgnoFactory()
            dept_id = str(auth.user.dept_id) if auth and auth.user and hasattr(auth.user, 'dept_id') and auth.user.dept_id else "default"
            # 使用新模型配置（提供商/模型），缺省回退 env
            runtime = None
            try:
                from app.plugin.module_ai.provider.service import AiModelService

                runtime = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
            except Exception:
                runtime = None
            agent = agno_factory.create_agent(
                user_id=auth.user.username if auth and auth.user else "user",
                dept_id=dept_id,
                session_id=session_id,
                db=crud.db,
                model_config=runtime,
            )

            # 执行聊天查询 - 流式输出（含工具/推理中间步骤，若支持）
            run = None
            try:
                run = agent.arun(input=query.message, stream=True, stream_intermediate_steps=True)
            except TypeError:
                run = agent.arun(input=query.message, stream=True)
            async for chunk in run:
                # Agno 中间步骤事件（工具调用/推理）：以 JSON 行回传，前端识别渲染
                event = getattr(chunk, "event", None)
                if event and event not in ("RunResponse", "run_response"):
                    payload = {
                        "type": "step",
                        "event": str(event),
                        "tool": getattr(getattr(chunk, "tool", None), "tool_name", None),
                        "content": getattr(chunk, "content", None),
                    }
                    import json as _json

                    yield "\u0000STEP " + _json.dumps(payload, ensure_ascii=False, default=str)
                    continue
                if chunk and chunk.content:
                    yield chunk.content

        except Exception as e:
            log.error(f"聊天查询失败: {e}")
            yield f"抱歉，处理您的请求时出现错误：{str(e)}"

    @classmethod
    async def chat_non_stream(
        cls, message: str, session_id: int | None, auth: AuthSchema
    ) -> dict[str, Any]:
        """非流式 AI 对话（/ai-chat）：用共享 Agno Agent 驱动，会话并入规范 `ai_sessions` 仓库。

        - 会话：优先复用调用方已归属的 `ai_sessions` 会话（整数 id），否则新建。
        - 执行：复用 ``agno_tools.agent_factory.build_agent``（业务工具统一注册），
          不再使用独立的 Agno Team / TeamSession。
        - 落库：每轮经 ``AiSessionService.record_exchange`` 写入 `ai_sessions` / `ai_messages`。
        """
        from app.plugin.module_ai.agno_tools.agent_factory import build_agent
        from app.plugin.module_ai.agno_tools.business import (
            reset_user_context,
            set_user_context,
        )
        from app.plugin.module_ai.provider.service import AiModelService
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        # 归属校验并复用会话；无归属/不符则新建（deny-by-default）
        sess = None
        if session_id:
            try:
                found = await AiSessionService.get_session(int(session_id))
                if found and (found.get("user_id") == uid or not found.get("user_id")):
                    sess = found
            except (TypeError, ValueError):
                sess = None
        if not sess:
            sess = await AiSessionService.create(title=(message or "")[:30], user_id=uid)
        session_id = int(sess["id"])

        try:
            model_config = (
                await AiModelService.get_runtime_model("chat")
                or await AiModelService.get_runtime_model()
            )
            if not model_config:
                return {
                    "response": "未配置大模型，请在 AI 管理→模型配置 中添加并启用",
                    "session_id": session_id,
                    "function_calls": None,
                    "action": None,
                }
            token = set_user_context(uid)
            try:
                agent = build_agent(model_config=model_config, user_id=uid)
                resp = await agent.arun(
                    message,
                    stream=False,
                    user_id=str(uid) if uid is not None else None,
                    add_history_to_context=True,
                )
            finally:
                reset_user_context(token)

            reply = (
                resp.get_content_as_string()
                if hasattr(resp, "get_content_as_string")
                else str(resp.content or "")
            )

            # 从工具执行结果提取 __action__ / function_calls
            action = None
            tool_log: list[dict[str, Any]] = []
            for tool in (resp.tools or []):
                name = getattr(tool, "tool_name", None)
                args = getattr(tool, "tool_args", None) or {}
                result = getattr(tool, "result", None)
                try:
                    if isinstance(result, str):
                        result = json.loads(result)
                except (ValueError, TypeError):
                    pass
                if isinstance(result, dict) and result.get("__action__"):
                    action = result["__action__"]
                tool_log.append({"name": name, "args": args, "result": result})

            await AiSessionService.record_exchange(
                session_id, message, reply, user_id=uid
            )
            return {
                "response": reply,
                "session_id": session_id,
                "function_calls": tool_log or None,
                "action": action,
            }
        except Exception as e:  # noqa: BLE001
            log.error(f"聊天查询失败: {e}")
            return {
                "response": f"抱歉，处理您的请求时出现错误：{str(e)}",
                "session_id": session_id,
                "function_calls": None,
                "action": None,
            }

    @staticmethod
    def _parse_action_from_response(response_text: str) -> dict[str, Any] | None:
        """从响应文本中解析操作建议"""

        # 定义路由配置
        route_config = {
            "用户管理": {"path": "/system/user", "name": "用户管理"},
            "角色管理": {"path": "/system/role", "name": "角色管理"},
            "菜单管理": {"path": "/system/menu", "name": "菜单管理"},
            "部门管理": {"path": "/system/dept", "name": "部门管理"},
            "字典管理": {"path": "/system/dict", "name": "字典管理"},
            "系统日志": {"path": "/system/log", "name": "系统日志"},
        }

        # 检查是否包含导航意图
        navigation_keywords = ["跳转", "打开", "进入", "前往", "去", "浏览", "查看"]
        has_navigation = any(keyword in response_text for keyword in navigation_keywords)

        if not has_navigation:
            return None

        # 查找页面名称
        for page_name, route_info in route_config.items():
            if page_name in response_text:
                return {
                    "type": "navigate",
                    "path": route_info["path"],
                    "name": route_info["name"],
                }

        # 尝试从关键词匹配
        keyword_mapping = {
            "用户": {"path": "/system/user", "name": "用户管理"},
            "角色": {"path": "/system/role", "name": "角色管理"},
            "菜单": {"path": "/system/menu", "name": "菜单管理"},
            "部门": {"path": "/system/dept", "name": "部门管理"},
            "字典": {"path": "/system/dict", "name": "字典管理"},
            "日志": {"path": "/system/log", "name": "系统日志"},
        }

        for keyword, route_info in keyword_mapping.items():
            if keyword in response_text:
                return {
                    "type": "navigate",
                    "path": route_info["path"],
                    "name": route_info["name"],
                }

        return None

    @classmethod
    async def create_service(
        cls, auth: AuthSchema, data: ChatSessionCreateSchema
    ) -> dict[str, Any] | None:
        """创建会话（并入规范 `ai_sessions` 仓库）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        session = await AiSessionService.create(data.title or "新对话", None, uid)
        return _fmt_ai_session(session, auth)

    @classmethod
    async def get_session_service(
        cls, auth: AuthSchema, session_id: str
    ) -> dict[str, Any] | None:
        """获取单个会话详情（含消息，来自 `ai_sessions` / `ai_messages`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        try:
            session = await AiSessionService.get_session(int(session_id))
        except (TypeError, ValueError):
            return None
        if not session:
            return None
        if session.get("user_id") not in (None, uid):
            return None
        session["messages"] = await AiSessionService.get_messages(int(session_id))
        return _fmt_ai_session(session, auth, include_messages=True)

    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        page_no: int,
        page_size: int,
        search: ChatSessionQueryParam,
        order_by: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """分页获取会话列表（来自 `ai_sessions`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        sessions = await AiSessionService.list_sessions(uid)
        items = [_fmt_ai_session(s, auth) for s in sessions]
        result = await PaginationService.paginate(
            data_list=items, page_no=page_no, page_size=page_size
        )
        return result

    @classmethod
    async def update_service(
        cls, auth: AuthSchema, session_id: str, data: ChatSessionUpdateSchema
    ) -> bool:
        """重命名会话（`ai_sessions`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        try:
            result = await AiSessionService.rename(int(session_id), data.title, auth)
        except (TypeError, ValueError):
            return False
        return result is not None

    @classmethod
    async def delete_service(cls, auth: AuthSchema, session_ids: list[str]) -> None:
        """批量删除会话及消息（`ai_sessions`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        ids: list[int] = []
        for s in session_ids:
            try:
                ids.append(int(s))
            except (TypeError, ValueError):
                continue
        if ids:
            await AiSessionService.delete(ids)
