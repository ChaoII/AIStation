import asyncio
import os
import zipfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import pull_image
from .job_runner import (
    JobCancelled,
    cancelled,
    cleanup_registry,
    gpu_slot,
    mark_failed,
    run_and_follow,
    settle,
)
from .model import TrainFramework, TrainModel, TrainPredict, TrainStatus
from .paths import work_dir
from .retired import ensure_active
from .task_executor import TaskExecutor
from .ws import broadcast_predict_log

#: 自研平台的推理镜像（镜像内已装好 torch+CUDA 与 tkiln CLI）
DOCKER_IMAGE = "torchkiln:0.1.0"

# 后台任务持有集合：防止 asyncio.create_task 返回的 Task 在进程退出时被 cancel
# 而留下半成品；任务完成/取消后自动丢弃引用。
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """创建后台任务并持有引用，完成/取消时自动丢弃。"""
    task = asyncio.create_task(coro)
    if task is not None:
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    return task


def _cleanup_export_dir(export_dir: str | None) -> None:
    """失败后清理本次导出的临时输出目录（保留日志文件供排查）。"""
    if not export_dir:
        return
    import shutil
    shutil.rmtree(export_dir, ignore_errors=True)


def predict_gpu_id(device) -> str | None:
    """GPU 设备 id；cpu/空 → None（不请求 GPU）。"""
    if device is None:
        return None
    d = str(device).strip().lower()
    if d in ("", "cpu"):
        return None
    return str(device)


def build_predict_cmd(framework: str, model_filename: str, hp: dict) -> list[str]:
    """构建 ``tkiln predict`` 命令。

    只剩自研平台一条通路（Ultralytics / PaddleX 已退场，由 ``ensure_active``
    在入口挡住）。保留 ``framework`` 形参是为了让调用点不必为退场再改一轮签名，
    这里的断言顺带把"传了已退场框架"这类错误在开发期就暴露出来。
    """
    from .framework_utils import framework_value

    fw = framework_value(framework)
    if fw != "torchkiln":
        raise ValueError(
            f"build_predict_cmd 只支持 torchkiln，收到 {fw!r}（已退场框架）")

    conf = hp.get("conf", 0.25)
    iou = hp.get("iou", 0.45)
    device = hp.get("device", "0")
    # 配置由训练任务带下来（model 名）
    model_cfg = hp.get("tk_config") or hp.get("model") or ""
    if not model_cfg:
        # 兜底：用训练任务的 hyperparams.model（调用方应透传）
        model_cfg = hp.get("tk_model") or ""
    # ⚠️ ``tkiln predict`` 用的是 **argparse 风格**，不是 ``tkiln val`` 那套
    #    ``-o Global.xxx=`` 配置覆盖。契约见 ``tools/infer/predict_yolo.py``：
    #        -c/--config（必填） --weights（必填） --input（必填）
    #        --output（默认 output/yolo_result.jpg） --device
    #        -o/--opt（可选，nargs="*"）
    #
    #    原实现照着 val 的样子拼 ``-o Global.pretrained_model=...``，容器里直接
    #    argparse 报「the following arguments are required: --weights, --input」。
    #    这条链路自接入 TorchKiln 起就没跑通过（与同文件里另外两个 bug 同源：
    #    都没有 e2e 覆盖）。部署侧的 ``tkiln serve`` 一直是对的，可作对照。
    cmd = [
        "tkiln", "predict",
        "-c", str(model_cfg),
        "--weights", f"/model/{model_filename}",
        # /data 挂的是**整个数据集目录**，不是单张图
        "--input", "/data",
        # 目录输入时 --output 语义是**输出目录**（TorchKiln 侧 predict_yolo 遍历
        # 目录、按原文件名写出结果图）。模型只加载一次，不会按图起进程。
        "--output", "/output",
        "--device", "cpu" if str(device).strip().lower() in ("", "cpu") else "cuda:0",
    ]
    # conf / iou 是后处理阈值，imgsz 走配置的 image_size；统一用 -o 覆盖
    # （tkiln 的覆盖机制）。YAML 里没有的键 TorchKiln 会 warning 后照加，
    # 不影响运行——但那三行 warning 会混进 error_log，故只传确有意义的项。
    opts = [f"Global.conf={conf}", f"Global.iou={iou}"]
    cmd += ["-o", *opts]
    return cmd


def collect_result_images(output_dir: str) -> list[tuple[str, str]]:
    """收集容器输出目录下的结果图，返回 ``[(相对路径, 绝对路径)]``，按相对路径排序。

    契约：``tkiln predict`` 收到目录输入时，按输入的**相对路径**把每张图的可视化
    结果写到 ``--output`` 下，只把扩展名统一成 ``.jpg``。所以这里**递归**扫。

    两处曾各踩一个坑，都是「同名互相覆盖 / 静默丢结果」这一类：

    1. 原来只扫 ``output``/``results``/``vis``/``exp`` 四个固定子目录加顶层，
       而实际布局是 ``images/train``、``images/val`` —— 扫不到，结果恒为空；
       更早还有一个「找到文件后反而只去看 ``exp/``」的写法，同样静默返回空。
       那套猜测是为 Ultralytics/PaddleX 准备的，两者已退场，留着只会让人以为
       还有别的输出布局要兼容。
    2. RustFS key 曾用 ``basename``：``images/train/a.jpg`` 与 ``images/val/a.jpg``
       同名，后者会静默覆盖前者，表现为「结果数对不上」。

    返回相对路径（``/`` 分隔）正是为了让调用方能把它当唯一标识用。
    """
    found: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(output_dir):
        dirs.sort()
        for name in sorted(files):
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue
            abspath = os.path.join(root, name)
            rel = os.path.relpath(abspath, output_dir).replace(os.sep, "/")
            found.append((rel, abspath))
    found.sort(key=lambda it: it[0])
    return found


async def resolve_predict_tk_config(model_id: int) -> str | None:
    """反查产出该模型版本的**训练任务**，取其 TorchKiln 配置名。

    预测必须用与训练一致的配置（架构/imgsz/后处理都对不上就没有可比性），
    所以这里不猜、不让用户手填——直接回到训练任务要。

    ⚠️ 两处 id 语义，历史上都踩过（与 ``eval_scheduler.resolve_eval_context``
    同一个坑，那边早已修好、这边一直漏着）：

    1. ``model_id`` 是**版本行 id**，不是仓库 id。
    2. ``TrainTask.model_repo_id`` 字段名有误导——实测**它存的也是版本行 id**
       （产出模型行的主键），不是仓库 id。逐条查过历史任务：torchkiln /
       ultralytics 的任务都是如此。

    原实现拿 ``TrainModel.repo_id``（仓库 id）去比 ``model_repo_id``，**永远匹配
    不到** → 恒返回 None → 预测恒失败于「找不到产出该模型的训练任务」。这条链路
    自接入 TorchKiln 起就没跑通过；此前没有 e2e 覆盖预测，所以一直没暴露。

    匹配**先按版本行 id 查**；为兼容万一真存了仓库 id 的老数据，查不到时再按
    ``TrainModel.repo_id`` 兜一次。
    """
    from sqlalchemy import desc, select

    from .framework_utils import framework_value
    from .model import TrainModel, TrainTask

    async with async_db_session() as db:
        model_row = await db.get(TrainModel, model_id)
        if not model_row:
            return None
        task = (await db.execute(
            select(TrainTask).where(TrainTask.model_repo_id == model_id)
            .order_by(desc(TrainTask.id)).limit(1)
        )).scalar_one_or_none()
        if not task and model_row.repo_id:
            # 兜底：万一某些老数据真的存了仓库 id
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_row.repo_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
    if not task:
        return None
    if framework_value(getattr(task, "framework", None)) != "torchkiln":
        return None
    return str((task.hyperparams or {}).get("model") or "") or None


async def start_prediction_scheduler():
    """PredictExecutor 孤儿恢复循环（此前缺失，Task 4 修复）。"""
    await PredictExecutor.start_recovery_loop()


async def start_prediction(predict_id: int):
    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainPredict)
            .where(TrainPredict.id == predict_id, TrainPredict.status != TrainStatus.RUNNING)
            .values(status=TrainStatus.RUNNING, started_at=datetime.now(), progress=10)
        )
        if result.rowcount == 0:
            # 影响 0 行：要么不存在，要么已在运行
            row = await db.get(TrainPredict, predict_id)
            if row:
                raise Exception("预测任务正在运行，请勿重复启动")
            raise Exception(f"预测任务 {predict_id} 不存在")
    _spawn(PredictExecutor.run(predict_id))


async def stop_prediction(predict_id: int):
    await PredictExecutor.stop(predict_id)


class PredictExecutor(TaskExecutor):
    name = "predict"
    task_kind = "predict"
    status_enum = TrainStatus
    model_class = TrainPredict
    _concurrency = 1

    @classmethod
    async def _execute(cls, predict_id: int):
        container_id = None
        export_dir = None
        try:
            async with async_db_session() as db:
                pred = await db.get(TrainPredict, predict_id)
                if not pred:
                    return

            # 有效框架：create_predict 未持久化 framework 时，从模型版本推断
            framework = pred.framework or TrainFramework.TORKILN
            async with async_db_session() as db:
                model_row = await db.get(TrainModel, pred.model_id)
                if model_row and model_row.framework:
                    framework = model_row.framework

            # Ultralytics / PaddleX 的推理通路已退场：在这里挡住并说明原因，
            # 而不是继续往下走——否则会拉错镜像、把 .pth 当 best.pt 加载，
            # 报出与真实原因毫无关系的错。
            ensure_active(framework, action="预测")

            docker_image = DOCKER_IMAGE

            export_dir = work_dir("predict_output", predict_id)
            source_dir = os.path.join(export_dir, "source")
            output_dir = os.path.join(export_dir, "output")
            model_dir = os.path.join(export_dir, "model")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(model_dir, exist_ok=True)

            # 超参需在数据导出前取得，供 mode/device 使用
            hp = pred.hyperparams or {}
            device = hp.get("device", "0")

            # Prepare source images
            from app.utils.s3_client import s3_client
            if pred.source_type == "dataset":
                await broadcast_predict_log(predict_id, "[predict] exporting dataset images...")
                from .exporter import YOLO_LAYOUT, prepare_training_data_for_task
                # ⚠️ 必须传 **YOLO_LAYOUT**（目录布局名），不能传 framework.value。
                #    两者恰好都是 "ultralytics" 的时候看不出问题，但 TorchKiln 下
                #    framework.value 是 "torchkiln"，而 _export_core 只按**布局名**
                #    分发，于是直接抛「不支持的导出框架: torchkiln」——预测链路
                #    从接入 TorchKiln 起就一直是坏的，只是此前没有 e2e 覆盖到它。
                #    eval_scheduler 早就用的是 YOLO_LAYOUT，两边不一致才拖到现在。
                await prepare_training_data_for_task(
                    pred.source_dataset_id, predict_id, YOLO_LAYOUT, source_dir
                )
                # Remove label files and yaml, keep only images
                for root, _, files in os.walk(source_dir):
                    for f in files:
                        if f.endswith(".txt") or f == "dataset.yaml":
                            os.remove(os.path.join(root, f))
            else:
                await broadcast_predict_log(predict_id, "[predict] downloading uploaded images...")
                for img_key in (pred.source_images or []):
                    try:
                        data = s3_client.download_fileobj(img_key)
                        filename = img_key.rsplit("/", 1)[-1]
                        with open(os.path.join(source_dir, filename), "wb") as f:
                            f.write(data.read())
                    except Exception as e:
                        log.warning(f"skip image {img_key}: {e}")

            # Download model（统一解析：/export/ 导出产物自动回溯原始 best.pt）
            from .service import TrainService
            # model_id 是版本行 id（model_repo_id 是仓库 id），不可用仓库 id 冒充版本 id
            storage_path = await TrainService._resolve_model_storage(pred.model_id)

            await broadcast_predict_log(predict_id, f"[predict] downloading model {storage_path}...")
            model_data = s3_client.download_fileobj(storage_path)
            model_filename = storage_path.rsplit("/", 1)[-1]
            model_local_path = os.path.join(model_dir, model_filename)
            with open(model_local_path, "wb") as f:
                f.write(model_data.read())

            # 自研平台的推理镜像（镜像内已装好 torch+CUDA 与 tkiln CLI）
            docker_image = hp.get("docker_image") or "torchkiln:0.1.0"

            # 配置名回查训练任务：预测必须与训练用同一套配置
            tk_cfg = hp.get("tk_config") or await resolve_predict_tk_config(pred.model_id)
            if not tk_cfg:
                raise Exception(
                    "TorchKiln 预测找不到产出该模型的训练任务，无法确定配置名")
            # ⚠️ 上面拿到的是**模型名**（如 yolo11-seg），而 `tkiln predict -c`
            # 只认 configs/ 下的**配置路径**。借常驻元数据服务换一次，否则容器里
            # 会报「省略 <task> 时必须用 -c <config> 指定配置」。
            from .torchkiln_client import TorchKilnClient
            async with TorchKilnClient() as _tk:
                tk_cfg = await _tk.resolve_config_path(tk_cfg)
            hp = {**hp, "tk_config": tk_cfg, "model": tk_cfg}

            cmd = build_predict_cmd(framework.value, model_filename, hp)

            await broadcast_predict_log(predict_id, f"[predict] pulling image {docker_image}...")
            await pull_image(docker_image)
            # GPU 申请 + 「起容器→跟日志→等退出码」骨架已抽到 job_runner，与
            # eval_scheduler 共用。见 job_runner 模块 docstring：两处独立演进曾导致
            # 结果收集逻辑漂移（这里曾写成「找到文件后反而只去看 exp/」）。
            async with gpu_slot(cls, predict_id, hp) as lease:
                outcome = await run_and_follow(
                    cls, predict_id,
                    image=docker_image, cmd=cmd,
                    volumes={
                        source_dir: {"bind": "/data", "mode": "ro"},
                        model_dir: {"bind": "/model", "mode": "ro"},
                        output_dir: {"bind": "/output", "mode": "rw"},
                    },
                    gpu_id=lease.device_ids or predict_gpu_id(device),
                    log_path=os.path.join(export_dir, "predict.log"),
                    broadcast=lambda line: broadcast_predict_log(predict_id, line),
                )
                container_id = outcome.container_id

            result_images = []
            result_zip_path = None

            # 结果收集/上传/打包要在 mark SUCCESS **之前**完成，所以先算出
            # success_fields 再交给 settle 统一收尾。取消或失败时不收集——否则会
            # 白白把一批图传上 RustFS，而状态最终会被写成 CANCELLED/FAILED。
            was_cancelled = cancelled(cls, predict_id)
            success_fields: dict = {}
            if not was_cancelled and outcome.exit_code == 0:
                result_files = collect_result_images(output_dir)

                if result_files:
                    for rel, img_path in result_files:
                        rustfs_key = f"train/predict/{predict_id}/{rel}"
                        with open(img_path, "rb") as img_f:
                            s3_client.upload_fileobj(img_f, rustfs_key)
                        result_images.append(rustfs_key)

                    # Create ZIP（相对 output_dir 保留层级，便于对照输入图定位）
                    zip_path = os.path.join(export_dir, "results.zip")
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for _rel, fp in result_files:
                            zf.write(fp, _rel)
                    zip_rustfs_key = f"train/predict/{predict_id}/results.zip"
                    with open(zip_path, "rb") as zf:
                        s3_client.upload_fileobj(zf, zip_rustfs_key)
                    result_zip_path = zip_rustfs_key

                success_fields = {
                    "result_images": result_images or None,
                    "result_zip_path": result_zip_path,
                }

            await settle(
                cls, predict_id,
                was_cancelled=was_cancelled,
                container_id=container_id,
                exit_code=outcome.exit_code,
                error_tail=outcome.error_tail,
                failure_message="predict failed",
                success_fields=success_fields,
            )

        except JobCancelled:
            # 等待 GPU 期间被取消：容器从未起来，不能记失败也不能走收尾。
            # 状态留给 stop_prediction 置 CANCELLED（与拆分前的 return 行为一致）。
            log.info(f"[predict] 任务 {predict_id} 在等待 GPU 期间被取消，未启动容器")
            return

        except Exception as e:
            await mark_failed(cls, predict_id, e, kind="predict")
            # 失败后清理本次导出的临时输出目录（保留日志文件供排查）
            _cleanup_export_dir(export_dir)
        finally:
            await cleanup_registry(cls, predict_id, container_id)
