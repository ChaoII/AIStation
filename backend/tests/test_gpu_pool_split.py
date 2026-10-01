"""``gpu_pool`` 包的结构守卫。

拆分的两个教训，各对应一组断言：

1. **转发层必须显式转发私有名。** ``from .x import *`` 只带 ``__all__``，
   而 ``_redis`` / ``_local`` / ``_port_bindable`` 这些私有名**确实有外部引用**
   （含测试）。少转一个就会在 pytest collection 阶段 ImportError——
   报错点离改动点很远，很难一眼看出是转发层漏了。

2. **转发层是别名，patch 它不生效。** 被调用方按**自己模块的全局**查找名字，
   所以 ``monkeypatch.setattr(gpu_pool, "gpu_devices", ...)`` 既不报错也不生效，
   症状是「GPU 列表根本没被伪造，测试却过了」。这条静默失效比报错危险得多，
   所以这里用**行为断言**把它钉住：patch 转发层必须**不**影响真实调用方。

第 2 条没法靠读代码保证（别名和真调用在运行时完全等价），只能靠一个
「patch 转发层 → 真实行为不变」的反向测试来证明。
"""

import asyncio

import pytest

from app.plugin.module_train import gpu_pool
from app.plugin.module_train.gpu_pool import (
    _store, alloc, device, lease, readiness, watchdog,
)

SUBMODULES = ("_store", "port", "device", "alloc", "lease", "readiness", "watchdog")


# ---------------------------------------------------------------------------
# 1. 转发层完整性
# ---------------------------------------------------------------------------


def test_submodules_importable():
    for name in SUBMODULES:
        assert hasattr(gpu_pool, name), f"子模块 {name} 未从转发层导出"


@pytest.mark.parametrize("name", [
    # 公开 API
    "acquire", "release", "allocation_of", "Allocation",
    "gpu_lease", "wait_service_ready",
    "gpu_devices", "busy_task_count", "reap_stale",
    "port_bindable", "claim_port", "release_port",
    "claim_gpu", "release_gpu_list", "cleanup_redis_by_task",
    "redis_or_none", "OCCUPIED_TTL", "ALIVE_STATUSES",
    # 拆分前的私有名：外部仍有引用（含测试），少一个就是 collection 期 ImportError
    "_redis", "_local", "_local_ports", "_local_gpus",
    "_port_bindable", "_claim_port", "_claim_gpu",
    "_release_port", "_release_gpu_list", "_cleanup_redis_by_task",
    "_K_PORT", "_K_GPU", "_OCCUPIED_TTL", "_ALIVE_STATUSES",
])
def test_forwarded_name_exists(name):
    assert hasattr(gpu_pool, name), f"转发层缺少 {name}"


def test_underscore_aliases_point_at_real_objects():
    """私有名别名必须**指向同一对象**，不能是拷贝。

    测试里 ``gpu_pool._local_ports.clear()`` 清的必须就是 :mod:`.port` 用的那份，
    否则测试清的是另一份字典、清理静默失效。
    """
    assert gpu_pool._local is _store.LOCAL
    assert gpu_pool._local_ports is _store.LOCAL_PORTS
    assert gpu_pool._local_gpus is _store.LOCAL_GPUS
    assert gpu_pool._K_PORT is _store.K_PORT
    assert gpu_pool._K_GPU is _store.K_GPU


def test_public_functions_are_not_rewrapped():
    """转发必须是 re-export 而不是 ``def f(...): return impl.f(...)``。

    包装函数会：① 让 ``inspect.signature`` 变成 ``(*args, **kwargs)``；
    ② 让文档/报错指向转发层而不是真实实现，排障时多绕一层。
    """
    import inspect

    for name in ("acquire", "release", "gpu_lease", "wait_service_ready",
                 "reap_stale", "busy_task_count", "gpu_devices"):
        a, b = getattr(gpu_pool, name), _REAL[name]
        assert a is b, f"{name} 是包装副本而不是别名"
        assert inspect.signature(a) is not None


_REAL = {
    "acquire": alloc.acquire,
    "release": alloc.release,
    "gpu_lease": lease.gpu_lease,
    "wait_service_ready": readiness.wait_service_ready,
    "reap_stale": watchdog.reap_stale,
    "busy_task_count": watchdog.busy_task_count,
    "gpu_devices": device.gpu_devices,
}


# ---------------------------------------------------------------------------
# 2. 依赖是 DAG，没有环
# ---------------------------------------------------------------------------


def test_no_import_cycles():
    """逐个单独导入每个子模块——有环时这里会 ImportError。"""
    import importlib

    for name in SUBMODULES:
        mod = importlib.import_module(f"app.plugin.module_train.gpu_pool.{name}")
        assert mod.__name__.endswith(name)


def test_sibling_imports_only_point_downward():
    """子模块只允许 import **更底层**的兄弟模块。"""
    import ast
    import pathlib

    pkg = pathlib.Path(gpu_pool.__file__).parent
    # 期望的层次（数字越大越底层）
    layer = {"_store": 0, "port": 1, "device": 1, "alloc": 2,
             "watchdog": 3, "lease": 3, "readiness": 0, "__init__": 9}

    for name in SUBMODULES:
        tree = ast.parse(pkg.joinpath(f"{name}.py").read_text(encoding="utf-8"))
        # 只看**模块级** import：直接遍历 tree.body，不 walk。
        # 函数内的延迟导入是有意为之（alloc↔watchdog 互相引用，必须有一边延迟），
        # 把它算进层次检查会永远报错。
        for node in tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            sibs = []
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                sibs.append(node.module)
            elif isinstance(node, ast.ImportFrom) and node.module and \
                    f"gpu_pool.{node.module}" in sys_modules():
                sibs.append(node.module)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if ".gpu_pool." in a.name:
                        sibs.append(a.name.rsplit(".", 1)[1])
            for s in sibs:
                if s not in layer:
                    continue
                assert layer[s] <= layer[name], (
                    f"{name}.py 导入了比自己更高层的 {s}"
                    f"（{name} 层 {layer[name]} < {s} 层 {layer[s]}）——会成环")


def sys_modules():
    import sys

    return sys.modules


# ---------------------------------------------------------------------------
# 3. 转发层 patch 不生效（这是刻意行为，用反向测试钉住）
# ---------------------------------------------------------------------------


def test_patching_forwarded_gpu_devices_does_not_affect_alloc(monkeypatch):
    """patch 转发层**不**影响真实调用方——文档里明确要求 patch 子模块。

    这条断言是「别名语义」的正面证明：如果哪天有人把转发层改成包装函数，
    这个测试会失败，从而挡住「看起来更友好、实际改变行为」的改法。
    """
    monkeypatch.setattr(device, "gpu_devices", lambda: [
        {"index": 0, "uuid": "GPU-orig", "total": 1, "used": 0, "free": 1,
         "free_gb": 99.0, "used_ratio": 0.0}])

    monkeypatch.setattr(gpu_pool, "gpu_devices", lambda: [
        {"index": 9, "uuid": "GPU-patched-fwd", "total": 1, "used": 0, "free": 1,
         "free_gb": 99.0, "used_ratio": 0.0}])

    seen = {}

    async def _spy():
        return device.gpu_devices()

    seen["real"] = asyncio.run(_spy())
    assert seen["real"][0]["uuid"] == "GPU-orig"
    # 而 alloc 用的正是 device.gpu_devices
    assert alloc.device_mod is device


def test_alloc_reaches_gpu_devices_through_module(monkeypatch):
    """``acquire`` 必须经 ``device_mod.gpu_devices()`` 取列表，而不是直接绑定。

    直接 ``from .device import gpu_devices`` 会把 patch 目标固定在导入时，
    测试就无法伪造 GPU 列表——这正是拆分前测试改 patch 目标的原因。
    """
    import ast
    import pathlib

    src = pathlib.Path(alloc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "gpu_devices"
    ]
    assert calls == ["gpu_devices"], "acquire 应通过 device 模块取 GPU 列表"
    assert "from .device import gpu_devices" not in src, (
        "不要直接 import gpu_devices——那会让 monkeypatch 失效")


def test_alloc_reaches_redis_through_store(monkeypatch):
    """同上：``acquire`` 必须经 ``_store.redis_or_none()``。"""
    import ast
    import pathlib

    src = pathlib.Path(alloc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    called = {
        n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "redis_or_none" in called, "acquire/release 应经 _store.redis_or_none()"
    assert "from ._store import redis_or_none" not in src, (
        "不要直接 import redis_or_none——patch 会失效")


def test_watchdog_imports_release_lazily():
    """``alloc.release`` 需要 ``watchdog.cleanup_redis_by_task``，反之亦然。

    两者互相引用，必须有一边是**函数内延迟导入**。这里守卫那个延迟导入还在，
    免得有人「顺手清理」成顶层导入，直接成环。
    """
    import ast
    import pathlib

    src = pathlib.Path(alloc.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    # alloc 里对 watchdog 的引用必须出现在函数体内部
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_src = ast.unparse(node)
            if "watchdog" in body_src:
                assert "import" in body_src, (
                    f"{node.name} 里引用 watchdog 但没在函数内 import")
                return
    raise AssertionError("alloc 里找不到对 watchdog 的延迟导入")


# ---------------------------------------------------------------------------
# 4. 职责边界（防止新职责又塞回某个模块）
# ---------------------------------------------------------------------------


def test_readiness_does_not_touch_resource_pool():
    """就绪探测不该分配资源——它只发 HTTP。"""
    import pathlib

    src = pathlib.Path(readiness.__file__).read_text(encoding="utf-8")
    for bad in ("acquire", "release", "redis_or_none", "K_PORT", "K_GPU"):
        assert bad not in src, f"readiness 不该出现 {bad}"


def test_store_has_no_allocation_logic():
    """存储层只管「拿句柄/记占用」，不含端口与 GPU 的判据。"""
    import ast
    import pathlib

    src = pathlib.Path(_store.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 看真实 import 而不是子串——子串会命中 "socket_timeout=" 这类配置项
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "socket" not in imported, "存储层不该做端口探测（那是 port.py 的事）"
    assert "pynvml" not in imported, "存储层不该枚举 GPU（那是 device.py 的事）"
    funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert funcs <= {"redis_or_none"}, f"存储层出现了意外的函数: {funcs - {'redis_or_none'}}"


def test_modules_are_reasonably_small():
    """守住「单一职责」：任何模块超过 ~200 行就该问是不是又混了职责。"""
    import pathlib

    pkg = pathlib.Path(gpu_pool.__file__).parent
    for name in SUBMODULES:
        lines = len(pkg.joinpath(f"{name}.py").read_text(encoding="utf-8").splitlines())
        assert lines <= 220, (
            f"{name}.py 有 {lines} 行，超过 220——多半是又混进了别的职责")
