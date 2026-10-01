"""``exporter`` 的**兼容层**：原 2291 行的实现已拆分，本模块只做转发。

拆分去向
--------
- 数据集导出（17 个格式 + 三条入口 + 格式分发）→ ``exporters/`` 子包
- 模型权重入库（``export_model``）→ ``model_persist.py``

为什么保留这一层
----------------
调用方有 3 处（``eval_scheduler`` / ``predict_executor`` / ``service``）加 18 个测试
文件从 ``.exporter`` import 符号。直接改调用方的风险在于：漏改一处的报错是
``ImportError: cannot import name '_export_yolo' from 'app.plugin.module_train.exporter'``，
而这个错**只在真正跑到那条路径时才出现**，测试未必覆盖得到。

转发层把风险一次性消掉：调用方一行不改，行为逐字节不变（函数体在拆分过程中未做任何
编辑，已用 ``ast.dump`` 逐个比对确认一致）。

⚠️ 下面的转发清单必须覆盖**全部**外部引用（含下划线私有名）。用
``from .exporters import *`` 是**不够**的——``import *`` 只带 ``__all__`` 里的名字，
而测试会引用 ``_export_core`` / ``_format_yolo_lines`` 这类私有符号，漏一个就
collection 阶段直接 ImportError（实测踩过）。
``tests/test_exporter_module_split.py`` 会核对这份清单与实际引用是否一致。

确认所有调用方都改到新位置、且测试不再引用本模块后，可连同本文件一起删除。
删除判据同样在那个测试文件里。

⚠️ 本模块**不要**新增实现——新代码请放进 ``exporters/`` 或 ``model_persist.py``，
否则拆分就白做了。
"""

# ---- 数据集导出：子包内的公共 API ----
from .exporters import (
    YOLO_LAYOUT,
    _export_audio_event,
    _export_core,
    _export_text_ner,
    _export_time_series_event,
    _export_video_detection,
    _export_video_event,
    _export_yolo_cls,
    _format_yolo_lines,
    _panoptic_mask,
    _write_torchkiln_index,
    _write_yaml,
    build_class_mapping,
    export_dataset_for_download,
    paddle_ocr_det_entries,
    pose_extra_yaml,
    prepare_eval_data_for_task,
    prepare_training_data_for_task,
    rotated_box_to_obb_corners,
    xany_classification_flags,
    xany_shapes,
)

# ---- 权重入库：module_train 层内的独立模块 ----
from .model_persist import _fetch_torchkiln_weights, export_model

__all__ = [
    "YOLO_LAYOUT",
    "prepare_training_data_for_task",
    "prepare_eval_data_for_task",
    "export_dataset_for_download",
    "export_model",
    "build_class_mapping",
    "rotated_box_to_obb_corners",
    "xany_shapes",
    "xany_classification_flags",
    "pose_extra_yaml",
    "paddle_ocr_det_entries",
    # 私有符号：外部（测试 + 兄弟模块）在用，故一并转发
    "_export_core",
    "_export_yolo_cls",
    "_export_text_ner",
    "_export_audio_event",
    "_export_time_series_event",
    "_export_video_event",
    "_export_video_detection",
    "_format_yolo_lines",
    "_panoptic_mask",
    "_write_torchkiln_index",
    "_write_yaml",
    "_fetch_torchkiln_weights",
]
