"""演示数据：一键灌入 / 一键清除。

**为什么需要它**：本体这一块功能很多（对象/属性/关系/动作/函数/决策/场景/权限/视图/索引/提案），
但空库上每页都是"暂无数据"，看不出效果也不知道怎么用。

**设计原则**

1. **精确可清除**：所有新建的东西都登记到 `ai_ont_demo`，清除时按登记逐条删除。
   不靠"名字里带演示"这种猜测（那会误删用户自己建的东西）。
2. **不改既有数据**：只新建，不修改/删除用户已有的对象类型、属性等。
   唯一例外是给已有对象类型（如摄像机表）补默认视图与索引——这些也登记在案。
3. **诚实标注**：所有名字带「演示」前缀，一眼能看出是样例。
4. **幂等**：重复载入不会重复创建（先清再建）。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.core.exceptions import CustomException

from . import service as _svc

DEMO_TAG = "演示"
DEMO_PREFIX = f"【{DEMO_TAG}】"


def _j(v: Any) -> str:
    def _d(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        return str(o)

    return json.dumps(v, ensure_ascii=False, default=_d)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 登记表
# ---------------------------------------------------------------------------
async def _ensure_registry() -> None:
    """确保登记表存在。

    建表语句的**唯一来源**是 `service._ONT_TABLES_SQL`（随 `_ensure_ontology_schema`
    一起建）。这里只做兜底，避免本模块被单独调用时表还没建——
    但**不能只在这里建**，否则会被回归测试 `test_defect01` 抓出来（它要求所有
    `ai_ont_*` 表都在唯一来源里声明）。
    """
    await _svc._exec_write(
        "CREATE TABLE IF NOT EXISTS ai_ont_demo ("
        "id BIGSERIAL PRIMARY KEY, kind VARCHAR(40), ref VARCHAR(200), "
        "label VARCHAR(240) DEFAULT '', created_time TIMESTAMP DEFAULT now())", {})


async def _reg(kind: str, ref: str, label: str = "") -> None:
    await _svc._exec_write(
        "INSERT INTO ai_ont_demo(kind,ref,label) VALUES (:k,:r,:l)",
        {"k": kind, "r": str(ref), "l": label[:240]})


#: 名字里带「演示」前缀、但没登记在案的东西 —— 认领进来
_ADOPT: tuple[tuple[str, str, str, str], ...] = (
    ("decision", "ai_ont_decision", "code", "title"),
    ("scenario", "ai_ont_scenario", "code", "name"),
    ("proposal", "ai_ont_proposal", "code", "title"),
    ("branch", "ai_ont_branch", "code", "name"),
    ("view", "ai_ont_object_view", "code", "name"),
)


async def _adopt_orphans() -> int:
    """认领「建了但没登记」的孤儿。

    真实教训：创建成功但登记那一步失败（比如返回值里没有 ``ok`` 字段、判断写错），
    对象就成了孤儿——清除时删不掉，会一直留在库里。这里按名字前缀兜底认领。
    """
    n = 0
    for kind, table, refcol, namecol in _ADOPT:
        try:
            rows = (await _svc._exec(
                f"SELECT {refcol} FROM {table} WHERE {namecol} LIKE :p",
                {"p": f"{DEMO_PREFIX}%"})).fetchall()
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            have = (await _svc._exec(
                "SELECT 1 FROM ai_ont_demo WHERE kind=:k AND ref=:r",
                {"k": kind, "r": str(r[0])})).fetchone()
            if not have:
                await _reg(kind, str(r[0]), f"{DEMO_PREFIX}（认领的孤儿）")
                n += 1
    return n


async def _registered() -> list[dict]:
    r = await _svc._exec(
        "SELECT id,kind,ref,COALESCE(label,'') FROM ai_ont_demo ORDER BY id", {})
    return [{"id": x[0], "kind": x[1], "ref": x[2], "label": x[3]}
            for x in r.fetchall()]


async def demo_status() -> dict:
    """当前演示数据的状态（界面上显示"已载入 N 项"）。"""
    await _ensure_registry()
    rows = await _registered()
    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    return {"ok": True, "loaded": len(rows) > 0, "total": len(rows),
            "by_kind": by_kind, "kind_label": _KIND_LABEL,
            "items": rows[:200], "item_count": len(rows)}


_KIND_LABEL = {
    "object": "对象类型", "property": "属性", "link": "关系", "action": "动作",
    "function": "函数", "view": "对象视图", "index": "索引", "branch": "分支",
    "proposal": "提案", "decision": "决策", "scenario": "场景",
    "row_policy": "行级策略", "acl": "资源权限", "value_type": "值类型",
    "shared_property": "共享属性", "interface": "接口",
}


# ---------------------------------------------------------------------------
# 载入
# ---------------------------------------------------------------------------
async def load_demo(actor: str = "admin", force: bool = False) -> dict:
    """灌入演示数据。已载入时需 force=True 才会重来（先清后建）。"""
    await _ensure_registry()
    await _adopt_orphans()   # 先把上次可能留下的孤儿认领进来
    st = await demo_status()
    if st["total"] and not force:
        return {"ok": False, "already": True,
                "msg": f"演示数据已载入（{st['total']} 项）。要重建请先清除，或勾选「先清除再载入」"}
    if st["total"]:
        await clear_demo()

    from . import decision as _dec
    from . import indexing as _ix
    from . import object_view as _ov
    from . import proposal as _pr
    from . import scenario as _sc
    from . import security as _sec

    steps: list[str] = []
    objs = await _svc.list_objects()
    code_of = {o["code"]: o for o in objs}

    # ---------------- 1) 对象视图 ----------------
    cam = "video_cameras"
    if cam in code_of:
        props = await _svc.list_properties(cam)
        pcodes = {p["code"]: p for p in props}
        pick = [c for c in ("name", "device_type", "stream_type", "onvif_address",
                            "status", "location", "group_id") if c in pcodes]
        links = await _svc.list_links(cam)
        acts = await _svc.list_actions(cam)
        tabs = [
            {"key": "overview", "label": "概览", "widgets": [
                {"type": "properties", "title": "基本信息",
                 "config": {"props": pick[:5]}},
                {"type": "metric", "title": "在线状态", "config": {"prop": "status"}},
            ]},
            {"key": "analysis", "label": "分析", "widgets": [
                {"type": "chart", "title": "按状态分布",
                 "config": {"group_by": "status", "limit": 8}},
                {"type": "chart", "title": "按设备类型分布",
                 "config": {"group_by": "device_type", "limit": 8}},
            ]},
            {"key": "related", "label": "关联", "widgets": [
                {"type": "links", "title": "关系", "config": {"link_ids": []}},
                {"type": "related", "title": "同组摄像机",
                 "config": {"link_id": links[0]["id"] if links else None, "limit": 10}},
            ]},
            {"key": "ops", "label": "运维", "widgets": [
                {"type": "actions", "title": "可执行动作",
                 "config": {"action_codes": [a["code"] for a in acts]}},
                {"type": "scenario", "title": "场景切换", "config": {}},
                {"type": "text", "title": "运维说明",
                 "config": {"markdown": "这是演示用的运维视图：左侧属性、"
                                        "中间分析图表、右侧关联对象与可执行动作。"}},
            ]},
        ]
        r = await _ov.create_view({
            "object_code": cam, "code": "video_cameras__demo_ops",
            "name": f"{DEMO_PREFIX}摄像机运维视图", "form_factor": "full",
            "tabs": tabs, "is_default": True, "is_managed": True, "created_by": actor,
        })
        await _reg("view", r["code"], f"{DEMO_PREFIX}摄像机运维视图")
        steps.append("对象视图：1 个（4 个标签页、9 个组件）")

        r2 = await _ov.create_view({
            "object_code": cam, "code": "video_cameras__demo_panel",
            "name": f"{DEMO_PREFIX}摄像机面板视图", "form_factor": "panel",
            "tabs": [{"key": "overview", "label": "概览", "widgets": [
                {"type": "properties", "title": "关键信息", "config": {"props": pick[:4]}},
            ]}],
            "is_default": True, "is_managed": True, "created_by": actor,
        })
        await _reg("view", r2["code"], f"{DEMO_PREFIX}摄像机面板视图")
        steps.append("对象视图：面板形态 1 个")

        # 带**筛选器**的视图（演示 widgets-filtering：筛选器作用于同标签页的数据组件）
        r3 = await _ov.create_view({
            "object_code": cam, "code": "video_cameras__demo_filtered",
            "name": f"{DEMO_PREFIX}只看某类设备", "form_factor": "full",
            "tabs": [{"key": "filtered", "label": "筛选", "widgets": [
                {"type": "filter", "title": "筛选条件", "config": {"filters": [
                    {"prop": "device_type", "op": "eq", "value": "IP_CAMERA"},
                ]}},
                {"type": "table", "title": "符合条件的摄像机",
                 "config": {"limit": 20}},
            ]}],
            "filters": [{"prop": "device_type", "op": "eq", "value": "IP_CAMERA"}],
            "is_default": False, "is_managed": True, "created_by": actor,
        })
        await _reg("view", r3["code"], f"{DEMO_PREFIX}只看某类设备")
        steps.append("对象视图：带筛选器的 1 个")

    # ---------------- 2) 索引（真的建） ----------------
    made_idx = 0
    for oc, prop in (("video_cameras", "name"), ("video_cameras", "group_id"),
                     ("video_cameras", "status"), ("train_tasks", "name"),
                     ("video_alarm_records", "name")):
        if oc not in code_of:
            continue
        try:
            r = await _ix.upsert_index({"object_code": oc, "prop_code": prop,
                                        "index_kind": "property"})
            await _reg("index", str(r["id"]), f"{oc}.{prop}")
            b = await _ix.build_index(r["id"])
            if b.get("ok"):
                made_idx += 1
        except Exception:  # noqa: BLE001
            continue
    # 故意留一个失败/过期样本，好看到失败态与重试入口
    if "video_cameras" in code_of:
        try:
            r = await _ix.upsert_index({"object_code": "video_cameras",
                                        "prop_code": "nonexistent_col",
                                        "index_kind": "property"})
        except Exception:  # noqa: BLE001
            r = None
        if r:
            await _reg("index", str(r["id"]), "video_cameras.nonexistent_col")
    steps.append(f"索引：{made_idx} 个已构建就绪")

    # ---------------- 3) 行级策略 + 资源权限 ----------------
    if "video_cameras" in code_of:
        r = await _sec.upsert_row_policy({
            "object_code": "video_cameras", "name": f"{DEMO_PREFIX}只看本部门设备",
            "description": "演示：按用户所属部门过滤",
            # 用真实存在的属性（status），并演示 user.role；dept 类属性该表没有
            "expression": "status == 'online' or user.role('ADMIN')",
            "effect": "allow", "enabled": False,   # 默认停用，避免影响你正常看数据
        })
        if r.get("ok"):
            await _reg("row_policy", str(r.get("id") or r.get("policy_id") or ""),
                       f"{DEMO_PREFIX}只看本部门设备")
        r2 = await _sec.set_resource_acl("function", "cam_online_rate",
                                         ["ADMIN", "ANNOTATOR"], ["ADMIN"], ["ADMIN"])
        await _reg("acl", "function:cam_online_rate", "函数 cam_online_rate")
        steps.append("权限：1 条行级策略（默认停用）+ 1 个资源 ACL")

    # ---------------- 4) 场景 ----------------
    s1 = await _sc.create_scenario(
        {"name": f"{DEMO_PREFIX}方案A-调低在线率阈值", "description": "演示：假设分析",
         "ttl_days": 30}, actor)
    await _reg("scenario", s1["code"], f"{DEMO_PREFIX}方案A")
    s2 = await _sc.create_scenario(
        {"name": f"{DEMO_PREFIX}方案B-维持现状", "description": "演示：对照方案",
         "ttl_days": 30}, actor)
    await _reg("scenario", s2["code"], f"{DEMO_PREFIX}方案B")
    if "video_cameras" in code_of:
        try:
            await _sc.record_edit(s1["code"], "video_cameras", "1", "modify",
                                  {"name": "闭环测试摄像头"},
                                  {"name": f"{DEMO_PREFIX}摄像头（方案A改名）"},
                                  "cam_rename")
            await _sc.record_edit(s2["code"], "video_cameras", "1", "modify",
                                  {"name": "闭环测试摄像头"},
                                  {"name": f"{DEMO_PREFIX}摄像头（方案B改名）"},
                                  "cam_rename")
        except Exception:  # noqa: BLE001
            pass
    steps.append("场景：2 个（各含 1 处改名改动，可对比）")

    # ---------------- 5) 决策 ----------------
    made_dec = 0
    for title, opts in (
        (f"{DEMO_PREFIX}是否把 3 号机位迁移到新分组",
         [{"code": "opt_a", "label": "迁移到「东区」", "params": {"group_id": 1}},
          {"code": "opt_b", "label": "保持原分组", "params": {}}]),
        (f"{DEMO_PREFIX}告警阈值从 70 调到 85",
         [{"code": "opt_up", "label": "上调到 85"},
          {"code": "opt_keep", "label": "维持 70"}]),
    ):
        try:
            r = await _dec.upsert_decision({
                "title": title, "object_code": "video_cameras", "object_key": "1",
                "category": "运维", "channel": "ontology",
                "rationale": "演示数据：用于展示决策数据与决策谱系。",
                "options": opts,
                "evidence": [{"kind": "object", "ref": "video_cameras#1",
                              "label": "摄像机 #1"}],
            }, actor_name=actor)
            if r.get("ok"):
                await _reg("decision", r["code"], title)
                made_dec += 1
        except Exception:  # noqa: BLE001
            continue
    steps.append(f"决策：{made_dec} 个（含选项与依据）")

    # ---------------- 6) 提案（三种阶段各一个） ----------------
    made_prop = []
    # 6.1 准备中
    try:
        r = await _pr.create_branch(f"{DEMO_PREFIX}给摄像机加「维护状态」字段",
                                    "演示：准备中的提案", actor)
        await _reg("branch", r["branch_code"], f"{DEMO_PREFIX}维护状态")
        await _reg("proposal", r["proposal_code"], f"{DEMO_PREFIX}维护状态")
        await _pr.save_on_branch(r["branch_code"], "property", "create",
                                 {"object_code": "video_cameras",
                                  "code": "demo_maint_status", "name": "维护状态",
                                  "prop_type": "string", "description": "演示字段"},
                                 actor)
        made_prop.append(r["proposal_code"])
    except Exception:  # noqa: BLE001
        pass
    # 6.2 审查中（部分批准）
    try:
        r = await _pr.create_branch(f"{DEMO_PREFIX}调整摄像机显示名与别名",
                                    "演示：审查中的提案", actor)
        await _reg("branch", r["branch_code"], f"{DEMO_PREFIX}显示名")
        await _reg("proposal", r["proposal_code"], f"{DEMO_PREFIX}显示名")
        await _pr.save_on_branch(r["branch_code"], "object", "update",
                                 {"code": "video_cameras",
                                  "name": "摄像机表", "plural_name": "摄像机"},
                                 actor)
        await _pr.save_on_branch(r["branch_code"], "property", "create",
                                 {"object_code": "video_cameras",
                                  "code": "demo_alias", "name": "设备别名",
                                  "prop_type": "string"}, actor)
        await _pr.request_review(r["proposal_code"], [actor], actor)
        p = await _pr.get_proposal(r["proposal_code"])
        if p and p["tasks"]:
            await _pr.review_task(p["tasks"][0]["id"], True, actor, "第一条没问题")
        made_prop.append(r["proposal_code"])
    except Exception:  # noqa: BLE001
        pass
    # 6.3 已合并（完整走一遍）
    try:
        r = await _pr.create_branch(f"{DEMO_PREFIX}给摄像机加「所属区域」字段",
                                    "演示：已合并的提案", actor)
        await _reg("branch", r["branch_code"], f"{DEMO_PREFIX}所属区域")
        await _reg("proposal", r["proposal_code"], f"{DEMO_PREFIX}所属区域")
        await _pr.save_on_branch(r["branch_code"], "property", "create",
                                 {"object_code": "video_cameras",
                                  "code": "demo_region", "name": "所属区域",
                                  "prop_type": "string", "description": "演示字段"},
                                 actor)
        await _pr.request_review(r["proposal_code"], [actor], actor)
        p = await _pr.get_proposal(r["proposal_code"])
        if p:
            for t in p["tasks"]:
                await _pr.review_task(t["id"], True, actor, "同意")
            await _pr.merge_proposal(r["proposal_code"], actor)
            # 合并产生的属性也登记，清除时一并删掉
            await _reg("property", "demo_region", "video_cameras.demo_region")
        made_prop.append(r["proposal_code"])
    except Exception:  # noqa: BLE001
        pass
    steps.append(f"提案：{len(made_prop)} 个（准备中 / 审查中 / 已合并）")

    # ---- 问数 × 本体：自带一张业务表，让「行级权限在问数里生效」肉眼可见 ----
    try:
        made_sales = await _load_sales_demo(actor)
        if made_sales:
            steps.append(made_sales)
    except Exception as e:  # noqa: BLE001
        # 不静默吞掉：失败必须说出来，否则界面显示"载入成功"但其实是残的
        steps.append(f"问数演示载入失败：{str(e)[:120]}")

    st2 = await demo_status()
    return {"ok": True, "total": st2["total"], "steps": steps,
            "by_kind": st2["by_kind"],
            "msg": f"演示数据已载入：共 {st2['total']} 项。"
                   f"（{'；'.join(steps)}）"}


# ---------------------------------------------------------------------------
# 清除
# ---------------------------------------------------------------------------
_CLEANERS: dict[str, tuple[str, str]] = {
    # kind -> (表, 用于匹配的列)
    "view": ("ai_ont_object_view", "code"),
    "index": ("ai_ont_index", "id"),
    "scenario": ("ai_ont_scenario", "code"),
    "decision": ("ai_ont_decision", "code"),
    "branch": ("ai_ont_branch", "code"),
    "proposal": ("ai_ont_proposal", "code"),
    "row_policy": ("ai_ont_row_policy", "id"),
}


# ---------------------------------------------------------------------------
# 问数 × 本体 演示：自带业务表 + 行级策略
#
# 为什么需要它：演示"行级权限在问数里真的生效"必须有**能被切分的数据**。
# 拿现成的 video_cameras 演示不行——它 55 行全是同一个 status，切了也看不出差别，
# 而且改用户既有数据是不可接受的。所以这里自带一张 `demo_sales`：
# 部门 1 / 部门 2 各 4 行，配一条 `dept == user.attribute('dept_id')` 的策略，
# 于是同一个问数问题，不同用户看到的销售额**不一样**。
# ---------------------------------------------------------------------------
SALES_TABLE = "demo_sales"
SALES_OBJECT = "demo_sales"
_SALES_ROWS = [
    (1, 1, "华东", "摄像机", 12000, "2026-01-05"),
    (2, 1, "华东", "录像机", 8000, "2026-01-18"),
    (3, 1, "华南", "摄像机", 15000, "2026-02-02"),
    (4, 1, "华南", "交换机", 3000, "2026-02-20"),
    (5, 2, "华北", "摄像机", 9000, "2026-01-09"),
    (6, 2, "华北", "录像机", 11000, "2026-01-25"),
    (7, 2, "西南", "摄像机", 7000, "2026-02-11"),
    (8, 2, "西南", "交换机", 5000, "2026-02-27"),
]


async def _load_sales_demo(actor: str) -> str:
    """建演示业务表 + 对象类型 + 行级策略，返回一句可读的小结。"""
    from datetime import date

    from . import security as _sec

    # 1) 真实表 + 数据（幂等：先删后建，表名带 demo_ 前缀，不碰业务表）
    await _svc._exec_write(f"DROP TABLE IF EXISTS {SALES_TABLE}")
    await _svc._exec_write(
        f"CREATE TABLE {SALES_TABLE} (id INTEGER PRIMARY KEY, dept INTEGER, "
        f"region VARCHAR(32), product VARCHAR(64), amount INTEGER, sold_at DATE)")
    for r in _SALES_ROWS:
        # 注意：DATE 列要传 date 对象，传字符串 asyncpg 会报
        # "invalid input ... 'str' object has no attribute 'toordinal'"
        y, m, d = (int(x) for x in r[5].split("-"))
        await _svc._exec_write(
            f"INSERT INTO {SALES_TABLE} (id,dept,region,product,amount,sold_at) "
            f"VALUES (:i,:d,:r,:p,:a,:s)",
            {"i": r[0], "d": r[1], "r": r[2], "p": r[3], "a": r[4],
             "s": date(y, m, d)})
    await _reg("sales_table", SALES_TABLE, f"{DEMO_PREFIX}销售演示表")

    # 2) 注册成对象类型（支撑表就是它自己，不是 ont_xxx）
    #
    # **别名很关键**：本体对象名/别名会参与问数检索（"人话 → 对象"）。
    # 不写别名的话，问「各部门的销售额是多少」时检索认不出这是"销售订单"，
    # 模型会去拿别的表的 cost 当"销售额"（实测返回 0）。演示数据本该是
    # **建模良好的样板**，所以这里把口语说法都登记上。
    await _svc.upsert_object({
        "code": SALES_OBJECT, "name": f"{DEMO_PREFIX}销售订单",
        "key_prop": "id", "name_prop": "product",
        "backing_table": SALES_TABLE,
        "description": "演示用：8 笔订单，分属部门 1 / 部门 2",
        "aliases": ["销售", "销售额", "销售订单", "订单", "订单金额", "成交额"],
    })
    await _reg("sales_object", SALES_OBJECT, f"{DEMO_PREFIX}销售订单")
    for code, name, pt in (("dept", "部门", "int"), ("region", "区域", "string"),
                           ("product", "产品", "string"),
                           # 属性名用**用户会说的词**（"销售额"），不是"金额"
                           ("amount", "销售额", "int"),
                           ("sold_at", "成交日期", "date")):
        await _svc.upsert_property({"object_code": SALES_OBJECT, "code": code,
                                    "name": name, "prop_type": pt})
    await _reg("sales_props", SALES_OBJECT, f"{DEMO_PREFIX}销售订单属性")

    # 3) 行级策略：只看本部门。**默认启用**（这一条就是要让你看到效果）
    r = await _sec.upsert_row_policy({
        "object_code": SALES_OBJECT,
        "name": f"{DEMO_PREFIX}只看本部门",
        "description": "演示：部门列必须等于访问者的 dept_id",
        "expression": "dept == user.attribute('dept_id')",
        "effect": "allow", "enabled": True, "priority": 10,
    })
    if r.get("id"):
        await _reg("row_policy", str(r["id"]), f"{DEMO_PREFIX}只看本部门")
    return ("问数演示：1 张自带业务表 demo_sales（8 笔订单 / 2 个部门）"
            "+ 1 条**已启用**的行级策略「只看本部门」")


#: 清除顺序很重要：先拆依赖方，最后才拆对象类型、DROP 演示表
_ORDER = ["proposal", "branch", "scenario", "decision", "index", "view",
          "row_policy", "acl", "property", "sales_props", "sales_object",
          "sales_table"]


async def clear_demo() -> dict:
    """按登记精确清除演示数据（只删登记过的，不动你自己建的东西）。"""
    await _ensure_registry()
    await _adopt_orphans()   # 清除前也认领一次，确保孤儿能被删掉
    rows = await _registered()
    if not rows:
        return {"ok": True, "cleared": 0, "msg": "没有演示数据需要清除"}

    from . import indexing as _ix

    removed: dict[str, int] = {}
    errors: list[str] = []

    def _bump(k: str) -> None:
        removed[k] = removed.get(k, 0) + 1

    # 顺序很重要：先删依赖方（提案→分支、场景→编辑、索引→底层索引），
    # 最后才拆对象类型、DROP 演示表（否则残留属性会挡住）
    order = _ORDER
    for kind in order:
        for r in [x for x in rows if x["kind"] == kind]:
            try:
                await _clear_one(kind, r["ref"], _ix)
                _bump(kind)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{kind} {r['ref']}：{str(e)[:60]}")
    # 未在 order 里的种类也尝试清掉
    for r in rows:
        if r["kind"] in order:
            continue
        try:
            await _clear_one(r["kind"], r["ref"], _ix)
            _bump(r["kind"])
        except Exception as e:  # noqa: BLE001
            errors.append(f"{r['kind']} {r['ref']}：{str(e)[:60]}")

    await _svc._exec_write("DELETE FROM ai_ont_demo", {})
    total = sum(removed.values())
    detail = "、".join(f"{_KIND_LABEL.get(k, k)} {v}" for k, v in removed.items())
    return {"ok": True, "cleared": total, "by_kind": removed, "errors": errors,
            "msg": f"已清除演示数据 {total} 项（{detail}）"
                   + (f"；{len(errors)} 项失败" if errors else "")}


async def _clear_one(kind: str, ref: str, ix: Any) -> None:
    if kind in ("proposal",):
        await _svc._exec_write("DELETE FROM ai_ont_proposal_comment WHERE proposal_code=:c",
                               {"c": ref})
        await _svc._exec_write("DELETE FROM ai_ont_proposal_task WHERE proposal_code=:c",
                               {"c": ref})
        await _svc._exec_write("DELETE FROM ai_ont_proposal WHERE code=:c", {"c": ref})
        return
    if kind == "branch":
        await _svc._exec_write("DELETE FROM ai_ont_branch_change WHERE branch_code=:c",
                               {"c": ref})
        await _svc._exec_write("DELETE FROM ai_ont_branch WHERE code=:c", {"c": ref})
        return
    if kind == "scenario":
        await _svc._exec_write("DELETE FROM ai_ont_scenario_edit WHERE scenario_code=:c",
                               {"c": ref})
        await _svc._exec_write("DELETE FROM ai_ont_scenario WHERE code=:c", {"c": ref})
        return
    if kind == "decision":
        for t in ("ai_ont_decision_option", "ai_ont_decision_evidence",
                  "ai_ont_decision_impact"):
            await _svc._exec_write(f"DELETE FROM {t} WHERE decision_code=:c", {"c": ref})
        await _svc._exec_write("DELETE FROM ai_ont_decision WHERE code=:c", {"c": ref})
        return
    if kind == "index":
        row = (await _svc._exec(
            "SELECT COALESCE(index_name,'') FROM ai_ont_index WHERE id=:i",
            {"i": int(ref)})).fetchone()
        if row and row[0]:
            await ix._drop_pg_index(row[0])
        await _svc._exec_write("DELETE FROM ai_ont_index WHERE id=:i", {"i": int(ref)})
        return
    if kind == "view":
        await _svc._exec_write("DELETE FROM ai_ont_object_view_version WHERE view_code=:c",
                               {"c": ref})
        await _svc._exec_write("DELETE FROM ai_ont_object_view WHERE code=:c", {"c": ref})
        return
    if kind == "row_policy":
        await _svc._exec_write("DELETE FROM ai_ont_row_policy WHERE id=:i", {"i": int(ref)})
        return
    if kind == "acl":
        rk, _, rc = ref.partition(":")
        await _svc._exec_write(
            "DELETE FROM ai_ont_resource_acl WHERE resource_kind=:k AND resource_code=:c",
            {"k": rk, "c": rc})
        return
    if kind == "property":
        # 演示合并进来的属性：按 (object_code, code) 删
        oc, _, pc = ref.partition(".")
        await _svc._exec_write(
            "DELETE FROM ai_ont_property WHERE object_code=:o AND code=:c",
            {"o": oc, "c": pc})
        return
    table, col = _CLEANERS.get(kind, ("", ""))
    if table:
        await _svc._exec_write(f"DELETE FROM {table} WHERE {col}=:r", {"r": ref})
        return
    raise CustomException(msg=f"不认识的演示数据种类 {kind}")


async def demo_report() -> dict:
    """载入后各页面的可见内容统计（用来证明"每页都有东西可看"）。"""
    from . import indexing as _ix
    from . import object_view as _ov
    from . import proposal as _pr
    from . import scenario as _sc

    views = await _ov.list_views()
    idx = await _ix.index_summary()
    props = await _pr.list_proposals()
    scns = await _sc.list_scenarios()
    decs = (await _svc._exec(
        "SELECT count(*) FROM ai_ont_decision WHERE is_deleted=false", {})).scalar() or 0
    policies = (await _svc._exec(
        "SELECT count(*) FROM ai_ont_row_policy", {})).scalar() or 0
    return {"ok": True, "pages": {
        "对象视图": f"{len(views)} 个（其中默认 {sum(1 for v in views if v['is_default'])} 个）",
        "索引": f"{idx['total']} 个，就绪 {idx['by_status'].get('ready', 0)}，"
                f"占用 {idx['total_size_human']}",
        "提案": f"{len(props)} 个（准备中 "
                f"{sum(1 for p in props if p['stage'] == 'preparing')}、审查中 "
                f"{sum(1 for p in props if p['stage'] == 'in_review')}、已合并 "
                f"{sum(1 for p in props if p['stage'] == 'merged')}）",
        "场景": f"{len(scns)} 个",
        "决策": f"{decs} 个",
        "行级策略": f"{policies} 条",
    }, "msg": "统计完成"}
