"""问数入口：``ask``（非流式）与 ``ask_stream``（SSE 事件流，2026-11-08 拆出）。

两条入口共用同一套路由：澄清反问 → 指标快路径 → 对象路径 → 慢路径 NL2SQL，
最后都经过 ``_execute_one``（权限网关）取数。``ask_stream`` 额外负责把过程拆成
``meta / ir / reasoning / tool / sql_delta / result / done`` 事件。

跨模块符号（``_build_params`` / ``_execute_metric`` / ``_sql_cache_*`` /
``_OBJECT_CTX`` / ``SYSTEM_DS`` 等）仍归 ``service.py``，这里用 ``_svc.`` 在调用时读取：
导入期不触碰属性（避免循环导入），且测试对 ``service._OBJECT_CTX`` 的 patch 仍然生效。
"""
from __future__ import annotations

from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc
from .dialect import build_system_prompt, dialect_name, templated_note


class AskOps:
    @classmethod
    async def ask(cls, question: str, auth, session_id: int | None = None,
                  datasource: str | None = None, redis=None, force_slow: bool = False,
                  object_code: str | None = None, object_key: str | None = None) -> dict:
        """主入口：意图路由 → 快/慢路径 → 执行 → 落库。"""
        await cls.ensure_system_seed()
        question = (question or "").strip()
        datasource = await _svc._norm_datasource(datasource)
        # 当前对象上下文：**确定性注入**（对齐 Palantir Retrieval Context）。
        # ⚠️ 每次调用都**显式设置**（没有对象时置空）——否则同一个任务里连续调用 ask
        #    （如评测逐题跑）会把上一题的上下文带进下一题。
        _svc._OBJECT_CTX.set(await cls._object_context_block(object_code, object_key, auth))
        if not question:
            raise CustomException(msg="请输入要查询的问题")

        sess = await cls.get_or_create_session(session_id, question[:30], auth)

        # 评测强制慢路径：跳过模板匹配，直接用 LLM 生成 SQL。
        # 注意：这一步必须在加载指标/术语**之前** —— 旧实现先查了 metrics+terms，
        # 慢路径里 `_nl2sql` 又查一遍，等于白跑两次库。
        if force_slow:
            return await cls._slow_path(question, sess["id"], datasource or _svc.SYSTEM_DS, auth)

        # P2 多轮查询重写（G7）：把「那上周呢」补全为自包含问题，随后**重新走一遍路由**
        # （可能命中指标快路径 / 对象查询）。放在 force_slow 之后：评测逐题生成不应受
        # 历史重写影响，保持 A/B 公平。开关默认关，仅在判定不自包含时才多一次 LLM 调用。
        question = await cls._maybe_rewrite(question, sess["id"], datasource)

        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)

        # 澄清反问：命中**确定性歧义**（如「按原煤仓分组」而表里同时有名称/编号两列）
        # → 先问用户，不生成 SQL。猜错的成本远高于问一句。
        # 用户已回答（问句里带【澄清】）则跳过；每轮最多问一次。
        if "【澄清】" not in question:
            try:
                from .clarify import detect_clarify

                schema_map = (
                    await cls._system_schema()
                    if (datasource or _svc.SYSTEM_DS) == _svc.SYSTEM_DS
                    else await cls._ds_schema_map(datasource)
                )
                _c = detect_clarify(question, schema_map)
                if _c:
                    # 澄清这一轮也要**落库**：否则刷新后丢历史、会话标题不更新
                    try:
                        await cls._save_message(
                            sess["id"], question, path="clarify",
                            datasource=datasource or _svc.SYSTEM_DS, sql="", rows=[],
                            summary=_c.get("question") or "需要确认口径", is_error=False,
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] 澄清轮落库失败（忽略）: {str(e)[:100]}")
                    return {"path": "clarify", "clarify": _c, "question": question,
                            "is_error": False, "sql": "", "columns": [], "rows": [],
                            "took_ms": 0, "metric": None, "ontology_used": []}
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 澄清检测失败（忽略，继续正常问答）: {str(e)[:100]}")

        metric = await cls._select_metric(question, datasource, metrics, terms)
        if metric:
            params = _svc._build_params(metric, question)
            try:
                cache_key, cached, res = None, False, None
                ttl = metric.get("cache_ttl") or 0
                if redis and ttl:
                    # 安全补丁：缓存 key 必须含调用者 —— 指标结果是按权限算的
                    cache_key = cls._cache_key(
                        metric, params,
                        user_id=getattr(getattr(auth, "user", None), "id", None))
                    hit = await cls._cache_get(redis, cache_key)
                    if hit is not None:
                        res, cached = hit, True
                if res is None:
                    res = await _svc._execute_metric(metric, params, auth)
                    if redis and ttl and cache_key:
                        await cls._cache_set(redis, cache_key, res, ttl)
                msg = await cls._save_message(
                    sess["id"], question, path="fast", datasource=metric["datasource"],
                    sql=res["sql"], columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0), cached=cached,
                    summary=cls._summarize(metric, res),
                )
                return cls._answer(msg, metric=metric)
            except Exception as e:  # noqa: BLE001
                # 快路径**任何**失败（含驱动异常）都不得整题崩溃 → 记录错误并回退慢路径。
                # 早期只 catch CustomException，裸 ProgrammingError 会直接冒泡（实测 ds:4）。
                reason = getattr(e, "msg", None) or str(e)
                await cls._save_message(
                    sess["id"], question, path="fast", datasource=metric["datasource"],
                    sql=metric["sql_template"], rows=[], is_error=True,
                    summary=f"快路径执行失败：{reason}",
                )
                return await cls._slow_path(question, sess["id"], metric["datasource"], auth)

        # 报表建议（澄清后选择）：未命中指标时，把相关已确认报表作为候选推荐，不自动执行。
        # 放在对象查询前：沉淀的"困难题"比现推更贴近用户意图；关键词命中率高才推荐（防误命中）。
        try:
            sugg = await cls.report_suggest(question, datasource or None)
            if sugg:
                return {"path": "report_suggest", "question": question, "reports": sugg,
                        "is_error": False, "sql": "", "columns": [], "rows": [],
                        "took_ms": 0, "metric": None, "ontology_used": []}
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 报表建议失败（忽略，继续对象/NL2SQL）: {str(e)[:100]}")

        # 对象查询（语义执行层）：LLM 出 IR → 本体实例层执行；任何失败自动降级
        cfg = await cls._cfg()
        if cls._cfg_bool(cfg, "object_query_enabled", False):
            try:
                ans = await cls._object_query_path(
                    question, sess["id"], datasource or _svc.SYSTEM_DS, auth,
                    object_code=object_code, object_key=object_key)
                if ans:
                    return ans
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 对象查询异常，降级 NL2SQL：{str(e)[:120]}")

        # 慢路径
        return await cls._slow_path(question, sess["id"], datasource or _svc.SYSTEM_DS, auth)

    @classmethod
    async def ask_stream(cls, question: str, auth, session_id: int | None = None,
                         datasource: str | None = None, object_code: str | None = None,
                         object_key: str | None = None) -> None:
        """流式问数：产出思考过程/工具调用/输出/最终结果的事件（作为 SSE 下发）。

        事件类型：meta / ir / reasoning_start / reasoning / reasoning_done /
        tool_start / tool_result / tool_error / sql_delta / sql_final /
        result / done / error / answer。
        """
        from .agno_query_tools import build_query_tools

        await cls.ensure_system_seed()
        question = (question or "").strip()
        if not question:
            yield {"type": "error", "message": "请输入要查询的问题"}
            return
        datasource = await _svc._norm_datasource(datasource)
        # 当前对象上下文：与 ask() 同款，**显式设置**（每次调用都覆盖，避免串题）
        _svc._OBJECT_CTX.set(await cls._object_context_block(object_code, object_key, auth))
        sess = await cls.get_or_create_session(session_id, question[:30], auth)
        datasource = datasource or _svc.SYSTEM_DS
        yield {"type": "meta", "session_id": sess["id"], "datasource": datasource,
               "question": question}

        # P2 多轮重写（G7）：把追问补全为自包含问题，随后**重新走路由**（对象查询 / 流式
        # NL2SQL）。meta 已带原始问题，这里只影响后续生成。开关默认关。
        question = await cls._maybe_rewrite(question, sess["id"], datasource)

        # ---- 澄清反问：命中确定性歧义 → 先问用户，不生成 SQL（对齐非流式 ask）----
        if "【澄清】" not in question:
            try:
                from .clarify import detect_clarify

                schema_map = (
                    await cls._system_schema()
                    if (datasource or _svc.SYSTEM_DS) == _svc.SYSTEM_DS
                    else await cls._ds_schema_map(datasource)
                )
                _c = detect_clarify(question, schema_map)
                if _c:
                    # 澄清轮也要落库（与 ask 对齐）：否则刷新后历史里看不到这次追问
                    try:
                        await cls._save_message(
                            sess["id"], question, path="clarify",
                            datasource=datasource, sql="", rows=[],
                            summary=_c.get("question") or "需要确认口径", is_error=False,
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] 流式澄清轮落库失败（忽略）: {str(e)[:100]}")
                    yield {"type": "clarify", "clarify": _c}
                    yield {"type": "done", "path": "clarify", "session_id": sess["id"]}
                    return
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 流式澄清检测失败（忽略）: {str(e)[:80]}")

        # ---- 指标快路径（与 ask 共用 _select_metric）：确定性、零 LLM；命中即流式返回 ----
        try:
            metrics = await cls.list_metrics(datasource)
            terms = await cls.list_terms(datasource)
            metric = await cls._select_metric(question, datasource, metrics, terms)
            if metric:
                params = _svc._build_params(metric, question)
                res = await _svc._execute_metric(metric, params, auth)
                # 摘要本地算一次即可：_save_message 返回的是 ORM 模型（没有 .get()），
                # 之前写成 msg.get("summary") → AttributeError → 被 except 吞掉后
                # **降级走 NL2SQL**，但消息已经提交入库 → 一次提问落 2 条历史消息、
                # 快路径占比统计被污染（单测当时把 _save_message mock 成 dict 了，所以没发现）。
                summary = cls._summarize(metric, res)
                msg = await cls._save_message(
                    sess["id"], question, path="fast", datasource=metric["datasource"],
                    sql=res["sql"], columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0),
                    summary=summary)
                yield {"type": "result", "path": "fast",
                       "columns": res["columns"], "rows": res["rows"],
                       "sql": res.get("sql") or "", "took_ms": res.get("took_ms", 0),
                       "applied": res.get("applied") or [],
                       "policy_ids": res.get("policy_ids") or [],
                       "summary": summary, "message_id": msg.id}
                yield {"type": "done", "path": "fast", "session_id": sess["id"]}
                return
        except Exception as e:  # noqa: BLE001
            # 快路径失败**不得中断 SSE** → 记录并继续走对象/NL2SQL 流式
            log.warning("[query] 流式指标快路径失败，降级：[{}] {}",
                        type(e).__name__, str(e)[:120])

        # ---- 报表建议（澄清后选择）：未命中指标时推荐相关报表，不自动执行、不打断 SSE ----
        try:
            sugg = await cls.report_suggest(question, datasource or None)
            if sugg:
                yield {"type": "report_suggest", "reports": sugg}
                yield {"type": "done", "path": "report_suggest", "session_id": sess["id"]}
                return
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 流式报表建议失败（忽略）：{e!r}")

        # ---- 对象查询（语义执行层）：能出合法 IR 就流式返回，否则继续 NL2SQL 流式 ----
        cfg0 = await cls._cfg()
        if cls._cfg_bool(cfg0, "object_query_enabled", False):
            try:
                ans = await cls._object_query_path(
                    question, sess["id"], datasource, auth,
                    object_code=object_code, object_key=object_key)
            except Exception as e:  # noqa: BLE001
                log.warning("[query] 流式对象查询异常，降级 NL2SQL：[{}] {}",
                            type(e).__name__, str(e)[:120])
                ans = None
            if ans:
                yield {"type": "ir", "ir": ans.get("ir") or {},
                       "object_query": ans.get("object_query") or {},
                       "confidence": ans.get("confidence")}
                yield {"type": "result", "path": "object",
                       "columns": ans.get("columns") or [], "rows": ans.get("rows") or [],
                       "summary": ans.get("summary") or "",
                       "ontology_used": ans.get("ontology_used") or [],
                       "message_id": ans.get("message_id"), "sql": (res.get("sql") or ""), "took_ms": res.get("took_ms", 0), "applied": res.get("applied") or [], "policy_ids": res.get("policy_ids") or []}
                yield {"type": "done", "path": "object", "session_id": sess["id"],
                       "message_id": ans.get("message_id")}
                return

        # ---- SQL 缓存：同一问句直接回放上次生成的 SQL（跳过 LLM） ----
        # 旧实现只有非流式分支有缓存，界面上重复提问要重新生成（10~40s）。
        cached_sql = _svc._sql_cache_get(question, datasource, _svc._auth_scope(auth))
        if cached_sql:
            evs = await cls._finish_sql_stream(question, sess["id"], cached_sql, datasource, auth)
            if any(e.get("type") == "error" for e in evs):
                # 缓存的 SQL 已经跑不通（schema/口径变了）→ 失效并继续重新生成
                _svc._SQL_CACHE.pop(_svc._sql_cache_key(question, datasource, _svc._auth_scope(auth)), None)
                log.warning("[query] 流式缓存 SQL 执行失败，已失效并重新生成：{}", question[:30])
            else:
                yield {"type": "sql_final", "sql": cached_sql, "cached": True}
                for ev in evs:
                    yield ev
                return

        # ---- 构建生成 Agent（与 _nl2sql 工具化模式一致） ----
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"未配置可用的问答模型：{e}"}
            return
        cfg = await cls._cfg()
        rules = []
        if cls._cfg_bool(cfg, "entity_name_rule", True):
            rules.append("（1）问题要求按实体（摄像头/设备/算法/数据集/规则等）展示时，"
                         "应 JOIN 对应表用其「name」列，而不是直接返回外键 id；")
        if cls._cfg_bool(cfg, "enum_hint_enabled", False):
            rules.append("（2）status/framework/severity/task_type 等枚举字段必须使用【取值】里给出的原始值；")
        rules.append("（3）占比用“COUNT(*) * 100.0 / 总数”或“FILTER (WHERE ...)”计算；")
        rules.append("（4）多行 SQL 直接换行输出即可，不要加注释。")
        rules.append("（5）**所有聚合列和计算列必须起中文别名**（如 COUNT(*) AS 告警数、"
                     "SUM(amount) AS 销售额），不要用 c / count / total 这类占位名——"
                     "用户会直接看到列头。")
        if cls._cfg_bool(cfg, "decomposed_planning", True):
            rules.append("（6）先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」，再按此规划生成 SQL；")
        extra = ""
        if cls._cfg_bool(cfg, "full_entity_no_limit", True):
            extra = ("注意：问题若要求列出/统计全量实体（每个摄像头/每台设备/每个数据集/每类…），"
                     "不要为了省事写 LIMIT 截断，应返回全部（系统最多保留 1000 行）。\n")
        schema_ctx = await cls._build_schema_context(question, datasource,
                                                     await cls.list_metrics(datasource),
                                                     await cls.list_terms(datasource),
                                                     principal=await cls._context_principal(auth))
        _dialect, _ds_type = await cls._resolve_dialect_info(datasource)
        system_prompt = build_system_prompt(
            _dialect, rules, schema_ctx, extra + templated_note(_ds_type))

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        _thinking = str(cfg.get("nl2sql_thinking_mode") or "low").strip().lower()
        _extra_body: dict = {}
        if _thinking == "off":
            _extra_body = {"enable_thinking": False}
        elif _thinking == "on":
            _extra_body = {}
        else:
            _extra_body = {"reasoning_effort": "low"}
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime["api_key"] or "sk-none",
            temperature=0.0, max_tokens=_svc.nl2sql_max_tokens(cfg),
            timeout=60,
            # 与非流式 `_nl2sql` 同款：推理型模型默认思考会拖到几十秒
            extra_body=_extra_body or None,
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-query"),
        )
        if cls._cfg_bool(cfg, "agno_tool_agent", False):
            agent = Agent(
                model=model, telemetry=False,
                tools=build_query_tools(auth), tool_call_limit=6,
                instructions=(
                    f"你是 {dialect_name(_dialect)} 数据库查询助手，生成只读 SELECT。"
                    "先调用 search_schema(question) 获取相关表/字段，可再用 "
                    "semantic_search(question) 做向量语义检索、table_metadata(表) 查看元数据标注、"
                    "get_fewshots(question) 参考样例、check_cost(候选SQL) 评估代价；"
                    "获取足够上下文后，最终消息必须直接输出一条 SELECT SQL（不要调用工具、不要多余解释）。"
                    "禁止 DELETE/UPDATE/INSERT/DDL。\n注意：" + "".join(rules)
                ),
            )
        else:
            agent = Agent(model=model, telemetry=False, instructions=system_prompt)

        # ---- 流式运行 Agent，转发思考/工具/输出事件 ----
        content_buf: list[str] = []
        final_content = ""
        sql = ""
        try:
            async for ev in agent.arun(question, stream=True, stream_events=True):
                etype = getattr(ev, "event", "")
                if etype == "RunStarted":
                    yield {"type": "run_start"}
                elif etype == "ReasoningStarted":
                    yield {"type": "reasoning_start"}
                elif etype == "ReasoningContentDelta":
                    yield {"type": "reasoning", "delta": getattr(ev, "reasoning_content", "") or ""}
                elif etype == "ReasoningStep":
                    yield {"type": "reasoning", "delta": getattr(ev, "reasoning_content", "") or getattr(ev, "content", "") or ""}
                elif etype == "ReasoningCompleted":
                    yield {"type": "reasoning_done"}
                elif etype == "ToolCallStarted":
                    tool = getattr(ev, "tool", None)
                    yield {"type": "tool_start",
                           "name": getattr(tool, "tool_name", ""), "call_id": getattr(tool, "tool_call_id", ""),
                           "args": getattr(tool, "tool_args", None)}
                elif etype == "ToolCallCompleted":
                    tool = getattr(ev, "tool", None)
                    yield {"type": "tool_result",
                           "name": getattr(tool, "tool_name", ""),
                           "call_id": getattr(tool, "tool_call_id", ""),
                           "result": getattr(tool, "result", None) or getattr(ev, "content", None)}
                elif etype == "ToolCallError":
                    tool = getattr(ev, "tool", None)
                    yield {"type": "tool_error",
                           "name": getattr(tool, "tool_name", ""), "error": getattr(ev, "error", "") or str(getattr(ev, "content", ""))}
                elif etype == "RunContent":
                    rc = getattr(ev, "reasoning_content", None)
                    if rc:
                        yield {"type": "reasoning", "delta": str(rc)}
                    c = getattr(ev, "content", None)
                    if c:
                        content_buf.append(str(c))
                        yield {"type": "sql_delta", "delta": str(c)}
                elif etype == "RunContentCompleted":
                    yield {"type": "sql_done"}
                elif etype == "RunCompleted":
                    c = getattr(ev, "content", None)
                    if c:
                        final_content = str(c)
                    rc = getattr(ev, "reasoning_content", None)
                    if rc:
                        yield {"type": "reasoning_done"}
                elif etype == "RunError":
                    msg = str(getattr(ev, "content", ""))
                    await cls._save_message(sess["id"], question, path="slow",
                                            datasource=datasource, sql="", rows=[],
                                            is_error=True, summary=f"模型返回错误：{msg}")
                    yield {"type": "error", "message": msg}
                    return
        except Exception as e:  # noqa: BLE001
            await cls._save_message(sess["id"], question, path="slow", datasource=datasource,
                                    sql="", rows=[], is_error=True,
                                    summary=f"问答模型调用失败：{e}")
            yield {"type": "error", "message": f"问答模型(Agno)调用失败：{e}"}
            return

        # ---- 提取并校验 SQL ----
        sql_source = "".join(content_buf) if content_buf else (final_content or "")
        sql = cls._extract_sql(sql_source)
        table = await cls._allowed_for_user(auth) if datasource in (_svc.SYSTEM_DS, None) else None
        try:
            sql = _svc.validate_sql(sql, table or set(), question)
        except Exception as e:  # noqa: BLE001
            # 失败也要落库（与 ask 对齐）：否则界面上这次提问直接消失，事后无法复盘
            await cls._save_message(sess["id"], question, path="slow", datasource=datasource,
                                    sql=sql, rows=[], is_error=True,
                                    summary=f"SQL 校验失败：{e}")
            yield {"type": "error", "message": f"SQL 校验失败：{e}"}
            return
        yield {"type": "sql_final", "sql": sql}

        # ---- 执行并返回结果 ----
        # 本体字段级 ACL：已下沉到 `_execute_one`（ask 与 ask_stream 的共同出口）
        # 统一执行且 fail-closed。修前这里是**唯一**调用点，却包着 `except: pass`
        # ⇒ 检查一炸就等于没做，受限字段被原样查出来；非流式 ask 更是完全不走这里。
        for ev in await cls._finish_sql_stream(question, sess["id"], sql, datasource, auth):
            yield ev
