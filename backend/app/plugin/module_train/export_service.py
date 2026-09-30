import asyncio
import os

from app.core.logger import log
from app.utils.s3_client import s3_client

from .paths import work_dir
from .retired import ensure_active

# Format -> supported export arguments mapping
# 注：原先这里还有 ``EXPORT_PARAMS_BY_FORMAT``（ultralytics yolo export 各格式的
# 可用参数表）与 ``_build_export_cmd()`` / ``_find_exported_file()``。三者都只服务
# 于 yolo export 通路，已随 Ultralytics 退场移除。``EXPORT_EXT`` 仍被
# ``resolve_download_target`` 与 torchkiln 导出共用，保留。

# Format -> output file extension
EXPORT_EXT = {
    "onnx": ".onnx",
    "torchscript": ".torchscript",
    "engine": ".engine",
    "openvino": "",
    "coreml": ".mlpackage",
    "saved_model": "",
    "paddle": "",
    "ncnn": "",
    "litert": ".tflite",
    "pb": ".pb",
    "edgetpu": ".tflite",
    "tflite": ".tflite",
    "tfjs": "",
}


def resolve_download_target(model: dict, exists_fn) -> tuple[str, str]:
    """决定下载对象键与真实格式：优先确定性导出产物，否则原始权重。

    导出产物上传到确定性键 `train/models/model_{id}/export/best.<ext>`，
    当模型 format 非原始且该键存在时返回导出键与导出格式；否则回退
    `storage_path` 与真实原始格式 "pytorch"。
    """
    storage_path = model.get("storage_path") or ""
    fmt = model.get("format") or "pytorch"
    if fmt != "pytorch":
        ext = EXPORT_EXT.get(fmt, "")
        key = f"train/models/model_{model.get('id')}/export/best{ext}"
        if exists_fn(key):
            return key, fmt
    return storage_path, "pytorch"


async def _run_export_container(image: str, cmd: list[str], volumes: dict) -> tuple[int, str]:
    """Run a container, capture logs to file, return (exit_code, log_path)"""
    import docker
    client = docker.from_env()
    loop = asyncio.get_event_loop()

    log_dir = work_dir("model_export_logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"export_{os.getpid()}_{id(volumes)}.log")

    def _sync():
        container = client.containers.run(
            image, cmd,
            volumes=volumes,
            detach=True,
            remove=False,
            stderr=True,
        )
        # Stream logs to file in background
        log_file = open(log_path, "w", encoding="utf-8", errors="replace")
        try:
            for line in container.logs(stream=True, follow=True):
                log_file.write(line.decode("utf-8", errors="replace"))
                log_file.flush()
        finally:
            log_file.close()

        try:
            result = container.wait(timeout=1800)
            return result["StatusCode"], log_path
        finally:
            container.remove()

    return await loop.run_in_executor(None, _sync)


#: TorchKiln 导出产物扩展名（与 ultralytics 的 EXPORT_EXT 分开）
TK_EXPORT_EXT = {"onnx": ".onnx", "engine": ".engine", "torchscript": ".torchscript"}


def _build_tk_export_cmd(weights_name: str, cfg: str, export_params: dict) -> list[str]:
    """构建 ``tkiln export`` 命令。

    权重是 TorchKiln 自己的 state_dict（.pth），配置名必须与训练时一致，
    所以从产出该模型的**训练任务**反查（resolve_export_tk_context），
    不让用户手填——填错架构导出的 ONNX 是不可用的。
    """
    opts = [
        f"Global.pretrained_model=/weights/{weights_name}",
        "Global.save_model_dir=/output",
    ]
    imgsz = export_params.get("imgsz")
    if imgsz:
        opts.append(f"Global.imgsz={imgsz}")
    half = export_params.get("half")
    if half is not None:
        opts.append(f"Global.export_half={'true' if half else 'false'}")
    simplify = export_params.get("simplify")
    if simplify is not None:
        opts.append(f"Global.export_simplify={'true' if simplify else 'false'}")
    fmt = str(export_params.get("format", "onnx")).lower()
    if fmt == "onnx":
        opts.append("Global.export_onnx=true")
    elif fmt == "torchscript":
        opts.append("Global.export_torchscript=true")
    elif fmt == "engine":
        opts.append("Global.export_engine=true")
    return ["tkiln", "export", "-c", str(cfg), "-o"] + opts


def _find_tk_exported_file(output_dir: str, weights_dir: str, fmt: str) -> str | None:
    """在输出目录里找导出的产物（递归，容忍 tkiln 不同的落盘子目录）。"""
    exts = [v for k, v in TK_EXPORT_EXT.items() if k == fmt] or [f".{fmt}"]
    for base in (output_dir, weights_dir):
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for f in files:
                if any(f.lower().endswith(e) for e in exts):
                    return os.path.join(root, f)
    return None


async def resolve_export_tk_context(model_id: int) -> str:
    """反查产出该模型版本的训练任务，取 TorchKiln 配置名。

    导出必须与训练用同一套配置——架构/imgsz 对不上，导出的 ONNX 推理结果就是错的。
    """
    from sqlalchemy import desc, select

    from app.core.database import async_db_session

    from .framework_utils import framework_value
    from .model import TrainModel, TrainTask

    async with async_db_session() as db:
        model_row = await db.get(TrainModel, model_id)
        repo_id = model_row.repo_id if model_row else None
        if not repo_id:
            raise Exception("找不到该模型版本所属的模型仓库")
        task = (await db.execute(
            select(TrainTask).where(TrainTask.model_repo_id == repo_id)
            .order_by(desc(TrainTask.id)).limit(1)
        )).scalar_one_or_none()
    if not task:
        raise Exception("找不到产出该模型的训练任务，无法确定导出配置")
    if framework_value(getattr(task, "framework", None)) != "torchkiln":
        raise Exception("该模型不是 TorchKiln 训练产出，无法用 tkiln export 导出")
    cfg = str((task.hyperparams or {}).get("model") or "")
    if not cfg:
        raise Exception("训练任务未记录 TorchKiln 模型配置名（hyperparams.model）")
    return cfg


async def _export_torchkiln(
    model_id: int, original_storage_path: str, export_params: dict,
    storage_path: str, existing_format: str | None,
) -> dict:
    """TorchKiln 的 ONNX/TensorRT 导出：跑 ``tkiln export`` 而非 ``yolo export``。

    与 ultralytics 路径的差异：权重是 .pth、配置名要回查训练任务、镜像也不同。
    这些差异足够大，所以**独立成函数**而不是在主流程里塞 if——主流程已经很长，
    再加分支会难以维护。
    """
    from app.utils.s3_client import s3_client

    cfg = await resolve_export_tk_context(model_id)
    export_format = export_params.get("format", "onnx")
    image = export_params.get("docker_image") or "torchkiln:0.1.0"

    work_path = work_dir("model_export", f"tk_{model_id}")
    weights_dir = os.path.join(work_path, "weights")
    output_dir = os.path.join(work_path, "output")
    os.makedirs(weights_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    # TorchKiln 的产物名是 best_accuracy.pth（不是 ultralytics 的 best.pt）
    weights_name = os.path.basename(original_storage_path) or "best_accuracy.pth"
    local = os.path.join(weights_dir, weights_name)
    buf = s3_client.download_fileobj(original_storage_path)
    with open(local, "wb") as f:
        f.write(buf.read())
    size = os.path.getsize(local)
    if size == 0:
        raise Exception(f"从 RustFS 下载的权重为空: {original_storage_path}")

    # ⚠️ cfg 是从训练任务反查来的**模型名**（如 yolo11-seg），而 `tkiln export -c`
    # 只认 configs/ 下的**配置路径**。借常驻元数据服务换一次，否则容器里会报
    # 「省略 <task> 时必须用 -c <config> 指定配置」——导出从来没成功过的根因。
    from .torchkiln_client import TorchKilnClient
    async with TorchKilnClient() as _tk:
        cfg = await _tk.resolve_config_path(cfg)

    cmd = _build_tk_export_cmd(weights_name, cfg, export_params)
    log.info(f"tkiln export cmd: {' '.join(cmd)}")
    exit_code, log_path = await _run_export_container(
        image, cmd,
        volumes={
            weights_dir: {"bind": "/weights", "mode": "rw"},
            output_dir: {"bind": "/output", "mode": "rw"},
        },
    )
    if exit_code != 0:
        tail = ""
        if os.path.isfile(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as lf:
                tail = "".join(lf.readlines()[-200:]).strip()
        raise Exception(f"tkiln export 退出码 {exit_code}\n最后日志:\n{tail}")

    exported = _find_tk_exported_file(output_dir, weights_dir, export_format)
    if not exported:
        listing = []
        for base in (output_dir, weights_dir):
            for root, _d, files in os.walk(base):
                listing.append(f"  {root}: {files}")
        raise Exception(
            f"未找到导出的 {export_format} 文件\n搜索目录:\n" + "\n".join(listing))

    ext = TK_EXPORT_EXT.get(export_format, f".{export_format}")
    rustfs_key = f"train/models/model_{model_id}/export/best{ext}"
    with open(exported, "rb") as f:
        s3_client.upload_fileobj(f, rustfs_key)
    file_size = os.path.getsize(exported)
    return {
        "download_url": s3_client.presigned_url(rustfs_key),
        "format": export_format,
        "file_size": file_size,
        "file_name": f"model_{model_id}_export{ext}",
        "storage_path": rustfs_key,
    }


async def export_model_to_format(
    model_id: int,
    storage_path: str | None,
    export_params: dict,
    model_name: str,
    created_id: int,
    dataset_id: int | None,
    framework: str | None = None,
) -> dict:
    """Export a trained model to the specified format

    Returns:
        dict with download_url, format, file_size, file_name
    """
    if not storage_path:
        raise Exception("该模型未存储训练产物文件，无法导出。请确认训练已完成且模型已正常保存。")

    # 格式转换导出只支持自研平台：TorchKiln 产物是 .pth，走它自带的
    # `tkiln export --onnx`。Ultralytics / PaddleX 的转换通路已退场
    # （原始权重下载不受影响，仍可从模型仓库直接下载）。
    if framework != "torchkiln":
        raise Exception(
            f"「{framework}」框架的格式转换导出已退场，仅支持下载原始权重文件。"
            f"请使用模型下载功能获取权重；如需 ONNX/TensorRT，请用 TorchKiln 重新训练后导出。"
        )

    # 每次导出都重新执行，除非原始 .pt 确实无法找回
    original_storage_path = storage_path
    existing_format = None
    if "/export/" in storage_path:
        existing_format = os.path.splitext(storage_path)[1].lstrip(".") or "onnx"
        # 尝试从训练任务找回原始 .pt
        from sqlalchemy import desc, select

        from app.core.database import async_db_session

        from .model import TrainTask
        async with async_db_session() as db:
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
        if task:
            original_storage_path = f"train/models/task_{task.id}/best.pt"
            log.info(f"storage_path 是导出产物，回溯原始路径: {original_storage_path}")
        else:
            # 找不到原始任务，直接返回已有导出产物
            dl_url = s3_client.presigned_url(storage_path)
            log.info(f"原始训练记录丢失，返回已有导出产物: {storage_path}")
            return {
                "download_url": dl_url,
                "format": existing_format,
                "file_size": 0,
                "file_name": f"model_{model_id}_export.{existing_format}",
            }

    # TorchKiln 走独立导出路径（.pth + tkiln export + 专用镜像），
    # 与 ultralytics 的 yolo export 差异太大，硬塞进主流程只会更难维护。
    if framework == "torchkiln":
        return await _export_torchkiln(
            model_id, original_storage_path, export_params, storage_path, existing_format)

    # Ultralytics 的 `yolo export` 与 PaddleX 的 .pdparams 转换通路都已退场。
    # 这里原本还有一整套「下载 .pt -> 组 yolo export 命令 -> 起容器 -> 找产物 ->
    # 上传 RustFS」的流程（约 140 行）；对已退场框架保留它没有意义——真跑起来
    # 也只会因为镜像/权重格式不匹配而失败，报错还与真实原因无关。
    #
    # 注意：**原始权重下载不受影响**，走的是 resolve_download_target 那条路。
    ensure_active(framework, action="格式转换导出")
