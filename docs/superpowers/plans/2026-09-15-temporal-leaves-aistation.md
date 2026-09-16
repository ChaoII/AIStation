# SP4-b 时序规则叶子 Implementation Plan（AIStation 云端）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans.

**Goal:** 云端时序叶子 `dwell`/`count_window`/`absence`（Redis + 内存降级），接线目录。

**Spec:** `docs/superpowers/specs/2026-09-15-temporal-leaves-design.md`

## Global Constraints
后端 `D:\AIStation\backend`；`uv run pytest`/ruff；中文注释；禁 `git add -A`；无迁移；不新增依赖（复用现有 redis 客户端；测试可用 dev 依赖 fakeredis 或内存降级）。

### Task 1: 时序状态存储 + 三个叶子
**Files:** `backend/app/api/v1/module_video/inference/service.py`（或新增 `inference/temporal.py`）、`backend/tests/test_temporal_leaves.py`（新）
- [ ] 设计一个 `_Temporal` 帮助器：`first_seen/last_seen/observe`，优先 Redis（`settings.REDIS_*`），不可用则进程内字典+锁；时间由调用方传入（`ts`）。
- [ ] 失败测试：`dwell`（达标/未达标/轨迹过期）、`count_window`（去重 track_id、各 op、窗口内外）、`absence`（有历史超时/未超时/无历史）、非法输入不抛异常；时间注入可控。
- [ ] 实现叶子分支（保持 and/or/not 与既有叶子不变；时序叶子在评估时读取 `event` 的 detections+ts，并在 `process_detection_callback` 中**先写入观测**再评估）。
- [ ] `uv run pytest tests/test_temporal_leaves.py -q` + 全量 + ruff；提交 `feat(video): 规则引擎新增时序叶子(dwell/count_window/absence)`。

### Task 2: 目录接线 + 云端端到端
**Files:** `backend/app/api/v1/module_video/scene/catalog.py`、`backend/tests/test_scene_catalog.py`、`backend/tests/test_temporal_leaves_e2e.py`
- [ ] `LOITER`→dwell、`ABSENT`→absence、`GATHER`→count_window（或保留单帧 count）；`LINE_CROSS` 保留 TODO（需边缘几何）。
- [ ] 云端端到端：多次带 `track_id` 的回调（模拟同轨迹跨时间），断言 `dwell` 命中出告警、未达时长不出；用注入时间或在测试中直接调用叶子+状态。
- [ ] 提交 `feat(video): 目录时序场景接线 + 时序叶子云端端到端`。

### Task 3: 全量回归 + 记账本
- [ ] `uv run pytest -q`；ruff；记账本。

## Self-Review
覆盖 spec §3/§4/§5：Task1(叶子+状态) Task2(目录+e2e)。line_cross 显式 TODO。兼容无时序规则。
