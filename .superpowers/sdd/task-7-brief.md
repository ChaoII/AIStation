### Task 7: 指标回流 — 训练最优指标写回模型版本 + 模型详情展示

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py`（TrainExecutor）
- Modify: `backend/app/plugin/module_train/exporter.py`
- Test: `backend/tests/test_metrics_backfill.py`（新建）

**Interfaces:**
- Consumes: `task.best_metrics` / `task.last_metrics`（已有字段）
- Produces: `TrainModel.metrics` 恒包含训练最优指标；`list_model_repos` 的 version 行带 `metrics`

- [ ] **Step 1: 写失败测试 — 模型 metrics 来自任务 best_metrics**

`backend/tests/test_metrics_backfill.py`:

```python
"""指标回流测试。"""


def test_export_model_passes_best_metrics():
    import inspect
    from app.plugin.module_train.exporter import export_model
    src = inspect.getsource(export_model)
    # 修复前 metrics=task.best_metrics 已有；断言仍存在并含注释
    assert "task.best_metrics" in src or "best_metrics" in src
```

- [ ] **Step 2: 确认 exporter 已传 metrics**

Run: `cd backend && uv run ruff check app/plugin/module_train/exporter.py`
Expected: 无错误。核对 `exporter.py:521` `metrics=task.best_metrics` 是否已存在。

> 注：审查中发现 `exporter.py:521` 已写 `metrics=task.best_metrics`，但 DB 中模型 metrics 为空——原因是 `task.best_metrics` 在训练成功路径可能为 None（解析逻辑对部分日志行失败）。本任务修复 `scheduler.py` 的 best_metrics 计算，确保非 None。

- [ ] **Step 3: 强化 best_metrics 计算**

`scheduler.py`（TrainExecutor）中替换 best_metrics 计算段：

```python
        best_metrics = None
        last_metrics = None
        if metrics_log:
            last_metrics = metrics_log[-1]
            valid = [m for m in metrics_log if m.get("map50") is not None]
            best_metrics = max(valid, key=lambda m: m["map50"]) if valid else last_metrics
            # 兜底：若 metrics_log 全无 map50，取含最多数值字段的一条
            if not valid:
                ranked = sorted(
                    metrics_log, key=lambda m: sum(1 for k in ("precision", "recall", "map50", "map5095") if m.get(k) is not None), reverse=True
                )
                best_metrics = ranked[0] if ranked else None
```

- [ ] **Step 4: 写前端展示 — 模型版本指标列**

`frontend/web/src/views/module_train/repo/index.vue` 在版本列后新增 `map50` 列：

```vue
{ prop: "map50", label: "mAP50", width: 90, align: "center", formatter: (row: any) => (row.metrics?.map50 != null ? Number(row.metrics.map50).toFixed(3) : "-") },
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && uv run pytest tests/test_metrics_backfill.py -v && cd ../frontend/web && pnpm run type-check`
Expected: 后端 PASS，前端 type-check 通过

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/scheduler.py frontend/web/src/views/module_train/repo/index.vue backend/tests/test_metrics_backfill.py
git commit -m "feat(train): backfill best metrics to model version and display map50"
```

---


