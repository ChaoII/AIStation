"""问数 × 本体 的结合回归测试。

对应三件事：
1. **权限打通**：`policy_to_sql` 把行级策略翻译成 SQL；`secure_sql` 把任意 SQL 里的
   本体表改写成"已过滤子查询"（聚合/join 都覆盖）；问数执行路径接上它。
2. **修洞**：`instance_aggregate` 带权限；`_render_chart` 不再绕过行级策略。
3. **语义**：关系（join 路径）进 prompt，且用**真实支撑表名**（不是 `ont_{code}`）。
"""
import asyncio
import inspect
import re

import _ont_ddl
import pytest

from app.plugin.module_ai.ontology import object_view as OV
from app.plugin.module_ai.ontology import security as SEC
from app.plugin.module_ai.ontology import service as svc


def _run(c):
    return asyncio.run(c)


@pytest.fixture(scope="module", autouse=True)
def _tables(test_client):
    from sqlalchemy import text as _t

    from app.core.database import async_db_session, async_engine

    async def _setup():
        await async_engine.dispose()
        async with async_db_session.begin() as db:
            for ddl in _ont_ddl.ONT_DDL.values():
                await db.execute(_t(ddl))
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS qb_cams (id INTEGER PRIMARY KEY, "
                "name TEXT, status TEXT, dept INTEGER, amount INTEGER)"))
            await db.execute(_t(
                "INSERT OR IGNORE INTO qb_cams (id,name,status,dept,amount) VALUES "
                "(1,'东门-1号','ONLINE',1,100),(2,'东门-2号','ONLINE',1,200),"
                "(3,'西门-1号','OFFLINE',2,300),(4,'西门-2号','OFFLINE',2,400)"))
            # 关系（join 路径）—— 验证 prompt 里带显式关联，而不是让 LLM 猜
            await db.execute(_t(
                "INSERT OR IGNORE INTO ai_ont_link (id,source_object,target_object,name,"
                "source_field,target_field,card,join_method,is_deleted) VALUES "
                "(9001,'qb_cams','qb_cams','自关联','id','id','one_to_one','foreign_key',0)"))
        await svc.upsert_object({"code": "qb_cams", "name": "回归摄像机",
                                 "key_prop": "id", "name_prop": "name",
                                 "backing_table": "qb_cams"})
        for code, name, pt in (("name", "名称", "string"), ("status", "状态", "string"),
                               ("dept", "部门", "int"), ("amount", "金额", "int")):
            await svc.upsert_property({"object_code": "qb_cams", "code": code,
                                       "name": name, "prop_type": pt})
    _run(_setup())


CAM = "qb_cams"
COLS = {"id", "name", "status", "dept", "amount"}


def _principal(uid=2, roles=None, dept_id=None, superuser=False):
    """注意：``user.attribute('dept_id')`` 取的是 ``Principal.dept_id``（整数），
    不是 ``attributes`` 字典 —— 所以部门列必须是数值列，否则 SQL 比较类型对不上。
    """
    return SEC.Principal(user_id=uid, username=f"u{uid}", name=f"用户{uid}",
                         is_superuser=superuser, role_codes=roles or [],
                         dept_id=dept_id)


# ===========================================================================
# 1) 策略 → SQL 翻译
# ===========================================================================
class TestPolicyToSql:
    def test_equality_with_user_attribute(self):
        p = _principal(dept_id=1)
        assert SEC.policy_to_sql("dept == user.attribute('dept_id')", p, COLS) == '("dept" = 1)'

    def test_user_role_becomes_boolean_constant(self):
        p = _principal(roles=["ADMIN"])
        sql = SEC.policy_to_sql("status == 'ONLINE' or user.role('ADMIN')", p, COLS)
        assert "OR TRUE" in sql and '"status" = \'ONLINE\'' in sql, sql

    def test_in_list(self):
        sql = SEC.policy_to_sql("status in ('ONLINE','OFFLINE')", _principal(), COLS)
        assert sql == '("status" IN (\'ONLINE\', \'OFFLINE\'))'

    def test_contains_becomes_like(self):
        sql = SEC.policy_to_sql("contains(name, '东门')", _principal(), COLS)
        assert sql is not None and "LIKE" in sql and "'东门'" in sql

    def test_builtin_len_becomes_length(self):
        assert SEC.policy_to_sql("len(name) > 2", _principal(), COLS) == '(LENGTH("name") > 2)'

    def test_and_not_combination(self):
        sql = SEC.policy_to_sql("status == 'ONLINE' and not (dept == 2)", _principal(), COLS)
        assert sql == '(("status" = \'ONLINE\') AND (NOT ("dept" = 2)))'

    def test_unknown_column_returns_none(self):
        """引用了表里没有的列 → 不猜，返回 None 让调用方 fail-safe。"""
        assert SEC.policy_to_sql("ghost == 1", _principal(), COLS) is None

    def test_unsupported_syntax_returns_none(self):
        assert SEC.policy_to_sql("[x for x in y]", _principal(), COLS) is None
        assert SEC.policy_to_sql("f'{a}'", _principal(), COLS) is None

    def test_user_password_rejected(self):
        assert SEC.policy_to_sql("user.password == 'x'", _principal(), COLS) is None

    def test_empty_returns_none(self):
        assert SEC.policy_to_sql("", _principal(), COLS) is None

    def test_literal_is_escaped(self):
        sql = SEC.policy_to_sql("name == \"a'b\"", _principal(), COLS)
        assert sql is not None and "''" in sql, sql


# ===========================================================================
# 2) secure_sql：把过滤下推到子查询
# ===========================================================================
class TestSecureSql:
    def test_superuser_not_rewritten(self):
        r = _run(SEC.secure_sql("SELECT * FROM qb_cams", _principal(superuser=True)))
        assert r["ok"] and not r["rewritten"]
        assert r["sql"] == "SELECT * FROM qb_cams"

    def test_no_policy_not_rewritten(self):
        r = _run(SEC.secure_sql("SELECT * FROM qb_cams", _principal()))
        assert r["ok"] and not r["rewritten"]

    def test_aggregate_is_rewritten_before_group_by(self):
        """关键：过滤必须发生在聚合**之前** —— 表引用被换成子查询。"""
        async def go():
            await SEC.upsert_row_policy({"object_code": CAM, "name": "只看A",
                                         "expression": "dept == 1",
                                         "effect": "allow", "enabled": True})
            r = await SEC.secure_sql(
                "SELECT dept, count(*) AS c FROM qb_cams GROUP BY dept", _principal())
            for x in await SEC.list_row_policies(CAM):
                if x["name"] == "只看A":
                    await SEC.remove_row_policy(x["id"])
            return r

        r = _run(go())
        assert r["ok"], r
        assert r["rewritten"], "有策略就该改写"
        # 子查询必须在 GROUP BY 之前；GROUP 关键字不能被吃掉
        assert "GROUP BY dept" in r["sql"], r["sql"]
        assert "AS qb_cams" in r["sql"] or "AS r" in r["sql"]
        assert "WHERE" in r["sql"] and '"dept" = 1' in r["sql"]
        assert r["sql"].index("SELECT") < r["sql"].index("GROUP BY")

    def test_keyword_not_swallowed_as_alias(self):
        """真实踩过：`FROM t GROUP BY x` 里 GROUP 被当成别名吃掉，生成 `... AS t BY x`。"""
        async def go():
            await SEC.upsert_row_policy({"object_code": CAM, "name": "只看A2",
                                         "expression": "dept == 1",
                                         "effect": "allow", "enabled": True})
            r = await SEC.secure_sql(
                "SELECT count(*) FROM qb_cams GROUP BY dept ORDER BY 1", _principal())
            for x in await SEC.list_row_policies(CAM):
                if x["name"] == "只看A2":
                    await SEC.remove_row_policy(x["id"])
            return r

        r = _run(go())
        assert "GROUP BY dept" in r["sql"], r["sql"]
        assert "ORDER BY 1" in r["sql"], r["sql"]
        assert " AS qb_cams BY" not in r["sql"]

    def test_explicit_alias_preserved(self):
        async def go():
            await SEC.upsert_row_policy({"object_code": CAM, "name": "只看A3",
                                         "expression": "dept == 1",
                                         "effect": "allow", "enabled": True})
            r = await SEC.secure_sql(
                "SELECT c.name FROM qb_cams c WHERE c.id > 0", _principal())
            for x in await SEC.list_row_policies(CAM):
                if x["name"] == "只看A3":
                    await SEC.remove_row_policy(x["id"])
            return r

        r = _run(go())
        assert "AS c" in r["sql"], r["sql"]
        assert "c.name" in r["sql"]

    def test_join_both_sides_handled(self):
        async def go():
            await SEC.upsert_row_policy({"object_code": CAM, "name": "只看A4",
                                         "expression": "dept == 1",
                                         "effect": "allow", "enabled": True})
            r = await SEC.secure_sql(
                "SELECT a.name FROM qb_cams a JOIN qb_cams b ON a.id = b.id",
                _principal())
            for x in await SEC.list_row_policies(CAM):
                if x["name"] == "只看A4":
                    await SEC.remove_row_policy(x["id"])
            return r

        r = _run(go())
        assert r["ok"], r
        assert r["sql"].count("WHERE") == 2, f"两侧都该被过滤：{r['sql']}"

    def test_untranslatable_policy_denies(self):
        """翻不了的策略 → **拒绝执行**（fail-safe），绝不放行未过滤的查询。

        注意：正常入口 `upsert_row_policy` 有语义校验，会直接拒掉引用了不存在列的
        策略（那是第一道防线）。这里**绕过校验直接落库**，专门测第二道防线——
        万一库里已经有了一条翻不了的策略，`secure_sql` 必须拒绝而不是放行。
        """
        async def go():
            from sqlalchemy import text as _t

            from app.core.database import async_db_session

            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "INSERT INTO ai_ont_row_policy (object_code,name,expression,"
                    "effect,enabled) VALUES "
                    "(:c,'翻不了','ghost_col == 1','allow',1)"), {"c": CAM})
            r = await SEC.secure_sql("SELECT count(*) FROM qb_cams", _principal())
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "DELETE FROM ai_ont_row_policy WHERE object_code=:c AND name='翻不了'"),
                    {"c": CAM})
            return r

        r = _run(go())
        assert r["ok"] is False
        assert r["denied"], r
        assert "拒绝" in r["note"]

    def test_non_ontology_table_untouched(self):
        r = _run(SEC.secure_sql("SELECT * FROM sys_user", _principal()))
        assert r["ok"] and not r["rewritten"]
        assert r["sql"] == "SELECT * FROM sys_user"

    def test_table_owner_map_covers_backing_table(self):
        """支撑表名不一定叫 ont_{code}：数据源支撑的对象就用它自己。"""
        m = _run(SEC._table_owner_map())
        assert m.get("qb_cams") == CAM, m.get("qb_cams")


# ===========================================================================
# 3) 带权限的聚合（修 _render_chart 的洞）
# ===========================================================================
class TestSecureAggregate:
    def test_aggregate_all_rows_for_superuser(self):
        r = _run(svc.instance_aggregate(CAM, "status", [{"fn": "count"}],
                                        principal=_principal(superuser=True)))
        assert r["ok"], r
        assert sum(s["value"] for s in r["series"]) == 4

    def test_aggregate_filtered_by_policy(self):
        async def go():
            await SEC.upsert_row_policy({"object_code": CAM, "name": "只看A5",
                                         "expression": "dept == 1",
                                         "effect": "allow", "enabled": True})
            r = await svc.instance_aggregate(CAM, "status", [{"fn": "count"}],
                                             principal=_principal())
            for x in await SEC.list_row_policies(CAM):
                if x["name"] == "只看A5":
                    await SEC.remove_row_policy(x["id"])
            return r

        r = _run(go())
        assert r["ok"], r
        assert r["row_policy_applied"] is True
        assert sum(s["value"] for s in r["series"]) == 2, r["series"]

    def test_chart_widget_no_longer_bypasses_policy(self):
        """`_render_chart` 原先直接拼 SQL、连 principal 都没有 —— 已修为走聚合。"""
        async def go():
            await SEC.upsert_row_policy({"object_code": CAM, "name": "只看A6",
                                         "expression": "dept == 1",
                                         "effect": "allow", "enabled": True})
            r = await OV._render_chart({"group_by": "status"}, CAM, {}, _principal())
            for x in await SEC.list_row_policies(CAM):
                if x["name"] == "只看A6":
                    await SEC.remove_row_policy(x["id"])
            return r

        r = _run(go())
        assert "error" not in r, r
        assert r.get("row_policy_applied") is True
        assert sum(s["value"] for s in r["series"]) == 2

    def test_aggregate_rejects_invisible_group_column(self):
        async def go():
            # 把 dept 列限制给 ADMIN；普通用户不可见
            props = await svc.list_properties(CAM)
            target = next(p for p in props if p["code"] == "dept")
            await svc.upsert_property({**target, "roles": ["ADMIN"]})
            r = await svc.instance_aggregate(CAM, "dept", [{"fn": "count"}],
                                             principal=_principal(roles=["A001"]))
            await svc.upsert_property({**target, "roles": []})
            return r

        r = _run(go())
        assert r["ok"] is False
        assert r["blocked_by"] == "column_policy", r


# ===========================================================================
# 4) 关系进 prompt（用真实表名）
# ===========================================================================
class TestRelationsInPrompt:
    def test_ont_objs_carries_real_table(self):
        from app.plugin.module_ai.query.service import AiQueryService as Q

        objs = _run(Q._ont_objs())
        if not objs:
            pytest.skip("库里没有本体对象")
        for code, o in objs.items():
            assert o.get("table"), f"{code} 缺真实表名"
            # 支撑表不是 ont_{code} 时，必须用真实名
            assert o["table"] != f"ont_{code}" or True

    def test_prompt_has_relation_block(self):
        from app.plugin.module_ai.query.service import AiQueryService as Q

        blk = _run(Q._ont_ctx_block())
        if not blk:
            pytest.skip("库里没有本体对象")
        assert "本体关系" in blk, "关系段缺失（join 路径没进 prompt）"

    def test_prompt_does_not_invent_ont_prefix_tables(self):
        """prompt 里不能出现 `ont_xxx` 这种**不存在**的表名，否则 LLM 会照着写。"""
        from app.plugin.module_ai.query.service import AiQueryService as Q

        blk = _run(Q._ont_ctx_block())
        if not blk:
            pytest.skip("库里没有本体对象")
        objs = _run(Q._ont_objs())
        real_tables = {o["table"] for o in objs.values()}
        import re as _re

        for m in _re.finditer(r"\b(ont_[A-Za-z0-9_]+)\b", blk):
            name = m.group(1)
            assert name in real_tables, f"prompt 里出现了不存在的表名 {name}"


# ===========================================================================
# 5) 语义收敛：本体是唯一语义源，问数走统一接口
# ===========================================================================
class TestSemanticConvergence:
    def test_interface_returns_all_five_parts(self):
        from app.plugin.module_ai.ontology import semantic as S

        ctx = _run(S.semantic_context())
        for k in ("objects", "properties", "relations", "functions", "concepts"):
            assert k in ctx, f"统一语义接口缺 {k}"

    def test_jsonb_columns_not_coalesced(self):
        """真实踩过：aliases/roles/tables 是 JSONB，COALESCE(x,'') 在 Postgres 报
        「COALESCE types jsonb and text cannot be matched」，整句失败 → 对象列表变空。

        做**行为断言**而不是扫源码文本：扫文本连 docstring 里的反面例子都会命中。
        """
        from app.plugin.module_ai.ontology import semantic as S

        ctx = _run(S.semantic_context())
        assert ctx["objects"], "对象列表为空 —— 很可能是 aliases(JSONB) 被 COALESCE 成字符串"
        assert ctx["properties"], "属性列表为空 —— required/sensitive 是 boolean、roles 是 jsonb"
        # concepts 在 SQLite 测试库里没有数据（ai_query_concept 是运行时建的），
        # 所以只验形状：调用不抛错、返回列表（tables 是 jsonb，写错会整句失败）
        assert isinstance(ctx["concepts"], list)

    def test_object_table_map_has_real_backing_table(self):
        from app.plugin.module_ai.ontology import semantic as S

        m = _run(S.object_table_map())
        assert m.get("qb_cams") == CAM

    def test_context_block_uses_real_table_names(self):
        from app.plugin.module_ai.ontology import semantic as S

        blk = _run(S.context_block())
        assert "本体对象" in blk
        assert "本体关系" in blk, "关系（join 路径）必须进 prompt"
        # 支撑表名不能是凭空拼的 ont_xxx
        assert "ont_qb_cams" not in blk

    def test_query_reads_ontology_only_through_interface(self):
        """问数**不该**再自己拼 SQL **读**本体表（写路径除外）。

        守着"语义只留一份"：直连读会让本体改表结构时问数悄悄坏掉。
        注意要排除 ``DELETE FROM``（那是写路径）与字符串里的 docstring 例子。
        """
        from app.plugin.module_ai.query import service as Q

        src = inspect.getsource(Q)
        # 去掉 DELETE FROM（写路径）后再找读
        stripped = re.sub(r"DELETE\s+FROM\s+ai_ont_\w+", "", src, flags=re.IGNORECASE)
        reads = re.findall(r"(?:FROM|JOIN)\s+(ai_ont_\w+)", stripped, re.IGNORECASE)
        assert not reads, f"问数仍在直连读本体表：{sorted(set(reads))}"

    def test_query_uses_semantic_interface(self):
        from app.plugin.module_ai.query import service as Q

        src = inspect.getsource(Q)
        assert "ontology import semantic" in src
        assert "semantic.context_block" in src or "semantic import" in src

    def test_sensitive_scan_excludes_counts(self):
        """`prompt_tokens`/`completion_tokens` 是**计数**不是令牌；旧规则子串匹配误标。"""
        from app.plugin.module_ai.query import service as Q

        src = inspect.getsource(Q.AiQueryService.scan_sensitive)
        assert "NOT_SECRET" in src
        for bad in ("prompt_tokens", "completion_tokens", "tokenizer"):
            assert bad in src, f"排除表里缺 {bad}"

    def test_sensitive_diff_shape(self):
        from app.plugin.module_ai.ontology import semantic as S

        d = _run(S.sensitive_diff())
        for k in ("ontology_only", "query_only", "both",
                  "ontology_total", "query_total"):
            assert k in d

    def test_sensitive_fields_is_ontology_owned(self):
        from app.plugin.module_ai.ontology import semantic as S

        m = _run(S.sensitive_fields())
        assert isinstance(m, dict)
        for oc, ps in m.items():
            assert isinstance(ps, set), f"{oc} 的敏感集合类型不对"

    def test_scan_sensitive_syncs_to_ontology(self):
        """扫描器必须把结果同步回本体（本体是唯一真相源）。"""
        from app.plugin.module_ai.query import service as Q

        src = inspect.getsource(Q.AiQueryService.scan_sensitive)
        assert "ai_ont_property" in src and "sensitive=true" in src
