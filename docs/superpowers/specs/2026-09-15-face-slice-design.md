# 人脸纵切片设计（FACE_DET 端到端）

> 创建日期：2026-09-15
> 关联：程序设计 spec §3 目录 / §5 事件 v2 / §6 规则
> 范围：**FACE_DET 端到端**（人脸检测→事件→区域/计数规则）。FACE_REC（识别/底库）/FACE_ATTR（年龄性别）/FACE_ANTISPOOF 归后续。

## 1. 目标
让 Agent 的**人脸检测**（`Scrfd`，已支持 `face_detection`）结果进入事件 v2 `objects[]`，云端 `FACE_DET` 场景用既有 `object_present`/`zone_enter`/`count` 叶子判定告警（无需新叶子）。

## 2. 现状缺口
- Agent `InferenceEngine` 已加载 `face_detection`（`Scrfd`），`InferGroup` 将其归入 `non_det`，`InferResult` 携带 `boxes`+`keypoints`。
- 但 `Pipeline::detect_loop` 的 sink 合并条件为 `!r.attributes.empty() || any_text` → **人脸框无属性/文本，永不进事件**。需把 `face_detection` 结果并入 sink。

## 3. 边缘改动（ModelDeploy Agent）
- `pipeline.cpp` sink 合并：`non_det` 中 `type=="face_detection"`（或有 boxes）的结果，其 boxes 一并并入事件；不影响其它类型。
- 事件 `objects[]`：人脸框已由现有字段承载（label/label_id/confidence/bbox）；可选 `keypoints` 暂不上报（后续 FACE_LANDMARK）。
- 能力：`face` 已在 `model_families`（无需改）。

## 4. 云端改动（AIStation）
- 编排：`build_agent_task_config` 在 `scene_type=="FACE_DET"` 时产出 `{type:"face_detection", url:algorithm.model_path, ...}`（`_resolve_model_type` 已把含 FACE 的算法映射为 `face`，但需显式 `face_detection` 类型码）。
- 目录：`FACE_DET.default_rule` → `{subject:"object_present"}` 或 `zone_enter`/`count`（已实现叶子）。
- 归一化/规则：无需改（对象框即 detections）。

## 5. 真机 E2E
- 场景 `FACE_DET`：`scrfd_2.5g_bnkps_shape640x640.onnx` + 含人脸视频（由 `test_images` 人脸图循环生成）。规则 `object_present`（或 `count>=1`）。断言告警 + `detections[]` 非空（人脸框）。

## 6. 验收
- 单测：Agent `pipeline` 人脸框进 sink（新增 integration 用例，SKIP 缺数据）；AIStation 编排 face 条目 + 目录默认规则。
- 真机：人脸事件到达、告警创建、快照非空。
- 兼容：非人脸模型行为不变；`application/surveillance` 不变。

## 7. 风险
- `Scrfd` 输入为固定 640x640（`input_size`）；按模型元数据/配置处理。
- 人脸图素材需确认；无则真机 SKIP（单测覆盖）。
- FACE_REC/ATTR 需边缘新增 pipeline（`face_rec`/`face_age`/`face_gender`）+ 人脸底库，属后续。
