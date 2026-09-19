# 标注工作台组件化与插件式标准化设计

- 日期：2026-09-19
- 状态：设计评审中
- 适用范围：仅前端（`frontend/`），后端接口保持不变

## 一、背景与目标

当前标注工作台位于 `frontend/src/views/module_annotation/annotation/index.vue`（约 4430 行），单文件承担了全部任务类型（detection / rotated_detection / segmentation / keypoint / ocr / classification）的绘制、编辑、渲染、拖拽、状态、历史、快捷键、右键菜单等逻辑。存在以下问题：

- 单文件过大，职责混杂，难以维护与扩展。
- 新增任务类型（音频、语义分割、深度、视频、3D 点云）会继续污染主文件。
- 无法在其它 Vue3 + Element Plus 项目中复用整套标注逻辑。

**目标**：把标注工作台抽象为**项目内独立、可复用、插件式**的组件库，使"新增任务类型"只需注册一个任务插件，不修改框架主体；整套组件可拷贝或作为本地库引入其它项目。

## 二、复用边界与决策

| 议题 | 决策 |
|------|------|
| 复用层面 | **仅前端组件**；后端 `module_annotation` 接口与数据结构不变 |
| 任务扩展方式 | **插件式注册**：新任务 = 一个独立任务插件组件，不改框架 |
| 载体形态 | **项目内独立目录 + 公共 API 出口**（`frontend/src/annotation/`） |
| 落地策略 | **分阶段渐进**：先搭骨架+迁移一个任务验证，再逐个迁移其余类型，每阶段行为不变、测试全绿 |

## 三、总体架构

```
frontend/src/annotation/
  index.ts                          # 公共 API 出口
  core/
    AnnotationWorkbench.vue         # 工作台壳
    useAnnotationCanvas.ts          # 画布 hook（缩放/平移/坐标换算）
    useAnnotationStore.ts           # 标注状态（Pinia store 化）
    AnnotationCanvas.vue            # 画布容器
    AnnotationToolbar.vue           # 通用 + 任务工具
    AnnotationLabelRenderer.vue     # 通用标签渲染
    types.ts                        # 坐标/标注对象/插件接口类型
    schema.ts                       # 标注对象与坐标约定常量
  tasks/
    detection/
    rotatedBox/
    segmentation/
    keypoint/
    ocr/
    classification/
    (未来: audio/ semanticSeg/ depth/ ...)
```

核心思想：把"每个任务是什么"（工具、绘制手势、编辑手柄、渲染、校验）从框架剥离成 **任务插件**；框架只负责"通用能力"（画布、坐标、状态、选中、历史、通用工具、布局）。

## 四、任务插件接口（`defineAnnotationTask`）

```ts
interface AnnotationTaskPlugin {
  name: string;                 // 'detection' / 'rotated_detection' / ...
  label: string;                // 中文名，如「目标检测」
  color: string;                // 任务标签色（el-tag 用）
  renderer: Component;           // 该任务标注的渲染子组件（按 ann.type 分发内部形态）
  tools: ToolDefinition[];       // 专属绘制工具（box / rotated_box / polygon / keypoint / ocr / classification）
  create(shape: any): boolean;   // 几何校验（零面积 / 越界等）
  onDrag?(...): void;            // 该任务的编辑语义（手柄 / 顶点 / 旋转）
}
```

框架通过 `AnnotationWorkbench` 的 `task="detection"` prop 选择插件，并注入到通用画布/工具栏/状态。

## 五、通用层与任务层职责边界

| 层 | 职责 | 不做什么 |
|----|------|---------|
| **core（通用层）** | 画布缩放/平移、坐标换算（鼠标↔图像归一化）、选中态、历史/撤销、未保存、快捷键、右键菜单、通用工具（select/pan/zoom）、布局、`AnnotationLabelRenderer` 标签渲染基座 | 不写任何具体任务的几何/编辑 |
| **tasks（任务层）** | 各自工具的绘制手势、编辑手柄/顶点/旋转、几何校验、各自渲染器 | 不写画布/状态/历史 |

## 六、渲染层

- 画布用 SVG，`viewBox="0 0 cw ch"`，CSS 尺寸 = 图像显示尺寸，坐标归一化 [0,1]。
- 各任务的几何形状由任务渲染子组件输出（AxisAlignedBox / RotatedBox / Polygon / Keypoint / Ocr / Classification）。
- **标签背景保持确定性**：背景宽高按文字实际渲染 `getBBox()`（同步）加边距计算，保证任何缩放/字号下背景必然包住文字；触发时机为图像加载完成、标注增删、切图、字号变化后的 `nextTick`（同步读取，无异步跳变）。

## 七、数据流

- `useAnnotationStore`（Pinia）承载：`annotations`、`selectedAnnotationId`、`currentImage`、`taskId`、`images`、`unsaved`、历史栈。
- 绘制/编辑 → 直接修改 store.annotations（响应式）→ 画布渲染。
- 保存：调用后端 `saveAnnotations(task_id, image_id, annotation_data)`，格式 `/annotation_data` 数组保持不变。
- 历史：以 `annotKey`（序列化整个标注集）为 key，`pushHistory/undo/redo/restoreHistory` 本地重放；恢复仅在真正变更时标记未保存。
- 通用工具 select/pan/zoom 与任务工具的互斥、切换时 `resetDrawingState()` 清理绘制残留。

## 八、错误处理与边界

- 只读锁定（他人已标注）时禁止新增/编辑/撤销/删除；前端 `v-hasPerm` 权限与后端权限一致。
- 几何校验（零面积/越界）由任务插件 `create()` 承担；未保存检测通过 `beforeunload` 拦截。
- 坐标归一化越界钳制（[0,1]），避免异常值污染导出。

## 九、测试策略

- 每个任务插件有独立的渲染/绘制/校验测试（组件级）。
- 保留现有 e2e（workbench、annotation-task-classes、annotation-history、collaboration、clean 相关）作为回归基线。
- 分阶段迁移时，每阶段跑通上述回归 + `uv run pytest`（后端不变）。

## 十、分阶段迁移计划

- **阶段 0**：建目录骨架 + core 通用层（`AnnotationWorkbench`/canvas/state/label renderer/types/schema）+ `defineAnnotationTask` 接口 + 脚手架；迁移 **detection** 一个任务作为插件验证接口合理性；行为不变、测试全绿。
- **阶段 1**：迁移 rotated_detection。
- **阶段 2**：迁移 segmentation。
- **阶段 3**：迁移 keypoint。
- **阶段 4**：迁移 ocr。
- **阶段 5**：迁移 classification + 移除 `views/.../annotation/index.vue` 中依赖，改由 `AnnotationWorkbench` 承载。
- 每阶段独立提交、可回滚；全部完成后，`index.vue` 归档/删除，工作台页仅引用 `AnnotationWorkbench`。

## 十一、交付与验收

- 功能行为与重构前完全一致（同一后端接口、同一数据格式、同样交互）。
- `index.ts` 导出 `AnnotationWorkbench` + `defineAnnotationTask` + `schema/types`，无本项目内部模块依赖，可拷贝到其它 Vue3+EP 项目使用。
- 新增任务类型 = 在 `tasks/` 加一个插件目录，零框架改动。

## 十二、范围外（不在本次）

- 后端 `module_annotation` 接口/数据结构/训练导出对接，均不改动。
- 旋转框 8 向缩放手柄、OCR 四边形插顶点、mousemove 去重等"任务内增强"，作为后续任务插件内的独立小项，不在本次框架重构范围；迁移时保持现有行为。
