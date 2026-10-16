"""自定义 Python 脚本工具：沙箱校验/执行/超时 + API 测试。"""
import asyncio
import uuid

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.tools_catalog import script_executor as se

VALID_CODE = """
def run(args):
    a = args.get("a", 0)
    b = args.get("b", 0)
    return {"sum": a + b}
"""


def _new_name(prefix: str = "pytest_script") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------- 沙箱：静态校验 ----------

def test_validate_accepts_safe_code():
    """合法脚本（白名单导入 + run 函数）通过校验。"""
    se.validate(
        """
import json, math
def run(args):
    return {"v": math.sqrt(args.get("x", 1)), "j": json.dumps({"a": 1})}
"""
    )


@pytest.mark.parametrize(
    "code",
    [
        "import os\ndef run(args):\n    return {}",
        "def run(args):\n    return __import__('os').listdir('.')",
        "def run(args):\n    return open('/etc/passwd').read()",
        "def run(args):\n    return eval('1+1')",
        "def run(args):\n    return exec('x=1')",
        "def run(args):\n    return args.__class__",
        "def run(args):\n    import io\n    return io.open('/tmp/x')",
    ],
)
def test_validate_rejects_dangerous(code):
    """危险脚本在**创建时**即被拒绝（不是运行时报错）。"""
    with pytest.raises(CustomException):
        se.validate(code)


def test_validate_requires_run_function():
    """缺少 run(args) 入口被拒。"""
    with pytest.raises(CustomException):
        se.validate("def other(args):\n    return {}")


# ---------- 沙箱：执行 ----------

def test_run_returns_dict():
    """合法脚本执行并返回 dict 结果。"""
    out = se.run(VALID_CODE, {"a": 2, "b": 3})
    assert out == {"sum": 5}


def test_run_supports_whitelisted_imports():
    """白名单模块（json/math/re）可用。"""
    out = se.run(
        """
import json, re
def run(args):
    return {"nums": re.findall(r"\\d+", args["text"]), "obj": json.loads('{"k": 1}')}
""",
        {"text": "a1b22"},
    )
    assert out["nums"] == ["1", "22"]
    assert out["obj"] == {"k": 1}


def test_run_timeout_raises():
    """死循环脚本触发超时。"""
    with pytest.raises(CustomException) as ei:
        se.run("def run(args):\n    while True:\n        pass", {}, timeout=1)
    assert "超时" in ei.value.msg


def test_run_wraps_non_dict_result():
    """非 dict 返回值包成 {"result": ...}。"""
    assert se.run("def run(args):\n    return 42", {}) == {"result": 42}


def test_run_runtime_error_wrapped():
    """脚本内部异常转为业务错误，不抛出原始异常类型。"""
    with pytest.raises(CustomException) as ei:
        se.run("def run(args):\n    return 1 / 0", {})
    assert "ZeroDivisionError" in ei.value.msg


# ---------- API ----------

def _create_script_tool(test_client, auth_headers, code: str, **overrides) -> int:
    payload = {
        "name": _new_name(),
        "kind": "script",
        "code": code,
        "timeout": 5,
        "params_schema": {
            "type": "object",
            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        },
        "enabled": True,
    }
    payload.update(overrides)
    r = test_client.post("/api/v1/ai/tools/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_api_create_script_tool_and_run(test_client, auth_headers):
    """API 创建脚本工具 → 试运行返回结果。"""
    tid = _create_script_tool(test_client, auth_headers, VALID_CODE)
    try:
        r = test_client.post(
            f"/api/v1/ai/tools/test-script/{tid}",
            json={"args": {"a": 10, "b": 5}},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["ok"] is True
        assert data["result"] == {"sum": 15}
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/tools/delete", json=[tid], headers=auth_headers
        )


def test_api_rejects_unsafe_script(test_client, auth_headers):
    """含 import os 的脚本创建被拒。"""
    r = test_client.post(
        "/api/v1/ai/tools/create",
        json={"name": _new_name(), "kind": "script", "code": "import os\ndef run(args):\n    return {}"},
        headers=auth_headers,
    )
    assert r.status_code != 200
    assert "不允许导入模块" in r.json()["msg"]


def test_api_test_script_timeout(test_client, auth_headers):
    """超时脚本试运行返回 ok=False 与错误信息。"""
    tid = _create_script_tool(
        test_client, auth_headers, "def run(args):\n    while True:\n        pass", timeout=1
    )
    try:
        r = test_client.post(
            f"/api/v1/ai/tools/test-script/{tid}", json={"args": {}}, headers=auth_headers
        )
        data = r.json()["data"]
        assert data["ok"] is False
        assert "超时" in data["error"]
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/tools/delete", json=[tid], headers=auth_headers
        )


def test_dispatch_script_tool(test_client):
    """dispatch_tool 能按脚本工具名派发执行。"""
    from app.plugin.module_ai.tools_catalog.model import AiToolModel
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    name = _new_name("dispatch")
    tool = AiToolModel(name=name, kind="script", source="script", code=VALID_CODE, timeout=5, enabled=True)

    async def _go():
        return await dispatch_tool(name, {"a": 1, "b": 2}, 1, db_rows={name: tool})

    out = asyncio.run(_go())
    assert out == {"sum": 3}


# ---------- 沙箱：可配置策略（script_sandbox_policies） ----------

def test_validate_policy_ban_lambda():
    """策略 ban_lambda=True 时拒绝含 lambda 的脚本。"""
    code = "def run(args):\n    f = lambda x: x + 1\n    return {'v': f(1)}"
    with pytest.raises(CustomException):
        se.validate(code, policies={"ban_lambda": True})


def test_validate_policy_allow_lambda():
    """策略 ban_lambda=False 时放行 lambda（灵活场景）。"""
    code = "def run(args):\n    f = lambda x: x + 1\n    return {'v': f(1)}"
    se.validate(code, policies={"ban_lambda": False})


def test_validate_policy_ban_class():
    """策略 ban_class=True 时静态拦截 class 定义。"""
    code = "class C:\n    pass\ndef run(args):\n    return {'ok': 1}"
    with pytest.raises(CustomException):
        se.validate(code, policies={"ban_class": True})


def test_validate_policy_ban_dunder_import():
    """策略 ban_dunder_import=True 时拒绝 from X import __y__。"""
    code = "from json import __decoder__\ndef run(args):\n    return 1"
    with pytest.raises(CustomException):
        se.validate(code, policies={"ban_dunder_import": True})


def test_validate_policy_ban_single_underscore_attr():
    """策略 ban_single_underscore_attr=True 时拒绝访问单下划线私有属性。"""
    code = "import re\ndef run(args):\n    return str(re._cache)"
    with pytest.raises(CustomException):
        se.validate(code, policies={"ban_single_underscore_attr": True})


def test_validate_policy_ban_single_underscore_attr_off():
    """策略 ban_single_underscore_attr=False（默认）时放行单下划线属性。"""
    code = "import re\ndef run(args):\n    return str(re._cache)"
    se.validate(code, policies={"ban_single_underscore_attr": False})


def test_validate_policy_ban_yield():
    """策略 ban_yield=True 时拒绝含 yield 的生成器函数。"""
    code = "def run(args):\n    yield 1"
    with pytest.raises(CustomException):
        se.validate(code, policies={"ban_yield": True})


def test_validate_default_policies_reject_lambda():
    """默认策略（未显式传 policies）应安全收紧：拒绝 lambda。"""
    code = "def run(args):\n    f = lambda x: x\n    return 1"
    with pytest.raises(CustomException):
        se.validate(code)


# ---------- script_allowed 全局开关 ----------

def _fake_auth(is_superuser: bool):
    from types import SimpleNamespace

    return SimpleNamespace(user=SimpleNamespace(is_superuser=is_superuser))


def test_can_create_script_tool_when_allowed():
    """script_allowed=True 时任意用户都可创建脚本工具。"""
    from app.plugin.module_ai.tools_catalog.service import can_create_script_tool

    assert can_create_script_tool(_fake_auth(False), script_allowed=True) is True


def test_can_create_script_tool_superuser_when_disabled():
    """script_allowed=False 时超管仍可创建脚本工具。"""
    from app.plugin.module_ai.tools_catalog.service import can_create_script_tool

    assert can_create_script_tool(_fake_auth(True), script_allowed=False) is True


def test_can_create_script_tool_normal_user_when_disabled():
    """script_allowed=False 时普通用户创建脚本工具被拒。"""
    from app.plugin.module_ai.tools_catalog.service import can_create_script_tool

    assert can_create_script_tool(_fake_auth(False), script_allowed=False) is False


# ---------- 平台脚本安全配置解析 ----------

def test_parse_script_allowed():
    """script_allowed 配置值解析：缺省视为允许，常见的真假字符串可识别。"""
    from app.plugin.module_ai.tools_catalog.service import _parse_script_allowed

    assert _parse_script_allowed(None) is True
    assert _parse_script_allowed("true") is True
    assert _parse_script_allowed("1") is True
    assert _parse_script_allowed("on") is True
    assert _parse_script_allowed("false") is False
    assert _parse_script_allowed("0") is False
    assert _parse_script_allowed("False") is False
    assert _parse_script_allowed("") is False


def test_parse_sandbox_policies():
    """script_sandbox_policies 解析：缺省/非法回退默认策略，部分覆盖未指定项用默认。"""
    from app.plugin.module_ai.tools_catalog.service import _parse_sandbox_policies

    assert _parse_sandbox_policies(None) == se.DEFAULT_POLICIES
    assert _parse_sandbox_policies("not json") == se.DEFAULT_POLICIES
    p = _parse_sandbox_policies('{"ban_lambda": false}')
    assert p["ban_lambda"] is False
    assert p["ban_class"] is True  # 未指定的项沿用默认（安全收紧）
    assert p["ban_single_underscore_attr"] is False  # 默认关


def test_script_allowed_switch_blocks_non_superuser(test_client):
    """`script_allowed=false` 时：超管可创建脚本工具，普通用户被拒不误伤超管。"""
    import asyncio
    from types import SimpleNamespace

    from app.plugin.module_ai.tools_catalog.schema import AiToolCreateSchema
    from app.plugin.module_ai.tools_catalog.service import AiToolService

    async def _set_param(key: str, value: str) -> None:
        from sqlalchemy import select

        from app.api.v1.module_system.params.model import ParamsModel
        from app.core.database import async_db_session

        async with async_db_session() as db:
            async with db.begin():
                row = await db.scalar(
                    select(ParamsModel).where(ParamsModel.config_key == key)
                )
                if row:
                    row.config_value = value
                else:
                    db.add(ParamsModel(
                        config_name=key, config_key=key, config_value=value,
                        config_type=True, status="0",
                    ))

    async def _go():
        await _set_param("script_allowed", "false")
        try:
            # 超管豁免：可创建
            sup = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
            await AiToolService.create(
                AiToolCreateSchema(name=_new_name("su"), kind="script", code=VALID_CODE),
                sup,
            )
            # 普通用户：被拦截
            norm = SimpleNamespace(user=SimpleNamespace(id=999, is_superuser=False))
            with pytest.raises(CustomException) as ei:
                await AiToolService.create(
                    AiToolCreateSchema(name=_new_name("normal"), kind="script", code=VALID_CODE),
                    norm,
                )
            assert "禁用脚本工具" in ei.value.msg
        finally:
            await _set_param("script_allowed", "true")

    asyncio.run(_go())
