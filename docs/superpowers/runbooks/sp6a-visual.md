# SP6-a 规则作用域与聚合叶子 e2e + 视觉核对（Task 6）

- 日期：2026-09-15
- 计划：`docs/superpowers/plans/2026-09-15-sp6a-rule-scope-group.md` Task 6
- 设计：`docs/superpowers/specs/2026-09-15-sp6a-rule-scope-group-design.md` §4
- 页面：`frontend/src/views/module_video/alarm/index.vue`（菜单：视频监控 → 报警管理 → 告警规则）
- 用例：`frontend/e2e/sp6a-rule-scope.spec.ts`

## 一、e2e（Playwright）

用例「规则作用域：组规则列表展示组名 + 相机作用域隐藏聚合叶子」覆盖：

1. 登录态（`e2e/auth.setup.ts`）→ `/#/video/alarm` → 「告警规则」页签；
2. 列表「作用域」列展示 `相机组：<组名>`；
3. 打开编辑框：作用域单选为「相机组」，`关联相机组` 下拉回填组名；
4. 相机组作用域下，字段候选含 `group_count`（组内目标总数）/ `group_coverage`（组内覆盖比例）；
5. 经「Add filter」配置 `group_count` 叶子 → 条件树出现该叶子 → 保存成功 → 列表仍显示组名；
6. 重新打开：叶子回填；
7. 切回「相机」作用域：`group_count`/`group_coverage` 从条件树与字段候选中**消失**（作用域过滤要求）；
8. `finally` 清理本次规则与相机组。

### 种子策略（为何规则也走 API）

相机组与「组规则」均经 API 创建（`POST /video/camera/group/create`、`POST /video/alarm/rule/create`），
规则以 `params={group_window_sec:10, group_count:2}` 预置。原因：

- 编译层（`scene/compile.py`）把 `params.group_window_sec → leaf.window_sec`、`params.group_count → leaf.value`
  注入 `group_*` 叶子；而当前**场景目录没有任何场景声明这两个参数键**，
  UI「新增」对话框无法产出它们（详见"已知问题"1）。
- 因此用例预置带参规则后，再由 UI 完成叶子的配置与保存；保存时编译层从 params 注入必填键，落库通过。

### 关键实现细节

- **字段下拉用键盘选择**：`openFieldPicker` 打开弹层做存在性断言；
  `selectFieldByLabel` 用 `ArrowDown` 逐项移动、以 `.wx-focus` 高亮确认命中「组内目标总数」后回车。
  原因见"已知问题"2（弹层被对话框遮挡，鼠标点击不可达）。
- **翻页定位规则**：规则列表按 id 升序、默认 10 条/页，`locateRuleRow` 从首页逐页翻找；
  先等首行出现再判断，避免分页未就绪时误判（后端 name 过滤形参未生效，见"已知问题"3）。
- 用例不触碰视频路由，请求稀疏，不会触发 5 次/10s 限流。

### 运行

```bash
# 前置：后端 8001（uv run main.py run --env=dev）、前端 5180（pnpm run dev）、PG/Redis 正常
cd frontend && pnpm run e2e -- sp6a-rule-scope
```

结果：**PASS**（`2 passed`，含 `auth.setup`；用例约 10s）。

## 二、截图与视觉核对

- 截图：`docs/superpowers/runbooks/sp6a-visual/rule-editor-group-scope.png`
  （编辑框，视口 1600×1000；截图前复位对话框滚动，使「作用域」与条件叶子同框）
- 工具：`vision-recognition` 技能（远端 Qwen3.6-27B）

### 结论：**通过，与预期一致**

识别确认：

| 项 | 结果 |
|----|------|
| 作用域单选 | **相机组**被选中（实心蓝色圆点） |
| 关联相机组 | `SP6A E2E 相机组 <时间戳>` |
| 触发条件 | `组内目标总数 contains 2`（即 `group_count` 叶子；JSON 预览 `{"op":"and","children":[{"subject":"group_count","label":2,"op":">="}]}`） |

## 三、复现命令

```bash
cd backend && uv run main.py run --env=dev
cd frontend && pnpm run dev
cd frontend && pnpm run e2e -- sp6a-rule-scope
python <skills>/vision-recognition/scripts/recognize_image.py \
  ../docs/superpowers/runbooks/sp6a-visual/rule-editor-group-scope.png --prompt "简述作用域选中项与触发条件行"
```

## 四、已知问题（本次 e2e 暴露，未在源码修复）

1. **组叶子无法在「新增」对话框完成参数配置**：`group_count` 的 `window_sec`/`value` 依赖场景参数
   `group_window_sec`/`group_count` 注入，但场景目录未声明这两个键，`SceneParamsForm` 也不渲染未知键；
   纯 UI 新增组规则会在编译期报 `叶子 group_count 缺少必填键 window_sec`（HTTP 400）。
   本用例以 API 预置 params 规避，此属 Task 4/5 集成的真实缺口。
2. **条件树字段下拉被对话框遮挡**：`@svar-ui/vue-filter` 弹层 `z-index:1001` 低于 `el-dialog`，
   且末项（`group_count`/`group_coverage`）超出弹层可视区，鼠标点击会被对话框内容命中拦截，
   只能键盘导航选择。建议后续为其弹层提升 z-index 或调整弹层定位。
3. **规则列表 `name` 过滤形参未生效**：`AlarmRuleQueryParam` 只把 `name` 存为普通属性（非 `("like", ...)`
   条件元组），列表接口 `name` 查询恒返回全量；e2e 改为翻页定位规则行。
