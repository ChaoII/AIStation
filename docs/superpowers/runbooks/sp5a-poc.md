# SP5-a 第三方组件集成 POC（前置闸门）

- 日期：2026-09-15
- 计划：`docs/superpowers/plans/2026-09-15-sp5a-rule-editor.md` Task 1
- 设计：`docs/superpowers/specs/2026-09-15-sp5a-rule-editor-design.md` §3

## 结论：PASS（可作为 Task 5/6 的实现基础）

两个第三方组件在本项目（Vue 3.5.39 + Vite 6.4.3 + Element Plus 2.14.2 + TS 5.9.3）中均可正常安装、编译、渲染与产出数据，浏览器控制台无任何 error。

| 组件 | 解析版本 | 结论 |
|------|----------|------|
| `@svar-ui/vue-filter`（FilterBuilder） | **2.6.1** | 可用（嵌套 AND/OR + JSON 进出 + 值编辑）；有 2 处能力缺口，见下 |
| `vue-konva` | **4.0.1** | 可用（声明式 Stage/Layer/Line/Circle，事件与坐标拾取正常） |
| `konva` | **10.5.0** | vue-konva 4.x 的 peer，正常 |

> Task 2/5/6 的契约据此锁定：
> - `RoiCanvas`：`v-model: number[][]`（归一化 0~1）——POC 实测 4 次点击输出 `[[0.199854,0.199870],[0.799414,0.199870],[0.799414,0.798828],[0.199854,0.798828]]`。
> - `ConditionTree`：`FilterBuilder` 的 `change` 事件产出 `IFilterSet`，需再转换为后端条件树 `{op, children:[{subject,...}]}`。

## 一、@svar-ui/vue-filter 2.6.1 真实 API（读 `types/*.d.ts` + 运行时实证）

### 1.1 组件与 props（运行时 props 定义，来自 `dist/index.es.js:627`）

```js
props: {
  value:   { default: () => ({ glue: "and", rules: [] }) }, // IFilterSet
  fields:  { default: () => [] },                            // IField[]
  options: { default: null },                                // IDataHash<AnyData[]> | (field)=>AnyData[]
  type:    { default: "list" },                              // "list" | "line" | "simple"
  init:    { default: null },                                // (api: IApi) => void
  onaddfilter / onremovefilter / onupdatefilter / onchange: { type: Function },
}
```

> 注意：`types/index.d.ts` 里写的是由 store 动作派生的 `onaddrule`/`onchange` 等事件名，但**运行时实际 props 是 `onaddfilter` / `onremovefilter` / `onupdatefilter` / `onchange`**（全小写）。二者不完全一致，故 POC 采用 `init` 回调订阅，最稳妥。

### 1.2 fields 形状（`IField`）

```ts
interface IField {
  id: string;                 // 稳定标识（后端 leaf subject）
  label: string;              // 显示名（中文）
  type: "number" | "text" | "date" | "tuple";
  predicate?: "month" | "year" | "yearMonth";
  format?: string | ((value: AnyData) => string);
}
```

- `type` **仅这 4 种**，没有 `boolean`/`list`/`polygon`；`tuple` 在序列化为查询串时不受支持（仅 UI）。
- `label` 会被 `sanitizeLabel` 去除 `[\s:,"'()#\-*><.=]`，中文不受影响。
- 有 `options[fieldId]` 时值是**复选列表**（输出 `includes`），无 options 时是**文本框**（输出 `value`）。

### 1.3 输入值 / 输出事件（`IFilterSet` / `IFilter`）

```ts
interface IFilterSet { glue?: "and" | "or"; rules?: (IFilter | IFilterSet)[]; }
interface IFilter { field: string; type?: TType; filter?: TFilterType;
                    includes?: AnyData[]; value?: AnyData; }
```

- 进出 JSON 一致：`:value="filterSet"` 进，`change` 事件出 `{ value: IFilterSet }`。
- 嵌套：`rules` 里既可放 `IFilter`（叶子）也可放 `IFilterSet`（分组，带自己的 `glue`）。
- 实测（POC `PocFilter.vue` 点 Add filter → 填 `person` → Apply）：

```json
{ "glue": "and", "rules": [
  { "field": "object_present", "filter": "contains", "value": "person",
    "type": "text", "includes": [] } ] }
```

- API 订阅方式（POC 采用）：

```ts
function handleInit(api: IApi) {
  api.on("change", (ev: { value: IFilterSet }) => { /* ev.value */ });
}
// <FilterBuilder :fields :options :value :init="handleInit" />
```

### 1.4 能力缺口 1：**不支持自定义 value 编辑组件**

- `IField` 无 `component`/`slot` 字段，`FilterBuilder`/`FilterEditor` 也无 value 编辑器插槽（源码里 `$slots.default` 仅用于菜单/包装组件内部，非字段值编辑）。
- 结论：**polygon / polyline / 自定义下拉不能在条件树叶子内联编辑**。
- 影响与对策：设计 §4.3 已规定「`roi`/`line`/`direction`/`count`/`window_sec` 等参数由**参数区（`SceneParamsForm` + `RoiCanvas`）唯一编辑**，条件树叶子的 value 表单不编辑它们」。因此 Task 6 的 `ConditionTree` 对这类叶子**不渲染值编辑器**（只保留 `subject`/`op`/`label` 等树内语义键），POC 结论与既有设计自洽，**不构成阻塞**。
- 若 Task 6 仍需在叶子内选 `labels`：用 `options`（复选列表 → `includes`）即可，无需自定义组件。

### 1.5 能力缺口 2：**不支持禁用单个 field（无 `disabled`）**

- `IField` 无 `disabled`；`IField` 之外也无 `disabledFields` 配置。源码里唯一的 `disabled` 是内部按钮 `disabled: !value.length`。
- 对策：`implemented:false` 的叶子**不进 `fields`**（Task 6 已如此规定），另以置灰列表展示"未实现"。

### 1.6 操作符（operators）**不可按 field 自定义**

- 操作符由 `type` 推导（`getFilters(type)`），不是按字段传入的。
- 库的 `filter` id 集合：`greater | less | greaterOrEqual | lessOrEqual | equal | notEqual | contains | notContains | beginsWith | notBeginsWith | endsWith | notEndsWith | between | notBetween`（`number/date/tuple` 支持比较；`text` 支持文本包含类）。
- 影响 Task 6：后端叶子的 `ops`（如 `["lt","gt","le","ge","eq"]`）**不能直接透传**，需做映射：

| 后端 op | 库 `filter` |
|---------|-------------|
| `gt` / `>` | `greater` |
| `ge` / `>=` | `greaterOrEqual` |
| `lt` / `<` | `less` |
| `le` / `<=` | `lessOrEqual` |
| `eq` / `==` | `equal` |
| `ne` / `!=` | `notEqual` |
| 无 op（存在/越线类） | 默认 `equal`（text 默认 `contains`） |

> 反解时按同一张表反向映射；库不支持"一元 NOT"，与设计 §4.6「UI 只产 AND/OR」一致。

### 1.7 主题必须包裹 `Willow`（否则是无样式裸 HTML）

- `all.css`（= `dist-full/index.css`，90 KB）里只有 `.wx-willow-theme` / `.wx-willow-dark-theme` 下的 231 个 `--wx-*` 变量定义，**没有 `:root` 默认值**。
- 若只 `import "@svar-ui/vue-filter/all.css"` 而不包裹 `<Willow>`（渲染 `<div class="wx-theme wx-willow-theme">`，见 `@svar-ui/vue-core`），所有 `var(--wx-*)` 失效 → 组件呈**裸 HTML**（无边框/圆角），POC 已实测到该现象并修复。
- 推荐写法（POC 采用，`fonts=false` 避免拉取外部字体、与 Element Plus 保持一致）：

```vue
<Willow :fonts="false">
  <FilterBuilder :fields :options :value :init="handleInit" />
</Willow>
```

- Task 6/8 视觉约束：在此之上再用 CSS 变量覆盖对齐 `--el-*` 主题色/圆角/字号（设计 §4.7）。

### 1.8 其它可用交互（POC 实测按钮）

- 工具栏：`Add filter`（新增条件行）。
- 条件行编辑器（点击行内控件打开）：字段下拉 → 操作符下拉 → 值控件（文框/复选列表），`Unselect all`、`Cancel`、`Apply`。
- 分组：通过 store 动作 `add-group` 实现（UI 为 Add group / 行内菜单），可产嵌套 `IFilterSet`（AND/OR 分组）。

## 二、vue-konva 4.0.1 + konva 10.5.0 真实 API

- 具名导出可直接局部注册（无需全局 `app.use`，POC 未改 `main.ts`）：
  `import { Stage, Layer, Line, Circle, ... } from "vue-konva"`（`dist/index.d.ts` → `export * from "./components.js"`）。
- 图形属性经 `config` 传入：`<Line :config="{ points, closed, stroke, strokeWidth, fill }" />`。
- 事件可写在 `config.onClick` 或直接 `@click`（模板编译为 `onClick` prop，`vue-konva` 会把它并进节点事件，见 `dist/vue-konva.js:40-46`）。
- 坐标：`e.target.getStage().getPointerPosition()` 返回容器内像素，自行除以 stage 宽高得归一化坐标（POC 即如此）。
- 事件名用 Konva 原生小写：`click` / `mousedown` / `dragend`。
- `Stage` 宽高放 `:config` 内（如 `:config="{ width, height }"`）以避免创建时闪动；容器尺寸用 `ResizeObserver` 自适应。
- POC 已验证：点击 4 次生成闭合多边形（`closed: true`）+ 顶点 `Circle`，并输出归一化点列；控制台无错误。

## 三、POC 文件与截图

- 组件（临时，Task 9 删除）：
  - `frontend/src/views/module_video/alarm/components/__poc__/PocRoi.vue`
  - `frontend/src/views/module_video/alarm/components/__poc__/PocFilter.vue`
  - `frontend/src/views/module_video/alarm/components/__poc__/PocPage.vue`
- 临时路由（Task 9 删除）：
  - `frontend/src/router/index.ts` → `/poc/sp5a`
  - `frontend/src/plugins/permission.ts` → 白名单临时放行 `/poc/sp5a`（POC 页面无需登录）

截图（`docs/superpowers/runbooks/sp5a-poc/`，Playwright 无头 Chromium，1440 宽）：

| 文件 | 内容 |
|------|------|
| `01-initial.png` | 初始页面（两块卡片） |
| `02-roi-drawn.png` | 画布点 4 点后的闭合多边形 + 归一化点列 JSON |
| `03-filter-rule.png` | 条件树 Apply 后的整页 |
| `04-filter-editor.png` | 条件行编辑态（字段/操作符/值 + Cancel/Apply + JSON 区） |
| `05-filter-applied.png` | Apply 后条件行折叠态 |

### 视觉核对（`vision-recognition` 技能，本地 Qwen3.6-27B）

- `02-roi-drawn.png`：识别确认——画布中出现**蓝色描边 + 半透明填充的闭合四边形**，四顶点有圆点；下方 JSON 为归一化坐标数组；条件树卡片含 `Add filter`。四项全部为「是」。
- `04-filter-editor.png`：识别确认——字段选择（中文「存在目标」）、操作符 `contains`、值输入框（`person`）三者齐备，`Cancel` / `Apply` 按钮可见，底部有 JSON 代码块。
- 主题一致性：`Willow` 主题生效后控件有边框/蓝色主按钮/焦点环，但**不精细**（方角、原生 checkbox、无 hover/圆角体系），视觉上与 Element Plus 存在可感知差异 → Task 6/8 需按设计 §4.7 用 `--el-*` 变量覆盖（POC 阶段可接受）。

## 四、闸门判定

- **PASS**：`@svar-ui/vue-filter` 满足「嵌套 AND/OR + JSON 进出 + 字段能力驱动」，`vue-konva` 满足「点击加点 + 闭合多边形 + 顶点 + 归一化导出」；均无运行时错误。
- 两处能力缺口（自定义 value 组件、field 禁用）**均有既有设计内的对策**（参数区唯一编辑 / 从 fields 中剔除），不触发回退。
- **不回退**：不采用 Syncfusion（商业授权），也不降级为手写实现。
- 交给 Task 6 的关键输入：`IField` 形状、`change` 事件契约、op→filter 映射表、`Willow` 包裹要求。

## 五、复现命令

```powershell
cd frontend
pnpm add @svar-ui/vue-filter vue-konva konva
pnpm run dev                       # http://localhost:5180/web/#/poc/sp5a
# 无头截图（Playwright CLI 或临时脚本，脚本不入库）
npx playwright screenshot --viewport-size=1440,900 "http://localhost:5180/web/#/poc/sp5a" ../docs/superpowers/runbooks/sp5a-poc/01-initial.png
```
