# 标注工具「创建流程」下沉设计（阶段 C）

- 日期：2026-09-21
- 前置：阶段 A（类型加固）+ 阶段 B（标注编辑交互下沉）已完成
- 分支：`feat/annotation-creation-sink`
- 目标：让「新增任务类型 = 新增 `tasks/<name>/` 目录 + 注册，零改 `core/`」真正成立

---

## 一、背景与问题

阶段 B 已把「已存在标注的编辑交互」（move/resize/rotate/vertex/tagAnchor）下沉到各插件。但**创建新标注的绘制流程**仍全部耦合在核心壳 `AnnotationWorkbench.vue`：

| 耦合点 | 现状 |
|--------|------|
| `onCanvasDown`（约 1391） | 按 `currentTool` 分支：box→`det.onStart`、rotated_box→`rot.onStep`、polygon→`seg.addPoint`、keypoint→`kp.setBoxStart/addPoint`、ocr→`ocr.addQuadPoint/onPoint` |
| `onMove`（约 1666） | box 预览、rotated_box 的 rbLast/rbPreview、keypoint 的 `kp.updateBox` |
| `onUp`（约 1939） | box→`det.onMoveEnd`、keypoint→`kp.build`、rotated_box 清预览 |
| `onDblClick`（约 1360） | polygon→`seg.closePolygon`、keypoint→`kp.beginBox`、ocr→`ocr.closeQuad` |
| 模板预览（115-220） | 按 `currentTool` 硬编码渲染各任务临时图形（kp 框/点、seg 点、rot 三步、ocr 四角） |
| import | 壳直接 import 5 个 `use*Tool`（det/rot/seg/kp/ocr） |

因此新增任务类型仍需改动核心壳：import 新 `useTool`、加 `currentTool` 分支、加模板预览、加三处鼠标事件处理。

**关键确认**：6 个插件每个只有**一个**绘制工具（detection=box、rotatedBox=rotated_box、segmentation=polygon、ocr=ocr、keypoint=keypoint），classification 无绘制工具（`tools` 为空）。

## 二、范围决策（用户确认）

- **仅下沉「绘制三阶段 + 临时预览」**（onCanvasDown/onMove/onUp/onDblClick 的绘制分支 + 预览渲染）。
- **任务特有 UI/面板暂留壳**（见第五节）。

## 三、方案选择

采用**方案 A（插件 `tool` 运行时 + 独立预览组件）**。

理由：预览与「静态标注渲染 renderer」职责分离；壳 `<component :is>` 完全通用；新增任务只需一个 tool + preview 组件；避免把预览状态耦合进各任务的 Canvas renderer（方案 B），也避免把 5 个绘制流程塞进一个通用 hook 重新引入按任务 if/else（方案 C，与「按任务组织」共识相悖）。

## 四、接口与架构

### 4.1 插件 `tool` 接口（`core/types.ts` 新增）

```ts
/** 绘制运行上下文（壳在画布事件时传入） */
export interface DrawContext {
  point?: Point;        // 归一化图像坐标
  event: MouseEvent;
}

/** 任务绘制工具运行时（阶段 C 下沉） */
export interface PluginTool {
  name: string;                    // 工具名（= tools[0].name），壳据此判断绘制模式
  preview?: Component;             // 绘制激活时挂载的临时预览组件
  state?: Record<string, any>;     // 绘制状态（reactive），供 preview 读取
  down?(ctx: DrawContext): void;                       // 按下
  move?(ctx: DrawContext): void;                       // 移动（更新预览）
  up?(ctx: DrawContext): Annotation | null;            // 抬起，返回合法标注则壳 push
  dblclick?(ctx: DrawContext): Annotation | null;      // 双击（闭合/进入框/OCR 闭合）
  reset?(): void;                    // 切换工具/换图/清空时调用
}
```

`AnnotationTaskPlugin` 增加 `tool?: PluginTool`。

- `use<Tool>.ts` 移至各自插件内部使用，**壳不再 import**。
- `state` 采用松散 `Record<string, any>`（项目既有约定，参考 `Annotation` 兼容接口），各任务按需读写。

### 4.2 壳派发（`AnnotationWorkbench.vue` 变薄）

```ts
const isDrawing = computed(() => currentTool.value === plugin.value.tool?.name);

// onCanvasDown
if (isDrawing) { plugin.value.tool?.down?.({ point: p, event: e }); return; }

// onMove
if (isDrawing) { plugin.value.tool?.move?.({ point: p, event: e }); return; }

// onUp
if (isDrawing) {
  const created = plugin.value.tool?.up?.({ event: e });
  if (created && plugin.value.create(created)) {
    created.class_id = selectedClassId.value ?? created.class_id;
    store.annotations.push(created); store.markUnsaved(); pushHistory();
  }
  return;
}

// onDblClick
if (isDrawing) {
  const created = plugin.value.tool?.dblclick?.({ point: p, event: e });
  if (created && plugin.value.create(created)) { push ...; return; }
  return;
}
```

### 4.3 预览渲染

壳在绘制中挂载：

```
<component :is="plugin.tool.preview" v-if="isDrawing && plugin.tool.preview"
           :tool="plugin.tool" :cw :ch :zoom />
```

各任务预览图形（kp 框/点、seg 点线、rot 三步、ocr 四角、box 矩形）在各自 `*Preview.vue` 内实现，读取 `tool.state`。

## 五、保留在壳的任务特有逻辑（用户确认）

- **OCR 文本输入弹窗**：`onUp/onDblClick` 收到 `type === "Ocr"` 的 created 时弹框输入文本。
- **keypoint 名/可见性**：编辑弹窗内（`kp.name`/`kp.visibility` 属于编辑态，随编辑弹窗走）；绘制时的 `setNames`/`addPoint` 由 keypoint 插件 `tool` 自身处理（从当前选中类别取 `keypoint_names` 作为 tool 的输入，不依赖壳）。
- **分类类别选择**：各任务共有（通用，非任务特有）。

## 六、错误与边界处理

- 绘制中切换工具/换图/清空 → 调 `tool.reset()`。
- 合法性由 `plugin.create()` 校验，壳在 push 前调用。
- classification 无 tool → `isDrawing` 恒 false，壳不派发（不回归）。

## 七、数据流

1. 用户选工具 → `currentTool` = 插件绘制工具名。
2. 画布 mousedown → 壳 `onCanvasDown` → `isDrawing` 则派发 `tool.down(point)`。
3. mousemove → 壳 `onMove` → 派发 `tool.move(point)`（更新 `state` 供预览）。
4. mouseup → 壳 `onUp` → `tool.up()` 返回 created → 壳 `create`+`push`。
5. dblclick → 壳 `onDblClick` → `tool.dblclick()` 返回 created → 壳 `create`+`push`（Ocr 时弹文本框）。

## 八、验证

- `vue-tsc --noEmit` 与 `eslint` 无新增错误。
- 六类任务各自「绘制 → 标注出现 → 可移动」e2e。
- 既有标注工作台 e2e 全量回归。

## 九、不做（边界）

- 不重构「任务特有面板」的 UI 位置（keypoint/OCR/分类面板仍按需在壳或弹窗内）。
- 不改造 `currentTool` 的选择列表来源（仍由插件 `tools` 驱动）。
- 不引入新的状态管理框架。
