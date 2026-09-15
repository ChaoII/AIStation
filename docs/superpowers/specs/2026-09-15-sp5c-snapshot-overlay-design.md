# SP5-c 告警快照叠加查看器设计

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md` §8（SP5 前端）、`2026-09-15-sp5b-edge-event-design.md`
- 范围：AIStation 前后端（告警补存 v2 objects + 共享叠加查看器组件）

## 1. 背景与现状

| 现状 | 证据 |
|------|------|
| 快照只显示**原图**，无检测框/属性叠加 | `frontend/src/views/module_video/alarm/index.vue`：表格缩略图与详情抽屉均用 `el-image` 直接绑定 `snapshot_url` |
| 告警只存 v2 的 `detections`，**不存 `objects`**（无属性/文本） | `inference/service.py::process_detection_callback` 的 `ai_result = {task_id, algorithm_type, detections, frame_timestamp}` |
| 边缘事件表已有 v2 `objects`（含 attributes/text/track_id） | `edge/model.py::EdgeEventModel.objects` |
| 快照现成可用（受权限保护） | 后端 `alarm/schema.py` 计算属性 `snapshot_url` ← `inference/snapshot.py`；路径 `/api/v1/video/detections/{rel}` |
| 事件流详情抽屉亦无叠加 | `frontend/src/views/module_video/event_stream/index.vue` |

因此"看得见目标框与属性"的能力缺失；且两处详情视图各自为政。

## 2. 目标 / 非目标

**目标**

1. 告警记录补存 v2 `objects`，使叠加有数据源（与事件表对齐）。
2. 提供一个**可复用**的快照叠加查看器：底图 + 归一化 bbox/label/置信度/属性/track_id，支持缩放/平移/重置/下载。
3. 在**告警详情抽屉**与**事件流详情抽屉**共用同一组件。

**非目标**

- 实时画面叠加（轮询最新快照 + 实时检测）。
- 多帧时间轴 / 录像回放联动。
- 框编辑（拖拽/改标签）。
- 导出视频、批量导出。

## 3. 设计

### 3.1 后端：告警补存 v2 objects

`inference/service.py::process_detection_callback` 的 `alarm_data["ai_result"]` 增加 `objects`：

```python
"ai_result": {
    "task_id": task_id,
    "algorithm_type": algorithm_type,
    "detections": detections,          # 兼容保留
    "objects": objects,                # v2（含 attributes/text/track_id）
    "frame_timestamp": frame_timestamp,
},
```

- `objects` 取自归一化事件（`event.get("objects")`）；HTTP 兼容路径若无 `objects`，回退由 `detections` 派生（与 `edge/consumer.py::normalize_edge_event` 同样的字段映射），保证 `objects` 恒为可用列表。
- 不改 `detections` 语义；老记录无 `objects` 时前端回退用 `detections`。

### 3.2 前端：`SnapshotOverlayViewer`

位置：`frontend/src/components/SnapshotOverlayViewer/index.vue`（全局可复用组件）。

**接口**

| prop | 类型 | 说明 |
|------|------|------|
| `src` | `string \| null` | 快照 URL（相对或绝对） |
| `objects` | `Array<{label,confidence,bbox:{x,y,width,height},attributes?,text?,track_id?}>` | 归一化坐标 |
| `labelColors?` | `Record<string,string>` | 可选：label→颜色；缺省按 label 哈希取色 |
| `height?` | `string` | 容器高度（默认 `480px`） |

**渲染（Konva，复用 SP5-a 已有依赖，零新增）**
- `v-stage` + `v-layer`：底图 `v-image` 按 `object-fit: contain` 等效 letterbox 铺满；叠加层与底图共用同一缩放/平移变换。
- 每个对象：`v-rect` 边框（颜色按 label）+ `v-text` 标签 `"{label} {conf:.2f}"`（贴框上沿）+ 属性小字（`attributes` 逐项 `k=v`）+ `track_id` 徽标（`#id`）。
- 文字用 `font-size` 为**画布单位**（非 CSS 像素）以保证缩放一致。

**交互**
- 滚轮缩放（以指针为锚点）、拖拽平移、`重置` 按钮。
- 悬停框高亮（描边加粗 + 半透明填充）。
- `下载`：① 原图；② **含叠加 PNG**（`stage.toDataURL()`）。

**取图（鉴权）**
- 用项目既有 `request`（`fetch` + 拦截器带 `Authorization`）取 `blob` → `URL.createObjectURL` → `new Image()` → `stage` 绘制；卸载时 `revokeObjectURL`。
- 失败（401/404/加载失败）显示占位与错误文案，不抛异常。
- 注意：`<video>`/`<img>` 直连无法带自定义头，故**不得**用 `el-image` 直接消费受保护 URL。

### 3.3 集成点

| 页面 | 改动 |
|------|------|
| `views/module_video/alarm/index.vue` | 详情抽屉内的快照区替换为 `SnapshotOverlayViewer`（数据：`detailDrawer.data.ai_result.objects ?? detections`）；表格缩略图保持 `el-image` 不变（避免列表渲染开销） |
| `views/module_video/event_stream/index.vue` | 详情抽屉内增加 `SnapshotOverlayViewer`（数据：`detail.objects ?? detections`；`snapshot_ref` 为 http(s) 时直接用，否则走受保护 URL） |

两处都不改既有字段与交互。

### 3.4 视觉约束

- 复用 Element Plus 组件与 `--el-*` 变量；组件外壳不引入自定义配色体系。
- 完成后无头浏览器截图 + `vision-recognition` 核对与既有页面一致。

## 4. 测试与验收

**后端**
- `tests/test_alarm_ai_result_objects.py`：`process_detection_callback` 落库的 `ai_result.objects` 非空且含 `attributes`/`track_id`；HTTP 路径无 `objects` 时由 `detections` 派生；老逻辑（`detections`）不变。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**前端**
- `pnpm run type-check`（0 新增）、`pnpm run lint`（本任务文件 0 新增）。
- Playwright e2e：打开告警详情 → 断言叠加层渲染出与 `objects` 数量一致的框（用 `data-testid` 计数或 canvas 尺寸/快照对比）；事件流详情同样断言。
- 无头截图 + `vision-recognition` 核对。

**真机**
- 用现有真实告警（含快照）打开详情，确认底图 + 框 + 属性渲染正确、缩放下叠加与底图同步。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Konva 无法直接断言渲染结果（canvas） | 组件暴露 `data-testid` 与 `data-box-count`；e2e 断言计数属性 + 截图 vision 核对 |
| 受保护快照的鉴权取图 | 统一走 `request` 的 fetch→blob；失败降级为占位与错误提示 |
| 老告警无 `objects` | 前端 `objects ?? detections` 回退 |
| 大图/多框性能 | 只在抽屉打开时渲染；框数 >200 时跳过属性小字（仅画框） |
| 归一化坐标与 letterbox 不一致 | 复用 SP5-a `RoiCanvas` 的 letterbox 换算逻辑（同一套公式） |

## 6. 兼容性

- `ai_result` 仅**新增** `objects` 字段；既有消费者（告警页、通知模板）不受影响。
- 事件流抽屉为新增内容，不改既有列。
- 不新增依赖（复用 `vue-konva`/`konva`）。
- 不新增表/迁移。
