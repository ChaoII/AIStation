# 帧级视频检测标注（VideoFrameDetection）设计

> 为标注系统新增「视频」媒体类型，支持用户上传视频并在**帧级**做 2D 目标检测（矩形框）标注，产物为 `AxisAlignedBox`，按帧复用现有检测导出链路。

## 1. 背景与目标

当前标注系统仅支持**图片**类素材：`AnnotationImageModel` 针对单图（width/height/object_key），前端工作台以「逐图」方式加载与标注。平台上无通用视频标注能力（`module_video` 仅围绕摄像头/录像闭环，且录像仅存本地磁盘，与标注数据集无交集）。

**目标**：新增「视频」媒体类型与 `video_detection` 标注任务，让标注者上传视频、在视频帧上逐帧标注 2D 检测框，松手/点击保存；产物复用现有 `AxisAlignedBox` 数据与检测导出链路。

**后续增量（不在本 spec）**：目标跨帧跟踪/轨迹、关键帧标注+自动插值、时间区间/事件标注。本 spec 仅做**帧级检测标注**这一地基子项目。

## 2. 范围

| 项 | 内容 |
|----|------|
| 媒体来源 | 用户上传视频至标注数据集（存 RustFS 对象存储），不依赖摄像头/录像模块 |
| 标注任务 | `video_detection`（帧级 2D 目标检测）；`AnnotationType` 新增枚举 |
| 帧呈现 | **惰性视频帧视图**：前端 `<video>` 元素 `seek` 到当前帧，标注 canvas 叠加其上；不预抽帧 |
| 形状 | 仅 2D 矩形检测框（`AxisAlignedBox`，归一化 `[0,1]`） |
| 标注锚定 | 每条标注按 `video_id + frame_index` 组织/保存/读取；`frame_index = round(time × fps)` |
| 导出 | **按帧导出**：导出时用 ffmpeg 抽帧 + 该帧标注，复用现有检测导出链（YOLO / xanylabeling），帧号命名 |

**非目标（YAGNI）**：
- 不做跨帧跟踪/轨迹、不做帧间插值、不做时间区间/事件标注（后续子项目）。
- 不做旋转框 / 多边形 / 语义分割等视频形状（本版仅 2D 矩形框）。
- 不引用现有摄像头录像（仅用户上传视频）。
- 不引入新的标注形状类型（沿用 `AxisAlignedBox`），不改视频底层的播放/存储机制。

## 3. 数据模型（后端）

在 `backend/app/api/v1/module_annotation/dataset/model.py` 与 `annotation/model.py`：

- `AnnotationType` 新增：
  ```python
  VIDEO_DETECTION = "video_detection"
  ```

- 新增 `AnnotationVideoModel`（表 `annotation_video`，继承 `ModelMixin, UserMixin`）：
  | 字段 | 类型 | 说明 |
  |------|------|------|
  | `dataset_id` | FK → `annotation_dataset.id` | 所属数据集 |
  | `name` | String(255) | 原文件名 |
  | `object_key` | String(512) | RustFS key |
  | `width` / `height` | Integer | 视频分辨率（ffprobe） |
  | `duration` | Float | 时长（秒） |
  | `fps` | Float | 帧率 |
  | `frame_count` | Integer | 总帧数（`round(duration×fps)`） |
  | `thumbnail_key` | String(512) nullable | 缩略图（可选） |
  | `status` | Enum(ImageStatus) 复用 | 未标注/进行中/已标注 |
  | `locked_by` / `locked_at` | Integer / DateTime nullable | 帧锁占用者（按视频整体锁） |
  | `annotation_count` | Integer | 已标注帧数 |

  `DatasetModel` 增加 `videos` 关系（`annotation_video`）与 `video_count` 字段。

- `AnnotationRecordModel`（表 `annotation_record`）增加：
  | 字段 | 说明 |
  |------|------|
  | `video_id` | FK → `annotation_video.id`，nullable；与 `image_id` 二选一 |
  | `frame_index` | Integer，标注所在帧；视频标注非空 |

  `annotation_data` 继续为 `JSONB list[dict]`（`AxisAlignedBox`，归一化 `[0,1]`，结构同 `detection`）。索引 `(task_id, video_id, frame_index, version)`。

## 4. 后端接口

- **视频上传**：`POST /video/upload`（multipart）→ 复用 RustFS 上传（对齐 `dataset/service.py` 图片上传），ffprobe 探测 `duration/width/height/fps` 并计算 `frame_count`，入库 `annotation_video`。
- **列表**：`GET /video/list?dataset_id=`。
- **详情**：`GET /video/detail/{id}`。
- **播放地址**：`GET /video/play-url/{id}` → RustFS 预签名 URL，供前端 `<video>`。
- **帧锁**：`POST /video/lock/{id}` / 续期 / 解锁（复用图片锁语义，按 video 整体锁）。
- **标注读写**（按 `video_id + frame_index`）：
  - `POST /annotation/video/save`：`{video_id, frame_index, annotations: list[dict]}`
  - `GET /annotation/video/load?v_id=&frame_index=`
  - 复用现有 `annotation_data` 校验（复用检测 `AxisAlignedBox` schema）。

## 5. 前端工作台（复用 + 扩展）

复用 `AnnotationWorkbench`/`AnnotationCanvas` 基础与 `detectionPlugin`（`DetectionCanvas` 渲染 + `useDetectionTool` 画框交互）。

- 工作台按 `store.task.task_type === "video_detection"` 走**视频模式**：
  - 媒体区由 `<img>` 改为 `<video>`（`play-url` 预签名），宽度/高度用 `width/height`（ffprobe）。
  - 当前帧画布叠加检测标注（复用 `detectionPlugin` 的 renderer/tools），`cw=width`、`ch=height`。
- **帧导航状态**：`currentFrame`（int）、`currentTime`（秒）、`duration`、`fps`、`frameCount`。
  - `currentFrame = round(currentTime × fps)`；`frame_index` 与之对齐。
  - 控制条：播放/暂停、上一帧/下一帧（`±1/fps`）、时间轴 seek、帧号显示 `当前帧 / 总帧数`。
- **标注加载/保存**：切帧时 `loadAnnotations(videoId, frameIndex)`；编辑后 `saveAnnotations`（按帧）。帧锁复用（按 video）。
- 帧导航与画布：seek 到目标帧后触发 `onLoadedMetadata`/`seeked` 事件来同步画布 `cw/ch` 与叠层。

## 6. 交互与 UI

- 工作台控制条：播放/暂停、逐帧前进/后退、时间轴（Element Plus 风格，对齐 `module_video/playback` 时间轴）、帧号文本 `x / N`。
- 画框、选中、删除、类别切换、`v-hasPerm` 权限、删除二次确认：完全复用现有检测交互与 `el-*` 组件规范（不新增自定义主题化外壳、不写死 `font-size`）。

## 7. 错误处理

- 视频解码失败 / ffprobe 探查失败 → 明确错误提示，不创建无效记录。
- `seek` 边界：`currentTime` 夹在 `[0, duration]`；`frame_index` 夹在 `[0, frame_count-1]`。
- 帧锁冲突：提示「该视频被 xx 标注中」。
- 多帧并发保存：非障碍，按帧粒度覆盖。

## 8. 导出（按帧复用检测链）

- 导出协程对每个视频：按预设 fps/间隔用 ffmpeg 抽取帧图（存储临时），逐帧取该帧 `annotation_data`，组装为标准检测样本（帧图 + AxisAlignedBox 列表），输出为现有检测导出格式（YOLO / xanylabeling），帧号命名；复用 `module_annotation/dataset/export_service.py` 相关分支，**零新增导出逻辑**。

## 9. 测试

- 后端：`AnnotationVideoModel`/`AnnotationType` 枚举迁移、视频上传（mock RustFS + ffprobe）、play-url、按帧标注读写、帧锁、按帧导出抽样 —— 单元/接口测试。
- 前端：帧号换算（`round(time×fps)`）、帧导航边界逻辑单测（Vitest）。
- e2e：上传视频 → 创建 `video_detection` 任务 → 逐帧画框 → 保存 → 导出。

## 10. 约束与选型

- 复用现有检测插件与 `AxisAlignedBox`，**无新增形状/导出逻辑**。
- 惰性帧视图：不预抽帧，浏览器 `<video>` seek 保证帧精确；省存储、保连续。
- 帧号换算基于 ffprobe `fps`；视频帧率不一致时以 `frame_index = round(time×fps)` 为准（帧级标注足够）。
- 遵循 `AGENTS.md`：局部刷新优先、`el-*` 组件/变量、删除二次确认、单根组件、中文注释/提交。

## 11. 相关文件

- 后端：`app/api/v1/module_annotation/{dataset,annotation,task}/model.py`、`dataset/service.py`、`dataset/export_service.py`、`app/core/base_model.py`（如需要）、`app/scripts/init_app.py`（路由注册）。
- 前端：`src/annotation/index.ts`（注册 `videoDetectionPlugin`）、`src/annotation/tasks/detection/`（复用）、`src/annotation/core/AnnotationWorkbench.vue`（视频模式）、`src/annotation/core/types.ts`（`TaskMedia`/插件能力标记）、`src/api/module_annotation/*`（视频接口）。
- e2e：`frontend/e2e/create-video-detection.spec.ts`。
