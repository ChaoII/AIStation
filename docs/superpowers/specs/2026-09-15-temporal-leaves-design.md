# SP4-b 时序规则叶子设计（dwell / count_window / absence）

> 创建日期：2026-09-15
> 关联：程序设计 spec §6；SP4 跟踪切片 `2026-09-15-tracking-slice-design.md`
> 范围：**仅 AIStation 云端**（复用事件 v2 的 `detections[].track_id`）

## 1. 目标
在 `_match_conditions` 增时序/窗口叶子，把目录中需时序的场景变为可用（配合 SP4 的 `track_id`）：
- `dwell`：某轨迹（track_id）持续存在 ≥ `min_sec`。
- `count_window`：窗口 `window_sec` 内出现的**去重目标数**（按 track_id，缺 track_id 时按事件）比较阈值。
- `absence`：某类目标距上次出现 ≥ `gap_sec`（在任一相关事件到达时评估）。
- `line_cross`：需边缘几何 → 本切片 **TODO 占位**（记录）。

## 2. 叶子 schema
```jsonc
{ "subject":"dwell",        "track_id":42, "label":"person", "min_sec":5 }
{ "subject":"count_window", "label":"person", "window_sec":60, "op":">=", "value":5 }
{ "subject":"absence",      "label":"person", "gap_sec":120 }
```
- 可选 `region` 复用 `_in_region`（按 bbox 中心）限定。
- 非法/缺失 → 不命中且不抛异常。

## 3. 状态存储
- 复用 `settings.REDIS_*`；`REDIS_ENABLE=false` 或不可用时**降级为进程内字典**（带锁），保证可测。
- Key：`ai:temporal:{camera_id}:{alarm_type}:{label}` → hash/ZSET(track_id → first_seen/last_seen 时间戳)。
- `dwell`：`now - first_seen(track_id) >= min_sec`（轨迹需仍然活跃：`now - last_seen <= grace_sec`，grace 取 `max(min_sec, alarm_interval)`）。
- `count_window`：窗口内 `last_seen >= now-window_sec` 的去重 track_id 数（无 track_id 计 1）。
- `absence`：`now - last_seen(label) >= gap_sec`（无历史视为尚未过期→不命中；需至少一次历史）。
- 时间源：事件 `frame_timestamp`（可注入，便于单测）。

## 4. 接线
- 目录 `LOITER`/`ABSENT`/`GATHER` 等对齐到这些叶子（带 TODO 注释说明依赖 track_id；无 track_id 时以事件计数近似）。
- `process_detection_callback` 在评估前把 `event` 的 detections 与时间戳写入状态存储（仅当 rule.conditions 含时序叶子时，避免无谓开销）。

## 5. 验收
- 单测（fakeredis 或内存降级）：`dwell` 达标/未达标/轨迹过期；`count_window` 去重计数与 op；`absence` 有历史超时/未超时/无历史；非法输入不抛异常；时间可注入。
- 兼容：无时序叶子的规则行为不变；现有 434+ 测试全绿。
- 云端端到端（可选）：构造带 track_id 的多次回调，验证 `dwell` 命中出告警。

## 6. 风险
- 事件受 `alarm_interval` 节流 → 时序粒度粗（文档注明；越界宜边缘判定，line_cross 见 TODO）。
- 多实例部署共享 Redis；单实例内存降级不跨进程（文档注明）。
