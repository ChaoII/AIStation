# 画笔像素分割（SP-A）设计

> 为实例分割 / 语义分割 / 全景分割任务补充「画笔（brush）」这一像素级自由绘制方式，产物复用现有 `Polygon` 数据与导出链路。

## 1. 背景与目标

当前三个分割任务（`segmentation` 实例 / `semanticSegmentation` 语义 / `panopticSegmentation` 全景）都只支持基于多边形顶点（`points`）的逐点勾勒，缺少像素级自由绘制能力（Label Studio 的画笔/笔刷）。

**目标**：给这三个分割任务各新增「画笔」工具，让标注者以自由笔刷描摹区域，松手后自动转成多边形轮廓。产物仍是 `Polygon`，**零后端改动、零导出改动**。

**非目标（YAGNI）**：
- 不新增标注类型 / 形状（沿用 `Polygon`）。
- 不做像素级掩码存储（RLE / 独立 mask 图）——不引入新存储与导出链路。
- 不再重复做区域填充（panoptic / 语义已有填充背景能力，保留不变）。
- 不为画笔改动具体业务的 `AnnotationWorkbench.vue` 业务分支；仅在 core 层面把**单 `plugin.tool` 泛化为按 `currentTool` 分发的多工具机制**（通用增强，方案 A），画笔作为通用能力的一种工具接入。

## 2. 范围

| 项 | 内容 |
|----|------|
| 覆盖任务 | 实例分割 `segmentation`、语义分割 `semanticSegmentation`、全景分割 `panopticSegmentation` |
| 新增交互 | 画笔（自由描摹）、笔刷大小调节、橡皮擦（减除）、实时预览、松手自动闭合转多边形 |
| 数据产物 | `Polygon`（`points: Point[]`，归一化 `[0,1]`） |
| 导出 | 复用现有 `xany_shapes` / YOLO seg / panoptic mask 分支，无新增逻辑 |

## 3. 交互设计

- 各分割插件的 `tools` 数组新增一项：`{ name: "brush", label: "画笔分割", title: "按住拖动自由描画，松手自动转多边形" }`，与现有 `polygon` 工具**并存**，用户可切换。
- 依赖 core 的多工具分发（见 §5）：插件在 `tools` 中同时声明 `polygon` 与 `brush` 两个可绘制工具，工作台按 `currentTool` 解析出对应 `PluginTool`，从而两个按钮都能独立绘制。
- 画笔状态：
  - `down`：开始一条笔画，记录轨迹点。
  - `move`：追加轨迹点，实时预览粗线（圆头笔刷，`lineCap/lineJoin = round`）。
  - 橡皮擦：绘制过程中可切换；对当前笔刷位图做 `destination-out` 擦除，预览同步更新。
  - `up`（松手）：结束笔画，对位图做轮廓提取 → 转 `Polygon` → 作为新标注提交。
- 笔刷半径：由面板 / 工具栏提供数值调节（归一化到图像宽度或像素值，取可调刻度）。

## 4. 数据生成（位图 → 多边形）

绘制阶段用**离屏 `<canvas>`**（尺寸 = 图像像素 `cw × ch`）维护二值笔刷掩码：

1. 前景：以圆头笔刷沿轨迹画出粗线（`ctx.lineCap="round"`、`lineJoin="round"`、`stroke()`），累加到掩码。
2. 橡皮擦：`ctx.globalCompositeOperation="destination-out"` 擦除。
3. 松手后：
   - `getImageData` 提取 alpha 通道，按阈值得到**二值掩码**（`mask: Uint8Array`，1=前景）。
   - `maskToPolygon(mask, cw, ch)`：对该二值掩码做**轮廓提取**（边界追踪），得到外轮廓（可能含孔洞，取最大外轮廓，孔洞暂不处理，见 §9 限制）。
   - **Douglas-Peucker** 顶点简化，控制顶点数（避免超密）。
   - 顶点归一化到 `[0,1]`，生成 `Polygon` 标注。

> 轮廓提取与简化为**纯函数**，输入二值掩码 `(mask, cw, ch)`，输出 `Point[]`，与 canvas 解耦、可单测。

## 5. core 下沉与模块结构

下沉到 `core/`（用户选定方案 C——作为通用能力便于未来复用）：

```
frontend/src/annotation/core/brush.ts        # useBrushTool 状态机 + 纯函数
frontend/src/annotation/core/BrushPreview.vue # 共享轨迹/掩码实时预览
```

- `brush.ts`：
  - `useBrushTool()`：状态机——`strokes`（当前笔画点集）、`brushSize`、`erasing`（是否橡皮擦）、`start/move/end/reset`；持有一个共享的离屏 canvas 掩码，把 `ImageData` 归一为二值掩码。
  - `maskToPolygon(mask: Uint8Array, cw: number, ch: number)`：二值掩码 → 轮廓提取 → DP 简化 → 归一化 `Point[]`（**纯函数，可单测**，与 canvas 解耦）。
  - `simplifyPolygon(points, tolerance)`：Douglas-Peucker（**纯函数，可单测**）。
- `BrushPreview.vue`：显示当前笔刷掩码/轨迹的实时预览（叠加在画布上）。
- 三个分割插件（`segmentation`/`semanticSegmentation`/`panopticSegmentation` 的 `index.ts` 与各自 canvas）仅挂载该工具并复用各自渲染画布；不新增各任务的重复画笔逻辑。
- `core/types.ts` 不新增形状类型（产物为 `Polygon`）；如需在 `PluginPanelContext` 提供笔刷大小通道，按既有 `update`/`selectedAnnotationId` 同方式扩展。

### 5.1 多工具分发机制（方案 A，通用增强）

现状：`AnnotationTaskPlugin.tool?: PluginTool` 为**单对象**，`tools: ToolDefinition[]`（`{name,label,title}`）仅作按钮；工作台只在 `currentTool === plugin.tool.name` 时调用 `tool.down/move/up/dblclick`。因此一个插件当前只能有一个可绘制工具。

**扩展**：
- 让 `PluginTool` 的 name 与 `ToolDefinition` 对齐，并在插件层提供**按名称取 `PluginTool`** 的映射：`AnnotationTaskPlugin` 新增可选 `toolMap?: Record<string, PluginTool>`（向后兼容：缺省时取 `tool`，其 name 与 `tools[0].name` 一致，保持既有单工具插件不变）。
- `AnnotationWorkbench.vue` 用 `activeTool = computed(() => toolMap?.[currentTool] ?? (currentTool === tool?.name ? tool : undefined))` 替换全部 `plugin.tool` 直接引用（分发点：preview 渲染、`down/move/up/dblclick/keydown`、`reset`）。`isDrawing` 改为 `activeTool?.name === currentTool`。
- 效果：一个插件可在 `tools` 中声明多个可绘制工具（如 `polygon` + `brush`），各自有独立 `PluginTool`；工作台按 `currentTool` 分发。既有单工具插件行为不变（回归护栏）。

## 6. 导出与兼容

- 产物为 `Polygon`，直接复用现有 `exporter.xany_shapes` 的 `Polygon` 分支、YOLO seg 归一化顶点分支、`_panoptic_mask` 多边形栅格化——**无导出新增代码**。
- 导入 `x_anylabeling_importer` 的 `polygon` 分支同样兼容（无需改动）。

## 7. 选型账本（位图 → 多边形轮廓提取）

| 候选 | 许可 | 最近发布 | 评估 |
|------|------|----------|------|
| `marching-squares` | **AGPL-3.0** | 2024-11 | 违反本项目"宽松许可（MIT/Apache）"门槛 → **落选** |
| OpenCV.js | Apache / BSD | — | 体积 >8MB，前端过重、加载慢 → **落选** |
| 手写二值轮廓提取 + Douglas-Peucker | — | — | 无依赖、可控、纯函数可单测、规模小 → **选用** |

**结论**：采用手写轻量二值轮廓提取 + Douglas-Peucker 简化（接入上述无成熟宽松许可库的现实选择），写为纯函数并配单测。

## 8. 测试

- **前端单测（引入 Vitest）**：项目当前无前端单测框架，按"优先成熟第三方库"引入 **Vitest**（MIT、活跃、Vite 原生）。单测覆盖纯函数：
  - `simplifyPolygon`（顶点简化、容差）；
  - `maskToPolygon`（斜线/圆/擦除残留多区域等二值掩码 → 顶点，含擦除减除用例）。
  - 将轮廓提取的输入设计为**脱离 canvas 的二值掩码**（`boolean[][]` 或 `Uint8Array` + 宽高），使单测无需 canvas/jsdom；`useBrushTool` 负责把 `ImageData` 归一为该掩码。
- **e2e**：在分割任务上切换「画笔分割」工具 → 拖画一笔 → 生成 `Polygon` 标注节点 → 保存后 `expectAnnotation`。
- **回归**：
  - 三个分割任务的既有多边形流程无回归（type-check / lint / 既有 e2e）。
  - 多工具分发：既有单工具插件（detection/rotatedBox/keypoint/ocr 等）在 `toolMap` 缺省下行为不变（e2e 单点覆盖 + type-check）。

## 9. 已知限制

- 转多边形采用**最大外轮廓**，孔洞（如 O 形中空）暂不保留为多边形（后续可扩展为多环或掩码模式）；空洞精度受笔刷半径影响。
- 橡皮擦作用于**绘制阶段**的笔刷位图；转换成多边形后如需二次修正，用现有顶点编辑手柄。
- 轮廓提取后顶点数受 DP 简化约束，极端细碎笔划可能被简化掉（可调容差）。
- 多工具分发依赖 core 改动：需对既有单工具插件做回归，确保 `toolMap` 缺省路径（回退单 `tool`）行为不变。
