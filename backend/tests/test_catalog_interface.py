"""共享数据目录接口：本体与问数只通过它读写"治理信息"，不互相直读表。

背景（实测）：`ontology/semantic.py` 直接 SQL 读/写了问数模块的
`ai_query_concept` 与 `ai_query_asset_columns`（本体反向依赖问数，方向反了）。
这里把它们收敛成一个**共享目录接口**，两侧都只依赖它。
"""
import asyncio


def test_catalog_exposes_concepts_sensitive_and_included():
    async def _run():
        from app.plugin.module_ai import catalog

        concepts = await catalog.list_concepts()
        assert isinstance(concepts, list)
        for c in concepts:
            assert {"name", "synonyms", "domain", "metric_key", "tables"} <= set(c)

        sens = await catalog.list_sensitive_columns()
        assert isinstance(sens, set)
        for t, col in sens:
            assert isinstance(t, str) and isinstance(col, str)

        inc = await catalog.included_tables()
        assert isinstance(inc, set)
        assert all(isinstance(t, str) for t in inc)

    asyncio.run(_run())


def test_catalog_mark_sensitive_is_idempotent():
    async def _run():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from app.plugin.module_ai import catalog

        # 用一张真实存在的资产表做幂等写入（不新增表，避免污染）
        async with async_db_session() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT table_name, column_name FROM ai_query_asset_columns "
                        "WHERE is_deleted=false LIMIT 1"
                    )
                )
            ).fetchone()
        if not row:
            return  # 无资产数据时跳过（不影响接口契约）
        pair = (str(row[0]), str(row[1]))

        before = await catalog.list_sensitive_columns()
        n1 = await catalog.mark_sensitive([pair])
        after1 = await catalog.list_sensitive_columns()
        n2 = await catalog.mark_sensitive([pair])
        after2 = await catalog.list_sensitive_columns()

        assert pair in after1, "标记后应出现在目录敏感集合里"
        assert after1 == after2, "重复标记必须幂等（结果集合不变）"
        assert n2 == 0, f"第二次不应有新增行，实际 {n2}"

        # 复原：仅当原本未标记时才清掉
        if pair not in before:
            async with async_db_session.begin() as db:
                await db.execute(
                    text(
                        "UPDATE ai_query_asset_columns SET sensitive=false "
                        "WHERE table_name=:t AND column_name=:c"
                    ),
                    {"t": pair[0], "c": pair[1]},
                )
        assert n1 >= 0

    asyncio.run(_run())


def test_ontology_does_not_directly_query_query_tables():
    """回归守卫：本体模块里不应再出现对 ai_query_* / ai_call_logs 的直读/直写 SQL。

    跨模块共享表（问数的 ai_query_*、调用日志的 ai_call_logs）一律走 catalog 接口，
    或记在本体自己的表里（工具调用用量即如此）。
    """
    import pathlib
    import re

    base = pathlib.Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_ai" / "ontology"
    pattern = re.compile(r"(FROM|INTO|UPDATE|JOIN)\s+(ai_query_|ai_call_logs)", re.IGNORECASE)
    hits: list[str] = []
    for f in base.glob("*.py"):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                hits.append(f"{f.name}:{i}: {line.strip()}")
    assert not hits, "本体不得直读/直写跨模块共享表，应走 catalog 接口：\n" + "\n".join(hits)
