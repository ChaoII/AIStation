# Phase 3C：视频推理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 推理 worker 不重复拉起（PID 记录 + 存活校验 + 落盘后清理）；布控时段 `schedule_json` 与 `sensitivity` 真实生效；worker 标签用名称而非数字；报警快照改由 HTTP 路由提供（不再暴露绝对本地路径）；规则匹配不再因多规则崩溃。

**Architecture:** `worker.py` 增加纯函数（可无 cv2/modeldeploy 导入测试）；`scheduler.py` 用 pidfile + `psutil` 校验防重；快照经 `init_app` 的受控路由提供，DB 存**相对路径**。

**Tech Stack:** FastAPI + SQLAlchemy + psutil（已有依赖）+ pytest。

## Global Constraints

- 后端 `D:\AIStation\backend`（`uv run pytest`/`uv run ruff check`，只判断新增）；中文注释；不新增依赖；提交 `fix(video): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- 测试不依赖 `modeldeploy`/cv2：只测纯函数与 HTTP 路由；`worker.py` 顶层不得 import cv2/modeldeploy（保持延迟导入）。
- `FastDeploy/modeldeploy` 未安装时，推理运行时仍不可用；本计划保证其**逻辑**正确并可降级。

---

### Task 1: 推理 worker/调度器防重与配置生效

**背景:** `_running_inferences` 仅内存，后端重启后调度循环对 DB `RUNNING` 的任务各起一个新 worker，而旧 worker 仍在运行 → 重复回调/告警。`_build_task_config` 硬编码 `fps_target=5`/`alarm_interval=30`，不含 `schedule_json`；`sensitivity` 下发但 worker 不用；worker `label = str(label_id)` → 告警显示数字。

**Files:**
- Modify: `backend/app/api/v1/module_video/inference/worker.py`
- Modify: `backend/app/api/v1/module_video/inference/scheduler.py`
- Modify: `backend/app/api/v1/module_video/algorithm/model.py`（如需 `schedule_json`/`interval_seconds` 字段确认）
- Test: `backend/tests/test_inference_worker.py`

**Interfaces:**
- Produces（worker.py 纯函数）：
  - `within_schedule(schedule_json, now) -> bool` —— 无配置→True；否则按 7×24 时段（`{"days":[0-6], "ranges":[["HH:MM","HH:MM"], ...]}` 或简化的 `{"start":"HH:MM","end":"HH:MM","days":[...]}`）判断；解析失败→True（不误停）。
  - `sensitivity_to_conf(sensitivity: int, base: float = 0.5) -> float` —— 灵敏度 0-100 映射阈值（越高阈值越低）：`base * (1 - (sensitivity-50)/100)`，clamp `[0.05, 0.95]`。
  - `label_name(result, names: list[str] | None = None) -> str` —— 优先 `result.label`，其次 `names[label_id]`，否则 `str(label_id)`。
- Produces（scheduler.py）：`pid_file(task_id) -> Path`、`read_worker_pid(task_id) -> int | None`、`is_worker_alive(pid) -> bool`（`psutil` 校验 cmdline 含 `worker.py`）、`write_worker_pid(task_id, pid)`、`clear_worker_pid(task_id)`。

- [ ] **Step 1: Write the failing test**

```python
"""推理 worker 纯逻辑与 PID 防重测试。"""
from datetime import datetime

from app.api.v1.module_video.inference import worker as w
from app.api.v1.module_video.inference import scheduler as sch


def test_within_schedule_empty_is_true():
    assert w.within_schedule(None, datetime(2026, 1, 1, 3, 0)) is True
    assert w.within_schedule({}, datetime(2026, 1, 1, 3, 0)) is True


def test_within_schedule_range():
    cfg = {"start": "08:00", "end": "18:00", "days": [0, 1, 2, 3, 4]}
    mon = datetime(2026, 1, 5, 12, 0)   # 周一
    assert w.within_schedule(cfg, mon) is True
    assert w.within_schedule(cfg, datetime(2026, 1, 5, 20, 0)) is False


def test_sensitivity_to_conf():
    assert w.sensitivity_to_conf(50) == 0.5
    assert w.sensitivity_to_conf(100) < 0.5
    assert w.sensitivity_to_conf(0) > 0.5
    assert 0.05 <= w.sensitivity_to_conf(1000) <= 0.95


def test_label_name():
    class R:
        label = "person"
        label_id = 0
    assert w.label_name(R()) == "person"
    class R2:
        label = None
        label_id = 2
    assert w.label_name(R2(), ["a", "b", "car"]) == "car"
    assert w.label_name(R2()) == "2"


def test_pidfile_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(sch, "CONFIG_DIR", tmp_path)
    assert sch.read_worker_pid(7) is None
    sch.write_worker_pid(7, 12345)
    assert sch.read_worker_pid(7) == 12345
    sch.clear_worker_pid(7)
    assert sch.read_worker_pid(7) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_inference_worker.py -q`
Expected: FAIL（函数不存在）。

- [ ] **Step 3: Implement**

`worker.py` 增加（顶层，纯 stdlib）：
```python
def within_schedule(schedule_json, now) -> bool:
    """判断当前时间是否在布控时段内；无配置或解析失败→True（不误停）。"""
    if not schedule_json:
        return True
    try:
        cfg = schedule_json if isinstance(schedule_json, dict) else json.loads(schedule_json)
        days = cfg.get("days")
        if days and now.weekday() not in days:
            return False
        start = cfg.get("start")
        end = cfg.get("end")
        if start and end:
            hm = now.strftime("%H:%M")
            if start <= end:
                return start <= hm <= end
            return hm >= start or hm <= end   # 跨天
        ranges = cfg.get("ranges")
        if isinstance(ranges, list):
            hm = now.strftime("%H:%M")
            return any(len(r) == 2 and r[0] <= hm <= r[1] for r in ranges)
    except Exception:
        return True
    return True


def sensitivity_to_conf(sensitivity, base: float = 0.5) -> float:
    """灵敏度(0-100) → 置信度阈值：越高阈值越低。"""
    try:
        s = max(0, min(100, int(sensitivity)))
    except (TypeError, ValueError):
        s = 50
    conf = base * (1 - (s - 50) / 100.0)
    return max(0.05, min(0.95, conf))


def label_name(result, names=None) -> str:
    """结果标签名：优先 result.label，其次外部名称表，最后数字 id。"""
    lbl = getattr(result, "label", None)
    if lbl:
        return str(lbl)
    lid = getattr(result, "label_id", None)
    if names and lid is not None and 0 <= int(lid) < len(names):
        return str(names[int(lid)])
    return str(lid)
```
在 `main()` 中：`fps_target` 从 config 取（scheduler 已下发）；`alarm_interval` 从 config；`conf_threshold` 若 preset 未给则用 `sensitivity_to_conf(config.get("sensitivity", 50))`；循环里：
```python
        if not within_schedule(config.get("schedule_json"), datetime.now()):
            time.sleep(1)
            continue
```
（放在取帧后、推理前。）标签：`label = label_name(r, names)`（`names` 从 config 可选取 `class_names`）。

`scheduler.py` 增加 PID 辅助：
```python
import psutil

def pid_file(task_id: int) -> Path:
    return CONFIG_DIR / f"infer_{task_id}.pid"

def read_worker_pid(task_id: int) -> int | None:
    pf = pid_file(task_id)
    try:
        return int(pf.read_text().strip())
    except Exception:
        return None

def is_worker_alive(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        return "worker.py" in " ".join(p.cmdline())
    except Exception:
        return False

def write_worker_pid(task_id: int, pid: int) -> None:
    pid_file(task_id).write_text(str(pid))

def clear_worker_pid(task_id: int) -> None:
    try:
        pid_file(task_id).unlink()
    except OSError:
        pass
```
`start_inference`：在启动前，若 `read_worker_pid(task_id)` 存活 → `psutil.Process(pid).terminate()`（清理旧进程，避免重复）并 `clear_worker_pid`；创建子进程后 `write_worker_pid(task_id, proc.pid)`。`stop_inference`：结束后 `clear_worker_pid(task_id)`。`_build_task_config` 增加下发 `schedule_json`（`task.schedule_json`）、`interval_seconds`/`sensitivity`（已下发）、`class_names`（若算法有）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_inference_worker.py -q`
Expected: PASS

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_video/inference/worker.py app/api/v1/module_video/inference/scheduler.py`

```bash
git add backend/app/api/v1/module_video/inference/worker.py backend/app/api/v1/module_video/inference/scheduler.py backend/tests/test_inference_worker.py
git commit -m "fix(video): 推理 worker PID 防重、布控时段/灵敏度生效、标签用名称"
```

---

### Task 2: 报警快照 HTTP 路由 + 规则匹配健壮

**背景:** `process_detection_callback` 把快照绝对路径存进 `alarm_record.snapshot_path`，且**无 HTTP 路由**服务 `DETECTIONS_DIR` → 前端图片空白；规则查询 `scalar_one_or_none()` 在多条匹配规则时抛 `MultipleResultsFound` → 回调 500；描述里标签是数字。

**Files:**
- Modify: `backend/app/scripts/init_app.py` 或 `backend/app/api/v1/module_video/__init__.py`（新增 `/detections/{path}` 路由）
- Modify: `backend/app/api/v1/module_video/inference/service.py`
- Test: `backend/tests/test_detection_snapshot.py`
- Test: `backend/tests/test_alarm_rule_match.py`

**Interfaces:**
- Produces: `snapshot_url(rel_path: str) -> str` —— 返回 `/detections/{rel_path}`（相对，前端拼 base）；DB 的 `snapshot_path` 存**相对** `date/name.jpg`。
- Produces: `pick_alarm_rule(rules: list, algorithm_type: str) -> Any | None` —— 从多规则中选一条（优先 `alarm_type` 精确匹配，否则第一条），避免 `MultipleResultsFound`。

- [ ] **Step 1: Write the failing tests**

```python
"""快照路由与规则匹配测试。"""
from app.api.v1.module_video.inference.service import pick_alarm_rule, snapshot_url


def test_snapshot_url():
    assert snapshot_url("2026-01-01/a.jpg") == "/detections/2026-01-01/a.jpg"


def test_pick_alarm_rule_prefers_type():
    class R:
        def __init__(self, t): self.alarm_type = t
    rules = [R("OTHER"), R("INTRUSION")]
    assert pick_alarm_rule(rules, "INTRUSION").alarm_type == "INTRUSION"
    assert pick_alarm_rule([], "X") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_detection_snapshot.py tests/test_alarm_rule_match.py -q`
Expected: FAIL。

- [ ] **Step 3: Implement**

快照路由（在 `module_video/__init__.py` 的 `_register_video_routers` 里注册，或 `init_app.register_files`）：
```python
from fastapi.responses import FileResponse
from app.config.setting import settings

@video_router.get("/detections/{file_path:path}", include_in_schema=False)
async def serve_detection(file_path: str):
    base = settings.DETECTIONS_DIR.resolve()
    target = (base / file_path).resolve()
    if base not in target.parents and target != base:
        return JSONResponse(status_code=404, content={"msg": "not found"})
    if target.is_file():
        return FileResponse(str(target), media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"msg": "not found"})
```
（若 `video_router` 前缀为 `/video`，则实际路径为 `/api/v1/video/detections/...`；请据真实前缀调整，并在报告写明最终 URL。若更合适用 `init_app` 的 `app.get`，二选一。）

`service.py`：
```python
def snapshot_url(rel_path: str) -> str:
    return f"/detections/{rel_path.lstrip('/')}"


def pick_alarm_rule(rules, algorithm_type):
    if not rules:
        return None
    for r in rules:
        if getattr(r, "alarm_type", None) == algorithm_type:
            return r
    return rules[0]
```
- `process_detection_callback`：快照写入后 `saved_snapshot_path = rel_name`（相对，如 `f"{date_str}/{snap_name}"`，不再存绝对路径）；规则查询改用 `rules = (await session.execute(stmt)).scalars().all()` + `rule = pick_alarm_rule(rules, algorithm_type)`；描述与 `ai_result` 用 `label` 名称（worker 已给名称）。
- 兼容：若历史行存绝对路径，可在返回时归一化（可选，报告说明）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_detection_snapshot.py tests/test_alarm_rule_match.py -q`
Expected: PASS

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/api/v1/module_video/inference/service.py`

```bash
git add backend/app/api/v1/module_video/inference/service.py backend/tests/test_detection_snapshot.py backend/tests/test_alarm_rule_match.py backend/app/api/v1/module_video/__init__.py backend/app/scripts/init_app.py
git commit -m "fix(video): 报警快照 HTTP 路由与规则匹配健壮化"
```

---

## Self-Review

**Spec coverage（对照 Phase 3 spec 组件 C）:**
- worker PID 防重 → Task 1 ✅
- 时段/灵敏度/ROI → Task 1（ROI worker 已支持，本期确保下发与生效）✅
- 报警快照 HTTP 路由 → Task 2 ✅
- 类别名 → Task 1（worker）+ Task 2（描述）✅
- 规则匹配 → Task 2 ✅

**Placeholder scan:** 无 TBD；快照路由前缀需按 `video_router` 实际前缀确认（已给指引）。

**Type consistency:** `within_schedule`/`sensitivity_to_conf`/`label_name`/`read_worker_pid`/`pick_alarm_rule`/`snapshot_url` 命名一致。

**风险:** `modeldeploy` 未安装 → worker 无法真跑；本计划只保证逻辑正确与降级。快照路由需防目录穿越（已用 resolve + parents 校验）。前端需在 Phase 3D 用 `snapshot_url` 构建完整地址。
