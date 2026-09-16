# OCR 纵切片设计（OCR_TEXT / METER_OCR）

> 创建日期：2026-09-15
> 状态：方向已确认（用户选定 OCR 为下一刀）
> 关联：程序设计 `docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md`（§3 目录 / §5 契约 / §6 规则）
> 复用：已打通的「边缘 pipeline → 事件 v2 → 云端场景/规则 → 告警」路径（PED_ATTR 切片）

## 1. 目标
让 Agent 支持 **`ocr` pipeline（PPOCR det+cls+rec + 字典）**，事件 v2 的 `objects[].text` 携带识别文本，云端 `OCR_TEXT`/`METER_OCR` 场景用 **`text_match`（正则）/`ocr_label`（包含）** 规则判定告警。

## 2. SDK 资产（真实）
- Pipeline：`modeldeploy::vision::ocr::PaddleOCR(det, cls, rec, dict, opt)` → `predict(image, &OCRResult)`。
- `OCRResult`：`boxes`(vector<array<int,8>> 四点框)、`text`(vector<string>)、`rec_scores`、`cls_scores`、`cls_labels`。
- 示例模型（`test_data/test_models/onnx/ocr/ppocrv6_tiny/`）：`det_infer.onnx`(1x3x960x960)、`cls_infer.onnx`(1x3x48x192)、`rec_infer.onnx`(1x3x48x320)；字典 `test_data/ppocrv6_tiny_dict.txt`（另有 ppocrv4/v5）。
- 示例图像：`test_data/test_images/ocr2.jpg`（含文本框）。

## 3. 边缘契约（ModelDeploy Agent）
- 新增模型类型 `ocr`；`ModelConfig` 增 `cls_path`、`dict_path`（`path`=det、`rec_path`=rec）。
- `config_adapter`：`type=="ocr"` 时映射 `det_url→path`、`cls_url→cls_path`、`rec_url→rec_path`、`dict_url→dict_path`（本地/远端 fetch 复用）。
- `InferenceEngine`：新成员 `ocr_model_`（`PaddleOCR`）；`load()` 分支构造 `PaddleOCR(path, cls_path, rec_path, dict_path, opt)`，`set_rec_batch_size(8)`、det `set_max_side_len(1440)`；`infer_ocr` → 把 `OCRResult` 映射为 `DetectionBox` 列表：`text`、`text_score=rec_scores[i]`、bbox=四点框的最小外接矩形。
- `DetectionBox` 增 `std::string text; float text_score;`（默认空/0，其它模型不受影响）。
- 事件 v2：`objects[]` 增 `"text"`、`"text_score"`（非空才写）；`detections[]` 兼容保留；`from_json` 往返保留 text。
- 能力上报：`capabilities.model_families += "ocr"`。

## 4. 云端契约（AIStation）
- `normalize_edge_event`：`objects[].text/text_score` 原样并入 `detections[]`（与 attributes 同法）。
- 规则引擎：新增叶子
  - `{"subject":"text_match","regex":"..."}`：任一 detection 的 `text` 命中正则。
  - `{"subject":"ocr_label","contains":"..."}`：任一 `text` 包含子串。
- 场景：`OCR_TEXT`（文本命中/正则）、`METER_OCR`（数值阈值，先用 `text_match`+数值解析占位）。
- 编排：`build_agent_task_config` 在 `scene_type ∈ {OCR_TEXT, METER_OCR}` 时产出单条 `ocr` pipeline 条目 `{type:"ocr", det_url, cls_url, rec_url, dict_url, labels:[], input_size, confidence_threshold}`；顶层 `scene_type`。

## 5. 真机 E2E
- 夹具：`ppocrv6_tiny` det/cls/rec + `ppocrv6_tiny_dict.txt` + 由 `ocr2.jpg` 生成的短视频（复用「图片循环成视频」做法）。
- 规则（链路验证）：`text_match` 命中图像中确实存在的词，或 `ocr_label contains` 一个稳定子串；断言告警 `ai_result.detections[].text` 非空且命中。
- 若识别文本不稳定，则退化为断言「OCR 事件到达且 text 非空」，规则用「任一 text 存在」（新增叶子 `text_present` 或 `text_match` regex `.+`）。

## 6. 验收
- 单测：Agent `config_adapter`(ocr 映射)、`inference_engine`(ocr 加载/映射)、`event_bus`(text 往返)；AIStation 场景编译、`text_match/ocr_label` 判定、归一化 text。
- 真机：OCR 事件到达、`objects[].text` 非空、规则命中出告警（含快照）。
- 兼容：v1 事件与其它模型族不受影响；`application/surveillance` 不变。

## 7. 风险
- 识别文本依赖图像质量；E2E 规则用稳定子串或 `.+` 兜底。
- det 输入尺寸需按模型元数据（复用 PED_ATTR 的做法，取 `get_detector()->get_input_info(0).shape` 或 `set_max_side_len`）。
- 多模型（det+cls+rec）加载内存/耗时更高。
