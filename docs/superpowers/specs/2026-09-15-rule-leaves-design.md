# 规则引擎通用叶子纵切片设计（object_present / zone_enter / count）

> 创建日期：2026-09-15
> 关联：程序设计 `docs/superpowers/specs/2026-09-14-visual-deployment-program-design.md`（§6 规则）
> 范围：**仅 AIStation 云端**（复用已打通的「边缘事件 v2 → 归一化 → 规则判定」；无需改边缘）

## 1. 目标
在 `_match_conditions` 增加通用叶子，并用它们把目录中大量**基于单事件**的场景变为可用（配合已有 det/cls/face/属性/文本事件）：
- `object_present`：存在某类目标（可限定区域/置信度）。
- `zone_enter`：某类目标的中心点落入指定区域（多边形，归一化坐标）。
- `count`：某类目标数量与阈值比较（可选区域限定）。
- （`absence`/`dwell`/`line_cross` 需时序/跟踪 → 归 SP4，不在本切片。）

## 2. 叶子 schema
```jsonc
{ "subject":"object_present", "label":"person", "labels":["person","car"], "region":[[x,y],...], "min_confidence":0.3 }
{ "subject":"zone_enter",     "label":"person", "region":[[x,y],...] }
{ "subject":"count",          "label":"person", "region":[[x,y],...], "op":">=", "value":5 }
```
- `label`/`labels` 可选（缺省任意）；`region` 可选（缺省全画面；**多边形点内判定**，检测框中心点）。
- `count` 的 `op ∈ {">=",">","<=","<","=="}`，`value` 数值。
- 与 `and/or/not`、已有 `attribute`/`text_match`/`ocr_label` 可任意组合。
- 非法/缺失字段 → 该叶子不命中，且**不抛异常**（延续既有约定）。

## 3. 实现
- `inference/service.py::_match_conditions` 增叶子分支；新增纯函数 `_point_in_polygon(x,y,pts)`、`_region_of(leaf)`（归一化多边形解析，clamp/校验）、`_bbox_center(d)`。
- 事件 `detections[]` 的 bbox 为归一化 `{x,y,width,height}`（边缘已归一化）；中心 = `(x+w/2, y+h/2)`。
- 无区域时 `zone_enter` 等价 `object_present`。

## 4. 目录接线
- 对齐 `DET_ZONE`(object_present/zone_enter)、`GATHER`/`OVERCROWD`(count)、`TRAFFIC_DET`、`FIRE_SMOKE`、`FACE_DET`、`FACE_CROWD`(count) 等场景的 `default_rule` 到上述已实现叶子。
- `METER_OCR`/`LPR_LIST` 等保留占位并加 TODO 注释。

## 5. 验收
- 单测：`object_present`（有无/带 label/带 region）、`zone_enter`（内/外/边界/缺区域）、`count`（各 op/阈值/区域）、组合与非法输入不抛异常。
- 场景目录测试：默认规则叶子键名与求值器一致。
- **端到端（云端）**：对 `DET_ZONE` 场景，用 HTTP 回调直投一条事件（含 detections）→ 命中 `object_present`/`zone_enter` 出告警、不命中不出（无需真机 Agent）。
- 兼容：既有 PED_ATTR/OCR/LPR 规则不受影响。

## 6. 风险
- 单事件 `count` 只是“当前帧该事件内的目标数”，非时序滑窗（时序归 SP4）；文档注明。
- 区域坐标为归一化多边形；与边缘 ROI 同语义。
