"""NL2SQL：``_nl2sql``（2026-11-08 从 service.py 拆出）。

用 agno Agent 把问题 + 裁剪后的 schema 上下文 + 快照样例变成一条只读 SQL。
``prev_error`` 是上一次执行报错（自纠错）；``thinking`` 可强制思考档位
（模型偶发把预算全花在推理上、返回空内容，重试传 ``off`` 能显著提高出 SQL 概率）。

``nl2sql_max_tokens`` / ``validate_sql`` / ``SYSTEM_DS`` 仍归 ``service.py``，
这里用 ``_svc.`` 在调用时读取（延迟解析避免循环导入，也保留测试打桩）。
"""
from __future__ import annotations

import asyncio
import time

from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc
from .dialect import build_system_prompt, dialect_name, templated_note


class Nl2SqlOps:
    @classmethod
    async def _nl2sql(cls, question: str, datasource: str, prev_error: str | None = None,
                      temperature: float = 0.0, auth=None,
                      thinking: str | None = None) -> str:
        """Agno Agent 生成 SQL（慢路径）。prev_error 为上一次执行报错，用于自纠错。

        ``thinking`` 可强制覆盖「思考档位」（off/low/on）：模型偶发把预算全花在推理上
        返回空内容，重试时传 ``off`` 能显著提高出 SQL 的概率（见 ``_slow_path``）。
        """
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"未配置可用的问答模型：{e}")
        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)
        t_p0 = time.perf_counter()
        schema_ctx = await cls._build_schema_context(question, datasource, metrics, terms,
                                                     principal=await cls._context_principal(auth))
        t_p1 = time.perf_counter()
        # 留痕：prompt 体积。生成耗时几乎全在 prefill 上，prompt 一大就慢，
        # 所以这个数字必须可见（实测全量倾倒时 37K 字符 → 生成 7s）
        log.warning("[query] prompt 长度={} 字符（schema 构建={}ms）",
                    len(schema_ctx), int((t_p1 - t_p0) * 1000))
        cfg = await cls._cfg()
        # 两段式分解：**多步题先出执行计划**（可检查的中间产物），再据计划写 SQL。
        # 失败即**降级**为单段生成（绝不因计划失败而答不出来）。
        # ⚠️ 独立开关、**默认关**：实测对个别题会把 SQL 变空（prompt 变长 + 模型只输出计划），
        #    必须先用留出法 A/B 验证再决定是否默认开启。
        if cls._cfg_bool(cfg, "two_stage_planning", False):
            try:
                from .plan import format_plan, is_multistep, parse_plan, plan_prompt

                if is_multistep(question):
                    # 必须把**真实表清单**给第一段：它看不到 schema，不给词表就只能编表名，
                    # 而编出来的名字会被第二段当成计划执行 → 毒先验（实测 −7.55 分 + 错误率 +9.4%）。
                    _sch = await cls._ds_schema_map(datasource or "")
                    _plan_text = await cls._plan_llm(
                        plan_prompt(question, tables=list(_sch.keys())), runtime, temperature
                    )
                    _plan = parse_plan(_plan_text)
                    # 约束：只保留**在真实 schema 里**的表；编出来的直接丢掉（宁可降级，不可毒化）
                    if _plan:
                        _ok_tables = [t for t in (_plan.get("tables") or []) if t in _sch]
                        if not _ok_tables:
                            _plan = None
                            log.warning("[query] 两段式：计划里的表名全都不在 schema 中，丢弃计划")
                        else:
                            _plan["tables"] = _ok_tables
                    if _plan:
                        schema_ctx = schema_ctx + "\n\n" + format_plan(_plan)
                        log.warning("[query] 两段式：计划已生成（表 {} 张）",
                                    len(_plan.get("tables") or []))
                    else:
                        log.warning("[query] 两段式：计划解析失败，降级为单段生成")
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 计划阶段失败，降级为单段生成: {str(e)[:100]}")
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
        rules.append(
            "（7）先看要的是「明细」还是「汇总」：出现 平均/均值/占比/百分比/比例/最多/最少/最高/最低/"
            "最大/最小 时，**先按组聚合、再在外层汇总或取 TOP1**"
            "（例：平均每个供应商关联几个矿点 = AVG(每组 COUNT)；关联最多的那家占多少 = 按组计数后 "
            "ORDER BY 计数 DESC LIMIT 1）；这类题即使句式里有「每个/各」，也**不要**返回全量分组明细。"
        )
        extra = ""
        if cls._cfg_bool(cfg, "full_entity_no_limit", True):
            # 全量列举与「组上聚合」是**互斥**的两种诉求：
            # 前者要求别截断（每个/各/所有…），后者要求先聚合再取一个数（平均/占比/最多…）。
            # 旧实现无条件贴"全量列举"提示，实测把「最多的那家占全部关系的百分之多少」
            # 引成了 53 行分组清单（正确答案 1 行）。
            if _svc._wants_full_list(question):
                extra = ("注意：问题若要求列出/统计全量实体（每个摄像头/每台设备/每个数据集/每类…），"
                         "不要为了省事写 LIMIT 截断，应返回全部（系统最多保留 1000 行）。\n")
            else:
                extra = ("注意：若问的是「平均每个…」「最多的/最少的那一个是谁」「占多少比例」，"
                         "要**先按组聚合、再在外层算一个数或取 TOP1**"
                         "（如 AVG(每组计数)、或 ORDER BY 计数 DESC LIMIT 1），"
                         "不要返回整张分组清单。\n")
        _dialect, _ds_type = await cls._resolve_dialect_info(datasource)
        system_prompt = build_system_prompt(
            _dialect, rules, schema_ctx, extra + templated_note(_ds_type))
        user_msg = question
        if prev_error:
            user_msg = (
                f"{question}\n\n注意：你上次的 SQL 存在问题：\n{prev_error}\n"
                "请修正 SQL（补全 FROM、改用正确表/列名、修正条件）后重新只返回一条 SQL。"
            )
        try:
            from agno.agent import Agent
            from agno.models.openai.like import OpenAILike

            from app.plugin.module_ai.models.service import build_headers

            # 必须注入网关请求头：opencode 网关要求 `x-opencode-session`，
            # 缺了它会直接返回一段错误文本，而那段文本会被当成 SQL 去校验，
            # 最终表现为「仅允许 SELECT 查询」——完全看不出真实原因。
            # 本文件其它两处（embedding / 检索）都用了 build_headers，这里漏了。
            # 思考长度控制（关键）：模型是**推理型**，thinking **计入 max_tokens**。
            # 之前把 max_tokens 从 2000 提到 8000（为了不被推理吃光而返回空 SQL），
            # 等于给了思考 8000 token 的预算 → 难题会想到**几分钟**（实测最长 467 秒）。
            # 实测同一难题：无限制 22.3s ｜ reasoning_effort=low 4.6s ｜ enable_thinking=false 3.8s
            # 现在把"思考"与"SQL 输出"**分开控制**：SQL 输出仍给足空间，思考被压住。
            _thinking = str(thinking or cfg.get("nl2sql_thinking_mode") or "low").strip().lower()
            _extra: dict = {}
            if _thinking == "off":
                _extra = {"enable_thinking": False}
            elif _thinking == "on":
                _extra = {}          # 完全不限制（会重现长尾，仅用于排查）
            else:
                _extra = {"reasoning_effort": "low"}   # 默认：保留少量思考
            model = OpenAILike(
                id=runtime["model"], base_url=runtime["base_url"],
                api_key=runtime["api_key"] or "sk-none",
                temperature=temperature, max_tokens=_svc.nl2sql_max_tokens(cfg),
                # 超时兜底：本地模型偶发长时间不返回 / 返回空。没有超时会把一次
                # 问答拖到几十秒（实测 32 秒换一个错误，是最差的体验）。
                timeout=60,
                extra_body=_extra or None,
                default_headers=build_headers(
                    runtime["base_url"], runtime.get("extra_headers"), "aistation-query"),
            )
            # 默认**关掉工具往返**：实测每题触发 ~7.25 次工具调用，每次都是一轮
            # LLM 往返；而工具能提供的信息（表结构 / 枚举值 / few-shot / join 路径 /
            # 代价护栏 / 执行校验）本地检索与本地执行已全覆盖——花 7 次往返去
            # "自主检索"是纯亏。执行反馈自纠错仍在（_slow_path 的 attempt 循环
            # 会带真实报错重新生成）。
            tool_agent = cls._cfg_bool(cfg, "agno_tool_agent", False)
            if tool_agent:
                # 工具化 Agent：让模型自主决定何时调用 schema/fewshots/cost 工具
                # （执行层不再叠加额外执行工具，避免重复；schema/fewshot 由模型自主检索）
                # P0-4：工具按请求构造，执行类工具绑定当前调用者身份（走同一份 ACL）
                from .agno_query_tools import build_query_tools

                agent = Agent(
                    model=model,
                    telemetry=False,
                    tools=build_query_tools(auth),
                    tool_call_limit=6, instructions=(
                        f"你是 {dialect_name(_dialect)} 数据库查询助手，生成只读 SELECT。"
                        "先调用 search_schema(question) 获取相关表/字段，必要时再调用 "
                        "get_fewshots(question) 参考样例、check_cost(候选SQL) 评估代价；"
                        "获取足够上下文后，生成一条 SELECT SQL；若对字段/关联/枚举不确定，可用 "
                        "resolve_value / find_join_path 确认；"
                        "最终消息必须输出 JSON：{\"sql\": \"<生成的 SELECT SQL>\"}。"
                        "禁止 DELETE/UPDATE/INSERT/DDL。\n注意："
                        + "".join(rules)
                    ),
                )
            else:
                agent = Agent(model=model, telemetry=False, instructions=system_prompt)
            t_llm0 = time.perf_counter()
            # 硬上限：agno 的 model 虽有 timeout=60，但那只是**单次 HTTP** 的超时；
            # agno 内部还可能重试/多段请求，叠起来能把一道题拖到 467 秒（实测）。
            # 在 agno **之外**用 wait_for 兜底，保证单次问答的 agno 阶段有天花板。
            resp = await asyncio.wait_for(
                agent.arun(user_msg),
                timeout=cls._cfg_int(cfg, "nl2sql_call_timeout", 90),
            )
            log.warning("[NL2SQL] agno 阶段耗时={}ms（占 生成 计时的比例见上一条计时行）",
                        int((time.perf_counter() - t_llm0) * 1000))
            # 留痕：模型原始输出。问数失败时这是唯一能定位"模型到底给了什么"的地方
            log.warning("[NL2SQL] 原始输出={}", (resp.content or "")[:500])
            sql = cls._extract_sql((resp.content or "").strip())
            table = await cls._allowed_for_user(auth) if datasource in (_svc.SYSTEM_DS, None) else None
            try:
                return _svc.validate_sql(sql, table or set(), question)
            except Exception:
                # 工具化模式若模型未取到 schema 导致校验失败，回退到提示版完整上下文重新生成
                if not tool_agent:
                    raise
                fallback = Agent(model=model, telemetry=False, instructions=system_prompt)
                resp2 = await fallback.arun(user_msg)
                sql2 = cls._extract_sql((resp2.content or "").strip())
                return _svc.validate_sql(sql2, table or set(), question)
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"问答模型(Agno)调用失败：{e}")
