from collections.abc import AsyncGenerator
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter, WebSocketRateLimiter

from app.config.setting import settings
from app.core.docs import get_custom_ui_html
from app.core.exceptions import handle_exception
from app.core.http_limit import http_limit_callback, ws_limit_callback
from app.core.logger import log
from app.utils.common_util import import_module, import_modules_async
from app.utils.console import console_close, console_run

from .initialize import InitializeData


async def _ensure_missing_columns() -> None:
    """Add new columns to existing tables if they don't exist."""
    from sqlalchemy import text as sa_text

    from app.core.database import async_engine

    new_columns: dict[str, list[tuple[str, str]]] = {
        "video_algorithms": [
            ("model_file_config", "JSONB"),
            ("runtime_config", "JSONB"),
            ("preset_params", "JSONB"),
        ],
        "video_algorithm_tasks": [
            ("runtime_overrides", "JSONB"),
            ("params_overrides", "JSONB"),
        ],
        "video_cameras": [
            ("reachable", "BOOLEAN"),
        ],
    }
    async with async_engine.begin() as conn:
        for table, columns in new_columns.items():
            for col_name, col_type in columns:
                try:
                    await conn.execute(
                        sa_text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
                    )
                except Exception:
                    pass


async def _ensure_deploy_menu() -> None:
    """Ensure the 智能布控 menu entry exists in the database."""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            existing = await db.execute(
                select(MenuModel).where(MenuModel.route_name == "VideoDeploy")
            )
            existing_menu = existing.scalar_one_or_none()
            if existing_menu:
                if existing_menu.icon or not existing_menu.title:
                    existing_menu.icon = None
                if not existing_menu.title:
                    existing_menu.title = "智能布控"
            else:
                parent = await db.execute(
                    select(MenuModel).where(MenuModel.name == "视频监控", MenuModel.type == 1)
                )
                parent_menu = parent.scalar_one_or_none()
                if not parent_menu:
                    log.warning("⚠️  未找到视频监控父菜单，跳过智能布控菜单注册")
                    return

                menu = MenuModel(
                    name="智能布控",
                    type=2,
                    icon=None,
                    order=9,
                    route_name="VideoDeploy",
                    route_path="/video/deploy",
                    component_path="module_video/deploy/index",
                    permission="module_video:deploy:query",
                    parent_id=parent_menu.id,
                    status="0",
                    is_deleted=False,
                    title="智能布控",
                )
                db.add(menu)
                await db.flush()

                from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
                admin_role = await db.execute(
                    select(RoleModel).where(RoleModel.id == 1)
                )
                admin = admin_role.scalar_one_or_none()
                if admin:
                    db.add(RoleMenusModel(role_id=admin.id, menu_id=menu.id))
                log.info("✅ 智能布控菜单已注册")

            # Assign icons to video sub-menus that lack them
            icon_map = {
                "实时预览": "el-icon-VideoCameraFilled",
                "录像回放": "el-icon-VideoPlay",
                "相机管理": "el-icon-CameraFilled",
                "分组管理": "el-icon-FolderOpened",
                "录像计划": "el-icon-Timer",
                "报警管理": "el-icon-BellFilled",
                "算法管理": "el-icon-Aim",
                "布局管理": "el-icon-Grid",
                "事件联动": "el-icon-Connection",
                "智能布控": "el-icon-MagicStick",
            }
            for name, icon in icon_map.items():
                menu_item = await db.execute(
                    select(MenuModel).where(MenuModel.name == name, MenuModel.type == 2)
                )
                item = menu_item.scalar_one_or_none()
                if item and (not item.icon or item.icon != icon):
                    item.icon = icon
            log.info("✅ 视频模块菜单图标已更新")


async def _ensure_annotation_menus() -> None:
    """Ensure the 数据标注 menu entries exist."""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            existing = await db.execute(
                select(MenuModel).where(MenuModel.route_name == "Annotation")
            )
            parent = existing.scalar_one_or_none()
            if parent:
                return

            # 一级菜单
            parent = MenuModel(
                name="数据标注",
                type=1,
                icon="menu-document",
                order=11,
                route_name="Annotation",
                route_path="/annotation",
                redirect="/annotation/dataset",
                permission="",
                status="0",
                is_deleted=False,
                title="数据标注",
            )
            db.add(parent)
            await db.flush()

            # 子菜单
            children = [
                MenuModel(name="数据集管理", type=2, icon="el-icon-FolderOpened", order=1,
                          route_name="AnnotationDataset", route_path="/annotation/dataset",
                          component_path="module_annotation/dataset/index",
                          permission="annotation:dataset:query", parent_id=parent.id,
                          status="0", is_deleted=False, title="数据集管理"),
                MenuModel(name="标注任务", type=2, icon="el-icon-List", order=2,
                          route_name="AnnotationTask", route_path="/annotation/task",
                          component_path="module_annotation/task/index",
                          permission="annotation:task:query", parent_id=parent.id,
                          status="0", is_deleted=False, title="标注任务"),
                MenuModel(name="工作量统计", type=2, icon="el-icon-DataAnalysis", order=3,
                          route_name="AnnotationStats", route_path="/annotation/stats",
                          component_path="module_annotation/stats/index",
                          permission="annotation:stats:query", parent_id=parent.id,
                          status="0", is_deleted=False, title="工作量统计"),
            ]
            for child in children:
                db.add(child)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=child.id))

            # 标注工作台（隐藏路由，不显示在菜单栏）
            workbench = MenuModel(
                name="标注工作台",
                type=2,
                icon=None,
                order=99,
                route_name="AnnotationWorkbench",
                route_path="/annotation/workbench/:id",
                component_path="module_annotation/annotation/index",
                permission="annotation:workbench:query",
                parent_id=parent.id,
                status="0",
                is_deleted=False,
                title="标注工作台",
                hidden=True,
            )
            db.add(workbench)
            await db.flush()
            db.add(RoleMenusModel(role_id=1, menu_id=workbench.id))

            # admin 角色关联父菜单
            db.add(RoleMenusModel(role_id=1, menu_id=parent.id))

    log.info("✅ 数据标注菜单已注册")


async def _ensure_annotation_button_menus() -> None:
    """Ensure button-level permissions for annotation module (always runs)."""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            dataset_menu = await db.scalar(
                select(MenuModel).where(MenuModel.permission == "annotation:dataset:query")
            )
            task_menu = await db.scalar(
                select(MenuModel).where(MenuModel.permission == "annotation:task:query")
            )
            stats_menu = await db.scalar(
                select(MenuModel).where(MenuModel.permission == "annotation:stats:query")
            )
            if not all([dataset_menu, task_menu, stats_menu]):
                log.warning("Parent annotation menus not found, skipping button menus")
                return

            existing = set(
                (await db.execute(
                    select(MenuModel.permission).where(MenuModel.permission.like("module_annotation:%"))
                )).scalars().all()
            )

            buttons = [
                (dataset_menu.id, "查询数据集", 1, "module_annotation:dataset:query"),
                (dataset_menu.id, "创建数据集", 2, "module_annotation:dataset:create"),
                (dataset_menu.id, "编辑数据集", 3, "module_annotation:dataset:update"),
                (dataset_menu.id, "删除数据集", 4, "module_annotation:dataset:delete"),
                (dataset_menu.id, "上传图片", 5, "module_annotation:dataset:upload"),
                (task_menu.id, "查询任务", 1, "module_annotation:task:query"),
                (task_menu.id, "创建任务", 2, "module_annotation:task:create"),
                (task_menu.id, "编辑任务", 3, "module_annotation:task:update"),
                (task_menu.id, "删除任务", 4, "module_annotation:task:delete"),
                (task_menu.id, "批量操作", 5, "module_annotation:task:patch"),
                (task_menu.id, "进入标注", 6, "module_annotation:task:workbench"),
                (stats_menu.id, "查询统计", 1, "module_annotation:stats:query"),
            ]

            for parent_id, name, order, perm in buttons:
                if perm in existing:
                    continue
                menu = MenuModel(name=name, type=3, order=order, permission=perm,
                                 parent_id=parent_id, status="0", is_deleted=False)
                db.add(menu)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=menu.id))

            log.info(f"✅ 标注按钮权限已注册 ({len(buttons)} 项)")


async def _ensure_train_menus() -> None:
    """Ensure the training module menu entries exist."""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            existing = await db.execute(
                select(MenuModel).where(MenuModel.route_name == "Train")
            )
            if existing.scalar_one_or_none():
                return

            parent = MenuModel(
                name="模型训练", type=1, icon="el-icon-Aim", order=12,
                route_name="Train", route_path="/train", redirect="/train/task",
                permission="", status="0", is_deleted=False, title="模型训练",
            )
            db.add(parent)
            await db.flush()

            children = [
                MenuModel(name="模型仓库", type=2, icon="el-icon-Box", order=1,
                          route_name="TrainRepo", route_path="/train/repo",
                          component_path="module_train/repo/index",
                          permission="module_train:model:query", parent_id=parent.id,
                          status="0", is_deleted=False, title="模型仓库"),
                MenuModel(name="训练任务", type=2, icon="el-icon-Notebook", order=2,
                          route_name="TrainTask", route_path="/train/task",
                          component_path="module_train/task/index",
                          permission="module_train:task:query", parent_id=parent.id,
                          status="0", is_deleted=False, title="训练任务"),
                MenuModel(name="模型评估", type=2, icon="el-icon-DataBoard", order=3,
                          route_name="TrainEval", route_path="/train/eval",
                          component_path="module_train/eval/index",
                          permission="module_train:eval:query", parent_id=parent.id,
                          status="0", is_deleted=False, title="模型评估"),
            ]
            for child in children:
                db.add(child)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=child.id))

            detail = MenuModel(
                name="训练详情", type=2, icon=None, order=99,
                route_name="TrainTaskDetail", route_path="/train/task/:id",
                component_path="module_train/task/detail",
                permission="module_train:task:query", parent_id=parent.id,
                status="0", is_deleted=False, title="训练详情", hidden=True,
            )
            db.add(detail)
            await db.flush()
            db.add(RoleMenusModel(role_id=1, menu_id=detail.id))

            db.add(RoleMenusModel(role_id=1, menu_id=parent.id))

            button_perms = [
                ("module_train:model:query", "查询模型"),
                ("module_train:model:create", "创建模型"),
                ("module_train:model:delete", "删除模型"),
                ("module_train:task:query", "查询任务"),
                ("module_train:task:create", "创建任务"),
                ("module_train:task:update", "更新任务"),
                ("module_train:task:delete", "删除任务"),
                ("module_train:eval:query", "查询评估"),
                ("module_train:eval:create", "创建评估"),
                ("module_train:eval:delete", "删除评估"),
            ]
            for perm_code, perm_name in button_perms:
                existing_perm = await db.execute(
                    select(MenuModel).where(MenuModel.permission == perm_code)
                )
                if existing_perm.first() is None:
                    pm = MenuModel(name=perm_name, type=3, icon=None, order=99,
                                   route_name="", route_path="", component_path="",
                                   permission=perm_code, parent_id=parent.id,
                                   status="0", is_deleted=False, title=perm_name)
                    db.add(pm)
                    await db.flush()
                    db.add(RoleMenusModel(role_id=1, menu_id=pm.id))

    log.info("✅ 训练模块菜单已注册")


NOTIFY_PARAMS = [
    ("notify_smtp_host", "SMTP服务器", ""),
    ("notify_smtp_port", "SMTP端口", "587"),
    ("notify_smtp_user", "SMTP用户名", ""),
    ("notify_smtp_pass", "SMTP密码", ""),
    ("notify_smtp_from", "发件人地址", ""),
    ("notify_smtp_from_name", "发件人名称", "告警通知"),
    ("notify_smtp_ssl", "SMTP启用SSL", "0"),
    ("notify_admin_email", "管理员邮箱", ""),
    ("notify_sms_api_url", "SMS API地址", ""),
    ("notify_sms_access_key", "SMS AccessKey", ""),
    ("notify_sms_secret", "SMS Secret", ""),
    ("notify_sms_sign", "SMS签名", ""),
    ("notify_sms_template", "SMS模板", ""),
    ("notify_webhook_default_url", "Webhook默认URL", ""),
    ("notify_webhook_default_method", "Webhook默认方法", "POST"),
    ("notify_webhook_retry_count", "Webhook重试次数", "3"),
    ("notify_webhook_retry_interval", "Webhook重试间隔(秒)", "5"),
    ("notify_webhook_secret", "Webhook共享密钥", ""),
    ("notify_ws_enabled", "WebSocket推送启用", "1"),
]


async def _ensure_notification_params() -> None:
    from sqlalchemy import select

    from app.api.v1.module_system.params.model import ParamsModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            for key, name, default in NOTIFY_PARAMS:
                existing = await db.execute(
                    select(ParamsModel).where(ParamsModel.config_key == key)
                )
                if not existing.scalar_one_or_none():
                    db.add(ParamsModel(
                        config_name=name,
                        config_key=key,
                        config_value=default,
                        config_type=True,
                        status="0",
                        description="通知配置",
                    ))
        log.info("✅ 通知系统参数已确保")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[Any, Any]:
    """
    自定义 FastAPI 应用生命周期。

    参数:
    - app (FastAPI): FastAPI 应用实例。

    返回:
    - AsyncGenerator[Any, Any]: 生命周期上下文生成器。
    """
    from app.api.v1.module_system.dict.service import DictDataService
    from app.api.v1.module_system.params.service import ParamsService
    from app.core.ap_scheduler import SchedulerUtil

    try:
        await InitializeData().init_db()
        log.info(f"✅ {settings.DATABASE_TYPE}数据库初始化完成")
        await _ensure_missing_columns()
        await _ensure_deploy_menu()
        await _ensure_notification_params()
        await _ensure_annotation_menus()
        await _ensure_annotation_button_menus()
        await _ensure_train_menus()
        await import_modules_async(
            modules=settings.EVENT_LIST, desc="全局事件", app=app, status=True
        )
        log.info("✅ 全局事件模块加载完成")
        await ParamsService().init_config_service(redis=app.state.redis)
        log.info("✅ Redis系统配置初始化完成")
        await DictDataService().init_dict_service(redis=app.state.redis)
        log.info("✅ Redis数据字典初始化完成")
        await SchedulerUtil.init_scheduler(redis=app.state.redis)
        log.info("✅ 定时任务调度器初始化完成")
        await FastAPILimiter.init(
            redis=app.state.redis,
            prefix=settings.REQUEST_LIMITER_REDIS_PREFIX,
            http_callback=http_limit_callback,
            ws_callback=ws_limit_callback,
        )
        log.info("✅ 请求限流器初始化完成")

        import asyncio

        from app.api.v1.module_video.record.scheduler import start_record_scheduler
        asyncio.create_task(start_record_scheduler())
        log.info("✅ 录制定时器已启动")

        from app.api.v1.module_video.inference.scheduler import start_inference_scheduler
        asyncio.create_task(start_inference_scheduler())
        log.info("✅ 推理调度器已启动")

        from app.api.v1.module_video.camera.health_checker import start_camera_health_checker
        asyncio.create_task(start_camera_health_checker())
        log.info("✅ 摄像头健康检查器已启动")

        from app.plugin.module_train.scheduler import start_scheduler
        asyncio.create_task(start_scheduler())
        log.info("✅ 训练调度器已启动")

        # 导入并显示最终的启动信息面板
        from app.common.enums import EnvironmentEnum

        console_run(
            host=settings.SERVER_HOST,
            port=settings.SERVER_PORT,
            reload=settings.ENVIRONMENT == EnvironmentEnum.DEV,
            database_ready=True,
            redis_ready=True,
            scheduler_ready=SchedulerUtil.is_running(),
            limiter_ready=True,
        )

    except Exception as e:
        log.error(f"❌ 应用初始化失败: {e!s}")
        raise SystemExit(1)

    yield

    try:
        await SchedulerUtil.shutdown(wait=False)
        log.info("✅ 定时任务调度器已关闭")
        from app.api.v1.module_video.record.scheduler import stop_record_scheduler
        await stop_record_scheduler()
        log.info("✅ 录制定时器已关闭")

        from app.api.v1.module_video.inference.scheduler import stop_inference_scheduler
        await stop_inference_scheduler()
        log.info("✅ 推理调度器已关闭")

        from app.api.v1.module_video.camera.health_checker import stop_camera_health_checker
        await stop_camera_health_checker()
        log.info("✅ 摄像头健康检查器已关闭")
        await FastAPILimiter.close()
        log.info("✅ 请求限制器已关闭")
        await import_modules_async(modules=settings.EVENT_LIST, desc="全局事件", app=app, status=False)
        log.info("✅ 全局事件模块卸载完成")
        console_close()

    except Exception as e:
        log.error(f"❌ 应用关闭过程中发生错误: {e!s}")


def register_middlewares(app: FastAPI) -> None:
    """
    注册全局中间件。

    参数:
    - app (FastAPI): FastAPI 应用实例。

    返回:
    - None
    """
    for middleware in settings.MIDDLEWARE_LIST[::-1]:
        if not middleware:
            continue
        middleware = import_module(middleware, desc="中间件")
        app.add_middleware(middleware)


def register_exceptions(app: FastAPI) -> None:
    """
    统一注册异常处理器。

    参数:
    - app (FastAPI): FastAPI 应用实例。

    返回:
    - None
    """
    handle_exception(app)


def register_routers(app: FastAPI) -> None:
    """
    注册根路由。

    参数:
    - app (FastAPI): FastAPI 应用实例。

    返回:
    - None
    """
    from app.api.v1.module_application import application_router
    from app.api.v1.module_common import common_router
    from app.api.v1.module_monitor import monitor_router
    from app.api.v1.module_system import system_router
    from app.api.v1.module_video import _register_video_routers, video_router

    _register_video_routers()
    app.include_router(common_router, dependencies=[Depends(RateLimiter(times=5, seconds=10))])
    app.include_router(application_router, dependencies=[Depends(RateLimiter(times=5, seconds=10))])
    app.include_router(system_router, dependencies=[Depends(RateLimiter(times=5, seconds=10))])
    app.include_router(monitor_router, dependencies=[Depends(RateLimiter(times=5, seconds=10))])
    app.include_router(video_router, dependencies=[Depends(RateLimiter(times=5, seconds=10))])

    from app.api.v1.module_annotation import _register_annotation_routers, annotation_router
    _register_annotation_routers()
    app.include_router(annotation_router, dependencies=[Depends(RateLimiter(times=5, seconds=10))])

    from app.plugin.module_ai.chat.ws import WS_AI

    # 手动注册WebSocket路由，不使用速率限制器
    app.include_router(
        router=WS_AI, dependencies=[Depends(WebSocketRateLimiter(times=1, seconds=5))]
    )

    from app.api.v1.module_video.alarm.ws import AlarmWSRouter

    app.include_router(AlarmWSRouter)
    # 先将动态路由注册到应用，使用速率限制器
    from app.core.discover import get_dynamic_router

    # 获取动态路由实例
    app.include_router(
        router=get_dynamic_router(),
        dependencies=[Depends(RateLimiter(times=5, seconds=10))],
    )


def register_files(app: FastAPI) -> None:
    """
    注册静态资源挂载和文件相关配置。

    参数:
    - app (FastAPI): FastAPI 应用实例。

    返回:
    - None
    """
    # 挂载静态文件目录
    if settings.STATIC_ENABLE:
        settings.STATIC_ROOT.mkdir(parents=True, exist_ok=True)
        app.mount(
            path=settings.STATIC_URL,
            app=StaticFiles(directory=settings.STATIC_ROOT),
            name=settings.STATIC_DIR,
        )
     # 挂载录制文件目录 — try simpler path
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.api.v1.module_video.record.service import RECORDINGS_DIR

    @app.get("/recordings/{stream_id}/{file_name}")
    async def serve_recording(stream_id: str, file_name: str):
        fp = RECORDINGS_DIR / stream_id / Path(file_name).name
        if fp.exists() and fp.is_file():
            return FileResponse(str(fp), media_type="video/mp4")
        return HTMLResponse(status_code=404)


def reset_api_docs(app: FastAPI) -> None:
    """
    使用本地静态资源自定义 API 文档页面（Swagger UI 与 ReDoc）。

    参数:
    - app (FastAPI): FastAPI 应用实例。

    返回:
    - None
    """

    @app.get(str(app.swagger_ui_oauth2_redirect_url), include_in_schema=False)
    async def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()

    @app.get(settings.DOCS_URL, include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=str(app.root_path) + str(app.openapi_url),
            title=app.title + " - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url=settings.SWAGGER_JS_URL,
            swagger_css_url=settings.SWAGGER_CSS_URL,
            swagger_favicon_url=settings.FAVICON_URL,
        )

    @app.get(settings.REDOC_URL, include_in_schema=False)
    async def custom_redoc_html():
        return get_redoc_html(
            openapi_url=str(app.root_path) + str(app.openapi_url),
            title=app.title + " - ReDoc",
            redoc_js_url=settings.REDOC_JS_URL,
            redoc_favicon_url=settings.FAVICON_URL,
        )

    @app.get(settings.LJDOC_URL, include_in_schema=False)
    async def custom_ui_html():
        return get_custom_ui_html(
            openapi_url=str(app.root_path) + str(app.openapi_url),
            title=app.title + " - LangJin UI",
            swagger_js_url=settings.CUSTOM_JS_URL,
            swagger_css_url=settings.CUSTOM_CSS_URL,
            swagger_favicon_url=settings.FAVICON_URL
        )
