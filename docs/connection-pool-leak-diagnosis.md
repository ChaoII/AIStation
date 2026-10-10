# 后端连接泄漏与池死锁：定位与修复

**这篇是一次真实排查的完整记录。结论都有实测数据支撑，没测到的地方明确标注。**

## 一、现象

用户反馈：「页面到处报错」。表现是页面能打开，但接口大面积 `timeout of 10000ms exceeded`，
而且**越用越严重，不会自己恢复，必须重启后端**。

## 二、定位过程（用数据说话）

### 2.1 先看 PG 侧连接状态——发现 20 条连接集体卡死

```
state = idle in transaction        ← 事务开着不提交
query = SELECT sys_role_1.id ..., sys_dept.name ...   ← 认证加载角色/部门
持续  = 3 分 59 秒
wait_event_type = Client           ← 服务端在等应用，应用却没动静
```

**池被占满 → 之后每个请求都排队 → 全线超时。**

### 2.2 量「一个请求到底占几条连接」

用 `pg_stat_activity` 在**单个请求**执行期间高频采样：

```
active=1                              ← 刚进来
active=2, idle in transaction=1       ← 峰值：同时 3 条！
active=2, idle in transaction=1
active=1, idle in transaction=2
active=1                              ← 结束
```

> **一个请求最多同时吃 3 条连接。**

原因：**服务层普遍自己开会话（`async_db_session()`），不复用请求的会话**——
问数服务 84 处、知识库 31 处、本体服务 9 处……
「请求会话」+「服务自己的会话」+「嵌套调用」叠起来就是 3 条。

**死锁条件因此是：并发请求数 ≥ POOL_SIZE / 2。** 池 20 条时只能支撑约 6~10 个真并发，
而页面一次加载就发 10+ 请求。

### 2.3 复现死锁（找到确切临界点）

同一接口，只改并发数：

| 并发 | 成功 | 耗时 |
|---|---|---|
| POST × 20 | **20/20** | 2.1 秒 |
| **POST × 30** | **1/30** | **60 秒（死锁）** |
| POST × 40 | 17/40 | 32 秒 |

### 2.4 关键区分：正常请求不漏，**被中断的请求才漏**

| 场景 | 结果 |
|---|---|
| **正常完成** 60 个请求 | `idle in transaction` **0 条**、SAWarning **0 次** |
| 浏览器巡检 12 个页面（大量翻页中断） | 残留 **10~34 条** `idle in transaction`、SAWarning **10~22 次** |

**所以根因是：请求被取消（浏览器翻页/关闭/超时）时，连接没被归还，永久卡在
`idle in transaction`。**

佐证：这些泄漏连接的**最后一句 SQL 都是认证的角色加载**，正是 `db_getter` 借出的那条连接；
后端日志同时出现 `SAWarning: The garbage collector is trying to clean up non-checked-in connection`
——会话对象被 GC 掉而从未归还。

### 2.5 走错的两条路（记录一下，别再走）

- ❌ **先怀疑 `OperationLogRoute`**（它在响应后另开会话写日志，看起来就是"占着 A 又要 B"）。
  **实测否定**：把操作日志整个关掉，30 并发**照样死锁**。
- ❌ **先怀疑 IP 归属地查询**（`resolve_location_for_log` 会发外网请求）。
  **实测否定**：`DEBUG=True` 时它直接返回占位，根本不发外网。

## 三、修了什么

### 3.1 `db_getter`：保证任何情况下都归还连接（第一道防线）

`app/core/dependencies.py` —— 改成 `try/finally` + `asyncio.shield`：

- `finally` 保证正常返回、抛异常、生成器被 `aclose()` 三种情况都执行
- `shield` 保证当前任务已被取消时，关闭动作仍能跑完（否则 `await` 会立刻再抛
  `CancelledError`，连接照样漏）

**效果：10 秒超时从 19 条降到 4 条。**

### 3.2 连接池按实测倍数放大

`env/.env.dev` —— `POOL_SIZE` 20 → **48**（`MAX_OVERFLOW` 保持 0）。

为什么不用 `MAX_OVERFLOW`：溢出连接归还即关闭，会反复建连
（本机 PG 建连含 SCRAM PBKDF2 约 0.7s/条，同步阻塞事件循环）。
用**持久连接 + 启动预热**没有这个问题。48 条可支撑约 24 个真并发请求；
PG `max_connections=100`，留足余量。

> ⚠️ **踩过的坑**：我第一次把新配置追加到文件末尾，而**旧块 `POOL_SIZE = 20` 还在**，
> 两处重复定义 → 改动完全没生效。配置项**必须只有一处**。

### 3.3 连接泄漏看门狗（第二道防线，让系统自愈）

`app/core/database.py` 新增 `db_leak_watchdog`，每 60 秒巡检一次，
把 `idle in transaction` **超过 120 秒**的连接 `pg_terminate_backend` 掉。

- 只回收"事务空转超 2 分钟"的连接——正常请求不可能这样，**不会误伤**
- 配合 `POOL_PRE_PING=true`，被回收的连接在下次签出时自动替换

**实测效果（巡检后）：**

```
🧹 连接泄漏看门狗：回收了 4 条卡死连接（idle in transaction > 120s）：[59367, 59372, 59374, 59366]
🧹 连接泄漏看门狗：回收了 1 条卡死连接：[59507]
🧹 连接泄漏看门狗：回收了 1 条卡死连接：[59563]

idle in tx:  34 → 0
登录:        正常 2797ms（★ 不需要重启后端）
```

> ⚠️ **踩过的坑**：事件加载器是 **await** 每个函数的，看门狗第一版写了 `while True`，
> **直接把启动阻塞死**（端口一直不监听）。改成派生后台任务后立即返回才正常。

## 四、还没解决的（诚实说明）

1. **泄漏本身没有被根除。** 被取消的请求仍会漏连接，`db_getter` 的 `finally` 在
   ASGI 任务被取消时不保证跑到。看门狗只是**兜底回收**，不是修复。
2. ~~**真正的修法**：把会话的生命周期从「`yield` 依赖」搬到「**中间件**」……~~
   **✅ 已修复（2026-10-10）**：新增纯 ASGI `DBSessionMiddleware`，会话生命周期搬到
   中间件，`finally` 在取消路径也执行（配 `asyncio.shield`）。
   见 `docs/superpowers/specs/2026-10-10-request-scoped-session-design.md`。
3. ~~**「一个请求吃 3 条连接」没有改。**~~ **✅ 已修复（2026-10-10）**：
   `async_db_session` 改为上下文感知包装器，请求内**同任务**透明复用请求会话
   （761 处调用点零改动），一请求降为 **1 条**连接；`create_task`/`gather` 子任务与
   后台任务照旧各自新建。
4. **`/ai/model`、`/ai/app`、`/ai/logs` 的 10 秒超时**：根因是并发下池被占用，
   随 1、3 的修复应显著缓解；仍需巡检复测确认。
5. **头像地址指向不存在的外部域名**：`https://service.aistation.com/api/v1/static/image/avatar.png`
   → `ERR_NAME_NOT_RESOLVED`。这是**既有配置问题**，出现在多个页面，**还没修**。
6. **AGENTS.md 里写的 `MAX_OVERFLOW=40` 是错的**，代码实际是 `0`（有明确理由）。文档需要更正。

## 五、复现与验证方法

```bash
# 看当前有多少卡死连接
docker exec aistation-pg-rag psql -U root -d aistation -c \
  "SELECT state, count(*) FROM pg_stat_activity WHERE datname='aistation' GROUP BY state;"

# 看泄漏连接的最后一句话是什么
docker exec aistation-pg-rag psql -U root -d aistation -c \
  "SELECT pid, now()-xact_start, left(query,80) FROM pg_stat_activity
   WHERE datname='aistation' AND state='idle in transaction';"

# 页面健康巡检（无头浏览器，抓控制台错误/未捕获异常/失败请求）
cd frontend
npx playwright test e2e/ai-pages-audit.spec.ts --project=chromium --reporter=list

# 看门狗是否在回收
Select-String -Path "$env:TEMP\be.out.log" -Pattern '看门狗'
```

## 六、给后来者的三条教训

1. **别猜，采样。** 我先后怀疑过操作日志、IP 查询，**都被实测否定**；
   真正的原因（一个请求吃 3 条连接、取消时泄漏）都是靠 `pg_stat_activity` 采样出来的。
2. **区分"正常路径"和"异常路径"。** 正常请求一个都不漏，泄漏全在**取消**路径上——
   不分别测就永远找不到。
3. **改动核心配置后必须确认生效。** 我因为配置重复定义，白跑了一轮验证；
   改完先 `print(settings.POOL_SIZE)` 确认，再谈效果。
