"""索引（Indexing）：让本体数据可被快速检索。

对齐官方 `object-indexing/*`：

- *"**indexing** is the process of making tabular or other forms of data in Foundry
  datasources available for **faster data retrieval operations** through specialized databases."*
- 由 **Funnel** 服务编排流水线；两种流水线：**batch** 与 **streaming**（另有 direct datasources）。
- 状态在 Ontology Manager 的流水线图里看：*"A **green tick** in the Object Storage v2 node …
  indicates that the indexing is complete and the object type is ready to be queried."*
- 失败重试：*"If a job fails due to a **transient error** … OSv2 will **automatically retry**
  the job after approximately **five minutes**. If OSv2 detects that the job failed
  **terminally** … it will automatically retry only when **new data is available**."*
- 限制：索引大小受存储空间限制；streaming 吞吐 **2 MB/s per object type**；
  不支持写部分行；CDC 支持增改删。

**我们的实现**：索引是**真的**——在对象类型的支撑表上建 PostgreSQL 索引
（`CREATE INDEX`），并记录行数、大小、构建次数与失败原因。
状态机与自动重试策略照官方语义实现。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.core.exceptions import CustomException

from . import service as _svc

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
ONT_INDEX_STATUS = ("not_started", "building", "ready", "failed", "stale")
ONT_INDEX_STATUS_LABEL = {
    "not_started": "未开始", "building": "构建中", "ready": "就绪",
    "failed": "失败", "stale": "已过期",
}
#: 官方两种流水线 + direct
ONT_PIPELINE_KINDS = ("batch", "streaming", "direct")
ONT_PIPELINE_LABEL = {"batch": "批量流水线", "streaming": "流式流水线", "direct": "直连数据源"}

ONT_INDEX_KINDS = ("primary", "property", "full_text", "link")
ONT_INDEX_KIND_LABEL = {
    "primary": "主键索引", "property": "属性索引",
    "full_text": "全文索引", "link": "关系索引",
}

#: 官方：失败后约 5 分钟自动重试
AUTO_RETRY_MINUTES = 5
#: 官方：streaming 每对象类型 2 MB/s
STREAMING_MAX_BYTES_PER_SEC = 2 * 1024 * 1024


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_index(row) -> dict:
    (i, oc, pc, kind, st, pk, name, rc, size, bc, lb, err, ar, en) = row
    return {
        "id": i, "object_code": oc, "prop_code": pc or "", "index_kind": kind,
        "index_kind_label": ONT_INDEX_KIND_LABEL.get(kind, kind),
        "status": st, "status_label": ONT_INDEX_STATUS_LABEL.get(st, st),
        "pipeline_kind": pk,
        "pipeline_label": ONT_PIPELINE_LABEL.get(pk, pk),
        "index_name": name or "", "row_count": int(rc or 0),
        "size_bytes": int(size or 0),
        "size_human": _human(int(size or 0)),
        "build_count": int(bc or 0),
        "last_built_at": lb.strftime("%Y-%m-%d %H:%M:%S") if isinstance(lb, datetime) else (lb or ""),
        "last_error": err or "",
        "auto_retry_at": (ar.strftime("%Y-%m-%d %H:%M:%S")
                          if isinstance(ar, datetime) else (ar or "")),
        "enabled": bool(en),
        # 官方：状态就绪 = 可以查询（绿勾）
        "ready": st == "ready",
    }


def _human(n: int) -> str:
    for unit, div in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


_INDEX_COLS = ("SELECT id,object_code,COALESCE(prop_code,''),COALESCE(index_kind,'property'),"
               "COALESCE(status,'not_started'),COALESCE(pipeline_kind,'batch'),"
               "COALESCE(index_name,''),COALESCE(row_count,0),COALESCE(size_bytes,0),"
               "COALESCE(build_count,0),last_built_at,COALESCE(last_error,''),"
               "auto_retry_at,enabled FROM ai_ont_index ")


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
async def list_indexes(object_code: str | None = None,
                       status: str = "") -> list[dict]:
    sql = _INDEX_COLS + "WHERE is_deleted=false"
    p: dict = {}
    if object_code:
        sql += " AND object_code=:o"
        p["o"] = object_code
    if status:
        sql += " AND status=:s"
        p["s"] = status
    sql += " ORDER BY object_code, index_kind, prop_code, id"
    return [_row_to_index(r) for r in (await _svc._exec(sql, p)).fetchall()]


async def index_summary() -> dict:
    """总览：各状态计数 + 按对象类型聚合（供列表页那一列用）。"""
    rows = await list_indexes()
    by_status: dict[str, int] = dict.fromkeys(ONT_INDEX_STATUS, 0)
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    per_object: dict[str, dict] = {}
    for r in rows:
        d = per_object.setdefault(r["object_code"], {
            "object_code": r["object_code"], "total": 0, "ready": 0, "failed": 0,
            "bytes": 0, "rows": 0})
        d["total"] += 1
        d["ready"] += 1 if r["status"] == "ready" else 0
        d["failed"] += 1 if r["status"] == "failed" else 0
        d["bytes"] += r["size_bytes"]
        d["rows"] += r["row_count"]
    objs = await _svc.list_objects()
    name_of = {o["code"]: o.get("name") or o["code"] for o in objs}
    per_list = sorted(per_object.values(), key=lambda x: x["object_code"])
    for d in per_list:
        d["object_name"] = name_of.get(d["object_code"], d["object_code"])
        d["size_human"] = _human(d["bytes"])
        d["all_ready"] = d["total"] > 0 and d["ready"] == d["total"]
    return {"ok": True, "total": len(rows), "by_status": by_status,
            "by_status_label": {ONT_INDEX_STATUS_LABEL.get(k, k): v
                                for k, v in by_status.items()},
            "objects": per_list, "object_count": len(per_list),
            "total_bytes": sum(r["size_bytes"] for r in rows),
            "total_size_human": _human(sum(r["size_bytes"] for r in rows)),
            "total_rows": sum(r["row_count"] for r in rows),
            "status_meta": [{"value": s, "label": ONT_INDEX_STATUS_LABEL[s]}
                            for s in ONT_INDEX_STATUS],
            "pipeline_meta": [{"value": s, "label": ONT_PIPELINE_LABEL[s]}
                              for s in ONT_PIPELINE_KINDS],
            "kind_meta": [{"value": s, "label": ONT_INDEX_KIND_LABEL[s]}
                          for s in ONT_INDEX_KINDS]}


# ---------------------------------------------------------------------------
# 写入：定义索引
# ---------------------------------------------------------------------------
def _pg_index_name(object_code: str, prop_code: str, kind: str) -> str:
    raw = f"ix_ont_{object_code}_{prop_code or 'pk'}_{kind}"
    safe = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in raw)
    return safe[:60].lower()


async def upsert_index(data: dict) -> dict:
    object_code = str(data.get("object_code") or "").strip()
    if not object_code:
        raise CustomException(msg="必须指定对象类型")
    prop_code = str(data.get("prop_code") or "").strip()
    kind = str(data.get("index_kind") or ("primary" if not prop_code else "property"))
    if kind not in ONT_INDEX_KINDS:
        raise CustomException(msg=f"索引种类不支持 {kind}")
    pipeline = str(data.get("pipeline_kind") or "batch")
    if pipeline not in ONT_PIPELINE_KINDS:
        raise CustomException(msg=f"流水线类型不支持 {pipeline}")
    if prop_code:
        props = await _svc.list_properties(object_code)
        if prop_code not in {p["code"] for p in props}:
            raise CustomException(msg=f"属性 {prop_code} 不属于 {object_code}")
    exist = (await _svc._exec(
        "SELECT id FROM ai_ont_index WHERE object_code=:o AND prop_code=:p "
        "AND index_kind=:k AND is_deleted=false",
        {"o": object_code, "p": prop_code, "k": kind})).fetchone()
    name = _pg_index_name(object_code, prop_code, kind)
    if exist:
        await _svc._exec_write(
            "UPDATE ai_ont_index SET pipeline_kind=:pk, enabled=:en, index_name=:n "
            "WHERE id=:id",
            {"pk": pipeline, "en": bool(data.get("enabled", True)), "n": name,
             "id": exist[0]})
        return {"ok": True, "id": exist[0], "msg": "索引定义已更新"}
    r = await _svc._exec_write(
        "INSERT INTO ai_ont_index(object_code,prop_code,index_kind,status,pipeline_kind,"
        "index_name,enabled) VALUES (:o,:p,:k,'not_started',:pk,:n,:en) RETURNING id",
        {"o": object_code, "p": prop_code, "k": kind, "pk": pipeline, "n": name,
         "en": bool(data.get("enabled", True))})
    await _svc._log_change(object_code, "index", "create",
                           f"索引 {name}（{ONT_INDEX_KIND_LABEL.get(kind, kind)}）")
    return {"ok": True, "id": r.scalar(), "index_name": name,
            "msg": f"索引「{ONT_INDEX_KIND_LABEL.get(kind, kind)}」已创建（尚未构建）"}


async def remove_index(index_id: int) -> dict:
    row = (await _svc._exec(
        "SELECT object_code,COALESCE(index_name,'') FROM ai_ont_index WHERE id=:i",
        {"i": int(index_id)})).fetchone()
    if not row:
        raise CustomException(msg="索引不存在")
    await _drop_pg_index(row[1])
    await _svc._exec_write("UPDATE ai_ont_index SET is_deleted=true WHERE id=:i",
                           {"i": int(index_id)})
    return {"ok": True, "msg": "索引已删除（底层索引也已移除）"}


async def _drop_pg_index(name: str) -> None:
    if not name:
        return
    try:
        await _svc._exec_write(f'DROP INDEX IF EXISTS "{_svc._safe_ident(name)}"', {})
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# 构建：真的在支撑表上建索引
# ---------------------------------------------------------------------------
async def build_index(index_id: int) -> dict:
    """构建一个索引（**真的执行 CREATE INDEX**）。

    官方语义：成功后状态变为就绪（绿勾）；失败分两类——
    瞬时错误排 5 分钟后自动重试；终态错误只等新数据。
    """
    row = (await _svc._exec(
        "SELECT object_code,COALESCE(prop_code,''),COALESCE(index_kind,'property'),"
        "COALESCE(index_name,''),COALESCE(build_count,0) FROM ai_ont_index WHERE id=:i",
        {"i": int(index_id)})).fetchone()
    if not row:
        raise CustomException(msg="索引不存在")
    object_code, prop_code, kind, name, bc = row[0], row[1], row[2], row[3], int(row[4] or 0)

    meta = await _svc._instance_meta(object_code)
    if not meta or meta.get("error"):
        return await _fail(index_id, object_code, name, "对象类型元数据不可用", terminal=True)
    if not meta.get("materialized"):
        return await _fail(index_id, object_code, name,
                           f"对象类型未物化（无支撑表 {meta.get('backing_table') or ''}），无法建索引",
                           terminal=True)

    table = _svc._safe_ident(meta["table"])
    await _svc._exec_write(
        "UPDATE ai_ont_index SET status='building', last_error='' WHERE id=:i",
        {"i": int(index_id)})
    try:
        if kind == "full_text" and _svc._dialect() == "postgresql":
            # gin + to_tsvector 是 Postgres 专属；其它方言退回普通索引
            col = _svc._safe_ident(prop_code or meta["name_prop"])
            await _svc._exec_write(
                f'CREATE INDEX IF NOT EXISTS "{_svc._safe_ident(name)}" ON "{table}" '
                f"USING gin (to_tsvector('simple', "
                f"COALESCE({_svc._cast_text(chr(34) + col + chr(34))}, '')))", {})
        else:
            col = _svc._safe_ident(prop_code or meta["key_prop"])
            await _svc._exec_write(
                f'CREATE INDEX IF NOT EXISTS "{_svc._safe_ident(name)}" ON "{table}" '
                f'("{col}")', {})
    except Exception as e:  # noqa: BLE001
        return await _fail(index_id, object_code, name, str(e)[:200], terminal=True)

    # 统计行数与占用（真实数据）
    rows, size = 0, 0
    try:
        rows = int((await _svc._exec(f'SELECT count(*) FROM "{table}"', {})).scalar() or 0)
        if _svc._dialect() == "postgresql":
            sz = (await _svc._exec(
                "SELECT pg_total_relation_size(:t)", {"t": meta["table"]})).scalar()
            size = int(sz or 0)
    except Exception:  # noqa: BLE001
        pass
    await _svc._exec_write(
        "UPDATE ai_ont_index SET status='ready', row_count=:r, size_bytes=:s, "
        "build_count=:bc, last_built_at=now(), auto_retry_at=NULL, last_error='' "
        "WHERE id=:i",
        {"r": rows, "s": size, "bc": bc + 1, "i": int(index_id)})
    await _sync_object_index_status(object_code)
    await _svc._log_change(object_code, "index", "build", f"索引 {name} 构建完成")
    return {"ok": True, "status": "ready", "rows": rows, "size": size,
            "size_human": _human(size),
            "msg": f"索引已就绪（{rows} 行，{_human(size)}）"}


async def _fail(index_id: int, object_code: str, name: str, err: str,
                terminal: bool) -> dict:
    """记录失败。

    官方：瞬时错误约 5 分钟后自动重试；终态错误只在有新数据时重试。
    """
    retry = None if terminal else (datetime.now() + timedelta(minutes=AUTO_RETRY_MINUTES))
    await _svc._exec_write(
        "UPDATE ai_ont_index SET status='failed', last_error=:e, auto_retry_at=:ar "
        "WHERE id=:i", {"e": err, "ar": retry, "i": int(index_id)})
    await _sync_object_index_status(object_code)
    await _svc._log_change(object_code, "index", "build_failed", f"{name}：{err[:80]}")
    return {"ok": False, "status": "failed", "terminal": terminal,
            "auto_retry_at": retry.strftime("%Y-%m-%d %H:%M:%S") if retry else None,
            "msg": f"索引构建失败：{err}"
                   + ("（终态错误，仅在有新数据时重试）" if terminal
                      else f"（约 {AUTO_RETRY_MINUTES} 分钟后自动重试）")}


async def build_all(object_code: str = "") -> dict:
    """构建某对象类型（或全部）的未就绪索引。"""
    idx = await list_indexes(object_code or None)
    todo = [i for i in idx if i["enabled"] and i["status"] != "ready"]
    ok_n, fail_n = 0, 0
    for i in todo:
        r = await build_index(i["id"])
        ok_n += 1 if r.get("ok") else 0
        fail_n += 0 if r.get("ok") else 1
    return {"ok": True, "built": ok_n, "failed": fail_n, "total": len(todo),
            "msg": f"构建完成：成功 {ok_n}、失败 {fail_n}（共 {len(todo)} 个待构建）"}


async def retry_due_indexes() -> dict:
    """执行到期的自动重试（官方：瞬时失败约 5 分钟后重试）。"""
    rows = (await _svc._exec(
        "SELECT id FROM ai_ont_index WHERE is_deleted=false AND status='failed' "
        "AND auto_retry_at IS NOT NULL AND auto_retry_at <= now()", {})).fetchall()
    done = []
    for r in rows:
        res = await build_index(r[0])
        done.append({"id": r[0], "ok": res.get("ok")})
    return {"ok": True, "retried": len(done), "results": done,
            "msg": f"已重试 {len(done)} 个到期索引" if done else "没有到期的重试"}


async def mark_stale(object_code: str) -> dict:
    """对象类型定义变了 → 相关索引标记为过期（官方：需要重建）。"""
    n = 0
    for i in await list_indexes(object_code):
        if i["status"] == "ready":
            await _svc._exec_write(
                "UPDATE ai_ont_index SET status='stale' WHERE id=:i", {"i": i["id"]})
            n += 1
    await _sync_object_index_status(object_code)
    return {"ok": True, "stale": n, "msg": f"已将 {n} 个索引标记为过期"}


async def _sync_object_index_status(object_code: str) -> None:
    """把索引总体状态回写到对象类型的 index_status（官方对象列表里显示的那个）。"""
    idx = [i for i in await list_indexes(object_code) if i["enabled"]]
    if not idx:
        status = "not_started"
    elif any(i["status"] == "failed" for i in idx):
        status = "failed"
    elif all(i["status"] == "ready" for i in idx):
        status = "ready"
    elif any(i["status"] == "stale" for i in idx):
        status = "stale"
    else:
        status = "building"
    try:
        await _svc._exec_write(
            "UPDATE ai_ont_object SET index_status=:s WHERE code=:c",
            {"s": status, "c": object_code})
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# 建议：哪些属性值得建索引
# ---------------------------------------------------------------------------
async def suggest_indexes(object_code: str) -> dict:
    """按"会被过滤/会被关联"给出建索引建议。

    依据：行级策略引用的属性、关系两端用到的字段、以及筛选器里出现过的字段。
    """
    from . import security as _sec

    props = await _svc.list_properties(object_code)
    have = {i["prop_code"] for i in await list_indexes(object_code) if i["prop_code"]}
    suggestions: list[dict] = []

    def _add(prop: str, why: str, prio: str) -> None:
        if not prop or prop in have:
            return
        if any(s["prop_code"] == prop for s in suggestions):
            return
        suggestions.append({"prop_code": prop, "reason": why, "priority": prio})

    meta = await _svc._instance_meta(object_code)
    if meta and not meta.get("error"):
        _add(meta.get("key_prop") or "", "对象主键，按主键取单条走的就是它", "high")
        _add(meta.get("name_prop") or "", "显示名，搜索与排序常用", "medium")
    for p in await _sec.policy_properties(object_code):
        _add(p, "被行级安全策略引用，每次读都要按它求值", "high")
    links = await _svc.list_links(object_code)
    for lk in links:
        for f in (lk.get("source_field"), lk.get("target_field")):
            if f:
                _add(str(f), f"关系「{lk.get('name')}」的关联字段", "medium")
    for p in props:
        if p.get("unique_col"):
            _add(p["code"], "声明了唯一约束，需要索引支撑", "high")
    order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda x: order.get(x["priority"], 3))
    return {"ok": True, "object_code": object_code, "suggestions": suggestions,
            "count": len(suggestions),
            "msg": f"给出 {len(suggestions)} 条索引建议"}


async def apply_suggestions(object_code: str, only_high: bool = True) -> dict:
    r = await suggest_indexes(object_code)
    todo = [s for s in r["suggestions"] if not only_high or s["priority"] == "high"]
    made = 0
    for s in todo:
        await upsert_index({"object_code": object_code, "prop_code": s["prop_code"],
                            "index_kind": "property"})
        made += 1
    built = await build_all(object_code) if made else {"built": 0, "failed": 0}
    return {"ok": True, "created": made, "built": built.get("built", 0),
            "failed": built.get("failed", 0),
            "msg": f"已创建 {made} 个建议索引，构建成功 {built.get('built', 0)}、"
                   f"失败 {built.get('failed', 0)}"}


def json_default(o: Any) -> Any:  # pragma: no cover - 兼容工具
    return json.loads(json.dumps(o, default=str))
