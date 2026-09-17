import asyncio

from fastapi import FastAPI
from redis import exceptions
from redis.asyncio import Redis
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.config.setting import settings
from app.core.base_model import MappedBase
from app.core.exceptions import CustomException
from app.core.logger import log


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
            class_=AsyncSession,
        )
        return async_engine, AsyncSessionLocal


engine, db_session = create_engine_and_session(settings.DB_URI)
async_engine, async_db_session = create_async_engine_and_session(settings.ASYNC_DB_URI)


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
