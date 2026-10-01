"""训练产出的**权重入库**：定位最优权重 → 上传 RustFS → 建/更新模型版本 → 回写任务。

与 ``exporters/``（数据集导出）刻意分开：前者是「训练产物进模型仓库」，
后者是「标注数据出成训练框架格式」，两者数据流方向相反、依赖的东西也不同
（前者要 s3_client + ORM 写事务，后者要标注查询 + 文件写入）。

历史上它们被塞在同一个 exporter.py 里，导致「改数据集导出格式」要在一个 2291 行
文件里翻找，而权重入库的写操作也没有独立的、可统一加事务边界的位置。

由原 ``exporter.py`` 拆分而来（原文件 2291 行，混合了数据集导出、模型权重入库、
DB 访问与 S3 操作四类职责）。拆分依据是模块内定义的**依赖 DAG**——先验证过
无强连通分量，故按拓扑序切分不会产生循环导入。

函数体**逐字节原样搬运**，未做任何编辑；拆分后用 ast.dump 逐个比对确认一致。
"""

import os

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.logger import log

# TrainModelRepo / TrainModel / TrainTask 在 export_model 内部按需 import（原来如此），
# 但 TrainModelRepo 在该函数的模块级作用域里被引用，必须在此导入——原 exporter.py
# 顶部就有这一行，拆分时若漏掉会得到「拆分后才暴露」的 NameError。
from .model import TrainModelRepo


async def _fetch_torchkiln_weights(task_id: int, export_dir: str) -> str | None:
    """定位该任务训练出的最优权重，返回其**本地**路径。

    改为直接读本地，而不是去连 TorchKiln 服务下载。原因是 job 容器模式
    （每任务一容器）下：训练期间 ``TKILN_DATA_ROOT`` 指向挂载点 ``/workspace``，
    权重其实已经写在宿主的 ``export_dir`` 下面了，容器销毁也不影响；而常驻
    服务已经不存在，那个固定 URL 连不上——照旧写法会直接拉取失败、权重不入库。

    布局：``export_dir/jobs/<job_id>/best_accuracy.pth``（TorchKiln 的
    ``output_dir = {data_root}/jobs/{job_id}``）。找不到时递归兜底搜一次，
    防止 TorchKiln 改了输出布局就彻底断掉。
    """
    import os as _os

    from .model import TrainTask as _TrainTask

    async with async_db_session() as db:
        task = await db.get(_TrainTask, task_id)
        if task is None:
            raise ValueError(f"训练任务 {task_id} 不存在")
        job_id = (task.hyperparams or {}).get("__tk_job_id")
    if not job_id:
        raise ValueError("任务没有 TorchKiln 作业 id（未启动过训练？）")

    direct = _os.path.join(export_dir, "jobs", job_id, "best_accuracy.pth")
    if _os.path.isfile(direct):
        log.info(f"torchkiln 权重命中（挂载目录）-> {direct}")
        return direct

    for root, dirs, files in _os.walk(export_dir):
        dirs[:] = [d for d in dirs if d != ".models_cache"]
        if "best_accuracy.pth" in files or "final.pth" in files:
            name = ("best_accuracy.pth" if "best_accuracy.pth" in files
                    else "final.pth")
            hit = _os.path.join(root, name)
            log.info(f"torchkiln 权重命中（递归兜底）-> {hit}")
            return hit

    raise FileNotFoundError(
        f"在 {export_dir} 下找不到作业 {job_id} 的权重"
        f"（期望 jobs/{job_id}/best_accuracy.pth）。"
        f"若训练确实成功，请检查该 job 容器当时是否把 TKILN_DATA_ROOT 指到了挂载点。"
    )


async def export_model(task_id: int, framework: str, export_dir: str, best_metrics: dict | None = None) -> dict:
    from .model import TrainModel, TrainTask

    # 0. TorchKiln：权重在训练服务的 output_dir（可能另一台机器/容器里），
    #    先把 best_accuracy.pth 拉回本地，后续流程与其它框架一致。
    if framework == "torchkiln":
        try:
            await _fetch_torchkiln_weights(task_id, export_dir)
        except Exception as e:  # noqa: BLE001
            log.error(f"从 TorchKiln 服务拉取权重失败: {e}")
            return {"repo_id": None, "storage_path": None}

    # 1. 优先从标准输出目录找模型文件。
    #    只剩 ``.pth``：``.pt``（ultralytics）与 ``.pdparams``（PaddleX）两个分支
    #    曾只为读回那两家的历史产物而存在，数据已随退场一并删净，留着就是永远走不到
    #    的死分支，还会让人以为那些权重仍受支持。
    best_path = None
    extensions = [".pth"]
    for ext in extensions:
        candidates = [
            os.path.join(export_dir, "exp", "weights", f"best{ext}"),
            os.path.join(export_dir, "runs", "train", "exp", "weights", f"best{ext}"),
            os.path.join(export_dir, "weights", f"best{ext}"),
            os.path.join(export_dir, f"best_accuracy{ext}"),
            os.path.join(export_dir, f"best{ext}"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                best_path = p
                break
        if best_path:
            break
    # 2. 降级：递归搜索，但排除 .models_cache 目录
    if not best_path:
        for root, dirs, files in os.walk(export_dir):
            dirs[:] = [d for d in dirs if d != ".models_cache"]
            for f in files:
                if framework == "torchkiln" and f in ("best_accuracy.pth", "final.pth"):
                    best_path = os.path.join(root, f)
                    break
            if best_path:
                break

    storage_path = None
    if best_path:
        rustfs_path = f"train/models/task_{task_id}/{os.path.basename(best_path)}"
        try:
            from app.utils.s3_client import s3_client
            with open(best_path, "rb") as f:
                s3_client.upload_fileobj(f, rustfs_path)
            storage_path = rustfs_path
        except Exception as e:
            log.error(f"upload model to RustFS failed: {e}，本次不创建模型版本")

    # 无训练产物（未找到 best_path 或上传失败）时直接返回，不写 DB：
    # 否则会在模型仓库留下一条无权重的最新版本，并污染 task.model_repo_id。
    if not storage_path:
        return {"repo_id": None, "storage_path": None}

    async with async_db_session.begin() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            return {"repo_id": None, "storage_path": storage_path}

        existing = await db.execute(
            select(TrainModel).where(TrainModel.name == task.name).order_by(TrainModel.id.desc()).limit(1)
        )
        last = existing.scalar_one_or_none()
        next_ver = 1
        if last and last.version:
            from .service import TrainService
            next_ver = TrainService._parse_version(last.version) + 1

        repo = (await db.execute(
            select(TrainModelRepo).where(TrainModelRepo.name == task.name)
        )).scalar_one_or_none()
        if not repo:
            repo = TrainModelRepo(name=task.name, framework=task.framework, created_id=task.created_id)
            db.add(repo)
            await db.flush()

        model_rec = TrainModel(
            repo_id=repo.id, name=task.name, framework=task.framework,
            version=f"v{next_ver}", storage_path=storage_path,
            format="pytorch",  # Original format is PyTorch
            annotation_dataset_id=task.dataset_id, created_id=task.created_id,
            metrics=best_metrics if best_metrics is not None else task.best_metrics,
        )
        db.add(model_rec)
        await db.flush()
        repo.latest_version_id = model_rec.id
        task.model_repo_id = model_rec.id

    return {"repo_id": model_rec.id, "storage_path": storage_path}
