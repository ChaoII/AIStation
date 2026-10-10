"""火电厂数据整理：纯逻辑单测（可 ``PYTEST_NO_APP=1`` 快速跑）。

落库/LLM 部分见 ``scripts/seed_power_plant_ontology.py``（不在单测里跑外部库与 LLM）。
"""
from app.plugin.module_ai.query import power_plant as PP


def _rec(table: str, comment: str = "", cols: list | None = None) -> dict:
    return {"table": table, "comment": comment, "columns": cols or []}


def test_is_core_filters_technical_tables():
    assert PP.is_core("FUEL_CB_COALBALANCE")
    assert PP.is_core("CMMS_CANVAS")
    assert PP.is_core("DTXY_PMXX")
    assert not PP.is_core("SYS_USER")
    assert not PP.is_core("U3D_MODEL")
    assert not PP.is_core("RPT_DAILY")


def test_domain_of_maps_business_domains():
    assert PP.domain_of("FUEL_CB_COALCONTRACT") == "燃煤采购结算"
    assert PP.domain_of("FUEL_CMCS_ASSAY") == "燃料设备与化验"
    assert PP.domain_of("FUEL_MIX_COAL") == "配煤掺烧"
    assert PP.domain_of("FUEL_STG_TMP") == "燃料数据暂存"
    assert PP.domain_of("CMMS_CANVAS") == "组态与设备"
    assert PP.domain_of("DTXY_QYXX") == "供应商与品名"
    assert PP.domain_of("UNKNOWN_T") == ""


def test_asset_payload_uses_table_comment_as_alias():
    p = PP.asset_payload(
        _rec("FUEL_CB_COALBALANCE", "燃煤采购结算主表", [{"name": "ID"}, {"name": "NAME"}])
    )
    assert p["alias"] == "燃煤采购结算主表"
    assert p["domain"] == "燃煤采购结算"
    assert p["object_enabled"] is True
    assert p["object_key_col"] == "ID"
    assert p["object_name_col"] == "NAME"


def test_asset_payload_without_comment_has_empty_alias_and_no_object():
    p = PP.asset_payload(_rec("FUEL_STG_X"))
    assert p["alias"] == ""
    assert p["object_enabled"] is False


def test_column_payloads_take_comments_and_skip_empty_names():
    cols = PP.column_payloads(
        _rec(
            "FUEL_CB_COALBALANCE",
            "",
            [
                {"name": "COALMONEY", "type": "numeric", "comment": "煤款金额", "is_sensitive": False},
                {"name": "OWNERID", "type": "varchar", "comment": "", "is_sensitive": True},
                {"name": "", "comment": "空列应被忽略"},
            ],
        )
    )
    assert [c["column_name"] for c in cols] == ["COALMONEY", "OWNERID"]
    assert cols[0]["description"] == "煤款金额"
    assert cols[0]["sensitive"] is False
    assert cols[1]["sensitive"] is True


def test_infer_links_matches_column_to_table_token():
    tables = ["FUEL_CB_COALBALANCE", "FUEL_CB_COALCONTRACT", "FUEL_CMCS_ASSAY"]
    idx = PP.build_entity_index(tables)
    has_id = dict.fromkeys(tables, True)
    links = PP.infer_links(
        "FUEL_CB_COALBALANCE",
        [{"name": "COALCONTRACTID"}, {"name": "ID"}, {"name": "CREATIONTIME"}],
        idx,
        has_id,
    )
    assert len(links) == 1
    link = links[0]
    assert link["target_object"] == "FUEL_CB_COALCONTRACT"
    assert link["source_field"] == "COALCONTRACTID"
    assert link["target_field"] == "ID"
    assert link["card"] == "many_to_one"
    assert link["join_method"] == "foreign_key"


def test_infer_links_skips_self_reference_and_unknown_target():
    idx = PP.build_entity_index(["FUEL_CB_COALBALANCE"])
    links = PP.infer_links(
        "FUEL_CB_COALBALANCE",
        [{"name": "COALBALANCEID"}, {"name": "UNKNOWNTHINGID"}],
        idx,
        {"FUEL_CB_COALBALANCE": True},
    )
    assert links == []


def test_infer_links_requires_target_to_have_id_and_dedups():
    tables = ["FUEL_CB_COALBALANCE", "FUEL_CB_COALCONTRACT"]
    idx = PP.build_entity_index(tables)
    # 目标表没有 ID 列 → 不建关系
    assert PP.infer_links(
        "FUEL_CB_COALBALANCE", [{"name": "COALCONTRACTID"}], idx,
        {"FUEL_CB_COALBALANCE": True, "FUEL_CB_COALCONTRACT": False},
    ) == []
    # 同一目标多列 → 只保留一条
    links = PP.infer_links(
        "FUEL_CB_COALBALANCE",
        [{"name": "COALCONTRACTID"}, {"name": "COALCONTRACT_ID"}],
        idx, dict.fromkeys(tables, True),
    )
    assert len(links) == 1
