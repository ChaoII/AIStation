"""市场快照脱敏：``_sanitize_payload`` 防提交者明文密钥经 payload 泄露（纯逻辑，PYTEST_NO_APP=1 可跑）。

覆盖点：
- 敏感键（api_key/token/secret/password 等）值清空；
- headers/env 整包凭证束：所有值清空、保留键名；
- 非敏感字段（url/method/params_schema/code/description/name/enabled/transport/auth_type）保留；
- 嵌套 dict/list 递归；
- args 里疑似令牌串清空、结构性启动参数保留；
- 插件 key（标识字段）不被误伤；
- None 原样返回；幂等。
"""

from app.plugin.module_ai.market.service import _sanitize_payload


def test_sensitive_keys_blanked():
    """config 中 api_key/token/secret/password 值清空，非敏感值保留。"""
    payload = {
        "name": "Web Search",
        "config": {
            "api_key": "sk-abc123456",
            "access_token": "ghp_0123456789abcdefghij",
            "secret": "s3cr3t",
            "password": "p@ss",
            "temperature": 0.7,
            "model": "gpt-4o",
        },
    }
    out = _sanitize_payload(payload)
    cfg = out["config"]
    assert cfg["api_key"] == ""
    assert cfg["access_token"] == ""
    assert cfg["secret"] == ""
    assert cfg["password"] == ""
    assert cfg["temperature"] == 0.7
    assert cfg["model"] == "gpt-4o"
    assert out["name"] == "Web Search"


def test_headers_env_bundle_blanked():
    """headers/env 整包凭证束：所有值清空、保留键名。"""
    payload = _sanitize_payload(
        {
            "name": "GitHub",
            "transport": "streamable-http",
            "url": "https://api.github.com/mcp",
            "headers": {"Authorization": "Bearer ghp_1234567890abcdefghij", "X-Custom": "1"},
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_1234567890abcdefghij"},
        }
    )
    assert payload["headers"] == {"Authorization": "", "X-Custom": ""}
    assert payload["env"] == {"GITHUB_PERSONAL_ACCESS_TOKEN": ""}
    # 非敏感字段保留
    assert payload["url"] == "https://api.github.com/mcp"
    assert payload["transport"] == "streamable-http"


def test_nonsensitive_fields_preserved():
    """url/method/params_schema/code/description/name/enabled 等原样保留。"""
    payload = {
        "name": "HTTP Tool",
        "kind": "http",
        "method": "POST",
        "url": "https://api.example.com/v1/search",
        "params_schema": [{"name": "q", "type": "string"}],
        "code": "",
        "timeout": 30,
        "enabled": True,
        "description": "一个示例工具",
        "headers": {},
        "config": {},
    }
    out = _sanitize_payload(payload)
    assert out["url"] == "https://api.example.com/v1/search"
    assert out["method"] == "POST"
    assert out["params_schema"] == [{"name": "q", "type": "string"}]
    assert out["code"] == ""
    assert out["timeout"] == 30
    assert out["enabled"] is True
    assert out["description"] == "一个示例工具"
    assert out["headers"] == {}
    assert out["config"] == {}


def test_nested_dict_and_list_recursive():
    """嵌套 dict/list 内敏感键也被清空。"""
    out = _sanitize_payload(
        {
            "config": {
                "endpoint": "https://api.example.com",
                "auth": {"api_key": "sk-xyz", "region": "cn"},
                "retry": [{"token": "t-1"}, {"ok": 1}],
            }
        }
    )
    assert out["config"]["endpoint"] == "https://api.example.com"
    assert out["config"]["auth"]["api_key"] == ""
    assert out["config"]["auth"]["region"] == "cn"
    assert out["config"]["retry"][0]["token"] == ""
    assert out["config"]["retry"][1]["ok"] == 1


def test_args_token_strings_blanked_structural_kept():
    """args 里疑似令牌串清空，结构性启动参数保留。"""
    out = _sanitize_payload(
        {
            "name": "Lark",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "lark_mcp", "-a", "<你的AppID>", "-s", "sk-abcdefghijklmnop"],
        }
    )
    assert out["args"][0] == "-m"
    assert out["args"][1] == "lark_mcp"
    assert out["args"][2] == "-a"
    assert out["args"][3] == ""  # 占位符清空
    assert out["args"][4] == "-s"
    assert out["args"][5] == ""  # sk- 令牌清空


def test_plugin_key_not_blanked():
    """插件 key 是标识字段（非凭证），不被误伤。"""
    out = _sanitize_payload(
        {
            "key": "web_search",
            "label": "Web Search",
            "kind": "builtin",
            "config": {"api_key": "sk-xxx"},
            "config_schema": [{"name": "api_key", "type": "string"}],
            "enabled": True,
        }
    )
    assert out["key"] == "web_search"
    assert out["label"] == "Web Search"
    assert out["config"]["api_key"] == ""
    # config_schema 里的字段名不是敏感值，保留
    assert out["config_schema"] == [{"name": "api_key", "type": "string"}]


def test_auth_type_and_boolean_not_blanked():
    """auth_type 是枚举非凭证，enabled/auth_type 保留。"""
    out = _sanitize_payload(
        {"auth_type": "bearer", "enabled": True, "executor_ready": False}
    )
    assert out["auth_type"] == "bearer"
    assert out["enabled"] is True
    assert out["executor_ready"] is False


def test_none_passthrough_and_idempotent():
    """None 原样返回；对已脱敏数据幂等。"""
    assert _sanitize_payload(None) is None
    first = _sanitize_payload(
        {
            "config": {"api_key": "sk-123"},
            "headers": {"Authorization": "Bearer sk-123"},
            "args": ["-s", "sk-abcdefghijklmnop"],
        }
    )
    second = _sanitize_payload(first)
    assert second == first
    assert second["config"] == {"api_key": ""}
