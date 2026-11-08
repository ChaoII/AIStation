"""金路径冒烟（后端）：改完问数/配置/权限后先跑这个，再交付。

覆盖的是「单测看不见、但用户一用就炸」的那类问题：
- 装饰器/导入丢失（运行时 500）
- 路由没注册
- 缓存没按主体隔离
- 导出/浏览绕过唯一网关
- 配置接口语义错（默认值 vs 生效值）

用法：cd backend && .venv\\Scripts\\python.exe scripts/query_golden_smoke.py
退出码非 0 即失败。
"""
from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("✅ " if ok else "❌ ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def main() -> None:
    from main import create_app

    app = create_app()
    paths = app.openapi().get("paths", {})

    from app.plugin.module_ai.query.service import AiQueryService as S, _sql_cache_key

    # 1. 类方法装饰器（这轮踩了两次：装饰器被脚本挤掉 → 慢路径全 500）
    for name in ("get_settings", "effective_settings", "_build_schema_context", "_context_principal"):
        check(f"{name} 是 classmethod", isinstance(inspect.getattr_static(S, name), classmethod))

    # 2. 默认配置非空（51 项）
    defaults = __import__("asyncio").run(S.get_settings())
    check("默认配置 >= 40 项", isinstance(defaults, dict) and len(defaults) >= 40, str(len(defaults)))

    # 3. 关键路由已注册
    for p in ("/ai/query/settings", "/ai/query/settings/defaults",
              "/ai/query/assets/draft-desc", "/ai/query/policy/list",
              "/ai/query/access/explain"):
        check(f"路由 {p}", any(p in k for k in paths))

    # 4. SQL 缓存按主体隔离
    a = _sql_cache_key("q", "ds:4", "1|ADMIN")
    b = _sql_cache_key("q", "ds:4", "2|USER")
    check("SQL 缓存按主体隔离", a != b)

    # 5. 导出/浏览必须走唯一网关
    for fn in ("export_asset", "object_browse"):
        src = inspect.getsource(getattr(S, fn))
        check(f"{fn} 走 _execute_one", "_execute_one" in src)

    # 6. 策略模块可导入、网关可调用
    try:
        from app.plugin.module_ai.query.policy import compiler, context, guard

        check("策略模块可导入", True)
        check("guard.prepare 可调用", callable(guard.prepare))
        check("compiler.rewrite 可调用", callable(compiler.rewrite))
        check("context.build_context_scope 可调用", callable(context.build_context_scope))
    except Exception as e:  # noqa: BLE001
        check("策略模块可导入", False, str(e)[:120])

    print(f"\n{'全部通过' if not FAILS else '失败 ' + str(len(FAILS)) + ' 项'}")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
