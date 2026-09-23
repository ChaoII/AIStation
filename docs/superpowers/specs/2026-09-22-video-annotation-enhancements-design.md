# 视频标注增强（目标跟踪 / 关键帧插值 / 时间区间事件）设计

> 为视频标注系统新增三项能力：**A. 目标跟踪**（`video_detection` 框关联 `track_id` 形成跨帧轨迹）、**B. 关键帧线性插值**（同一 track 的两个关键帧之间自动生成中间帧框）、**C. 独立 `video_event` 时间轴区间标注**（视频时间段打事件类别，导出事件 JSONL/CSV）。

用户已确认：跟踪扩展 `video_detection` 加 `track_id` 关联（不新增类型）；插值用**关键帧线性插值**；时间区间为**独立 `video_event` 任务类型**。

## 背景

`video_detection`（已合并）是**每帧独立目标检测**：`AnnotationRecordModel` 每行 = 某帧最新版本（`task_id, video_id, frame_index, version` 组合索引），`annotation_data` 为 `AxisAlignedBox[]`（`{id, type:"AxisAlignedBox", class_id, x1,y1,x2,y2}` 归一化 `[0,1]`）。帧定位基于 `video.currentTime = frame_index/fps` 时间换算。**无 `track_id`、无跨帧关联、无插值/轨迹概念；视频标注当前未导出。**

## 范围

| 项 | 内容 |
|----|------|
| A. 目标跟踪 | 给 `video_detection` 每帧框增加可选 `track_id`；同一 `track_id` 跨帧的框构成一条轨迹；工作台支持将框关联到 track（新建/指定已有）、跨帧轨迹连线显示、按轨迹跳转/查看。**不新增任务类型**（仍 `video_detection`）。 |
| B. 关键帧线性插值 | 在**同一 `track_id`** 的两个关键帧（frame A、frame B 各画了该 track 的框）之间，按帧序对归一化框坐标 `x1/y1/x2/y2` **线性插值**，为中间帧生成同 `track_id` 的框并写入各中间帧 `annotation_data`，逐帧保存。 |
| C. `video_event` 时间轴区间 | 新增独立任务类型 `video_event`：在视频**时间轴**（`0..duration` 秒）上拖选时间段 `[start,end)`，打事件类别 `label_id`；区间不重叠、越界 `[0,duration]`；导出**事件 JSONL/CSV**（`{start,end,label}`，秒级）。 |

**非目标（YAGNI）**：
- 不装目标检测/跟踪算法自动生成轨迹（仅**人工**关联/插值）。
- 不做跨视频轨迹、不做轨迹合并/拆分算法、不做轨迹平滑插值（先线性）。
- `video_event` 不做子区间嵌套、不做点事件（仅区间）。
- 不改变 `video_detection` 现有检测框语义（无 `track_id` 的框仍合法，视为独立目标）。

## A. 目标跟踪（track_id 关联）

### 数据模型（向后兼容）
- `annotation_data` 框增加可选 `track_id`（`string | null`）。`AxisAlignedBoxSchema`（`annotation/schema.py`）新增 `track_id: str | None = None`。
- `save_video_annotations` / `_validate` 允许 `track_id` 存在或缺失；无 `track_id` 的框行为与现状一致。
- 跨帧同 `track_id` 的框即一条轨迹（无独立 track 表，靠 `track_id` 字段关联）。
- 导出（若后续为 video 增加导出）可带 `track_id`；本版允许。

### 前端交互
- 帧框增加 `track_id` 字段；`useDetectionTool` 生成框可带 `track_id`。
- 工作台 `video_detection` 模式增强：
  1. 选中某帧一个框 →「关联到轨迹」：弹菜单新建 track 或选择已有 `track_id`，给该框赋 `track_id`。
  2. **轨迹显示**：开启「显示轨迹」时，对当前 `track_id` 的各关键帧框绘制连线（SVG polyline 或高亮），展示跨帧运动路径。
  3. **按轨迹导航**：选中 track 后，可跳转到该 track 的其它出现帧（用 `track_id` 搜各帧 annotation_data）。
  4. 删除框时同帧同 track 的其余框不受影响（track_id 仅归属元数据）。
- 局部刷新：track 关联/轨迹显示只更新相关框/轨迹层，不整表刷新。

### 语义
- `track_id` 由前端生成（`crypto.randomUUID()`）或复用，持久化进 `annotation_data`；跨帧一致性靠用户在同一 track 下给各帧框赋同一 id。
- 校验：同任务内同一 `track_id` 可在多帧出现（轨迹）；单帧内不可有重复 `track_id`（一帧一框一目标）——前端把关 + 后端校验（若后端校验则拒绝同帧重复 track_id；可放宽为仅警告，spec 定为「同一帧内同一 track_id 至多一框」）。

## B. 关键帧线性插值

### 触发与算法
- 工作台 `video_detection` 模式提供「插值」工具：选中一条轨迹（同一 `track_id`），在其**已标注的两个关键帧**（frame_index = A、B，A<B，且两帧均含该 track_id 的框）之间，用户点「插值中间帧」。
- 对中间帧 `k ∈ (A, B)`，对四个归一化坐标线性插值：
  ```
  t = (k - A) / (B - A)
  x1_k = x1_A + (x1_B - x1_A) * t   （y1/y2/x2 同理）
  ```
  生成 `{id: newId, type:"AxisAlignedBox", class_id: <取A或B的class_id>, track_id: <同一track_id>, x1,y1,x2,y2: 插值}`。
- 插值结果写入各中间帧的 `annotation_data`（与该帧既存框合并；若该帧已含同 track_id 框则**覆盖**）。随后**逐帧保存**（复用 `saveVideoAnnotations`，或新增批量接口，见下）。
- 关键帧框保持不动（不被覆盖）；仅生成中间帧。

### 保存策略
- 逐帧 `saveVideoAnnotations(taskId, videoId, frameIndex, annotations)`（已有接口）逐帧提交；或新增后端批量接口 `POST /anno/video/interpolate` 接收 `{task_id, video_id, track_id, frame_a, frame_b, annotations: list[{frame_index, annotations}]}` 一次性写入中间帧（事务化、版本递增）。**选批量接口**（减少请求、保证一致），前端把插值计算好的各帧框提交。
- 后端批量接口：对每个 `frame_index` 校验 `[0, frame_count)`、t 范围、`track_id` 一致、框合法，逐帧 upsert。

## C. `video_event` 时间轴区间标注

### 后端
- `AnnotationType` 新增 `VIDEO_EVENT = "video_event"`。
- 复用 `AnnotationRecordModel`，**video_event 任务锚定 `video_id`（`frame_index = None`）**：`annotation_data` 为 `VideoSegment[]`（`{id, type:"VideoSegment", start, end, label_id}`，秒级）。与 `video_detection`（用 `frame_index`）由校验器按 `task_type` 区分。
- 新增 `save_video_event_annotations(task_id, video_id, segments)` / `load_video_event_annotations(task_id, video_id)` / `_verify_video_event_task_relation`（task_type=="video_event" + 同数据集）/ `_validate_video_event_annotations`（`type=="VideoSegment"`、`start/end` float、`end>start`、`[0, duration]`、`label_id` 在 classes、区间不重叠顺序无关）。
- 接口：`POST /anno/video-event/save`、`GET /anno/video-event/load?task_id=&video_id=`。
- 导出：`_export_video_event` 置于 `_export_core` 图片空集守卫之前，用 `annotation_task_id` 读 `load_video_event_annotations`，产出 `<stem>_{video_id}.jsonl`（每行 `{start,end,label}`）+ 可选 CSV（`framework=="video-event-csv"`）。`annotation_task_id=None` 兜底。

### 前端
- `TaskMedia` 不变（仍 `"video"`）；新增 `videoEventPlugin`（`name="video_event"`、`media="video"`、`renderer=VideoTimelineCanvas`、`create` 校验 `VideoSegment`）。workbench 按 `task.task_type===VideoTimestampBlock` 选插件（`plugins.find(p=>p.name===task.task_type)` 已按任务类型匹配）。
- **workbench 区分**：`video_detection`（`task_type==="video_detection"`）走帧画布（`AnnotationCanvas` + `VideoPlayerBar`）；`video_event`（`task_type==="video_event"`）走时间轴画布（`VideoTimelineCanvas`）。用 `isVideoEventTask = task.task_type==="video_event"` 分支，避免与现有 `isVideoTask`（帧检测）冲突。
- `VideoTimelineCanvas.vue`：视频时长 `0..duration` 纯时间轴（不渲染波形），`region` 拖选区间（复用 audio 事件映射：`@create/update/remove/click`），`VideoEventPanel` 片段列表（类别、删除二次确认）。参考 `audioEventPlugin`+`AudioTimelineCanvas`，但 x 轴为视频秒（`value` 轴）无播放/波形。
- `VideoSegment` 语义 `[start,end)` 秒级、区间不重叠、`[0,duration]`；`EventPanel` 与音频面板一致（`el-*`、`--el-*`、局部刷新、删除二次确认）。
- 保存：`saveVideoEventAnnotations({task_id, video_id, segments})` 显式 `task_id`。

## 导出

- `video_event` → 事件 JSONL/CSV（`{start,end,label}` 秒级）。
- `video_detection` 跟踪：本版不强制导出（沿用现状未导出）；若后续导出，可带 `track_id`。**不在本版**。

## 交互与 UI 规范

- 沿用 `el-*`/`--el-*`、局部刷新、删除二次确认、单根组件、`v-hasPerm`、成熟库（插值/轨迹用前端计算；时间轴用 `value` 轴，视频时间轴可复用 echarts 或逐帧 seek——`VideoTimelineCanvas` 用 div/滑动条实现纯时间轴，参考 `VideoPlayerBar`）。
- 严格遵循 `AGENTS.md` 的编辑器类交互用成熟库要求；插值为纯数值计算，轨迹连线为 SVG，均属平台已有能力。

## 测试

- 后端：`track_id` 字段兼容（save/load 带与不带）、`video_event` 枚举/校验/读写/任务归属/越界/重叠、批量插值接口（帧范围/track 一致/事务化/版本递增）、`_export_video_event`（JSONL/CSV/annotation_task_id/None 兜底）。
- 前端：`useDetectionTool`/`useTrackTool`（track 关联）、插值计算函数（线性插值）、`videoEventPlugin`/`VideoTimelineCanvas`/`VideoEventPanel`（区间）、`getVideoEventContent` 类 API 单测；type-check 无新增 annotation 错误。
- e2e：`video_event`（建任务→时间轴拖选区间→改类型/删除→保存→刷新持久化→导出）与现有 `video_detection`（含 track 关联/插值）回归。

## 约束

- 扩展 `video_detection` 的框字段（`track_id`）需**向后兼容**（旧数据无该字段仍可加载/保存）。
- `video_event` 与 `video_detection` 共用 `video` 媒体，靠 `task_type` 与校验器区分，**互不干扰**。
- 遵循 `AGENTS.md`（局部刷新、`el-*`、删除二次确认、单根、中文注释/提交、成熟库）。
