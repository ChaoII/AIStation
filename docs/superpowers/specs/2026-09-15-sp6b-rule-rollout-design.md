# SP6-b 规则灰度设计（时间段 + 比例 + 白/黑名单）

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md` §8（SP6 进阶）、`2026-09-15-sp6a-rule-scope-group-design.md`
- 范围：AIStation 前后端（规则灰度字段 + 评估 gating + 编辑器灰度区块）

## 1. 背景与现状

| 现状 | 证据 |
|------|------|
| `AlarmRule.schedule_json`（生效时间段）**字段存在但评估完全没消费** | `alarm/model.py` + `alarm/schema.py` 有该字段；`inference/service.py` 只检查 `status`，未读 `schedule_json`（仅 `AlgorithmTask` 的 schedule 经 `edge/orchestrator.py` 下发到边缘执行） |
| `sensitivity` 同样只存不消费 | 全仓仅 seed 数据引用 |
| 规则无"部分生效"能力 | 无 `rollout` 概念 |
| `status` 生效（评估前过滤） | `service.py` `AlarmRuleModel.status.is_(True)` |

因此"新规则先小流量验证再全量"无法表达；规则级时间段是死字段。

## 2. 目标 / 非目标

**目标**

1. 规则级**生效时间段**真正接入评估（`schedule_json`）。
2. **比例灰度**：按 `camera_id` 稳定哈希分桶，规则仅对命中桶的相机生效。
3. **相机白/黑名单**：白名单强制生效、黑名单强制跳过。
4. 灰度可解释（跳过原因可查日志）+ 前端可视化配置与摘要。

**非目标**

- `sensitivity` 接通（属半成品功能，另议）。
- 灰度命中统计报表 / 告警分流报表。
- 事件表记录"被跳过规则"（follow-up）。
- 规则版本分流（新旧规则并行）。

## 3. 设计

### 3.1 数据模型

`AlarmRuleModel` 新增：

```python
rollout: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", comment="灰度配置: {percent, whitelist, blacklist}")
```

- `{"percent": int 0-100, "whitelist": [camera_id], "blacklist": [camera_id]}`；缺省 `{}` 表示**全量生效**。
- `schedule_json` 复用（规则级生效时间段）。
- schema（`AlarmRuleCreate/Update/Out`）：新增 `rollout: dict`。
- 新增 Alembic 迁移（仅该列）。

**校验**（`alarm/service.py`，create/update 均按合并后结果态校验，HTTP 400）：

- `percent` 为整数且 `0 <= percent <= 100`（缺省 0 表示不限？**约定：缺省/不存在 = 全量；显式 100 = 全量**）。
- `whitelist` / `blacklist` 必须是相机 id 列表（正整数），且**交集为空**。

### 3.2 评估 gating（可解释纯函数）

`inference/gating.py`：

```python
def rule_active_now(schedule: dict | None, rollout: dict | None, camera_id: int | None,
                    now: float, *, rule_id: int | None = None) -> tuple[bool, str]:
    """规则此刻对该相机是否生效；返回 (生效?, 原因)。

    原因：schedule | blacklist | whitelist | rollout_all | rollout_bucket | rollout_zero | all
    优先级：时间段 → 黑名单 → 白名单（强制生效）→ 比例（稳定哈希分桶）。
    任何非法/缺失输入按"生效"处理（fail-open），避免灰度配置错误导致规则静默失效。
    """
```

- **时间段**：`schedule_json` 语义与 `AlgorithmTask.schedule` 一致（`[{day,start_hour,end_hour}]`，空=全天）。**注**：为与边缘一致，直接复用既有 schedule 结构；`now` 为事件时间（`to_epoch`）。
- **黑名单**：`camera_id in blacklist` → `(False, "blacklist")`。
- **白名单**：`camera_id in whitelist` → `(True, "whitelist")`（忽略比例）。
- **比例**：`percent <= 0` → `(False, "rollout_zero")`；`>= 100` → `(True, "rollout_all")`；否则
  `bucket = zlib.crc32(f"{rule_id}:{camera_id}".encode()) % 100`，`bucket < percent` → `(True, "rollout_bucket")` 否则 `(False, "rollout_bucket")`。
  - 用 `zlib.crc32`（跨进程稳定），**禁止** Python 内置 `hash()`。

### 3.3 接入点

`process_detection_callback` 遍历作用域匹配规则时：

```python
            active, reason = rule_active_now(rule.schedule_json, rule.rollout, camera_id, event_now, rule_id=rule.id)
            if not active:
                log.info(f"规则 {rule.id} 灰度跳过（{reason}）: camera={camera_id}")
                continue
```

- 被跳过的规则：**不观测时序状态、不评估、不落库**。
- 其他规则不受影响（逐条独立 gating）。
- gating 在**规则层**：`_match_conditions` / `explain_conditions` 不变。
- 返回体：`rule_matched_list` 只含真正命中者；可选新增 `rule_skipped_list`（形如 `[{"rule_id","reason"}]`）便于排查。

### 3.4 前端

`RuleEditor` 新增「灰度」区块：

- **生效时间段**：日/时段选择（参考 `frontend/src/components/Train/SchedulePanel.vue` 的既有交互与数据结构），空=全天。
- **比例**：`el-slider` 0-100 + 数字显示；0 表示"不生效"，100 表示"全量（等同不设灰度）"。
- **相机白名单/黑名单**：两个 `el-select multiple`（相机列表），提交前做交集校验。
- 规则列表/详情显示灰度摘要（如「30%」「白名单 3 台」「09:00-18:00」）。

### 3.5 视觉约束

复用 Element Plus 组件与 `--el-*` 变量；完成后无头截图 + `vision-recognition` 核对。

## 4. 测试与验收

**后端**
- `tests/test_rule_rollout.py`：
  - `rule_active_now` 全分支：空配置 → 生效；时间段内/外/边界；黑名单命中；白名单强制（`percent=0` 也生效）；`percent=0/100/50`；哈希稳定性（同 `rule_id+camera_id` 多次调用同结果）；非法输入 fail-open。
  - 灰度配置校验：`percent=-1/101/非整数` → 400；白黑名单交集非空 → 400。
  - 集成：`percent=0` 的规则不产生告警，同相机其他规则正常告警；组规则按相机分桶（组内部分相机生效）。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**前端**
- `pnpm run type-check`、`pnpm run lint`（本任务文件 0 新增）。
- Playwright e2e：配置灰度（比例 0 + 白名单）→ 保存 → 列表摘要可见 → 回填一致。
- 无头截图 + `vision-recognition` 核对。

**真机**
- 同一相机两条规则：A=`percent=0`（应不告警）、B=`percent=100`（应告警）；再验白名单强制生效。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 灰度配置错误导致规则**静默失效** | 非法/缺失输入 fail-open（按生效处理）；跳过原因写日志；`rule_skipped_list` 可查 |
| 哈希不稳定导致"同一相机时好时坏" | 固定用 `zlib.crc32`，并用单测锁定稳定性 |
| 组规则按相机分桶后聚合语义变化（只计命中桶相机） | 文档明确；列表摘要提示"灰度 30%"；白名单可强制纳入关键相机 |
| 时间段与边缘任务 schedule 语义不一致 | 复用同一 schedule 结构（`[{day,start_hour,end_hour}]`），并写测试对齐 |
| 既有规则行为变化 | `rollout` 缺省 `{}` → 始终生效；`schedule_json` 缺省 → 全天；全量回归锁定 |

## 6. 兼容性

- 新增列 `rollout` 默认 `{}`：既有规则行为完全不变。
- `schedule_json` 此前从未生效，接通后**仅对显式配置了时间段的规则**产生变化（这类规则此前是"全天生效"，现在是"按配置生效"）——属修正死字段，需在发布说明中提示。
- `_match_conditions` / `explain_conditions` / 叶子契约不变。
- 不新增第三方依赖。
