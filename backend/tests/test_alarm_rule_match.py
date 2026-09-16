"""告警规则匹配测试。"""
from app.api.v1.module_video.inference.service import pick_alarm_rule


class _Rule:
    def __init__(self, alarm_type):
        self.alarm_type = alarm_type


def test_pick_alarm_rule_prefers_exact_type():
    rules = [_Rule("OTHER"), _Rule("INTRUSION")]
    assert pick_alarm_rule(rules, "INTRUSION").alarm_type == "INTRUSION"


def test_pick_alarm_rule_falls_back_to_first():
    rules = [_Rule("OTHER"), _Rule("SECOND")]
    assert pick_alarm_rule(rules, "INTRUSION").alarm_type == "OTHER"


def test_pick_alarm_rule_empty():
    assert pick_alarm_rule([], "X") is None
