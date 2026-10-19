"""模型扫描排除 submodules 的聚焦测试（Ruling R5）。

背景：`ImportUtil.find_models` 从 backend/ 全工程 `os.walk` 收集 `model.py`/
`models.py` 并逐个 import。Task 1 引入的 `backend/submodules/torchkiln/`
子模块里也有 model.py（如 kokoro 模型），其依赖 torch 等非核心依赖、
backend venv 未安装，若被扫描导入会 ImportError → 应用启动失败。
修复：`find_models` 的 `exclude_dirs` 排除 `submodules`。

纯逻辑测试，用 PYTEST_NO_APP=1 快速模式运行（不构造应用）。
"""
from app.core.base_model import MappedBase
from app.utils.import_util import ImportUtil

# submodule 内第三方代码的模块名前缀——任何 ORM 模型都不允许来自这些前缀
FORBIDDEN_MODULE_PREFIXES = ("torchkiln", "ptcore", "submodules")


def test_find_models_excludes_submodule_models():
    """find_models 不抛异常，且返回的模型类不得来自 submodule 第三方代码。"""
    # find_models 带 lru_cache：清缓存后强制真正重新扫描，避免命中旧结果
    ImportUtil.find_models.cache_clear()
    try:
        models = ImportUtil.find_models(MappedBase)
    finally:
        ImportUtil.find_models.cache_clear()

    # 基础项目的模型应能正常被扫到（防止排除规则过猛导致全空）
    assert len(models) > 0, "find_models 应至少扫到本项目自身的 ORM 模型"

    for model_cls in models:
        assert not model_cls.__module__.startswith(FORBIDDEN_MODULE_PREFIXES), (
            f"模型 {model_cls.__name__} 的模块 {model_cls.__module__} "
            f"来自 submodule 第三方代码，不应被扫描导入"
        )
