<template>
  <div class="app-container">
    <el-tabs type="border-card" class="cache-page-tabs">
      <!-- 监控信息 Tab -->
      <el-tab-pane class="monitor" :label="t('monitor.cacheMonitorInfo')">
        <div class="monitor-tab">
          <el-row :gutter="16">
            <!-- 基本信息 -->
            <el-col :span="24">
              <el-card shadow="hover">
                <template #header>
                  <div class="flex items-center gap-2">
                    <el-icon>
                      <Monitor />
                    </el-icon>
                    <span>{{ t("monitor.cacheRedisMonitor") }}</span>
                    <el-tooltip :content="t('monitor.cacheRedisMonitorTip')">
                      <el-icon>
                        <QuestionFilled />
                      </el-icon>
                    </el-tooltip>
                  </div>
                </template>
                <el-descriptions :column="12" border :direction="'vertical'">
                  <el-descriptions-item :label="t('monitor.cacheRedisVersion')">
                    {{ cache.info?.redis_version || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheRunMode')">
                    {{
                      cache.info?.redis_mode === "standalone"
                        ? t("monitor.cacheStandalone")
                        : t("monitor.cacheCluster")
                    }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cachePort')">
                    {{ cache.info?.tcp_port || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheClients')">
                    {{ cache.info?.connected_clients || 0 }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheUptimeDays')">
                    {{ cache.info?.uptime_in_days || 0 }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheUsedMem')">
                    {{ cache.info?.used_memory_human || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheUsedCpu')">
                    {{
                      cache.info?.used_cpu_user_children
                        ? parseFloat(cache.info.used_cpu_user_children).toFixed(2)
                        : "-"
                    }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheMemConfig')">
                    {{ cache.info?.maxmemory_human || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheAofEnabled')">
                    {{
                      cache.info?.aof_enabled === "0" ? t("monitor.cacheNo") : t("monitor.cacheYes")
                    }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheRdbSuccess')">
                    {{ cache.info?.rdb_last_bgsave_status || "-" }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheKeyCount')">
                    {{ cache.db_size || 0 }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('monitor.cacheNetworkIo')">
                    {{
                      `${cache.info?.instantaneous_input_kbps || 0}kps/${cache.info?.instantaneous_output_kbps || 0}kps`
                    }}
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
          </el-row>

          <!-- 监控图表：单独一行并占满剩余高度 -->
          <el-row :gutter="16" class="monitor-charts-row">
            <el-col :span="12" class="cache-chart-col">
              <el-card shadow="hover" class="cache-chart-card">
                <template #header>
                  <div class="flex items-center gap-2">
                    <el-icon>
                      <Stopwatch />
                    </el-icon>
                    <span class="title">{{ t("monitor.cacheCmdStats") }}</span>
                    <el-tooltip :content="t('monitor.cacheCmdStatsTip')">
                      <el-icon>
                        <QuestionFilled />
                      </el-icon>
                    </el-tooltip>
                  </div>
                </template>
                <div ref="commandstats" class="chart-container" />
              </el-card>
            </el-col>

            <el-col :span="12" class="cache-chart-col">
              <el-card shadow="hover" class="cache-chart-card">
                <template #header>
                  <div class="flex items-center gap-2">
                    <el-icon>
                      <Stopwatch />
                    </el-icon>
                    <span>{{ t("monitor.cacheMemInfo") }}</span>
                    <el-tooltip :content="t('monitor.cacheMemInfoTip')">
                      <el-icon>
                        <QuestionFilled />
                      </el-icon>
                    </el-tooltip>
                  </div>
                </template>
                <div ref="usedmemory" class="chart-container" />
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- 缓存管理 Tab -->
      <el-tab-pane class="cache" :label="t('monitor.cacheMgmt')">
        <div class="cache-mgmt-tab">
          <el-row :gutter="16" class="cache-mgmt-row">
            <!-- 缓存列表 -->
            <el-col :span="8" class="cache-mgmt-col">
              <el-card :loading="loading" shadow="hover" class="cache-mgmt-card">
                <template #header>
                  <div class="flex justify-between items-center">
                    <div class="flex items-center gap-2">
                      <el-icon>
                        <Tickets />
                      </el-icon>
                      <span class="flex items-center gap-2">{{ t("monitor.cacheList") }}</span>
                      <el-tooltip :content="t('monitor.cacheListTip')">
                        <el-icon>
                          <QuestionFilled />
                        </el-icon>
                      </el-tooltip>
                    </div>
                    <div>
                      <el-button
                        v-hasPerm="['module_monitor:cache:query']"
                        type="primary"
                        link
                        icon="RefreshRight"
                        @click="refreshCacheNames"
                      />
                    </div>
                  </div>
                </template>
                <el-table
                  :loading="loading"
                  :data="cacheNames"
                  row-key="cache_name"
                  height="100%"
                  border
                  stripe
                >
                  <template #empty>
                    <el-empty :image-size="80" :description="t('monitor.noData')" />
                  </template>
                  <el-table-column
                    prop="cache_name"
                    :label="t('monitor.cacheName')"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <el-button
                        v-hasPerm="['module_monitor:cache:query']"
                        type="primary"
                        link
                        @click="getCacheKeyList(row as CacheInfo)"
                      >
                        {{ row.cache_name }}
                      </el-button>
                    </template>
                  </el-table-column>
                  <el-table-column
                    prop="remark"
                    :label="t('monitor.cacheRemark')"
                    show-overflow-tooltip
                  />
                  <el-table-column :label="t('monitor.operation')" width="60" align="center">
                    <template #default="{ row }">
                      <el-popconfirm
                        class="box-item"
                        :title="t('monitor.cacheDeleteNameConfirm', { name: row.cache_name })"
                        placement="top"
                        @confirm="handleClearCacheName(row as CacheInfo)"
                      >
                        <template #reference>
                          <el-button
                            v-hasPerm="['module_monitor:cache:delete']"
                            type="danger"
                            size="small"
                            link
                            icon="delete"
                          />
                        </template>
                      </el-popconfirm>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>

            <!-- 键名列表 -->
            <el-col :span="8" class="cache-mgmt-col">
              <el-card :loading="loading" shadow="hover" class="cache-mgmt-card">
                <template #header>
                  <div class="flex justify-between items-center">
                    <div class="flex items-center gap-2">
                      <el-icon>
                        <Key />
                      </el-icon>
                      <span class="flex items-center gap-2">{{ t("monitor.cacheKeyList") }}</span>
                      <el-tooltip :content="t('monitor.cacheKeyListTip')">
                        <el-icon>
                          <QuestionFilled />
                        </el-icon>
                      </el-tooltip>
                    </div>
                    <div>
                      <el-button
                        v-hasPerm="['module_monitor:cache:query']"
                        type="primary"
                        link
                        icon="RefreshRight"
                        @click="refreshCacheKeys"
                      />
                    </div>
                  </div>
                </template>
                <el-table
                  stripe
                  :loading="subLoading"
                  :data="cacheKeys.map((key) => ({ cacheKey: key }))"
                  height="100%"
                  row-key="cacheKey"
                  border
                >
                  <template #empty>
                    <el-empty :image-size="80" :description="t('monitor.noData')" />
                  </template>
                  <el-table-column
                    prop="cacheKey"
                    :label="t('monitor.cacheKeyName')"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">
                      <el-button
                        v-hasPerm="['module_monitor:cache:detail']"
                        type="primary"
                        link
                        @click="handleCacheValue(row.cacheKey)"
                      >
                        {{ row.cacheKey }}
                      </el-button>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('monitor.operation')" width="60" align="center">
                    <template #default="{ row }">
                      <el-popconfirm
                        class="box-item"
                        :title="t('monitor.cacheDeleteKeyConfirm', { key: row.cacheKey })"
                        placement="top"
                        @confirm="handleClearCacheKey(row.cacheKey)"
                      >
                        <template #reference>
                          <el-button
                            v-hasPerm="['module_monitor:cache:delete']"
                            type="danger"
                            size="small"
                            link
                            icon="delete"
                          />
                        </template>
                      </el-popconfirm>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>

            <!-- 缓存内容 -->
            <el-col :span="8">
              <el-card :loading="loading" shadow="hover">
                <template #header>
                  <div class="flex justify-between items-center">
                    <div class="flex items-center gap-2">
                      <el-icon>
                        <Key />
                      </el-icon>
                      <span class="flex items-center gap-2">{{ t("monitor.cacheContent") }}</span>
                      <el-tooltip :content="t('monitor.cacheContentTip')">
                        <el-icon>
                          <QuestionFilled />
                        </el-icon>
                      </el-tooltip>
                    </div>
                    <div>
                      <el-button
                        v-hasPerm="['module_monitor:cache:delete']"
                        type="danger"
                        link
                        icon="delete"
                        @click="handleClearCacheAll"
                      >
                        {{ t("monitor.cacheClearAll") }}
                      </el-button>
                    </div>
                  </div>
                </template>
                <el-form
                  :model="cacheForm"
                  label-suffix=":"
                  label-width="auto"
                  label-position="top"
                >
                  <el-form-item :label="t('monitor.cacheName')">
                    <el-input
                      v-model="cacheForm.cache_name"
                      readonly
                      :placeholder="t('monitor.cacheName')"
                    />
                  </el-form-item>
                  <el-form-item :label="t('monitor.cacheKeyName')">
                    <el-input
                      v-model="cacheForm.cache_key"
                      readonly
                      :placeholder="t('monitor.cacheKeyName')"
                    />
                  </el-form-item>
                  <el-form-item :label="t('monitor.cacheContent')">
                    <el-input
                      v-model="cacheForm.cache_value"
                      type="textarea"
                      :rows="20"
                      readonly
                      :placeholder="t('monitor.cacheContent')"
                    />
                  </el-form-item>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script lang="ts" setup>
import CacheAPI, {
  type CacheInfo,
  type CacheForm,
  type CacheMonitor,
  type RedisInfo,
} from "@/api/module_monitor/cache";
import * as echarts from "echarts";
import { useI18n } from "vue-i18n";

// 响应式状态定义
const { t } = useI18n();
const cacheNames = ref<CacheInfo[]>([]);
const cacheKeys = ref<string[]>([]);
const loading = ref(true);
const subLoading = ref(false);
const nowCacheName = ref("");
const commandstats = ref<HTMLElement | null>(null);
const usedmemory = ref<HTMLElement | null>(null);
const cache = ref<CacheMonitor>({
  info: {} as RedisInfo,
  command_stats: [],
  db_size: 0,
});
const cacheForm = ref<CacheForm>({
  cache_name: "",
  cache_key: "",
  cache_value: "",
});

let commandstatsInstance: echarts.ECharts | null = null;
let usedmemoryInstance: echarts.ECharts | null = null;

const resetCacheForm = () => {
  cacheKeys.value = [];
  cacheForm.value = {
    cache_name: "",
    cache_key: "",
    cache_value: "",
  };
};

// 缓存名称相关方法
const getCacheNameList = async () => {
  try {
    loading.value = true;
    const response = await CacheAPI.getCacheNames();
    cacheNames.value = response.data.data;
    resetCacheForm();
  } catch (error) {
    console.error(t("monitor.cacheGetListError"), error);
  } finally {
    loading.value = false;
  }
};

// 刷新缓存列表
const refreshCacheNames = () => {
  getCacheNameList();
};

// 清理缓存名称
const handleClearCacheName = async (row: CacheInfo) => {
  try {
    await CacheAPI.deleteCacheName(row.cache_name);
    refreshCacheNames();
  } catch (error) {
    console.error(t("monitor.cacheClearNameError"), error);
  }
};

// 缓存键名相关方法
const getCacheKeyList = async (row?: CacheInfo) => {
  try {
    const cacheName = row?.cache_name || nowCacheName.value;
    if (!cacheName) return;

    subLoading.value = true;
    const response = await CacheAPI.getCacheKeys(cacheName);
    cacheKeys.value = response.data.data;
    nowCacheName.value = cacheName;
    cacheForm.value = {
      cache_name: cacheName,
      cache_key: "",
      cache_value: "",
    };
  } catch (error) {
    console.error(t("monitor.cacheGetKeysError"), error);
  } finally {
    subLoading.value = false;
  }
};

// 刷新键名列表
const refreshCacheKeys = () => {
  getCacheKeyList();
};

// 清理缓存键名
async function handleClearCacheKey(cacheKey: string) {
  try {
    await CacheAPI.deleteCacheKey(cacheKey);
    getCacheKeyList();
  } catch (error) {
    console.error(t("monitor.cacheClearKeyError"), error);
  }
}

// 缓存内容相关方法
async function handleCacheValue(cacheKey: string) {
  try {
    loading.value = true;
    const response = await CacheAPI.getCacheValue(nowCacheName.value, cacheKey);
    cacheForm.value = response.data.data;
  } catch (error) {
    console.error(t("monitor.cacheGetContentError"), error);
  } finally {
    loading.value = false;
  }
}

// 清理全部缓存
const handleClearCacheAll = async () => {
  ElMessageBox.confirm(t("monitor.cacheClearAllConfirm"), t("monitor.cacheDanger"), {
    confirmButtonText: t("monitor.confirm"),
    cancelButtonText: t("monitor.cancel"),
    type: "warning",
  })
    .then(async () => {
      return await CacheAPI.deleteCacheAll();
    })
    .then(() => {
      getCacheNameList();
    })
    .catch((error) => {
      if (error !== "cancel") {
        console.error(t("monitor.cacheClearAllError"), error);
      }
    });
};

// 监控数据获取
const getInfo = async () => {
  try {
    loading.value = true;
    const response = await CacheAPI.getCacheInfo();
    cache.value = response.data.data || {
      info: {},
      command_stats: [],
      dbSize: 0,
    };
    initCharts();
  } catch (error) {
    console.error(t("monitor.cacheGetInfoError"), error);
  } finally {
    loading.value = false;
  }
};

// 图表初始化
const initCharts = () => {
  if (!commandstats.value || !usedmemory.value) return;

  commandstatsInstance = echarts.init(commandstats.value, "macarons");
  usedmemoryInstance = echarts.init(usedmemory.value, "macarons");

  const commandStatsOption = {
    tooltip: {
      trigger: "item",
      formatter: "{a} <br/>{b} : {c} ({d}%)",
    },
    series: [
      {
        name: t("monitor.cacheCommand"),
        type: "pie",
        roseType: "radius",
        radius: [15, 95],
        center: ["50%", "38%"],
        data: cache.value.command_stats || [],
        animationEasing: "cubicInOut",
        animationDuration: 1000,
      },
    ],
  };

  const usedMemory = cache.value.info?.used_memory_human || "0";
  const usedMemoryOption = {
    tooltip: {
      formatter: `{b} <br/>{a} : ${usedMemory}`,
    },
    series: [
      {
        name: t("monitor.cachePeak"),
        type: "gauge",
        min: 0,
        max: 1000,
        detail: {
          formatter: usedMemory,
        },
        data: [
          {
            value: parseFloat(usedMemory) || 0,
            name: t("monitor.cacheMemConsume"),
          },
        ],
      },
    ],
  };

  commandstatsInstance.setOption(commandStatsOption);
  usedmemoryInstance.setOption(usedMemoryOption);

  void nextTick(() => {
    commandstatsInstance?.resize();
    usedmemoryInstance?.resize();
  });
};

// 生命周期钩子
onMounted(() => {
  getCacheNameList();
  getInfo();
});

onUnmounted(() => {
  commandstatsInstance?.dispose();
  usedmemoryInstance?.dispose();
});
</script>

<style scoped lang="scss">
/* 与 .app-container 纵向 flex 衔接：tabs 占满剩余高度 */
.cache-page-tabs {
  display: flex;
  flex: 1;
  flex-direction: column;
  width: 100%;
  min-height: 0;

  :deep(.el-tabs__header) {
    flex-shrink: 0;
  }

  :deep(.el-tabs__content) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }

  :deep(.el-tab-pane) {
    box-sizing: border-box;
    flex: 1;
    min-height: 0;
    overflow: auto;
  }
}

.monitor-tab {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.monitor-charts-row {
  flex: 1;
  align-items: stretch;
  min-height: 0;
}

.cache-chart-col {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cache-chart-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;

  :deep(.el-card__body) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
  }
}

.chart-container {
  flex: 1;
  height: 100%;
  min-height: 200px;
}

.cache-mgmt-tab {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.cache-mgmt-row {
  flex: 1;
  align-items: stretch;
  min-height: 0;
}

.cache-mgmt-col {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.cache-mgmt-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;

  :deep(.el-card__body) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
  }
}
</style>
