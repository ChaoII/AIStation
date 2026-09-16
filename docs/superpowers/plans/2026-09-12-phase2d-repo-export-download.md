# Phase 2D：模型仓库/导出/下载一致性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复"导出产物下载不可靠、format 标签与真实文件不符"；修复模型仓库编辑表单字段错位（`dataset_id` vs `annotation_dataset_id`、status 未提交）；评估/预测/部署的模型下拉不再被默认 20 条截断。

**Architecture:** 导出产物使用**确定性对象键**（`train/models/model_{id}/export/best.<ext>`）；新增 `s3_client.object_exists`，下载接口按该键重签 URL 且返回**真实** format；前端修编辑载荷与模型下拉分页。

**Tech Stack:** FastAPI + SQLAlchemy + boto3 + pytest；Vue3 + Playwright。

## Global Constraints

- 后端 `D:\AIStation\backend`（`uv run pytest`/`uv run ruff check`，只判断新增）；前端 `D:\AIStation\frontend`（`pnpm run type-check` 无新增；`pnpm e2e` 通过）。
- 中文注释。不新增依赖、**不做数据库迁移**。提交 `fix(train): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- 导出产物 URL 有效期（`RUSTFS_PRESIGNED_URL_EXPIRY=3600s`）过期后，前端应能通过下载接口**重新**获取，而不是持有过期 URL。

---

### Task 1: 导出产物可重下载 + format 真实

**背景:** `export_service.export_model_to_format` 上传到确定性键 `train/models/model_{id}/export/best.<ext>` 但**不落库**；`download_model` 永远返回 `storage_path`（原始 `.pt`/`.pdparams`）却把 DB 的 `format` 当导出格式返回（如 format=onnx 实为 best.pt）。导出响应里的 presigned URL 过期后无法再取。

**Files:**
- Modify: `backend/app/utils/s3_client.py`（新增 `object_exists`）
- Modify: `backend/app/plugin/module_train/controller.py`（`download_model`）
- Test: `backend/tests/test_model_download.py`

**Interfaces:**
- Produces: `S3Client.object_exists(object_key: str, env: str | None = None) -> bool`（`head_object`，`ClientError`→False）。
- Produces: `resolve_download_target(model: dict, exists_fn) -> tuple[str, str]` —— 返回 `(object_key, format)`：若模型 `format` 非原始（`!= "pytorch"`）且确定性导出键存在 → 返回导出键与导出格式；否则返回 `storage_path` 与 `"pytorch"`（真实原始格式）。

- [ ] **Step 1: Write the failing test**

```python
"""模型下载目标解析测试。"""
from app.plugin.module_train.controller import resolve_download_target


def test_download_target_export_when_exists():
    model = {"id": 5, "storage_path": "train/models/task_1/best.pt", "format": "onnx"}
    key, fmt = resolve_download_target(model, exists_fn=lambda k: k.endswith("best.onnx"))
    assert key == "train/models/model_5/export/best.onnx"
    assert fmt == "onnx"


def test_download_target_original_when_export_missing():
    model = {"id": 5, "storage_path": "train/models/task_1/best.pt", "format": "onnx"}
    key, fmt = resolve_download_target(model, exists_fn=lambda k: False)
    assert key == "train/models/task_1/best.pt"
    assert fmt == "pytorch"


def test_download_target_pytorch_original():
    model = {"id": 5, "storage_path": "train/models/task_1/best.pt", "format": "pytorch"}
    key, fmt = resolve_download_target(model, exists_fn=lambda k: True)
    assert key == "train/models/task_1/best.pt" and fmt == "pytorch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_model_download.py -q`
Expected: FAIL（`resolve_download_target` 不存在）。

- [ ] **Step 3: Implement**

`s3_client.py`：
```python
    def object_exists(self, object_key: str, env: str | None = None) -> bool:
        try:
            self.client.head_object(Bucket=self._bucket(env), Key=object_key)
            return True
        except ClientError:
            return False
```

`controller.py` 新增纯函数（放在 `download_model` 附近）：
```python
_EXPORT_EXT = {"onnx": ".onnx", "torchscript": ".torchscript", "engine": ".engine",
               "coreml": ".mlpackage", "litert": ".tflite", "pb": ".pb", "tflite": ".tflite",
               "edgetpu": ".tflite", "openvino": "", "saved_model": "", "paddle": "", "ncnn": "", "tfjs": ""}


def resolve_download_target(model: dict, exists_fn) -> tuple[str, str]:
    """决定下载对象键与真实格式：优先确定性导出产物，否则原始权重。"""
    storage_path = model.get("storage_path") or ""
    fmt = model.get("format") or "pytorch"
    if fmt != "pytorch":
        ext = _EXPORT_EXT.get(fmt, "")
        key = f"train/models/model_{model.get('id')}/export/best{ext}"
        if exists_fn(key):
            return key, fmt
    return storage_path, "pytorch"
```

`download_model` 改用：
```python
    key, fmt = resolve_download_target(model, lambda k: s3_client.object_exists(k))
    url = s3_client.presigned_url(key)
    return SuccessResponse(data={"download_url": url, "format": fmt})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_model_download.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/utils/s3_client.py app/plugin/module_train/controller.py`

```bash
git add backend/app/utils/s3_client.py backend/app/plugin/module_train/controller.py backend/tests/test_model_download.py
git commit -m "fix(train): 导出产物可重新下载且返回真实格式"
```

---

### Task 2: 模型编辑字段/状态 + 模型下拉分页

**背景:** `repo/index.vue` 编辑模型时表单绑定 `formData.dataset_id` 而后端返回 `annotation_dataset_id`（回显为空）；提交未带 `status`（弹窗有草稿/发布/归档选择但从不保存）；eval/predict/deploy 的模型下拉用 `getModelList()` 默认 `page_size=20`，超过 20 个版本无法选择。

**Files:**
- Modify: `frontend/src/views/module_train/repo/index.vue`
- Modify: `frontend/src/views/module_train/eval/index.vue`
- Modify: `frontend/src/views/module_train/predict/index.vue`
- Modify: `frontend/src/views/module_train/deploy/index.vue`
- Test: `frontend/e2e/model-repo-edit.spec.ts`（可选）

**Interfaces:**
- 编辑回显使用 `annotation_dataset_id`；提交带 `status`（与后端 `ModelUpdateSchema` 一致）。
- 各下拉 `getModelList({ page_no: 1, page_size: 100 })`（或循环取全量）。

- [ ] **Step 1: 修编辑字段与状态**

`repo/index.vue`：`handleOpenDialog`（编辑）改为 `formData.annotation_dataset_id = item.annotation_dataset_id`（模板相应改绑定）；提交载荷加入 `status: formData.status`（若后端 `ModelUpdateSchema` 无 `status`，先确认——Phase 0A 审阅指出 `status` 未在 update schema；若确实没有，请在 `backend/app/plugin/module_train/schema.py` 的 `ModelUpdateSchema` 增加 `status: str | None = None` 并允许更新）。

- [ ] **Step 2: 模型下拉分页**

`eval/index.vue`、`predict/index.vue`、`deploy/index.vue` 中加载模型列表处传 `page_size: 100`；若仍需更多，循环翻页合并。

- [ ] **Step 3: 类型检查 + E2E**

Run: `cd frontend && pnpm run type-check && pnpm e2e`
Expected: 无新增类型错误；e2e 通过。若新增 `model-repo-edit.spec.ts`，创建模型 → 编辑描述/状态 → 断言列表回显与持久化。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_train/repo/index.vue frontend/src/views/module_train/eval/index.vue frontend/src/views/module_train/predict/index.vue frontend/src/views/module_train/deploy/index.vue backend/app/plugin/module_train/schema.py frontend/e2e/model-repo-edit.spec.ts
git commit -m "fix(train): 模型编辑字段/状态落库 + 模型下拉取全量"
```

---

## Self-Review

**Spec coverage（对照 Phase 2 spec 组件 D）:**
- 导出/下载一致性 + 真实格式 → Task 1 ✅
- 模型 id 语义（导出用版本 id；下载确定性键）→ Task 1 ✅
- 编辑字段/状态 → Task 2 ✅
- 模型下拉分页 → Task 2 ✅

**Placeholder scan:** 无 TBD；Task 2 Step 1 对 `ModelUpdateSchema.status` 先确认再改。

**Type consistency:** `object_exists`/`resolve_download_target`/`annotation_dataset_id`/`status` 命名一致。

**风险:** Task 1 的 `resolve_download_target` 依赖导出格式到扩展名的映射与 `export_service.EXPORT_EXT` 一致；若两处漂移会导致 object_exists 查错键。建议从 `export_service` 导入 `EXPORT_EXT` 而非复制。
