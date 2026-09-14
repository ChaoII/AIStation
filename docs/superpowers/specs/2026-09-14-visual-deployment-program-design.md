# 视觉布控程序（场景注册表 · 规则引擎 · 多模型 pipeline · 加密分发）设计

> 创建日期：2026-09-14
> 状态：方向已确认（全部纳入范围；「任务类型目录」作为 SP2 核心资产一并实现）
> 关联：
> - 云边系统设计 `docs/superpowers/specs/2026-09-12-cloud-edge-visual-analysis-design.md`
> - Agent 交接 `docs/superpowers/specs/2026-09-12-modeldeploy-agent-handoff.md`
> - 契约统一与真机联调 `docs/superpowers/specs/2026-09-13-edge-agent-contract-e2e-design.md`
> - ModelDeploy 侧资产：`examples/demo_*`、`tools/convert/models.json`、`csrc/encryption/`

## 1. 目标与范围

把 AIStation 从「通用检测事件链路」升级为**多模型 pipeline 的视觉布控平台**：

- **边缘**：解码 → 按场景组装的模型 pipeline（det/cls/face/ocr/lpr/pose/seg/obb/depth/track/attr/action/barcode/reid/sam）→ 事件 v2（带 track/属性/统计）。
- **云端**：**任务类型目录（场景注册表）** 为核心资产；场景模板驱动编排；**规则引擎**判定告警；模型格式/后端矩阵 + 加密分发。
- **安全**：模型可加密下发，边缘自动解密加载。

**全部纳入范围**（用户明确）：模型族全覆盖、规则引擎、场景目录、跟踪时序、多后端/加密、前端。

## 2. 架构总览

```
AIStation（云）                                        ModelDeploy Agent（边）
┌───────────────────────────────┐                    ┌───────────────────────────────────┐
│ 场景注册表 scene catalog       │   TaskConfig v2    │ 解码 → pipeline 组装（多模型）     │
│  ├ 场景类型/参数 schema        │ ─────────────────▶ │  ├ det/cls/face/ocr/lpr/pose/...  │
│  ├ 模型 pipeline 规格          │                    │  ├ tracker（可选）                │
│  ├ 所需边缘能力                │                    │  └ ROI/时段/节流/快照             │
│  └ 默认规则                    │                    │ 事件 v2（objects+attributes+...）  │
│ 模型分发（格式矩阵+加密）      │                    │        │ MQTT/HTTP               │
│ 规则引擎（条件树+Redis 状态）  │ ◀──────────────────┘        ▼                          │
│ 告警/联动/通知/审计            │                    │ 受控快照 / 预览                   │
│ 前端：场景表单/规则编辑器      │                    └───────────────────────────────────┘
└───────────────────────────────┘
```

原则：**感知在边缘，决策在云端**；规则/RBAC/告警复用既有链路；规则热更新不改边缘。

## 3. SP2 核心资产：任务类型目录（Scene Catalog）

场景码 → 名称 → pipeline → 参数 → 规则判定 → 是否需跟踪 → 所需边缘能力。模型路径为 ModelDeploy 真实示例（相对 `E:\CLionProjects\ModelDeploy\`），shape 取自 `tools/convert/models.json`。

### 3.1 目标检测类
| 场景码 | 名称 | pipeline / 模型（示例） | 关键参数 | 默认规则 | 跟踪 |
|---|---|---|---|---|---|
| `DET_ZONE` | 区域入侵 | `test_models/onnx/zhgd_det.onnx`（人体）/`onnx/yolo26n/yolo26n.onnx` | ROI、labels、conf | 区域内出现目标 | 否 |
| `LINE_CROSS` | 越界/绊线 | det | 线、方向 | 轨迹穿线 | ✅ |
| `LOITER` | 徘徊/停留 | det | ROI、min_sec | 区域内停留 >T | ✅ |
| `GATHER` | 聚集 | `onnx/zhgd_det.onnx` | ROI、count≥N、window | 滑窗计数 | ✅ |
| `OVERCROWD` | 超员 | det | ROI、max_count | 计数>阈值 | 可选 |
| `ABSENT` | 离岗/无人 | det | ROI、gap_sec | 区域内无目标 >T | 可选 |
| `ILLEGAL_PARK` | 车辆违停 | `onnx/yolo26n/yolo26n.onnx` | ROI、dwell_sec | 车辆停留 >T | ✅ |
| `ABANDON` | 遗留/抛洒物 | det | ROI、dwell_sec | 静止 >T | ✅ |
| `FIRE_SMOKE` | 烟火 | det 自定义 | ROI、conf | 命中 label | 否 |
| `TRAFFIC_DET` | 交通目标 | `yolo26n.onnx` | ROI、labels | 命中/计数 | 可选 |
| `PED_ATTR` | **工作服/安全帽/反光衣/安全带** | `onnx/zhgd_det.onnx`(1x3x1280x1280) + `onnx/zhgd_ml.onnx`(1x3x256x192) | ROI、属性映射、conf、cls_thr | `attribute(field)==false` | 否 |

### 3.2 分类类
| 场景码 | 名称 | pipeline / 模型 | 参数 | 规则 |
|---|---|---|---|---|
| `SCENE_CLS` | 场景/状态分类 | `onnx/yolo11n/yolo11n-cls.onnx`(224) | ROI、topk | label∈集合 |
| `DEFECT_CLS` | 缺陷/异常分类 | cls 自定义 | ROI、阈值 | 命中异常类 |
| `ACTION_CLS` | 视频动作 | `tsn.onnx`（argv，demo_action） | clip、topk | 命中动作 |
| `ACTION_SKELETON` | 骨架动作 | `stgcn.onnx` + `onnx/yolo11n/yolo11n-pose.onnx` | 窗口 | 命中骨架动作 |

### 3.3 姿态/行为
| 场景码 | 名称 | pipeline / 模型 | 规则 |
|---|---|---|---|
| `FALL` | 跌倒 | `onnx/yolo11n/yolo11n-pose.onnx` | 关键点几何 |
| `SMOKE_PHONE` | 抽烟/打电话 | pose/det | 手-头/手-耳几何+时长 |
| `CLIMB` | 攀爬/翻越 | pose/det | 关键点高度/越线 |
| `NO_MASK` | 未戴口罩 | det/cls | 命中 label |
| `HAND_GESTURE` | 手势 | `hand::HandKeypoint`（argv） | 21 关键点 |

### 3.4 分割/旋转框
| 场景码 | 名称 | pipeline / 模型 | 规则 |
|---|---|---|---|
| `I_SEG` | 实例分割 | `onnx/yolo11n/yolo11n-seg.onnx` | 区域内实例 |
| `SEM_AREA` | 语义区域 | `onnx/yolo26n/yolo26n-sem.onnx` | 区域类别占比 |
| `SAM_SEG` | 交互分割 | `onnx/FastSAM-s.onnx` | 提示点分割 |
| `OBB_DET` | 旋转目标 | `onnx/yolo11n/yolo11n-obb.onnx` / `yolo26n-obb.onnx`(1024) | 命中/区域 |

### 3.5 人脸（face pipeline）
| 场景码 | 名称 | pipeline / 模型 | 规则 |
|---|---|---|---|
| `FACE_DET` | 人脸检测 | `onnx/seetaface/scrfd_2.5g_bnkps_shape640x640.onnx`(640) | 区域内人脸 |
| `FACE_REC` | 人脸识别 | scrfd + `onnx/seetaface/face_recognizer.onnx`(248) | 命中/相似度 |
| `STRANGER` | 陌生人 | 同上 + 底库 | 未命中底库 |
| `FACE_ATTR` | 性别/年龄 | + `gender_predictor.onnx`(112)/`age_predictor.onnx`(256) | 属性命中 |
| `FACE_ANTISPOOF` | 活体 | + `fas_first.onnx`(224)+`fas_second.onnx`(300) | 非活体 |
| `FACE_LANDMARK` | 人脸关键点 | insightface `2d106det`(192) | 关键点规则 |
| `FACE_CROWD` | 人脸计数 | scrfd | 计数 |

### 3.6 车牌 / OCR / 文档
| 场景码 | 名称 | pipeline / 模型 | 规则 |
|---|---|---|---|
| `LPR` | 车牌识别 | `onnx/yolov5plate.onnx`(640) + `onnx/plate_recognition_color.onnx`(48x168) | 命中车牌 |
| `LPR_LIST` | 车牌黑白名单 | 同上 | ∈名单 |
| `OCR_TEXT` | 通用文本 | `onnx/ocr/ppocrv4_mobile/{det,cls,rec}_infer.onnx` + `test_data/ppocrv4_dict.txt`（或 ppocrv5/v6：det 960/cls 48x192/rec 48x320） | 文本∈/正则 |
| `METER_OCR` | 仪表读数 | 同上 | 数值阈值 |
| `DOC_TABLE` | 文档/表格 | `demo_doc`（layout+formula + `--ocr`/`--table`） | 结构/文本规则 |
| `BARCODE` | 条码/二维码 | `demo_barcode`（zxing，无模型） | 码值匹配 |

### 3.7 其他
| 场景码 | 名称 | pipeline / 模型 | 规则 |
|---|---|---|---|
| `DEPTH_SAFE` | 安全距离 | `onnx/yolo26n/yolo26n-depth.onnx` | 距离阈值 |
| `REID_TRACK` | 跨镜重识别 | `vision/reid/ReID`(OSNet)+`gallery` | 跨相机关联 |
| `DEPLOY_TRACK` | 通用跟踪 | det + `tracking` | track 生命周期 |

> 详细每类定义（参数 schema、默认规则、所需能力）以 AIStation 场景注册表模块为准（§4）。

## 4. 场景注册表（AIStation，SP2 实现）

新增 `backend/app/api/v1/module_video/scene/`：
- `catalog.py`：**单一事实源**，定义每个场景：
  ```python
  SceneDef(
    code="PED_ATTR", name="工作服/安全帽", category="attribute",
    model_families=["pedestrian_attribute"],
    pipeline=[{"role":"det","type":"detection","required":True},
              {"role":"cls","type":"classification","required":True}],
    param_schema=[ {"key":"attributes","type":"list"}, {"key":"conf","type":"float","default":0.4},
                   {"key":"cls_thr","type":"float","default":0.5}, {"key":"roi","type":"polygon"} ],
    default_rule={...}, needs_tracking=False,
    edge_capabilities={"model_families":["pedestrian_attribute"]},
  )
  ```
- `schema.py` / `controller.py`：`GET /video/scene/catalog`、`GET /video/scene/catalog/{code}`（前端据此渲染表单）。
- `init_app`：可选落 DB 供参考/权限；前端也可直接消费 API。

对齐：`AlgorithmModel.scene_type`（新增）指向场景码；`param_meta` 由 `param_schema` 生成；`orchestrator.build_agent_task_config` 按场景 `pipeline` 产出模型条目。

## 5. 边缘契约 v2（ModelDeploy）

### 5.1 TaskConfig 扩展
- `models[]` 支持 pipeline 型条目：`type` ∈ {`detection`,`classification`,`face_detection`,`pedestrian_attribute`,`ocr`,`lpr`,`face_rec`,`face_attr`,`face_as`,`pose`,`iseg`,`sem`,`obb`,`depth`}；字段含 `det_url/cls_url/rec_url/dict_url/...`、`labels`、`attributes`、`password`（加密模型）、阈值、`input_size`。
- `scene_type`（透传）、`tenant`、`algorithm_type`（保留）、`schedule`、`roi`、`events.snapshot`、`preview`（沿用）。
- `decoder/encoder` 沿用；`backends` 由设备能力决定。

### 5.2 事件 v2（向后兼容，`schema_version=2`）
```jsonc
{
  "event_id": "...", "edge_code": "edge-01", "camera_id": 7, "task_id": 123,
  "scene_type": "PED_ATTR", "algorithm_type": "PED_ATTR",
  "ts": "...",
  "objects": [
    { "track_id": 12, "label": "person", "label_id": 0, "confidence": 0.91,
      "bbox": {"x":0.1,"y":0.2,"width":0.15,"height":0.3},
      "attributes": { "safety_helmet": {"label":"no","score":0.12},
                      "work_uniform":  {"label":"no","score":0.20} } }
  ],
  "regions": [ {"region_id":"R1","count":6,"labels":{"person":6}} ],
  "lines":   [ {"line_id":"L1","crossings":[{"track_id":12,"dir":"A2B"}]} ],
  "detections": [ ... ],   // 兼容保留
  "snapshot": {"data":"<base64>","width":640,"height":360},
  "latency_ms": 12.3, "schema_version": 2
}
```

### 5.3 模型分发 / 格式矩阵 / 加密
- 每个逻辑模型可有多后端产物（onnx/mnn/engine/bmodel），来自 `tools/convert/*`（含 int8 qtable）。AIStation 按设备 `capabilities.backends` 选文件；`model_fetcher` 走 local/http/s3。
- 加密：`TaskConfig.models[].password`；Agent `RuntimeOption::set_model_path(path, password)` 自动识别/解密/切后端（`csrc/runtime/runtime_option.cpp:36-70`）。密钥由 AIStation 下发或 Agent 环境提供。
- `input_size` 默认取 `tools/convert/models.json`。

## 6. 云端规则引擎（AIStation，SP3）

- **数据模型**：`AlarmRuleModel` 增 `conditions`（JSONB，条件树）；保留 `schedule/interval_seconds/severity/notify_channels`。
- **叶子原语**：`object_present / zone_enter / zone_exit / zone_dwell / line_cross(dir) / count(op,window) / density / absence(gap) / attribute(field,value,score) / text_match(regex) / ocr_label / meter_value / barcode_match / face_match|stranger|gender|age|anti_spoof / lpr_match(list) / pose_geo(fall|phone|smoke|climb) / action_class / seg_ratio / depth / reid_match`。
- **组合**：`and/or/not` 嵌套。
- **有状态**：Redis（滑窗计数、轨迹/穿越状态、冷却 `interval_seconds`）。
- **执行点**：`EdgeEventConsumer`（MQTT）与 HTTP 回调**共用**事件归一化（v2）后进入规则引擎；命中→建 `alarm_record`→联动/通知（复用现有 `EventService.execute_linkage_actions` + `dispatch_notification`）。
- **热更新**：规则存 DB，改动即生效，边缘无感。

## 7. 第一刀纵切片：`PED_ATTR`（工作服/安全帽）端到端

目标：贯通「场景注册表 → 编排 → 边缘 pipeline → 事件 v2 → 云端属性规则 → 告警（含快照）」。真实资产：`zhgd_det.onnx` + `zhgd_ml.onnx`（多标签：safety_helmet/reflective_vest/safety_rope/work_uniform…）。

### 7.1 边缘（ModelDeploy Agent）
- 新增模型类型 `pedestrian_attribute`：`vision::PedestrianAttribute(det, cls, opt)`；`set_det_threshold/set_det_input_size/set_cls_input_size/set_cls_batch_size`；`predict → AttributeResult[]`（`box/box_label_id/box_score/attr_scores`）。
- 结果映射：按 `TaskConfig.models[].attributes`（属性名↔attr_scores 下标）→ `objects[].attributes`。
- 事件：`objects` + `schema_version=2`，保留 `detections`。
- 能力上报：`capabilities.model_families += ["pedestrian_attribute"]`。

### 7.2 云端（AIStation）
- 场景 `PED_ATTR` 注册（§4）；`AlgorithmModel.scene_type="PED_ATTR"`（含 det/cls 路径、属性映射、阈值）。
- 编排：`build_agent_task_config` 产出 pipeline 模型条目（含 `det_url/cls_url/labels/attributes/password`）。
- 规则：`attribute(field="work_uniform", equals="no", min_score=0.5)` 等；事件归一化到 v2 后判定；命中→告警。
- 前端（最小）：场景选择 + 属性规则表单。

### 7.3 验收
- 单测：Agent `config_adapter`（pipeline/attributes）、`event_bus`（v2/属性）；AIStation 场景注册/编译、属性规则判定、`normalize_edge_event` v2。
- 真机：起 Agent（本地 det+cls）→ 下发布控 → 事件含 `objects[].attributes` → 违规出告警（含快照）、合规/无属性不出。
- 兼容：旧 `detections` 事件仍能建告警。

## 8. 子项目拆解与顺序

| 子项目 | 内容 | 仓库 |
|---|---|---|
| **SP1 边缘多模型 pipeline + 事件 v2 + 模型分发/加密** | 逐族实现 pipeline（先 pedestrian_attribute，再 ocr/lpr/face/pose/seg/obb/depth/track/action/barcode/reid/sam）；事件 v2；格式矩阵 + 加密 + 能力上报 | ModelDeploy |
| **SP2 场景注册表（目录核心资产）** | `scene/catalog.py` + API + 与 `AlgorithmModel.scene_type`/`param_meta` 对齐；前端场景表单 | AIStation |
| **SP3 规则引擎** | 条件树 + 叶子 + Redis 有状态 + 告警/联动/通知 + 规则 CRUD | AIStation |
| **SP4 跟踪/时序** | 边缘 tracker + 状态变化事件 + 云端滑窗（越界/聚集/停留） | 双侧 |
| **SP5 前端** | 规则编辑器、场景表单、事件/规则可视化、快照/预览 | AIStation 前端 |
| **SP6 进阶** | 跨相机/多规则组合、规则灰度、模型热更新 | 双侧 |

**执行顺序**：SP2（注册表骨架 + `PED_ATTR` 定义）→ SP1（`pedestrian_attribute` 纵切片）→ SP3（最小规则引擎 + 属性叶子）→ 真机联调（§7）→ 再批量扩 SP1 其它族 + SP3 其余叶子 → SP4 → SP5 → SP6。

## 9. 风险与取舍
- **模型分发/转换**：不同后端产物需预先转换（`tools/convert`）；边缘 `backends` 决定选文件；加密需密钥管理。
- **规则有状态**：滑窗/轨迹放 Redis；断网期由 Agent durable queue 缓存状态事件，恢复按 `ts` 补算（注意时序）。
- **跟踪精度**：越界/聚集依赖 tracker 质量；先做稳定 det + ROI 类场景。
- **兼容**：事件 v2 必须向后兼容 v1（保留 `detections`）；TaskConfig 新增字段可选。
- **规模**：场景/叶子/模型族数量大，按子项目与纵切片渐进，避免一次性大爆炸。

## 10. 验收标准
- 场景目录：`GET /video/scene/catalog` 覆盖 §3 全部条目，字段含 pipeline/参数/默认规则/所需能力。
- 第一刀：`PED_ATTR` 真机端到端通过（MQTT+HTTP，含快照与属性判定）。
- 规则引擎：条件树叶子上线并可热更新；Redis 有状态计数/穿越正确。
- 模型分发：按后端选格式、加密模型可加载；`input_size` 与 `models.json` 一致。
- 无回归：既有测试全绿；`application/surveillance` 不变。
