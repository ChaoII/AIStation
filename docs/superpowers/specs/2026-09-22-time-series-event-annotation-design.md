# 时间序列事件标注（TimeSeriesEvent）设计

> 为标注系统新增「时间序列」媒体类型与 `time_series_event` 标注任务，支持用户上传**数值序列 CSV**，在**折线图**上做**区间事件**标注（时间戳 `[start, end)`），产物为 `TimeSeriesSegment`（区间 + 事件类别），导出为**区间 JSONL/CSV**（`{start, end, label}`，时间戳单位）。

## 1. 背景与目标

当前标注系统支持图片、视频、文本、音频四类媒体；其中**音频事件标注**（`audio_event`，wavesurfer 时间轴 + 秒级区间拖选）已建立「时间轴区间 + 事件类别 + 区间不重叠 + 导出 JSONL/CSV」的完整交互闭环。平台**无任何时间序列/数值序列媒体能力**：无 series 类型/模型/存储；但已有 **echarts 6 / vue-echarts 8**（标注 stats 页、训练详情页折线图先例），且 `annotation_data` JSONB 可复用承载区间。

**目标**：新增「时间序列」媒体类型与 `time_series_event` 标注任务，让标注者上传**数值序列 CSV**、在 **echarts 折线图**上拖动鼠标选取**时间戳区间**标记为事件/异常（故障/峰值/波动…），每个区间对应一个事件类别；产物 `TimeSeriesSegment {start, end, label_id}`（时间戳），导出为**区间 JSONL/CSV**。

**上下文**：这是「文本 NER → 音频 → 时间序列」三类标注增量的第三项（视频、文本 NER、音频已交付）。

## 2. 范围

| 项 | 内容 |
|----|------|
| 媒体来源 | 用户上传数值序列 CSV（含时间列 + 一个或多个数值列）至标注数据集（存 RustFS），后端探测行数/列数/时间范围 |
| 标注任务 | `time_series_event`（时间序列区间事件标注）；`AnnotationType` 新增 `TIME_SERIES_EVENT` |
| 标注形式 | `TimeSeriesSegment`：时间戳 `[start, end)` 区间 + 事件类别 `label_id`；区间不重叠 |
| 类型配置 | 任务 `classes` 沿用**列表**结构（`[{id, name, color}]`）作为事件类别 |
| 可视化 | echarts 折线图（x 轴时间戳）；`markArea` 渲染区间；鼠标拖选生成区间 |
| 导出 | **区间 JSONL**（每行 `{start, end, label}` 时间戳）+ 可选 CSV |

**非目标（YAGNI）**：
- 不做点标注/单点事件（本版仅区间事件，点标注后续）。
- 不做多层/嵌套区间、不做区间内子事件。
- 不做多列叠加的联动连线（默认渲染主数值列，可切换列显示）。
- 不做时序预测/异常检测算法（仅人工区间标注）。
- 不做流式/实时序列（仅上传静态 CSV）。

## 3. 选型（折线图/区间 = 编辑器类交互，用户强制：成熟第三方库）

时间序列折线图 + 区间拖选属于「编辑器/构造器」类交互，遵循 `AGENTS.md` 采用成熟第三方库、禁止手写。

| 候选 | 许可 | 最近发布 | 评估 |
|------|------|----------|------|
| **echarts 6**（`echarts` + `vue-echarts`，项目已内置） | Apache-2.0 | 活跃 | 成熟折线图；`markArea` 渲染区间高亮；`convertFromPixel` 把鼠标像素换算为 x 轴数据值（时间戳）；`dataZoom` 缩放/平移 ● **首选** |
| wavesurfer.js | BSD-3 | 活跃 | 音频波形，不适合数值折线图/时间戳轴 |
| 手写 canvas 折线 | — | — | 属「手写编辑器类」 → 违反强制约束，禁止 |

**结论**：选 **echarts 6 + vue-echarts**（已有依赖）。`TimeSeriesCanvas.vue` 封装：
- 载入 CSV 数据（解析为 `{time, value}` 数组，x 轴为 time 轴、value 为 y）。
- `markArea` 渲染已标注区间高亮。
- 鼠标在网格上拖选：监听 `mousedown/mousemove/mouseup`，用 `convertFromPixel` 取 x 轴数据值（时间戳）得 `[start, end)`；复用 `graphic` 或临时 markArea 预览。
- `dataZoom` 缩放/平移；鼠标滚轮缩放。
- 点击已标注 markArea → 编辑/删除（删除二次确认）。
- 事件（`create/update/remove/click/time` 等）映射到 `TimeSeriesSegment` 状态。

## 4. 数据模型（后端）

在 `backend/app/api/v1/module_annotation/dataset/model.py` 与 `annotation/model.py`：

- `AnnotationType` 新增：
  ```python
  TIME_SERIES_EVENT = "time_series_event"
  ```

- 新增 `AnnotationTimeSeriesModel`（表 `annotation_time_series`，继承 `ModelMixin, UserMixin`）：
  | 字段 | 类型 | 说明 |
  |------|------|------|
  | `dataset_id` | FK → `annotation_dataset.id` | 所属数据集 |
  | `name` | String(255) | 原文件名 |
  | `object_key` | String(512) | RustFS key |
  | `time_column` | String(64) | 时间列名 |
  | `value_columns` | JSONB | 数值列名列表 |
  | `row_count` | Integer | 数据行数 |
  | `time_unit` | String(8) | 时间单位（`s`/`ms`） |
  | `start_time` / `end_time` | Float | 时间范围（同单位） |
  | `size_bytes` | Integer | 文件字节数 |
  | `status` | Enum(ImageStatus) 复用 | 未标注/进行中/已标注 |
  | `locked_by` / `locked_at` | Integer / DateTime nullable | 序列锁占用者 |
  | `annotation_count` | Integer | 已标事件数 |

  `DatasetModel` 增加 `time_series` 关系（`annotation_time_series`）与 `time_series_count` 字段。

- `AnnotationRecordModel`（表 `annotation_record`）增加：
  | 字段 | 说明 |
  |------|------|
  | `time_series_id` | FK → `annotation_time_series.id`，nullable；与 `image_id`/`video_id`/`document_id`/`audio_id` **五者互斥**，时间序列任务用 |

  索引 `(task_id, time_series_id, version)`（与其余媒体一致）。

  `annotation_data` 继续 `JSONB list[dict]`，`time_series_event` 形状：
  ```python
  {"id": "<uuid>", "type": "TimeSeriesSegment", "start": 1700000000.0, "end": 1700000010.0, "label_id": 1}
  ```
  `start`/`end` 为该序列时间列的**时间戳值**（`time_unit` 决定的单位，Float），`[start, end)`，区间**不重叠**（同一序列任务内）。

## 5. 任务 `classes`

`time_series_event` 沿用现有 `classes` **列表**结构（`[{id, name, color}]`）作为事件类别，无需新字典结构（同 audio_event）。任务创建 UI 复用现有类别编辑。

## 6. 后端接口（对齐音频/文本，前缀 `/annotation`）

- **上传**：`POST /timeseries/upload`（multipart）→ 校验 `.csv/.tsv` 扩展名 + 大小上限（如 200MB / 行数上限如 50 万）；RustFS 上传原始 CSV；**探测**：识别时间列（默认首列或含 `time/timestamp/date` 关键字），数值列（其余数字列），`row_count`、`time_unit`（首条时间值大于 1e12 判为 ms 否则 s）、`start_time`/`end_time`；入库 `AnnotationTimeSeriesModel`；`time_series_count` 递增；失败清理。上传控制器 `db.begin()` + 缓存 `object_key` 补偿删除（同已交付的 document/audio 修复）。
- **列表**：`GET /timeseries/list?dataset_id=`。
- **详情**：`GET /timeseries/detail/{id}`。
- **内容**：`GET /timeseries/content/{id}` → `text/csv` 返回原始 CSV，供前端解析渲染。
- **序列锁**：`POST /timeseries/lock/{id}` / `unlock`。
- **标注读写**（`time_series_id` 锚定）：
  - `POST /annotation/anno/timeseries/save`：`{task_id, time_series_id, annotations: list[dict]}`（显式 `task_id`）。
  - `GET /annotation/anno/timeseries/load?task_id=&t_id=`。
  - 两端点先做任务级校验（`_verify_task_access` + `_verify_time_series_task_relation`），再调 service；`TimeSeriesSegment` 校验：`start/end` float、`end>start`、在 `[start_time, end_time]` 范围、`label_id` 在 `classes`、区间不重叠（顺序无关）。

## 7. 前端工作台

### 插件
- `TaskMedia` 新增 `"time_series"`。
- 新增 `timeSeriesEventPlugin`（`annotation/tasks/timeSeriesEvent/index.ts`）：`name:"time_series_event"`, `media:"time_series"`，自建 `renderer`（`TimeSeriesCanvas`）与 `panel`（区间列表），不走 SVG 几何坐标系。

### 工作台 `time_series` 模式
- `isTimeSeriesTask = plugin.media === "time_series"`。
- 模式：`getTimeSeriesList → getTimeSeriesDetail → getTimeSeriesContent`（CSV 原文），解析为 `{time, value}` 数组（默认主数值列；可切换列/叠加）。
- `TimeSeriesCanvas.vue`：echarts 折线图（x 轴 time，y 轴 value）；`markArea` 高亮区间；`dataZoom` 缩放；鼠标拖选生成区间；`convertFromPixel` 换算时间戳。
- 交互：
  1. 折线图拖选区间 → 弹事件类别选择（`classes`，`--el-*`）→ 生成 `TimeSeriesSegment`。
  2. 点击/选中 markArea → 改类型/删除（删除二次确认）。
  3. 右面板：区间列表（start-end + 类型），新建/编辑/删除（删除二次确认）。
  4. 保存：`saveTimeSeriesAnnotations({task_id, time_series_id, annotations})`；`lockTimeSeries/unlockTimeSeries`。
- 无 SVG 几何坐标系；右栏显示序列元数据（行数/时间范围/数值列），底部控制条。

## 8. 交互与 UI 规范

- 全部沿用 `el-card/el-form/el-dialog/el-tag/el-select` 与 `--el-*` 变量；不自定义主题化外壳、不写死 `font-size`。
- 删除/清空区间必须二次确认（`ElMessageBox.confirm`，写明影响与不可逆）。
- `v-hasPerm` + 后端校验；局部刷新（区间变更只更新对应 markArea/列表项，不整页重渲染）。
- 区间拖选/缩放为 echarts 原生能力，外层 `--el-*` 封装视觉。

## 9. 错误处理

- CSV 解析失败 / 无时间列 / 无数值列 / 超过行数上限 / 非 CSV 扩展名 → 明确错误，不创建无效记录。
- `start/end` 越界（`[start_time, end_time]`）拒绝；`end<=start` 拒绝；区间重叠拒绝。
- 序列锁冲突：提示「该序列被 xx 标注中」。

## 10. 导出（区间 JSONL/CSV）

- `export_service`/`exporter` 新增 `time_series_event` 分支（在 `_export_core` 图片空集守卫之前，同 video/text/audio 分支），用 `annotation_task_id` 读 `load_time_series_annotations`。
- 生成 `<stem>_{time_series_id}.jsonl`：每行 `{"start": <时间戳>, "end": <时间戳>, "label": "<事件名>"}`（label 取 `classes` 中 `label_id` 对应 name）。
- 可选 CSV：`start,end,label` 表头。
- 复用导出框架（下载/训练导出入口），正确透传 `annotation_task_id`。

## 11. 测试

- 后端：`AnnotationTimeSeriesModel`/`TIME_SERIES_EVENT` 枚举迁移、CSV 上传（mock RustFS + 探测时间/数值列/行数/时间范围）、content、序列标注读写（含任务级校验、区间/越界/重叠校验）、区间 JSONL/CSV 导出、`annotation_task_id` 透传回归——单元/接口测试。
- 前端：时间序列工具函数/区间状态、CSV 解析、echarts 区间换算（可测部分）——Vitest 单测。
- e2e：上传 CSV → 创建 `time_series_event` 任务 → 折线图拖选区间生成事件 → 改类型/删除 → 保存 → 刷新持久化 → 导出。

## 12. 约束与选型

- 复用 echarts 6 + vue-echarts（已有依赖）；区间用时间戳 float（`time_unit` 决定单位）。
- `time_series_event` 用现有 `classes` 列表（事件类别）。
- 区间不重叠；`start/end` 在 `[start_time, end_time]`；`label_id` 归属校验。
- 遵循 `AGENTS.md`：局部刷新、`el-*` 组件/变量、删除二次确认、单根组件、中文注释/提交、编辑器/构造器用成熟库。

## 13. 相关文件

- 后端：`app/api/v1/module_annotation/{dataset,annotation,task}/model.py`、`dataset/time_series_service.py`（新增）、`dataset/time_series_controller.py`（新增）、`annotation/service.py`、`annotation/controller.py`、`app/plugin/module_train/exporter.py`（导出分支）、`app/alembic/versions/`。
- 前端：`src/annotation/index.ts`（注册 `timeSeriesEventPlugin`）、`src/annotation/tasks/timeSeriesEvent/`（新增）、`src/annotation/core/types.ts`（`TaskMedia`+`"time_series"`）、`src/annotation/core/AnnotationWorkbench.vue`（时间序列模式）、`src/api/module_annotation/`（时间序列接口）。
- e2e：`frontend/e2e/create-time-series-event.spec.ts`。
