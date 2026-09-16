# Phase 2B：指标解析与训练详情 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 统一"最优指标"策略为单一实现（按框架选主指标），各框架解析出正确指标；训练无产物不标 SUCCESS；训练详情页按框架展示主指标（PaddleX hmean/acc、YOLO cls top1/top5、det/seg/obb/pose mAP）。

**Architecture:** 新增 `backend/app/plugin/module_train/metrics.py` 提供 `best_metric()` 与主指标映射；`scheduler._compute_best` 与 `paddlex_executor` 内联 best 改为调用它；`export_model` 无 `storage_path` 时 ultralytics 分支标记 FAILED。前端 `task/detail.vue` 依据 `task.framework`/`hyperparams.mode` 渲染主指标。

**Tech Stack:** FastAPI + SQLAlchemy + pytest；Vue3 + Element Plus + Playwright。

## Global Constraints

- 后端命令 `D:\AIStation\backend`（`uv run pytest` / `uv run ruff check`，只判断新增问题）；前端 `D:\AIStation\frontend`（`pnpm run type-check` 无新增错误；`pnpm e2e` 通过）。
- 中文注释。不新增依赖。只改本任务文件。提交 `fix(train): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- 指标记录结构：每轮 `{epoch, total_epochs|total, ...metrics}`；PaddleX 另含 `{hmean|acc, best:True}` 记录。

---

### Task 1: 统一最优指标 + 各框架解析 + 无产物失败

**背景:** 最优指标策略分裂：`scheduler._compute_best` 只认 `map50`；`paddlex_executor` 内联取 `best` 记录。ultralytics 分类/分割/姿态指标未解析；PaddleX 的 hmean/acc 虽解析但前端不认。`export_model` 无产物时 ultralytics 分支仍标 SUCCESS。

**Files:**
- Create: `backend/app/plugin/module_train/metrics.py`
- Modify: `backend/app/plugin/module_train/scheduler.py`
- Modify: `backend/app/plugin/module_train/paddlex_executor.py`
- Test: `backend/tests/test_train_metrics.py`

**Interfaces:**
- Produces: `primary_metric_key(framework: str, task_type: str, mode: str | None = None) -> str` —— 返回主指标键：`ultralytics+cls→"top1"`、`ultralytics+其他→"map50"`、`paddlex+rec→"acc"`、`paddlex+det→"hmean"`。
- Produces: `best_metric(metrics_log: list[dict], framework: str, task_type: str = "detection", mode: str | None = None) -> dict | None` —— 过滤掉 `best:True` 汇总记录后，按主指标取最大的一轮；主指标无值时取最近一轮含任意指标的记录；空则 None。

- [ ] **Step 1: Write the failing test**

```python
"""最优指标策略测试。"""
from app.plugin.module_train.metrics import best_metric, primary_metric_key


def test_primary_metric_key():
    assert primary_metric_key("ultralytics", "classification") == "top1"
    assert primary_metric_key("ultralytics", "detection") == "map50"
    assert primary_metric_key("paddlex", "ocr", mode="rec") == "acc"
    assert primary_metric_key("paddlex", "ocr", mode="det") == "hmean"


def test_best_metric_picks_max_primary():
    log = [
        {"epoch": 1, "map50": 0.5},
        {"epoch": 2, "map50": 0.7},
        {"epoch": -1, "map50": 0.6},  # summary row must be ignored
    ]
    assert best_metric(log, "ultralytics", "detection")["epoch"] == 2


def test_best_metric_paddlex_rec_acc():
    log = [{"epoch": 1, "acc": 0.8}, {"epoch": 2, "acc": 0.9}]
    assert best_metric(log, "paddlex", "ocr", mode="rec")["epoch"] == 2


def test_best_metric_fallback_and_empty():
    log = [{"epoch": 1, "loss": 1.2}]
    assert best_metric(log, "ultralytics", "detection") == log[0]
    assert best_metric([], "ultralytics", "detection") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_metrics.py -q`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: Write minimal implementation**

`metrics.py`：

```python
"""训练指标：主指标选择与最优轮次。"""

_PRIMARY = {
    ("ultralytics", "classification"): "top1",
    ("ultralytics", "cls"): "top1",
    ("paddlex", "rec"): "acc",
    ("paddlex", "det"): "hmean",
}


def primary_metric_key(framework: str, task_type: str, mode: str | None = None) -> str:
    """按框架/任务/模式返回主指标键。"""
    fw = (framework or "").lower()
    if fw == "paddlex":
        return "acc" if (mode or "").lower() == "rec" else "hmean"
    if fw == "ultralytics":
        tt = (task_type or "").lower()
        return "top1" if tt in ("cls", "classification") else "map50"
    return "map50"


def best_metric(metrics_log, framework, task_type="detection", mode=None):
    """选出最优轮次：忽略 best 汇总记录，按主指标取最大；无主指标时退最近一轮。"""
    rows = [m for m in (metrics_log or []) if isinstance(m, dict) and not m.get("best")]
    if not rows:
        return None
    key = primary_metric_key(framework, task_type, mode)
    scored = [m for m in rows if m.get(key) is not None]
    if scored:
        return max(scored, key=lambda m: m.get(key, 0))
    return rows[-1]
```

`scheduler.py`：删除 `_compute_best`（或保留为薄封装调用 `best_metric`），在 `TrainExecutor._execute` 中用：

```python
            from .metrics import best_metric
            best_metrics = best_metric(metrics_log, "ultralytics", task_type)
```

（`task_type` 已在 `_build_cmd` 内解析；`_execute` 需同样取到 `annotation_task.task_type`，可复用 `_build_cmd` 的查询或抽一个 `_resolve_task_type(task)` 纯函数。）

`paddlex_executor.py`：把内联 best 提取替换为：

```python
            from .metrics import best_metric
            hp = task.hyperparams or {}
            best = best_metric(metrics_log, "paddlex", "ocr", mode) or {}
            latest = [m for m in metrics_log if m.get("epoch") and not m.get("best")]
            latest = latest[-1] if latest else {}
```

`export_model` 无产物时 ultralytics 分支标 FAILED：在 `TrainExecutor._execute` 的 `exit_code == 0` 分支，`model_info = await export_model(...)` 后：

```python
                if not model_info.get("storage_path"):
                    await cls._mark_status(task_id, TrainStatus.FAILED,
                                           error_log="训练完成但未找到模型产物",
                                           fnished_at=datetime.now())
                else:
                    await cls._mark_status(task_id, TrainStatus.SUCCESS, ...)
```

（注意 `finished_at` 拼写；按真实字段为准。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_train_metrics.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/metrics.py app/plugin/module_train/scheduler.py app/plugin/module_train/paddlex_executor.py`

```bash
git add backend/app/plugin/module_train/metrics.py backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/paddlex_executor.py backend/tests/test_train_metrics.py
git commit -m "fix(train): 统一最优指标策略，无产物不标成功"
```

---

### Task 2: 训练详情页按框架展示主指标

**背景:** `task/detail.vue` 指标卡与图表写死 YOLO（precision/recall/map50/map5095 + box/cls/dfl loss），PaddleX（hmean/acc）显示为空；分类（top1/top5）也无展示。

**Files:**
- Modify: `frontend/src/views/module_train/task/detail.vue`
- Test: `frontend/e2e/train-detail.spec.ts`（可选，或复用现有）

**Interfaces:**
- 依据 `task.framework` 与 `task.hyperparams.mode` 决定指标卡：PaddleX det→HMean/Precision/Recall；PaddleX rec→Acc；YOLO det/seg/obb/pose→mAP@50/mAP@50:95/Precision/Recall；YOLO cls→Top1/Top5。
- 图表 series 仅使用该框架实际有值的键（OCR 用 loss 单线，不再引用 box/cls/dfl）。

- [ ] **Step 1: 抽取框架感知的指标定义**

在 `detail.vue` `<script setup>` 增加：

```ts
const metricSpec = computed(() => {
  const fw = (task.value?.framework || "").toLowerCase();
  const mode = (task.value?.hyperparams?.mode || "det").toLowerCase();
  if (fw === "paddlex") {
    return mode === "rec"
      ? [{ key: "acc", label: "Acc", color: "#409eff" }]
      : [
          { key: "hmean", label: "HMean", color: "#52c41a" },
          { key: "precision", label: "Precision", color: "#409eff" },
          { key: "recall", label: "Recall", color: "#fa8c16" },
        ];
  }
  return [
    { key: "map50", label: "mAP@50", color: "#fa8c16" },
    { key: "map5095", label: "mAP@50:95", color: "#9b59b6" },
    { key: "precision", label: "Precision", color: "#52c41a" },
    { key: "recall", label: "Recall", color: "#409eff" },
  ];
});
```

模板中把写死的 4 个指标卡改为 `v-for="s in metricSpec"`，值取 `displayMetrics[s.key]`（`displayMetrics` 改为按 `s.key` 从 `bestMetrics/lastMetrics` 取值；百分比格式：hmean/acc/map/top 为 0-1 小数→百分比，loss 为小数）。

- [ ] **Step 2: 图表按框架选择 series**

`lossChartOption` / `metricChartOption` 依据框架：PaddleX 只画 `{name:"Loss", data: log.map(m => m.loss)}`（及 rec 的 acc 曲线）；YOLO 画现有 map/PR 曲线。指标对比表（`metricsRows`）同样按 `metricSpec` 生成。

- [ ] **Step 3: 类型检查 + E2E**

Run: `cd frontend && pnpm run type-check && pnpm e2e`
Expected: 无新增类型错误；e2e 通过。若新增 `train-detail.spec.ts`，用 API 造一个已完成任务或用既有数据打开 `/#/train/task/:id`，断言指标卡渲染且不出现 `—`（有数据时）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_train/task/detail.vue frontend/e2e/train-detail.spec.ts
git commit -m "fix(train): 训练详情按框架展示主指标"
```

---

## Self-Review

**Spec coverage（对照 Phase 2 spec 组件 B）:**
- 统一最优指标策略 → Task 1 ✅
- 各框架指标解析（PaddleX hmean/acc；YOLO cls top1/其他 map）→ Task 1 ✅
- 无产物不标成功 → Task 1 ✅
- 前端按框架展示 → Task 2 ✅

**Placeholder scan:** 无 TBD；Task 1 Step 3 的 `finished_at` 拼写已提示按真实字段为准。

**Type consistency:** `primary_metric_key`/`best_metric`/`metricSpec`/`displayMetrics[s.key]` 命名一致。

**风险:** ultralytics cls/seg/pose 的日志解析键名依 Ultralytics 版本而变（`top1` vs `top1_acc`）；Task 1 的 `_parse_epoch` 应同时产出 `top1`/`top5` 并对已有 `map50` 保持兼容；若真机日志不同，按实际键名调整并记录。Task 1 需在 `_execute` 取到 `task_type`（复用 `_resolve_task_type`）。
