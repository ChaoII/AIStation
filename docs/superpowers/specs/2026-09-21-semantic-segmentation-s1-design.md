# 语义分割标注（S1：核心类型）设计

- 日期：2026-09-21
- 状态：设计已获用户批准，待实施
- 范围：S1 —— 语义分割标注核心类型（多边形 + 同类合并渲染 + 背景类填充）
- 后续：S2（画笔涂抹工具）、S3（后端类别掩码导出）为本子项目之外，另行推进。

## 一、背景与目标

标注工作台已支持 detection / rotated_detection / segmentation（实例分割）/ keypoint / ocr / classification 六种任务类型，采用「按任务组织插件」架构（`frontend/src/annotation/tasks/<name>/index.ts` + 在 `annotation/index.ts` 注册），后端 `AnnotationType` 枚举在 `app/api/v1/module_annotation/dataset/model.py`。

本子项目新增 **语义分割（semantic_segmentation）** 标注任务类型，体现类别级（而非实例级）语义：

- 实例分割回答「图里有哪些对象、每个对象在哪」；语义分割回答「每个像素属于哪一类」。
- 因此语义分割的同类区域在语义上**合并为一个类别**，且通常**覆盖整图（含背景类）**，与 Label Studio 的语义分割语义一致。

**目标**：新增语义分割任务类型，提供「多边形勾勒 + 同类按类别合并渲染 + 背景类填充」，让标注结果呈现「逐像素类别、整图覆盖」的语义分割效果，并为 S2（画笔）与 S3（后端掩码导出）打基础。

## 二、数据模型（不改核心联合类型）

- 复用现有 **`Polygon` shape**（`type: "Polygon"`, `points: Point[]`, `class_id`）存语义分割区域。
  - 语义分割与实例分割的区分靠 **`task_type` + 专属插件**，而非 shape 类型，因此**不改** `core/types.ts` 的 `ShapeAnnotation` 判别联合，符合「零改 core」。
- `annotation_record.annotation_data` 仍为 JSONB，存形状列表（同实例分割）。
- **背景类**：任务 `classes` 里的一个**普通类别**（用户可命名为「背景」），语义分割区域通过 `class_id` 指向它。背景类无需额外字段，靠插件约定的背景 `class_id`（见下）。

### 背景类别标识
- 语义分割插件在配置里维护一个「背景类别」选择（从任务 `classes` 中挑选），用 `class_id` 记录。渲染时该 `class_id` 的类别**垫底**。
- 选择持久化在插件运行态（前端 ref），不对 `core` 增加状态。

## 三、前端：新增 `tasks/semanticSegmentation/` 插件

### 3.1 插件定义（`index.ts`）
- `semanticSegmentationPlugin`：
  - `name: "semantic_segmentation"`（与后端 task_type 一致）。
  - `label: "语义分割"`。
  - `renderer: SemanticSegCanvas`。
  - `tools: [{ name: "polygon", label: "语义分割", title: "逐点绘制轮廓，双击闭合" }]`（绘制工具为**多边形**，复用多边形交互）。
  - `create(shape)`：校验 `type === "Polygon"` 且 `points` 为合法归一化点。
  - `tool`：复用 `useSemanticSegTool`（或复用多边形绘制工具），`down/dblclick/reset` 与 polygon 一致。
  - `interaction`：move / vertexMove / vertexInsert / vertexDelete / tagAnchor 与 polygon 一致（复用多边形交互）。

### 3.2 渲染与同类合并（`SemanticSegCanvas.vue`）
- 对每个标注渲染其多边形轮廓与填充（沿用 `polygonPath`、`fill-rule="evenodd"`、半透明填色）。
- **同类合并渲染**：同 `class_id` 的多个多边形用**同一类别颜色**填充（类别级视觉）。渲染顺序保证**背景类别垫底、其它类别在上叠加**。
- **整图覆盖**：由于背景类别垫底 + 前景类别叠加，任一像素最终可归属某一类别（前景类别或背景），呈现「整图覆盖」的语义分割效果，**无需几何补集运算**。
- 顶点编辑（选中态 handles / 中点插入）与 polygon 一致。

### 3.3 填充背景按钮
- 提供「填充背景」操作：在当前图片上生成一个**覆盖整图**的背景类别多边形（四角点，`class_id = 背景类别`），作为垫底层。
  - 该多边形与其它多边形一致存入形状列表；渲染时因其 `class_id` 为背景类别而垫底。
- 交互要求：
  - 按钮带 `v-hasPerm` 校验。
  - 「填充背景」为**覆盖/新建**类操作，须**二次确认**（ElMessageBox.confirm，写明影响范围，如「将把整图填充为背景类，未标注处显示为背景，可撤销」）。
  - 若已存在背景多边形，提示「覆盖」而非重复添加（避免重叠），可撤销。
- 该按钮为插件级 UI，挂在语义分割插件内部或工具栏扩展点（具体挂载位置在实现时对齐壳的工具栏扩展点，若壳无扩展点则用插件自身标注行内控件，避免改 `core`）。

### 3.4 标签层
- 标签位置用多边形最小包围点（`tagAnchor` 返回 `min(x), min(y)`），与 polygon 一致。
- 复用现有 `AnnotationLabelRenderer`，无需改 `core`。

## 四、后端

### 4.1 枚举
- `AnnotationType` 增加 `SEMANTIC_SEGMENTATION = "semantic_segmentation"`（`app/api/v1/module_annotation/dataset/model.py`）。
- 任务创建（`TaskCreateSchema.task_type: AnnotationType`）与统计（`stats/service.py`）天然支持该枚举值。

### 4.2 Alembic 迁移
- `annotation_task.task_type` 为 PG `Enum(AnnotationType)` 列。新增枚举值需迁移：
  - `ALTER TYPE annotationtype ADD VALUE 'semantic_segmentation'`（需在 `transaction` 外的 `ALTER TYPE ... ADD VALUE` 单独执行，PG 不支持在事务块内 ADD VALUE）。
  - 用 Alembic 生成增量迁移（`uv run main.py revision` / `upgrade`）。
- 注意：若 `annotationtype` 枚举名与 Python 枚举名一致，则 `ADD VALUE` 需避免与新列默认值冲突；实现时按 Alembic op 生成并核对。

### 4.3 传输/查询无改动
- 除枚举与迁移外，任务的创建、查询、保存标注均基于 JSONB 与 `task_type` 字符串，无其它后端改动。

## 五、前端任务类型映射

- `frontend/src/views/module_annotation/task/index.vue`：
  - 创建任务下拉（`el-option`）加「语义分割 / semantic_segmentation」。
  - 类型显示映射（`record`/`typeLabel`）加 `semantic_segmentation: "语义分割"`。
- `frontend/web/` 为独立前端副本，不改动。

## 六、明确不在 S1（后续子项目）

- **S2**：画笔涂抹工具（新增第 3 个绘制工具 + 相应数据模型/交互）。
- **S3**：后端类别掩码导出（按类别将多边形/画笔区域栅格化为逐像素 label map / 每类别掩码，含背景反选）。

## 七、测试

- **前端 e2e**：
  - 新增 `create-semantic-seg.spec.ts`：创建 `semantic_segmentation` 任务 → 画多边形 → 填充背景 → 断言标注出现与背景着色。
  - `vue-tsc`（annotation 无新增错误）+ `eslint`（新增文件全通过）。
- **后端**：枚举/迁移为增量，无破坏性改动；`uv run ruff check` 通过。

## 八、风险与注意

- PG `Enum` 列 `ADD VALUE` 不能在事务内执行，且旧值需在新迁移中保留；实现时用 Alembic 增量迁移并验证 `upgrade` 成功。
- 「填充背景」若反复点击会产生重复背景多边形，需在 UI 层防止重复（覆盖式 + 二次确认 + 可撤销）。
- 渲染顺序（背景垫底、前景叠加）需在 `SemanticSegCanvas` 内实现，不能依赖 `core` 调整顺序。
