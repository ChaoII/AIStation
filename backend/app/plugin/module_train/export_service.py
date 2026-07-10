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


def _build_export_cmd(params: dict) -> list[str]:
    """Build yolo export CLI command from user params"""
    cmd = ["yolo", "export", "model=/weights/best.pt"]

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


async def _run_export_container(image: str, cmd: list[str], volumes: dict) -> int:
    """Run a container and wait for it to finish, return exit code"""
    import docker
    client = docker.from_env()
    loop = asyncio.get_event_loop()

    def _sync():
        container = client.containers.run(
            image, cmd,
            volumes=volumes,
            detach=True,
            remove=True,
            stderr=True,
        )
        result = container.wait(timeout=600)
        return result["StatusCode"]

    return await loop.run_in_executor(None, _sync)


def _find_exported_file(output_dir: str, export_format: str) -> str | None:
    """Find the exported file in output directory"""
    ext = EXPORT_EXT.get(export_format, "")
    for root, _, files in os.walk(output_dir):
        for f in files:
            if ext and f.endswith(ext):
                return os.path.join(root, f)
            if not ext and export_format in root:
                # For directory formats like openvino, saved_model
                return root
    return None


async def export_model_to_format(
    model_id: int,
    storage_path: str,
    export_params: dict,
    model_name: str,
    created_id: int,
    dataset_id: int | None,
) -> dict:
    """Export a trained model to the specified format

    Returns:
        dict with download_url, format, file_size, file_name
    """
    from .model import TrainModel

    export_format = export_params.get("format", "onnx")
    image = "ultralytics/ultralytics:latest"

    work_dir = os.path.join(tempfile.gettempdir(), "model_export", str(model_id))
    weights_dir = os.path.join(work_dir, "weights")
    output_dir = os.path.join(work_dir, "output")
    os.makedirs(weights_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 1. Download .pt from RustFS
        pt_path = os.path.join(weights_dir, "best.pt")
        buf = s3_client.download_fileobj(storage_path)
        with open(pt_path, "wb") as f:
            f.write(buf.read())
        log.info(f"downloaded {storage_path} to {pt_path} ({os.path.getsize(pt_path)} bytes)")

        # 2. Build and run export command
        cmd = _build_export_cmd(export_params)
        log.info(f"export cmd: {' '.join(cmd)}")

        await _run_export_container(
            image, cmd,
            volumes={
                weights_dir: {"bind": "/weights", "mode": "ro"},
                output_dir: {"bind": "/output", "mode": "rw"},
            },
        )

        # 3. Find exported file
        exported = _find_exported_file(output_dir, export_format)
        if not exported:
            raise Exception(f"exported file not found for format {export_format}")

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
            rustfs_key = rustfs_key.rstrip("/") + ".zip"

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
                    storage_path=rustfs_key,
                    updated_time=datetime.now(),
                )
            )

        # 6. Generate download URL
        download_url = s3_client.presigned_url(rustfs_key)

        file_name = f"model_{model_id}_{export_format}{EXPORT_EXT.get(export_format, '.zip')}"

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
