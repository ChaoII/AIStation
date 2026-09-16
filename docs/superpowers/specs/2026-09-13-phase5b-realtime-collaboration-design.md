# Phase 5B：实时协作（P7）设计

> 创建日期：2026-09-13
> 状态：方向由用户授权自主确定（用户指示"不再确认，按推荐完成全部任务"）
> 关联：`2026-09-11-pipeline-optimization-program-design.md`（Phase 5 实时协作）

## 1. 背景

`module_annotation/collaboration/controller.py` 的 WS 端点存在但**无鉴权**（首帧自报 user_id）、前端**从未接入**；锁逻辑还引用 `image_crud`（`auth=None` 静默崩溃，见 `docs/issues.md`）。

## 2. 决策（自主）

| 决策点 | 结论 |
|---|---|
| WS 鉴权 | 连接 query 参数 `?token=`，用 `decode_access_token` 校验；无效关闭 4001 |
| 房间存储 | 保持**进程内内存**（当前单 worker 部署）；多 worker Redis 化记为后续 |
| 锁 | 改用 `AnnotationService.lock_image/unlock_image`（DB 持久、有超时） |
| 实时范围 | presence（在线用户）+ 图片焦点 + 锁协调 + 标注事件转发；收到远端标注事件时**重载当前图**（last-write-wins，不做 CRDT 合并） |
| 光标 | 广播 `cursor:move`（归一化坐标），前端可选展示 |
| 测试 | 后端 pytest（token 解析/房间助手）；前端 E2E（打开工作台出现在线指示） |

## 3. 后端设计

- `collaboration_ws(ws, task_id, token: str | None = Query(None))`：
  - `user = parse_ws_user(token)`；为 None → `close(4001)`。
  - `_rooms[task_id][user_id] = {"ws": ws, "name": name}`。
  - join：向新用户发 `room:presence`（`[{id,name}]`）；向他人广播 `user:join`（含 name）。
  - 事件处理：`annotate:*`（转发）、`image:focus`、`cursor:move`、`image:lock`/`image:unlock`（走 `AnnotationService`，被占则回 `image:lock:denied`）。
  - finally：移除并广播 `user:leave`；释放该用户锁。
- `parse_ws_user(token) -> tuple[int,str] | None`：`decode_access_token` → `json.loads(payload.sub)` → `(user_id, user_name)`。
- `presence_list(task_id) -> list[dict]`：房间内在线的 `{id,name}`。

## 4. 前端设计

- `src/composables/useCollab.ts`：
  - 依据 `Auth.getAccessToken()` 与 `import.meta.env.VITE_APP_BASE_API` 推导 ws URL（http→ws）。
  - 暴露 `connected`、`onlineUsers`、`lastFocus`、`remoteAnnotationTick`，方法 `focus(imageId)`、`cursor(imageId,x,y)`、`lock(imageId)`、`unlock(imageId)`、`close()`。
  - 收到 `annotate:create/update/delete` 递增 `remoteAnnotationTick`（供产物重载）。
  - 收到 `image:lock:denied` 通过回调通知（工作台 toast）。
- 工作台 `annotation/index.vue`：
  - 进入后 `connect(taskId)`；底栏显示「在线 N」。
  - 切换图片时 `focus(imageId)`。
  - `remoteAnnotationTick` 变化且非本端编辑时，重载当前图标注。
  - `lock:denied` 弹 warning。
  - 离开/卸载 `close()`。

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| token 缺失/无效 | 关闭 4001，前端不重连或提示未登录 |
| WS 断开 | 前端指数退避重连（上限），页面卸载停止 |
| 锁被占 | `image:lock:denied` → toast |
| 远端标注事件 | 重载当前图（幂等） |
| 单 worker 之外 | 内存房间不共享 → 记为已知限制 |

## 6. 验收

- 后端 pytest：`parse_ws_user` 有效/无效；`presence_list`。
- 前端 E2E：登录进入工作台，底栏出现「在线 1」且在 WS 连接后更新。
- 手动：两个浏览器打开同一任务，互相看到在线与焦点。

## 7. 非目标 / 已知限制

- 多 worker Redis 化（内存房间限制）。
- CRDT/冲突合并（采用 last-write-wins 重载）。
- 远端光标在画布上的精确渲染（仅广播，前端展示可选）。
