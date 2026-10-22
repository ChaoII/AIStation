"""Agno 原生事件流助手服务：由 Agno Agent 驱动执行，直出 Agno 原生 SSE。

设计（对齐用户「都用 agno、全部换成 Agno 原生流式」）：
- 执行层完全由 ``agno_tools.agent_factory.build_agent`` 构建的 Agno ``Agent`` 驱动，
  Agno 负责全部 function-calling 循环（不再手写 OpenAI 循环）。
- 业务工具统一来自 ``agno_tools.business`` 注册中心。
- 输出为 Agno 原生事件流：``event: <RunEvent>\ndata: {event.to_dict()}\n\n``，
  事件类型见 ``agno.run.agent.RunEvent``（RunStarted / RunContent / ToolCallStarted /
  ToolCallCompleted / ReasoningContentDelta / RunCompleted / RunError ...）。

用法：``async for sse in run_agno_stream(...)`` 产出已格式化的 SSE 字符串。
"""
from __future__ import annotations

import base64
import io
from collections.abc import AsyncIterator

from app.core.exceptions import CustomException
from app.plugin.module_ai.models.service import AiModelService


def _parse_data_uri(data_url: str) -> tuple[bytes, str]:
    """从 data URL（``data:<mime>;base64,<b64>``）提取原始字节与 mime，失败返回 ``(b"", "")``。"""
    try:
        header, b64 = data_url.split(",", 1)
        mime = ""
        if header.startswith("data:"):
            mime = header[5:].split(";")[0]
        return base64.b64decode(b64), mime
    except Exception:  # noqa: BLE001 单个文件解析失败不阻断
        return b"", ""


#: 纯文本扩展名（无需解析器，直接 UTF-8 解码）
_TEXT_EXTS = {
    "txt", "md", "markdown", "csv", "json", "log", "yaml", "yml", "ini", "toml",
    "xml", "html", "htm", "js", "mjs", "cjs", "ts", "tsx", "jsx", "py", "java",
    "c", "h", "cpp", "hpp", "go", "rs", "sql", "sh", "bat", "ps1", "conf",
    "properties", "env", "graphql", "vue", "css", "scss",
}
#: 纯文本 MIME（含带 charset 后缀的，如 text/plain; charset=utf-8）
_TEXT_MIME_PREFIX = ("text/", "application/json", "application/xml", "application/csv",
                     "application/yaml", "application/x-yaml", "application/x-www-form-urlencoded")


def _extract_doc_text(raw: bytes, mime: str, name: str = "") -> str:
    """抽取文档纯文本（txt/md/csv/json 等直接解码；pdf/docx 解析）。

    老 .doc / 未知格式返回空串。
    """
    ext = (name.rsplit(".", 1)[-1] if "." in name else "").lower()
    if ext in _TEXT_EXTS or mime.lower().startswith(_TEXT_MIME_PREFIX):
        return raw.decode("utf-8", errors="ignore")
    if ext == "txt" or "text/plain" in mime:
        return raw.decode("utf-8", errors="ignore")
    if ext == "pdf" or "application/pdf" in mime:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:  # noqa: BLE001
            return ""
    if ext == "docx" or "officedocument.wordprocessingml" in mime:
        try:
            import docx

            doc = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:  # noqa: BLE001
            return ""
    return ""


async def _resolve_workspace_file(file_id: int, user_id: int | None) -> dict | None:
    """按 file_id 读取用户个人空间文件字节；越权/不存在/读取失败统一返回 None。

    供 ``_process_uploaded_files`` 处理「对话引用个人空间文件」；返回
    ``{"data": bytes, "mime_type": str, "name": str, "file_type": str}``。
    """
    if not user_id:
        return None
    try:
        from app.plugin.module_ai.space.service import SpaceService

        return await SpaceService.get_file_bytes(user_id, file_id)
    except Exception:  # noqa: BLE001 单个引用失败不阻断对话
        return None


async def _process_uploaded_files(
    files: list[dict] | None, user_id: int | None = None
) -> tuple[list, str]:
    """把上传/引用文件拆成 `(images, doc_context)`。

    - 图片（mime 以 ``image/`` 开头，或 workspace 引用中的图片类型）→ Agno ``Image``（原始字节）。
    - 文档 → 抽取文本拼到 ``doc_context``，作为输入上下文。
    - 个人空间引用（``{"type": "workspace", "file_id": ...}``）→ 经
      ``_resolve_workspace_file`` 读取，失败自动跳过。
    - 非图片非文档（含 .doc 老格式/未知）→ 忽略。
    """
    if not files:
        return [], ""
    from agno.media import Image

    images: list = []
    doc_chunks: list[str] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "")
        ftype = str(f.get("type") or f.get("mime_type") or "").lower()
        # 个人空间引用：读取真实字节后再按类型处理
        if f.get("type") == "workspace" and f.get("file_id"):
            got = await _resolve_workspace_file(int(f["file_id"]), user_id)
            if not got:
                continue
            raw = got.get("data") or b""
            mime = got.get("mime_type") or ""
            name = got.get("name") or name
            ftype = got.get("file_type") or ftype
            if not raw:
                continue
            if ftype == "image" or mime.startswith("image/"):
                images.append(Image(content=raw, mime_type=mime or "image/png", format=((mime.split("/")[-1]) or None)))
            else:
                text = _extract_doc_text(raw, mime, name)
                if text.strip():
                    doc_chunks.append(f"【{name or '个人空间文件'}】\n{text.strip()}")
            continue
        data_url = str(f.get("dataUrl") or f.get("data_url") or f.get("data") or "")
        if not data_url:
            continue
        raw, mime = _parse_data_uri(data_url)
        if not raw:
            continue
        if ftype.startswith("image/") or mime.startswith("image/"):
            images.append(Image(content=raw, mime_type=mime or ftype, format=(ftype.split("/")[-1] or None)))
        else:
            text = _extract_doc_text(raw, mime or ftype, name)
            if text.strip():
                doc_chunks.append(f"【{name or '上传文档'}】\n{text.strip()}")
    return images, "\n\n".join(doc_chunks)


def _sse(event) -> str:
    """把 Agno RunOutputEvent 格式化为 Agno 原生 SSE 帧。"""
    from agno.os.utils import format_sse_event

    try:
        return format_sse_event(event)
    except Exception:  # noqa: BLE001 单事件序列化失败不中断整个流
        return ": event-serialize-error\n\n"


async def run_agno_core(
    *,
    model_config: dict,
    user_text: str,
    user_id: int | None,
    session_id: int | None,
    input_text: str | None = None,
    images: list | None = None,
    instructions: list[str] | None = None,
    description: str | None = None,
    tools: list | None = None,
    extra_tools: list | None = None,
    name: str | None = None,
    skills=None,
) -> AsyncIterator[str]:
    """Agno Agent 驱动的通用事件流执行核心：app / agent / assistant 共用。

    - 工具：默认业务工具；传入 ``tools``（如 ``dynamic.build_dynamic_tools`` 生成的
      app/agent 自定义工具）则覆盖。``extra_tools`` 追加（如 MCP 工具集）。
    - ``input_text`` 缺省用 ``user_text``。
    - 产出 Agno 原生 SSE 帧并累积正文供会话落库由调用方决定。
    - 使用 ``agno_tools.business`` / ``agno_tools.dynamic`` 两个 ContextVar 同时注入
      user_id（业务工具与动态派发工具分别读取）。
    """
    from app.plugin.module_ai.agno_tools import business as biz
    from app.plugin.module_ai.agno_tools import dynamic as dyn
    from app.plugin.module_ai.agno_tools.agent_factory import build_agent

    biz_token = biz.set_user_context(user_id)
    dyn_token = dyn.set_user_context(user_id)
    try:
        agent = build_agent(
            model_config=model_config,
            user_id=user_id,
            session_id=session_id,
            instructions=instructions,
            description=description,
            tools=tools,
            extra_tools=extra_tools,
            name=name,
            skills=skills,
        )
        async for item in agent.arun(
            input_text if input_text is not None else user_text,
            stream=True,
            stream_events=True,
            images=images,
            user_id=str(user_id) if user_id is not None else None,
            session_id=f"session_{session_id}" if session_id is not None else None,
            add_history_to_context=True,
        ):
            if isinstance(item, str):
                yield item
                continue
            yield _sse(item)
    finally:
        biz.reset_user_context(biz_token)
        dyn.reset_user_context(dyn_token)


async def run_agno_stream(
    *,
    messages: list[dict],
    auth,
    user_id: int | None = None,
    session_id: int | None = None,
    knowledge_ids: list[int] | None = None,
    model_id: int | None = None,
    files: list[dict] | None = None,
) -> AsyncIterator[str]:
    """用 Agno Agent 驱动一轮助手对话，产出 Agno 原生 SSE 事件流。

    - ``messages``：AI SDK UIMessage 列表（兼容现有前端入参），取最后一条 user 文本作为输入。
    - 知识库 RAG 上下文会注入 system 提示。
    - 用户上下文（user_id）通过 ContextVar 注入业务工具。
    """
    from app.plugin.module_ai.assistant.service import last_user_text

    # 决定运行时模型：显式 model_id > chat 类 > 默认
    model_config = None
    if model_id:
        model_config = await AiModelService.get_runtime_model(model_id=model_id)
    if not model_config:
        model_config = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    if not model_config:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")

    user_text = last_user_text(messages)

    # 知识库 RAG：检索上下文拼接到 system 提示
    system_ctx = ""
    if knowledge_ids:
        try:
            from app.plugin.module_ai.assistant.service import retrieve_kb_rag

            kb_ctx, _ = await retrieve_kb_rag(knowledge_ids, user_text)
            if kb_ctx:
                system_ctx = kb_ctx
        except Exception:  # noqa: BLE001 RAG 失败不阻断
            pass

    input_text = user_text
    if system_ctx:
        input_text = f"【参考知识】\n{system_ctx}\n\n问题：{user_text}"
    # 上传文件：图片转 Agno Image，文档文本抽取注入上下文（含个人空间引用）
    images, doc_ctx = await _process_uploaded_files(files, user_id=user_id)
    if doc_ctx:
        input_text = f"{input_text}\n\n【上传文档】\n{doc_ctx}"
    if not input_text.strip() and images:
        input_text = "请分析上传的图片，并描述你看到的内容与相关建议。"
    assistant_text = ""
    try:
        async for sse in run_agno_core(
            model_config=model_config,
            user_text=user_text,
            user_id=user_id,
            session_id=session_id,
            input_text=input_text,
            images=images,
        ):
            # 累积正文（RunContent 事件），用于会话落库
            if "event: RunContent" in sse:
                try:
                    import json as _json

                    _data = sse.split("\ndata:", 1)[1].strip()
                    _payload = _json.loads(_data)
                    if isinstance(_payload.get("content"), str):
                        assistant_text += _payload["content"]
                except Exception:  # noqa: BLE001 解析失败不影响透传
                    pass
            yield sse
    finally:
        # 会话落库（无论正常/异常/中断）：无 session_id 时内部直接返回
        try:
            from app.plugin.module_ai.sessions.service import persist_session_exchange

            await persist_session_exchange(
                session_id, user_text, assistant_text, user_id=user_id
            )
        except Exception:  # noqa: BLE001 落库失败不阻断（persist_session_exchange 内部已吞异常）
            pass


async def run_agno_tool_stream(
    *,
    model_config: dict,
    system_prompt: str,
    tool_schemas: list[dict] | None,
    dispatch,
    user_text: str,
    user_id: int | None,
    session_id: int | None,
    name: str | None = None,
    description: str | None = None,
    instructions_extra: list[str] | None = None,
    mcp_tools: list | None = None,
    state: dict | None = None,
    skills=None,
) -> AsyncIterator[str]:
    """app/agent 运行台共用：用 Agno Agent 驱动“模型 + 提示词 + 动态工具”。

    - ``tool_schemas``：OpenAI function schema 列表（来自 ``_build_app_tools``）。
    - ``dispatch(name, args, user_id)``：异步派发器（内置/Agno/HTTP 工具）。
    - 内部用 ``dynamic.build_dynamic_tools`` 把 schema 包装成 Agno 工具，
      执行统一走 ``dispatch``；``user_id`` 通过 ContextVar 注入。
    - ``mcp_tools``：已构建的 MCP 工具集（``mcp.tools.build_mcp_tools`` 产出），
      在此处统一连接/关闭；连接失败的服务器自动跳过（降级运行）。
    - 传入 ``state``（含 ``assistant_text``）时会把正文增量累加进去，供调用方
      会话落库（对齐旧实现 ``state["assistant_text"]`` 的语义）。
    """
    import json as _json

    from app.plugin.module_ai.agno_tools.business import build_workspace_tools
    from app.plugin.module_ai.agno_tools.dynamic import build_dynamic_tools

    tools = build_dynamic_tools(tool_schemas or [], dispatch) if tool_schemas else []
    # 运行台传入 tools 会覆盖默认业务工具 → 显式并入个人空间工具
    tools.extend(build_workspace_tools())
    instructions: list[str] = []
    if system_prompt:
        instructions.append(system_prompt)
    if instructions_extra:
        instructions.extend(instructions_extra)

    connected_mcp: list = []
    if mcp_tools:
        from app.plugin.module_ai.mcp.tools import connect_mcp_tools

        connected_mcp = await connect_mcp_tools(mcp_tools)
    try:
        async for sse in run_agno_core(
            model_config=model_config,
            user_text=user_text,
            user_id=user_id,
            session_id=session_id,
            instructions=instructions or None,
            description=description,
            tools=tools or None,
            extra_tools=connected_mcp or None,
            name=name,
            skills=skills,
        ):
            if state is not None and "event: RunContent" in sse:
                try:
                    _data = sse.split("\ndata:", 1)[1].strip()
                    _payload = _json.loads(_data)
                    if isinstance(_payload.get("content"), str):
                        state["assistant_text"] = state.get("assistant_text", "") + _payload["content"]
                except Exception:  # noqa: BLE001 解析失败不影响透传
                    pass
            yield sse
    finally:
        if connected_mcp:
            from app.plugin.module_ai.mcp.tools import close_mcp_tools

            await close_mcp_tools(connected_mcp)


def agno_stream_response(body: AsyncIterator[str]):
    """Agno 原生事件流的 StreamingResponse（**共享 SSE 契约**，勿手抄响应头）。"""
    from app.core.sse import sse_response

    return sse_response(body, extra_headers={"Connection": "keep-alive"})


def agno_event_frame(event: str, payload: dict | None = None) -> str:
    """构造 Agno 原生 SSE 事件帧（``event: <name>`` + data 冗余 event 字段）。"""
    import json

    data = {"event": event}
    if payload:
        data.update(payload)
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def agno_error_frame(message: str) -> str:
    """Agno 原生 error 帧（配合 SSE 终止）。"""
    return agno_event_frame("RunError", {"error": message})


async def ui_stream_to_agno(body: AsyncIterator[str]) -> AsyncIterator[str]:
    """把 UI Message Stream 帧流转译为 Agno 原生事件帧。

    协议边界（勿混淆）：工作流端点自身保持 UI Message Stream（编辑器/分享页/HITL
    依赖 ``node-status`` / ``data-run`` / ``data-finish``）；而 agent/app 的
    ``run/stream`` 端点契约是 Agno 原生事件（前端 ``AgnoChatTransport`` 只认
    ``event: Run*`` 帧，UI 帧会被静默丢弃）。委托工作流运行时在此转译：

    - ``text-delta`` → ``RunContent``；``reasoning-delta`` → ``ReasoningContentDelta``
    - ``tool-input/output-*`` → ``ToolCallStarted/Completed``
    - ``error`` → ``RunError``；``finish`` → ``RunCompleted``
    - ``data-finish``：``reply``（end 节点回复只装在这里，无流式正文）补发为
      ``RunContent``；``awaiting_approval`` → ``RunError`` 提示（对话页无审批 UI）。
    - 其余编排专属帧（``node-status`` / ``data-run`` / ``sources`` / ``tool-approval``）
      对对话无意义，丢弃。
    """
    import json as _json

    completed = False
    text_emitted = False
    pending_reply = ""
    awaiting = False
    async for frame in body:
        # 一次 yield 可能拼了多帧（如 ms.text 首次 = text-start + text-delta）：逐行解析
        for line in frame.split("\n"):
            s = line.strip()
            if not s.startswith("data:"):
                continue
            raw = s[5:].strip()
            if raw == "[DONE]":
                continue
            try:
                obj = _json.loads(raw)
            except Exception:  # noqa: BLE001 非 JSON 帧忽略
                continue
            if not isinstance(obj, dict):
                continue
            t = obj.get("type")
            if t == "text-delta":
                delta = obj.get("delta") or ""
                if delta:
                    text_emitted = True
                    yield agno_event_frame("RunContent", {"content": delta})
            elif t == "reasoning-delta":
                delta = obj.get("delta") or ""
                if delta:
                    yield agno_event_frame(
                        "ReasoningContentDelta", {"reasoning_content": delta}
                    )
            elif t == "tool-input-available":
                yield agno_event_frame(
                    "ToolCallStarted",
                    {
                        "tool": {
                            "tool_name": obj.get("toolName") or "工具",
                            "tool_call_id": obj.get("toolCallId") or "",
                            "tool_args": obj.get("input"),
                        }
                    },
                )
            elif t == "tool-output-available":
                yield agno_event_frame(
                    "ToolCallCompleted",
                    {
                        "tool": {
                            "tool_name": obj.get("toolName") or "工具",
                            "tool_call_id": obj.get("toolCallId") or "",
                            "result": obj.get("output"),
                        }
                    },
                )
            elif t == "tool-output-error":
                # 前端 toolResultError 启发式按 success===false 识别为错误输出
                yield agno_event_frame(
                    "ToolCallCompleted",
                    {
                        "tool": {
                            "tool_name": obj.get("toolName") or "工具",
                            "tool_call_id": obj.get("toolCallId") or "",
                            "result": {"success": False, "error": obj.get("errorText")},
                        }
                    },
                )
            elif t == "error":
                yield agno_error_frame(str(obj.get("errorText") or "运行失败"))
            elif t == "data-finish":
                d = obj.get("data")
                d = d if isinstance(d, dict) else {}
                pending_reply = str(d.get("reply") or "")
                awaiting = bool(d.get("awaiting_approval"))
            elif t == "finish" and not completed:
                completed = True
                if awaiting:
                    # HITL 挂起：对话页无审批 UI，明确告知用户去向
                    yield agno_error_frame("工作流等待工具审批，请到工作流编辑器处理后重试")
                elif pending_reply and not text_emitted:
                    # end 节点回复只装在 data-finish.reply（无流式正文）：补发为正文
                    yield agno_event_frame("RunContent", {"content": pending_reply})
                yield agno_event_frame("RunCompleted")
    if not completed:
        yield agno_event_frame("RunCompleted")
