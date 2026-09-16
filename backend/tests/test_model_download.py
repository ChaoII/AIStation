"""模型下载目标解析测试。

`resolve_download_target` 决定下载时应命中的对象键与真实格式：
- 模型已导出且确定性导出产物存在 -> 返回导出键与导出格式；
- 导出产物缺失 -> 回退原始权重与真实格式 "pytorch"；
- 模型本身即为原始格式 -> 始终返回原始权重与 "pytorch"。
"""
import asyncio
import io

from app.plugin.module_train import export_service
from app.plugin.module_train.export_service import resolve_download_target
from app.utils.s3_client import s3_client


def test_download_target_export_when_exists():
    """导出产物存在时命中确定性导出键。"""
    model = {"id": 5, "storage_path": "train/models/task_1/best.pt", "format": "onnx"}
    key, fmt = resolve_download_target(model, exists_fn=lambda k: k.endswith("best.onnx"))
    assert key == "train/models/model_5/export/best.onnx"
    assert fmt == "onnx"


def test_download_target_original_when_export_missing():
    """导出产物缺失时回退原始权重并返回真实格式 pytorch。"""
    model = {"id": 5, "storage_path": "train/models/task_1/best.pt", "format": "onnx"}
    key, fmt = resolve_download_target(model, exists_fn=lambda k: False)
    assert key == "train/models/task_1/best.pt"
    assert fmt == "pytorch"


def test_download_target_pytorch_original():
    """原始格式模型始终返回原始权重与 pytorch。"""
    model = {"id": 5, "storage_path": "train/models/task_1/best.pt", "format": "pytorch"}
    key, fmt = resolve_download_target(model, exists_fn=lambda k: True)
    assert key == "train/models/task_1/best.pt" and fmt == "pytorch"


async def _fake_run_export_container(image, cmd, volumes):
    """替身：跳过真实容器导出，直接返回成功。"""
    return 0, ""


class _FakeAsyncSession:
    """替身：跳过真实数据库写入，仅满足异步上下文协议。"""

    def begin(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, *args, **kwargs):
        return None


def test_directory_format_download_url_uses_uploaded_key(monkeypatch, tmp_path):
    """目录格式（如 openvino）：下载链接必须指向真实上传对象键，而非 .zip 变体。

    回归背景：目录格式打包为 zip 上传到无后缀键 `.../export/best`，若下载链接
    被错误地加上 `.zip` 后缀，会指向并不存在的对象而 404。
    """
    # 构造一个真实存在的导出目录，使目录分支可被打包
    export_dir = tmp_path / "openvino_model"
    export_dir.mkdir()
    (export_dir / "model.xml").write_text("<net/>", encoding="utf-8")

    uploaded_key = {}
    presigned_key = {}

    monkeypatch.setattr(
        s3_client,
        "download_fileobj",
        lambda key, env=None: io.BytesIO(b"\x80\x02" + b"0" * 16),
    )
    monkeypatch.setattr(
        s3_client,
        "upload_fileobj",
        lambda fileobj, key, env=None: uploaded_key.update(key=key),
    )
    monkeypatch.setattr(
        s3_client,
        "presigned_url",
        lambda key, env=None: presigned_key.update(key=key) or "https://rustfs/download",
    )
    monkeypatch.setattr(export_service, "_run_export_container", _fake_run_export_container)
    monkeypatch.setattr(export_service, "_find_exported_file", lambda *a, **k: str(export_dir))
    monkeypatch.setattr("app.core.database.async_db_session", _FakeAsyncSession())

    result = asyncio.run(
        export_service.export_model_to_format(
            model_id=5,
            storage_path="train/models/task_1/best.pt",
            export_params={"format": "openvino"},
            model_name="m",
            created_id=1,
            dataset_id=None,
            framework=None,
        )
    )

    # 上传键与预签名键必须一致，且为无后缀的真实对象键
    assert uploaded_key["key"] == "train/models/model_5/export/best"
    assert presigned_key["key"] == uploaded_key["key"]
    assert presigned_key["key"].endswith("export/best")
    assert result["download_url"] == "https://rustfs/download"
    # 仅用户可见文件名保留 .zip 后缀
    assert result["file_name"].endswith(".zip")
