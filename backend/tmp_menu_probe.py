"""探针：登录用户后端(8002)，拉取当前用户菜单树，检查「智能问数」目录结构是否已迁移生效。"""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8002"


def req(path, method="GET", data=None, headers=None, form=None):
    url = BASE + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            h.update(headers)
    elif data is not None:
        body = json.dumps(data).encode()
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


# 1. 登录（form data: username/password，dev 无验证码）
st, txt = req(
    "/api/v1/system/auth/login",
    method="POST",
    form={"username": "admin", "password": "123456"},
)
print("login:", st)
try:
    j = json.loads(txt)
except Exception:
    print(txt[:500])
    raise SystemExit(1)
if j.get("code") != 0 and j.get("success") is not False:
    print("login resp:", json.dumps(j, ensure_ascii=False)[:500])
token = (j.get("data") or {}).get("access_token") or (j.get("data") or {}).get("token")
print("token got:", bool(token), "keys:", list((j.get("data") or {}).keys()))

# 2. 拉当前用户信息（含 menus）
st, txt = req(
    "/api/v1/system/user/current/info",
    headers={"Authorization": f"Bearer {token}"},
)
print("info:", st)
if st == 500:
    with open("tmp_500.txt", "w", encoding="utf-8") as f:
        import urllib.error as urlerr

        r2 = urllib.request.Request(
            "/api/v1/system/user/current/info".join(["http://127.0.0.1:8002", ""]),
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(r2, timeout=15) as resp:
                raw = resp.read()
        except urlerr.HTTPError as e:
            raw = e.read()
        f.write(raw.decode("utf-8", errors="replace"))
    raise SystemExit(1)
try:
    info = json.loads(txt)
except Exception:
    print(txt[:300])
    raise SystemExit(1)
menus = (info.get("data") or {}).get("menus")
print("menus count:", len(menus) if menus else None)


def walk(items, depth=0, out=None):
    if out is None:
        out = []
    for m in items or []:
        out.append(
            {
                "route_name": m.get("route_name"),
                "title": m.get("title"),
                "type": m.get("type"),
                "path": m.get("route_path"),
                "comp": m.get("component_path"),
                "hidden": m.get("hidden"),
                "redirect": m.get("redirect"),
                "order": m.get("order"),
            }
        )
        if m.get("children"):
            walk(m.get("children"), depth + 1, out)
    return out


flat = walk(menus)
# 聚焦 AI 相关
ai = [m for m in flat if m["route_name"] in ("AI", "AiQueryGroup", "AiQuery", "AiIntegration", "AiEval", "AiQueryReports", "AiAsset")]
print("\n===== AI 相关菜单 =====")
for m in ai:
    print(f"{m['route_name']:18s} type={m['type']} hidden={m['hidden']} path={m['path']} comp={m['comp']} redirect={m['redirect']} order={m['order']} title={m['title']}")
