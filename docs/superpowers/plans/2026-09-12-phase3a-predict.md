# Phase 3A：批量预测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 PaddleX 预测参数全丢（多个 `-o`）、device/GPU 处理、结果存对象键并按需重签（不再存过期 URL）、删除预测清理对象存储、`start_prediction` 状态守卫。

**Architecture:** 抽出纯函数 `_build_predict_cmd(...)`/`predict_gpu_id(...)` 便于单测；结果 `result_images`/`result_zip_path` 存**对象键**，接口层 `sign_predict_results` 转为签名 URL（兼容历史已存 URL 的行）；`s3_client.delete_prefix` 清理。

**Tech Stack:** FastAPI + SQLAlchemy + boto3 + pytest。

## Global Constraints

- 后端 `D:\AIStation\backend`（`uv run pytest`/`uv run ruff check`，只判断新增）；中文注释；不新增依赖；提交 `fix(train): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- 测试不跑真实容器：monkeypatch docker/S3。
- 保持 Ultralytics 预测现有行为（除新增 `device=` 与结果键存储）。

---

### Task 1: PaddleX 预测命令修正 + device 处理

**背景:** `predict_executor._execute` 用 5 个独立 `-o`（`predict_executor.py:123-132`）→ PaddleOCR argparse（`nargs='+'`）只保留最后一个，`infer_img`/`pretrained_model`/`save_res_path`/`use_gpu`/`output_dir` 全丢；`Global.use_gpu=true` 硬编码；Ultralytics 命令不带 `device=`，而 `gpu_id=device` 在 `device="cpu"` 时把 "cpu" 当 GPU id 传 Docker → 报错。PaddleX rec 预测导出数据集未传 `ocr_rec`。

**Files:**
- Modify: `backend/app/plugin/module_train/predict_executor.py`
- Test: `backend/tests/test_predict_cmd.py`

**Interfaces:**
- Produces: `predict_gpu_id(device: str | None) -> str | None` —— `"cpu"`/空 → `None`；否则返回该值。
- Produces: `build_predict_cmd(framework: str, model_filename: str, hp: dict) -> list[str]` —— 按框架返回容器命令；PaddleX 用**单个 `-o`** + 空格分隔全部 opt。

- [ ] **Step 1: Write the failing test**

```python
"""预测命令与 GPU 处理测试。"""
from app.plugin.module_train.predict_executor import build_predict_cmd, predict_gpu_id


def test_predict_gpu_id():
    assert predict_gpu_id("cpu") is None
    assert predict_gpu_id("") is None
    assert predict_gpu_id(None) is None
    assert predict_gpu_id("0") == "0"


def test_paddlex_predict_single_dash_o():
    cmd = build_predict_cmd("paddlex", "best_accuracy.pdparams",
                            {"mode": "det", "model_size": "small", "device": "0"})
    assert cmd[0] == "bash" and cmd[1] == "-c"
    inner = cmd[2]
    assert inner.count(" -o ") == 1            # 只有一个 -o
    assert "Global.infer_img=/data" in inner
    assert "Global.pretrained_model=/model/best_accuracy.pdparams" in inner
    assert "Global.save_res_path=/output/results.txt" in inner
    assert "Global.output_dir=/output" in inner
    assert "PP-OCRv6_small_det.yml" in inner
    assert "use_gpu=false" in inner            # device=cpu 时不启用 GPU


def test_ultralytics_predict_has_device():
    cmd = build_predict_cmd("ultralytics", "best.pt", {"device": "cpu", "imgsz": 640})
    assert "device=cpu" in cmd
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_predict_cmd.py -q`
Expected: FAIL（函数不存在）。

- [ ] **Step 3: Implement**

`predict_executor.py`：
```python
def predict_gpu_id(device) -> str | None:
    """GPU 设备 id；cpu/空 → None（不请求 GPU）。"""
    if device is None:
        return None
    d = str(device).strip().lower()
    if d in ("", "cpu"):
        return None
    return str(device)


def build_predict_cmd(framework: str, model_filename: str, hp: dict) -> list[str]:
    """按框架构建预测命令。"""
    conf = hp.get("conf", 0.25)
    iou = hp.get("iou", 0.45)
    imgsz = hp.get("imgsz", 640)
    device = hp.get("device", "0")
    if str(framework).lower() == "paddlex":
        mode = str(hp.get("mode", "det")).lower()
        size = hp.get("model_size", "tiny")
        if size not in ("tiny", "small", "medium"):
            size = "tiny"
        if mode == "rec":
            cfg = f"configs/rec/PP-OCRv6/PP-OCRv6_{size}_rec.yml"
            infer = "tools/infer_rec.py"
        else:
            cfg = f"configs/det/PP-OCRv6/PP-OCRv6_{size}_det.yml"
            infer = "tools/infer_det.py"
        use_gpu = "true" if predict_gpu_id(device) is not None else "false"
        opts = [
            f"Global.infer_img=/data",
            f"Global.pretrained_model=/model/{model_filename}",
            f"Global.save_res_path=/output/results.txt",
            f"Global.use_gpu={use_gpu}",
            f"Global.output_dir=/output",
        ]
        inner = (
            "cd /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR && "
            f"python {infer} -c {cfg} -o " + " ".join(opts)
        )
        return ["bash", "-c", inner]
    return [
        "yolo", "predict",
        f"model=/model/{model_filename}",
        "source=/data",
        f"imgsz={imgsz}",
        f"conf={conf}",
        f"iou={iou}",
        f"device={device}",
        "save_txt=True", "save_conf=True",
        "project=/output", "name=exp",
    ]
```

`_execute` 中替换原命令构造为 `cmd = build_predict_cmd(framework.value, model_filename, hp)`；`gpu_id=predict_gpu_id(device)`；PaddleX 的 dataset 导出改为按 mode 传 `ocr_rec`：
```python
            if pred.source_type == "dataset":
                ocr_rec = (framework == TrainFramework.PADDLEX and str(hp.get("mode", "det")).lower() == "rec")
                await prepare_training_data_for_task(pred.source_dataset_id, predict_id, framework.value, source_dir, ocr_rec=ocr_rec)
```
（`hp` 需在导出前取到。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_predict_cmd.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/predict_executor.py`

```bash
git add backend/app/plugin/module_train/predict_executor.py backend/tests/test_predict_cmd.py
git commit -m "fix(train): PaddleX 预测单 -o 参数、device/cpu 处理、rec 数据导出"
```

---

### Task 2: 预测结果对象键存储 + 重签 + 清理 + 状态守卫

**背景:** `_execute` 把 presigned URL 存进 `result_images`/`result_zip_path`（`predict_executor.py:205,215`），1h 后详情图与下载永久 403；删除预测不清理 RustFS；`start_prediction` 无状态守卫。

**Files:**
- Modify: `backend/app/plugin/module_train/predict_executor.py`
- Modify: `backend/app/plugin/module_train/service.py`（`get_predict`/`list_predicts` 重签；`delete_predicts` 清理）
- Modify: `backend/app/utils/s3_client.py`（`delete_prefix`）
- Test: `backend/tests/test_predict_results.py`

**Interfaces:**
- Produces: `sign_predict_results(predict: dict) -> dict` —— 把 `result_images`/`result_zip_path` 中的**对象键**转签名 URL；已是 `http` 的值原样保留（兼容历史行）。
- Produces: `S3Client.delete_prefix(prefix: str, env: str | None = None) -> int` —— 删除该前缀下所有对象，返回数量。

- [ ] **Step 1: Write the failing test**

```python
"""预测结果重签与兼容性测试。"""
from app.plugin.module_train.service import sign_predict_results


def test_sign_converts_keys_preserves_urls(monkeypatch):
    seen = []
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url",
        lambda k, *a, **kw: seen.append(k) or f"https://signed/{k}",
    )
    row = {
        "result_images": ["train/predict/1/a.png", "https://old/url.png"],
        "result_zip_path": "train/predict/1/results.zip",
    }
    out = sign_predict_results(row)
    assert out["result_images"][0] == "https://signed/train/predict/1/a.png"
    assert out["result_images"][1] == "https://old/url.png"     # 历史 URL 保留
    assert out["result_zip_path"] == "https://signed/train/predict/1/results.zip"
    assert seen == ["train/predict/1/a.png", "train/predict/1/results.zip"]


def test_sign_handles_none():
    assert sign_predict_results({"result_images": None, "result_zip_path": None}) == {
        "result_images": None, "result_zip_path": None,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_predict_results.py -q`
Expected: FAIL（`sign_predict_results` 不存在）。

- [ ] **Step 3: Implement**

`s3_client.py`：
```python
    def delete_prefix(self, prefix: str, env: str | None = None) -> int:
        bucket = self._bucket(env)
        resp = self.client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        keys = [o["Key"] for o in resp.get("Contents", [])]
        for k in keys:
            self.client.delete_object(Bucket=bucket, Key=k)
        return len(keys)
```

`service.py` 新增纯函数（模块级）：
```python
def sign_predict_results(predict: dict) -> dict:
    """把预测结果中的对象键转为签名 URL；历史 URL 原样保留。"""
    from app.utils.s3_client import s3_client

    def _sign(v):
        if not v or not isinstance(v, str):
            return v
        return v if v.startswith(("http://", "https://")) else s3_client.presigned_url(v)

    if predict is None:
        return predict
    out = dict(predict)
    imgs = predict.get("result_images")
    out["result_images"] = [_sign(v) for v in imgs] if isinstance(imgs, list) else imgs
    out["result_zip_path"] = _sign(predict.get("result_zip_path"))
    return out
```
- `get_predict` 返回值经 `sign_predict_results`；`list_predicts` 的每行同样处理。
- `delete_predicts`：删行前对每个 id `s3_client.delete_prefix(f"train/predict/{id}/")`。
- `predict_executor._execute`：`result_images.append(rustfs_key)`（存键）、`result_zip_path = zip_rustfs_key`（存键）。
- `start_prediction` 守卫：
```python
    async with async_db_session.begin() as db:
        row = await db.get(TrainPredict, predict_id)
        if row and row.status == TrainStatus.RUNNING:
            raise Exception("预测任务正在运行，请勿重复启动")
        await db.execute(update(TrainPredict)...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_predict_results.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/predict_executor.py app/plugin/module_train/service.py app/utils/s3_client.py`

```bash
git add backend/app/plugin/module_train/predict_executor.py backend/app/plugin/module_train/service.py backend/app/utils/s3_client.py backend/tests/test_predict_results.py
git commit -m "fix(train): 预测结果存对象键并重签、删除清理、状态守卫"
```

---

## Self-Review

**Spec coverage（对照 Phase 3 spec 组件 A）:**
- PaddleX `-o` / device / rec 导出 → Task 1 ✅
- 结果对象键 + 重签 + 清理 → Task 2 ✅
- 状态守卫 → Task 2 ✅

**Placeholder scan:** 无 TBD；每步含完整代码。

**Type consistency:** `predict_gpu_id`/`build_predict_cmd`/`sign_predict_results`/`delete_prefix` 命名一致。

**风险:** `sign_predict_results` 需同时用于 detail 与 list；历史行已存 URL（保留）与新行存键（重签）共存，兼容逻辑已覆盖。真机验证：用 `ultralytics/ultralytics:latest` + 小数据集跑一次预测，确认出图与下载；PaddleX 用 `paddlex:latest` 跑 det/rec 预测确认 `-o` 生效。
