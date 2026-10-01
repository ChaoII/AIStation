"""已退场框架（Ultralytics / PaddleX）的守卫测试。

退场这件事最容易的失败方式不是「忘了删」，而是**半年后有人顺手把分支加回来**——
尤其是看到 UI 上还留着一批历史数据，就以为「框架还支持」。所以这里把不变量钉死。

两个退场框架的**处理方式不同**，取决于退场时库里还有没有数据：

1. **执行通路确实没了**：``ensure_active`` 挡住各种大小写/带不带枚举的输入形式。
2. **PADDLEX 的枚举成员必须留着**：它的历史数据仍在库，而 ``SAEnum`` 按成员名
   反序列化，删成员会让读那些行直接报 ``invalid input value for enum``。
3. **ULTRALYTICS 已彻底移除**：项目未发布、处于开发态，历史 82 行数据已按显式 id
   白名单清空、PG 枚举值已 ``ALTER TYPE`` 移除、Python 枚举成员也已删除。
   这里额外断言它**不会**被人顺手加回来。
4. **新建入口当场拒绝**：训练/评估/预测/定时训练的 create 都返回明确提示。
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
        # 两个退场框架的枚举成员都已删除（数据也清干净了），但请求体里的 framework
        # 是字符串，客户端仍能传这些形式——所以守卫必须继续挡。
        "ultralytics", "ULTRALYTICS", "Ultralytics", "ultralytics/ultralytics",
        "ultralytics/ultralytics:latest",
        "paddlex", "PADDLEX", "PaddleX", "paddlex/paddlex:cpu",
    ],
)
def test_ensure_active_rejects_retired_frameworks(fw):
    """各种书写形式都要挡住——只挡小写是最常见的漏网方式。

    顺带把**镜像标签**形式也钉住：历史脏数据里出现过 ``framework`` 被填成整个镜像
    标签（多半是某处把 ``docker_image`` 误赋给了 framework）。不归一的话守卫认不出
    来会**放行**，退场框架就能绕过它——而这正是守卫唯一要拦的事。
    """
    with pytest.raises(_RetiredFramework):
        ensure_active(fw, action="评估")


@pytest.mark.parametrize("fw", ["torchkiln", "TORKILN", TrainFramework.TORKILN, None, ""])
def test_ensure_active_allows_active_framework(fw):
    """TORKILN 与空值（“未指定”）都要放行。"""
    ensure_active(fw, action="评估")


def test_is_retired_matches_framework_value_normalisation():
    """is_retired 必须复用 framework_value：PG 枚举存的是**成员名**（大写），
    直接 `== "paddlex"` 会恒为 False 而放行——本项目在多个分发点踩过这个坑。

    ⚠️ 退场框架的枚举成员已删，所以这里只能拿**裸字符串**验归一化；这恰恰是
    真实场景——从库里读出来、或者客户端传来的，就是这种形态。
    """
    assert framework_value("PADDLEX") == "paddlex"
    assert framework_value("ULTRALYTICS") == "ultralytics"
    assert is_retired("PADDLEX") is True
    assert is_retired("ULTRALYTICS") is True
    assert is_retired("TorchKiln") is False


def test_framework_enum_only_has_torchkiln():
    """``TrainFramework`` 必须**只剩** TORKILN。

    两个退场框架的历史数据都已按显式 id 白名单删净、PG 枚举值也已移除，所以成员
    不必保留。把它们加回来只会变成「枚举里有值但库里没有行」的孤儿——本项目就踩过
    这个坑（``PYTORCH_OCR_DET`` / ``PYTORCH_OCR_REC`` 正是这么攒出来的，
    ULTRALYTICS / PADDLEX 又续了两笔，这次一并清掉了）。

    同理，``init_app._TRAINFRAMEWORK_VALUES`` 也不能再把它们兜底补回 PG。
    """
    assert {m.name for m in TrainFramework} == {"TORKILN"}
    assert not hasattr(TrainFramework, "ULTRALYTICS")
    assert not hasattr(TrainFramework, "PADDLEX")

    init_app = MODULE_DIR.parents[1] / "scripts" / "init_app.py"
    line = next(
        ln for ln in init_app.read_text(encoding="utf-8").splitlines()
        if ln.startswith("_TRAINFRAMEWORK_VALUES")
    )
    assert '"TORKILN"' in line
    for gone in ("ULTRALYTICS", "PADDLEX", "PYTORCH_OCR_DET", "PYTORCH_OCR_REC"):
        assert f'"{gone}"' not in line, f"{gone} 已从 PG 枚举移除，别再兜底补回来"


def test_retired_message_states_three_things():
    """提示必须说清：已退场 / 改用什么 / **历史数据已经不在了**。

    缺任何一条用户都会误判：只说“不支持”会以为是 bug；只说“已退场”不知道
    接下来该干什么；最要紧的是**不能说历史权重还能下载**——数据已随退场删净，
    留这种承诺等于让用户去列表里翻、翻不到然后以为系统坏了。
    """
    for action in ("训练", "评估", "预测", "部署", "格式转换导出", "定时训练"):
        for fw in ("ULTRALYTICS", "PADDLEX"):
            msg = retired_message(fw, action=action)
            assert action in msg, f"{fw} 的提示里没提是哪个操作"
            assert "已退场" in msg
            assert "TorchKiln" in msg, "没告诉用户改用什么"
            assert "清理" in msg, "没说清历史数据已随退场清理"
            # 反向断言：假承诺不许出现
            assert "仍可" not in msg, f"{fw} 的数据已删净，不该承诺「仍可…」"
            assert "仍可正常下载" not in msg


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


def test_train_executor_class_stays_deleted():
    """``scheduler.TrainExecutor`` 必须**不存在**。

    它曾只为接住 ``framework='ULTRALYTICS'/'PADDLEX'`` 的历史任务行：让它们落到
    一个只会报「已退场」的执行器，而不是掉进无人处理的分支。那两个框架的数据已按
    显式 id 白名单删净、枚举值也已 ``ALTER TYPE`` 移除，所以它成了永远走不到的死
    分支。

    连带被它拖成死代码的三个 import 也一并删了（``TaskExecutor`` / ``broadcast_log``
    / ``find_task_containers``）——留着它们只会让 ruff 报 F401，或者更糟：
    让人误以为 scheduler 里还有别的执行器在用。

    退场框架的拒绝改由 service 层的 ``retired.ensure_active()`` 承担（另有测试）。
    """
    import app.plugin.module_train.scheduler as sched

    assert not hasattr(sched, "TrainExecutor"), \
        "TrainExecutor 只会拒绝不执行，且已无行可拒——别把它加回来"
    assert sched._executor_for(None).__name__ == "TorchKilnExecutor", \
        "训练执行器只剩 TorchKilnExecutor 一条通路"

    # 孤儿恢复也必须归到唯一那个执行器上。
    # ⚠️ 用 **AST** 判定而不是子串匹配：docstring 里提到 ``TrainExecutor`` 是在
    #    解释「它为什么被删」，那是正常文档，子串匹配会把文档判成「还在用」。
    tree = ast.parse(pathlib.Path(sched.__file__).read_text(encoding="utf-8"))
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert "TrainExecutor" not in classes, "scheduler.py 里还定义了 TrainExecutor"
    refs = [
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id == "TrainExecutor"
    ]
    assert not refs, f"scheduler.py 里还有对 TrainExecutor 的引用: {refs}"


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
    """``yolo predict`` 整条通路必须消失。

    ⚠️ 断言的是**符号不存在**，而不是「调用时报错」——更强也更准确：预测改走
    HTTP 作业通路后，命令行由 TorchKiln 服务侧的 ``build_predict_argv`` 拼，
    平台侧不再有任何命令构造入口。这条退场不变量就是它的守卫。

    退场框架的拦截改由 ``_execute`` 里的 ``ensure_active`` 承担（另有一条测试）。
    """
    import app.plugin.module_train.predict_executor as pe

    for gone in ("build_predict_cmd", "predict_gpu_id"):
        assert not hasattr(pe, gone), (
            f"{gone} 还在 predict_executor 里——预测已改走 HTTP 作业通路，"
            f"命令由 TorchKiln 服务侧拼，平台侧留一份必然漂移")

    # 也不能以「换个名字/私有名」的形式把命令拼装藏回来。
    # ⚠️ 用 **AST** 判定而不是子串匹配：docstring 里出现 ``tkiln predict`` 是
    #    正常的（解释契约），子串匹配会把文档也判成「还在拼命令」。
    tree = ast.parse(pathlib.Path(pe.__file__).read_text(encoding="utf-8"))
    cmd_literals = [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.List) and n.elts
        and isinstance(n.elts[0], ast.Constant) and n.elts[0].value == "tkiln"
    ]
    assert not cmd_literals, f"predict_executor 里还在拼 tkiln 命令: {cmd_literals}"


def test_predict_retired_framework_is_refused_by_ensure_active():
    """退场框架的预测必须在**入口**被挡住并说明原因。"""
    from app.plugin.module_train.retired import ensure_active

    for fw in ("ULTRALYTICS", "PADDLEX", "ultralytics", "paddlex"):
        with pytest.raises(Exception) as ei:
            ensure_active(fw, action="预测")
        msg = str(ei.value)
        assert "已" in msg, f"退场原因要写进报错: {msg}"

    # 唯一在用的框架必须放行
    ensure_active("TORKILN", action="预测")


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


def test_model_persist_no_longer_has_ultralytics_artifact_branch():
    """``model_persist`` 里读 ``best.pt`` 的分支必须跟着数据一起消失。

    那个分支存在的唯一理由是读回**历史 ultralytics 任务**的产物。数据已删，
    留着就成了永远走不到的死分支，而且会让人以为 ultralytics 权重还受支持。
    """
    tree = ast.parse((MODULE_DIR / "model_persist.py").read_text(encoding="utf-8"))
    literals = {
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert "best.pt" not in literals, "model_persist 里还有 ultralytics 的 best.pt 分支"
    assert not any("ultralytics" in v for v in literals), \
        "model_persist 里还有裸 ultralytics 字面量（框架名）"


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
    import app.plugin.module_train.schedule_service as sched_mod
    import app.plugin.module_train.service as service_mod

    for cls, names in (
        (service_mod.TrainService, ("create_task", "create_eval", "create_predict")),
        (sched_mod.ScheduleService, ("create_schedule", "update_schedule")),
    ):
        for name in names:
            fn = getattr(cls, name)
            src = inspect.getsource(fn)
            assert "ensure_active" in src, f"{cls.__name__}.{name} 没有退场守卫"


# ------------------------------------------------ 最优指标策略（随退场改写）


def test_best_metric_prefers_map5095_then_map50():
    """TorchKiln 的 main_indicator 由各任务配置自行声明，键名不固定，
    所以按候选优先级探测，而不是像以前那样给每个框架写一张映射表。"""
    log = [
        {"epoch": 1, "mAP50": 0.95, "mAP50-95": 0.40},
        {"epoch": 2, "mAP50": 0.60, "mAP50-95": 0.55},
    ]
    assert best_metric(log, "torchkiln")["epoch"] == 2
