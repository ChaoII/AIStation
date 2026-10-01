"""数据集导出子包：把标注数据导出成各训练框架/外部工具可读的文件。

拆分背景
--------
原先全部挤在 ``exporter.py``（2291 行）里，混合了四类不相关职责：

1. 17 个数据集导出格式（YOLO / X-AnyLabeling / COCO Panoptic / PaddleOCR …）
2. 模型权重入库（``export_model``）——已独立到 ``../model_persist.py``
3. DB 访问（原文件里直接开 24 次会话，绕过 service 层）
4. S3 操作（25 次）

拆分依据是模块内定义的**依赖 DAG**（先验证强连通分量为 0），故按拓扑序切分后
模块间不会循环导入；每个函数体逐字节搬运，事后用 ``ast.dump`` 逐个比对确认一致。

分层
----
- ``common``        Layer 0：布局常量、标注批量查询、几何换算、文件写入
- ``yolo`` / ``semantic`` / ``xanylabeling`` / ``paddle`` / ``torchkiln_ocr``
  / ``events`` / ``video`` / ``mono3d``
                    Layer 1：各格式的具体实现
- ``dispatch``      Layer 2：训练 / 评估 / 数据集下载三条入口与格式分发

新增格式时：实现放进对应的 Layer 1 模块，在 ``dispatch`` 的分发链上加一个分支即可，
不必再动其它格式的代码。
"""

from .common import (
    YOLO_LAYOUT,
    _write_torchkiln_index,
    _write_yaml,
    build_class_mapping,
    rotated_box_to_obb_corners,
)
from .dispatch import (
    _export_core,
    export_dataset_for_download,
    prepare_eval_data_for_task,
    prepare_training_data_for_task,
)
from .events import (
    _export_audio_event,
    _export_text_ner,
    _export_time_series_event,
    _export_video_event,
    _line_bio_tags,
)
from .mono3d import _export_mono3d
from .paddle import (
    _crop_text_region,
    _export_paddle_mlcls,
    _export_paddle_ocr,
    _find_official_ocr_dict,
    paddle_ocr_det_entries,
)
from .semantic import (
    _export_coco_panoptic,
    _export_yolo_semantic,
    _panoptic_mask,
)
from .torchkiln_ocr import _export_torchkiln_ocr
from .video import _export_video_detection
from .xanylabeling import (
    _export_x_anylabeling,
    xany_classification_flags,
    xany_shapes,
)
from .yolo import (
    _export_yolo,
    _export_yolo_cls,
    _format_yolo_lines,
    pose_extra_yaml,
)

__all__ = [
    # 布局常量
    "YOLO_LAYOUT",
    # 三条入口
    "prepare_training_data_for_task",
    "prepare_eval_data_for_task",
    "export_dataset_for_download",
    # 各格式实现（供测试与 dispatch 使用）
    "_export_core",
    "_export_yolo",
    "_export_yolo_cls",
    "_export_yolo_semantic",
    "_export_x_anylabeling",
    "_export_paddle_ocr",
    "_export_paddle_mlcls",
    "_export_torchkiln_ocr",
    "_export_coco_panoptic",
    "_export_video_detection",
    "_export_mono3d",
    "_export_text_ner",
    "_export_audio_event",
    "_export_time_series_event",
    "_export_video_event",
    "_write_torchkiln_index",
    # 几何 / 掩码 / 布局工具（测试与兄弟模块直接引用）
    "build_class_mapping",
    "rotated_box_to_obb_corners",
    "xany_shapes",
    "xany_classification_flags",
    "paddle_ocr_det_entries",
    "pose_extra_yaml",
    "_panoptic_mask",
    "_crop_text_region",
    "_find_official_ocr_dict",
    "_line_bio_tags",
    "_format_yolo_lines",
    "_write_yaml",
]
