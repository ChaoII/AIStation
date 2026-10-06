<!-- 数据资产 Data Assets & Semantics（Palantir 底层：数据准备 + 语义单一事实源） -->
<template>
  <div class="app-container ai-mod ai-asset-page">
    <PageHeader
      title="数据资产"
      subtitle="平台底层数据准备：资产目录 / 指标 / 术语 / 概念 / 图谱 / 语义抽取（问数与 Agent 的接地底座）"
    />
    <el-tabs v-model="tab">
      <!-- 数据资产(表) -->
      <el-tab-pane label="数据资产" name="asset">
        <div class="as-bar">
          <el-button
            type="primary"
            size="small"
            :icon="Refresh"
            :loading="syncing"
            @click="syncAssets"
          >
            同步目录
          </el-button>
          <el-button size="small" :icon="MagicStick" :loading="genDesc" @click="genAssetDesc">
            LLM 生成描述
          </el-button>
          <el-button size="small" :icon="DataAnalysis" :loading="extracting" @click="extract">
            语义抽取(识别对象)
          </el-button>
          <el-tag size="small" type="info" effect="plain">共 {{ assets.length }} 张资产表</el-tag>
        </div>
        <el-table :data="assets" size="small" border max-height="420">
          <template #empty>
            <el-empty description="暂无数据，点击「同步目录」拉取资产" :image-size="60" />
          </template>
          <el-table-column prop="table_name" label="表" min-width="160" show-overflow-tooltip />
          <el-table-column prop="alias" label="别名" min-width="110" show-overflow-tooltip />
          <el-table-column prop="domain" label="数据域" width="90" />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column label="对象化" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.object_enabled ? 'success' : 'info'" effect="plain">
                {{ row.object_enabled ? "是" : "否" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="字段" width="70" align="center">
            <template #default="{ row }">{{ row.column_count ?? "-" }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 指标 -->
      <el-tab-pane label="指标" name="metric">
        <div class="as-bar">
          <el-tag size="small" type="info" effect="plain">语义指标（问数与 Agent 消费）</el-tag>
        </div>
        <el-table :data="metrics" size="small" border max-height="420">
          <el-table-column prop="name" label="指标" min-width="140" show-overflow-tooltip />
          <el-table-column prop="key" label="编码" min-width="120" show-overflow-tooltip />
          <el-table-column
            prop="sql_template"
            label="SQL 模板"
            min-width="200"
            show-overflow-tooltip
          />
        </el-table>
      </el-tab-pane>

      <!-- 术语 -->
      <el-tab-pane label="术语" name="term">
        <div class="as-bar">
          <el-tag size="small" type="info" effect="plain">业务黑话 ↔ 字段映射</el-tag>
        </div>
        <el-table :data="terms" size="small" border max-height="420">
          <el-table-column prop="term" label="术语" min-width="140" show-overflow-tooltip />
          <el-table-column prop="metric_key" label="指标" min-width="120" show-overflow-tooltip />
          <el-table-column
            prop="field_path"
            label="字段路径"
            min-width="200"
            show-overflow-tooltip
          />
        </el-table>
      </el-tab-pane>

      <!-- 概念 -->
      <el-tab-pane label="概念" name="concept">
        <div class="as-bar">
          <el-tag size="small" type="info" effect="plain">本体/概念（语义层）</el-tag>
        </div>
        <el-table :data="concepts" size="small" border max-height="420">
          <el-table-column prop="name" label="概念" min-width="140" show-overflow-tooltip />
          <el-table-column label="涉及表" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="t in row.tables || []"
                :key="t"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ t }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 图谱 -->
      <el-tab-pane label="图谱" name="kg">
        <div class="as-bar">
          <el-button size="small" :icon="Refresh" @click="syncKg">重建图谱</el-button>
          <el-tag size="small" type="info" effect="plain">schema 图谱 + 知识库 + 概念</el-tag>
        </div>
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="表节点">{{ kg.nodes ?? "-" }}</el-descriptions-item>
          <el-descriptions-item label="关系边">{{ kg.edges ?? "-" }}</el-descriptions-item>
          <el-descriptions-item label="实体">{{ kg.entities ?? "-" }}</el-descriptions-item>
        </el-descriptions>
        <div class="gov-section">可识别对象（对象化）</div>
        <el-table :data="objects" size="small" border max-height="300">
          <el-table-column prop="table" label="对象表" min-width="160" />
          <el-table-column prop="alias" label="别名" min-width="120" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, MagicStick, DataAnalysis } from "@element-plus/icons-vue";
import {
  getQueryAssets,
  syncQueryAssets,
  generateQueryAssetDesc,
  extractQueryObjects,
  getQueryMetrics,
  getQueryTerms,
  getQueryConcepts,
  getQueryKgStats,
  rebuildQueryKg,
  getQueryObjects,
} from "@/api/module_ai/query";

const tab = ref("asset");
const assets = ref<any[]>([]);
const metrics = ref<any[]>([]);
const terms = ref<any[]>([]);
const concepts = ref<any[]>([]);
const objects = ref<any[]>([]);
const kg = ref<any>({});
const syncing = ref(false);
const genDesc = ref(false);
const extracting = ref(false);

async function loadAssets() {
  const r = await getQueryAssets();
  assets.value = r.data?.data || [];
}
async function loadMetrics() {
  const r = await getQueryMetrics();
  metrics.value = r.data?.data || [];
}
async function loadTerms() {
  const r = await getQueryTerms();
  terms.value = r.data?.data || [];
}
async function loadConcepts() {
  const r = await getQueryConcepts();
  concepts.value = r.data?.data || [];
}
async function loadKg() {
  const r = await getQueryKgStats();
  kg.value = r.data?.data || {};
}
async function loadObjects() {
  const r = await getQueryObjects();
  objects.value = r.data?.data || [];
}

async function syncAssets() {
  syncing.value = true;
  try {
    await syncQueryAssets();
    ElMessage.success("目录已同步");
    await loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "同步失败");
  } finally {
    syncing.value = false;
  }
}
async function genAssetDesc() {
  genDesc.value = true;
  try {
    const r = await generateQueryAssetDesc();
    ElMessage.success(r.data?.msg || "描述已生成");
    await loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "生成失败");
  } finally {
    genDesc.value = false;
  }
}
async function extract() {
  extracting.value = true;
  try {
    const r = await extractQueryObjects();
    ElMessage.success(`已识别 ${r.data?.data?.length ?? 0} 个对象`);
    await loadObjects();
  } catch (e: any) {
    ElMessage.error(e?.msg || "抽取失败");
  } finally {
    extracting.value = false;
  }
}
async function syncKg() {
  try {
    await rebuildQueryKg();
    ElMessage.success("图谱已重建");
    await loadKg();
  } catch (e: any) {
    ElMessage.error(e?.msg || "失败");
  }
}

onMounted(() => {
  loadAssets();
  loadMetrics();
  loadTerms();
  loadConcepts();
  loadKg();
  loadObjects();
});
</script>

<style scoped lang="scss">
.ai-asset-page {
  padding: 12px;
}
.as-bar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gov-section {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin: 8px 0 4px;
}
</style>
