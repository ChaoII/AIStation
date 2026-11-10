"""路由判定：指标快路径 vs 对象路径 vs NL2SQL（2026-11-08 从 service.py 拆出）。

两条判定都**不调模型**，只按确定性规则决定「这道题走哪条路」，避免指标抢答与
对象路径硬答（实测「供应商的运损扣吨」被对象路径答成「供应商矿点关系数」）。

规则函数在 `metric_rules` / `question_rules`，这里通过 `_svc.` 调用：
测试对 `service._match_metric` / `_wants_grouping` 的打桩因此仍然生效。
"""
from __future__ import annotations

import time

from app.core.logger import log

from . import service as _svc


class RoutingOps:
    @classmethod
    async def _object_query_path(cls, question: str, session_id: int, datasource: str,
                                 auth, object_code: str | None = None,
                                 object_key: str | None = None) -> dict | None:
        """对象查询路径：LLM 出 IR → 本体实例层执行。

        **任何环节失败都返回 ``None``**（由调用方降级 NL2SQL）——
        绝不因新路径失败而答不出来。返回 ``None`` 的时机：
        非系统库 / 无可用对象 / 无可用模型 / IR 生成失败 / 校验不通过 / 执行失败。
        """
        from app.plugin.module_ai.ontology import security as _ont_sec

        from . import object_query as oq
        from .object_exec import execute_ir

        cfg = await cls._cfg()
        max_objs = cls._cfg_int(cfg, "object_query_max_objects", 8)

        # 问句里出现**未绑定指标**的业务术语（如「扣吨」——词典有词、但库里没有对应
        # 指标）时，对象查询帮不上忙：它只能执行「对象 + 绑定指标」的组合，硬答只会
        # 用相近对象凑数（实测「供应商的运损扣吨合计」被答成「供应商矿点关系数 140」）。
        # 这里直接降级 NL2SQL，让模型按真实列去算。
        try:
            _terms0 = await cls.list_terms(datasource)
        except Exception:  # noqa: BLE001
            _terms0 = []
        _unbound0 = [t["term"] for t in _terms0
                     if t.get("term") and str(t["term"]) in question
                     and not t.get("metric_key")]
        if _unbound0:
            log.warning("[query] 对象查询：问句含未绑定指标的术语 {}，降级 NL2SQL", _unbound0)
            return None
        if _svc._needs_custom_sql(question):
            # 对象查询（IR）只覆盖「对象/属性/计数」这类结构化诉求；带 WHERE/DISTINCT 的问法
            # 它答不了，却要先花 20~30 秒构建对象白名单、再 20 秒生成 IR，最后照样降级。
            log.warning("[query] 对象查询：问句含条件/去重语义，跳过对象路径（交给 NL2SQL）")
            return None
        # 时间范围 / 分组 / 排序：IR 只产出「对象实例过滤」，这类诉求它表达不了，
        # 实测会产出一条空 SQL 然后当成功返回（path=object、sql 为空、结果 0 行）。
        if _svc._TIME_QUALIFIER_RE.search(question) or _svc._wants_grouping(question) \
                or _svc._ORDER_WORD_RE.search(question) or _svc._OBJECT_AGG_RE.search(question):
            # 对象路径只做「实体/属性检索」，聚合与分组排序都表达不了。
            # 实测「煤质信息的平均灰分是多少」走了对象路径，产出空 SQL 且当成功返回。
            log.warning("[query] 对象查询：问句含时间/分组/排序/聚合诉求，跳过对象路径")
            return None
        if _svc._ir_circuit_open():
            log.warning(
                "[query] 对象查询：IR 熔断中（最近失败 {}s 前），本轮直接走 NL2SQL",
                int(time.time() - _svc._IR_FAIL_AT))
            return None

        # 指标字典（供 IR 提示词注入 / 校验收敛 / 绑定型指标执行）
        try:
            metrics_list = await cls.list_metrics(datasource)
        except Exception:  # noqa: BLE001
            metrics_list = []
        metrics_map = {m["key"]: m for m in metrics_list}
        # 检索优化（S4）：问题命中某个指标时，把其对象排到最前并显式建议用 metric
        try:
            matched = _svc._match_metric(
                question, metrics_list, await cls.list_terms(datasource),
                await cls.list_concepts())
        except Exception:  # noqa: BLE001
            matched = None

        # 对象白名单：系统库按授权过滤，自定义数据源按对象归属过滤（S2 放开）
        allowed = await cls._allowed_objects_for_query(
            question, auth, max_objects=max_objs, datasource=datasource,
            prefer_object=(matched or {}).get("object_code"))
        allowed = _svc._prioritize_metric_object(allowed, matched)
        # 「当前对象」即使没被检索命中，也**强制进词表并排在最前**：
        # 用户已经明确站在这个对象上提问，不该因为召回没命中就查不了它。
        if object_code:
            if object_code not in allowed:
                spec = await cls._object_spec_for(object_code)
                if spec:
                    allowed[object_code] = spec
            if object_code in allowed:
                allowed = {object_code: allowed[object_code],
                           **{k: v for k, v in allowed.items() if k != object_code}}
        if not allowed:
            log.warning("[query] 对象查询：没有可用（已物化且授权）的对象，降级 NL2SQL")
            return None

        try:
            runtime = await cls._ir_runtime()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 对象查询：无可用模型 {str(e)[:100]}")
            return None

        try:
            text = await cls._ir_llm(
                _svc._metric_prompt_hint(matched)
                + oq.render_ir_prompt(question, allowed, max_objects=max_objs,
                                      max_traverse_depth=cls._cfg_int(
                                          cfg, "object_query_max_traverse_depth", 1),
                                      metrics=metrics_map),
                runtime)
        except Exception as e:  # noqa: BLE001
            # ⚠️ 必须打**异常类型**：TimeoutError 的 str(e) 是空串，只打 message 时
            #    日志里会是"IR 生成失败 "，完全看不出是超时（实测踩到，排查了半天）。
            log.warning("[query] 对象查询：IR 生成失败 [{}] {}", type(e).__name__, str(e)[:120])
            _svc._mark_ir_fail()
            return None

        if not (text or "").strip():
            # 空正文 → 降级 NL2SQL，并**熔断一段时间**：连问多题时否则每题都要
            # 白等一轮 IR（实测 30s×2），整体慢一倍以上。
            _svc._mark_ir_fail()
            log.warning("[query] 对象查询：IR 空正文，熔断后续对象查询，直接走 NL2SQL")
            return None

        # 留痕：模型原始输出（问数排查时这是唯一能定位"模型到底给了什么"的地方）
        log.warning("[OQ] IR 原始输出={}", (text or "")[:800])

        parsed = oq.parse_ir(text)
        if (parsed is not None and object_key and not parsed.object_key
                and oq._resolve_object(parsed.object, allowed) == object_code):
            # 当前对象就是用户问的那个 → 把实例主键补进 IR（单对象读取 / 关系跳转需要它）
            parsed.object_key = str(object_key)
        ir, reasons = oq.validate_ir(
            parsed, allowed,
            max_traverse_depth=cls._cfg_int(cfg, "object_query_max_traverse_depth", 1),
            metrics=metrics_map)
        if not ir:
            log.warning("[query] 对象查询未通过校验，降级 NL2SQL：{}", "；".join(reasons[:3]))
            return None

        uid = getattr(getattr(auth, "user", None), "id", None)
        try:
            principal = await _ont_sec.load_principal(uid)
        except Exception:  # noqa: BLE001
            principal = None
        res = await execute_ir(ir, principal, metrics=metrics_map)
        if not res.get("ok"):
            log.warning("[query] 对象查询执行失败，降级 NL2SQL：{}", res.get("error"))
            return None

        cols = res.get("columns") or []
        rows = res.get("rows") or []
        # **没有列的对象结果一律不算成功**：没有列名，前端无法渲染，用户看到的是
        # 一条什么都没有的回答，而本可以走 NL2SQL 答出来。
        # 实测两次都踩在这里：
        #   ① 「每日出入库报表一共有多少条记录」→ ok=True 但无列无行（旧判定）；
        #   ② 同题另一种 IR 输出 → 有行但**无列**，旧判定（`not cols and not rows`）
        #      放行了，评测判错、界面上仍未给出数字。
        # 所以判据只取 `not cols`：`traverse` / `traverse-agg` 这类真结果都带列。
        if not cols:
            log.warning("[query] 对象查询无可用列（cols={} rows={}），降级 NL2SQL",
                        len(cols), len(rows))
            return None
        retrieved = await cls._recall_grounding(question, _svc.SYSTEM_DS)
        msg = await cls._save_message(
            session_id, question, path="object", datasource=_svc.SYSTEM_DS,
            sql="", columns=cols, rows=rows, result_rows=len(rows),
            summary=cls._summarize_rows(cols, rows),
            grounding={"ir": ir.to_dict(), "ir_reasons": reasons, "retrieved": retrieved},
        )
        ans = cls._answer(msg, sql="", retrieved=retrieved)
        ans["ir"] = ir.to_dict()
        ans["object_query"] = {
            "shape": res.get("shape"), "note": res.get("note") or "", "reasons": reasons,
        }
        # 前端「本体对象」标签用（对象查询没有 SQL，故手动补）
        ans["ontology_used"] = [ir.object]
        # message_id：前端反馈按钮按 v-if="m.id" 门控（与快/慢路径对齐）
        ans["message_id"] = msg.id
        # 热度驱动自动建索引：**放在答案构造之后**，且自带 try —— 绝不能影响这次问答
        try:
            await cls._maybe_auto_index(ir.object, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 自动索引判定失败（忽略）: {str(e)[:100]}")
        log.warning("[query] 对象查询命中：object={} shape={} rows={}",
                    ir.object, res.get("shape"), len(rows))
        return ans

    @classmethod
    async def _select_metric(cls, question: str, datasource: str | None,
                             metrics: list[dict], terms: list[dict]) -> dict | None:
        """指标快路径选型（**ask 与 ask_stream 共用**，避免两套路由漂移）。

        规则：
        - 列举类问题（哪些/列出/名称…）不走指标模板；
        - 「每个/各/按X分组」跳过**单值**指标（agg != group）；
        - 术语口径优先（命中已绑定术语以术语为准；命中未绑定术语则让位 NL2SQL）；
        - 自定义数据源：指标来源表必须与问句有共同业务词（防「指标抢答」）。
        """
        if _svc._is_listing_question(question):
            return None
        if _svc._needs_custom_sql(question):
            log.warning("[query] 问句带条件/去重语义，不走指标模板：question={}", question[:40])
            return None
        try:
            concepts = await cls.list_concepts()
        except Exception:  # noqa: BLE001
            concepts = []
        # 本体桥：指标绑定的对象名/别名也是"用户会怎么说"（语义层存在的意义）。
        # semantic_context 有 60 秒进程缓存，这里不会打库。
        objects: dict[str, dict] = {}
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            ctx = await _sem.semantic_context(include_properties=False)
            objects = {
                str(o.get("code")): {"name": o.get("name") or "", "aliases": o.get("aliases") or []}
                for o in (ctx.get("objects") or [])
            }
        except Exception:  # noqa: BLE001
            objects = {}
        metric = _svc._match_metric(question, metrics, terms, concepts, objects)
        if metric and metric.get("agg") != "group" and _svc._wants_grouping(question):
            log.warning("[query] 分组诉求，跳过单值指标快路径：metric={} question={}",
                        metric.get("key"), question[:40])
            metric = None
        if metric:
            q_low = question.lower()
            hit_terms = [t for t in terms if t.get("term") and str(t["term"]).lower() in q_low]
            bound = {t.get("metric_key") for t in hit_terms if t.get("metric_key")}
            # 术语已**明确绑定**到这个指标：说明用户说的就是它，后面的「来源表共同词」
            # 守卫不该再拦（否则「热值是多少」会被判成"来源表与问句无共同词"→ 慢路径，
            # 实测模型还会返回空 SQL，答案直接失败）。
            via_term = metric["key"] in bound
            unbound = [t["term"] for t in hit_terms if not t.get("metric_key")]
            if bound and metric["key"] not in bound and len(bound) == 1:
                alt = next((m for m in metrics if m["key"] in bound and m.get("enabled")), None)
                if alt:
                    log.warning("[query] 术语明确指向另一指标，改判：{} → {}（question={}）",
                                metric["key"], alt["key"], question[:40])
                    metric = alt
            if unbound:
                log.warning("[query] 问句用了未绑定指标的术语 {}，跳过快路径（question={}）",
                            unbound, question[:40])
                metric = None
            if metric:
                # 改判后要重算：via_term 必须以**最终**指标为准
                via_term = metric["key"] in bound
        # 准入检查（白名单）：模板必须能解释问句里的时间范围与聚合口径，
        # 解释不了就让位 NL2SQL —— 宁可变慢，不要"自信地答错"。
        if metric:
            blockers = _svc._fast_path_blockers(question, metric, terms, concepts)
            if blockers:
                log.warning("[query] 快路径让位（{}）：metric={} question={}",
                            "；".join(blockers), metric.get("key"), question[:40])
                metric = None
        if metric and (datasource or _svc.SYSTEM_DS) != _svc.SYSTEM_DS:
            try:
                mt = _svc._metric_main_table(metric)
                if not mt and metric.get("object_code"):
                    obmap = await cls._object_backing_map()
                    mt = obmap.get(str(metric["object_code"]), "")
                mname = (metric.get("name") or "").strip()
                # 本体对象名命中 = 已确认"说的是这个实体"，不必再用列标签二元组兜底
                oname = str((objects.get(str(metric.get("object_code") or "")) or {}).get("name") or "")
                if mt and not via_term and not (mname and mname in question) and not (len(oname) >= 2 and oname in question):
                    sch = await cls._ds_schema_map(datasource)
                    hint = " ".join(sch.get(mt) or [])
                    shared = _svc._bigrams(question) & _svc._bigrams(hint)
                    shared |= _svc._latin_words(question) & _svc._latin_words(hint)
                    if hint and not shared:
                        log.warning(
                            "[query] 指标来源表与问句无共同业务词，跳过快路径：metric={} table={} "
                            "question={}", metric.get("key"), mt, question[:40])
                        metric = None
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 指标来源表相关性检查失败（忽略）: {str(e)[:100]}")
        return metric
