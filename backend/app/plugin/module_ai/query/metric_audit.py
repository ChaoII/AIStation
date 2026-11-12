"""治理体检（只读）：找出脏指标、抢答题，以及**悬空引用**（指向已不存在的东西）。

供 `GET /ai/query/metrics/audit` 与 `scripts/audit_metrics.py` 共用；
停用/改名/补别名由界面上的操作完成，这里只负责**发现**。

两类体检：

1. **可疑指标**：名字像机器拼的（带字段码、「表名+聚合」、过长），或者绑定了对象
   却没有对象（SQL 是 `SELECT 1`），以及**抢答**——留出集/题库里本该走 SQL 的问题被
   指标快路径接走。
2. **悬空引用**：指标绑的对象不存在、指标/实体映射/本体对象/术语指向资产目录里
   没有的表。换数据源、删表、改名之后最容易出现，表现是「问数突然答错但没人报错」。
"""
from __future__ import annotations

import re

FIELD_CODE_RE = re.compile(r"[A-Z][A-Z0-9_]{3,}")
AGG_SUFFIX_RE = re.compile(r"(合计|总和|数量|计数|平均值|最大值|最小值|记录数)$")
TABLE_WORD_RE = re.compile(r"(明细表|主表|表)")
#: 金标 SQL 里引用的表（FROM/JOIN），用于判断「指标绑的表是不是这题该查的表」
GOLD_TABLE_RE = re.compile(r"\b(?:FROM|JOIN)\s+\"?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _norm_table(name: str) -> str:
    """表名归一：大写、去空白、去本体影子前缀 `ont_`。"""
    n = str(name or "").strip().upper()
    return n[4:] if n.startswith("ONT_") else n


def _reasons(m: dict) -> list[str]:
    out: list[str] = []
    name = str(m.get("name") or "")
    if FIELD_CODE_RE.search(name):
        out.append("名字里带字段码")
    if TABLE_WORD_RE.search(name) and AGG_SUFFIX_RE.search(name):
        out.append("「表名+聚合」拼装")
    if len(name) > 16:
        out.append("名字过长")
    tpl = str(m.get("sql_template") or "")
    if not m.get("object_code") and "FROM" not in tpl.upper():
        out.append("绑定型但没对象（SQL 是 SELECT 1）")
    return out


def _add_table(store: set[str], name) -> None:
    """登记表名，并去掉本体影子表前缀 `ont_`（资产/对象常以 ont_X 命名，实际表是 X）。"""
    n = str(name or "").strip().upper()
    if not n:
        return
    store.add(n)
    if n.startswith("ONT_"):
        store.add(n[4:])


async def _known_tables(datasource: str) -> set[str]:
    """「引用是否有效」的标准 = 资产目录 ∪ 当前数据源的 schema 同步表。

    只看资产目录会误报：不少表（如 CMCS_APPVERSION）在 schema 里正常同步，
    但没被收进资产目录；资产里又常以 `ont_X` 形式存在。
    """
    from sqlalchemy import text

    from app.core.database import async_db_session_fresh as async_db_session

    store: set[str] = set()
    try:
        async with async_db_session() as db:
            rows = (await db.execute(text(
                "SELECT table_name FROM ai_query_assets WHERE is_deleted=false"
            ))).fetchall()
            rows2 = (await db.execute(text(
                "SELECT table_name FROM ai_query_schema "
                "WHERE is_deleted=false AND datasource=:d"
            ), {"d": datasource})).fetchall()
        for (t,) in list(rows) + list(rows2):
            _add_table(store, t)
    except Exception:  # noqa: BLE001 - 精简库/SQLite 没有这些表
        return store
    return store


async def _ont_objects(datasource: str) -> dict[str, dict]:
    """本体对象 → 支撑表。

    ⚠️ `ai_ont_object.datasource_id` 是 **integer**（数据源表主键），
    早先写成 `COALESCE(datasource_id,'')` 会报类型错误；而错误被吞掉后
    会在**请求复用的事务**里留下 aborted 状态，导致后续查询全部「静默失败」
    （实测：接口里 dangling 恒为 0，新进程里却是 1）。所以这里必须 CAST。
    """
    from sqlalchemy import text

    from app.core.database import async_db_session_fresh as async_db_session

    try:
        async with async_db_session() as db:
            ds_id = (await db.execute(text(
                "SELECT id FROM ai_query_datasources WHERE 'ds:' || id = :d AND is_deleted=false"
            ), {"d": datasource})).scalar()
            rows = (await db.execute(text(
                "SELECT code, COALESCE(backing_table,''), "
                "COALESCE(CAST(datasource_id AS TEXT),'') "
                "FROM ai_ont_object WHERE is_deleted=false"
            ))).fetchall()
        want = str(ds_id) if ds_id is not None else ""
        return {
            str(c): {"table": str(t or ""), "datasource": str(d or "")}
            for c, t, d in rows
            if not want or not d or str(d) == want
        }
    except Exception:  # noqa: BLE001
        return {}


async def _terms(datasource: str) -> list[dict]:
    from sqlalchemy import text

    from app.core.database import async_db_session_fresh as async_db_session

    try:
        async with async_db_session() as db:
            rows = (await db.execute(text(
                "SELECT term, COALESCE(field_path,'') FROM ai_query_dictionary "
                "WHERE is_deleted=false AND datasource=:d"
            ), {"d": datasource})).fetchall()
        return [{"term": str(t or ""), "field_path": str(f or "")} for t, f in rows]
    except Exception:  # noqa: BLE001
        return []


async def _dangling(datasource: str, metrics: list[dict]) -> list[dict]:
    """悬空引用：引用目标在资产目录/本体里找不到。"""
    from . import metric_rules as M
    from .service import AiQueryService as S

    tables = await _known_tables(datasource)
    ont = await _ont_objects(datasource)
    out: list[dict] = []

    def _bad_table(name: str) -> bool:
        n = str(name or "").strip().upper()
        if not n or not tables:
            return False
        return n not in tables and n.removeprefix("ONT_") not in tables

    for m in metrics:
        code = str(m.get("object_code") or "")
        if code and ont and code not in ont:
            out.append({
                "kind": "metric_object", "ref": m["key"], "name": m.get("name") or "",
                "detail": f"绑定的本体对象 {code} 不存在",
                "fix": "指标页改绑对象，或本体页恢复该对象",
            })
            continue
        table = M.metric_main_table(m) or (ont.get(code, {}).get("table") if code else "")
        if _bad_table(table):
            out.append({
                "kind": "metric_table", "ref": m["key"], "name": m.get("name") or "",
                "detail": f"引用的表 {table} 不在资产目录/当前数据源 schema",
                "fix": "资产页补该表，或指标页改口径/停用",
            })

    # 实体映射 → 表
    try:
        cfg = await S._cfg()
        emap = S._cfg_entity_map(cfg)
    except Exception:  # noqa: BLE001
        emap = {}
    for noun, ts in (emap or {}).items():
        for t in ts or []:
            if _bad_table(t):
                out.append({
                    "kind": "entity_map", "ref": noun, "name": "",
                    "detail": f"实体映射「{noun}」指向的表 {t} 不在资产目录",
                    "fix": "问数设置 →「实体映射」改表或删掉这一条",
                })

    # 本体对象 → 支撑表（_ont_objects 已按数据源过滤）
    for code, info in ont.items():
        if _bad_table(info["table"]):
            out.append({
                "kind": "ontology_table", "ref": code, "name": "",
                "detail": f"本体对象支撑表 {info['table']} 不在资产目录",
                "fix": "本体页改支撑表，或确认是不是换数据源后没重绑",
            })

    # 术语 → 字段路径（形如 TABLE.COLUMN）
    terms = await _terms(datasource)
    for it in terms:
        fp = str(it.get("field_path") or "").strip()
        if not fp:
            continue
        head = fp.split(".")[0].strip().upper()
        if _bad_table(head):
            out.append({
                "kind": "term_field", "ref": it.get("term") or "", "name": "",
                "detail": f"术语的字段路径 {fp} 指向的表 {head} 不在资产目录",
                "fix": "问数设置 →「术语」改字段路径或删掉这一条",
            })
    return out


async def audit_metrics(
    datasource: str = "ds:6",
    top: int = 100,
    dataset: str | None = None,
    include_dangling: bool = True,
) -> dict:
    """指标体检。`dataset` 为空 = 扫描该数据源**全部**题库（原来只扫两个留出集）。"""
    from . import metric_rules as M
    from .eval_set import list_cases
    from .service import AiQueryService as S

    metrics = [m for m in await S.list_metrics(datasource) if m.get("enabled")]
    try:
        cases = await list_cases(datasource=datasource, dataset=dataset, enabled=True)
    except Exception:  # noqa: BLE001
        cases = []
    aliases = await S._metric_alias_map()
    ont = await _ont_objects(datasource)

    def _bound_table(m: dict) -> str:
        return M.metric_main_table(m) or ont.get(str(m.get("object_code") or ""), {}).get("table", "")

    hits: dict[str, list[str]] = {}
    matched = 0
    for c in cases:
        q = c["question"]
        got = M.match_metric(q, metrics, [], [], {}, table_alias=aliases)
        if not got:
            continue
        matched += 1
        # 只算**真的会走快路径且答错**的：快路径准入不拦，但金标查的表不是该指标的绑定表
        try:
            if M.fast_path_blockers(q, got):
                continue
        except Exception:  # noqa: BLE001
            pass
        mt = _norm_table(_bound_table(got))
        gold = {_norm_table(t) for t in GOLD_TABLE_RE.findall(str(c.get("gold_sql") or ""))}
        if mt and gold and mt not in gold:
            hits.setdefault(got["key"], []).append(q)

    rows = []
    for m in metrics:
        rs = _reasons(m)
        if not rs:
            continue
        rows.append({
            "key": m["key"], "name": m.get("name") or "", "agg": m.get("agg") or "",
            "table": M.metric_main_table(m) or (m.get("object_code") or ""),
            "reasons": rs, "questions": hits.get(m["key"], []),
            "action": "disable" if hits.get(m["key"]) else "rename",
        })
    rows.sort(key=lambda r: (-len(r["questions"]), -len(r["reasons"]), r["key"]))

    dangling = await _dangling(datasource, metrics) if include_dangling else []
    dangling.sort(key=lambda d: (d["kind"], d["ref"]))
    datasets = sorted({str(c.get("dataset") or "") for c in cases})
    return {
        "total_metrics": len(metrics),
        "suspect": len(rows),
        "hijacking": sum(1 for r in rows if r["questions"]),
        "matched": matched,
        "items": rows[: max(1, int(top))],
        "total_cases": len(cases),
        "datasets_scanned": datasets,
        "dangling_total": len(dangling),
        "dangling": dangling[: max(1, int(top))],
    }


__all__ = ["audit_metrics"]
