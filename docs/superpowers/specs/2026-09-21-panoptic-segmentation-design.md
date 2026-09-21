# 全景分割（Panoptic Segmentation）标注类型设计

日期：2026-09-21
状态：已确认
范围：在标注工作台新增「全景分割（panoptic_segmentation）」标注类型——整图每个像素都有语义类别标签，其中 thing（实例）类别的每个对象可区分实例。

## 背景与目标

用户希望覆盖主流全景分割（panoptic segmentation）标注。全景分割 = 语义分割 + 实例分割的统一：每个像素既属于某语义类别，也（对 thing 对象）能区分是哪个实例（COCO Panoptic 基准）。当前工作台已有 `segmentation`（实例分割）、`semantic_segmentation`（语义分割），但缺少「类别级 + 实例级 + 整图覆盖」合一的全景分割能力。

目标：新增 `panoptic_segmentation` 标注类型，复用现有 Polygon 形状与语义分割骨架，通过类别 `is_instance` 标记区分 thing/stuff，thing 类多边形自动编号实例，stuff 类垫底覆盖，导出 COCO Panoptic 格式（PNG 掩码 + 段表 JSON）用于训练。

## 决策要点

- **独立任务类型** `panoptic_segmentation`（与语义/实例分割并列，独立插件）。
- **复用 `Polygon` 形状**（不新增形状联合）：全景分割多边形与实例/语义分割同构，仅 thing 类额外携带 `instance_id` 字段；`annotation_data` 为 JSONB 任意字段直接存储。
- **类别 `is_instance` 标记**区分 thing（实例）/stuff（非实例）。
- **`instance_id` 用派生编号**：不写死、不占 core——渲染/导出时对每个 thing 类别的多边形按其在标注数组中的出现顺序编号（组内从 1 起），stuff 段 instance 恒 0。删除/编辑自动重排，标号与导出同源。
- **stuff 垫底**：复用语义分割「填充背景」语义，保证整图覆盖。
- **导出 COCO Panoptic**：每图 panoptic PNG 掩码（像素值 = panoptic id）+ 段表 JSON。

## 1. 类型与后端

### 后端 `backend/app/api/v1/module_annotation/dataset/model.py`
- `AnnotationType` 增加 `PANOPTIC_SEGMENTATION = "panoptic_segmentation"`。

### 数据库迁移
- 新增 alembic 迁移，`ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'PANOPTIC_SEGMENTATION'`（**大写**，与 SQLAlchemy 枚举按成员名存储一致）。
- 需 `op.get_context().autocommit_block()` + `is_postgres(op.get_bind())` 守卫（沿用水印语义分割/折线迁移模式）。
- `down_revision` = 当前 head（折线迁移 `c3d4e5f6a7b8`）。

### 形状
- 前端 `ShapeAnnotation` **不新增**联合类型；复用 `PolygonShape`（`points + class_id`）。thing 段在 `Annotation` 上携带 `instance_id`（运行时由插件/渲染派生，存储可选）。

## 2. 类别 thing/stuff 标记（`is_instance`）

- 任务类别 `{id, name, color}` 增加布尔字段 **`is_instance`**（true=thing 实例类，false=stuff 非实例）。
- 后端类别 schema 增加 `is_instance` 字段（默认 false）。
- 前端任务创建/编辑的**类别编辑**增加一个「实例类(thing)」开关：勾选=thing，不勾=stuff。
- 交互语义：stuff 类面板「填充背景」垫底；thing 类每个多边形按实例渲染并显示实例号。

## 3. 前端插件 `frontend/src/annotation/tasks/panopticSegmentation/`

**零 core 改动**（复用现有骨架，不触碰 `core/`）。

- `usePanopticTool.ts` 或复用 `useSegmentTool`（`points/addPoint/closePolygon`）。
- `PanopticSegCanvas.vue`：基于语义分割 canvas，额外对 thing 类多边形标签显示 `<类别名>#<实例号>`（实例号按派生编号），stuff 类垫底（复用背景垫底排序逻辑）。
- `PanopticSegPanel.vue`：复用「填充背景」面板（选择 stuff 类垫底）；可含「显示实例号」开关。
- `index.ts`（`panopticSegmentationPlugin`）：`name:"panoptic_segmentation"`、`label:"全景分割"`、`create()` 复用多边形校验（`Polygon`、≥3 点、点归一化）。
- 复用 `SegmentPreview.vue` 绘制预览。

**instance_id 派生规则**（渲染/导出统一定义）：
- 对每个 thing 类别（`is_instance=true`）的多边形，按其在 `annotations` 数组中的出现顺序，从 **1 开始递增**编号。
- stuff 类别段无实例号（导出 instance=0）。

## 4. 注册

- `frontend/src/annotation/index.ts` 导出 `panopticSegmentationPlugin`。
- `frontend/src/views/module_annotation/annotation/index.vue` plugins 数组接入。
- `frontend/src/views/module_annotation/task/index.vue` 下拉/label/tag 映射加「全景分割 / panoptic_segmentation / warning」。

## 5. 导出 COCO Panoptic

在 `backend/app/plugin/module_train/exporter.py` 增加导出框架 `panoptic`（`_export_coco_panoptic`）。每图像输出：
- **`panoptic_<stem>.png`**：整图编码掩码，每像素值 = **panoptic id**（uint32/int32）。
- **`panoptic.json`**：`{ info, categories:[{id,name,isthing}], images:[...], annotations:[{id,image_id,category_id,segmentation,area,bbox,iscrowd}] }`。

**id 编码（COCO 规则）**：`panoptic_id = category_id * 1000 + instance_id`。
- thing 段：`instance_id` = 派生编号（按类别内数组顺序从 1 起）。
- stuff 段：`instance_id` 恒 0（`id = category_id * 1000`）。

**重叠/渲染优先级**：先把所有 stuff 段铺满整图（垫底），再叠加 thing 段（后画的覆盖前画的）。用 OpenCV `fillPoly`（或 PIL `ImageDraw.polygon`）栅格化到 uint32 掩码，numpy 合成最终每像素 panoptic id。
- `categories[].isthing`：1（thing）/0（stuff）。
- `annotations[].iscrowd` = 0；每段 `area`/`bbox` 从掩码计算；`segmentation` 存多边形点集（或据此）。

## 6. 错误处理 / 其它

- 某图无任何标注：输出全背景掩码（若配置了 stuff 则其 id，否则全 0）+ 空段表，导出不中断。
- 无 thing 类别、仅 stuff 背景：合法（纯语义），照常导出。
- instance_id 派生规则统一：thing 按类别分组、组内按数组顺序编号；stuff 一律 instance 0。

## 7. 测试

- 后端 `backend/tests/test_export_coco_panoptic.py`：给一组 polygon（含 thing/stuff、`is_instance`）断言生成的 PNG 掩码编码、JSON 段表（id/category/isthing/area/bbox）。
- 前端 e2e `frontend/e2e/create-panoptic-seg.spec.ts`：画 thing 多边形 + 填充 stuff 背景，断言标注生成。
- `pnpm run type-check`、`pnpm run lint`（annotation 模块清零）。

## 相关文件

- `backend/app/api/v1/module_annotation/dataset/model.py`（`AnnotationType`）
- `backend/app/alembic/versions/<new>_panoptic_enum.py`（PG 枚举大写值迁移）
- 后端类别 schema（`is_instance`）
- `backend/app/plugin/module_train/exporter.py`（`_export_coco_panoptic`）
- `backend/tests/test_export_coco_panoptic.py`（新建）
- `frontend/src/annotation/tasks/panopticSegmentation/{index.ts,usePanopticTool.ts,PanopticSegCanvas.vue,PanopticSegPanel.vue}`（新建，或复用 useSegmentTool）
- `frontend/src/annotation/index.ts`、`frontend/src/views/module_annotation/annotation/index.vue`、`frontend/src/views/module_annotation/task/index.vue`
- `frontend/e2e/create-panoptic-seg.spec.ts`（新建）
