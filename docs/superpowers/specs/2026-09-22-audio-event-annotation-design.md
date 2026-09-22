# 音频事件标注（AudioEvent / SED）设计

> 为标注系统新增「音频」媒体类型与 `audio_event` 标注任务，支持用户上传音频文件并在**时间轴**上做**声音事件/片段**标注（秒级 `[start, end)` 区间），产物为 `AudioSegment`（区间 + 事件类别），导出为**事件 JSONL/CSV**（`{start, end, label}`）。

## 1. 背景与目标

当前标注系统支持图片（`AnnotationImageModel`）、视频（`AnnotationVideoModel`）、文本（`AnnotationDocumentModel`）三类媒体，工作台分别以「逐图 / 逐帧 / 文本 CodeMirror」方式加载与标注。平台**无任何音频能力**：无音频类型/模型、无波形/转录/音频流处理，前端无 `<audio>` 播放器与波形库（`package.json` 无 wavesurfer/howler）。

**目标**：新增「音频」媒体类型与 `audio_event` 标注任务，让标注者上传音频文件、在**波形 + 时间轴**上拖动鼠标选取**秒级区间**标记为声音事件（说话/音乐/噪音/鸟鸣…），每个区间对应一个事件类别；产物 `AudioSegment {start, end, label_id}`，导出为**事件 JSONL/CSV**。

**上下文**：这是「文本 NER → 音频 → 时间序列」三类标注增量中第二项（视频、文本 NER 已交付）；时间序列标注不在本 spec。

## 2. 范围

| 项 | 内容 |
|----|------|
| 媒体来源 | 用户上传音频文件至标注数据集（存 RustFS 对象存储），后端 ffprobe 探测元数据 |
| 标注任务 | `audio_event`（声音事件检测 SED）；`AnnotationType` 新增 `AUDIO_EVENT` |
| 标注形式 | `AudioSegment`：秒级 `[start, end)` 区间 + 事件类别 `label_id`；区间不重叠 |
| 类型配置 | 任务 `classes` 沿用现有**列表**结构（`[{id, name, color}]`）作为事件类别 |
| 时间轴交互 | 波形 + 时间轴；鼠标拖选区间生成片段；播放/暂停 + 标记起止；右面板片段列表 |
| 导出 | **事件 JSONL**（每行 `{start, end, label}` 秒级），可选 CSV |

**非目标（YAGNI）**：
- 不做语音转写/ASR、不做说话人分离/重叠说话（仅区间事件标注）。
- 不做音频分类（整段打标）、不做音频转录+NER（后续可能的子项目）。
- 不做事件层级/嵌套、不做区间内子事件。
- 不做从视频提取音轨（仅上传音频文件）。
- 时间序列标注在后续子项目。

## 3. 选型（时间轴/波形 = 编辑器类交互，用户强制：成熟第三方库）

波形 + 区间拖选属于「编辑器/构造器」类交互，遵循 `AGENTS.md` 强制要求采用成熟第三方库、禁止手写（含用 `el-card`+`el-table` 自拼）。

| 候选 | 许可 | 最近发布 | 评估 |
|------|------|----------|------|
| **wavesurfer.js**（v7，含 `@wavesurfer/*` 插件） | BSD-3 | 活跃 | 浏览器原生音频渲染波形；`**regions**` 插件支持鼠标拖选区间（增删/移动/调整端点）；零依赖、体积小、Vue 3 可封装；事实标准 ● **首选** |
| howler.js | MIT | 活跃 | 仅音频播放，无波形/区间 → 不满足 |
| 自绘 canvas 波形 | — | — | 属「手写编辑器类」 → 违反强制约束，禁止 |

**结论**：选 **wavesurfer.js（v7 + regions 插件）**。实现时以 `@wavesurfer/*` 相关包（或单包）在 Vue 组件中封装：加载 presigned `play_url` 渲染波形，`regions` 插件提供拖选区间；`AudioTimelineCanvas.vue` 对外 emit 区间增删/移动事件与播放时间。

**交互实现**（wavesurfer regions）：
- 载入音频 `play_url`（browser `<audio>` via presigned URL + Range，同视频模式）。
- 波形渲染；`regions` 插件开启拖选：鼠标在时间轴拖动生成新区间 → 弹事件类别选择（`classes` 列表）。
- 区间上可移动/调整起点终点 / 删除（删除二次确认）；右面板片段列表 + 类型切换/删除。
- 播放/暂停 + 当前时间/总时长显示；`RegionsPlugin` 事件（`region-created`/`region-updated`/`region-removed`）映射到 `AudioSegment` 状态。

## 4. 数据模型（后端）

在 `backend/app/api/v1/module_annotation/dataset/model.py` 与 `annotation/model.py`：

- `AnnotationType` 新增：
  ```python
  AUDIO_EVENT = "audio_event"
  ```

- 新增 `AnnotationAudioModel`（表 `annotation_audio`，继承 `ModelMixin, UserMixin`）：
  | 字段 | 类型 | 说明 |
  |------|------|------|
  | `dataset_id` | FK → `annotation_dataset.id` | 所属数据集 |
  | `name` | String(255) | 原文件名 |
  | `object_key` | String(512) | RustFS key |
  | `duration` | Float | 时长（秒，ffprobe） |
  | `sample_rate` | Integer | 采样率（Hz） |
  | `channels` | Integer | 声道数 |
  | `bitrate` | Integer nullable | 码率（kbps，可选） |
  | `size_bytes` | Integer | 文件字节数 |
  | `status` | Enum(ImageStatus) 复用 | 未标注/进行中/已标注 |
  | `locked_by` / `locked_at` | Integer / DateTime nullable | 音频锁占用者 |
  | `annotation_count` | Integer | 已标事件数 |

  `DatasetModel` 增加 `audios` 关系（`annotation_audio`）与 `audio_count` 字段。

- `AnnotationRecordModel`（表 `annotation_record`）增加：
  | 字段 | 说明 |
  |------|------|
  | `audio_id` | FK → `annotation_audio.id`，nullable；与 `image_id`/`video_id`/`document_id` 四者互斥，音频任务用 |

  索引 `(task_id, audio_id, version)`（与 image/video/document 索引惯例一致）。

  `annotation_data` 继续 `JSONB list[dict]`，`audio_event` 形状：
  ```python
  {"id": "<uuid>", "type": "AudioSegment", "start": 1.25, "end": 3.5, "label_id": 1}
  ```
  `start`/`end` 为**秒（float）**，`[start, end)`，区间**不重叠**（同一音频任务内）。

## 5. 任务 `classes`

`audio_event` 沿用现有 `classes` **列表**结构（`[{id, name, color}]`）作为事件类别，无需新字典结构（区别于 text_ner）。任务创建 UI 复用现有类别编辑（名称+颜色）。

## 6. 后端接口（对齐视频/文本，前缀 `/annotation`）

- **音频上传**：`POST /audio/upload`（multipart）→ 校验音频扩展名白名单（`.wav/.mp3/.m4a/.ogg/.aac/.flac` 等），RustFS 上传，ffprobe 探测 `duration/sample_rate/channels`（可含 bitrate），入库 `annotation_audio`，`audio_count` 递增；失败清理。上传控制器用 `db.begin()` 包裹并缓存 `object_key` 补偿删除（同已交付的 document 上传修复）。
- **列表**：`GET /audio/list?dataset_id=`。
- **详情**：`GET /audio/detail/{id}`。
- **播放地址**：`GET /audio/play-url/{id}` → presigned URL，供前端 `<audio>`/wavesurfer。
- **音频锁**：`POST /audio/lock/{id}` / `unlock`（复用图片/视频/文本锁语义）。
- **标注读写**（`audio_id` 锚定）：
  - `POST /annotation/anno/audio/save`：`{task_id, audio_id, annotations: list[dict]}`（显式 `task_id`）。
  - `GET /annotation/anno/audio/load?task_id=&a_id=`。
  - 两端点先做任务级校验（`_verify_task_access` + `_verify_audio_task_relation`，仿文本/视频），再调 service；`AudioSegment` 校验：`start/end` float、`end>start`、`[0,duration]` 范围内、`label_id` 在 `classes`、区间不重叠。

## 7. 前端工作台

### 插件
- `TaskMedia` 新增 `"audio"`。
- 新增 `audioEventPlugin`（`annotation/tasks/audioEvent/index.ts`）：`name:"audio_event"`, `media:"audio"`，自建 `renderer`（`AudioTimelineCanvas`）与 `panel`（片段列表），不走 SVG 几何坐标系。

### 工作台 `audio` 模式
- `isAudioTask = plugin.media === "audio"`。
- 音频模式：`getAudioList → getAudioDetail → getAudioPlayUrl`，wavesurfer 加载 `play_url` 渲染波形。
- `AudioTimelineCanvas.vue`：封装 wavesurfer（v7 + regions）；波形 + 时间轴；`region-created/updated/removed` 事件映射到 `AudioSegment`；播放/暂停、时间显示。
- 交互：
  1. 时间轴拖选区间 → 弹事件类别选择（`classes`，`--el-*`）→ 生成 `AudioSegment`。
  2. 点击/选中区间 → 可改类型/删除（删除二次确认）。
  3. 右面板：事件片段列表（start-end + 类型），新建/编辑/删除，删除二次确认。
  4. 保存：`saveAudioAnnotations({task_id, audio_id, annotations})`；`lockAudio/unlockAudio`。
- 无帧导航/光栅坐标系；右栏显示音频时长/采样率，底部控制条显示播放/时间。

## 8. 交互与 UI 规范

- 全部沿用 `el-card/el-form/el-dialog/el-tag/el-select` 与 `--el-*` 变量；不自定义主题化外壳、不写死 `font-size`。
- 删除/清空片段必须二次确认（`ElMessageBox.confirm`，写明影响与不可逆）。
- `v-hasPerm` + 后端校验；局部刷新（片段变更只更新对应 region/列表项，不整页重渲染）。
- 区间拖选/播放为 wavesurfer 原生能力，外层用 `--el-*` 封装视觉。

## 9. 错误处理

- 音频解码失败 / ffprobe 探测失败 / 非音频扩展名 / 超过大小上限（如 100MB，可按 plan）→ 明确错误，不创建无效记录。
- `start/end` 越界（`[0, duration]`）拒绝；`end<=start` 拒绝；区间重叠拒绝。
- 音频锁冲突：提示「该音频被 xx 标注中」。

## 10. 导出（事件 JSONL/CSV）

- `export_service` 新增 `audio_event` 分支 `_export_audio_event`（在 `_export_core` 图片空集守卫之前，同 video/text 分支），用 `annotation_task_id` 读 `load_audio_annotations`。
- 生成 `<stem>_{audio_id}.jsonl`：每行 `{"start": <float秒>, "end": <float秒>, "label": "<事件名>"}`（label 取 `classes` 中 `label_id` 对应 name）。
- 可选 CSV：`start,end,label` 表头。
- 复用导出框架（下载导出 / 训练导出入口），正确透传 `annotation_task_id`。

## 11. 测试

- 后端：`AnnotationAudioModel`/`AUDIO_EVENT` 枚举迁移、音频上传（mock RustFS + ffprobe）、play-url、音频标注读写（含任务级校验、区间/重叠/越界校验）、SED JSONL/CSV 导出、`annotation_task_id` 透传回归——单元/接口测试。
- 前端：音频工具函数/区间状态、wavesurfer region → AudioSegment 映射逻辑（可测部分）——Vitest 单测。
- e2e：上传音频 → 创建 `audio_event` 任务 → 拖选区间生成事件 → 改类型/删除 → 保存 → 刷新持久化 → 导出。

## 12. 约束与选型

- 复用 wavesurfer.js（v7 + regions 插件）；区间用秒级 float。
- `audio_event` 用现有 `classes` 列表（事件类别），不改字典结构。
- 区间不重叠；`start/end` 在 `[0, duration]`；`label_id` 归属校验。
- 遵循 `AGENTS.md`：局部刷新、`el-*` 组件/变量、删除二次确认、单根组件、中文注释/提交、编辑器/构造器用成熟库。

## 13. 相关文件

- 后端：`app/api/v1/module_annotation/{dataset,annotation,task}/model.py`、`dataset/audio_service.py`（新增）、`dataset/audio_controller.py`（新增）、`annotation/service.py`、`annotation/controller.py`、`dataset/export_service.py`、`app/alembic/versions/`。
- 前端：`src/annotation/index.ts`（注册 `audioEventPlugin`）、`src/annotation/tasks/audioEvent/`（新增）、`src/annotation/core/types.ts`（`TaskMedia`+`"audio"`）、`src/annotation/core/AnnotationWorkbench.vue`（audio 模式）、`src/api/module_annotation/`（音频接口）、`package.json`（+ wavesurfer）。
- e2e：`frontend/e2e/create-audio-event.spec.ts`。
