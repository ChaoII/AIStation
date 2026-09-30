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


