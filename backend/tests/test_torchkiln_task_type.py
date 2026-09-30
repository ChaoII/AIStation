"""TorchKiln 训练通路的任务类型对齐守卫。

为什么需要这个文件：``task_type`` 曾经有**两个来源**——后端读
``hyperparams.task_type``（由前端按**模型**的 ``task`` 字段填写），而白名单的
语义说明、前端过滤、导出格式分派说的其实都是**标注任务类型**。两边对不上时
**不会报错，只会静默产出坏数据**：

  - 模型 ``task=classify`` / ``task=obb`` 不在白名单 -> 选得了却提交不了，
    而导出器其实早就支持旋转框 9 字段角点；
  - 模型 ``task=segment`` 恰好在白名单，但 ``export_framework`` 被拼成
    ``yolo-segment``，格式器只认 ``segmentation``/``seg`` ->
    **标签文件全空**，训练照常跑完却学的是空数据集；
  - OCR 模型 yml 的 ``task`` 字段为空 -> 退化成 ``detection`` -> ``ocr_rec``
    恒 False -> **rec 按 det 的清单导出，数据语义全错**。

本文件钉住三件事，任何一件被改坏都会立刻红：

1. 前后端白名单**逐条一致**（且成员都是 ``AnnotationType`` 的裸值）；
2. ``_task_type`` 取**标注任务类型**，忽略模型 task；
3. 每个「需要 YOLO 文本标签」的支持类型，格式器都产出**非空**行。
"""
import asyncio
import re
from pathlib import Path

from app.api.v1.module_annotation.dataset.model import AnnotationType
from app.plugin.module_train.exporter import _format_yolo_lines
from app.plugin.module_train.torchkiln_executor import TorchKilnExecutor

FRONTEND_LIST = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "views" / "module_train" / "task" / "index.vue"
)
FRONTEND_EXPORT_MAP = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "views" / "module_annotation" / "dataset" / "index.vue"
)


def _frontend_tk_types() -> set[str]:
    """从前端源码里抠出 TK_SUPPORTED_TASK_TYPES 的字符串成员（剔除注释）。"""
    text = FRONTEND_LIST.read_text(encoding="utf-8")
    m = re.search(r"const TK_SUPPORTED_TASK_TYPES\s*=\s*\[(.*?)\]", text, re.S)
    assert m, "找不到 TK_SUPPORTED_TASK_TYPES，前端白名单可能改名了"
    body = "\n".join(line.split("//")[0] for line in m.group(1).splitlines())
    return set(re.findall(r'"([a-z_]+)"', body))


def test_front_and_back_whitelists_match():
    """前端下拉过滤与后端兜底拦截必须逐条一致，否则会出现「选得了提交不了」。"""
    front = _frontend_tk_types()
    back = set(TorchKilnExecutor.SUPPORTED_TASK_TYPES)
    assert front == back, (
        "前后端 TorchKiln 任务白名单漂移："
        f"前端独有 {sorted(front - back)}，后端独有 {sorted(back - front)}"
    )


def test_whitelist_is_annotation_type_subset():
    """白名单成员必须是 AnnotationType 裸值——它是按标注任务类型校验的。"""
    valid = {t.value for t in AnnotationType}
    bad = set(TorchKilnExecutor.SUPPORTED_TASK_TYPES) - valid
    assert not bad, f"白名单含非 AnnotationType 的值（会永远匹配不上）: {sorted(bad)}"


def _frontend_torchkiln_export_types() -> set[str]:
    """从数据集导出页 ``FORMAT_TASK_MAP`` 里抠出 ``torchkiln-<任务类型>`` 的类型集合。"""
    text = FRONTEND_EXPORT_MAP.read_text(encoding="utf-8")
    m = re.search(r"FORMAT_TASK_MAP[^=]*=\s*\{(.*?)\n\};", text, re.S)
    assert m, "找不到 FORMAT_TASK_MAP，前端数据集导出页可能改名了"
    body = "\n".join(line.split("//")[0] for line in m.group(1).splitlines())
    return set(re.findall(r'"torchkiln-([a-z_]+)"', body))


def test_dataset_export_covers_all_torchkiln_task_types():
    """数据集下载导出必须覆盖 TorchKiln 支持的**每一种**任务类型。

    少任何一种，用户就导不出该任务能直接喂给 TorchKiln 的数据——导出的目录
    缺 ``train.txt`` / ``val.txt`` 清单，而 TorchKiln 侧读到空清单不会报错，
    只是训练时按 0 个样本走，排查起来毫无线索。
    """
    back = set(TorchKilnExecutor.SUPPORTED_TASK_TYPES)
    front = _frontend_torchkiln_export_types()
    assert front == back, (
        "数据集导出的 torchkiln-* 格式与训练白名单不一致："
        f"缺少 {sorted(back - front)}，多余 {sorted(front - back)}"
    )


def test_task_type_reads_annotation_task_not_model_task(monkeypatch):
    """``_task_type`` 必须取标注任务类型，忽略 hyperparams.task_type（模型 task）。"""

    async def fake_resolve(task):
        return "segmentation"

    monkeypatch.setattr(
        "app.plugin.module_train.scheduler._resolve_task_type", fake_resolve)

    class _Task:
        # 模拟模型 task=segment：老实现会返回 "segment"，导致拼出 yolo-segment
        # 并最终导出空标签
        hyperparams = {"task_type": "segment", "model": "yolo11-seg"}
        annotation_task_id = 7

    got = asyncio.run(TorchKilnExecutor._task_type(_Task()))
    assert got == "segmentation", f"应取标注任务类型，实际 {got!r}"


# --------------------------------------------------------------- 空标签守卫
#: 走 `_format_yolo_lines`（YOLO 文本标签）的支持类型 -> 对应形状的样例标注。
#: 其余支持类型各有专用导出器（semantic/yolo_cls/torchkiln_ocr/video_detection/
#: mono3d），不经此函数，故不在表内。
_YOLO_TEXT_SAMPLES = {
    "detection": {
        "type": "AxisAlignedBox", "class_id": 1,
        "x1": 0.10, "y1": 0.10, "x2": 0.50, "y2": 0.60,
    },
    "rotated_detection": {
        "type": "AxisAlignedBox", "class_id": 1,
        "x1": 0.10, "y1": 0.10, "x2": 0.50, "y2": 0.60,
    },
    "rotated_detection_rotated_box": {
        "type": "RotatedBox", "class_id": 1,
        "cx": 0.30, "cy": 0.35, "width": 0.40, "height": 0.20, "angle": 0.5,
    },
    "segmentation": {
        "type": "Polygon", "class_id": 1,
        "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1},
                   {"x": 0.5, "y": 0.5}, {"x": 0.1, "y": 0.5}],
    },
    "keypoint": {
        "type": "Keypoint", "class_id": 1,
        "bounding_box": {"cx": 0.3, "cy": 0.4, "width": 0.2, "height": 0.3},
        "keypoints": [{"x": 0.28, "y": 0.36, "visibility": "Visible"},
                      {"x": 0.34, "y": 0.36, "visibility": "Occluded"}],
    },
}


def test_yolo_text_tasks_emit_non_empty_labels():
    """每个走文本标签格式器的支持类型都必须产出非空行。

    这是「空标签」的直接守卫：标签为空时训练照常跑完，但等于在空数据集上训练，
    不会有任何报错——segmentation 曾经就是这样坏掉的。
    """
    for name, ann in _YOLO_TEXT_SAMPLES.items():
        task_type = "rotated_detection" if name.startswith("rotated_") else name
        lines = _format_yolo_lines([ann], task_type, class_id_map={1: 0},
                                   img_w=640, img_h=480)
        assert lines, f"{task_type}（{name}）导出的标签行为空——会被当空数据集训练"
        assert lines[0].startswith("0 "), f"{name} 的 class_id 映射没生效: {lines[0]}"
