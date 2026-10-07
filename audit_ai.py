import os, re, glob, json

BASE="D:/AIStation/backend/app/plugin/module_ai"
FRONT="D:/AIStation/frontend/src/api/module_ai"

def norm_path(p):
    # replace ${...} and `...` interpolations with {p}
    p = re.sub(r'\$\{[^}]*\}', '{p}', p)
    p = re.sub(r'\$\{[A-Z_]+\}', '{p}', p)
    # normalize {any_param} -> {p}
    p = re.sub(r'\{[^}]*\}', '{p}', p)
    return p

# --- backend routes -> full path (mount under /ai) ---
back_routes=set()  # (method, path)
for ctrl in glob.glob(BASE+"/**/controller.py", recursive=True):
    mod=os.path.basename(os.path.dirname(ctrl))
    raw=open(ctrl,encoding='utf-8').read()
    # find router name
    rname=None
    for m in re.finditer(r'(\w+Router)\s*=\s*APIRouter\(', raw):
        rname=m.group(1)
    # find prefix in same file
    prefix=""
    pm=re.search(r'prefix\s*=\s*"([^"]+)"', raw)
    if pm: prefix=pm.group(1)
    if not prefix:
        # look in router file / __init__
        for other in glob.glob(BASE+"/"+mod+"/**/*.py", recursive=True):
            o=open(other,encoding='utf-8').read()
            pm=re.search(r'prefix\s*=\s*"([^"]+)"', o)
            if pm: prefix=pm.group(1); break
    for m in re.finditer(r'@\w+Router\.(get|post|put|delete|patch)\("([^"]+)"', raw):
        method=m.group(1).upper(); path=m.group(2)
        full=("/ai"+prefix+path if prefix else "/ai"+path)
        back_routes.add((method, norm_path(full)))

# --- frontend calls -> full path ---
front_calls=[]  # (method, path, file^func)
for f in glob.glob(FRONT+"/*.ts"):
    raw=open(f,encoding='utf-8').read()
    # API_PATH / BASE / CAT_PATH / DS definitions
    defs={}
    for dm in re.finditer(r'(API_PATH|BASE|CAT_PATH|DS\w*|KNOWLEDGE\w*)\s*=\s*("([^"]+)"|`([^`]+)`)', raw):
        name=dm.group(1); val=dm.group(3) or dm.group(4)
        defs[name]=val
    fname=os.path.basename(f)
    # find function blocks and their url
    for fm in re.finditer(r'export function (\w+)\([^)]*\)\s*\{', raw):
        fn=fm.group(1)
        seg=raw[fm.start():fm.start()+1600]
        um=re.search(r'url:\s*(`[^`]+`|"[^"]+")', seg)
        mm=re.search(r'method:\s*"(get|post|put|delete|patch)"', seg)
        if not um: continue
        url=um.group(1)[1:-1]
        method=(mm.group(1).upper() if mm else "GET")
        # substitute known defs
        for k,v in defs.items():
            url=url.replace("${"+k+"}", v)
        # resolve remaining ${...} to {x}
        url=norm_path(url)
        # strip query params after ?
        url=url.split("?")[0]
        front_calls.append((method, url, fname+":"+fn))

# normalize frontend to /ai-prefixed path (they are like /ai/query/... or /query/...)
def to_full(method,url):
    if url.startswith("/ai"):
        return url
    return "/ai"+url

front_set=set()
for m,u,src in front_calls:
    front_set.add((m, to_full(m,u)))

# unmatched frontend -> backend
unmatched=[]
for m,u,src in front_calls:
    fu=to_full(m,u)
    found=False
    for bm,bp in back_routes:
        if bm==m and re.match('^'+re.escape(bp)+'$', fu):
            found=True; break
    if not found:
        unmatched.append((m,to_full(m,u),src))

# unmatched backend (not called by frontend) - informational
called_paths=set()
for m,u,src in front_calls:
    called_paths.add(u.replace("{x}","{x}"))
unused=[]
for bm,bp in back_routes:
    found=False
    for cm,cu in front_set:
        if cm==bm and re.match('^'+re.escape(bp)+'$', cu):
            found=True; break
    if not found:
        unused.append((bm,bp))

print("=== 后端路由总数:", len(back_routes))
print("=== 前端调用总数:", len(front_calls))
print("=== 前端调用了但后端无对应路由 (穿不上) ===")
for m,u,s in unmatched:
    print(f"  {m} {u}  <- {s}")
print("=== 后端有路由但前端未调用 (可能无用) ===")
seen=set()
for bm,bp in unused:
    key=(bm,bp.replace("{x}","{x}"))
    if key in seen: continue
    seen.add(key)
    print(f"  {bm} {bp}")
