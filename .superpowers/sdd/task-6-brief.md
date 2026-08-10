### Task 6: 打通 paddlex 执行链路（训练→评估→预测→部署）

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py`（TrainExecutor._execute）
- Modify: `backend/app/plugin/module_train/eval_scheduler.py`（EvalExecutor._execute）
- Modify: `backend/app/plugin/module_train/predict_executor.py`（PredictExecutor._execute）
- Modify: `backend/app/plugin/module_train/exporter.py`（`_export_paddlex` 真正导出数据）
- Test: `backend/tests/test_paddlex_export.py`（新建）

**Interfaces:**
- Consumes: `TrainFramework.PADDLEX`, `_export_paddlex` 现有占位
- Produces: `_export_paddlex(dataset_id, task_id, images, output_dir, annotation_task_id)` 完整实现；paddlex 的 eval/predict 命令构造

- [ ] **Step 1: 写失败测试 — paddlex 导出生成 PaddleX 数据**

`backend/tests/test_paddlex_export.py`:

```python
"""PaddleX 数据集导出测试（验证不再空实现）。"""


def test_export_paddlex_is_implemented():
    import inspect
    from app.plugin.module_train.exporter import _export_paddlex
    src = inspect.getsource(_export_paddlex)
    # 原实现只有 mkdir + log；修复后应有 label 或 yaml 生成
    assert "yaml" in src.lower() or "label" in src.lower() or "json" in src.lower()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_paddlex_export.py -v`
Expected: FAIL（当前 `_export_paddlex` 只有 mkdir + log）

- [ ] **Step 3: 实现 `_export_paddlex` 完整导出**

在 `exporter.py` 中替换 `_export_paddlex`：

```python
async def _export_paddlex(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None) -> None:
    """导出 PaddleX 检测格式：images/ + annotations/ (XML) + train/val 划分 + PaddleX 目录规范。

    PaddleX 3.0 期望目录结构：
      {output}/images/{img}
      {output}/annotations/{img}.xml
      {output}/train.txt / val.txt
    """
    import random
    import xml.etree.ElementTree as ET

    from app.utils.s3_client import s3_client

    random.shuffle(images)
    split_idx = max(1, int(len(images) * 0.8))
    img_dir = os.path.join(output_dir, "images")
    ann_dir = os.path.join(output_dir, "annotations")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(ann_dir, exist_ok=True)

    train_lines: list[str] = []
    val_lines: list[str] = []
    classes: set[str] = set()

    async with async_db_session() as db:
        for idx, img in enumerate(images):
            img_path = os.path.join(img_dir, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning(f"skip image {img.filename}: {e}")
                    continue

            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            # 构造 PaddleX XML
            root = ET.Element("annotation")
            ET.SubElement(root, "filename").text = img.filename
            size = ET.SubElement(root, "size")
            ET.SubElement(size, "width").text = str(img.width or 0)
            ET.SubElement(size, "height").text = str(img.height or 0)
            for ann in anns:
                if ann.get("type") not in ("AxisAlignedBox", "box"):
                    continue
                if "x1" in ann:
                    x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                else:
                    xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                    x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
                obj = ET.SubElement(root, "object")
                ET.SubElement(obj, "name").text = f"class_{ann.get('class_id', 0)}"
                ET.SubElement(obj, "difficult").text = "0"
                bbox = ET.SubElement(obj, "bndbox")
                ET.SubElement(bbox, "xmin").text = f"{int(x1 * (img.width or 1))}"
                ET.SubElement(bbox, "ymin").text = f"{int(y1 * (img.height or 1))}"
                ET.SubElement(bbox, "xmax").text = f"{int(x2 * (img.width or 1))}"
                ET.SubElement(bbox, "ymax").text = f"{int(y2 * (img.height or 1))}"
                classes.add(f"class_{ann.get('class_id', 0)}")

            xml_path = os.path.join(ann_dir, os.path.splitext(img.filename)[0] + ".xml")
            tree = ET.ElementTree(root)
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)

            rel = f"images/{img.filename}\tannotations/{os.path.splitext(img.filename)[0]}.xml"
            if idx < split_idx:
                train_lines.append(rel)
            else:
                val_lines.append(rel)

    with open(os.path.join(output_dir, "train.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(train_lines))
    with open(os.path.join(output_dir, "val.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(val_lines))
    with open(os.path.join(output_dir, "labels.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(classes)))
    log.info(f"paddlex: train={len(train_lines)} val={len(val_lines)} classes={sorted(classes)}")
```

- [ ] **Step 4: paddlex 训练命令与产物查找修正**

`scheduler.py`（TrainExecutor）中：

```python
        if task.framework == TrainFramework.ULTRALYTICS:
            cmd = _build_ultralytics_cmd(...)
        elif task.framework == TrainFramework.PADDLEX:
            # PaddleX 训练需挂载导出目录并执行训练
            cmd = [
                "paddlex", "--train", "--data", "/data",
                "--model", task.hyperparams.get("model", "PP-YOLOE"),
                "--epochs", str(task.hyperparams.get("epochs", 100)),
                "--batch", str(task.hyperparams.get("batch", 16)),
                "--output", "/output",
            ]
```

`exporter.py:export_model` 扩展 paddlex 产物搜索（`best.pdparams` 已支持，补充 PaddleX 输出路径变体）：

```python
    if framework == "paddlex":
        candidates = [
            os.path.join(export_dir, "output", "best_model", "model.pdparams"),
            os.path.join(export_dir, "best_model", "model.pdparams"),
            os.path.join(export_dir, "exp", "best_model", "model.pdparams"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                best_path = p
                break
```

- [ ] **Step 5: paddlex 评估/预测命令分支**

`eval_scheduler.py`（EvalExecutor）按 `framework` 分支：

```python
        if eval_rec.framework == TrainFramework.ULTRALYTICS:
            cmd = ["yolo", "val", ...]
        else:
            cmd = ["paddlex", "--eval", f"--model=/model/{model_filename}", "data=/data", ...]
```

`predict_executor.py`（PredictExecutor）同理按框架构造命令。

- [ ] **Step 6: 运行测试**

Run: `cd backend && uv run pytest tests/test_paddlex_export.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/eval_scheduler.py backend/app/plugin/module_train/predict_executor.py backend/app/plugin/module_train/exporter.py backend/tests/test_paddlex_export.py
git commit -m "feat(train): implement PaddleX training/eval/predict pipeline"
```

---


