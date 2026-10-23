import asyncio
import json
import time
from contextlib import suppress

from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1.module_system.params.service import ParamsService
from app.common.response import ErrorResponse
from app.config.setting import settings
from app.core.database import (
    activate_request_session,
    async_db_session,
    deactivate_request_session,
)
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.security import decode_access_token


class CustomCORSMiddleware(CORSMiddleware):
    """CORS跨域中间件"""

    def __init__(self, app: ASGIApp) -> None:
        allow_credentials = settings.ALLOW_CREDENTIALS
        if "*" in settings.ALLOW_ORIGINS and allow_credentials:
            # 通配来源 + 允许凭据会被浏览器视为对任意站点开放凭据（并回显 Origin），
            # 这里强制降级为不携带凭据；需要凭据时应配置显式域名白名单。
            log.warning(
                "[安全告警] ALLOW_ORIGINS 为通配 '*'，已强制关闭 ALLOW_CREDENTIALS；"
                "如需携带凭据请配置显式域名白名单。"
            )
            allow_credentials = False
        super().__init__(
            app,
            allow_origins=settings.ALLOW_ORIGINS,
            allow_methods=settings.ALLOW_METHODS,
            allow_headers=settings.ALLOW_HEADERS,
            allow_credentials=allow_credentials,
            expose_headers=settings.CORS_EXPOSE_HEADERS,
        )


class RequestLogMiddleware:
    """请求日志中间件（**纯 ASGI**，不要改回 BaseHTTPMiddleware）。

    为什么必须纯 ASGI：``BaseHTTPMiddleware`` 把下游放进**新任务**执行，而且 starlette 的
    ``_CachedRequest`` **只在中间件自己先看到断开时**，才把 ``http.disconnect`` 转发给下游
    （源码里的 ``_is_disconnected`` 判断）。本中间件从不消费 ``receive``，于是流式端点（SSE）
    永远收不到断开通知：客户端关掉页面后，服务端既不会抛 ``GeneratorExit``，也不会被
    ``StreamingResponse.listen_for_disconnect`` 取消——运行会白跑到底（实测：断开 12 秒后
    运行记录仍是 running）。纯 ASGI 直接透传 ``receive``，断开照常传播，这类问题从根上消失。

    职责：请求日志、演示模式/IP 黑白名单拦截、``X-Process-Time`` 响应头、响应日志。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 非 HTTP（lifespan / websocket）直接透传
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        start_time = time.time()
        session_id = self._extract_session_id_from_request(request)

        log.info(
            f"请求来源: {request.client.host if request.client else '未知'},"
            f"请求方法: {request.method},"
            f"请求路径: {request.url.path}"
        )

        started = False
        try:
            blocked = await self._blocked_response(request, session_id)
            if blocked is not None:
                await blocked(scope, receive, send)
                return

            async def send_wrapper(message: Message) -> None:
                nonlocal started
                if message["type"] == "http.response.start":
                    started = True
                    process_time = round(time.time() - start_time, 5)
                    # 补处理耗时头（原实现是改 Response 对象，纯 ASGI 只能改响应消息头）
                    MutableHeaders(scope=message)["X-Process-Time"] = str(process_time)
                    content_length = Headers(raw=message["headers"]).get("content-length", "0")
                    log.info(
                        f"响应状态: {message['status']}, 响应内容长度: {content_length}, "
                        f"处理时间: {round(process_time * 1000, 3)}ms"
                    )
                await send(message)

            await self.app(scope, receive, send_wrapper)
        except CustomException as e:
            log.exception(f"中间件处理异常: {e!s}")
            # 不回显异常细节，避免泄露内部实现/敏感信息；已开始发送响应就不能再发错误响应
            if not started:
                await ErrorResponse(msg="系统异常，请联系管理员")(scope, receive, send)

    async def _blocked_response(self, request: Request, session_id: str | None):
        """演示模式 / IP 黑白名单拦截：返回响应表示拦截，``None`` 表示放行。"""
        path = request.scope.get("path")
        request_ip = (
            x_forwarded_for.split(",")[0].strip()
            if (x_forwarded_for := request.headers.get("X-Forwarded-For"))
            else request.client.host
            if request.client
            else None
        )

        demo_enable = False
        ip_white_list: list = []
        white_api_list_path: list = []
        ip_black_list: list = []
        config_error = False

        try:
            # 从应用实例获取Redis连接
            redis = request.app.state.redis
            if not redis:
                raise CustomException(msg="无法获取Redis连接")

            # 使用ParamsService获取系统配置
            system_config = await ParamsService.get_system_config_for_middleware(redis)
            # 提取配置值
            demo_enable = system_config["demo_enable"]
            ip_white_list = system_config["ip_white_list"]
            white_api_list_path = system_config["white_api_list_path"]
            ip_black_list = system_config["ip_black_list"]
        except Exception as e:  # noqa: BLE001
            config_error = True
            log.error(f"获取系统配置失败，按 fail-closed 拦截: {e}")

        should_block = False
        block_reason = ""

        # F8：配置读取失败时 fail-closed（默认拒绝），避免黑名单/演示限制被绕过
        if config_error:
            should_block = True
            block_reason = "系统安全配置读取失败，已按 fail-closed 拒绝请求"
        # 1. 首先检查IP是否在黑名单中
        elif request_ip and request_ip in ip_black_list:
            should_block = True
            block_reason = f"IP地址 {request_ip} 在黑名单中"

        # 2. 如果不在黑名单中，检查是否在演示模式下需要拦截
        elif demo_enable in ["true", "True"] and request.method != "GET":
            # 在演示模式下，非GET请求需要检查白名单
            is_ip_whitelisted = request_ip in ip_white_list
            is_path_whitelisted = path in white_api_list_path

            if not is_ip_whitelisted and not is_path_whitelisted:
                should_block = True
                block_reason = f"演示模式下拦截非GET请求，IP: {request_ip}, 路径: {path}"

        if not should_block:
            return None

        # 增强安全审计：记录详细的拦截日志
        log.warning(
            " | ".join(
                [
                    f"会话ID: {session_id or '未认证'}",
                    f"请求被拦截: {block_reason}",
                    f"请求来源: {request_ip}",
                    f"请求方法: {request.method}",
                    f"请求路径: {path}",
                    f"用户代理: {request.headers.get('user-agent', '未知')}",
                    f"演示模式: {demo_enable}",
                ]
            )
        )
        # 拦截请求
        if config_error:
            return ErrorResponse(msg="系统安全策略暂时不可用，请稍后重试")
        return ErrorResponse(msg="演示环境，禁止操作")

    @staticmethod
    def _extract_session_id_from_request(request: Request) -> str | None:
        """
        从请求中提取session_id（支持从Token或已设置的scope中获取）

        参数:
        - request (Request): 请求对象

        返回:
        - str | None: 会话ID，如果无法提取则返回None
        """
        # 1. 先检查 scope 中是否已经有 session_id（登录接口会设置）
        session_id = request.scope.get("session_id")
        if session_id:
            return session_id

        # 2. 尝试从 Authorization Header 中提取
        try:
            authorization = request.headers.get("Authorization")
            if not authorization:
                return None

            # 处理Bearer token
            token = authorization.replace("Bearer ", "").strip()

            # 解码token
            payload = decode_access_token(token)
            if not payload or not hasattr(payload, "sub"):
                return None

            # 从payload中提取session_id
            user_info = json.loads(payload.sub)
            session_id = user_info.get("session_id")

            # 同时设置到request.scope中，避免后续重复解析
            if session_id:
                request.scope["session_id"] = session_id

            return session_id
        except Exception:
            # 解析失败静默处理，返回None（可能是未认证请求）
            return None


class AdmissionGateMiddleware:
    """并发准入闸门：**超过连接池承载能力就立刻 503**，不让请求排队到超时。

    为什么需要它（2026-10 实测根因）：

    - PostgreSQL 每次建连都要算 SCRAM-SHA-256 的 PBKDF2，本机 **846ms/条（672ms 纯 CPU）**，
      并且这段 CPU 在事件循环里**同步执行、完全串行**（5 条并发建连实测 = 5×1392ms）。
    - 连接池打满后，后续请求只能等 `POOL_TIMEOUT`（30 秒）才报错；而前端 10 秒就超时了，
      于是用户看到的是「请求超时」，服务端却还挂着一堆等连接的请求——两边都白等。
    - 本中间件在**进请求前**按池容量放行：拿得到槽位就处理，`GATE_WAIT_SECONDS` 内拿不到
      就**立刻**回 503 + `Retry-After`，由前端按服务繁忙重试，而不是排队 10 秒再超时。

    为什么在最外层：它要拦在 CORS / 日志 / 会话中间件之前，连被拒的请求都不必建会话。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        #: 槽位数：默认取池大小，但应显式小于 POOL_SIZE，给「一个请求内部再开会话」留余量
        self._slots = max(1, int(getattr(settings, "GATE_SLOTS", 0) or settings.POOL_SIZE))
        self._wait = float(getattr(settings, "GATE_WAIT_SECONDS", 0.6))
        self._sem: asyncio.Semaphore = asyncio.Semaphore(self._slots)

    async def _reject(self, scope: Scope, send: Send) -> None:
        body = json.dumps(
            {
                "code": 503,
                "msg": f"服务繁忙：已有 {self._slots} 个并发请求在处理，请稍后重试",
                "data": None,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (b"retry-after", str(max(1, int(self._wait)) or 1).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 非 HTTP（lifespan / websocket）与 CORS 预检一律放行
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self._wait)
        except TimeoutError:
            await self._reject(scope, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._sem.release()


class DBSessionMiddleware:
    """请求作用域会话中间件：一请求一条连接，且保证归还。

    必须是**纯 ASGI 中间件**：``BaseHTTPMiddleware`` 会把下游放进新任务执行，
    使 ContextVar 的「owner task」判定失配（端点任务 ≠ 中间件任务），
    服务层就无法复用请求会话。

    行为（配合 ``app.core.database`` 的请求作用域会话）：

    - ``http`` 请求：建一条会话 → 登记请求会话（记录 owner task）→ 交给下游；
      正常结束提交、异常回滚；``finally`` 里关闭并归还连接。
      用 ``asyncio.shield`` 保证即使当前任务已被取消（浏览器翻页/关闭/超时），
      关闭动作仍能跑完——这正是连接泄漏的根因路径。
    - 非 ``http``（lifespan / websocket）：直接透传，不建会话。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 此处尚未登记请求会话，拿到的是真会话（不会被复用成自身）。
        async with async_db_session() as session:
            token = activate_request_session(session)
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
                deactivate_request_session(token)
                with suppress(Exception):
                    await asyncio.shield(session.close())


class CustomGZipMiddleware(GZipMiddleware):
    """GZip压缩中间件"""

    # 媒体内容流式端点不压缩：这类端点以 StreamingResponse 逐块返回原始字节，
    # 若被 GZip 包裹会二次压缩（音频本身多有损压缩，压缩收益极低且浪费 CPU），
    # 且中间件会删除 Content-Length 并缓冲流式响应，违背「流式 + Content-Length」
    # 的设计。此处按路径前缀跳过 GZip。
    _NO_COMPRESS_PREFIXES = (
        "/api/v1/annotation/audio/content/",
    )

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(
            app,
            minimum_size=settings.GZIP_MIN_SIZE,
            compresslevel=settings.GZIP_COMPRESS_LEVEL,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if any(path.startswith(p) for p in self._NO_COMPRESS_PREFIXES):
                await self.app(scope, receive, send)
                return
            # SSE（text/event-stream）一律不压缩：GZip 会缓冲流式响应，把"逐帧到达"
            # 变成"结束时一次性到达"（前端看不到实时进度）。此前只靠流式响应自带的
            # `Content-Encoding: identity` 头让 GZip 跳过——那是**约定**，一旦该头被
            # 改动就会静默退回缓冲，故这里按 Accept 再兜一道，不依赖约定。
            accept = ""
            for k, v in scope.get("headers") or []:
                if k == b"accept":
                    accept = v.decode("latin-1").lower()
                    break
            if "text/event-stream" in accept:
                await self.app(scope, receive, send)
                return
        await super().__call__(scope, receive, send)
