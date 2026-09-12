# Phase 5B：实时协作（P7）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax.
> **Spec:** `docs/superpowers/specs/2026-09-13-phase5b-realtime-collaboration-design.md`

**Goal:** 协作 WS 加鉴权、锁走 DB、暴露在线/焦点/光标，前端工作台接入并在远端标注时重载当前图。

**Architecture:** 后端改造 `collaboration/controller.py`（token 鉴权 + 房间 presence + DB 锁）；前端新增 `useCollab` composable 并接入工作台。

## Global Constraints

- 后端 `backend`：`uv run pytest`、`uv run ruff check`（只判断新增）；不新增依赖。
- 前端 `frontend`：`pnpm type-check`、目标文件 eslint/prettier clean；不新增依赖。
- 中文注释；提交 `feat(annotation): 中文描述`；禁 `git add -A`。
- E2E 关闭引导 Tour。

---

### Task 1: 后端 WS 鉴权 + presence + DB 锁

**Files:**
- Modify: `backend/app/api/v1/module_annotation/collaboration/controller.py`
- Test: `backend/tests/test_collaboration_ws.py`

**Interfaces:**
- Produces：`parse_ws_user(token) -> tuple[int,str] | None`、`presence_list(task_id) -> list[dict]`。

- [ ] **Step 1: 写失败测试**

```python
"""协作 WS 鉴权与 presence 助手测试。"""
import json
from datetime import datetime, timedelta

from app.api.v1.module_annotation.collaboration import controller as C


def test_parse_ws_user_invalid():
    assert C.parse_ws_user(None) is None
    assert C.parse_ws_user("not-a-jwt") is None


def test_parse_ws_user_valid():
    from app.core.security import create_access_token
    from app.api.v1.module_system.auth.schema import JWTPayloadSchema

    token = create_access_token(
        JWTPayloadSchema(
            sub=json.dumps({"user_id": 7, "user_name": "alice"}),
            is_refresh=False,
            exp=datetime.now() + timedelta(minutes=5),
        )
    )
    assert C.parse_ws_user(token) == (7, "alice")


def test_presence_list_empty():
    assert C.presence_list(999999) == []
```

- [ ] **Step 2: 运行确认失败** → `uv run pytest tests/test_collaboration_ws.py -q`（FAIL）

- [ ] **Step 3: 实现**

重写 `collaboration/controller.py`：
- 顶部：`import json`；`from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect`；`from app.core.security import decode_access_token`；`from ..annotation.service import AnnotationService`；移除 `image_crud` 依赖。
- `_rooms: dict[int, dict[int, dict]]`（user_id → `{"ws": WebSocket, "name": str}`）。
- `parse_ws_user(token)`：decode → `json.loads(payload.sub)` → `(int(d["user_id"]), str(d.get("user_name") or d["user_id"]))`；异常返回 None。
- `presence_list(task_id)`：返回 `[{"id": uid, "name": v["name"]} for uid, v in _rooms.get(task_id, {}).items()]`。
- 端点签名 `async def collaboration_ws(ws: WebSocket, task_id: int, token: str | None = Query(None))`：
  - `await ws.accept()` → `parsed = parse_ws_user(token)`；None → `await ws.close(code=4001); return`。
  - 注册房间；向新用户发 `{"type":"room:presence","users":presence_list(task_id)}`；向他人广播 `user:join`（含 name）。
  - 事件：`annotate:*` 转发含 user `{id,name}`；`image:focus`、`cursor:move` 转发；`image:lock` 调 `AnnotationService.lock_image(image_id, user_id)`，返回 `{"locked": True, ...}` → 回 `image:lock:denied`，否则广播 `image:lock`；`image:unlock` 调 `AnnotationService.unlock_image` 并广播。
  - finally：移除房间项；广播 `user:leave`；对本用户仍持有的 DB 锁调用 `unlock_image`。
- `_broadcast` 适配新结构（`v["ws"]`）。

- [ ] **Step 4: 运行测试通过** → `uv run pytest tests/test_collaboration_ws.py -q`（PASS）

- [ ] **Step 5: ruff + 提交**

```bash
uv run ruff check app/api/v1/module_annotation/collaboration/controller.py
git add backend/app/api/v1/module_annotation/collaboration/controller.py backend/tests/test_collaboration_ws.py
git commit -m "feat(annotation): 协作WS鉴权、在线列表与DB锁"
```

---

### Task 2: 前端 useCollab composable

**Files:**
- Create: `frontend/src/composables/useCollab.ts`

**Interfaces:**
- Produces：`useCollab()` 返回 `{ connected, onlineUsers, lastFocus, remoteAnnotationTick, lockDeniedTick, connect(taskId), focus(id), cursor(id,x,y), close() }`。

- [ ] **Step 1: 实现**

```ts
import { ref } from "vue";
import { Auth } from "@/utils/auth";

export interface OnlineUser { id: number; name: string }

export function useCollab() {
  const connected = ref(false);
  const onlineUsers = ref<OnlineUser[]>([]);
  const lastFocus = ref<{ user: OnlineUser; image_id: number } | null>(null);
  const remoteAnnotationTick = ref(0);
  const lockDeniedTick = ref(0);

  let ws: WebSocket | null = null;
  let taskId = 0;
  let closedByUs = false;
  let retry = 0;

  function wsBase(): string {
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const origin = window.location.origin.replace(/^http/, "ws");
    return `${origin}${base}`;
  }

  function connect(id: number) {
    taskId = id;
    closedByUs = false;
    const token = Auth.getAccessToken() || "";
    ws = new WebSocket(`${wsBase()}/annotation/collab/ws/${taskId}?token=${encodeURIComponent(token)}`);
    ws.onopen = () => { connected.value = true; retry = 0; };
    ws.onmessage = (ev) => {
      let msg: any;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "room:presence") onlineUsers.value = msg.users || [];
      else if (msg.type === "user:join") onlineUsers.value = [...onlineUsers.value.filter(u => u.id !== msg.user.id), msg.user];
      else if (msg.type === "user:leave") onlineUsers.value = onlineUsers.value.filter(u => u.id !== msg.user.id);
      else if (msg.type === "image:focus") lastFocus.value = { user: msg.user, image_id: msg.image_id };
      else if (msg.type === "image:lock:denied") lockDeniedTick.value++;
      else if (msg.type?.startsWith("annotate:")) remoteAnnotationTick.value++;
    };
    ws.onclose = () => {
      connected.value = false;
      if (!closedByUs && retry < 5) {
        retry++;
        setTimeout(() => connect(taskId), Math.min(1000 * 2 ** retry, 15000));
      }
    };
    ws.onerror = () => { /* onclose 处理重连 */ };
  }

  function send(payload: any) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
  }

  function focus(imageId: number) { send({ type: "image:focus", image_id: imageId }); }
  function cursor(imageId: number, x: number, y: number) { send({ type: "cursor:move", image_id: imageId, x, y }); }
  function close() { closedByUs = true; ws?.close(); ws = null; connected.value = false; }

  return { connected, onlineUsers, lastFocus, remoteAnnotationTick, lockDeniedTick, connect, focus, cursor, close };
}
```

- [ ] **Step 2: 类型检查** → `pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'useCollab'`（无输出）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/composables/useCollab.ts
git commit -m "feat(annotation): 协作WebSocket前端composable"
```

---

### Task 3: 工作台接入协作

**Files:**
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`
- Test: `frontend/e2e/collaboration.spec.ts`

**Interfaces:**
- Consumes：`useCollab`。

- [ ] **Step 1: 接入**

- 导入：`import { useCollab } from "@/composables/useCollab";`；`import { watch } from "vue";`（若未导入）。
- 实例化：`const collab = useCollab();`
- 底栏新增在线指示（帮助按钮前）：`<span class="collab-online">在线 {{ collab.onlineUsers.value.length }}</span>`
- 首图加载后连接：在 `loadImg` 成功或 `onMounted` 后 `watch` `store.taskId` → `collab.connect(store.taskId)`。
- 切换图片：在 `loadImg` 中 `collab.focus(imageId)`。
- 远端标注：`watch(() => collab.remoteAnnotationTick.value, () => { if (store.currentImage) loadImg(store.currentImage.id); })`
- 锁冲突：`watch(() => collab.lockDeniedTick.value, () => ElMessage.warning("图片已被其他用户锁定"))`
- 卸载：`onBeforeUnmount(() => collab.close())`（若已有 onBeforeUnmount，合并）。

- [ ] **Step 2: 类型检查 + 提交**

```bash
pnpm exec vue-tsc --noEmit 2>&1 | Select-String -Pattern 'annotation/index'
git add frontend/src/views/module_annotation/annotation/index.vue
git commit -m "feat(annotation): 工作台接入实时协作在线/焦点/锁"
```

---

### Task 4: E2E + 回归

**Files:**
- Create: `frontend/e2e/collaboration.spec.ts`
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: E2E（复用 workbench 造数，断言在线指示）**

参考 `annotation-history.spec.ts` 造数进入工作台；断言 `.collab-online` 可见且文本匹配 `在线 1`（或 `>=1`）。连接成功即计数 1。

- [ ] **Step 2: 运行** → `pnpm e2e -- collaboration.spec.ts`（passed）

- [ ] **Step 3: 全量回归** → `cd backend && uv run pytest -q`；`cd frontend && pnpm e2e`（环境波动时逐项复跑）

- [ ] **Step 4: 账本 + 提交**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs(pipeline): Phase 5B 完成记录"
```

---

## Self-Review

- Spec §3 后端 → Task 1 ✅；§4 前端 → Task 2/3 ✅；§6 验收 → Task 1/4 ✅
- 命名一致：`parse_ws_user`/`presence_list`/`useCollab` 前后统一。
- 已知限制（多 worker Redis、CRDT、光标精确渲染）已在 spec §7 记录。
