<template>
  <div class="app-container">
    <el-row :gutter="16">
      <el-col :span="12" class="mb-4">
        <el-card :loading="loading" shadow="hover">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Cpu /></el-icon>
              <span class="flex items-center gap-2">CPU使用情况</span>
              <el-tooltip content="展示CPU核心数及使用率">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-row :gutter="16">
            <!-- CPU核心数卡片 -->
            <el-col :span="12">
              <el-card shadow="hover">
                <span>核心数</span>
                <el-tooltip :content="(server.cpu?.cpu_num || 0).toFixed(1)">
                  <div class="text-center mb-4">
                    <el-progress
                      type="circle"
                      :percentage="100"
                      :format="() => `${server.cpu?.cpu_num || 0}`"
                    />
                  </div>
                </el-tooltip>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="总核心数">
                    {{ server.cpu?.cpu_num || 0 }}
                  </el-descriptions-item>
                  <el-descriptions-item label="已用核心">
                    {{ Math.floor(((server.cpu?.used || 0) * server.cpu?.cpu_num) / 100) }}
                  </el-descriptions-item>
                  <el-descriptions-item label="空闲核心">
                    {{ Math.floor(((server.cpu?.free || 0) * server.cpu?.cpu_num) / 100) }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
            <!-- CPU使用率卡片 -->
            <el-col :span="12">
              <el-card shadow="hover" class="h-full">
                <span>使用率</span>
                <el-tooltip :content="(server.cpu?.used || 0).toFixed(1) + '%'">
                  <div class="text-center mb-4">
                    <el-progress
                      type="circle"
                      :percentage="server.cpu?.used || 0"
                      :status="
                        server.cpu?.used > 80
                          ? 'exception'
                          : server.cpu?.used > 60
                            ? 'warning'
                            : 'success'
                      "
                    />
                  </div>
                </el-tooltip>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="用户使用率">
                    {{ (server.cpu?.used || 0).toFixed(1) + "%" }}
                  </el-descriptions-item>
                  <el-descriptions-item label="系统使用率">
                    {{ (server.cpu?.sys || 0).toFixed(1) + "%" }}
                  </el-descriptions-item>
                  <el-descriptions-item label="当前空闲率">
                    {{ (server.cpu?.free || 0).toFixed(1) + "%" }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <el-col :span="12" class="mb-4">
        <el-card :loading="loading" shadow="hover">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Memo /></el-icon>
              <span>内存使用情况</span>
              <el-tooltip content="展示系统内存和Python程序内存使用情况">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-row :gutter="16">
            <!-- 系统内存卡片 -->
            <el-col :span="12">
              <el-card shadow="hover" class="h-full">
                <span>系统内存</span>
                <el-tooltip :content="(server.mem?.usage || 0).toFixed(1) + '%'">
                  <div class="text-center mb-4">
                    <el-progress
                      type="circle"
                      :percentage="server.mem?.usage || 0"
                      :status="
                        server.mem?.usage > 80
                          ? 'exception'
                          : server.mem?.usage > 60
                            ? 'warning'
                            : 'success'
                      "
                    />
                  </div>
                </el-tooltip>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="总内存">
                    {{ server.mem?.total }}
                  </el-descriptions-item>
                  <el-descriptions-item label="已用内存">
                    {{ server.mem?.used }}
                  </el-descriptions-item>
                  <el-descriptions-item label="空闲内存">
                    {{ server.mem?.free }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
            <!-- Python内存卡片 -->
            <el-col :span="12">
              <el-card shadow="hover" class="h-full">
                <span>Python内存</span>
                <el-tooltip :content="(server.py?.memory_usage || 0).toFixed(1) + '%'">
                  <div class="text-center mb-4">
                    <el-progress
                      type="circle"
                      :percentage="server.py?.memory_usage || 0"
                      :status="
                        server.py?.memory_usage > 80
                          ? 'exception'
                          : server.py?.memory_usage > 60
                            ? 'warning'
                            : 'success'
                      "
                    />
                  </div>
                </el-tooltip>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="总内存">
                    {{ server.py?.memory_total }}
                  </el-descriptions-item>
                  <el-descriptions-item label="已用内存">
                    {{ server.py?.memory_used }}
                  </el-descriptions-item>
                  <el-descriptions-item label="空闲内存">
                    {{ server.py?.memory_free }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <el-col :span="24" class="mb-4">
        <el-card :loading="loading">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Odometer /></el-icon>
              <span class="font-medium">GPU 使用情况</span>
              <el-tooltip content="宿主机 NVIDIA 显卡实时状态，与训练容器是否可用无关">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
              <el-tag v-if="server.gpu?.driver_version" size="small" type="info">
                驱动 {{ server.gpu.driver_version }}
              </el-tag>
              <el-tag v-if="server.gpu?.cuda_version" size="small" type="info">
                驱动支持 CUDA {{ server.gpu.cuda_version }}
              </el-tag>
            </div>
          </template>

          <el-empty
            v-if="!server.gpu?.available"
            :image-size="60"
            :description="server.gpu?.error || '未检测到 NVIDIA GPU'"
          />

          <el-row v-else :gutter="16">
            <el-col
              v-for="d in server.gpu.devices"
              :key="d.index"
              :xs="24"
              :sm="24"
              :md="12"
              :lg="12"
              class="mb-4"
            >
              <el-card shadow="never">
                <div class="flex items-center gap-2 mb-3">
                  <span class="font-medium">GPU {{ d.index }}</span>
                  <span>{{ d.name }}</span>
                  <el-tooltip v-if="d.uuid" :content="d.uuid">
                    <el-tag size="small" type="info">{{ d.uuid.slice(0, 12) }}…</el-tag>
                  </el-tooltip>
                </div>
                <el-row :gutter="16">
                  <el-col :span="12">
                    <span>显存</span>
                    <div class="text-center my-2">
                      <el-progress
                        type="circle"
                        :percentage="d.usage"
                        :status="usageStatus(d.usage)"
                        :format="() => d.usage + '%'"
                      />
                    </div>
                    <el-descriptions :column="1" border>
                      <el-descriptions-item label="总量">{{ d.total }}</el-descriptions-item>
                      <el-descriptions-item label="已用">{{ d.used }}</el-descriptions-item>
                      <el-descriptions-item label="可用">{{ d.free }}</el-descriptions-item>
                    </el-descriptions>
                  </el-col>
                  <el-col :span="12">
                    <span>核心利用率</span>
                    <div class="text-center my-2">
                      <el-progress
                        type="circle"
                        :percentage="d.utilization"
                        :status="usageStatus(d.utilization)"
                        :format="() => d.utilization + '%'"
                      />
                    </div>
                    <el-descriptions :column="1" border>
                      <el-descriptions-item label="温度">
                        {{ d.temperature ?? "-" }} ℃
                      </el-descriptions-item>
                      <el-descriptions-item label="当前功耗">
                        {{ d.power || "-" }}
                      </el-descriptions-item>
                      <el-descriptions-item label="功耗上限">
                        {{ d.power_limit || "-" }}
                      </el-descriptions-item>
                    </el-descriptions>
                  </el-col>
                </el-row>
              </el-card>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <el-col :span="24" class="mb-4">
        <el-card :loading="loading">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Monitor /></el-icon>
              <span class="font-medium">服务器基本信息</span>
              <el-tooltip content="展示服务器基本配置信息">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="服务器名称">
              {{ server.sys?.computer_name || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="操作系统">
              {{ server.sys?.os_name || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="服务器IP">
              {{ server.sys?.computer_ip || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="系统架构">
              {{ server.sys?.os_arch || "-" }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="24" class="mb-4">
        <el-card :loading="loading">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Platform /></el-icon>
              <span class="font-medium">训练环境</span>
              <el-tooltip
                content="训练服务（TorchKiln）上报的运行时版本——torch / CUDA / cuDNN 只有训练容器里才有，本机不装 torch"
              >
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>

          <el-alert
            v-if="!server.torch_env?.available"
            type="warning"
            :closable="false"
            :title="server.torch_env?.error || '训练服务不可达'"
            description="训练环境版本需从训练服务读取，服务未启动时无法展示；上方 GPU 信息不受影响。"
          />

          <template v-else>
            <el-descriptions :column="3" border>
              <el-descriptions-item label="训练框架">
                {{ server.torch_env?.framework || "-" }}
                {{ server.torch_env?.framework_version || "" }}
              </el-descriptions-item>
              <el-descriptions-item label="PyTorch">
                {{ server.torch_env?.torch || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="CUDA 运行时">
                {{ server.torch_env?.cuda || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="cuDNN">
                {{ server.torch_env?.cudnn || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="Python">
                {{ server.torch_env?.python || "-" }}
              </el-descriptions-item>
              <el-descriptions-item label="训练用 GPU">
                {{ server.torch_env?.device || "-" }}
                <template v-if="server.torch_env?.device_count">
                  （{{ server.torch_env.device_count }} 张）
                </template>
              </el-descriptions-item>
            </el-descriptions>

            <el-alert
              class="mt-3"
              type="info"
              :closable="false"
              title="两个 CUDA 版本的区别"
              description="「驱动支持 CUDA」是本机显卡驱动能支持的上限；「CUDA 运行时」是训练环境的 PyTorch 编译时链接的版本。两者不一致是正常的，实际训练用的是运行时版本。"
            />
          </template>
        </el-card>
      </el-col>

      <el-col :span="24" class="mb-4">
        <el-card :loading="loading" class="shadow-sm">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Dish /></el-icon>
              <span class="font-medium">Python运行环境</span>
              <el-tooltip content="展示Python环境配置及运行状态">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="Python名称">
              {{ server.py?.name || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="Python版本">
              {{ server.py?.version || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="启动时间">
              {{ server.py?.start_time || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="运行时长">
              {{ server.py?.run_time || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="安装路径">
              {{ server.py?.home || "-" }}
            </el-descriptions-item>
            <el-descriptions-item label="项目路径">
              {{ server.sys?.user_dir || "-" }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :span="24">
        <el-card :loading="loading">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon>
                <Files />
              </el-icon>
              <span class="font-medium">磁盘使用情况</span>
              <el-tooltip content="展示磁盘空间使用详情">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-table :data="server.disks" border stripe>
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column label="盘符路径" prop="dir_name" :show-overflow-tooltip="true" />
            <el-table-column label="文件系统" prop="sys_type_name" align="center" width="100" />
            <el-table-column label="盘符名称" prop="type_name" />
            <el-table-column prop="usage" label="使用率" align="center">
              <template #default="{ row }">
                <!-- 使用 element-plus 的 Progress 组件 -->
                <div>
                  <el-progress
                    :percentage="Number(row.usage)"
                    :status="row.usage > 80 ? 'exception' : row.usage > 60 ? 'warning' : 'success'"
                    :text-inside="true"
                    :stroke-width="16"
                  />
                </div>
              </template>
            </el-table-column>
            <el-table-column label="总大小" prop="total" align="center" width="100" />
            <el-table-column label="可用大小" prop="free" align="center" width="100" />
            <el-table-column label="已用大小" prop="used" align="center" width="100" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script lang="ts" setup>
import ServerAPI, { type ServerInfo } from "@/api/module_monitor/server";

const loading = ref(false);
const server = ref<ServerInfo>({
  cpu: {
    cpu_num: 0,
    used: 0,
    sys: 0,
    free: 0,
  },
  mem: {
    total: "",
    used: "",
    free: "",
    usage: 0,
  },
  sys: {
    computer_name: "",
    os_name: "",
    computer_ip: "",
    os_arch: "",
    user_dir: "",
  },
  py: {
    name: "",
    version: "",
    start_time: "",
    run_time: "",
    home: "",
    memory_total: "",
    memory_used: "",
    memory_free: "",
    memory_usage: 0,
  },
  disks: [],
  gpu: {
    available: false,
    error: "",
    driver_version: null,
    cuda_version: null,
    device_count: 0,
    devices: [],
  },
  torch_env: {
    available: false,
    error: "",
    framework: null,
    framework_version: null,
    python: null,
    torch: null,
    cuda: null,
    cudnn: null,
    device: null,
    device_count: 0,
  },
});

/** 占用率 -> 进度条状态，阈值与本页 CPU/内存保持一致 */
const usageStatus = (value: number): "success" | "warning" | "exception" => {
  if (value > 80) return "exception";
  if (value > 60) return "warning";
  return "success";
};

async function getList() {
  loading.value = true;
  try {
    const response = await ServerAPI.getServer();
    server.value = response.data.data;
  } catch (error) {
    console.error("获取服务器信息失败:", error);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  getList();
});
</script>

<style lang="scss" scoped></style>
