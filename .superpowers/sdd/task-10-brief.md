### Task 10: 清理与回归验证

**Files:**
- Modify: `backend/app/scripts/init_app.py`（如残留旧调度器引用）
- Test: 全量回归

- [ ] **Step 1: 清理临时目录残留**

确认 `%TEMP%/train_output`、`eval_output`、`predict_output` 下无占用大文件。提供 `backend/app/plugin/module_train/cleanup.py` 定时清理（保留最近 N 天）：

```python
"""定时清理临时训练产物目录。"""
import asyncio
import os
import shutil
import tempfile
import time


async def cleanup_loop(keep_days: int = 7, interval_sec: int = 3600):
    while True:
        try:
            base = tempfile.gettempdir()
            for sub in ("train_output", "eval_output", "predict_output", "deploy_output", "model_export", "dataset_export", "model_export_logs"):
                d = os.path.join(base, sub)
                if not os.path.isdir(d):
                    continue
                cutoff = time.time() - keep_days * 86400
                for entry in os.listdir(d):
                    p = os.path.join(d, entry)
                    try:
                        if os.path.getmtime(p) < cutoff:
                            if os.path.isdir(p):
                                shutil.rmtree(p, ignore_errors=True)
                            else:
                                os.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(interval_sec)
```

在 `init_app.py` 启动该清理循环。

- [ ] **Step 2: 后端全量测试**

Run: `cd backend && uv run pytest tests/ -v`
Expected: 全部 PASS（含既有测试）

- [ ] **Step 3: ruff 检查**

Run: `cd backend && uv run ruff check`
Expected: 0 errors（若有历史问题记录，注明忽略项）

- [ ] **Step 4: 前端 type-check + build**

Run: `cd frontend/web && pnpm run type-check && npx vite build 2>&1 | Select-Object -Last 3`
Expected: type-check 0 errors，build 成功

- [ ] **Step 5: 真实库端到端冒烟**

1. 登录 v3 前端 (http://localhost:5190/web) admin/123456
2. 模型仓库页：确认 41 条旧数据聚合为仓库+版本两级展示，无 `vv1`
3. 创建一次训练任务 → 跑通 → 确认产物落盘、metrics 非空
4. 评估：选最新版本 → 跑通 → metrics 正常
5. 预测：上传图片 → 跑通 → 结果图/zip 可见
6. 部署：创建 + 启动 → 健康检查通过 → 停止
7. 重启后端：确认无 RUNNING 残留任务卡死（孤儿恢复生效）

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/cleanup.py backend/app/scripts/init_app.py
git commit -m "chore(train): temp dir cleanup and regression verification"
```

---

## Self-Review 结论

- **Spec 覆盖**：P0 数据模型语义（Task 1-3, 5）✅；P0 导出覆盖 hack（Task 5）✅；P1 并发控制（Task 4）✅；P1 predict 孤儿（Task 4）✅；P1 paddlex 半成品（Task 6）✅；P1 指标未回流（Task 7）✅；P2 部署未用/端口竞态（Task 9）✅；P2 临时目录清理（Task 10）✅；前端适配（Task 8）✅。版本号 vv bug（Task 2, 5）✅。
- **回滚安全**：Task 2 迁移含 downgrade；Task 3-9 均小步提交。
- **类型一致性**：`_parse_version`、`_resolve_model_storage`、`TaskExecutor` 接口在各 Task 间签名一致。
- **遗留说明**：`TrainTask.model_repo_id` 保留指向版本行 id（兼容旧前端跳转），前端已改为通过 `version/{id}/repo` 解析仓库。

