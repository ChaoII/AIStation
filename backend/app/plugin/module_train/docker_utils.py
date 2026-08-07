import asyncio

import docker

from app.core.logger import log

client = docker.from_env()


async def pull_image(image: str) -> None:
    """拉取 Docker 镜像（如果已存在则跳过）"""
    loop = asyncio.get_event_loop()
    try:
        client.images.get(image)
        log.info(f"image {image} already exists locally, skipping pull")
        return
    except docker.errors.ImageNotFound:
        pass
    log.info(f"pulling image {image}...")
    await loop.run_in_executor(None, _pull_sync, image)


def _pull_sync(image: str) -> None:
    client.images.pull(image)


def _run_container(
    image: str,
    cmd: list[str],
    volumes: dict,
    gpu_id: str,
    env: dict,
    ports: dict | None = None,
    entrypoint: str | None = None,
    shm_size: str | None = None,
) -> docker.models.containers.Container:
    device_requests = []
    if gpu_id:
        device_requests = [docker.types.DeviceRequest(device_ids=[gpu_id], capabilities=[["gpu"]])]
    kwargs = {
        "image": image, "command": cmd, "volumes": volumes, "environment": env,
        "ports": ports, "entrypoint": entrypoint, "device_requests": device_requests,
        "detach": True, "remove": False, "stderr": True,
    }
    if shm_size:
        kwargs["shm_size"] = shm_size
    return client.containers.run(**kwargs)


async def run_container(
    image: str,
    cmd: list[str],
    volumes: dict,
    gpu_id: str = "0",
    env: dict | None = None,
    ports: dict | None = None,
    entrypoint: str | None = None,
    shm_size: str | None = None,
) -> docker.models.containers.Container:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _run_container, image, cmd, volumes, gpu_id, env or {}, ports, entrypoint, shm_size
    )


def _stop_container(container_id: str) -> None:
    try:
        c = client.containers.get(container_id)
        c.stop(timeout=10)
        c.remove()
    except docker.errors.NotFound:
        pass


async def stop_container(container_id: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _stop_container, container_id)


async def follow_container_logs(container_id: str) -> asyncio.Queue:
    """异步逐行读取容器日志，返回 asyncio.Queue"""
    queue: asyncio.Queue = asyncio.Queue()
    container = client.containers.get(container_id)
    loop = asyncio.get_event_loop()

    def _stream():
        for line in container.logs(stream=True, follow=True, timestamps=False):
            loop.call_soon_threadsafe(queue.put_nowait, line.decode("utf-8", errors="replace").rstrip("\n"))
        loop.call_soon_threadsafe(queue.put_nowait, "__EOF__")

    loop.run_in_executor(None, _stream)
    return queue


async def remove_container(container_id: str) -> None:
    """移除容器"""
    try:
        c = client.containers.get(container_id)
        c.remove(force=True)
    except docker.errors.NotFound:
        pass


async def get_container_error_tail(container_id: str, tail: int = 50) -> str:
    """在 executor 中同步读取容器 stderr 末尾日志（避免阻塞事件循环）。

    任何异常（容器已删除 / daemon 不可达等）返回空串，与调用方原 try/except 行为一致。
    """
    loop = asyncio.get_event_loop()

    def _sync() -> str:
        try:
            c = client.containers.get(container_id)
            return c.logs(stdout=False, stderr=True, tail=tail).decode("utf-8", errors="replace")
        except Exception:
            return ""

    return await loop.run_in_executor(None, _sync)
