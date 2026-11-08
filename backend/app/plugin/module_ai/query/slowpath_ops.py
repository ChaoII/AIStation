"""慢路径：``_slow_path``（2026-11-08 从 service.py 拆出）。

未命中指标模板时走这里：对象路径 → NL2SQL（含自纠错重试）→ 取数收口 → 写会话。
SQL 缓存按**主体指纹**分桶（``_auth_scope``），避免 A 生成的 SQL 给 B 用。

``_sql_cache_*`` / ``_auth_scope`` / ``_scan_ont_tables`` / ``SYSTEM_DS`` / ``_SQL_CACHE``
仍归 ``service.py``，这里用 ``_svc.`` 在调用时读取（避免循环导入，保留测试打桩）。
"""
from __future__ import annotations

import time

from app.core.exceptions import CustomException
from app.core.logger import log

from . import service as _svc


class SlowPathOps:
    @classmethod
    async def _slow_path(cls, question: str, session_id: int, datasource: str, auth) -> dict:
        """生成 SQL（带 SQL 缓存）→ EXPLAIN 代价护栏 → 按身份执行 → 失败自纠错。

        **慢的地方只有"生成"这一步**（一次 LLM 调用），执行只要几十毫秒。
        所以这里缓存**生成的 SQL**，重复提问直接跳过 LLM。
        结果行**绝不缓存**——行级/列级策略在执行时下推，缓存结果会串权限。
        """
        cfg = await cls._cfg()
        n = cls._cfg_int(cfg, "self_consistency_n", 1)
        cost_enabled = cls._cfg_bool(cfg, "query_cost_enabled", True)
        max_rows = cls._cfg_int(cfg, "query_cost_max_rows", 50000)
        # 最多尝试次数（含首次）。以前硬编码 range(2)，而设置项 `nl2sql_retry` 只是
        # 默认值表里的一行死数据 —— 想「少重试一次省时间」根本改不动。
        attempts = _svc.nl2sql_attempts(cfg)
        last_err: str | None = None
        sql = ""
        # 首轮生成失败（空内容/超时）→ 次轮强制关掉思考：实测推理型模型会把 max_tokens
        # 全吃在思考上，返回空正文，而"再想一遍"只会更慢更空（140s 后仍然失败）。
        force_no_thinking = False
        cached_sql = _svc._sql_cache_get(question, datasource, _svc._auth_scope(auth))
        cache_used = bool(cached_sql)
        # 阶段计时：问数是"慢"被投诉的功能，必须能一眼看出时间花在哪
        t_start = time.perf_counter()
        t_gen = t_start
        t_exec = t_start
        for attempt in range(attempts):
            candidate_sqls: list[str] = []
            if cached_sql and attempt == 0:
                # 缓存命中：跳过生成（这是"快"的主要来源）
                candidate_sqls = [cached_sql]
            else:
                try:
                    for i in range(max(n, 1)):
                        # 自一致性：不同候选用不同温度增加多样性
                        temp = round(0.2 * i, 2) if n > 1 else 0.0
                        candidate_sqls.append(
                            await cls._nl2sql(question, datasource, prev_error=last_err,
                                              temperature=temp, auth=auth,
                                              thinking="off" if force_no_thinking else None)
                        )
                except CustomException as e:
                    last_err = e.msg
                    # 模型偶发**返回空**（实测本地 284B 会这样）：原样重试基本没用，
                    # 给一条可操作的提示 + 关掉思考才有意义——否则白等两轮（实测 28 秒）。
                    if ("未生成有效的查询语句" in (e.msg or "")
                            or "调用失败" in (e.msg or "")):
                        force_no_thinking = True
                        last_err = ("你上次**没有返回任何 SQL**。请只输出一条 SELECT 语句，"
                                    "不要输出解释、不要输出空内容。")
                    log.warning(f"[query] NL2SQL 生成/校验失败第 {attempt + 1} 轮: {e.msg}")
                    continue
            t_gen = time.perf_counter()
            # 逐一执行；代价护栏过滤超重查询；结果一致性分组取多数
            groups: dict = {}
            results: list[tuple[str, dict]] = []
            for csql in candidate_sqls:
                try:
                    if cost_enabled and datasource in (_svc.SYSTEM_DS, None):
                        try:
                            er = await cls._explain_rows(csql)
                        except CustomException as e:
                            last_err = e.msg
                            continue
                        except Exception as e:  # noqa: BLE001
                            # EXPLAIN 失败说明候选 SQL 不合法（如引用了不存在的列/表），跳过该候选
                            last_err = f"SQL 校验失败：{e}"
                            continue
                        if er > max_rows:
                            last_err = f"查询代价过高(预计{er}行>上限{max_rows})，请改为聚合/加条件/限制范围"
                            continue
                    res = await cls._execute_one(csql, datasource, auth, question)
                    results.append((csql, res))
                    sig = tuple(sorted(tuple(str(v) for v in r) for r in res["rows"]))
                    groups.setdefault(sig, []).append(csql)
                except CustomException as e:
                    last_err = e.msg
                except Exception as e:  # noqa: BLE001
                    last_err = f"执行失败：{e}"
            if results:
                t_exec = time.perf_counter()
                # 优先非空结果；多数一致组内取第一候选；全空则按多数
                if any(c[1]["rows"] for c in results):
                    nonempty_ids = {c for c, res in results if res["rows"]}
                    base = max((g for g in groups.values() if set(g) & nonempty_ids), key=len)
                    sql = base[0]
                else:
                    sql = max(groups.values(), key=len)[0]
                res = next(r for (c, r) in results if c == sql)
                # 缓存里的 SQL 执行失败/返回全 NULL（schema/口径变了）→ 清掉缓存，下一轮重新生成。
                # 不这么做的话，一条坏 SQL 会被反复命中，变成"越缓存越慢还查不出东西"。
                _flat_cache = [v for r in (res.get("rows") or [])
                               for v in (r if isinstance(r, (list, tuple)) else [r])]
                if (cache_used and attempt == 0
                        and (not _flat_cache or all(v is None for v in _flat_cache))):
                    _svc._SQL_CACHE.pop(_svc._sql_cache_key(question, datasource, _svc._auth_scope(auth)), None)
                    cached_sql, cache_used = None, False
                    last_err = "上一轮查询返回结果为空，可能是条件/表/字段选择不准确，请检查后再重新生成一条 SQL。"
                    continue
                # 执行反馈自纠错：结果为空且还有重试机会 → 携带空结果提示二次生成
                if not res["rows"] and attempt == 0 and cls._cfg_bool(cfg, "empty_self_correct", True):
                    last_err = "上一轮查询返回结果为空，可能是条件/表/字段选择不准确，请检查后再重新生成一条 SQL。"
                    continue
                # 结果自校验：占比合计/累计单调/排名范围/分组行数 —— 可疑就**带具体错因**重试一次
                if attempt == 0 and cls._cfg_bool(cfg, "empty_self_correct", True):
                    try:
                        from .selfcheck import format_issue, run_selfcheck

                        _iss = run_selfcheck(
                            question, res.get("columns") or [], res.get("rows") or []
                        )
                        if _iss:
                            last_err = ("上一次结果看起来有问题：" + format_issue(_iss)
                                        + "。请修正后重新只返回一条 SQL。")
                            log.warning(f"[query] 自校验命中，重试一次：{format_issue(_iss)}")
                            continue
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] 自校验失败（忽略）: {str(e)[:100]}")
                # 生成成功才入缓存（失败/空的 SQL 不入，避免污染）。
                # 「全 NULL 结果」也算空：旧实现只判 `rows` 是否为空，于是一条落在空表上、
                # 返回 [[None]] 的 SQL 会被缓存 30 分钟，之后同问句永远秒回 NULL（实测）。
                _flat = [v for r in (res.get("rows") or [])
                         for v in (r if isinstance(r, (list, tuple)) else [r])]
                if not _flat or all(v is None for v in _flat):
                    log.warning("[query] 结果为全 NULL，不写 SQL 缓存：{}", question[:30])
                else:
                    _svc._sql_cache_set(question, datasource, sql, _svc._auth_scope(auth))
                # **口径提示**（只提示、不重试）：问句说要什么 vs SQL 做了什么。
                # 这类差异在结果里看不出来（数字都合理），但值得让人知道。
                # 实测当前题库 78 题**一次都没命中** —— 所以不拿它触发重试（重试就是多 5 秒），
                # 只作为运行时的廉价提示挂出去。
                try:
                    from .selfcheck import check_sql_intent, format_sql_intent

                    _advice = check_sql_intent(question, sql)
                    if _advice:
                        res["advice"] = _advice
                        log.warning("[query] 口径提示：{}（question={}）",
                                    format_sql_intent(_advice), question[:30])
                except Exception as e:  # noqa: BLE001
                    log.warning(f"[query] 口径提示检查失败（忽略）: {str(e)[:80]}")
                # 结果列头中文化 + 一句人话的答案（原先摘要是硬编码废话）
                cn_cols = await cls._cn_columns(res["columns"], sql)
                res["columns"] = cn_cols
                summary = cls._summarize_rows(cn_cols, res["rows"])
                # 收尾阶段单独计时：这一步里有两个"重"调用（再次检索 + DQ 概览），
                # 缓存命中时生成阶段为 0，若收尾仍慢就会吃掉缓存的收益
                t_tail = time.perf_counter()
                retrieved = await cls._recall_grounding(question, datasource)
                grounding = {"retrieved": retrieved, "ontology_used": _svc._scan_ont_tables(sql)}
                msg = await cls._save_message(
                    session_id, question, path="slow", datasource=datasource,
                    sql=sql, columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0),
                    cached=cache_used,
                    summary=summary, grounding=grounding,
                )
                ans = cls._answer(msg, sql=sql, retrieved=retrieved)
                ans["dq_warning"] = await cls._dq_warning_for_sql(sql)
                log.warning(
                    "[query] 计时 缓存命中={} 生成={:.0f}ms 执行={:.0f}ms 收尾={:.0f}ms 总计={:.0f}ms",
                    cache_used, (t_gen - t_start) * 1000, (t_exec - t_gen) * 1000,
                    (time.perf_counter() - t_tail) * 1000,
                    (time.perf_counter() - t_start) * 1000)
                return ans
        await cls._save_message(
            session_id, question, path="slow", datasource=datasource,
            sql=sql, rows=[], is_error=True, summary=f"查询失败：{last_err}",
        )
        return {"path": "slow", "is_error": True, "answer": f"查询失败：{last_err}", "sql": sql}
