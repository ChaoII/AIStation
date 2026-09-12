"""训练 GPU 全局并发控制。

TrainExecutor / PaddleXOCRDetExecutor / PaddleXOCRRecExecutor 各自 ``_concurrency = 1``，
但它们是三个独立的执行器类，各持有独立信号量，最多会有 3 个 GPU 训练容器抢同一张卡。
本模块提供跨三个执行器共享的全局信号量，把「同时运行的训练容器数」限制为
``TRAIN_GPU_CONCURRENCY``（默认 1）。

为什么用 ``get_train_semaphore()`` 惰性创建而不是模块级 ``asyncio.Semaphore(...)``：
``asyncio.Semaphore`` 在 Python 3.10+ 不在构造时绑定事件循环，但一旦被不同事件循环
复用（如测试里的 ``asyncio.run`` 每次新建 loop）仍可能触发 loop 绑定错误。惰性创建
把实例化推迟到首次真正 ``acquire`` 的异步上下文，行为更可控；首次实例化后即全局单例，
保证三个执行器共享同一把锁。
"""
import asyncio

# 同一时刻允许运行的训练容器数（跨 ultralytics / PaddleX det / PaddleX rec）
TRAIN_GPU_CONCURRENCY = 1

_train_gpu_semaphore: asyncio.Semaphore | None = None


def get_train_semaphore() -> asyncio.Semaphore:
    """返回跨训练执行器共享的全局 GPU 信号量（惰性创建、进程内单例）。"""
    global _train_gpu_semaphore
    if _train_gpu_semaphore is None:
        _train_gpu_semaphore = asyncio.Semaphore(TRAIN_GPU_CONCURRENCY)
    return _train_gpu_semaphore
