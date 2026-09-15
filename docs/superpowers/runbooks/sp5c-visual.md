# SP5-c 快照叠加查看器 — e2e 与视觉核对

- 日期：2026-09-15
- 计划：`docs/superpowers/plans/2026-09-15-sp5c-snapshot-overlay.md` Task 5
- 设计：`docs/superpowers/specs/2026-09-15-sp5c-snapshot-overlay-design.md` §3.4/§4
- 用例：`frontend/e2e/sp5c-snapshot-overlay.spec.ts`

## 1. 执行结果

```
cd frontend && pnpm run e2e -- sp5c-snapshot-overlay
Running 2 tests using 1 worker
  ok 1 [setup] › e2e\auth.setup.ts:5:1 › authenticate (22.5s)
  ok 2 [chromium] › e2e\sp5c-snapshot-overlay.spec.ts › 快照叠加查看器：告警详情与事件流详情渲染检测框 (8.2s)
  2 passed (32.5s)
```

断言内容：

| 页面 | `[data-testid="snapshot-overlay"]` | `data-box-count` | `data-image-loaded` |
|------|-----------------------------------|------------------|---------------------|
| 告警详情抽屉 | 存在 | `2`（= `ai_result.objects` 数量） | **true** |
| 事件流详情抽屉 | 存在 | `2`（= `objects` 数量） | **true** |

两处均断言 Konva `canvas` 已挂载；用例结束清理规则、告警记录与落盘快照（`backend/data/detections/sp5c-e2e-<stamp>.png` 已删除）。

## 2. 快照来源与 `data-image-loaded`

**底图真实加载（`data-image-loaded="true"`）**。种子经内部回调 `/video/algorithm/detection/callback` 携带：

- `snapshot: { ref: "sp5c-e2e-<stamp>.png", data: "<192x108 PNG base64>" }` → 后端 `process_detection_callback` 解码并落盘到 `DETECTIONS_DIR/<ref>`，告警记录写 `snapshot_path`（绝对路径）；
- `snapshot_ref: "/api/v1/video/detections/sp5c-e2e-<stamp>.png"` → 事件表 `snapshot_ref` 存该**受保护相对路径**（与告警 `snapshot_url` 同构）。

查看器取图路径：

- 告警抽屉：`snapshot_url` = `/api/v1/video/detections/<rel>` → `toRequestUrl` 剥离 `/api/v1` → 鉴权 GET `/video/detections/<rel>` → 命中 `SnapshotRouter`，200。
- 事件流抽屉：`snapshot_ref` = 上列受保护路径 → `toRequestUrl` 剥离 `/api/v1` → 同样命中路由器，200。

测试用 PNG 在 spec 内**零依赖运行时生成**（`zlib` + 自写 CRC32/PNG chunk），避免手抄 base64 出错；图案为左蓝/中绿/右紫三色块 + 白网格 + 橙边框，便于视觉核对底图与 letterbox。

## 3. 视觉核对（vision-recognition）

截图：

- `alarm-snapshot-overlay.png`（告警详情抽屉）
- `event-stream-snapshot-overlay.png`（事件流详情抽屉）

视觉模型结论（客观描述）：

- **告警抽屉**：底图存在（三色块 + 白网格 + 橙色外框）；画有 2 个检测框——左侧蓝色框标签 `person 0.9 #7`，右侧红/品红框标签 `car 0.81`；框下方属性小字 `vest=0.88`、`helmet=0.12`、`color=white`；底图**等比缩放、上下留白（letterbox）**清晰可见；工具栏“快照叠加 / 重置”正常。
- **事件流抽屉**：同一底图加载成功；2 个检测框 `person 0.93`（+`#7`）与 `car 0.81`（`#` 徽标在右边缘被裁切），属性小字 `vest=0.88; helmet=0.12`、`color=white` 可见；下方“检测目标 (2)”表格与命中叶子标签照常渲染。该抽屉（620px 宽 / 360px 高）中底图接近铺满，letterbox 留白极窄，视觉模型未标注——属观察差异，非缺陷。

结论：底图 + 框 + 标签/属性/track_id 徽标与两处详情视图风格一致，无与 Element Plus 框架割裂的自定义配色。

## 4. 发现与风险

1. **事件流 `snapshot_ref` 为对象存储 key 时无法加载底图（集成缺口）**：当 `snapshot_ref` 是原始 key（如 `edge/2026-09-15/x.jpg`，真实 Agent 上报形态）时，查看器 `toRequestUrl` 不会补 `/video/detections/` 前缀，请求会打到 `/api/v1/<key>` → 404，`data-image-loaded="false"`。本用例为验证 happy path，显式把 `snapshot_ref` 播成受保护相对路径（与 `snapshot_url` 同构）。若要覆盖真实 Agent 形态，需要后端在事件详情里把本地命中文件归一化为 `/api/v1/video/detections/<rel>`（复用 `inference/snapshot.py::resolve_snapshot_url`）。**本任务未改源码**，仅记录。
2. **大框数降级**：`objects.length > 200` 时只画框与标签（跳过属性小字），e2e 未覆盖该分支。
3. **canvas 渲染无法直接断言像素**：依赖组件暴露的 `data-box-count` / `data-image-loaded` + 截图 vision 核对（spec §5 已列为缓解措施）。
4. e2e 在 `page.reload()` 后依赖清单首行即新告警（后端按 `alarm_time desc` 排序 + 唯一 `alarm_type` 校验行文本），降低了对历史数据量的敏感度。

## 5. 复现命令

```bash
# 后端 8001（默认模式）+ 前端 dev 5180 已启动
cd frontend && pnpm run e2e -- sp5c-snapshot-overlay
```
