# 人脸纵切片（AIStation 侧）Implementation Plan（FACE_DET）

**Goal:** 编排 FACE_DET → `face_detection` 模型条目；目录默认规则；E2E。

**Spec:** `docs/superpowers/specs/2026-09-15-face-slice-design.md`；ModelDeploy 侧：`.superpowers/plans/2026-09-15-face-slice-modeldeploy.md`

## Global Constraints
后端 `D:\AIStation\backend`；`uv run pytest`/ruff；中文注释；禁 `git add -A`；无迁移。

### Task 1: 编排 face_detection + 目录默认规则
**Files:** `backend/app/api/v1/module_video/edge/orchestrator.py`、`backend/app/api/v1/module_video/scene/catalog.py`、`backend/tests/test_edge_task_config.py`、`backend/tests/test_scene_catalog.py`
- [ ] 失败测试：伪 algorithm `scene_type="FACE_DET"`、`model_path=<scrfd>` → `models[0].type=="face_detection"`、`url=model_path`、`input_size` 默认 [640,640]。
- [ ] 实现：`build_agent_task_config` 增 `scene_type=="FACE_DET"` 分支产出 `type:"face_detection"` 单模型条目（其余场景不变）。
- [ ] 目录：`FACE_DET.default_rule` 对齐 `object_present`（可选 label "face"）；`test_scene_catalog` 断言其叶子为已实现 subject。
- [ ] 全量+ruff；提交 `feat(video): 编排 FACE_DET 人脸检测并接线目录`。

### Task 2: E2E 脚本 FACE_DET + runbook
**Files:** `scripts/e2e/edge_agent_e2e.ps1`、`docs/superpowers/runbooks/edge-agent-e2e.md`
- [ ] `-Scene FACE_DET`：播种 `face_detection` 算法（scrfd，cpu/ort）、`text_match`-无关规则（`object_present`）、断言 `algorithm_type=FACE_DET` 告警且 `detections[]` 非空；能力族含 `face`。
- [ ] 语法校验；runbook 增节；提交 `test(video): FACE_DET 场景真机联调脚本与 runbook`。

### Task 3: 真机 E2E（控制器）
- [ ] 切 cloud_edge+MQTT、重启后端、起 broker、人脸图循环成视频、跑 `-Scene FACE_DET`、断言通过、恢复环境、记账本。

## Self-Review
覆盖 spec §4/§5：Task1(编排+目录) Task2/3(E2E)。规则复用已实现叶子。
