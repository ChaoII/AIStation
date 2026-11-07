"""Step 2b：语义层草稿的提示词与幻觉过滤（纯逻辑）。"""
from app.plugin.module_ai.query.asset_draft import (
    DraftColumn,
    DraftResult,
    DraftTable,
    build_draft_prompt,
    filter_drafts,
)

TABLES = {"DTXY_PMXX": ["ID", "VARIETY", "RZ"], "DTXY_KQ": ["ID", "NAME"]}


def test_prompt_contains_table_and_columns():
    p = build_draft_prompt(TABLES)
    assert "DTXY_PMXX" in p and "VARIETY" in p
    assert "只输出 JSON" in p


def test_filter_drops_unknown_table_and_column():
    result = DraftResult(tables=[
        DraftTable(table="DTXY_PMXX", alias="煤质", description="煤质化验",
                   columns=[
                       DraftColumn(name="VARIETY", description="煤种"),
                       DraftColumn(name="SECRET", description="不该存在"),
                   ]),
        DraftTable(table="NOT_EXIST", description="幻觉表"),
    ])
    out = filter_drafts(result, TABLES)
    assert len(out) == 1
    assert out[0]["table"] == "DTXY_PMXX"
    assert [c["name"] for c in out[0]["columns"]] == ["VARIETY"]


def test_filter_is_case_insensitive():
    result = DraftResult(tables=[
        DraftTable(table="dtxy_pmxx", columns=[DraftColumn(name="variety", description="煤种")]),
    ])
    out = filter_drafts(result, TABLES)
    assert out[0]["table"] == "DTXY_PMXX"
    assert out[0]["columns"][0]["name"] == "variety"
