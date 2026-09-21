# 3D 目标检测（Cuboid）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 3D 目标检测（cuboid）标注类型：后端 `AnnotationType.CUBOID` + PG 枚举迁移；前端 `Cuboid` 插件（中心+宽/高/深+yaw 参数化透视立方体交互）；AnyLabeling 导出（多边形+3D 参数）；e2e 与后端导出测试。

**Architecture:** 复用 rotatedBox 的旋转角点几何与交互（中心定位 + 角度 + 拖拽缩放/旋转），扩展 `depth`（面板填）与 `top_cy`（高度投影线）渲染透视立方体。插件自带完整 `interaction`，零改 `AnnotationWorkbench.vue` 逻辑（仅 `core/types.ts` 加类型声明）。导出走现有 `x-anylabeling` 框架，在 `xany_shapes` 加 `cuboid` shape_type。

**Tech Stack:** Vue 3 + Element Plus + TypeScript（前端），FastAPI + SQLAlchemy + Alembic + Pillow（后端），Playwright（e2e）。

## Global Constraints

- 零改 `frontend/src/annotation/core/` 逻辑。仅允许在 `core/types.ts` 加 `CuboidShape` 接口与 `"Cuboid"` 形状枚举（纯类型声明，零逻辑），**绝不动** `AnnotationWorkbench.vue` 逻辑分支。
- `CuboidShape` 字段：`{ id, type:"Cuboid", class_id, cx, cy, w, h, yaw, depth, top_cy }`；所有参数归一化 [0,1]（renderer 乘 `cw/ch`）；`depth`/`top_cy` 均为 [0,1]。
- `plugin.name === "cuboid"`（必须等于后端 `task_type` 枚举值，`AnnotationWorkbench.vue:481` 按 `plugin.name` 匹配）。
- 底部矩形用 `cx/cy/w/h/yaw`（复刻 rotatedBox 参数化）；顶面 = 底部矩形沿 y 平移 `-top_cy` 的平行四边形；4 条竖直棱线连接底/顶对应角。
- SQLAlchemy `Enum(AnnotationType)` 按成员名**大写**存储；PG 迁移 `ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'CUBOID'`（大写），`autocommit_block` + `is_postgres` 守卫；`down_revision="d4e5f6a7b8c9"`（当前 head）。
- 导出复用 `x-anylabeling`，`xany_shapes` 加 `cuboid` shape_type（底部旋转矩形 4 顶点像素坐标 + 3D 参数）。
- 中文注释；提交信息 `feat|test|fix(annotation): 中文描述`；前端用 Element Plus 组件与 `--el-*` 变量，不用内联 font-size/自造主题化外壳；单根 Vue 组件。
- 删除/覆盖类操作二次确认。
- 前端 dev `:5180`、后端 `:8001`；e2e 需二者运行。

---

### Task 1: 后端 `AnnotationType.CUBOID` + PG 枚举迁移

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/model.py:11-22`
- Create: `backend/app/alembic/versions/<new>_cuboid_enum.py`

**Interfaces:**
- Consumes: `is_postgres`（`app.alembic.dialect_compat`）。
- Produces: `AnnotationType.CUBOID`（值 `"cuboid"`）；迁移 revision 位于 `d4e5f6a7b8c9` 之后。

- [ ] **Step 1: 修改 `model.py`**

在 `AnnotationType` 中 `PANOPTIC_SEGMENTATION = "panoptic_segmentation"` 之后加：

```python
    CUBOID = "cuboid"
```

- [ ] **Step 2: 创建迁移文件**

先读 `backend/app/alembic/versions/d4e5f6a7b8c9_panoptic_enum.py` 与 `backend/app/alembic/dialect_compat.py` 确认 `is_postgres` 导入路径，然后创建 `backend/app/alembic/versions/<new>_cuboid_enum.py`：

```python
"""cuboid enum

Revision ID: <new_rev>
Revises: d4e5f6a7b8c9
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import is_postgres

revision: str = "<new_rev>"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """给 annotationtype 枚举增加 CUBOID 值（仅 PostgreSQL）。

    SQLAlchemy 以枚举成员 NAME（大写）存储，而非 .value（小写），
    因此必须添加大写值 'CUBOID'。
    """
    if is_postgres(op.get_bind()):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS 'CUBOID'"
            )


def downgrade() -> None:
    """PG 不支持移除枚举值，downgrade 为空操作（保留该值）。"""
    pass
```

`<new_rev>` 用一个新的 12 位十六进制 revision（如 `e5f6a7b8c9d0`）。

- [ ] **Step 3: 运行迁移并校验**

Run (在 `backend/`): `uv run main.py upgrade --env=dev`
Expected: 无报错；`uv run alembic heads` 输出 `<new_rev> (head)`。

- [ ] **Step 4: 提交**

```bash
git add backend/app/api/v1/module_annotation/dataset/model.py backend/app/alembic/versions/<new>_cuboid_enum.py
git commit -m "feat(annotation): 后端新增3D目标检测(cuboid)类型与枚举迁移"
```

---

### Task 2: 后端 AnyLabeling 导出支持 cuboid + 测试

**Files:**
- Modify: `backend/app/plugin/module_train/exporter.py`（`xany_shapes` 加 cuboid 分支）
- Test: `backend/tests/test_export_cuboid.py`（新建）

**Interfaces:**
- Consumes: `rotated_box_to_obb_corners`（exporter.py:196）、`_px`（exporter.py:241）、`xany_shapes`（exporter.py:245）。
- Produces: `xany_shapes` 对 `type=="Cuboid"` 输出 `{label, points, shape_type:"cuboid", group_id:None, flags:{}, attributes:{cx,cy,w,h,yaw,depth,top_cy}}`。

- [ ] **Step 1: 先写失败测试 `backend/tests/test_export_cuboid.py`**

```python
"""AnyLabeling 导出 cuboid 形状单测：底部旋转矩形顶点 + 3D 参数附加字段。"""
from app.plugin.module_train.exporter import xany_shapes


def test_xany_shapes_cuboid():
    anns = [{
        "type": "Cuboid",
        "class_id": 1,
        "cx": 0.5, "cy": 0.5, "w": 0.4, "h": 0.2,
        "yaw": 0.0, "depth": 0.5, "top_cy": 0.3,
    }]
    shapes = xany_shapes(anns, 100, 100, {1: "car"})
    assert len(shapes) == 1
    s = shapes[0]
    assert s["shape_type"] == "cuboid"
    assert s["label"] == "car"
    # 底部旋转矩形 4 顶点（像素坐标），yaw=0 时按 w/h 展开
    pts = s["points"]
    assert len(pts) == 4
    assert pts[0] == [30.0, 40.0]
    assert pts[2] == [70.0, 60.0]
    # 3D 参数附加字段
    attrs = s["attributes"]
    assert attrs["cx"] == 0.5
    assert attrs["depth"] == 0.5
    assert attrs["top_cy"] == 0.3
```

- [ ] **Step 2: 运行测试确认失败**

Run (在 `backend/`): `uv run pytest tests/test_export_cuboid.py -q`
Expected: FAIL（`shape_type` 非 `"cuboid"`，`shape_type` 判断为 `polygon` 兜底或无该分支）。

- [ ] **Step 3: 在 `xany_shapes` 加 cuboid 分支**

在 `xany_shapes` 中 `elif t in ("RotatedBox", "rotated_box"):` 分支之后、`elif t in ("Polygon", "polygon"):` 之前加：

```python
        elif t in ("Cuboid", "cuboid"):
            # 底部旋转矩形 4 顶点（像素坐标），顶面仅用参数表达（不额外产出面）
            px = rotated_box_to_obb_corners(ann["cx"] * img_w, ann["cy"] * img_h,
                                            ann["w"] * img_w, ann["h"] * img_h,
                                            float(ann.get("yaw", 0) or 0),
                                            reorder=False)
            pts = [[px[i], px[i + 1]] for i in range(0, 8, 2)]
            shapes.append({
                **base,
                "points": pts,
                "shape_type": "cuboid",
                "attributes": {
                    "cx": ann.get("cx", 0),
                    "cy": ann.get("cy", 0),
                    "w": ann.get("w", 0),
                    "h": ann.get("h", 0),
                    "yaw": ann.get("yaw", 0),
                    "depth": ann.get("depth", 0),
                    "top_cy": ann.get("top_cy", 0),
                },
            })
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_export_cuboid.py -q`
Expected: PASS（1 用例）。

- [ ] **Step 5: 运行既有导出测试确认无回归**

Run: `uv run pytest tests/test_export_xanylabeling.py -q`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/exporter.py backend/tests/test_export_cuboid.py
git commit -m "feat(annotation): AnyLabeling导出支持3D目标检测(cuboid)形状"
```

---

### Task 3: 前端 `core/types.ts` 加 `CuboidShape` 类型声明

**Files:**
- Modify: `frontend/src/annotation/core/types.ts`

**Interfaces:**
- Consumes: `TaskShapeType`（types.ts:3-6）、`ShapeAnnotation` 判别联合（types.ts:63-73）、`Point`。
- Produces: `CuboidShape` 接口 + `"Cuboid"` 加入 `TaskShapeType` 与 `ShapeAnnotation` 联合。

- [ ] **Step 1: `TaskShapeType` 加 `"Cuboid"`**

在 `TaskShapeType`（types.ts:3-6）中 `| "Classification"` 之后加：

```ts
  | "Cuboid"
```

- [ ] **Step 2: 新增 `CuboidShape` 接口**

在 `ShapeAnnotation` 相关的现有 shape 接口定义之后加：

```ts
export interface CuboidShape {
  id: string;
  type: "Cuboid";
  class_id: number;
  /** 底部矩形中心 x（归一化 [0,1]） */
  cx: number;
  /** 底部矩形中心 y（归一化 [0,1]） */
  cy: number;
  /** 底部矩形宽（归一化，按图像宽） */
  w: number;
  /** 底部矩形高（归一化，按图像高） */
  h: number;
  /** 底部矩形朝向角（弧度，绕中心，参照 rotatedBox） */
  yaw: number;
  /** 图像深度（归一化 [0,1]，由侧边面板填写） */
  depth: number;
  /** 高度投影线在画布上的垂直偏移（归一化，顶面=底部矩形沿 y 平移 -top_cy 的投影） */
  top_cy: number;
}
```

- [ ] **Step 3: 将 `CuboidShape` 并入 `ShapeAnnotation` 联合**

在 `ShapeAnnotation` 判别联合中加 `| CuboidShape`。

- [ ] **Step 4: type-check**

Run (在 `frontend/`): `pnpm run type-check`
Expected: 无本模块新增报错。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/types.ts
git commit -m "feat(annotation): 新增Cuboid形状类型声明"
```

---

### Task 4: 前端 cuboid 插件 `tasks/cuboid/` + 注册

**Files:**
- Create: `frontend/src/annotation/tasks/cuboid/useCuboidTool.ts`
- Create: `frontend/src/annotation/tasks/cuboid/CuboidCanvas.vue`
- Create: `frontend/src/annotation/tasks/cuboid/CuboidPreview.vue`
- Create: `frontend/src/annotation/tasks/cuboid/CuboidPanel.vue`
- Create: `frontend/src/annotation/tasks/cuboid/index.ts`
- Modify: `frontend/src/annotation/index.ts`（导出）
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`（plugins 数组）
- Modify: `frontend/src/views/module_annotation/task/index.vue`（el-option / 搜索 options / label / tag）
- Modify: `frontend/src/views/module_annotation/dataset/index.vue`（FORMAT_TASK_MAP / taskTypeLabel / taskTagType）

**Interfaces:**
- Consumes: `AnnotationTaskPlugin`/`Annotation`/`DragContext`/`Point`（core/types.ts）；复用 rotatedBox 的几何（`rotatedBoxFromEdgeAndPoint`、handlePos 角点、resize/rotate/tagAnchor 交互逻辑）。
- Produces: `cuboidPlugin`（`name:"cuboid"`、`label:"3D 目标检测"`、`color`、renderer/tools/panel/create/tool/interaction）。

**Step 1: `useCuboidTool.ts`**（复用 rotatedBox 三步画旋转框，扩展高度投影线）

```ts
import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";

// 三步旋转底框：p1(边起点) → p2(边终点) → p3(垂直方向点)
export function cuboidFromEdgeAndPoint(p1: Point, p2: Point, p3: Point) {
  const vx = p2.x - p1.x;
  const vy = p2.y - p1.y;
  const width = Math.hypot(vx, vy);
  if (width < 1e-6) return null;
  const mx = (p1.x + p2.x) / 2;
  const my = (p1.y + p2.y) / 2;
  const tx = vx / width;
  const ty = vy / width;
  const t = (p3.x - p1.x) * tx + (p3.y - p1.y) * ty;
  const footX = p1.x + t * tx;
  const footY = p1.y + t * ty;
  const offx = p3.x - footX;
  const offy = p3.y - footY;
  const height = Math.hypot(offx, offy);
  if (height < 1e-6) return null;
  const nx = offx / height;
  const ny = offy / height;
  return {
    cx: mx + (height / 2) * nx,
    cy: my + (height / 2) * ny,
    width,
    height,
    angle: Math.atan2(vy, vx),
  };
}

export function useCuboidTool() {
  const step = ref(0); // 0=idle,1=置p1,2=拖边,3=置p3
  const pt1 = ref<Point | null>(null);
  const pt2 = ref<Point | null>(null);

  function onStep(p: Point): Annotation | null {
    if (step.value === 0) {
      pt1.value = p;
      step.value = 1;
      return null;
    }
    if (step.value === 1) {
      pt2.value = p;
      step.value = 2;
      return null;
    }
    if (step.value === 2) {
      const geom = cuboidFromEdgeAndPoint(pt1.value!, pt2.value!, p);
      step.value = 0;
      pt1.value = null;
      pt2.value = null;
      if (!geom) return null;
      return {
        id: crypto.randomUUID(),
        type: "Cuboid",
        class_id: 0,
        cx: geom.cx,
        cy: geom.cy,
        w: geom.width,
        h: geom.height,
        yaw: geom.angle,
        depth: 0.5,
        top_cy: 0,
      };
    }
    return null;
  }

  return { step, pt1, pt2, onStep };
}
```

**Step 2: `CuboidCanvas.vue`**（渲染透视立方体：底部旋转矩形 + 顶面平行四边形 + 4 棱线）

```vue
<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <!-- 顶面平行四边形（底部矩形沿 y 平移 -top_cy） -->
    <polygon
      :points="topPoints(ann)"
      fill="none"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <!-- 4 条竖直棱线 -->
    <line
      v-for="i in 4"
      :key="'edge-' + i"
      :x1="corner(ann, i-1).x"
      :y1="corner(ann, i-1).y"
      :x2="topCorner(ann, i-1).x"
      :y2="topCorner(ann, i-1).y"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
    />
    <!-- 底部旋转矩形 -->
    <polygon
      :points="bottomPoints(ann)"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
      <circle
        v-for="h in handles"
        :key="'rot-' + h"
        :cx="handlePos(ann, h).x"
        :cy="handlePos(ann, h).y"
        r="4"
        fill="#fff"
        stroke="#1a1a1a"
        stroke-width="1.5"
        :data-handle="h"
        class="handle"
        :style="peStyle"
        vector-effect="non-scaling-stroke"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, h)"
      />
      <circle
        :cx="rotateHandlePos(ann).x"
        :cy="rotateHandlePos(ann).y"
        r="3"
        fill="#fff"
        :stroke="color(ann)"
        stroke-width="1.5"
        class="handle"
        :style="peStyle"
        :data-handle="'rotate'"
        @mousedown.stop.prevent="$emit('rotate-down', $event, ann)"
      />
    </template>
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Annotation } from "../../core/types";

const props = defineProps<{
  annotations: Annotation[];
  cw: number;
  ch: number;
  selectedId: string;
  color: (a: Annotation) => string;
  clsName: (a: Annotation) => string;
  fontSize: number;
  tagH: number;
  stroke?: number;
  selStroke?: number;
  pointerNone?: boolean;
}>();

defineEmits<{
  (e: "ann-down", ev: MouseEvent, ann: Annotation): void;
  (e: "handle-down", ev: MouseEvent, ann: Annotation, handle: string): void;
  (e: "rotate-down", ev: MouseEvent, ann: Annotation): void;
}>();

const handles = ["tl", "tr", "bl", "br"];
const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

function corner(a: Annotation, idx: number): { x: number; y: number } {
  const hw = (a.w * props.cw) / 2;
  const hh = (a.h * props.ch) / 2;
  const cos = Math.cos(a.yaw);
  const sin = Math.sin(a.yaw);
  const map: Record<number, [number, number]> = {
    0: [-hw, -hh],
    1: [hw, -hh],
    2: [hw, hh],
    3: [-hw, hh],
  };
  const [lx, ly] = map[idx] || [0, 0];
  return { x: a.cx * props.cw + lx * cos - ly * sin, y: a.cy * props.ch + lx * sin + ly * cos };
}

function topCorner(a: Annotation, idx: number): { x: number; y: number } {
  const c = corner(a, idx);
  return { x: c.x, y: c.y - a.top_cy * props.ch };
}

function pts(ann: Annotation, fn: (a: Annotation, i: number) => { x: number; y: number }): string {
  return [0, 1, 2, 3].map((i) => {
    const p = fn(ann, i);
    return `${p.x},${p.y}`;
  }).join(" ");
}

function bottomPoints(ann: Annotation): string {
  return pts(ann, (a, i) => corner(a, i));
}

function topPoints(ann: Annotation): string {
  return pts(ann, (a, i) => topCorner(a, i));
}

function handlePos(a: Annotation, key: string) {
  const idx = { tl: 0, tr: 1, br: 2, bl: 3 }[key as string] ?? 0;
  return corner(a, idx);
}

function rotateHandlePos(a: Annotation) {
  const tc = corner(a, 0);
  const cx = a.cx * props.cw;
  const cy = a.cy * props.ch;
  const dx = tc.x - cx;
  const dy = tc.y - cy;
  const len = Math.hypot(dx, dy) || 1;
  const off = 25;
  return { x: tc.x + (dx / len) * off, y: tc.y + (dy / len) * off };
}
</script>
```

**Step 3: `CuboidPreview.vue`**

```vue
<template>
  <g>
    <polyline
      v-if="preview && preview.pt1 && preview.pt2"
      :points="edgePts"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
    />
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  preview: any;
  cw: number;
  ch: number;
  pointerNone?: boolean;
}>();

const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
const edgePts = computed(() => {
  if (!props.preview?.pt1 || !props.preview?.pt2) return "";
  return `${props.preview.pt1.x * props.cw},${props.preview.pt1.y * props.ch} ${props.preview.pt2.x * props.cw},${props.preview.pt2.y * props.ch}`;
});
</script>
```

**Step 4: `CuboidPanel.vue`**（侧边面板：编辑 depth）

```vue
<template>
  <div class="cuboid-panel">
    <el-form label-width="72px" size="small">
      <el-form-item label="深度">
        <el-input-number
          v-model="depthVal"
          :min="0"
          :max="1"
          :step="0.05"
          :controls="false"
          @change="applyDepth"
        />
      </el-form-item>
      <el-form-item label="朝向">
        <span style="color: var(--el-text-color-secondary)">{{ yawText }}</span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import type { PluginPanelContext, Annotation } from "../../core/types";

const props = defineProps<{ ctx: PluginPanelContext }>();
const depthVal = ref<number>(0.5);

function selectedCuboid(): Annotation | null {
  const sel = props.ctx.selectedClassId;
  const cands = (props.ctx.annotations ?? []).filter((a) => a.type === "Cuboid");
  if (cands.length === 0) return null;
  // 取最后选中的 cuboid（简化：当前选中类别下最后一个）
  const cls = cands.filter((a) => a.class_id === sel);
  return cls[cls.length - 1] ?? cands[cands.length - 1];
}

function applyDepth() {
  const cub = selectedCuboid();
  if (!cub) return;
  cub.depth = depthVal.value;
  (cub as any).__depthDirty = true;
}

const yawText = ref("");

watch(
  () => props.ctx.annotations,
  () => {
    const cub = selectedCuboid();
    if (cub) {
      depthVal.value = cub.depth ?? 0.5;
      yawText.value = `${(((cub.yaw ?? 0) * 180) / Math.PI).toFixed(1)}°`;
    }
  },
  { deep: true }
);

onMounted(() => {
  const cub = selectedCuboid();
  if (cub) {
    depthVal.value = cub.depth ?? 0.5;
    yawText.value = `${(((cub.yaw ?? 0) * 180) / Math.PI).toFixed(1)}°`;
  }
});
</script>
```

**Step 5: `index.ts`（plugin）**

```ts
import { ref } from "vue";
import type { AnnotationTaskPlugin, Annotation, DragContext, Point } from "../../core/types";
import CuboidCanvas from "./CuboidCanvas.vue";
import CuboidPreview from "./CuboidPreview.vue";
import CuboidPanel from "./CuboidPanel.vue";
import { useCuboidTool, cuboidFromEdgeAndPoint } from "./useCuboidTool";

export const cuboidPlugin: AnnotationTaskPlugin = {
  name: "cuboid",
  label: "3D 目标检测",
  color: "danger",
  renderer: CuboidCanvas,
  tools: [{ name: "cuboid", label: "3D 目标检测", title: "三步拖底部旋转矩形，选中后在面板填深度" }],
  panel: CuboidPanel,
  create(shape: Annotation): boolean {
    if (shape.type !== "Cuboid") return false;
    if (shape.w <= 0 || shape.h <= 0) return false;
    if (shape.cx < 0 || shape.cy < 0 || shape.cx > 1 || shape.cy > 1) return false;
    const half = Math.hypot(shape.w, shape.h) / 2;
    if (shape.cx - half < 0 || shape.cx + half > 1) return false;
    if (shape.cy - half < 0 || shape.cy + half > 1) return false;
    if (shape.depth < 0 || shape.depth > 1) return false;
    if (shape.top_cy < 0 || shape.top_cy > 1) return false;
    return true;
  },
  tool: (() => {
    const cub = useCuboidTool();
    const last = ref<Point | null>(null);
    const preview = ref<any>(null);
    return {
      name: "cuboid",
      preview: CuboidPreview,
      state: { step: cub.step, pt1: cub.pt1, pt2: cub.pt2, last, preview },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        last.value = p;
        const created = cub.onStep(p);
        if (created) preview.value = null;
        return created;
      },
      move(ctx) {
        const p = ctx.point;
        if (!p) return;
        last.value = p;
        if (cub.pt1.value && cub.pt2.value) {
          const g = cuboidFromEdgeAndPoint(cub.pt1.value, cub.pt2.value, p);
          if (g) preview.value = { ...g, pt1: cub.pt1.value, pt2: cub.pt2.value };
        }
      },
      reset() {
        cub.step.value = 0;
        cub.pt1.value = null;
        cub.pt2.value = null;
        last.value = null;
        preview.value = null;
      },
    };
  })(),
  interaction: {
    move(ctx: DragContext): void {
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      ctx.ann.cx = nc(ctx.orig.cx + ctx.dx);
      ctx.ann.cy = nc(ctx.orig.cy + ctx.dy);
      ctx.trigger();
    },
    resize(ctx: DragContext): void {
      const { ann, orig, handle, point, cw, ch } = ctx;
      if (!point) return;
      const aspect = ch / cw;
      const o = orig;
      const cos = Math.cos(o.yaw);
      const sin = Math.sin(o.yaw);
      const fx = handle.includes("l") ? 1 : handle.includes("r") ? -1 : 1;
      const fy = handle.includes("t") ? 1 : handle.includes("b") ? -1 : 1;
      const fix_x = o.cx + ((fx * o.w) / 2) * cos - ((fy * o.h) / 2) * aspect * sin;
      const fix_y = o.cy + ((fx * o.w) / 2 / aspect) * sin + ((fy * o.h) / 2) * cos;
      const newCx = (fix_x + point.x) / 2;
      const newCy = (fix_y + point.y) / 2;
      const dvx = (point.x - newCx) * cw;
      const dvy = (point.y - newCy) * ch;
      const lx = dvx * cos + dvy * sin;
      const ly = -dvx * sin + dvy * cos;
      ann.w = Math.max(0.001, (Math.abs(lx) * 2) / cw);
      ann.h = Math.max(0.001, (Math.abs(ly) * 2) / ch);
      ann.cx = Math.max(0, Math.min(1, newCx));
      ann.cy = Math.max(0, Math.min(1, newCy));
      ctx.trigger();
    },
    rotate(ctx: DragContext): void {
      const { ann, center, start, client } = ctx;
      if (!center || !start || !client) return;
      const prev = Math.atan2(start.y - center.y, start.x - center.x);
      const cur = Math.atan2(client.y - center.y, client.x - center.x);
      ann.yaw = JSON.parse(JSON.stringify(ann)).yaw + (cur - prev);
      ctx.trigger();
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const hw = ann.w / 2;
      const hh = ann.h / 2;
      const cos = Math.cos(ann.yaw);
      const sin = Math.sin(ann.yaw);
      return { x: ann.cx + -hw * cos - -hh * sin, y: ann.cy + -hw * sin + -hh * cos };
    },
  },
};
```

**Step 6: 注册到 `annotation/index.ts`**

在 `export { polylinePlugin } ...` 后（或任一导出处）加：

```ts
export { cuboidPlugin } from "./tasks/cuboid";
```

**Step 7: 注册到 `annotation/index.vue`**

import 处加 `import { cuboidPlugin } from "@/annotation";`；`plugins` 数组加 `cuboidPlugin,`。

**Step 8: 注册到 `task/index.vue`**（四处映射）

按现有 `rotated_detection`/`panoptic_segmentation` 的位置，加 `{ label: "3D 目标检测", value: "cuboid" }` 到 el-option、搜索 options、`annotationTypeLabel`（`cuboid: "3D 目标检测"`）、`annotationTypeTag`（`cuboid: "danger"`）。

**Step 9: 注册到 `dataset/index.vue`**

- `FORMAT_TASK_MAP` 的 `"x-anylabeling"` 列表加 `"cuboid"`。
- `taskTypeLabel`（或 `taskTypeLabel`/`taskTagType`）映射加 `cuboid: "3D 目标检测"` 与 `cuboid: "danger"`。

**Step 10: type-check / lint**

Run (在 `frontend/`): `pnpm run type-check`；`pnpm run lint`
Expected: 无本模块新增报错（既有无关模块报错忽略）。

**Step 11: 提交**

```bash
git add frontend/src/annotation/tasks/cuboid frontend/src/annotation/index.ts frontend/src/views/module_annotation/annotation/index.vue frontend/src/views/module_annotation/task/index.vue frontend/src/views/module_annotation/dataset/index.vue
git commit -m "feat(annotation): 新增3D目标检测(cuboid)插件并注册"
```

---

### Task 5: e2e 3D 目标检测创建流程

**Files:**
- Create: `frontend/e2e/create-cuboid.spec.ts`

**Interfaces:**
- Consumes: `login`/`createAnnotationTask`/`gotoWorkbench`/`imageBox`/`expectAnnotation`（`e2e/anno-helper.ts`）。
- Produces: 验证 cuboid 标注创建（底部旋转矩形三步 + 面板填 depth）。

- [ ] **Step 1: 创建 `frontend/e2e/create-cuboid.spec.ts`**

```ts
import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 回归护栏：3D 目标检测（cuboid 底部旋转矩形三步绘制 + 面板填深度）创建流程。

test("cuboid 三步拖底部旋转矩形生成标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "cuboid", "cuboid", [
    { id: 1, name: "车", color: "#f56c6c" },
  ]);
  await gotoWorkbench(page, taskId);

  // 经工具栏按钮切到 3D 目标检测工具
  await page.locator(".tool-btn", { hasText: "3D 目标检测" }).click();

  const img = await imageBox(page);
  // 三步：p1(边起点) → p2(边终点) → p3(垂直方向点)
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);

  await expectAnnotation(page);

  // 保存后断言存在标注
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});
```

- [ ] **Step 2: 运行 e2e（需前端 :5180 与后端 :8001 已运行）**

Run (在 `frontend/`): `npx playwright test e2e/create-cuboid.spec.ts --reporter=list`
Expected: 2 passed（含 auth setup）。

- [ ] **Step 3: 提交**

```bash
git add frontend/e2e/create-cuboid.spec.ts
git commit -m "test(annotation): 新增3D目标检测创建流程 e2e"
```

---

### Task 6: 全量回归与收尾验证

**Files:**（无新文件，纯验证）

**Interfaces:**（无）

- [ ] **Step 1: 后端标注相关测试**

Run (在 `backend/`): `uv run pytest tests/test_export_cuboid.py tests/test_export_xanylabeling.py -q`
Expected: PASS。

- [ ] **Step 2: 前端 e2e 回归**

Run (在 `frontend/`): `npx playwright test e2e/create-cuboid.spec.ts e2e/create-rotatedbox.spec.ts e2e/create-polygon.spec.ts --reporter=list`
Expected: 全通过（cuboid + rotated_box/polygon 不回归）。

- [ ] **Step 3: type-check / lint**

Run (在 `frontend/`): `pnpm run type-check`；`pnpm run lint`
Expected: 无本模块新增报错。

- [ ] **Step 4: 汇总核对**

确认 `annotation/index.ts` 导出 `cuboidPlugin`；`task/index.vue` 四处映射含「3D 目标检测 / cuboid」；后端 `AnnotationType` 含 `CUBOID`（大写）；`alembic heads` 为 cuboid 新 revision；`xany_shapes` 含 `cuboid` 分支。全部核对无误后结束。

---

## 相关文件汇总

- `backend/app/api/v1/module_annotation/dataset/model.py`（`AnnotationType.CUBOID`）
- `backend/app/alembic/versions/<new>_cuboid_enum.py`（新建）
- `backend/app/plugin/module_train/exporter.py`（`xany_shapes` cuboid 分支）
- `backend/tests/test_export_cuboid.py`（新建）
- `frontend/src/annotation/core/types.ts`（`CuboidShape` + `"Cuboid"` 枚举）
- `frontend/src/annotation/tasks/cuboid/{useCuboidTool.ts,CuboidCanvas.vue,CuboidPreview.vue,CuboidPanel.vue,index.ts}`（新建）
- `frontend/src/annotation/index.ts`、`frontend/src/views/module_annotation/annotation/index.vue`、`frontend/src/views/module_annotation/task/index.vue`、`frontend/src/views/module_annotation/dataset/index.vue`
- `frontend/e2e/create-cuboid.spec.ts`（新建）
