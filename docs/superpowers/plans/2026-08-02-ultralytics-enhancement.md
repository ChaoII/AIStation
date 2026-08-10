# ultralytics 训练增强 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善 ultralytics 训练参数（前端表单→后端白名单映射→yolo CLI 全部生效）、支持多标签分类（multi_label），并彻底移除 PaddleX。

**Architecture:** 后端 `_build_ultralytics_cmd` 用白名单 `_ULTRALYTICS_HP` 把 hp dict 映射到 yolo CLI 参数；前端"基础/高级"两级表单收集参数；多标签分类通过 `_export_yolo_cls` 的多标签 label 格式 + `multi_label=True` 实现；PaddleX 代码/数据/前端入口彻底移除。

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Vue 3 + Element Plus + TypeScript, Docker

## Global Constraints

- 所有 API 端点 `Depends(AuthPermission([...]))`
- 测试用 `backend/tests/` pytest，同步 `TestClient`（conftest 已配 SQLite + `test_client` fixture + JSONB 补丁）；测试函数用同步 `def`
- 登录测试需带 `X-Forwarded-For: 127.0.0.1` 头（`OperationLogRoute` 校验 IP）
- 前端 v3 模式（`useTable`/`useCrudForm`），端口 5190，登录 admin/123456
- `TrainFramework.PADDLEX` 枚举值**保留**（历史数据兼容），但 `create_task` 拒绝新建 paddlex 任务
- `exporter.py` 的 `_export_paddle_ocr`/`_export_paddle_mlcls` **保留**（子项目 2 完成后删除）；仅删 `_export_paddlex`（通用 paddlex 检测导出）
- 前端 hp dict key 统一用 `lr0`（不是 `lr`），`train_ratio` 为 0-1 小数
- paddlex 历史测试数据清理：`train_models`/`train_tasks`/`train_evals`/`train_predicts`/`train_deploys` 中 `framework='paddlex'` 行

---

### Task 1: 后端白名单常量 + `_build_ultralytics_cmd` 改造

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py:130-140`
- Test: `backend/tests/test_ultralytics_cmd.py`（新建）

**Interfaces:**
- Consumes: `hp: dict`（前端超参表），`task_type: str`（"detection"/"rotated_detection"/"cls" 等）
- Produces: `_ULTRALYTICS_HP` 模块级常量；`_build_ultralytics_cmd(hp, data_dir, export_dir, task_type) -> list[str]` 返回完整 yolo CLI 参数

- [ ] **Step 1: 写失败测试 — 白名单映射**

`backend/tests/test_ultralytics_cmd.py`:

```python
"""测试 ultralytics 训练命令白名单映射。"""
import pytest

from app.plugin.module_train.scheduler import _ULTRALYTICS_HP, _build_ultralytics_cmd


def test_all_frontend_keys_mapped():
    """前端会发送的所有 key 都应出现在白名单（除 train_ratio）。"""
    hp = {"model": "yolo11n.pt", "epochs": 100, "batch": 16, "lr0": 0.01,
          "optimizer": "AdamW", "imgsz": 640, "workers": 4, "device": "0",
          "train_ratio": 0.8}
    assert set(hp.keys()) - {"train_ratio"} <= set(_ULTRALYTICS_HP.keys())


def test_build_cmd_includes_all_present_params():
    hp = {"model": "yolo11n.pt", "epochs": 50, "batch": 32, "lr0": 0.02,
          "optimizer": "SGD", "imgsz": 512, "workers": 8, "device": "1",
          "hsv_h": 0.1, "mosaic": 0.5}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "detection")
    s = " ".join(cmd)
    assert "model=/models/yolo11n.pt" in s
    assert "epochs=50" in s
    assert "batch=32" in s
    assert "lr0=0.02" in s
    assert "optimizer=SGD" in s
    assert "imgsz=512" in s
    assert "workers=8" in s
    assert "device=1" in s
    assert "hsv_h=0.1" in s
    assert "mosaic=0.5" in s
    assert "data=/data/dataset.yaml" in s
    assert "project=/output" in s


def test_build_cmd_omits_absent_params():
    hp = {"model": "yolo11n.pt", "epochs": 100}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "detection")
    s = " ".join(cmd)
    assert "epochs=100" in s
    assert "batch=" not in s
    assert "imgsz=" not in s
    assert "optimizer=" not in s


def test_build_cmd_obb_suffix():
    hp = {"model": "yolo11n.pt"}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "rotated_detection")
    assert "model=/models/yolo11n-obb.pt" in " ".join(cmd)


def test_build_cmd_invalid_param_skipped():
    """校验失败的参数应被跳过（不中断训练）。"""
    hp = {"model": "yolo11n.pt", "epochs": 99999}  # >1000, invalid
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "detection")
    s = " ".join(cmd)
    assert "epochs=" not in s
    assert "model=/models/yolo11n.pt" in s


def test_build_cmd_classification_multi_label():
    hp = {"model": "yolo11n-cls.pt", "multi_label": True}
    cmd = _build_ultralytics_cmd(hp, "/data", "/output", "cls")
    assert "multi_label=True" in " ".join(cmd)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_ultralytics_cmd.py -v`
Expected: FAIL（`_ULTRALYTICS_HP` ImportError，及 `_build_ultralytics_cmd` 当前不返回白名单参数）

- [ ] **Step 3: 实现白名单常量 + 改造命令构造**

在 `scheduler.py` 中、`_build_ultralytics_cmd` 之前添加模块级常量：

```python
# hp dict key → (yolo CLI flag, 默认值, 校验lambda)。仅当 key 在 hp 且值非 None 时拼入命令。
_ULTRALYTICS_HP: dict[str, tuple[str, object, object | None]] = {
    "model":        ("model",         "yolo11n.pt",  None),
    "epochs":       ("epochs",        100,           lambda v: 1 <= int(v) <= 1000),
    "batch":        ("batch",         16,            lambda v: 1 <= int(v) <= 512),
    "imgsz":        ("imgsz",         640,           lambda v: 32 <= int(v) <= 4096),
    "lr0":          ("lr0",           0.01,          lambda v: float(v) > 0),
    "lrf":          ("lrf",           0.01,          lambda v: 0 <= float(v) <= 1),
    "momentum":     ("momentum",      0.937,         lambda v: 0 <= float(v) <= 1),
    "weight_decay": ("weight_decay",  0.0005,        lambda v: float(v) >= 0),
    "optimizer":    ("optimizer",     "AdamW",       lambda v: v in ("AdamW", "SGD", "Adam", "Adamax", "NAdam")),
    "patience":     ("patience",      100,           lambda v: int(v) >= 0),
    "workers":      ("workers",       8,             lambda v: 0 <= int(v) <= 32),
    "device":       ("device",        "0",           None),
    "seed":         ("seed",          0,             None),
    "hsv_h":        ("hsv_h",         0.015,         lambda v: 0 <= float(v) <= 1),
    "hsv_s":        ("hsv_s",         0.7,           lambda v: 0 <= float(v) <= 1),
    "hsv_v":        ("hsv_v",         0.4,           lambda v: 0 <= float(v) <= 1),
    "fliplr":       ("fliplr",        0.5,           lambda v: 0 <= float(v) <= 1),
    "flipud":       ("flipud",        0.0,           lambda v: 0 <= float(v) <= 1),
    "mosaic":       ("mosaic",        1.0,           lambda v: 0 <= float(v) <= 1),
    "mixup":        ("mixup",         0.0,           lambda v: 0 <= float(v) <= 1),
    "multi_label":  ("multi_label",   False,         None),
}
```

替换 `_build_ultralytics_cmd`：

```python
def _build_ultralytics_cmd(hp: dict, data_dir: str, export_dir: str, task_type: str = "detection") -> list[str]:
    model_name = hp.get("model") or "yolo11n.pt"
    # Auto-select OBB model for rotated_detection tasks
    if task_type == "rotated_detection" and "-obb" not in model_name:
        base = model_name.replace(".pt", "")
        model_name = f"{base}-obb.pt"
    cmd = ["yolo", "train", f"model=/models/{model_name}", "data=/data/dataset.yaml",
           "project=/output", "name=exp"]
    for key, (flag, default, validator) in _ULTRALYTICS_HP.items():
        if key == "model":
            continue
        if key not in hp or hp[key] is None:
            continue
        val = hp[key]
        if validator is not None:
            try:
                if not validator(val):
                    log.warning(f"[yolo] skipping invalid hyperparam {key}={val}")
                    continue
            except (TypeError, ValueError):
                log.warning(f"[yolo] skipping invalid hyperparam {key}={val}")
                continue
        if isinstance(val, bool):
            cmd.append(f"{flag}={str(val)}")
        else:
            cmd.append(f"{flag}={val}")
    return cmd
```

注意：`data` 参数保持**硬编码 `data=/data/dataset.yaml`**——`data_dir` 参数是宿主机临时目录路径（`os.path.join(export_dir, "data")`），容器挂载为 `/data`，容器内必须用 `/data`。`data_dir`/`export_dir` 参数保留在签名中（兼容现有调用），本函数内不使用（除非未来需要相对路径）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_ultralytics_cmd.py -v`
Expected: 6 passed

- [ ] **Step 5: 确认 `log` 已导入**

`scheduler.py` 顶部已有 `from app.core.logger import log`。若无则添加。

- [ ] **Step 6: ruff + 提交**

Run: `cd D:/AIStation/backend && uv run ruff check app/plugin/module_train/scheduler.py tests/test_ultralytics_cmd.py`
Expected: clean

```bash
git add backend/app/plugin/module_train/scheduler.py backend/tests/test_ultralytics_cmd.py
git commit -m "feat(train): ultralytics hyperparam whitelist mapping in train command"
```

---

### Task 2: 多标签分类数据导出

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py:57-63, 267-322`
- Test: `backend/tests/test_multilabel_export.py`（新建）

**Interfaces:**
- Consumes: `annotation_task.classification_mode`（"single"/"multi"），`_export_core` 现有 `task_type == "cls"` 分支
- Produces: `_export_yolo_cls(..., multi_label: bool = False)`；多标签时输出 `train/`+`val/` 目录 + 每图 `labels/*.txt`（每行 class id）

- [ ] **Step 1: 写失败测试 — 多标签导出格式**

`backend/tests/test_multilabel_export.py`:

```python
"""测试多标签分类数据集导出（YOLO CLS multi-label 格式）。"""
import inspect

from app.plugin.module_train.exporter import _export_core, _export_yolo_cls


def test_export_yolo_cls_accepts_multi_label_param():
    """_export_yolo_cls 应支持 multi_label 参数（规范参数检查）。"""
    sig = inspect.signature(_export_yolo_cls)
    assert "multi_label" in sig.parameters


def test_export_core_passes_classification_mode():
    """_export_core 应读取 annotation_task.classification_mode 并传给 _export_yolo_cls。"""
    src = inspect.getsource(_export_core)
    assert "classification_mode" in src
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_multilabel_export.py -v`
Expected: FAIL（`_export_yolo_cls` 无 `multi_label` 参数；`_export_core` 无 `classification_mode`）

- [ ] **Step 3: `_export_core` 读取 classification_mode 并传递**

修改 `_export_core` 中确定 `task_type`/`class_names` 的代码块（exporter.py:44-55），在 `ann_task` 存在时额外读取 `classification_mode`：

```python
    # Determine task_type and class names
    task_type = "detection"
    class_names: dict[int, str] = {}
    classification_mode: str | None = None
    if annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task:
                task_type = ann_task.task_type
                classification_mode = ann_task.classification_mode
                if ann_task.classes:
                    for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                        class_names[c["id"]] = c.get("name", f"class_{c['id']}")
```

修改 `_export_core` 的 cls 分支（exporter.py:60-61）：

```python
        if task_type == "cls":
            await _export_yolo_cls(
                dataset_id, task_id, images, output_dir, annotation_task_id,
                train_ratio=train_ratio, class_names=class_names, for_training=for_training,
                multi_label=(classification_mode == "multi"),
            )
```

- [ ] **Step 4: 改造 `_export_yolo_cls` 支持多标签**

替换 `_export_yolo_cls`（exporter.py:267-322）。签名加 `multi_label: bool = False`。单标签走原目录结构；多标签走 label 文件格式：

```python
async def _export_yolo_cls(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None, for_training: bool = False, multi_label: bool = False) -> None:
    """Export classification to YOLO CLS format with train/val split.

    single_label: train/<cls>/<img>.jpg (目录结构)
    multi_label:  train/<img>.jpg + train/labels/<img>.txt (每行一个 class id)
    """
    import random

    from app.utils.s3_client import s3_client

    task_cn: dict[int, str] = class_names or {}
    if not task_cn and annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and ann_task.classes:
                for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                    task_cn[c["id"]] = c.get("name", f"class_{c['id']}")

    # Collect per-image labels: {img_id: [class_id, ...]} (multi) or {img_id: class_id} (single)
    img_labels: dict[int, list[int]] = {}
    async with async_db_session() as db:
        for img in images:
            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            ids: list[int] = []
            for ann in (record.annotation_data if record and record.annotation_data else []):
                cid = ann.get("class_id")
                if cid is not None:
                    ids.append(cid)
            if ids:
                img_labels[img.id] = ids

    if multi_label:
        # Multi-label: flat train/val dirs + labels/*.txt (one class id per line)
        random.shuffle(images)
        split_idx = max(1, int(len(images) * train_ratio)) if images else 0
        for split_name, sub in [("train", images[:split_idx]), ("val", images[split_idx:])]:
            img_dir = os.path.join(output_dir, split_name)
            lbl_dir = os.path.join(output_dir, split_name, "labels")
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(lbl_dir, exist_ok=True)
            for img in sub:
                ids = img_labels.get(img.id, [])
                if not ids:
                    continue
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(os.path.join(img_dir, img.filename), "wb") as f:
                        f.write(data.read())
                except Exception:
                    continue
                stem = os.path.splitext(img.filename)[0]
                with open(os.path.join(lbl_dir, stem + ".txt"), "w") as f:
                    f.write("\n".join(str(cid) for cid in sorted(set(ids))))
        log.info(f"yolo-cls (multi): exported to {output_dir}")
        return

    # Single-label: existing directory structure
    class_imgs: dict[int, list] = {}
    for img in images:
        ids = img_labels.get(img.id, [])
        if ids:
            class_imgs.setdefault(ids[0], []).append(img)
    for cid, imgs in class_imgs.items():
        random.shuffle(imgs)
        split = max(0, int(len(imgs) * train_ratio))
        for split_name, sub in [("train", imgs[:split]), ("val", imgs[split:])]:
            cls_name = task_cn.get(cid, f"class_{cid}")
            dst_dir = os.path.join(output_dir, split_name, cls_name)
            os.makedirs(dst_dir, exist_ok=True)
            for img in sub:
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(os.path.join(dst_dir, img.filename), "wb") as f:
                        f.write(data.read())
                except Exception:
                    continue
    log.info(f"yolo-cls: exported to {output_dir}")
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_multilabel_export.py -v`
Expected: 2 passed

- [ ] **Step 6: 全量回归**

Run: `cd D:/AIStation/backend && uv run pytest tests/ -v`
Expected: 全部通过（含既有）

- [ ] **Step 7: ruff + 提交**

Run: `cd D:/AIStation/backend && uv run ruff check app/plugin/module_train/exporter.py tests/test_multilabel_export.py`
Expected: clean

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_multilabel_export.py
git commit -m "feat(train): multi-label YOLO CLS dataset export"
```

---

### Task 3: 前端超参表单（基础+高级）与 multi_label 开关

**Files:**
- Modify: `frontend/web/src/views/module_train/task/index.vue:80-134, 373-400`
- Test: `cd frontend/web && pnpm run type-check` + `npx vite build`

**Interfaces:**
- Consumes: `_ULTRALYTICS_HP` key 集合（Task 1）
- Produces: `hpForm` 含全部白名单 key；`buildHyperparams()` 返回含 `lr0`（非 `lr`）的 dict；`multi_label` 开关（分类任务显示）

- [ ] **Step 1: 改造 hpForm 默认值与 buildHyperparams**

在 `task/index.vue:373` 将 `hpForm` 默认值更新（key 用 `lr0`）：

```typescript
const hpForm = reactive<Record<string, any>>({
  model: "yolo11n.pt", epochs: 100, batch: 16, lr0: 0.01, optimizer: "AdamW",
  imgsz: 640, workers: 4, device: "0", trainRatio: 80,
  lrf: 0.01, momentum: 0.937, weight_decay: 0.0005, patience: 100, seed: 0,
  hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4, fliplr: 0.5, flipud: 0.0, mosaic: 1.0, mixup: 0.0,
  multi_label: false,
});
```

更新 `buildHyperparams()`（task/index.vue:382-387），`lr` → `lr0`，并保留 train_ratio：

```typescript
function buildHyperparams(): Record<string, any> {
  if (formData.value.framework === "ultralytics") {
    return { ...hpForm, lr0: hpForm.lr0 ?? 0.01, train_ratio: (hpForm.trainRatio || 80) / 100 };
  }
  return { model: hpForm.model, epochs: hpForm.epochs, batch: hpForm.batch, device: hpForm.device };
}
```

注意：`onFrameworkChange`（task/index.vue:375-380）同步更新，ultralytics 分支用新默认值；paddlex 分支删除（Task 4 处理，但此处先保留 paddlex 分支避免未定义引用——Task 4 会移除）。

- [ ] **Step 2: 添加高级参数折叠区**

在 `task/index.vue` 的 `</ElRow>` 之后（`<ElDivider content-position="left">Docker 命令预览</ElDivider>` 之前，约 line 131）插入高级参数折叠：

```html
          <ElCollapse class="hp-advanced-collapse">
            <ElCollapseItem title="高级参数" name="advanced">
              <ElRow :gutter="16">
                <ElCol :span="12"><ElFormItem label="LR Factor (lrf)"><ElInputNumber v-model="hpForm.lrf" :min="0" :max="1" :step="0.001" :precision="4" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Momentum"><ElInputNumber v-model="hpForm.momentum" :min="0" :max="1" :step="0.001" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Weight Decay"><ElInputNumber v-model="hpForm.weight_decay" :min="0" :max="1" :step="0.0001" :precision="4" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Patience"><ElInputNumber v-model="hpForm.patience" :min="0" :max="1000" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Seed"><ElInputNumber v-model="hpForm.seed" :min="0" :max="999999" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="HSV-Hue"><ElInputNumber v-model="hpForm.hsv_h" :min="0" :max="1" :step="0.01" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="HSV-Saturation"><ElInputNumber v-model="hpForm.hsv_s" :min="0" :max="1" :step="0.01" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="HSV-Value"><ElInputNumber v-model="hpForm.hsv_v" :min="0" :max="1" :step="0.01" :precision="3" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Flip LR"><ElInputNumber v-model="hpForm.fliplr" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Flip UD"><ElInputNumber v-model="hpForm.flipud" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="Mosaic"><ElInputNumber v-model="hpForm.mosaic" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
                <ElCol :span="12"><ElFormItem label="MixUp"><ElInputNumber v-model="hpForm.mixup" :min="0" :max="1" :step="0.1" :precision="1" style="width:100%" /></ElFormItem></ElCol>
              </ElRow>
            </ElCollapseItem>
          </ElCollapse>
```

- [ ] **Step 3: 添加 multi_label 开关（分类任务显示）**

在基础参数区末尾（`device` 之后，`</ElRow>` 之前，约 line 130）添加：

```html
            <ElCol v-if="isClassificationTask" :span="12">
              <ElFormItem label="多标签分类">
                <ElSwitch v-model="hpForm.multi_label" />
              </ElFormItem>
            </ElCol>
```

在 script 中新增 computed：

```typescript
const isClassificationTask = computed(() => {
  const activeTask = annoTasks.value.find((t: any) => t.id === formData.value.annotation_task_id);
  return activeTask?.task_type === "classification" || activeTask?.task_type === "cls";
});
```

- [ ] **Step 4: 更新 dockerCmdPreview 使用 lr0**

`task/index.vue:397` 的预览命令 `lr0=${hpForm.lr}` → `lr0=${hpForm.lr0}`。

- [ ] **Step 5: type-check + build**

Run: `cd D:/AIStation/frontend/web && pnpm run type-check`
Expected: 0 errors
Run: `cd D:/AIStation/frontend/web && npx vite build 2>&1 | Select-Object -Last 3`
Expected: `built in ...`

- [ ] **Step 6: 提交**

```bash
git add frontend/web/src/views/module_train/task/index.vue
git commit -m "feat(train): frontend advanced hyperparams form and multi-label switch"
```

---

### Task 4: PaddleX 彻底移除（后端命令 + 数据清理）

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py:143-151, 165`
- Modify: `backend/app/plugin/module_train/service.py:create_task`
- Modify: `backend/app/plugin/module_train/exporter.py:71-72`
- Test: `backend/tests/test_paddlex_removal.py`（新建）

**Interfaces:**
- Consumes: `TrainFramework.PADDLEX`（保留枚举值）
- Produces: `_build_cmd` 无 PADDLEX 分支（删 `_build_paddlex_cmd`）；`create_task` 拒绝 paddlex；`_export_core` 的 `else` 分支改为抛错

- [ ] **Step 1: 写失败测试 — paddlex 移除**

`backend/tests/test_paddlex_removal.py`:

```python
"""验证 PaddleX 训练入口已移除。"""
import inspect

from app.plugin.module_train.scheduler import _build_cmd
from app.plugin.module_train.service import TrainService
from app.plugin.module_train.model import TrainFramework


def test_build_cmd_has_no_paddlex_branch():
    """_build_cmd 不再构造 paddlex 命令。"""
    src = inspect.getsource(_build_cmd)
    assert "paddlex" not in src.lower()


def test_paddlex_framework_still_defined():
    """枚举值保留（历史数据兼容）。"""
    assert TrainFramework.PADDLEX == "paddlex"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd D:/AIStation/backend && uv run pytest tests/test_paddlex_removal.py -v`
Expected: `test_build_cmd_has_no_paddlex_branch` FAIL（当前含 paddlex 分支）

- [ ] **Step 3: 删 `_build_paddlex_cmd` + 改 `_build_cmd`**

`scheduler.py`：
- 删 `_build_paddlex_cmd`（143-151 行）
- `_build_cmd`（154-165）改为：

```python
async def _build_cmd(task, data_dir: str, export_dir: str) -> list[str]:
    """按框架构建训练命令。"""
    if task.framework == TrainFramework.ULTRALYTICS:
        task_type = "detection"
        if task.annotation_task_id:
            from app.api.v1.module_annotation.task.model import AnnotationTaskModel
            async with async_db_session() as db:
                ann_task = await db.get(AnnotationTaskModel, task.annotation_task_id)
                if ann_task:
                    task_type = ann_task.task_type
        return _build_ultralytics_cmd(task.hyperparams, data_dir, export_dir, task_type)
    raise ValueError(f"不支持的训练框架: {task.framework}")
```

- [ ] **Step 4: `service.py:create_task` 拒绝 paddlex**

在 `create_task`（service.py:177 附近）开头添加：

```python
        if data.framework == "paddlex":
            raise Exception("PaddleX 已下线，请使用 ultralytics 框架")
```

- [ ] **Step 5: `exporter.py` 删 `_export_paddlex` 调用分支**

`_export_core`（exporter.py:71-72）的 `else` 分支改为：

```python
    else:
        raise ValueError(f"不支持的导出框架: {framework}")
```

并删除 `_export_paddlex` 函数本体（exporter.py:129-227 附近，即函数定义到 `log.info(f"paddlex: ...")` 为止）。确认该函数未被其他引用（`prepare_training_data_for_task` 只走 `_export_core`）。

- [ ] **Step 6: 数据清理脚本（一次性迁移或 SQL）**

创建 `backend/app/plugin/module_train/cleanup_paddlex_data.py`（一次性脚本）：

```python
"""一次性清理 paddlex 框架的历史测试数据（框架已下线）。"""
import asyncio

from sqlalchemy import delete

from app.core.database import async_db_session

from .model import TrainDeploy, TrainEval, TrainModel, TrainPredict, TrainTask


async def main() -> None:
    async with async_db_session.begin() as db:
        counts = {}
        for model in (TrainModel, TrainTask, TrainEval, TrainPredict, TrainDeploy):
            result = await db.execute(
                delete(model).where(model.framework == "paddlex")
            )
            counts[model.__tablename__] = result.rowcount
        print(f"deleted paddlex rows: {counts}")


if __name__ == "__main__":
    asyncio.run(main())
```

运行：`cd D:/AIStation/backend && uv run python -m app.plugin.module_train.cleanup_paddlex_data`

- [ ] **Step 7: 全量回归 + 提交**

先处理 `test_paddlex_export.py`：该文件是 Task 6（前一计划）为验证 `_export_paddlex` 非 stub 而写的 inspect 测试。`_export_paddlex` 本任务删除后该测试会 FAIL。**删除 `backend/tests/test_paddlex_export.py`**（其断言对象已不存在）。

Run: `cd D:/AIStation/backend && uv run pytest tests/ -v`
Expected: 全部通过（`test_paddlex_removal.py` + 既有测试）

Run: `cd D:/AIStation/backend && uv run ruff check app/plugin/module_train/`
Expected: 无新增错误

```bash
git add backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/service.py backend/app/plugin/module_train/exporter.py backend/app/plugin/module_train/cleanup_paddlex_data.py backend/tests/test_paddlex_removal.py backend/tests/test_paddlex_export.py
git commit -m "feat(train): remove PaddleX training entry and clean historical data"
```

---

### Task 5: 前端 PaddleX 入口移除

**Files:**
- Modify: `frontend/web/src/views/module_train/task/index.vue:75-78, 375-380, 399`
- Test: `cd frontend/web && pnpm run type-check`

**Interfaces:**
- Consumes: Task 4（后端 paddlex 拒绝）
- Produces: framework 下拉仅剩 ultralytics；`onFrameworkChange` 无 paddlex 分支；`dockerCmdPreview` 无 paddlex 预览

- [ ] **Step 1: framework 下拉移除 paddlex**

`task/index.vue:75-78` 的 `ElRadioGroup` 改为仅 ultralytics：

```html
          <ElRadioGroup v-model="formData.framework">
            <ElRadio value="ultralytics">Ultralytics</ElRadio>
          </ElRadioGroup>
```

- [ ] **Step 2: `onFrameworkChange` 删 paddlex 分支**

`task/index.vue:375-380` 改为：

```typescript
function onFrameworkChange(fw: string | number | boolean | undefined) {
  const val = String(fw);
  Object.keys(hpForm).forEach(k => delete hpForm[k]);
  Object.assign(hpForm, {
    model: "yolo11n.pt", epochs: 100, batch: 16, lr0: 0.01, optimizer: "AdamW",
    imgsz: 640, workers: 4, device: "0", trainRatio: 80,
    lrf: 0.01, momentum: 0.937, weight_decay: 0.0005, patience: 100, seed: 0,
    hsv_h: 0.015, hsv_s: 0.7, hsv_v: 0.4, fliplr: 0.5, flipud: 0.0, mosaic: 1.0, mixup: 0.0,
    multi_label: false,
  });
}
```

- [ ] **Step 3: dockerCmdPreview 删 paddlex 分支**

`task/index.vue:392-400` 改为仅 ultralytics 预览（`@change="onFrameworkChange"` 保留但仅 ultralytics）。

- [ ] **Step 4: type-check + build**

Run: `cd D:/AIStation/frontend/web && pnpm run type-check`
Expected: 0 errors
Run: `cd D:/AIStation/frontend/web && npx vite build 2>&1 | Select-Object -Last 3`
Expected: `built in ...`

- [ ] **Step 5: 提交**

```bash
git add frontend/web/src/views/module_train/task/index.vue
git commit -m "feat(train): remove PaddleX from frontend framework options"
```

---

### Task 6: 端到端回归验证

**Files:**
- Test: 全量后端 + 前端

**Interfaces:**
- Consumes: Task 1-5 全部产物

- [ ] **Step 1: 后端全量测试**

Run: `cd D:/AIStation/backend && uv run pytest tests/ -v`
Expected: 全部通过

- [ ] **Step 2: ruff**

Run: `cd D:/AIStation/backend && uv run ruff check`
Expected: 无新增错误（既有 274 个历史错误不计）

- [ ] **Step 3: 前端 type-check + build**

Run: `cd D:/AIStation/frontend/web && pnpm run type-check && npx vite build 2>&1 | Select-Object -Last 3`
Expected: type-check 0 errors, build 成功

- [ ] **Step 4: 后端重启 + API 冒烟**

1. 重启后端（迁移/清理后）：`cd D:/AIStation/backend && uv run main.py run --env=dev`
2. 登录：`POST /api/v1/system/auth/login`（form admin/123456）→ 200 + token
3. `GET /api/v1/train/model/repos?page_no=1&page_size=5` → 200
4. `GET /api/v1/train/task/list?page_no=1&page_size=5` → 200（确认无 paddlex 框架残留）
5. `POST /api/v1/train/task/create` 带 `framework=paddlex` → 应被拒绝（报错）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_train/cleanup_paddlex_data.py
git commit -m "chore(train): regression verification after ultralytics enhancement"
```

---

## Self-Review 结论

- **Spec 覆盖**：组件 A（白名单）Task 1 ✅；组件 B（前端表单）Task 3 ✅；组件 C（多标签）Task 2 ✅；组件 D（PaddleX 移除）Task 4/5 ✅；测试 Task 6 ✅。
- **占位符扫描**：无 TBD/TODO（Task 4 的"检查 test_paddlex_export.py"是明确行动指令，非占位）。
- **类型一致性**：`_ULTRALYTICS_HP` key 集在 Task 1 定义、Task 3 前端 hpForm 使用；`lr0` 键统一；`multi_label` 在 Task 1 白名单 + Task 2 导出 + Task 3 前端一致。
- **遗留说明**：`_export_paddle_ocr`/`_export_paddle_mlcls` 保留（spec 规定，子项目 2 后删除）；`TrainFramework.PADDLEX` 枚举值保留。
