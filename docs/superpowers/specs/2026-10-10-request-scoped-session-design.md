# 请求作用域会话（Request-Scoped Session）设计

- 日期：2026-10-10
- 状态：**待评审**
- 承接：`docs/connection-pool-leak-diagnosis.md`（该文第 4 节「还没解决的」第 2、3 条）

## 一、要解决的问题（都有实测支撑）

| 问题 | 实测证据 |
|---|---|
| **一个请求最多同时吃 3 条连接** | `pg_stat_activity` 在单请求执行期高频采样：峰值 `active=2, idle in transaction=1`。原因：服务层普遍自己开 `async_db_session()`，不复用请求会话 |
| **被取消的请求会漏连接，且不自愈** | 正常完成 60 个请求 → `idle in transaction` 为 0；浏览器翻页巡检后残留 10~34 条，最后一句 SQL 都是认证的角色加载（即 `db_getter` 借出的那条）。池占满后所有接口一起超时，**只能重启后端** |
| **死锁临界点** | 同接口 POST × 20 全成功（2.1s）；POST × 30 只成功 1 个（60s 死锁） |
| 现有防线只是缓解 | `db_getter` 的 `try/finally + shield`（超时 19→4 条）、`db_leak_watchdog`（每 60s 回收空闲事务 >120s）都**不是根因修复** |

**目标**：一请求一条连接（服务层透明复用）；会话归还点搬到 **ASGI 中间件**（比 `yield` 依赖可靠）；看门狗降级为兜底。

## 二、现状约束（已核对代码）

1. 全仓 `async_db_session` **761 处**，只有两种用法：`async_db_session()` 与 `async_db_session.begin()`。
   非调用用法仅 4 条（定义行/注释），**没有**把它当对象传递 → 可以用「包装器」零改动覆盖全部调用点。
2. 现有中间件 `RequestLogMiddleware` 是 **`BaseHTTPMiddleware`**：它会把下游放进**新任务**执行。
   因此会话中间件**必须用纯 ASGI 中间件**，否则 ContextVar 的「owner task」判定会失配（端点任务 ≠ 中间件任务）。
3. `register_middlewares` 逆序注册：`MIDDLEWARE_LIST` **第一项在最外层**（见 `setting.py:590`）。
4. 后台任务/调度器（训练、推理、看门狗等）**没有请求上下文**，必须保持「各自新开会话」。
5. 测试用 `TestClient(app)` 走真实 lifespan 与中间件；未使用 `dependency_overrides`（`tests/conftest.py`）。

## 三、设计

### 3.1 请求会话的存放与判定（`app/core/database.py`）

```python
_request_session: ContextVar[tuple[AsyncSession, asyncio.Task] | None] = ContextVar(
    "request_session", default=None
)

def current_request_session() -> AsyncSession | None:
    """仅当当前任务就是持有者时才返回请求会话；子任务（create_task/gather）不返回。"""
    cur = _request_session.get()
    if cur is None:
        return None
    session, owner = cur
    try:
        return session if asyncio.current_task() is owner else None
    except RuntimeError:
        return None
```

**owner-task 判定是关键**：`asyncio.create_task` 会把 ContextVar **复制**给子任务，
若不判定任务归属，子任务会拿到「请求会话」，而请求结束时中间件会把它关掉 → 子任务崩溃。
判定后子任务一律新建会话，行为与今天一致。

### 3.2 `async_db_session` 换成上下文感知包装器

```python
class _SessionFactory:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[AsyncSession]:
        ambient = current_request_session()
        if ambient is not None:
            yield ambient          # 复用请求会话：不关闭、不另起事务
            return
        async with self._factory() as session:
            yield session

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        ambient = current_request_session()
        if ambient is not None:
            yield ambient          # 复用：提交/回滚交由中间件收尾
            return
        async with self._factory.begin() as session:
            yield session
```

`async_db_session` 由 `async_sessionmaker` 实例替换为该包装器（仍是模块级对象，
**所有 `from app.core.database import async_db_session` 导入点不变**）。

### 3.3 纯 ASGI 中间件（`app/core/middlewares.py`）

```python
class DBSessionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":          # lifespan / websocket 透传
            await self.app(scope, receive, send)
            return

        async with async_db_session() as session:   # 此处无 ambient → 真建一条
            token = _request_session.set((session, asyncio.current_task()))
            try:
                await self.app(scope, receive, send)
            except BaseException:
                with suppress(Exception):
                    await asyncio.shield(session.rollback())
                raise
            else:
                if session.in_transaction():
                    with suppress(Exception):
                        await asyncio.shield(session.commit())
            finally:
                _request_session.reset(token)
                with suppress(Exception):
                    await asyncio.shield(session.close())
```

> 注意：中间件里 `async_db_session()` 调用发生在**设置 ambient 之前**，所以它拿到的是真会话，
> 不会自我复用造成递归。

### 3.4 注册顺序

`setting.py` 的 `MIDDLEWARE_LIST` 末尾追加：

```python
"app.core.middlewares.DBSessionMiddleware" if self.SQL_DB_ENABLE else None,
```

放在**列表最后** → 逆序注册后位于**最内层**，紧贴端点，保证中间件与端点**同一任务**
（若放在 `RequestLogMiddleware` 外层，端点会被 `BaseHTTPMiddleware` 换任务，owner 判定失效）。

### 3.5 `db_getter` 兜底

```python
async def db_getter() -> AsyncGenerator[AsyncSession, None]:
    ambient = current_request_session()
    if ambient is not None:
        yield ambient
        return
    async with async_db_session() as session:        # 非请求上下文：退回现状
        try:
            async with session.begin():
                yield session
        finally:
            with suppress(Exception):
                await asyncio.shield(session.close())
```

## 四、语义变化（诚实列出）

1. **请求内服务层写入并入请求事务**：此前服务层各自 `commit()`（部分成功也会落库）；
   现在与请求同生共死，请求异常会一起回滚。这是泄漏的根因修复，但确属行为变化。
2. **提交点**从依赖收尾移到中间件收尾（两者都在响应之后，时机基本一致）。
3. **`asyncio.gather` 内并发子任务不共享会话**（owner-task 判定）→ 与今天一致的并发安全。

## 五、风险与缓解

| 风险 | 缓解 |
|---|---|
| 个别代码需要「独立提交」（审计/通知/进度落库）被并入请求事务 | 跑全量 pytest（1939）；若失败，为该点引入 `async_db_session_fresh()` 显式逃生口，并就地注释原因 |
| `create_task` 子任务被提前关闭会话 | owner-task 判定，子任务新建会话 |
| 中间件层次放错导致跨任务 | 置于最内层；e2e 复测 |
| 取消时 `finally` 内 `await` 被再次取消 | `shield` + `suppress`（沿用现有已验证做法） |
| SQLite 测试环境差异 | 测试走同一中间件；pytest 全绿作为门槛 |

## 六、验收标准

- `uv run pytest`：全绿（仅剩 3 个既有 Alembic 失败）。
- 并发 30 个 POST：不再死锁（此前 1/30）。
- 浏览器 12 页面巡检后 `idle in transaction` = 0，且**不重启后端**仍可用。
- `pg_stat_activity` 单请求采样：峰值连接 = **1**（此前 3）。
- `ruff check` 无新增。

## 七、本轮不做（明确边界）

- **不逐个改服务层调用点**：靠 3.2 的包装器透明覆盖。
- **不删除看门狗**：保留为第二道防线。
- **不改 `MAX_OVERFLOW` / `POOL_SIZE`**：用户已确认维持 `POOL_SIZE=48`。
