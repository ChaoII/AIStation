"""澄清反问：确定性歧义检测（纯逻辑，PYTEST_NO_APP=1 可跑）。"""


def test_detects_group_key_ambiguity_when_name_and_id_both_exist():
    """问「按原煤仓分组」而表里同时有 BUNKERNAME/BUNKERID → 反问用户选哪个。

    实测：模型自己挑（常挑到与金标不同的那个）→ 判错。问一句成本远低于猜错。
    """
    from app.plugin.module_ai.query.clarify import detect_clarify

    schema = {
        "FUEL_CMCS_INCOALBUNKER": [
            "BUNKERNAME(原煤仓名称)", "BUNKERID(原煤仓编号)", "INQTY(入仓煤量)",
        ],
    }
    got = detect_clarify("按原煤仓分组统计入仓煤量", schema)
    assert got is not None, "应检出分组键歧义"
    assert got["field"] == "group_key"
    assert {o["value"] for o in got["options"]} == {"BUNKERNAME", "BUNKERID"}
    assert got["allow_free_text"] is True


def test_no_clarify_when_not_asking_grouping():
    """不是分组问句 → 不打扰用户。"""
    from app.plugin.module_ai.query.clarify import detect_clarify

    schema = {"T": ["BUNKERNAME(原煤仓名称)", "BUNKERID(原煤仓编号)"]}
    assert detect_clarify("原煤仓一共有多少个", schema) is None


def test_no_clarify_when_only_one_key_available():
    from app.plugin.module_ai.query.clarify import detect_clarify

    schema = {"T": ["BUNKERID(原煤仓编号)", "INQTY(入仓煤量)"]}
    assert detect_clarify("按原煤仓分组统计入仓煤量", schema) is None


def test_no_clarify_when_question_mentions_other_entity():
    from app.plugin.module_ai.query.clarify import detect_clarify

    schema = {"T": ["BUNKERNAME(原煤仓名称)", "BUNKERID(原煤仓编号)"]}
    assert detect_clarify("按供应商分组统计煤款", schema) is None


def test_merge_clarify_answer_appends_choice_to_question():
    from app.plugin.module_ai.query.clarify import merge_clarify_answer

    clarify = {"options": [{"label": "原煤仓名称（BUNKERNAME）", "value": "BUNKERNAME"}]}
    out = merge_clarify_answer("按原煤仓分组统计入仓煤量", clarify, "BUNKERNAME")
    assert "按原煤仓分组统计入仓煤量" in out
    assert "BUNKERNAME" in out
