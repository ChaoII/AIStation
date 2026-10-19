"""simple mode 四链路 smoke 脚本（一键验证 train → eval → predict → export）。

用途
----
用合成小数据集（128×128 PNG，YOLO txt 归一化标签），以本地 subprocess
方式跑通 TorchKiln ``simple_run`` 的四条链路，并把事件通过本地 HTTP 回调
（``X-Torchkiln-Token`` 鉴权）收集回来做**事件级断言**（不只信退出码）：

    train    yolo11-det，1 epoch，batch 2，8 图训练 / 3 图验证
    eval     加载训练产物权重，对验证集出指标（main_value 可解析）
    predict  加载权重对 3 张图推理，逐图 ``predict`` 进度事件
    export   子进程 ``tools/export.py`` 导出 ONNX（交付标准，``model.onnx``；
             TorchScript 仅兼容保留）

设备
----
**默认用 GPU**（``resources.gpu=1``、``Global.device=cuda:0``）：
- ``--cpu`` 强制 CPU（``gpu=0``、``Global.device=cpu``）；
- 无 CUDA（``torch.cuda.is_available()`` 为 False）且未显式指定时，
  打印提示并**自动回退 CPU**（跨机器通用）；
- 汇总输出中明确标注本次运行设备（GPU 型号 / CPU）。

前置依赖（simple extra）
------------------------
本脚本要求 backend 虚拟环境已安装 simple 依赖组（torch / torchvision /
torchkiln / cv2 / yaml 缺一不可）；缺失时打印中文引导并 **exit 2**（不算
smoke 失败）::

    cd backend
    uv sync --extra simple

说明：
- ``uv sync --extra simple`` 装的是清华镜像的 **CPU 版 torch**（体积较大，
  需耐心等待）；本机要跑 GPU 需另装 CUDA 轮子（会覆盖 CPU 版），例如本机
  （阿里云 pytorch-wheels/cu132）：::

      uv pip install --no-deps --find-links \
          https://mirrors.aliyun.com/pytorch-wheels/cu132/ \
          "torch==2.14.1+cu132" "torchvision==0.29.1+cu132"

  ⚠️ **之后不要执行 ``uv sync``**：锁文件里记的是 PyPI 的 CPU 版 torch，
  重新 sync 会用 CPU 轮子覆盖 CUDA 版；补包请用 ``uv pip install``。
- ``torchkiln`` 来自本地 submodule（``backend/submodules/torchkiln``），
  由 uv 以本地路径安装，**不要**再 pip 装别的版本。

运行
----
在 backend 目录下用项目虚拟环境的解释器运行（Windows 原生可跑，不依赖
bash/docker）::

    cd backend
    .venv/Scripts/python.exe scripts/smoke_simple_mode.py            # 默认 GPU
    .venv/Scripts/python.exe scripts/smoke_simple_mode.py --cpu      # 强制 CPU

Linux 同理：``.venv/bin/python scripts/smoke_simple_mode.py``。

通过标准
--------
每条链路：退出码 0、有且仅 1 条 ``end`` 事件且 ``exit_reason`` ∈
{finished, early_stop, already_complete}；此外：
- train：≥1 条 ``step``、≥1 条 ``eval`` 事件，产物目录存在
  ``best_accuracy.pth``（或 ``final.pth`` / ``latest.pth`` 兜底）；
- eval：≥1 条 ``eval`` 事件且 ``main_value`` 可解析为数字；
- predict：≥1 条 ``predict`` 事件且末条 ``images_done == images_total``，
  输出目录逐图落 ``.jpg``；
- export：``output_dir`` 存在且包含 **ONNX 交付产物 ``model.onnx``（存在
  且非空）**，``end.onnx_path`` 指向该文件（TorchScript/推理权重仅作兼容
  保留，不再是通过依据）。

末尾打印每链路一行汇总（链路 / 退出码 / end / 事件计数 / 耗时 / PASS|FAIL，
含运行设备与总耗时）与 ``ALL PASS`` / ``FAILED``：全过 exit 0，任一失败
exit 1。

产物位置
--------
全部落在临时工作区 ``tempfile.mkdtemp(prefix="tk-smoke-")`` 下
（数据集 / spec JSON / 各链路输出）；**默认结束即清理**并打印路径，
``--keep`` 保留现场便于排查。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# ---------------------------------------------------------------- 常量
#: backend 根（本脚本位于 backend/scripts/ 下）
BACKEND_ROOT = Path(__file__).resolve().parents[1]
#: TorchKiln submodule 仓库根（simple_run 的 --repo-root 与子进程 cwd）
REPO_ROOT = BACKEND_ROOT / "submodules" / "torchkiln"

#: yolo11-det 配置名（相对 TorchKiln configs/ 根，走 resolve_config）
CONFIG_NAME = "yolo/yolo11-det.yml"

IMG_SIZE = 128          # 训练/评估/导出统一 128（32 的倍数，smoke 要快）
BATCH = 2
N_TRAIN = 8             # 训练图数（batch 2 → 每 epoch 4 个 step）
N_VAL = 3               # 验证图数
N_PREDICT = 3           # 推理图数
LINK_TIMEOUT = 1800     # 单链路 subprocess 超时（秒）
SETTLE_SEC = 3.0        # 进程退出后等事件回调到齐的宽限（秒）

#: 依赖守卫：缺任一 → 中文引导 + exit 2
REQUIRED_DEPS = ("torch", "torchvision", "torchkiln", "cv2", "yaml")

#: 合法终态（end 事件 exit_reason）
VALID_END_REASONS = {"finished", "early_stop", "already_complete"}

#: 四链路固定顺序
LINK_ORDER = ("train", "eval", "predict", "export")


# ---------------------------------------------------------------- 依赖守卫
def ensure_deps() -> None:
    """检查 simple 依赖组是否齐全；缺失打印中文引导并 exit 2（不算失败）。"""
    missing = [m for m in REQUIRED_DEPS if importlib.util.find_spec(m) is None]
    if not missing:
        return
    print("[依赖缺失] simple 模式依赖未安装完整，缺少：{}。".format(" / ".join(missing)))
    print("请先在 backend 目录下安装（国内清华镜像已配置，无需另加源）：")
    print("")
    print("    cd backend")
    print("    uv sync --extra simple")
    print("")
    print("说明：")
    print("  - uv sync 默认安装清华镜像的 torch CPU 轮子（体积较大，请耐心等待）；")
    print("    本机要跑 GPU 需另装 CUDA 轮子（会覆盖 CPU 版），例如：")
    print("      uv pip install --no-deps --find-links "
          "https://mirrors.aliyun.com/pytorch-wheels/cu132/ "
          "\"torch==2.14.1+cu132\" \"torchvision==0.29.1+cu132\"")
    print("    ⚠️ 装 CUDA 轮子后不要再执行 uv sync（锁文件记的是 CPU 版，")
    print("    重新 sync 会用 CPU 轮子覆盖 CUDA 版）；补包请用 uv pip install。")
    print("  - torchkiln 来自本地 submodule（backend/submodules/torchkiln），")
    print("    由 uv 以本地路径安装，不要从 PyPI 另装。")
    print("")
    print("exit 2（未安装依赖不算 smoke 失败）")
    sys.exit(2)


# ---------------------------------------------------------------- 设备选择
def resolve_device(force_cpu: bool) -> tuple:
    """返回 (use_gpu, 设备描述)。

    - ``--cpu`` 强制 CPU；
    - 否则 ``torch.cuda.is_available()`` 可用 → GPU（默认）；
    - 无 CUDA → 打印提示并自动回退 CPU（跨机器通用）。
    """
    import torch

    if force_cpu:
        return False, "CPU（--cpu 指定）"
    try:
        cuda_ok = bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001
        cuda_ok = False
    if cuda_ok:
        try:
            name = torch.cuda.get_device_name(0)
        except Exception:  # noqa: BLE001
            name = "CUDA device"
        return True, f"GPU: {name}"
    print("[提示] 未检测到 CUDA（torch.cuda.is_available()=False），"
          "自动回退 CPU。本脚本默认在有 CUDA 的机器上用 GPU 运行，"
          "或用 --cpu 显式指定 CPU。")
    return False, "CPU（无 CUDA，自动回退）"


# ---------------------------------------------------------------- 合成数据集
def _make_image(rng: random.Random):
    """画一张 128×128 灰底图，随机 1-2 个白色矩形；返回 (BGR 图, 标签行列表)。"""
    import cv2
    import numpy as np

    img = np.full((IMG_SIZE, IMG_SIZE, 3), 114, dtype=np.uint8)
    lines = []
    for _ in range(rng.randint(1, 2)):
        w = rng.randint(24, 64)
        h = rng.randint(24, 64)
        x1 = rng.randint(4, IMG_SIZE - w - 4)
        y1 = rng.randint(4, IMG_SIZE - h - 4)
        cv2.rectangle(img, (x1, y1), (x1 + w - 1, y1 + h - 1), (255, 255, 255), -1)
        cx = (x1 + w / 2.0) / IMG_SIZE
        cy = (y1 + h / 2.0) / IMG_SIZE
        bw, bh = w / IMG_SIZE, h / IMG_SIZE
        lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return img, lines


def make_dataset(ws: Path) -> dict:
    """生成 YOLO 检测小数据集与推理输入目录。

    布局（与 torchkiln/data/det.py 契约一致）::

        <ws>/data/images/train|val/xxx.png
        <ws>/data/labels/train|val/xxx.txt      # "cls cx cy w h" 归一化
        <ws>/data/train.txt / val.txt           # 每行 data_dir 相对图片路径
        <ws>/predict_input/xxx.png

    返回 data_dir / train_list / val_list / predict_dir 绝对路径。
    """
    import cv2

    rng = random.Random(42)
    data_dir = ws / "data"
    for split, n, prefix in (("train", N_TRAIN, "train"), ("val", N_VAL, "val")):
        img_dir = data_dir / "images" / split
        lbl_dir = data_dir / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        names = []
        for i in range(n):
            img, lines = _make_image(rng)
            stem = f"{prefix}_{i:03d}"
            cv2.imwrite(str(img_dir / (stem + ".png")), img)
            (lbl_dir / (stem + ".txt")).write_text(
                "\n".join(lines) + "\n", encoding="utf-8")
            names.append(f"images/{split}/{stem}.png")
        (data_dir / f"{split}.txt").write_text(
            "\n".join(names) + "\n", encoding="utf-8")

    # 推理输入：3 张新图（无需标签）
    pred_dir = ws / "predict_input"
    pred_dir.mkdir(parents=True, exist_ok=True)
    for i in range(N_PREDICT):
        img, _ = _make_image(rng)
        cv2.imwrite(str(pred_dir / f"predict_{i:03d}.png"), img)

    return {
        "data_dir": str(data_dir),
        "train_list": str(data_dir / "train.txt"),
        "val_list": str(data_dir / "val.txt"),
        "predict_dir": str(pred_dir),
    }


# ---------------------------------------------------------------- 事件收集器
class EventCollector:
    """本地 HTTP 事件收集器（torchkiln simple_run 回调目标）。

    - 仅接受 ``POST /events``；``X-Torchkiln-Token`` 不符 → 401；
    - 线程安全（threading.Lock）；提供按类型过滤 / 取 end / 等待终态。
    """

    def __init__(self, token: str):
        self.token = token
        self._lock = threading.Lock()
        self._events: list = []

        collector = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server 契约
                if self.path != "/events":
                    self._respond(404, {"ok": False, "error": "not found"})
                    return
                if self.headers.get("X-Torchkiln-Token") != collector.token:
                    self._respond(401, {"ok": False, "error": "bad token"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    obj = json.loads(self.rfile.read(length).decode("utf-8"))
                except Exception:  # noqa: BLE001
                    self._respond(400, {"ok": False, "error": "bad json"})
                    return
                with collector._lock:
                    collector._events.append(obj)
                self._respond(200, {"ok": True})

            def _respond(self, code, body):
                payload = json.dumps(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):  # 静音 http.server 默认日志
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="smoke-events")
        self._thread.start()
        self.port = self._httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/events"

    def events(self, type=None):  # noqa: A002 - 事件字段名即 type
        with self._lock:
            return [e for e in self._events
                    if type is None or e.get("type") == type]

    def end_events(self):
        return self.events("end")

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def wait_end(self, timeout: float) -> bool:
        """等待出现终态事件（end）；超时返回 False。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.end_events():
                return True
            time.sleep(0.1)
        return bool(self.end_events())

    def wait_stable(self, quiet: float = SETTLE_SEC, timeout: float = 15.0) -> None:
        """进程退出后等事件流静默（简单模式 sink 退出前已 join 发送线程，
        这里是兜底，防最后一两条回调晚到）。"""
        deadline = time.time() + timeout
        last_count, last_change = 0, time.time()
        while time.time() < deadline:
            with self._lock:
                count = len(self._events)
            if count != last_count:
                last_count, last_change = count, time.time()
            elif time.time() - last_change >= quiet:
                return
            time.sleep(0.1)

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- spec 构造
def _base_params(ws: Path, use_gpu: bool) -> dict:
    """四链路共用的小配置覆盖（点分键 → -o k=v）。

    覆盖 yml 默认里的设备/大尺寸/大类数；数据集键（data_dir /
    label_file_list / names / image_size）都走 spec.params，
    torchkiln 侧 merge_config 会把列表字段自动包成 list。
    """
    return {
        "Global.use_gpu": use_gpu,
        "Global.device": "cuda:0" if use_gpu else "cpu",
        "Architecture.Head.num_classes": 1,
        "Train.dataset.transform.image_size": IMG_SIZE,
        "Eval.dataset.transform.image_size": IMG_SIZE,
        "Train.dataset.names": ["object"],
        "Eval.dataset.names": ["object"],
    }


def build_specs(ws: Path, ds: dict, use_gpu: bool):
    """按固定顺序生成四链路 JobSpec（dict 形态，写盘即 simple_run 输入）。

    ``use_gpu`` 决定 ``resources.gpu``（predict 链路据此自动选
    cuda:0 / cpu）与 Global.use_gpu / Global.device。eval / predict /
    export 的 ``weights_path`` 初始为 None，train 结束后用返回的
    ``fill_weights`` 回填真实权重路径。
    """
    out = ws / "out"
    out.mkdir(parents=True, exist_ok=True)

    def _spec(kind: str) -> dict:
        return {
            "spec_version": "1.0",
            "framework": "torchkiln",
            "kind": kind,
            "config_path": CONFIG_NAME,
            "params": _base_params(ws, use_gpu),
            "resources": {"gpu": 1 if use_gpu else 0},
            "seed": 42,
        }

    train = _spec("train")
    train["dataset"] = {
        "data_dir": ds["data_dir"],
        "train_list": ds["train_list"],
        "val_list": ds["val_list"],
    }
    train["params"].update({
        "Global.epoch_num": 1,
        "Global.save_model_dir": str(out / "train"),
        "Global.save_epoch_step": 1,
        "Global.eval_epoch_step": 1,
        "Global.print_batch_step": 1,
        "Train.loader.batch_size_per_card": BATCH,
        "Train.loader.num_workers": 0,
        "Eval.loader.num_workers": 0,
    })

    eval_spec = _spec("eval")
    eval_spec["dataset"] = {
        "data_dir": ds["data_dir"],
        "val_list": ds["val_list"],
    }
    eval_spec["weights_path"] = None  # 运行时回填
    eval_spec["params"]["Global.save_model_dir"] = str(out / "eval")

    predict_spec = _spec("predict")
    predict_spec["weights_path"] = None  # 运行时回填
    predict_spec["input_dir"] = ds["predict_dir"]
    predict_spec["params"]["Global.output"] = str(out / "predict")

    export_spec = _spec("export")
    export_spec["weights_path"] = None  # 运行时回填
    export_spec["params"]["Global.output"] = str(out / "export")

    specs = [
        ("train", 1, train),
        ("eval", 2, eval_spec),
        ("predict", 3, predict_spec),
        ("export", 4, export_spec),
    ]

    def fill_weights(weights_path: str) -> None:
        for name, _tid, spec in specs:
            if name in ("eval", "predict", "export"):
                spec["weights_path"] = weights_path

    return specs, fill_weights


# ---------------------------------------------------------------- 链路执行
def _tail(text: str, n: int = 60) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[-n:])


def run_link(collector: EventCollector, ws: Path, name: str, task_id: int,
             spec: dict) -> subprocess.CompletedProcess:
    """写 spec JSON → subprocess 跑 simple_run → 返回 CompletedProcess。

    ``--repo-root`` 与 cwd 都指向 TorchKiln 仓库根：``service/`` 包不在
    wheel 里，simple_run 的 ``main()`` 依赖它做 JobSpec 解析。
    """
    spec_dir = ws / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_path = spec_dir / f"spec_{name}.json"
    spec_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    cmd = [
        sys.executable, "-m", "torchkiln.simple_run", str(spec_path),
        "--callback-url", collector.url, "--token", collector.token,
        "--task-id", str(task_id), "--repo-root", str(REPO_ROOT),
    ]
    print(f"[{name}] 启动：python -m torchkiln.simple_run spec_{name}.json "
          f"--task-id {task_id}（cwd={REPO_ROOT}）")
    return subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=LINK_TIMEOUT)


# ---------------------------------------------------------------- 断言
def check_end(name: str, proc, collector) -> list:
    """公共断言：退出码 0 + 有且仅 1 条合法 end。返回 (说明, ok, 细节) 列表。"""
    checks = []
    checks.append(("退出码为 0", proc.returncode == 0,
                   f"returncode={proc.returncode}"))
    ends = collector.end_events()
    ok = len(ends) == 1
    reason = ends[0].get("exit_reason") if ends else None
    checks.append(("有且仅 1 条 end 事件", ok,
                   f"end 条数={len(ends)}，exit_reason={reason}"))
    checks.append(("end.exit_reason 合法",
                   reason in VALID_END_REASONS,
                   f"exit_reason={reason}"))
    if ends and ends[0].get("error"):
        # simple_run 失败时 stdout/stderr 可能全空，错误只在 end 事件里
        checks.append(("end 错误信息", False, str(ends[0].get("error"))))
    if proc.returncode != 0:
        checks.append(("进程输出（尾部 60 行）", False,
                       f"stdout:\n{_tail(proc.stdout)}\nstderr:\n{_tail(proc.stderr)}"))
    return checks


def check_train(name, proc, collector, ws):
    """train 专属：step/eval 事件 + 权重产物落盘；返回 (checks, 权重路径)。"""
    checks = check_end(name, proc, collector)
    steps, evs = collector.events("step"), collector.events("eval")
    checks.append(("有 step 事件（≥1）", len(steps) >= 1,
                   f"step 条数={len(steps)}"))
    checks.append(("有 eval 事件（≥1）", len(evs) >= 1,
                   f"eval 条数={len(evs)}"))
    out_dir = Path(ws) / "out" / "train"
    weights = None
    for cand in ("best_accuracy.pth", "final.pth", "latest.pth"):
        if (out_dir / cand).is_file():
            weights = str(out_dir / cand)
            break
    checks.append(("训练权重产物存在（best/final/latest）", weights is not None,
                   f"目录={out_dir}，选用={weights}"))
    return checks, weights


def check_eval(name, proc, collector):
    checks = check_end(name, proc, collector)
    evs = collector.events("eval")
    ok_parse, detail = False, f"eval 条数={len(evs)}"
    if evs:
        raw = evs[-1].get("main_value")
        try:
            float(raw)
            ok_parse = raw is not None
            detail += "，main_value={}（{}）".format(
                raw, evs[-1].get("main_indicator"))
        except (TypeError, ValueError):
            detail += f"，main_value 不可解析：{raw}"
    checks.append(("有 eval 事件且 main_value 可解析",
                   len(evs) >= 1 and ok_parse, detail))
    return checks


def check_predict(name, proc, collector):
    checks = check_end(name, proc, collector)
    evs = collector.events("predict")
    ok_done, detail = False, f"predict 条数={len(evs)}"
    out_dir = (collector.end_events() or [{}])[0].get("output_dir")
    if evs:
        last = evs[-1]
        total, done = last.get("images_total"), last.get("images_done")
        ok_done = (total == N_PREDICT and done == total)
        detail += f"，末条 images_done={done}/{total}"
    checks.append((f"predict 进度完整（末条 done==total=={N_PREDICT}）",
                   len(evs) >= 1 and ok_done, detail))
    ok_out, out_detail = False, f"output_dir={out_dir}"
    if out_dir and Path(out_dir).is_dir():
        jpgs = sorted(p.name for p in Path(out_dir).glob("*.jpg"))
        ok_out = len(jpgs) == N_PREDICT
        out_detail += f"，落盘 jpg：{jpgs}"
    checks.append(("输出目录逐图落 .jpg", ok_out, out_detail))
    return checks


def check_export(name, proc, collector):
    """export 专属：ONNX 是交付标准——model.onnx 必须存在且非空，
    且 end 事件的 onnx_path 指向该文件（TorchScript/推理权重仅兼容保留）。"""
    checks = check_end(name, proc, collector)
    end = (collector.end_events() or [{}])[0]
    out_dir = end.get("output_dir")
    ok_dir = bool(out_dir and Path(out_dir).is_dir())
    checks.append(("output_dir 存在", ok_dir, f"output_dir={out_dir}"))
    onnx_file = Path(out_dir) / "model.onnx" if ok_dir else None
    size = (onnx_file.stat().st_size
            if onnx_file is not None and onnx_file.is_file() else 0)
    files = sorted(p.name for p in Path(out_dir).iterdir()) if ok_dir else []
    checks.append(("ONNX 交付产物 model.onnx 存在且非空", bool(size > 0),
                   f"model.onnx={size} bytes，文件：{files}"))
    end_onnx = end.get("onnx_path")
    if end_onnx:
        same = bool(onnx_file is not None and size > 0
                    and Path(end_onnx).resolve() == onnx_file.resolve())
        checks.append(("end.onnx_path 指向该 ONNX 文件", same,
                       f"onnx_path={end_onnx}"))
    return checks


# ---------------------------------------------------------------- 主流程
def _print_checks(name: str, checks: list) -> bool:
    all_ok = True
    for desc, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"    [{mark}] {desc} — {detail}")
    return all_ok


def main(argv=None) -> int:
    # GBK 控制台/重定向兼容：⚠️ 等非 BMP/GBK 外字符在 `> log.txt` 重定向下会
    # UnicodeEncodeError（交互控制台走 UTF-16 看不出）。放最前，连 --help 也覆盖。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")   # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - 无 reconfigure 的流静默跳过
            pass
    parser = argparse.ArgumentParser(
        description="simple mode 四链路 smoke（默认 GPU；--cpu 强制 CPU，"
                    "无 CUDA 时自动回退 CPU）")
    parser.add_argument("--keep", action="store_true",
                        help="保留临时工作目录（默认结束清理）")
    parser.add_argument("--cpu", action="store_true",
                        help="强制 CPU（默认有 CUDA 时用 GPU）")
    args = parser.parse_args(argv)

    ensure_deps()
    if not (REPO_ROOT / "torchkiln" / "simple_run.py").is_file():
        print(f"[错误] 未找到 TorchKiln submodule：{REPO_ROOT}（请先 "
              "git submodule update --init --recursive）")
        return 1

    use_gpu, device_desc = resolve_device(args.cpu)

    ws = Path(tempfile.mkdtemp(prefix="tk-smoke-"))
    print(f"工作区：{ws}")
    print(f"运行设备：{device_desc}")
    ds = make_dataset(ws)
    specs, fill_weights = build_specs(ws, ds, use_gpu)
    print(f"合成数据集：train {N_TRAIN} 张 / val {N_VAL} 张 / 推理 {N_PREDICT} 张（{IMG_SIZE}×{IMG_SIZE} PNG，1 类）")

    collector = EventCollector(token=f"smoke-{random.getrandbits(32)}")
    print(f"事件收集器：{collector.url}")

    # 结果：name -> dict(ok, rc, end_reason, elapsed, counts)
    results = {}
    t_all = time.time()
    try:
        for name, task_id, spec in specs:
            t0 = time.time()
            collector.reset()
            try:
                proc = run_link(collector, ws, name, task_id, spec)
            except subprocess.TimeoutExpired as exc:
                print(f"[{name}] 超时（{LINK_TIMEOUT}s）被终止。stdout 尾部：\n{_tail(exc.stdout)}")
                print(f"[{name}] stderr 尾部：\n{_tail(exc.stderr)}")
                results[name] = {"ok": False, "rc": None, "end": "超时",
                                 "elapsed": time.time() - t0, "counts": {}}
                break
            elapsed = time.time() - t0
            collector.wait_end(10.0)
            collector.wait_stable()

            counts = {t: len(collector.events(t))
                      for t in ("step", "eval", "predict", "best", "end")
                      if collector.events(t)}
            ends = collector.end_events()

            if name == "train":
                checks, weights = check_train(name, proc, collector, ws)
                if weights:
                    fill_weights(weights)
                    print(f"    选用权重：{weights}")
            elif name == "eval":
                checks = check_eval(name, proc, collector)
            elif name == "predict":
                checks = check_predict(name, proc, collector)
            else:
                checks = check_export(name, proc, collector)
            ok = _print_checks(name, checks)
            results[name] = {
                "ok": ok,
                "rc": proc.returncode,
                "end": (ends[0].get("exit_reason") if ends else "缺失"),
                "elapsed": elapsed,
                "counts": counts,
            }
            if not ok and name == "train":
                # 训练失败时后续链路无权重可用，直接汇总退出
                break
    finally:
        collector.stop()

    # ------------------------------------------------------------ 汇总
    print("")
    print("=" * 76)
    print(f"运行设备：{device_desc}")
    print("链路汇总：")
    print("{:<10} {:<8} {:<18} {:<28} {:<10} {}".format(
        "链路", "退出码", "end", "事件计数", "耗时", "结果"))
    print("-" * 76)
    all_ok = True
    for name in LINK_ORDER:
        if name not in results:
            print("{:<10} {:<8} {:<18} {:<28} {:<10} {}".format(
                name, "-", "-", "-", "-", "FAIL（前置链路失败跳过）"))
            all_ok = False
            continue
        r = results[name]
        counts = " ".join(f"{k}={v}" for k, v in r["counts"].items())
        print("{:<10} {:<8} {:<18} {:<28} {:<10} {}".format(
            name, r["rc"], "1条/{}".format(r["end"]), counts,
            "{:.1f}s".format(r["elapsed"]), "PASS" if r["ok"] else "FAIL"))
        all_ok = all_ok and r["ok"]
    print("-" * 76)
    print("结论：{}（总耗时 {:.1f}s，设备：{}）".format(
        "ALL PASS" if all_ok else "FAILED", time.time() - t_all, device_desc))
    print("=" * 76)

    if args.keep:
        print(f"工作目录已保留（--keep）：{ws}")
    else:
        shutil.rmtree(ws, ignore_errors=True)
        print(f"工作目录已清理：{ws}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
