"""函数引擎单测：表达式 / 关联聚合 / 外部服务 / 模型 四种形态。

对照官方 functions 文档的语义：类型化入参、对象上下文、外部来源、模型调用。
"""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.plugin.module_ai.ontology import function_engine as F


# ---------------------------------------------------------------------------
# 受控表达式求值
# ---------------------------------------------------------------------------
def test_safe_eval_arithmetic_and_compare():
    assert F.safe_eval("a * b - c", {"a": 2, "b": 3, "c": 1}) == 5
    assert F.safe_eval("price > 10", {"price": 12}) is True
    assert F.safe_eval("x >= 1 and y <= 2", {"x": 1, "y": 2}) is True
    assert F.safe_eval("1 if flag else 2", {"flag": False}) == 2


def test_safe_eval_builtins():
    assert F.safe_eval("max(a, b)", {"a": 3, "b": 7}) == 7
    assert F.safe_eval("round(x, 2)", {"x": 1.2345}) == 1.23
    assert F.safe_eval("concat(a, '-', b)", {"a": "x", "b": "y"}) == "x-y"
    assert F.safe_eval("coalesce(a, b, 'z')", {"a": None, "b": "", }) == "z"
    assert F.safe_eval("iif(a > 1, 'big', 'small')", {"a": 5}) == "big"
    assert F.safe_eval("percent(3, 4)", {}) == 75.0
    assert F.safe_eval("upper(trim(s))", {"s": " ab "}) == "AB"
    assert F.safe_eval("contains(name, 'cam')", {"name": "my_cam_1"}) is True
    assert F.safe_eval(r"regex_extract(s, '\d+')", {"s": "abc123"}) == "123"
    assert F.safe_eval("json_get(payload, 'data.total')",
                       {"payload": json.dumps({"data": {"total": 5}})}) == 5


def test_safe_eval_rejects_dangerous_input():
    # 未知变量
    with pytest.raises(F.ExprError):
        F.safe_eval("nope + 1", {})
    # 未知函数
    with pytest.raises(F.ExprError):
        F.safe_eval("__import__('os')", {})
    # 属性访问（不许）
    with pytest.raises(F.ExprError):
        F.safe_eval("a.b", {"a": 1})
    # 把内置函数当变量用要给出可读提示
    with pytest.raises(F.ExprError) as e:
        F.safe_eval("max", {})
    assert "函数" in str(e.value)
    # 关键字参数不支持
    with pytest.raises(F.ExprError):
        F.safe_eval("round(number=x)", {"x": 1})


def test_expr_vars_and_calls():
    assert F.expr_vars("a + b * max(c, 1)") == ["a", "b", "c"]
    assert F.expr_calls("max(a, min(b, c))") == ["max", "min"]
    assert F.expr_vars("((bad") == []


# ---------------------------------------------------------------------------
# 取值路径与模板
# ---------------------------------------------------------------------------
def test_dig_paths():
    obj = {"data": {"items": [{"name": "a"}, {"name": "b"}]}}
    assert F.dig(obj, "data.items[1].name") == "b"
    assert F.dig(obj, "data.items[9].name") is None
    assert F.dig(obj, "") == obj
    assert F.dig({"a": 1}, None) == {"a": 1}


def test_interp_templates():
    ctx = F.FunctionContext(user_id=7, user_name="张三")
    assert F.interp("{{a}}/{{当前用户}}", {"a": "x"}, ctx) == "x/张三"
    assert F.interp("x{{missing}}y", {}, ctx) == "xy"


# ---------------------------------------------------------------------------
# 输入准备
# ---------------------------------------------------------------------------
def test_prepare_inputs_sources():
    fn = {"parameters": [
        {"key": "a", "source": "parameter", "required": True},
        {"key": "b", "source": "static", "default": 10},
        {"key": "who", "source": "current_user"},
        {"key": "when", "source": "current_time"},
        {"key": "status", "source": "object_property", "object_property": "status"},
    ]}
    ctx = F.FunctionContext(object_code="cams", object_key="1",
                            user_id=9, user_name="李四",
                            object_props={"status": "ONLINE"})
    v = asyncio.run(F.prepare_inputs(fn, {"a": 1}, ctx))
    assert v["a"] == 1
    assert v["b"] == 10
    assert v["who"] == "李四"
    assert v["status"] == "ONLINE"
    assert v["when"]
    # 未声明但传入的参数也带上（兼容只写 expr 的老函数）
    v2 = asyncio.run(F.prepare_inputs({"parameters": []}, {"legacy": 3}, ctx))
    assert v2["legacy"] == 3


def test_prepare_inputs_coerces_by_declared_type():
    """声明了类型就转换：界面/Agent 传进来的都是字符串，不转换算不了数。"""
    fn = {"parameters": [
        {"key": "n", "type": "number", "source": "parameter"},
        {"key": "i", "type": "integer", "source": "parameter"},
        {"key": "b", "type": "boolean", "source": "parameter"},
        {"key": "s", "type": "string", "source": "parameter"},
    ]}
    v = asyncio.run(F.prepare_inputs(
        fn, {"n": "8", "i": "3", "b": "true", "s": 5}, F.FunctionContext()))
    assert v["n"] == 8 and isinstance(v["n"], int)
    assert v["i"] == 3 and isinstance(v["i"], int)
    assert v["b"] is True
    assert v["s"] == "5"
    # 小数保持小数
    v2 = asyncio.run(F.prepare_inputs(fn, {"n": "8.5"}, F.FunctionContext()))
    assert v2["n"] == 8.5


def test_prepare_inputs_passes_through_when_type_undeclared():
    """未声明类型 → 原样透传，否则老函数（只写 expr）的数字会变成字符串。"""
    fn = {"parameters": [{"key": "a", "source": "parameter"}]}
    v = asyncio.run(F.prepare_inputs(fn, {"a": 1}, F.FunctionContext()))
    assert v["a"] == 1 and isinstance(v["a"], int)
    v2 = asyncio.run(F.prepare_inputs(fn, {"a": "x"}, F.FunctionContext()))
    assert v2["a"] == "x"


def test_prepare_inputs_reports_bad_value_for_declared_type():
    fn = {"parameters": [{"key": "n", "type": "number", "source": "parameter"}]}
    with pytest.raises(F.ExprError) as e:
        asyncio.run(F.prepare_inputs(fn, {"n": "abc"}, F.FunctionContext()))
    assert "不是合法数字" in str(e.value)


def test_run_expression_with_string_inputs_from_ui():
    """端到端复现界面场景：输入框给字符串，声明 number 后应能算。"""
    fn = {"kind": "expression", "expr": "online_count / total_count * 100",
          "parameters": [
              {"key": "online_count", "type": "number", "required": True},
              {"key": "total_count", "type": "number", "required": True},
          ]}
    r = asyncio.run(F.run_function(fn, {"online_count": "8", "total_count": "10"}))
    assert r["ok"] is True, r.get("msg")
    assert r["value"] == 80.0


def test_prepare_inputs_loads_object_when_needed():
    fn = {"parameters": [{"key": "name", "source": "object_property", "object_property": "name"}]}
    ctx = F.FunctionContext(object_code="cams", object_key="1")

    async def loader(code, key):
        return {"name": "东门-1号"}

    v = asyncio.run(F.prepare_inputs(fn, {}, ctx, loader))
    assert v["name"] == "东门-1号"


def test_missing_required_only_applies_to_parameter_source():
    fn = {"parameters": [
        {"key": "a", "source": "parameter", "required": True},
        {"key": "b", "source": "static", "required": True, "default": 1},
    ]}
    assert F.missing_required(fn, {}) == ["a"]
    assert F.missing_required(fn, {"a": 1}) == []


def test_coerce_outputs():
    assert F.coerce_outputs({}, 5) == 5
    assert F.coerce_outputs({"outputs": [{"key": "r"}]}, 5) == {"r": 5}
    assert F.coerce_outputs({"outputs": [{"key": "a"}, {"key": "b"}]}, 5) == {"value": 5}


# ---------------------------------------------------------------------------
# 四种形态
# ---------------------------------------------------------------------------
def test_run_expression_function():
    fn = {"kind": "expression", "expr": "online / total * 100",
          "parameters": [{"key": "online", "required": True}, {"key": "total", "required": True}]}
    r = asyncio.run(F.run_function(fn, {"online": 8, "total": 10}))
    assert r["ok"] and r["value"] == 80.0
    # 缺必填
    r2 = asyncio.run(F.run_function(fn, {"online": 8}))
    assert not r2["ok"] and "必填" in r2["msg"]
    # 表达式引用了未声明的变量 → 按「推断成必填入参」处理，提示缺哪个入参
    r3 = asyncio.run(F.run_function({"kind": "expression", "expr": "ghost + 1"}, {}))
    assert not r3["ok"] and "ghost" in r3["msg"]


def test_run_aggregate_function():
    fn = {"kind": "aggregate", "config": {"source_object": "recs", "link_path": [27],
                                          "aggregation": "count", "limit": 5}}
    calls = []

    async def agg(cfg, values):
        calls.append((cfg, values))
        return 3

    r = asyncio.run(F.run_function(fn, {"object_key": "1"}, aggregate_runner=agg))
    assert r["ok"] and r["value"] == 3
    assert calls[0][1]["object_key"] == "1"
    # 没有 runner 时如实报错，而不是静默返回 None
    r2 = asyncio.run(F.run_function(fn, {"object_key": "1"}))
    assert not r2["ok"] and "关联聚合" in r2["msg"]


def test_run_model_function_requires_runner():
    fn = {"kind": "model", "config": {"model_id": 1, "prompt": "总结 {{text}}"}}

    async def runner(cfg, values):
        return f"OK:{values.get('text')}"

    r = asyncio.run(F.run_function(fn, {"text": "x"}, model_runner=runner))
    assert r["ok"] and r["value"] == "OK:x"
    r2 = asyncio.run(F.run_function(fn, {"text": "x"}))
    assert not r2["ok"] and "模型调用" in r2["msg"]


def test_run_function_rejects_unknown_kind():
    r = asyncio.run(F.run_function({"kind": "magic"}, {}))
    assert not r["ok"] and "magic" in r["msg"]


# ---------------------------------------------------------------------------
# 外部服务（真起一个本地 HTTP 服务）
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"data": {"total": 42, "items": [{"n": 1}]}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n) or b"{}")
        body = json.dumps({"echo": payload}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # 静音
        pass


@pytest.fixture
def allow_loopback():
    """显式打开**仅供测试**的 SSRF 逃生阀（生产不得设置该环境变量）。

    需要打 127.0.0.1 的用例必须声明依赖它 —— 让"为什么例外"在用例处可见，
    而不是隐式放宽防护。函数级作用域：用例结束即恢复，不会泄漏给其它模块。
    """
    import os

    os.environ["AISTATION_ALLOW_LOOPBACK_HTTP"] = "1"
    yield
    os.environ.pop("AISTATION_ALLOW_LOOPBACK_HTTP", None)


@pytest.fixture(scope="module")
def local_server():
    """本地 HTTPServer：供 http 形态函数用例打真实请求（打的也是 127.0.0.1）。"""
    import os

    os.environ["AISTATION_ALLOW_LOOPBACK_HTTP"] = "1"
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    os.environ.pop("AISTATION_ALLOW_LOOPBACK_HTTP", None)


def test_http_function_get_with_result_path(local_server):
    fn = {"kind": "http", "config": {"url": f"{local_server}/x", "method": "GET",
                                     "result_path": "data.total"}}
    r = asyncio.run(F.run_function(fn, {}))
    assert r["ok"] and r["value"] == 42


def test_http_function_post_and_template(local_server):
    fn = {"kind": "http",
          "config": {"url": f"{local_server}/y", "method": "POST",
                     "body_template": '{"name":"{{name}}"}',
                     "result_path": "echo.name"}}
    r = asyncio.run(F.run_function(fn, {"name": "东门-1号"}))
    assert r["ok"] and r["value"] == "东门-1号"


def test_http_function_validates_and_handles_unreachable(allow_loopback):
    # 该用例专门测"连接被拒"路径，必须打 127.0.0.1 ⇒ 显式打开测试逃生阀
    bad = asyncio.run(F.run_function(
        {"kind": "http", "config": {"url": "ftp://x"}}, {}))
    assert not bad["ok"] and "http" in bad["msg"]
    unreachable = asyncio.run(F.run_function(
        {"kind": "http", "config": {"url": "http://127.0.0.1:9/nope", "timeout": 1}}, {}))
    assert not unreachable["ok"] and "失败" in unreachable["msg"]
    missing = asyncio.run(F.run_function(
        {"kind": "http", "config": {"url": "http://127.0.0.1:9/nope", "timeout": 1}}, {}))
    assert not missing["ok"]


# ---------------------------------------------------------------------------
# 编辑期校验
# ---------------------------------------------------------------------------
def test_validate_expression_function():
    assert F.validate_function({"kind": "expression", "expr": "a + 1",
                                "parameters": [{"key": "a"}]}) == []
    errs = F.validate_function({"kind": "expression", "expr": "ghost + nope()"})
    joined = "；".join(errs)
    assert "ghost" in joined and "nope" in joined
    assert F.validate_function({"kind": "expression", "expr": ""}) != []


def test_validate_aggregate_function():
    ok = {"kind": "aggregate", "config": {"source_object": "recs", "link_path": [1],
                                          "aggregation": "count", "limit": 10}}
    assert F.validate_function(ok) == []
    errs = F.validate_function({"kind": "aggregate", "config": {
        "source_object": "recs", "link_path": [1, 2, 3, 4], "aggregation": "xxx", "limit": 500}})
    joined = "；".join(errs)
    assert "3 层" in joined and "聚合方式" in joined and "1–100" in joined
    # 非 count 聚合必须给 property
    assert any("property" in e for e in F.validate_function(
        {"kind": "aggregate", "config": {"source_object": "r", "link_path": [1],
                                         "aggregation": "sum", "limit": 10}}))


def test_validate_http_and_model_function():
    assert F.validate_function({"kind": "http", "config": {
        "url": "https://a.com", "method": "POST"}}) == []
    e1 = F.validate_function({"kind": "http", "config": {"url": "ftp://a"}})
    assert any("http" in x for x in e1)
    e2 = F.validate_function({"kind": "http", "config": {
        "url": "https://a.com", "body_template": "{bad json"}})
    assert any("body_template" in x for x in e2)
    # model_id 可留空（用平台默认模型），但 prompt 必填；写了非法值要报
    assert F.validate_function({"kind": "model", "config": {"prompt": "x"}}) == []
    e3 = F.validate_function({"kind": "model", "config": {}})
    assert any("prompt" in x for x in e3)
    e4 = F.validate_function({"kind": "model", "config": {"model_id": "abc", "prompt": "x"}})
    assert any("model_id" in x for x in e4)


def test_validate_inputs():
    errs = F.validate_function({"kind": "expression", "expr": "a", "parameters": [
        {"key": ""},
        {"key": "a", "source": "telepathy"},
        {"key": "b", "type": "matrix"},
        {"key": "c", "source": "object_property"},
    ]})
    joined = "；".join(errs)
    assert "缺少 key" in joined
    assert "telepathy" in joined
    assert "matrix" in joined
    assert "object_property" in joined


def test_recommend_kind():
    assert F.recommend_kind({"expr": "a + 1"}) == "expression"
    assert F.recommend_kind({"kind": "http"}) == "http"
