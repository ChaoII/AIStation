"""OpenAPI schema 预生成回归（对应「首次访问 /openapi.json 卡死 6.7 秒」）。

实测：989 条路由的 schema 生成是 **6.7 秒纯 CPU**，期间事件循环完全卡死——
所有请求（含无关接口）都得排队。启动期预生成后应直接命中缓存。
"""

import pytest


def test_openapi_schema_precomputed_at_startup() -> None:
    import conftest

    app = conftest.app
    if app is None:
        pytest.skip("PYTEST_NO_APP=1：需要应用实例")

    assert app.openapi_schema is not None, (
        "启动时没有预生成 /openapi.json 的 schema——首次访问要现场算 6.7 秒并卡死事件循环"
    )

    first = app.openapi_schema
    assert app.openapi() is first, "openapi() 必须直接命中缓存，不得重算"
