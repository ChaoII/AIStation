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


def _run_container(image: str, cmd: list[str], volumes: dict, gpu_id: str, env: dict) -> docker.models.containers.Container:
    device_requests = []
    if gpu_id:
        device_requests = [docker.types.DeviceRequest(device_ids=[gpu_id], capabilities=[["gpu"]])]
    return client.containers.run(
        image, cmd,
        volumes=volumes,
        environment=env,
        device_requests=device_requests,
        detach=True,
        remove=False,
        stderr=True,
    )


async def run_container(image: str, cmd: list[str], volumes: dict, gpu_id: str = "0", env: dict | None = None) -> docker.models.containers.Container:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_container, image, cmd, volumes, gpu_id, env or {})


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

    thread = loop.run_in_executor(None, _stream)
    return queue


async def remove_container(container_id: str) -> None:
    """移除容器"""
    try:
        c = client.containers.get(container_id)
        c.remove(force=True)
    except docker.errors.NotFound:
        pass
