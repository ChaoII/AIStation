# 导入进度体验 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。步骤用 `- [ ]`。

**Goal:** 导入全程有可见进度、弹窗可关闭后台继续、关闭/刷新后数据集列表仍显示导入状态并可 hover 查看详情。

**Architecture:** 后端 job 注册表按 dataset 建索引并把快照附到数据集列表；导入器每张图回调进度。前端页面级 `activeImports` 同时驱动弹窗三段进度与列表「导入状态」列，页面轮询在弹窗关闭后继续。

**Tech Stack:** FastAPI/SQLAlchemy、Vue3+Element Plus、axios、pytest、vue-tsc。

## Global Constraints

- 中文注释/提交（`feat(annotation): ...`）。
- 前端布局用 el-row/el-col；新组件单根。
- 上传请求 `timeout: 0` + 可 `AbortController` 取消；请求 `_silent`。
- 进度回调**每张图片**一次；状态机 `ready/uploading/scanning/importing/done/failed`。
- 提交前：`uv run pytest tests/ -q`、`pnpm run type-check`。

---

### Task B1: job 注册表升级

**Files:** Modify `backend/app/api/v1/module_annotation/dataset/import_jobs.py`

**Interfaces:**
- Produces: `get_latest_job(dataset_id: int) -> ImportJob | None`、`job_snapshot(job: ImportJob | None) -> dict | None`；`ImportJob` 新增 `file_name: str`、`file_size: int`、`started_at: float`、`updated_at: float`、`touch()`

- [ ] `ImportJob` 增加字段与 `touch()`；`create_job(dataset_id, user_id, file_name="", file_size=0)`；`_LATEST: dict[int,str]`；`get_latest_job`；`job_snapshot`（`asdict` + 派生 `elapsed_sec`）；容量控制同时清理 `_LATEST`。
- [ ] 验证：`uv run pytest tests/test_dataset_import_job.py -q` → 全绿
- [ ] Commit：`feat(annotation): 导入任务注册表按数据集索引并支持快照`

### Task B2: 导入器每张图回调进度

**Files:** Modify `backend/app/api/v1/module_annotation/dataset/x_anylabeling_importer.py`

- [ ] 在建立任务前 `if progress_cb: progress_cb(0, total, "scan")`；把回调从「每批一次」移到每张图片入库后 `progress_cb(imported, total, "import")`。
- [ ] 验证：`uv run pytest tests/test_dataset_import_job.py -q`
- [ ] Commit：`feat(annotation): 导入进度按单张图片回调`

### Task B3: 列表附加 import 快照 + job 元数据

**Files:** Modify `backend/app/api/v1/module_annotation/dataset/service.py`、`controller.py`
**Test:** `backend/tests/test_dataset_list_progress.py`

- [ ] 测试：构造 job（`create_job`）后请求 `/dataset/list`，断言该 `item["import"]["job_id"]` 存在。
- [ ] `enrich_dataset_list` 末尾为每条附加 `item["import"] = job_snapshot(get_latest_job(item["id"]))`。
- [ ] `controller._run_import_job`：创建时记 `file_name/file_size`（在导入端点里 `create_job` 时传入）；每步 `job.touch()`；`create_task` 传入文件名/大小。
- [ ] 验证：`uv run pytest tests/test_dataset_list_progress.py tests/test_dataset_import_job.py -q`
- [ ] Commit：`feat(annotation): 数据集列表附带导入任务快照`

### Task F1: 前端 API 支持上传进度与取消

**Files:** Modify `frontend/src/api/module_annotation.ts`

- [ ] `importXAnyLabeling(datasetId, file, opts?: { onUploadProgress?, signal? })`：`timeout: 0`、`headers._silent`、透传 `onUploadProgress`/`signal`。
- [ ] `getImportJob` 保持。
- [ ] 验证：`pnpm run type-check`（annotation 无新错误）
- [ ] Commit：`feat(annotation): 导入请求支持上传进度与取消`

### Task F2: 导入弹窗三段进度 + 计时 + 关闭语义

**Files:** Modify `frontend/src/views/module_annotation/dataset/index.vue`

- [ ] 状态：`activeImports: Record<number, ActiveImport>`、`importAbort`、`importTicker`（1s）。
- [ ] `handleImportSubmit`：立即置 `uploading`；`onUploadProgress` 更新字节/百分比/速率；响应得 `job_id` → `scanning` 并轮询；错误 → `failed`。
- [ ] 轮询：1s 更新 `processed/total/phase/status`；`done` 时 `refreshList()` 一次。
- [ ] 取消：上传中 `abort()` → 状态"已取消"。
- [ ] 关闭：上传/解析中确认后 abort 关闭；导入中确认后关闭但保留轮询；重开仍在导入的数据集直接显示进度视图。
- [ ] 展示：三段步骤 + 当前段进度条（上传/解析用 `:indeterminate`）+ 秒级 `已用 mm:ss` + 速率 + `预计还剩`。
- [ ] Commit：`feat(annotation): 导入弹窗三段进度与可关闭后台继续`

### Task F3: 列表「导入状态」列 + hover 详情 + 页面轮询

**Files:** Modify `frontend/src/views/module_annotation/dataset/index.vue`

- [ ] `contentCols` 增 `import_status`；表格插列（任务列后）。
- [ ] 状态取值：`activeImports[id]` → `row.import` → `ready`；标签映射与颜色按 spec。
- [ ] `el-popover` hover 详情：进度条、`processed/total`、已用、任务名、错误、按钮（查看进度/去任务/重试）。
- [ ] `refreshList` 后把 `row.import` 中 `running/pending` 的 job 播种进 `activeImports` 并轮询；全部结束停轮询。
- [ ] 验证：`pnpm run type-check`；`pnpm exec eslint <改动文件>` 无新增（prettier 既有除外）
- [ ] Commit：`feat(annotation): 数据集列表展示导入状态并支持 hover 查看`

### Task T1: 回归

- [ ] `uv run pytest tests/ -q` 全绿；`uv run ruff check --no-fix app/api/v1/module_annotation` 无新增（FAST002 既有除外）
- [ ] `pnpm run type-check` annotation 无新错误
- [ ] 真实小 zip 导入：列表出现「导入中」→「已完成」，关闭弹窗后仍更新
- [ ] Commit（如有）：`test(annotation): 导入进度体验回归`

## Self-Review
- Spec A→F2、B→F3、C→F3、后端 1→B1、2→B2、3→B3、4→B3。
- 类型一致：`job_snapshot`、`get_latest_job`、`ActiveImport`、`importXAnyLabeling(opts)`。
