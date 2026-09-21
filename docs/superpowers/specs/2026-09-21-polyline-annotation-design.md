# 折线（Polyline）标注类型设计

日期：2026-09-21
状态：已确认
范围：通用开放折线点集标注（车道线 / 裂纹中心线 / 路径等任意 1D 几何目标）

## 背景与目标

用户在标注工作台（module_annotation）需要覆盖「主流」的 1D 几何目标标注。业界主流车道线检测（UFLD、PolyLaneNet、LaneATT、CLRNet 等点/曲线回归式）与裂纹中心线等都用**折线点集**作为标注形式。当前工作台缺少「折线」类型（现有最接近的是闭合像素多边形 `Polygon`，语义不同）。

目标：新增**通用开放折线（polyline）点集**标注类型——不闭合、点数 ≥2、带类别，可兼作车道线点集 / 裂纹中心线 / 路径等。

## 决策要点

- **独立类型**：折线是「开放 1D 几何」，与闭合 `Polygon` 语义不同 → 新增**独立 `Polyline` 形状类型**，不复用 `Polygon`。
- **最简范围（YAGNI）**：开放折线点集（≥2 点、不闭合）；逐点点击 + 双击结束 + 节点移动/插入/删除 + 带类别。**不做**平滑曲线、闭合切换、分叉。
- **通用导出**：先产出通用归一化点集 + `class_id`；车道点集专用格式（TuSimple/CULane）本期不做，后续扩展。

## 1. 形状与数据类型

### 前端 `frontend/src/annotation/core/types.ts`
- `TaskShapeType` 增加 `"Polyline"`。
- 新增接口：

```ts
export interface PolylineShape {
  id: string;
  type: "Polyline";
  class_id: number;
  points: Point[];
}
```

- `ShapeAnnotation` 判别联合增加 `PolylineShape`。

### 后端 `backend/app/api/v1/module_annotation/dataset/model.py`
- `AnnotationType` 增加 `POLYLINE = "polyline"`。

### 数据库迁移
- 新增 alembic 迁移，`ALTER TYPE annotationtype ADD VALUE 'POLYLINE'`（**大写**，与 SQLAlchemy 枚举按成员名存储一致）。
- 需 `autocommit_block` + `is_postgres` 守卫（沿用语义分割枚举迁移模式；小写为 bug，勿复用）。
- 若 dev 库此前已被前序迁移污染需先清理小写残留。

## 2. 前端插件 `frontend/src/annotation/tasks/polyline/`

### `index.ts`（`polylinePlugin`）
- `name: "polyline"`，`label: "折线"`，`color` 与同模块保持一致。
- `tools: [{ name: "polyline", label: "折线", title: "逐点绘制折线，双击结束" }]`。
- `create(shape)`：`shape.type === "Polyline"`；`points` 为数组且 `length >= 2`；每点归一化（`0 <= x,y <= 1`）。

### `usePolylineTool.ts`
- `points: Ref<Point[]>`（归一化）。
- `addPoint(p)`：追加点。
- `finish()`：若 `points.length >= 2` 返回开放折线标注对象，否则返回 `null`（并提示/丢弃）。
- `reset()`：清空。

### `PolylineCanvas.vue`
- 渲染**开放折线**：按 `points` 顺序连线（`<polyline>`，**不闭合**）。
- 每点绘制圆圈节点手柄；类别颜色取 `color(a)`。
- 选中态高亮，节点可拖拽。

### `PolylinePreview.vue`
- 绘制进行中的预览线 + 当前点。

### `interaction`（在 `index.ts`）
- `move(ctx)`：整体平移所有点（clamp 0–1）。
- `vertexMove(ctx)`：移动单个节点（clamp 0–1）。
- `vertexInsert(ann, handle)`：在 `idx` 与 `idx+1` **中间插入**点（**非循环**，即 `idx+1` 不超过 `points.length` 边界；不闭环）。
- `vertexDelete(ann, handle)`：删除节点，**保底至少 2 点**（`points.length > 2` 时允许删除）。
- `tagAnchor(ann)`：返回 `{ x: min(points.x), y: min(points.y) }`。

## 3. 注册

- `frontend/src/annotation/index.ts`：导出 `polylinePlugin`。
- `frontend/src/views/module_annotation/annotation/index.vue`：`plugins` 数组接入 `polylinePlugin`。
- `frontend/src/views/module_annotation/task/index.vue`：任务类型下拉、label、tag 映射增加「折线」。

## 4. 导出

- 折线标注随 `annotation_data` JSONB 写入：`{ id, type:"Polyline", class_id, points:[{x,y}...] }`（归一化点集）。
- AnyLabeling 导出映射 `shape_type: "line"`（该导入器已支持 `line`）。
- 车道点集专用格式（TuSimple/CULane）不在本期范围。

## 5. 错误处理

- 双击结束需 `points.length >= 2`，否则丢弃并弹提示。
- 节点删除保底至少 2 点。

## 6. 测试

- e2e：`frontend/e2e/create-polyline.spec.ts`（画开放折线 + 命名/数量断言）。
- `pnpm run type-check`、`pnpm run lint`（annotation 模块清零）。

## 相关文件

- `frontend/src/annotation/core/types.ts`（`PolylineShape`、联合、`TaskShapeType`）
- `frontend/src/annotation/tasks/polyline/{index.ts,usePolylineTool.ts,PolylineCanvas.vue,PolylinePreview.vue}`（新建）
- `frontend/src/annotation/index.ts`、`frontend/src/views/module_annotation/annotation/index.vue`、`frontend/src/views/module_annotation/task/index.vue`
- `backend/app/api/v1/module_annotation/dataset/model.py`（`AnnotationType`）
- `backend/app/alembic/versions/<new>_polyline_enum.py`（PG 枚举大写值迁移）
