"""问数提示词的时间口径 + 本体能力清单的回归护栏。

两个真实 bug（2026-11-10 燃料数据实测）：
1. 「上个月」被模型写成 ``>= 本月1日``（data 跨月就答错）→ 现在提示词里写死各口径；
2. ``ontology_catalog_text`` 先截断前 N 个对象**再**过滤「有函数/动作」，
   前几个对象没能力时整段返回空 → Agent 以为没有本体能力（实测 catalog(8) 长度 0）。
"""
import asyncio

from app.plugin.module_ai.ontology import agent_tools
from app.plugin.module_ai.ontology import service as ont_service
from app.plugin.module_ai.query.dialect import DIALECTS, time_rules


def test_time_rules_postgres_canonical():
    text = time_rules(DIALECTS["postgres"])
    assert "上个月" in text
    assert "date_trunc('month', CURRENT_DATE - INTERVAL '1 month')" in text
    # 明确禁止把「上个月」写成本月
    assert "不是" in text and "本月1日" in text


def test_time_rules_other_dialects_use_own_functions():
    mysql = time_rules(DIALECTS["mysql"])
    assert "DATE_SUB(CURDATE(), INTERVAL 1 MONTH)" in mysql
    sqlite = time_rules(DIALECTS["sqlite"])
    assert "date('now','-1 month','start of month')" in sqlite


def test_system_prompt_contains_time_rules():
    from app.plugin.module_ai.query.dialect import build_system_prompt

    sp = build_system_prompt(DIALECTS["postgres"], ["- 规则1\n"], "表：t(a)")
    assert "时间口径" in sp and "上个月" in sp


def test_ontology_catalog_filters_before_truncating(monkeypatch):
    """前 N 个对象没有能力时，也要继续往后找（而不是返回空）。"""
    objs = [{"code": f"plain_{i}", "name": f"无能力{i}"} for i in range(5)]
    objs += [{"code": "video_cameras", "name": "摄像头"}]

    async def fake_list_objects():
        return objs

    async def fake_list_functions(code):
        return [{"code": "cam_online_rate", "name": "在线率"}] if code == "video_cameras" else []

    async def fake_list_actions(code):
        return []

    monkeypatch.setattr(ont_service, "list_objects", fake_list_objects)
    monkeypatch.setattr(ont_service, "list_functions", fake_list_functions)
    monkeypatch.setattr(ont_service, "list_actions", fake_list_actions)

    text = asyncio.run(agent_tools.ontology_catalog_text(3))
    assert text, "前 5 个对象没能力时不应整段为空"
    assert "video_cameras" in text
