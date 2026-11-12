"""治理包导入导出：表别名/描述、本体对象别名、业务术语。

为什么要它（2026-11-12）：830 张表的别名只能一条条点；换环境（dev→prod）要重录。
这里给一个**可导出、可对比、可幂等导入**的 JSON 包：

    {
      "version": 1, "datasource": "ds:6",
      "assets": [{"table_name": "...", "alias": "...", "description": "..."}],
      "ontology_aliases": [{"code": "...", "aliases": ["...", "..."]}],
      "terms": [{"term": "...", "metric_key": "...", "field_path": "..."}]
    }

导入分两步：`apply=False` 只算差异（预演），`apply=True` 才落库；
导入**只更新包里有值的字段**，不会清空库里其它内容。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

BUNDLE_VERSION = 1


def _uuid() -> str:
    return str(uuid.uuid4())


def diff_rows(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, list[str]]:
    """纯逻辑：按 key 比较 existing / incoming（值为可比较的字符串或列表）。"""
    add, update, same = [], [], []
    for key, want in incoming.items():
        if key not in existing:
            add.append(key)
            continue
        if existing[key] == want:
            same.append(key)
        else:
            update.append(key)
    return {"add": add, "update": update, "same": same}


async def export_bundle(datasource: str = "ds:6") -> dict:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async def _rows(sql: str, params: dict | None = None) -> list:
        try:
            async with async_db_session() as db:
                return (await db.execute(text(sql), params or {})).fetchall()
        except Exception:  # noqa: BLE001
            return []

    assets = await _rows(
        "SELECT table_name, COALESCE(alias,''), COALESCE(description,'') "
        "FROM ai_query_assets WHERE is_deleted=false ORDER BY table_name")
    objs = await _rows(
        "SELECT code, COALESCE(name,''), COALESCE(CAST(aliases AS TEXT),'[]') "
        "FROM ai_ont_object WHERE is_deleted=false ORDER BY code")
    terms = await _rows(
        "SELECT term, COALESCE(metric_key,''), COALESCE(field_path,'') "
        "FROM ai_query_dictionary WHERE is_deleted=false AND datasource=:d ORDER BY term",
        {"d": datasource})

    out_objs = []
    for code, name, raw in objs:
        try:
            arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:  # noqa: BLE001
            arr = []
        out_objs.append({"code": code, "name": name, "aliases": [str(a) for a in arr]})

    return {
        "version": BUNDLE_VERSION,
        "datasource": datasource,
        "assets": [
            {"table_name": t, "alias": a, "description": d} for t, a, d in assets
        ],
        "ontology_aliases": out_objs,
        "terms": [{"term": t, "metric_key": m, "field_path": f} for t, m, f in terms],
    }


def _norm_aliases(v: Any) -> list[str]:
    if isinstance(v, str):
        v = v.replace("|", ",").split(",")
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


async def preview_bundle(bundle: dict, datasource: str = "ds:6") -> dict:
    """计算差异（不写库）：新增/更新/未变 各多少，附前几条样例。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async def _rows(sql: str, params: dict | None = None) -> list:
        """单表查询容错：表不存在（SQLite/精简库）时返回空，不让整包导出失败。"""
        try:
            async with async_db_session() as db:
                return (await db.execute(text(sql), params or {})).fetchall()
        except Exception:  # noqa: BLE001
            return []

    asset_rows = await _rows(
        "SELECT upper(table_name), COALESCE(alias,''), COALESCE(description,'') "
        "FROM ai_query_assets WHERE is_deleted=false")
    obj_rows = await _rows(
        "SELECT code, COALESCE(CAST(aliases AS TEXT),'[]') FROM ai_ont_object "
        "WHERE is_deleted=false")
    term_rows = await _rows(
        "SELECT term, COALESCE(metric_key,''), COALESCE(field_path,'') "
        "FROM ai_query_dictionary WHERE is_deleted=false AND datasource=:d",
        {"d": datasource})

    # 比较口径：去首尾空白 + 多值集合（库里可能同名不同大小写各存一行，
    # 那是**数据重复**，不该每轮都报成「更新」）
    cur_assets: dict[str, set[tuple[str, str]]] = {}
    for t, a, d in asset_rows:
        cur_assets.setdefault(str(t), set()).add(
            (str(a or "").strip(), str(d or "").strip()))
    want_assets: dict[str, set[tuple[str, str]]] = {}
    for row in bundle.get("assets") or []:
        t = str(row.get("table_name") or "").strip().upper()
        if t:
            want_assets.setdefault(t, set()).add((
                str(row.get("alias") or "").strip(),
                str(row.get("description") or "").strip(),
            ))

    cur_aliases: dict[str, set[str]] = {}
    for code, raw in obj_rows:
        try:
            arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:  # noqa: BLE001
            arr = []
        cur_aliases[str(code)] = set(arr)
    want_aliases: dict[str, set[str]] = {}
    for row in bundle.get("ontology_aliases") or []:
        code = str(row.get("code") or "").strip()
        if code:
            want_aliases[code] = set(_norm_aliases(row.get("aliases")))

    cur_terms: dict[str, set[tuple[str, str]]] = {}
    for t, m, f in term_rows:
        cur_terms.setdefault(str(t), set()).add(
            (str(m or "").strip(), str(f or "").strip()))
    want_terms: dict[str, set[tuple[str, str]]] = {}
    for row in bundle.get("terms") or []:
        t = str(row.get("term") or "").strip()
        if t:
            want_terms.setdefault(t, set()).add((
                str(row.get("metric_key") or "").strip(),
                str(row.get("field_path") or "").strip(),
            ))

    def _cmp(cur: dict, want: dict) -> dict:
        """`cur`/`want` 的值都是集合：包里那条已在库中 → 未变；否则算更新。"""
        add = [k for k in want if k not in cur]
        # 包里每条都在库中（子集）即「未变」；空集合等于空集合，不能判成更新
        upd = [k for k in want if k in cur and not want[k].issubset(cur[k])]
        dup = [k for k, v in cur.items() if len(v) > 1]
        return {
            "add": len(add), "update": len(upd),
            "same": len(want) - len(add) - len(upd),
            "samples": (add + upd)[:5],
            "duplicates": len(dup), "duplicate_keys": dup[:10],
        }

    missing_assets = [t for t in want_assets if t not in cur_assets]
    missing_codes = [c for c in want_aliases if c not in cur_aliases]
    return {
        "assets": _cmp(cur_assets, want_assets),
        "ontology_aliases": {
            **_cmp(cur_aliases, want_aliases),
            "unknown_codes": missing_codes[:10],
        },
        "terms": _cmp(cur_terms, want_terms),
        "unknown_tables": missing_assets[:10],
    }


async def import_bundle(bundle: dict, datasource: str = "ds:6", apply: bool = False) -> dict:
    """幂等导入。`apply=False` 只预演；只写包里有值的字段，不清空其它内容。"""
    summary = await preview_bundle(bundle, datasource)
    if not apply:
        return {"applied": False, **summary}

    from sqlalchemy import text

    from app.core.database import async_db_session

    changed = {"assets": 0, "ontology_aliases": 0, "terms": 0}
    for row in bundle.get("assets") or []:
        t = str(row.get("table_name") or "").strip()
        alias = str(row.get("alias") or "").strip()
        desc = str(row.get("description") or "").strip()
        if not t or not (alias or desc):
            continue
        async with async_db_session.begin() as db:
            res = await db.execute(text(
                "UPDATE ai_query_assets SET "
                "alias=CASE WHEN :a<>'' THEN :a ELSE alias END, "
                "description=CASE WHEN :d<>'' THEN :d ELSE description END, "
                "updated_time=CURRENT_TIMESTAMP WHERE upper(table_name)=upper(:t) AND is_deleted=false"
            ), {"a": alias, "d": desc, "t": t})
            changed["assets"] += res.rowcount or 0

    for row in bundle.get("ontology_aliases") or []:
        code = str(row.get("code") or "").strip()
        add = _norm_aliases(row.get("aliases"))
        if not code or not add:
            continue
        async with async_db_session.begin() as db:
            cur = (await db.execute(text(
                "SELECT COALESCE(CAST(aliases AS TEXT),'[]') FROM ai_ont_object "
                "WHERE code=:c AND is_deleted=false"
            ), {"c": code})).scalar()
            if cur is None:
                continue
            try:
                arr = json.loads(cur) if isinstance(cur, str) else (cur or [])
            except Exception:  # noqa: BLE001
                arr = []
            merged = [str(x) for x in arr]
            for a in add:
                if a not in merged:
                    merged.append(a)
            if merged != arr:
                await db.execute(text(
                    "UPDATE ai_ont_object SET aliases=:a, updated_time=CURRENT_TIMESTAMP "
                    "WHERE code=:c AND is_deleted=false"
                ), {"a": json.dumps(merged, ensure_ascii=False), "c": code})
                changed["ontology_aliases"] += 1

    for row in bundle.get("terms") or []:
        term = str(row.get("term") or "").strip()
        mk = str(row.get("metric_key") or "").strip()
        fp = str(row.get("field_path") or "").strip()
        if not term:
            continue
        async with async_db_session.begin() as db:
            res = await db.execute(text(
                "UPDATE ai_query_dictionary SET "
                "metric_key=CASE WHEN :m<>'' THEN :m ELSE metric_key END, "
                "field_path=CASE WHEN :f<>'' THEN :f ELSE field_path END, updated_time=CURRENT_TIMESTAMP "
                "WHERE datasource=:d AND term=:t AND is_deleted=false"
            ), {"m": mk, "f": fp, "d": datasource, "t": term})
            if not res.rowcount:
                await db.execute(text(
                    "INSERT INTO ai_query_dictionary(datasource,term,metric_key,field_path,type,"
                    "is_deleted,uuid,status,created_time,updated_time) "
                    "VALUES (:d,:t,:m,:f,'term',false,:u,'0',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {"d": datasource, "t": term, "m": mk, "f": fp, "u": _uuid()})
                changed["terms"] += 1
            else:
                changed["terms"] += res.rowcount
    return {"applied": True, **summary, "changed": changed}


__all__ = ["BUNDLE_VERSION", "export_bundle", "preview_bundle", "import_bundle", "diff_rows"]
