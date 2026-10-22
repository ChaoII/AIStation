# tests/test_embed_sdk.py
"""SDK 静态端点：公开可取、零凭证、契约标记齐全。"""
import pathlib

import pytest

API = "/api/v1"


def test_sdk_js_served_publicly_without_secret(test_client):
    r = test_client.get(f"{API}/ai/embed/sdk.js")
    assert r.status_code == 200, r.text
    assert "javascript" in r.headers["content-type"]
    text = r.text
    # 契约标记：入口、事件、下行命令
    for marker in ("AiAssistant", "init", "setToken", "sendMessage", "ai-host", "ai-embed"):
        assert marker in text, marker
    # 只允许「安全警示语」里出现 appkey 字样，不得出现任何真实/示例密钥或凭证头
    assert "stew7" not in text
    assert "Authorization" not in text


def test_sdk_destroy_lifecycle_behavior():
    """SDK 生命周期（node 执行行为测试）：init → 派发 → destroy → 幂等 → 销毁后 API 安全。"""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用：跳过 SDK 行为测试（静态断言仍覆盖）")
    fixture = str(pathlib.Path(__file__).parent / "fixtures" / "embed_sdk_behavior.js")
    proc = subprocess.run([node, fixture], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"SDK 行为测试失败：\n{proc.stdout}\n{proc.stderr}"
    assert "SDK_LIFECYCLE_OK" in proc.stdout, proc.stdout


def test_sdk_destroy_lifecycle_static():
    """静态兜底：销毁语义的关键语句必须在源码里（node 不可用时也能挡住回归）。"""
    import pathlib as _pathlib

    js = (
        _pathlib.Path(__file__).parent.parent
        / "app" / "plugin" / "module_ai" / "develop" / "static" / "ai-assistant.js"
    ).read_text(encoding="utf-8")
    assert "global.removeEventListener(\"message\", onMessage)" in js
    assert "destroyed = true" in js
    assert "handlers = {}" in js, "destroy 应释放宿主回调引用"
    assert js.count("if (destroyed") >= 4, "setToken/sendMessage/resize/destroy 应有 4 处守卫"
