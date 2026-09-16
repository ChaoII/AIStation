# SP4 跟踪纵切片（AIStation 侧）Implementation Plan

**Goal:** 编排透传 `tracking` 配置；E2E 验证事件含 `track_id`。

**Spec:** `docs/superpowers/specs/2026-09-15-tracking-slice-design.md`；ModelDeploy 侧：`.superpowers/plans/2026-09-15-tracking-slice-modeldeploy.md`

## Global Constraints
后端 `D:\AIStation\backend`；`uv run pytest`/ruff；中文注释；禁 `git add -A`；无迁移。

### Task 1: 编排透传 tracking
**Files:** `backend/app/api/v1/module_video/edge/orchestrator.py`、`backend/tests/test_edge_task_config.py`
- [ ] 失败测试：`algorithm.runtime_config={"tracking":{"enabled":True,"algorithm":"bytetrack"}}` → `cfg["tracking"]["enabled"] is True`；缺省不含或为 disabled。
- [ ] 实现：`build_agent_task_config` 输出顶层 `tracking`（取自 `merged_runtime.get("tracking") or merged_params.get("tracking") or {"enabled": False}`）。
- [ ] 全量+ruff；提交 `feat(video): 编排透传 tracking 配置`。

### Task 2: E2E 脚本跟踪断言
**Files:** `scripts/e2e/edge_agent_e2e.ps1`、`docs/superpowers/runbooks/edge-agent-e2e.md`
- [ ] 通用场景（如 `DET_ZONE`）增 `-Tracking` 开关：算法 `runtime_config.tracking={enabled=true,algorithm=bytetrack}`；断言 `ai_result.detections[].track_id` 出现（至少一条 >=0）。
- [ ] 语法校验；runbook 增节；提交 `test(video): 跟踪 track_id 真机联调脚本与 runbook`。

### Task 3: 真机 E2E（控制器）
- [ ] 切 cloud_edge+MQTT、重启后端、起 broker、跑 `DET_ZONE -Tracking`（`test_video60.mp4`）、断言 track_id 出现、恢复环境、记账本。

## Self-Review
spec §4/§5：Task1(编排) Task2/3(E2E)。`normalize_edge_event` 已支持 track_id。
