# cron 表达式统一（5 段标准 crontab）设计规格

日期：2026-10-18
状态：待评审（阶段 A 口径统一 + 阶段 B 调度入口统一）

## 1. 背景

平台里"定时"这件事被三块独立实现各写了一遍，导致同一个 cron 字符串在不同模块里
**含义不同、甚至有一半是错的**。当前共 4 种方言：

| 入口 | 现状格式 | 解析/调度实现 |
|---|---|---|
| AI 工作台定时任务（`ai_workspace_cron.cron`） | 5 段标准 | `CronTrigger.from_crontab()` |
| AI 工作流定时调度（`ai_workflow_schedules.cron`） | 5 段标准 | `CronTrigger.from_crontab()` |
| 训练调度（`train_schedules.cron_expr`） | 5 段标准（容忍 6 段） | `croniter` |
| 系统定时任务节点（`task_node.trigger_args`，trigger=cron） | 6~7 段 Quartz | `CronUtil` 校验 + `CronTrigger(second…year)` |
| 系统定时任务节点（trigger=interval） | 5 个数字「秒 分 时 天 周」= **时长** | `IntervalTrigger(weeks,days,hours,minutes,seconds)` |
| `app/utils/time_util.py::TimeUtil.validate_cron_expression` | 6 段 | **无人调用（死代码）** |

> interval 触发器不是 cron，而是"时长"，本设计**不动它**（见 §3 非目标）。

## 2. 实测缺陷清单（全部为实测结果，非推测）

复现脚本：临时探针（`CronUtil.validate_cron_expression` + `CronTrigger` + `croniter` 对同一表达式求下一次触发时间）。

### D1（严重）同一表达式在不同模块跑在不同星期几
基准时刻 2026-10-18（周日）：

| 表达式 | APScheduler（AI 侧 / 系统定时任务） | croniter（训练调度） | 判定 |
|---|---|---|---|
| `0 9 * * 1` | 2026-10-20 **Tue** | 2026-10-19 **Mon** | 不一致 |
| `0 9 * * 5` | 2026-10-24 **Sat** | 2026-10-23 **Fri** | 不一致 |
| `0 9 * * 0` | 2026-10-19 **Mon** | 2026-10-18 **Sun** | 不一致 |

根因：APScheduler 的数字周字段是 `0=周一`，标准 crontab 是 `0/7=周日`；而 `CronUtil`
校验器又按 Quartz（`1=周日`）放行 → **三套口径互不相同**。

### D2（严重）校验器放行、调度器报错（"存得下、到点才炸"）
| 表达式 | `CronUtil` 校验 | `CronTrigger(...)` |
|---|---|---|
| `0 0 9 L * *` | True | `ValueError` |
| `0 0 9 15W * *` | True | `ValueError` |
| `0 0 9 * * 1#2` | True | `ValueError` |
| `0 0 9 * * 7` | True | `ValueError` |
| `0 0 9 ? * *` | True | `ValueError`（注：`ap_scheduler` 会把 `?` 转 `*`，但校验与转换分离，语义仍混乱） |

即：Quartz 专有语法（`L`/`W`/`#`/`7`）能通过校验并保存，但真正建触发器时才抛错。

### D3（中）7 段的"年"字段是时间炸弹
`CronUtil.validate_year` 只接受 `[当前年, 当前年+8]`：今天 `0 0 9 * * * 2030` 合法，
`0 0 9 * * * 2036` 已非法 → 存量的 7 段配置会在未来某年突然无法保存/失效。

### D4（中）秒级规则自相矛盾，且秒级调度在 web 多副本下不利
- `0 * * * * *`（每分钟第 0 秒，无实际意义）→ 校验通过、调度器接受
- `*/5 * * * * *`（每 5 秒，最常见的秒级写法）→ 校验 **不通过**

并且 APScheduler 是**进程内**调度：多 worker/多副本部署时每个进程各跑一份 → 秒级任务重复触发风险显著。

### D5（中）AI 侧"下次运行时间"显示同样被带偏
`0 9 * * 1-5`（用户理解：工作日 9 点）实际下次触发为 **周二 09:00**，与训练调度（周一）也不一致。

### D6（轻）重复实现 / 死代码
`app/utils/time_util.py::TimeUtil.validate_cron_expression` 与 `app/utils/cron_util.py` 是两份
同用途实现，前者无任何调用方。

## 3. 目标 / 非目标

### 目标
1. **一种格式**：全平台 cron 统一为 **5 段标准 crontab**：`分 时 日 月 周`。
2. **一种语义**：周字段按标准 crontab —— `0` 与 `7` 均为周日，`1`=周一 … `6`=周六，
   同时接受名称 `mon…sun`（大小写不敏感）。
3. **一处实现**：校验、规范化、触发器构造全部收敛到 `app/utils/cron_util.py`，
   调度入口收敛到 `app/core/ap_scheduler.py`。
4. **一套调度（阶段 B）**：凡按 cron 触发的定时任务（AI 工作台 / AI 工作流 / 训练调度）
   一律注册到中心 APScheduler，删除各自的自建轮询（见 §9）。
5. **修掉 D1~D6**。
6. 前端三处 cron 输入换成**可视化选择器**（成熟第三方组件，见 §7）。

### 分期
- **阶段 A（口径统一）**：§4~§8。风险低、收益直接（消除"同一表达式三种含义"），先落地。
- **阶段 B（调度入口统一）**：§9。把三处 cron 调度并入中心调度器，删除自建轮询。

### 非目标
- 不改 `interval` 触发器（它是"时长"而非 cron；秒级需求由它承担）。
- 不引入分布式调度（APScheduler 进程内调度的局限不在本次范围；仅去掉秒级以降低重复触发风险）。
- 不支持 Quartz 专有语法（`?`/`L`/`W`/`#`/7 段年字段）：写入时**明确报错**，不静默转换。

## 4. 统一契约

### 4.1 表达式格式
- 唯一合法形式：**5 段**：`分 时 日 月 周`
- 字段取值：
  - 分：`0-59`；时：`0-23`；日：`1-31`；月：`1-12`；周：`0-7` 或 `mon…sun`
  - 支持 `*`、`a-b`、`a,b,c`、`*/n`、`a-b/n`
- **周字段映射表**（规范化后统一交给调度器，绕开 APScheduler 的 `0=周一`，这是 D1 的修法）：

  | 输入（标准 crontab） | 规范化输出 | 含义 |
  |---|---|---|
  | `0`、`7`、`sun` | `sun` | 周日 |
  | `1`、`mon` | `mon` | 周一 |
  | `2` … `6`、`tue`…`sat` | `tue` … `sat` | 周二 … 周六 |
  | `1-5` | `mon-fri` | 周一到周五 |
  | `*` | `*` | 每天 |

- `?` 仅在**读旧数据/迁移**时容错转换（`?` → `*`，语义等价）；**写入接口一律拒绝** `?`

### 4.2 统一层 API（`app/utils/cron_util.py`）
| 方法 | 作用 |
|---|---|
| `CronUtil.normalize(expr) -> str` | 规范化：去多余空格、周字段按 §4.1 映射表转换；非法则抛 `CustomException` |
| `CronUtil.validate(expr) -> tuple[bool, str]` | 校验并返回**可读错误原因**（用于接口 400 与前端提示） |
| `CronUtil.to_trigger_kwargs(expr) -> dict` | 输出 APScheduler 的 `minute/hour/day/month/day_of_week`（周字段已映射为名称） |
| `CronUtil.next_run(expr, base=None) -> datetime \| None` | 统一的"下次运行时间"，供 AI 侧展示（修 D5）；内部走 `to_trigger_kwargs`，与调度器同源 |

约束：`normalize` 与 `validate` 必须**互相同源**（校验通过 ⇒ 一定可构造触发器），
并用参数化测试锁死（含 D2 的五个反例）。

### 4.3 调用方改造
| 位置 | 改法 |
|---|---|
| `app/core/ap_scheduler.py::add_cron_job` | 改用 `normalize` + `to_trigger_kwargs` + `CronTrigger(minute=…)`；删除就地 `?`→`*` 与 `year` 字段 |
| `module_ai/workspace/service.py`（定时任务增改 + 轮询匹配） | 写入时 `normalize`；匹配/下次时间改用 `CronUtil.next_run` |
| `module_ai/workflow/service.py`（定时调度 + 调度循环） | 同上（替换 3 处 `from_crontab`） |
| `module_train/schedule_service.py`（croniter 匹配） | 写入时 `normalize`；匹配表达式直接用规范化值（croniter 本就是标准口径，改后与全平台一致） |
| `module_task/cronjob/node/service.py`（校验） | 改用 `CronUtil.validate`，错误信息原样回给前端 |
| `app/utils/time_util.py` | 删除重复的 `validate_cron_expression`（D6） |

### 4.4 数据迁移
- 一次性幂等脚本（或 Alembic 数据迁移），对 4 张表做 `normalize`：
  `ai_workspace_cron.cron`、`ai_workflow_schedules.cron`、`train_schedules.cron_expr`、`task_node.trigger_args`（仅 `trigger='cron'`）
- 规则（与 §4.1 一致，**不做静默语义改写**）：
  - 5 段 → 原样规范化（周字段按映射表转换）
  - `?` → `*`（语义等价，可安全转换）
  - 6 段且秒位为 `0` → 去掉首段
  - 6 段且秒位非 `0`（如 `30 * * * * *`）、7 段（带年）→ **跳过并写入迁移日志**，由人工确认
    （这类表达式含义会变，不能自动降级）
- 当前 dev 库实际只有 1 条（`ai_workspace_cron.cron = "0 9 * * *"`，5 段，无需改动），迁移风险≈0

## 5. 前端（三处 cron 输入 → 一个可视化选择器）

新增薄封装 `frontend/src/components/CronEditor/index.vue`，内部用第三方组件，
对外只暴露 `v-model`（cron 字符串）+ `@error`：

| 使用处 | 现状 | 改后 |
|---|---|---|
| `views/module_ai/workspace/index.vue`「新建定时任务」 | 裸 `el-input` | `<CronEditor v-model="cronForm.cron" />` |
| `views/module_ai/workflow/components/WorkflowEditor.vue`「定时调度」 | 裸 `el-input` | 同上 |
| `views/module_task/cronjob/node/index.vue`（trigger=cron 分支） | 停更的 `vue3CronPlus`（Quartz 7 段，且回填 prop 名写错导致回填失效） | `<CronEditor v-model="executeFormData.trigger_args" />` |

`trigger=interval` 分支的 `IntervalTab`（时长构造器）**保留不动**。

## 6. 测试与验收

### 单元测试（新增 `tests/test_cron_unified.py`）
1. `normalize`：5 段原样；周字段按 §4.1 映射表转换（`1`→`mon`、`1-5`→`mon-fri`、`7`→`sun`）；多余空格；非法输入抛错
2. `validate`：**必须判非法**的是 Quartz 专有语法与 6/7 段——`L`、`15W`、`1#2`、`?`、`0 0 9 * * * 2030`（7 段）、
   `30 * * * * *`（6 段且秒位非 0）；**必须判合法**的含 `0 9 * * 7`（标准 crontab 的周日）
3. **口径一致性（锁死 D1）**：对 `0 9 * * 1`、`0 9 * * 5`、`0 9 * * 0`、`0 9 * * 7`、`0 9 * * 1-5`
   断言 `CronUtil.next_run(...)` 与 `croniter` 的下次触发**是同一时刻**
4. `to_trigger_kwargs`：断言 `1-5` 映射为 `mon-fri`，且构造的 `CronTrigger` 下次触发为**周一**
5. 6 段秒位为 0（`0 0 9 * * *`）经 `normalize` 得 `0 9 * * *`；秒位非 0 则报错并说明原因

### 接口/回归
- AI 工作台、AI 工作流：保存 `0 9 * * 1-5` → 接口返回的下次运行时间为**周一 09:00**
- 系统定时任务：保存 `0 9 * * 1-5` → `task_node` 存的值与触发时刻为**周一~周五**
- 全量 `uv run pytest -q -n 4` 通过

### 前端验收（无头浏览器 + 截图）
- 三处页面点开选择器 → 选"每周一 09:00" → 生成 `0 9 * * 1` → 保存成功
- 输入非法表达式（如 `0 9 L * *`）→ 前端提示非法、后端 400，且**不落库**

## 7. 附：前端组件选型对比（AGENTS.md 要求）

| 候选 | 许可 | 最近发布 | 判定 |
|---|---|---|---|
| **`@vue-js-cron/element-plus` 3.2.2** | MIT | 2026-09-14（37 版本；同族 core 6.5.0） | ✅ **首选**：Element Plus 原生 UI；`v-model` + `@error`；默认即标准 5 段（无秒、无 `?`、无 L/W）；`firstWeekDay` 默认 `sun=0` 与标准 crontab 一致；依赖仅 icons + core + `element-plus@^2.2.13`（本项目 ^2.11，同大版本可去重） |
| `vue3-cron-plus`（项目已装） | MIT | 2023-03（停更 3 年+） | ❌ 固定 Quartz 7 段，与本设计目标冲突；且其真实 prop 名是 `cron-value`（现用法 `:expression` 回填从未生效） |
| `vue-js-cron` 1.0.1 | MIT | 2022-02（停更） | ❌ Vue2 + element-ui |
| `vue-cron-editor-buefy` | MIT | 2021-04（停更） | ❌ Vue2 + Buefy |
| `cronstrue` | MIT | 2026-10（15.7M 下载/月） | 备选补充（仅"表达式→人话"）：**本轮不引入**，选择器自带中文描述；若后续要做列表展示再评估 |

## 8. 风险与回滚（阶段 A：口径统一）

- **风险**：统一后"6 段带秒"的写法会被拒绝（能力变化，属有意为之）；存量若有秒位非 0 的数据需人工确认。
- **回滚**：迁移脚本只做"5 段规范化"，不改表结构；回滚即恢复 `from_crontab`/`CronTrigger` 旧调用（数据无需回滚）。
- **部署注意**：APScheduler 是进程内调度，多副本部署时定时任务会重复执行（既有问题，阶段 B 的
  `SCHEDULER_ENABLED` 开关可解决，见 §9.3.5）。

## 9. 调度入口统一（阶段 B）——同一套调度

### 9.1 现状
中心调度器 `app/core/ap_scheduler.py` **已经存在且完整**：`AsyncIOScheduler` + 持久化
`SQLAlchemyJobStore` + 执行日志事件监听 + `sync_jobs_to_db()` + 暂停/恢复，启动时由
`init_app` 调 `SchedulerUtil.init_scheduler()` 拉起。

但**按 cron 触发的三处各自写了轮询**，没走它：

| 位置 | 现状实现 | 问题 |
|---|---|---|
| AI 工作台定时任务 | `workspace/service.py::cron_scheduler` 每分钟 `while True` 轮询，读 DB 行比对 `next_run_time` | 每个进程各跑一份（多副本重复触发）；无 coalesce/超时/最大并发控制；重启期间漏跑 |
| AI 工作流定时调度 | `workflow/service.py` 内自行计算 `next_run`（`from_crontab`） | 同上，且口径与中心调度器不同源 |
| 训练定时调度 | `module_train/scheduler.py` 自建循环 + `croniter` | 同上 |

> 说明：项目里还有若干 `while True` 循环（训练任务状态轮询、评估/预测队列、视频推理/录制、
> TTL 清理、连接池看门狗等）——它们是**状态/队列轮询**，不是 cron 触发，**不在本次范围**。

### 9.2 目标
**凡"按 cron 表达式触发"的定时任务，一律注册到中心调度器**，不再自建轮询。

### 9.3 设计
1. `SchedulerUtil` 增加**业务作业**通用入口（与现有 `NodeModel` 作业并列，互不干扰）：
   - `register_business_cron(job_key, cron, func, args=(), replace=True) -> Job`
     （`job_key` 形如 `ai_workspace_cron:12`、`ai_workflow_schedule:3`、`train_schedule:5`）
   - `remove_business_job(job_key) -> bool`
   - `sync_business_jobs() -> dict`（启动时按各表 `enabled` 行注册/清理，幂等）
2. 三处调用方：
   - **新增/修改/启停/删除**定时任务时同步作业（replace / remove）
   - **启动时** `sync_business_jobs()` 注册全部启用行（替代各自的 `while True`）
   - **执行体**复用现有逻辑（AI 走 `_run_target` / `run_schedule`，训练走原训练提交函数）
3. **状态单一真源**：`next_run_time` / `last_run_time` 由作业（`job.next_run_time`）写回 DB 列，
   供列表展示；不再由轮询循环推算（AI 侧现有 `_compute_next_run` 删除）。
4. **行为参数显式化**（替代当前隐式行为）：
   - `coalesce=True`（错过多次只补一次，与现有 `max_instances`/job_defaults 一致）
   - `misfire_grace_time` 显式设置（建议 60s，避免默认 1s 导致轻微延迟即丢跑）
   - `max_instances=1`（同一个定时任务不允许并发重叠，AI 侧尤其重要）
5. **多副本开关（可选收益）**：新增 `SCHEDULER_ENABLED`（默认 true）。多副本部署时可只让一个实例
   开启调度，避免重复触发（现状是每进程都轮询，同样重复——统一后才有地方加这个开关）。

### 9.4 迁移
- 首次启动 `sync_business_jobs()` 即完成注册（无需改表结构；DB 列继续保留，语义变为"调度器回写"）。
- 灰度：先合并 AI 工作台一处（最小面）验证，再合并 AI 工作流与训练。

### 9.5 验证
- 单测：注册/替换/删除/同步幂等；`job_key` 与 DB 行一一对应
- 联调：把某条定时任务的 cron 改为"下一分钟"，等待触发一次（断言执行体被调用、DB 回写 `last_run_time`）
- 回归：AI 工作台/工作流/训练的既有定时行为不退化（含"禁用后不再触发"）
- 全量 `uv run pytest -q -n 4` 通过

### 9.6 风险
- **行为差异**：`coalesce` / `misfire_grace_time` / `max_instances` 与自建轮询不同（需按业务显式设定，见 §9.3.4）
- **重启语义**：APScheduler 持久化 jobstore 重启后按 `next_run_time` 恢复；自建轮询靠 DB 行比对（两者对"停机期间错过的任务"处理不同：前者按 misfire 规则，后者会立刻补跑）→ 迁移时需确认可接受
- **多副本**：默认行为与现状同级（每进程都触发）；如需彻底避免，开启 §9.3.5 的单实例开关
