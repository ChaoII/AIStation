"""血缘（第一步：表级）：从四种来源自动推断"谁依赖谁"。

为什么不复用 `ai_query_asset_columns.related_table`
--------------------------------------------------
那个字段是**人工维护的外键配置**，是权威数据。把自动推断写回去，人工配置和
机器猜测就混在一起，以后分不清谁对。本模块只读产出到 `ai_query_lineage`，
人工字段一个都不碰。

四种来源（见 `docs/superpowers/specs/2026-11-04-ontology-lineage-design.md`）：

    fk     真外键            置信度 1.0
    view   视图 → 基表同名列  置信度 0.9
    name   XXXID → 表 *XXX    置信度 0.6（**只收唯一匹配**）
    usage  表.列被谁使用       置信度 1.0（指标 / 报表 / 历史问数）

原则：**宁缺勿错**。解析失败返回空集、只记 warning，绝不让一条脏 SQL 把整次重算打断。
"""
from __future__ import annotations

import json
from typing import NamedTuple

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.logger import log

from .ddl_dialect import cast_text, ddl_for_dialect


class Edge(NamedTuple):
    """一条血缘边：`src → dst`。`usage` 边没有 dst，用 ref_kind/ref_key 表示"被谁用"。"""

    kind: str                     # fk | view | name | usage
    src_table: str
    src_column: str | None = None
    dst_table: str | None = None
    dst_column: str | None = None
    ref_kind: str | None = None   # usage: metric | report | ask
    ref_key: str | None = None
    confidence: float = 1.0


#: 开关关闭时返回的固定空结构（避免调用方各自造 dict）
EMPTY_LINEAGE: dict = {
    "upstream": [],
    "downstream": [],
    "used_by": [],
    "sensitive_columns": [],
    "sensitive_downstream": [],
}


def infer_name_edges(columns_by_table: dict[str, set[str]]) -> list[Edge]:
    """列 `XXXID` → 表名以 `XXX` 结尾的表。

    **只收唯一匹配**：`ID`、`USERID`、`CREATEDID` 这类列在多张表上都可能成立，
    连错了比不连更糟（影响分析会给出假答案）。真外键（`fk`）不受此限。
    """
    table_names = sorted(columns_by_table)
    edges: list[Edge] = []
    for table, cols in columns_by_table.items():
        for col in cols:
            if col == "ID" or not col.endswith("ID") or len(col) <= 3:
                continue
            base = col[:-2].rstrip("_")
            if not base:
                continue
            cands = [tn for tn in table_names if tn.endswith(base) and tn != table]
            if len(cands) != 1:
                continue
            edges.append(Edge("name", table, col, cands[0], "ID", confidence=0.6))
    return edges


def tables_in_sql(sql: str) -> set[str]:
    """SQL 里出现的表名（大写）。解析失败返回空集 —— 脏 SQL 不该打断重算。"""
    if not sql or not sql.strip():
        return set()
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # pragma: no cover - 依赖缺失时降级
        return set()
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        return set()
    return {t.name.upper() for t in tree.find_all(exp.Table) if t.name}


def resolve_columns(sql: str, columns_by_table: dict[str, set[str]]) -> list[tuple[str, str]]:
    """把 SQL 解析成**真实的 (表, 列)** 列表（第二步：正规列解析）。

    相比第一步的"列名在文本里出现就算"，这里解决了四种串表/漏算：

    1. **别名**：`FROM "T" b ... b."COL"` → (T, COL)，而不是把 `b` 当表；
    2. **单表未限定**：`SELECT COL FROM "T"` → (T, COL)；多表时若该列在**多张表**
       都有 → 视为歧义，**不猜**（宁可少连）；
    3. **`SELECT *`**：展开成该表全部列（`COUNT(*)` 不算 —— 它是计数不是取列）；
    4. **CTE / 子查询别名**：`WITH x AS (...) SELECT * FROM x` 里的 `x` 不是真表，
       表名一律以 `columns_by_table` 里存在的为准。

    解析失败返回空列表：脏 SQL 不该打断重算。
    """
    if not sql or not sql.strip() or not columns_by_table:
        return []
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # pragma: no cover
        return []
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        return []

    cte_names = {c.alias_or_name.upper() for c in tree.find_all(exp.CTE)}
    out: set[tuple[str, str]] = set()

    for sel in tree.find_all(exp.Select):
        # 这个 SELECT **直接**引用的真实表：别名 → 表名
        alias_to_table: dict[str, str] = {}
        for t in sel.find_all(exp.Table):
            if t.find_ancestor(exp.Select) is not sel:
                continue
            name = (t.name or "").upper()
            if not name or name in cte_names or name not in columns_by_table:
                continue
            alias_to_table[(t.alias_or_name or name).upper()] = name
        if not alias_to_table:
            continue
        real_tables = sorted(set(alias_to_table.values()))

        # `SELECT *` / `t.*`：展开；`COUNT(*)` 里的星号排除
        for star in sel.find_all(exp.Star):
            if star.find_ancestor(exp.Select) is not sel:
                continue
            if star.find_ancestor(exp.Count) is not None:
                continue
            parent = star.parent
            qual = ""
            if isinstance(parent, exp.Column):
                qual = (parent.table or "").upper()
            for alias, table in alias_to_table.items():
                if qual and qual != alias:
                    continue
                for col in columns_by_table[table]:
                    out.add((table, col))

        for col in sel.find_all(exp.Column):
            if isinstance(col.this, exp.Star):
                continue
            cname = (col.name or "").upper()
            if not cname:
                continue
            qual = (col.table or "").upper()
            if qual:
                table = alias_to_table.get(qual)
                if table and cname in columns_by_table[table]:
                    out.add((table, cname))
                continue
            cands = [t for t in real_tables if cname in columns_by_table[t]]
            if len(cands) == 1:          # 唯一命中才认，多表都有 → 不猜
                out.add((cands[0], cname))
    return sorted(out)


def columns_used(sql: str, table: str, columns: set[str]) -> set[str]:
    """向后兼容的薄封装：只关心一张表时用。

    ⚠️ 内部走 `resolve_columns` —— 多表 SQL 请直接用后者，否则只能拿到
    这张表自己的列（这正是第一步串表的原因）。
    """
    if not sql or not columns:
        return set()
    return {c for t, c in resolve_columns(sql, {table.upper(): set(columns)})
            if t == table.upper()}


# ---------------------------------------------------------------------------
# 落库
# ---------------------------------------------------------------------------

_DDL = (
    """CREATE TABLE IF NOT EXISTS ai_query_lineage (
        id            BIGSERIAL PRIMARY KEY,
        datasource    VARCHAR(64)  NOT NULL,
        kind          VARCHAR(16)  NOT NULL,
        src_table     VARCHAR(128) NOT NULL,
        src_column    VARCHAR(128),
        dst_table     VARCHAR(128),
        dst_column    VARCHAR(128),
        ref_kind      VARCHAR(16),
        ref_key       VARCHAR(255),
        confidence    REAL         NOT NULL DEFAULT 1.0,
        is_deleted    BOOLEAN      NOT NULL DEFAULT FALSE,
        created_time  TIMESTAMP    NOT NULL DEFAULT now(),
        updated_time  TIMESTAMP    NOT NULL DEFAULT now()
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_query_lineage
       ON ai_query_lineage (datasource, kind, src_table,
                            COALESCE(src_column,''), COALESCE(dst_table,''),
                            COALESCE(dst_column,''), COALESCE(ref_key,''))""",
    "CREATE INDEX IF NOT EXISTS ix_ai_query_lineage_src "
    "ON ai_query_lineage (datasource, src_table)",
    "CREATE INDEX IF NOT EXISTS ix_ai_query_lineage_dst "
    "ON ai_query_lineage (datasource, dst_table)",
)


async def ensure_lineage_table() -> None:
    """幂等建表（插件表不走 alembic，与 `ai_query_kg_relation` 一致）。

    ⚠️ 必须过 `ddl_for_dialect`：`BIGSERIAL` / `DEFAULT now()` 在 SQLite（测试库）
    是**语法错误**，不是"不生效"。项目已有这个转换器，别再手写方言分支。
    """
    async with async_db_session.begin() as db:
        for stmt in _DDL:
            await db.execute(text(ddl_for_dialect(stmt)))


async def _columns_by_table(datasource: str) -> dict[str, set[str]]:
    """本地已同步的 schema：`{表: {列}}`（`columns` 是 JSONB 数组）。"""
    async with async_db_session() as db:
        # `columns::text` 是 PG 专有写法，SQLite 报 `unrecognized token: ":"`
        # —— 用项目现成的 cast_text
        rows = (await db.execute(text(
            f"SELECT table_name, {cast_text('columns')} FROM ai_query_schema "
            "WHERE datasource=:d AND is_deleted=false"), {"d": datasource})).fetchall()
    out: dict[str, set[str]] = {}
    for table, raw in rows:
        try:
            labels = json.loads(raw or "[]")
        except Exception:  # noqa: BLE001
            labels = []
        cols = set()
        for lab in labels:
            name = lab.get("name") if isinstance(lab, dict) else str(lab).split("(", 1)[0]
            if name:
                cols.add(str(name).upper())
        out[(table or "").upper()] = cols
    return out


async def _fk_edges(datasource_id: int) -> list[Edge]:
    """真外键：子表.列 → 父表.列。燃料库几乎没有（全库 16 条），但最可信。"""
    from . import executor as _ex
    from .service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(datasource_id)
    rows = await _ex.execute_select(_ds_cfg_from_model(ds), """
        SELECT tc.table_name, kcu.column_name,
               ccu.table_name AS ref_table, ccu.column_name AS ref_col
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema='public'
    """, max_rows=20000)
    return [
        Edge("fk", str(t).upper(), str(c).upper(), str(rt).upper(), str(rc).upper(),
             confidence=1.0)
        for t, c, rt, rc in (rows.get("rows") or [])
    ]


async def _view_edges(datasource_id: int, columns_by_table: dict[str, set[str]]) -> list[Edge]:
    """视图 → 基表：视图定义里引用到的表，同名列算一条（同名才连，避免瞎猜）。"""
    from . import executor as _ex
    from .service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(datasource_id)
    cfg = _ds_cfg_from_model(ds)
    rows = (await _ex.execute_select(cfg, """
        SELECT table_name, view_definition FROM information_schema.views
        WHERE table_schema='public'
    """, max_rows=5000)).get("rows") or []
    if not rows:
        return []
    names = [str(r[0]).upper() for r in rows]
    # 视图自身的列（用来判断"同名列"）
    col_rows = (await _ex.execute_select(cfg, """
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema='public'
    """, max_rows=50000)).get("rows") or []
    view_cols: dict[str, set[str]] = {}
    for t, c in col_rows:
        view_cols.setdefault(str(t).upper(), set()).add(str(c).upper())

    edges: list[Edge] = []
    for vname, vdef in zip(names, [r[1] for r in rows], strict=False):
        for ref in tables_in_sql(vdef or ""):
            if ref not in columns_by_table:
                continue
            for col in view_cols.get(vname, set()) & columns_by_table[ref]:
                edges.append(Edge("view", vname, col, ref, col, confidence=0.9))
    return edges


async def _usage_edges(datasource: str, columns_by_table: dict[str, set[str]]) -> list[Edge]:
    """使用血缘：表.列被哪个指标 / 报表 / 问数用过（"谁在查这一列"）。"""
    async with async_db_session() as db:
        metrics = (await db.execute(text(
            "SELECT key, sql_template FROM ai_query_metrics "
            "WHERE datasource=:d AND is_deleted=false"), {"d": datasource})).fetchall()
        reports = (await db.execute(text(
            "SELECT key, sql_template FROM ai_report_template "
            "WHERE datasource=:d AND is_deleted=false"), {"d": datasource})).fetchall()
        asks = (await db.execute(text(
            "SELECT id, sql FROM ai_query_messages "
            "WHERE datasource=:d AND coalesce(sql,'')<>'' "
            "ORDER BY id DESC LIMIT 3000"), {"d": datasource})).fetchall()

    edges: list[Edge] = []
    sources = (
        [("metric", k, s) for k, s in metrics]
        + [("report", k, s) for k, s in reports]
        + [("ask", str(i), s) for i, s in asks]
    )
    for ref_kind, ref_key, sql in sources:
        if not sql:
            continue
        # 正规列解析：别名/CTE/`SELECT *` 都由 resolve_columns 处理。
        # 第一步的"列名在文本里出现就算"会串表（A 表的列被算到 B 表头上）。
        for table, col in resolve_columns(sql, columns_by_table):
            edges.append(Edge("usage", table, col, ref_kind=ref_kind,
                              ref_key=str(ref_key), confidence=1.0))
    return edges


def _dedupe(edges: list[Edge]) -> list[Edge]:
    """同一 (kind, src, dst, ref) 只留置信度最高的一条（对应唯一索引）。"""
    best: dict[tuple, Edge] = {}
    for e in edges:
        k = (e.kind, e.src_table, e.src_column, e.dst_table, e.dst_column, e.ref_key)
        cur = best.get(k)
        if cur is None or e.confidence > cur.confidence:
            best[k] = e
    return list(best.values())


async def rebuild_lineage(datasource_id: int) -> dict[str, int]:
    """幂等重算：先按数据源清空，再按四个来源重建。

    任何一步失败都只记 warning 并继续 —— 血缘是**增强**，不能因为它让
    schema 同步失败（同步本身是主流程）。
    """
    from .service import _ds_code

    await ensure_lineage_table()
    datasource = _ds_code(datasource_id)
    columns_by_table = await _columns_by_table(datasource)
    counts = {"fk": 0, "view": 0, "name": 0, "usage": 0}
    edges: list[Edge] = []

    for kind, fn in (
        ("fk", lambda: _fk_edges(datasource_id)),
        ("view", lambda: _view_edges(datasource_id, columns_by_table)),
        ("usage", lambda: _usage_edges(datasource, columns_by_table)),
    ):
        try:
            got = await fn()
            edges += got
            counts[kind] = len(got)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[lineage] {kind} 推断失败（忽略）: {str(e)[:120]}")

    try:
        named = [e for e in infer_name_edges(columns_by_table)
                 if e.src_table in columns_by_table]
        edges += named
        counts["name"] = len(named)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[lineage] name 推断失败（忽略）: {str(e)[:120]}")

    edges = _dedupe(edges)
    async with async_db_session.begin() as db:
        await db.execute(text("DELETE FROM ai_query_lineage WHERE datasource=:d"),
                         {"d": datasource})
        if edges:
            await db.execute(
                text(
                    "INSERT INTO ai_query_lineage(datasource,kind,src_table,src_column,"
                    "dst_table,dst_column,ref_kind,ref_key,confidence) VALUES "
                    "(:ds,:k,:st,:sc,:dt,:dc,:rk,:rkey,:cf) "
                    "ON CONFLICT DO NOTHING"
                ),
                [
                    {"ds": datasource, "k": e.kind, "st": e.src_table, "sc": e.src_column,
                     "dt": e.dst_table, "dc": e.dst_column, "rk": e.ref_kind,
                     "rkey": e.ref_key, "cf": e.confidence}
                    for e in edges
                ],
            )
    counts["total"] = len(edges)
    log.warning(f"[lineage] 重算完成 {datasource}：{counts}")
    return counts


# ---------------------------------------------------------------------------
# 按表查询
# ---------------------------------------------------------------------------

async def _sensitive_columns(datasource: str, table: str) -> list[str]:
    """该表被标敏感的列：资产目录 ∪ 本体属性。

    本体那半必须经 `ontology.semantic` 取 —— 问数**禁止直连读 ai_ont_***，
    `tests/test_ontology_query_bridge.py` 会扫源码断言。
    """
    cols: set[str] = set()
    try:
        async with async_db_session() as db:
            rows = (await db.execute(text(
                "SELECT column_name FROM ai_query_asset_columns "
                "WHERE UPPER(table_name)=:t AND sensitive=true AND is_deleted=false"),
                {"t": table})).fetchall()
        cols |= {str(r[0]).upper() for r in rows if r[0]}
    except Exception as e:  # noqa: BLE001
        log.warning(f"[lineage] 读资产敏感列失败（忽略）: {str(e)[:80]}")
    try:
        from app.plugin.module_ai.ontology import semantic as _sem

        table_map = await _sem.object_table_map()      # {表名或 ont_code: object_code}
        codes = {code for key, code in (table_map or {}).items()
                 if str(key).upper() == table}
        if codes:
            sens = await _sem.sensitive_fields()       # {object_code: {属性 code}}
            for code in codes:
                cols |= {str(c).upper() for c in (sens.get(code) or set())}
    except Exception as e:  # noqa: BLE001
        log.warning(f"[lineage] 读本体敏感列失败（忽略）: {str(e)[:80]}")
    return sorted(cols)


def propagate_sensitive(rows: list, table: str, sensitive_cols: list[str]) -> list[dict]:
    """敏感列沿血缘**传播一格**：谁在消费这张表的敏感列。

    `rows` 是 `(kind, src_table, src_column, dst_table, dst_column, ...)` 的数据库行。

    ⚠️ 方向必须按**锚点表在哪一侧**判断（踩过）：
      - 我 → 下游（`src_table == T`）：下游是 `dst`（子表引用我 / 我用 `XXXID` 指向别人）
      - 我 ← 上游（`dst_table == T`）：我是基表，**消费方是 `src`**（视图引用我）
    只认 src 一侧会把"视图 → 基表"的边算成基表传给自己（实测出现过
    `{"table": "FUEL_CB_COALBALANCE"}` 这种自指）。

    只做一格，不做多跳 —— 多跳误伤大，先看一格的实际效果。
    """
    t = str(table or "").upper()
    sens = {str(c).upper() for c in (sensitive_cols or [])}
    if not t or not sens:
        return []
    out: dict[tuple[str, str, str], None] = {}
    for row in rows:
        kind, src_table, src_column, dst_table, dst_column = row[:5]
        if src_table == t and str(src_column or "").upper() in sens and dst_table:
            out[(str(dst_table), str(dst_column or "").upper(), str(kind))] = None
        elif dst_table == t and str(dst_column or "").upper() in sens and src_table:
            out[(str(src_table), str(src_column or "").upper(), str(kind))] = None
    return [{"table": tb, "column": c, "via": k} for (tb, c, k) in sorted(out)]


async def lineage_for_table(datasource: str, table_name: str, strict: bool = False) -> dict:
    """一张表的血缘：上游（我依赖谁）/ 下游（谁依赖我）/ 被谁使用 / 敏感列。

    边方向是 `src → dst`，语义是「**src 依赖 dst**」（子表→父表、视图→基表、
    `XXXID`→候选表）。所以：
        上游 = src_table 是我的行 → dst
        下游 = dst_table 是我的行 → src
        被谁用 = kind='usage' 且 src_table 是我

    ``strict=True`` 时读库失败**上抛**：权限判定不能把"读不到血缘"当成"没有上游"
    （后者会让视图静默绕过基表限制），由 guard 转成 deny。
    """
    t = (table_name or "").upper()
    if not t:
        return dict(EMPTY_LINEAGE)
    try:
        async with async_db_session() as db:
            rows = (await db.execute(text(
                "SELECT kind, src_table, src_column, dst_table, dst_column, "
                "       ref_kind, ref_key, confidence "
                "FROM ai_query_lineage WHERE datasource=:d AND is_deleted=false "
                "AND (src_table=:t OR dst_table=:t)"), {"d": datasource, "t": t})).fetchall()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[lineage] 读血缘失败（返回空）: {str(e)[:80]}")
        if strict:
            raise
        return dict(EMPTY_LINEAGE)

    # 边是**列级**的：同一张视图/同一个指标会因为多列各出现一次。
    # 对外要的是"哪些对象依赖我"，所以按对象去重（置信度取最高）。
    upstream: dict[tuple[str, str], float] = {}
    downstream: dict[tuple[str, str], float] = {}
    used_by: dict[tuple[str, str], None] = {}
    for kind, src_t, _src_c, dst_t, _dst_c, ref_kind, ref_key, conf in rows:
        if kind == "usage":
            if src_t == t and ref_key:
                used_by[(str(ref_kind or ""), str(ref_key))] = None
            continue
        if src_t == t and dst_t:
            key = (dst_t, kind)
            upstream[key] = max(upstream.get(key, 0.0), float(conf))
        elif dst_t == t:
            key = (src_t, kind)
            downstream[key] = max(downstream.get(key, 0.0), float(conf))

    def _as_list(d: dict[tuple[str, str], float]) -> list[dict]:
        return [{"table": tbl, "kind": k, "confidence": round(c, 2)}
                for (tbl, k), c in sorted(d.items())]

    sensitive_cols = await _sensitive_columns(datasource, t)
    return {
        "upstream": _as_list(upstream),
        "downstream": _as_list(downstream),
        "used_by": [{"ref_kind": rk, "ref_key": rk_key, "kind": "usage"}
                    for (rk, rk_key) in sorted(used_by)],
        "sensitive_columns": sensitive_cols,
        # 敏感列被谁消费（下游一格）。用于回答"这列脱敏了，视图里还在裸奔吗"
        "sensitive_downstream": propagate_sensitive(rows, t, sensitive_cols),
    }


# ---------------------------------------------------------------------------
# 覆盖率
# ---------------------------------------------------------------------------

async def lineage_coverage(datasource: str) -> dict:
    """血缘覆盖率：多少表 / 多少列参与至少一条关系，按来源分布。

    分母来自本地已同步的 `ai_query_schema`（与用户看到的表一致），
    分子来自 `ai_query_lineage`。
    """
    columns_by_table = await _columns_by_table(datasource)
    tables_total = len(columns_by_table)
    columns_total = sum(len(v) for v in columns_by_table.values())

    async with async_db_session() as db:
        pairs = (await db.execute(text(
            "SELECT src_table, src_column, dst_table, dst_column, kind "
            "FROM ai_query_lineage WHERE datasource=:d AND is_deleted=false"),
            {"d": datasource})).fetchall()

    cols: set[tuple[str, str]] = set()
    tables: set[str] = set()
    by_kind: dict[str, int] = {}
    for src_t, src_c, dst_t, dst_c, kind in pairs:
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if src_t:
            tables.add(src_t)
        if src_c:
            cols.add((src_t, src_c))
        if dst_t:
            tables.add(dst_t)
        if dst_c:
            cols.add((dst_t, dst_c))
    return {
        "tables_total": tables_total,
        "tables_with_edges": len(tables),
        "columns_total": columns_total,
        "columns_with_edges": len(cols),
        "by_kind": by_kind,
    }


# ---------------------------------------------------------------------------
# 治理概览（看板用）
# ---------------------------------------------------------------------------

async def _sensitive_map(datasource: str) -> dict[str, set[str]]:
    """一次取全库敏感列：`{表: {列}}`（资产目录 ∪ 本体属性）。

    逐表调 `_sensitive_columns` 会 N 次查库；看板要的是全量，所以单独取一次。
    """
    out: dict[str, set[str]] = {}
    try:
        async with async_db_session() as db:
            rows = (await db.execute(text(
                "SELECT UPPER(table_name), UPPER(column_name) FROM ai_query_asset_columns "
                "WHERE sensitive=true AND is_deleted=false"))).fetchall()
        for t, c in rows:
            if t and c:
                out.setdefault(t, set()).add(c)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[lineage] 读资产敏感列失败（忽略）: {str(e)[:80]}")
    try:
        from app.plugin.module_ai.ontology import semantic as _sem

        table_map = await _sem.object_table_map()     # {表名或 ont_code: object_code}
        sens = await _sem.sensitive_fields()          # {object_code: {属性 code}}
        for key, code in (table_map or {}).items():
            props = sens.get(code) or set()
            if not props:
                continue
            out.setdefault(str(key).upper(), set()).update(str(p).upper() for p in props)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[lineage] 读本体敏感列失败（忽略）: {str(e)[:80]}")
    return out


async def governance_summary(datasource: str, limit: int = 200) -> dict:
    """治理看板数据：覆盖率 + 孤儿表 + 敏感列暴露。

    - **孤儿表**：既没有血缘、也没有资产描述、也没有敏感标记的表 ——
      这类表在最需要治理的时候最容易被漏掉（没人看、没人标、没人问）。
    - **敏感暴露**：敏感列被下游（视图/关联表）消费的情况，
      例如 `VIEW_GETBATCHPRICE` 在裸用 `COALPRICE`。
    """
    coverage = await lineage_coverage(datasource)
    columns_by_table = await _columns_by_table(datasource)

    async with async_db_session() as db:
        edge_tables = {
            str(r[0]).upper()
            for r in (await db.execute(text(
                "SELECT DISTINCT src_table FROM ai_query_lineage "
                "WHERE datasource=:d AND is_deleted=false "
                "UNION SELECT DISTINCT dst_table FROM ai_query_lineage "
                "WHERE datasource=:d AND is_deleted=false AND dst_table IS NOT NULL"),
                {"d": datasource})).fetchall()
            if r[0]
        }
        described = {
            str(r[0]).upper()
            for r in (await db.execute(text(
                "SELECT DISTINCT table_name FROM ai_query_assets "
                "WHERE is_deleted=false AND coalesce(description,'')<>''"))).fetchall()
            if r[0]
        }
        edges = (await db.execute(text(
            "SELECT kind, src_table, src_column, dst_table, dst_column "
            "FROM ai_query_lineage WHERE datasource=:d AND is_deleted=false "
            "AND kind<>'usage'"), {"d": datasource})).fetchall()

    sens_map = await _sensitive_map(datasource)
    marked = set(sens_map)

    orphans = sorted(set(columns_by_table) - edge_tables - described - marked)

    exposure: dict[tuple[str, str, str, str], None] = {}
    for kind, src_t, src_c, dst_t, dst_c in edges:
        src_t = str(src_t or "").upper()
        dst_t = str(dst_t or "").upper()
        if src_t in sens_map and str(src_c or "").upper() in sens_map[src_t] and dst_t:
            exposure[(dst_t, str(dst_c or "").upper(), kind, src_t)] = None
        if dst_t in sens_map and str(dst_c or "").upper() in sens_map[dst_t] and src_t:
            exposure[(src_t, str(src_c or "").upper(), kind, dst_t)] = None

    return {
        "coverage": coverage,
        "orphans": {
            "count": len(orphans),
            "tables": orphans[:limit],
        },
        "sensitive_exposure": {
            "count": len(exposure),
            "items": [
                {"table": t, "column": c, "via": k, "from": frm}
                for (t, c, k, frm) in sorted(exposure)[:limit]
            ],
        },
    }
