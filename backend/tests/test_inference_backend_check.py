"""推理后端可用性校验测试。"""
import importlib

import pytest

from app.api.v1.module_video.inference import registry


def test_ensure_backend_raises_clear_error(monkeypatch):
    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "modeldeploy":
            raise ImportError("No module named 'modeldeploy'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    with pytest.raises(ImportError, match="modeldeploy"):
        registry.ensure_inference_backend()


def test_backend_available_returns_bool():
    assert isinstance(registry.inference_backend_available(), bool)
