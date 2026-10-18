# 定时任务统一（触发类型 / 口径 / 调度 / UI）设计规格

日期：2026-10-18
状态：待评审

## 1. 背景

平台里"定时"这件事被四块独立实现各写了一遍：**触发类型不同、cron 口径不同、调度机制不同、
UI 也各是各的**。用户视角的后果是"同一件事在四个页面填法不同、同一个表达式含义还不同"。

| 入口 | 现有触发类型 | cron 口径 | 调度机制 |
|---|---|---|---|
| 系统定时任务节点（`task_node.trigger_args`） | `now` / `cron` / `interval` / `date` | 6~7 段 Quartz | 中心 APScheduler ✅ |
| AI 工作台定时任务（`ai_workspace_cron.cron`） | 仅 `cron` | 5 段 | 自建 `while True` 轮询（每分钟） |
| AI 工作流定时调度（`ai_workflow_schedules.cron`） | 仅 `cron` | 5 段 | 自建循环 + 自算 `next_run` |
| 训练调度（`train_schedules.cron_expr`） | 仅 `cron` | 5 段（`croniter`） | 自建循环 + `croniter` |
| `app/utils/time_util.py::TimeUtil.validate_cron_expression` | — | 6 段 | **无人调用（死代码）** |

中心调度器 `app/core/ap_scheduler.py` **已存在且完整**（`AsyncIOScheduler` + 持久化
`SQLAlchemyJobStore` + 执行日志事件监听 + `sync_jobs_to_db()` + 暂停/恢复，启动由
`init_app` 调 `SchedulerUtil.init_scheduler()`），但只有"系统定时任务"用了它。

## 2. 实测缺陷清单（全部实测，非推测）

### D1（严重）同一表达式在不同模块跑在不同星期几
基准 2026-10-18（周日）：

| 表达式 | APScheduler（AI 侧 / 系统定时任务） | croniter（训练调度） | 判定 |
|---|---|---|---|
| `0 9 * * 1` | 2026-10-20 **Tue** | 2026-10-19 **Mon** | 不一致 |
| `0 9 * * 5` | 2026-10-24 **Sat** | 2026-10-23 **Fri** | 不一致 |
| `0 9 * * 0` | 2026-10-19 **Mon** | 2026-10-18 **Sun** | 不一致 |

根因：APScheduler 数字周字段是 `0=周一`，标准 crontab 是 `0/7=周日`，`CronUtil` 又按 Quartz
（`1=周日`）放行 → 三套口径互不相同。

### D2（严重）校验器放行、调度器报错（"存得下、到点才炸"）
`0 0 9 L * *`、`0 0 9 15W * *`、`0 0 9 * * 1#2`、`0 0 9 * * 7`、`0 0 9 ? * *`：`CronUtil` 全部判
**合法**，而 `CronTrigger(...)` 全部抛 `ValueError`。

### D3（中）7 段"年"字段是时间炸弹
`CronUtil.validate_year` 只接受 `[当前年, 当前年+8]`：今天 `... 2030` 合法、`... 2036` 已非法
→ 存量 7 段配置未来某年会突然无法保存。

### D4（中）秒级规则自相矛盾，且秒级调度在 web 多副本下不利
`0 * * * * *`（每分钟第 0 秒，无意义）合法；`*/5 * * * * *`（每 5 秒，常用）**非法**。
且 APScheduler 是进程内调度，多副本会重复触发。

### D5（中）"下次运行时间"显示被带偏
`0 9 * * 1-5`（用户理解：工作日 9 点）实际下次触发为 **周二 09:00**，与训练调度（周一）也不一致。

### D6（轻）重复实现 / 死代码
`app/utils/time_util.py::TimeUtil.validate_cron_expression` 无任何调用方。

## 3. 目标 / 非目标 / 分期

### 目标
1. **一种触发模型**：全平台统一 `trigger ∈ {cron, interval, date, now}` + 结构化参数
   （四个入口都支持四种，见 §5）。
2. **一种 cron 口径**：唯一 5 段标准 crontab `分 时 日 月 周`；周字段 `0/7=周日`，也接受 `mon…sun`。
3. **一处实现**：规范化/校验/预览/触发器构造收敛到一个工具（§4.2、§5.2）。
4. **一套调度**：凡定时任务一律注册到中心 APScheduler，删除自建轮询（§7）。
5. **一套 UI**：一个 `TriggerEditor`（类型切换 + 参数编辑 + 人话预览 + 下次运行时间），四入口共用（§6）。
6. 修掉 D1~D6。

### 分期
- **阶段 A｜触发与 cron 口径统一**：§4、§5（后端契约与统一层）
- **阶段 B｜调度入口统一**：§7（并入中心调度器、删自建轮询）
- **阶段 C｜统一 UI**：§6（`TriggerEditor` + 四入口替换 + 列表展示）

> 实施计划按阶段拆分（A → B → C），每阶段独立验收；A 落地即可消除"同一表达式三种含义"。

### 非目标
- 不改状态/队列轮询（训练任务状态、评估/预测队列、视频推理/录制、TTL 清理、连接池看门狗）——
  它们不是定时任务。
- 不引入分布式调度；多副本重复触发用开关规避（§7.3.5）。
- 不支持 Quartz 专有语法（`?`/`L`/`W`/`#`/7 段年字段）：写入明确报错，不静默转换。

## 4. cron 口径统一（阶段 A）

### 4.1 表达式格式
- 唯一合法形式：**5 段** `分 时 日 月 周`
- 取值：分 `0-59`、时 `0-23`、日 `1-31`、月 `1-12`、周 `0-7` 或 `mon…sun`；
  支持 `*`、`a-b`、`a,b,c`、`*/n`、`a-b/n`
- **周字段映射表**（规范化后交给调度器，绕开 APScheduler 的 `0=周一`，修 D1）：

  | 输入（标准 crontab） | 规范化输出 | 含义 |
  |---|---|---|
  | `0`、`7`、`sun` | `sun` | 周日 |
  | `1`、`mon` | `mon` | 周一 |
  | `2`…`6`、`tue`…`sat` | `tue`…`sat` | 周二…周六 |
  | `1-5` | `mon-fri` | 周一到周五 |
  | `*` | `*` | 每天 |

- `?` 仅在**读旧数据/迁移**时容错（→ `*`）；写入接口一律拒绝
- 周字段**不支持 `/` 步长**（如 `*/2`、`mon/2`）：APScheduler 的 day_of_week 步长语义不明确，
  写入时明确报错，而不是猜一个含义

### 4.2 统一层 API（`app/utils/trigger_util.py`，由 `cron_util.py` 演进而来）
| 方法 | 作用 |
|---|---|
| `TriggerUtil.normalize(trigger, args) -> (trigger, args)` | 按类型规范化（cron 走 §4.1 映射；interval 补齐缺省字段；date 归一为 `YYYY-MM-DD HH:mm:ss`） |
| `TriggerUtil.validate(trigger, args) -> (bool, str)` | 校验并返回**可读原因**（用于接口 400 与前端提示） |
| `TriggerUtil.describe(trigger, args) -> str` | 人话描述（如"每周一 09:00"、"每 2 小时 30 分"、"2026-10-20 09:00 执行一次"、"保存后立即执行"） |
| `TriggerUtil.to_trigger(trigger, args) -> BaseTrigger` | 构造 APScheduler 触发器（Cron/Interval/Date） |
| `TriggerUtil.next_run(trigger, args, base=None) -> datetime \| None` | 统一的"下次运行时间"，列表与预览共用 |

约束：`normalize`/`validate`/`to_trigger` **同源**（校验通过 ⇒ 一定能构造触发器），用参数化测试锁死（含 D2 的五个反例）。

### 4.3 调用方改造
| 位置 | 改法 |
|---|---|
| `app/core/ap_scheduler.py::add_cron_job` | 改走 `TriggerUtil.to_trigger`；删就地 `?`→`*` 与 `year` |
| `app/core/ap_scheduler.py::add_interval_job` | 参数契约由「秒 分 时 天 周」字符串 → 结构化 JSON（§5.1） |
| `module_ai/workspace/service.py` | 写入时 normalize；匹配/下次时间改走 `TriggerUtil`（替换自算） |
| `module_ai/workflow/service.py` | 同上（替换 3 处 `from_crontab`） |
| `module_train/schedule_service.py` | 写入时 normalize；匹配改用统一 `to_trigger`（不再直接用 `croniter` 判定） |
| `module_task/cronjob/node/service.py` | 校验改走 `TriggerUtil.validate`，错误信息原样回传 |
| `app/utils/time_util.py` | 删除重复校验器（D6） |

### 4.4 数据迁移（手写 Alembic，本项目禁用 autogenerate）
- 四张表统一到 `trigger` + `trigger_args` 两列（**结构化**）：
  - `ai_workspace_cron`：新增 `trigger`（默认 `cron`）/`trigger_args`；把 `cron` 值搬过去
  - `ai_workflow_schedules`：同上
  - `train_schedules`：`cron_expr` → `trigger='cron'` + `trigger_args`
  - `task_node`：`trigger` 已有；`trigger_args` 由字符串规范化为新契约（cron 5 段 / interval JSON / date ISO）
- 规则（**不做静默语义改写**）：5 段原样规范化；`?`→`*`；6 段且秒位为 `0` → 去首段；
  6 段秒位非 0、7 段带年 → **跳过并写迁移日志**，人工确认
- 当前 dev 库仅 1 条（`ai_workspace_cron.cron = "0 9 * * *"`），迁移风险≈0

## 5. 触发类型统一（阶段 A）

### 5.1 统一契约
| 类型 | `trigger` | `trigger_args` | 语义 | APScheduler 触发器 |
|---|---|---|---|---|
| 定时 | `cron` | `"0 9 * * 1"`（5 段字符串） | 按日历规则重复 | `CronTrigger` |
| 间隔 | `interval` | `{"weeks":0,"days":0,"hours":2,"minutes":30,"seconds":0}` | 每隔固定时长重复 | `IntervalTrigger` |
| 单次 | `date` | `"2026-10-20 09:00:00"` | 到点执行一次 | `DateTrigger` |
| 立即 | `now` | `null` | 保存后立即执行一次（注册 `DateTrigger(now+2s)` 的一次性作业，确保接口先返回；执行完置"已完成"） | `DateTrigger` |

- 四列约定：`trigger` 字符串 + `trigger_args` **JSON**（TEXT 列存 JSON，向后兼容旧字符串）
- 前端只提交这两个字段；后端**只信统一层**（不再各自解析）

### 5.2 各入口支持矩阵（统一后）
| 入口 | cron | interval | date | now |
|---|---|---|---|---|
| 系统定时任务节点 | ✅ | ✅ | ✅ | ✅ |
| AI 工作台定时任务 | ✅ | ✅ | ✅ | ✅ |
| AI 工作流定时调度 | ✅ | ✅ | ✅ | ✅ |
| 训练调度 | ✅ | ✅ | ✅ | ✅ |

（AI 侧三张表新增 `trigger`/`trigger_args` 列，见 §4.4）

## 6. 统一 UI（阶段 C）

### 6.1 一个组件，四处复用
新增 `frontend/src/components/TriggerEditor/index.vue`（对外 `v-model:trigger` / `v-model:triggerArgs` + `@error`），
内部结构：

```
触发方式  ( ) 定时   ( ) 间隔   ( ) 单次   ( ) 立即      ← el-radio-group（按钮样式）
┌─ 定时：@vue-js-cron/element-plus 选择器（点开下拉选择）+ 可手输
├─ 间隔：每 [ 0 ] 天 [ 2 ] 小时 [ 30 ] 分 [ 0 ] 秒        ← el-input-number
├─ 单次：[ 2026-10-20 09:00:00 ]                          ← el-date-picker(datetime)
└─ 立即：说明"保存后立即执行一次"
────────────────────────────────────────────
预览：每周一 09:00 执行          下次运行：2026-10-20 09:00:00
```

- **人话预览** 与 **下次运行时间** 都来自后端统一接口（`TriggerUtil.describe/next_run`），
  前端不自算（避免又出现"两套口径"）
- 非法输入：组件内即时提示（`@error`）+ 保存前拦截；后端 400 返回可读原因
- 列表展示：新增"触发方式"标签（定时/间隔/单次/立即）+ 人话描述 + 下次运行时间

### 6.2 替换点
| 使用处 | 现状 | 改后 |
|---|---|---|
| `module_ai/workspace/index.vue`「新建定时任务」 | 裸 `el-input` 填 cron | `TriggerEditor` |
| `module_ai/workflow/components/WorkflowEditor.vue`「定时调度」 | 裸 `el-input` 填 cron | `TriggerEditor` |
| `module_train` 调度面板（`components/Train/SchedulePanel.vue`） | 裸输入 + 停更 Quartz 组件 | `TriggerEditor` |
| `module_task/cronjob/node/index.vue` | 4 个分支各一套（含手写 `IntervalTab`、停更 `vue3CronPlus`） | `TriggerEditor`（删掉两套旧编辑器） |

### 6.3 风格约束（AGENTS.md）
- 只用 Element Plus 原生组件 + `--el-*` 变量；不自造主题外壳；字号统一（正文 14px / 次要 12px）
- 弹窗宽度用常用档位（500/600px）、放在页面根元素内（单根，避免 `<Transition>` 白屏）
- 删除/停用类操作二次确认；进度/状态用局部刷新，不整表轮询

## 7. 调度入口统一（阶段 B）

### 7.1 现状
中心调度器已具备：持久化 jobstore、执行日志事件监听、`sync_jobs_to_db()`、暂停/恢复；
但**按 cron 触发的三处各自 `while True` 轮询**（AI 工作台每分钟比对 DB `next_run_time`、
AI 工作流自算 `next_run`、训练用 `croniter`）→ 每进程各跑一份、无 coalesce/超时/并发控制、重启期间漏跑。

> 边界：项目里其它 `while True`（训练任务状态、评估/预测队列、视频推理/录制、TTL 清理、
> 连接池看门狗）是**状态/队列轮询**，不是定时任务，**不在范围**。

### 7.2 目标
凡定时任务（四种触发类型）一律注册到中心调度器，不再自建轮询。

### 7.3 设计
1. `SchedulerUtil` 增加**业务作业**通用入口（与 `NodeModel` 作业并列）：
   - `register_business_trigger(job_key, trigger, trigger_args, func, args=(), replace=True) -> Job`
     （`job_key` 形如 `ai_workspace_cron:12`、`ai_workflow_schedule:3`、`train_schedule:5`）
   - `remove_business_job(job_key) -> bool`
   - `sync_business_jobs() -> dict`（启动时按各表"启用"行注册/清理，幂等）
2. 三处调用方：新增/修改/启停/删除时同步作业；启动时 `sync_business_jobs()` 取代 `while True`
3. **状态单一真源**：`next_run_time`/`last_run_time` 由作业回写 DB 列（AI 侧删掉 `_compute_next_run`）
4. **行为参数显式化**：`coalesce=True`、`misfire_grace_time=60s`、`max_instances=1`
5. **多副本开关**：新增 `SCHEDULER_ENABLED`（默认 true），多副本部署时只让一个实例开启调度

### 7.4 验证
- 单测：注册/替换/删除/同步幂等；`job_key` ↔ DB 行一一对应
- 联调：把某条任务改成"下一分钟"→ 等它触发（断言执行体被调用、DB 回写 `last_run_time`）
- 回归：四个入口既有行为不退化（含"禁用后不再触发"）；全量 `uv run pytest -q -n 4` 通过

## 8. 测试与验收（汇总）

### 单元测试
1. `TriggerUtil.normalize/validate`：cron 映射表（`1`→`mon`、`1-5`→`mon-fri`、`7`→`sun`）；
   interval/date/now 的规范化；非法输入报错含原因
2. **必须判非法**：`L`、`15W`、`1#2`、`?`、7 段（`... 2030`）、6 段秒位非 0；
   **必须判合法**：`0 9 * * 7`
3. **口径一致性（锁死 D1）**：`0 9 * * 1`、`* * 5`、`* * 0`、`* * 7`、`* * 1-5` 的
   `TriggerUtil.next_run` 与 `croniter` 结果**同一时刻**
4. `to_trigger`：`1-5` → `mon-fri` 且下次触发为**周一**；interval/date/now 各构造正确触发器

### 接口 / 前端验收
- 四个入口都能配置四种触发类型并保存成功；列表显示触发方式 + 人话描述 + 下次运行时间
- 非法表达式：前端即时提示 + 后端 400，且**不落库**
- 无头浏览器截图核对四入口（风格与既有模块一致）

## 9. 前端组件选型对比（AGENTS.md 要求）

| 候选 | 许可 | 最近发布 | 判定 |
|---|---|---|---|
| **`@vue-js-cron/element-plus` 3.2.2** | MIT | 2026-09-14（37 版本；同族 core 6.5.0） | ✅ **首选**：Element Plus 原生 UI；`v-model` + `@error`；默认即标准 5 段（无秒/无 `?`/无 L·W）；`firstWeekDay` 默认 `sun=0` 与标准 crontab 一致；依赖仅 icons + core + `element-plus@^2.2.13`（本项目 ^2.11，同大版本可去重） |
| `vue3-cron-plus`（项目已装） | MIT | 2023-03（停更 3 年+） | ❌ 固定 Quartz 7 段；且真实 prop 是 `cron-value`（现用法 `:expression` 回填从未生效） |
| `vue-js-cron` 1.0.1 | MIT | 2022-02（停更） | ❌ Vue2 + element-ui |
| `vue-cron-editor-buefy` | MIT | 2021-04（停更） | ❌ Vue2 + Buefy |
| `cronstrue` | MIT | 2026-10（15.7M/月） | 备选（仅"表达式→人话"）：**不引入**——描述统一由后端 `TriggerUtil.describe` 产出，避免前端再有一套口径 |

## 10. 风险与回滚
- **能力变化（有意为之）**：6 段带秒写法被拒绝；秒级需求由 `interval`（时长）承担
- **契约变化**：interval 参数由字符串改结构化 JSON；AI 两张表（`ai_workspace_cron`、
  `ai_workflow_schedules`）与训练一张表（`train_schedules`）新增 `trigger`/`trigger_args` 列
  → 迁移脚本幂等、不改语义；回滚即恢复旧调用（数据可回滚，因规范化只做等价变换）
- **调度行为差异**：停机期间错过的任务按 `misfire_grace_time`（60s）处理（现状是开机即补跑）；
  已确认可接受
- **多副本**：默认与现状同级（每进程都触发）；需要时开启 `SCHEDULER_ENABLED` 单实例调度
