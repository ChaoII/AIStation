<!-- 数据与集成 Data Connection & Integration（Palantir Foundry 支柱） -->
<template>
  <div class="app-container ai-integration-page">
    <el-row :gutter="12">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="mi-head">
              <span>数据连接（Connection）</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openDs">
                新建连接
              </el-button>
            </div>
          </template>
          <el-table :data="datasources" size="small" border>
            <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
            <el-table-column prop="type" label="类型" width="80" />
            <el-table-column label="地址" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.host }}:{{ row.port }}/{{ row.database }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="testDs(row)">测试</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            <div class="mi-head">
              <span>数据管道（Pipeline）</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openPipe">
                新建管道
              </el-button>
            </div>
          </template>
          <el-table :data="pipelines" size="small" border max-height="420">
            <el-table-column prop="name" label="管道" min-width="130" show-overflow-tooltip />
            <el-table-column label="源→目标" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.source_table }} → {{ row.target_object }}
              </template>
            </el-table-column>
            <el-table-column label="运行" width="80" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="runPipe(row)">运行</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import {
  getQueryDatasources,
  testQueryDatasource,
  getPipelineList,
  runPipeline,
} from "@/api/module_ai/query";

const datasources = ref<any[]>([]);
const pipelines = ref<any[]>([]);
async function load() {
  try {
    const [d, p] = await Promise.all([getQueryDatasources(), getPipelineList()]);
    datasources.value = d.data?.data || [];
    pipelines.value = p.data?.data || [];
  } catch {
    datasources.value = [];
    pipelines.value = [];
  }
}
async function testDs(row: any) {
  const r = await testQueryDatasource(row.id);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](d.message || (d.ok ? "连接成功" : "连接失败"));
}
async function runPipe(row: any) {
  const r = await runPipeline(row.id);
  const d = r.data?.data || {};
  ElMessage[d.ok ? "success" : "error"](d.msg || "已运行");
  load();
}
function openDs() {
  ElMessage.info("请在「智能问数→指标运营→数据源」标签中管理连接详情");
}
function openPipe() {
  ElMessage.info("请在「智能问数→指标运营→数据管道」标签中管理管道详情");
}
onMounted(load);
</script>

<style scoped lang="scss">
.ai-integration-page {
  padding: 12px;
}
.mi-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
