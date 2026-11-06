import os
import sys
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from app.common.enums import EnvironmentEnum

aistation_cli = typer.Typer()
alembic_cfg = Config("alembic.ini")

BASE_DIR = Path(__file__).resolve().parent

# 热重载只盯代码目录：backend/ 下有 .venv(2.4 万文件)、submodules、data、logs，
# 全量盯着会让文件监听器空转（StatReload 甚至会把 .venv 里每个 .py 都 stat 一遍）。
RELOAD_EXCLUDES = [
    "*.pyc",
    "__pycache__/*",
    ".venv/*",
    "submodules/*",
    "data/*",
    "logs/*",
    "tests/*",
    "docs/*",
    "static/*",
    "sql/*",
    "keys/*",
    "env/*",
    ".pytest_cache/*",
    ".ruff_cache/*",
]


def _patch_windows_reload() -> None:
    """
    修掉 Windows 上 uvicorn reloader 的死锁（0.54 实测）。

    `BaseReload.restart()` 在 win32 走 `os.kill(pid, signal.CTRL_C_EVENT)` 通知子进程退出，
    这个事件只有在父/子进程挂在**同一个控制台**时才送得到。从 IDE 任务、重定向输出、
    Start-Process -WindowStyle Hidden 等方式启动时根本没有控制台 → 子进程收不到 Ctrl+C
    就继续跑，reloader 卡在 `process.join()`：
    日志显示「StatReload detected changes ... Reloading...」，然后几分钟纹丝不动。

    这里改成 `process.terminate()`（TerminateProcess，必达）。dev 场景不做优雅关闭，
    进程级别的收尾由启动期的 reconcile（工作流/问数评测僵尸记录）兜底。

    返回:
    - None
    """
    from uvicorn.supervisors import basereload

    def restart(self) -> None:  # type: ignore[no-untyped-def]
        self.process.terminate()
        self.process.join()
        self.process = basereload.get_subprocess(
            config=self.config, target=self.target, sockets=self.sockets
        )
        self.process.start()

    def shutdown(self) -> None:  # type: ignore[no-untyped-def]
        # 原版 win32 分支只 `self.should_exit.set()`（那是 reloader 自己的标志），
        # 子进程根本没收到通知，`join()` 于是永久阻塞 —— 表现为 Ctrl+C 后父进程不退、
        # 或者父进程没了但子进程还占着端口用旧代码服务。
        self.process.terminate()
        self.process.join()
        for sock in self.sockets:
            sock.close()

    basereload.BaseReload.restart = restart  # type: ignore[method-assign]
    basereload.BaseReload.shutdown = shutdown  # type: ignore[method-assign]


def create_app() -> FastAPI:
    """
    创建 FastAPI 应用实例并完成日志、中间件、路由与静态资源注册。

    返回:
    - FastAPI: 已配置生命周期的应用对象。
    """
    from app.config.setting import settings
    from app.scripts.init_app import (
        lifespan,
        register_exceptions,
        register_files,
        register_middlewares,
        register_routers,
        reset_api_docs,
    )

    # 创建FastAPI应用
    app = FastAPI(**settings.FASTAPI_CONFIG, lifespan=lifespan)

    from app.core.logger import setup_logging

    # 初始化日志
    setup_logging()
    # 注册各种组件
    register_exceptions(app)
    # 注册中间件
    register_middlewares(app)
    # 注册路由
    register_routers(app)
    # 注册静态文件
    register_files(app)
    # 重设API文档
    reset_api_docs(app)
    # 预生成 OpenAPI schema：首次访问 /openapi.json 要把 989 条路由的 schema 算一遍，
    # 实测 **6.7 秒纯 CPU、期间事件循环完全卡死**（任何请求都要等）。启动期一次性算好缓存，
    # 之后 /docs、/openapi.json 都是纯字典读取。
    if app.openapi_url:
        import time as _time

        _t0 = _time.perf_counter()
        app.openapi()
        _ms = round((_time.perf_counter() - _t0) * 1000)
        from app.core.logger import log as _log

        _log.info(f"✅ OpenAPI schema 预生成完成：{_ms}ms（原为首次请求时卡 6.7s）")

    return app


# typer.Option是非必填；typer.Argument是必填
@aistation_cli.command(
    name="run",
    help="启动 AIStation 服务, 运行 python main.py run --env=dev 不加参数默认 dev 环境",
)
def run(
    env: Annotated[
        EnvironmentEnum, typer.Option("--env", help="运行环境 (dev, prod)")
    ] = EnvironmentEnum.DEV,
    reload: Annotated[
        bool | None,
        typer.Option(
            "--reload/--no-reload",
            help="热重载。**dev 默认开启**、prod 默认关闭；Windows 上已修掉 uvicorn 的"
            "CTRL_C_EVENT 死锁（见 _patch_windows_reload）。",
        ),
    ] = None,
) -> None:
    """
    按指定环境加载配置并启动 Uvicorn。

    参数:
    - env (EnvironmentEnum): 运行环境，对应 `--env`。
    - reload (bool | None): 热重载；None 时 dev 开、prod 关。

    返回:
    - None
    """
    if reload is None:
        reload = env == EnvironmentEnum.DEV

    try:
        # 设置环境变量
        os.environ["ENVIRONMENT"] = env.value
        typer.echo("项目启动中...")

        # 清除配置缓存，确保重新加载配置
        from app.config.setting import get_settings

        get_settings.cache_clear()
        settings = get_settings()

        from app.core.logger import setup_logging

        setup_logging()

        # 显示启动横幅
        from app.utils.banner import worship

        worship(env.value)

        # 启动uvicorn服务（dev 默认开 reload；Windows 的 reloader 死锁在此修掉）
        if reload and sys.platform == "win32":
            _patch_windows_reload()

        uvicorn.run(
            app="main:create_app",
            host=settings.SERVER_HOST,
            port=settings.SERVER_PORT,
            reload=reload,
            reload_dirs=[str(BASE_DIR)] if reload else None,
            reload_excludes=RELOAD_EXCLUDES if reload else None,
            factory=True,
            log_config=None,
        )
    finally:
        from app.core.logger import cleanup_logging

        cleanup_logging()


@aistation_cli.command(
    name="revision",
    help="生成新的 Alembic 迁移脚本, 运行 python main.py revision --env=dev",
)
def revision(
    env: Annotated[
        EnvironmentEnum, typer.Option("--env", help="运行环境 (dev, prod)")
    ] = EnvironmentEnum.DEV,
) -> None:
    """
    使用 Alembic 自动生成迁移脚本（autogenerate）。

    参数:
    - env (EnvironmentEnum): 运行环境，用于加载对应数据库模型元数据。

    返回:
    - None
    """
    os.environ["ENVIRONMENT"] = env.value
    from app.config.setting import get_settings

    get_settings.cache_clear()
    command.revision(alembic_cfg, autogenerate=True, message="迁移脚本")
    typer.echo("迁移脚本已生成")


@aistation_cli.command(
    name="upgrade",
    help="应用最新的 Alembic 迁移, 运行 python main.py upgrade --env=dev",
)
def upgrade(
    env: Annotated[
        EnvironmentEnum, typer.Option("--env", help="运行环境 (dev, prod)")
    ] = EnvironmentEnum.DEV,
) -> None:
    """
    将数据库升级到 Alembic 最新版本（head）。

    参数:
    - env (EnvironmentEnum): 运行环境。

    返回:
    - None
    """
    os.environ["ENVIRONMENT"] = env.value
    from app.config.setting import get_settings

    get_settings.cache_clear()
    command.upgrade(alembic_cfg, "head")
    typer.echo("所有迁移已应用。")


# 注：原先这里有个 ``download-models`` 命令，用于预下载 30 个 Ultralytics 权重
# （yolov8/yolo11/yolo26 × det/obb/cls）到缓存目录。Ultralytics 通路已退场，
# 预置权重不再被任何训练路径使用，故一并移除；TorchKiln 的权重由它自己的
# 镜像与 ``resolve_pretrained`` 解析，不走这套缓存。


if __name__ == "__main__":
    aistation_cli()
