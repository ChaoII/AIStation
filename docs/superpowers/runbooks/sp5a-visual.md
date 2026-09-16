# SP5-a 规则编辑器 e2e + 视觉核对（Task 8）

- 日期：2026-09-15
- 计划：`docs/superpowers/plans/2026-09-15-sp5a-rule-editor.md` Task 8
- 设计：`docs/superpowers/specs/2026-09-15-sp5a-rule-editor-design.md` §4.7 / §5

## 一、e2e（Playwright）

- 用例：`frontend/e2e/sp5a-rule-editor.spec.ts` → 「规则编辑器：ROI 画布 + 条件树 创建并回填」
- 覆盖链路（复用既有 `e2e/auth.setup.ts` 登录态与 hash 路由约定）：

  登录 → `/#/video/alarm` → 切「告警规则」页签（lazy）→ 新增 → 选场景 `DET_ZONE`
  → ROI 画布点 4 点 → 条件树新增一个 `object_present` 叶子 → 填名称/摄像机 → 保存
  → 列表出现新规则（且告警类型为 `DET_ZONE`）→ 重新打开编辑 → 断言 ROI 点列与条件树回填一致。

- 关键断言方式：后端无 `/rule/detail/{id}`，编辑态由列表接口回填；ROI 经参数编译层注入
  `conditions[].region`，因此**断言「条件预览」JSON** 即可同时覆盖 ROI 点列（`region` 4 点）
  与条件树回填（2 个 `object_present` 叶子、`label=person`、`min_confidence=0.4`）。

- 运行（需后端 8001 + 前端 5180 已启动；`auth.setup` 自动登录 admin/123456）：

  ```bash
  cd frontend && pnpm run e2e -- sp5a-rule-editor
  ```

- 结果：**PASS**（`2 passed`，含 setup；用例 6.9s）。

## 二、截图与视觉核对

- 截图：`docs/superpowers/runbooks/sp5a-visual/rule-editor.png`
  （编辑态对话框：ROI 4 点闭合多边形 + 场景参数 + 条件树 2 行 + 暂不支持叶子；视口 1600×1000，含页面框架便于风格对比）
- 核对工具：`vision-recognition` 技能（本地 Qwen3.6-27B，`recognize_image.py`）

### 结论：**通过（无严重样式割裂）**

识别确认：

| 项 | 结果 |
|----|------|
| 画布闭合蓝色多边形 | 是，矩形，**4 个顶点** |
| 条件树 | 两行 `存在目标 contains person`，中间黄色 `and` 连接 |
| 场景参数 | 置信度 0.40（数字输入）、目标标签 `person`（多选标签） |
| 风格一致性 | 与 Element Plus 一致（颜色/圆角/字号大体统一），无控件错位或被裁切 |

次要观察（不阻塞，作为后续打磨项）：

1. 「Add filter」按钮圆角/配色为第三方 `@svar-ui/vue-filter` 默认样式，与 `el-button` 略有差异
   （ConditionTree 已用 `--el-*` 覆盖主题，按钮尺寸/圆角仍由库决定）；条件树内的 `and` 为库默认黄色 pill。
2. 编辑器整体较高（ROI 画布 16:9 + 条件树），在小视口下需页面滚动；非功能缺陷。

## 三、本次修复的阻断性缺陷（重要，额外改动 1 个文件）

**现象**：在规则对话框内点击条件树的 `Add filter` / `Apply` / `Cancel` 等按钮，**页面整页刷新、
对话框内容全部丢失**。

**根因**：`@svar-ui/vue-filter` 的按钮是原生 `<button>`（未设 `type`，默认 `submit`），而
Element Plus 的 `<el-form>` 渲染的是裸 `<form>`（不拦截 submit），按钮位于表单内即触发原生表单提交。

**修复**：`frontend/src/views/module_video/alarm/components/RuleEditor.vue` 的内层 `<el-form>`
加 `@submit.prevent`（submit 在 form 上触发并向祖先冒泡，故在最内层表单拦截）。
仅 1 行，属必要修复——不修则 e2e 与真实用户都**无法使用**条件树。

> 复用 POC 结论：该缺陷在 Task 1 的 POC 页面未暴露（POC 页面不在 `el-form` 内），是 Task 7 集成对话框后才引入的。

## 四、已知小问题（未修，供后续决策）

**ROI 画布固定宽度导致对话框轻微水平溢出**（实测，视口 1600）：

| 元素 | clientWidth | scrollWidth | 右边超出对话框 |
|------|------------|-------------|----------------|
| `.el-dialog` | 960 | 976 | +16px |
| `.el-dialog__body` | 928 | 960 | +32px |
| `.roi-canvas` / `.roi-canvas__stage` | 640 | 640 | 超出父内容区 52px |

原因链：`RoiCanvas` 的 `onMounted` 用 `ResizeObserver` 观察 `.roi-canvas__stage` 自身，而 Konva `Stage`
会把该容器的行内 `width` 设为 `stageW`，形成「观察自身又被自身撑大」的环 → 画布锁定在初始的
640×360，不再随容器收缩；嵌套在 `el-form-item` 中时使内容区超宽。

- 影响：`overflow: visible`，无滚动条、内容不丢失，仅场景参数控件右侧**轻微溢出对话框边框约 16px**。
- 建议修复（未做，避免超出本任务范围）：改为观察外层 `.roi-canvas`（`width:100%`）而非 `.roi-canvas__stage`。

## 五、复现命令

```bash
# 后端
cd backend && uv run main.py run --env=dev
# 前端
cd frontend && pnpm run dev
# e2e（自动截图到 docs/superpowers/runbooks/sp5a-visual/）
cd frontend && pnpm run e2e -- sp5a-rule-editor
# 视觉核对
python <skills>/vision-recognition/scripts/recognize_image.py \
  ../docs/superpowers/runbooks/sp5a-visual/rule-editor.png --prompt "…"
```
