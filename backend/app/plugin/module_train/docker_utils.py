import asyncio
import time

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
    labels: dict | None = None,
) -> docker.models.containers.Container:
    device_requests = []
    if gpu_id:
        device_requests = [docker.types.DeviceRequest(device_ids=[gpu_id], capabilities=[["gpu"]])]
    kwargs = {
        "image": image, "command": cmd, "volumes": volumes, "environment": env,
        "ports": ports, "entrypoint": entrypoint, "device_requests": device_requests,
        "detach": True, "remove": False, "stderr": True, "labels": labels or {},
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
    labels: dict | None = None,
) -> docker.models.containers.Container:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _run_container, image, cmd, volumes, gpu_id, env or {}, ports, entrypoint, shm_size, labels
    )


def _wait_until_gone(container_id: str, timeout: float = 30.0) -> bool:
    """轮询直到容器真正消失。返回是否在超时前消失。

    只用于「另一个协程正在移除这个容器」的情况——那时再发一次 remove 只会再拿
    一个 409，唯一能做的就是等。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            client.containers.get(container_id)
        except docker.errors.NotFound:
            return True
        except Exception:  # noqa: BLE001
            # Docker API 临时不可用等，按「还没消失」处理，继续轮询
            pass
        time.sleep(0.3)
    return False


def _remove_now(container_id: str, *, force: bool = True,
                stop_timeout: int | None = None) -> None:
    """移除容器，对「已被移除」与「正在被移除」都幂等。

    ⚠️ 409 是**必须处理**的，不是可以忽略的噪音。

    本项目有两个移除入口：:func:`_stop_container`（阻塞 stop 后 remove）与
    :func:`remove_container`（force remove）。它们经常作用于**同一个容器**——
    部署停止时「协程 A 正在 stop 并 remove，协程 B 的 finally 也来 remove」
    就是常态。此时 B 撞上 A 正在进行的移除，Docker 返回::

        409 Conflict ("removal of container X is already in progress")

    让它冒出去的后果不是「日志里多几行」：收尾路径被打断，后台任务变成
    ``Task exception was never retrieved``，而且**容器可能没被移除**。
    正确做法是轮询等它消失——那是唯一确定会到来的结果。
    """
    # 空 id 的守卫放在这里而不是调用方：``_stop_container`` 也直接调本函数，
    # 而 ``client.containers.get(None)`` 抛的是 ``NullResource``（不在
    # NotFound 捕获范围内），会把「本来就没容器可清」变成异常。
    if not container_id:
        return
    try:
        c = client.containers.get(container_id)
    except docker.errors.NotFound:
        return
    try:
        if stop_timeout is not None:
            c.stop(timeout=stop_timeout)
        c.remove(force=force)
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError as e:
        if e.status_code == 409:
            if not _wait_until_gone(container_id):
                log.warning(
                    f"[docker] 等待容器 {container_id[:12]} 被移除超时（30s）"
                    f"——可能仍有进程持有它；下次看门狗会重试")
            return
        raise


def _stop_container(container_id: str) -> None:
    _remove_now(container_id, force=False, stop_timeout=10)


async def stop_container(container_id: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _stop_container, container_id)


async def get_container(container_id: str):
    """按 id 获取 Docker 容器对象（用于后端重启后的重连）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: client.containers.get(container_id))


def find_task_containers(task_kind: str, task_id: int) -> list[str]:
    """按 label 查找该任务的容器 id（含已退出未删除的）。"""
    try:
        cs = client.containers.list(all=True, filters={
            "label": [f"aistation.task_kind={task_kind}", f"aistation.task_id={task_id}"]})
        return [c.id for c in cs]
    except Exception as e:
        log.warning(f"find_task_containers(kind={task_kind}, id={task_id}) 查询失败: {e}")
        return []


def get_container_labels(container_id: str) -> dict[str, str]:
    """读容器的 labels。

    后端重启后要重新连上 job 容器里的 TorchKiln 服务，光有容器 id 不够——还得
    知道它映射到宿主机的哪个端口。起容器时把端口写进 label
    （``aistation.tk_port``），这里读回来即可，**不必为此加数据库字段**。
    """
    try:
        c = client.containers.get(container_id)
        return dict(c.labels or {})
    except Exception as e:
        log.warning(f"get_container_labels({container_id[:12]}) 读取失败: {e}")
        return {}


async def stop_task_containers(task_kind: str, task_id: int) -> None:
    """按 label 停止并移除该任务的所有容器（用于内存 registry 丢失后的兜底）。"""
    for cid in find_task_containers(task_kind, task_id):
        await stop_container(cid)


async def follow_container_logs(container_id: str) -> asyncio.Queue:
    """异步逐行读取容器日志，返回 asyncio.Queue"""
    queue: asyncio.Queue = asyncio.Queue()
    container = client.containers.get(container_id)
    loop = asyncio.get_event_loop()

    def _stream():
        try:
            for line in container.logs(stream=True, follow=True, timestamps=False):
                loop.call_soon_threadsafe(
                    queue.put_nowait, line.decode("utf-8", errors="replace").rstrip("\n")
                )
        finally:
            # 容器被移除/日志流异常时也务必推送 EOF，否则 follow_logs 永久挂起
            loop.call_soon_threadsafe(queue.put_nowait, "__EOF__")

    loop.run_in_executor(None, _stream)
    return queue


async def remove_container(container_id: str | None) -> None:
    """移除容器；没给 id 就什么都不做。

    ``id`` 为空**必须**静默跳过而不是往下走：``client.containers.get(None)`` 抛的是
    ``NullResource``，不在下面的 ``NotFound`` 捕获范围内，会把「本来就没容器可清」
    变成一次异常——而这恰恰发生在收尾路径上（容器从未起来、注册表已被清掉），
    结果是任务状态永远停在 RUNNING。

    「正在被另一个协程移除」也必须幂等，见 :func:`_remove_now` 的说明。
    """
    if not container_id:
        return
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _remove_now, container_id)


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
