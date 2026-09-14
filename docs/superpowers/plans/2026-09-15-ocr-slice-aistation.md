# OCR 纵切片（AIStation 侧）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Checkbox steps.

**Goal:** 事件 v2 `objects[].text` 贯通；规则引擎支持 `text_match`/`ocr_label`；编排按 `OCR_TEXT`/`METER_OCR` 场景编译 `ocr` pipeline；E2E 覆盖。

**Spec:** `docs/superpowers/specs/2026-09-15-ocr-slice-design.md`
**ModelDeploy 侧:** `.superpowers/plans/2026-09-15-ocr-slice-modeldeploy.md`（另仓库）

## Global Constraints
- 后端 `D:\AIStation\backend`；`uv run pytest`/`uv run ruff check`（只判新增）；中文注释；禁 `git add -A`；无关工作区改动不碰。
- 不做迁移（无新列；本切片不新增 DB 字段）。

---

### Task 1: 归一化 text + 规则叶子 text_match/ocr_label
**Files:** `backend/app/api/v1/module_video/edge/consumer.py`、`backend/app/api/v1/module_video/inference/service.py`、`backend/tests/test_edge_event_intake.py`、`backend/tests/test_attribute_rule.py`

**Interfaces:**
- `normalize_edge_event`：`objects[].text/text_score` 并入 `detections[]`（与 attributes 同法，双数组按索引）。
- `_match_conditions` 增叶子：`{"subject":"text_match","regex":"..."}`（任一 detection.text 命中正则，非法正则视为不命中）、`{"subject":"ocr_label","contains":"..."}`（子串）。

- [ ] Step 1 失败测试：v2 同时含 detections+objects（objects 带 text）→ `detections[0]["text"]` 保留；`text_match` regex 命中/不命中；`ocr_label` contains。
- [ ] Step 2 确认失败。
- [ ] Step 3 实现（正则用 `re.search`，`re.error` 捕获返回 False；text 非字符串跳过）。
- [ ] Step 4 `uv run pytest tests/test_edge_event_intake.py tests/test_attribute_rule.py -q` + 全量 + ruff。
- [ ] Step 5 提交 `feat(video): 事件 text 归一化与文本规则叶子`。

### Task 2: 编排按场景编译 ocr pipeline
**Files:** `backend/app/api/v1/module_video/edge/orchestrator.py`、`backend/tests/test_edge_task_config.py`

**Interfaces:** `build_agent_task_config`：`scene_type ∈ {OCR_TEXT, METER_OCR}` 时产出 `{type:"ocr", det_url:algorithm.model_path, cls_url, rec_url, dict_url, labels, input_size, confidence_threshold, password}`（cls/rec/dict 取 `preset_params`/`runtime_config` 的 `cls_path/rec_path/dict_path`）。其它场景不变。

- [ ] Step 1 失败测试：伪 algorithm `scene_type="OCR_TEXT"`、`preset_params={"cls_path","rec_path","dict_path","input_size":[960,960]}` → 断言 `models[0].type=="ocr"` 且四路径正确。
- [ ] Step 2..4 实现/通过/ruff。
- [ ] Step 5 提交 `feat(video): 编排按场景编译 ocr pipeline`。

### Task 3: E2E 脚本 OCR 场景 + runbook
**Files:** `scripts/e2e/edge_agent_e2e.ps1`、`docs/superpowers/runbooks/edge-agent-e2e.md`

**Interfaces:** `-Scene OCR_TEXT`：播种 `ocr` 算法（三模型+字典，cpu/ort）、放宽文本规则（`text_match` regex `.+` 或 `ocr_label contains <稳定子串>`）、断言告警 `ai_result.detections[].text` 非空；视频由 `ocr2.jpg` 循环生成（`-VideoPath`）。

- [ ] Step 1 实现脚本分支 + 断言；语法校验。
- [ ] Step 2 runbook 增节。
- [ ] Step 3 提交 `test(video): OCR 场景真机联调脚本与 runbook`。

### Task 4: 真机 E2E（控制器执行）
- [ ] 切 cloud_edge+MQTT、重启后端、起 broker、生成 ocr 视频、跑 `-Scene OCR_TEXT`、断言通过、恢复环境、记账本。

---

## Self-Review
覆盖 spec §4/§5：Task1(归一化+叶子) Task2(编排) Task3/4(E2E)。兼容：非 OCR 场景与 v1 不变。
