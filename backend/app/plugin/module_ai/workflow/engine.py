"""低代码工作流运行时引擎（类 Dify 节点 DAG 执行器）。

V1 节点集：``start`` / ``llm`` / ``tool`` / ``code`` / ``condition`` /
``variable`` / ``knowledge``（RAG，阶段 3 落地）/ ``end``。

执行方式：从 ``start`` 节点沿边顺序推进（V1 无并行扇出），``condition`` 按
表达式走 ``sourceHandle`` 为 ``true`` / ``false`` 的分支。``llm`` 节点调用大模型
并**流式**产出 UI Message Stream 帧；各节点输出写入变量命名空间供下游插值。
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.plugin.module_ai.streaming import UiMessageStream

# 匹配 {{变量名}}（兼容中文）
_VAR_RE = re.compile(r"\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}")


def render_template(template: str | None, variables: dict) -> str:
    """替换 ``{{var}}``，未知变量原样保留。"""
    if not template:
        return ""
    return _VAR_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), template)


def _extract_json(text: str) -> Any:
    """从 LLM 输出中提取第一个 JSON 对象/数组；失败返回原文本。"""
    if not text:
        return {}
    text = text.strip()
    for token in ("{", "["):
        start = text.find(token)
        if start == -1:
            continue
        # 做括号配平以切出合法 JSON 片段
        open_ch = token
        close_ch = "}" if token == "{" else "]"
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:  # noqa: BLE001
                        break
    return text


# 节点类型 → 中文标签（供调试追踪显示）
_NODE_LABELS = {
    "start": "开始",
    "llm": "LLM",
    "knowledge": "知识检索",
    "tool": "工具调用",
    "code": "代码转换",
    "condition": "条件分支",
    "variable": "变量赋值",
    "http": "HTTP 请求",
    "iteration": "迭代/批量",
    "classifier": "问题分类器",
    "extractor": "参数提取",
    "template": "模板转换",
    "variable_aggregator": "变量聚合",
    "answer": "回答",
    "sub_workflow": "子工作流",
    "agent": "子智能体",
    "loop": "循环",
    "parallel": "并行",
    "doc_extractor": "文档提取",
    "web_search": "网页搜索",
    "database": "数据库",
    "end": "结束",
}


def _snapshot(value: Any, limit: int = 500) -> Any:
    """输出快照：过大/二进制值截断转字符串，便于前端展示。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, (dict, list)):
        try:
            s = json.dumps(value, ensure_ascii=False, default=str)
            if len(s) <= limit:
                return value
            return s[:limit] + "…"
        except Exception:  # noqa: BLE001
            return str(value)[:limit]
    return value


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
        initial_outputs: dict | None = None,
        initial_visited: set | None = None,
        initial_stack: list | None = None,
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
        self.outputs: dict[str, Any] = dict(initial_outputs or {})
        self._initial_visited = set(initial_visited or [])
        self._initial_stack = list(initial_stack or [])
        self._visited: set[str] = set(self._initial_visited)
        self._stack: list[str] = list(self._initial_stack)
        self._completed = False

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

    def _node_input(self, node: dict) -> dict:
        """采集节点输入：解析 data 中引用到的变量，生成「输入」快照供前端展示。

        仅保留含 ``{{变量}}`` 的字符串字段的解析结果，避免把整份配置原样透出。
        """
        data = node.get("data") or {}
        resolved: dict = {}

        def _walk(val: Any, key: str) -> None:
            if isinstance(val, str):
                if "{{" in val:
                    resolved[key] = self._render(val)
            elif isinstance(val, dict):
                for k, v in val.items():
                    _walk(v, f"{key}.{k}" if key else k)
            elif isinstance(val, list):
                for i, v in enumerate(val):
                    _walk(v, f"{key}[{i}]" if key else str(i))

        _walk(data, "")
        return _snapshot(resolved, limit=800)

    # ---------------------------- 单节点调试 ---------------------------- #
    async def _exec_single(self, node: dict) -> AsyncIterator[Any]:
        """仅执行单个节点（调试用）：按类型分派，流式节点透传帧。"""
        ntype = node.get("type") or "start"
        if ntype == "llm":
            async for f in self._exec_llm(node):
                yield f
        elif ntype == "agent":
            async for f in self._exec_agent(node):
                yield f
        elif ntype == "knowledge":
            async for f in self._exec_knowledge(node):
                yield f
        elif ntype == "sub_workflow":
            async for f in self._exec_sub_workflow(node):
                yield f
        elif ntype == "start":
            await self._exec_start(node)
        elif ntype == "end":
            await self._exec_end(node)
        elif ntype == "tool":
            await self._exec_tool(node)
        elif ntype == "code":
            await self._exec_code(node)
        elif ntype == "condition":
            await self._exec_condition(node)
        elif ntype == "variable":
            await self._exec_variable(node)
        elif ntype == "http":
            await self._exec_http(node)
        elif ntype == "iteration":
            await self._exec_iteration(node)
        elif ntype == "classifier":
            await self._exec_classifier(node)
        elif ntype == "extractor":
            await self._exec_extractor(node)
        elif ntype == "template":
            await self._exec_template(node)
        elif ntype == "variable_aggregator":
            await self._exec_variable_aggregator(node)
        elif ntype == "answer":
            await self._exec_answer(node)
        elif ntype == "loop":
            await self._exec_loop(node)
        elif ntype == "parallel":
            await self._exec_parallel(node)
        elif ntype == "doc_extractor":
            await self._exec_doc_extractor(node)
        elif ntype == "web_search":
            await self._exec_web_search(node)
        elif ntype == "database":
            await self._exec_database(node)

    async def run_single(self, node_id: str):
        """调试：运行单个节点（带给定变量），产出 node-status/输出帧。"""
        node = self._node(node_id)
        if not node:
            raise RuntimeError("节点不存在")
        ntype = node.get("type") or "start"
        label = _NODE_LABELS.get(ntype, ntype)
        yield self.ms.node_status(node_id, "running", label, input=self._node_input(node))
        try:
            async for frame in self._exec_single(node):
                yield frame
        except Exception as e:  # noqa: BLE001
            yield self.ms.node_status(
                node_id, "error", label, input=self._node_input(node), error=str(e)
            )
            yield self.ms.error(str(e))
            return
        yield self.ms.node_status(
            node_id, "success", label, input=self._node_input(node), output=_snapshot(self.outputs.get(node_id))
        )

    # ------------------------------------------------------------------ #
    # 各节点实现
    # ------------------------------------------------------------------ #
    async def _exec_start(self, node: dict) -> None:
        """初始化输入变量：start.variables 的默认值兜底（显式入参优先），并校验必填项。"""
        missing = []
        for v in (node.get("data") or {}).get("variables") or []:
            name = v.get("name")
            if not name:
                continue
            if name not in self.variables and "default" in v:
                self.variables[name] = v["default"]
            if v.get("required") and name not in self.variables:
                missing.append(name)
        if missing:
            raise RuntimeError(f"缺少必填输入变量：{', '.join(missing)}")

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

    # ---------------------------- 文档提取 / 网页搜索 / 数据库 ---------------------------- #
    @staticmethod
    def _strip_html(raw: str) -> str:
        """剥离 HTML 标签，提取纯文本。"""
        import html as html_mod

        t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        t = re.sub(r"(?s)<[^>]+>", " ", t)
        t = html_mod.unescape(t)
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n", t)
        return t.strip()

    @staticmethod
    def _format_search_results(obj) -> str | None:
        """从搜索 API JSON 中抽取常见结果数组，格式化为可读文本。"""
        items = None
        if isinstance(obj, dict):
            for key in ("results", "data", "items", "organic", "organic_results", "web", "news", "value"):
                if isinstance(obj.get(key), list) and obj[key]:
                    items = obj[key]
                    break
        elif isinstance(obj, list):
            items = obj
        else:
            return None
        lines = []
        for it in items:
            if isinstance(it, str):
                lines.append(it)
            elif isinstance(it, dict):
                title = it.get("title") or it.get("name") or ""
                link = it.get("link") or it.get("url") or it.get("href") or it.get("snippet_url") or ""
                snip = it.get("snippet") or it.get("description") or it.get("abstract") or ""
                outline = " | ".join(p for p in (title, link, snip) if p)
                if outline:
                    lines.append(outline)
        return "\n".join(lines) if lines else None

    async def _exec_doc_extractor(self, node: dict) -> None:
        """文档提取节点：抓取 URL 页面或内联文本，剥离标签得到纯文本。

        ``data``：``url``(模板，可选)、``source``(内联文本/模板)、``output_variable``。
        二者都给出时优先 url。
        """
        data = node.get("data") or {}
        url = self._render(data.get("url") or "")
        txt = ""
        if url:
            import httpx

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                txt = resp.text
            else:
                txt = self._strip_html(resp.text)
        else:
            txt = self._render(data.get("source") or "")
            if "<" in txt and ">" in txt:
                txt = self._strip_html(txt)
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = txt
        self.outputs[node["id"]] = txt

    async def _exec_web_search(self, node: dict) -> None:
        """网页搜索节点：调用可配置搜索 API，把结果文本写入变量。

        ``data``：``query``(模板)、``endpoint``(URL，含 ``{{query}}`` 占位)、
        ``api_key``(可选)、``output_variable``。
        """
        data = node.get("data") or {}
        query = self._render(data.get("query") or "")
        if not query:
            raise RuntimeError("网页搜索节点缺少 query")
        endpoint = self._render(data.get("endpoint") or "")
        if not endpoint:
            raise RuntimeError("网页搜索节点缺少 endpoint")
        import urllib.parse

        import httpx

        url = endpoint.replace("{{query}}", urllib.parse.quote(query))
        headers = {"User-Agent": "Mozilla/5.0"}
        api_key = self._render(data.get("api_key") or "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
        try:
            obj = resp.json()
        except Exception:  # noqa: BLE001
            obj = resp.text
        text_out = self._format_search_results(obj)
        if text_out is None:
            text_out = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = text_out
        self.outputs[node["id"]] = text_out

    async def _exec_database(self, node: dict) -> None:
        """数据库查询节点：对给定 DSN 执行 SQL，返回行列表。

        ``data``：``dsn``(如 ``postgresql+asyncpg://...`` 或 ``sqlite+aiosqlite://...``)、
        ``sql``(模板，可含 ``{{变量}}``)、``output_variable``。
        """
        data = node.get("data") or {}
        dsn = self._render(data.get("dsn") or "")
        if not dsn:
            raise RuntimeError("数据库节点缺少 dsn")
        sql = self._render(data.get("sql") or "")
        if not sql:
            raise RuntimeError("数据库节点缺少 sql")
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(dsn)
        try:
            async with engine.connect() as conn:
                res = await conn.execute(text(sql))
                rows = [dict(r._mapping) for r in res]
        finally:
            await engine.dispose()
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = rows
        self.outputs[node["id"]] = rows

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

    async def _exec_iteration(self, node: dict) -> None:
        """迭代/循环节点：遍历列表并对每项调用指定工具，聚合结果为数组。

        ``data``：``items``(列表变量引用或内联数组/模板)、``tool_name``、
        ``args``(可含 ``{{item}}``)、``output_variable``、``max_iterations``。
        """
        data = node.get("data") or {}
        items = self._resolve_option(data.get("items"))
        if isinstance(items, str):
            rendered = self._render(items)
            try:
                parsed = json.loads(rendered)
            except Exception:  # noqa: BLE001
                parsed = rendered
            items = parsed if isinstance(parsed, list) else [rendered]
        if items is None:
            items = []
        if not isinstance(items, list):
            items = [items] if items else []
        max_iter = int(data.get("max_iterations") or 20)
        items = items[:max_iter]
        tool_name = data.get("tool_name")
        results: list = []
        from app.plugin.module_ai.tools_catalog.service import dispatch_tool

        for item in items:
            self.variables["item"] = item
            args = self._resolve_option(data.get("args") or {})
            if isinstance(args, dict):
                args = {k: self._render(str(v)) for k, v in args.items()}
            if tool_name:
                results.append(await dispatch_tool(tool_name, args, self.user_id))
            else:
                results.append(item)
        self.outputs[node["id"]] = results
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = results

    async def _exec_classifier(self, node: dict) -> None:
        """问题分类器：LLM 把输入归类到预设类别，并按类别路由到对应分支。

        命中类别后写 ``output_variable``，执行器按 ``sourceHandle == 类别`` 选边。
        """
        data = node.get("data") or {}
        client, runtime, _tools, _dispatch = await self._resolve_llm_client(data)
        categories = data.get("categories") or []
        if not categories:
            raise RuntimeError("分类器缺少 categories")
        query = self._render(data.get("query") or "") or ""
        if not query:
            query = self.state.get("assistant_text") or ""
        prompt = (
            "你是问题分类器。把用户问题归入下列类别之一，只输出类别名，不要其它文字。\n"
            f"类别：{'、'.join(categories)}\n问题：{query}"
        )
        resp = await client.chat.completions.create(
            model=runtime["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=32,
            stream=False,
        )
        text = ""
        if isinstance(resp, dict):
            text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        else:
            try:
                text = resp.choices[0].message.content or ""
            except Exception:  # noqa: BLE001
                text = ""
        category = next((c for c in categories if c and c in text), (categories[0] or ""))
        self.outputs[node["id"]] = category
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = category

    async def _exec_extractor(self, node: dict) -> None:
        """参数提取（JSON 输出）节点：LLM 按 schema 从输入抽取 JSON 对象写变量。"""
        data = node.get("data") or {}
        client, runtime, _tools, _dispatch = await self._resolve_llm_client(data)
        schema = data.get("schema") or []
        query = self._render(data.get("query") or "") or ""
        if not query:
            query = self.state.get("assistant_text") or ""
        prompt = (
            "你是信息抽取器。根据给定字段从输入中提取 JSON 对象，只输出 JSON，不要其它文字。\n"
            f"字段：{json.dumps(schema, ensure_ascii=False)}\n输入：{query}"
        )
        resp = await client.chat.completions.create(
            model=runtime["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=256,
            stream=False,
        )
        text = ""
        if isinstance(resp, dict):
            text = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        else:
            try:
                text = resp.choices[0].message.content or ""
            except Exception:  # noqa: BLE001
                text = ""
        parsed = _extract_json(text)
        self.outputs[node["id"]] = parsed
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = parsed

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

    async def _exec_template(self, node: dict) -> None:
        """模板节点：对模板做 ``{{变量}}`` 替换，产出文本/JSON 到输出变量。

        ``data``：``template``（支持 {{var}} 与 Jinja 风格）、``output_variable``。
        """
        data = node.get("data") or {}
        rendered = self._render(data.get("template") or "")
        # 若结果是合法 JSON 则解析成对象，否则保留字符串
        try:
            value = json.loads(rendered) if rendered.strip().startswith(("{", "[")) else rendered
        except Exception:  # noqa: BLE001
            value = rendered
        self.outputs[node["id"]] = value
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = value

    async def _exec_variable_aggregator(self, node: dict) -> None:
        """变量聚合节点：把多个字段/变量合并成一个对象。

        ``data``：``fields``=[{"name","value"}]，value 可为 ``{"__var__": name}``
        变量引用、字面量或带 ``{{var}}`` 的模板；``output_variable``。
        """
        data = node.get("data") or {}
        result: dict = {}
        for f in (data.get("fields") or []):
            name = f.get("name")
            if not name:
                continue
            val = self._resolve_option(f.get("value"))
            if isinstance(val, str):
                val = self._render(val)
            result[name] = val
        self.outputs[node["id"]] = result
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = result

    async def _exec_answer(self, node: dict) -> AsyncIterator[Any]:
        """回答节点：在任意位置向用户流式输出一段文本（可引用变量）。"""
        data = node.get("data") or {}
        text = self._render(data.get("output_template") or "") or self.state.get("assistant_text") or ""
        self.outputs[node["id"]] = text
        self.state["reply"] = text
        if text:
            yield_ms = self.ms.text(text)
            if yield_ms:
                yield yield_ms
            yield_end = self.ms.text_end()
            if yield_end:
                yield yield_end

    async def _exec_sub_workflow(self, node: dict) -> AsyncIterator[Any]:
        """子工作流节点：以给定变量调用另一工作流（嵌套），透传其回复。

        ``data``：``workflow_id``、``variables``(可选，模板/变量引用)。
        子工作流的流式帧转发到当前消息流，使回复始终可见。
        """
        data = node.get("data") or {}
        wf_id = data.get("workflow_id")
        if not wf_id:
            raise RuntimeError("子工作流节点缺少 workflow_id")
        from app.plugin.module_ai.workflow.service import AiWorkflowService

        sub = await AiWorkflowService.get_workflow(int(wf_id))
        if not sub:
            raise RuntimeError(f"子工作流 {wf_id} 不存在")
        sub_vars = dict(self.variables)
        supplied = self._resolve_option(data.get("variables"))
        if isinstance(supplied, dict):
            for k, v in supplied.items():
                sub_vars[k] = self._render(str(v)) if isinstance(v, str) else v
        sub_engine = WorkflowEngine(
            graph=sub["graph"] or {"nodes": [], "edges": []},
            variables=sub_vars,
            messages=[],
            ms=self.ms,
            state={},
            user_id=self.user_id,
        )
        async for frame in sub_engine.run():
            yield frame
        reply = sub_engine.state.get("reply") or sub_engine.state.get("assistant_text") or ""
        self.outputs[node["id"]] = reply
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = reply

    async def _exec_agent(self, node: dict) -> AsyncIterator[Any]:
        """子智能体节点：调用另一 AI 智能体（若其绑定工作流则走子工作流，
        否则按模型+提示词+知识库执行），透传回复。

        ``data``：``agent_id``、``query``(用户输入模板，可选)。
        """
        data = node.get("data") or {}
        agent_id = data.get("agent_id")
        if not agent_id:
            raise RuntimeError("子智能体节点缺少 agent_id")
        from app.plugin.module_ai.agent.service import AiAgentService

        agent = await AiAgentService.get_agent(int(agent_id))
        if not agent:
            raise RuntimeError(f"子智能体 {agent_id} 不存在")
        query = self._render(data.get("query") or "") or ""
        if not query:
            query = self.state.get("assistant_text") or ""

        # 绑定工作流：委托子工作流
        if agent.get("workflow_id"):
            sub_node = {
                "id": node["id"],
                "type": "sub_workflow",
                "data": {
                    "workflow_id": agent["workflow_id"],
                    "variables": {"query": query, "user_text": query},
                    "output_variable": data.get("output_variable") or "",
                },
            }
            async for frame in self._exec_sub_workflow(sub_node):
                yield frame
            self.outputs[node["id"]] = self.outputs.get(node["id"])
            return

        # 未绑定工作流：按智能体模型+提示词+知识库执行
        agent_vars = {**self.variables, "query": query, "user_text": query, "assistant_text": query}
        saved = self.variables
        self.variables = agent_vars
        kb_context = ""
        if agent.get("knowledge_ids"):
            kb_context, sources = await self._retrieve_context(
                {"knowledge_ids": agent["knowledge_ids"], "query": query}
            )
            if sources:
                yield_src = self.ms.sources(sources)
                if yield_src:
                    yield yield_src
        try:
            llm_node = {
                "id": node["id"],
                "type": "llm",
                "data": {
                    "model_id": agent.get("model_id") or None,
                    "prompt": agent.get("agent_role") or agent.get("description") or "你是智能助手。",
                    "temperature": agent.get("temperature") or 0.7,
                    "tools": agent.get("tool_ids") or [],
                    "knowledge_ids": agent.get("knowledge_ids") or [],
                    "output_variable": data.get("output_variable") or "",
                },
            }
            async for frame in self._exec_llm(llm_node):
                yield frame
        finally:
            self.variables = saved
        self.outputs[node["id"]] = self.outputs.get(node["id"])

    # ---------------------------- 循环 / 并行（子图语义） ---------------------------- #
    async def _resolve_workflow(self, wf_id):
        """解析工作流定义，供循环体/并行分支复用。"""
        from app.plugin.module_ai.workflow.service import AiWorkflowService

        return await AiWorkflowService.get_workflow(int(wf_id))

    async def _run_workflow_graph(self, graph, variables) -> Any:
        """以给定变量运行一段工作流图（丢弃内部帧），返回最终回复/最后输出。"""
        inner = WorkflowEngine(
            graph=graph or {"nodes": [], "edges": []},
            variables=dict(variables),
            messages=self.messages,
            ms=UiMessageStream(),
            state={},
            user_id=self.user_id,
        )
        async for _ in inner.run():
            pass
        out = inner.state.get("reply")
        if out is None:
            for v in inner.outputs.values():
                if isinstance(v, str) and v:
                    out = v
        return out

    async def _exec_loop(self, node: dict) -> None:
        """循环节点：对列表逐项运行「循环体工作流」，聚合每次结果。

        ``data``：``items``(列表变量/内联列表)、``body_workflow_id``(循环体工作流)、
        ``max_iterations``、``output_variable``。每项把 ``item`` 注入循环体变量。
        """
        data = node.get("data") or {}
        wf_id = data.get("body_workflow_id")
        if not wf_id:
            raise RuntimeError("循环节点缺少循环体工作流 body_workflow_id")
        wf = await self._resolve_workflow(wf_id)
        items = self._resolve_option(data.get("items"))
        if isinstance(items, str):
            rendered = self._render(items)
            try:
                parsed = json.loads(rendered)
            except Exception:  # noqa: BLE001
                parsed = rendered
            items = parsed if isinstance(parsed, list) else [rendered]
        if items is None:
            items = []
        if not isinstance(items, list):
            items = [items] if items else []
        max_iter = int(data.get("max_iterations") or 50)
        items = items[:max_iter]
        results = []
        for item in items:
            sub_vars = {**self.variables, "item": item, "loop_item": item}
            results.append(await self._run_workflow_graph(wf["graph"], sub_vars))
        self.outputs[node["id"]] = results
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = results

    async def _exec_parallel(self, node: dict) -> None:
        """并行节点：并发运行多个分支工作流，聚合为 ``{分支名: 输出}``。

        ``data``：``branches``=[{"name","workflow_id"}]、``output_variable``。
        """
        data = node.get("data") or {}
        branches = data.get("branches") or []

        async def _one(b: dict):
            wf = await self._resolve_workflow(b.get("workflow_id"))
            out = await self._run_workflow_graph(wf["graph"], dict(self.variables))
            return (b.get("name") or b.get("id") or "branch", out)

        outs = await asyncio.gather(*[_one(b) for b in branches])
        results = dict(outs)
        self.outputs[node["id"]] = results
        out_var = data.get("output_variable")
        if out_var:
            self.variables[out_var] = results

    # ------------------------------------------------------------------ #
    # 主执行
    # ------------------------------------------------------------------ #
    async def run(self, budget: int | None = None):
        """按 DAG 顺序执行全部节点，逐帧产出 SSE 帧（异步生成器）。

        每个节点执行前/后产出 ``node-status`` 帧（running/success/error），
        前端据此高亮当前节点并展示各节点的输入输出。

        ``budget``：限制本次执行的节点数量（逐步调试用）；耗尽后暂停，前端可持
        frontier 续跑。默认 ``None`` 表示一次性执行到底。
        """
        start = next(
            (n for n in (self.graph.get("nodes") or []) if n.get("type") == "start"),
            None,
        )
        if not start:
            raise RuntimeError("工作流缺少 start 节点")
        visited: set[str] = set(self._visited)
        stack: list[str] = list(self._stack) or [start["id"]]
        executed = 0

        def _snapshot_frontier() -> None:
            self._visited = set(visited)
            self._stack = list(stack)

        while stack:
            node_id = stack.pop()
            if node_id in visited:
                continue
            node = self._node(node_id)
            ntype = node.get("type") or "start"
            label = _NODE_LABELS.get(ntype, ntype)
            executed += 1
            # 禁用节点：跳过执行，直接走下游边
            if (node.get("data") or {}).get("enabled", True) is False:
                yield self.ms.node_status(node_id, "skipped", label, input=self._node_input(node))
                next_id = self._edge_target(node_id)
                if next_id:
                    stack.append(next_id)
                visited.add(node_id)
                _snapshot_frontier()
                if budget is not None and executed >= budget:
                    break
                continue
            yield self.ms.node_status(node_id, "running", label, input=self._node_input(node))
            try:
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
                        yield self.ms.node_status(
                            node_id, "success", label, input=self._node_input(node), output=_snapshot(self.outputs.get(node_id))
                        )
                        visited.add(node_id)
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
                    result = self.outputs.get(node_id)
                    handle = "true" if result else "false"
                    next_id = self._edge_target(node_id, handle)
                    if not next_id:
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
                elif ntype == "iteration":
                    await self._exec_iteration(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "classifier":
                    await self._exec_classifier(node)
                    cat = self.outputs.get(node_id)
                    next_id = self._edge_target(node_id, str(cat)) if cat else None
                    if not next_id:
                        next_id = self._edge_target(node_id)
                    if next_id and next_id not in visited:
                        stack.append(next_id)
                elif ntype == "extractor":
                    await self._exec_extractor(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "template":
                    await self._exec_template(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "variable_aggregator":
                    await self._exec_variable_aggregator(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "answer":
                    async for frame in self._exec_answer(node):
                        yield frame
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "sub_workflow":
                    async for frame in self._exec_sub_workflow(node):
                        yield frame
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "agent":
                    async for frame in self._exec_agent(node):
                        yield frame
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "loop":
                    await self._exec_loop(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "parallel":
                    await self._exec_parallel(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "doc_extractor":
                    await self._exec_doc_extractor(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "web_search":
                    await self._exec_web_search(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "database":
                    await self._exec_database(node)
                    next_id = self._edge_target(node_id)
                    if next_id:
                        stack.append(next_id)
                elif ntype == "end":
                    await self._exec_end(node)
            except Exception as e:  # noqa: BLE001
                yield self.ms.node_status(node_id, "error", label, error=str(e), input=self._node_input(node))
                self.state["error"] = str(e)
                yield self.ms.error(str(e))
                break
            yield self.ms.node_status(
                node_id, "success", label, input=self._node_input(node), output=_snapshot(self.outputs.get(node_id))
            )
            visited.add(node_id)
            _snapshot_frontier()
            if budget is not None and executed >= budget:
                break
        self._completed = not stack
        self._visited = set(visited)
        self._stack = list(stack)
