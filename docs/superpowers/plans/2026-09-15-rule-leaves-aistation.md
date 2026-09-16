# 规则引擎通用叶子 Implementation Plan（AIStation 云端）

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans.

**Goal:** 在 `_match_conditions` 增 `object_present`/`zone_enter`/`count` 叶子并接线目录；云端端到端验证。

**Spec:** `docs/superpowers/specs/2026-09-15-rule-leaves-design.md`

## Global Constraints
- 后端 `D:\AIStation\backend`；`uv run pytest`/`uv run ruff check`（只判新增）；中文注释；禁 `git add -A`；无新列/迁移；不新增依赖。

### Task 1: 叶子与辅助函数
**Files:** `backend/app/api/v1/module_video/inference/service.py`、`backend/tests/test_rule_leaves.py`（新）
- [ ] 失败测试：`object_present`（有/无/带 label/带 region/带 min_confidence）；`zone_enter`（内/外/边界/缺 region）；`count`（>=,>,<=,<,==，带/不带 region）；非法输入（非 dict/None/坏 region）不抛异常返回 False/True 合理值。
- [ ] 实现：`_point_in_polygon(x,y,pts)`、`_region_of(leaf)`、`_bbox_center(d)`、`_matches_label(d, leaf)`、`_in_region(d, leaf)`；在 `_match_conditions` 增三个 subject 分支（保持 `and/or/not` 与既有属性/文本叶子不变，异常不抛出）。
- [ ] `uv run pytest tests/test_rule_leaves.py -q` + 全量 + ruff；提交 `feat(video): 规则引擎新增对象/区域/计数叶子`。

### Task 2: 目录默认规则对齐
**Files:** `backend/app/api/v1/module_video/scene/catalog.py`、`backend/tests/test_scene_catalog.py`
- [ ] 将 `DET_ZONE`(object_present 或 zone_enter)、`GATHER`/`OVERCROWD`(count)、`FACE_DET`/`TRAFFIC_DET`/`FIRE_SMOKE` 等默认规则对齐到已实现叶子；其余占位加 TODO。
- [ ] 测试：断言这些场景默认规则使用已实现 subject/键（扩展既有 `_IMPLEMENTED_LEAF_KEYS`）。
- [ ] 提交 `feat(video): 目录默认规则对齐通用叶子`。

### Task 3: 云端端到端（HTTP 回调直投）
**Files:** `backend/tests/test_rule_leaves_e2e.py`（新，用 `test_client`/`auth_headers`）
- [ ] 建 camera + algorithm(scene DET_ZONE) + task + AlarmRule(conditions=object_present person in region)；`POST /api/v1/video/algorithm/detection/callback`（Bearer INFERENCE_CALLBACK_TOKEN）投一条命中事件 → 断言 `alarm_record` 建立；投一条不命中（区域外/无目标）→ 断言不建立。
- [ ] `uv run pytest tests/test_rule_leaves_e2e.py -q` + 全量 + ruff；提交 `test(video): 地区入侵叶子云端端到端`。

## Self-Review
覆盖 spec §3/§4/§5：Task1(叶子) Task2(目录) Task3(云端 e2e)。时序/跟踪叶子显式留待 SP4。
