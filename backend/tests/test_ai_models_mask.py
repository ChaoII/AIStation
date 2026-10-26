"""模型/提供商 `extra_headers` 脱敏：列表/详情只回显掩码，请求仍用真实值。"""
from app.plugin.module_ai.models.service import _mask_headers, _to_dict, build_headers
from app.plugin.module_ai.models.model import AiModelModel


def test_mask_headers_none_and_empty():
    assert _mask_headers(None) is None
    assert _mask_headers({}) == {}


def test_mask_headers_masks_all_values():
    out = _mask_headers({"Authorization": "Bearer sk-secret", "x-api-key": "abc123"})
    assert out == {"Authorization": "****", "x-api-key": "****"}


def test_to_dict_masks_extra_headers_but_build_headers_uses_real():
    m = AiModelModel(
        name="gpt-x", provider="openai", usage="chat",
        base_url="https://api.openai.com", model="gpt-4o",
        extra_headers={"Authorization": "Bearer secret-token"},
        api_key="sk-abcdef1234567890", enabled=True, is_default=False,
    )
    d = _to_dict(m)
    # 响应中的 extra_headers 被掩码
    assert d["extra_headers"] == {"Authorization": "****"}
    # api_key 以掩码回显
    assert d["api_key_masked"] == "sk-a****7890"
    # build_headers 仍使用真实值（供请求头构造）
    h = build_headers("https://api.openai.com", m.extra_headers, session_id="s")
    assert h["Authorization"] == "Bearer secret-token"
