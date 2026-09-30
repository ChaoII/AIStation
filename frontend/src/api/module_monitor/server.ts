import request from "@/utils/request";

const API_PATH = "/monitor/server";

const ServerAPI = {
  // 获取服务信息
  getServer() {
    return request<ApiResponse>({
      url: `${API_PATH}/info`,
      method: "get",
    });
  },
};

export default ServerAPI;

export interface Cpu {
  cpu_num: number;
  used: number;
  sys: number;
  free: number;
}

export interface Memory {
  total: string;
  used: string;
  free: string;
  usage: number;
}

export interface System {
  computer_name: string;
  os_name: string;
  computer_ip: string;
  os_arch: string;
  user_dir: string;
}

export interface Python {
  name: string;
  version: string;
  start_time: string;
  run_time: string;
  home: string;
  memory_total: string;
  memory_used: string;
  memory_free: string;
  memory_usage: number;
}

export interface SysFile {
  dirName: string;
  sysTypeName: string;
  typeName: string;
  total: string;
  free: string;
  used: string;
  usage: number;
}

/** 单张 GPU（后端 NVML 直读，字段为 snake_case） */
export interface GpuDevice {
  index: number;
  name: string;
  uuid: string;
  total: string;
  used: string;
  free: string;
  /** 显存使用率(%) */
  usage: number;
  /** GPU 核心利用率(%) */
  utilization: number;
  temperature: number | null;
  power: string | null;
  power_limit: string | null;
}

/** 宿主机 GPU 信息 */
export interface Gpu {
  available: boolean;
  error: string | null;
  driver_version: string | null;
  /** 驱动支持的 CUDA 版本（不是 torch 编译时的运行时版本） */
  cuda_version: string | null;
  device_count: number;
  devices: GpuDevice[];
}

/** 训练环境运行时版本（由 TorchKiln 服务上报） */
export interface TorchEnv {
  available: boolean;
  error: string | null;
  framework: string | null;
  framework_version: string | null;
  python: string | null;
  torch: string | null;
  cuda: string | null;
  cudnn: string | null;
  device: string | null;
  device_count: number;
}

export interface ServerInfo {
  cpu: Cpu;
  mem: Memory;
  sys: System;
  py: Python;
  disks: SysFile[];
  gpu?: Gpu;
  torch_env?: TorchEnv;
}
