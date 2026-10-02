"""低代码工作流运行时引擎（类 Dify 节点 DAG 执行器）。

V1 节点集：``start`` / ``llm`` / ``tool`` / ``code`` / ``condition`` /
``variable`` / ``knowledge``（RAG，阶段 3 落地）/ ``end``。

执行方式：从 ``start`` 节点沿边顺序推进（V1 无并行扇出），``condition`` 按
表达式走 ``sourceHandle`` 为 ``true`` / ``false`` 的分支。``llm`` 节点调用大模型
并**流式**产出 UI Message Stream 帧；各节点输出写入变量命名空间供下游插值。
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any

from app.plugin.module_ai.streaming import UiMessageStream

# 匹配 {{变量名}}（兼容中文）
_VAR_RE = re.compile(r"\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}")


def render_template(template: str | None, variables: dict) -> str:
    """替换 ``{{var}}``，未知变量原样保留。"""
    if not template:
        return ""
    return _VAR_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), template)


class WorkflowEngine:
    """按节点 DAG 顺序执行工作流，流式产出 SSE 帧。

    - ``graph``：``{"nodes":[{id,type,data,x,y}], "edges":[{id,source,target,sourceHandle}]}``
    - ``variables``：入参变量（来自 ``input_schema`` / 调用方）
    - ``messages``：OpenAI 格式对话消息（从 AI SDK UI messages 抽取）
    - ``state``：可变状态，含 assistant_text / reply / tool_calls / error
    """

    def __init__(
        self,
        graph: dict,
        variables: dict,
        messages: list[dict],
        ms: UiMessageStream,
        state: dict,
        user_id: int | None = None,
    ) -> None:
        self.graph = graph or {}
        self.nodes: dict[str, dict] = {
            n["id"]: n for n in (self.graph.get("nodes") or [])
        }
        self.edges = self.graph.get("edges") or []
        self.variables = dict(variables or {})
        self.messages = list(messages or [])
        self.ms = ms
        self.state = state
        self.user_id = user_id
        self.outputs: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # 工具函数
    # ------------------------------------------------------------------ #
    def _node(self, node_id: str) -> dict:
        return self.nodes[node_id]

    def _out_edges(self, node_id: str) -> list[dict]:
        return [e for e in self.edges if e.get("source") == node_id]

    def _edge_target(self, node_id: str, source_handle: str | None = None) -> str | None:
        for e in self._out_edges(node_id):
            if source_handle is None or e.get("sourceHandle") == source_handle:
                return e.get("target")
        return None

    def _render(self, template: str | None) -> str:
        return render_template(template, self.variables)

    def _resolve_option(self, val: Any) -> Any:
        """变量取用：若为 ``{"__var__": name}`` 则从变量空间取值。"""
        if isinstance(val, dict) and val.get("__var__"):
            return self.variables.get(val["__var__"])
        return val

    # ------------------------------------------------------------------ #
    # 各节点实现
    # ------------------------------------------------------------------ #
    async def _exec_start(self, node: dict) -> None:
        """初始化输入变量：start.variables 的默认值兜底（显式入参优先）。"""
        for v in (node.get("data") or {}).get("variables") or []:
            name = v.get("name")
            if not name:
                continue
            if name not in self.variables and "default" in v:
                self.variables[name] = v["default"]

    async def _resolve_llm_client(self, data: dict):
        """解析 LLM 节点运行时：返回 (client, runtime, tool_schemas, dispatch)。"""
        from app.plugin.module_ai.provider.service import (
            AiModelService,
            build_headers,
        )

        runtime = None
        if data.get("model_id"):
            runtime = await AiModelService.get_runtime_model(model_id=data["model_id"])
        if not runtime:
            runtime = await AiModelService.get_runtime_model()
        if not runtime:
            raise RuntimeError("未配置大模型，请在 AI 管理→模型配置 中添加并启用")

        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url=runtime["base_url"],
            api_key=runtime["api_key"] or "sk-none",
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-workflow"
            ),
        )
        tool_schemas, dispatch = await self._llm_tools(data)
        return client, runtime, tool_schemas, dispatch

    def _llm_base_messages(self, data: dict, kb_context: str = "") -> list[dict]:
        """组装 LLM 节点输入消息：系统提示词 + 知识库上下文 + 历史消息。"""
        system_prompt = self._render(data.get("prompt") or "")
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if kb_context:
            messages.append({"role": "system", "content": f"参考知识：\n{kb_context}"})
        messages += self.messages
        return messages

    async def _exec_llm(self, node: dict) -> None:
        """LLM 节点：渲染提示词 → 流式调用 → 累积文本；写入输出变量。

        当节点配置 ``require_approval`` 且模型发起工具调用时，透出
        ``tool-approval`` 帧并挂起运行，等待用户审批后经 ``resume_after_approval`` 续跑。
        """
        data = node.get("data") or {}
        client, runtime, tool_schemas, dispatch = await self._resolve_llm_client(data)

        kb_context = ""
        if data.get("knowledge_ids"):
            kb_context, sources = await self._retrieve_context(data)
            if sources:
                yield_src = self.ms.sources(sources)
                if yield_src:
                    yield yield_src
        messages = self._llm_base_messages(data, kb_context)

        kwargs: dict = {
            "model": runtime["model"],
            "messages": messages,
            "temperature": data.get("temperature", runtime["temperature"]),
            "max_tokens": data.get("max_tokens", runtime["max_tokens"]),
            "stream": True,
        }
        if tool_schemas:
            kwargs["tools"] = tool_schemas
            kwargs["tool_choice"] = "auto"

        content = ""
        tool_calls: dict = {}
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                yield_ms = self.ms.reasoning(rc)
                if yield_ms:
                    yield yield_ms
            if getattr(delta, "content", None):
                content += delta.content
                self.state["assistant_text"] += delta.content
                yield_text = self.ms.text(delta.content)
                if yield_text:
                    yield yield_text
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = tool_calls.setdefault(
                    tc.index, {"id": "", "name": "", "arguments": ""}
                )
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments

        yield_reason_end = self.ms.reasoning_end()
        if yield_reason_end:
            yield yield_reason_end
        yield_text_end = self.ms.text_end()
        if yield_text_end:
            yield yield_text_end

        # HITL：需人工审批的工具调用 → 透出审批帧并挂起（不执行工具）
        if tool_calls and tool_schemas and data.get("require_approval"):
            pending = [
                {
                    "toolCallId": s["id"],
                    "toolName": s["name"],
                    "arguments": json.loads(s["arguments"] or "{}") if s["arguments"] else {},
                }
                for s in tool_calls.values()
            ]
            yield_ap = self.ms.tool_approval(pending)
            if yield_ap:
                yield yield_ap
            self.state["pending_approval"] = {
                "node_id": node["id"],
                "llm_messages": messages,
                "tool_calls": tool_calls,
                "content": content,
                "pending": pending,
            }
            self.state["halted"] = True
            self.outputs[node["id"]] = content
            return

        # 工具循环（V1：单轮工具调用后把结果并入本轮文本，供模型继续）
        if tool_calls and tool_schemas:
            for s in tool_calls.values():
                name = s["name"]
                try:
                    args = json.loads(s["arguments"] or "{}") if s["arguments"] else {}
                except Exception:  # noqa: BLE001
                    args = {}
                result = await dispatch(name, args, self.user_id)
                self.state["tool_calls"].append({"name": name, "args": args, "result": result})
                yield_tool = self.ms.tool(s["id"], name, args=args, output=result)
                if yield_tool:
                    yield yield_tool
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": [
                            {
                                "id": s["id"],
                                "type": "function",
                                "function": {"name": s["name"], "arguments": s["arguments"]},
                            }
                        ],
                    }
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": s["id"],
                        "content": json.dumps(result, ensure_ascii=False, default=str)[:4000],
                    }
                )
            # 二次调用聚合工具结果
            content += await self._continue_llm(client, runtime, data, tool_schemas, dispatch)
            yield_text2 = self.ms.text(content)
            if yield_text2:
                yield yield_text2
            yield_text_end2 = self.ms.text_end()
            if yield_text_end2:
                yield yield_text_end2

        self.outputs[node["id"]] = content
        out_var = (data or {}).get("output_variable")
        if out_var:
            self.variables[out_var] = content

    async def _continue_llm(self, client, runtime, data, tool_schemas, dispatch) -> str:
        """工具执行后让模型继续生成最终回复（单轮）。"""
        kwargs: dict = {
            "model": runtime["model"],
            "messages": self.messages,
            "temperature": data.get("temperature", runtime["temperature"]),
            "max_tokens": data.get("max_tokens", runtime["max_tokens"]),
            "stream": False,
        }
        if tool_schemas:
            kwargs["tools"] = tool_schemas
            kwargs["tool_choice"] = "auto"
        try:
            resp = await client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            self.state["assistant_text"] += content
            self.messages.append({"role": "assistant", "content": content})
            return content
        except Exception as e:  # noqa: BLE001
            return f"（工具结果收尾失败：{e}）"

    async def resume_after_approval(
        self, node_id: str, tool_calls: list[dict], decision: str
    ):
        """用户审批后从 LLM 节点续跑：执行/拒绝挂起的工具调用并生成最终回复。

        ``tool_calls`` 为 ``[{"toolCallId","toolName","arguments"}]``，
        ``decision`` 为 ``approve`` / ``reject``。产出 text 帧（异步生成器）。
        """
        node = self._node(node_id)
        data = node.get("data") or {}
        client, runtime, tool_schemas, dispatch = await self._resolve_llm_client(data)

        norm: list[dict] = []
        for t in tool_calls:
            slot = {
                "id": t.get("toolCallId"),
                "name": t.get("toolName"),
                "arguments": json.dumps(t.get("arguments") or {}, ensure_ascii=False),
            }
            norm.append(slot)

        content = ""
        pending = self.state.get("pending_approval") or {}
        base_messages = pending.get("llm_messages") or self._llm_base_messages(data)
        self.messages = list(base_messages)

        for s in norm:
            name = s["name"]
            try:
                args = json.loads(s["arguments"] or "{}") if s["arguments"] else {}
            except Exception:  # noqa: BLE001
                args = {}
            self.messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": s["id"],
                            "type": "function",
                            "function": {"name": s["name"], "arguments": s["arguments"]},
                        }
                    ],
                }
            )
            if decision == "approve":
                result = await dispatch(name, args, self.user_id)
                self.state["tool_calls"].append(
                    {"name": name, "args": args, "result": result}
                )
                yield_tool = self.ms.tool(s["id"], name, args=args, output=result)
                if yield_tool:
                    yield yield_tool
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": s["id"],
                        "content": json.dumps(
                            result, ensure_ascii=False, default=str
                        )[:4000],
                    }
                )
            else:
                self.state["tool_calls"].append(
                    {"name": name, "args": args, "result": {"approved": False}}
                )
                yield_deny = self.ms.tool(s["id"], name, args=args, error="用户拒绝了该工具调用")
                if yield_deny:
                    yield yield_deny
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": s["id"],
                        "content": "用户拒绝了该工具调用。",
                    }
                )

        final = await self._continue_llm(client, runtime, data, tool_schemas, dispatch)
        content = (pending.get("content") or "") + (final or "")
        self.outputs[node_id] = content
        self.state["reply"] = content
        yield_final = self.ms.text(content)
        if yield_final:
            yield yield_final
        yield_end = self.ms.text_end()
        if yield_end:
            yield yield_end

    async def _llm_tools(self, data: dict):
        """解析 LLM 节点绑定的工具名 → schema 与派发器。"""
        names = (data or {}).get("tools") or []
        if not names:
            return [], None
        from app.plugin.module_ai.apps.service import _build_app_tools

        schemas, http_tools = await _build_app_tools(names)

        async def _dispatch(name: str, args: dict, user_id: int | None):
            from app.plugin.module_ai.apps.service import _run_app_tool

            return await _run_app_tool(name, args, user_id, http_tools)

        return schemas, _dispatch

    async def _retrieve_context(self, data: dict) -> tuple[str, list[dict]]:
        """知识检索（RAG）：返回 ``(注入上下文, 引用来源列表)``。

        引用来源供流式 ``sources`` 帧透出，前端可展示知识块标题/片段/相似度。
        检索或模型异常时返回 ``("", [])``，节点可安全跳过。
        """
        try:
            from app.plugin.module_ai.knowledge.service import AiKnowledgeService

            kb_ids = data.get("knowledge_ids")
            query = self._render(data.get("query") or "")
            if not kb_ids or not query:
                return "", []
            top_k = int(data.get("top_k") or 5)
            results = await AiKnowledgeService.search(kb_ids, query, top_k)
            if not results:
                return "", []
            ctx = "\n\n".join(
                f"[来源: {r.get('file_name') or '未知'}] {r.get('content')}" for r in results
            )
            sources = [
                {
                    "title": r.get("file_name") or "未知",
                    "content": (r.get("content") or "")[:200],
                    "score": r.get("score"),
                    "chunkId": r.get("chunk_id"),
                }
                for r in results
            ]
            return ctx, sources
        except Exception:  # noqa: BLE001
            return "", []

    async def _exec_tool(self, node: dict) -> None:
        """工具节点：调用工具目录中的工具并把结果写入变量。"""
        data = node.get("data") or {}
        name = data.get("tool_name")
        if not name:
            raise RuntimeError("工具节点缺少 tool_name")
        from app.plugin.module_ai.tools_catalog.service import dispatch_tool

        args = self._resolve_option(data.get("args") or {})
        if isinstance(args, dict):
            args = {k: self._render(str(v)) for k, v in args.items()}
        result = await dispatch_tool(name, args, self.user_id)
        self.outputs[node["id"]] = result
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = result

    async def _exec_code(self, node: dict) -> None:
        """代码节点：对变量做 Python 表达式转换（受限，单表达式）。

        仅允许读取 ``inputs`` 声明的输入，写回 ``output_variable``；以受限
        命名空间执行（``__builtins__`` 置空），且只放行常量/算术等安全操作。
        """
        data = node.get("data") or {}
        code = (data.get("code") or "").strip()
        fn = data.get("function") or "transform"
        inputs = data.get("inputs") or {}
        scope = {k: self._resolve_option(inputs.get(k)) for k in (inputs or {})}
        try:
            module = ast.parse(code, mode="exec")
            last_expr = None
            if module.body and isinstance(module.body[-1], ast.Expr):
                last_expr = ast.Expression(module.body.pop().value)
            namespace: dict = {"__builtins__": {}}
            namespace.update(scope)
            eval(compile(module, "<wf>", "exec"), namespace, namespace)  # noqa: S307
            if last_expr is not None:
                value = eval(compile(last_expr, "<wf>", "eval"), namespace, namespace)  # noqa: S307
                self.outputs[node["id"]] = value
                out_var = data.get("output_variable")
                if out_var:
                    self.variables[out_var] = value
            else:
                result = namespace.get(fn)
                self.outputs[node["id"]] = result
                out_var = data.get("output_variable")
                if out_var:
                    self.variables[out_var] = result
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"代码节点执行失败：{e}") from e

    async def _exec_condition(self, node: dict) -> None:
        """条件节点：求值表达式并记录命中分支（由执行器决定走 true/false）。"""
        data = node.get("data") or {}
        expr = self._render(data.get("expression") or "")
        self.outputs[node["id"]] = self._eval_condition(expr)

    def _eval_condition(self, expr: str) -> bool:
        """安全求值条件表达式：支持 == != > < >= <= in，基于变量空间。"""
        if not expr:
            return True
        # 仅允许安全的比较表达式，不允许函数调用/属性访问
        allowed = re.compile(r"^[\w\u4e00-\u9fa5\s\.\-+*/%<>=!&|()'\"\[\]:,，。！？]+$")
        if not allowed.match(expr):
            return False
        try:
            return bool(eval(expr, {"__builtins__": {}}, self.variables))  # noqa: S307
        except Exception:  # noqa: BLE001
            return False

    async def _exec_variable(self, node: dict) -> None:
        """变量赋值节点：把值（或上游输出）写入变量。"""
        data = node.get("data") or {}
        name = data.get("name")
        if not name:
            return
        value = self._resolve_option(data.get("value"))
        if isinstance(value, str):
            value = self._render(value)
        self.variables[name] = value
        self.outputs[node["id"]] = value

    async def _exec_http(self, node: dict) -> None:
        """HTTP 节点：发起一次外部 API 请求，把 JSON/文本结果写入变量。

        ``data``：``method`` / ``url`` / ``headers``(dict) / ``body``(模板) /
        ``output_variable``。响应写入 ``{"status", "body", "text"}``。
        """
        data = node.get("data") or {}
        method = (data.get("method") or "GET").upper()
        url = self._render(data.get("url") or "")
        if not url:
            raise RuntimeError("HTTP 节点缺少 url")
        headers = self._resolve_option(data.get("headers") or {})
        if isinstance(headers, dict):
            headers = {k: self._render(str(v)) for k, v in headers.items()}
        body = self._resolve_option(data.get("body"))
        if isinstance(body, str):
            body = self._render(body)
        elif isinstance(body, dict):
            body = {k: (self._render(v) if isinstance(v, str) else v) for k, v in body.items()}
        elif isinstance(body, list):
            body = [self._render(v) if isinstance(v, str) else v for v in body]
        import httpx

        payload = body if isinstance(body, (dict, list)) else body
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method,
                url,
                headers=headers or None,
                json=payload if isinstance(payload, (dict, list)) else None,
                content=None if isinstance(payload, (dict, list)) else (payload or None),
            )
        try:
            parsed: object = resp.json()
        except Exception:  # noqa: BLE001
            parsed = resp.text
        value = {"status": resp.status_code, "body": parsed, "text": resp.text}
        self.outputs[node["id"]] = value
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = parsed

    async def _exec_knowledge(self, node: dict):
        """知识检索节点：检索知识库，透出引用来源并把上下文写入输出变量。

        供下游 LLM 节点通过 ``{{变量}}`` 引用检索到的上下文。
        """
        data = node.get("data") or {}
        kb_context, sources = await self._retrieve_context(data)
        if sources:
            yield_src = self.ms.sources(sources)
            if yield_src:
                yield yield_src
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = kb_context
        elif kb_context:
            # 未指定输出变量时写入默认上下文变量，供下游 LLM 引用
            self.variables["kb_context"] = kb_context
        self.outputs[node["id"]] = kb_context

    async def _exec_end(self, node: dict) -> None:
        """结束节点：组装最终回复（output_template 或最后 LLM 输出）。"""
        data = node.get("data") or {}
        template = data.get("output_template")
        if template:
            final = self._render(template)
        else:
            # 取最近一个 LLM / 变量输出作为最终回复
            final = self.state.get("assistant_text") or ""
            for nid in reversed(list(self.nodes.keys())):
                if self.nodes[nid].get("type") in ("llm", "variable", "tool") and nid in self.outputs:
                    val = self.outputs[nid]
                    if isinstance(val, str) and val:
                        final = val
                        break
        self.outputs[node["id"]] = final
        self.state["reply"] = final

    # ------------------------------------------------------------------ #
    # 主执行
    # ------------------------------------------------------------------ #
    async def run(self):
        """按 DAG 顺序执行全部节点，逐帧产出 SSE 帧（异步生成器）。"""
        start = next(
            (n for n in (self.graph.get("nodes") or []) if n.get("type") == "start"),
            None,
        )
        if not start:
            raise RuntimeError("工作流缺少 start 节点")
        visited: set[str] = set()
        stack: list[str] = [start["id"]]
        while stack:
            node_id = stack.pop()
            if node_id in visited:
                continue
            node = self._node(node_id)
            ntype = node.get("type") or "start"
            if ntype == "start":
                await self._exec_start(node)
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "llm":
                async for frame in self._exec_llm(node):
                    yield frame
                # HITL：LLM 节点挂起等待审批时停止后续节点执行
                if self.state.get("halted"):
                    break
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "tool":
                await self._exec_tool(node)
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "code":
                await self._exec_code(node)
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "condition":
                await self._exec_condition(node)
                # 只走命中分支：true 命中则走 sourceHandle=true，否则走 false
                result = self.outputs.get(node_id)
                handle = "true" if result else "false"
                next_id = self._edge_target(node_id, handle)
                if not next_id:
                    # 无对应 handle 边时回退到无条件边
                    next_id = self._edge_target(node_id)
                if next_id and next_id not in visited:
                    stack.append(next_id)
            elif ntype == "variable":
                await self._exec_variable(node)
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "knowledge":
                async for frame in self._exec_knowledge(node):
                    yield frame
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "http":
                await self._exec_http(node)
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
            elif ntype == "end":
                await self._exec_end(node)
            visited.add(node_id)
