# 时间序列事件标注实施计划

> brief: `docs/superpowers/specs/2026-09-22-time-series-event-annotation-design.md`
> 目标：为标注系统新增「时间序列」媒体类型与 `time_series_event` 标注任务，上传数值序列 CSV，在 echarts 折线图上拖选时间戳区间标注事件类别，导出区间 JSONL/CSV。

## 关键约定（各任务统一遵守）
- **分支**：`feat/time-series-event-annotation`（已建，base = spec `05fd657`）；**base(merge-base main)** 在计划执行前确认（应为 `05fd657`）。
- 后端 `prefix="/annotation"`（`AnnotationRouter`），`ROOT_PATH="/api/v1"`。新 controller 文件注册进对应 `__init__.py` 且 register_routers。
- 任务 `classes` 用**列表** `[{id, name, color}]`（事件类别）。
- `annotation_data` JSONB 形状：`{"id": "<uuid>", "type":"TimeSeriesSegment", "start": <float 时间戳>, "end": <float 时间戳>, "label_id": n}`；`[start,end)` 区间，区间不重叠。
- 区间校验：`start/end` float、`end>start`、在 `[start_time, end_time]`、`label_id` 在 classes、区间不重叠（顺序无关）。
- 前端一律**局部刷新**、`el-*`/`--el-*`、删除二次确认、单根组件、中文注释/提交、编辑器类交互用成熟库（echarts 6/vue-echarts 8，项目已有）。
- 绝不在功能分支跑 `pnpm run lint`（lint:prettier 会改写全项目源码）；type-check 前也不跑。
- 若子代理 prompt 含 session/login/AuthPermission/guard/validate/401/403 等英文词会被 `sensitive_words_detected` 拦截 → 用纯中文精简描述。
- 后端环境 `uv` + 测试 `uv run pytest tests/...`；前端 `pnpm run test:unit` / `pnpm run type-check`；e2e `npx playwright test ...`（dev 栈在跑：backend :8001、frontend :5180、PG aistation-pg、Redis aistation-redis）。

## 任务分解

### Task 1 — 后端数据模型、枚举、迁移
- `dataset/model.py`：`AnnotationType` 加 `TIME_SERIES_EVENT = "time_series_event"`；新增 `AnnotationTimeSeriesModel`（表 `annotation_time_series`，`ModelMixin, UserMixin`）：`dataset_id` FK、`name`、`object_key`、`time_column`、`value_columns` JSONB、`row_count`、`time_unit`、`start_time`/`end_time` Float、`size_bytes`、`status`（复用 ImageStatus）、`locked_by`/`locked_at`、`annotation_count`；`DatasetModel` 加 `time_series` 关系 + `time_series_count`。
- `annotation/model.py`：`AnnotationRecordModel` 加 `time_series_id` nullable FK + 五者互斥注释；索引 `(task_id, time_series_id, version)`。
- 生成 alembic 迁移（`uv run main.py revision`），upgrade/downgrade 干净、线性单头。
- 单测：枚举、模型字段、迁移 up/down。

### Task 2 — 时间序列上传 service
- `dataset/time_series_service.py`：`_probe_csv` 解析表头识别时间列（默认首列或含 time/timestamp/date 关键字）与数值列（其余数字列）；统计 `row_count`；推断 `time_unit`（首条时间值 > 1e12 判 ms 否则 s）；`start_time`/`end_time` 范围；校验 `.csv/.tsv` 扩展名、大小上限（200MB）、行数上限（50 万）；无时间列/无数值列报错。
- RustFS 上传原始 CSV；`size_bytes`；`time_series_count` 递增；失败清理。
- 单测：探测各场景、上限、失败清理。

### Task 3 — 时间序列接口 controller + 路由
- `dataset/time_series_controller.py` `TimeSeriesRouter`：upload / list / detail / content（`text/csv`）/ lock / unlock。
- upload 用 `db.begin()` + begin 块内捕获 `object_key` 补偿删除（同 document/audio）。
- 注册进 `dataset/__init__.py` 与模块 `__init__.py`。
- 单测：各端点 + 鉴权（用纯中文措辞描述测试）。

### Task 4 — 时间序列标注 service/schema/controller
- `annotation/{service,schema,controller}.py`：`save_time_series_annotations`/`load_time_series_annotations`/`_verify_time_series_task_relation`（校验任务 task_type=="time_series_event" 且同数据集）。
- `/annotation/anno/timeseries/save|load`；`TimeSeriesSegment` 校验（float、end>start、[start_time,end_time]、label_id 在 classes、区间不重叠顺序无关）。
- 版本化存取（同音频：新版本 + prune 旧版本）。
- 单测：读/写/校验/任务级归属/越界/重叠。

### Task 5 — 导出区间 JSONL/CSV
- `app/plugin/module_train/exporter.py` `_export_time_series`：置于 `_export_core` 图片空集守卫之前；用 `annotation_task_id` 读 `load_time_series_annotations`；按 `TimeSeriesSegment` 过滤，产出 `<stem>_{time_series_id}.jsonl`（每行 `{start,end,label}`）；`csv=True` 产出 `start,end,label` CSV；`annotation_task_id=None` 兜底（warning+return）。
- 复用导出框架透传 `annotation_task_id`；回归：训练/评估/下载三入口。
- 单测：JSONL/CSV、annotation_task_id 透传、None 兜底。

### Task 6 — 前端 api 层
- `api/module_annotation/timeSeries.ts`：`uploadTimeSeries/getTimeSeriesList/getTimeSeriesDetail/getTimeSeriesContent(get api().get(url,{responseType:"text"}))/lockTimeSeries/unlockTimeSeries/saveTimeSeriesAnnotations/loadTimeSeriesAnnotations`；TS 类型 `TimeSeriesMeta/TimeSeriesSegment/TimeSeriesAnnotationsPayload`；`index.ts` 导出。
- `__tests__/timeSeries.test.ts`。
- 单测：8。

### Task 7 — TaskMedia + timeSeriesEventPlugin + TimeSeriesCanvas
- `annotation/core/types.ts`：`TaskMedia` 加 `"time_series"`。
- `annotation/tasks/timeSeriesEvent/`：`index.ts`（`timeSeriesEventPlugin`，`media:"time_series"`，renderer=TimeSeriesCanvas，create 校验 `TimeSeriesSegment`）；`useTimeSeriesEventTool.ts`（`createTimeSeriesSegment`/`hasTimeSeriesOverlap`/`hasOverlapExcluding`/`clampTimeRange`）；`TimeSeriesCanvas.vue`（echarts 折线图 + `markArea` 区间高亮 + 鼠标拖选 `convertFromPixel` 换算时间戳 + `dataZoom` 缩放 + `@create/update/remove/click` 事件 + 单根 cleanup）。
- `annotation/index.ts` 注册。
- package.json：echarts 6 / vue-echarts 8 已有，无需新增。
- 单测：useTimeSeriesEventTool。

### Task 8 — 工作台 time_series 模式交互
- `AnnotationWorkbench.vue`：`isTimeSeriesTask`、`initTimeSeries`（getTimeSeriesList→getTimeSeriesDetail→getTimeSeriesContent 解析 CSV 为 `{time,value}`）、`TimeSeriesPanel.vue` 事件面板、拖选→类别弹窗→`createTimeSeriesSegment`、`hasTimeSeriesOverlap` 拒绝、点击区间改类型/删除二次确认、`saveTimeSeriesAnnotations` 显式 task_id、保存按钮 isTimeSeriesTask 启用、`lockTimeSeries/unlockTimeSeries`、单根、局部刷新、`--el-*`、`v-hasPerm` 与既有面板一致。
- 修复既有同名 TDZ 类缺陷（若有）。
- 单测：40。

### Task 9 — e2e
- `e2e/create-time-series-event.spec.ts` + `anno-helper.ts` 时间序列辅助 + `e2e/fixtures/test-series.csv`。
- 流程：上传 CSV → 创建 `time_series_event` 任务 → 折线图拖选区间生成事件 → 改类型/删除 → 保存 → 刷新持久化 → 导出。
- e2e + 回归各若干通过。

### Task 10 — 收尾验证
- 后端：time_series_event 全量测试 + 回归；前端单测 + type-check（无新增 annotation 错误）；e2e + 回归；视觉核对（echarts 折线渲染、markArea 高亮联动、面板、保存/缩放/拖选、风格一致）。
- 无新代码改动。

## 账本
每任务完成后追加 `.superpowers/sdd/time-series-event-progress.md`（gitignored），记录提交 SHA、review 结论、严重度。

## 完工标准
所有测试通过（后端、前端单测、e2e、回归）、视觉核对通过、逐任务评审通过、最终整分支评审确认 Ready to merge、`annotation_task_id`/区间校验/classes 列表/向后兼容正确。
