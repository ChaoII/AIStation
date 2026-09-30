"""TorchKiln「每任务一容器」模式的回归守卫。

这套模式换掉了一件事：TorchKiln 不再是常驻服务，而是**每个训练任务一个容器**，
容器内跑完整服务、映射到宿主的不同端口，平台侧各连各的端口。由此引出三处
最容易错的地方，本文件逐条钉住：

1. **路径必须是容器内的 posix 路径**。数据实际写在宿主上，但 TorchKiln 是在
   容器里读的；把宿主路径（Windows 的 ``C:\\...\\data``）挂进 JobSpec，容器里
   ``open`` 必然 FileNotFoundError。
2. **资源不能泄漏**。拿不到 GPU 时必须把已认领的端口和 GPU 一起还回去，否则
   等一轮之后它们还挂在那个 task_id 名下，下一轮永远抢不到。
3. **权重必须能从宿主目录找到**。容器销毁后 HTTP 通路已经没了，权重入库只能
   靠挂载点。
"""
import asyncio
import socket

import pytest

from app.config.setting import settings
from app.plugin.module_train import gpu_pool
from app.plugin.module_train.torchkiln_executor import (
    _CONTAINER_DATA_DIR,
    TorchKilnExecutor,
)

CONTAINER_WORKSPACE = "/workspace"


# ----------------------------------------------------------------- 路径


def test_attach_dataset_lists_gives_container_posix_paths(tmp_path):
    """宿主探测存在性，给容器的是**容器内 posix 路径**。"""
    host_data = tmp_path / "data"
    host_data.mkdir()
    spec = {"model_name": "yolo11-det", "dataset": {"data_dir": "宿主路径要被覆盖"}}

    # 导出前：两个清单都不存在 -> 都不注入（避免指向模板里的残留路径）
    d = TorchKilnExecutor._attach_dataset_lists(spec, str(host_data),
                                                _CONTAINER_DATA_DIR)["dataset"]
    assert d["data_dir"] == _CONTAINER_DATA_DIR
    assert "train_list" not in d and "val_list" not in d

    # 导出后
    (host_data / "train.txt").write_text("images/train/a.jpg\n", encoding="utf-8")
    (host_data / "val.txt").write_text("images/val/a.jpg\n", encoding="utf-8")
    d = TorchKilnExecutor._attach_dataset_lists(spec, str(host_data),
                                                _CONTAINER_DATA_DIR)["dataset"]
    assert d["data_dir"] == _CONTAINER_DATA_DIR
    assert d["train_list"] == "/workspace/data/train.txt"
    assert d["val_list"] == "/workspace/data/val.txt"
    # Windows 宿主上 os.path.join 会产出反斜杠，容器里不是合法路径
    assert "\\" not in d["data_dir"] + d["train_list"] + d["val_list"]
    assert str(host_data) not in str(d)


def test_attach_dataset_lists_partial(tmp_path):
    """只有 train.txt 存在时只挂 train——不能给容器一个不存在的路径。"""
    host_data = tmp_path / "data"
    host_data.mkdir()
    (host_data / "train.txt").write_text("x\n", encoding="utf-8")
    d = TorchKilnExecutor._attach_dataset_lists(
        {"dataset": {}}, str(host_data), _CONTAINER_DATA_DIR)["dataset"]
    assert d["train_list"] == "/workspace/data/train.txt"
    assert "val_list" not in d


# ----------------------------------------------------------------- 白名单


def test_check_task_type_rejects_unsupported():
    with pytest.raises(ValueError, match="暂不支持"):
        TorchKilnExecutor._check_task_type("polyline")
    with pytest.raises(ValueError, match="暂不支持"):
        TorchKilnExecutor._check_task_type("panoptic_segmentation")
    # 白名单里的必须放行
    for tt in TorchKilnExecutor.SUPPORTED_TASK_TYPES:
        TorchKilnExecutor._check_task_type(tt)


# ----------------------------------------------------------------- 资源池


@pytest.fixture
def fake_gpus(monkeypatch):
    """固定成 2 张「显存充足」的卡，避免测试依赖真实机器的显卡状态。"""
    monkeypatch.setattr(gpu_pool, "gpu_devices", lambda: [
        _dev(0, "GPU-a", free_gb=12.0),
        _dev(1, "GPU-b", free_gb=8.0),
    ])
    monkeypatch.setattr(settings, "TORKILN_GPU_MIN_FREE_GB", 4.0, raising=False)
    monkeypatch.setattr(settings, "TORKILN_GPU_MAX_USED_RATIO", 0.95, raising=False)
    monkeypatch.setattr(settings, "TORKILN_PORT_START", 19300, raising=False)
    monkeypatch.setattr(settings, "TORKILN_PORT_END", 19303, raising=False)
    yield


def _dev(index: int, uuid: str, *, free_gb: float) -> dict:
    """构造一张卡的 NVML 视图。total 固定 16GB，便于算 used_ratio。"""
    total = int(16 * (1024 ** 3))
    free = int(free_gb * (1024 ** 3))
    return {"index": index, "uuid": uuid, "total": total, "free": free,
            "used": total - free, "free_gb": free_gb,
            "used_ratio": (total - free) / total}


def _reset_local():
    gpu_pool._local.clear()
    gpu_pool._local_ports.clear()
    gpu_pool._local_gpus.clear()


def test_acquire_gets_port_and_gpu(fake_gpus):
    _reset_local()
    alloc = asyncio.run(gpu_pool.acquire(1, need_gpu=1, wait=False))
    assert alloc is not None
    assert alloc.port in range(19300, 19304)
    assert alloc.gpu_indices == [0]
    assert alloc.base_url == f"http://127.0.0.1:{alloc.port}"
    asyncio.run(gpu_pool.release(1))


def test_two_tasks_get_different_ports(fake_gpus):
    _reset_local()
    a1 = asyncio.run(gpu_pool.acquire(11, need_gpu=1, wait=False))
    a2 = asyncio.run(gpu_pool.acquire(12, need_gpu=1, wait=False))
    assert a1 and a2
    assert a1.port != a2.port
    assert a1.gpu_indices != a2.gpu_indices  # 2 张卡各拿一张
    asyncio.run(gpu_pool.release(11))
    asyncio.run(gpu_pool.release(12))


def test_single_gpu_second_task_does_not_leak(fake_gpus, monkeypatch):
    """只有 1 张卡时第二个任务拿不到卡，**已认领的端口必须归还**。"""
    _reset_local()
    monkeypatch.setattr(gpu_pool, "gpu_devices",
                        lambda: [_dev(0, "GPU-a", free_gb=12.0)])
    a1 = asyncio.run(gpu_pool.acquire(21, need_gpu=1, wait=False))
    assert a1 is not None
    before = dict(gpu_pool._local_ports)

    a2 = asyncio.run(gpu_pool.acquire(22, need_gpu=1, wait=False))
    assert a2 is None
    # 关键：22 没拿到任何端口（不是 21 那个）
    assert gpu_pool._local_ports == before
    asyncio.run(gpu_pool.release(21))


def test_insufficient_memory_not_handed_out(fake_gpus, monkeypatch):
    """资源层：可用显存不够本次训练要求的卡不能派出去。"""
    _reset_local()
    # 卡上还剩 2GB，本次训练要 4GB -> 不该派
    monkeypatch.setattr(gpu_pool, "gpu_devices",
                        lambda: [_dev(0, "GPU-a", free_gb=2.0)])
    assert asyncio.run(gpu_pool.acquire(31, need_gpu=1, need_mem_gb=4.0,
                                        wait=False)) is None
    # 同一张卡，训练只要 1.5GB -> 可以派
    alloc = asyncio.run(gpu_pool.acquire(32, need_gpu=1, need_mem_gb=1.5,
                                         wait=False))
    assert alloc is not None and alloc.gpu_indices == [0]
    asyncio.run(gpu_pool.release(32))


def test_desktop_baseline_usage_does_not_block(monkeypatch):
    """带桌面环境的 Windows：系统常驻占 20% 显存也**不能**因此永远排队。

    这条是实测逼出来的——本机 dwm.exe + Edge 硬件加速常驻占 3.2GB/16GB（20%），
    按「已用占比 < 5%」判会得出「卡被占满」，平台永远排队。判据必须是绝对可用显存。
    """
    _reset_local()
    monkeypatch.setattr(settings, "TORKILN_PORT_START", 19700, raising=False)
    monkeypatch.setattr(settings, "TORKILN_PORT_END", 19702, raising=False)
    # 已用 20%（3.2GB），剩 12.8GB —— 典型的桌面环境基线
    monkeypatch.setattr(gpu_pool, "gpu_devices",
                        lambda: [_dev(0, "GPU-a", free_gb=12.8)])
    alloc = asyncio.run(gpu_pool.acquire(61, need_gpu=1, need_mem_gb=4.0,
                                         wait=False))
    assert alloc is not None, "桌面基线占用不该导致永久排队"
    assert alloc.gpu_indices == [0]
    asyncio.run(gpu_pool.release(61))


def test_no_gpu_enumerated_degrades_instead_of_hanging(monkeypatch):
    """一台卡都枚举不到时必须降级为「不指定 --gpus」，不能死等。"""
    _reset_local()
    monkeypatch.setattr(gpu_pool, "gpu_devices", lambda: [])
    monkeypatch.setattr(settings, "TORKILN_PORT_START", 19400, raising=False)
    monkeypatch.setattr(settings, "TORKILN_PORT_END", 19400, raising=False)
    alloc = asyncio.run(gpu_pool.acquire(41, need_gpu=1, wait=False))
    assert alloc is not None
    assert alloc.gpu_indices == []
    assert alloc.port == 19400
    asyncio.run(gpu_pool.release(41))


def test_port_range_exhausted_returns_none_not_hang(monkeypatch):
    """端口段被占满时应返回 None（明确失败），而不是无限等。"""
    _reset_local()
    monkeypatch.setattr(gpu_pool, "gpu_devices", lambda: [])
    monkeypatch.setattr(settings, "TORKILN_PORT_START", 19500, raising=False)
    monkeypatch.setattr(settings, "TORKILN_PORT_END", 19500, raising=False)
    hog = socket.socket()
    hog.bind(("127.0.0.1", 19500))
    hog.listen(1)
    try:
        alloc = asyncio.run(gpu_pool.acquire(51, need_gpu=0, wait=False))
        assert alloc is None
    finally:
        hog.close()


def test_port_probe_rejects_port_in_use(monkeypatch):
    """真实 bind 探测：Redis 说空闲但端口被本机其它进程占着时不能发出去。"""
    monkeypatch.setattr(settings, "TORKILN_PORT_START", 19600, raising=False)
    monkeypatch.setattr(settings, "TORKILN_PORT_END", 19600, raising=False)
    hog = socket.socket()
    hog.bind(("127.0.0.1", 19600))
    hog.listen(1)
    try:
        assert gpu_pool._port_bindable(19600) is False
    finally:
        hog.close()
    assert gpu_pool._port_bindable(19600) is True
