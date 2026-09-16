# Phase 3D：云边可视化前端 设计（边缘设备管理 + 布控设备选择 + 告警快照）

> 创建日期：2026-09-12
> 状态：设计已确认（用户批准）
> 关联：
> - `2026-09-11-pipeline-optimization-program-design.md`（Phase 3 前端部分按本文细化）
> - `2026-09-12-cloud-edge-visual-analysis-design.md`（§10B.5 前端交付项）
> - `2026-09-12-phase3c-edge-agent-integration.md`（已落地的后端能力）

## 1. 背景与目标

Phase 3C 已完成 AIStation 侧云边协同后端：`module_video/edge`（设备管理/心跳/能力校验）、布控任务编排（`edge_device_id` + TaskConfig 编译 + Agent 下发）、MQTT/HTTP 事件接入。但前端仍是空白或有断层：

- **没有边缘设备管理页**：后端 `/video/edge/*` CRUD、`module_video:edge:*` 权限与按钮菜单均已就绪，但前端无 API 文件、无页面、无菜单。
- **布控任务页（`deploy/index.vue`）**：表单没有 `edge_device_id` 选择器，也没有 `detect_region`（ROI）编辑器；任务启用/失败原因 `error_log` 无展示入口。
- **告警快照不可访问**：本地快照存的是**绝对 OS 路径**（如 `D:\AIStation\backend\data\detections\...`），且 `DETECTIONS_DIR` **没有 HTTP 路由**；列表无缩略图，详情仅用裸 `el-image` 直接绑 `snapshot_path`，实际显示空白。边缘事件的 `snapshot.ref` 为相对引用/对象存储 key，也无统一访问方式。

**目标**：把 3C 的后端能力接到前端并补齐快照可访问性，使"设备 → 布控 → 告警快照"在 UI 上完整可见。

**范围（三项全做）**：
1. 边缘设备管理页：CRUD + 详情（能力/指标）+ 定时轮询状态。
2. 布控任务页增强：设备选择与状态/能力反馈、启停失败原因、ROI 多边形编辑器。
3. 告警快照：受鉴权 HTTP 路由 + 读写归一化 + 列表缩略图/详情预览。

**非目标**：
- 模型 → ModelDeploy 可加载格式（ONNX/engine）导出与分发（spec §10B.4，另开）。
- MQTT/边缘缓存等 Agent 侧实现（ModelDeploy 仓库，另会话）。
- 视频布控时段 UI 之外的其它 Phase 5 半成品。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|---|---|
| Phase 3D 范围 | 三项全做（设备页 + 布控设备选择/ROI + 快照路由/预览） |
| 快照访问策略 | 受控路由 + **读取时归一化**（不改 DB、不做数据迁移） |
| 快照路由鉴权 | **鉴权路由** + 前端 `SnapshotImage` 用已鉴权 axios 拉 blob 生成 objectURL |
| 设备页交互 | CRUD + 详情抽屉 + **15s 定时轮询**在线状态 |
| 布控页改动 | 设备选择 + 状态/能力反馈 + ROI 多边形编辑器 |
| ROI 编辑器底图 | **实时预览（LivePlayer）+ SVG 叠加**画多边形，不新增截图接口 |
| 前端组织 | 抽复用组件（`EdgeDeviceSelect` / `EdgeCapabilityPanel` / `SnapshotImage` / `RoiEditor`） |
| 测试范围 | 后端 pytest + 前端 Playwright E2E + type-check/lint + **真机 Agent 端到端（可用时）** |

## 3. 架构总览

```
┌────────────────────────── 前端 (Vue3 + Element Plus) ──────────────────────────┐
│ module_video/edge/index.vue   ← 设备 CRUD + 详情抽屉 + 15s 轮询                  │
│ module_video/deploy/index.vue ← +EdgeDeviceSelect +EdgeCapabilityPanel +RoiEditor│
│ module_video/alarm/index.vue  ← +缩略图列 +SnapshotImage 详情预览                 │
│ components/Edge/EdgeDeviceSelect.vue / EdgeCapabilityPanel.vue                  │
│ components/Video/RoiEditor.vue                                                  │
│ components/Common/SnapshotImage.vue                                            │
│ api/module_video/edge.ts                                                       │
└───────────────┬────────────────────────────────────────────────────────────────┘
                │  REST /api/v1/video/*
┌───────────────▼────────────────────────────── 后端 (FastAPI) ──────────────────┐
│ edge/controller.py        （3C 已就绪：/video/edge/*）                          │
│ algorithm/controller.py   （3C 已就绪：/video/algorithm/task/* + callback）     │
│ inference/controller.py   （新增：GET /video/detections/{path} 受鉴权静态服务） │
│ inference/snapshot.py     （新增：resolve_snapshot_url 读取时归一化）           │
│ alarm/schema.py           （改：AlarmRecordOutSchema + snapshot_url 计算字段）  │
│ inference/service.py      （改：规则匹配健壮化 + 快照相对路径归一化）           │
└────────────────────────────────────────────────────────────────────────────────┘
```

## 4. 后端设计

### 4.1 受控快照路由

- 新文件 `backend/app/api/v1/module_video/inference/controller.py`，定义 `SnapshotRouter = APIRouter(prefix="/detections", route_class=OperationLogRoute)`。
- 端点：`GET /api/v1/video/detections/{file_path:path}`（`video_router` 前缀 `/video`）。
- 鉴权：`Depends(AuthPermission(["module_video:alarm:query"]))`，与告警查看权限一致。
- 行为：
  - `base = Path(settings.DETECTIONS_DIR).resolve()`，`target = (base / file_path).resolve()`；
  - 若 `target != base` 且 `base not in target.parents` → 404（防目录穿越）；
  - `target.is_file()` 为真 → `FileResponse(str(target))`（按扩展名给 `image/jpeg` 等），否则 404。
  - `include_in_schema=False` 可选；错误响应沿用项目 `ErrorResponse`/404 语义。
- 注册：在 `module_video/__init__.py::_register_video_routers()` 中 `include_router(SnapshotRouter)`。

### 4.2 读取时归一化 `resolve_snapshot_url`

新文件 `backend/app/api/v1/module_video/inference/snapshot.py`（纯函数 + 惰性依赖）：

```python
def resolve_snapshot_url(value: str | None) -> str | None:
    """把 DB 中存储的快照引用归一化为前端可访问 URL。
    规则：
      1. 空 → None
      2. http(s):// → 原样返回
      3. s3://key / oss://key → 去 scheme 后 presigned_url
      4. 本地文件存在（绝对路径或相对 DETECTIONS_DIR）→ /api/v1/video/detections/{相对路径}
      5. 否则视为对象存储 key，尽力 presigned_url；失败 → None
    """
```

- 相对路径以 `settings.DETECTIONS_DIR` 为基准；绝对路径若不在 `DETECTIONS_DIR` 之下则**不**经本地路由暴露（返回 None 或按 key 处理）。
- `s3://`/`oss://` 前缀用于显式对象存储引用；无前缀的相对引用先尝试本地文件是否存在，避免误判。
- 为避免列表序列化时逐行 IO，plan 中可加**短 TTL 进程内缓存**（`(path, mtime)` → 结果），并保证测试可关闭。

### 4.3 告警 Schema

`AlarmRecordOutSchema`（`alarm/schema.py`）：
- 保留 `snapshot_path`（原始存储值，向后兼容）；
- 新增 `snapshot_url: str | None = None`，通过 Pydantic v2 `@computed_field` 计算，内部**惰性 import** `resolve_snapshot_url` 避免循环依赖；
- `video_clip_path` 同法新增 `video_clip_url`（可选，plan 视成本决定）。

### 4.4 规则匹配健壮化（相邻小修复）

`inference/service.py::process_detection_callback` 中按 camera+alarm_type 查规则由 `scalar_one_or_none()` 改为：

```python
rules = (await session.execute(stmt)).scalars().all()
rule = pick_alarm_rule(rules, algorithm_type or "AI_DETECTION")
```

`pick_alarm_rule(rules, algorithm_type)`：优先 `alarm_type` 精确匹配，否则取第一条，空返回 None。消除多规则 `MultipleResultsFound` 导致的回调 500。

## 5. 前端设计

### 5.1 API 与菜单/路由

- `frontend/src/api/module_video/edge.ts`：
  `getEdgeDeviceList(params)`、`getEdgeDeviceDetail(id)`、`createEdgeDevice(data)`、`updateEdgeDevice(id, data)`、`deleteEdgeDevice(ids)`，对齐后端 `/video/edge/*`。
- 菜单：`backend/app/scripts/init_app.py` 新增 `_ensure_edge_page_menu()`（仿 `_ensure_deploy_menu()`）：
  - route_name `VideoEdge`，path `/video/edge`，component `module_video/edge/index`，permission `module_video:edge:query`，挂在"视频监控"下并分配 admin（role 1）。
  - 按钮权限 `module_video:edge:*` 已由 `_ensure_edge_button_menus()` 种入，不重复。

### 5.2 边缘设备管理页 `module_video/edge/index.vue`

- 结构：`PageSearch` + `PageContent` + `EnhancedDialog`（遵循项目 CRUD 范式，用 `useCrudList()`）。
- 表单字段：`name`、`code`、`control_url`、`secret`（密码输入）、`description`。
- 列表列：名称、编码、状态（online/offline/busy/error 标签色）、在跑路数（取自 `metrics`）、最后心跳、控制地址、操作。
- 详情抽屉：`EdgeCapabilityPanel` 渲染 `capabilities`（platform/gpu_model/vram_mb、backends、model_families、max_channels、codecs）与 `metrics`（CPU/GPU/显存/在跑路数）。
- 轮询：默认 15s 调 `getEdgeDeviceList` 刷新状态；`onUnmounted` 清理；页面隐藏（`document.hidden`）或详情抽屉内编辑时暂停；轮询失败静默（`_silent`），不弹 toast。
- `secret` 出参脱敏（后端 `EdgeDeviceOutSchema` 不含 secret），表单编辑时留空表示不变更。

### 5.3 复用组件

| 组件 | 路径 | 职责 |
|---|---|---|
| `EdgeDeviceSelect` | `components/Edge/EdgeDeviceSelect.vue` | 设备下拉；含"本机/纯云端"（value=null）选项；显示状态点与在跑路数/最大路数；支持 `disabled`、清空 |
| `EdgeCapabilityPanel` | `components/Edge/EdgeCapabilityPanel.vue` | 把 `capabilities`/`metrics` JSON 渲染为人类可读分组与标签；缺失字段显示"—" |
| `RoiEditor` | `components/Video/RoiEditor.vue` | 内嵌 `LivePlayer` + SVG 叠加；按视频 `videoWidth/videoHeight` 计算 contain 显示矩形；点击加点、双击/按钮闭合、清空/撤销；`v-model` 输出归一化 `points: [[x,y],...]` |
| `SnapshotImage` | `components/Common/SnapshotImage.vue` | 统一快照展示：`http(s)`/`blob` 直接用；否则用已鉴权 axios `responseType:'blob'` 拉取→`URL.createObjectURL`；`onUnmounted`/`src` 变化时 `revokeObjectURL`；加载骨架、失败占位；`previewable` 时支持 `el-image` 预览 |

### 5.4 布控任务页 `module_video/deploy/index.vue`

- 表单新增 `edge_device_id`：`EdgeDeviceSelect`，默认 null（本机/纯云端）；提交 payload 带 `edge_device_id`。
- 选中设备后展示 `EdgeCapabilityPanel`（只读）与状态；设备 offline 或（前端可判定的）能力不符时给出提示（不硬阻止，最终以后端编排为准）。
- 任务卡片/详情展示 `error_log`（若 `AlgorithmTaskOutSchema` 暴露；plan 中确认并必要时补字段）。
- 表单新增 ROI：`RoiEditor`，绑定 `detect_region.points`（归一化），提交写入 `detect_region`。

### 5.5 告警页 `module_video/alarm/index.vue`

- 列表新增缩略图列（`SnapshotImage`，尺寸约 48px，`previewable=false`）。
- 详情抽屉：用 `SnapshotImage`（`src = snapshot_url || snapshot_path`，`previewable`）替换裸 `el-image`。
- `video_clip_url` 若实现则同样接入。

## 6. 数据流

```
本机 worker / 边缘 Agent
   └─ 事件 (detections + snapshot)
        └─ InferenceService.process_detection_callback
             ├─ 本机 base64 → 存 DETECTIONS_DIR，snapshot_path=绝对路径
             └─ 边缘 ref   → snapshot_path=相对引用 / 对象存储 key
                  └─ AlarmRecord 落库
                       └─ GET /video/alarm/record/list
                            └─ AlarmRecordOutSchema.snapshot_url = resolve_snapshot_url(snapshot_path)
                                 ├─ 本地 → /api/v1/video/detections/{rel}（鉴权）
                                 └─ key  → presigned_url
                       └─ 前端 SnapshotImage：鉴权拉 blob / 直接签名 URL → objectURL
```

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| 快照路径越界 / 文件不存在 | 路由返回 404；`snapshot_url` 可为 None，前端占位 |
| 对象存储签名失败 | `snapshot_url=None`，日志 warning，不阻断告警列表 |
| 未登录 / 无权限访问快照 | 路由 401/403 |
| 设备离线 | 设备页状态标签 offline；布控页选择处提示 |
| 能力不满足 / 下发失败 | 后端写 `error_log`；布控页展示；`start_task` 返回错误信息 |
| 轮询请求失败 | 静默（`_silent`），保留上次数据 |
| ROI 未闭合 / 点数 < 3 | 不写入 `detect_region`，表单校验提示 |

## 8. 测试与验收

**后端 pytest**
- 快照路由：无 token → 401/403；合法文件 200 且 `Content-Type` 正确；目录穿越（`..`、绝对路径越界）→ 404；不存在 → 404。
- `resolve_snapshot_url`：空 / http / s3 / 本地绝对 / 本地相对 / 不存在 key（签名失败）各分支。
- `pick_alarm_rule`：精确匹配优先、回退第一条、空列表 None。
- 多规则场景不再抛 `MultipleResultsFound`（回调集成测试）。

**前端**
- `pnpm type-check` 0 错误；`pnpm lint` 无新增错误。
- Playwright E2E：
  - 边缘设备页：列表渲染、创建、详情抽屉、删除。
  - 布控页：选择设备（含本机）、ROI 画点并保存后回显。
  - 告警页：缩略图列出现且 `snapshot_url` 请求成功（可用路由拦截）。

**真机端到端（可用时）**
- 注册边缘设备（心跳）→ 能力可见 → 下发布控 → 事件经 MQTT 回流 → 告警快照展示。
- 若 ModelDeploy Agent 不可用（属另一仓库会话），记录为阻塞项并给出已完成的替代验证证据。

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 对象存储 key 与本地相对路径结构相似，归一化误判 | 显式 `s3://` 前缀优先；无前缀先查本地文件是否存在；加短 TTL 缓存与分支测试 |
| ROI 画布与视频 contain 坐标换算不准 | 用 `videoWidth/Height` 计算显示矩形；专门用例（含黑边/非等比） |
| 逐行 blob 拉取影响列表性能 | 缩略图列分页量小；`SnapshotImage` 做 lazy（`IntersectionObserver` 可选）与 objectURL 回收 |
| 真机 e2e 依赖外部 Agent | 作为最终验收步骤，不可用则明确记录阻塞，不虚构结果 |
| 快照路由公开化安全风险 | 采用鉴权路由，不用公开 `/static` 式挂载 |

## 10. 交付拆分（供 writing-plans 参考）

1. 后端：快照路由 + `resolve_snapshot_url` + schema `snapshot_url` + 规则匹配健壮化 + pytest。
2. 前端基础：`edge.ts`、菜单/路由、`EdgeDeviceSelect`、`EdgeCapabilityPanel`。
3. 边缘设备管理页（含轮询、详情抽屉）+ E2E。
4. 布控页：设备选择/状态/`error_log` + `RoiEditor` + 保存回显。
5. 告警页：`SnapshotImage` + 缩略图列 + 详情预览。
6. 回归：pytest + `pnpm type-check`/`lint`/`e2e`；真机 Agent 端到端（可用时）。
