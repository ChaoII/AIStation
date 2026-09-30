import logging
import platform
import socket
import time
from pathlib import Path

import psutil

from app.config.setting import settings
from app.utils.common_util import bytes2human

from .schema import (
    CpuInfoSchema,
    DiskInfoSchema,
    GpuDeviceSchema,
    GpuInfoSchema,
    MemoryInfoSchema,
    PyInfoSchema,
    ServerMonitorSchema,
    SysInfoSchema,
    TorchEnvSchema,
)

log = logging.getLogger(__name__)


def _pct(value) -> float:
    """NVML 给的百分比夹到 [0, 100]。

    schema 上有 ``ge=0``/``le=100`` 校验，越界会让**整个 /info 接口 500**——
    而本页、dashboard、workplace 三处都依赖这个接口。显存 ``used`` 偶尔会略超
    ``total``（驱动保留了一段），所以这里必须兜住。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return round(max(0.0, min(100.0, v)), 2)


def _nvml_str(value) -> str:
    """NVML 新版返回 str、旧版返回 bytes，统一成 str。"""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


class ServerService:
    """服务监控模块服务层"""

    #: 训练环境版本探测的成功缓存时长（秒）。torch/cuda/cudnn 版本在进程内不变，
    #: 没必要每次请求都去问一遍训练服务。
    TORCH_ENV_OK_TTL = 300.0
    #: 失败缓存时长（秒）。**失败也必须缓存**——否则训练服务挂掉时，每次刷新页面
    #: 都要白等一次连接超时。
    TORCH_ENV_FAIL_TTL = 30.0
    #: 探测用的短超时（秒）。走 TORKILN_TIMEOUT（默认 30s）会把监控接口拖垮。
    TORCH_ENV_PROBE_TIMEOUT = 3.0

    _torch_env_cache: TorchEnvSchema | None = None
    _torch_env_cached_at: float = 0.0
    _torch_env_ttl: float = 0.0

    @classmethod
    async def get_server_monitor_info_service(cls) -> dict:
        """
        获取服务器监控信息

        返回:
        - Dict: 包含服务器监控信息的字典。
        """
        torch_env = await cls._get_torch_env()
        return ServerMonitorSchema(
            cpu=cls._get_cpu_info(),
            mem=cls._get_memory_info(),
            sys=cls._get_system_info(),
            py=cls._get_python_info(),
            disks=cls._get_disk_info(),
            gpu=cls._get_gpu_info(),
            torch_env=torch_env,
        ).model_dump()

    # ------------------------------------------------------------ GPU（NVML）
    @classmethod
    def _get_gpu_info(cls) -> GpuInfoSchema:
        """宿主机 GPU 信息，走 NVML 直读。

        与训练容器是否可用**无关**：这里读的是本机驱动/显卡，训练容器申请到的
        是同一块物理卡。NVML 不可用（没装驱动 / 容器内无 GPU / pynvml 缺失）时
        一律降级成 ``available=False``，绝不抛异常把 /info 打挂。
        """
        try:
            import pynvml
        except Exception as e:  # noqa: BLE001
            return GpuInfoSchema(available=False, error=f"未安装 pynvml：{e}")

        try:
            pynvml.nvmlInit()
        except Exception as e:  # noqa: BLE001
            return GpuInfoSchema(available=False, error=f"NVML 初始化失败：{e}")

        try:
            driver = _nvml_str(pynvml.nvmlSystemGetDriverVersion())
            cuda = cls._driver_cuda_version(pynvml)
            count = int(pynvml.nvmlDeviceGetCount())
            devices: list[GpuDeviceSchema] = []
            for index in range(count):
                try:
                    devices.append(cls._get_gpu_device(pynvml, index))
                except Exception as e:  # noqa: BLE001
                    # 单张卡读失败不该拖垮整块信息
                    log.warning("读取 GPU %s 失败：%s", index, e)
            return GpuInfoSchema(
                available=True,
                driver_version=driver,
                cuda_version=cuda,
                device_count=count,
                devices=devices,
            )
        except Exception as e:  # noqa: BLE001
            return GpuInfoSchema(available=False, error=str(e))
        finally:
            try:
                pynvml.nvmlShutdown()
            except Exception:  # noqa: BLE001
                pass

    @classmethod
    def _driver_cuda_version(cls, pynvml) -> str | None:
        """驱动支持的 CUDA 版本：13040 -> "13.4"。

        注意这是**驱动**支持的上限，与训练环境 torch 编译时的 CUDA 运行时版本
        不是一回事——两者都展示，别混为一谈。
        """
        try:
            raw = int(pynvml.nvmlSystemGetCudaDriverVersion_v2())
        except Exception:  # noqa: BLE001
            return None
        if raw <= 0:
            return None
        return f"{raw // 1000}.{(raw % 1000) // 10}"

    @classmethod
    def _get_gpu_device(cls, pynvml, index: int) -> GpuDeviceSchema:
        """单张 GPU 的型号 / 显存 / 利用率 / 温度 / 功耗。"""
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)

        total = int(mem.total)
        used = int(mem.used)
        free = max(0, total - used)
        usage = _pct(used / total * 100) if total else 0.0

        try:
            utilization = _pct(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
        except Exception:  # noqa: BLE001
            utilization = 0.0

        try:
            temperature: int | None = int(
                pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
        except Exception:  # noqa: BLE001
            temperature = None

        power = cls._nvml_mw(pynvml, handle, pynvml.nvmlDeviceGetPowerUsage)
        power_limit = cls._nvml_mw(
            pynvml, handle, pynvml.nvmlDeviceGetPowerManagementLimit)

        try:
            uuid = _nvml_str(pynvml.nvmlDeviceGetUUID(handle))
        except Exception:  # noqa: BLE001
            uuid = ""

        return GpuDeviceSchema(
            index=index,
            name=_nvml_str(pynvml.nvmlDeviceGetName(handle)),
            uuid=uuid,
            total=bytes2human(total),
            used=bytes2human(used),
            free=bytes2human(free),
            usage=usage,
            utilization=utilization,
            temperature=temperature,
            power=power,
            power_limit=power_limit,
        )

    @classmethod
    def _nvml_mw(cls, pynvml, handle, getter) -> str | None:
        """NVML 的毫瓦读数转成 "60.0 W"；读不到就返回 None。"""
        try:
            return f"{int(getter(handle)) / 1000.0:.1f} W"
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------- 训练环境（TorchKiln 上报）
    @classmethod
    async def _get_torch_env(cls) -> TorchEnvSchema:
        """训练环境的 torch / CUDA / cuDNN 版本。

        这三个值只有装了 torch 的训练进程报得出来（本服务不装 torch），所以由
        TorchKiln 的 ``GET /api/v1/info`` 上报，这里只做汇总展示。

        结果带 TTL 缓存：**成功缓存 5 分钟，失败也缓存 30 秒**——训练服务挂掉时
        失败若不缓存，每次刷新页面都要白等一次连接超时。
        """
        now = time.time()
        cached = cls._torch_env_cache
        if cached is not None and now - cls._torch_env_cached_at < cls._torch_env_ttl:
            return cached

        if not settings.TORKILN_ENABLED:
            result = TorchEnvSchema(
                available=False, error="训练服务未启用（TORKILN_ENABLED=false）")
        else:
            result = await cls._probe_torch_env()

        cls._torch_env_cache = result
        cls._torch_env_cached_at = now
        cls._torch_env_ttl = (
            cls.TORCH_ENV_OK_TTL if result.available else cls.TORCH_ENV_FAIL_TTL)
        return result

    @classmethod
    async def _probe_torch_env(cls) -> TorchEnvSchema:
        """向训练服务要一次 ``/api/v1/info``，任何异常都降级成 available=False。"""
        try:
            from app.plugin.module_train.torchkiln_client import TorchKilnClient

            async with TorchKilnClient(timeout=cls.TORCH_ENV_PROBE_TIMEOUT) as client:
                info = await client.info()
        except Exception as e:  # noqa: BLE001
            return TorchEnvSchema(available=False, error=str(e))

        runtime = info.get("runtime") or {}
        # 老版本训练服务没有 runtime 键：服务是通的，只是报不出版本，
        # 这时 available 仍为 True，前端显示 "-" 而不是报错。
        return TorchEnvSchema(
            available=True,
            framework=info.get("framework"),
            framework_version=info.get("framework_version"),
            python=runtime.get("python"),
            torch=runtime.get("torch"),
            cuda=runtime.get("cuda"),
            cudnn=runtime.get("cudnn"),
            device=runtime.get("device"),
            device_count=int(runtime.get("device_count") or 0),
        )

    # ------------------------------------------------------------ 基础信息
    @classmethod
    def _get_cpu_info(cls) -> CpuInfoSchema:
        """
        获取CPU信息

        返回:
        - CpuInfoSchema: CPU信息模型。
        """
        cpu_times = psutil.cpu_times_percent()
        cpu_num = psutil.cpu_count(logical=True)
        if not cpu_num:
            cpu_num = 1
        return CpuInfoSchema(
            cpu_num=cpu_num,
            used=cpu_times.user,
            sys=cpu_times.system,
            free=cpu_times.idle,
        )

    @classmethod
    def _get_memory_info(cls) -> MemoryInfoSchema:
        """
        获取内存信息

        返回:
        - MemoryInfoSchema: 内存信息模型。
        """
        memory = psutil.virtual_memory()
        return MemoryInfoSchema(
            total=bytes2human(memory.total),
            used=bytes2human(memory.used),
            free=bytes2human(memory.free),
            usage=memory.percent,
        )

    @classmethod
    def _get_system_info(cls) -> SysInfoSchema:
        """
        获取系统信息

        返回:
        - SysInfoSchema: 系统信息模型。
        """
        hostname = socket.gethostname()
        return SysInfoSchema(
            computer_ip=socket.gethostbyname(hostname),
            computer_name=platform.node(),
            os_arch=platform.machine(),
            os_name=platform.platform(),
            user_dir=str(Path.cwd()),
        )

    @classmethod
    def _get_python_info(cls) -> PyInfoSchema:
        """
        获取Python解释器信息

        返回:
        - PyInfoSchema: Python解释器信息模型。
        """
        current_process = psutil.Process()
        memory = psutil.virtual_memory()
        process_memory = current_process.memory_info()

        start_time = current_process.create_time()
        run_time = ServerService._calculate_run_time(start_time)

        return PyInfoSchema(
            name=current_process.name(),
            version=platform.python_version(),
            start_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time)),
            run_time=run_time,
            home=str(Path(current_process.exe())),
            memory_total=bytes2human(memory.available),
            memory_used=bytes2human(process_memory.rss),
            memory_free=bytes2human(memory.available - process_memory.rss),
            memory_usage=round((process_memory.rss / memory.available) * 100, 2),
        )

    @classmethod
    def _get_disk_info(cls) -> list[DiskInfoSchema]:
        """
        获取磁盘信息

        返回:
        - list[DiskInfoSchema]: 磁盘信息模型列表。
        """
        disk_info = []
        for partition in psutil.disk_partitions():
            try:
                # 使用mountpoint而不是device来获取磁盘使用情况
                usage = psutil.disk_usage(partition.mountpoint)
                mount_point = str(Path(partition.mountpoint))
                disk_info.append(
                    DiskInfoSchema(
                        dir_name=mount_point,  # 使用mountpoint替代device
                        sys_type_name=partition.fstype,
                        type_name=f"本地固定磁盘（{mount_point}）",
                        total=bytes2human(usage.total),
                        used=bytes2human(usage.used),
                        free=bytes2human(usage.free),
                        usage=usage.percent,  # 直接使用数字而不是字符串
                    )
                )
            except (PermissionError, FileNotFoundError):
                # 明确指定可能的异常
                continue
        return disk_info

    @classmethod
    def _calculate_run_time(cls, start_time: float) -> str:
        """
        计算运行时间

        参数:
        - start_time (float): 进程启动时间（时间戳）

        返回:
        - str: 格式化后的运行时间字符串（例如："1天2小时3分钟"）
        """
        difference = time.time() - start_time
        days = int(difference // (24 * 60 * 60))
        hours = int((difference % (24 * 60 * 60)) // (60 * 60))
        minutes = int((difference % (60 * 60)) // 60)
        return f"{days}天{hours}小时{minutes}分钟"
