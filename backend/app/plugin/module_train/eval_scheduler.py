import asyncio
import json
import os
import re
from datetime import datetime

from sqlalchemy import update

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import log

from .concurrency import get_train_semaphore
from .docker_utils import get_container_error_tail, pull_image, remove_container, run_container
from .gpu_pool import gpu_lease
from .model import TrainEval, TrainFramework, TrainModel, TrainStatus
from .paths import work_dir
from .task_executor import TaskExecutor
from .ws import broadcast_eval_log

DOCKER_IMAGE = "ultralytics/ultralytics:latest"

# 后台任务持有集合：防止 asyncio.create_task 返回的 Task 在进程退出时被 cancel
# 而留下半成品；任务完成/取消后自动丢弃引用。
_bg_tasks: set[asyncio.Task] = set()


#: ``tkiln val`` 结尾那行的主指标：``main indicator (mask_mAP50-95): 0.0``
_MAIN_INDICATOR_RE = re.compile(r"main indicator\s*\(([^)]+)\)\s*:\s*([-\d.eE+]+)")


def _spawn(coro) -> asyncio.Task:
    """创建后台任务并持有引用，完成/取消时自动丢弃。"""
    task = asyncio.create_task(coro)
    if task is not None:
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    return task


# PaddleX OCR 独立 eval 脚本（挂载容器 /scripts/paddlex_eval.py，det/rec 通用）。
# 加载 best.pdparams + Eval dataset，跑 program.eval，输出 EVAL_METRIC_JSON。
_PADDLEX_EVAL_SCRIPT = r'''
import sys, os, json
__dir__ = os.path.dirname(os.path.abspath(__file__))
_POCR_DIR = "/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR"
sys.path.append(__dir__)
sys.path.insert(0, _POCR_DIR)
sys.path.insert(0, os.path.abspath(os.path.join(_POCR_DIR, "..")))

import paddle
from ppocr.data import build_dataloader
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import build_post_process
from ppocr.metrics import build_metric
from ppocr.utils.save_load import load_model
import tools.program as program

config, device, logger, vdl_writer = program.preprocess(is_train=False)
model = build_model(config["Architecture"])
load_model(config, model, model_type=config["Architecture"]["model_type"])
valid_dataloader = build_dataloader(config, "Eval", device, logger)
post_process_class = build_post_process(config["PostProcess"], config["Global"])
eval_class = build_metric(config["Metric"])
metric = program.eval(
    model, valid_dataloader, post_process_class, eval_class,
    model_type=config["Architecture"]["model_type"],
)
print("EVAL_METRIC_JSON " + json.dumps(metric, ensure_ascii=False), flush=True)
'''


async def start_evaluation_scheduler():
    await EvalExecutor.start_recovery_loop()


async def start_evaluation(eval_id: int):
    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainEval)
            .where(TrainEval.id == eval_id, TrainEval.status != TrainStatus.RUNNING)
            .values(
                status=TrainStatus.RUNNING, started_at=datetime.now(), progress=10,
                metrics=None, metrics_log=None, best_metrics=None, last_metrics=None,
                log=None, error_log=None, finished_at=None,
            )
        )
        if result.rowcount == 0:
            # 影响 0 行：要么不存在，要么已在运行
            row = await db.get(TrainEval, eval_id)
            if row:
                raise Exception("评估任务正在运行，请勿重复启动")
            raise Exception(f"评估任务 {eval_id} 不存在")
    _spawn(EvalExecutor.run(eval_id))


async def resolve_eval_context(model_id: int) -> tuple[int | None, str, str]:
    """从产出该模型的训练任务推断 ``(annotation_task_id, mode, size)``。

    评估必须传 ``annotation_task_id`` 给导出，否则任务类型默认 detection，
    分类/分割评估会导出错误格式；PaddleX 规格也须与被评模型一致而非沿用
    eval 超参。无匹配训练任务时回退 ``(None, "det", "tiny")``。

    ⚠️ 两处 id 语义，历史上都踩过：

    1. ``model_id`` 是**版本行 id**，不是仓库 id。
    2. ``TrainTask.model_repo_id`` 这个字段名有误导——实测**它存的也是版本行
       id**（产出模型行的主键），不是仓库 id。逐条查过历史任务：
       torchkiln / ultralytics 的任务都是如此。

    所以匹配要**先按版本行 id 查**；为兼容万一真存了仓库 id 的老数据，查不到
    时再按 ``TrainModel.repo_id`` 兜一次。此前这里拿仓库 id 去比
    ``model_repo_id``，**永远匹配不到**，于是恒走回退：``annotation_task_id``
    丢成 None（分类/分割评估导出成 detection 格式）、规格丢成 tiny。
    """
    from sqlalchemy import desc, select

    from .framework_utils import framework_value
    from .model import TrainModel, TrainTask

    async with async_db_session() as db:
        model_row = await db.get(TrainModel, model_id)
        task = None
        if model_row:
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
        if task is None and model_row and model_row.repo_id:
            # 兜底：万一这行的 model_repo_id 真的存的是仓库 id
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_row.repo_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
    if not task:
        log.warning(
            f"评估上下文：模型版本 {model_id} 找不到产出它的训练任务，"
            f"回退 annotation_task_id=None / det / tiny——若被评模型不是 detection，"
            f"导出的标签格式会与训练时不一致")
        return (None, "det", "tiny")
    hp = task.hyperparams or {}
    mode = str(hp.get("mode", "det")).lower()
    size = str(hp.get("model_size", "tiny"))
    if framework_value(getattr(task, "framework", None)) == "torchkiln":
        # TorchKiln 的"规格"就是配置名（configs/... 的 model_name），直接回传
        return (task.annotation_task_id, str(hp.get("model") or ""), "tiny")
    return (
        task.annotation_task_id,
        mode if mode in ("det", "rec") else "det",
        size if size in ("tiny", "small", "medium") else "tiny",
    )


def _parse_yolo_cls_line(line: str) -> dict | None:
    """解析 YOLO 分类 val 汇总行：``all <img> <inst> <top1> <top5>``（5 列）。"""
    if re.match(r"^\s+all\s+", line):
        parts = line.strip().split()
        if len(parts) == 5:
            try:
                return {"top1": float(parts[3]), "top5": float(parts[4])}
            except ValueError:
                return None
    return None


def _accumulate_yolo_metrics(line: str, metrics: dict) -> dict | None:
    """累积解析 YOLO val 输出行到 ``metrics``。

    分类汇总行（5 列）走 ``_parse_yolo_cls_line``；检测汇总行（7 列）解析
    precision/recall/map50/map5095；per-class 行按检测格式累积。
    命中时返回当前 metrics 快照，否则 None。
    """
    m_cls = _parse_yolo_cls_line(line)
    if m_cls is not None:
        metrics.update(m_cls)
        return dict(metrics)
    if re.match(r"^\s+all\s+", line):
        parts = line.strip().split()
        if len(parts) >= 7:
            metrics.update({
                "precision": float(parts[3]) if parts[3] else 0,
                "recall": float(parts[4]) if parts[4] else 0,
                "map50": float(parts[5]) if parts[5] else 0,
                "map5095": float(parts[6]) if parts[6] else 0,
            })
            return dict(metrics)
    m = re.match(r"^\s+(\d+)\s+", line)
    if m:
        parts = line.strip().split()
        if len(parts) >= 7:
            cls_id = int(parts[0])
            metrics.setdefault("classes", {})[str(cls_id)] = {
                "precision": float(parts[3]) if parts[3] else 0,
                "recall": float(parts[4]) if parts[4] else 0,
                "map50": float(parts[5]) if parts[5] else 0,
                "map5095": float(parts[6]) if parts[6] else 0,
            }
            return dict(metrics)
    return None


async def stop_evaluation(eval_id: int):
    await EvalExecutor.stop(eval_id)


class EvalExecutor(TaskExecutor):
    name = "eval"
    task_kind = "eval"
    status_enum = TrainStatus
    model_class = TrainEval
    _concurrency = 1

    @classmethod
    async def _execute(cls, eval_id: int):
        container_id = None
        data_dir = None
        try:
            async with async_db_session() as db:
                eval_rec = await db.get(TrainEval, eval_id)
                if not eval_rec:
                    return

            # 有效框架：create_eval 未持久化 framework 时，从模型版本推断
            framework = eval_rec.framework or TrainFramework.ULTRALYTICS
            async with async_db_session() as db:
                model_row = await db.get(TrainModel, eval_rec.model_id)
                if model_row and model_row.framework:
                    framework = model_row.framework

            # ⚠️ 必须用 framework_value 归一化：PG 的 SAEnum 存的是**成员名**
            # （"TORKILN"），读回来是 str 而非枚举成员，直接 `== TrainFramework.X`
            # 恒为 False 会静默走 ultralytics 分支（train 侧已踩过这个坑）。
            from .framework_utils import framework_value

            fw = framework_value(framework)
            docker_image = DOCKER_IMAGE

            export_dir = work_dir("eval_output", eval_id)
            data_dir = os.path.join(export_dir, "data")
            model_dir = os.path.join(export_dir, "model")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(model_dir, exist_ok=True)

            # Export evaluation dataset（全量确定性 + 任务类型/规格从产出模型推断）
            from .exporter import prepare_eval_data_for_task
            await broadcast_eval_log(eval_id, "[eval] exporting dataset...")
            ann_task_id, paddlex_mode, paddlex_size = await resolve_eval_context(eval_rec.model_id)
            if fw == "torchkiln":
                # TorchKiln 读 data_dir + label_file_list（train.txt/val.txt 索引），
                # 图片/标签布局与 ultralytics 一致，故复用 YOLO 导出并补索引。
                await prepare_eval_data_for_task(
                    eval_rec.eval_dataset_id, eval_id, "ultralytics", data_dir,
                    annotation_task_id=ann_task_id,
                )
                from .exporter import _write_torchkiln_index
                _write_torchkiln_index(data_dir)
            else:
                await prepare_eval_data_for_task(
                    eval_rec.eval_dataset_id, eval_id, framework.value, data_dir,
                    annotation_task_id=ann_task_id, ocr_mode=paddlex_mode,
                )

            # Download model file from RustFS（统一解析：/export/ 导出产物自动回溯原始 best.pt）
            from .service import TrainService
            # model_id 是版本行 id（model_repo_id 是仓库 id），不可用仓库 id 冒充版本 id
            storage_path = await TrainService._resolve_model_storage(eval_rec.model_id)

            await broadcast_eval_log(eval_id, f"[eval] downloading model {storage_path}...")
            from app.utils.s3_client import s3_client
            model_data = s3_client.download_fileobj(storage_path)
            model_filename = storage_path.rsplit("/", 1)[-1]
            model_local_path = os.path.join(model_dir, model_filename)
            with open(model_local_path, "wb") as f:
                f.write(model_data.read())

            # Build command by framework
            hp = eval_rec.hyperparams or {}
            imgsz = hp.get("imgsz", 640)
            batch = hp.get("batch", 16)
            conf = hp.get("conf", 0.001)
            iou = hp.get("iou", 0.6)
            device = hp.get("device", "0")

            if fw == "paddlex":
                # PaddleX OCR eval：容器内脚本加载 best.pdparams 跑 program.eval（det/rec）
                # 规格取自产出该模型的训练任务（resolve_eval_context），不用 eval 超参
                mode = paddlex_mode
                size = paddlex_size
                cfg = (
                    f"configs/det/PP-OCRv6/PP-OCRv6_{size}_det.yml"
                    if mode == "det" else f"configs/rec/PP-OCRv6/PP-OCRv6_{size}_rec.yml"
                )
                eval_script = os.path.join(export_dir, "paddlex_eval.py")
                with open(eval_script, "w", encoding="utf-8") as f:
                    f.write(_PADDLEX_EVAL_SCRIPT)
                docker_image = "paddlex:latest"
                inner = (
                    f"cd /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR && "
                    f"PYTHONPATH=/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR "
                    f"python /scripts/paddlex_eval.py -c {cfg} -o "
                    f"Global.pretrained_model=/model/{model_filename} "
                    f"Global.save_model_dir=/output "
                    f"Eval.dataset.data_dir=/data/{mode}/dataset "
                    f"'Eval.dataset.label_file_list=[\"/data/{mode}/dataset/val.txt\"]' "
                    f"Eval.loader.num_workers=0"
                )
                cmd = ["bash", "-c", inner]
            elif fw == "torchkiln":
                # 自研平台：走 `tkiln val`，配置名取自**产出该模型的训练任务**
                # （resolve_eval_context 返回的第 2 项），保证与训练时同一套配置。
                tk_cfg = paddlex_mode  # resolve_eval_context 对 torchkiln 返回的就是配置名
                if not tk_cfg:
                    raise Exception(
                        "TorchKiln 评估找不到产出该模型的训练任务，无法确定配置名；"
                        "请确认该模型版本确实由 TorchKiln 训练产出")
                # ⚠️ 上面的 tk_cfg 是**模型名**（如 yolo11-seg），而 `tkiln val -c`
                # 只认 **configs/ 下的配置路径**。原样传会在容器里报
                # 「省略 <task> 时必须用 -c <config> 指定配置」——评估从来没跑通过的
                # 根因。借常驻元数据服务把模型名换成配置路径。
                from .torchkiln_client import TorchKilnClient
                async with TorchKilnClient() as _tk:
                    tk_cfg = await _tk.resolve_config_path(tk_cfg)
                opts = [
                    f"Global.pretrained_model=/model/{model_filename}",
                    "Global.save_model_dir=/output",
                    f"Global.imgsz={imgsz}",
                    f"Global.batch={batch}",
                    f"Global.conf={conf}",
                    f"Global.iou={iou}",
                    f"Global.device={device}",
                    # ⚠️ 路径是**挂载点根**：``data_dir`` 整个挂在 ``/data``，清单就在
                    # ``/data/val.txt``。写成 ``/data/dataset/val.txt``（PaddleX 那种
                    # 多一层 dataset/ 的结构）会 FileNotFoundError。
                    "Eval.dataset.data_dir=/data",
                    "Eval.dataset.label_file_list=[\"/data/val.txt\"]",
                    "Eval.loader.num_workers=0",
                    # ⚠️ `tkiln val` 的 task.build_datasets 会**同时**构造 Train 与 Eval
                    # 两个 dataset。只覆盖 Eval 的话，Train 仍用配置模板里的
                    # `datasets/seg_demo/train.txt` -> FileNotFoundError 直接崩。
                    # 评估导出是 for_eval=True（全量进 val 目录），所以 Train 指向
                    # 同一份数据即可，不会读到不存在的清单。
                    "Train.dataset.data_dir=/data",
                    "Train.dataset.label_file_list=[\"/data/val.txt\"]",
                ]
                cmd = ["tkiln", "val", "-c", str(tk_cfg), "-o"] + opts
                docker_image = hp.get("docker_image") or "torchkiln:0.1.0"
            else:
                cmd = [
                    "yolo", "val",
                    f"model=/model/{model_filename}",
                    "data=/data/dataset.yaml",
                    f"imgsz={imgsz}",
                    f"batch={batch}",
                    f"conf={conf}",
                    f"iou={iou}",
                ]

            await broadcast_eval_log(eval_id, f"[eval] pulling image {docker_image}...")
            await pull_image(docker_image)
            volumes = {
                data_dir: {"bind": "/data", "mode": "rw"},
                model_dir: {"bind": "/model", "mode": "ro"},
            }
            if fw == "paddlex":
                volumes[export_dir] = {"bind": "/scripts", "mode": "ro"}
                volumes[os.path.join(export_dir, "output")] = {"bind": "/output", "mode": "rw"}
                os.makedirs(os.path.join(export_dir, "output"), exist_ok=True)
            elif fw == "torchkiln":
                # tkiln val 写 Global.save_model_dir=/output
                volumes[os.path.join(export_dir, "output")] = {"bind": "/output", "mode": "rw"}
                os.makedirs(os.path.join(export_dir, "output"), exist_ok=True)
            # 全局 GPU 并发上限：与训练/预测共享同一信号量，避免同一张卡被并发抢占。
            # ⚠️ 信号量**只认本进程里排队的任务**，看不见别的框架、更看不见平台外
            #   占着卡的人——而训练走的是 gpu_pool（Redis + NVML）。两套排队互不知情
            #   必然撞卡，所以这里在信号量之后**再**向 gpu_pool 租一张够显存的卡：
            #   信号量是进程内的快速闸门（拒绝得快），gpu_pool 负责跨进程的精确判定。
            need_mem_gb = float((hp.get("resources") or {}).get("gpu_memory_gb")
                                or settings.TORKILN_GPU_MIN_FREE_GB)
            async with get_train_semaphore(), gpu_lease(eval_id, need_mem_gb) as lease:
                # 等待期间可能被取消：启动容器前再检查一次
                if cls._registry.get(eval_id, {}).get("cancel"):
                    return
                container = await run_container(
                    docker_image, cmd,
                    volumes=volumes,
                    gpu_id=lease.device_ids or device,
                    shm_size="4g" if fw in ("paddlex", "torchkiln") else None,
                    labels={"aistation.task_kind": cls.task_kind, "aistation.task_id": str(eval_id)},
                )
                container_id = container.id
                entry = cls._registry.get(eval_id) or {}
                entry.update({"container_id": container_id})
                cls._registry[eval_id] = entry

                metrics: dict = {}

                def _parse_paddlex_metrics(line: str) -> dict | None:
                    """解析 PaddleX eval 脚本输出的 EVAL_METRIC_JSON 行。"""
                    if "EVAL_METRIC_JSON" in line:
                        try:
                            data = json.loads(line.split("EVAL_METRIC_JSON", 1)[1].strip())
                            metrics.update(data)
                            return dict(metrics)
                        except Exception:
                            return None
                    return None

                def _parse_val_metrics(line: str) -> dict | None:
                    """解析 YOLO val 输出：分类 top1/top5 与检测汇总/per-class 均累积到 metrics。"""
                    return _accumulate_yolo_metrics(line, metrics)

                def _parse_torchkiln_metrics(line: str) -> dict | None:
                    """解析 ``tkiln val`` 的评估指标。

                    首选 ``EVAL_METRIC_JSON {...}`` 标记行（结构化、抗格式变动）；
                    没有标记时兜底解析它实际打印的那两行——
                    ``cur metric, box_mAP50: 0.0, mask_mAP50-95: 0.0, fps: 7.3``
                    与 ``main indicator (mask_mAP50-95): 0.0``。

                    ⚠️ 只认标记行的话，指标会**静默变成空**：任务显示成功、页面却
                    没有任何数值，看不出是评估没跑还是解析没匹配上。
                    """
                    if "EVAL_METRIC_JSON" in line:
                        try:
                            data = json.loads(line.split("EVAL_METRIC_JSON", 1)[1].strip())
                            metrics.update(data)
                            return dict(metrics)
                        except Exception:
                            return None
                    # 兜底 1：cur metric, k: v, k: v ...
                    if "cur metric" in line:
                        payload = line.split("cur metric", 1)[1].lstrip(" ,:")
                        for part in payload.split(","):
                            if ":" not in part:
                                continue
                            key, _, val = part.partition(":")
                            key, val = key.strip(), val.strip()
                            try:
                                metrics[key] = float(val)
                            except ValueError:
                                continue
                        return dict(metrics)
                    # 兜底 2：main indicator (mask_mAP50-95): 0.0
                    m = _MAIN_INDICATOR_RE.search(line)
                    if m:
                        metrics["main_indicator"] = m.group(1).strip()
                        try:
                            metrics["main_value"] = float(m.group(2))
                        except ValueError:
                            pass
                        return dict(metrics)
                    return None

                if fw == "torchkiln":
                    _parser = _parse_torchkiln_metrics
                elif fw == "paddlex":
                    _parser = _parse_paddlex_metrics
                else:
                    _parser = _parse_val_metrics

                await cls.follow_logs(
                    container_id,
                    os.path.join(export_dir, "eval.log"),
                    lambda line: broadcast_eval_log(eval_id, line),
                    _parser,
                )
                exit_code = await cls._get_exit_code(container)

            current_metrics = metrics or None

            if cls._registry.get(eval_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(eval_id, TrainStatus.CANCELLED, finished_at=datetime.now(), progress=100)
            elif exit_code == 0:
                await remove_container(container_id)
                await cls._mark_status(eval_id, TrainStatus.SUCCESS,
                                       metrics=current_metrics,
                                       metrics_log=[current_metrics] if current_metrics else None,
                                       best_metrics=current_metrics,
                                       last_metrics=current_metrics,
                                       finished_at=datetime.now(),
                                       progress=100)
            else:
                error_msg = (await get_container_error_tail(container_id)).strip()
                await remove_container(container_id)
                await cls._mark_status(eval_id, TrainStatus.FAILED,
                                       log=error_msg or "eval failed",
                                       error_log=error_msg or "eval failed",
                                       finished_at=datetime.now(), progress=100)

        except Exception as e:
            log.error(f"eval task {eval_id} failed: {e}")
            await cls._mark_status(eval_id, TrainStatus.FAILED, log=str(e), finished_at=datetime.now())
            # 失败后清理本次导出的 data 半成品目录（保留日志文件供排查）
            if data_dir:
                import shutil
                shutil.rmtree(data_dir, ignore_errors=True)
        finally:
            cls._registry.pop(eval_id, None)
            if container_id:
                await remove_container(container_id)
