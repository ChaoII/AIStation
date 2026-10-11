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
