# 导入进度体验与可关闭后台状态 设计

> 创建日期：2026-09-18
> 状态：用户已授权「设计后直接实现」
> 范围：`frontend/src/views/module_annotation/dataset/index.vue`、`frontend/src/api/module_annotation.ts`、
> `backend/app/api/v1/module_annotation/dataset/{import_jobs,controller,service,x_anylabeling_importer}.py`

## 目标

导入 x-anylabeling ZIP 时全程无"卡死感"：点击后立即出现进度、上传/解析/导入三段都有可见变化、
弹窗可关闭且后台继续、关闭后在数据集列表仍能看到进度并可 hover 查看详情。

## 背景（实测）

- 749MB `车号数据集.zip`：上传体接收+解析 ~19s（浏览器端无任何反馈 → 卡死感），后台处理 936 张 ~210s。
- 现状进度按批（50 张）更新，约每 10s 跳一次，仍显僵。

## 状态机

| 状态 | 来源 | 触发 |
|---|---|---|
| `ready` 就绪 | 无记录 | 默认 |
| `uploading` 上传中 | **前端**（`onUploadProgress`） | 点击开始导入 |
| `scanning` 初始化中 | 后端 job.phase=`scan` | ZIP 读完、扫描类映射/建任务 |
| `importing` 导入中 | 后端 job.phase=`import` | 分批处理图片 |
| `done` 已完成 | 后端 job.status=`done` | 全部完成 |
| `failed` 失败 | 后端 job.status=`failed` | 异常 |

## 数据契约

### 后端 job 快照（`GET /annotation/dataset/import/{job_id}` 与列表 `item.import`）
```
{ job_id, dataset_id, status, phase, processed, total, imported,
  total_annotations, task_id, task_name, error, file_name, file_size,
  started_at, updated_at }
```
- `ImportJob` 增加 `file_name`/`file_size`/`started_at`/`updated_at`。
- 注册表新增 `dataset_id -> latest job_id` 索引与 `get_latest_job(dataset_id)`；保留最近完成项（上限 200）。
- `DatasetService.enrich_dataset_list` 为每条附加 `import = job_snapshot(latest) | null`。

### 前端请求
- `importXAnyLabeling(datasetId, file, { onUploadProgress, signal })`：透传 axios 选项，`timeout: 0`（大文件不超时，改为可取消），`headers._silent`。

## 前端设计

### A. 导入弹窗（`dataset/index.vue`）
- 三段步骤（`el-steps` 或等价指示）+ 当前段进度条：
  - 上传：`el-progress` 百分比 + `已发送 X / Y MB · Z MB/s`；总长未知时 `:indeterminate`。
  - 解析：`:indeterminate` 条纹 + `服务端解析中…`。
  - 导入：`el-progress` + `已导入 processed / total` + `预计还剩 mm:ss`。
- **秒级计时**：常驻 `已用 mm:ss`，每 1s 刷新（即使百分比不动也有变化）。
- 提交后**下一帧**即渲染进度 UI（不等首字节）。
- 上传中「取消」：`AbortController.abort()` → 状态 `failed/cancelled`，显示"已取消"。
- 关闭语义：
  - `uploading`/`scanning`：确认「关闭将取消本次导入」→ abort + 关闭。
  - `importing`：确认「导入将在后台继续」→ 关闭弹窗，**页面级轮询继续**。
  - `done`/`failed`：直接关闭。
- 重开弹窗：若该数据集存在进行中任务 → 直接进入进度视图（不回文件选择）。

### B. 数据集列表「导入状态」列
- 新增列 `import_status`（在「关联标注任务」列之后、操作列之前），显示标签：
  `已就绪`(info) / `上传中 n%`(primary) / `初始化中`(warning) / `导入中 p/t`(warning) / `已完成`(success) / `失败`(danger)。
- `el-popover`（hover）详情：状态、进度条、`processed/total`、已用时间、任务名、错误；按钮「查看进度」（打开弹窗进度视图）、「去任务」（有 task_id 时）、「重试」（失败时）。
- 状态解析优先级：`activeImports[datasetId]`（前端实时）→ `row.import`（后端快照）→ 就绪。

### C. 页面级轮询
- `activeImports: Record<datasetId, ActiveImport>` 存于页面，弹窗与列表共享。
- 有任一 `uploading|scanning|importing` 时，每 1s 轮询其 `job_id` 更新状态；全部结束则停止。
- `refreshList()` 后，把 `row.import` 中仍进行中的 job 播种到 `activeImports` 并继续轮询（刷新页面后进度继续动）。
- 任务 `done` 时对对应数据集执行一次列表刷新（更新图片数/任务进度徽标）。

## 后端改动

1. `import_jobs.py`：字段补充 + dataset 索引 + `get_latest_job` + `job_snapshot()` + 容量控制。
2. `x_anylabeling_importer.py`：进度回调改为**每完成 1 张图片**调用一次；开始时回调 `(0, total, "scan")`。
3. `controller.py`：`_run_import_job` 更新 `job.started_at/file_name/file_size`、每步 `touch()`；job 状态 `running→done|failed`。
4. `service.enrich_dataset_list`：附加 `item["import"]`。

## 验收标准

- 点击导入后 ≤100ms 出现进度 UI 并开始变化。
- 上传阶段有百分比+字节；解析阶段有条纹+文字；导入阶段数字持续增长。
- **任意 5 秒窗口内至少一个可见元素在变化**（进度/张数/计时器/条纹）。
- 上传中「取消」能真正中止请求。
- 导入中关闭弹窗有确认，关闭后列表该行状态持续更新并可 hover 查看详情。
- 刷新页面后，进行中的导入仍能在列表看到并继续更新。
- 完成后列表刷新，图片数与任务进度正确。

## 测试

- pytest：`enrich_dataset_list` 附带 `import` 快照；`get_latest_job` 取最新；进度回调节奏（每张）。
- vue-tsc：annotation 相关无新错误。
- Playwright（可选）：打开弹窗→选文件→看到上传/导入文字变化。
