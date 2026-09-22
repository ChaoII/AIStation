# 音频事件标注 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给标注系统新增「音频」媒体类型与 `audio_event` 标注任务，支持用户上传音频文件并在**波形 + 时间轴**上做**声音事件/片段**标注（秒级 `[start, end)` 区间），产物 `AudioSegment`（区间 + 事件类别），导出为**事件 JSONL/CSV**。

**Architecture:** 后端新增 `AnnotationAudioModel` + `AnnotationType.AUDIO_EVENT` 枚举，音频文件存 RustFS 并用 ffprobe 探测 `duration/sample_rate/channels/bitrate`；标注记录增加 `audio_id`（四者互斥）+ 复合索引。前端工作台对 `audio_event` 任务用 **wavesurfer.js v7 + regions 插件**渲染波形 + 时间轴，拖选区间生成 `AudioSegment`，右面板管理片段，标注按 `audio_id` 读写；导出为事件 JSONL/CSV。

**Tech Stack:** FastAPI / SQLAlchemy 2.0 / Pydantic v2 / PostgreSQL / Alembic / ffprobe / RustFS(S3) / Vue 3 + Vite + Element Plus + TS / wavesurfer.js / Vitest / Playwright e2e。

## Global Constraints

- **时间轴/波形**：必须用 **wavesurfer.js v7 + regions 插件**（成熟库，用户强制禁止手写编辑器类交互的波形/时间轴）。`AudioTimelineCanvas.vue` 封装：加载 presigned `play_url` 渲染波形，regions 插件提供拖选区间，事件（`region-created/updated/removed`、播放时间）映射到 `AudioSegment` 状态。
- **区间语义**：`AudioSegment {id, type:"AudioSegment", start:float秒, end:float秒, label_id:int}`；`[start,end)`，区间**不重叠**；`start/end` 在 `[0, duration]`；`label_id` 归属 `classes`（列表）。
- **媒体**：`TaskMedia` 加 `"audio"`；`audioEventPlugin`（`media:"audio"`，自建 renderer/panel，不走 SVG 几何坐标系）。
- **标注锚定** `audio_id`（`annotation/audio/save|load`，显式 `task_id`，任务级归属校验）。
- 音频上传白名单（`.wav/.mp3/.m4a/.ogg/.aac/.flac` 等），ffprobe 探测音频流；上传控制器 `db.begin()` + 缓存 `object_key` 补偿删除（同 document 修复）；`DatasetModel.audio_count` 递增。
- 遵循 `AGENTS.md`：局部刷新优先、`el-*` 组件与 `--el-*` 变量、删除/覆盖二次确认、组件单根、中文注释与提交（`feat|fix(annotation): 中文`）。

## File Structure

**后端（`backend/app/api/v1/module_annotation/`）**
- `dataset/model.py` — 新增 `AnnotationAudioModel`、`AnnotationType.AUDIO_EVENT`、`DatasetModel.audios/audio_count`。
- `dataset/audio_service.py`（新建）— 音频上传（RustFS + ffprobe 探测音频流）、列表/详情/play-url、音频锁。
- `dataset/audio_controller.py`（新建）— 音频接口路由（upload/list/detail/play-url/lock/unlock）。
- `annotation/service.py` / `schema.py` / `controller.py` — 音频标注按音频读写 + 区间/重叠/越界校验。
- `dataset/export_service.py` — 新增 `_export_audio_event`（JSNL/CSV，`annotation_task_id`）。
- `app/scripts/init_app.py` / `dataset/__init__.py` — 注册音频路由。
- Alembic 迁移。

**前端（`frontend/src/`）**
- `api/module_annotation/` — 音频 API（`uploadAudio/getAudioList/getAudioDetail/getAudioPlayUrl/lockAudio/unlockAudio/saveAudioAnnotations/loadAudioAnnotations`）。
- `annotation/core/types.ts` — `TaskMedia` 加 `"audio"`。
- `annotation/core/AnnotationWorkbench.vue` — `audio` 模式（加载 play_url，wavesurfer 波形，片段面板，保存 + 锁）。
- `annotation/tasks/audioEvent/index.ts`（新建）— `audioEventPlugin`（`media:"audio"`，renderer/panel）。
- `annotation/tasks/audioEvent/AudioTimelineCanvas.vue`（新建）— wavesurfer 封装（波形 + regions 拖选 + 事件映射）。
- `annotation/tasks/audioEvent/useAudioEventTool.ts`（新建）— 区间 → AudioSegment、重叠检测、映射辅助。
- `annotation/index.ts` — 导出 `audioEventPlugin`。
- `package.json` — +wavesurfer（及 regions 插件依赖）。
- e2e `frontend/e2e/create-audio-event.spec.ts`（新建）+ `e2e/fixtures/sample.wav`（或运行时生成）。

---

### Task 1: 后端数据模型 + 枚举 + 迁移

**Files:** Modify `backend/app/api/v1/module_annotation/dataset/model.py`、`annotation/model.py`；Test `backend/tests/test_audio_event_model.py`（新建）；Alembic revision.

- [ ] **Step 1: 枚举** 在 `AnnotationType` 加 `AUDIO_EVENT = "audio_event"`。
- [ ] **Step 2: `AnnotationAudioModel`**（继承 `ModelMixin, UserMixin`，表 `annotation_audio`）：`dataset_id` FK、`name`、`object_key`、`duration` Float、`sample_rate` Integer、`channels` Integer、`bitrate` Integer nullable、`size_bytes` Integer、`status` Enum(ImageStatus)、`locked_by`/`locked_at`、`annotation_count`。`DatasetModel` 加 `audios` 关系 + `audio_count`。
- [ ] **Step 3: `AnnotationRecordModel.audio_id`** nullable FK，注释「图片/视频/文本/音频四者互斥」；索引 `(task_id, audio_id, version)`。
- [ ] **Step 4: 迁移** `uv run main.py revision --env=dev`；确认建表/加列/加索引/枚举、线性单头、`upgrade/downgrade` 干净、无无关 drop。
- [ ] **Step 5: 单测** `test_audio_event_model.py`：枚举、字段齐全、`audio_id`、索引。`uv run pytest tests/test_audio_event_model.py -q` 通过。

### Task 2: 音频上传 service

**Files:** Create `backend/app/api/v1/module_annotation/dataset/audio_service.py`；Test `backend/tests/test_audio_event_upload.py`（新建）.

- [ ] **Step 1: 白名单 + 大小** 校验扩展名（`.wav/.mp3/.m4a/.ogg/.aac/.flac`）与大小上限（如 100MB）；不符合抛业务异常。
- [ ] **Step 2: ffprobe 探测音频流** 仿 `_probe_video` 但取音频流（`codec_type=="audio"`），提取 `duration/sample_rate/channels/bitrate`；失败明确错误。
- [ ] **Step 3: RustFS + 入库** `object_key = datasets/{id}/audios/{uuid}{ext}`；`s3_client.upload_fileobj`；入库 `AnnotationAudioModel`；`dataset.audio_count += 1`；失败清理（删除已传 object）。
- [ ] **Step 4: 单测** `test_audio_event_upload.py`：mock s3 + ffprobe；白名单拒绝非音频、ffprobe 探测字段正确、计数递增、失败清理。`uv run pytest tests/test_audio_event_upload.py -q` 通过。

### Task 3: 音频接口 controller + 路由

**Files:** Create `backend/app/api/v1/module_annotation/dataset/audio_controller.py`；Modify `dataset/__init__.py`、`module_annotation/__init__.py`；Test `backend/tests/test_audio_event_api.py`（新建）.

- [ ] **Step 1: controller** `POST /audio/upload`、`GET /audio/list?dataset_id=`、`GET /audio/detail/{id}`、`GET /audio/play-url/{id}`（presigned URL）、`POST /audio/lock/{id}`/`unlock`；`db.begin()` + 缓存 `object_key` 补偿删除；guard/session 镜像 video/document。
- [ ] **Step 2: 注册** `dataset/__init__.py` 导出 `AudioRouter`，`module_annotation/__init__.py` 注册。
- [ ] **Step 3: 单测** `test_audio_event_api.py`：upload/list/detail/play-url/lock/unlock，presigned URL 正确，guard 401/403。`uv run pytest tests/test_audio_event_api.py -q` 通过。

### Task 4: 音频标注按音频读写 + 校验

**Files:** Modify `backend/app/api/v1/module_annotation/annotation/{service,schema,controller}.py`；Test `backend/tests/test_audio_event_annotation.py`（新建）.

- [ ] **Step 1: 校验** `audio_event` 的 `annotations` 为 `AudioSegment[]`：`start/end` float、`end>start`、`[0,duration]`、`label_id` 在 `classes`；**区间不重叠**（顺序无关：收集全部区间后两两检测）。
- [ ] **Step 2: save/load** `save_audio_annotations(db, task_id, audio_id, annotations)`（`version` 递增，`annotation_data`）；`load_audio_annotations(db, task_id, audio_id)`；`_verify_audio_task_relation` 镜像 `_verify_document_task_relation`。
- [ ] **Step 3: controller** `POST /annotation/anno/audio/save` `{task_id, audio_id, annotations}` + `GET /annotation/anno/audio/load?task_id=&a_id=`，先 `_verify_task_access`。
- [ ] **Step 4: 单测** `test_audio_event_annotation.py`：save/load、`task_id` 显式、归属校验、start/end/越界/重叠拒绝、`version` 递增。`uv run pytest tests/test_audio_event_annotation.py -q` 通过。

### Task 5: 音频导出（SED JSONL/CSV）

**Files:** Modify `backend/app/api/v1/module_annotation/dataset/export_service.py`；Test `backend/tests/test_audio_event_export.py`（新建）.

- [ ] **Step 1: `_export_audio_event`**（`_export_core` 图片空集守卫之前分支）用 `annotation_task_id` 调 `load_audio_annotations`；生成 `<stem>_{audio_id}.jsonl` 每行 `{"start","end","label"}`（label 取 `classes[label_id].name`）；可选 CSV。
- [ ] **Step 2: 透传** 确保 `annotation_task_id` 传入（非训练 task id），训练/下载路径均可达。
- [ ] **Step 3: 单测** `test_audio_event_export.py`：JSONL 序列正确、CSV、`annotation_task_id` 透传（训练 path id≠标注 id 仍导出）。`uv run pytest tests/test_audio_event_export.py -q` 通过 + `test_video_export`/`test_text_ner_export` 无回归。

### Task 6: 前端 api 层

**Files:** Create `frontend/src/api/module_annotation/audio.ts`；Modify `index.ts`（`export * from "./audio"`）.

- [ ] **Step 1: 接口 + 类型** `uploadAudio(file, datasetId)`/`getAudioList`/`getAudioDetail`/`getAudioPlayUrl`（presigned）/ `lockAudio`/`unlockAudio`/`saveAudioAnnotations({task_id,audio_id,annotations})`/`loadAudioAnnotations({task_id,audio_id})`；TS 类型 `AudioMeta`/`AudioSegment`/`AudioAnnotationsPayload`。`getAudioPlayUrl` 返回 presigned url。type-check 无新增错误。

### Task 7: `TaskMedia` + `audioEventPlugin` + wavesurfer

**Files:** Modify `frontend/src/annotation/core/types.ts`（`TaskMedia` 加 `"audio"`）；Create `frontend/src/annotation/tasks/audioEvent/{index.ts,AudioTimelineCanvas.vue,useAudioEventTool.ts}`；Modify `annotation/index.ts`；`package.json`（+wavesurfer 及 regions 插件）.

- [ ] **Step 1: types.ts 加 `"audio"`**。
- [ ] **Step 2: wavesurfer 依赖** 安装 `wavesurfer.js`（v7）+ 所需 regions 插件包；确认可用。
- [ ] **Step 3: `AudioTimelineCanvas.vue`** 封装 wavesurfer（v7 + regions）：单根；载入 presigned `play_url` 渲染波形；regions 拖选区间；`region-created/updated/removed` 与播放时间事件 emit；props 传外部 `AudioSegment[]` 与事件类别；`--el-*` 外层。
- [ ] **Step 4: `useAudioEventTool.ts`** 区间 + `label_id` → `AudioSegment`；`hasAudioOverlap`；映射/roundtrip 辅助（可单测）。
- [ ] **Step 5: `audioEventPlugin`** `{name:"audio_event", media:"audio", renderer: AudioTimelineCanvas, panel}` + 注册。
- [ ] **Step 6: 单测** `useAudioEventTool.test.ts`（区间/重叠/映射）。`pnpm run test:unit` + type-check 无新增错误。

### Task 8: 工作台 audio 模式交互

**Files:** Modify `frontend/src/annotation/core/AnnotationWorkbench.vue`；Test（如含核心逻辑）.

- [ ] **Step 1: `isAudioTask`** audio 模式加载 `getAudioList→getAudioDetail→getAudioPlayUrl`，渲染 `AudioTimelineCanvas` + 片段面板。
- [ ] **Step 2: 区间交互** 拖选区间 → 弹类别选择（`classes`）→ 生成 `AudioSegment`；点击区间改类型/删除（二次确认）；右面板片段列表（增/删/编辑，删除二次确认）。
- [ ] **Step 3: 保存 + 锁** `saveAudioAnnotations({task_id,audio_id,annotations})` 显式 `task_id`；保存按钮 audio 模式启用（`currentImage||isVideoTask||isTextTask` 扩展 `isAudioTask`）；`lockAudio/unlockAudio`；单根组件；局部刷新。
- [ ] **Step 4: 验证** `pnpm run test:unit` + type-check 无新增错误；无头截图视觉核对（波形渲染、区间高亮、片段面板、播放/时间控制，风格一致）。

### Task 9: e2e

**Files:** Create `frontend/e2e/create-audio-event.spec.ts`；Modify `frontend/e2e/anno-helper.ts`；Fixture（生成或添加 `e2e/fixtures/test-audio.wav`）.

- [ ] **Step 1: helper + fixture** `uploadTestAudio`/`createAudioEventTask`/`gotoAudioWorkbench`/`createAudioSegment`/`selectAudioLabel`；生成一个有效 `wav`（可用 ffmpeg/weejs 或提交小 wav）。
- [ ] **Step 2: e2e** 上传音频 → 创建 `audio_event` 任务 → 拖选区间生成事件 → 改类型/删除 → 保存 → 刷新持久化 → 导出。`npx playwright test create-audio-event.spec.ts` 通过。

### Task 10: 收尾验证

- [ ] 后端 `uv run pytest`（`test_audio_event_*` + `test_video_*` + `test_text_ner_*` + 导出回归）全通过。
- [ ] 前端 `pnpm run test:unit` 通过；`type-check` 无 annotation 新增错误。
- [ ] e2e `create-audio-event` + 既有回归通过。
- [ ] 无头截图视觉核对；清理临时 spec。
- [ ] 记录 ledger `.superpowers/sdd/audio-event-progress.md`。

---

## Testing

- 后端：`test_audio_event_model` / `upload` / `api` / `annotation` / `export`；回归 `test_video_*`、`test_text_ner_*`、`test_export_cuboid`、`test_export_xanylabeling`。
- 前端：Vitest（audioEvent 工具）+ type-check。
- e2e：`create-audio-event.spec.ts` + 既有回归。
