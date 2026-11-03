"""死代码审计：找出"定义了但没人调用"的函数/方法（接线审计的静态那一半）。

⚠️ 与 `scripts/audit_wiring.py` 分工：那个查**前端页面 ↔ 菜单 component_path**
   是否一一对应（孤儿页/缺失页），本脚本查**后端函数有没有调用方**。

用户最在意的不是"功能写错"，而是**逻辑没接上**：函数写了、开关加了，
但运行时走的是另一条路 / 另一个常量。这类缺陷编译不报错、单测未必覆盖、
界面上看着一切正常，只能靠静态对账 + 真实提问才能发现。

用法::

    cd backend
    uv run python scripts/audit_dead_code.py                    # 默认扫问数模块
    uv run python scripts/audit_dead_code.py app/plugin/module_ai/ontology

判据与已知误报
--------------
- 有装饰器的函数**跳过**：`@router.get` / `@cli.command` / `@property` /
  `@classmethod` 是框架按装饰器注册的，按名字找不到引用属正常。
- 名字只出现在字符串里（`getattr(obj, "xxx")`）也算引用，故动态分派不会误报成死代码。
- 反过来，**同名不同物**会漏报（例如两个模块各有一个 `_stats`）：只作线索，人工确认。

本脚本不会删任何东西，输出仅供人工判断。
"""
from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # backend/
TARGET = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "app/plugin/module_ai/query")
SCAN_DIRS = [ROOT / "app", ROOT / "tests", ROOT / "scripts"]


def _py_files(dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        if d.exists():
            out += [p for p in d.rglob("*.py") if ".venv" not in p.parts]
    return out


def _defs(path: Path) -> tuple[list[tuple[str, int]], int]:
    """(无装饰器的函数名与行号, 被跳过的装饰器函数个数)。"""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except SyntaxError as e:                          # 语法错的文件单独提示
        print(f"! 无法解析 {path.relative_to(ROOT)}: {e}")
        return [], 0
    plain: list[tuple[str, int]] = []
    decorated = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.decorator_list:
                decorated += 1
            elif not node.name.startswith("__"):
                plain.append((node.name, node.lineno))
    return plain, decorated


def main() -> None:
    targets = _py_files([TARGET])
    corpus = _py_files(SCAN_DIRS)
    print(f"扫描 {TARGET.relative_to(ROOT)}：{len(targets)} 个文件；"
          f"参照全仓 {len(corpus)} 个 .py")

    entries: list[tuple[str, str, int]] = []
    skipped_decorated = 0
    for f in targets:
        defs, dec = _defs(f)
        skipped_decorated += dec
        entries += [(n, str(f.relative_to(ROOT)), ln) for n, ln in defs]
    print(f"跳过有装饰器的函数 {skipped_decorated} 个（路由/CLI/属性，由框架注册）\n")

    # 全仓文本里各名字出现次数（减掉定义处；同名多处定义按次数减）
    counts: Counter[str] = Counter()
    for f in corpus:
        try:
            text = open(f, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        for name in {e[0] for e in entries}:
            counts[name] += text.count(name)
    defs_per_name: dict[str, int] = defaultdict(int)
    for name, _, _ in entries:
        defs_per_name[name] += 1

    dead = [(n, p, ln) for n, p, ln in entries
            if counts[n] - defs_per_name[n] <= 0]

    if not dead:
        print("✅ 没有零引用的函数")
        return
    print(f"【零引用】{len(dead)} 个（需人工确认：可能是预留/运维入口）")
    for name, path, line in sorted(dead, key=lambda x: x[1]):
        print(f"  {path}:{line}  {name}")


if __name__ == "__main__":
    main()
