"""演示数据补丁二段：市场（自有资产→提交/分享）+ 图视图（绑定领域）。幂等。"""
from __future__ import annotations

import requests

BASE = "http://127.0.0.1:8002/api/v1"
_ok = _skip = _fail = 0


def rep(tag: str, name: str, err: str = "") -> None:
    global _ok, _skip, _fail
    if tag == "OK":
        _ok += 1
        print(f"  [OK]   {name}")
    elif tag == "SKIP":
        _skip += 1
        print(f"  [SKIP] {name}")
    else:
        _fail += 1
        print(f"  [FAIL] {name}: {err[:160]}")


def main() -> None:
    login = requests.post(
        f"{BASE}/system/auth/login",
        data={"username": "admin", "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
        timeout=15,
    ).json()
    h = {"Authorization": f"Bearer {login['data']['access_token']}"}

    def get(p, params=None):
        return requests.get(f"{BASE}{p}", headers=h, params=params, timeout=30)

    def post(p, payload):
        return requests.post(f"{BASE}{p}", headers=h, json=payload, timeout=30)

    def lst(p) -> list:
        try:
            d = get(p).json().get("data")
            if isinstance(d, list):
                return d
            if isinstance(d, dict):
                for k in ("items", "list", "rows"):
                    if isinstance(d.get(k), list):
                        return d[k]
                for v in d.values():
                    if isinstance(v, list):
                        return v
        except Exception:
            pass
        return []

    # ---------------------------------------------------------- #
    # 1. 自有工具 ×2（市场提交/分享、我的资产卡片都依赖自有资产）
    # ---------------------------------------------------------- #
    print("== 自有工具 ==")
    tools = [
        {"name": "气象数据接口", "kind": "http", "method": "GET",
         "url": "http://127.0.0.1:8765/weather", "description": "按城市查询气象实况",
         "params_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
         "enabled": True},
        {"name": "工单查询接口", "kind": "http", "method": "GET",
         "url": "http://127.0.0.1:8765/tickets", "description": "查询运维工单列表与状态",
         "params_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
         "enabled": True},
    ]
    have = {t.get("name") for t in lst("/ai/tools/list")}
    for t in tools:
        if t["name"] in have:
            rep("SKIP", f"工具:{t['name']}")
            continue
        try:
            body = post("/ai/tools/create", t).json()
            rep(*(("OK", f"工具:{t['name']}") if body.get("code") in (0, None) else ("FAIL", f"工具:{t['name']}", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            rep("FAIL", f"工具:{t['name']}", str(e))

    # ---------------------------------------------------------- #
    # 2. 市场审核中心：提交自有工具/技能（pending 供审核）
    # ---------------------------------------------------------- #
    print("== 审核中心 ==")
    if lst("/ai/market/review/list"):
        rep("SKIP", "审核中心（已有待审）")
    else:
        mine_tool = next(
            (t for t in lst("/ai/market/mine?asset_type=tool")
             if t.get("name") in ("气象数据接口", "工单查询接口")), None
        )
        if mine_tool:
            try:
                body = post("/ai/market/submit", {
                    "asset_type": "tool",
                    "real_id": mine_tool.get("real_id") or mine_tool.get("id"),
                    "name": mine_tool.get("name"),
                    "description": "共享给其他空间安装使用（演示待审数据）",
                }).json()
                rep(*(("OK", "市场提交:气象数据接口") if body.get("code") in (0, None) else ("FAIL", "市场提交", str(body.get("msg")))))
            except Exception as e:  # noqa: BLE001
                rep("FAIL", "市场提交", str(e))
        else:
            rep("FAIL", "市场提交", "自有工具未就绪")

    # ---------------------------------------------------------- #
    # 3. 分享：发给协作用户 ac(id=2)，让分享链路有数据
    # ---------------------------------------------------------- #
    print("== 分享链路 ==")
    shares = lst("/ai/market/shares")
    mine_tool = next(
        (t for t in lst("/ai/market/mine?asset_type=tool") if t.get("name") == "工单查询接口"), None
    )
    if shares:
        rep("SKIP", "分享（列表已有数据）")
    elif mine_tool:
        try:
            body = post("/ai/market/shares/share", {
                "to_user_id": 2,
                "asset_type": "tool",
                "real_id": mine_tool.get("real_id") or mine_tool.get("id"),
                "name": mine_tool.get("name"),
                "message": "演示：共享工具给协作成员 ac",
            }).json()
            rep(*(("OK", "分享:工单查询接口→ac") if body.get("code") in (0, None) else ("FAIL", "分享", str(body.get("msg")))))
        except Exception as e:  # noqa: BLE001
            rep("FAIL", "分享", str(e))
    else:
        rep("FAIL", "分享", "自有工具未就绪")

    # ---------------------------------------------------------- #
    # 4. 图视图：必须绑定领域（domain_code）
    # ---------------------------------------------------------- #
    print("== 本体图视图 ==")
    if lst("/ai/ontology/graph-views"):
        rep("SKIP", "图视图（已有）")
    else:
        domains = lst("/ai/query/domain/list")
        code = ""
        if domains:
            d0 = domains[0]
            code = d0.get("code") or d0.get("domain_code") or ""
        if not code:
            rep("FAIL", "图视图", "无可用领域(domain/list 空)")
        else:
            for v in (
                {"code": "gv_core", "name": "核心对象关系图", "description": "演示：核心对象两跳关系",
                 "graph_kind": "saved", "domain_code": code, "_mode": "create"},
                {"code": "gv_biz", "name": "业务域全景图", "description": "演示：业务域对象全景",
                 "graph_kind": "saved", "domain_code": code, "_mode": "create"},
            ):
                try:
                    body = post("/ai/ontology/graph-views/save", v).json()
                    rep(*(("OK", f"图视图:{v['name']}") if body.get("code") in (0, None) else ("FAIL", f"图视图:{v['name']}", str(body.get("msg")))))
                except Exception as e:  # noqa: BLE001
                    rep("FAIL", f"图视图:{v['name']}", str(e))

    print()
    print(f"二段完成：新增 {_ok} / 已存在 {_skip} / 失败 {_fail}")


if __name__ == "__main__":
    main()
