import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import suppress

from fastapi import Depends, Query, Request
from redis.asyncio.client import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_system.user.crud import UserCRUD
from app.api.v1.module_system.user.model import UserModel
from app.common.enums import RedisInitKeyConfig
from app.config.setting import settings
from app.core.database import async_db_session, current_request_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.redis_crud import RedisCURD
from app.core.security import OAuth2Schema, decode_access_token


async def db_getter() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话连接

    返回:
    - AsyncSession: 数据库会话连接

    ⚠️ **这里的清理必须做到"无论如何都归还连接"。**

    实测根因（2026-10，pg_stat_activity 采样）：请求被**取消**时（浏览器翻页/关闭、
    前端 abort），依赖生成器的收尾不一定跑得到，连接就被永久留在
    ``idle in transaction``，池占满后**所有接口一起超时，而且不会自愈，必须重启后端**。
    这就是「页面到处报错、接口全超时」的真正来源。

    证据：一次 12 页面的浏览器巡检后，PG 侧残留 10 条 ``idle in transaction``，
    最后执行的 SQL 都是认证的 ``SELECT sys_role_1.id ...``（即本依赖借出的那条连接）；
    后端日志同时出现 22 次
    ``SAWarning: The garbage collector is trying to clean up non-checked-in connection``
    —— 会话对象被 GC 掉而从未归还。

    所以这里用 ``try/finally`` + ``asyncio.shield``：
    - ``finally`` 保证正常返回、抛异常、以及生成器被 ``aclose()`` 三种情况都执行；
    - ``shield`` 保证即使当前任务已被取消，关闭动作也能跑完（否则 await 会立刻
      再次抛 CancelledError，连接照样漏）。

    自 2026-10 起还有**请求作用域会话**（``DBSessionMiddleware``）：请求内
    ``current_request_session()`` 已有会话时**直接复用**（避免二次 ``begin()`` 抛
    ``InvalidRequestError``）。复用时**提交/回滚仍在本依赖收尾完成**——因为 FastAPI
    在返回响应前就关闭依赖 exit stack，此处的提交早于「路由处理器写操作日志」，
    否则写日志会撞上请求会话未释放的写锁；连接的**关闭**则交给中间件。
    """
    ambient = current_request_session()
    if ambient is not None:
        # 复用请求会话；**提交/回滚仍在依赖收尾完成**（与既有语义一致）。
        #
        # 为什么不能把提交推迟到中间件：FastAPI 0.115 在 ``return response`` 之前
        # 就关闭依赖 exit stack（``fastapi/routing.py`` 的 ``async with AsyncExitStack()``
        # 包住 ``return response``），因此这里的收尾发生在「路由处理器继续写操作日志」
        # **之前**。若推迟到中间件（在路由处理器**之后**），操作日志会用另一条连接写入，
        # 而请求会话仍持有写锁——SQLite 下实测直接 ``database is locked``（全量回归
        # 243 个 error）。
        #
        # 连接**关闭**由 ``DBSessionMiddleware`` 负责（取消路径也能保证归还）。
        try:
            yield ambient
        except BaseException:
            with suppress(Exception):
                await asyncio.shield(ambient.rollback())
            raise
        else:
            with suppress(Exception):
                await asyncio.shield(ambient.commit())
        return

    async with async_db_session() as session:
        try:
            async with session.begin():
                yield session
        finally:
            with suppress(Exception):
                await asyncio.shield(session.close())


async def redis_getter(request: Request) -> Redis:
    """获取Redis连接

    参数:
    - request (Request): 请求对象

    返回:
    - Redis: Redis连接
    """
    return request.app.state.redis


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(db_getter),
    redis: Redis = Depends(redis_getter),
    token: str = Depends(OAuth2Schema),
) -> AuthSchema:
    """获取当前用户

    参数:
    - request (Request): 请求对象
    - db (AsyncSession): 数据库会话
    - redis (Redis): Redis连接
    - token (str): 访问令牌

    返回:
    - AuthSchema: 认证信息模型
    """
    if not token:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)

    # 处理Bearer token
    if token.startswith("Bearer"):
        token = token.split(" ")[1]

    payload = decode_access_token(token)
    if not payload or not hasattr(payload, "is_refresh") or payload.is_refresh:
        raise CustomException(msg="非法凭证", code=10401, status_code=401)

    online_user_info = payload.sub
    # 从Redis中获取用户信息
    user_info = json.loads(online_user_info)  # 确保是字典类型

    session_id = user_info.get("session_id")
    if not session_id:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)

    # 检查用户是否在线
    online_ok = await RedisCURD(redis).exists(
        key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}"
    )
    if not online_ok:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)

    # 如果启用了滑动过期，自动续期token
    if settings.TOKEN_SLIDING_EXPIRE:
        await RedisCURD(redis).expire(
            key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}",
            expire=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        await RedisCURD(redis).expire(
            key=f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}",
            expire=settings.REFRESH_TOKEN_EXPIRE_MINUTES,
        )

    # 关闭数据权限过滤，避免当前用户查询被拦截
    auth = AuthSchema(db=db, check_data_scope=False)
    username = user_info.get("user_name")
    if not username:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)
    # 获取用户信息，使用深层预加载确保RoleModel.creator被正确加载
    user = await UserCRUD(auth).get_by_username_crud(
        username=username,
        preload=[
            "dept",
            selectinload(UserModel.roles),
            "positions",
            "created_by",
        ],
    )
    if not user:
        raise CustomException(msg="用户不存在", code=10401, status_code=401)
    if user.status == "1":
        raise CustomException(msg="用户已被停用", code=10401, status_code=401)

    # 设置请求上下文
    request.scope["user_id"] = user.id
    request.scope["user_username"] = user.username

    # 过滤可用的角色和职位
    if hasattr(user, "roles"):
        user.roles = [role for role in user.roles if role and role.status]
    if hasattr(user, "positions"):
        user.positions = [pos for pos in user.positions if pos and pos.status]

    auth.user = user
    return auth


async def get_current_user_ws(
    token: str = Query(..., description="认证token"),
    db: AsyncSession = Depends(db_getter),
    redis: Redis = Depends(redis_getter),
) -> AuthSchema:
    """获取当前用户（WebSocket专用，从查询参数获取token）

    参数:
    - token (str): 认证token
    - db (AsyncSession): 数据库会话
    - redis (Redis): Redis连接

    返回:
    - AuthSchema: 认证信息模型
    """
    return await _verify_token(token, db, redis)


async def _verify_token(
    token: str,
    db: AsyncSession,
    redis: Redis,
) -> AuthSchema:
    """验证token并返回用户信息

    参数:
    - token (str): 认证token
    - db (AsyncSession): 数据库会话
    - redis (Redis): Redis连接

    返回:
    - AuthSchema: 认证信息模型
    """
    if not token:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)

    # 处理Bearer token（如果通过查询参数传递时包含Bearer前缀）
    if token.startswith("Bearer"):
        token = token.split(" ")[1]

    payload = decode_access_token(token)
    if not payload or not hasattr(payload, "is_refresh") or payload.is_refresh:
        raise CustomException(msg="非法凭证", code=10401, status_code=401)

    online_user_info = payload.sub
    # 从Redis中获取用户信息
    user_info = json.loads(online_user_info)  # 确保是字典类型

    session_id = user_info.get("session_id")
    if not session_id:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)

    # 检查用户是否在线
    online_ok = await RedisCURD(redis).exists(
        key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}"
    )
    if not online_ok:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)

    # 如果启用了滑动过期，自动续期token
    if settings.TOKEN_SLIDING_EXPIRE:
        await RedisCURD(redis).expire(
            key=f"{RedisInitKeyConfig.ACCESS_TOKEN.key}:{session_id}",
            expire=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        await RedisCURD(redis).expire(
            key=f"{RedisInitKeyConfig.REFRESH_TOKEN.key}:{session_id}",
            expire=settings.REFRESH_TOKEN_EXPIRE_MINUTES,
        )

    # 关闭数据权限过滤，避免当前用户查询被拦截
    auth = AuthSchema(db=db, check_data_scope=False)
    username = user_info.get("user_name")
    if not username:
        raise CustomException(msg="认证已失效", code=10401, status_code=401)
    # 获取用户信息，使用深层预加载确保RoleModel.creator被正确加载
    user = await UserCRUD(auth).get_by_username_crud(
        username=username,
        preload=[
            "dept",
            selectinload(UserModel.roles),
            "positions",
            "created_by",
        ],
    )
    if not user:
        raise CustomException(msg="用户不存在", code=10401, status_code=401)
    if user.status == "1":
        raise CustomException(msg="用户已被停用", code=10401, status_code=401)

    # 设置请求上下文
    # request.scope["user_id"] = user.id
    # request.scope["user_username"] = user.username

    # 过滤可用的角色和职位
    if hasattr(user, "roles"):
        user.roles = [role for role in user.roles if role and role.status]
    if hasattr(user, "positions"):
        user.positions = [pos for pos in user.positions if pos and pos.status]

    auth.user = user
    return auth


class AuthPermission:
    """权限验证类"""

    def __init__(
        self,
        permissions: list[str] | None = None,
        check_data_scope: bool = True,
    ) -> None:
        """
        初始化权限验证

        参数:
        - permissions (list[str] | None): 权限标识列表。
        - check_data_scope (bool): 是否启用严格模式校验。
        """
        self.permissions = permissions or []
        self.check_data_scope = check_data_scope

    async def __call__(self, auth: AuthSchema = Depends(get_current_user)) -> AuthSchema:
        """
        调用权限验证

        参数:
        - auth (AuthSchema): 认证信息对象。

        返回:
        - AuthSchema: 认证信息对象。
        """
        auth.check_data_scope = self.check_data_scope

        # 超级管理员直接通过
        if auth.user and auth.user.is_superuser:
            return auth

        # 无需验证权限
        if not self.permissions:
            return auth

        # 超级管理员权限标识
        if "*" in self.permissions or "*:*:*" in self.permissions:
            return auth

        # 检查用户是否有角色
        if not auth.user or not auth.user.roles:
            raise CustomException(msg="无权限操作", code=10403, status_code=403)

        # 获取用户权限集合
        user_permissions = {
            menu.permission
            for role in auth.user.roles
            for menu in role.menus
            if role.status == "0" and menu.permission and menu.status == "0"
        }

        # 统一「数据标注」权限命名：后端用 annotation:X，前端按钮/种子菜单用
        # module_annotation:X，二者互为别名；「上传」按钮权限同时满足「创建」。
        # （仅放宽，不收紧，保证 admin/既有角色不受影响。）
        expanded: set[str] = set(self.permissions)
        for p in self.permissions:
            if p.startswith("annotation:"):
                expanded.add("module_annotation:" + p[len("annotation:"):])
            if p == "annotation:dataset:create":
                expanded.add("module_annotation:dataset:upload")

        # 权限验证 - 满足任一权限即可
        if not any(perm in user_permissions for perm in expanded):
            log.warning(
                f"权限拒绝 user={auth.user.id} name={auth.user.name} "
                f"required={self.permissions} actual={sorted(user_permissions)}"
            )
            raise CustomException(msg="无权限操作", code=10403, status_code=403)

        return auth
