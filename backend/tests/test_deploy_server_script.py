"""部署服务脚本生成测试：规格驱动 cfg、rec 检测框裁剪、超参透传、按需安装依赖。"""

import asyncio

from app.plugin.module_train.deploy_executor import (
    _generate_paddlex_server_script,
    _generate_server_script,
    resolve_deploy_spec,
)


def test_paddlex_script_uses_spec():
    script = _generate_paddlex_server_script("key123", "cpu", mode="rec", size="medium")
    assert "PP-OCRv6_medium_rec.yml" in script
    # rec 必须裁剪检测框后识别（不是整图）：断言调用点，而非仅断言函数定义存在
    assert "_rec_text(crop)" in script
    assert "_rec_text(img)" not in script
    assert "key123" in script
    # 实际部署规格通过 /health 暴露，便于诊断
    assert '"mode": MODE' in script and '"size": SIZE' in script


def test_paddlex_script_det_spec_and_crop_helper():
    script = _generate_paddlex_server_script("k", "cpu", mode="det", size="tiny")
    assert "PP-OCRv6_tiny_det.yml" in script
    # 裁剪辅助函数必须定义在生成的脚本内
    assert "def _crop_box(" in script
    assert "cv2.boundingRect" in script


def test_ultralytics_script_embeds_hyperparams():
    script = _generate_server_script("k", "cpu", conf=0.3, iou=0.5, imgsz=960)
    assert "conf=0.3" in script
    assert "iou=0.5" in script
    assert "imgsz=960" in script


def test_scripts_defer_pip_install_until_import_fails():
    """两个脚本都不得在启动时无条件 pip install，应在 import 失败时兜底。"""
    for script in (
        _generate_server_script("k", "cpu"),
        _generate_paddlex_server_script("k", "cpu"),
    ):
        assert "except ImportError" in script


def test_resolve_deploy_spec_prefers_deploy_hyperparams():
    class FakeDeploy:
        hyperparams = {"mode": "rec", "model_size": "medium"}

    mode, size = asyncio.run(resolve_deploy_spec(FakeDeploy(), None))
    assert (mode, size) == ("rec", "medium")


def test_resolve_deploy_spec_defaults_invalid_values(monkeypatch):
    import app.plugin.module_train.deploy_executor as de

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def execute(self, _stmt):
            return _Result()

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(de, "async_db_session", lambda: _Ctx())

    class FakeDeploy:
        model_id = 1
        hyperparams = {"mode": "bogus", "model_size": "huge"}

    mode, size = asyncio.run(resolve_deploy_spec(FakeDeploy(), None))
    assert (mode, size) == ("det", "tiny")


def test_resolve_deploy_spec_normalizes_capitalized_size(monkeypatch):
    """非法但非空的规格（如 "Small"）应归一化回退，而非被收紧成 tiny。"""
    import app.plugin.module_train.deploy_executor as de

    class _Task:
        hyperparams = {"mode": "rec", "model_size": "small"}

    class _Result:
        def scalar_one_or_none(self):
            return _Task()

    class _Session:
        async def execute(self, _stmt):
            return _Result()

    class _Ctx:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(de, "async_db_session", lambda: _Ctx())

    class FakeDeploy:
        model_id = 1
        hyperparams = {"model_size": "Small"}

    mode, size = asyncio.run(resolve_deploy_spec(FakeDeploy(), None))
    assert size == "small"
    assert (mode, size) == ("rec", "small")
