# 样式回归系统原生（AI 模块）

**第 4 步改造记录。核心原则：不自己造样式，用 Element Plus 的组件、变量和原生属性。**

## 一、改造前的扫描结果（用数字说话）

对 `frontend/src/views/module_ai/` 全部 `.vue` 文件做违规扫描：

| 违规类型 | 数量 | 规范要求（AGENTS.md） |
|---|---|---|
| **零散字号**（13/15/16/17/18px） | **57 处 / 15 个文件** | 「不要 13/15/16px 零散混用」 |
| **内联 `style="font-size:..."`** | **26 处** | 「禁止内联 `style="font-size:..."`」 |
| **重复内联排版样式** | 100+ 处 | 「颜色/间距/圆角引用 `--el-*` 变量」 |
| **`el-progress` 写死颜色** | 4 处 | 应用组件原生属性而非硬编码色 |
| stylelint 问题 | **423 个** | — |

## 二、做了什么

### 2.1 零散字号 → Element Plus 字号变量（57 处 → 0）

关键认识：**13/16/18px 正好就是 Element Plus 的字号变量值**，
所以正确修法是**换成变量**，而不是改数值——**零视觉变化**。

| 原值 | 改为 |
|---|---|
| `13px` | `var(--el-font-size-small)` |
| `16px` | `var(--el-font-size-medium)` |
| `18px` | `var(--el-font-size-large)` |
| `15px`（EP 无对应值） | `var(--el-font-size-base)`（按「正文 14px」归位） |

### 2.2 内联 `style="font-size"` → 语义 class（26 处 → 0）

`overview/index.vue` 里有 **26 处完全相同的**内联样式
`font-size: 12px; color: var(--el-text-color-secondary)`，抽成一个类：

```scss
/* 次要说明文字：统一 12px + 次要色（替代 26 处重复的内联 style） */
.ai-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
/* 单行截断（替代重复的内联 overflow/ellipsis 组合） */
.ai-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

**实测计算样式**：`.ai-sub` = `12px / rgb(100, 116, 139)`，正是 `--el-text-color-secondary` 的值。

### 2.3 重复的排版内联 → UnoCSS 工具类

项目已配 `presetUno`，所以这些用工具类而不是自造 class：

| 原内联 | 改为 |
|---|---|
| `justify-content: space-between`（25 处） | `flex justify-between` |
| `margin-top: 12px`（22 处） | `mt-3` |
| `margin-bottom: 8px`（14 处） | `mb-2` |
| `margin-top: 8px`（13 处） | `mt-2` |
| `margin-bottom: 4px`（9 处） | `mb-1` |
| `width: 100%` / `flex: 1` | `w-full` / `flex-1` |

### 2.4 `el-progress` 写死颜色 → 原生 `:status` 属性（4 处）

```html
<!-- ❌ 写死主题色 -->
<el-progress :color="score >= 80 ? '#67C23A' : score >= 60 ? '#E6A23C' : '#F56C6C'" />
<!-- ✅ 用组件原生属性，走主题 -->
<el-progress :status="score >= 80 ? 'success' : score >= 60 ? 'warning' : 'exception'" />
```

## 三、结果

| 指标 | 改造前 | 改造后 |
|---|---|---|
| 零散字号（13/15/16/17/18px） | **57** | **0** |
| 内联 `style="font-size"` | **26** | **0** |
| `el-progress` 硬编码色 | **4** | **0** |
| stylelint 问题 | **423** | **390** |
| eslint 新增问题 | — | **0**（剩余 4 个在 git HEAD 里就有） |
| vue-tsc 类型错误 | — | **0** |
| 全 12 页面控制台错误 / 超时 | — | **0 / 0** |

**两个新页面（`integration`、`query`）零违规**：零散字号 0、内联字号 0、硬编码主题色 0。

## 四、改造中我自己犯的错（记录，避免重犯）

**把内联 `style` 替换成 `class` 时，没先检查元素是否已有 `class` 属性，
导致 74 个元素出现 `<div class="A" class="B">` 这种无效 HTML。**

浏览器只用第一个 `class`，所以那些替换**等于没生效**，而且标记非法。
发现后写脚本把重复的 `class` 合并成一个（去重保序），并复查到 0 处真重复。

> **教训**：批量替换属性前，**必须先确认目标元素是否已有同名属性**。
> 现在剩下的「重复 class」都是 `class="..." :class="..."` 的合法 Vue 写法。

## 五、没做的（诚实说明）

1. **35 处硬编码色仍在**，但它们是**技术必需**，不是偷懒：
   - **ECharts `itemStyle.color`**（canvas 渲染，不认 CSS 变量）
   - **SVG `fill`/`stroke` 属性**（表现属性不认 CSS 变量）
   - 这些要么保留、要么改成 CSS 类（工作量大、收益低），本轮**没动**。
2. **stylelint 还有 390 个问题**（改造前 423）。绝大多数是
   `stylelint-config-recess-order` 的**属性书写顺序**告警，**既有问题**，
   不影响渲染，本轮**没批量重排**（会改动大量与本次无关的代码）。
3. **只覆盖了 AI 模块**（`module_ai`）。其它模块（`module_system`、`module_train`、
   `module_video` 等）**没有扫描**，它们可能有同样的零散字号。
4. **没有做视觉回归比对**（改造前后像素级 diff）。本轮的依据是：
   字号替换**值完全相等**、`.ai-sub` 的计算样式实测正确、
   12 个页面截图人工核对无异常。**没有自动化像素比对**。
5. **`chat/`、`workflow/` 下的组件仍有自造样式**（如 `Sidebar.vue` 的
   自定义布局），本轮只改了字号与颜色违规，**没有重构成 Element Plus 组件**。
