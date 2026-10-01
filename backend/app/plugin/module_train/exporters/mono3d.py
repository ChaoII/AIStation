"""单目 3D 检测导出

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import math
import os

from app.core.database import async_db_session
from app.core.logger import log

from .common import _load_latest_anns_by_image, _write_torchkiln_index, build_class_mapping


async def _export_mono3d(
    dataset_id: int, task_id: int, images: list, output_dir: str,
    annotation_task_id: int | None = None, train_ratio: float = 0.8,
    class_names: dict | None = None, for_eval: bool = False,
    torchkiln_index: bool = True,
) -> None:
    """导出单目 3D 检测：``images/<split>/*.jpg`` + ``labels/<split>/*.txt``。

    标签每行 ``cls x y z l w h yaw``，是 TorchKiln ``mono3d``/``det3d`` 要的
    **LiDAR/ego 系**（x 前 / y 左 / z 上、``z`` 为框**中心**、``l`` 沿 ``yaw``）。

    ## 坐标系转换（本项目存相机系，TorchKiln 要 LiDAR 系）

    本平台标注与存储用 KITTI 相机系（x 右 / y 下 / z 前；``ry`` 是 KITTI 的
    ``rotation_y``，车长轴方向为 ``(cos ry, 0, -sin ry)``），TorchKiln 用
    LiDAR/ego 系::

        x_lidar =  z_cam          # 前
        y_lidar = -x_cam          # 左
        z_lidar = -y_cam + h/2    # 上；且相机系存的是**底面**，要抬 h/2 成中心
        yaw      =  ry_cam + π/2  # 照抄 TorchKiln 的 KITTI 转换式

    ⚠️ 最后一条刻意**直接沿用** TorchKiln ``tools/convert/kitti_to_det3d.py`` 的
    ``yaw = ry + np.pi / 2.0``，不做「几何修正」。该文件注释里的角度推导与 KITTI
    devkit ``compute_box_3d`` 的实际约定并不自洽；两边**共用一个约定**比「各自
    推导正确」更重要，否则导出的朝向会与 TorchKiln 的后处理/评估差一个固定角。
    前端 ``box3d.ts`` 有一份镜像实现（``box3dToLidar``），**必须同步改**。

    ⚠️ 另外两处也极易漏：
      - 只换轴不换角 -> 朝向差固定角度；
      - 忘记 y 取反 -> 左右镜像。

    ⚠️ TorchKiln 的 ``load_box_labels`` **只按列数校验**（``len(parts) < 8`` 就跳过），
    列数够但语义错（比如误写图像像素坐标）会被直接当米制解析、不报错——
    所以这里必须严格保证 8 列的语义精确。
    """
    import random

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        anns_by_img = await _load_latest_anns_by_image(
            db, [img.id for img in images], annotation_task_id)

    used_ids: set[int] = set()
    for anns in anns_by_img.values():
        for ann in anns:
            cid = ann.get("class_id")
            if cid is not None and cid != -1:
                used_ids.add(int(cid))
    class_id_map = build_class_mapping(used_ids)

    if for_eval:
        train_imgs, val_imgs = [], list(images)
    else:
        images = list(images)
        random.shuffle(images)
        split_idx = max(1, int(len(images) * train_ratio))
        train_imgs, val_imgs = images[:split_idx], images[split_idx:]

    n_box = 0
    n_skipped = 0
    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        lab_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(lab_split, exist_ok=True)
        for img in split_imgs:
            img_path = os.path.join(img_split, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning("skip {}: {}", img.filename, e)
                    continue
            lines: list[str] = []
            for ann in anns_by_img.get(img.id, []):
                raw_cls = ann.get("class_id")
                if raw_cls is None or raw_cls == -1:
                    continue
                cls_id = class_id_map.get(raw_cls)
                if cls_id is None:
                    continue
                b = ann.get("box3d")
                if not isinstance(b, dict):
                    # 没有米制 3D 参数：只有 2D 投影，**无法**反推深度与真实尺寸。
                    # 绝不能拿归一化的 cx/cy/w/h 顶替——那会被 TorchKiln 当米制解析，
                    # 不报错但数据全错。
                    n_skipped += 1
                    continue
                try:
                    cam_x = float(b["x"])
                    cam_y = float(b["y"])
                    cam_z = float(b["z"])
                    # 用 box_l/w/h 而不是 l/w/h：单字母 l 在代码里极易与 1 混淆
                    # （ruff E741），w/h 也会遮蔽掉常见名
                    box_l = float(b["l"])
                    box_w = float(b["w"])
                    box_h = float(b["h"])
                    ry = float(b["ry"])
                except (KeyError, TypeError, ValueError):
                    n_skipped += 1
                    continue
                if cam_z <= 0 or box_l <= 0 or box_w <= 0 or box_h <= 0:
                    n_skipped += 1
                    continue
                # 相机系 -> LiDAR/ego 系（详见函数 docstring 的警告）
                x_lidar = cam_z
                y_lidar = -cam_x
                z_lidar = -cam_y + box_h / 2.0
                yaw = ry + math.pi / 2.0
                lines.append(
                    f"{cls_id} {x_lidar:.4f} {y_lidar:.4f} {z_lidar:.4f} "
                    f"{box_l:.4f} {box_w:.4f} {box_h:.4f} {yaw:.6f}"
                )
            if not lines:
                continue
            stem = os.path.splitext(img.filename)[0]
            with open(os.path.join(lab_split, stem + ".txt"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            n_box += len(lines)

    if torchkiln_index:
        _write_torchkiln_index(output_dir)
    log.info("mono3d: images={} boxes={} skipped={} classes={} → {}",
             len(train_imgs) + len(val_imgs), n_box, n_skipped,
             len(class_id_map), output_dir)
    if n_skipped:
        log.warning(
            "mono3d: {} 个标注缺少 box3d 米制参数（只有 2D 投影），已跳过——"
            "请在 3D 目标检测任务的面板里补齐深度与尺寸", n_skipped)
