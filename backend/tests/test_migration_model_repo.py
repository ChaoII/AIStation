"""迁移工具函数测试。"""
from app.alembic.versions import __path__  # noqa: F401  (确保包可导入)


def test_normalize_version_variants():
    from importlib import import_module
    from pathlib import Path

    # 动态导入生成的迁移模块
    versions_dir = Path(__file__).parent.parent / "app" / "alembic" / "versions"
    mod_file = list(versions_dir.glob("*_model_repo_split.py"))[0]
    mod = import_module(f"app.alembic.versions.{mod_file.stem}")
    assert mod._normalize_version("v1") == "v1"
    assert mod._normalize_version("vv1") == "v1"
    assert mod._normalize_version("1") == "v1"
    assert mod._normalize_version(None) == "v1"
    assert mod._normalize_version("") == "v1"
