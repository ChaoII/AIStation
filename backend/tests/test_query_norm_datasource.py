"""数据源入参归一化（code ↔ ds:{id}）。"""
import asyncio


def test_norm_datasource_passthrough():
    async def _go():
        from app.plugin.module_ai.query import service as S

        return (
            await S._norm_datasource(None),
            await S._norm_datasource(""),
            await S._norm_datasource("system"),
            await S._norm_datasource("ds:4"),
        )

    assert asyncio.run(_go()) == (None, None, "system", "ds:4")


def test_norm_datasource_unknown_code_returns_as_is():
    async def _go():
        from app.plugin.module_ai.query import service as S

        return await S._norm_datasource("no_such_code_xyz")

    assert asyncio.run(_go()) == "no_such_code_xyz"
