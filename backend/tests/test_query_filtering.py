from app.plugin.module_ai.query.filtering import (
    classify_fields,
    classify_tables,
    is_audit_field,
    is_system_table,
)


def test_system_table_by_prefix(): assert is_system_table("SYS_USER")
def test_system_table_case(): assert is_system_table("sys_user")
def test_system_table_by_keyword(): assert is_system_table("FUEL_CMCS_X_BAK")
def test_system_table_by_exact(): assert is_system_table("alembic_version")
def test_business_table(): assert not is_system_table("video_cameras")
def test_audit_field(): assert is_audit_field("created_time")
def test_business_field(): assert not is_audit_field("coal_amount")


def test_classify_tables_prefix_reason():
    r = classify_tables(["SYS_USER", "video_cameras"])
    assert r[0]["is_system"] is True and r[0]["reason"] == "前缀 SYS_"
    assert r[1]["is_system"] is False and r[1]["reason"] == ""


def test_classify_tables_keyword_exact_regex():
    rules = {"enabled": True, "system_table": {"prefixes": [], "keywords": ["_BAK"],
             "exact": ["alembic_version"], "regex": "^TMP_"}, "audit_fields": []}
    r2 = classify_tables(["T_A_BAK", "alembic_version", "TMP_X", "ok"], rules)
    assert r2[0]["reason"] == "关键词 _BAK"
    assert r2[1]["reason"] == "精确表名 alembic_version"
    assert r2[2]["reason"] == "正则 ^TMP_"
    assert r2[3]["is_system"] is False


def test_classify_disabled_passes_all():
    rules = {"enabled": False, "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": ""}, "audit_fields": []}
    assert classify_tables(["SYS_USER"], rules)[0]["is_system"] is False


def test_classify_case_insensitive_and_bad_regex():
    rules = {"enabled": True, "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": "["}, "audit_fields": []}
    assert classify_tables(["sys_user"], rules)[0]["is_system"] is True
    assert classify_tables(["sys_user_bak_x"], rules)[0]["is_system"] is True  # 非法正则被跳过不抛异常


def test_classify_invalid_regex_isolation():
    """非法正则应被跳过（不抛异常、不误命中），且仅靠非法正则时表名判为业务表。

    与上方用例不同：此处 prefixes/keywords/exact 全空，表名 ``tmp_x`` 只可能因
    非法正则 ``[`` 命中——`re.error` 被跳过后应返回 ``is_system=False``、``reason=""``，
    真正覆盖 ``except re.error`` 路径。
    """
    rules = {"enabled": True, "system_table": {"prefixes": [], "keywords": [], "exact": [], "regex": "["}, "audit_fields": []}
    r = classify_tables(["tmp_x"], rules)[0]
    assert r["is_system"] is False
    assert r["reason"] == ""


def test_classify_fields_reason():
    r = classify_fields(["created_time", "coal_amount"])
    assert r[0]["is_audit"] is True and r[0]["reason"] == "审计字段 created_time"
    assert r[1]["is_audit"] is False and r[1]["reason"] == ""
