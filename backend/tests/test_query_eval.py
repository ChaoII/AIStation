"""问数评测模块单测：表/CRUD、指标纯函数、生成解析与校验、执行器与消融。

纯逻辑部分可 ``PYTEST_NO_APP=1`` 快速跑；涉及 DB/HTTP 的按默认模式跑。
"""
import asyncio


# ===========================================================================
# 批次1：三表 + 测试集 CRUD
# ===========================================================================
def test_ensure_eval_tables_is_idempotent():
    async def _run():
        from app.plugin.module_ai.query.eval_set import ensure_eval_tables

        await ensure_eval_tables()
        await ensure_eval_tables()  # 第二次不得报错

    asyncio.run(_run())


def test_upsert_case_is_idempotent_and_filterable():
    async def _run():
        from app.plugin.module_ai.query.eval_set import list_cases, upsert_case

        await upsert_case({
            "question": "Q_IDEMPOTENT", "gold_sql": "SELECT 1", "datasource": "system",
            "difficulty": "简单", "scenario": "安防", "form": "单维统计",
        })
        await upsert_case({
            "question": "Q_IDEMPOTENT", "gold_sql": "SELECT 1", "datasource": "system",
            "difficulty": "困难", "scenario": "安防", "form": "联表",
        })
        rows = [c for c in await list_cases(datasource="system") if c["question"] == "Q_IDEMPOTENT"]
        assert len(rows) == 1, "同 (datasource,question) 必须只有一条"
        assert rows[0]["difficulty"] == "困难"  # 后写覆盖
        assert await list_cases(difficulty="不存在的难度") == []

    asyncio.run(_run())


def test_import_cases_skips_invalid():
    async def _run():
        from app.plugin.module_ai.query.eval_set import import_cases

        out = await import_cases([
            {"question": "Q_OK", "gold_sql": "SELECT 1", "datasource": "system"},
            {"question": "", "gold_sql": "SELECT 1"},
            {"question": "Q_NO_SQL"},
        ])
        assert out == {"saved": 1, "skipped": 2}

    asyncio.run(_run())


# ===========================================================================
# 批次2：指标纯函数（可 PYTEST_NO_APP=1 快速跑）
# ===========================================================================
def test_gold_tables_and_recall_at_k():
    from app.plugin.module_ai.query.eval_metrics import gold_tables, recall_at_k

    schema = {"FUEL_CB_COALBALANCE": [], "FUEL_CMCS_ASSAY": [], "OTHER": []}
    sql = 'SELECT * FROM "FUEL_CB_COALBALANCE" a JOIN FUEL_CMCS_ASSAY b ON a.id=b.id'
    assert gold_tables(sql, schema) == {"FUEL_CB_COALBALANCE", "FUEL_CMCS_ASSAY"}
    assert recall_at_k({"A", "B"}, ["A", "B", "C"], k=8) == 1.0
    assert recall_at_k({"A", "B"}, ["X", "Y"], k=8) == 0.0
    assert recall_at_k({"A", "B"}, ["B", "X", "Y", "A"], k=2) == 0.5  # 只看前 2
    assert recall_at_k(set(), ["X"], k=8) == 1.0


def test_summarize_and_group_by_dimension():
    from app.plugin.module_ai.query.eval_metrics import group_by, summarize

    results = [
        {"gold_match": True, "metric_key": "m1", "expected_metric": "m1", "path": "fast",
         "is_error": False, "took_ms": 100, "recall": 1.0, "difficulty": "简单"},
        {"gold_match": False, "metric_key": "m2", "expected_metric": "m1", "path": "slow",
         "is_error": True, "took_ms": 300, "recall": 0.0, "difficulty": "困难"},
    ]
    s = summarize(results)
    assert s["total"] == 2
    assert s["data_accuracy"] == 0.5
    assert s["semantic_accuracy"] == 0.5  # 2 题都带期望，命中 1 题
    assert s["fast_rate"] == 0.5
    assert s["error_rate"] == 0.5
    assert s["avg_ms"] == 200.0
    assert s["recall_at_k"] == 0.5
    g = group_by(results, "difficulty")
    assert g["简单"]["accuracy"] == 1.0 and g["困难"]["accuracy"] == 0.0
    assert summarize([])["total"] == 0


# ===========================================================================
# 批次3：LLM 出题解析 + 金标校验入库
# ===========================================================================
def test_parse_cases_tolerates_markdown_and_noise():
    from app.plugin.module_ai.query.eval_generate import parse_cases

    text = (
        "这是说明\n```json\n"
        '{"cases":[{"question":"Q","gold_sql":"SELECT 1","difficulty":"简单","form":"单维统计"}]}'
        "\n```\n完毕"
    )
    out = parse_cases(text)
    assert out and out[0]["question"] == "Q" and out[0]["gold_sql"] == "SELECT 1"
    assert parse_cases("没有任何 JSON") == []
    assert parse_cases('[{"question":"A","sql":"SELECT 2"}]')[0]["gold_sql"] == "SELECT 2"


def test_verify_and_save_rejects_unexecutable_or_empty_gold(monkeypatch):
    async def _run():
        from types import SimpleNamespace

        from app.plugin.module_ai.query import eval_generate as G
        from app.plugin.module_ai.query.eval_set import list_cases

        async def fake_run(sql, ds, auth):
            if sql == "SELECT bad":
                return {"ok": False, "rows": [], "error": "UndefinedTable"}
            if sql == "SELECT empty":
                return {"ok": True, "rows": [], "error": ""}
            return {"ok": True, "rows": [1], "error": ""}

        monkeypatch.setattr(G, "_run_gold", fake_run)
        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        out = await G.verify_and_save(
            [
                {"question": "EV_GOOD", "gold_sql": "SELECT good", "difficulty": "简单", "form": "单维统计"},
                {"question": "EV_BAD", "gold_sql": "SELECT bad", "difficulty": "简单", "form": "单维统计"},
                {"question": "EV_EMPTY", "gold_sql": "SELECT empty", "difficulty": "简单", "form": "单维统计"},
            ],
            "system", auth,
        )
        assert out["saved"] == 1 and out["rejected"] == 2
        questions = {c["question"] for c in await list_cases(datasource="system")}
        assert "EV_GOOD" in questions
        assert "EV_BAD" not in questions and "EV_EMPTY" not in questions

    asyncio.run(_run())


# ===========================================================================
# 批次4：执行器 + 配置覆盖 + 消融
# ===========================================================================
def test_override_settings_restores_original_values():
    """决定性：配置覆盖退出后**必须恢复**（否则污染后续评测与业务请求）。"""
    async def _run():
        from app.plugin.module_ai.query.eval_runner import override_settings
        from app.plugin.module_ai.query.service import AiQueryService as S

        before = (await S._cfg()).get("recall_enabled")
        flipped = "false" if before == "true" else "true"
        async with override_settings({"recall_enabled": flipped}):
            S._SETTINGS_CACHE = None
            assert (await S._cfg()).get("recall_enabled") == flipped
        S._SETTINGS_CACHE = None
        assert (await S._cfg()).get("recall_enabled") == before

    asyncio.run(_run())


def test_run_finishes_normally_with_empty_filter(monkeypatch):
    """筛选后无题 → 正常结束（total=0/done=0），不得报错。"""
    async def _run():
        from app.plugin.module_ai.query import eval_runner as R

        async def fake_ask(question, auth, datasource, force_slow=False):
            return {"path": "fast", "is_error": False, "sql": "SELECT 1", "rows": [[1]]}

        monkeypatch.setattr(R, "_ask", fake_ask)
        rid = R.start_run(R._auth(), filter={"difficulty": "不存在的难度"})
        for _ in range(60):
            st = R.get_status(rid)
            if st and st["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.05)
        assert st["status"] == "done", st
        assert st["total"] == 0 and st["done"] == 0

    asyncio.run(_run())


def test_ablation_runs_baseline_first_and_is_serial(monkeypatch):
    async def _run():
        from app.plugin.module_ai.query import eval_runner as R

        order: list[str] = []

        async def fake_group(name, auth, flt, overrides, run_id):
            order.append(name)
            return {"data_accuracy": 0.5}

        monkeypatch.setattr(R, "_run_ablation_group", fake_group)
        rid = R.start_ablation(R._auth(), keys=["recall_enabled", "kg_enabled"])
        for _ in range(60):
            rep = R.get_ablation_report(rid)
            if rep and rep["status"] in ("done", "error"):
                break
            await asyncio.sleep(0.05)
        assert order[0] == "baseline"  # 先跑全开基线
        assert order == ["baseline", "recall_enabled", "kg_enabled"]  # 串行、每组一次
        assert set(R.get_ablation_report(rid)["table"]) == {"baseline", "recall_enabled", "kg_enabled"}

    asyncio.run(_run())


def test_parse_cases_recovers_complete_items_from_truncated_json():
    """实测：模型输出常被**截断**（reasoning 吃掉 max_tokens），
    旧解析器直接返回 0 条 → 硬形式出题全部落空。必须能**救回**前面完整的对象。"""
    from app.plugin.module_ai.query.eval_generate import parse_cases

    truncated = (
        '{"cases":['
        '{"question":"q1","gold_sql":"SELECT 1","difficulty":"简单",'
        '"scenario":"s","form":"f","expected_metric":""},'
        '{"question":"q2","gold_sql":"SELECT 2","difficulty":"中等",'
        '"scenario":"s","form":"f","expected_metric":"'
    )
    cases = parse_cases(truncated)
    assert len(cases) == 1, f"应救回 1 条完整对象，实际 {len(cases)}: {cases}"
    assert cases[0]["question"] == "q1"
    assert cases[0]["gold_sql"] == "SELECT 1"


def test_parse_cases_still_handles_wellformed_json():
    from app.plugin.module_ai.query.eval_generate import parse_cases

    ok = ('```json\n{"cases":[{"question":"q","gold_sql":"SELECT 1",'
          '"difficulty":"简单","scenario":"s","form":"f","expected_metric":""}]}\n```')
    cases = parse_cases(ok)
    assert len(cases) == 1 and cases[0]["question"] == "q"


# ===========================================================================
# 批次7：生成专用题（指标答不了的题才算"考生成能力"）
# ===========================================================================
def test_verify_and_save_generation_only_rejects_metric_eligible(monkeypatch):
    """快路径能答的题不算生成题：`generation_only=True` 时必须被拒。"""
    async def _run():
        from types import SimpleNamespace

        from app.plugin.module_ai.query import eval_generate as G

        async def fake_run(sql, ds, auth):
            return {"ok": True, "rows": [[5]], "error": ""}

        monkeypatch.setattr(G, "_run_gold", fake_run)
        # 让"今日告警数"命中指标（快路径能答），"各部门平均单价"答不了
        async def _elig(q, ds):
            return "告警" in q

        monkeypatch.setattr(G, "_metric_eligible_for", _elig)
        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        out = await G.verify_and_save(
            [
                {"question": "今天一共产生了多少条告警？", "gold_sql": "SELECT 1",
                 "difficulty": "简单", "form": "单维统计"},
                {"question": "各部门的平均单价是多少？", "gold_sql": "SELECT 1",
                 "difficulty": "中等", "form": "多维报表"},
            ],
            "system", auth, generation_only=True,
        )
        assert out["saved"] == 1, out
        assert out["rejected_metric"] == 1, out

        from app.plugin.module_ai.query.eval_set import list_cases

        qs = {c["question"] for c in await list_cases(datasource="system")}
        assert "各部门的平均单价是多少？" in qs
        assert "今天一共产生了多少条告警？" not in qs

    asyncio.run(_run())


def test_verify_and_save_default_keeps_metric_questions(monkeypatch):
    """默认（非 generation_only）仍然收录指标题 —— 快路径的枚举能力也要保住。"""
    async def _run():
        from types import SimpleNamespace

        from app.plugin.module_ai.query import eval_generate as G

        async def fake_run(sql, ds, auth):
            return {"ok": True, "rows": [[5]], "error": ""}

        monkeypatch.setattr(G, "_run_gold", fake_run)

        async def _elig(q, ds):
            return True

        monkeypatch.setattr(G, "_metric_eligible_for", _elig)
        auth = SimpleNamespace(user=SimpleNamespace(id=1))
        out = await G.verify_and_save(
            [{"question": "枚举题EV_METRIC", "gold_sql": "SELECT 1",
              "difficulty": "简单", "form": "单维统计"}],
            "system", auth,
        )
        assert out["saved"] == 1, out

    asyncio.run(_run())


def test_summarize_reports_generation_accuracy_separately():
    """「生成能力」必须能单独看到：快路径能答的题不算考生成。"""
    from app.plugin.module_ai.query.eval_metrics import summarize

    def row(match, eligible, degenerate=False):
        return {"gold_match": match, "is_error": False, "path": "slow", "took_ms": 10,
                "recall": 0.0, "degenerate": degenerate, "metric_eligible": eligible}

    s = summarize([
        row(True, True),        # 指标题：答对
        row(False, False),      # 生成题：答错
        row(True, False),       # 生成题：答对
        row(True, True, True),  # 退化题：两边都不计
    ])
    assert s["total"] == 3
    assert s["metric_total"] == 1 and s["metric_accuracy"] == 1.0
    assert s["generation_total"] == 2, s
    assert s["generation_accuracy"] == 0.5, s


# ===========================================================================
# 批次8：few-shot 相关度选取（中文必须按字/二元组，不能整句当 token）
# ===========================================================================
def test_fewshot_scoring_is_chinese_aware():
    """实测 bug：中文整句被当成一个 token → 相关度全为 0 → 选出的示例与问句无关。"""
    from app.plugin.module_ai.query.service import score_fewshot

    q = "按煤种类型统计记录数并排名"
    related = score_fewshot(q, "按煤种类型统计记录数并排名")
    unrelated = score_fewshot(q, "化验记录一共有多少条？")
    assert related > unrelated, f"相关示例应得分更高: {related} vs {unrelated}"
    assert related >= 6, f"完全相同的问句得分应较高，实际 {related}"


def test_pick_fewshots_prefers_relevant_and_same_datasource():
    from app.plugin.module_ai.query.service import pick_fewshots

    examples = [
        {"question": "化验记录一共有多少条？", "datasource": "ds:4", "sql": "S1"},
        {"question": "按煤种类型统计记录数并排名", "datasource": "ds:4", "sql": "S2"},
        # 注意：**不能与查询完全相同** —— 相同的示例会被防泄漏规则排除
        {"question": "各煤种类型的记录占比是多少（按类型分组）", "datasource": "ds:4", "sql": "S3"},
        {"question": "按告警类型统计各类告警的数量", "datasource": "system", "sql": "S4"},
    ]
    picked = pick_fewshots("各煤种类型的记录占比是多少", examples, "ds:4", k=2)
    assert [p["sql"] for p in picked] == ["S3", "S2"], picked


def test_lenient_match_allows_model_subset_of_gold_columns():
    """模型只返回金标列的一个**前缀子集**时，只要行值对得上就算对。

    实测：窗口函数题模型逻辑完全正确（ROW_NUMBER OVER + rn=1），
    但少选了一列（金标多一列 CREATIONTIME）→ 旧口径一律判错，
    导致「窗口函数 0%」里混进了大量"逻辑对、列少了"的假失败。
    """
    from app.plugin.module_ai.query.benchmark import lenient_match

    gold_cols = ["FACILITYID", "CODE", "NAME", "CREATIONTIME"]
    gold_rows = [[1, "A", "测点A", "2024-01-01"], [2, "B", "测点B", "2024-01-02"]]
    model_cols = ["设备ID", "测点编码", "测点名称"]
    model_rows = [[1, "A", "测点A"], [2, "B", "测点B"]]
    assert lenient_match(gold_cols, gold_rows, model_cols, model_rows) is True


def test_lenient_match_still_rejects_wrong_values_with_subset_columns():
    from app.plugin.module_ai.query.benchmark import lenient_match

    gold_cols = ["FACILITYID", "CODE", "NAME", "CREATIONTIME"]
    gold_rows = [[1, "A", "测点A", "2024-01-01"]]
    model_cols = ["设备ID", "测点编码", "测点名称"]
    model_rows = [[1, "A", "别的名字"]]        # 值不对
    assert lenient_match(gold_cols, gold_rows, model_cols, model_rows) is False


def test_lenient_match_subset_requires_same_row_count():
    from app.plugin.module_ai.query.benchmark import lenient_match

    gold_cols = ["A", "B", "C"]
    gold_rows = [[1, "x", "p"], [2, "y", "q"]]
    model_cols = ["A", "B"]
    model_rows = [[1, "x"]]                    # 行数不同
    assert lenient_match(gold_cols, gold_rows, model_cols, model_rows) is False


# ===========================================================================
# 批次9：NL2SQL 生成的 token 预算（推理模型会先"想"再吐 SQL）
# ===========================================================================
def test_nl2sql_max_tokens_has_floor_because_reasoning_eats_budget():
    """实测：本机模型**先推理约 2084 token 才输出 SQL**；
    max_tokens=2000 时 finish_reason=length、正文为空 → "未生成有效的查询语句"。
    所以配置值低于下限必须抬高（否则困难题必空）。"""
    from app.plugin.module_ai.query.service import nl2sql_max_tokens

    assert nl2sql_max_tokens({"nl2sql_max_tokens": "1200"}) >= 4000
    assert nl2sql_max_tokens({}) >= 4000
    assert nl2sql_max_tokens({"nl2sql_max_tokens": "9000"}) == 9000
    # 非法值走默认
    assert nl2sql_max_tokens({"nl2sql_max_tokens": "abc"}) >= 4000


# ===========================================================================
# 批次10：检索必须按数据源隔离（否则 ds:4 问题召回到 system 源的表 → 表名幻觉）
# ===========================================================================
def test_retrieval_cache_key_includes_datasource():
    from app.plugin.module_ai.query.service import _retrieval_cache_key

    a = _retrieval_cache_key("测点有多少个", "ds:4")
    b = _retrieval_cache_key("测点有多少个", "system")
    assert a != b, "检索缓存 key 必须含数据源，否则两个数据源互相串缓存"


def test_pick_fewshots_excludes_the_question_itself():
    """防泄漏：示例里与当前问句**完全相同**的那条必须被排除。

    实测：把评测错题沉淀成示例后，评测时 top-4 里就有本题自己 →
    模型等于看到答案 → 分数从 80.7% 虚高到 95.0%。
    """
    from app.plugin.module_ai.query.service import pick_fewshots

    examples = [
        {"question": "各煤种类型的记录占比是多少", "datasource": "ds:4", "sql": "S_self"},
        {"question": "各煤种类型有多少条记录", "datasource": "ds:4", "sql": "S_other"},
    ]
    picked = pick_fewshots("各煤种类型的记录占比是多少", examples, "ds:4", k=2)
    assert [p["sql"] for p in picked] == ["S_other"], picked
    # 空格差异也算同一题
    picked2 = pick_fewshots("各煤种类型的记录占比是多少 ", examples, "ds:4", k=2)
    assert [p["sql"] for p in picked2] == ["S_other"], picked2


def test_recall_grounding_scopes_to_datasource():
    """召回结果必须被限制在本次数据源的 schema 内（纯函数，不依赖真库）。"""
    from app.plugin.module_ai.query.service import scope_tables_to_schema

    schema = {"CMMS_POINT": [], "FUEL_CB_COALBALANCE": []}
    core = ("video_cameras",)      # system 源的核心表

    # 命中：只留同源表
    assert scope_tables_to_schema(
        ["video_cameras", "CMMS_POINT"], schema, core, 12) == ["CMMS_POINT"]
    # 全被过滤 → 用核心表里的同源表
    assert scope_tables_to_schema(
        ["video_cameras"], schema, ("CMMS_POINT",), 12) == ["CMMS_POINT"]
    # 核心表也不匹配 → 兜底取该数据源前若干张（绝不返回空）
    assert scope_tables_to_schema(["video_cameras"], schema, (), 1) == ["CMMS_POINT"]
    # top_k 截断
    assert len(scope_tables_to_schema(
        ["CMMS_POINT", "FUEL_CB_COALBALANCE"], schema, core, 1)) == 1


def test_gold_must_reference_entities_mentioned_in_question():
    """问题提到的业务实体，金标**必须引用对应表**。

    实测：问题「每个**设备**下上限最高的两个测点」的金标只用了 `CMMS_POINT`，
    **没联设备表** —— 金标自己"抄近路"，与问题语义不一致；
    模型老老实实联了设备表（而设备表为空）反而被判错。这是**出题质量**问题。
    """
    from app.plugin.module_ai.query.eval_generate import missing_entity_tables

    m = {"设备": "CMMS_FACILITY", "测点": "CMMS_POINT"}
    assert missing_entity_tables(
        "每个设备下上限最高的两个测点", 'SELECT * FROM "CMMS_POINT"', m
    ) == ["CMMS_FACILITY"]
    assert missing_entity_tables(
        "每个设备下的测点",
        'SELECT * FROM "CMMS_POINT" p JOIN "CMMS_FACILITY" f ON 1=1', m,
    ) == []
    # 问题没提到的实体不算缺
    assert missing_entity_tables('SELECT 1 FROM "CMMS_POINT"', 'SELECT 1 FROM "CMMS_POINT"', m) == []


# ===========================================================================
# 批次5：REST 接口
# ===========================================================================
def test_lenient_match_normalizes_null_on_both_sides():
    """NULL 必须两侧一致归一化，否则「金标 NULL vs 模型 NULL」被误判为错。

    实测：ds:4 有 48% 的题结果是 NULL（空表聚合），金标侧没走 _norm_cell →
    `'None' != '∅'` → 即使模型 SQL 与金标完全相同也被判错。
    """
    from app.plugin.module_ai.query.benchmark import lenient_match

    assert lenient_match(["c"], [[None]], ["c"], [[None]]) is True
    assert lenient_match(["c"], [[None]], ["c"], [["∅"]]) is True


# ===========================================================================
# 批次6：退化题闸门（金标结果为空/NULL/单值 0 的题不参与精度统计）
# ===========================================================================
def test_is_degenerate_result_detects_empty_null_and_single_zero():
    from app.plugin.module_ai.query.eval_metrics import is_degenerate_result

    assert is_degenerate_result([]) is True
    assert is_degenerate_result([[None]]) is True
    assert is_degenerate_result([[0]]) is True
    assert is_degenerate_result([[0.0]]) is True
    assert is_degenerate_result([[""]]) is True
    assert is_degenerate_result([[None], [None]]) is True
    # 有真实信息 → 不算退化
    assert is_degenerate_result([[1]]) is False
    assert is_degenerate_result([[0], [1]]) is False
    assert is_degenerate_result([[None], [3]]) is False


def test_summarize_excludes_degenerate_rows():
    """退化题不能进分母：否则「任何 SQL 都能答对」把精度抬成虚高。"""
    from app.plugin.module_ai.query.eval_metrics import summarize

    rows = [
        {"gold_match": True, "is_error": False, "path": "fast", "took_ms": 10,
         "recall": 1.0, "degenerate": False},
        {"gold_match": False, "is_error": True, "path": "slow", "took_ms": 20,
         "recall": 0.0, "degenerate": False},
        {"gold_match": True, "is_error": False, "path": "fast", "took_ms": 30,
         "recall": 0.0, "degenerate": True},   # 退化题：不计入
    ]
    s = summarize(rows)
    assert s["total"] == 2, f"total 应只算非退化题: {s}"
    assert s["degenerate_n"] == 1
    assert s["all_total"] == 3
    assert s["data_accuracy"] == 0.5, s
    assert s["avg_ms"] == 15.0, s


def test_group_by_excludes_degenerate_rows():
    from app.plugin.module_ai.query.eval_metrics import group_by

    rows = [
        {"difficulty": "简单", "gold_match": False, "degenerate": False},
        {"difficulty": "简单", "gold_match": True, "degenerate": True},
    ]
    g = group_by(rows, "difficulty")
    assert g["简单"]["total"] == 1, g
    assert g["简单"]["accuracy"] == 0.0, g


def test_eval_cases_and_status_endpoints(test_client, auth_headers):
    h = auth_headers
    r = test_client.post(
        "/api/v1/ai/query/eval/cases",
        json={"question": "接口测试题EV", "gold_sql": "SELECT 1", "datasource": "system",
              "difficulty": "简单", "scenario": "安防", "form": "单维统计"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    r = test_client.get("/api/v1/ai/query/eval/cases", params={"difficulty": "简单"}, headers=h)
    assert r.status_code == 200
    assert any(c["question"] == "接口测试题EV" for c in r.json()["data"])
    r = test_client.get("/api/v1/ai/query/eval/status", headers=h)
    assert r.status_code == 200
    r = test_client.get("/api/v1/ai/query/eval/runs", headers=h)
    assert r.status_code == 200 and isinstance(r.json()["data"], list)
