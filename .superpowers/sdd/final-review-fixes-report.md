# 终审修复报告 — feat/pipeline-optimization

日期：2026-09-16
基线 HEAD：`e1a1a28`（+ `441a06d`、`14c01a1`、`6734c27`、`5965df2`）
依据：`.superpowers/sdd/final-branch-review.md`（SHOULD FIX #1/#2/#3/#9）
未执行合并：按要求仅提交到 `feat/pipeline-optimization`。

---

## 一、修复提交（SHA）

| # | SHA | 说明 |
|---|-----|------|
| 1 | `0b05e74` | fix(video): 时序观测按事件时间戳幂等，修复多条 line_cross 规则不命中 |
| 2 | `3f7c70f` | fix(video): 既有库启动补列补齐告警规则 params/rollout/group_id |
| 3 | `92b5276` | fix(video): 内联快照写盘路径归一化，拒绝目录穿越 |
| 4 | `6c9c7b2` | fix(video): 边缘心跳未配置共享密钥时 fail-closed |
| 5 | `aeb8538` | chore: 忽略 .superpowers/brainstorm 本地草稿目录 |
| 6 | （本文件独立提交） | docs: 终审修复报告 |

---

## 二、各 finding 处理

### Finding 1 — 多条时序规则共享观测导致 line_cross 永不命中
- 根因：`process_detection_callback` 对每条候选规则各调一次 `_observe_temporal_event`，
  同一 `(camera, alarm_type, scope)` 被重复观测；`_observe_locked` 第二次把 `pos_p=旧cur=now`、
  `pos_c=now` → `prev==cur`，`_segments_cross` 恒假。
- 修复（`temporal.py:255-264`）：位置推进增加幂等条件 —— 仅当本次事件 ts **严格新于**
  该轨迹已记录的 last 时才推进 `pos_p/pos_c`。同一事件被多条规则重复观测时第二次为 no-op；
  乱序到达的更早事件也不会让位置回退。单规则语义完全不变。
- 回归测试：
  - `test_temporal_positions.py::test_repeated_observe_same_ts_does_not_advance_position`
  - `test_temporal_positions.py::test_observe_older_ts_does_not_rewind_position`
  - `test_rule_scope.py::test_two_line_cross_rules_both_fire`（同相机同 alarm_type 两条 line_cross 均命中）
- 既有 `test_temporal_observe_runs_per_temporal_rule`（断言观测调用次数=2）保持绿：调用次数未变，
  变化的是重复调用不再污染位置状态。

### Finding 2 — 启动补列漏了新列
- `init_app.py` 的兜底补列字典提取为模块级 `ENSURE_NEW_COLUMNS`（便于测试），并为
  `video_alarm_rules` 补齐 `params` / `rollout`（`JSONB NOT NULL DEFAULT '{}'`）与
  `group_id`（`INTEGER`，可空），与 Alembic `1164d4a7539d` / `183fb76b1184` / `d6d5f85952f5` 的
  `server_default` 保持一致。
- 测试：`test_ensure_columns.py`（清单结构 + 三列 server_default）。
- 说明：Alembic 迁移仍是权威；该 helper 仅服务「不跑 Alembic、只重启后端」的既有库兜底。

### Finding 3a — 内联快照写盘路径未归一
- `snapshot.py` 新增 `safe_detections_path()`：在 DETECTIONS_DIR 下归一化并校验包含关系，
  不要求文件存在；`safe_local_snapshot()` 复用它（保持「文件不存在返回 None」语义）。
- `service.py` 的内联 base64 写盘改用 `safe_detections_path()`，越界时仅告警并跳过写盘
  （`saved_snapshot_path` 保持 None），不再 `mkdir`/`write_bytes` 到 DETECTIONS_DIR 之外。
- 测试：
  - `test_snapshot_url.py::test_safe_detections_path_blocks_traversal`
  - `test_snapshot_url.py::test_safe_detections_path_allows_nested_relative`
  - `test_snapshot_write_safety.py`（相对穿越 / 越界绝对路径被拒；合法子目录正常写入）

### Finding 3b — 心跳 fail-open
- `edge/controller.py` 改为 **fail-closed**：`EDGE_CONTROL_TOKEN` 未配置（或空白）时直接
  HTTP 403 拒绝，不再放行未鉴权心跳；凭证不匹配同样返回 HTTP 403（此前是 HTTP 500 + 业务码 403）。
- 测试：`test_edge_heartbeat.py`（未配置拒绝 / 不匹配拒绝 / 凭证正确放行）。
- e2e 影响：无任何 e2e 或前端调用 `POST /video/edge/heartbeat`（已全量 grep 确认），
  fail-closed **不影响** e2e；重启后端实测该端点返回 `403`。
- 备注：`setting.py` 的 `VIDEO_ANALYSIS_MODE=="cloud_edge"` 启动告警保留；本次未改默认密钥值。

---

## 三、验证证据

- 后端全量：`cd backend && uv run pytest -q` → **641 passed**（基线 628 + 新增 13）。
- Ruff（`--no-fix`，仅本次触碰文件）：
  - 新增/修改的测试与源码文件 0 新增问题；
  - `edge/controller.py` 仅 14 条 **pre-existing** `FAST002`（HEAD 版本同数，均在与本次无关的既有函数签名行）。
- e2e（重启后端加载新代码后）：
  `pnpm run e2e -- e2e/edge.spec.ts e2e/alarm-snapshot.spec.ts e2e/sp5c-snapshot-overlay.spec.ts e2e/sp6a-rule-scope.spec.ts e2e/smoke.spec.ts`
  → **7 passed (1.0m)**。
- 运行时探针：`POST /api/v1/video/edge/heartbeat`（无 token）→ `403`（修复前 `200`）。

---

## 四、工作区清理（Part 4）

### 已回滚（纯噪音 / 会话产物）
- `.superpowers/sdd/` 下 10 个文件（`progress.md` 与 9 个 task brief/report）：
  该目录 `.gitignore` 内容为 `*`（gitignored），属本地流程产物，回滚丢弃工作区改动。
- 6 张重新生成的视觉核对截图（`docs/superpowers/runbooks/{sp5a,sp5b,sp5c,sp6a,sp6b}-visual/*.png`）：
  同用途重渲染，回滚保留已提交版本。

### 已提交（属程序的合法内容）
- 5 个修复/杂项提交（见第一节）+ 本报告。
- `.gitignore` 新增忽略 `.superpowers/brainstorm/`。

### 有意保留未提交（非本程序产物）
- 16 个前端文件（`module_train/*`、`module_annotation/*`、`ModelExportDialog`、`Notification`、
  `NavBar/notification`、`useCollab`、`api/module_train.ts`、`Train/SchedulePanel.vue` 等）：
  经 `git diff -w` 核对，为 prettier/eslint 格式化与属性重排（含 `<v-chart>`→`<VChart>`），
  与 video/AI 程序无功能关联，无法确认由本程序授权产生，按指示保留未提交。
- 未跟踪 `docs/issues.md`：内容为 2026-07-08 的 annotation/train 既有问题清单，早于本程序，
  非本程序产物，保留未跟踪。

---

## 五、遗留关注点

1. **Finding 1 采用「时间戳幂等」方案**（评审给出的两个可选项之一），未改为「按 scope 去重后
   只观测一次」；好处是既有 `test_temporal_observe_runs_per_temporal_rule` 无需改写，
   且顺带修复乱序事件回退。副作用是底层 `observe` 的调用仍按规则次数发生（第二次为 no-op）。
2. **重复观测仍未消除调用开销**：多规则场景下 `_observe_temporal_event` 仍被调用 N 次（写入幂等）。
   如需彻底去重，可后续把观测提升到规则循环之前（会改动既有测试语义）。
3. **心跳 fail-closed 的运维影响**：未配置 `EDGE_CONTROL_TOKEN` 时云边心跳将被拒（403）。
   这是有意的安全默认；部署云边模式时必须显式配置该密钥。
4. **前端 16 个文件的格式化改动仍留在工作区**，合并前如需清理请单独决策（本次按指示未动）。
5. `docs/issues.md` 仍未纳入版本控制，如需归档可单独提交。
