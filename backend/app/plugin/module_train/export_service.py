import asyncio
import os
import tempfile

from app.core.logger import log
from app.utils.s3_client import s3_client

# Format -> supported export arguments mapping
EXPORT_PARAMS_BY_FORMAT = {
    "onnx": ["imgsz", "batch", "device", "dynamic", "simplify", "opset", "nms", "quantize", "data", "fraction"],
    "torchscript": ["imgsz", "batch", "device", "dynamic", "optimize", "nms", "quantize"],
    "engine": ["imgsz", "batch", "device", "dynamic", "workspace", "nms", "quantize", "simplify", "data", "fraction"],
    "openvino": ["imgsz", "batch", "device", "dynamic", "nms", "quantize", "data", "fraction"],
    "coreml": ["imgsz", "batch", "device", "dynamic", "nms", "quantize"],
    "saved_model": ["imgsz", "batch", "device", "nms", "quantize", "keras", "data", "fraction"],
    "paddle": ["imgsz", "batch", "device"],
    "ncnn": ["imgsz", "batch", "device", "quantize"],
    "litert": ["imgsz", "batch", "device", "quantize", "data", "fraction"],
    "pb": ["imgsz", "batch", "device"],
    "edgetpu": ["imgsz", "quantize", "data", "fraction", "device"],
    "tflite": ["imgsz", "batch", "device", "quantize", "data", "fraction"],
    "tfjs": ["imgsz", "batch", "device"],
}

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


def _build_export_cmd(params: dict) -> list[str]:
    """Build yolo export CLI command from user params"""
    cmd = ["yolo", "export", "model=/weights/best.pt", "project=/output", "name=export"]

    for key, val in params.items():
        if key == "format":
            cmd.append(f"format={val}")
            continue
        fmt = params.get("format", "onnx")
        if key not in EXPORT_PARAMS_BY_FORMAT.get(fmt, []):
            continue
        if val is None or val is False:
            continue
        if val is True:
            cmd.append(f"{key}={str(val).lower()}")
        else:
            cmd.append(f"{key}={val}")

    return cmd


async def _run_export_container(image: str, cmd: list[str], volumes: dict) -> tuple[int, str]:
    """Run a container, capture logs to file, return (exit_code, log_path)"""
    import docker
    client = docker.from_env()
    loop = asyncio.get_event_loop()

    log_dir = os.path.join(tempfile.gettempdir(), "model_export_logs")
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


def _find_exported_file(output_dir: str, weights_dir: str, export_format: str) -> str | None:
    """Find the exported file in output or weights directory"""
    ext = EXPORT_EXT.get(export_format, "")
    search_dirs = [output_dir, weights_dir]
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for root, _, files in os.walk(search_dir):
            for f in files:
                if ext and f.endswith(ext):
                    return os.path.join(root, f)
                if not ext and export_format in root:
                    return root
    return None


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

    work_dir = os.path.join(tempfile.gettempdir(), "model_export", f"tk_{model_id}")
    weights_dir = os.path.join(work_dir, "weights")
    output_dir = os.path.join(work_dir, "output")
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
    from .model import TrainModel

    if not storage_path:
        raise Exception("该模型未存储训练产物文件（best.pt），无法导出。请确认训练已完成且模型已正常保存。")

    # 非 ultralytics 框架：
    #   - PaddleX 产物是 .pdparams，无法用 yolo export 转格式
    #   - TorchKiln 产物是 .pth（自己的 state_dict），同样不能用 yolo export，
    #     但它自带 `tkiln export --onnx`，可以走自己的导出路径
    if framework and framework not in ("ultralytics", "yolo", "torchkiln", None):
        raise Exception(
            f"「{framework}」框架暂不支持 ONNX/TensorRT 等格式转换导出，"
            "仅支持下载原始权重文件。请使用模型下载功能获取 .pdparams 权重。"
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

    export_format = export_params.get("format", "onnx")
    image = "ultralytics/ultralytics:latest"
    log_path = ""

    work_dir = os.path.join(tempfile.gettempdir(), "model_export", str(model_id))
    weights_dir = os.path.join(work_dir, "weights")
    output_dir = os.path.join(work_dir, "output")
    os.makedirs(weights_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 1. Download .pt from RustFS
        pt_path = os.path.join(weights_dir, "best.pt")
        try:
            buf = s3_client.download_fileobj(original_storage_path)
        except Exception as e:
            if existing_format and "404" in str(e):
                dl_url = s3_client.presigned_url(storage_path)
                log.info(f"原始 .pt 不存在(404)，返回已有导出产物: {storage_path}")
                return {
                    "download_url": dl_url,
                    "format": existing_format,
                    "file_size": 0,
                    "file_name": f"model_{model_id}_export.{existing_format}",
                }
            raise
        with open(pt_path, "wb") as f:
            f.write(buf.read())
        file_size = os.path.getsize(pt_path)
        log.info(f"downloaded {original_storage_path} to {pt_path} ({file_size} bytes)")
        if file_size == 0:
            raise Exception(f"从 RustFS 下载的文件为空 (storage_path={storage_path})")
        # 检查文件头是否为有效的 PyTorch pickle 格式（前两个字节通常为 0x80 0x02-0x05）
        with open(pt_path, "rb") as f:
            header = f.read(8)
        if not header.startswith(b"\x80") and not header.startswith(b"PK\x03\x04"):
            if existing_format:
                # 回溯的 .pt 路径无效，但有旧导出产物，提供下载
                dl_url = s3_client.presigned_url(storage_path)
                log.info(f"原始 .pt 不存在，返回已有导出产物: {storage_path}")
                return {
                    "download_url": dl_url,
                    "format": existing_format,
                    "file_size": 0,
                    "file_name": f"model_{model_id}_export.{existing_format}",
                }
            raise Exception(
                f"RustFS 返回的文件不是有效的 PyTorch 模型文件\n"
                f"storage_path={original_storage_path}, 文件大小={file_size} bytes\n"
                f"前 8 字节 hex: {header.hex()}\n"
                f"说明: 该模型训练产物丢失或损坏，请重新训练"
            )

        # 2. Build and run export command
        cmd = _build_export_cmd(export_params)
        log.info(f"export cmd: {' '.join(cmd)}")

        exit_code, log_path = await _run_export_container(
            image, cmd,
            volumes={
                weights_dir: {"bind": "/weights", "mode": "rw"},
                output_dir: {"bind": "/output", "mode": "rw"},
            },
        )

        if exit_code != 0:
            log_tail = ""
            if os.path.isfile(log_path):
                with open(log_path, encoding="utf-8", errors="replace") as lf:
                    lines = lf.readlines()
                    log_tail = "".join(lines[-200:]).strip()
            raise Exception(f"容器退出码 {exit_code}\n最后日志:\n{log_tail}")

        # 3. Find exported file
        exported = _find_exported_file(output_dir, weights_dir, export_format)
        if not exported:
            dir_listing = []
            for d in [output_dir, weights_dir]:
                if os.path.isdir(d):
                    for root, _, files in os.walk(d):
                        dir_listing.append(f"  {root}: {files}")
            raise Exception(
                f"exported file not found for format {export_format}\n"
                f"searched dirs:\n" + "\n".join(dir_listing)
            )

        # 4. Upload to RustFS
        rustfs_key = f"train/models/model_{model_id}/export/best{EXPORT_EXT.get(export_format, '')}"
        if os.path.isfile(exported):
            with open(exported, "rb") as f:
                s3_client.upload_fileobj(f, rustfs_key)
            file_size = os.path.getsize(exported)
        else:
            # Directory format - zip it
            import shutil
            zip_path = output_dir + ".zip"
            shutil.make_archive(output_dir, "zip", exported)
            with open(zip_path, "rb") as f:
                s3_client.upload_fileobj(f, rustfs_key)
            file_size = os.path.getsize(zip_path)
            # 目录格式打包为 zip 上传，但对象键仍为真实上传键（无 .zip 后缀），
            # 下载链接必须指向该真实对象，否则会 404。.zip 仅用于用户可见文件名。

        # 5. Update DB
        from datetime import datetime

        from sqlalchemy import update

        from app.core.database import async_db_session

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainModel)
                .where(TrainModel.id == model_id)
                .values(
                    format=export_format,
                    updated_time=datetime.now(),
                )
            )

        # 6. Generate download URL
        download_url = s3_client.presigned_url(rustfs_key)

        # 目录格式（EXPORT_EXT 为空串）用户可见文件名以 .zip 结尾
        file_name = f"model_{model_id}_{export_format}{EXPORT_EXT.get(export_format) or '.zip'}"

        log.info(f"model {model_id} exported to {export_format}: {rustfs_key} ({file_size} bytes)")

        return {
            "download_url": download_url,
            "format": export_format,
            "file_size": file_size,
            "file_name": file_name,
        }

    except Exception as e:
        log.error(f"model export failed: {e}")
        raise
    finally:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
        if os.path.isfile(log_path):
            os.remove(log_path)
