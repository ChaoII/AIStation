<template>
  <div class="app-container">
    <el-card shadow="never">
      <template #header>
        <div class="ov-head">
          <span>大模型控制台</span>
          <el-button size="small" @click="load">刷新</el-button>
        </div>
      </template>
      <el-descriptions :column="5" border>
        <el-descriptions-item label="提供商">{{ stats.providers }}</el-descriptions-item>
        <el-descriptions-item label="模型">{{ stats.models }}</el-descriptions-item>
        <el-descriptions-item label="调用次数">{{ stats.calls }}</el-descriptions-item>
        <el-descriptions-item label="错误次数">
          <el-tag :type="stats.errors ? 'danger' : 'success'" size="small" effect="plain">
            {{ stats.errors }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="平均耗时">{{ stats.avg_latency_ms }} ms</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-row :gutter="16" class="ov-row">
      <el-col :xs="24" :md="16">
        <el-card shadow="never">
          <template #header>最近调用</template>
          <el-table :data="stats.recent_calls" size="small" stripe>
            <el-table-column prop="model_name" label="模型" min-width="140">
              <template #default="{ row }">{{ row.model_name || "—" }}</template>
            </el-table-column>
            <el-table-column prop="usage" label="用途" min-width="100" />
            <el-table-column prop="latency_ms" label="耗时" min-width="100">
              <template #default="{ row }">{{ row.latency_ms }}ms</template>
            </el-table-column>
            <el-table-column label="结果" min-width="90">
              <template #default="{ row }">
                <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
                  {{ row.result === "success" ? "成功" : "失败" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="created_time"
              label="时间"
              min-width="170"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" description="暂无调用记录，去运行台问一句试试" />
            </template>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="8">
        <el-card shadow="never">
          <template #header>快捷入口</template>
          <el-space direction="vertical" alignment="flex-start" :size="10" style="width: 100%">
            <el-button class="ov-quick" @click="go('/ai/provider')">配置提供商 / API Key</el-button>
            <el-button class="ov-quick" @click="go('/ai/model')">添加并启用模型</el-button>
            <el-button class="ov-quick" @click="go('/ai/playground')">打开运行台试运行</el-button>
            <el-button class="ov-quick" @click="go('/ai/report')">查看 AI 报告</el-button>
          </el-space>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { getAiOverviewStats } from "@/api/module_ai/overview";

const router = useRouter();
const stats = reactive<any>({
  providers: 0,
  models: 0,
  reports: 0,
  calls: 0,
  errors: 0,
  avg_latency_ms: 0,
  recent_calls: [],
});

async function load() {
  try {
    const res = await getAiOverviewStats();
    Object.assign(stats, res.data?.data || {});
  } catch {
    /* 静默 */
  }
}

function go(path: string) {
  router.push(path);
}

onMounted(load);
</script>

<style scoped lang="scss">
.ov-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ov-row {
  margin-top: 16px;
}

.ov-quick {
  justify-content: flex-start;
  width: 100%;
  margin-left: 0 !important;
}
</style>
