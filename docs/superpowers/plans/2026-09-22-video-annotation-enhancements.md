# 视频标注增强实施计划（跟踪 / 插值 / 时间区间事件）

> brief: `docs/superpowers/specs/2026-09-22-video-annotation-enhancements-design.md`
> 目标：A. `video_detection` 框加 `track_id` 跨帧轨迹关联；B. 关键帧线性插值；C. 独立 `video_event` 时间轴区间任务 + 事件 JSONL/CSV 导出。

## 关键约定
- 分支 `feat/video-annotation-enhancements`（base = spec `c935bfc`）。
- 后端 `prefix="/annotation"`，`ROOT_PATH="/api/v1"`。`video_event` 用 `video_id` 锚定（`frame_index=None`），与 `video_detection`（用 `frame_index`）靠 `task_type` + 校验器区分。
- 遵循 AGENTS.md：`el-*`/`--el-*`、局部刷新、删除二次确认（`ElMessageBox.confirm` 写明不可逆）、单根组件、`v-hasPerm`、中文注释/提交、编辑器类交互用成熟库。绝不在功能分支跑 `pnpm run lint`。子代理 prompt 用纯中文精简措辞避免敏感词拦截。
- 向后兼容：旧 `video_detection` 数据（无 `track_id`）仍可加载/保存。
- 后端 `uv run pytest tests/...`；前端 `pnpm run test:unit`/`type-check`（不跑 lint）；e2e `npx playwright test`（dev 栈在跑）。

## 任务分解

### Phase A — 目标跟踪（track_id 关联）

#### A1 后端：框支持 track_id（兼容）
- `annotation/schema.py` `AxisAlignedBoxSchema` 加 `track_id: str | None = None`。
- `annotation/service.py` `save_video_annotations`/校验：允许 `track_id` 存在/缺失；同帧同 `track_id` 至多一框（后端校验拒绝重复，不破坏旧数据）。
- 单测：带/不带 track_id 存取、同帧重复 track_id 拒绝。

#### A2 前端：框 track_id 关联 + 轨迹显示
- `useDetectionTool`/检测工具生成框带 `track_id`（可空）。
- 工作台 `video_detection` 模式：选中框→「关联到轨迹」（新建/选已有 track_id）；开启显示轨迹时对当前 `track_id` 各关键帧框画 SVG 连线（跨帧运动路径）；按轨迹导航（跳转到该 track 其它出现帧）。
- 局部刷新；`--el-*`。
- 单测：track 关联/轨迹路径计算逻辑。

#### A3 回归 + 视觉
- 后端 video_detection 回归；前端单测/type-check；e2e `create-video-detection` 回归 + 截图视觉核对（轨迹显示）。

### Phase B — 关键帧线性插值

#### B1 后端：批量插值保存接口
- `POST /anno/video/interpolate`：接收 `{task_id, video_id, track_id, frame_a, frame_b, frames: [{frame_index, annotations}]}`；校验帧范围 `[0,frame_count)`、track_id 一致、框合法（轨道一致）；事务化逐帧 upsert + 版本递增（复用 `save_video_annotations` 的写版本逻辑）。
- 单测：批量保存、帧范围、track 一致、事务回滚。

#### B2 前端：插值工具
- 工作台：选同一 track 的两关键帧（含该 track_id 框）→「插值中间帧」→ 前端线性插值（`t=(k-A)/(B-A)`，四坐标），生成中间帧框（同 track_id），批量提交后端。
- 关键帧框不动；中间帧同 track 覆盖；局部刷新。
- 单测：线性插值计算函数。

#### B3 回归 + 视觉
- 后端/前端回归；e2e 插值 + 截图视觉核对。

### Phase C — `video_event` 时间轴区间任务

#### C1 后端：video_event 模型/枚举/校验/读写/导出
- `AnnotationType.VIDEO_EVENT="video_event"`。
- `annotation/service.py`：`save_video_event_annotations`/`load_video_event_annotations`/`_verify_video_event_task_relation`/`_validate_video_event_annotations`；schema `VideoSegmentSchema`/`VideoEventSaveSchema`；controller `POST /anno/video-event/save`、`GET /anno/video-event/load?task_id=&video_id=`。
- 导出 `_export_video_event`（图片空集守卫前、`annotation_task_id` 透传、None 兜底、JSONL/CSV）。
- 单测：枚举/校验（end>start、越界 [0,duration]、label 归属、重叠顺序无关）/读写/任务归属/导出。

#### C2 前端：videoEventPlugin + VideoTimelineCanvas + VideoEventPanel
- `TaskMedia` 不变；`videoEventPlugin`（`name="video_event"`、`media="video"`、创建校验 VideoSegment）；`VideoTimelineCanvas.vue`（视频秒时间轴 + 区间拖选 + `@create/update/remove/click`）；`VideoEventPanel.vue`（片段列表/类别/删除二次确认）。
- `api/module_annotation/videoEvent.ts`：`saveVideoEventAnnotations/loadVideoEventAnnotations`（显式 task_id）。
- 单测：VideoSegment 工具、panel、API。

#### C3 工作台 video_event 模式
- `AnnotationWorkbench.vue`：`isVideoEventTask = task.task_type==="video_event"`，与 `isVideoTask`（帧检测）区分；时间轴渲染 + VideoEventPanel；拖选→类别弹窗→生成 VideoSegment；重叠拒绝；点击改类型/删除二次确认；保存/锁；单根、局部刷新。`videoEventPlugin` 注册。
- 单测/type-check。

#### C4 e2e + 视觉
- `frontend/e2e/create-video-event.spec.ts`：建任务→时间轴拖选→改类型/删除→保存→刷新持久化→导出；回归（video_detection/text/audio/time_series/smoke/workbench）；截图视觉核对。

## 账本
`.superpowers/sdd/video-enhancements-progress.md`（gitignored），记录每任务提交 SHA/review 结论。

## 完工标准
三个 Phase 全部实现 + 逐任务评审 + 最终整分支评审 Ready to merge；向后兼容（旧 video_detection 无 track_id 仍可加载）、`video_event` 与 `video_detection` 互不干扰；后端/前端单测、type-check、e2e、视觉核对通过。
