# SP5-a 规则编辑器设计（场景参数 + 条件树 + ROI 画布）

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md` §8（SP5 前端）
- 承接欠账：SP4-b 明确「目录 `param_schema`/`default_rule` 驱动任务/规则创建」留待 SP5
- 范围：AIStation 前后端（后端接口/编译层 + 前端编辑器组件）

## 1. 背景与现状

`AlarmRule` 已有条件树数据模型与云端求值器，但**没有任何条件编辑 UI**：

| 现状 | 证据 |
|------|------|
| 规则对话框只有 name/camera/alarm_type/severity/sensitivity/interval_seconds/status/description，**无 `conditions`** | `frontend/src/views/module_video/alarm/index.vue`（`ruleForm`） |
| `conditions` 为空时求值器返回匹配（`if not conditions: return True`） | `backend/app/api/v1/module_video/inference/service.py:_match_conditions` |
| 场景目录已提供 `param_schema`/`default_rule`，但**无人消费** | `backend/app/api/v1/module_video/scene/catalog.py` |
| 参数键与求值器键存在口径不符（如 `direction` vs `dir`） | SP4-b 账本记录 |

因此规则只能"建了但命中一切"，场景参数无法配置。

## 2. 目标 / 非目标

**目标**

1. 规则编辑器：场景选择 → 场景参数表单 → 条件树编辑 → 保存为「可评估」的 `conditions` + 原值 `params`。
2. 后端提供**单一事实源**的叶子能力描述与**编译/校验**层，杜绝前后端口径漂移。
3. ROI/绊线用画布绘制（第三方）。
4. 顺带修复 `direction`→`dir` 等参数口径不一致。

**非目标**

- SP5-b 边缘事件/规则命中可视化；SP5-c 告警快照/叠加预览。
- SP6 三项（跨相机组合、灰度、模型热更新）。
- 新增求值器叶子（未实现叶子仅置灰展示）。

## 3. 选型（第三方组件，用户强制要求）

### 3.1 条件树编辑器

| 候选 | 许可 | 最近发布 | 结论 |
|------|------|----------|------|
| **`@svar-ui/vue-filter`（FilterBuilder）** | MIT | 2026-09 | **采用**：Vue 3 原生、嵌套 AND/OR、JSON 进出、TS 完整、依赖均为 `@svar-ui/*` |
| `@syncfusion/ej2-vue-querybuilder` | 商业许可 | 2026-09 | 落选：需商业授权 |
| `vue3-advanced-query-builder` | MIT | 2023-09 | 落选：停更约 3 年，违反"维护活跃"门槛，且把 `vue` 打进 dependencies |
| `@form-create/element-ui` | MIT | 2024-12 | 落选：表单构造器而非条件构造器，嵌套条件仍需自定义 |
| `@awesome-query-builder/vue`、`@react-awesome-query-builder/vue` | — | — | 不可用：npm 404（Vue 包不存在） |

### 3.2 画布（ROI/绊线）

| 候选 | 许可 | 最近发布 | 依赖 | 结论 |
|------|------|----------|------|------|
| **`vue-konva` 4.x + `konva` 10.x** | MIT | 2026-09 | 零 | **采用**：Vue 3 声明式绑定，Konva 成熟场景图 |
| `fabric` 7.x | MIT | 2026-05 | 零 | 落选：命令式，Vue 集成需自建桥接，工作量更大 |
| `vue-drawing-canvas` | MIT | ~2023 | 1 | 落选：面向签名板，且停更 |

> 说明：Konva 提供画布与图形原语（Stage/Layer/Line/Circle + 事件），多边形拾取与顶点拖拽是本项目业务逻辑；**不使用原生 `<canvas>` + 手写鼠标绘制**（那才是被禁止的"手写编辑器"）。

### 3.3 集成 POC 结论（2026-09-15，已通过）

落地版本：`@svar-ui/vue-filter` 2.6.1、`vue-konva` 4.0.1、`konva` 10.5.0（无控制台报错）。
产出：`docs/superpowers/runbooks/sp5a-poc.md` + `docs/superpowers/runbooks/sp5a-poc/`（5 张截图）。
结论：两个组件均可用；`FilterBuilder` 的 fields 形态与上述限制已写入 §4.6，未触发回退选型。

## 4. 设计

### 4.1 数据模型

`AlarmRuleModel` 新增：

```python
params: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}", comment="场景参数原值")
```

- `params`：场景参数原值（`roi`/`line`/`direction`/`count`/`window_sec`/`dwell_sec`/`gap_sec`/`confidence_threshold`/`labels`/`attributes`/`pattern` 等），供 UI 回填。
- `conditions`：**保存后为展开完成、可直接求值**的条件树（求值器只认具体数值/点列，禁止符号引用）。
- `algorithm_type` 即场景码（与 `catalog.SCENES` 的 `code` 一致）。
- 新增 Alembic 迁移；`params` 默认 `{}`，既有规则不受影响。

### 4.2 叶子能力注册表（单一事实源）

新增 `backend/app/api/v1/module_video/scene/leaves.py`：

```python
LEAF_CAPABILITIES: dict[str, dict] = {
    "object_present": {
        "label": "存在目标", "implemented": True,
        "params": [{"key": "label", "type": "str"}, {"key": "labels", "type": "list"},
                   {"key": "region", "type": "polygon"}, {"key": "min_confidence", "type": "float"}],
        "ops": [],
    },
    "zone_enter":   {"label": "进入区域", "implemented": True,
                     "params": [{"key": "label", "type": "str"}, {"key": "region", "type": "polygon"}], "ops": []},
    "count":        {"label": "目标计数", "implemented": True,
                     "params": [{"key": "label", "type": "str"}, {"key": "region", "type": "polygon"},
                                {"key": "value", "type": "int"}],
                     "ops": [">=", ">", "<=", "<", "=="]},
    "attribute":    {"label": "属性判定", "implemented": True,
                     "params": [{"key": "field", "type": "str"}, {"key": "value", "type": "float"}],
                     "ops": ["lt", "gt", "le", "ge", "eq"]},
    "text_match":   {"label": "文本正则", "implemented": True,
                     "params": [{"key": "regex", "type": "str"}], "ops": []},
    "ocr_label":    {"label": "文本包含", "implemented": True,
                     "params": [{"key": "contains", "type": "str"}], "ops": []},
    "dwell":        {"label": "停留时长", "implemented": True,
                     "params": [{"key": "label", "type": "str"}, {"key": "region", "type": "polygon"},
                                {"key": "min_sec", "type": "int"}, {"key": "track_id", "type": "int"}], "ops": []},
    "count_window": {"label": "滑窗计数", "implemented": True,
                     "params": [{"key": "label", "type": "str"}, {"key": "region", "type": "polygon"},
                                {"key": "window_sec", "type": "int"}, {"key": "value", "type": "int"}],
                     "ops": [">=", ">", "<=", "<", "=="]},
    "absence":      {"label": "持续无目标", "implemented": True,
                     "params": [{"key": "label", "type": "str"}, {"key": "region", "type": "polygon"},
                                {"key": "gap_sec", "type": "int"}], "ops": []},
    "line_cross":   {"label": "越线/绊线", "implemented": True,
                     "params": [{"key": "line", "type": "polyline"}, {"key": "dir", "type": "str"},
                                {"key": "label", "type": "str"}, {"key": "region", "type": "polygon"}], "ops": []},
}
```

未实现叶子（`face_match`/`stranger`/`liveness`/`keypoint_geometry`/`region_ratio`/`distance`/`structure`/`code_match`/`reid_match`/`static`/`track`/`prompt_segment`/`classification`）以 `implemented: False` 列出（仅置灰展示，不可选）。

**关键不变量**：该注册表必须与 `service.py` 求值器支持集一致——由单测对拍（见 §5）。

### 4.3 参数 → 叶子键 绑定表

新增 `backend/app/api/v1/module_video/scene/compile.py`：

```python
PARAM_TO_LEAF = {
    "roi":                  ("region",        None),      # None = 注入所有「声明了 region 参数」的叶子
    "line":                 ("line",          "line_cross"),
    "direction":            ("dir",           "line_cross"),   # 修复 SP4-b 的 direction/dir 口径
    "labels":               ("labels",        {"object_present", "count", "count_window", "dwell", "absence", "line_cross"}),
    "confidence_threshold": ("min_confidence", "object_present"),
    "count":                ("value",         {"count", "count_window"}),
    "window_sec":           ("window_sec",    "count_window"),
    "dwell_sec":            ("min_sec",       "dwell"),
    "min_sec":              ("min_sec",       "dwell"),
    "gap_sec":              ("gap_sec",       "absence"),
    "pattern":              ("regex",         "text_match"),
    # 仅作 UI 选项、不注入叶子的参数：attributes / cls_threshold / topk / plate_pattern / min_value / max_value
}
```

**注入语义（消除歧义）**：被 `PARAM_TO_LEAF` 接管的键，**参数值总是覆盖叶子中的同名键**（覆盖 `default_rule` 预填值，如 `LINE_CROSS` 的 `dir:"A2B"`、`OVERCROWD` 的 `value:5`）。原因是这些键由参数区唯编辑入口，条件树的叶子表单**不编辑**它们——叶子只负责 `subject`/`label`/`labels`/`op`/`field` 等「树内语义键」。参数缺省时保留 `default_rule` 的原值。

### 4.4 编译与校验

`compile_rule(scene_type, params, conditions) -> dict`：

1. **校验**：`conditions` 必须是 `and/or/not` 或叶子节点；叶子 `subject` ∈ `LEAF_CAPABILITIES` 且 `implemented`；必填键存在；`op` ∈ 该叶子 `ops`；数值键为数值；`region`/`line` 为合法点列（`[[x,y],...]`）。任一失败 → 抛业务异常（HTTP 400，中文错误信息）。
2. **注入**：按 `PARAM_TO_LEAF` 把 `params` 展开进对应叶子；被接管的键**总是覆盖**叶子同名键（见 §4.3 注入语义），参数缺省时保留叶子原值。
3. 返回展开后的条件树；`params` 原值原样持久化。

`scene_type` 与 `catalog.get_scene()` 不符时告警但不阻断（允许自定义规则类型）。

### 4.5 后端接口

| 接口 | 变更 |
|------|------|
| `GET /video/scene/rule-capabilities` | **新增**：返回 `{"logic": ["and","or","not"], "leaves": [...LEAF_CAPABILITIES...]}` |
| `GET /video/scene/catalog` / `.../{code}` | 不变（已含 `param_schema`/`default_rule`） |
| `POST /video/alarm/rule/create`、`PUT /video/alarm/rule/update/{id}` | 接受 `params`；写入前调用 `compile_rule` 校验并展开 `conditions` |
| `GET /video/alarm/rule/list` / `detail` | 返回 `params` + `conditions` |

权限沿用既有 `video:alarm:rule:*`；`rule-capabilities` 用只读权限（复用 catalog 接口权限）。

### 4.6 前端

新增组件（`frontend/src/views/module_video/alarm/components/`）：

- `RuleEditor.vue`：编排「场景选择 → 参数区 → 条件树 → 校验提示」。
- `SceneParamsForm.vue`：按 `param_schema` 的 `type` 分派：
  `polygon`/`polyline`/`point` → `RoiCanvas`；`int`/`float` → `el-input-number`；`str` → `el-input`；`list` → `el-select multiple`（allow-create）；`bool` → `el-switch`。
- `RoiCanvas.vue`：`vue-konva` 的 `v-stage/v-layer/v-line/v-circle`；支持加点、拖顶点、双击删点、清空；`v-model` 为归一化 `[[x,y],...]`；底图可传快照 URL。
- `ConditionTree.vue`：封装 `@svar-ui/vue-filter` 的 `FilterBuilder`；把 `rule-capabilities` 编译成 `fields`。
  - **POC 实测限制（2026-09-15）**：① 不支持自定义 value 编辑组件（无插槽）；② 不支持按字段禁用/限制算子（算子由 field `type` 推导）；③ `all.css` 必须配 `<Willow :fonts="false">` 包裹，否则无样式。
  - **适配**：每个已实现叶子一个 field，`type` 按叶子取值语义选（多为 `text`=标签、计数类为 `number`）；field 取值即该叶子的**主标签/主数值**，叶子其余参数（region/line/阈值/窗口）**全部由参数区唯一编辑**（与 §4.3 注入语义一致）。库算子经 `OP_MAP` 映射到本项目算子（如 `equals→==`、`more→>`、`less→<`）。
  - `implemented:false` 的叶子**不进 `fields`**（库不支持置灰），改在编辑器下方渲染"暂不支持的叶子"置灰标签区。
  - 库只支持 AND/OR → 条件树 UI 不产出一元 `not`；后端仍兼容 `not`（历史数据只读展示）。
- `src/api/module_video/scene.ts`：`getSceneCatalog`、`getSceneDetail`、`getRuleCapabilities`。
- 集成：`alarm/index.vue` 规则对话框内嵌 `RuleEditor`，保存时提交 `{scene_type, params, conditions}`。

### 4.7 视觉约束

- 复用 Element Plus 组件与 `--el-*` 变量；`FilterBuilder` 用 CSS 变量覆盖对齐主题色/圆角/字号，不自造配色外壳。
- 完成后用无头浏览器截图 + `vision-recognition` 技能核对与既有（`module_system/param` 风格）一致。

## 5. 测试与验收

**后端**
- `tests/test_rule_compile.py`：编译注入各参数（roi/line/direction/count/window_sec/dwell_sec/gap_sec/labels/pattern）、不覆盖叶子显式值、非法条件（未知 subject/缺必填键/非法 op/非数值/非法点列）报错、`params` 为空时条件原样返回。
- `tests/test_rule_capabilities.py`：**对拍测试**——`LEAF_CAPABILITIES` 中 `implemented=True` 的叶子，必须与 `service.py` 实际可求值集一致（正向：每个已实现叶子的必填键被求值器识别；反向：求值器支持的 subject 都在注册表中）。
- `tests/test_alarm_rule_params.py`：`params` 持久化与读取；create/update 走编译校验（非法 → 400）。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**前端**
- `pnpm run type-check`、`pnpm run lint`。
- Playwright e2e（`e2e/`）：登录 → 规则管理 → 新建规则 → 选场景（如 `DET_ZONE`）→ 画 ROI → 配条件 → 保存 → 重开回填一致。
- 无头截图 + `vision-recognition` 视觉核对。

**POC 前置（Task 1）**
- 最小样例分别跑通 `RoiCanvas`（vue-konva 画多边形并导出归一化点列）与 `ConditionTree`（vue-filter 渲染字段并输出 JSON），各自截图。**POC 不通过则回到选型环节**（不擅自改用手写实现）。

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `@svar-ui/vue-filter` 生态新（star 少） | Task 1 先做 POC + 截图；不通过则回退选型（Syncfusion 或再议），不降级为手写 |
| 第三方字段配置无法表达异构叶子参数 | 每个叶子一个 field，参数编辑器按 `type` 分派；POC 验证自定义 value 组件可行性 |
| 前后端能力漂移 | 能力注册表由后端下发 + **对拍单测**锁定 |
| 归一化坐标与画布尺寸不一致 | `RoiCanvas` 内部统一归一化（除以 stage 尺寸），进出均为 0~1 |
| `params` 与 `conditions` 不一致 | `params` 为原值、`conditions` 由后端编译产物；UI 只读 `conditions`，编辑以 `params` 为准 |
| 迁移破坏既有规则 | `params` 默认 `{}`；`conditions` 不重算（既有规则保持原样） |

## 7. 兼容性

- 既有规则（无 `params`、`conditions` 为空）行为不变（空条件仍然匹配一切）。
- 求值器不改语义；本次只新增编译层与接口。
- `direction`→`dir` 的映射在编译层完成，求值器仍读 `dir`。
