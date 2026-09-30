"""已退场框架（Ultralytics / PaddleX）的守卫与历史可读性测试。

退场这件事最容易的失败方式不是"忘了删"，而是**半年后有人顺手把分支加回来**——
尤其是看到 ``TrainFramework.ULTRALYTICS`` 还在、UI 上还显示着历史任务，
就以为"框架还支持"。所以这里把三条不变量钉死：

1. **执行通路确实没了**：``ensure_active`` 挡住四种大小写/带不带枚举的输入形式。
2. **历史数据仍可读**：``TrainFramework`` 的枚举成员与 PG 枚举值必须留着，
   否则 92 个 ULTRALYTICS 模型反序列化失败，整个模型列表页打不开。
3. **新建入口当场拒绝**：训练/评估/预测/定时训练的 create 都返回明确提示。
"""

import ast
import inspect
import pathlib

import pytest

from app.plugin.module_train import retired
from app.plugin.module_train.framework_utils import framework_value
from app.plugin.module_train.metrics import best_metric
from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.retired import (
    ACTIVE_FRAMEWORK,
    RETIRED_FRAMEWORKS,
    _RetiredFramework,
    ensure_active,
    is_retired,
    retired_message,
)

MODULE_DIR = pathlib.Path(retired.__file__).parent


# ---------------------------------------------------------------- 守卫本身


@pytest.mark.parametrize(
    "fw",
    [
        "ultralytics", "ULTRALYTICS", "Ultralytics", "ULTRALYTICS",
        "paddlex", "PADDLEX", "PaddleX",
        TrainFramework.ULTRALYTICS, TrainFramework.PADDLEX,
    ],
)
def test_ensure_active_rejects_retired_frameworks(fw):
    """四种书写形式都要挡住——只挡小写是最常见的漏网方式。"""
    with pytest.raises(_RetiredFramework):
        ensure_active(fw, action="评估")


@pytest.mark.parametrize("fw", ["torchkiln", "TORKILN", TrainFramework.TORKILN, None, ""])
def test_ensure_active_allows_active_framework(fw):
    """TORKILN 与空值（"未指定"）都要放行：历史评估记录里有 framework=None 的行。"""
    ensure_active(fw, action="评估")


def test_is_retired_matches_framework_value_normalisation():
    """is_retired 必须复用 framework_value：PG 枚举存的是成员名（"ULTRALYTICS"），
    直接 `== "ultralytics"` 会恒为 False 而放行——本项目在多个分发点踩过这个坑。"""
    assert framework_value(TrainFramework.ULTRALYTICS) == "ultralytics"
    assert is_retired(TrainFramework.ULTRALYTICS) is True
    assert is_retired("ULTRALYTICS") is True
    assert is_retired("TorchKiln") is False


def test_retired_message_states_three_things():
    """提示必须说清：已退场 / 改用什么 / 历史数据还在。

    缺任何一条用户都会误判：只说"不支持"会以为是 bug，只说"已退场"不知道
    怎么办，只说"请重训"会以为历史模型连权重都下载不了了。
    """
    for action in ("训练", "评估", "预测", "部署", "格式转换导出", "定时训练"):
        msg = retired_message("ULTRALYTICS", action=action)
        assert action in msg, f"{action} 的提示里没提是哪个操作"
        assert "已退场" in msg
        assert "TorchKiln" in msg, "没告诉用户改用什么"
        assert "下载" in msg, "没说明历史权重仍可下载"


def test_retired_uses_its_own_exception_type():
    """单独一个异常类型：调用方要能精确捕获并给 4xx，而不是混进 500。"""
    assert issubclass(_RetiredFramework, Exception)
    assert not issubclass(_RetiredFramework, (ValueError, RuntimeError, KeyError))


def test_module_constants():
    assert RETIRED_FRAMEWORKS == ("ultralytics", "paddlex")
    assert ACTIVE_FRAMEWORK == "torchkiln"


# ------------------------------------------------- 不变量 1：执行通路没有回来


def test_retired_framework_executors_are_gone():
    """PaddleX 执行器文件必须不存在（它是整文件都为 PaddleX 的）。"""
    assert not (MODULE_DIR / "paddlex_executor.py").exists(), \
        "PaddleX 执行器被加回来了——若要恢复请先想清楚它依赖的镜像还在不在"


def test_no_bash_c_string_concatenation_in_module():
    """模块里不应再有 ``bash -c "..."`` 字符串拼接。

    那是命令注入面：PaddleX 通路靠它拼 shell 命令，因此才有 ``safe_base_model_name``
    这个白名单校验。TorchKiln 全部用 list 形式传参，注入面随之消失——但也可能
    被人顺手写回 bash 拼接，届时的注入防护已一并删除。
    """
    offenders = []
    for py in MODULE_DIR.glob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "bash" in line and "-c" in line and "paddlex" in line.lower():
                offenders.append(f"{py.name}:{i}")
    assert not offenders, f"仍有 PaddleX 的 bash -c 拼接: {offenders}"


@pytest.mark.parametrize(
    "filename, forbidden",
    [
        ("scheduler.py", ("_build_ultralytics_cmd", "_build_paddlex_ocr_cmd",
                          "_build_cmd", "_parse_epoch", "resolve_base_model",
                          "safe_base_model_name", "_ensure_model_file")),
        ("eval_scheduler.py", ("_PADDLEX_EVAL_SCRIPT", "_parse_yolo_cls_line",
                               "_accumulate_yolo_metrics")),
        ("predict_executor.py", ("ocr_rec",)),
        ("deploy_executor.py", ("_generate_server_script",
                                "_generate_paddlex_server_script", "resolve_deploy_spec")),
        ("export_service.py", ("_build_export_cmd", "_find_exported_file",
                               "EXPORT_PARAMS_BY_FORMAT")),
    ],
)
def test_deleted_builders_stay_deleted(filename, forbidden):
    """逐个模块断言已删符号不存在（AST 层面，不受注释/字符串干扰）。

    用 AST 而不是字符串查找：文档字符串里提到"原先这里有 _build_ultralytics_cmd"
    是正常的（我们留了解释性注释），字符串搜索会误判。
    """
    tree = ast.parse((MODULE_DIR / filename).read_text(encoding="utf-8"))
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
    hit = [name for name in forbidden if name in defined]
    assert not hit, f"{filename} 里已退场的符号又回来了: {hit}"


def test_yolo_ultralytics_predict_command_is_gone():
    """``yolo predict`` 整条通路必须消失，且 build_predict_cmd 对退场框架主动报错。"""
    from app.plugin.module_train.predict_executor import build_predict_cmd

    with pytest.raises(ValueError, match="torchkiln"):
        build_predict_cmd("ultralytics", "best.pt", {})
    with pytest.raises(ValueError, match="torchkiln"):
        build_predict_cmd("paddlex", "best_accuracy.pdparams", {})

    cmd = build_predict_cmd("torchkiln", "best_accuracy.pth", {"tk_config": "configs/det/x.yml"})
    assert cmd[0] == "tkiln" and cmd[1] == "predict"
    assert not any("yolo" == c for c in cmd), "命令里还混着 yolo"


# --------------------------------------- 不变量 2：历史数据必须仍可读


def test_framework_enum_keeps_retired_members():
    """⚠️ 这是本文件最重要的一条。

    SQLAlchemy 的 ``SAEnum(TrainFramework)`` 按**成员名**反序列化。删掉
    ULTRALYTICS/PADDLEX 成员，读取那 92 个模型行会直接报
    ``invalid input value for enum``，模型列表页 500——数据还在，但读不出来，
    等于等于丢了。
    """
    names = {e.name for e in TrainFramework}
    assert {"ULTRALYTICS", "PADDLEX", "TORKILN"} <= names


def test_init_app_still_backfills_retired_enum_values():
    """PG 枚举里也必须留着 PADDLEX / ULTRALYTICS（既有表的行靠它反序列化）。"""
    # MODULE_DIR = backend/app/plugin/module_train，往上两级是 app，再拼 scripts/
    init_app = MODULE_DIR.parents[1] / "scripts" / "init_app.py"
    src = init_app.read_text(encoding="utf-8")
    assert "_TRAINFRAMEWORK_VALUES" in src
    # 只匹配定义那一行，避免命中注释里对它的解释
    line = next(ln for ln in src.splitlines() if ln.startswith("_TRAINFRAMEWORK_VALUES"))
    assert '"PADDLEX"' in line and '"ULTRALYTICS"' in line and '"TORKILN"' in line


def test_defaults_no_longer_point_at_retired_frameworks():
    """ORM 默认值不能是已退场框架。

    默认值是历史脏数据的根源：``create_eval``/``create_predict`` 在
    ``framework`` 为空时会用 ORM 默认值填充，于是 2 条评估 + 3 条预测被记成
    ULTRALYTICS——哪怕实际跑的是 TorchKiln。
    """
    from app.plugin.module_train.model import TrainDeploy, TrainEval, TrainPredict

    for cls in (TrainEval, TrainPredict, TrainDeploy):
        col = cls.__table__.c.framework
        default = getattr(col.default, "arg", None)
        assert default is TrainFramework.TORKILN, \
            f"{cls.__name__}.framework 的 ORM 默认值仍是 {default}"


def test_export_download_path_still_works_for_retired_models():
    """格式转换导出退场了，但**原始权重下载**必须仍可用。

    ``resolve_download_target`` 是模型下载功能走的路，与导出格式无关；
    退场时若连它一起砍掉，用户连历史权重都拿不回来。
    """
    from app.plugin.module_train import export_service

    assert callable(export_service.resolve_download_target)
    src = inspect.getsource(export_service.resolve_download_target)
    assert "EXPORT_EXT" in src, "下载目标仍需按扩展名拼 RustFS key"


# --------------------------------------- 不变量 3：新建入口当场拒绝


def test_create_entrypoints_guard_retired_framework():
    """训练/评估/预测/定时训练/部署的创建入口都必须调 ensure_active。

    AST 层面检查：靠「服务里出现了 ensure_active 调用」来钉住，比断言行为更稳
    （这些函数都要 DB 会话，测行为成本高且脆弱）。
    """
    guards = {
        "service.py": 3,      # create_task / create_eval / create_predict
        "schedule_service.py": 2,  # create_schedule / update_schedule
    }
    for filename, expected in guards.items():
        src = (MODULE_DIR / filename).read_text(encoding="utf-8")
        n = src.count("ensure_active(")
        assert n >= expected, f"{filename} 只有 {n} 处 ensure_active，应至少 {expected} 处"


def test_service_guards_are_inside_create_methods():
    """守卫必须在 create_* 方法体内，而不是文件里的注释或 import 行。"""
    import app.plugin.module_train.service as service_mod
    import app.plugin.module_train.schedule_service as sched_mod

    for cls, names in (
        (service_mod.TrainService, ("create_task", "create_eval", "create_predict")),
        (sched_mod.ScheduleService, ("create_schedule", "update_schedule")),
    ):
        for name in names:
            fn = getattr(cls, name)
            assert "ensure_active" in inspect.getsource(fn), f"{cls.__name__}.{name} 没有退场守卫"


# ------------------------------------------------ 最优指标策略（随退场改写）


def test_best_metric_prefers_map5095_then_map50():
    """TorchKiln 的 main_indicator 由各任务配置自行声明，键名不固定，
    所以按候选优先级探测，而不是像以前那样给每个框架写一张映射表。"""
    log = [
        {"epoch": 1, "mAP50": 0.95, "mAP50-95": 0.40},
        {"epoch": 2, "mAP50": 0.60, "mAP50-95": 0.55},
    ]
    assert best_metric(log, "torchkiln")["epoch"] == 2


def test_best_metric_still_serves_ultralytics_log_shape():
    """历史任务的 metrics_log 里是 map50/map5095（小写、无连字符），
    最优指标计算仍要认它们——否则回填时挑不出正确的轮次。"""
    log = [
        {"epoch": 1, "map50": 0.3, "map5095": 0.1},
        {"epoch": 2, "map50": 0.6, "map5095": 0.3},
    ]
    assert best_metric(log, "ultralytics")["epoch"] == 2
