# 数据集列表性能与导入体验 优化设计

> 创建日期：2026-09-18
> 状态：已确认（用户授权直接开始）
> 范围：`backend/app/api/v1/module_annotation/dataset/`、`frontend/src/views/module_annotation/dataset/`

## 背景（实测证据）

- `/annotation/dataset/list?page_size=100` 实测 **5.9s**（157 个数据集）；`page_size=1` 仅 0.15s。
  根因：`dataset/controller.py` 的列表逻辑对每个数据集开新会话、对每个 task 跑
  `TaskService._calc_progress`（多次查询，含 `jsonb_array_length`）**并在读路径调用
  `update_progress` 写库** → N+1 + 读时写。
- 导入弹窗为填充「目标数据集」下拉，调用 `getDatasetList(page_size=100)`（约 6s），
  且无服务端搜索，>100 个数据集时无法检索。
- `x-anylabeling` 导入全同步：在 `async def` 内做阻塞 zip 解压 + 936 次串行 boto3 上传 +
  936 次 flush 的**单个大事务**，全程阻塞事件循环；前端导入超时 120s。
  实测数据集 `D:\项目资料\21代县\车号数据集.zip`：**750MB、936 张 1920×1080 JPG + 936 JSON**，
  远超超时 → 导入失败且期间后端整体卡顿。
- 导入器不生成缩略图，导入的图片在网格/工作台无缩略图。
- 数据集操作列 **9 个按钮分 3 行**（图片/上传/导出 · 导出历史/数据清洗/编辑 · 去训练/删除/彻底删除）。
- 导入弹窗无文件名回显、无大小/进度提示，标题大小写不一致，下半留白过大。

数据内容核实：该 zip 全部为矩形框、`label` 固定 `"text"`（1019 个框），`flags` 空，
`description` 为 `01..08` 循环的短编号；`classes.txt` 为 `text`。属**纯检测**数据集。

## 关键决策（已确认）

| 决策点 | 结论 |
|---|---|
| 导入执行模型 | **后台任务 + 进度轮询**（上传后立即返回 job_id，避免超时/阻塞） |
| 操作列收纳 | **主操作（图片/上传/编辑）+「更多」下拉**，严格一行 |
| 导入入口 | **移入数据集行「更多 → 导入标注」**，数据集隐式确定，删除全局入口与慢下拉 |
| 列表进度计算 | **单条聚合查询批量算，只读不写**（保留进度徽标） |
| 删除按钮 | 「删除」「彻底删除」均收进「更多」危险分组 |
| `description` | 保持忽略（短编号，非车牌文本） |
| 导入流式化 | 不 `extractall` 到临时目录，直接按 zip 成员读取 |
| 导入缩略图 | 导入时生成缩略图（复用 `media.process_image`） |

## 组件设计

### A. 后端：数据集列表性能（`dataset/controller.py`）

移除逐条 `async with async_db_session()` 循环与 `_calc_progress`/`update_progress` 调用。
新增批量聚合（`DatasetService.get_dataset_task_progress(db, dataset_ids)` 或直接在 controller）：

1. 每个数据集的图片总数：`SELECT dataset_id, count(*) FROM annotation_image
   WHERE is_deleted=false AND dataset_id IN (...) GROUP BY dataset_id`。
2. 每个任务的已标注图片数：先取 `(task_id, image_id)` 的 `MAX(version)`，再 join 回
   `annotation_record` 过滤 `annotation_data` 非空，按 `task_id` 计数：
   - `max_v = SELECT task_id, image_id, MAX(version) AS mv FROM annotation_record
     WHERE task_id IN (...) GROUP BY task_id, image_id`
   - 再 `JOIN annotation_record r ON r.task_id=max_v.task_id AND r.image_id=max_v.image_id
     AND r.version=max_v.mv WHERE r.annotation_data IS NOT NULL AND <json_len> > 0`
   - `GROUP BY r.task_id` 计数。
   - 方言兼容：`jsonb_array_length`（PG）/ `json_array_length`（SQLite），沿用现有判断。
3. 进度 = `annotated / total * 100`，状态由进度推导（与现有 `_calc_progress` 语义一致）。

- 任务列表与 `task_count` 保留，但用一次 `SELECT ... WHERE dataset_id IN (...)` 取本页所有任务。
- 读路径不再写库。

### B. 后端：导入后台任务与进度

新增 `dataset/import_jobs.py`（进程内注册表，`uvicorn` 单 worker 安全）：

```python
@dataclass
class ImportJob:
    job_id: str
    dataset_id: int
    user_id: int
    status: str = "pending"      # pending|running|done|failed
    phase: str = ""              # scan|import|finalize
    processed: int = 0
    total: int = 0
    imported: int = 0
    total_annotations: int = 0
    task_id: int | None = None
    error: str | None = None

JOBS: dict[str, ImportJob] = {}
```

- `create_job(dataset_id, user_id) -> ImportJob`；`get_job(job_id)`；`_jobs_lock`。
- 路由改造：
  - `POST /annotation/dataset/{id}/import/x-anylabeling`（multipart file）：
    校验扩展名 `.zip`、文件大小 ≤ `ANNOTATION_IMPORT_MAX_MB`；创建 job；
    `asyncio.create_task(_run_import_job(job, file))`；立即返回 `{job_id}`。
    注意：必须先 `await file.read()` 把上传体读到内存/BytesIO 再交给后台任务
    （请求结束后 `UploadFile` 的生命周期不可依赖）。若文件超过内存阈值，
    改为先落临时文件并把路径交给后台任务。
  - `GET /annotation/dataset/import/{job_id}`：返回 job 快照。
- 后台任务入口 `_run_import_job(job, data: bytes)`：调用重写后的
  `import_x_anylabeling_bytes(data, dataset_id, user_id, progress_cb)`；
  `progress_cb(processed, total, phase)` 更新 job；异常写 `job.status="failed", job.error`。
- 权限沿用 `annotation:dataset:create`。

### C. 后端：导入器重写（`x_anylabeling_importer.py`）

新增 `import_x_anylabeling_bytes(data: bytes, dataset_id, user_id, progress_cb=None) -> dict`：
1. `zipfile.ZipFile(io.BytesIO(data))`，构建 `(reldir, stem) → ZipInfo` 映射：
   - 图片扩展名沿用现有白名单；JSON 同名配对。
   - 显示 filename 消歧逻辑沿用现有实现。
2. 扫描所有 JSON 建立类映射与形状统计（顺序读取，字节量小）。
3. 推断任务类型（沿用 `_infer_task_type`）并创建 `AnnotationTaskModel`（`COMPLETED`, progress 100）。
4. 分批（`ANNOTATION_IMPORT_BATCH_SIZE`，默认 50）循环：
   - 顺序从 zip 读出本批图片与 sidecar 字节（zipfile 非线程安全）。
   - `asyncio.gather` + 信号量（`ANNOTATION_IMPORT_CONCURRENCY`，默认 8）在线程池内：
     `process_image`（尺寸 + 缩略图）→ 上传原图（带 ContentType）→ 上传缩略图。
   - 单批一个 DB 事务：写 `AnnotationImageModel`（含 `thumbnail_key`、`status=ANNOTATED`）
     与 `AnnotationRecordModel`（`version=1`）。
   - 更新进度并 `progress_cb`。
5. 收尾：重算 `dataset.image_count` / `annotated_count`，`update_progress(task_id)`。
6. 返回 `{imported, total_images, total_annotations, class_mapping, task_id, task_name}`。

- 保留 `import_x_anylabeling_zip` 作为薄封装（解压场景/测试）或直接移除；测试改用 bytes 版本。
- 入参为 bytes 时无需 zip-slip 校验（不写盘）。
- 保留既有 `_shape_to_annotation` / `_classification_names` / `_class_color` 等纯函数。
- 导入图片生成缩略图（复用 `dataset/media.py`）。

### D. 配置（`setting.py` + `.env.dev.example`）

- `ANNOTATION_IMPORT_MAX_MB: int = 1024`
- `ANNOTATION_IMPORT_CONCURRENCY: int = 8`
- `ANNOTATION_IMPORT_BATCH_SIZE: int = 50`

### E. 前端：数据集页（`views/module_annotation/dataset/index.vue`）

1. **操作列**：`[图片] [上传] [编辑] [更多 ▾]`；「更多」下拉项：
   导入标注 / 导出 / 导出历史 / 数据清洗 / 去训练 / —— / 删除 / 彻底删除（危险）。
   移除工具栏全局「X-AnyLabeling 导入」按钮。列 `min-width` 调整为一行放得下。
2. **导入弹窗**（改为行内入口打开）：
   - 标题「导入标注到〈数据集名〉」；不再有数据集下拉。
   - ZIP 选择后回显文件名与大小；提示大小上限与格式。
   - 提交后展示 `el-progress`（百分比）+ 阶段文字 + `processed/total`。
   - 轮询 `GET /dataset/import/{job_id}`（1s）；`done` 显示结果 + 「去任务」跳工作台；
     `failed` 显示错误；组件卸载/关闭弹窗时停止轮询。
3. API 层 `api/module_annotation.ts`：新增
   `getImportJob(jobId)`；`importXAnyLabeling` 返回结构改为 `{job_id}`（上传超时保持较大值）。
4. `getDatasetList` 列表接口不再需要为下拉预加载 100 条（移除 `loadDatasetOptions`）。

### F. 错误处理

- 导入 job 内任何异常 → 记录 `error`，状态 `failed`，不影响其他请求。
- zip 非法/超限 → 提交阶段直接 400。
- 轮询 job 不存在 → 404。
- 后台任务持有的文件字节：读入内存后释放请求体；超大文件（> `ANNOTATION_IMPORT_MAX_MB`）拒绝。

## 验收标准

- `/dataset/list?page_size=100` 在 157 个数据集下显著下降（目标 < 1s），且读路径不再写库。
- 数据集列表任务进度徽标数值与详情一致。
- 750MB `车号数据集.zip` 可导入：上传后立即返回 job_id，进度单调递增至 100%，期间其他接口不卡顿。
- 导入完成后：936 张图片入库（含缩略图）、1019 个检测框、生成 1 个 `[导入] ...` 任务、数据集计数正确。
- 导入图片在工作台左侧与数据集图片网格显示缩略图。
- 操作列严格一行；「更多」包含全部次级操作；全局导入按钮移除。
- 超大/非 zip 文件被拒。
- 既有导入相关测试更新并通过；全量 pytest 通过；annotation 前端 vue-tsc 无新错误。

## 测试

- pytest：
  - 列表聚合：构造多数据集多任务，断言进度与逐任务计算一致；断言列表接口不产生写（可通过对比 `updated_time` 或计数不变近似验证）。
  - 导入端到端（小 zip，mock S3）：images/annotations/thumbnail_key/task 正确；进度单调。
  - 导入超限拒绝；job 不存在 404。
- Playwright：
  - 行「更多」菜单展开含全部次级操作。
  - 行内导入打开弹窗（无数据集下拉），选文件→进度→完成。
  - 操作列不再 3 行。

## 风险

- 后台任务对象在请求结束后仍被引用：必须先把上传字节物化（内存或临时文件）。
- 进程内 job 表：服务重启后丢失（可接受；重启后导入中断）。
- 大文件内存：`ANNOTATION_IMPORT_MAX_MB=1024` 上限下，读入内存 1GB 峰值；如需更大改临时文件路径。
- 列表聚合查询需覆盖 `jsonb_array_length` 方言差异。
