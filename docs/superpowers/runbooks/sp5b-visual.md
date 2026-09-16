# SP5-b 边缘事件流 e2e + 视觉核对（Task 7）

- 日期：2026-09-15
- 计划：`docs/superpowers/plans/2026-09-15-sp5b-edge-event.md` Task 7
- 设计：`docs/superpowers/specs/2026-09-15-sp5b-edge-event-design.md` §4
- 页面：`frontend/src/views/module_video/event_stream/index.vue`（路由 `/#/video/event-stream`，菜单「视频监控 → 边缘事件」）

## 一、e2e（Playwright）

- 用例：`frontend/e2e/sp5b-event-stream.spec.ts` → 「边缘事件流：历史详情展示检测目标与命中叶子高亮」
- 覆盖链路（复用既有 `e2e/auth.setup.ts` 登录态与 hash 路由约定）：

  登录 → `/#/video/event-stream` → 切「历史」视图 → 列表首行出现种子事件（含 `person` + 「命中」）
  → 点击行打开详情抽屉 → 断言检测目标（`person` / 置信度 `0.930`）
  → 断言「命中叶子」高亮标签（`and/0` + `person conf=0.93`）→ 截图。

### 种子事件的做法（关键）

e2e 不直接改库，而是走**真实落库链路**，用例自包含、可重复：

1. 读取登录态 `access_token`（`localStorage`，值为 JSON 字符串）作为 `Authorization`；
2. 建一条**条件树**规则：`{"op":"and","children":[{"subject":"object_present","label":"person"}]}`
   （含条件树才能产生非空 `matched_leaves`）；
3. `POST /video/algorithm/detection/callback`（内部回调，`Authorization: Bearer infer_callback_shared_secret`）
   落库一条 `person conf=0.93` 的边缘事件，命中规则 → 落库 `matched=True` + 命中叶子；
4. 用例 `finally` 中清理：`DELETE /video/alarm/record/delete`（物理删）+ `DELETE /video/alarm/rule/delete`
   （项目 `CRUDBase.delete()` 对含 `ModelMixin` 的模型为**软删**，行保留但 `is_deleted=True`，UI 不可见）。

隔离与限流：

- 每次运行的 `algorithm_type` 为唯一值 `SP5B_E2E_DET_ZONE_<ts>`，避免历史遗留规则被
  `pick_alarm_rule` 选中导致叶子为空；规则名同样带时间戳。
- 视频路由限流 5 次/10s 且**按路由分桶**（`fastapi_limiter` key 含 route index），本用例
  各路由至多 1-2 次调用，不会触发 429。

### 运行

```bash
# 前置：后端 8001 + 前端 5180 已启动（Redis/PG 就绪）
# 首次需重启一次后端，确保「边缘事件」菜单被幂等启动钩子注册（本次已验证菜单已存在，未重启）
cd frontend && pnpm run e2e -- sp5b-event-stream
```

- 结果：**PASS**（`2 passed`，含 `auth.setup`；用例 3.7s）。

## 二、截图与视觉核对

- 截图：`docs/superpowers/runbooks/sp5b-visual/event-stream-detail.png`
  （历史视图 + 详情抽屉打开态；视口 1600×1000，含左侧菜单/面包屑/筛选区，便于风格对比）
- 核对工具：`vision-recognition` 技能（本地 Qwen3.6-27B，`recognize_image.py --detail high`）

### 结论：**通过（与既有模块风格一致）**

识别确认：

| 项 | 结果 |
|----|------|
| 布局风格 | 左侧深色导航 + 中间内容区 + 右侧白色 `el-drawer`，Element Plus 蓝白主题，与既有模块一致 |
| 抽屉字段 | 事件时间 / 相机 / 场景 / 任务ID / 边缘设备 / 延迟 / 命中 / 命中规则 / 快照引用 |
| **命中叶子** | 存在标题，下方绿色高亮标签文字为 **`and/0 person conf=0.93`** |
| 检测目标 | 标题「检测目标 (1)」，列为 标签/置信度/track_id/属性/文本；`person`、`0.930`、`1` |
| 列表 | 表头 时间/相机/场景，`历史` 按钮为选中态 |

无控件错位/裁切，无与框架割裂的自定义配色。

## 三、复现命令

```bash
# 后端
cd backend && uv run main.py run --env=dev
# 前端
cd frontend && pnpm run dev
# e2e（自动截图到 docs/superpowers/runbooks/sp5b-visual/）
cd frontend && pnpm run e2e -- sp5b-event-stream
# 视觉核对
python <skills>/vision-recognition/scripts/recognize_image.py \
  ../docs/superpowers/runbooks/sp5b-visual/event-stream-detail.png --prompt "…"
```

## 四、已知事项（不阻塞）

1. 事件行无删除接口，e2e 每次运行会**新增一条**边缘事件（设计上只有 30 天 TTL 清理）；
   规则/告警已按任务要求清理。
2. e2e 使用唯一 `algorithm_type`，列表「场景」列会显示该原始码而非场景中文名——为隔离
   遗留规则的有意取舍，不影响本用例断言。
3. 抽屉中「场景」显示为场景码（`getSceneCatalog` 未收录该 e2e 专属码）；真实场景码显示中文名。
