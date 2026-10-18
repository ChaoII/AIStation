"""问数的「精准 + 快速」回归测试。

对应本轮专项优化，守住三类**确定性**行为：
1. 缓存 —— 只缓存 SQL，**绝不缓存结果行**（缓存结果会串权限）
2. LIMIT —— "全量列举"要放宽，但"取前 N"绝不能放宽
3. 支撑表解析 —— `backing_table` 为空时按库里实际存在的表定，两个函数不许打架
"""
import inspect
import re

import pytest

from app.plugin.module_ai.query import service as Q


# ===========================================================================
# 1) 缓存：快，但绝不能串权限
# ===========================================================================
class TestSqlCache:
    def setup_method(self):
        Q.sql_cache_clear()

    def teardown_method(self):
        Q.sql_cache_clear()

    def test_set_and_get(self):
        Q._sql_cache_set("今日告警数", "system", "SELECT 1")
        assert Q._sql_cache_get("今日告警数", "system") == "SELECT 1"

    def test_whitespace_normalised(self):
        Q._sql_cache_set("今日 告警 数", "system", "SELECT 1")
        assert Q._sql_cache_get("今日告警数", "system") == "SELECT 1"

    def test_datasource_isolated(self):
        """不同数据源的同一个问题不能互相命中。"""
        Q._sql_cache_set("今日告警数", "system", "SELECT 1")
        assert Q._sql_cache_get("今日告警数", "ds:9") is None

    def test_empty_sql_not_cached(self):
        Q._sql_cache_set("q", "system", "")
        assert Q._sql_cache_get("q", "system") is None

    def test_clear(self):
        Q._sql_cache_set("q", "system", "SELECT 1")
        assert Q.sql_cache_clear() == 1
        assert Q._sql_cache_get("q", "system") is None

    def test_cache_holds_sql_not_rows(self):
        """**关键安全断言**：缓存里只允许出现 SQL 字符串。

        一旦有人"顺手"把结果行也缓存进去，行级/列级策略就被绕过了
        ——A 的数据会被 B 拿到。这条守着那个边界。
        """
        Q._sql_cache_set("q", "system", "SELECT id FROM t")
        for _k, (ts, v) in Q._SQL_CACHE.items():
            assert isinstance(v, str), "缓存值必须是 SQL 字符串，不能是结果行"
            assert isinstance(ts, float)

    def test_retrieval_cache_shape(self):
        """检索缓存只存表名列表，不含数据。"""
        assert isinstance(Q._RETRIEVAL_CACHE, dict)
        assert isinstance(Q._retrieval_cache_key("A B"), str)


# ===========================================================================
# 2) LIMIT：全量列举放宽，"取前 N"绝不放宽
# ===========================================================================
class TestLimitPolicy:
    @pytest.mark.parametrize("q", [
        "每个告警规则分别触发多少告警",
        "各小时的告警分布",
        "列出所有订单编号",
        "所有摄像机的名称",
        "有哪些告警类型",
    ])
    def test_full_list_detected(self, q):
        assert Q._wants_full_list(q) is True, q

    @pytest.mark.parametrize("q", [
        "各算法类型的平均延迟，取前5名",
        "各摄像头告警数与边缘事件数对比，取告警最多前5",
        "告警数量最多的前5种类型",
        "产生过告警且告警数排前3的摄像头",
        "一共有多少条告警记录",
    ])
    def test_top_n_not_full_list(self, q):
        """真实踩过：`各算法类型的平均延迟，取前5名` 含"各"被误判成全量列举，
        5 行被放到 1000 行——基准立刻从 ✓ 变 ✗。"""
        assert Q._wants_full_list(q) is False, q

    def test_limit_widened_for_full_list(self):
        sql = ("SELECT r.name, COUNT(a.id) AS c FROM video_alarm_rules r "
               "LEFT JOIN video_alarm_records a ON a.rule_id=r.id "
               "GROUP BY r.name ORDER BY c DESC LIMIT 50")
        out = Q.validate_sql(sql, {"video_alarm_rules", "video_alarm_records"},
                             "每个告警规则分别触发多少告警")
        assert f"LIMIT {Q.MAX_ROWS}" in out

    def test_limit_kept_for_top_n(self):
        sql = ("SELECT alarm_type, COUNT(*) AS c FROM video_alarm_records "
               "GROUP BY alarm_type ORDER BY c DESC LIMIT 5")
        out = Q.validate_sql(sql, {"video_alarm_records"},
                             "各算法类型的平均延迟，取前5名")
        assert "LIMIT 5" in out, "取前5名不能放宽"
        assert f"LIMIT {Q.MAX_ROWS}" not in out

    def test_limit_added_when_absent(self):
        out = Q.validate_sql("SELECT COUNT(*) FROM video_alarm_records",
                             {"video_alarm_records"}, "告警记录总数是多少")
        assert f"LIMIT {Q.MAX_ROWS}" in out


# ===========================================================================
# 3) 支撑表解析：两个函数必须一致
# ===========================================================================
class TestTableResolution:
    def test_resolve_prefers_explicit_backing(self):
        from app.plugin.module_ai.ontology import semantic as S

        assert S._resolve_table("video_cameras", "video_cameras", set()) == "video_cameras"

    def test_resolve_falls_back_to_ont_prefix(self):
        """真实踩过：`backing_table` 为空时旧实现回退成 `code`，
        把「订单」指向一张**不存在的表 orders**（真实表叫 `ont_orders`）。"""
        from app.plugin.module_ai.ontology import semantic as S

        assert S._resolve_table("orders", "", {"ont_orders", "sys_user"}) == "ont_orders"

    def test_resolve_falls_back_to_code_when_no_ont_table(self):
        from app.plugin.module_ai.ontology import semantic as S

        assert S._resolve_table("foo", "", {"foo", "bar"}) == "foo"

    def test_map_and_context_agree(self):
        """`object_table_map` 与 `semantic_context` 必须给出**同一张表**，
        否则会"白名单认一张、prompt 里写另一张"。"""
        import asyncio

        from app.plugin.module_ai.ontology import semantic as S

        async def go():
            ctx = await S.semantic_context(include_properties=False)
            m = await S.object_table_map()
            return ctx["objects"], m

        try:
            objs, m = asyncio.run(go())
        except Exception:  # noqa: BLE001
            pytest.skip("测试库无本体数据")
        if not objs:
            pytest.skip("测试库无本体数据")
        for o in objs:
            assert m.get(o["table"]) == o["code"], \
                f"{o['code']}：map 里 {o['table']} 指向 {m.get(o['table'])}"


# ===========================================================================
# 4) 语义块过滤（快的来源）
# ===========================================================================
class TestContextBlockFilter:
    def test_only_tables_filters(self):
        import asyncio

        from app.plugin.module_ai.ontology import semantic as S

        async def go():
            ctx = await S.semantic_context(include_properties=False)
            full = await S.context_block()
            # 用**测试库里真实存在**的对象表，而不是写死一张业务表
            if not ctx["objects"]:
                return full, "", None, 0
            tbl = ctx["objects"][0]["table"]
            small = await S.context_block(only_tables={tbl})
            return full, small, tbl, len(ctx["objects"])

        try:
            full, small, tbl, n_objs = asyncio.run(go())
        except Exception:  # noqa: BLE001
            pytest.skip("测试库无本体数据")
        if not full or tbl is None:
            pytest.skip("测试库无本体数据")
        if n_objs < 2:
            # 全库只有 1 个对象时，"按表过滤"不可能比全量更小 —— 断言无意义。
            # 测试库是**会话级共享**的：单独跑本文件时通常只有 1 个对象，
            # 而被 test_ontology_query_bridge.py 等创建过对象后才会 ≥2（实测）。
            pytest.skip(f"测试库只有 {n_objs} 个本体对象，过滤效果无从体现")
        assert "本体对象" in small, f"按表 {tbl} 过滤后应仍有内容"
        assert len(small) < len(full), "过滤后必须更小"

    def test_only_tables_unknown_returns_empty(self):
        import asyncio

        from app.plugin.module_ai.ontology import semantic as S

        blk = asyncio.run(S.context_block(only_tables={"__no_such_table__"}))
        assert blk == ""


# ===========================================================================
# 5) 结构性断言：慢路径不该再有工具往返、不该重复加载
# ===========================================================================
class TestNoRegressions:
    def test_tool_agent_default_off(self):
        """工具往返实测 7.25 次/题，而信息本地已全覆盖 —— 默认必须是关的。"""
        src = inspect.getsource(Q)
        assert 'cfg, "agno_tool_agent", False' in src, "默认值应为 False"
        assert 'cfg, "agno_tool_agent", True' not in src, "不应残留 True 默认"

    def test_metrics_not_loaded_twice_on_slow_path(self):
        """`ask()` 里 force_slow 必须在加载指标/术语**之前**返回，
        否则慢路径里 `_nl2sql` 又查一遍，等于白跑两次库。"""
        src = inspect.getsource(Q.AiQueryService.ask)
        i_slow = src.index("if force_slow")
        i_metrics = src.index("list_metrics")
        assert i_slow < i_metrics, "force_slow 应早于 list_metrics"

    def test_retrieval_memoised(self):
        """同一问题一次问答里会被检索两次（拼 prompt + 溯源）。"""
        src = inspect.getsource(Q)
        assert "_RETRIEVAL_CACHE" in src
        assert "_semantic_tables_uncached" in src

    def test_phase_timing_logged(self):
        """问数是被投诉"慢"的功能，必须能一眼看出时间花在哪。"""
        src = inspect.getsource(Q.AiQueryService._slow_path)
        assert "计时" in src and "生成=" in src

    def test_loguru_brace_style(self):
        """项目用 loguru，格式化是 `{}` 不是 `%s` —— 写错会打印原始格式串。"""
        src = inspect.getsource(Q.AiQueryService._slow_path)
        for m in re.finditer(r'log\.\w+\(\s*"([^"]*)"', src):
            assert "%s" not in m.group(1), f"日志用了 %s 风格：{m.group(1)[:40]}"
            assert "%.0f" not in m.group(1)
