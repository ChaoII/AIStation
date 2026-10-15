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
