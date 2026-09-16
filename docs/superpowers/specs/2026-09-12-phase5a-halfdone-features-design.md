# Phase 5A：非主链路半成品功能补全（P1-P6）设计

> 创建日期：2026-09-12
> 状态：设计已确认（用户批准）
> 关联：
> - `2026-09-11-pipeline-optimization-program-design.md`（Phase 5：非主链路半成品功能补全）
> - 本阶段为 Phase 5 的第一部分；实时协作（P7）拆到 5B 单独 spec/plan

## 1. 背景与目标

Phase 5 目标是把非主链路的半成品功能修到"可从 UI 完整操作并产生正确结果"。经只读审计，当前 7 项中的 6 项仍不完整（布控/录制定时已 FIXED）：

| # | 功能 | 现状 |
|---|---|---|
| P1 | 导出历史 | **BROKEN**：`annotation_dataset_export` 表只读、无任何写入方，历史恒为空；无前端 |
| P2 | 定时训练 UI | 后端完整（模型/服务/调度器/接口/测试）；**前端全无** |
| P3 | 数据清洗/异常检测 UI | 后端完整（check/duplicates/anomalies）；**前端全无** |
| P4 | 部署详情/日志查看器 | 后端有 detail/logs 接口且写日志文件；**前端无查看器** |
| P5 | 标注历史/回滚 | 后端只读历史（`version` append-only），**无回滚接口**；前端未接入（仅本地 undo/redo） |
| P6 | 模型仓库/版本 UI | 后端 repo+version 接口已有（无 tags）；前端仍是扁平版本列表 |

**目标**：让上述 6 项均可在 UI 完整操作并产生正确结果。

**非目标**：
- 实时协作（P7）→ 5B。
- 给模型仓库加 tags/分组字段（本次仅仓库+版本 UI，无 schema 变更）。
- 布控/录制定时（已 FIXED）。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|---|---|
| 范围 | P1-P6；P7 拆到 5B |
| P6 深度 | 仓库列表 + 版本抽屉，**不加 tags/分组字段、不做迁移** |
| P5 回滚语义 | **新建最新版本**（append-only，可再回滚、可审计） |
| P1 字段 | `dataset_id/format/exported_by/file_size/checksum/download_url/export_time/extra` |
| P2 cron | **可视化构建器**（`vue3-cron-plus` 已是现有依赖） |
| 实施结构 | 按功能独立切片：P1→P4→P2→P3→P5→P6 |
| 测试 | 后端 pytest + 前端 Playwright E2E + type-check/lint |

## 3. 架构总览

```
后端（仅 P1 写入 + P5 回滚为新增）
  module_train/service.export_dataset ──写入──▶ annotation_dataset_export
  annotation/anno/image/{id}/rollback ──新建版本──▶ AnnotationRecordModel

前端（新增 API + 抽屉/Tab，全部挂现有页面，不新增菜单）
  api/module_annotation.ts  ← P1/P3/P5
  api/module_train.ts       ← P2/P4/P6
  dataset 页    : 导出历史抽屉(P1) + 数据清洗抽屉(P3)
  deploy 页     : 部署详情/日志抽屉(P4)
  task 页       : 定时训练 Tab(P2)
  workbench     : 标注历史抽屉 + 回滚(P5)
  repo 页       : 仓库列表 + 版本抽屉(P6)
```

## 4. 后端设计

### 4.1 P1 导出历史写入
- `backend/app/plugin/module_train/service.py::export_dataset`：在生成 ZIP、计算 `file_size`/`checksum(MD5)`、上传 RustFS 得到 `download_url` 后，写入 `DatasetExportModel(dataset_id, format, exported_by=auth.user.id, download_url, file_size, checksum, export_time=now, extra={"annotation_task_id":..., "ocr_rec":...})`。
- 复用现有 `GET /api/v1/annotation/dataset/export/history/{dataset_id}`；返回结构与字段已在 `export_service.list_exports` 定义。
- 写入失败不阻断导出主流程（记录 warning）。

### 4.2 P5 标注回滚
- `AnnotationService.rollback_annotation(task_id, image_id, version, auth) -> dict`：
  1. 校验图片锁（同 `save_annotations`，被他人锁 → 409）；
  2. 查询目标 `version` 的 `annotation_data`（不存在 → 404/`CustomException`）；
  3. 取当前最大 version，插入**新记录** `version = max+1`，`annotation_data` 为目标版本内容；
  4. 同步 `image.status`/`annotation_count` 与 `dataset.annotated_count`（复用现有逻辑）。
- `POST /api/v1/annotation/anno/image/{image_id}/rollback`，body `{task_id, version}`，权限沿用标注保存权限。
- 历史读取接口已存在（`GET /anno/image/{id}/history`）。

### 4.3 P2/P3/P4 后端
无需改动：schedule CRUD、clean check/duplicates/anomalies、deploy detail/logs 均已存在。

## 5. 前端设计

### 5.1 API
- `src/api/module_annotation.ts` 新增：
  `getExportHistory(datasetId)`、`getAnnotationHistory(taskId, imageId)`、`rollbackAnnotation(imageId, { task_id, version })`、`cleanCheck(datasetId)`、`cleanDuplicates(datasetId)`、`cleanAnomalies(datasetId)`。
- `src/api/module_train.ts` 新增：
  schedule：`getTrainScheduleList/createTrainSchedule/updateTrainSchedule/deleteTrainSchedule`；
  deploy：`getDeployDetail(id)`、`getDeployLogs(id)`；
  repo：`getModelRepos(params)`、`getModelVersions(repoId)`。

### 5.2 P1 导出历史抽屉（dataset 页）
- 操作列新增「导出历史」→ 抽屉：表格列 格式 / 导出时间 / 大小 / 导出人 / 操作(下载)。
- 下载用历史 `download_url`；为空显示「—」。

### 5.3 P4 部署详情/日志抽屉（deploy 页）
- 操作列新增「详情」→ 抽屉：上半部署信息（模型/端口/状态/API URL/续期时间），下半日志查看器（`getDeployLogs`，刷新按钮 + 打开时拉取；文本域样式复用训练详情）。

### 5.4 P2 定时训练 Tab（task 页）
- task 页加 `el-tabs`：「训练任务」+「定时训练」。
- 定时 Tab：列表（名称/关联框架/`cron_expr`/启用/上次运行/操作）+ 新建/编辑弹窗（名称、框架、数据集、超参复用、cron 可视化构建器 `vue3-cron-plus`、启用开关、备注）。
- 将构建器输出的 cron 值转换为后端可解析的 5 段 `cron_expr`。
- **不新增前端依赖**；列表不做「下次运行时间」计算，仅展示 `cron_expr` 文本与「上次运行时间」。

### 5.5 P3 数据清洗抽屉（dataset 页）
- 操作列新增「数据清洗」→ 抽屉，三个分区（`el-tabs`）：健康检查（统计/问题概览）、重复文件名（分组列表）、异常标注（列表 + 原因）。
- 只读展示，不做自动修复（避免误删）。

### 5.6 P5 标注历史抽屉（workbench）
- 工具栏「历史」→ 抽屉：版本列表（版本号、时间、标注数）+ 预览 + 「恢复此版本」（`ElMessageBox.confirm` 后调 rollback，成功后刷新画布与历史、重载当前标注）。

### 5.7 P6 模型仓库/版本 UI（repo 页）
- 列表维度从版本改为**仓库**：`getModelRepos` 数据源，列 名称 / 框架 / 版本数 / 状态 / 创建时间 / 操作。
- 操作列「版本」→ 版本抽屉：`getModelVersions(repoId)` 列表（版本号 / 指标摘要 / 时间），行内保留 训练/评估/预测/导出/部署 操作（迁移现有 `handleTrain/handleEval/handlePredict/handleExport/handleDeploy`，注意它们基于版本 `id`）。
- 保留现有编辑/删除（仓库维度）。

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| 历史/日志为空 | 空态提示，不报错 |
| 导出历史下载链接过期/为空 | 下载按钮 disabled 或提示重新导出 |
| 回滚目标版本不存在 | 后端 404/异常 → 前端提示 |
| 回滚时图片被他人锁 | 后端 409 → 前端提示 |
| cron 非法 | 前端构建器校验 + 后端拒绝 |
| 清洗接口失败 | 抽屉内错误态，不阻断页面 |
| 历史写入失败 | 仅 warning，不阻断导出 |

## 7. 测试与验收

**后端 pytest**
- 导出后 `annotation_dataset_export` 有记录且 `/export/history/{id}` 返回该记录（含 file_size/checksum/format）。
- `rollback_annotation`：回滚生成 `version=max+1` 且内容等于目标版本；被他人锁 → 409。
- clean 端点：check/duplicates/anomalies 返回结构（已有后端，补冒烟）。

**前端 Playwright E2E**
- 数据集页：打开「导出历史」抽屉；打开「数据清洗」抽屉并渲染分区。
- 部署页：打开「详情」抽屉并加载日志。
- 训练页：切到「定时训练」Tab，打开新建弹窗并可见 cron 构建器。
- 工作台：打开「历史」抽屉（有数据时展示版本）。
- 仓库页：列表为仓库维度，打开「版本」抽屉。

**静态检查**
- 新增/改动前端文件 eslint+prettier clean；`vue-tsc` 新增文件 0 错误。

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `vue3-cron-plus` 输出格式与后端 croniter 不一致 | plan 中先确认其输出为 5 段 cron；转换/校验后再提交 |
| 仓库页改造影响 Phase 4 的跳转（训练/评估/预测/导出/部署基于版本 id） | 操作下沉到版本抽屉行，保持传 `version.id`；E2E 回归跳转 |
| 导出历史写入影响导出主流程 | try/except 包裹，失败仅 warning |
| 回滚并发/锁竞态 | 复用 save_annotations 的锁校验；事务内取 max version |
| 清洗结果误读 | 只读展示 + 文案说明，不提供自动删除 |

## 9. 交付拆分（供 writing-plans 参考）

1. P1 导出历史：后端写入 + pytest；前端历史抽屉。
2. P4 部署详情/日志：API + 抽屉 + E2E。
3. P2 定时训练 Tab：API + cron 构建器 + 列表/弹窗 + E2E。
4. P3 数据清洗抽屉：API + 三分区 + E2E。
5. P5 标注历史/回滚：后端回滚 + pytest；前端历史抽屉 + 回滚 + E2E。
6. P6 仓库/版本 UI：API + 仓库列表 + 版本抽屉 + 回归跳转。
7. 回归：pytest + E2E + type-check/lint。
