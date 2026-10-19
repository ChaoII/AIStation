# TorchKiln Simple Mode 支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 TorchKiln 增加「简单模式」支撑能力：结构化事件回调（EventCallback）、环境指标采样（EnvSampler）、单作业进程入口（`torchkiln.simple_run`），并完成 Windows 平台无关化审计——使 AIStation 可以以子进程方式直接调用 TorchKiln 并获得直接回调。

**Architecture:** 在 `ptcore` 增加事件抽象与 env 采样器，`BaseTrainer` 在 step/eval/best/end 关键点 emit 事件（与现有 `metrics.jsonl` 写入并行，不替换）；新增 `torchkiln.simple_run` 作为「单作业进程入口」（读 JobSpec → 分派 train/eval/predict/export → 通过 HTTP loopback 推送事件）；`metrics.jsonl` 文件契约保持不动。

**Tech Stack:** Python 3.8+、PyTorch、psutil（新增）、httpx（已有依赖族，回调用 urllib 亦可，见任务 5）、pytest。

**Spec:** `docs/superpowers/specs/2026-10-19-aistation-torchkiln-bridge-design.md`（第 3.3 / 3.7 / 3.9 节）

## Global Constraints

- **不能破坏现有契约**：`metrics.jsonl` 每行格式、`meta.json` 的 `metric_events`、`service/` 的 JobSpec/runner/classify_exit 行为、`tools/*.py` 入口参数**均不得改变**；现有 `tests/test_service_*.py` 必须全绿。
- **事件通道是并行新增**，不是替换：回调与文件写入同时发生。
- **Windows 原生可用**为目标：代码不得引入 Linux-only API（`os.fork`/`resource`/`fcntl`/`/dev/` 路径）；`multiprocessing` 必须可 spawn。
- **依赖按需**：`pynvml` 不新增为硬依赖（try-import 可选，缺失时 GPU 指标以 `torch.cuda` 为准并置 None）；`psutil` 为新增硬依赖（跨平台、轻量）。
- **事件 seq 契约**：每个事件必须带自增 `seq`、`ts`（epoch 秒 float）、`type`。
- **命令约束**：测试用 `cd D:\TorchKiln && python -m pytest tests/<file>.py -q`（该仓库无 uv 配置，pytest 为环境自带）。
- **本 plan 在 TorchKiln worktree 分支实施，验收后合并 main；AIStation 侧 submodule 将 pin 本 plan 最终 commit。**

## Review Focus

1. **无 GPU 环境**（CI/Windows 无 N 卡）：训练仍能跑，env 事件只含 CPU/内存/磁盘/网络，不报错、不阻塞训练。→ 任务 3、4 的测试覆盖。
2. **回调目标不可达**（端口未起/连接被拒）：训练循环不得因回调失败而中断或变慢；事件丢弃并记录，进程继续。→ 任务 5 的测试覆盖。
3. **事件顺序与去重**：seq 严格递增，重复回调（网络重发）由接收方按 seq 去重，发送方只需保证单调。→ 任务 1 的测试覆盖。
4. **dump_config=False 场景**（check/eval/smoke）：此时 metrics_sink 是 `_NullSink`，事件回调仍应可用（回调独立于 sink）。→ 任务 4 的测试覆盖。
5. **Windows spawn 入口**：`python -m torchkiln.simple_run` 必须能从任意 cwd 启动且模块级无副作用（顶部不 import torch 之外的重量模块）。→ 任务 5 的测试覆盖。

---

### Task 1: 事件模型与回调基础（`ptcore/events.py`）

**Files:**
- Create: `ptcore/events.py`
- Test: `tests/test_events.py`

**Interfaces:**
- Consumes: 无（纯标准库）
- Produces:
  - `EVENT_TYPES: tuple[str, ...] = ("step", "eval", "best", "env", "end", "failed")`
  - `@dataclass class Event`: `seq: int`, `ts: float`, `type: str`, `fields: dict[str, Any]`；`to_dict() -> dict`（返回 `{"seq","ts","type", **fields}`，None 值丢弃）
  - `class EventSink(Protocol)`: `def emit(self, type: str, fields: dict[str, Any]) -> None`
  - `class CallbackList`: `def __init__(self, sinks: list[EventSink] | None = None)`；`add(sink)`；`emit(type, fields)`（内部维护 `_seq` 自增并注入 `seq/ts`；sink 抛异常时吞掉并 `logging.warning`，**绝不向上传播**）

- [ ] **Step 1: 写失败测试**

```python
def test_event_to_dict_drops_none():
    e = Event(seq=1, ts=1.0, type="step", fields={"loss": 0.5, "x": None})
    assert e.to_dict() == {"seq": 1, "ts": 1.0, "type": "step", "loss": 0.5}

def test_callback_list_injects_seq_and_swallows_errors():
    out = {}
    def bad(type, fields): raise RuntimeError("network down")
    cb = CallbackList([bad, lambda t, f: out.update(f)])
    cb.emit("step", {"loss": 1.0})          # bad sink 抛错不影响第二个 sink
    assert out["seq"] == 1 and out["ts"] > 0 and out["type"] == "step"
    cb.emit("step", {"loss": 0.9})
    assert out["seq"] == 2
```

- [ ] **Step 2: 运行确认失败**
  Run: `cd D:\TorchKiln && python -m pytest tests/test_events.py -q` → FAIL（`ModuleNotFoundError: ptcore.events`）

- [ ] **Step 3: 实现 `ptcore/events.py`**（按 Interfaces 签名；`CallbackList.emit` 用 `try/except Exception` 包每个 sink 调用）

- [ ] **Step 4: 运行确认通过**（同上命令 → PASS）

- [ ] **Step 5: 提交**
  `git add ptcore/events.py tests/test_events.py && git commit -m "feat(ptcore): 新增事件模型与回调列表（seq/ts 注入、错误隔离）"`

---

### Task 2: MetricSink 支持 env 事件（`ptcore/metrics_sink.py`）

**Files:**
- Modify: `ptcore/metrics_sink.py`（`MetricSink` 类 188 行附近、`_NullSink` 156 行、`meta.json` 214-215 行）
- Test: `tests/test_metrics_sink_env.py`

**Interfaces:**
- Consumes: Task 1 的事件概念（本任务不强制 import，事件序列化格式对齐 `{"seq","ts","type",**fields}`）
- Produces:
  - `MetricSink.env(fields: dict) -> None`：写一行 `type="env"`（沿用 `emit` 内部逻辑；`seq/ts` 由 sink 自带计数器+当前时间，与现有 emit 一致）
  - `_NullSink.env(fields)`：空实现
  - `meta.json` 的 `metric_events` 列表追加 `"env"`

- [ ] **Step 1: 写失败测试**

```python
def test_env_event_written_and_meta_updated(tmp_path):
    sink = build_sink(str(tmp_path), enabled=True, meta={"schema_version": 1})
    sink.env({"gpu": [{"id": 0, "util": 42.0}], "cpu": 0.3})
    sink.close()
    lines = (tmp_path / "metrics.jsonl").read_text().strip().splitlines()
    row = json.loads(lines[-1])
    assert row["type"] == "env" and row["gpu"][0]["util"] == 42.0 and row["seq"] > 0
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert "env" in meta["metric_events"]

def test_null_sink_env_noop():
    s = build_sink(str(tmp_path), enabled=False)
    s.env({"cpu": 0.3})   # 不抛
```

- [ ] **Step 2: 运行确认失败**（`tests/test_metrics_sink_env.py` → FAIL：`MetricSink` 无 `env`）

- [ ] **Step 3: 实现**：给 `MetricSink` 加 `env()`（复用现有 `emit` 的写行路径，注意 `newline="\n"` 已有）；`_NullSink` 加同签名空方法；`_metrics_meta`（或写 meta 处）把 `"env"` 加进 `metric_events`。

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交**
  `git commit -m "feat(ptcore): MetricSink 支持 env 事件（含 meta.json 声明）"`

---

### Task 3: EnvSampler 环境采样器（`ptcore/env_sampler.py`）

**Files:**
- Create: `ptcore/env_sampler.py`
- Modify: `pyproject.toml`（dependencies 加 `"psutil"`）
- Test: `tests/test_env_sampler.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class EnvSampler`: `__init__(self, interval: float = 5.0, device_indices: list[int] | None = None)`
  - `sample() -> dict`：返回事件字段 dict（**不含 type/seq/ts**）：
    - `gpu`: `list[dict]`，每卡 `{"id", "util"|None, "mem_reserved_mb", "mem_allocated_mb", "mem_total_mb"|None, "temp_c"|None, "power_w"|None}`（util/temp/power 仅在 pynvml 可用时非 None；无 CUDA 时 `gpu=[]`）
    - `cpu`: `float`（百分比），`cpu_per_core`: `list[float]`
    - `mem`: `{"used_mb", "total_mb"}`
    - `disk`: `{"read_mb_s", "write_mb_s", "free_mb"}`
    - `net`: `{"rx_mb_s", "tx_mb_s"}`
  - `maybe_sample() -> dict | None`：按 `interval` 节流（`time.monotonic()` 距上次 < interval 返回 None），用于训练循环内调用
  - `close()`：关闭 pynvml 句柄（若打开）

- [ ] **Step 1: 写失败测试**（mock `psutil` 与 `torch.cuda`）

```python
def test_sample_without_cuda(monkeypatch, tmp_path):
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)
    s = EnvSampler(interval=0.1)
    data = s.sample()
    assert data["gpu"] == [] and 0 <= data["cpu"] <= 100
    assert "used_mb" in data["mem"] and "rx_mb_s" in data["net"]

def test_maybe_sample_throttles():
    s = EnvSampler(interval=60.0)
    assert s.maybe_sample() is not None
    assert s.maybe_sample() is None          # 60s 内第二次不采

def test_pynvml_missing_degrades(monkeypatch):
    import builtins
    real = builtins.__import__
    def fake(name, *a, **k):
        if name == "pynvml": raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake)
    s = EnvSampler()
    data = s.sample()
    assert data["gpu"][0]["util"] is None    # 无 pynvml → util 为 None 而非报错
```

- [ ] **Step 2: 运行确认失败**（`tests/test_env_sampler.py` → FAIL：无 `ptcore.env_sampler`）

- [ ] **Step 3: 实现**：`psutil` 读 CPU/内存/磁盘（`psutil.disk_io_counters` 差值算速率，首次记基线返回 0）/网络；GPU 用 `torch.cuda`（is_available/device_count/mem_get_info/memory_allocated/reserved）+ `try: import pynvml`（可选，拿 util/temp/power，失败则 None）；全程无异常上抛（采样失败降级为空字段）。`pyproject.toml` dependencies 追加 `"psutil"`。

- [ ] **Step 4: 运行确认通过**（含跑一遍 `tests/test_infer_api.py` 确保无回归）

- [ ] **Step 5: 提交**
  `git commit -m "feat(ptcore): 新增跨平台环境采样器 EnvSampler（psutil+torch.cuda+可选pynvml）"`

---

### Task 4: BaseTrainer 事件注入与 env 周期采样（`ptcore/trainers/base.py`）

**Files:**
- Modify: `ptcore/trainers/base.py`（`__init__` 70 行、`_train_one_epoch` 731 行、`evaluate_and_save` 1016 行、`train` 1107 行、`MetricSink` 调用点 875-889 / 1035-1062 / 1183-1196）
- Modify: `ptcore/trainers/__init__.py`（`build_trainer` 87 行透传）
- Test: `tests/test_trainer_events.py`

**Interfaces:**
- Consumes: Task 1 `CallbackList`/`EventSink`；Task 3 `EnvSampler`
- Produces:
  - `BaseTrainer.__init__(self, config, dump_config=True, task=None, event_sink: EventSink | None = None)`
  - `BaseTrainer._emit(type: str, fields: dict) -> None`（内部 `self._event_cb.emit(...)`；`event_sink=None` 时直接返回）
  - 事件触发点（字段对齐现有 `metrics_sink` 调用实参，另加 `seq` 由 CallbackList 注入）：
    - `step`：`_train_one_epoch` 现有 `print_batch_step` 分支内，字段 = `{epoch, epoch_num, global_step, steps_per_epoch, lr, loss, comps, ips, eta_sec, mem_reserved, mem_allocated}`
    - `eval`：`evaluate_and_save` 内 `metrics` 就绪后，字段 = `{main_indicator, main_value, main_indicator_mode, is_best, fps, metrics}`
    - `best`：`if better:` 分支内，字段 = `{main_indicator, main_value, main_indicator_mode, metrics, checkpoint}`
    - `env`：训练循环内按 `EnvSampler.maybe_sample()` 节流，字段 = sampler.sample() 结果
    - `end`：`train()` 的 finally 分支（与 `metrics_sink.end` 同处），字段 = `{exit_reason, error, epoch, epoch_num, global_step, main_indicator, main_value, main_indicator_mode, best_epoch, duration_sec}`
  - 配置项：`config["Global"]["env_sample_interval"]`（默认 5.0，`-o` 可覆盖）

- [ ] **Step 1: 写失败测试**（用轻量假 trainer 子类，monkeypatch `EnvSampler` 与 sink）

```python
def test_emit_called_on_step_and_end(monkeypatch):
    from ptcore.events import CallbackList
    events = []
    cb = CallbackList([lambda t, f: events.append((t, f))])
    trainer = _FakeTrainer(config, event_sink=cb)   # 极小子类，直接调 _emit
    trainer._emit("step", {"loss": 0.1})
    assert events[-1][0] == "step" and events[-1][1]["loss"] == 0.1

def test_env_emitted_after_interval(monkeypatch):
    # 构造 trainer，monkeypatch EnvSampler.maybe_sample 返回固定采样，断言 env 事件出现在 events
    ...

def test_dump_config_false_still_emits():
    # dump_config=False 时 sink 为 _NullSink，但 event_sink 仍然收到事件
    ...
```

- [ ] **Step 2: 运行确认失败**（`tests/test_trainer_events.py` → FAIL：`BaseTrainer` 无 `event_sink` 参数）

- [ ] **Step 3: 实现**：`__init__` 加 `event_sink` 参数（`self._event_cb = event_sink or CallbackList()`；`self._env_sampler = EnvSampler(interval=config["Global"].get("env_sample_interval", 5.0))` 仅在训练路径创建）；`_emit` 方法；在上述四个触发点调用 `self._emit(...)`（与 metrics_sink 调用并列，**不替换**）；`_train_one_epoch` 循环内 `_maybe_emit_env()`；`build_trainer(config, **kwargs)` 透传 `event_sink`。

- [ ] **Step 4: 运行确认通过** + 回归：`python -m pytest tests/ -q`（15 分钟内全量；重点 `test_service_*.py` 不红）

- [ ] **Step 5: 提交**
  `git commit -m "feat(ptcore): BaseTrainer 事件回调注入与 env 周期采样（与 metrics.jsonl 并行）"`

---

### Task 5: 单作业进程入口（`torchkiln/simple_run.py`）

**Files:**
- Create: `torchkiln/simple_run.py`
- Test: `tests/test_simple_run.py`

**Interfaces:**
- Consumes: Task 4 的 `event_sink` 注入；`service/schemas.JobSpec`、`service/runner.build_*`（只读不修改）；`ptcore.config_schema.resolve_config`；`tool` 入口（train/eval/predict 进程内、export 子进程）
- Produces:
  - CLI: `python -m torchkiln.simple_run <spec.json> --callback-url <url> --token <token> [--task-id <int>] [--repo-root <root>]`
  - 模块内 `class SimpleRun`: `__init__(self, spec: JobSpec, callback_url: str, token: str, repo_root: str, task_id: int | None = None)`
  - `async def run(self) -> int`：按 `spec.kind`（允许 `train|eval|predict|export`）分派，终态返回退出码（0 成功 / 1 失败），**每条路径都 emit `end`（或 `failed`）事件后再退出**
  - `class HttpEventSink`: `__init__(self, callback_url: str, token: str, task_id: int | None = None)`；`emit(type, fields)` 同步 `queue.put_nowait`（永不阻塞/上抛）；后台 daemon 线程批量 POST `{callback_url}`（header `X-Torchkiln-Token`，body = `{"task_id": task_id, **event.to_dict()}`），失败重试 3 次（1s/2s/4s），仍失败仅 `logging.warning`
  - `build_http_events(callback_url, token, task_id)`：工厂返回 `HttpEventSink`（供 `build_trainer(..., event_sink=...)`）

- [ ] **Step 1: 写失败测试**（mock `HttpEventSink` 与 `build_trainer`）

```python
def test_parse_spec_and_kind_dispatch(tmp_path, monkeypatch):
    spec = {"spec_version": "1.0", "framework": "torchkiln", "kind": "train",
            "model_name": "yolo11n", "config_path": "configs/yolo/yolo11-det.yml",
            "params": {"Global.epoch_num": 1}, "resources": {"gpu": 1}}
    sp = tmp_path / "spec.json"; sp.write_text(json.dumps(spec))
    # monkeypatch ptcore.factory.build_trainer 返回假 trainer（记录 event_sink 注入）
    rc = asyncio.run(run_one([str(sp), "--callback-url", "http://127.0.0.1:1/x",
                              "--token", "t", "--repo-root", str(REPO)]))
    assert rc == 0 and injected_sink is not None

def test_http_sink_never_raises_and_retries(monkeypatch):
    # emit 到不可达 url：不抛异常，线程重试 3 次后丢弃
    ...
```

- [ ] **Step 2: 运行确认失败**（`tests/test_simple_run.py` → FAIL：无模块）

- [ ] **Step 3: 实现**：
  - `main()`（argparse）→ `if __name__ == "__main__": main()`（Windows spawn 保护）
  - train/eval：`resolve_config` → `build_trainer(config, event_sink=HttpEventSink(...))` → `trainer.train()`；eval 用 `epoch_num=0`（对齐 tools/eval.py 语义）
  - predict：进程内 `torchkiln.infer_api.Runtime.load(config, weights, device=...)` + 遍历输入（回调 predict 进度事件 `{images_total, images_done}`，与 predict_yolo 同字段）→ 结果写输出目录
  - export：`subprocess.run([python, "tools/export.py", ...])`（短任务，stdout 透传）
  - 每个分支 try/except：异常 → emit `failed` + 返回码 1；正常 → emit `end` + 返回码 0

- [ ] **Step 4: 运行确认通过** + 回归全量

- [ ] **Step 5: 提交**
  `git commit -m "feat(torchkiln): 新增 simple_run 单作业进程入口（JobSpec 分派 + HTTP 事件回调）"`

---

### Task 6: Windows 平台无关化审计与兼容清单

**Files:**
- Modify: `torchkiln/ocr/data/__init__.py:10`（删除死代码 `import signal`）
- Modify: `torchkiln/ocr/postprocess/pse_postprocess/pse/__init__.py:21-27`（编译失败提示增强：Windows 需 VS C++ 工具链，且避免 `shell=True` 注入风险——改为 `shell=False` + 列表参数）
- Create: `docs/windows_compat.md`（兼容清单：已确认项 + 已知限制 + 修复记录）
- Test: `tests/test_windows_compat.py`

**Interfaces:**
- Consumes: 无
- Produces: 审计测试 `test_no_linux_only_apis()`（扫描 `torchkiln/`、`ptcore/` 源码：断言不含 `os.fork`/`resource`/`fcntl`/`posixpath`/`/dev/` 常量路径等禁用符号——`signal` 仅允许 `signal.signal`/`SIGTERM` 类且仅在非 nt 分支）

- [ ] **Step 1: 写失败测试**

```python
def test_no_linux_only_apis():
    bad = ("os.fork(", "import resource", "fcntl.", "posixpath", "/dev/shm", "/dev/null", "pwd.", "grp.")
    for root in ("torchkiln", "ptcore"):
        for path in Path(root).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for tok in bad:
                assert tok not in text, f"{path} contains {tok}"
```

- [ ] **Step 2: 运行确认失败**（应先有一处命中，如当前存在的 `import signal` 死代码——若测试全过，则调 Step 3 的额外项：`import signal` 在非 `if os.name != "nt"` 保护下即为失败项）

- [ ] **Step 3: 实现**：清理命中的死代码/风险点；编写 `docs/windows_compat.md`（内容：已确认兼容项——base.py Windows batch 分支、persistent_workers、pretrained 隐藏缓存、metrics_sink newline、runner nt 分支；已知限制——PSE C 扩展需 VS 工具链、Windows spawn 需 `__main__` 保护；简单模式跑法说明）

- [ ] **Step 4: 运行确认通过**（审计测试 + 全量回归）

- [ ] **Step 5: 提交**
  `git commit -m "fix(ptcore): Windows 平台无关化审计修复与兼容清单"`

---

### Task 7: 文档与整体回归

**Files:**
- Modify: `README.md`（新增「Simple Mode」小节：`python -m torchkiln.simple_run` 用法、事件回调说明、依赖说明（psutil 新增）、env 事件契约）
- Test: 无新增测试

- [ ] **Step 1: 写 README 小节**（中文；含 CLI 示例与事件 JSON 示例）

- [ ] **Step 2: 回归验证**：`python -m pytest tests/ -q` 全绿；`python tools/check_graph_build.py` 输出 `55 configs: 0 FAIL`

- [ ] **Step 3: 提交**
  `git commit -m "docs: simple run 用法与事件契约说明"`

---

## Execution Notes

- 任务 1-4 之间接口依赖（events → sink → sampler → trainer），严格按序；任务 5 依赖 4；任务 6/7 可并行于 5 之后。
- 每任务提交前必须跑该任务测试 + `tests/test_service_eval_jobs.py`（契约不破坏的哨兵）。
- 完成后（用户确认验收）合并回 TorchKiln main；将最终 commit hash 提供给 AIStation 侧 plan 用于 submodule pin。
