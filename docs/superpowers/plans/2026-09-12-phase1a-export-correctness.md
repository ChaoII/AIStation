# Phase 1A：数据集导出格式正确性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `backend/app/plugin/module_train/exporter.py` 的导出数据损坏问题：类 id 越界、YOLO OBB 非法、pose YAML 缺字段、X-AnyLabeling 写了归一化坐标/丢形状/丢类名、PaddleOCR det 与 rec 不能并存。

**Architecture:** 把导出中的"坐标/形状/类名转换"抽成**纯函数**（无 S3/DB 依赖），用单元测试锁定正确性；`_export_*` 负责 IO 编排。每个 task 独立可测。

**Tech Stack:** Python 3.13 + pytest；坐标约定：**工作台标注坐标为归一化值 [0,1]**（已在导出代码中体现：PaddleOCR 乘以 width/height，YOLO 直接用归一化值）。

## Global Constraints

- 命令在 `D:\AIStation\backend` 下执行：`uv run pytest`、`uv run ruff check`。只判断**新增** ruff 问题。
- 遵循现有中文 docstring/注释风格。不新增依赖。不改动无关文件。
- 提交信息风格 `fix(export): 中文描述`；只 `git add` 本任务文件（禁止 `git add -A`）。
- ruff 配置 `fix = true`：提交前 `git status`，若 ruff 自动改了无关文件则 `git checkout -- <file>`。
- 标注数据键约定（导出器现存用法，勿改）：
  - `AxisAlignedBox`: `{x1,y1,x2,y2}` 或 `{x,y,width,height}`（归一化）
  - `RotatedBox`: `{cx,cy,width,height,angle}`（归一化；`angle` 为弧度）
  - `Polygon`: `{points:[{x,y},...]}`（归一化）
  - `Keypoint`: `{bounding_box:{cx,cy,width,height}, keypoints:[{x,y,visibility}]}`（归一化）
  - `Ocr`: `{points:[{x,y},...], text}`（归一化）
  - `Classification`: `{class_ids:[...]}` 或 `{class_id}`
  - 类名来源：`AnnotationTaskModel.classes = [{"id":int,"name":str},...]`

---

### Task 1: 连续类 id 映射 + YAML names 正确

**背景:** `_export_yolo` 用 `classes: set[int]` 收集原始 `class_id` 并直接写 `nc=len(classes)`、`names`，但标签行里仍写原始 id。当类别被删过（id 稀疏，如只用了 2 与 5）时，`nc=2` 而标签出现 `5` → YOLO 报越界/错配。

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_export_yolo_classmap.py`

**Interfaces:**
- Produces: `build_class_mapping(class_ids: set[int]) -> dict[int, int]` —— 把出现的类 id 按升序映射为 `0..n-1`。
- Produces: `_write_yaml(path, base_path, sorted_classes, class_names, class_id_map=None, extra_yaml: dict | None = None)` —— 写 `nc`/`names`；`names` 使用**映射后**的连续下标，名称取 `class_names[原始id]`。

- [ ] **Step 1: Write the failing test**

```python
"""YOLO 导出类 id 连续化测试。"""
from app.plugin.module_train.exporter import build_class_mapping, _write_yaml


def test_build_class_mapping_contiguous():
    assert build_class_mapping({2, 5, 7}) == {2: 0, 5: 1, 7: 2}


def test_build_class_mapping_empty():
    assert build_class_mapping(set()) == {}


def test_write_yaml_uses_mapped_names(tmp_path):
    path = tmp_path / "dataset.yaml"
    _write_yaml(
        str(path),
        "/data",
        [0, 1],
        {2: "cat", 5: "dog"},
        class_id_map={2: 0, 5: 1},
    )
    text = path.read_text(encoding="utf-8")
    assert "nc: 2" in text
    assert '"0": "cat"' in text
    assert '"1": "dog"' in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_export_yolo_classmap.py -q`
Expected: FAIL（`ImportError: cannot import name 'build_class_mapping'`）

- [ ] **Step 3: Write minimal implementation**

在 `exporter.py` 中新增/修改：

```python
def build_class_mapping(class_ids: set[int]) -> dict[int, int]:
    """把稀疏的原始类 id 映射为连续 0..n-1（按原始 id 升序）。"""
    return {raw: idx for idx, raw in enumerate(sorted(class_ids))}
```

修改 `_write_yaml` 签名与实现：

```python
def _write_yaml(
    path: str,
    base_path: str,
    sorted_classes: list,
    class_names: dict,
    class_id_map: dict[int, int] | None = None,
    extra_yaml: dict | None = None,
) -> None:
    """Write dataset.yaml.

    sorted_classes 为**映射后**的连续下标列表；class_id_map 用于把下标回指原始
    id 以取真实名称（不传时按下标直接取）。
    """
    names_dict: dict[str, str] = {}
    for out_id in sorted_classes:
        raw_id = out_id
        if class_id_map:
            for raw, mapped in class_id_map.items():
                if mapped == out_id:
                    raw_id = raw
                    break
        names_dict[str(out_id)] = class_names.get(raw_id, str(out_id))
    with open(path, "w") as f:
        f.write(f"path: {base_path}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(sorted_classes)}\n")
        f.write(f"names: {json.dumps(names_dict, ensure_ascii=False)}\n")
        for k, v in (extra_yaml or {}).items():
            f.write(f"{k}: {v}\n")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_export_yolo_classmap.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 两遍式改写 `_export_yolo`**

把 `_export_yolo` 改为：先收集所有图片的最新标注、确定全局类 id 集合与映射，再下载图片并按映射写标签。参考实现：

```python
async def _export_yolo(dataset_id, task_id, images, output_dir, task_type="detection",
                       annotation_task_id=None, train_ratio=0.8, class_names=None,
                       for_training=False) -> None:
    import random

    from app.utils.s3_client import s3_client

    anns_by_img: dict[int, list] = {}
    used_ids: set[int] = set()
    async with async_db_session() as db:
        for img in images:
            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            record = (await db.execute(query)).scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []
            anns_by_img[img.id] = anns
            for ann in anns:
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    used_ids.add(int(cid))

    class_id_map = build_class_mapping(used_ids)

    random.shuffle(images)
    split_idx = max(1, int(len(images) * train_ratio))
    train_imgs = images[:split_idx]
    val_imgs = images[split_idx:]

    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        label_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(label_split, exist_ok=True)
        for img in split_imgs:
            img_path = os.path.join(img_split, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning(f"skip {img.filename}: {e}")
                    continue
            anns = anns_by_img.get(img.id, [])
            lines = _format_yolo_lines(anns, task_type, class_id_map=class_id_map,
                                       img_w=img.width or 1, img_h=img.height or 1)
            if lines:
                label_path = os.path.join(label_split,
                                          img.filename.rsplit(".", 1)[0] + ".txt")
                with open(label_path, "w") as f:
                    f.write("\n".join(lines))

    base_path = "/data" if for_training else "."
    sorted_out = list(range(len(class_id_map)))
    _write_yaml(os.path.join(output_dir, "dataset.yaml"), base_path, sorted_out,
                class_names or {}, class_id_map=class_id_map)
    log.info(f"yolo: train={len(train_imgs)} val={len(val_imgs)} classes={len(sorted_out)} → {output_dir}")
```

- [ ] **Step 6: `_format_yolo_lines` 应用映射**

修改 `_format_yolo_lines(anns, task_type, class_id_map=None, img_w=1, img_h=1)`：把 `cls_id = ann.get("class_id", 0)` 改为经映射：

```python
        raw_cls = ann.get("class_id", 0)
        cls_id = (class_id_map or {}).get(raw_cls, raw_cls)
```

（Task 3 会用到 `img_w/img_h`。此步先让签名就位，其余保持。）

- [ ] **Step 7: 全量测试 + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/exporter.py`
Expected: 通过（既有 YOLO 导出测试可能需同步映射预期；若失败且是"测试假设旧行为"，修正断言并在报告说明）。

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_export_yolo_classmap.py
git commit -m "fix(export): YOLO 类 id 连续化映射，修正 nc/names 越界"
```

---

### Task 2: YOLO OBB 合法 8 点格式

**背景:** `_format_yolo_lines` 对 `RotatedBox` 写 `cls cx cy w h angle`（6 值），YOLO OBB 要求 8 个归一化坐标点；且 `rotated_detection` 分支对 `AxisAlignedBox` 写的是轴对齐 8 点（正确），但 `RotatedBox` 分支非法。角度"弧度→度"用 `abs(ang)>3.0` 猜测也不可靠。

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_export_yolo_obb.py`

**Interfaces:**
- Produces: `rotated_box_to_obb_corners(cx, cy, w, h, angle_rad) -> list[float]` —— 返回 8 个归一化坐标 `[x1,y1,x2,y2,x3,y3,x4,y4]`（顺序：左上→右上→右下→左下）。

- [ ] **Step 1: Write the failing test**

```python
"""YOLO OBB 旋转框转换测试。"""
import math

from app.plugin.module_train.exporter import rotated_box_to_obb_corners


def test_obb_corners_zero_angle():
    pts = rotated_box_to_obb_corners(0.5, 0.5, 0.4, 0.2, 0.0)
    assert len(pts) == 8
    # 左上→右上→右下→左下
    assert pts[0] == 0.3 and pts[1] == 0.4
    assert pts[2] == 0.7 and pts[3] == 0.4
    assert pts[4] == 0.7 and pts[5] == 0.6
    assert pts[6] == 0.3 and pts[7] == 0.6


def test_obb_corners_90deg_swap_extent():
    pts = rotated_box_to_obb_corners(0.5, 0.5, 0.4, 0.2, math.pi / 2)
    assert len(pts) == 8
    # 旋转 90° 后，宽高在坐标轴上互换
    assert abs(pts[0] - 0.4) < 1e-6 and abs(pts[1] - 0.3) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_export_yolo_obb.py -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: Write minimal implementation**

```python
def rotated_box_to_obb_corners(cx: float, cy: float, w: float, h: float,
                               angle_rad: float) -> list[float]:
    """归一化旋转框 → YOLO OBB 8 点（左上→右上→右下→左下）。"""
    import math

    hw, hh = w / 2.0, h / 2.0
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    out: list[float] = []
    for dx, dy in local:
        out.append(cx + dx * cos_a - dy * sin_a)
        out.append(cy + dx * sin_a + dy * cos_a)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_export_yolo_obb.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 改 `_format_yolo_lines` 的 OBB 分支**

把 `elif ann_type in ("RotatedBox", "rotated_box"):` 分支改为（`task_type` 为 `rotated_detection`/`obb` 时用 8 点；否则退化为中心点+宽高+度，供非 OBB 使用）：

```python
        elif ann_type in ("RotatedBox", "rotated_box"):
            cx, cy = ann["cx"], ann["cy"]
            w, h = ann["width"], ann["height"]
            ang = float(ann.get("angle", 0) or 0)
            if task_type in ("rotated_detection", "obb"):
                pts = rotated_box_to_obb_corners(cx, cy, w, h, ang)
                lines.append(f"{cls_id} " + " ".join(f"{v:.6f}" for v in pts))
            else:
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f} {math.degrees(ang):.6f}")
```

并在文件顶部 `import math`。

- [ ] **Step 6: 全量测试 + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/exporter.py`
Expected: 通过。

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_export_yolo_obb.py
git commit -m "fix(export): YOLO OBB 输出合法 8 点坐标"
```

---

### Task 3: YOLO Pose 的 dataset.yaml 补 kpt_shape/flip_idx

**背景:** `_write_yaml` 不写 `kpt_shape`/`flip_idx`，Ultralytics pose 训练会拒绝/误读关键点。`_export_yolo` 需在 `task_type in ("keypoint","pose")` 时传入。

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_export_yolo_pose_yaml.py`

**Interfaces:**
- Produces: `pose_extra_yaml(anns_by_img: dict[int, list]) -> dict` —— 从关键点数量推断 `{"kpt_shape": "[K, 3]", "flip_idx": "[...]"}`（无关键点返回 `{}`）。

- [ ] **Step 1: Write the failing test**

```python
"""YOLO Pose YAML 额外字段测试。"""
from app.plugin.module_train.exporter import pose_extra_yaml


def test_pose_extra_yaml_from_annotations():
    anns = {1: [{"type": "Keypoint", "keypoints": [{"x": 0.1, "y": 0.1, "visibility": "Visible"}] * 4}]}
    extra = pose_extra_yaml(anns)
    assert extra["kpt_shape"] == "[4, 3]"
    assert extra["flip_idx"] == "[0, 1, 2, 3]"


def test_pose_extra_yaml_empty_when_no_keypoints():
    assert pose_extra_yaml({1: [{"type": "AxisAlignedBox"}]}) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_export_yolo_pose_yaml.py -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: Write minimal implementation**

```python
def pose_extra_yaml(anns_by_img: dict[int, list]) -> dict:
    """当存在关键点标注时，返回 pose 训练所需的 kpt_shape / flip_idx。"""
    k = 0
    for anns in anns_by_img.values():
        for ann in anns:
            if ann.get("type") in ("Keypoint", "keypoint"):
                k = max(k, len(ann.get("keypoints", [])))
    if k <= 0:
        return {}
    return {"kpt_shape": f"[{k}, 3]", "flip_idx": "[" + ", ".join(str(i) for i in range(k)) + "]"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_export_yolo_pose_yaml.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 在 `_export_yolo` 中传入 extra_yaml**

在 `_export_yolo` 末尾计算：

```python
    extra = pose_extra_yaml(anns_by_img) if task_type in ("keypoint", "pose") else None
```

并把 `_write_yaml(...)` 调用补上 `extra_yaml=extra`。

- [ ] **Step 6: 全量测试 + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/exporter.py`

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_export_yolo_pose_yaml.py
git commit -m "fix(export): YOLO pose 补 kpt_shape/flip_idx"
```

---

### Task 4: X-AnyLabeling 导出像素坐标 + 全形状 + 真实类名

**背景:** `_export_x_anylabeling` 直接写归一化坐标（应为像素）、只处理 AxisAlignedBox/Polygon（RotatedBox/Keypoint/Ocr/Classification 全丢）、label 回退 `class_N`（真实类名丢失）。

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_export_xanylabeling.py`

**Interfaces:**
- Produces: `xany_shapes(anns: list, img_w: int, img_h: int, class_names: dict[int, str]) -> list[dict]` —— 返回 LabelMe shapes；坐标像素化；类名取 `class_names[class_id]`（缺省 `class_{id}`）。

- [ ] **Step 1: Write the failing test**

```python
"""X-AnyLabeling shapes 转换测试（归一化→像素、全形状、真实类名）。"""
from app.plugin.module_train.exporter import xany_shapes


def test_rectangle_pixelized_and_named():
    anns = [{"type": "AxisAlignedBox", "class_id": 2, "x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.6}]
    shapes = xany_shapes(anns, 100, 200, {2: "cat"})
    assert shapes[0]["label"] == "cat"
    assert shapes[0]["shape_type"] == "rectangle"
    assert shapes[0]["points"][0] == [10.0, 40.0]
    assert shapes[0]["points"][2] == [40.0, 120.0]


def test_rotated_box_pixelized():
    anns = [{"type": "RotatedBox", "class_id": 1, "cx": 0.5, "cy": 0.5, "width": 0.2, "height": 0.1, "angle": 0.0}]
    shapes = xany_shapes(anns, 100, 100, {1: "box"})
    assert shapes[0]["shape_type"] == "rotation"
    xs = [p[0] for p in shapes[0]["points"]]
    ys = [p[1] for p in shapes[0]["points"]]
    assert min(xs) == 40.0 and max(xs) == 60.0
    assert min(ys) == 45.0 and max(ys) == 55.0


def test_keypoint_and_ocr_and_polygon_present():
    anns = [
        {"type": "Polygon", "class_id": 0, "points": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.1}, {"x": 0.2, "y": 0.2}]},
        {"type": "Keypoint", "class_id": 1, "keypoints": [{"x": 0.5, "y": 0.5, "visibility": "Visible"}]},
        {"type": "Ocr", "class_id": 2, "points": [{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.1}, {"x": 0.3, "y": 0.2}, {"x": 0.1, "y": 0.2}], "text": "hi"},
    ]
    shapes = xany_shapes(anns, 100, 100, {0: "a", 1: "b", 2: "c"})
    types = {s["shape_type"] for s in shapes}
    assert "polygon" in types
    assert "point" in types
    assert any(s.get("description") == "hi" for s in shapes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_export_xanylabeling.py -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: Write minimal implementation**

```python
def _px(v: float, scale: int) -> float:
    return round(float(v) * scale, 4)


def xany_shapes(anns: list, img_w: int, img_h: int, class_names: dict[int, str]) -> list[dict]:
    """工作台归一化标注 → LabelMe/x-anylabeling shapes（像素坐标）。"""
    shapes: list[dict] = []
    for ann in anns:
        cid = ann.get("class_id", 0)
        label = class_names.get(cid, f"class_{cid}")
        base = {"label": label, "group_id": None, "flags": {}}
        t = ann.get("type", "")
        if t in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
            pts = [[_px(x1, img_w), _px(y1, img_h)], [_px(x2, img_w), _px(y1, img_h)],
                   [_px(x2, img_w), _px(y2, img_h)], [_px(x1, img_w), _px(y2, img_h)]]
            shapes.append({**base, "points": pts, "shape_type": "rectangle"})
        elif t in ("RotatedBox", "rotated_box"):
            from app.plugin.module_train.exporter import rotated_box_to_obb_corners
            flat = rotated_box_to_obb_corners(ann["cx"], ann["cy"], ann["width"], ann["height"],
                                              float(ann.get("angle", 0) or 0))
            pts = [[_px(flat[i], img_w), _px(flat[i + 1], img_h)] for i in range(0, 8, 2)]
            shapes.append({**base, "points": pts, "shape_type": "rotation"})
        elif t in ("Polygon", "polygon"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 3:
                shapes.append({**base, "points": pts, "shape_type": "polygon"})
        elif t in ("Keypoint", "keypoint"):
            for kp in ann.get("keypoints", []):
                shapes.append({**base,
                               "points": [[_px(kp.get("x", 0), img_w), _px(kp.get("y", 0), img_h)]],
                               "shape_type": "point"})
        elif t in ("Ocr", "ocr"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 3:
                shapes.append({**base, "points": pts, "shape_type": "polygon",
                               "description": ann.get("text", "")})
    return shapes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_export_xanylabeling.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: `_export_x_anylabeling` 使用 `xany_shapes` 并传类名**

- 函数签名增加 `class_names: dict | None = None`；调用方 `_export_core` 的 `x-anylabeling` 分支传 `class_names=class_names`。
- 把内联 shapes 构造替换为 `shapes = xany_shapes(anns, img.width or 0, img.height or 0, class_names or {})`。

- [ ] **Step 6: 全量测试 + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/exporter.py`

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_export_xanylabeling.py
git commit -m "fix(export): X-AnyLabeling 像素坐标/全形状/真实类名"
```

---

### Task 5: PaddleOCR det+rec 可同时导出 + 官方词表 + 矩形纳入 det

**背景:** 当前 `_export_paddle_ocr` 以 `export_rec` 二选一导出；det 只认 polygon/ocr（漏 AxisAlignedBox）；rec 的 `dict.txt` 从数据字符集推断而不是官方 `ppocrv6_dict`（与预训练权重不匹配）。

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_export_paddle_ocr.py`

**Interfaces:**
- Produces: `paddle_ocr_det_entries(anns: list, img_w: int, img_h: int, text_by_ann: dict | None = None) -> list[dict]` —— 把 AxisAlignedBox/Polygon/Ocr 统一为 `{"transcription","points"}[]`（像素 4 点）。
- 行为：当 `ocr_rec=False`（det 模式）只输出 det；`ocr_rec=True` 时**同时**输出 `det/dataset` 与 `rec/dataset`。

- [ ] **Step 1: Write the failing test**

```python
"""PaddleOCR det 条目转换测试（矩形纳入 det）。"""
from app.plugin.module_train.exporter import paddle_ocr_det_entries


def test_det_entries_include_axis_aligned_box():
    anns = [{"type": "AxisAlignedBox", "class_id": 0, "x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.5, "text": "abc"}]
    entries = paddle_ocr_det_entries(anns, 100, 100)
    assert len(entries) == 1
    assert entries[0]["transcription"] == "abc"
    pts = entries[0]["points"]
    assert pts == [[10.0, 20.0], [40.0, 20.0], [40.0, 50.0], [10.0, 50.0]]


def test_det_entries_polygon_and_ocr():
    anns = [
        {"type": "Polygon", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.1}, {"x": 0.3, "y": 0.2}, {"x": 0.1, "y": 0.2}], "text": "p"},
        {"type": "Ocr", "points": [{"x": 0.5, "y": 0.5}, {"x": 0.7, "y": 0.5}, {"x": 0.7, "y": 0.6}, {"x": 0.5, "y": 0.6}], "text": "o"},
    ]
    entries = paddle_ocr_det_entries(anns, 100, 100)
    assert len(entries) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_export_paddle_ocr.py -q`
Expected: FAIL（ImportError）

- [ ] **Step 3: Write minimal implementation**

```python
def paddle_ocr_det_entries(anns: list, img_w: int, img_h: int,
                           text_by_ann: dict | None = None) -> list[dict]:
    """把矩形/多边形/OCR 标注统一成 PaddleOCR det 条目（像素 4 点）。"""
    entries: list[dict] = []
    for ann in anns:
        t = ann.get("type", "")
        text = ann.get("text", "") or ""
        if t in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
            points = [[x1 * img_w, y1 * img_h], [x2 * img_w, y1 * img_h],
                      [x2 * img_w, y2 * img_h], [x1 * img_w, y2 * img_h]]
        elif t in ("Polygon", "polygon", "Ocr", "ocr"):
            pts = ann.get("points", [])
            if len(pts) < 4:
                continue
            points = [[(p["x"] if isinstance(p, dict) else p[0]) * img_w,
                       (p["y"] if isinstance(p, dict) else p[1]) * img_h] for p in pts[:4]]
        else:
            continue
        entries.append({"transcription": text, "points": points})
    return entries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_export_paddle_ocr.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 改造 `_export_paddle_ocr` 支持 det+rec 并存**

把 `_export_paddle_ocr` 改为：无论 `export_rec` 真假都写 det；`export_rec=True` 追加 rec。要点：
- 用 `paddle_ocr_det_entries(anns, w, h)` 生成 det 条目（替代原只认 polygon/ocr 的循环）。
- 保留 rec 裁剪逻辑；rec 的 `dict.txt` 改为写官方词表路径的**拷贝来源**：优先从环境读取官方 `ppocrv6_dict.txt`（如 `backend/app/plugin/module_train/assets/ppocrv6_dict.txt` 若存在），否则退化为数据字符集，并 `log.warning` 明确提示词表非官方。
- 目录：det → `<output>/det/dataset`，rec → `<output>/rec/dataset`。

（此步代码较长，按上述要点改写；若官方词表文件仓库中不存在，请在报告中明确记录并只做"退化为字符集 + warning"。）

- [ ] **Step 6: 全量测试 + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/exporter.py`

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_export_paddle_ocr.py
git commit -m "fix(export): PaddleOCR det+rec 并存、矩形纳入 det、官方词表优先"
```

---

## Self-Review

**Spec coverage（对照 Phase 1 spec 组件 C）:**
- 类 id 连续化 → Task 1 ✅
- YOLO OBB 合法格式 → Task 2 ✅
- pose YAML kpt_shape/flip_idx → Task 3 ✅
- X-AnyLabeling 像素/全形状/类名 → Task 4 ✅
- PaddleOCR det+rec 并存 / 矩形纳入 det / 官方词表 → Task 5 ✅

**Placeholder scan:** 无 TBD；每步含完整代码或明确改写要点。Task 5 Step 5 因改动面大给了要点式说明，其余为完整代码。

**Type consistency:** `build_class_mapping`、`rotated_box_to_obb_corners`、`pose_extra_yaml`、`xany_shapes`、`paddle_ocr_det_entries` 命名在定义/使用/测试处一致；`_write_yaml`/`_format_yolo_lines` 新增参数均有默认值，向后兼容。

**风险:** Task 1 改写 `_export_yolo` 为两遍式，可能影响既有导出测试的期望（如按原始 id 断言）；按 Step 7 说明修正为映射后断言，不得回退修复。Task 5 官方词表文件可能在仓库中不存在，需按 Step 5 明确退化并记录。
