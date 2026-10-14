"""决策数据与决策谱系的纯函数单测。

对照官方 why-ontology：
· 决策数据 = 上下文 + 评估过的不同选项 + 承诺选择的下游影响
· 决策谱系 = 何时 / 基于哪个数据版本 / 经由哪个应用
"""
from datetime import datetime
from decimal import Decimal

from app.plugin.module_ai.ontology import decision as D


# ---------------------------------------------------------------------------
# 安全序列化（决策依据里存的是对象属性快照）
# ---------------------------------------------------------------------------
def test_json_safe_handles_datetime_and_decimal():
    """快照里出现 datetime/Decimal 时不能让 json.dumps 抛错。"""
    payload = {
        "t": datetime(2026, 10, 9, 12, 30, 0),
        "d": Decimal("3.14"),
        "b": b"abc",
        "nested": {"when": datetime(2026, 1, 1)},
        "list": [Decimal("1"), datetime(2026, 2, 2)],
    }
    s = D._j(payload)
    assert "2026-10-09 12:30:00" in s
    assert "3.14" in s
    assert "abc" in s
    assert "2026-01-01" in s


def test_json_safe_plain_values():
    assert D._j({}) == "{}"
    assert D._j({"a": 1}) == '{"a": 1}'
    # 中文不转义
    assert "决策" in D._j({"t": "决策"})


# ---------------------------------------------------------------------------
# 决策编码
# ---------------------------------------------------------------------------
def test_derive_code_from_ascii_title():
    assert D.derive_decision_code("Replace Camera 12") == "dec_replace_camera_12"
    assert D.derive_decision_code("a-b_c") == "dec_a_b_c"


def test_derive_code_from_chinese_title_is_nonempty_and_stable():
    """中文标题推不出 ASCII，但要给出确定性的非空编码。"""
    c1 = D.derive_decision_code("东门摄像机反复离线")
    c2 = D.derive_decision_code("东门摄像机反复离线")
    assert c1.startswith("dec_")
    # 同一标题在同一秒内应一致（摘要相同）
    assert c1.split("_")[1] == c2.split("_")[1]
    # 不同标题摘要不同
    assert D.derive_decision_code("另一个决策").split("_")[1] != c1.split("_")[1]


def test_code_regex_accepts_generated_codes():
    for t in ("Replace Camera 12", "东门摄像机反复离线", "x"):
        assert D._CODE_RE.match(D.derive_decision_code(t)), D.derive_decision_code(t)


# ---------------------------------------------------------------------------
# 谱系统计
# ---------------------------------------------------------------------------
def _node(title, up=None, down=None, evidence=0, impacts=0):
    return {
        "title": title, "upstream": up or [], "downstream": down or [],
        "evidence": [{}] * evidence, "impacts": [{}] * impacts,
    }


def test_lineage_summary_counts_recursively():
    leaf = _node("上游决策", evidence=2)
    down = _node("下游决策", evidence=1)
    root = _node("根决策", up=[leaf], down=[down], evidence=3, impacts=2)
    s = D._lineage_summary(root)
    assert s["evidence"] == 3
    assert s["impacts"] == 2
    assert s["upstream_decisions"] == 1
    assert s["downstream_decisions"] == 1


def test_lineage_summary_deep_chain():
    lvl3 = _node("三层")
    lvl2 = _node("二层", down=[lvl3])
    lvl1 = _node("一层", down=[lvl2])
    root = _node("根", down=[lvl1])
    s = D._lineage_summary(root)
    assert s["downstream_decisions"] == 3


def test_lineage_summary_on_bare_node():
    s = D._lineage_summary(_node("孤立决策"))
    assert s == {"evidence": 0, "impacts": 0,
                 "upstream_decisions": 0, "downstream_decisions": 0}


# ---------------------------------------------------------------------------
# 常量与标签
# ---------------------------------------------------------------------------
def test_status_and_channel_labels_cover_all_values():
    for s in D.ONT_DECISION_STATUS:
        assert s in D.ONT_DECISION_STATUS_LABEL, s
    for c in D.ONT_DECISION_CHANNELS:
        assert c in D.ONT_CHANNEL_LABEL, c
    for k in D.ONT_EVIDENCE_KINDS:
        assert k in D.ONT_EVIDENCE_LABEL, k
    for k in D.ONT_IMPACT_KINDS:
        assert k in D.ONT_IMPACT_LABEL, k


def test_decision_object_type_props_cover_key_columns():
    codes = {c for c, _, _, _ in D.DECISION_PROPS}
    for must in ("code", "title", "status", "object_code", "action_code",
                 "rationale", "data_version", "channel", "made_by", "made_at", "outcome"):
        assert must in codes, must
    # 恰好一个标题键
    assert sum(1 for *_, is_title in D.DECISION_PROPS if is_title) == 1


def test_now_format():
    s = D._now()
    assert len(s) == 19 and s[4] == "-" and s[13] == ":"
