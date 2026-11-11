"""给 ds:6 的业务表批量生成「中文名 / 别名 / 描述 / 字段描述」，落资产目录。

为什么需要它
------------
留出集暴露的最大短板是**表/字段语义消歧**（`ASSAY` vs `ASSAYCHECKSUGGESTION`、
`BELT` vs `BELTMODEL`）。资产目录里 `alias` 大多是表名本身、`description` 只有 200 多条，
而且源库的 `COMMENT ON` 在燃料系列表上**一条都没有**（实测 11 张表 0 注释）——
只能靠模型从「表名 + 字段名 + 数据分布」反推业务含义。

它与 `AutopilotOps.generate_asset_descriptions` 的区别：
- 那个走**平台库**画像（`SELECT COUNT(*)` 打在 `aistation` 上），对自定义数据源的表拿不到
  任何分布，等于让模型只看表名猜；
- 本脚本直连目标数据源做画像（行数/空值率/去重数/低基数取值），并且**只写 alias/description**，
  不碰 `included` 等治理字段。

用法
----
    cd backend
    uv run python scripts/backfill_table_descriptions.py --dry-run          # 只看会处理哪些表
    uv run python scripts/backfill_table_descriptions.py --limit 20         # 先跑 20 张看质量
    uv run python scripts/backfill_table_descriptions.py                    # 全量（缺描述的）
    uv run python scripts/backfill_table_descriptions.py --force --only FUEL_CMCS_ASSAY

幂等：默认只补空描述；`--force` 才覆盖已有内容。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_ID = 6
SKIP_PREFIX = ("AI_", "SYS_", "JIMU", "ONT_", "RPT_", "PG_", "U3D", "__EFMIGRATION")
PROFILE_COL_LIMIT = 40
SAMPLE_VALUE_COLS = 10


def _auth():
    from types import SimpleNamespace

    return SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))


async def _ds_cfg() -> dict:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        row = (await db.execute(text(
            "SELECT host,port,\"database\",username,password FROM ai_query_datasources WHERE id=:i"
        ), {"i": DS_ID})).first()
    return {"host": row[0], "port": row[1], "database": row[2], "user": row[3], "password": row[4]}


async def _candidates(conn) -> list[str]:
    """ds:6 里「已纳入 + 有数据 + 非系统表」的表名。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT s.table_name FROM ai_query_schema s "
            "WHERE s.datasource='ds:6' AND s.is_deleted=false"
        ))).fetchall()
        included = {
            str(r[0]).upper() for r in (await db.execute(text(
                "SELECT table_name FROM ai_query_assets "
                "WHERE is_deleted=false AND included=true"
            ))).fetchall()
        }
    known = [str(r[0]) for r in rows]
    live = {r["relname"].upper() for r in await conn.fetch(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind='r' AND c.reltuples > 0"
    )}
    out = []
    for t in known:
        up = t.upper()
        if up.startswith(SKIP_PREFIX) or "BAK" in up or "ENCRYPT" in up:
            continue
        if up not in included or up not in live:
            continue
        out.append(t)
    return sorted(out)


async def _columns(conn, table: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND lower(table_name)=lower($1) "
        "ORDER BY ordinal_position", table)
    return [r["column_name"] for r in rows]


async def _profile(conn, table: str, cols: list[str]) -> tuple[int, dict[str, dict]]:
    """行数 + 每列（空值率/去重数/低基数取值）。列多时只画像前 N 列。"""
    total = int(await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"') or 0)
    info: dict[str, dict] = {}
    if total == 0:
        return 0, info
    for i, c in enumerate(cols[:PROFILE_COL_LIMIT]):
        try:
            row = await conn.fetchrow(
                f'SELECT count("{c}") AS n, count(DISTINCT "{c}") AS d FROM "{table}"')
            n = int(row["n"] or 0)
            d = int(row["d"] or 0)
            item: dict = {"null_pct": round((total - n) * 100.0 / total), "distinct": d}
            if i < SAMPLE_VALUE_COLS and 0 < d <= 8:
                vals = await conn.fetch(
                    f'SELECT DISTINCT "{c}" AS v FROM "{table}" WHERE "{c}" IS NOT NULL LIMIT 8')
                item["values"] = [str(v["v"])[:20] for v in vals]
            info[c] = item
        except Exception:  # noqa: BLE001
            continue
    return total, info


def _prompt(table: str, total: int, cols: list[str], prof: dict[str, dict]) -> str:
    lines = [
        "你是电力/燃料（燃煤）业务系统的数据建模专家。请根据表名、字段名和数据分布，"
        "判断这张表在业务上是什么，并给出中文名、别名与字段含义。",
        "要求：",
        "1) alias：表的中文业务名，4~16 字，必须是业务人员会说的词（如「装车计划明细」）；"
        "不要照抄英文表名，不要写「表」「数据」这种废话。",
        "2) description：一句话说明这张表存什么、粒度是什么，不超过 40 字。",
        "3) columns：只对**有业务含义**的字段给一句话说明（不超过 20 字）；"
        "主键/创建时间/同步标记等可以留空。必须原样使用给定字段名。",
        "4) 不确定就留空，禁止编造。",
        '5) 只输出 JSON：{"alias":"...","description":"...","columns":[{"name":"...","description":"..."}]}',
        f"表名：{table}",
        f"数据量：{total} 行",
        "字段：" + ", ".join(cols[:PROFILE_COL_LIMIT]),
    ]
    for c, v in prof.items():
        seg = f"  {c}: 空值率{v['null_pct']}%、去重{v['distinct']}个"
        if v.get("values"):
            seg += "，取值[" + ",".join(v["values"]) + "]"
        lines.append(seg)
    return "\n".join(lines)


async def _save(table: str, alias: str, desc: str, col_desc: dict[str, str],
                force: bool, actor: int) -> tuple[bool, int]:
    """写回资产目录：只补空（force 才覆盖）。返回 (是否更新表, 更新了几个字段)。"""
    from sqlalchemy import select, text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.model import AiQueryAssetColumnModel, AiQueryAssetModel

    updated_tbl = False
    updated_cols = 0
    async with async_db_session.begin() as db:
        row = (await db.execute(select(AiQueryAssetModel).where(
            AiQueryAssetModel.table_name == table,
            AiQueryAssetModel.is_deleted.is_(False),
        ))).scalars().first()
        if row is None:
            # 没有资产行：建一条（included=true），否则描述无处可放
            await db.execute(text(
                "INSERT INTO ai_query_assets(table_name,description,alias,included,remark,is_deleted,"
                "created_time,updated_time) VALUES (:t,:d,:a,true,'',false,now(),now())"
            ), {"t": table, "d": desc, "a": alias})
            updated_tbl = True
        else:
            if force or not (row.description or "").strip():
                if desc:
                    row.description = desc
                    updated_tbl = True
            if alias and (force or not (row.alias or "").strip() or str(row.alias).upper() == table.upper()):
                row.alias = alias
                row.updated_id = actor
                updated_tbl = True
        if not col_desc:
            return updated_tbl, updated_cols
        cols = (await db.execute(select(AiQueryAssetColumnModel).where(
            AiQueryAssetColumnModel.table_name == table,
            AiQueryAssetColumnModel.is_deleted.is_(False),
        ))).scalars().all()
        for c in cols:
            d = (col_desc.get(c.column_name) or "").strip()
            if not d:
                continue
            if force or not (c.description or "").strip():
                c.description = d
                c.updated_id = actor
                updated_cols += 1
    return updated_tbl or updated_cols > 0, updated_cols


async def _existing_desc() -> dict[str, str]:
    """表名 → 现有描述（用于跳过已描述的，避免白花 LLM 调用）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT upper(table_name), coalesce(description,'') FROM ai_query_assets "
            "WHERE is_deleted=false"
        ))).fetchall()
    return {str(r[0]): str(r[1] or "") for r in rows}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="逗号分隔的表名，只处理这些")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    from main import create_app

    create_app()
    import asyncpg
    from pydantic import BaseModel

    from app.plugin.module_ai.query.service import AiQueryService

    cfg = await _ds_cfg()
    conn = await asyncpg.connect(host=cfg["host"], port=cfg["port"], database=cfg["database"],
                                 user=cfg["user"], password=cfg["password"])
    try:
        tables = await _candidates(conn)
        if args.only:
            want = {x.strip().upper() for x in args.only.split(",") if x.strip()}
            tables = [t for t in tables if t.upper() in want]
        if not args.force:
            desc = await _existing_desc()
            tables = [t for t in tables if not (desc.get(t.upper()) or "").strip()]
        if args.limit:
            tables = tables[: args.limit]

        class ColOut(BaseModel):
            name: str = ""
            description: str = ""

        class TableOut(BaseModel):
            alias: str = ""
            description: str = ""
            columns: list[ColOut] = []

        print(f"[plan] 待处理 {len(tables)} 张表；dry-run={args.dry_run}")
        if args.dry_run:
            for t in tables:
                print("  -", t)
            return

        actor = int(getattr(_auth().user, "id", 1) or 1)
        done = skipped = failed = 0
        for i, table in enumerate(tables, 1):
            cols = await _columns(conn, table)
            total, prof = await _profile(conn, table, cols)
            if total == 0:
                skipped += 1
                continue
            try:
                out = await AiQueryService._llm_structured(
                    _prompt(table, total, cols, prof), TableOut,
                    temperature=0, max_tokens=1500, tag="aistation-table-glossary")
                data = out.model_dump()
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL {i}/{len(tables)} {table}: {str(e)[:90]}")
                continue
            col_desc = {str(c.get("name") or ""): str(c.get("description") or "")
                        for c in (data.get("columns") or [])}
            changed, ncol = await _save(
                table, str(data.get("alias") or "").strip(),
                str(data.get("description") or "").strip(), col_desc,
                args.force, actor)
            if changed:
                done += 1
                print(f"OK   {i}/{len(tables)} {table} | {data.get('alias')} | "
                      f"cols={ncol}")
            else:
                skipped += 1
        print(f"[done] 更新 {done} 张、跳过 {skipped} 张、失败 {failed} 张")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
