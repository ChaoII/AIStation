# AIStation 标注组件库抽象评估与重构方案

- 日期：2026-09-20
- 范围：`frontend/src/annotation/`（core + tasks 插件）
- 状态：评估报告，待后续立项实施

---

## 背景

标注组件库已从"单体工作台"重构为「核心壳 + 任务插件」结构，生产环境已切换（`views/module_annotation/annotation/index.vue` 薄包装，旧实现归档 `index.legacy.vue`）。

当前评估聚焦一个问题：**"加一种新的标注任务，成本是多少？"** 即插件化的抽象是否彻底，交互逻辑是否真的下沉到了插件。

---

## 一、现状分析

### 1.1 目录结构

```
annotation/
  index.ts                     # 插件注册表（aggregate exports）
  core/
    AnnotationWorkbench.vue     # 核心壳（约 2000 行，大杂烩）
    AnnotationCanvas.vue        # 画布容器（图像加载/坐标换算）
    AnnotationToolbar.vue       # 顶部工具栏
    AnnotationRightPanel.vue    # 右栏（类别/标注列表）
    AnnotationHistoryBar.vue    # 底部历史条
    AnnotationLabelRenderer.vue # 标签层
    annotationTypes.ts          # WorkbenchApi / WorkbenchConfig / CollabAdapter
    useAnnotationStore.ts       # Pinia store
    useAnnotationCanvas.ts      # 画布交互 hook
    types.ts                    # Annotation / Plugin 类型
  tasks/
    detection/    index.ts + DetectionCanvas.vue + useDetectionTool.ts
    rotatedBox/   index.ts + RotatedBoxCanvas.vue + useRotatedTool.ts
    segmentation/ index.ts + SegmentCanvas.vue + useSegmentTool.ts
    keypoint/     index.ts + KeypointCanvas.vue + useKeypointTool.ts
    ocr/          index.ts + OcrCanvas.vue + useOcrTool.ts
    classification/ index.ts + ClassificationCanvas.vue
```

### 1.2 度量（代码行数，印证判断）

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/AnnotationWorkbench.vue` | ~2000 | 壳 + 几乎所有任务交互 |
| `tasks/*/use*Tool.ts` | 40~68 | 各任务几何工具（很薄） |
| `tasks/*/*Canvas.vue` | 28~114 | 各任务渲染 |

**关键信号**：核心壳的行数是各任务工具合计的 ~10 倍以上，说明**交互逻辑集中在壳内**，插件只承担了「渲染」。

---

## 二、抽象评估（五大维度）

### 2.1 分层与解耦 —— ✅ 良好

- `core/` 不 import 业务模块；`api`/`collab`/`config` 通过 props 注入（`WorkbenchApi`/`WorkbenchConfig`/`CollabAdapter`）。
- 依赖注入化解耦干净，符合组件库定位（可复用、可测试）。

### 2.2 插件扩展点 —— ⚠️ 半良好

- 有注册表（`plugins` 数组）+ `AnnotationTaskPlugin` 接口（name/label/color/renderer/tools/create/onDrag）。
- **但** 插件只表达了「渲染」与「创建校验」，没有声明「编辑行为」。

### 2.3 渲染与工具分离 —— 🌗 中等

- 每任务拆成 `*Canvas.vue`（渲染）+ `use*Tool.ts`（几何），方向对。
- **但** `use*Tool` 只封装"计算"，不包含"与壳的交互契约"。

### 2.4 类型安全 —— ⚠️ 弱

- `types.ts` 中 `Annotation` 为 `[key: string]: any`，未做**判别联合**。
- 不同任务字段（`x1/y1` vs `cx/cy/angle` vs `points` vs `keypoints`）全靠运行时 `if (ann.type === ...)` 分支。
- `Plugin.renderer: any`、`WorkbenchApi` 大量 `any`，缺少组件级 props/emits 契约。

### 2.5 交互下沉（本次核心缺口）—— ❌ 未下沉

核心壳内存在大量按任务类型分发的 if 链（截取自 `AnnotationWorkbench.vue`）：

```ts
// onHandleDown
if (handle.startsWith("kpb-")) {...}
if (handle.startsWith("kp-")) {...}
if (handle.startsWith("ocr-")) {...}
if (handle.startsWith("poly-ins-")) {...}
if (handle.startsWith("poly-")) {...}

// onMove 的 dragState.type 分支
if (dragState.type === "kp-move") {...}
if (dragState.type === "kp-resize") {...}
if (dragState.type === "kp-vertex") {...}
if (dragState.type === "poly-vertex") {...}
if (dragState.type === "rotate") {...}
if (dragState.type === "move") {
  if (ann.type === "AxisAlignedBox") {...}
  else if (ann.type === "RotatedBox") {...}
  else if (ann.type === "Polygon") {...}
  else if (ann.type === "Ocr") {...}
}
if (dragState.type === "resize") {
  if (ann.type === "RotatedBox") {...}
  else if (ann.type === "AxisAlignedBox") {...}
  else if (ann.type === "Ocr") {...}
}

// tagStyle 锚点
if (ann.x1 !== undefined) {...}          // AxisAlignedBox
else if (ann.type === "RotatedBox") {...}
else if (ann.cx !== undefined) {...}     // 旋转框中心
else if (ann.bounding_box) {...}         // Keypoint
else if (Array.isArray(ann.points)) {...}// Polygon / Ocr
```

**结论**：`AnnotationTaskPlugin.onDrag` 形同虚设（基本未被调用），所有编辑行为由核心壳代劳。要加新任务，仍需改 `AnnotationWorkbench.vue`。

---

## 三、重构成本评估

| 缺口 | 现状 | 目标 | 重构成本 | 风险 |
|------|------|------|---------|------|
| 1. `Annotation` 判别联合 | `[key:string]:any` | 按 type 收窄 | **中**（需动所有 task 的字段引用 + 壳内 if 改收窄） | 中（改面广，需回归 6 类任务） |
| 2. 交互下沉到插件 | 壳内 if 链 | 插件声明 move/resize/vertex/create/tagAnchor | **高**（核心壳大幅瘦身） | 高（行为等价难，易引入回归） |
| 3. `renderer` 类型化 | `any` | 约束 Canvas props/emits 契约 | 低 | 低 |
| 4. `WorkbenchApi` 类型化 | 多 `any` | 接口明确 | 低 | 低 |
| 5. 插件能力声明完整 | 仅 create/onDrag | move/resize/vertex/create/tagAnchor | 中 | 中 |

### 优先级建议

- **P1（低风险，高收益）**：`renderer` + `WorkbenchApi` 类型化，`Annotation` 判别联合。收益是类型安全、消除多处理撞。
- **P2（高风险，高收益）**：交互行为下沉到插件。收益是"加任务零改壳"。**必须分任务增量化进行**，每迁移一类跑一次 e2e 回归。

---

## 四、推荐演进路线（分阶段，可灰度）

### 阶段 A：类型加固（先做，安全）
1. `types.ts` 定义判别联合：`AxisAlignedBox | RotatedBox | Polygon | Keypoint | Ocr | Classification`，各自字段明确。
2. `Plugin.renderer` 泛型化，定义 `CanvasProps`/`CanvasEmits` 契约接口。
3. `WorkbenchApi` / `WorkbenchConfig` / `CollabAdapter` 补全类型，去掉散落的 `any`。
4. 目标：`vue-tsc --noEmit` 通过，消掉壳内大量 `as any`。

### 阶段 B：抽出「编辑行为」抽象（增量化，高风险）
1. 扩展 `AnnotationTaskPlugin`，新增能力声明：
   ```ts
   interface AnnotationTaskPlugin {
     ...
     renderer: TaskCanvas;
     create(shape): boolean;
     // 新增（声明可选行为）
     move?(ann, orig, dx, dy): void;
     resize?(ann, orig, handle, ctrl): void;
     /** 顶点级编辑（polygon/ocr/keypoint） */
     vertexMove?(ann, handle, point): void;
     vertexInsert?(ann, handle): void;
     vertexDelete?(ann, handle): void;
     /** 标签锚点 */
     tagAnchor?(ann): { x: number; y: number } | null;
     start?(ctx): Annotation | null;   // 绘制 steps
   }
   ```
2. `AnnotationWorkbench.vue` 改为**派发器**：把 move/resize/vertex/tagAnchor 委托给 `plugin.xxx`，否则默认实现。
3. **迁移顺序**（每类一提交 + e2e）：
   - 先 `detection`（基准，已有）→ `RotatedBox` → `Polygon` → `Ocr` → `Keypoint` → `Classification`（无几何最简）。
4. 迁移完一类，`onMove`/`onHandleDown`/`tagStyle` 相应删掉该类分支。

### 阶段 C：核心壳瘦身与验收
1. `AnnotationWorkbench.vue` 应降到只保留「通用流程」：选择/创建/保存/历史/协作/撤重。
2. 量级目标：壳内不再出现 `ann.type === "xxx"` 的交互分支。
3. 验收标准（每个新任务场景）：
   - 新增任务类型 = 新增 `tasks/<name>/` 目录 + 注册，**零改** `core/`。
   - `vue-tsc` 通过、`eslint` 无新增、六类任务各自 e2e 通过。

---

## 五、明确不做的（共识边界）

- **不**把画布/标签层改成第三方（SVG/Canvas2D 性能已达标，见此前优化）。
- **不**引入额外的状态管理框架，保留现有 Pinia。
- **不**在阶段 A 阶段就冒险拆壳（避免一次性大改引入回归），先类型、后行为、再瘦身。

---

## 六、结论

当前抽象**方向正确、分层清晰、解耦出色**，是可用且已上线的质量；但"交互逻辑下沉"这一步还没做，导致插件只承担渲染、加任务仍需动核心壳。

- **低垂果实**：类型加固（阶段 A），成本低、收益直接。
- **核心突破**：交互行为下沉（阶段 B），需要分任务增量化 + e2e 兜底。
- **最终目标**：壳变"纯壳"，插件真正接管渲染 + 编辑行为。

是否立项执行？若执行，建议**从阶段 A（类型加固）开始**，它是阶段 B 的前置，且无行为回归风险。

---

## 七、阶段 A 执行记录（2026-09-20 已立项）

### 共识决策
- **保留按任务组织**（不学竞品形状层）：任务决定开放哪些工具，检测任务不开放旋转矩形工具——针对性强、是正确产品取舍。
- 阶段 B 目标调整为"交互下沉到各任务插件"而非"重构成形状层"，让"按任务组织"名副其实。

### 已落地改动（`frontend/src/annotation/core/types.ts`）
1. **新增各形状判别联合类型**（非破坏性）：
   - `AxisAlignedBoxShape` / `RotatedBoxShape` / `PolygonShape` / `OcrShape` / `KeypointShape` / `ClassificationShape`
   - `ShapeAnnotation` 判别联合，供新增代码引用。
   - 保留 `Annotation` 为兼容接口（`[key:string]:any`），**不强制改造存量访问**。
2. **定义 Canvas 契约**：
   - `TaskCanvasProps` / `TaskCanvasEmits`（六个 Canvas 高度一致的 props/emits）。
   - `TaskCanvasRenderer` 泛型替代 `renderer: any`，`AnnotationTaskPlugin.renderer` 引用该契约。

### 未做（务实权衡，记录原因）
- **未将 `WorkbenchApi` 的 `any` 强制收成强类型**：workbench 统一经 `r?.data?.data` 访问后端包裹结构，收紧需与后端响应精确对齐，会牵动 13+ 处调用；且 `updateTask`/`saveAnnotations` 载荷结构后端不定，保留 `any` 是合理选择。
- **未将 `Annotation` 改为严格判别联合**：workbench 内字段访问（points/cx/cy/bounding_box/keypoints/angle/text/width/height 等）约 50+ 处，强制收窄会全部报错、需逐一加守卫，工作量和回归风险远高于收益。当前以"补全类型别名 + 新代码优先判别联合"渐进推进。

### 阶段 A 完成定义
- `vue-tsc --noEmit` 通过（新增类型不破坏存量）。
- `eslint` 无新增错误。
- 六类任务 e2e 回归通过。
