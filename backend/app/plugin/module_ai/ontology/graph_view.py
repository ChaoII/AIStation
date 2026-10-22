"""图视图（Graph View）：本体图谱的可复用呈现。

对齐设计：`docs/superpowers/specs/2026-10-20-ontology-p7-graph-views-design.md`

三种子能力：
- **saved**（保存视图）：按 `domain_code` 归属，可分享/版本化/设为域默认。
- **template**（图模板）：全局（`domain_code` 可空），一键还原图配置。
- **时间轴**（timeline-props）：基于对象已有时间属性（`base_type ∈ {date, datetime, timestamp, time}`）。

权限 / 分享 / 版本完全复刻 `object_view.py`，唯一差异是**归属维度是 `domain_code`
（本体域）而非 `object_code`（对象类型）**。写库一律走 `service._exec/_exec_write`。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.core.exceptions import CustomException

from . import service as _svc


def _j(v: Any) -> str:
    """把任意值安全序列化成 JSON 字符串（处理 datetime / Decimal / bytes）。"""
    from decimal import Decimal

    def _d(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (bytes, bytearray)):
            return o.decode("utf-8", "replace")
        return str(o)

    return json.dumps(v, ensure_ascii=False, default=_d)


def _now() -> datetime:
    # asyncpg 严格要求时间参数为 datetime 实例（传 str 会 DataError：图视图保存曾因此全挂）
    return datetime.now()


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
ONT_GRAPH_KINDS = ("saved", "template")

#: SELECT 列（顺序必须与 _G_FIELDS 一致；不含 is_deleted，查询用 WHERE 过滤）
_G_COLS = ("SELECT id,code,COALESCE(name,''),COALESCE(description,''),"
           "COALESCE(graph_kind,'saved'),COALESCE(domain_code,''),state,filters,"
           "share_roles,COALESCE(share_mode,'inherit'),COALESCE(status,'experimental'),"
           "COALESCE(visibility,'normal'),COALESCE(created_by,''),is_default,"
           "COALESCE(version,1),created_time,updated_time "
           "FROM ai_ont_graph_view ")
_G_FIELDS = ("id", "code", "name", "description", "graph_kind", "domain_code",
             "state", "filters", "share_roles", "share_mode", "status", "visibility",
             "created_by", "is_default", "version", "created_time", "updated_time")
#: JSON 列（读回需反序列化）。漏掉 state 会让回放/更新时静默丢图配置。
_G_JSON_FIELDS = ("state", "filters", "share_roles")


def _row_to_view(row) -> dict:
    out: dict[str, Any] = {}
    for i, n in enumerate(_G_FIELDS):
        v = row[i]
        if n == "state":
            v = v if isinstance(v, dict) else _svc._json_dict(v)
        elif n in _G_JSON_FIELDS:
            v = v if isinstance(v, list) else _svc._json_list(v)
        elif isinstance(v, datetime):
            v = v.strftime("%Y-%m-%d %H:%M:%S")
        out[n] = v
    return out


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
async def list_views(domain_code: str = "", kind: str = "") -> list[dict]:
    """列出可见图视图。``kind`` 为 'saved'/'template' 时过滤；``domain_code`` 为空则不限域。"""
    sql = _G_COLS + "WHERE is_deleted=false"
    p: dict = {}
    if domain_code:
        sql += " AND domain_code=:d"
        p["d"] = domain_code
    if kind:
        sql += " AND graph_kind=:k"
        p["k"] = kind
    sql += " ORDER BY id DESC"
    return [_row_to_view(r) for r in (await _svc._exec(sql, p)).fetchall()]


async def get_view(code: str) -> dict | None:
    r = await _svc._exec(_G_COLS + "WHERE code=:c AND is_deleted=false", {"c": code})
    row = r.fetchone()
    if not row:
        return None
    return _row_to_view(row)


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------
async def create_view(data: dict, actor: str = "") -> dict:
    code = str(data.get("code") or "").strip() or f"gv_{uuid.uuid4().hex[:12]}"
    graph_kind = str(data.get("graph_kind") or "saved")
    if graph_kind not in ONT_GRAPH_KINDS:
        raise CustomException(msg=f"图视图类型不支持 {graph_kind}")
    domain_code = str(data.get("domain_code") or "").strip()
    if graph_kind == "saved" and not domain_code:
        raise CustomException(msg="保存视图必须归属某个本体域")
    if (await _svc._exec(
            "SELECT 1 FROM ai_ont_graph_view WHERE code=:c AND is_deleted=false",
            {"c": code})).fetchone():
        raise CustomException(msg=f"视图编码 {code} 已存在")
    await _svc._exec_write(
        "INSERT INTO ai_ont_graph_view(code,name,description,graph_kind,domain_code,state,"
        "filters,share_roles,share_mode,status,visibility,created_by,is_default,version,"
        "created_time,updated_time) "
        "VALUES (:c,:n,:d,:k,:dc,:st,:fl,:sr,:sm,:status,:vis,:cb,:df,:v,:ct,:ut)",
        {"c": code, "n": str(data.get("name") or ""), "d": str(data.get("description") or ""),
         "k": graph_kind, "dc": domain_code, "st": _j(data.get("state") or {}),
         "fl": _j(data.get("filters") or []), "sr": _j(data.get("share_roles") or []),
         "sm": str(data.get("share_mode") or "inherit"),
         "status": str(data.get("status") or "experimental"),
         "vis": str(data.get("visibility") or "normal"), "cb": actor,
         "df": bool(data.get("is_default")), "v": int(data.get("version") or 1),
         "ct": _now(), "ut": _now()})
    await _svc._log_change(domain_code or code, "graph_view", "create", f"图视图 {code}")
    return {"ok": True, "code": code, "msg": "已保存"}


async def update_view(code: str, data: dict, actor: str = "") -> dict:
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    # 版本自增 + 先快照当前 state（供回滚）
    new_version = int(v["version"] or 1) + 1
    await _svc._exec_write(
        "INSERT INTO ai_ont_graph_view_version(view_code,version,state,note,created_by,"
        "created_time) VALUES (:c,:v,:st,:n,:cb,:ct)",
        {"c": code, "v": int(v["version"] or 1), "st": _j(v["state"] or {}),
         "n": "更新前快照", "cb": actor, "ct": _now()})
    sets: list[str] = []
    p: dict = {"c": code}
    for key in ("name", "description", "graph_kind", "domain_code", "share_mode"):
        if key in data:
            sets.append(f"{key}=:{key}")
            p[key] = str(data[key])
    if "state" in data:
        sets.append("state=:state")
        p["state"] = _j(data.get("state") or {})
    if "filters" in data:
        sets.append("filters=:filters")
        p["filters"] = _j(data.get("filters") or [])
    if "share_roles" in data:
        sets.append("share_roles=:share_roles")
        p["share_roles"] = _j(data.get("share_roles") or [])
    if not sets:
        raise CustomException(msg="没有可更新的内容")
    sets.append("version=:version")
    sets.append("updated_time=:ut")
    p["version"] = new_version
    p["ut"] = _now()
    await _svc._exec_write(
        f"UPDATE ai_ont_graph_view SET {', '.join(sets)} "
        "WHERE code=:c AND is_deleted=false", p)
    await _svc._log_change(v["domain_code"] or code, "graph_view", "update", f"图视图 {code}")
    return {"ok": True, "code": code, "msg": "已更新", "version": new_version}


async def remove_view(code: str) -> dict:
    await _svc._exec_write(
        "UPDATE ai_ont_graph_view SET is_deleted=true WHERE code=:c", {"c": code})
    await _svc._exec_write(
        "DELETE FROM ai_ont_graph_view_version WHERE view_code=:c", {"c": code})
    return {"ok": True, "msg": "视图已删除"}


# ---------------------------------------------------------------------------
# 版本管理
# ---------------------------------------------------------------------------
async def list_versions(code: str) -> list[dict]:
    r = await _svc._exec(
        "SELECT id,version,state,COALESCE(note,''),COALESCE(created_by,''),created_time "
        "FROM ai_ont_graph_view_version WHERE view_code=:c ORDER BY version DESC",
        {"c": code})
    return [{"id": x[0], "version": x[1], "state": _svc._json_dict(x[2]), "note": x[3],
             "created_by": x[4],
             "created_time": x[5].strftime("%Y-%m-%d %H:%M:%S")
             if isinstance(x[5], datetime) else (x[5] or "")}
            for x in r.fetchall()]


async def restore_version(code: str, version: int, actor: str = "") -> dict:
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    r = await _svc._exec(
        "SELECT state FROM ai_ont_graph_view_version WHERE view_code=:c AND version=:v",
        {"c": code, "v": version})
    row = r.fetchone()
    if not row:
        raise CustomException(msg=f"版本 {version} 不存在")
    # 先把当前 state 快照，避免回滚覆盖掉未保存的较新配置
    await _svc._exec_write(
        "INSERT INTO ai_ont_graph_view_version(view_code,version,state,note,created_by,"
        "created_time) VALUES (:c,:v,:st,:n,:cb,:ct)",
        {"c": code, "v": int(v["version"] or 1), "st": _j(v["state"] or {}),
         "n": "回滚前快照", "cb": actor, "ct": _now()})
    new_version = int(v["version"] or 1) + 1
    await _svc._exec_write(
        "UPDATE ai_ont_graph_view SET state=:s, version=:v, updated_time=:ut "
        "WHERE code=:c AND is_deleted=false",
        {"s": _j(_svc._json_dict(row[0])), "v": new_version, "ut": _now(), "c": code})
    await _svc._log_change(v["domain_code"] or code, "graph_view", "restore",
                           f"图视图 {code} 回滚到 v{version}")
    return {"ok": True, "msg": f"已回滚到 v{version}", "version": new_version}


# ---------------------------------------------------------------------------
# 默认视图
# ---------------------------------------------------------------------------
async def set_default(code: str, domain_code: str = "") -> dict:
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    d = domain_code or v["domain_code"]
    # 同域内先清掉其它默认（保持每个域最多一个默认）
    await _svc._exec_write(
        "UPDATE ai_ont_graph_view SET is_default=false "
        "WHERE domain_code=:d AND is_deleted=false", {"d": d})
    await _svc._exec_write(
        "UPDATE ai_ont_graph_view SET is_default=true WHERE code=:c", {"c": code})
    await _svc._log_change(d or code, "graph_view", "set_default", f"图视图 {code}")
    return {"ok": True, "msg": f"「{v['name']}」已设为默认视图"}


# ---------------------------------------------------------------------------
# 分享与权限
# ---------------------------------------------------------------------------
async def share_view(code: str, share_mode: str, roles: list[str] | None = None) -> dict:
    """设置图视图的共享方式。

    - ``inherit``（默认）：跟随本体域权限
    - ``roles``：只给指定角色看

    注意：**只看得到视图 ≠ 看得到图数据** —— 图数据仍走对象类型/实例权限。
    """
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    mode = share_mode if share_mode in ("inherit", "roles") else "inherit"
    rs = [str(x).strip() for x in (roles or []) if str(x).strip()]
    if mode == "roles" and not rs:
        raise CustomException(msg="按角色共享时至少要指定一个角色")
    await _svc._exec_write(
        "UPDATE ai_ont_graph_view SET share_mode=:m, share_roles=:r WHERE code=:c",
        {"m": mode, "r": _j(rs), "c": code})
    await _svc._log_change(v["domain_code"] or code, "graph_view", "share",
                           f"图视图 {code} 共享方式 → {mode}")
    return {"ok": True, "share_mode": mode, "share_roles": rs,
            "msg": ("已改为跟随本体域权限" if mode == "inherit"
                    else f"已共享给角色：{'、'.join(rs)}")}


async def can_view_view(code: str, principal: Any) -> tuple[bool, str]:
    """某个人能不能看这个图视图（共享层面）。数据能否看由对象类型权限决定。"""
    v = await get_view(code)
    if not v:
        return False, "视图不存在"
    if v.get("share_mode") != "roles":
        return True, "跟随本体域权限"
    if principal is None:
        return True, "未提供身份，跳过共享校验"
    if getattr(principal, "is_superuser", False):
        return True, "超级管理员"
    roles = set(getattr(principal, "role_codes", []) or [])
    want = set(v.get("share_roles") or [])
    if roles & want:
        return True, "角色命中"
    return False, f"该视图只共享给：{'、'.join(sorted(want))}"


async def list_shared_views(principal: Any) -> list[dict]:
    """当前身份可见的图视图（按共享设置过滤）。"""
    out = []
    for v in await list_views():
        ok, why = await can_view_view(v["code"], principal)
        if ok:
            v["share_reason"] = why
            out.append(v)
    return out


# ---------------------------------------------------------------------------
# 生成链接（官方 generate-urls）
# ---------------------------------------------------------------------------
def view_url(code: str, base: str = "#/ai/ontology") -> str:
    """生成能直接打开某个图视图的深链。"""
    from urllib.parse import quote

    return f"{base}?graphview={quote(str(code or ''), safe='')}"


async def view_link(code: str) -> dict:
    """返回深链与其含义（界面上「复制链接」用）。"""
    v = await get_view(code)
    if not v:
        raise CustomException(msg="视图不存在")
    return {"ok": True, "url": view_url(code), "view_code": code,
            "graph_kind": v["graph_kind"], "domain_code": v["domain_code"],
            "msg": "链接可直接打开该图视图"}


# ---------------------------------------------------------------------------
# 时间轴属性候选
# ---------------------------------------------------------------------------
async def timeline_props(domain_code: str = "") -> list[dict]:
    """返回可作为时间轴的属性候选（``base_type`` 表示时间/日期的属性）。

    时间值属于**实例**，因此候选来自对象类型的日期类属性；前端据此在
    对象探索（实例图）上做时间滑块过滤。集合取 `ON value valid` 中的
    ``{'date','datetime','timestamp','time'}``（兼容 `ONT_BASE_TYPE` 与实例数据）。
    """
    sql = ("SELECT o.code, o.name, p.code, p.name, p.base_type "
           "FROM ai_ont_object o JOIN ai_ont_property p ON p.object_code = o.code "
           "WHERE p.is_deleted = false AND o.is_deleted = false AND p.base_type IN "
           "('date','datetime','timestamp','time')")
    params: dict = {}
    if domain_code:
        sql += " AND o.domain_code = :d"
        params["d"] = domain_code
    rows = await _svc._exec(sql, params)
    return [{"object_code": r[0], "object_name": r[1], "prop_code": r[2],
             "prop_name": r[3], "base_type": r[4]} for r in rows.fetchall()]
