from collections.abc import AsyncGenerator, Iterable
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
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

# 注册 JSONB→JSON、SQLite 注释降级等跨方言编译规则（SQLite/MySQL 下 create_all 需要）
from app.alembic import dialect_compat  # noqa: F401
from app.config.setting import settings
from app.core.docs import get_custom_ui_html
from app.core.exceptions import handle_exception
from app.core.http_limit import http_limit_callback, ws_limit_callback
from app.core.logger import log
from app.utils.common_util import import_module, import_modules_async
from app.utils.console import console_close, console_run

from .initialize import InitializeData

# 既有库「不跑 Alembic、仅重启后端」的兜底补列清单：
# 模型新增的可空/带默认列必须同步登记在此，server_default 与 Alembic 迁移保持一致。
ENSURE_NEW_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "video_algorithms": [
        ("model_file_config", "JSONB"),
        ("runtime_config", "JSONB"),
        ("preset_params", "JSONB"),
        ("scene_type", "VARCHAR(64)"),
        # 与 Alembic 38d18b9077de / b2c3d4e5f6a7 对齐
        ("param_meta", "JSONB"),
        ("previous_model_path", "VARCHAR(512)"),
        ("previous_version", "VARCHAR(32)"),
    ],
    "video_algorithm_tasks": [
        ("runtime_overrides", "JSONB"),
        ("params_overrides", "JSONB"),
        ("edge_device_id", "INTEGER"),
        ("error_log", "TEXT"),
    ],
    "video_cameras": [
        ("reachable", "BOOLEAN"),
    ],
    "video_alarm_rules": [
        ("conditions", "JSONB"),
        # 与 Alembic 1164d4a7539d / 183fb76b1184 / d6d5f85952f5 对齐
        ("params", "JSONB NOT NULL DEFAULT '{}'"),
        ("rollout", "JSONB NOT NULL DEFAULT '{}'"),
        ("group_id", "INTEGER"),
    ],
    # train_predicts 兜底建表 DDL 为旧版，补齐模型声明的列（与 a3f3956bb77b 对齐）
    "train_predicts": [
        ("description", "TEXT"),
        ("progress", "INTEGER NOT NULL DEFAULT 0"),
        ("error_log", "TEXT"),
    ],
    "ai_models": [
        ("extra_headers", "JSONB"),
        ("provider_id", "INTEGER"),
        ("usage", "VARCHAR(16)"),
        ("capabilities", "JSONB"),
        ("context_window", "INTEGER"),
    ],
    "ai_call_logs": [
        ("user_id", "INTEGER"),
    ],
    "ai_reports": [
        ("app_id", "INTEGER"),
        ("session_id", "INTEGER"),
    ],
    "ai_tools": [
        ("source", "VARCHAR(16) DEFAULT 'system'"),
        ("config", "JSONB"),
    ],
    # B4：底库表新增 kind 判别列（face/reid，复用同一张表；与迁移 c1d2e3f4a5b6 对齐）
    "video_face_gallery": [
        ("kind", "VARCHAR(16) NOT NULL DEFAULT 'face'"),
    ],
}


async def _exec_ddl(sql: str, label: str) -> bool:
    """单条 DDL 用**独立事务**执行；失败仅告警并返回 False。

    PostgreSQL 中一条语句失败会让当前事务进入 aborted 状态，后续语句全部报
    ``InFailedSqlTransaction``，块尾 COMMIT 实际变 ROLLBACK——同块内先前成功的
    语句会被一并丢弃且不留痕迹。逐条独立事务可隔离单条失败，保证其余补列不被
    静默回滚，并留下明确日志（H1）。
    """
    from sqlalchemy import text as sa_text

    from app.core.database import async_engine

    try:
        async with async_engine.begin() as conn:
            await conn.execute(sa_text(sql))
        return True
    except Exception as e:
        log.warning(f"[补列/建表] {label} 执行失败，已跳过: {e}")
        return False


async def _ensure_missing_columns() -> None:
    """为既有表幂等补齐模型新增列（逐列独立事务，失败必留日志）。

    ``ENSURE_NEW_COLUMNS`` 是「既有库不跑 Alembic、仅重启后端」的兜底清单，
    必须与 Alembic 迁移保持同步；漏登会导致运行期随机 ``UndefinedColumn`` 500。
    """
    from sqlalchemy import text as sa_text

    from app.core.database import async_engine

    is_sqlite = settings.DATABASE_TYPE == "sqlite"
    for table, columns in ENSURE_NEW_COLUMNS.items():
        for col_name, col_type in columns:
            if is_sqlite:
                # SQLite 不支持 ADD COLUMN IF NOT EXISTS，先探测现有列（失败则跳过整表该列）
                try:
                    async with async_engine.begin() as conn:
                        rows = (
                            await conn.execute(sa_text(f"PRAGMA table_info({table})"))
                        ).fetchall()
                    if col_name in {r[1] for r in rows}:
                        continue
                except Exception as e:
                    log.warning(f"[补列] {table}.{col_name} 列探测失败，已跳过: {e}")
                    continue
                await _exec_ddl(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}",
                    f"{table}.{col_name}",
                )
            else:
                await _exec_ddl(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type}",
                    f"{table}.{col_name}",
                )

    # 存量 HTTP 工具迁移：source 默认 system，需按 kind='http' 修正为 http
    await _exec_ddl(
        "UPDATE ai_tools SET source='http' "
        "WHERE kind='http' AND (source IS NULL OR source='system')",
        "ai_tools.source 修正",
    )

    # Drop unused columns + ensure re-added columns
    await _exec_ddl(
        "ALTER TABLE annotation_dataset DROP COLUMN IF EXISTS annotation_type",
        "annotation_dataset.annotation_type 清理",
    )
    await _exec_ddl(
        "ALTER TABLE annotation_task ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'pending'",
        "annotation_task.status",
    )
    await _exec_ddl(
        "ALTER TABLE annotation_task ADD COLUMN IF NOT EXISTS progress INTEGER DEFAULT 0",
        "annotation_task.progress",
    )

    # 边缘设备表兜底（旧库无 Alembic 迁移时直接建表，做法同 train_predicts）
    # DDL 与 EdgeDeviceModel 对齐：uuid NOT NULL UNIQUE，审计/状态字段 NOT NULL 并建立索引
    await _exec_ddl(
        """
        CREATE TABLE IF NOT EXISTS video_edge_devices (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(16) NOT NULL DEFAULT 'offline',
            description TEXT,
            created_time TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_time TIMESTAMP NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_time TIMESTAMP,
            created_id INTEGER,
            updated_id INTEGER,
            deleted_id INTEGER,
            name VARCHAR(128) NOT NULL,
            code VARCHAR(64) NOT NULL UNIQUE,
            control_url VARCHAR(512),
            secret VARCHAR(128),
            capabilities JSONB,
            metrics JSONB,
            last_heartbeat TIMESTAMP
        )
        """,
        "video_edge_devices 建表",
    )
    for col in ("uuid", "status", "created_time", "updated_time", "is_deleted", "deleted_time"):
        await _exec_ddl(
            f"CREATE INDEX IF NOT EXISTS ix_video_edge_devices_{col} ON video_edge_devices ({col})",
            f"video_edge_devices.{col} 索引",
        )

    # 人脸底库表兜底（旧库无 Alembic 迁移时直接建表，做法同 video_edge_devices）
    # DDL 与 FaceGalleryModel / 迁移 b3c1d2e3f4a5 对齐；外键依赖 create_all（此处省略，仅保数据）
    await _exec_ddl(
        """
        CREATE TABLE IF NOT EXISTS video_face_gallery (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(64) NOT NULL UNIQUE,
            status VARCHAR(10) NOT NULL DEFAULT '0',
            description TEXT,
            created_time TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_time TIMESTAMP NOT NULL DEFAULT NOW(),
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_time TIMESTAMP,
            created_id INTEGER,
            updated_id INTEGER,
            deleted_id INTEGER,
            name VARCHAR(128) NOT NULL,
            person_no VARCHAR(64),
            kind VARCHAR(16) NOT NULL DEFAULT 'face',
            model_key VARCHAR(64) NOT NULL DEFAULT 'unknown',
            embedding JSONB NOT NULL,
            dimension INTEGER NOT NULL,
            face_image_url VARCHAR(512)
        )
        """,
        "video_face_gallery 建表",
    )
    for col in ("uuid", "status", "created_time", "updated_time", "is_deleted", "deleted_time", "name", "person_no", "kind"):
        await _exec_ddl(
            f"CREATE INDEX IF NOT EXISTS ix_video_face_gallery_{col} ON video_face_gallery ({col})",
            f"video_face_gallery.{col} 索引",
        )

    await _ensure_camera_group_parent_fk()


CAMERA_GROUP_PARENT_FK = "fk_video_camera_groups_parent_id"


async def _ensure_camera_group_parent_fk() -> None:
    """兜底补建 ``video_camera_groups.parent_id`` 自引用外键（审计 M7）。

    仅对「不跑迁移、只靠 create_all + 兜底」的既有库生效：create_all 建的新库已含该
    外键、跑过迁移的库已由 ``e6f7a8b9c0d1`` 补建，此处按存在性探测幂等跳过。SQLite
    不支持 ``ALTER ADD CONSTRAINT``，其外键依赖 create_all 建表时声明。
    """
    from sqlalchemy import inspect as sa_inspect

    from app.core.database import async_engine

    def _needs_fk(conn) -> bool:
        insp = sa_inspect(conn)
        if not insp.has_table("video_camera_groups"):
            return False
        if "parent_id" not in {c["name"] for c in insp.get_columns("video_camera_groups")}:
            return False
        return not any(
            tuple(fk.get("constrained_columns") or ()) == ("parent_id",)
            for fk in insp.get_foreign_keys("video_camera_groups")
        )

    try:
        async with async_engine.connect() as conn:
            needed = await conn.run_sync(_needs_fk)
    except Exception as e:
        log.warning(f"[补列] video_camera_groups.parent_id 外键探测失败，已跳过: {e}")
        return
    if needed:
        await _exec_ddl(
            "ALTER TABLE video_camera_groups ADD CONSTRAINT "
            f"{CAMERA_GROUP_PARENT_FK} FOREIGN KEY (parent_id) "
            "REFERENCES video_camera_groups(id) ON DELETE RESTRICT",
            "video_camera_groups.parent_id 外键",
        )


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


EDGE_BUTTON_PERMS: list[tuple[str, str]] = [
    ("module_video:edge:query", "查询边缘设备"),
    ("module_video:edge:create", "创建边缘设备"),
    ("module_video:edge:update", "编辑边缘设备"),
    ("module_video:edge:delete", "删除边缘设备"),
]


async def _ensure_edge_button_menus() -> None:
    """确保边缘设备按钮权限存在（挂在视频监控父菜单下）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            parent = await db.scalar(
                select(MenuModel).where(MenuModel.name == "视频监控", MenuModel.type == 1)
            )
            if not parent:
                log.warning("⚠️  未找到视频监控父菜单，跳过边缘设备按钮权限注册")
                return

            existing = set(
                (await db.execute(
                    select(MenuModel.permission).where(MenuModel.permission.like("module_video:edge:%"))
                )).scalars().all()
            )
            for order, (perm_code, perm_name) in enumerate(EDGE_BUTTON_PERMS, start=1):
                if perm_code in existing:
                    continue
                menu = MenuModel(
                    name=perm_name, type=3, icon=None, order=order,
                    route_name="", route_path="", component_path="",
                    permission=perm_code, parent_id=parent.id,
                    status="0", is_deleted=False, title=perm_name,
                )
                db.add(menu)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=menu.id))
            log.info("✅ 边缘设备按钮权限已注册")


async def _ensure_edge_page_menu() -> None:
    """确保『边缘设备』页面菜单存在（挂在视频监控父菜单下，分配 admin）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            existing = await db.execute(
                select(MenuModel).where(MenuModel.route_name == "VideoEdge")
            )
            if existing.scalar_one_or_none():
                return
            parent = await db.scalar(
                select(MenuModel).where(MenuModel.name == "视频监控", MenuModel.type == 1)
            )
            if not parent:
                log.warning("⚠️  未找到视频监控父菜单，跳过边缘设备菜单注册")
                return
            menu = MenuModel(
                name="边缘设备",
                type=2,
                icon="el-icon-Cpu",
                order=10,
                route_name="VideoEdge",
                route_path="/video/edge",
                component_path="module_video/edge/index",
                permission="module_video:edge:query",
                parent_id=parent.id,
                status="0",
                is_deleted=False,
                title="边缘设备",
            )
            db.add(menu)
            await db.flush()
            admin = await db.scalar(select(RoleModel).where(RoleModel.id == 1))
            if admin:
                db.add(RoleMenusModel(role_id=admin.id, menu_id=menu.id))
            log.info("✅ 边缘设备菜单已注册")


async def _ensure_edge_event_page_menu() -> None:
    """确保『边缘事件』页面菜单存在（挂在视频监控父菜单下，分配 admin；幂等）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            existing = await db.execute(
                select(MenuModel).where(MenuModel.route_name == "VideoEdgeEvent")
            )
            if existing.scalar_one_or_none():
                return
            parent = await db.scalar(
                select(MenuModel).where(MenuModel.name == "视频监控", MenuModel.type == 1)
            )
            if not parent:
                log.warning("⚠️  未找到视频监控父菜单，跳过边缘事件菜单注册")
                return
            menu = MenuModel(
                name="边缘事件",
                type=2,
                icon="el-icon-DataLine",
                order=11,
                route_name="VideoEdgeEvent",
                route_path="/video/event-stream",
                component_path="module_video/event_stream/index",
                permission="module_video:edge:query",
                parent_id=parent.id,
                status="0",
                is_deleted=False,
                title="边缘事件",
            )
            db.add(menu)
            await db.flush()
            admin = await db.scalar(select(RoleModel).where(RoleModel.id == 1))
            if admin:
                db.add(RoleMenusModel(role_id=admin.id, menu_id=menu.id))
            log.info("✅ 边缘事件菜单已注册")


FACE_GALLERY_BUTTON_PERMS: list[tuple[str, str]] = [
    ("module_video:face_gallery:query", "查询人脸底库"),
    ("module_video:face_gallery:create", "录入/编辑人脸底库"),
    ("module_video:face_gallery:delete", "删除人脸底库"),
]


async def _ensure_face_gallery_menus() -> None:
    """确保『人脸底库』页面菜单与按钮权限存在（挂在视频监控父菜单下，分配 admin；幂等）。

    页面路由 `/video/face-gallery` 对应前端 `module_video/face_gallery/index`，
    用于维护 FACE_REC/STRANGER 规则所依赖的人脸特征底库。
    """
    from sqlalchemy import select

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel, RoleModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            parent = await db.scalar(
                select(MenuModel).where(MenuModel.name == "视频监控", MenuModel.type == 1)
            )
            if not parent:
                log.warning("⚠️  未找到视频监控父菜单，跳过人脸底库菜单注册")
                return

            page = await db.scalar(
                select(MenuModel).where(MenuModel.route_name == "VideoFaceGallery")
            )
            if not page:
                page = MenuModel(
                    name="人脸底库",
                    type=2,
                    icon="el-icon-Postcard",
                    order=12,
                    route_name="VideoFaceGallery",
                    route_path="/video/face-gallery",
                    component_path="module_video/face_gallery/index",
                    permission="module_video:face_gallery:query",
                    parent_id=parent.id,
                    status="0",
                    is_deleted=False,
                    title="人脸底库",
                )
                db.add(page)
                await db.flush()
                admin = await db.scalar(select(RoleModel).where(RoleModel.id == 1))
                if admin:
                    db.add(RoleMenusModel(role_id=admin.id, menu_id=page.id))
                log.info("✅ 人脸底库菜单已注册")

            existing = set(
                (
                    await db.execute(
                        select(MenuModel.permission).where(
                            MenuModel.permission.like("module_video:face_gallery:%")
                        )
                    )
                )
                .scalars()
                .all()
            )
            for order, (perm_code, perm_name) in enumerate(FACE_GALLERY_BUTTON_PERMS, start=1):
                if perm_code in existing:
                    continue
                menu = MenuModel(
                    name=perm_name,
                    type=3,
                    icon=None,
                    order=order,
                    route_name="",
                    route_path="",
                    component_path="",
                    permission=perm_code,
                    parent_id=parent.id,
                    status="0",
                    is_deleted=False,
                    title=perm_name,
                )
                db.add(menu)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=menu.id))
            log.info("✅ 人脸底库按钮权限已注册")


AI_BUTTON_PERMS: list[tuple[str, str]] = [
    ("module_ai:model:query", "查询大模型配置"),
    ("module_ai:model:create", "新增大模型配置"),
    ("module_ai:model:update", "编辑大模型配置"),
    ("module_ai:model:delete", "删除大模型配置"),
    ("module_ai:prompt:create", "新增提示词"),
    ("module_ai:prompt:update", "编辑提示词"),
    ("module_ai:prompt:delete", "删除提示词"),
    ("module_ai:assistant:query", "AI助手对话"),
    ("module_ai:tool:query", "查询工具"),
    ("module_ai:tool:create", "新增工具"),
    ("module_ai:tool:update", "编辑工具"),
    ("module_ai:tool:delete", "删除工具"),
    ("module_ai:app:query", "查询AI应用"),
    ("module_ai:app:create", "新增AI应用"),
    ("module_ai:app:update", "编辑AI应用"),
    ("module_ai:app:delete", "删除AI应用"),
]

# 已下线的 AI 页面路由名：存量库置 hidden=True（新库不再创建对应菜单）
REMOVED_ROUTE_NAMES: list[str] = ["AiOverview", "AiPlayground", "AiProvider", "AiReport", "Memory"]


async def _ensure_ai_menus() -> None:
    """确保 AI 管理保留的 5 个页面与按钮权限存在，并隐藏已下线页面（chat 来自种子数据）。"""
    from sqlalchemy import select, update

    from app.api.v1.module_system.menu.model import MenuModel
    from app.api.v1.module_system.role.model import RoleMenusModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        async with db.begin():
            parent = await db.scalar(
                select(MenuModel).where(MenuModel.route_name == "AI", MenuModel.type == 1)
            )
            if not parent:
                log.warning("⚠️  未找到 AI 父菜单，跳过 AI 菜单注册")
                return

            # 父菜单固定落地智能助手；chat 保持可见，已下线页面统一隐藏
            await db.execute(
                update(MenuModel)
                .where(MenuModel.route_name == "AI", MenuModel.type == 1)
                .values(redirect="/ai/chat")
            )
            await db.execute(
                update(MenuModel)
                .where(MenuModel.component_path == "module_ai/chat/index")
                .values(hidden=False)
            )
            # 智能助手菜单权限与流式/会话接口对齐（旧的 module_ai:chat:* 页面已不再使用）
            await db.execute(
                update(MenuModel)
                .where(MenuModel.route_name == "Chat")
                .values(permission="module_ai:assistant:query")
            )
            chat_menu = await db.scalar(
                select(MenuModel).where(MenuModel.route_name == "Chat")
            )
            if chat_menu:
                link = await db.scalar(
                    select(RoleMenusModel).where(
                        RoleMenusModel.role_id == 1,
                        RoleMenusModel.menu_id == chat_menu.id,
                    )
                )
                if not link:
                    db.add(RoleMenusModel(role_id=1, menu_id=chat_menu.id))
            await db.execute(
                update(MenuModel)
                .where(MenuModel.route_name.in_(REMOVED_ROUTE_NAMES))
                .values(hidden=True)
            )

            pages = [
                ("模型配置", "AiModel", "/ai/model", "module_ai/model/index", "module_ai:model:query", 10),
                ("提示词", "AiPrompt", "/ai/prompt", "module_ai/prompt/index", "module_ai:prompt:query", 13),
                ("工具中心", "AiTool", "/ai/tool", "module_ai/tool/index", "module_ai:tool:query", 14),
                ("AI应用", "AiApp", "/ai/app", "module_ai/app/index", "module_ai:app:query", 15),
                ("调用日志", "AiLogs", "/ai/logs", "module_ai/logs/index", "module_ai:assistant:query", 16),
            ]
            for title, rname, rpath, comp, perm, order in pages:
                exists = await db.scalar(
                    select(MenuModel).where(MenuModel.route_name == rname)
                )
                if exists:
                    continue
                m = MenuModel(
                    name=title,
                    type=2,
                    icon=None,
                    order=order,
                    route_name=rname,
                    route_path=rpath,
                    component_path=comp,
                    permission=perm,
                    parent_id=parent.id,
                    status="0",
                    is_deleted=False,
                    title=title,
                )
                db.add(m)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=m.id))

            existing = set(
                (
                    await db.execute(
                        select(MenuModel.permission).where(
                            MenuModel.permission.like("module_ai:%")
                        )
                    )
                ).scalars().all()
            )
            for order, (perm_code, perm_name) in enumerate(AI_BUTTON_PERMS, start=1):
                if perm_code in existing:
                    continue
                m = MenuModel(
                    name=perm_name,
                    type=3,
                    icon=None,
                    order=order,
                    route_name="",
                    route_path="",
                    component_path="",
                    permission=perm_code,
                    parent_id=parent.id,
                    status="0",
                    is_deleted=False,
                    title=perm_name,
                )
                db.add(m)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=m.id))
            log.info("✅ AI 菜单与权限已注册")


async def _ensure_ai_tools() -> None:
    """幂等同步内置工具到 ai_tools：仅补缺失行，不覆盖已存在行的 enabled 状态。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY
    from app.plugin.module_ai.tools_catalog.model import AiToolModel

    async with async_db_session() as db:
        async with db.begin():
            existing = set((await db.execute(select(AiToolModel.name))).scalars().all())
            added = 0
            for tool_name in TOOL_REGISTRY:
                if tool_name in existing:
                    continue
                db.add(
                    AiToolModel(
                        name=tool_name,
                        kind="builtin",
                        source="system",
                        method="GET",
                        url="",
                        enabled=True,
                    )
                )
                added += 1
            if added:
                log.info(f"✅ 已注册 {added} 个内置 AI 工具")
            else:
                log.info("✅ 内置 AI 工具已就绪")


async def _ensure_agno_tools() -> None:
    """幂等同步 Agno 精选工具到 ai_tools：仅补缺失行，默认停用，不覆盖已有配置。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.agno_tools.registry import AGNO_CATALOG
    from app.plugin.module_ai.tools_catalog.model import AiToolModel

    async with async_db_session() as db:
        async with db.begin():
            existing = set((await db.execute(select(AiToolModel.name))).scalars().all())
            added = 0
            for spec in AGNO_CATALOG:
                if spec["key"] in existing:
                    continue
                db.add(
                    AiToolModel(
                        name=spec["key"],
                        kind="agno",
                        source="agno",
                        method="GET",
                        url="",
                        enabled=False,
                        description=spec.get("description") or spec["title"],
                    )
                )
                added += 1
            if added:
                log.info(f"✅ 已注册 {added} 个 Agno 精选 AI 工具")
            else:
                log.info("✅ Agno 精选 AI 工具已就绪")


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
                icon="el-icon-EditPen",
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


TRAIN_BUTTON_PERMS: list[tuple[str, str]] = [
    ("module_train:model:query", "查询模型"),
    ("module_train:model:create", "创建模型"),
    ("module_train:model:update", "编辑模型"),
    ("module_train:model:delete", "删除模型"),
    ("module_train:task:query", "查询任务"),
    ("module_train:task:create", "创建任务"),
    ("module_train:task:update", "更新任务"),
    ("module_train:task:delete", "删除任务"),
    ("module_train:eval:query", "查询评估"),
    ("module_train:eval:create", "创建评估"),
    ("module_train:eval:delete", "删除评估"),
    ("module_train:predict:query", "查询预测"),
    ("module_train:predict:create", "创建预测"),
    ("module_train:predict:delete", "删除预测"),
]

# (name, route_name, route_path, component_path, permission, hidden)
TRAIN_EXTRA_MENUS: list[tuple[str, str, str, str, str, bool]] = [
    ("模型预测", "TrainPredict", "/train/predict", "module_train/predict/index", "module_train:predict:query", False),
    ("模型部署", "TrainDeploy", "/train/deploy", "module_train/deploy/index", "module_train:model:query", False),
    ("训练详情", "TrainTaskDetail", "/train/task/:id", "module_train/task/detail", "module_train:task:query", True),
    ("评估详情", "TrainEvalDetail", "/train/eval/:id", "module_train/eval/detail", "module_train:eval:query", True),
    ("预测详情", "TrainPredictDetail", "/train/predict/:id", "module_train/predict/detail", "module_train:predict:query", True),
]


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
            parent = existing.scalar_one_or_none()

            if parent is None:
                parent = MenuModel(
                    name="模型训练", type=1, icon="el-icon-Aim", order=12,
                    route_name="Train", route_path="/train", redirect="/train/task",
                    permission="", status="0", is_deleted=False, title="模型训练",
                )
                db.add(parent)
                await db.flush()

                # Seed all sub-menus (first run)
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
                    MenuModel(name="模型预测", type=2, icon="el-icon-VideoCamera", order=4,
                              route_name="TrainPredict", route_path="/train/predict",
                              component_path="module_train/predict/index",
                              permission="module_train:predict:query", parent_id=parent.id,
                              status="0", is_deleted=False, title="模型预测"),
                    MenuModel(name="模型部署", type=2, icon="el-icon-Upload", order=5,
                              route_name="TrainDeploy", route_path="/train/deploy",
                              component_path="module_train/deploy/index",
                              permission="module_train:model:query", parent_id=parent.id,
                              status="0", is_deleted=False, title="模型部署"),
                ]
                for child in children:
                    db.add(child)
                    await db.flush()
                    db.add(RoleMenusModel(role_id=1, menu_id=child.id))

                # Detail / extra pages（与已存在分支共用 TRAIN_EXTRA_MENUS，避免清单分叉）
                for name, route_name, route_path, component_path, permission, hidden in TRAIN_EXTRA_MENUS:
                    existing_menu = await db.execute(
                        select(MenuModel).where(MenuModel.route_name == route_name)
                    )
                    if existing_menu.scalar_one_or_none():
                        continue
                    dm = MenuModel(
                        name=name, type=2, icon=None, order=99,
                        route_name=route_name, route_path=route_path,
                        component_path=component_path,
                        permission=permission, parent_id=parent.id,
                        status="0", is_deleted=False, title=name, hidden=hidden,
                    )
                    db.add(dm)
                    await db.flush()
                    db.add(RoleMenusModel(role_id=1, menu_id=dm.id))

                db.add(RoleMenusModel(role_id=1, menu_id=parent.id))

                for perm_code, perm_name in TRAIN_BUTTON_PERMS:
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
                return

            # ── Parent already exists: add any missing sub-menus ──
            for name, route_name, route_path, component_path, permission, hidden in TRAIN_EXTRA_MENUS:
                existing_menu = await db.execute(
                    select(MenuModel).where(MenuModel.route_name == route_name)
                )
                if existing_menu.scalar_one_or_none():
                    continue
                mm = MenuModel(
                    name=name, type=2, icon=None, order=99,
                    route_name=route_name, route_path=route_path,
                    component_path=component_path, permission=permission,
                    parent_id=parent.id, status="0", is_deleted=False,
                    title=name, hidden=hidden,
                )
                db.add(mm)
                await db.flush()
                db.add(RoleMenusModel(role_id=1, menu_id=mm.id))

            # Add missing permissions
            for perm_code, perm_name in TRAIN_BUTTON_PERMS:
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

            log.info("✅ 训练模块缺失菜单已补全")


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

    edge_event_consumer = None

    try:
        await InitializeData().init_db()
        log.info(f"✅ {settings.DATABASE_TYPE}数据库初始化完成")
        await _ensure_missing_columns()
        # I1：create_all 建的库无 alembic_version，直接 upgrade head 会在 base create_table
        # 处 DuplicateTable。schema 与当前模型一致时补写 head（使升级成安全空操作）；
        # schema 落后则拒绝并给出指引，绝不把落后库误标为 head 而跳过迁移。
        from app.core.database import async_engine as _stamp_engine
        from app.scripts.schema_stamp import StampState, ensure_schema_stamp

        _stamp = await ensure_schema_stamp(_stamp_engine)
        if _stamp.state is StampState.SCHEMA_MATCHES_HEAD:
            log.info(f"✅ 已为 create_all 库补写 Alembic 版本戳: {_stamp.revision}")
        elif _stamp.state is StampState.LEGACY_MISMATCH:
            log.warning(f"⚠️  {_stamp.message} 缺失项: {_stamp.missing}")
        else:
            log.info(f"ℹ️  Alembic 版本戳检查: {_stamp.state.value}")
        # 作用域不变量启动校验：发现历史「双空/双非空」告警规则并告警
        from app.api.v1.module_video.alarm.service import validate_rule_scope_invariant
        await validate_rule_scope_invariant()
        await _ensure_deploy_menu()
        await _ensure_edge_button_menus()
        await _ensure_edge_page_menu()
        await _ensure_edge_event_page_menu()
        await _ensure_face_gallery_menus()
        await _ensure_ai_menus()
        await _ensure_ai_tools()
        await _ensure_agno_tools()
        await _ensure_notification_params()
        await _ensure_annotation_menus()
        await _ensure_annotation_button_menus()
        await _ensure_train_menus()
        # 人脸底库进程内缓存（face_match/stranger 叶子求值依赖）；表缺失时告警不阻断启动
        try:
            from app.api.v1.module_video.face_gallery.service import FaceGalleryService

            loaded = await FaceGalleryService.refresh_cache()
            log.info(f"✅ 人脸底库缓存已加载（{loaded} 条）")
        except Exception as e:
            log.warning(f"⚠️  人脸底库缓存加载失败（底库为空或表未迁移）: {e}")
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

        from app.api.v1.module_video.edge.consumer import EdgeEventConsumer
        edge_event_consumer = EdgeEventConsumer()
        await edge_event_consumer.start()
        log.info("✅ 边缘事件消费者已启动")

        from app.api.v1.module_video.inference.registry import inference_backend_available
        if not inference_backend_available():
            log.warning("⚠️  智能分析推理库 modeldeploy(FastDeploy) 不可用，视频布控推理将无法启动")

        # 云边模式下心跳写入端无凭证，攻击者可伪造设备上报，启动时显式告警
        if settings.VIDEO_ANALYSIS_MODE == "cloud_edge" and not settings.EDGE_CONTROL_TOKEN:
            log.warning("⚠️ 边缘心跳未配置 EDGE_CONTROL_TOKEN，存在被伪造风险")

        from app.api.v1.module_video.inference.scheduler import start_inference_scheduler
        asyncio.create_task(start_inference_scheduler())
        log.info("✅ 推理调度器已启动")

        from app.api.v1.module_video.camera.health_checker import start_camera_health_checker
        asyncio.create_task(start_camera_health_checker())
        log.info("✅ 摄像头健康检查器已启动")

        from app.plugin.module_train.scheduler import start_scheduler
        asyncio.create_task(start_scheduler())
        log.info("✅ 训练调度器已启动")

        from app.plugin.module_train.paddlex_executor import (
            PaddleXOCRDetExecutor,
            PaddleXOCRRecExecutor,
        )
        asyncio.create_task(PaddleXOCRDetExecutor.start_recovery_loop())
        asyncio.create_task(PaddleXOCRRecExecutor.start_recovery_loop())
        log.info("✅ OCR 训练调度器已启动")

        from app.plugin.module_train.eval_scheduler import start_evaluation_scheduler
        asyncio.create_task(start_evaluation_scheduler())
        log.info("✅ 评估调度器已启动")

        from app.plugin.module_train.predict_executor import start_prediction_scheduler
        asyncio.create_task(start_prediction_scheduler())
        log.info("✅ 预测调度器已启动")

        from app.plugin.module_train.deploy_executor import start_deploy_recovery
        asyncio.create_task(start_deploy_recovery())
        log.info("✅ 部署孤儿回收已启动")

        from app.plugin.module_train.cleanup import cleanup_loop
        asyncio.create_task(cleanup_loop())
        log.info("✅ 临时训练产物目录清理已启动")

        from app.api.v1.module_video.edge.retention import start_edge_event_retention
        start_edge_event_retention()
        log.info("✅ 边缘事件 TTL 清理已启动")

        from app.api.v1.module_video.alarm.retention import start_alarm_record_retention
        start_alarm_record_retention()
        log.info("✅ 告警记录 TTL 清理已启动")

        try:
            from app.core.database import async_engine as _train_engine
            from app.plugin.module_train.schema_check import ensure_train_columns

            await ensure_train_columns(_train_engine)

            # train_predicts 兜底建表：DDL 与 TrainPredictModel 对齐（逐条独立事务，失败留日志）
            await _exec_ddl(
                """
                CREATE TABLE IF NOT EXISTS train_predicts (
                    id SERIAL PRIMARY KEY,
                    uuid VARCHAR(64) NOT NULL,
                    status VARCHAR(10) NOT NULL DEFAULT 'PENDING',
                    description TEXT,
                    created_time TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_time TIMESTAMP NOT NULL DEFAULT NOW(),
                    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    deleted_time TIMESTAMP,
                    created_id INTEGER,
                    updated_id INTEGER,
                    deleted_id INTEGER,
                    model_repo_id INTEGER NOT NULL,
                    model_id INTEGER NOT NULL,
                    framework VARCHAR(16) NOT NULL DEFAULT 'ULTRALYTICS',
                    source_type VARCHAR(16) NOT NULL,
                    source_dataset_id INTEGER,
                    source_images JSONB,
                    result_images JSONB,
                    result_zip_path VARCHAR(512),
                    hyperparams JSONB,
                    progress INTEGER NOT NULL DEFAULT 0,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    log TEXT,
                    error_log TEXT
                )
                """,
                "train_predicts 建表",
            )
            for col in (
                "uuid", "status", "created_time", "updated_time",
                "is_deleted", "deleted_time", "created_id", "updated_id", "deleted_id",
            ):
                await _exec_ddl(
                    f"CREATE INDEX IF NOT EXISTS ix_train_predicts_{col} ON train_predicts ({col})",
                    f"train_predicts.{col} 索引",
                )
        except Exception as e:
            log.warning(f"train migration warning: {e}")

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

        if edge_event_consumer:
            await edge_event_consumer.stop()
            log.info("✅ 边缘事件消费者已关闭")

        from app.api.v1.module_video.edge.retention import stop_edge_event_retention
        await stop_edge_event_retention()
        log.info("✅ 边缘事件 TTL 清理已关闭")

        from app.api.v1.module_video.alarm.retention import stop_alarm_record_retention
        await stop_alarm_record_retention()
        log.info("✅ 告警记录 TTL 清理已关闭")

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


def resolve_rate_limit(module: str, method: str, paths: Iterable[str]) -> dict[str, int]:
    """解析某请求实际生效的限流参数。

    优先按 ``"METHOD /path"`` 精确匹配 ``settings.RATE_LIMIT_PATH_OVERRIDES``
    （设备接入/回调路径独立限额），否则回退到 ``settings.RATE_LIMIT_OVERRIDES[module]``。
    传入的 ``paths`` 可含/不含 ``ROOT_PATH`` 前缀，均会归一化后匹配。

    参数:
    - module (str): 模块名。
    - method (str): HTTP 方法。
    - paths (Iterable[str]): 候选请求路径（如 ``scope["path"]`` 与 ``url.path``）。

    返回:
    - dict[str, int]: ``{"times": N, "seconds": M}``。
    """
    from app.config.setting import settings

    root = settings.ROOT_PATH.rstrip("/")
    normalized: set[str] = set()
    for path in paths:
        if not path:
            continue
        normalized.add(path)
        if root and path.startswith(root):
            normalized.add(path[len(root):] or "/")
    method = method.upper()
    for path in normalized:
        cfg = settings.RATE_LIMIT_PATH_OVERRIDES.get(f"{method} {path}")
        if cfg:
            return {"times": cfg["times"], "seconds": cfg["seconds"]}
    ov = settings.RATE_LIMIT_OVERRIDES.get(module, {})
    return {
        "times": ov.get("times", settings.REQUEST_RATE_LIMIT_TIMES),
        "seconds": ov.get("seconds", settings.REQUEST_RATE_LIMIT_SECONDS),
    }


def _rate_limit(module: str = "default"):
    """按「路径优先、模块兜底」生成限流依赖（支持 settings 动态配置）。

    设备接入/回调路径（边缘事件回调、心跳、录像 webhook）由
    ``RATE_LIMIT_PATH_OVERRIDES`` 单独限额，避免与交互路由共用模块级小额限流而
    在机队峰值下 429 丢告警；其余路由沿用模块级限额。

    参数:
    - module (str): 模块名，对应 settings.RATE_LIMIT_OVERRIDES 的 key。

    返回:
    - Depends: 对应请求的限流依赖。
    """

    async def _limiter_dependency(request: Request, response: Response) -> None:
        cfg = resolve_rate_limit(
            module,
            request.method,
            (request.scope.get("path", ""), request.url.path),
        )
        limiter = RateLimiter(times=cfg["times"], seconds=cfg["seconds"])
        await limiter(request, response)

    return Depends(_limiter_dependency)


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
    app.include_router(common_router, dependencies=[_rate_limit("common")])
    app.include_router(application_router, dependencies=[_rate_limit("application")])
    app.include_router(system_router, dependencies=[_rate_limit("system")])
    app.include_router(monitor_router, dependencies=[_rate_limit("monitor")])
    app.include_router(video_router, dependencies=[_rate_limit("video")])

    from app.api.v1.module_annotation import _register_annotation_routers, annotation_router
    _register_annotation_routers()
    app.include_router(annotation_router, dependencies=[_rate_limit("annotation")])

    from app.plugin.module_ai.chat.ws import WS_AI

    # 手动注册WebSocket路由，不使用速率限制器
    app.include_router(
        router=WS_AI, dependencies=[Depends(WebSocketRateLimiter(times=1, seconds=5))]
    )

    from app.api.v1.module_video.alarm.ws import AlarmWSRouter

    app.include_router(AlarmWSRouter)

    from app.plugin.module_train.ws import WS_Train

    app.include_router(WS_Train)

    from app.api.v1.module_system.notification.ws import NotificationWSRouter

    app.include_router(NotificationWSRouter)
    # 先将动态路由注册到应用，使用速率限制器
    from app.core.discover import get_dynamic_router

    # 获取动态路由实例（train 等插件模块）
    app.include_router(
        router=get_dynamic_router(),
        dependencies=[_rate_limit("train")],
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
    # 挂载录制文件目录 — 短时签名 URL（替代原未鉴权 app 级静态路由）
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.api.v1.module_video.record.service import (
        RECORDINGS_DIR,
        safe_stream_segment,
        verify_recording_signature,
    )

    @app.get("/recordings/{stream_id}/{file_name}")
    async def serve_recording(
        stream_id: str,
        file_name: str,
        exp: int = 0,
        sig: str = "",
    ):
        """校验短时签名后返回录像文件（无签名/过期/越界一律拒绝）。

        前端 ``<video>`` 无法携带 Authorization 头，故使用 ``play_url`` 中的
        ``?exp=&sig=`` 短时签名鉴权；签名由 ``record`` 模块的受权限保护接口签发。
        """
        try:
            seg = safe_stream_segment(stream_id)
        except Exception:
            return HTMLResponse(status_code=403)
        safe_name = Path(file_name).name
        if not verify_recording_signature(seg, safe_name, exp, sig):
            return HTMLResponse(status_code=403)
        fp = RECORDINGS_DIR / seg / safe_name
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
