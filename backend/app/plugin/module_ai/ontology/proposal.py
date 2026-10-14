"""分支与提案（Branch / Proposal）：本体变更的评审与合并。

对齐官方 `ontologies/ontologies-proposals`：

- **分支**：*"从主版本派生出的独立版本，旨在进行实验和更改而不影响主分支"*。
- **提案**：*"类似于版本控制系统中的拉取请求 … **在分支创建时自动生成**"*。
- 工作流：**创建分支 → 准备提案 → 请求审查 → 审查（按任务批准/拒绝）→ 发布（合并）**。
- **任务（task）**：*"每个修改的 Ontology 实体将在您的提案中构成一个单独的**任务**"*。
- 阶段：`准备` → `审查中` → `合并`；提案标签：我的提案 / 指派给我 / 审查中 / 已合并 / 关闭的。
- **变更记录**：*"显示分支上的详细更改历史。任务可以展开以显示某个用户在某个时间点所做的编辑。"*
- 权限：查看=访客；创建=访客；编辑分支=创建者或对该资源的 editor/owner；
  **批准任务要求批准者是底层资源的 editor/owner**；合并=任何能编辑分支的人。
- 约束：*"提案分支只能在主 Ontology 配置上创建。您不能基于另一个提案创建新分支。"*
  *"一旦提案被关闭，它就不能重新打开。"* *"提案不能自动恢复。"*

**与既有机制的关系**：工作副本（WIP）是**个人草稿**，场景（scenario）是**数据沙箱**，
分支是**共享的、可评审的定义改动**。三者互不替代。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.exceptions import CustomException

from . import service as _svc

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
ONT_BRANCH_STATUS = ("active", "merged", "closed")
ONT_BRANCH_STATUS_LABEL = {"active": "进行中", "merged": "已合并", "closed": "已关闭"}

ONT_PROPOSAL_STAGES = ("preparing", "in_review", "merged", "closed")
ONT_PROPOSAL_STAGE_LABEL = {
    "preparing": "准备中", "in_review": "审查中",
    "merged": "已合并", "closed": "已关闭",
}
#: 官方提案标签页
ONT_PROPOSAL_TABS = ("mine", "assigned", "in_review", "merged", "closed")
ONT_PROPOSAL_TAB_LABEL = {
    "mine": "我的提案", "assigned": "指派给我", "in_review": "审查中",
    "merged": "已合并提案", "closed": "关闭的提案",
}

ONT_TASK_STATUS = ("pending", "approved", "rejected")
ONT_TASK_STATUS_LABEL = {"pending": "待审查", "approved": "已批准", "rejected": "已拒绝"}

ONT_CHANGE_KINDS = ("create", "update", "delete")
ONT_CHANGE_LABEL = {"create": "新建", "update": "修改", "delete": "删除"}

#: 允许在分支上改动的资源种类（与 WIP 对齐）
ONT_BRANCH_KINDS = ("object", "property", "link", "action", "function", "group",
                    "value_type", "shared_property", "interface")


def _j(v: Any) -> str:
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


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ts(v: Any) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else (v or "")


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
async def list_branches(status: str = "") -> list[dict]:
    sql = ("SELECT id,code,COALESCE(name,''),COALESCE(description,''),"
           "COALESCE(status,'active'),COALESCE(base_version,0),COALESCE(created_by,''),"
           "created_time,merged_at,COALESCE(merged_by,'') FROM ai_ont_branch "
           "WHERE is_deleted=false")
    p: dict = {}
    if status:
        sql += " AND status=:s"
        p["s"] = status
    sql += " ORDER BY id DESC"
    out = []
    for r in (await _svc._exec(sql, p)).fetchall():
        n = int((await _svc._exec(
            "SELECT count(*) FROM ai_ont_branch_change WHERE branch_code=:c",
            {"c": r[1]})).scalar() or 0)
        prop = (await _svc._exec(
            "SELECT code FROM ai_ont_proposal WHERE branch_code=:c AND is_deleted=false",
            {"c": r[1]})).fetchone()
        out.append({"id": r[0], "code": r[1], "name": r[2], "description": r[3],
                    "status": r[4],
                    "status_label": ONT_BRANCH_STATUS_LABEL.get(r[4], r[4]),
                    "base_version": r[5], "created_by": r[6], "created_time": _ts(r[7]),
                    "merged_at": _ts(r[8]), "merged_by": r[9],
                    "change_count": n, "proposal_code": prop[0] if prop else ""})
    return out


async def get_branch(code: str) -> dict | None:
    bs = [b for b in await list_branches() if b["code"] == code]
    if not bs:
        return None
    b = bs[0]
    b["changes"] = await list_branch_changes(code)
    prop = (await _svc._exec(
        "SELECT code FROM ai_ont_proposal WHERE branch_code=:c AND is_deleted=false",
        {"c": code})).fetchone()
    b["proposal"] = await get_proposal(prop[0]) if prop else None
    return b


async def list_branch_changes(branch_code: str) -> list[dict]:
    r = await _svc._exec(
        "SELECT id,resource_kind,resource_code,change_kind,before,after,"
        "COALESCE(created_by,''),created_time FROM ai_ont_branch_change "
        "WHERE branch_code=:c ORDER BY id", {"c": branch_code})
    return [{"id": x[0], "resource_kind": x[1], "resource_code": x[2],
             "change_kind": x[3],
             "change_kind_label": ONT_CHANGE_LABEL.get(x[3], x[3]),
             "before": _svc._json_dict(x[4]), "after": _svc._json_dict(x[5]),
             "created_by": x[6], "created_time": _ts(x[7])}
            for x in r.fetchall()]


async def list_proposals(tab: str = "", actor: str = "") -> list[dict]:
    sql = ("SELECT id,code,branch_code,COALESCE(title,''),COALESCE(description,''),"
           "COALESCE(stage,'preparing'),reviewers,COALESCE(created_by,''),created_time,"
           "review_requested_at,merged_at,COALESCE(merged_by,''),closed_at,"
           "COALESCE(closed_by,'') FROM ai_ont_proposal WHERE is_deleted=false")
    p: dict = {}
    if tab == "mine" and actor:
        sql += " AND created_by=:a"
        p["a"] = actor
    elif tab == "in_review":
        sql += " AND stage='in_review'"
    elif tab == "merged":
        sql += " AND stage='merged'"
    elif tab == "closed":
        sql += " AND stage='closed'"
    sql += " ORDER BY id DESC"
    out = []
    for r in (await _svc._exec(sql, p)).fetchall():
        reviewers = _svc._json_list(r[6])
        if tab == "assigned" and actor and actor not in reviewers:
            continue
        tasks = await list_tasks(r[1])
        out.append({
            "id": r[0], "code": r[1], "branch_code": r[2], "title": r[3],
            "description": r[4], "stage": r[5],
            "stage_label": ONT_PROPOSAL_STAGE_LABEL.get(r[5], r[5]),
            "reviewers": reviewers, "created_by": r[7], "created_time": _ts(r[8]),
            "review_requested_at": _ts(r[9]), "merged_at": _ts(r[10]),
            "merged_by": r[11], "closed_at": _ts(r[12]), "closed_by": r[13],
            "task_count": len(tasks),
            "approved": sum(1 for t in tasks if t["status"] == "approved"),
            "rejected": sum(1 for t in tasks if t["status"] == "rejected"),
            "pending": sum(1 for t in tasks if t["status"] == "pending"),
            "can_merge": bool(tasks) and all(t["status"] == "approved" for t in tasks),
        })
    return out


async def list_tasks(proposal_code: str) -> list[dict]:
    r = await _svc._exec(
        "SELECT id,resource_kind,resource_code,COALESCE(resource_name,''),"
        "COALESCE(change_kind,'update'),before,after,COALESCE(status,'pending'),"
        "COALESCE(reviewed_by,''),reviewed_at,COALESCE(review_note,''),created_time "
        "FROM ai_ont_proposal_task WHERE proposal_code=:p ORDER BY id",
        {"p": proposal_code})
    return [{"id": x[0], "resource_kind": x[1], "resource_code": x[2],
             "resource_name": x[3] or x[2], "change_kind": x[4],
             "change_kind_label": ONT_CHANGE_LABEL.get(x[4], x[4]),
             "before": _svc._json_dict(x[5]), "after": _svc._json_dict(x[6]),
             "status": x[7], "status_label": ONT_TASK_STATUS_LABEL.get(x[7], x[7]),
             "reviewed_by": x[8], "reviewed_at": _ts(x[9]), "review_note": x[10],
             "created_time": _ts(x[11])}
            for x in r.fetchall()]


async def list_comments(proposal_code: str, task_id: int = 0) -> list[dict]:
    sql = ("SELECT id,task_id,COALESCE(author,''),COALESCE(body,''),created_time "
           "FROM ai_ont_proposal_comment WHERE proposal_code=:p")
    p: dict = {"p": proposal_code}
    if task_id:
        sql += " AND task_id=:t"
        p["t"] = int(task_id)
    sql += " ORDER BY id"
    return [{"id": x[0], "task_id": x[1], "author": x[2], "body": x[3],
             "created_time": _ts(x[4])}
            for x in (await _svc._exec(sql, p)).fetchall()]


async def get_proposal(code: str) -> dict | None:
    ps = [x for x in await list_proposals() if x["code"] == code]
    if not ps:
        return None
    p = ps[0]
    p["tasks"] = await list_tasks(code)
    p["comments"] = await list_comments(code)
    p["changes"] = await list_branch_changes(p["branch_code"])
    p["changelog"] = await proposal_changelog(code)
    return p


# ---------------------------------------------------------------------------
# 创建分支（官方：提案在分支创建时自动生成）
# ---------------------------------------------------------------------------
async def _unique_code(prefix: str, name: str) -> str:
    import hashlib
    import re

    ascii_part = re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_").lower()
    base = f"{prefix}_{ascii_part[:40]}" if ascii_part else \
        f"{prefix}_{hashlib.md5((name or '').encode()).hexdigest()[:8]}"
    table = "ai_ont_branch" if prefix == "br" else "ai_ont_proposal"
    code, n = base[:120], 1
    while (await _svc._exec(f"SELECT 1 FROM {table} WHERE code=:c", {"c": code})).fetchone():
        n += 1
        code = base[: 120 - len(f"_{n}")] + f"_{n}"
    return code


async def create_branch(title: str, description: str = "", actor: str = "") -> dict:
    """创建分支 —— 同时**自动生成提案**（官方行为）。

    官方：*"提案分支只能在主 Ontology 配置上创建。您不能基于另一个提案创建新分支。"*
    （我们的分支没有父分支概念，因此天然满足。）
    """
    title = (title or "").strip()
    if not title:
        raise CustomException(msg="请填写提案标题")
    bcode = await _unique_code("br", title)
    ver = (await _svc._exec(
        "SELECT COALESCE(max(version),0) FROM ai_ont_version", {})).scalar() or 0
    await _svc._exec_write(
        "INSERT INTO ai_ont_branch(code,name,description,base_version,created_by) "
        "VALUES (:c,:n,:d,:v,:cb)",
        {"c": bcode, "n": title, "d": description, "v": int(ver), "cb": actor})
    pcode = await _unique_code("prop", title)
    await _svc._exec_write(
        "INSERT INTO ai_ont_proposal(code,branch_code,title,description,created_by) "
        "VALUES (:c,:b,:t,:d,:cb)",
        {"c": pcode, "b": bcode, "t": title, "d": description, "cb": actor})
    await _svc._log_change("", "branch", "create", f"分支 {bcode}（提案 {pcode}）")
    return {"ok": True, "branch_code": bcode, "proposal_code": pcode,
            "base_version": int(ver),
            "msg": f"分支已创建，并自动生成提案「{title}」"}


# ---------------------------------------------------------------------------
# 在分支上改动（每个资源构成一个 task）
# ---------------------------------------------------------------------------
async def save_on_branch(branch_code: str, kind: str, action: str, data: dict,
                         actor: str = "") -> dict:
    """在分支上保存一处定义改动。

    对应官方："每个修改的 Ontology 实体将在您的提案中构成一个单独的任务"。
    同一资源的多次改动**合并到同一个 task**（后者覆盖前者）。
    """
    br = await get_branch(branch_code)
    if not br:
        raise CustomException(msg=f"分支 {branch_code} 不存在")
    if br["status"] != "active":
        raise CustomException(msg=f"分支已{br['status_label']}，不能再改")
    if kind not in ONT_BRANCH_KINDS:
        raise CustomException(msg=f"资源种类不支持 {kind}（可用：{'、'.join(ONT_BRANCH_KINDS)}）")
    action = action if action in ONT_CHANGE_KINDS else "update"
    code = str(data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="改动必须带资源编码 code")
    prop = (await _svc._exec(
        "SELECT code FROM ai_ont_proposal WHERE branch_code=:b AND is_deleted=false",
        {"b": branch_code})).fetchone()
    if not prop:
        raise CustomException(msg="该分支没有对应提案")
    pcode = prop[0]

    # 基线：主分支上的当前定义（删除时也留一份 before）
    before = await _snapshot(kind, code)
    # 关键：after 存**完整新状态**（before + 改动），而不是只存传进来的子集。
    # 否则合并时会把未提及的字段（icon/description/status…）重置为默认值。
    if action == "delete":
        after: dict = {}
    elif before:
        after = {**before, **data}
    else:
        after = dict(data)

    # 同一资源已有 task → 覆盖（保留最早的 before）
    old = (await _svc._exec(
        "SELECT id,before,change_kind FROM ai_ont_proposal_task "
        "WHERE proposal_code=:p AND resource_kind=:k AND resource_code=:c "
        "ORDER BY id LIMIT 1", {"p": pcode, "k": kind, "c": code})).fetchone()
    if old:
        keep_before = _svc._json_dict(old[1]) or before
        await _svc._exec_write(
            "UPDATE ai_ont_proposal_task SET after=:a, before=:b, change_kind=:ck, "
            "status='pending', reviewed_by='', reviewed_at=NULL, review_note='' "
            "WHERE id=:id",
            {"a": _j(after), "b": _j(keep_before), "ck": action, "id": old[0]})
        task_id = old[0]
        merged_note = "（已更新同一任务）"
    else:
        r = await _svc._exec_write(
            "INSERT INTO ai_ont_proposal_task(proposal_code,resource_kind,resource_code,"
            "resource_name,change_kind,before,after) "
            "VALUES (:p,:k,:c,:n,:ck,:b,:a) RETURNING id",
            {"p": pcode, "k": kind, "c": code, "n": data.get("name") or code,
             "ck": action, "b": _j(before), "a": _j(after)})
        task_id = r.scalar()
        merged_note = ""

    await _svc._exec_write(
        "INSERT INTO ai_ont_branch_change(branch_code,resource_kind,resource_code,"
        "change_kind,before,after,created_by) VALUES (:b,:k,:c,:ck,:bf,:a,:cb)",
        {"b": branch_code, "k": kind, "c": code, "ck": action,
         "bf": _j(before), "a": _j(after), "cb": actor})
    # 有改动就回到准备中（除非已合并/关闭）
    await _svc._exec_write(
        "UPDATE ai_ont_proposal SET stage='preparing' "
        "WHERE code=:p AND stage='in_review'", {"p": pcode})
    return {"ok": True, "task_id": task_id, "proposal_code": pcode,
            "msg": f"已在分支上暂存{ONT_CHANGE_LABEL[action]}：{kind} {code}{merged_note}"}


async def _snapshot(kind: str, code: str) -> dict:
    """取主分支上该资源的当前定义（作为 before）。"""
    try:
        if kind == "object":
            objs = await _svc.list_objects()
            return next((o for o in objs if o["code"] == code), {})
        if kind == "property":
            r = (await _svc._exec(
                "SELECT object_code FROM ai_ont_property WHERE code=:c AND is_deleted=false "
                "LIMIT 1", {"c": code})).fetchone()
            if r:
                props = await _svc.list_properties(r[0])
                return next((p for p in props if p["code"] == code), {})
        if kind == "link":
            links = await _svc.list_links(None)
            return next((x for x in links if x.get("code") == code), {})
        if kind == "action":
            acts = await _svc.list_actions(None)
            return next((a for a in acts if a["code"] == code), {})
        if kind == "function":
            fns = await _svc.list_functions(None)
            return next((f for f in fns if f["code"] == code), {})
    except Exception:  # noqa: BLE001
        pass
    return {}


async def discard_task(task_id: int) -> dict:
    """丢弃某个任务的改动（官方：概览页可"丢弃该更改"）。"""
    r = (await _svc._exec(
        "SELECT proposal_code,resource_kind,resource_code FROM ai_ont_proposal_task "
        "WHERE id=:i", {"i": int(task_id)})).fetchone()
    if not r:
        raise CustomException(msg="任务不存在")
    await _svc._exec_write("DELETE FROM ai_ont_proposal_task WHERE id=:i",
                           {"i": int(task_id)})
    await _svc._exec_write(
        "DELETE FROM ai_ont_branch_change WHERE branch_code="
        "(SELECT branch_code FROM ai_ont_proposal WHERE code=:p) "
        "AND resource_kind=:k AND resource_code=:c",
        {"p": r[0], "k": r[1], "c": r[2]})
    return {"ok": True, "msg": f"已丢弃任务（{r[1]} {r[2]}）"}


# ---------------------------------------------------------------------------
# 请求审查 / 审查 / 合并 / 关闭
# ---------------------------------------------------------------------------
async def request_review(proposal_code: str, reviewers: list[str],
                         actor: str = "") -> dict:
    """请求审查。官方：审查者**只有在提案处于「审查中」阶段时才会收到通知**。"""
    p = await get_proposal(proposal_code)
    if not p:
        raise CustomException(msg="提案不存在")
    if p["stage"] in ("merged", "closed"):
        raise CustomException(msg=f"提案已{p['stage_label']}，不能请求审查")
    if not p["tasks"]:
        raise CustomException(msg="提案里还没有任何改动，先改点东西")
    names = [str(x).strip() for x in (reviewers or []) if str(x).strip()]
    if not names:
        raise CustomException(msg="请至少指派一名审查者")
    await _svc._exec_write(
        "UPDATE ai_ont_proposal SET stage='in_review', reviewers=:r, "
        "review_requested_at=now() WHERE code=:c", {"r": _j(names), "c": proposal_code})
    # 通知审查者（官方：进入审查阶段才通知）
    notified = await _notify_reviewers(names, p)
    await _svc._log_change("", "proposal", "request_review",
                           f"提案 {proposal_code} 请求审查：{'、'.join(names)}")
    return {"ok": True, "reviewers": names, "notified": notified,
            "msg": f"已进入审查中，已通知 {notified} 名审查者"}


async def _notify_reviewers(names: list[str], p: dict) -> int:
    """给审查者写平台通知（复用 sys_user_notification）。"""
    n = 0
    for name in names:
        try:
            row = (await _svc._exec(
                "SELECT id FROM sys_user WHERE (name=:n OR username=:n) "
                "AND is_deleted=false LIMIT 1", {"n": name})).fetchone()
            if not row:
                continue
            await _svc._exec_write(
                "INSERT INTO sys_user_notification(user_id,title,content,type,module,"
                "module_id,is_read,created_time) "
                "VALUES (:u,:t,:c,'info','ontology',0,false,now())",
                {"u": row[0], "t": f"本体提案待审查：{p['title']}",
                 "c": f"提案 {p['code']} 有 {len(p['tasks'])} 个任务待审查。"})
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


async def review_task(task_id: int, approve: bool, reviewer: str = "",
                      note: str = "", actor_id: int | None = None) -> dict:
    """批准/拒绝一个任务。

    官方：*"为了使任务被视为已批准，**批准者必须是底层资源的编辑者或所有者**。"*
    我们用 P4 的资源 ACL 实现这条：批准需要对该资源的 edit 权限。
    """
    t = (await _svc._exec(
        "SELECT proposal_code,resource_kind,resource_code,COALESCE(status,'pending') "
        "FROM ai_ont_proposal_task WHERE id=:i", {"i": int(task_id)})).fetchone()
    if not t:
        raise CustomException(msg="任务不存在")
    pcode, kind, rcode = t[0], t[1], t[2]

    from . import security as _sec

    principal = await _sec.load_principal(actor_id) if actor_id else None
    if principal is not None and not principal.is_superuser:
        # 资源种类 → P4 的资源种类映射
        acl_kind = {"object": "object", "link": "link", "action": "action",
                    "function": "function", "interface": "interface",
                    "value_type": "value_type",
                    "shared_property": "shared_property"}.get(kind)
        if acl_kind:
            ok, why = await _sec.can_edit_resource(acl_kind, rcode, principal)
            if not ok:
                return {"ok": False, "blocked_by": "permission",
                        "msg": f"批准该任务需要对 {kind} {rcode} 的编辑权限：{why}"}

    status = "approved" if approve else "rejected"
    await _svc._exec_write(
        "UPDATE ai_ont_proposal_task SET status=:s, reviewed_by=:r, reviewed_at=now(), "
        "review_note=:n WHERE id=:i",
        {"s": status, "r": reviewer, "n": note, "i": int(task_id)})
    await _sync_stage(pcode)
    await _svc._log_change("", "proposal", status,
                           f"任务 #{task_id}（{kind} {rcode}）被{ONT_TASK_STATUS_LABEL[status]}")
    return {"ok": True, "status": status,
            "msg": f"任务「{kind} {rcode}」→ {ONT_TASK_STATUS_LABEL[status]}"}


async def _sync_stage(proposal_code: str) -> None:
    """全部任务审完且无拒绝 → 可以合并（官方：进入「合并提案」阶段）。"""
    tasks = await list_tasks(proposal_code)
    if not tasks:
        return
    if all(t["status"] == "approved" for t in tasks):
        await _svc._exec_write(
            "UPDATE ai_ont_proposal SET stage='in_review' "
            "WHERE code=:c AND stage='preparing'", {"c": proposal_code})


async def review_all(proposal_code: str, approve: bool, reviewer: str = "",
                     actor_id: int | None = None) -> dict:
    """批量处理所有符合条件的任务（官方：可批量处理所有符合条件的任务）。"""
    tasks = await list_tasks(proposal_code)
    ok_n, blocked = 0, []
    for t in tasks:
        if t["status"] != "pending":
            continue
        r = await review_task(t["id"], approve, reviewer, "", actor_id)
        if r.get("ok"):
            ok_n += 1
        else:
            blocked.append(r.get("msg"))
    return {"ok": True, "reviewed": ok_n, "blocked": blocked,
            "msg": f"批量{'批准' if approve else '拒绝'}了 {ok_n} 个任务"
                   + (f"，{len(blocked)} 个因权限被拦" if blocked else "")}


async def merge_proposal(proposal_code: str, actor: str = "",
                         actor_id: int | None = None) -> dict:
    """合并提案到主本体。

    官方：*"将更改合并到 Ontology 中不需要特殊权限。提案被批准后，任何可以编辑分支的人
    都可以将提案合并到 Ontology 中。"*
    另外：*"提案不能自动恢复。要撤销提案，您必须撤销其中的不同更改。"*
    """
    p = await get_proposal(proposal_code)
    if not p:
        raise CustomException(msg="提案不存在")
    if p["stage"] == "merged":
        return {"ok": False, "msg": "提案已合并"}
    if p["stage"] == "closed":
        return {"ok": False, "msg": "提案已关闭，且不能重新打开"}
    if not p["tasks"]:
        return {"ok": False, "msg": "提案里没有任何改动"}
    not_ok = [t for t in p["tasks"] if t["status"] != "approved"]
    if not_ok:
        return {"ok": False, "blocked_by": "not_approved",
                "msg": f"还有 {len(not_ok)} 个任务未批准，不能合并"}

    applied, failed = 0, []
    for t in p["tasks"]:
        try:
            await _apply_task(t, actor)
            applied += 1
        except Exception as e:  # noqa: BLE001
            failed.append(f"{t['resource_kind']} {t['resource_code']}：{str(e)[:80]}")
    if failed:
        return {"ok": False, "msg": "合并失败（部分改动未生效）：" + "；".join(failed[:3])}
    await _svc._exec_write(
        "UPDATE ai_ont_proposal SET stage='merged', merged_at=now(), merged_by=:b "
        "WHERE code=:c", {"b": actor, "c": proposal_code})
    await _svc._exec_write(
        "UPDATE ai_ont_branch SET status='merged', merged_at=now(), merged_by=:b "
        "WHERE code=:c", {"b": actor, "c": p["branch_code"]})
    await _svc._log_change("", "proposal", "merge",
                           f"提案 {proposal_code} 已合并（{applied} 个任务）")
    return {"ok": True, "applied": applied,
            "msg": f"提案已合并到主本体（{applied} 个改动生效）"}


async def _apply_task(t: dict, actor: str) -> None:
    """把单个任务的改动落到主本体（复用既有 upsert，因此会走全部校验）。"""
    kind, after = t["resource_kind"], dict(t["after"] or {})
    if t["change_kind"] == "delete":
        # 直接按 (kind, code) 反查 id 后软删；不走 WIP（那会把别人的草稿一起提交）
        eid = await _svc._resolve_entity_id(kind, {"code": t["resource_code"]})
        table = _svc._ONT_TABLE_OF.get(kind)
        if not table or not eid:
            raise CustomException(msg=f"找不到要删除的 {kind} {t['resource_code']}")
        await _svc.delete_one(table, eid)
        return
    if kind == "object":
        await _svc.upsert_object(after)
    elif kind == "property":
        await _svc.upsert_property(after)
    elif kind == "link":
        await _svc.upsert_link(after)
    elif kind == "action":
        await _svc.upsert_action(after)
    elif kind == "function":
        await _svc.upsert_function(after)
    elif kind == "group":
        await _svc.upsert_group(after)
    elif kind == "value_type":
        await _svc.upsert_value_type(after)
    elif kind == "shared_property":
        await _svc.upsert_shared_property(after)
    elif kind == "interface":
        await _svc.upsert_interface(after)
    else:
        raise CustomException(msg=f"不支持合并的资源种类 {kind}")


async def close_proposal(proposal_code: str, actor: str = "") -> dict:
    """关闭提案。官方：*"一旦提案被关闭，它就不能重新打开。"*"""
    p = await get_proposal(proposal_code)
    if not p:
        raise CustomException(msg="提案不存在")
    if p["stage"] == "merged":
        return {"ok": False, "msg": "已合并的提案不能关闭"}
    if p["stage"] == "closed":
        return {"ok": False, "msg": "提案已关闭"}
    await _svc._exec_write(
        "UPDATE ai_ont_proposal SET stage='closed', closed_at=now(), closed_by=:b "
        "WHERE code=:c", {"b": actor, "c": proposal_code})
    await _svc._exec_write(
        "UPDATE ai_ont_branch SET status='closed' WHERE code=:c", {"c": p["branch_code"]})
    await _svc._log_change("", "proposal", "close", f"提案 {proposal_code} 已关闭")
    return {"ok": True, "msg": "提案已关闭（不能重新打开）"}


async def comment(proposal_code: str, body: str, author: str = "",
                  task_id: int = 0) -> dict:
    """在提案或某个任务下留言。"""
    if not (body or "").strip():
        raise CustomException(msg="评论内容不能为空")
    await _svc._exec_write(
        "INSERT INTO ai_ont_proposal_comment(proposal_code,task_id,author,body) "
        "VALUES (:p,:t,:a,:b)",
        {"p": proposal_code, "t": int(task_id or 0), "a": author, "b": body})
    return {"ok": True, "msg": "已留言"}


# ---------------------------------------------------------------------------
# 变更记录（官方「变更记录」标签）
# ---------------------------------------------------------------------------
async def proposal_changelog(proposal_code: str) -> list[dict]:
    """按任务聚合的详细改动历史。

    官方：*"任务可以展开以显示某个用户在某个时间点所做的编辑。"*
    """
    p = (await _svc._exec(
        "SELECT branch_code FROM ai_ont_proposal WHERE code=:c", {"c": proposal_code}
    )).fetchone()
    if not p:
        return []
    changes = await list_branch_changes(p[0])
    tasks = await list_tasks(proposal_code)
    by_key: dict[tuple[str, str], dict] = {}
    for c in changes:
        k = (c["resource_kind"], c["resource_code"])
        d = by_key.setdefault(k, {"resource_kind": c["resource_kind"],
                                  "resource_code": c["resource_code"],
                                  "edits": [], "authors": []})
        d["edits"].append({"change_kind": c["change_kind"],
                           "change_kind_label": c["change_kind_label"],
                           "created_by": c["created_by"],
                           "created_time": c["created_time"],
                           "diff": _diff(c["before"], c["after"])})
        if c["created_by"] and c["created_by"] not in d["authors"]:
            d["authors"].append(c["created_by"])
    task_of = {(t["resource_kind"], t["resource_code"]): t for t in tasks}
    out = []
    for k, d in by_key.items():
        t = task_of.get(k)
        d["task_id"] = t["id"] if t else 0
        d["resource_name"] = t["resource_name"] if t else d["resource_code"]
        d["status"] = t["status"] if t else "pending"
        d["status_label"] = t["status_label"] if t else "待审查"
        d["edit_count"] = len(d["edits"])
        out.append(d)
    out.sort(key=lambda x: (x["resource_kind"], x["resource_code"]))
    return out


def _diff(before: dict, after: dict) -> list[dict]:
    """字段级差异（变更记录里展开看的东西）。"""
    out = []
    for k in sorted(set(before) | set(after)):
        b, a = (before or {}).get(k), (after or {}).get(k)
        if b != a:
            out.append({"field": k, "before": b, "after": a})
    return out
