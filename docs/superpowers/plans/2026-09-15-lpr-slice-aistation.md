# LPR 车牌纵切片（AIStation 侧）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans.

**Goal:** 编排按 `LPR`/`LPR_LIST` 场景编译 `lpr` pipeline；目录默认规则对齐实现叶子；E2E 覆盖（复用 `text_match`/`ocr_label`）。

**Spec:** `docs/superpowers/specs/2026-09-15-lpr-slice-design.md`
**ModelDeploy 侧:** `.superpowers/plans/2026-09-15-lpr-slice-modeldeploy.md`

## Global Constraints
- 后端 `D:\AIStation\backend`；`uv run pytest`/`uv run ruff check`（只判新增）；中文注释；禁 `git add -A`；无新列/迁移。

### Task 1: 编排 lpr pipeline + 目录默认规则对齐
**Files:** `backend/app/api/v1/module_video/edge/orchestrator.py`、`backend/app/api/v1/module_video/scene/catalog.py`、`backend/tests/test_edge_task_config.py`、`backend/tests/test_scene_catalog.py`
- [ ] 失败测试：伪 algorithm `scene_type="LPR"`、`preset_params={"rec_path":...,"input_size":[640,640]}` → `models[0].type=="lpr"`、`det_url=model_path`、`rec_url=rec_path`。
- [ ] 实现：`scene_type ∈ {LPR, LPR_LIST}` 分支产出 `{type:"lpr", det_url, rec_url, labels, input_size, confidence_threshold}`（其它场景不变）。
- [ ] 目录：`LPR`/`LPR_LIST` 的 `default_rule` 对齐为 `{"subject":"ocr_label","contains":"..."}`（或 `text_match regex`），并加测试断言这些场景默认叶子使用已实现 subject/键。
- [ ] `uv run pytest tests/test_edge_task_config.py tests/test_scene_catalog.py -q` + 全量 + ruff；提交 `feat(video): 编排 LPR 车牌 pipeline 并对齐目录默认规则`。

### Task 2: E2E 脚本 LPR 场景 + runbook
**Files:** `scripts/e2e/edge_agent_e2e.ps1`、`docs/superpowers/runbooks/edge-agent-e2e.md`
- [ ] `-Scene LPR`：播种 `lpr` 算法（det+rec，cpu/ort）、放宽车牌规则（`text_match` regex `.+`）、断言 `algorithm_type=LPR` 告警且 `detections[].text` 非空；设备能力含 `lpr`。
- [ ] 语法校验；runbook 增节；提交 `test(video): LPR 场景真机联调脚本与 runbook`。

### Task 3: 真机 E2E（控制器）
- [ ] 切 cloud_edge+MQTT、重启后端、起 broker、准备车牌视频、跑 `-Scene LPR`、断言通过、恢复环境、记账本。

## Self-Review
覆盖 spec §4/§5：Task1(编排+目录) Task2/3(E2E)。规则复用已有 text 叶子（无新叶子）。
