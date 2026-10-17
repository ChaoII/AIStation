"""大模型辅助筛选规则接口（suggest / parse / classify-advise）测试。

全部 mock 掉 `_llm_structured` / agno `Agent`（避免真实模型/DB），只验证：
- `_extract_json` 去掉代码块包裹与前后杂文；
- `_llm_structured` 的结构化返回与兜底解析（实例 / dict / JSON 文本 / 空内容）；
- 三个接口方法正确消费结构化结果并返回完整 `rules` 结构。
"""
import asyncio
import json
from types import SimpleNamespace

from app.core.exceptions import CustomException
from app.plugin.module_ai.query.llm_schemas import (
    ClassifyAdviseOut,
    FilterRulesOut,
    MetricsTermsOut,
)
from app.plugin.module_ai.query.service import AiQueryService


def _fake_structured(payload: dict):
    """把 `_llm_structured` 换成「按传入 schema 校验 payload 并返回实例」。"""

    async def _inner(cls, prompt, schema, **kwargs):
        return schema.model_validate(payload)

    return classmethod(_inner)


def _fake_agent(content):
    """构造假的 agno Agent：`arun` 固定返回给定 content。"""

    class _A:
        init_kwargs: dict = {}

        def __init__(self, **kwargs):
            _A.init_kwargs = kwargs

        async def arun(self, prompt):
            return SimpleNamespace(content=content)

    return _A


def _patch_llm_env(monkeypatch):
    """屏蔽运行时模型解析与配置读取（不触 DB）。"""

    async def fake_runtime(cls):
        return {"model": "m", "base_url": "http://x/v1", "api_key": "k",
                "extra_headers": None}

    async def fake_cfg(cls):
        return {}

    monkeypatch.setattr(AiQueryService, "_get_runtime", classmethod(fake_runtime))
    monkeypatch.setattr(AiQueryService, "_cfg", classmethod(fake_cfg))
    monkeypatch.setattr(AiQueryService, "_cfg_int",
                        classmethod(lambda cls, cfg, key, default=90: 30))


async def _fake_schema(ds, included_only=False):
    return [{"table": "SYS_A", "comment": "", "columns": [{"name": "created_time"}]},
            {"table": "biz_t", "comment": "", "columns": [{"name": "coal"}]}]


async def _fake_load(ds):
    class _D:
        filter_rules = None

    return _D()


# ---------------------------- _extract_json ---------------------------- #

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


# ---------------------------- _llm_structured ---------------------------- #

def test_llm_structured_parses_json_text(monkeypatch):
    """网关不回原生结构（content 为 JSON 文本）时，兜底解析为 schema 实例。"""
    _patch_llm_env(monkeypatch)
    monkeypatch.setattr("agno.agent.Agent",
                        _fake_agent(json.dumps({"metrics": [{"name": "总数"}]})))
    out = asyncio.run(AiQueryService._llm_structured("p", MetricsTermsOut))
    assert isinstance(out, MetricsTermsOut)
    assert out.metrics[0].name == "总数"


def test_llm_structured_accepts_dict_content(monkeypatch):
    """content 已是 dict 时直接校验，不再走 JSON 文本解析。"""
    _patch_llm_env(monkeypatch)
    monkeypatch.setattr("agno.agent.Agent",
                        _fake_agent({"terms": [{"term": "销量"}]}))
    out = asyncio.run(AiQueryService._llm_structured("p", MetricsTermsOut))
    assert out.terms[0].term == "销量"


def test_llm_structured_empty_content_raises(monkeypatch):
    """实测推理型模型可能把 token 预算全烧在思考上 → content 为空，应给可读错误。"""
    _patch_llm_env(monkeypatch)
    monkeypatch.setattr("agno.agent.Agent", _fake_agent("   "))
    try:
        asyncio.run(AiQueryService._llm_structured("p", MetricsTermsOut))
    except CustomException as e:
        assert "未返回结构化结果" in e.msg
    else:
        raise AssertionError("应抛出 CustomException")


def test_llm_structured_invalid_content_raises(monkeypatch):
    """content 既不是实例/dict，也不是合法 JSON 文本 → 可读错误。"""
    _patch_llm_env(monkeypatch)
    monkeypatch.setattr("agno.agent.Agent", _fake_agent("这不是 JSON"))
    try:
        asyncio.run(AiQueryService._llm_structured("p", MetricsTermsOut))
    except CustomException as e:
        assert "结构不完整" in e.msg
    else:
        raise AssertionError("应抛出 CustomException")


# ---------------------------- 三个接口方法 ---------------------------- #

def test_suggest_filter_rules(monkeypatch):
    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", _fake_load)
    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", _fake_schema)
    rules_payload = {
        "enabled": True,
        "system_table": {"prefixes": ["SYS_"], "keywords": [], "exact": [], "regex": ""},
        "audit_fields": ["created_time"],
    }
    monkeypatch.setattr(AiQueryService, "_llm_structured",
                        _fake_structured({"rules": rules_payload}))
    out = asyncio.run(AiQueryService.suggest_filter_rules(4))
    assert out["rules"]["system_table"]["prefixes"] == ["SYS_"]
    assert out["rules"]["audit_fields"] == ["created_time"]


def test_parse_filter_rules(monkeypatch):
    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", _fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_structured", _fake_structured({
        "rules": {"enabled": True,
                  "system_table": {"prefixes": ["SYS_"], "keywords": [],
                                   "exact": [], "regex": ""},
                  "audit_fields": ["created_time"]}}))
    out = asyncio.run(AiQueryService.parse_filter_rules(4, "把 SYS_ 前缀当系统表"))
    assert out["rules"]["system_table"]["prefixes"] == ["SYS_"]


def test_classify_advise(monkeypatch):
    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", _fake_load)
    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", _fake_schema)
    monkeypatch.setattr(AiQueryService, "_llm_structured", _fake_structured({
        "system_suggest": [{"name": "SYS_A", "reason": "疑似系统表"}],
        "audit_suggest": [{"name": "created_time", "reason": "审计字段"}]}))
    out = asyncio.run(AiQueryService.classify_advise(4))
    assert out["system_suggest"][0]["name"] == "SYS_A"
    assert out["audit_suggest"][0]["reason"] == "审计字段"


# ---------------------------- schema 默认值 ---------------------------- #

def test_filter_rules_out_defaults_on_missing_keys():
    """模型漏字段时取默认值（比抛错更可用），不丢整体结构。"""
    out = FilterRulesOut.model_validate({})
    assert out.rules.enabled is True
    assert out.rules.system_table.prefixes == []
    assert out.rules.audit_fields == []


def test_classify_advise_out_defaults_on_missing_keys():
    out = ClassifyAdviseOut.model_validate({"system_suggest": [{"name": "T"}]})
    assert out.system_suggest[0].name == "T"
    assert out.system_suggest[0].reason == ""
    assert out.audit_suggest == []
