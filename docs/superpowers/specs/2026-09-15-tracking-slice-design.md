# SP4 跟踪纵切片设计（边缘跟踪 → track_id 端到端）

> 创建日期：2026-09-15
> 关联：程序设计 `docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md`（§5 事件 v2 / §6 规则）
> 范围：**边缘跟踪 + 事件 `objects[].track_id` 端到端**（云端时序叶子 `dwell/count(window)/absence/line_cross` 归 SP4-b）

## 1. 目标
Agent 支持**逐帧目标跟踪**（ByteTrack），在检测结果上附加稳定 `track_id`，经事件 v2 `objects[].track_id` 上报，供后续时序规则（越界/聚集/停留）与去重使用。

## 2. SDK 资产
- `modeldeploy::vision::tracking::{ByteTracker,BotSORT,StrongSORT}`：`update(vector<Detection>, frame*, ts) -> vector<TrackResult>`；`TrackResult{track_id, box, score, label_id, state}`；`ByteTracker::set_params(track_thresh,high_thresh,low_thresh,max_age,min_hits,iou_threshold)`。

## 3. 边缘契约（ModelDeploy Agent）
- TaskConfig 增可选 `tracking: {enabled: bool, algorithm: "bytetrack"|"botsort"}`（默认关闭）。
- `DetectionBox` 增 `int track_id = -1;`。
- `Pipeline`：每个任务持有 `std::unique_ptr<BaseTracker>`（`tracking.enabled` 时按 `algorithm` 创建）；`detect_loop` 在 `run_models` 后，把 detection 结果转 `tracking::Detection`（像素 box/score/label_id）→ `tracker->update(dets, &frame, ts)` → 按 IoU/顺序把 `track_id` 回填到 `DetectionBox`；无跟踪时 `track_id=-1`。
- 事件 v2：`objects[]` 写 `track_id`（>=0 才写）；`from_json` 往返保留 `track_id`。
- 能力上报：`capabilities.model_families += "tracking"`（或 `capabilities.tracking=true`）。
- 兼容：`tracking` 缺省关闭 → 既有任务零差异；`surveillance` 不受影响（sink 默认空）。

## 4. 云端契约（AIStation）
- `normalize_edge_event` 已把 `objects[].track_id` 并入 `detections[]`（无需改）。
- 编排：`build_agent_task_config` 增顶层 `tracking`（来源 `algorithm.runtime_config.tracking` / `preset_params`，缺省不启用）。

## 5. 真机 E2E
- 场景 `LINE_CROSS`/`GATHER` 之一或通用 det 任务 + `tracking.enabled=true`；断言事件 `ai_result.detections[].track_id` 出现且同一目标跨帧稳定。
- 夹具：`test_data/test_video60.mp4`（含目标）+ `yolo11n_nms.onnx`。

## 6. 验收
- 单测：Agent `config_adapter`(tracking 解析)、`pipeline`(跟踪回填 track_id，多帧稳定/单调)、`event_bus`(track_id 往返)。
- 真机：事件含 `track_id`。
- 兼容：关闭跟踪时行为不变；`application/surveillance` 不变。

## 7. 风险
- 跟踪器跨帧状态在 `interval` 抽帧/丢帧下可能断轨（可接受）。
- 事件节流（alarm_interval）会稀疏化轨迹；时序叶子（SP4-b）需注意仅凭稀疏事件无法精确判越界 → 越界宜边缘判定（SP4-b 评估）。
- ROI 裁剪回映射后 box 已为全图像素坐标，tracker 直接可用。
