import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token

from fastapi import FastAPI
from redis import exceptions
from redis.asyncio import Redis
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.config.setting import settings
from app.core.base_model import MappedBase
from app.core.exceptions import CustomException
from app.core.logger import log


class RequestScopedSession(AsyncSession):
    """请求作用域会话：把「二次 ``begin()``」降级为 ``begin_nested()``（SAVEPOINT）。

    实测（2026-10-10，全量回归 243 个 error）：请求作用域会话落地后，
    ``async with async_db_session() as s: async with s.begin():`` 这类**先取会话再开事务**
    的写法（全仓 25 处，请求路径上约 10 处；登录成功后写操作日志即命中）会在
    「事务已开启」的请求会话上二次 ``begin()``，抛
    ``InvalidRequestError: A transaction is already begun on this Session``。

    这里覆盖 ``begin()``：**已有事务时返回 ``begin_nested()``**（SAVEPOINT，退出释放、
    异常回滚到保存点），无事务时保持原语义。这样既维持「一请求一连接」的透明复用，
    又不用改各调用点「进入即开始、退出即提交」的既有写法。
    """

    def begin(self) -> AsyncSessionTransaction:
        if self.in_transaction():
            return self.begin_nested()
        return super().begin()


def create_engine_and_session(
    db_url: str = settings.DB_URI,
) -> tuple[Engine, sessionmaker]:
    """
    创建同步数据库引擎和会话工厂。

    参数:
    - db_url (str): 数据库连接URL,默认从配置中获取。

    返回:
    - tuple[Engine, sessionmaker]: 同步数据库引擎和会话工厂。
    """
    try:
        if not settings.SQL_DB_ENABLE:
            raise CustomException(
                msg="请先开启数据库连接",
                data="请启用 app/config/setting.py: SQL_DB_ENABLE",
            )
        # 同步数据库引擎
        engine: Engine = create_engine(
            url=db_url,
            echo=settings.DATABASE_ECHO,
            pool_pre_ping=settings.POOL_PRE_PING,
            pool_recycle=settings.POOL_RECYCLE,
        )
    except Exception as e:
        log.error(f"❌ 数据库连接失败 {e}")
        raise
    else:
        # 同步数据库会话工厂
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        return engine, SessionLocal


def create_async_engine_and_session(
    db_url: str = settings.ASYNC_DB_URI,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """
    获取异步数据库会话连接。

    参数:
    - db_url (str): 异步数据库 URL，默认取配置项 ASYNC_DB_URI。

    返回:
    - tuple[AsyncEngine, async_sessionmaker[AsyncSession]]: 异步数据库引擎和会话工厂。
    """
    try:
        if not settings.SQL_DB_ENABLE:
            raise CustomException(
                msg="请先开启数据库连接",
                data="请启用 app/config/setting.py: SQL_DB_ENABLE",
            )
        # 异步数据库引擎
        if settings.DATABASE_TYPE == "sqlite":
            async_engine = create_async_engine(
                url=db_url,
                echo=settings.DATABASE_ECHO,
                echo_pool=settings.ECHO_POOL,
                pool_pre_ping=settings.POOL_PRE_PING,
                future=settings.FUTURE,
                pool_recycle=settings.POOL_RECYCLE,
            )
        else:
            async_engine = create_async_engine(
                url=db_url,
                echo=settings.DATABASE_ECHO,
                echo_pool=settings.ECHO_POOL,
                pool_pre_ping=settings.POOL_PRE_PING,
                future=settings.FUTURE,
                pool_recycle=settings.POOL_RECYCLE,
                pool_size=settings.POOL_SIZE,
                max_overflow=settings.MAX_OVERFLOW,
                pool_timeout=settings.POOL_TIMEOUT,
                pool_use_lifo=settings.POOL_USE_LIFO,
            )
    except Exception as e:
        log.error(f"❌ 数据库连接失败 {e}")
        raise
    else:
        # 异步数据库会话工厂
        AsyncSessionLocal = async_sessionmaker(
            bind=async_engine,
            autocommit=settings.AUTOCOMMIT,
            autoflush=settings.AUTOFETCH,
            expire_on_commit=settings.EXPIRE_ON_COMMIT,
            class_=RequestScopedSession,
        )
        return async_engine, AsyncSessionLocal


engine, db_session = create_engine_and_session(settings.DB_URI)
async_engine, _async_session_factory = create_async_engine_and_session(settings.ASYNC_DB_URI)


# ===================================================================== #
# ******************* 请求作用域会话（一请求一连接） ******************* #
# ===================================================================== #
#: 当前请求的会话及其**持有任务**。
#: 只允许「同一任务」复用：``asyncio.create_task`` 会把 ContextVar 复制进子任务，
#: 若不校验任务归属，子任务会拿到请求会话、并在请求结束被关闭后继续使用而崩溃。
_request_session: ContextVar[tuple[AsyncSession, asyncio.Task] | None] = ContextVar(
    "request_session", default=None
)


def activate_request_session(session: AsyncSession) -> Token:
    """把 ``session`` 登记为**当前任务**的请求会话，返回可用于还原的 token。"""
    return _request_session.set((session, asyncio.current_task()))


def deactivate_request_session(token: Token) -> None:
    """还原 :func:`activate_request_session` 的登记。"""
    _request_session.reset(token)


def current_request_session() -> AsyncSession | None:
    """返回当前任务的请求会话；非请求任务（含 ``create_task`` 子任务）返回 ``None``。

    任务归属判定是安全关键：子任务一律走「新建会话」，避免复用后被提前关闭。
    """
    current = _request_session.get()
    if current is None:
        return None
    session, owner = current
    try:
        if asyncio.current_task() is not owner:
            return None
    except RuntimeError:  # 没有运行中的事件循环/任务
        return None
    return session


class _SessionFactory:
    """``async_sessionmaker`` 的上下文感知包装器。

    命中请求会话时**直接复用**（不关闭、不另起事务；提交/回滚由
    ``DBSessionMiddleware`` 收尾）；否则行为与 ``async_sessionmaker`` 完全一致。
    这样全仓 761 处 ``async_db_session()`` / ``.begin()`` 调用点**零改动**，
    后台任务、调度器与测试的行为也不变。
    """

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[AsyncSession]:
        ambient = current_request_session()
        if ambient is not None:
            yield ambient
            return
        async with self._factory() as session:
            yield session

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncSession]:
        ambient = current_request_session()
        if ambient is not None:
            # 复用请求会话，但**保持 ``async_sessionmaker.begin()`` 的既有语义：退出即提交**。
            #
            # 若把提交推迟到请求结束，块内写入会一直持有写锁——实测 SQLite 下
            # 直接 ``database is locked``（视频检测回调落库后写操作日志即命中），
            # 且与既有调用约定不符。已有事务时 ``ambient.begin()`` 会退化为
            # SAVEPOINT（见 ``RequestScopedSession``），异常只回滚到保存点。
            async with ambient.begin():
                yield ambient
            await ambient.commit()
            return
        async with self._factory.begin() as session:
            yield session


async_db_session = _SessionFactory(_async_session_factory)


@asynccontextmanager
async def async_db_session_fresh() -> AsyncIterator[AsyncSession]:
    """**显式新建**会话（不复用请求会话）。

    用于必须**独立提交**的写入：典型是 ``OperationLogRoute`` 的操作日志——
    请求即使失败（含未处理异常被回滚）也必须留痕，不能并入请求事务。
    """
    async with _async_session_factory() as session:
        yield session


async def async_pool_warmup(app: FastAPI, status: bool) -> None:
    """启动期并发预热异步 DB 连接池（审计·并发 #11）。

    DB 建连（含 SCRAM-SHA-256 的 PBKDF2，属同步 CPU 计算）在事件循环内串行执行，
    实测约 0.7s/条：若留到首个接入突发再按需建连，会长时间阻塞事件循环，使吞吐
    随并发下降。这里在启动阶段并发签出 ``POOL_SIZE`` 条连接（并发签出才能建出多条；
    顺序复用只会命中同一条）并立即归还，使保留连接一次性建好，请求路径只做复用。

    参数:
    - app (FastAPI): FastAPI 应用实例（事件加载器统一签名，此处不直接使用）。
    - status (bool): True 为启动期执行；False（关停）不处理。

    返回:
    - None
    """
    if not status or not settings.SQL_DB_ENABLE or settings.TESTING:
        return
    if settings.DATABASE_TYPE == "sqlite" or not getattr(settings, "DB_POOL_WARMUP", True):
        return

    target = max(1, int(settings.POOL_SIZE))
    acquired: list = []

    async def _acquire() -> None:
        acquired.append(await async_engine.connect())

    try:
        await asyncio.gather(*[_acquire() for _ in range(target)])
        log.info(f"✅ 数据库连接池预热完成：{len(acquired)} 条保留连接")
    except Exception as e:  # noqa: BLE001 - 预热失败不阻断启动，后续按需建连
        log.warning(f"⚠️ 数据库连接池预热失败（不影响启动，后续按需建连）: {e}")
    finally:
        for conn in acquired:
            try:
                await conn.close()
            except Exception:  # noqa: BLE001 - 归还失败不影响启动
                pass


#: 泄漏连接的判定阈值（秒）：事务开着且**这么久没动静**，必然是泄漏。
#: 正常请求不可能让一个事务空转两分钟。
_LEAK_IDLE_SECONDS = 120
#: 看门狗巡检间隔（秒）
_LEAK_SWEEP_INTERVAL = 60


async def db_leak_watchdog(app: FastAPI, status: bool) -> None:
    """连接泄漏看门狗：把**卡死的空闲事务连接**回收掉，让系统自愈。

    为什么需要它（实测根因，2026-10）：

    - 一个请求最多同时占 **3 条**连接（服务层普遍自己开会话，不复用请求会话）。
    - **正常完成的请求不漏连接**（实测 60 个请求后 ``idle in transaction`` 仍为 0）。
    - 但**被中断的请求会漏**：浏览器翻页/超时取消请求时，ASGI 任务被取消，
      依赖生成器的收尾不一定跑得到，连接被永久留在 ``idle in transaction``。
      实测一次 12 页面的浏览器巡检后残留 10~18 条，并伴随
      ``SAWarning: garbage collector is trying to clean up non-checked-in connection``。
    - 池被这些**永远不会被归还**的连接占满后，所有接口一起超时，
      而且**不会自愈**——只能重启后端。这就是「页面到处报错」的来源。

    ``db_getter`` 已经加了 ``try/finally`` + ``asyncio.shield`` 做第一道防线
    （实测超时数从 19 条降到 4 条），但取消路径上仍有残留，所以这里兜底。

    只回收 ``idle in transaction`` **超过 2 分钟**的连接——这是泄漏的确凿特征，
    不会误伤正常请求。配合 ``POOL_PRE_PING=true``，被回收的连接在下次签出时
    会被自动替换。

    参数:
    - app (FastAPI): 应用实例（统一签名，此处不用）。
    - status (bool): True 为启动期执行。

    返回:
    - None
    """
    if not status or not settings.SQL_DB_ENABLE or settings.TESTING:
        return
    if settings.DATABASE_TYPE != "postgres":
        return

    # ⚠️ 事件加载器是 **await** 每个函数的：这里绝不能自己跑循环，
    # 否则启动会被永久阻塞（真踩过：加了 while True 后端口一直不监听）。
    # 派生后台任务后立即返回，跟其它调度器一个套路。
    asyncio.create_task(_db_leak_sweep_loop())


async def _db_leak_sweep_loop() -> None:
    """看门狗的实际巡检循环（由 :func:`db_leak_watchdog` 派生）。"""
    from sqlalchemy import text as _t

    while True:
        await asyncio.sleep(_LEAK_SWEEP_INTERVAL)
        try:
            async with async_engine.connect() as conn:
                rows = (
                    await conn.execute(
                        _t(
                            "SELECT pid"
                            " FROM pg_stat_activity"
                            " WHERE datname = current_database()"
                            "   AND state = 'idle in transaction'"
                            "   AND pid <> pg_backend_pid()"
                            "   AND now() - state_change > make_interval(secs => :sec)"
                        ),
                        {"sec": _LEAK_IDLE_SECONDS},
                    )
                ).fetchall()
                if not rows:
                    continue
                pids = [r[0] for r in rows]
                for pid in pids:
                    await conn.execute(
                        _t("SELECT pg_terminate_backend(:p)"), {"p": pid}
                    )
                await conn.commit()
                log.warning(
                    f"🧹 连接泄漏看门狗：回收了 {len(pids)} 条卡死连接"
                    f"（idle in transaction > {_LEAK_IDLE_SECONDS}s）：{pids}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - 看门狗自身绝不能拖垮服务
            log.warning(f"连接泄漏看门狗巡检失败（忽略）: {e}")


async def create_tables() -> None:
    """
    创建数据库表（根据 ORM metadata）。

    返回:
    - None
    """
    async with async_engine.begin() as coon:
        await coon.run_sync(MappedBase.metadata.create_all)


async def drop_tables() -> None:
    """
    删除数据库表（根据 ORM metadata）。

    返回:
    - None
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(MappedBase.metadata.drop_all)


async def redis_connect(app: FastAPI, status: bool) -> Redis | None:
    """
    创建或关闭Redis连接。

    参数:
    - app (FastAPI): FastAPI应用实例。
    - status (bool): 连接状态,True为创建连接,False为关闭连接。

    返回:
    - Redis | None: Redis连接实例,如果连接失败则返回None。
    """
    if not settings.REDIS_ENABLE:
        raise CustomException(
            msg="请先开启Redis连接",
            data="请启用 app/core/config.py: REDIS_ENABLE",
        )

    if status:
        try:
            if settings.TESTING:
                # 测试模式：使用内存 Redis，避免依赖外部服务
                import fakeredis.aioredis as fakeredis_aioredis

                rd = fakeredis_aioredis.FakeRedis(decode_responses=True)
                app.state.redis = rd
                if await rd.ping():
                    return rd
            else:
                rd = await Redis.from_url(
                    url=settings.REDIS_URI,
                    encoding="utf-8",
                    decode_responses=True,
                    health_check_interval=20,
                    max_connections=settings.REDIS_MAX_CONNECTIONS,
                    socket_timeout=settings.POOL_TIMEOUT,
                )
                app.state.redis = rd
                if await rd.ping():  # pyright: ignore[reportGeneralTypeIssues]
                    return rd
        except exceptions.AuthenticationError as e:
            log.error(f"❌ 数据库 Redis 认证失败: {e}")
            raise
        except exceptions.TimeoutError as e:
            log.error(f"❌ 数据库 Redis 连接超时: {e}")
            raise
        except exceptions.RedisError as e:
            log.error(f"❌ 数据库 Redis 连接错误: {e}")
            raise
    else:
        close_fn = getattr(app.state.redis, "aclose", None) or app.state.redis.close
        await close_fn()
        log.info("✅️ Redis连接已关闭")
