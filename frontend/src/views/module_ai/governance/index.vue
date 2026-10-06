<!-- 治理 Governance / Oversight（Palantir Foundry 支柱） -->
<template>
  <div class="app-container ai-governance-page">
    <el-card shadow="never" style="margin-bottom: 12px">
      <template #header>治理驾驶舱（Governance Overview）</template>
      <el-row :gutter="12">
        <el-col :span="3">
          <el-statistic title="业务对象" :value="g.overview?.objects ?? 0" />
        </el-col>
        <el-col :span="3">
          <el-statistic title="数据源" :value="g.overview?.datasources ?? 0" />
        </el-col>
        <el-col :span="3">
          <el-statistic title="数据管道" :value="g.overview?.pipelines ?? 0" />
        </el-col>
        <el-col :span="3">
          <el-statistic title="ABAC 策略" :value="g.overview?.access_rules ?? 0" />
        </el-col>
        <el-col :span="3"><el-statistic title="数据域" :value="g.overview?.domains ?? 0" /></el-col>
        <el-col :span="3"><el-statistic title="智能体" :value="g.overview?.agents ?? 0" /></el-col>
        <el-col :span="3">
          <el-statistic title="动作审计" :value="g.overview?.action_logs ?? 0" />
        </el-col>
        <el-col :span="3">
          <el-statistic title="平均健康分" :value="g.overview?.dq?.avg_score ?? 0" :precision="1" />
        </el-col>
      </el-row>
    </el-card>

    <el-row :gutter="12">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="mg-head">
              <span>数据质量（DQ）</span>
              <el-tag v-if="(g.overview?.dq_alerts ?? 0) > 0" size="small" type="danger">
                预警 {{ g.overview.dq_alerts }}
              </el-tag>
            </div>
          </template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="平均健康分">
              {{ g.overview?.dq?.avg_score ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="健康/预警/共">
              {{ g.overview?.dq?.healthy ?? 0 }} / {{ g.overview?.dq?.risk ?? 0 }} /
              {{ g.overview?.dq?.total ?? 0 }}
            </el-descriptions-item>
          </el-descriptions>
          <div class="gov-section">质量预警</div>
          <div v-for="a in g.overview?.alert_list || []" :key="a.table" class="mg-alert">
            <el-tag size="small" type="danger">{{ a.alias }}</el-tag>
            <span class="mg-score">健康分 {{ a.score }}</span>
            <div class="mg-down">
              <el-tag
                v-for="o in a.downstream.objects"
                :key="o"
                size="small"
                type="warning"
                effect="plain"
              >
                对象 {{ o }}
              </el-tag>
              <el-tag
                v-for="m in a.downstream.metrics"
                :key="m"
                size="small"
                type="primary"
                effect="plain"
              >
                指标 {{ m }}
              </el-tag>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>资产与语义资产</template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="指标">{{ g.overview?.metrics ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="术语">{{ g.overview?.terms ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="本体概念">
              {{ g.overview?.concepts ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="对象应用">
              {{ g.overview?.workshop_apps ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="动作定义">
              {{ g.overview?.actions ?? 0 }}
            </el-descriptions-item>
            <el-descriptions-item label="动作审计">
              {{ g.overview?.action_logs ?? 0 }}
            </el-descriptions-item>
          </el-descriptions>
          <div class="gov-section">最近管道运行</div>
          <el-table :data="g.overview?.pipeline_runs || []" size="small" max-height="180">
            <el-table-column prop="name" label="管道" min-width="120" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'success' ? 'success' : 'info'">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="at" label="运行时间" min-width="140" show-overflow-tooltip />
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getGovernanceOverview } from "@/api/module_ai/query";

const g = ref<any>({ overview: {} });
async function load() {
  try {
    const r = await getGovernanceOverview();
    g.value = { overview: r.data?.data || {} };
  } catch {
    g.value = { overview: {} };
  }
}
onMounted(load);
</script>

<style scoped lang="scss">
.ai-governance-page {
  padding: 12px;
}
.mg-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mg-alert {
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
}
.mg-score {
  margin-left: 8px;
  font-size: 13px;
  color: var(--el-color-warning);
}
.mg-down {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
