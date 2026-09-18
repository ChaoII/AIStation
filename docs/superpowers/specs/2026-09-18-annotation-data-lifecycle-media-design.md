# 标注数据生命周期与媒体管线 设计

> 创建日期：2026-09-18
> 状态：已确认（用户认可范围与关键决策）
> 所属：数据标注模块（`backend/app/api/v1/module_annotation/`、`frontend/src/views/module_annotation/`）

## 背景

对标注模块与对象存储架构做了一次评审，结论：整体方向正确且主流（图片放 S3 兼容对象存储 RustFS、元数据与标注放 PostgreSQL、客户端用 presigned URL 访问），但存在四个会在数据量增长后放大的问题：

1. **删除不清理对象存储**：`DatasetService.delete_datasets` 只软删 DB 行，S3 对象永不删除 → 存储泄漏。且软删可 restore，与"删对象不可逆"存在语义冲突。
2. **无缩略图**：PRD 6.3 提到 `thumbnails/`，但上传未生成缩略图，任何多图列表都会拉原图。
3. **上传全走后端且串行**：`upload_images` 逐文件读取到内存后上传，未设置 `ContentType`，无校验，批量上传慢且渲染可能异常。
4. **标注版本表无索引且无限膨胀**：`annotation_record` 每次保存插入完整 JSON 快照（append-only），无 `(task_id, image_id, version)` 索引，历史无保留策略。

另核实：当前前端**没有消费缩略图的 UI**（数据集页是表格，工作台左侧仅文件名列表），因此缩略图必须同时新增消费方才有收益。

## 范围

**做：**

- **P1 数据生命周期**：软删保持不动 S3；新增"彻底删除"（purge）+ 定时清理过期软删；标注版本保留策略 + 复合索引。
- **P2 媒体管线**：上传时服务端生成缩略图；设置 `ContentType`；线程池并发 + 并发限流；扩展名/单文件大小/单次数量校验；存量缩略图回填脚本。
- **P3 前端消费**：工作台左侧图片列表改为缩略图 filmstrip；数据集页新增图片网格抽屉（缩略图 + 状态筛选 + 进入工作台）；数据集操作列增加"彻底删除"。
- **P4 回归**：导出 → 训练链路不被破坏，e2e 与 lint/typecheck。

**不做：**

- 浏览器直传（presigned PUT）——本次保留后端中转，避免引入 CORS 与"后端拿不到字节无法生成缩略图"的矛盾。
- 对象存储内容去重、感知哈希、质量评分。
- presigned URL 自动续期（保持现状，1h 过期）。
- 修改标注画布/绘制/协作逻辑。

## 关键决策（已确认）

| 决策点 | 结论 |
|---|---|
| 上传方式 | 保留浏览器 → 后端 → S3；后端生成缩略图。不做直传 |
| 缩略图规格 | JPEG、长边 ≤ 512、质量 85、按 EXIF 方向转正；上传时生成 + 提供存量回填脚本 |
| 缩略图 URL 下发 | `get_images` 每项返回 presigned `thumbnail_url`（presign 为本地签名，无网络开销） |
| 删除生命周期 | 软删只藏 DB（可 restore）；新增 purge 接口 + 定时清理；对象存储删除只在 purge 发生 |
| 版本保留 | 保留首版 v1 + 最近 N 版（默认 20），中间版本清理；rollback 仍 append-only |
| 上传部分失败 | 单文件失败不拖垮整批，返回 `uploaded` 与 `failed` 明细 |
| 缩略图消费方 | 工作台 filmstrip **与** 数据集页图片网格，两者都做 |

## 组件设计

### A. 数据契约（对象存储 key）

| 用途 | key 模式 | 状态 |
|---|---|---|
| 原图 | `datasets/{datasetId}/images/{uuid}{ext}` | 现有 |
| 缩略图 | `datasets/{datasetId}/thumbnails/{uuid}.jpg` | 新增 |
| X-AnyLabeling 导入标注 | `annotations/dataset_{datasetId}/{uuid}{ext}` | 现有 |
| 导出 ZIP | `train/exports/dataset_{datasetId}_{format}_{userId}.zip` | 现有 |

### B. 后端：数据模型与迁移

- `AnnotationImageModel` 新增 `thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="RustFS 缩略图 key")`。
- Alembic 迁移（单个 revision，供升级与回滚）：
  - 新增列 `annotation_image.thumbnail_key`。
  - 新增索引 `ix_annotation_record_task_image_version (task_id, image_id, version)`。
  - 新增索引 `ix_annotation_image_dataset_status (dataset_id, status)`。
  - 删除 `annotation_dataset.bucket_name`（死字段，真实 bucket 由 `RUSTFS_BUCKET_PREFIX + env` 推导）。
- 说明：已核实 `bucket_name` 仅在模型定义与建表迁移中出现，`DatasetOutSchema` 与前端均无引用，删除列不影响 API 合约。

### C. 后端：删除生命周期

- `delete_datasets`（现有软删）**保持不变**：仅级联软删 DB，不触碰任何 S3 key。UI 文案需相应修正（当前确认框写"图片和标注数据将一并删除"，会误导）。
- 新增 `DatasetService.purge_datasets(ids)`：
  1. 物理删除 `annotation_record`（按该数据集图片）、`annotation_dataset_export`、`annotation_image`、`annotation_task`、`annotation_dataset`。
     注意：`DatasetExportModel` 继承 `MappedBase`（无软删），本就物理数据；其余为物理 DELETE。
  2. 删除 S3 前缀：`datasets/{dsId}/`、`annotations/dataset_{dsId}/`、`train/exports/dataset_{dsId}_`。
     复用 `s3_client.delete_prefix`；`delete_prefix` 目前只取第一页（1000 对象上限），需改造为分页循环直至 `IsTruncated=False`。
  3. 幂等：对象不存在不报错。
- 新增路由 `DELETE /annotation/dataset/purge`，权限 `annotation:dataset:purge`。
- 新增定时任务 `app/api/v1/module_annotation/dataset/retention.py::start_annotation_purge_retention()`：
  - 循环间隔 `ANNOTATION_PURGE_INTERVAL_SEC`（默认 86400）。
  - 扫描 `is_deleted=true` 且 `deleted_time < now - ANNOTATION_PURGE_RETENTION_DAYS`（默认 30 天）的数据集 id，调用 purge。
  - 在 `init_app.py` 生命周期中 `start_annotation_purge_retention()` 挂载（参考 `start_alarm_record_retention`）。
- 新增配置（`setting.py`，命名与 `.env.dev` 同步）：`ANNOTATION_PURGE_RETENTION_DAYS=30`、`ANNOTATION_PURGE_INTERVAL_SEC=86400`。

### D. 后端：上传与缩略图管线

改造 `DatasetService.upload_images`：

1. **校验（整批前置，不通过则 400，不写任何对象）：**
   - 扩展名白名单：`.jpg .jpeg .png .bmp .webp .tif .tiff`。
   - 单文件大小 ≤ `ANNOTATION_UPLOAD_MAX_MB`（默认 20）。
   - 单次数量 ≤ `ANNOTATION_UPLOAD_MAX_FILES`（默认 200）。
   - 配置项加入 `setting.py` 与 `.env.dev`。
2. **每文件处理（`asyncio.to_thread` + `asyncio.Semaphore(ANNOTATION_UPLOAD_CONCURRENCY)`，默认 4）：**
   - 读取内容（`await file.read()`）。
   - PIL：`ImageOps.exif_transpose` 后取 `size`；生成缩略图 `img.thumbnail((512, 512))`，转 RGB 后编码 JPEG（quality=85）。
   - 上传原图到 `datasets/{dsId}/images/{uuid}{ext}`，`ContentType` 取真实 mime（由扩展名映射，不用 `octet-stream`）。
   - 上传缩略图到 `datasets/{dsId}/thumbnails/{uuid}.jpg`，`ContentType=image/jpeg`。
   - 写 `AnnotationImageModel`（含 `thumbnail_key`）。
   - 单文件异常：捕获记入 `failed:[{filename, reason}]`，继续后续文件。
3. **返回**：`{"uploaded": [{id, filename, object_key, thumbnail_key}], "failed": [...], "uploaded_count": n, "failed_count": m}`。
4. **计数重算**：与现有逻辑一致，重算 `dataset.image_count`。
5. `s3_client` 扩展：`upload_fileobj` 增加可选 `content_type` 参数（透传 `ExtraArgs={"ContentType": ...}`）。

改动的 API 兼容性：现有前端 `handleUploadSubmit` 只 `refreshList()`，不消费返回值，因此返回结构变化不影响现有调用；但前端应提示 `failed`。

### E. 后端：读取契约

- `DatasetService.get_images` 每条 item 增加：
  - `thumbnail_key: str | None`
  - `thumbnail_url: str | None`（`thumbnail_key` 存在时 `s3_client.presigned_url(thumbnail_key)`，否则 `null`）
- 老数据（`thumbnail_key IS NULL`）前端回退到 `presigned-url` 原图。
- 工作台单张原图访问仍走 `GET /anno/image/{id}/presigned-url`。

### F. 后端：标注版本保留

- `AnnotationService.save_annotations` 插入新版本后执行清理：
  - 设 `keep = ANNOTATION_VERSION_KEEP`（默认 20）。
  - 当 `version > keep + 1` 时：`DELETE FROM annotation_record WHERE task_id=.. AND image_id=.. AND version >= 2 AND version <= version - keep`。
  - 语义：保留 v1（原始）与最近 `keep` 版。
- `rollback_annotation` 不变（仍 append 新版本）。若回滚目标版本已被清理 → 沿用现有"目标版本不存在 404"。
- 配置项 `ANNOTATION_VERSION_KEEP=20` 加入 `setting.py` 与 `.env.dev`。

### G. 存量回填脚本

- `backend/scripts/backfill_annotation_thumbnails.py`：
  - 复用 app 的 async engine / `async_db_session`，参考 `scripts/seed_layouts.py` 的启动方式。
  - 查询 `thumbnail_key IS NULL AND is_deleted = false` 的图片，逐张从 S3 下载原图 → 生成缩略图 → 上传 → 回写 `thumbnail_key`。
  - 支持 `--dataset-id` 限定、`--limit` 限量、`--dry-run`。
  - 幂等：已存在缩略图 key 则跳过。

### H. 前端：工作台 filmstrip

- 修改 `frontend/src/views/module_annotation/annotation/index.vue` 左侧列表（约 950–980 行）：
  - 每项由"文件名文本"改为"缩略图 + 文件名"。
  - `thumbnail_url` 存在时用 `<img loading="lazy" :src="img.thumbnail_url">`，否则回退原图 presigned（或文件名占位）。
  - 失败 `@error` 回退占位，不阻塞翻页。
- **约束**：仅改该列表的模板与最小样式，不触碰画布/绘制/协作/Pinia 逻辑；不改标注保存链路。

### I. 前端：数据集图片网格

- 新增组件 `frontend/src/components/Annotation/DatasetImageGrid.vue`：
  - **单根元素**（项目要求，避免 `<Transition>` 白屏）。
  - 布局用 `el-row`/`el-col`（项目约束：不用自定义 CSS Grid）。
  - 数据源 `AnnotationAPI.getImages(datasetId, undefined, page, pageSize)`，分页加载。
  - 每格：缩略图（无则回退原图 presigned）、文件名、状态角标（unannotated/in_progress/annotated）。
  - 顶部筛选：全部 / 未标注 / 已标注（前端过滤或后端 `status` 参数；`get_images` 当前未实现 `status` 过滤，本设计采用**前端过滤当前页 + 后端分页**，如需全量筛选另议）。
  - 点击图片：若数据集存在任务则跳转 `/annotation/workbench/{taskId}`，否则提示先建任务。
- 数据集页 `dataset/index.vue` 操作列新增"图片"按钮，打开网格抽屉；新增"彻底删除"按钮（`v-hasPerm="['module_annotation:dataset:purge']"`，危险色 + 二次确认，调用 purge 接口）。
- API 层 `frontend/src/api/module_annotation.ts` 增加 `purgeDataset(ids: number[])`。
- 修正软删确认框文案：改为"确认删除所选数据集？可在保留期内恢复。"（不再声称一并删除图片）。

### J. 错误处理

- 上传：整批校验失败返回明确错误信息；单文件失败返回明细，前端 `ElMessage` 汇总提示。
- purge：S3 删除失败记录日志但不阻断 DB 清理（先删 DB 再删对象，或先删对象再删 DB 二选一）——**决策：先删 S3 前缀再删 DB 行**；S3 删除异常向上抛出，DB 事务回滚，保证不会出现"DB 没了对象还在"的不可恢复态。
- 缩略图生成失败：不阻断原图上传，`thumbnail_key` 置空，前端回退原图。
- retention loop：任何异常 catch + log，不退出循环。

## 验收标准

- 软删数据集后，S3 对象仍在；`restore` 后图片可正常访问。
- `purge` 数据集后：DB 相关行全部物理删除，`datasets/{id}/`、`annotations/dataset_{id}/`、`train/exports/dataset_{id}_*` 下对象清空；重复 purge 幂等。
- 超过保留期的软删数据集被 retention loop 自动 purge。
- 上传图片后：S3 存在原图与缩略图；原图 `Content-Type` 为真实图片类型；缩略图长边 ≤512 且为 JPEG。
- 上传非法扩展名 / 超大文件 / 超数量 → 400，且不产生任何对象或 DB 行。
- 上传含坏图 → 其余成功，返回 `failed` 明细。
- `get_images` 返回 `thumbnail_url`；老数据返回 `null`。
- 保存标注超过 N 次后，`annotation_record` 保留 v1 + 最近 N 版（数量可控）；rollback 最近版本仍可用。
- 迁移包含两个索引与 `thumbnail_key` 列；`alembic upgrade`/`downgrade` 可逆。
- 工作台 filmstrip 显示缩略图且懒加载；数据集图片网格可筛选并跳转工作台。
- 回归：现有导出（YOLO/PaddleOCR/X-AnyLabeling）→ 训练链路不变。

## 测试

- pytest：
  - 缩略图生成尺寸/格式；`ContentType` 透传。
  - 上传校验拒绝（扩展名/大小/数量），无副作用。
  - 上传部分失败返回明细。
  - `get_images` 的 `thumbnail_url` 合约与老数据回退。
  - 软删不删对象；purge 删对象且幂等；purge S3 失败时 DB 不提交。
  - retention loop 选中过期软删并 purge。
  - 版本保留：保存 N+k 次后保留 v1 + 最近 N 版。
  - 迁移升级/回滚（索引与列存在性）。
  - `delete_prefix` 分页（>1000 对象，可用 fake client）。
- Playwright：
  - 工作台 filmstrip 加载缩略图、翻图正常。
  - 数据集图片网格渲染、筛选、点击跳转。
  - 软删 → 恢复；purge 后列表消失。

## 实施顺序

1. **P1 数据生命周期**（低风险先做）：迁移（列+索引+删死字段）、`delete_prefix` 分页、purge 接口、retention loop、版本保留、文案修正。
2. **P2 媒体管线**：`ContentType`、缩略图生成、并发 + 校验、`get_images` 合约、回填脚本。
3. **P3 前端消费**：filmstrip、图片网格、purge 按钮。
4. **P4 回归**：导出→训练链路 e2e、lint、type-check、pytest 全量。

## 风险与缓解

- **P3 改动 4202 行 `annotation/index.vue`**：该文件已有历史 lint 问题。缓解：只做最小模板/样式改动，不引入新业务逻辑，改后单独 lint 该文件（既有问题记录在案，不扩大）。
- **数据集页图片网格是新增功能而非修 bug**：工作量集中在 P3，需与用户确认交互细节后再动。
- **purge 不可逆**：仅权限点 + 危险色 + 二次确认 + 保留期软删缓冲三重保护。
- **缩略图回填是长任务**：脚本化、可分批（`--limit`/`--dataset-id`），不在服务进程内跑。
