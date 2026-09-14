# LPR 车牌纵切片设计（LPR / LPR_LIST）

> 创建日期：2026-09-15
> 关联：程序设计 `docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md`（§3 目录 / §5 契约 / §6 规则）
> 复用：已打通的「边缘 pipeline → 事件 v2 → 云端场景/规则 → 告警」路径

## 1. 目标
Agent 支持 **`lpr` pipeline（车牌检测 + 识别）**，事件 v2 `objects[].text` 携带车牌号；云端 `LPR`/`LPR_LIST` 场景用既有 **`text_match`（车号正则）/`ocr_label`（车号包含）** 规则判定告警（无需新叶子）。

## 2. SDK 资产（真实）
- Pipeline：`modeldeploy::vision::lpr::LprPipeline(det, rec, opt)` → `predict(image, &vector<LprResult>)`。
- `LprResult`：`box`(Rect2f)、`keypoints`(4 点)、`label_id`、`score`、`car_plate_str`、`car_plate_color`。
- 示例模型：`test_models/onnx/yolov5plate.onnx`(det) + `test_models/onnx/plate_recognition_color.onnx`(rec)。

## 3. 边缘契约（ModelDeploy Agent）
- 新增模型类型 `lpr`；`ModelConfig` 复用 `path`(det)+`rec_path`(rec)。
- `config_adapter`：`type=="lpr"` 时 `det_url→path`、`rec_url→rec_path`（本地/远端 fetch）。
- `InferenceEngine`：新成员 `lpr_model_`（`LprPipeline`）；`load()` 构造 `LprPipeline(path, rec_path, opt)`；`infer_lpr` → 把 `LprResult` 映射为 `DetectionBox`：`text=car_plate_str`、`text_score=score`、bbox=box（后端 `event_bus` 归一化）。
- 复用已实现的 `DetectionBox.text/text_score` 与事件 v2 `objects[].text`。
- 能力上报：`capabilities.model_families += "lpr"`。
- `pipeline_manager.create_engine` 路由 `lpr`（直接 load，同 classification/ocr/pedestrian_attribute）。

## 4. 云端契约（AIStation）
- 编排：`build_agent_task_config` 在 `scene_type ∈ {LPR, LPR_LIST}` 时产出单条 `lpr` pipeline 条目 `{type:"lpr", det_url:algorithm.model_path, rec_url, labels, input_size, confidence_threshold}`。
- 场景 `LPR`/`LPR_LIST` 已在目录；其 `default_rule` 对齐到实现叶子（`text_match` regex / `ocr_label` contains）。
- 规则引擎复用 `text_match`/`ocr_label`（无新叶子）。
- `normalize_edge_event` 已支持 `objects[].text` 并入 `detections[]`（无需改）。

## 5. 真机 E2E
- 夹具：`yolov5plate.onnx` + `plate_recognition_color.onnx` + 含车牌图像（`test_data/test_images/`，如 `plate_*.jpg`，实施时确认）。
- 规则（链路验证）：`text_match` regex `.+`（任一车牌命中）。断言告警 `algorithm_type=LPR` 且 `ai_result.detections[].text` 非空。

## 6. 验收
- 单测：Agent `config_adapter`(lpr 映射)、`inference_engine`(lpr 加载/映射)、`event_bus`(text 复用)；AIStation 编排 lpr、场景默认规则键名一致。
- 真机：LPR 事件到达、`objects[].text`（车号）非空、规则命中出告警（含快照）。
- 兼容：v1 与其它模型族不受影响；`application/surveillance` 不变。

## 7. 风险
- 车牌图像素材需确认存在；无则不跑真机，仅单测（沿用 SKIP 约定）。
- LprResult 的 `car_plate_color` 本期不入事件（可后续并入 `objects[].attributes` 或新增字段）。
