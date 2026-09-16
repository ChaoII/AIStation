# SP6-b 规则灰度 e2e + 视觉核对（Task 5）

- 日期：2026-09-15
- 计划：`docs/superpowers/plans/2026-09-15-sp6b-rule-rollout.md` Task 5
- 设计：`docs/superpowers/specs/2026-09-15-sp6b-rule-rollout-design.md` §3.4 / §3.5
- 页面：`frontend/src/views/module_video/alarm/index.vue` + `components/RuleEditor.vue`（菜单：视频监控 → 报警管理 → 告警规则）
- 用例：`frontend/e2e/sp6b-rule-rollout.spec.ts`

## 一、e2e（Playwright）

共 2 个用例（`pnpm run e2e -- sp6b-rule-rollout`，含 `auth.setup` 共 3 项）：

### 1. 规则灰度：比例 30 + 白名单 + 生效时段 保存与回填一致

1. 登录态（`e2e/auth.setup.ts`）→ `/#/video/alarm` → 「告警规则」页签 → 「新增」；
2. 填规则名 + 关联摄像机（相机作用域必填）；
3. 生效时间段：点「工作日 08-18」预设 → 断言 `7×24` 网格有 **50** 个激活格（周一至周五 × 08-17）；
4. 灰度比例：聚焦滑块按钮，方向键从默认 100 逐格递减到 **30**（断言右侧文案为 `30%`）；
5. 相机白名单：多选 1 台相机（断言 select 内出现该相机 tag，且无行内错误）；
6. **截图**（截图前把「灰度」区块滚到对话框顶部，并断言时段网格 / 比例 / 白名单三者 boundingBox 均落在视口内）；
7. 保存 → 断言 `POST /video/alarm/rule/create` 返回 **200**（并记录 id 供清理）；
8. 列表「灰度」列摘要：`30% · 白名单 1 台 · 周一至周五 08:00-18:00`；
9. 重新打开编辑 → 回填一致（滑块 `30%`、白名单同一相机、时段仍 50 个激活格）；
10. `finally` 按 id 清理本次规则。

### 2. 灰度交集守卫：同相机同时选入白/黑名单 → 提示冲突并阻止提交

1. 新增对话框：白名单与黑名单各选「第一项」（同一台相机，断言名称相同）；
2. 行内错误 `.rule-editor__field-error` 出现且含「冲突」；
3. 点「保存」→ 对话框**不关闭**，顶部 alert `.rule-editor__error` 含「冲突」（`RuleEditor.validate()` 直接 return false，不发请求）；
4. 「取消」关闭 → 按名称查列表断言**未落库**。

### 关键实现细节

- **滑块键盘操作**：Element Plus 滑块可聚焦并承载 `keydown` 的是 **`.el-slider__button-wrapper`**，内层 `.el-slider__button` 不可聚焦（首次实现聚焦内层导致 70 次 `ArrowLeft` 全部无效，值恒为 `100（全量）`）。鼠标点击滑轨只能近似定位，键盘路径可精确到整数。
- **列表定位用搜索**：规则名带时间戳，经「规则名称」搜索（`AlarmRuleQueryParam.name` 为 `("like", ...)` 语义，已确认生效）定位到第 1 页行，避免翻页。
- **限流隔离**：视频模块路由限流 5 次/10s，且计数键为 `(客户端 IP, 路由)`（`fastapi_limiter` 的 `default_identifier` 取 `X-Forwarded-For` 首段）。两个用例分别注入 `10.66.11.1` / `10.66.11.2`，与其它 spec 的 `127.0.0.1` 互不干扰；清理按 id 删除（不再二次查列表），单用例对同一路由的请求 < 5。

### 运行

```bash
# 前置：后端 8001（uv run main.py run --env=dev）、前端 5180（pnpm run dev）、PG/Redis 正常
cd frontend && pnpm run e2e -- sp6b-rule-rollout
```

结果：**PASS**（`3 passed`，含 `auth.setup`；主用例约 9.7s，交集守卫约 4.9s）。

## 二、截图与视觉核对

- 截图：`docs/superpowers/runbooks/sp6b-visual/rule-editor-rollout.png`
  （新增/编辑框，视口 1600×1000，「灰度」区块滚动到可视区顶部后整页截图）
- 工具：`vision-recognition` 技能（远端 Qwen3.6-27B，`--detail high`）

### 结论：**通过，与预期一致**

识别确认：

| 项 | 结果 |
|----|------|
| 「灰度」分区 | 存在（带下划线标题，位于「条件预览」下方） |
| 生效时间段 7×24 网格 | 仅周一~周五的 **08–17** 高亮（5×10=50 个蓝格），周六/周日整行未选中 → 窗口 `08:00-18:00` |
| 灰度比例 | 滑块滑钮约在 1/3 处，右侧文案 **`30%`** |
| 相机白名单 | 选中 **1 个 tag**（`E2E 摄像机 <时间戳>`，带 × 删除图标） |
| 相机黑名单 | 空，占位「黑名单相机强制跳过」 |
| 红色错误/冲突提示 | **无**（正确，本用例无冲突） |
| 视觉风格 | Element Plus 常规风格（蓝色主题滑块/开关、圆角下拉、tag、白底+蓝底按钮），与既有模块一致 |

## 三、复现命令

```bash
cd backend && uv run main.py run --env=dev
cd frontend && pnpm run dev
cd frontend && pnpm run e2e -- sp6b-rule-rollout
python <skills>/vision-recognition/scripts/recognize_image.py \
  ../docs/superpowers/runbooks/sp6b-visual/rule-editor-rollout.png \
  --prompt "灰度分区、时段高亮分布、比例文案、白名单 tag、是否有红色错误" --detail high
```

## 四、结论与遗留

- 灰度配置在前端**可配置、可保存、可回填**，列表摘要可读；白/黑名单交集在**前端即被拦截**（后端另有 400 兜底），不含静默默认行为。
- 缺省不配置灰度时提交 `rollout: {}`（`RuleEditor.normalizeRollout` 在「100% 且两名单为空」时回退为 `{}`），列表摘要函数对空配置返回空串 → 「灰度」列不显示内容，符合「缺省零行为变化」（该路径由实现与后端缺省 `{}` 保证，本 e2e 未单独断言）。

### 需注意（非阻塞）

1. 交集错误提示渲染在「相机黑名单」项下方（`.rule-editor__field-error`），同时在编辑器顶部 alert 重复一次；未接入 `el-form` 的 `prop/rule` 校验，属组件内自行校验，样式与 Element Plus 表单报错不完全一致（信息清晰，可接受）。
2. 视觉核对提到对话框上半部有「目标跟踪/未实现」等只读标签与「条件预览」`{}` —— 为既有场景参数区的正常渲染，与灰度无关。
3. `pnpm run lint` 不覆盖 `e2e/`（`@typescript-eslint/parser` 的 `parserOptions.project` 未包含该目录，`sp5a`/`sp6a` spec 同样如此），故新 spec 仅以 `type-check` 无新增错误 + 实际运行通过作为质量依据。
