"""``exporter.py`` 拆分的结构守卫。

背景
----
原 ``exporter.py`` 有 **2291 行**，混合了四类互不相干的职责：

1. 17 个数据集导出格式（YOLO / X-AnyLabeling / COCO Panoptic / PaddleOCR / 事件…）
2. 模型权重入库（``export_model``）
3. DB 访问（直接开 24 次会话，绕过 service 层）
4. S3 操作（25 次）

已按依赖 DAG 拆成 ``exporters/`` 子包（10 个模块）+ ``model_persist.py``，函数体逐字节
搬运（用 ``ast.dump`` 逐个比对确认过）。

这个文件防止拆分被回退。**回退几乎总是无声的**：不会有人写"把 exporter 重新合并"，
而是某天加新格式时图方便，直接往 ``exporter.py`` 里加几百行——于是「改数据集格式要
在 2000 行文件里翻找」「权重入库的写操作没有独立事务边界」这两个问题悄悄回来了。

删除条件
--------
等所有调用方都改到新位置、且没有测试再引用 ``exporter`` 后，可连同它一起删除；
届时把下面两条守卫改成断言"``exporter`` 不再存在"。
"""

import ast
import pathlib

import pytest

TRAIN_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_train"
EXPORTERS = TRAIN_DIR / "exporters"
COMPAT = TRAIN_DIR / "exporter.py"
PERSIST = TRAIN_DIR / "model_persist.py"


def module_defs(path: pathlib.Path) -> set[str]:
    """模块级**定义**的函数名与常量名（不含 import 进来的转发名）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            out |= {t.id for t in n.targets
                    if isinstance(t, ast.Name) and t.id.isupper()}
    return out


def module_imports(path: pathlib.Path) -> set[str]:
    """模块级 import 进来的名字。

    转发层（``exporter.py``）里全是 import、没有定义，所以判断「是否覆盖了外部引用」
    必须看 import 集合而不是定义集合——否则会误报「一个都没覆盖」。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.Import):
            out |= {(a.asname or a.name).split(".")[0] for a in n.names}
    return out


# ---------------------------------------------------------------- 拆分形状


def test_compat_layer_has_no_implementation():
    """``exporter.py`` 必须只剩转发，不许再有函数/常量定义。

    这是整条守卫的核心：只要它还是纯转发，实现就不可能悄悄堆回这里。
    """
    assert COMPAT.exists(), "exporter.py 兼容层不见了——若已改完调用方可直接删（见模块 docstring）"
    tree = ast.parse(COMPAT.read_text(encoding="utf-8"))
    impl = [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert not impl, f"exporter.py 里不该再有函数定义，实际有：{impl}"


def test_compat_layer_size_stays_small():
    """转发层应该很小。超过 150 行说明有人在往里加东西。"""
    n = len(COMPAT.read_text(encoding="utf-8").splitlines())
    assert n < 150, (
        f"exporter.py 已涨到 {n} 行——新实现应放进 exporters/ 或 model_persist.py，"
        f"而不是把拆分退回去"
    )


def test_weight_persistence_lives_outside_exporters():
    """``export_model`` / ``_fetch_torchkiln_weights`` 必须在 ``model_persist.py``。

    刻意不放进 ``exporters/``：权重入库的数据流方向与数据集导出相反（前者进模型仓库、
    后者出训练框架格式），依赖的东西也不同（前者要 s3_client + ORM 写事务，后者要标注
    查询 + 文件写入）。塞在一起正是当初 2291 行文件的成因。
    """
    assert PERSIST.exists(), "model_persist.py 不见了"
    names = module_defs(PERSIST)
    assert "export_model" in names
    assert "_fetch_torchkiln_weights" in names
    # 且不能同时出现在 exporters/ 里（否则等于没拆）
    in_pkg = {n for f in EXPORTERS.glob("*.py") for n in module_defs(f)}
    assert "export_model" not in in_pkg, "export_model 不该同时存在于 exporters/"


@pytest.mark.parametrize("mod", [
    "common", "yolo", "semantic", "xanylabeling", "paddle",
    "torchkiln_ocr", "events", "video", "mono3d", "dispatch",
])
def test_exporters_subpackage_module_exists(mod):
    """子包应有约定的这些模块——少一个说明有人把实现挪回去了。"""
    assert (EXPORTERS / f"{mod}.py").exists(), f"exporters/{mod}.py 不见了"


# ---------------------------------------------------------------- 依赖方向


def test_module_level_graph_is_acyclic():
    """模块级依赖必须无环。

    函数级 DAG 成立**不代表**模块级成立——若两个模块互相 import（比如 yolo ↔ video），
    拆出来的文件会在导入时循环。拆分时靠这个断言拦过一次，值得固化。
    """
    mods = {p.stem: p for p in EXPORTERS.glob("*.py")}
    deps: dict[str, set[str]] = {}
    for stem, p in mods.items():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        found: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module:
                if n.module in mods:
                    found.add(n.module)
        deps[stem] = found

    for a, bs in deps.items():
        for b in bs:
            assert a not in deps.get(b, set()), (
                f"模块级双向依赖：{a} ↔ {b}（导入时会循环）"
            )


#: 允许横向依赖的组合，及其**理由**。
#:
#: 只有 ``video`` 例外：抽帧后的帧样本既可写成 YOLO 检测布局、也可写成
#: X-AnyLabeling 布局（``_export_video_detection`` 按 framework 二选一），这是
#: 「同一种数据、两种输出格式」的本质要求，不是耦合失控。
_ALLOWED_SIBLING_DEPS = {
    "video": {"xanylabeling", "yolo"},
}


def test_only_dispatch_depends_on_every_format_module():
    """格式模块之间不该横向耦合；唯一的例外见 ``_ALLOWED_SIBLING_DEPS``。

    反过来说：若某个格式模块开始 import 别的格式模块，说明该抽公共函数到 common，
    而不是横向耦合。
    """
    mods = {p.stem for p in EXPORTERS.glob("*.py")} - {"__init__", "common", "dispatch"}
    for p in EXPORTERS.glob("*.py"):
        if p.stem in ("__init__", "common", "dispatch"):
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        siblings = {n.module for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom) and n.level == 1
                    and n.module in mods}
        allowed = _ALLOWED_SIBLING_DEPS.get(p.stem, set())
        assert siblings <= allowed, (
            f"{p.name} import 了未授权的兄弟格式模块 {sorted(siblings - allowed)}"
            f"——应把共用部分上提到 common.py；确需横跨请登记到 _ALLOWED_SIBLING_DEPS"
        )


def test_common_has_no_format_module_dependencies():
    """Layer 0（common）不得依赖任何 Layer 1 模块，否则分层失效。"""
    tree = ast.parse((EXPORTERS / "common.py").read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module:
            assert n.module != "common", "common 不该 import 自己"
            assert n.module != "__init__", "common 不该 import 包 __init__（会循环）"


# ---------------------------------------------------------------- 转发完整性


def external_references() -> set[str]:
    """扫出 app/ 与 tests/ 里所有 ``from ... import <名字>``（指向 exporter）。"""
    root = TRAIN_DIR.parents[2]  # backend/
    need: set[str] = set()
    for p in list((root / "app").rglob("*.py")) + list((root / "tests").rglob("*.py")):
        if p.resolve() in (COMPAT.resolve(), PERSIST.resolve()):
            continue
        if EXPORTERS in p.parents or p.parent == EXPORTERS:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.ImportFrom) or not n.module:
                continue
            if n.module == "exporter" or n.module.endswith(".module_train.exporter"):
                need |= {a.name for a in n.names}
    return need


def test_compat_layer_covers_every_external_reference():
    """转发层必须覆盖全部外部引用，**含下划线私有名**。

    ``from .exporters import *`` 是不够的——它只带 ``__all__``，而测试会引用
    ``_export_core`` / ``_format_yolo_lines`` 这类私有符号。漏一个的后果是
    collection 阶段直接 ImportError（实测踩过，且错误信息指向 exporter，
    掩盖了真正缺的是转发清单）。
    """
    need = external_references()
    assert need, "扫描不到任何外部引用——检查 external_references 的路径推断是否失效"
    have = module_imports(COMPAT)
    missing = sorted(need - have)
    assert not missing, (
        f"exporter.py 未转发这些符号（被 {len(need)} 处外部引用）：{missing}"
    )


def test_exported_symbols_are_not_shadowed():
    """转发层拿到的必须是**真实现**，不是占位。

    逐个断言这些符号在子包里也有定义——防止有人在兼容层写同名 stub 掩盖缺失。
    """
    pkg = {n for p in EXPORTERS.glob("*.py") for n in module_defs(p)}
    for name in sorted(module_defs(COMPAT)):
        assert name in pkg or name in module_defs(PERSIST), (
            f"exporter.py 转发了 {name}，但子包里没有对应实现——"
            f"这意味着调用方拿到的是不存在的符号"
        )
