"""AI 管理全子模块演示数据种子（dev 库）。

目的：让每个 AI 管理页面打开都有像样的测试数据，不留空表。
特性：
- 幂等：按 name/code 查重，重复执行不会堆垃圾；
- 逐条容错：单条失败打印原因不影响其它；
- 走真实后端接口（数据与页面渲染完全一致）。

用法：cd backend && .venv/Scripts/python.exe scripts/seed_ai_demo.py
"""
from __future__ import annotations

import requests

BASE = "http://127.0.0.1:8002/api/v1"

_ok = _skip = _fail = 0


def report(tag: str, name: str, err: str = "") -> None:
    global _ok, _skip, _fail
    if tag == "OK":
        _ok += 1
        print(f"  [OK]   {name}")
    elif tag == "SKIP":
        _skip += 1
        print(f"  [SKIP] {name}（已存在）")
    else:
        _fail += 1
        print(f"  [FAIL] {name}: {err[:120]}")


def main() -> None:
    login = requests.post(
        f"{BASE}/system/auth/login",
        data={"username": "admin", "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
        timeout=15,
    ).json()
    h = {"Authorization": f"Bearer {login['data']['access_token']}"}

    def get(path: str, params: dict | None = None):
        return requests.get(f"{BASE}{path}", headers=h, params=params, timeout=30)

    def post(path: str, payload: dict):
        return requests.post(f"{BASE}{path}", headers=h, json=payload, timeout=30)

    def put(path: str, payload: dict):
        return requests.put(f"{BASE}{path}", headers=h, json=payload, timeout=30)

    def list_of(path: str) -> list:
        try:
            body = get(path).json()
            data = body.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for k in ("items", "list", "rows"):
                    if isinstance(data.get(k), list):
                        return data[k]
                for v in data.values():
                    if isinstance(v, list):
                        return v
        except Exception:
            pass
        return []

    # ---------------------------------------------------------- #
    # 1. 模型供应商（控制台「供应商 0」）
    # ---------------------------------------------------------- #
    print("== 模型供应商 ==")
    providers = [
        {
            "name": "OpenAI 官方",
            "protocol": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-proj-demo-mask",
            "description": "GPT 系列官方端点（演示配置，key 为占位值）",
        },
        {
            "name": "DeepSeek 开放平台",
            "protocol": "openai",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-demo-mask",
            "description": "DeepSeek-V3/R1 兼容 OpenAI 协议",
        },
        {
            "name": "本地 vLLM 推理服务",
            "protocol": "openai",
            "base_url": "http://192.168.1.100:8000/v1",
            "api_key": "local-none",
            "description": "内网 GPU 节点 vLLM（OpenAI 兼容）",
        },
    ]
    have = {p.get("name") for p in list_of("/ai/providers/list")}
    for p in providers:
        if p["name"] in have:
            report("SKIP", p["name"])
            continue
        try:
            r = post("/ai/providers/create", p)
            body = r.json()
            if body.get("code") in (0, None):
                report("OK", p["name"])
            else:
                report("FAIL", p["name"], str(body.get("msg")))
        except Exception as e:  # noqa: BLE001
            report("FAIL", p["name"], str(e))

    # ---------------------------------------------------------- #
    # 2. 提示词（/ai/prompts/list = 0）：用内置模板批量创建
    # ---------------------------------------------------------- #
    print("== 提示词 ==")
    tpl_names: list[str] = []
    try:
        tpls = get("/ai/prompts/templates").json().get("data") or []
        tpl_names = [t.get("key") or t.get("name") for t in tpls if isinstance(t, dict)]
    except Exception:
        tpl_names = []
    prompt_names = {
        "通用问答助手": "通用问答助手",
        "数据分析问数": "数据分析问数",
        "AI 报告生成": "AI 报告生成",
        "代码审查意见": "代码审查意见",
    }
    have = {p.get("name") for p in list_of("/ai/prompts/list")}
    made = 0
    for name in prompt_names:
        if name in have:
            report("SKIP", name)
            continue
        # 优先模板创建（内置模板保证 blocks 合法）；无模板则手工 blocks
        used_tpl = tpl_names[made % len(tpl_names)] if tpl_names else None
        try:
            if used_tpl:
                r = post("/ai/prompts/create-from-template", {"key": used_tpl, "name": name})
            else:
                r = post(
                    "/ai/prompts/create",
                    {
                        "name": name,
                        "category": "通用",
                        "blocks": [
                            {"type": "system", "content": f"你是「{name}」，请用简洁专业的中文回答。"},
                            {"type": "user", "content": "{{question}}"},
                        ],
                        "variables": ["question"],
                        "enabled": True,
                    },
                )
            body = r.json()
            if body.get("code") in (0, None):
                report("OK", name)
                made += 1
            else:
                report("FAIL", name, str(body.get("msg")))
        except Exception as e:  # noqa: BLE001
            report("FAIL", name, str(e))

    # ---------------------------------------------------------- #
    # 3. AI 开发·接入应用（/ai/develop/list = 0）
    # ---------------------------------------------------------- #
    print("== 接入应用（AI 开发） ==")
    apps = [
        {"name": "集团数据大屏", "description": "大屏看板接入平台问数与指标能力"},
        {"name": "第三方 BI 系统", "description": "外部 BI 平台经 REST/MCP 调用平台能力"},
        {"name": "企业门户机器人", "description": "门户侧 AI 机器人（嵌入对话 + 能力调用）"},
    ]
    have = {a.get("name") for a in list_of("/ai/develop/list")}
    for a in apps:
        if a["name"] in have:
            report("SKIP", a["name"])
            continue
        try:
            r = post("/ai/develop/create", a)
            body = r.json()
            if body.get("code") in (0, None):
                report("OK", a["name"])
            else:
                report("FAIL", a["name"], str(body.get("msg")))
        except Exception as e:  # noqa: BLE001
            report("FAIL", a["name"], str(e))

    # 审批通知配置（/ai/develop/notify-config = 0）
    try:
        cur = get("/ai/develop/notify-config").json().get("data") or {}
        if not (cur.get("channels") or cur.get("configs")):
            r = put(
                "/ai/develop/notify-config",
                {
                    "channels": ["email", "webhook"],
                    "configs": {
                        "email": {"to": "ai-ops@example.com", "subject_prefix": "[AI审批] "},
                        "webhook": {"url": "http://127.0.0.1:9/notify", "timeout_sec": 5},
                    },
                },
            )
            body = r.json()
            report(*(("OK", "审批通知配置") if body.get("code") in (0, None) else ("FAIL", "审批通知配置", str(body.get("msg")))))
        else:
            report("SKIP", "审批通知配置")
    except Exception as e:  # noqa: BLE001
        report("FAIL", "审批通知配置", str(e))

    # ---------------------------------------------------------- #
    # 4. 知识库数据源 / 关系类型
    # ---------------------------------------------------------- #
    print("== 知识库数据源 / 关系类型 ==")
    dss = [
        {"name": "生产 PostgreSQL", "description": "生产主库（pg17），只读同步"},
        {"name": "业务 MySQL", "description": "历史业务库（MySQL 8），按需接入"},
    ]
    have = {d.get("name") for d in list_of("/ai/knowledge/datasources/list")}
    for d in dss:
        if d["name"] in have:
            report("SKIP", d["name"])
            continue
        try:
            r = post("/ai/knowledge/datasources/create", d)
            body = r.json()
            report(*(("OK", d["name"]) if body.get("code") in (0, None) else ("FAIL", d["name"], str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", d["name"], str(e))

    rels = ["属于", "依赖", "前置", "汇总"]
    have = {x.get("name") for x in list_of("/ai/knowledge/relation-types")}
    for name in rels:
        if name in have:
            report("SKIP", f"关系类型:{name}")
            continue
        try:
            r = post("/ai/knowledge/relation-types", {"name": name, "description": f"实体间「{name}」关系"})
            body = r.json()
            report(*(("OK", f"关系类型:{name}") if body.get("code") in (0, None) else ("FAIL", f"关系类型:{name}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", f"关系类型:{name}", str(e))

    # ---------------------------------------------------------- #
    # 5. 能力市场：提交审核 + 分享
    # ---------------------------------------------------------- #
    print("== 能力市场（审核中心 / 分享给我） ==")
    # 5.1 提交自有资产到市场 → 审核中心出现待审条目
    if not list_of("/ai/market/review/list"):
        mine_tools = list_of("/ai/market/mine/tool") or []
        mine_skills = list_of("/ai/market/mine/skill") or []
        picks = []
        if mine_tools:
            t = mine_tools[0]
            picks.append({"asset_type": "tool", "source_id": t.get("real_id") or t.get("id"),
                          "name": t.get("name"), "description": "提交到共享市场供其他空间安装使用"})
        if mine_skills:
            s = mine_skills[0]
            picks.append({"asset_type": "skill", "source_id": s.get("real_id") or s.get("id"),
                          "name": s.get("name"), "description": "技能共享：市场橱窗上架"})
        for p in picks:
            if not p.get("source_id"):
                continue
            try:
                r = post("/ai/market/submit", p)
                body = r.json()
                report(*(("OK", f"市场提交:{p['name']}") if body.get("code") in (0, None) else ("FAIL", f"市场提交:{p['name']}", str(body.get("msg")))))
            except Exception as e:  # noqa: BLE001
                report("FAIL", f"市场提交:{p['name']}", str(e))
    else:
        report("SKIP", "市场提交（审核中心已有数据）")

    # 5.2 分享资产给用户 ac（id=2）→ 「分享给我」侧演示由对方数据不可控，改为分享动作本身可查
    if not list_of("/ai/market/shares"):
        mine = list_of("/ai/market/mine/skill") or []
        if mine:
            s = mine[0]
            try:
                r = post(
                    "/ai/market/shares/share",
                    {
                        "to_user_id": 2,
                        "asset_type": "skill",
                        "source_id": s.get("real_id") or s.get("id"),
                        "name": s.get("name"),
                        "message": "演示：共享技能给协作成员",
                    },
                )
                body = r.json()
                report(*(("OK", f"市场分享:{s.get('name')}") if body.get("code") in (0, None) else ("FAIL", f"市场分享:{s.get('name')}", str(body.get("msg")))))
            except Exception as e:  # noqa: BLE001
                report("FAIL", f"市场分享:{s.get('name')}", str(e))
        else:
            report("FAIL", "市场分享", "无自有技能可分享")
    else:
        report("SKIP", "市场分享")

    # ---------------------------------------------------------- #
    # 6. 本体：对象分组 / 共享属性 / 接口 / 图视图
    # ---------------------------------------------------------- #
    print("== 本体（分组/共享属性/接口/图视图） ==")
    groups = [
        {"code": "grp_business", "name": "业务域", "description": "订单、合同、结算等业务对象", "color": "#409eff", "sort": 1},
        {"code": "grp_tech", "name": "技术域", "description": "设备、摄像头、算法等技术对象", "color": "#67c23a", "sort": 2},
        {"code": "grp_common", "name": "公共域", "description": "跨域复用的公共对象与字典", "color": "#e6a23c", "sort": 3},
    ]
    have = {g.get("code") for g in list_of("/ai/ontology/groups")}
    for g in groups:
        if g["code"] in have:
            report("SKIP", f"分组:{g['name']}")
            continue
        try:
            r = post("/ai/ontology/group/save", g)
            body = r.json()
            report(*(("OK", f"分组:{g['name']}") if body.get("code") in (0, None) else ("FAIL", f"分组:{g['name']}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", f"分组:{g['name']}", str(e))

    props = [
        {"code": "sp_code", "name": "对象编码", "description": "全局唯一业务编码"},
        {"code": "sp_owner", "name": "责任主体", "description": "对象归口责任部门/人"},
        {"code": "sp_lifecycle", "name": "生命周期", "description": "草稿/在用/停用状态"},
        {"code": "sp_security", "name": "密级", "description": "公开/内部/机密"},
    ]
    have = {p.get("code") for p in list_of("/ai/ontology/shared-properties")}
    for p in props:
        if p["code"] in have:
            report("SKIP", f"共享属性:{p['name']}")
            continue
        try:
            r = post("/ai/ontology/shared-property/save", p)
            body = r.json()
            report(*(("OK", f"共享属性:{p['name']}") if body.get("code") in (0, None) else ("FAIL", f"共享属性:{p['name']}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", f"共享属性:{p['name']}", str(e))

    ifaces = [
        {"code": "if_query", "name": "标准查询接口", "description": "按对象编码+条件的统一查询契约",
         "required_properties": [], "required_links": []},
        {"code": "if_event", "name": "事件推送接口", "description": "对象变更事件的出站契约",
         "required_properties": [], "required_links": []},
    ]
    have = {i.get("code") for i in list_of("/ai/ontology/interfaces")}
    for i in ifaces:
        if i["code"] in have:
            report("SKIP", f"接口:{i['name']}")
            continue
        try:
            r = post("/ai/ontology/interface/save", i)
            body = r.json()
            report(*(("OK", f"接口:{i['name']}") if body.get("code") in (0, None) else ("FAIL", f"接口:{i['name']}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", f"接口:{i['name']}", str(e))

    views = [
        {"code": "gv_core", "name": "核心对象关系图", "description": "演示：核心对象两跳关系视图", "_mode": "create"},
        {"code": "gv_biz", "name": "业务域全景图", "description": "演示：业务域对象全景", "_mode": "create"},
    ]
    have = {v.get("code") for v in list_of("/ai/ontology/graph-views")}
    for v in views:
        if v["code"] in have:
            report("SKIP", f"图视图:{v['name']}")
            continue
        try:
            r = post("/ai/ontology/graph-views/save", v)
            body = r.json()
            report(*(("OK", f"图视图:{v['name']}") if body.get("code") in (0, None) else ("FAIL", f"图视图:{v['name']}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", f"图视图:{v['name']}", str(e))

    # ---------------------------------------------------------- #
    # 7. 智能体分类（/ai/agents/categories/list = 0）
    # ---------------------------------------------------------- #
    print("== 智能体分类 ==")
    cats = [
        {"name": "数据问数", "parent_id": None, "sort": 1},
        {"name": "知识助手", "parent_id": None, "sort": 2},
        {"name": "流程自动化", "parent_id": None, "sort": 3},
    ]
    have = {c.get("name") for c in list_of("/ai/agents/categories/list")}
    for c in cats:
        if c["name"] in have:
            report("SKIP", f"分类:{c['name']}")
            continue
        try:
            r = post("/ai/agents/categories/create", c)
            body = r.json()
            report(*(("OK", f"分类:{c['name']}") if body.get("code") in (0, None) else ("FAIL", f"分类:{c['name']}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            report("FAIL", f"分类:{c['name']}", str(e))

    print()
    print(f"完成：新增 {_ok} / 已存在 {_skip} / 失败 {_fail}")


if __name__ == "__main__":
    main()
