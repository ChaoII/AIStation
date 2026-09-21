# 3D 目标检测（Cuboid）标注类型设计

日期：2026-09-22
状态：已确认
范围：3D 目标检测（cuboid / 3D 框）标注——在 2D 图像上以「中心 + 宽/高/深 + yaw」参数化的透视立方体表示目标，支持导出。

## 背景与目标

用户在标注工作台（module_annotation）需要覆盖「主流」的 3D 目标检测标注。业界 3D 检测（KITTI、nuScenes 等）在单目图像上用**3D 框（cuboid）**描述目标的三维位置与朝向。当前工作台缺少 cuboid 类型（最接近的是 2D 旋转框 `rotated_detection`，语义不同——无深度/高度语义）。

目标：新增 **3D 目标检测（cuboid）** 标注类型——用户在 2D 画布上拖拽一个透视立方体（底部旋转矩形 + 高度投影线），内部表示为「中心 `cx/cy` + 宽 `w` + 高 `h` + 深 `depth` + 朝向 `yaw`」参数化，导出为 AnyLabeling 可读的多边形 + 3D 参数。

## 决策要点

- **数据建模**：`中心 (cx,cy) + 宽 w + 高 h + 深 depth + 朝向 yaw` 3D 参数化（选型：中心+宽高深+yaw，弃用「2D 8 顶点投影」与「底矩形+高度透视」）。
- **导出**：复用 `x-anylabeling`（AnyLabeling 多边形 + 3D 参数），不新增导出框架。
- **前端交互**：拖拽透视立方体——先拖底部旋转矩形（`cx/cy/w/h/yaw`），再向上拖「高度投影线」确定 `top_cy`（顶面高度投影）；`depth` 由侧边面板填写。
- **参数映射**：`w/h/yaw` 从底部矩形拖拽实时派生（可信）；`depth` 面板填；`top_cy` 表达高度投影线。
- **零改 core 逻辑**：插件自带完整 `interaction`（move/resize/rotate/tagAnchor），不触发 `AnnotationWorkbench.vue` 默认分支。仅允许在 `core/types.ts` 加 `CuboidShape` 类型与 `"Cuboid"` 形状枚举（纯类型声明，零逻辑）。
- **最简范围（YAGNI）**：仅单一 cuboid 形状（无并联多边形、无遮挡分层、无截断/遮挡字段）；不做 KITTI/nuScenes 专用格式（本期导出 AnyLabeling 多边形 + 3D 参数）。

## 1. 形状与数据类型

### 前端 `frontend/src/annotation/core/types.ts`（仅类型声明，零逻辑）
- `TaskShapeType` 增加 `"Cuboid"`。
- 新增接口：

```ts
export interface CuboidShape {
  id: string;
  type: "Cuboid";
  class_id: number;
  cx: number;    // 底部矩形中心 x（归一化 [0,1]）
  cy: number;    // 底部矩形中心 y（归一化 [0,1]）
  w: number;     // 底部矩形宽（归一化，按图像宽）
  h: number;     // 底部矩形高（归一化，按图像高）
  yaw: number;   // 底部矩形朝向角（弧度，绕中心，参照 rotatedBox）
  depth: number; // 图像深度（归一化 [0,1]，由侧边面板填写）
  top_cy: number; // 高度投影线在画布上的垂直偏移（归一化，用于渲染顶面，
                  // 顶部矩形 = 底部矩形整体沿 y 方向平移 -top_cy 后的投影）
}
```

- `ShapeAnnotation` 判别联合增加 `CuboidShape`。

**约定**：底部矩形用 `cx/cy/w/h/yaw`（复刻 rotatedBox 参数化）；顶面 = 底部矩形沿 y 平移 `-top_cy` 的平行四边形；`depth` 不参与画布拖拽，仅面板填写；所有参数归一化到 [0,1]，renderer 乘 `cw/ch`。

### 后端 `backend/app/api/v1/module_annotation/dataset/model.py`
- `AnnotationType` 增加 `CUBOID = "cuboid"`。

### 数据库迁移
- 新增 alembic 迁移 `ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'CUBOID'`（**大写**，与 SQLAlchemy 枚举按成员名存储一致）。
- 需 `autocommit_block` + `is_postgres` 守卫（沿用 panoptic 枚举迁移模式；`down_revision = "d4e5f6a7b8c9"`，当前 head）。
- 迁移 revision 命名遵循现有格式（如 `cuboid_enum`）。

## 2. 前端插件 `frontend/src/annotation/tasks/cuboid/`

参照 `rotatedBox/` 结构（中心定位 + 角度 + 拖拽缩放/旋转）。

### `index.ts`（`cuboidPlugin`）
- `name: "cuboid"`（**必须等于后端 task_type 枚举值**，`AnnotationWorkbench.vue:481` 按 `plugin.name` 匹配），`label: "3D 目标检测"`，`color` 与同模块保持一致。
- `tools: [{ name: "cuboid", label: "3D 目标检测", title: "拖拽底部旋转矩形 + 向上拖高度投影线" }]`。
- `create(shape)`：`shape.type === "Cuboid"`；`w/h > 0`；`cx/cy` 在 [0,1]；`depth`、`top_cy` 均在 [0,1]；yaw 数值合法。
- `interaction`：完整实现 `move`（平移 cx/cy，clamp）、`resize`（旋转坐标系下改 w/h）、`rotate`（用 center/start/client atan2 增 yaw）、`tagAnchor`（底部矩形左上角，用 w/h/yaw 旋转变换）。**不依赖 workbench 默认分支**。

### `useCuboidTool.ts`
- 复用/参照 `useRotatedTool` 的 3 点画旋转矩形逻辑（`cuboidFromEdgeAndPoint`）。
- 新增「高度投影线」状态：底部矩形完成后，向上拖一条线确定 `top_cy`（顶面高度投影）。

### `CuboidCanvas.vue`（renderer）
- 绘制透视立方体：
  - 底部旋转矩形（`cx/cy/w/h/yaw`）。
  - 顶面 = 底部矩形沿 y 平移 `-top_cy` 的平行四边形。
  - 4 条竖直棱线连接底/顶对应角。
  - 类别颜色取 `color(a)`。
  - 选中态显示 8 个角点 handle（底 4 + 顶 4）。
- 标签锚点由 `tagAnchor` 返回底部矩形左上角。

### `CuboidPanel.vue`（panel）
- 侧边属性面板：编辑 `depth`（深度输入），并显示当前 `w/h/yaw/depth/top_cy` 只读值。
- 提供「应用深度」等操作（填写后写入当前选中标注的 `depth`）。

### 注册
- `frontend/src/annotation/index.ts`：导出 `cuboidPlugin`。
- `frontend/src/views/module_annotation/annotation/index.vue`：`plugins` 数组接入 `cuboidPlugin`。
- `frontend/src/views/module_annotation/task/index.vue`：任务类型映射四处（el-option、搜索 options、`annotationTypeLabel`、`annotationTypeTag`）加「3D 目标检测 / cuboid」。

## 3. 数据持久化

- `CuboidShape` 随 `annotation_data` JSONB 写入：`{ id, type:"Cuboid", class_id, cx, cy, w, h, yaw, depth, top_cy }`（归一化参数）。
- `saveAnnotations` 直接把整份 `annotation_data`（`any`）交给后端，无 shape 字段限制，前端无需改 API。

## 4. 导出

- 复用 `x-anylabeling` 框架（`frontend/src/views/module_annotation/dataset/index.vue` 的 `FORMAT_TASK_MAP` 中 `"x-anylabeling"` 列表加 `"cuboid"`；`exportFormatOptions` 不改，因复用 x-anylabeling）。
- `backend/app/plugin/module_train/exporter.py` 的 `xany_shapes` 加 `cuboid` shape_type 分支：
  - `shape_type: "cuboid"`。
  - `points`：底部矩形 4 个投影顶点（屏幕坐标，由 `cx/cy/w/h/yaw` + `top_cy` 派生：底 4 角 + 顶 4 角，共 8 点或仅存底部 4 点 + 参数）。
  - 附加 3D 参数字段（`cx/cy/w/h/yaw/depth/top_cy`，含数据约定），便于回读。
- 若 AnyLabeling 导入器（`x_anylabeling_importer.py`）需回导 cuboid，则在 `_shape_to_annotation` 加 `cuboid` 分支（本期可先支持导出，回导按需）。

## 5. 错误处理

- 底部矩形需 `w/h > 0` 且范围在 [0,1]（`create` 校验，不合法丢弃并提示）。
- 高度投影线可选（`top_cy` 允许 0，表示无顶面偏移）。
- `depth` 为 [0,1]，面板输入校验。

## 6. 测试

- e2e：`frontend/e2e/create-cuboid.spec.ts`（拖底部旋转矩形 + 向上拖高度投影线 + 面板填 depth + 保存 + 命名/数量断言）。
- 后端：`test_export_xanylabeling.py` 增加 cuboid 用例（或新建 `test_export_cuboid.py`），验证 xany_shapes 的 cuboid 输出（points/params）；含回导测试（按需）。
- `pnpm run type-check`、`pnpm run lint`（annotation 模块清零）。
- 后端迁移 `uv run main.py upgrade --env=dev`，`alembic heads` 为新 revision。

## 相关文件

- `frontend/src/annotation/core/types.ts`（`CuboidShape`、联合、`TaskShapeType`）
- `frontend/src/annotation/tasks/cuboid/{index.ts,useCuboidTool.ts,CuboidCanvas.vue,CuboidPreview.vue,CuboidPanel.vue}`（新建）
- `frontend/src/annotation/index.ts`、`frontend/src/views/module_annotation/annotation/index.vue`、`frontend/src/views/module_annotation/task/index.vue`、`frontend/src/views/module_annotation/dataset/index.vue`
- `backend/app/api/v1/module_annotation/dataset/model.py`（`AnnotationType`）
- `backend/app/alembic/versions/<new>_cuboid_enum.py`（PG 枚举大写值迁移）
- `backend/app/plugin/module_train/exporter.py`（`xany_shapes` cuboid 分支）
- `backend/tests/test_export_cuboid.py`（新建，或并入 `test_export_xanylabeling.py`）
- `frontend/e2e/create-cuboid.spec.ts`（新建）
