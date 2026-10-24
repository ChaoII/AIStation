<template>
  <div class="app-container">
    <el-row :gutter="16">
      <el-col :span="12" class="mb-4">
        <el-card :loading="loading" shadow="hover">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Cpu /></el-icon>
              <span class="flex items-center gap-2">{{ t("monitor.serverCpuUsage") }}</span>
              <el-tooltip :content="t('monitor.serverCpuTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-row :gutter="16">
            <!-- CPU核心数卡片 -->
            <el-col :span="12">
              <el-card shadow="hover">
                <span>{{ t("monitor.serverCoreCount") }}</span>
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
                  <el-descriptions-item :label="t('monitor.serverTotalCores')">
                    {{ server.cpu?.cpu_num || 0 }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.serverUsedCores')">
                    {{ Math.floor(((server.cpu?.used || 0) * server.cpu?.cpu_num) / 100) }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.serverFreeCores')">
                    {{ Math.floor(((server.cpu?.free || 0) * server.cpu?.cpu_num) / 100) }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
            <!-- CPU使用率卡片 -->
            <el-col :span="12">
              <el-card shadow="hover" class="h-full">
                <span>{{ t("monitor.usageRate") }}</span>
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
                  <el-descriptions-item :label="t('monitor.serverUserUsageRate')">
                    {{ (server.cpu?.used || 0).toFixed(1) + "%" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.serverSysUsageRate')">
                    {{ (server.cpu?.sys || 0).toFixed(1) + "%" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.serverFreeRate')">
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
              <span>{{ t("monitor.serverMemUsage") }}</span>
              <el-tooltip :content="t('monitor.serverMemTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-row :gutter="16">
            <!-- 系统内存卡片 -->
            <el-col :span="12">
              <el-card shadow="hover" class="h-full">
                <span>{{ t("monitor.serverSysMem") }}</span>
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
                  <el-descriptions-item :label="t('monitor.totalMem')">
                    {{ server.mem?.total }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.usedMem')">
                    {{ server.mem?.used }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.freeMem')">
                    {{ server.mem?.free }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
            <!-- Python内存卡片 -->
            <el-col :span="12">
              <el-card shadow="hover" class="h-full">
                <span>{{ t("monitor.serverPyMem") }}</span>
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
                  <el-descriptions-item :label="t('monitor.totalMem')">
                    {{ server.py?.memory_total }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.usedMem')">
                    {{ server.py?.memory_used }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.freeMem')">
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
              <span class="font-medium">{{ t("monitor.serverGpuUsage") }}</span>
              <el-tooltip :content="t('monitor.serverGpuTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
              <el-tag v-if="server.gpu?.driver_version" size="small" type="info">
                {{ t("monitor.serverGpuDriver", { ver: server.gpu.driver_version }) }}
              </el-tag>
              <el-tag v-if="server.gpu?.cuda_version" size="small" type="info">
                {{ t("monitor.serverGpuCuda", { ver: server.gpu.cuda_version }) }}
              </el-tag>
            </div>
          </template>

          <el-empty
            v-if="!server.gpu?.available"
            :image-size="60"
            :description="server.gpu?.error || t('monitor.serverNoGpu')"
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
                  <span class="font-medium">
                    {{ t("monitor.serverGpuIndex", { index: d.index }) }}
                  </span>
                  <span>{{ d.name }}</span>
                  <el-tooltip v-if="d.uuid" :content="d.uuid">
                    <el-tag size="small" type="info">{{ d.uuid.slice(0, 12) }}…</el-tag>
                  </el-tooltip>
                </div>
                <el-row :gutter="16">
                  <el-col :span="12">
                    <span>{{ t("monitor.serverVram") }}</span>
                    <div class="text-center my-2">
                      <el-progress
                        type="circle"
                        :percentage="d.usage"
                        :status="usageStatus(d.usage)"
                        :format="() => d.usage + '%'"
                      />
                    </div>
                    <el-descriptions :column="1" border>
                      <el-descriptions-item :label="t('monitor.serverTotal')">
                        {{ d.total }}
                      </el-descriptions-item>
                      <el-descriptions-item :label="t('monitor.serverUsed')">
                        {{ d.used }}
                      </el-descriptions-item>
                      <el-descriptions-item :label="t('monitor.serverFree')">
                        {{ d.free }}
                      </el-descriptions-item>
                    </el-descriptions>
                  </el-col>
                  <el-col :span="12">
                    <span>{{ t("monitor.serverCoreUtil") }}</span>
                    <div class="text-center my-2">
                      <el-progress
                        type="circle"
                        :percentage="d.utilization"
                        :status="usageStatus(d.utilization)"
                        :format="() => d.utilization + '%'"
                      />
                    </div>
                    <el-descriptions :column="1" border>
                      <el-descriptions-item :label="t('monitor.serverTemp')">
                        {{ d.temperature ?? "-" }} ℃
                      </el-descriptions-item>
                      <el-descriptions-item :label="t('monitor.serverPower')">
                        {{ d.power || "-" }}
                      </el-descriptions-item>
                      <el-descriptions-item :label="t('monitor.serverPowerLimit')">
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
              <span class="font-medium">{{ t("monitor.serverBasicInfo") }}</span>
              <el-tooltip :content="t('monitor.serverBasicInfoTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-descriptions :column="2" border>
            <el-descriptions-item :label="t('monitor.serverName')">
              {{ server.sys?.computer_name || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.os')">
              {{ server.sys?.os_name || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverIp')">
              {{ server.sys?.computer_ip || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverArch')">
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
              <span class="font-medium">{{ t("monitor.serverTrainEnv") }}</span>
              <el-tooltip :content="t('monitor.serverTrainEnvTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>

          <el-alert
            v-if="!server.torch_env?.available"
            type="warning"
            :closable="false"
            :title="server.torch_env?.error || t('monitor.serverTrainEnvUnavailable')"
            :description="t('monitor.serverTrainEnvUnavailableDesc')"
          />

          <template v-else>
            <el-descriptions :column="3" border>
              <el-descriptions-item :label="t('monitor.serverTrainFramework')">
                {{ server.torch_env?.framework || "-" }}
                {{ server.torch_env?.framework_version || "" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('monitor.serverPytorch')">
                {{ server.torch_env?.torch || "-" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('monitor.serverCudaRuntime')">
                {{ server.torch_env?.cuda || "-" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('monitor.serverCudnn')">
                {{ server.torch_env?.cudnn || "-" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('monitor.serverPython')">
                {{ server.torch_env?.python || "-" }}
              </el-descriptions-item>
              <el-descriptions-item :label="t('monitor.serverTrainGpu')">
                {{ server.torch_env?.device || "-" }}
                <template v-if="server.torch_env?.device_count">
                  {{ t("monitor.serverGpuCount", { count: server.torch_env.device_count }) }}
                </template>
              </el-descriptions-item>
            </el-descriptions>

            <el-alert
              class="mt-3"
              type="info"
              :closable="false"
              :title="t('monitor.serverCudaDiffTitle')"
              :description="t('monitor.serverCudaDiffDesc')"
            />
          </template>
        </el-card>
      </el-col>

      <el-col :span="24" class="mb-4">
        <el-card :loading="loading" class="shadow-sm">
          <template #header>
            <div class="flex items-center gap-2">
              <el-icon><Dish /></el-icon>
              <span class="font-medium">{{ t("monitor.serverPyEnv") }}</span>
              <el-tooltip :content="t('monitor.serverPyEnvTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-descriptions :column="3" border>
            <el-descriptions-item :label="t('monitor.serverPyName')">
              {{ server.py?.name || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverPyVersion')">
              {{ server.py?.version || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverPyStartTime')">
              {{ server.py?.start_time || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverPyRunTime')">
              {{ server.py?.run_time || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverPyInstallPath')">
              {{ server.py?.home || "-" }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('monitor.serverPyProjectPath')">
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
              <span class="font-medium">{{ t("monitor.serverDiskUsage") }}</span>
              <el-tooltip :content="t('monitor.serverDiskTip')">
                <el-icon><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
          <el-table :data="server.disks" border stripe>
            <template #empty>
              <el-empty :image-size="80" :description="t('monitor.noData')" />
            </template>
            <el-table-column
              :label="t('monitor.serverDiskPath')"
              prop="dir_name"
              :show-overflow-tooltip="true"
            />
            <el-table-column
              :label="t('monitor.serverFileSystem')"
              prop="sys_type_name"
              align="center"
              width="100"
            />
            <el-table-column :label="t('monitor.serverDiskName')" prop="type_name" />
            <el-table-column prop="usage" :label="t('monitor.usageRate')" align="center">
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
            <el-table-column
              :label="t('monitor.serverDiskTotal')"
              prop="total"
              align="center"
              width="100"
            />
            <el-table-column
              :label="t('monitor.serverDiskFree')"
              prop="free"
              align="center"
              width="100"
            />
            <el-table-column
              :label="t('monitor.serverDiskUsed')"
              prop="used"
              align="center"
              width="100"
            />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import ServerAPI, { type ServerInfo } from "@/api/module_monitor/server";

const { t } = useI18n();

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
    console.error(t("monitor.serverGetInfoError"), error);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  getList();
});
</script>

<style lang="scss" scoped></style>
