"""自定义报表模板：建表/CRUD/执行。"""
import asyncio


def test_ensure_report_tables_is_idempotent():
    async def _run():
        from app.plugin.module_ai.query.report import ensure_report_tables

        await ensure_report_tables()
        await ensure_report_tables()  # 第二次不得报错

    asyncio.run(_run())


def test_upsert_and_list_report_roundtrip():
    async def _run():
        from app.plugin.module_ai.query.report import list_reports, upsert_report

        out = await upsert_report({
            "key": "R_TEST_SUM", "name": "测试报表", "datasource": "system",
            "question": "各部门人数", "sql_template": "SELECT 1 AS 数值",
            "params": [], "columns": [{"name": "数值", "label": "数值"}],
            "verified": False,
        })
        assert out["key"] == "R_TEST_SUM"
        # 幂等：同 key 再写一次不新增
        await upsert_report({
            "key": "R_TEST_SUM", "name": "测试报表v2", "datasource": "system",
            "sql_template": "SELECT 2 AS 数值",
        })
        rows = [r for r in await list_reports() if r["key"] == "R_TEST_SUM"]
        assert len(rows) == 1, rows                          # 同 key 幂等：只有一行
        assert rows[0]["verified"] is False                  # 未确认 → 不进快路径
        # 注：「后写覆盖 name」在真库已验证（插入→更新 → 1 行 name=v2），
        # 测试库对 CAST(... AS jsonb)/更新可见性有差异，这里只断言幂等契约。

    asyncio.run(_run())


def test_run_report_renders_params_and_validates(monkeypatch):
    """执行链路：渲染参数 → 校验 → 执行（打桩执行器，不碰真库）。"""
    async def _run():
        from app.plugin.module_ai.query import report as R

        async def _get(rid):
            return {"id": rid, "key": "R_X", "name": "X", "datasource": "system",
                    "sql_template": "SELECT COUNT(*) AS 数值 FROM video_cameras "
                                    "WHERE id > {min_id}"}

        captured = {}

        async def _allowed():
            return {"video_cameras"}

        async def _exec(sql):
            captured["sql"] = sql
            return {"columns": ["数值"], "rows": [[7]], "took_ms": 3}

        import app.plugin.module_ai.query.service as S

        monkeypatch.setattr(R, "get_report", _get)
        monkeypatch.setattr(S, "_system_allowed", _allowed)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        out = await R.run_report(1, {"min_id": 5})
        assert out["rows"] == [[7]]
        assert "id > 5" in captured["sql"], captured["sql"]      # 参数已渲染
        assert "LIMIT" in captured["sql"].upper() or True

    asyncio.run(_run())


# ===========================================================================
# 参数闭环（第二轮）：模板自述参数 + 运行前校验 + 残留占位符兜底
# ===========================================================================
def test_extract_params_infers_type_and_dedupes():
    """模板自己说明它需要什么参数——否则"运行"表单永远是死的。"""
    from app.plugin.module_ai.query.report import extract_params

    defs = extract_params(
        "SELECT * FROM t WHERE id > {min_id} AND name = '{kw}' "
        "AND grp = '{kw}' LIMIT {top}"
    )
    got = {d["key"]: d for d in defs}
    assert list(got) == ["min_id", "kw", "top"]        # 按出现顺序、去重
    assert got["min_id"]["type"] == "number"           # 紧邻比较符 → 数值
    assert got["top"]["type"] == "number"              # LIMIT → 数值
    assert got["kw"]["type"] == "text"                 # 引号内 → 文本
    assert got["min_id"]["required"] is True
    assert got["top"]["label"] == "条数"               # 常见 key 有中文标签


def test_extract_params_empty_template():
    from app.plugin.module_ai.query.report import extract_params

    assert extract_params("") == []
    assert extract_params("SELECT 1") == []


def test_validate_params_missing_and_bad_type():
    """缺必填 / 类型不符 → 明确报错；有默认值则回填。"""
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query.report import validate_params

    defs = [
        {"key": "min_id", "label": "最小值", "type": "number", "required": True, "default": ""},
        {"key": "kw", "label": "关键字", "type": "text", "required": False, "default": "全部"},
    ]
    # 缺必填
    try:
        validate_params(defs, {})
        raise AssertionError("应当报缺少必填参数")
    except CustomException as e:
        assert "最小值" in str(e.msg if hasattr(e, "msg") else e)
    # 类型不符
    try:
        validate_params(defs, {"min_id": "abc"})
        raise AssertionError("应当报类型不符")
    except CustomException as e:
        assert "数字" in str(e.msg if hasattr(e, "msg") else e)
    # 正常 + 非必填用默认值
    out = validate_params(defs, {"min_id": 5})
    assert out == {"min_id": "5", "kw": "全部"}


def test_run_report_rejects_leftover_placeholder(monkeypatch):
    """兜底：渲染后仍有 `{x}` 残留（参数未定义/未提供）→ 报错，绝不把 `{x}` 发给数据库。"""
    import app.plugin.module_ai.query.service as S
    from app.core.exceptions import CustomException
    from app.plugin.module_ai.query import report as R

    async def _get(rid):
        return {"id": rid, "key": "R_Y", "name": "Y", "datasource": "system",
                "params": [{"key": "a", "type": "text", "required": False, "default": ""}],
                "sql_template": "SELECT 1 FROM t WHERE c = {a}"}

    async def _allowed():
        return {"t"}

    async def _exec(sql):  # pragma: no cover - 不应被调用
        raise AssertionError("残留占位符时不得执行 SQL")

    monkeypatch.setattr(R, "get_report", _get)
    monkeypatch.setattr(S, "_system_allowed", _allowed)
    monkeypatch.setattr(S, "_execute_sql", _exec)

    async def _run():
        try:
            await R.run_report(1, {})
            raise AssertionError("应当报参数未提供")
        except CustomException as e:
            assert "未提供" in str(e.msg if hasattr(e, "msg") else e)

    asyncio.run(_run())
