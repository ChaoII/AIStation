"""进程内 GPU 并发信号量（评估 / 预测链路用）。

⚠️ **训练不走这里**。``TorchKilnExecutor`` 与 ``TorchKilnExecutor`` 都走
``gpu_pool.gpu_lease()``——它做的是真正的 GPU 认领（跨进程、按显存需求量、
Redis 去重），而这里只是本进程里的一把计数锁。

本模块仍服务于 ``EvalExecutor`` / ``PredictExecutor``：它们是一次性命令
（``tkiln val`` / ``tkiln predict``），走本信号量 + ``gpu_lease`` 双层限制。

为什么用 ``get_train_semaphore()`` 惰性创建而不是模块级 ``asyncio.Semaphore(...)``：
``asyncio.Semaphore`` 在 Python 3.10+ 不在构造时绑定事件循环，但一旦被不同事件循环
复用（如测试里的 ``asyncio.run`` 每次新建 loop）仍可能触发 loop 绑定错误。惰性创建
把实例化推迟到首次真正 ``acquire`` 的异步上下文，行为更可控；首次实例化后即全局单例，
保证所有调用方共享同一把锁。
"""
import asyncio

# 同一时刻允许运行的评估/预测容器数（训练另走 gpu_pool.gpu_lease）
TRAIN_GPU_CONCURRENCY = 1

_train_gpu_semaphore: asyncio.Semaphore | None = None


def get_train_semaphore() -> asyncio.Semaphore:
    """返回跨训练执行器共享的全局 GPU 信号量（惰性创建、进程内单例）。"""
    global _train_gpu_semaphore
    if _train_gpu_semaphore is None:
        _train_gpu_semaphore = asyncio.Semaphore(TRAIN_GPU_CONCURRENCY)
    return _train_gpu_semaphore
