from pydantic import BaseModel, ConfigDict, Field


class CpuInfoSchema(BaseModel):
    """CPU信息模型"""

    model_config = ConfigDict(from_attributes=True)

    cpu_num: int = Field(description="CPU核心数")
    used: float = Field(ge=0, le=100, description="CPU用户使用率(%)")
    sys: float = Field(ge=0, le=100, description="CPU系统使用率(%)")
    free: float = Field(ge=0, le=100, description="CPU空闲率(%)")


class MemoryInfoSchema(BaseModel):
    """内存信息模型"""

    model_config = ConfigDict(from_attributes=True)

    total: str = Field(description="内存总量")
    used: str = Field(description="已用内存")
    free: str = Field(description="剩余内存")
    usage: float = Field(ge=0, le=100, description="使用率(%)")


class SysInfoSchema(BaseModel):
    """系统信息模型"""

    model_config = ConfigDict(from_attributes=True)

    computer_ip: str = Field(description="服务器IP")
    computer_name: str = Field(description="服务器名称")
    os_arch: str = Field(description="系统架构")
    os_name: str = Field(description="操作系统")
    user_dir: str = Field(description="项目路径")


class PyInfoSchema(BaseModel):
    """Python运行信息模型"""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(description="Python名称")
    version: str = Field(description="Python版本")
    start_time: str = Field(description="启动时间")
    run_time: str = Field(description="运行时长")
    home: str = Field(description="安装路径")
    memory_used: str = Field(description="内存占用")
    memory_usage: float = Field(ge=0, le=100, description="内存使用率(%)")
    memory_total: str = Field(description="总内存")
    memory_free: str = Field(description="剩余内存")


class DiskInfoSchema(BaseModel):
    """磁盘信息模型"""

    model_config = ConfigDict(from_attributes=True)

    dir_name: str = Field(description="磁盘路径")
    sys_type_name: str = Field(description="文件系统类型")
    type_name: str = Field(description="磁盘类型")
    total: str = Field(description="总容量")
    used: str = Field(description="已用容量")
    free: str = Field(description="可用容量")
    usage: float = Field(ge=0, le=100, description="使用率(%)")


class GpuDeviceSchema(BaseModel):
    """单张 GPU 的信息"""

    model_config = ConfigDict(from_attributes=True)

    index: int = Field(description="GPU序号")
    name: str = Field(description="GPU型号")
    uuid: str = Field(default="", description="GPU UUID")
    total: str = Field(default="", description="显存总量")
    used: str = Field(default="", description="已用显存")
    free: str = Field(default="", description="可用显存")
    usage: float = Field(default=0, ge=0, le=100, description="显存使用率(%)")
    utilization: float = Field(default=0, ge=0, le=100, description="GPU核心利用率(%)")
    temperature: int | None = Field(default=None, description="温度(℃)")
    power: str | None = Field(default=None, description="当前功耗")
    power_limit: str | None = Field(default=None, description="功耗上限")


class GpuInfoSchema(BaseModel):
    """GPU 信息（宿主机 NVML 直读，与训练容器是否可用无关）"""

    model_config = ConfigDict(from_attributes=True)

    available: bool = Field(default=False, description="NVML 是否可用")
    error: str | None = Field(default=None, description="不可用原因")
    driver_version: str | None = Field(default=None, description="NVIDIA驱动版本")
    cuda_version: str | None = Field(default=None, description="驱动支持的CUDA版本")
    device_count: int = Field(default=0, description="GPU数量")
    devices: list[GpuDeviceSchema] = Field(default_factory=list, description="GPU列表")


class TorchEnvSchema(BaseModel):
    """训练环境运行时版本（由 TorchKiln 服务上报，本服务不装 torch）"""

    model_config = ConfigDict(from_attributes=True)

    available: bool = Field(default=False, description="训练服务是否可达")
    error: str | None = Field(default=None, description="不可用原因")
    framework: str | None = Field(default=None, description="训练框架")
    framework_version: str | None = Field(default=None, description="框架版本")
    python: str | None = Field(default=None, description="训练环境Python版本")
    torch: str | None = Field(default=None, description="PyTorch版本")
    cuda: str | None = Field(default=None, description="CUDA运行时版本")
    cudnn: str | None = Field(default=None, description="cuDNN版本")
    device: str | None = Field(default=None, description="训练用GPU")
    device_count: int = Field(default=0, description="训练环境可见GPU数")


class ServerMonitorSchema(BaseModel):
    """服务器监控信息模型"""

    model_config = ConfigDict(from_attributes=True)

    cpu: CpuInfoSchema = Field(description="CPU信息")
    mem: MemoryInfoSchema = Field(description="内存信息")
    py: PyInfoSchema = Field(description="Python运行信息")
    sys: SysInfoSchema = Field(description="系统信息")
    disks: list[DiskInfoSchema] = Field(default_factory=list, description="磁盘信息")
    gpu: GpuInfoSchema = Field(default_factory=GpuInfoSchema, description="GPU信息")
    torch_env: TorchEnvSchema = Field(
        default_factory=TorchEnvSchema, description="训练环境运行时版本")
