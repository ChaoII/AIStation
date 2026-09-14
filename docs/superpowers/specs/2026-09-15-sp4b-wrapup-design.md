# SP4-b 收尾设计（line_cross 几何 / GATHER 口径 / absence 心跳）

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md`、`2026-09-15-temporal-leaves-design.md`
- 范围：清三处已知欠账；不含前端与目录 `default_rule` 驱动创建

## 1. 背景

SP4-b 已实现云端时序叶子 `dwell` / `count_window` / `absence`（`backend/app/api/v1/module_video/inference/temporal.py` + `service.py`），但留有三处欠账：

| # | 欠账 | 证据 |
|---|------|------|
| 1 | `line_cross` 无求值器，目录占位 | `scene/catalog.py:75-76`；`2026-09-15-temporal-leaves-design.md` 标注「需边缘几何 → TODO」 |
| 2 | GATHER 滑窗口径不一致 | `catalog.py:92` 参数 `window`「滑窗帧数」vs `catalog.py:96` 规则 `window_sec`「秒」 |
| 3 | absence 无法端到端 | `inference/service.py:476` 空 `detections` 直接早退；`event_bus.cpp:169` 空框直接 return → 静默期无事件到达，absence 永不评估 |

## 2. 目标 / 非目标

**目标**

1. 实现 `line_cross` 云端时序几何求值器并接线目录 `LINE_CROSS`。
2. 统一 GATHER 滑窗参数为 `window_sec`（秒）。
3. 打通 `absence` 端到端：Agent 空事件心跳 → 云端空事件评估 → 告警（含防抖）。

**非目标**

- SP5 前端（规则编辑器 / 场景表单 / 事件可视化）。
- 目录 `param_schema` / `default_rule` 驱动任务创建（归 SP5）。
- `line_cross` 边缘几何（Agent 侧轨迹判定）——本切片走云端时序几何。
- 人脸 REC/ATTR/ANTISPOOF。

## 3. 设计

### 3.1 line_cross 云端时序几何

**状态扩展**（`inference/temporal.py`）

时序哈希 `ai:temporal:{camera_id}:{alarm_type}:{label}:{scope}` 每个轨迹 field 追加两个位置字段：

- `{field}\x1fpos_p`：上一观测中心 `"x,y"`（round 6）
- `{field}\x1fpos_c`：当前观测中心 `"x,y"`

其中 `{field}` 复用既有 `_field(track_id, ts)`（`t:{id}` 或 `e:{ts}`）。

`observe()` / `_observe_locked()` 增加位置写入（复用既有「同锁读-改-写」保证原子）：

```
new = center(det)                      # bbox 中心；无 bbox 跳过该框
old_c = parse(current[f"{field}\x1fpos_c"])
mapping[f"{field}\x1fpos_c"] = new
if old_c is not None: mapping[f"{field}\x1fpos_p"] = old_c
```

- 现有 `query()` 只识别 `\x1ffirst` / `\x1flast` 后缀，位置字段不影响其行为（向后兼容）。
- 新增 `query_positions(camera_id, alarm_type, label, scope) -> {field: (prev|None, cur|None)}`，复用 `_keys` / `_read_hash`。
- 无 bbox 的框（如 OCR 文本行）不写位置，不产生误判。

**求值**（`service.py`）

- `TEMPORAL_SUBJECTS` 增加 `"line_cross"`（从而被 `_iter_temporal_leaves` 收集并写入观测）。
- `_eval_temporal` 增加 `line_cross` 分支（纯读取，无副作用）：
  - `line`：折线 ≥2 点，取**首尾两点** `L0→L1` 作为有向线段（起点 `L0`）。
  - `dir ∈ {"A2B","B2A","both"}`，默认 `A2B`。
  - 对每条 field 取 `(prev, cur)`；两者都存在才参与判定（首帧无 prev → 不命中，避免误报）。
  - 方向符号 `s(P) = cross(P - L0, L1 - L0)`：
    - `A2B`：`s(prev) > 0 > s(cur)`
    - `B2A`：`s(prev) < 0 < s(cur)`
    - `both`：任一
  - 且 `prev→cur` 线段与 `L0→L1` 线段**真正相交**（交点参数在 [0,1] 区间），避免绊线延长线上的假穿越。
  - `region` 可选：用 `cur` 中心做 `_in_region` 过滤。
  - 命中任一轨迹即 `True`。
- 语义：一次穿越只命中一次（穿越后 `pos_p` 前移到穿越后位置，符号不再变化）；回穿需再跨，可被再次命中。
- 越界为**状态转移**，天然不重复，不再额外节流。

**目录**：`catalog.py` `LINE_CROSS` 去掉 TODO 注释，默认规则改为 `{"op":"and","children":[{"subject":"line_cross","dir":"A2B"}]}`——**不写符号化 `line`**（与 `region` 一致：实际绊线由任务参数在运行时注入，`"line": "line"` 这类字符串引用无法被求值器解析）。`_LINE`（polyline）+ `_DIRECTION` 参数已就绪。`needs_tracking=True` 不变。

### 3.2 GATHER window_sec 口径

`catalog.py` GATHER 的 `param_schema`：

```diff
- {"key": "window", "type": "int", "default": 5, "label": "滑窗帧数"}
+ {"key": "window_sec", "type": "int", "default": 5, "label": "滑窗时长(秒)"}
```

`default_rule`（`window_sec: 5`）不变，二者口径一致。`ACTION_SKELETON` 的 `window`（骨架窗口，姿态语义）不受影响。

### 3.3 absence 心跳端到端

**Agent（`ModelDeploy`）**

- `EventMeta` 增加 `heartbeat_sec`（默认 5，`<=0` 禁用，`>=1` 生效），由任务配置（`config_adapter`）解析。
- `EventBus` 新增 `on_heartbeat(task_id)`：遵守 `schedule_active_now`，装配一条 **空检测** 事件（`detections=[]`、`objects=[]`、`heartbeat=true`、`schema_version=2`）经 `sink_` 发布；不做 ROID/节流过滤。
- `agent_runtime` 新增任务级心跳定时线程：任务运行期每 `heartbeat_sec` 对本任务已注册的 `EventBus` 任务调用 `on_heartbeat`，随任务启停。

**事件契约**（Agent → 云端，新增字段仅为 `heartbeat`）

```json
{
  "event_id": "...", "edge_code": "...", "camera_id": 12, "task_id": 45,
  "algorithm_type": "ABSENT", "ts": "2026-09-15T07:30:00.000Z",
  "detections": [], "objects": [], "heartbeat": true, "schema_version": 2
}
```

**云端（`AIStation`）**

- `edge/consumer.py::normalize_edge_event`：`heartbeat` 随 `**payload` 透传；空 `objects[]` 不派生 `detections`（保持空）——无需改动。
- `inference/service.py::process_detection_callback`：**移除空 `detections` 早退**（`:476`）。改为：
  1. 仍查规则（`algorithm_type` 匹配，`status=True`）。
  2. 若规则含时序叶子 → `_observe_temporal_event` + `_match_conditions`（空检测照常评估）。
  3. 仅在「无检测 **且** 规则不含时序叶子（或规则为空）」时返回 `{"alarm_created": False, "reason": "no_detections"}`。
  4. 告警构造兼容空 `detections`：`description` 在空检测时使用场景文案（如「区域内持续无目标」），`ai_result.detections=[]`、`snapshot_path=None`。
- **absence 防抖**（避免心跳每 `heartbeat_sec` 重复告警）：
  - 新增标量键 `ai:temporal:{camera_id}:{alarm_type}:__absent__:{scope}:{label|__all__}`，值为上次触发 epoch。`label` 取叶子 `label` 且为非空字符串时用其值；叶子缺 `label` 或仅给 `labels` 列表时一律用 `__all__`（避免多标签集合组合爆炸）。
  - `TemporalStore` 新增 `get_absent_fired(...)` / `set_absent_fired(..., ts)`（Redis `setex`，TTL 24h；内存降级用 `_memory_meta`）。
  - `_eval_temporal` 的 `absence` 分支保持**纯读取**：命中需 `(now - last_seen) >= gap` **且**（`fired` 为空 或 `now - fired >= alarm_interval`）。
  - 触发写入由 `process_detection_callback` 在规则命中后执行：遍历 absence 叶子调用 `set_absent_fired(..., now)`；`_eval_temporal` 不写状态，避免 `and/or` 多次求值导致的自相矛盾。
  - 检测恢复后 `last_seen` 推进、`gap` 条件为假，自然再次计时。

## 4. 测试策略

**AIStation**

- `tests/test_line_cross.py`（新增）：相交/不相交、`A2B`/`B2A`/`both` 方向、跨线后不重复、回穿再命中、无 prev 不命中、非法 `line`/`dir` 不抛异常、`region` 过滤。
- `tests/test_temporal_leaves.py`（回归）：位置字段不影响 `dwell`/`count_window`/`absence`；`TEMPORAL_SUBJECTS` 含 `line_cross`。
- `tests/test_absence_heartbeat.py`（新增）：空 `detections` + 含 absence 规则 → 命中并创建告警；`alarm_interval` 内不重复；无历史不命中；规则非时序且空检测 → `no_detections`。
- `tests/test_scene_catalog.py`（回归）：GATHER 参数键为 `window_sec` 且与 `default_rule.window_sec` 一致。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**ModelDeploy**

- `tests/test_event_bus.cpp` 扩展或新增：`on_heartbeat` 产生空检测事件、`heartbeat=true`、遵守 schedule、未注册任务不发布。
- 心跳间隔解析用例（`heartbeat_sec` 默认/最小/禁用）。
- `[agent]` 全量 + `surveillance` 仅编译。

**端到端**

- HTTP/MQTT 联调：播含目标的视频使 absence 规则先积累历史，停止目标后由心跳触发 absence 告警；`line_cross` 用绊线 + 移动目标验证。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 心跳过密导致流量/告警风暴 | 间隔默认 5s 且可配；absence 防抖 `alarm_interval`（默认 30s） |
| 位置字段膨胀 Redis | 仅有点位框写入；既有 `_TTL_SEC=24h` |
| 去早退影响既有非时序规则 | 仅当规则含时序叶子才继续评估；否则维持 `no_detections` |
| line_cross 采样稀疏漏判 | 文档注明依赖事件频率与 track_id；后续可补边缘几何 |
| 事件无 `track_id` | 退化为 `e:{ts}` 单帧，无 prev → 不命中（不误报） |

## 6. 验收标准

1. `line_cross` 目录规则可被真实事件命中；单元测试覆盖方向与边界。
2. GATHER 参数与规则口径一致（`window_sec`）。
3. `ABSENT` 场景在静默期由 Agent 心跳触发告警，且在同一 `alarm_interval` 内不重复。
4. 两仓全量测试通过、ruff 通过；AIStation 与 ModelDeploy 均可编译。

## 7. 兼容性

- `absence` 新增的 `alarm_interval` 判定默认 0 → 既有单测行为不变。
- `query()` / 既有哈希字段语义不变；位置字段为增量。
- 心跳为可选（`heartbeat_sec<=0` 禁用），不影响既有事件流。
