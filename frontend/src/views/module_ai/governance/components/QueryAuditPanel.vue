<!-- 问答体检：可疑指标 / 抢答题 / 悬空引用（只读发现；处置走指标页与各语义页） -->
<template>
  <div class="qga">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      :title="`共 ${stats.total_metrics || 0} 个启用指标，扫描 ${stats.total_cases || 0} 道题；可疑 ${stats.suspect || 0} 个，抢答 ${stats.hijacking || 0} 条，悬空引用 ${stats.dangling_total || 0} 条。停用只关开关，不改口径。`"
      class="qga__tip"
    />
    <div class="qga__bar">
      <span class="qga__label">数据源</span>
      <el-select v-model="ds" size="small" style="width: 220px" @change="load">
        <el-option v-for="d in dsList" :key="d.code" :label="d.name" :value="d.code" />
      </el-select>
      <span class="qga__label">扫描范围</span>
      <el-select
        v-model="dataset"
        size="small"
        placeholder="全部题库"
        style="width: 200px"
        @change="load"
      >
        <el-option label="全部题库" value="" />
        <el-option
          v-for="d in stats.datasets_scanned || []"
          :key="d"
          :label="d || '未标注数据集'"
          :value="d"
        />
      </el-select>
      <el-button size="small" :loading="loading" @click="load">重新体检</el-button>
      <span class="qga__hint">
        数据集：{{ (stats.datasets_scanned || []).filter(Boolean).join("、") || "—" }}
      </span>
    </div>

    <el-tabs v-model="tab" class="qga__tabs">
      <el-tab-pane label="可疑指标" name="metrics">
        <el-table
          v-loading="loading"
          :data="rows"
          border
          stripe
          size="small"
          height="100%"
          class="qga__table"
        >
          <el-table-column prop="name" label="指标名" min-width="220" show-overflow-tooltip />
          <el-table-column prop="table" label="绑定表/对象" min-width="180" show-overflow-tooltip />
          <el-table-column label="问题" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="r in row.reasons"
                :key="r"
                size="small"
                type="warning"
                effect="plain"
                style="margin-right: 4px"
              >
                {{ r }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="抢答" width="80" align="center">
            <template #default="{ row }">{{ row.questions?.length || 0 }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150" align="center">
            <template #default="{ row }">
              <el-button
                link
                type="danger"
                size="small"
                :loading="row._saving"
                @click="disableMetric(row)"
              >
                停用
              </el-button>
              <el-button link type="primary" size="small" @click="goFix">去改名</el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty :image-size="60" description="没有可疑指标" />
          </template>
        </el-table>
      </el-tab-pane>
      <el-tab-pane :label="`悬空引用 (${stats.dangling_total || 0})`" name="dangling">
        <el-table
          v-loading="loading"
          :data="dangling"
          border
          stripe
          size="small"
          height="100%"
          class="qga__table"
        >
          <el-table-column label="类型" width="140">
            <template #default="{ row }">
              <el-tag size="small" type="danger" effect="plain">
                {{ kindLabel(row.kind) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="ref" label="引用" min-width="200" show-overflow-tooltip />
          <el-table-column prop="detail" label="说明" min-width="260" show-overflow-tooltip />
          <el-table-column prop="fix" label="怎么处理" min-width="220" show-overflow-tooltip />
          <template #empty>
            <el-empty :image-size="60" description="没有悬空引用" />
          </template>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { getMetricsAudit, getQueryDatasources, setMetricEnabled } from "@/api/module_ai/query";

defineOptions({ name: "QueryAuditPanel" });

const router = useRouter();

const dsList = ref<any[]>([]);
const ds = ref("ds:6");
const dataset = ref("");
const loading = ref(false);
const tab = ref("metrics");
const rows = ref<any[]>([]);
const dangling = ref<any[]>([]);
const stats = ref<any>({});

const KIND_LABELS: Record<string, string> = {
  metric_object: "指标→本体对象",
  metric_table: "指标→表",
  entity_map: "实体映射→表",
  ontology_table: "本体对象→表",
  term_field: "术语→字段",
};

function kindLabel(kind: string) {
  return KIND_LABELS[kind] || kind;
}

async function loadDatasources() {
  try {
    const r = await getQueryDatasources();
    // 接口里 code 是 ezdcs_local 这类短名，问数侧统一用 ds:<id>
    const list = (r.data?.data || []).map((d: any) => ({
      code: `ds:${d.id}`,
      name: `${d.name}（${d.type}）`,
    }));
    dsList.value = list;
    if (!dsList.value.some((d: any) => d.code === ds.value) && dsList.value.length) {
      ds.value = dsList.value[0].code;
    }
  } catch {
    // 列数据源失败不阻塞体检，保留默认 ds:6
  }
}

async function load() {
  loading.value = true;
  try {
    const r = await getMetricsAudit({
      datasource: ds.value,
      top: 200,
      dataset: dataset.value || undefined,
    });
    const d = r.data?.data || {};
    stats.value = d;
    rows.value = (d.items || []).map((x: any) => ({ ...x, _saving: false }));
    dangling.value = d.dangling || [];
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "加载体检结果失败");
  } finally {
    loading.value = false;
  }
}

async function disableMetric(row: any) {
  try {
    await ElMessageBox.confirm(
      `将停用指标「${row.name}」。停用后它不再参与快路径，可在指标页随时重新启用；口径与数据不受影响。`,
      "停用指标",
      { type: "warning", confirmButtonText: "停用", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  row._saving = true;
  try {
    await setMetricEnabled({ key: row.key, enabled: false });
    ElMessage.success("已停用");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "停用失败");
  } finally {
    row._saving = false;
  }
}

function goFix() {
  router.push("/ai/integration");
}

onMounted(async () => {
  await loadDatasources();
  await load();
});
</script>

<style lang="scss" scoped>
.qga {
  display: flex;
  flex-direction: column;
  min-height: 420px;
  height: 100%;
}
.qga__tip {
  margin-bottom: 8px;
}
.qga__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.qga__label {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.qga__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.qga__tabs {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.qga__tabs :deep(.el-tabs__content) {
  flex: 1 1 auto;
  min-height: 0;
}
.qga__table {
  height: 100%;
}
</style>
