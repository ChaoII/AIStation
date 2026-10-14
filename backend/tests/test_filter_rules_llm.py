"""Task6：大模型辅助筛选规则接口（suggest / parse / classify-advise）测试。

全部 mock 掉 `_llm_json`（避免真实模型/DB），只验证：
- `_extract_json` 去掉代码块包裹；
- 三个接口方法把 `_llm_json` 的 JSON 产出正确解析并返回完整 `rules` 结构。
"""
import asyncio
import json

from app.plugin.module_ai.query.filtering import DEFAULT_FILTER_RULES
from app.plugin.module_ai.query.service import AiQueryService


def _fake_llm(payload: dict):
    async def _inner(cls, prompt, temperature=0.2):
        return json.dumps(payload, ensure_ascii=False)

    return classmethod(_inner)


def test_extract_json_strips_fence():
    assert AiQueryService._extract_json("```json\n{\"a\":1}\n```") == "{\"a\":1}"
    assert AiQueryService._extract_json("{\"a\":1}") == "{\"a\":1}"


def test_extract_json_mixed_text():
    """模型在 JSON 前后附带了自然语言解释（无围栏/无换行）时，仍能提取出平衡的 JSON 对象。"""
    assert (
        AiQueryService._extract_json(
            '根据规则判断，解释如下 {"rules": {"enabled": true}} 以上为结果'
        )
        == '{"rules": {"enabled": true}}'
    )
    assert AiQueryService._extract_json("前缀说明 正文 {\"a\": 1} 结尾") == '{"a": 1}'


def test_extract_json_skips_braces_in_strings():
    """提取平衡 JSON 时应跳过字符串字面量内的花括号与转义。"""
    assert (
        AiQueryService._extract_json('{"a": "含 } 的字符串", "b": 2} 后文')
        == '{"a": "含 } 的字符串", "b": 2}'
    )


def test_suggest_filter_rules(monkeypatch):
    async def fake_load(ds):
        class D:
            pass

        d = D()
        d.filter_rules = None
        return d

    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(ds, included_only=False):
        return [{"table": "SYS_A", "comment": "", "columns": [{"name": "created_time"}]},
                {"table": "biz_t", "comment": "", "columns": [{"name": "coal"}]}]

    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    rules_payload = {"enabled": True, "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": ""},
                     "audit_fields": ["created_time"]}
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({"rules": rules_payload}))
    out = asyncio.run(AiQueryService.suggest_filter_rules(4))
    assert out["rules"]["system_table"]["prefixes"] == ["SYS_"]
    assert out["rules"]["audit_fields"] == ["created_time"]


def test_parse_filter_rules(monkeypatch):
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({"rules": {"enabled": True,
        "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": ""}, "audit_fields": ["created_time"]}}))
    out = asyncio.run(AiQueryService.parse_filter_rules(4, "把 SYS_ 前缀当系统表，created_time 当审计"))
    assert out["rules"]["system_table"]["prefixes"] == ["SYS_"]


def test_classify_advise(monkeypatch):
    async def fake_load(ds):
        class D:
            pass

        d = D()
        d.filter_rules = None
        return d

    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(ds, included_only=False):
        return [{"table": "TMP_A", "comment": "", "columns": [{"name": "deleted_time"}]}]

    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({
        "system_suggest": [{"name": "TMP_A", "reason": "疑似临时表"}],
        "audit_suggest": [{"name": "deleted_time", "reason": "审计字段"}]}))
    out = asyncio.run(AiQueryService.classify_advise(4))
    assert out["system_suggest"][0]["name"] == "TMP_A"
    assert out["audit_suggest"][0]["reason"] == "审计字段"


def test_suggest_missing_rules_key_raises(monkeypatch):
    """模型返回合法 JSON 但缺 `rules` 键时，应抛可读 CustomException 而非 KeyError。"""
    from app.core.exceptions import CustomException

    async def fake_load(ds):
        class D:
            pass

        d = D()
        d.filter_rules = None
        return d

    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(ds, included_only=False):
        return [{"table": "SYS_A", "comment": "", "columns": [{"name": "created_time"}]}]

    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({"enabled": True}))
    try:
        asyncio.run(AiQueryService.suggest_filter_rules(4))
    except CustomException as e:
        assert "结构不完整" in e.msg
    else:
        raise AssertionError("应抛出 CustomException")


def test_classify_advise_missing_keys_raises(monkeypatch):
    """classify_advise 缺 `system_suggest`/`audit_suggest` 键时应抛可读 CustomException。"""
    from app.core.exceptions import CustomException

    async def fake_load(ds):
        class D:
            pass

        d = D()
        d.filter_rules = None
        return d

    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(ds, included_only=False):
        return [{"table": "TMP_A", "comment": "", "columns": [{"name": "deleted_time"}]}]

    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({"system_suggest": []}))
    try:
        asyncio.run(AiQueryService.classify_advise(4))
    except CustomException as e:
        assert "结构不完整" in e.msg
    else:
        raise AssertionError("应抛出 CustomException")


def test_suggest_rules_not_dict_raises(monkeypatch):
    """`rules` 键存在但值不是 dict 时，应抛可读 CustomException 而非下游崩溃。"""
    from app.core.exceptions import CustomException

    async def fake_load(ds):
        class D:
            pass

        d = D()
        d.filter_rules = None
        return d

    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(ds, included_only=False):
        return [{"table": "SYS_A", "comment": "", "columns": [{"name": "created_time"}]}]

    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({"rules": ["不是 dict"]}))
    try:
        asyncio.run(AiQueryService.suggest_filter_rules(4))
    except CustomException as e:
        assert "rules 类型错误" in e.msg
    else:
        raise AssertionError("应抛出 CustomException")


def test_classify_advise_suggest_not_list_raises(monkeypatch):
    """`audit_suggest` 键存在但值不是 list 时，应抛可读 CustomException。"""
    from app.core.exceptions import CustomException

    async def fake_load(ds):
        class D:
            pass

        d = D()
        d.filter_rules = None
        return d

    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(ds, included_only=False):
        return [{"table": "TMP_A", "comment": "", "columns": [{"name": "deleted_time"}]}]

    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_json", _fake_llm({
        "system_suggest": [], "audit_suggest": {"不是": "list"}}))
    try:
        asyncio.run(AiQueryService.classify_advise(4))
    except CustomException as e:
        assert "audit_suggest 类型错误" in e.msg
    else:
        raise AssertionError("应抛出 CustomException")
