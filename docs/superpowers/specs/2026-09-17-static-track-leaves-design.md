# SP4-b 扩展：static / track 时序叶子设计（解锁 ABANDON / DEPLOY_TRACK）

> 创建日期：2026-09-17
> 关联：`2026-09-15-temporal-leaves-design.md`（dwell / count_window / absence）
> 范围：仅 AIStation 云端，无新模型、无新依赖

## 1. 目标

复用 `TemporalStore` 已记录的每轨迹 `first/last` 与位置状态，补齐两个可计算的叶子，
使目录中此前因「求值器未实现」而置灰的两个场景变为可配置：

- `static`：**遗留/抛洒物（ABANDON）**——目标静止超过阈值。
- `track`：**通用跟踪（DEPLOY_TRACK）**——存在被跟踪的目标。

## 2. 叶子 schema

```jsonc
{ "subject":"static", "label"?:"person", "labels"?:["person"], "region"?:[[x,y],...],
  "min_sec":10, "max_move"?:0.02, "track_id"?:42 }
{ "subject":"track", "label"?:"person", "labels"?:["person"], "region"?:[[x,y],...], "min_sec"?:5 }
```

- 仅真实轨迹（键形如 `t:{id}` 且 `id >= 0`）参与判定；无 `track_id` 的事件键 `e:{ts}`
  不具备轨迹身份，一律不算。
- 非法/缺失输入 → 不命中且不抛异常（延续既有 fail-closed 约定）。
- `static` 的 `min_sec` 为必填（编译层校验），`max_move` / `track_id` / label / region 可选。

## 3. `static` 语义（产品决策，精确定义）

> 一条轨迹满足以下 **全部** 条件即判为「静止」：
> 1. 轨迹身份有效（`track_id >= 0`）；
> 2. `now - first_seen >= min_sec`（存在时长达到阈值）；
> 3. `now - last_seen <= grace`（仍活跃；`grace = max(min_sec, alarm_interval)`，与 `dwell` 一致）；
> 4. **相对首帧中心的最大位移** `<= max_move`（缺省 `0.02`，归一化坐标下的欧氏距离）。

「最大位移」定义为轨迹所有观测中心相对**首次观测中心** `pos_f` 的距离上确界
（`max_f dist(pos_f, pos_t)`），而非累加路径长度：

- 对检测框逐帧抖动不敏感（抖动只贡献单帧偏差，不会像路径长度那样累积）；
- 能识别「走远又折返」——最大位移仍很大，不会被误判为静止；
- 只随更新的观测时间戳单调不减，乱序事件不会回退。

## 4. 状态存储扩展（最小改动）

`TemporalStore` 每条轨迹新增两个 hash 字段（与 `pos_p/pos_c` 同一把锁、同一次读改写内完成）：

- `pos_f`：首次观测中心 `"x,y"`，只写一次；
- `move`：相对 `pos_f` 的最大位移（浮点），仅当位置随更新的 ts 推进时更新，单调不减。

新增只读查询 `query_moves(camera_id, alarm_type, label, scope) -> {track_key: move}`。
未写入 `move` 的轨迹由求值器按 `0.0` 处理。该扩展不改变 `first/last/pos_p/pos_c` 语义，
`observe` 仍是「单次读 + 单次写」的原子读改写，既有测试保持不变。

## 5. `track` 语义

> 存在至少一条活跃真实轨迹即命中；若声明 `min_sec`，则要求该轨迹存在时长 `>= min_sec`。
> 活跃 = `now - last_seen <= grace`，`grace = max(min_sec or 0, alarm_interval)`。

## 6. 接线

- `inference/service.py`：`static` / `track` 加入 `TEMPORAL_SUBJECTS`（触发观测写入与空检测心跳评估）；
  `_eval_temporal` 增两个分支；`_temporal_detail` 生成 `static {elapsed:.0f}s move={moved:.3f}` / `track {count}`。
- `scene/compile.py`：`dwell_sec` / `min_sec` → `min_sec`（适用 `dwell/static/track`）；
  `labels` 适用集加 `static/track`；新增 `max_move` → `max_move`（仅 `static`）；`static` 必填 `min_sec`。
- `scene/leaves.py`：`static/track` 标记 `implemented: True` 并给出正式参数表。
- `scene/catalog.py`：ABANDON 默认规则改 `{"subject":"static","min_sec":10}`，新增 `max_move` 参数
  （默认 0.02）；DEPLOY_TRACK 默认规则改 `{"subject":"track"}`；两者随之变为可配置（不再置灰）。

## 7. 验收

- 单测：`tests/test_static_track_leaves.py`（命中/未命中/无 track_id/负数 track_id/
  阈值边界/region 分桶/label 过滤/非法输入 fail-closed/detail）；
- 存储：`query_moves` 首帧为 0、取最大位移、乱序不回退、区域分桶隔离；
- 一致性：`test_scene_contract_consistency.py` 断言 ABANDON/DEPLOY_TRACK 现为可配置，
  且仍不可配置场景给出原因；`test_scene_catalog.py` 断言两场景默认规则落到 `static/track`。

## 8. 已知限制

- 事件受 `alarm_interval` 节流时，静止判定的时间分辨率受限于事件频率；
- 轨迹 ReID 断链（track_id 跳变）会重新计为一条新轨迹，可能漏判/延后判定。
