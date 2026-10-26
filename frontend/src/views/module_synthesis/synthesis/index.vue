<template>
  <div class="synthesis-page">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-header">
          <span>{{ t("synthesis.title") }}</span>
          <span class="card-sub">{{ t("synthesis.sub") }}</span>
        </div>
      </template>

      <el-form ref="formRef" :model="form" label-width="100px">
        <el-row :gutter="12">
          <el-col :xs="24" :md="8">
            <el-form-item :label="t('synthesis.plateType')">
              <el-select v-model="form.plate_type" style="width: 100%">
                <el-option v-for="t in plateTypes" :key="t.key" :label="t.label" :value="t.key" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="8">
            <el-form-item :label="t('synthesis.dataset')">
              <el-select
                v-model="form.dataset_id"
                :placeholder="t('synthesis.datasetPlaceholder')"
                clearable
                style="width: 100%"
              >
                <el-option v-for="d in datasetOptions" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="12" :md="4">
            <el-form-item :label="t('synthesis.count')">
              <el-input-number v-model="form.count" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :xs="12" :md="4">
            <el-form-item :label="t('synthesis.seed')">
              <el-input-number
                v-model="form.seed"
                :min="0"
                :max="999999"
                controls-position="right"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="t('synthesis.disturbance')">
          <div style="width: 100%">
            <el-collapse v-model="activeDisturbs" class="disturb-collapse">
              <el-collapse-item v-for="d in disturbanceDefs" :key="d.key" :name="d.key">
                <template #title>
                  <span class="disturb-title">
                    <span @click.stop>
                      <el-switch v-model="form.disturbances[d.key]" />
                    </span>
                    <span class="disturb-name">{{ d.label }}</span>
                    <el-tag
                      v-if="form.disturbances[d.key] === false"
                      size="small"
                      type="info"
                      effect="plain"
                    >
                      {{ t("synthesis.closed") }}
                    </el-tag>
                    <span class="disturb-sum">{{ disturbSummary(d) }}</span>
                  </span>
                </template>
                <el-row :gutter="12">
                  <el-col v-for="pm in d.params" :key="pm.key" :xs="24" :md="12">
                    <div class="param-row">
                      <span class="param-label">{{ pm.label }}</span>
                      <el-input-number
                        v-model="form.params[pm.key][0]"
                        :min="pm.min"
                        :max="pm.max"
                        :step="pm.step"
                        :precision="precisionOf(pm.step)"
                        controls-position="right"
                        class="param-num"
                      />
                      <span class="param-tilde">~</span>
                      <el-input-number
                        v-model="form.params[pm.key][1]"
                        :min="pm.min"
                        :max="pm.max"
                        :step="pm.step"
                        :precision="precisionOf(pm.step)"
                        controls-position="right"
                        class="param-num"
                      />
                    </div>
                  </el-col>
                </el-row>
              </el-collapse-item>
            </el-collapse>
            <div style="margin-top: 6px">
              <el-button icon="RefreshLeft" size="small" link type="primary" @click="resetParams">
                {{ t("synthesis.restoreDefault") }}
              </el-button>
              <el-button
                :icon="activeDisturbs.length ? 'ArrowUp' : 'ArrowDown'"
                size="small"
                link
                @click="toggleAll"
              >
                {{ activeDisturbs.length ? t("synthesis.collapseAll") : t("synthesis.expandAll") }}
              </el-button>
              <span class="disturb-hint">{{ t("synthesis.disturbHint") }}</span>
            </div>
          </div>
        </el-form-item>

        <el-form-item :label="t('synthesis.output')">
          <el-switch
            v-model="form.upload"
            :active-text="t('synthesis.writeDataset')"
            :inactive-text="t('synthesis.previewOnly')"
            style="margin-right: 20px"
          />
          <el-switch
            v-model="form.with_annotation"
            :active-text="t('synthesis.writeAnnotation')"
            :inactive-text="t('synthesis.noAnnotation')"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" :icon="MagicStick" @click="onGenerate">
            {{ t("synthesis.start") }}
          </el-button>
          <span class="config-tip">{{ t("synthesis.tip") }}</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="items.length" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>{{ t("synthesis.resultCount", { count: items.length }) }}</span>
          <span class="card-sub">
            {{ uploaded ? t("synthesis.writeDataset") : t("synthesis.notUploaded") }} ·
            {{ t("synthesis.taskNo", { id: lastJobId }) }}
          </span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col v-for="it in items" :key="it.filename" :xs="24" :sm="12" :md="8" :lg="6">
          <div class="result-item">
            <img :src="it.preview_base64" :alt="t('synthesis.resultAlt')" class="result-img" />
            <div class="result-meta">
              <div class="result-text">
                <el-tag size="small" effect="plain">{{ it.text || it.label }}</el-tag>
              </div>
              <div class="result-sub">
                bbox ({{ fmt(it.bbox.x1) }}, {{ fmt(it.bbox.y1) }}, {{ fmt(it.bbox.x2) }},
                {{ fmt(it.bbox.y2) }})
              </div>
              <div v-if="it.image_id" class="result-sub">
                {{ t("synthesis.savedStore", { id: it.image_id }) }}
              </div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="history-card">
      <template #header>
        <div class="card-header">
          <span>{{ t("synthesis.historyTitle") }}</span>
          <el-button size="small" :icon="Refresh" @click="loadJobs">
            {{ t("synthesis.refresh") }}
          </el-button>
        </div>
      </template>
      <el-table border stripe :data="jobs" size="default">
        <template #empty>
          <el-empty :image-size="80" :description="t('synthesis.noJobs')" />
        </template>
        <el-table-column prop="id" :label="t('synthesis.jobId')" width="80" />
        <el-table-column prop="plate_type_label" :label="t('synthesis.plateType')" width="150" />
        <el-table-column prop="params" :label="t('synthesis.params')" min-width="180">
          <template #default="{ row }">
            <span class="dim">{{ paramText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total" :label="t('synthesis.total')" width="70" />
        <el-table-column prop="status" :label="t('synthesis.status')" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="
                row.status === 'completed'
                  ? 'success'
                  : row.status === 'running'
                    ? 'warning'
                    : row.status === 'failed'
                      ? 'danger'
                      : 'info'
              "
            >
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" :label="t('synthesis.createdTime')" width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { MagicStick, Refresh } from "@element-plus/icons-vue";
import {
  SynthesisAPI,
  type GeneratedPlateItem,
  type PlateTypeOption,
  type SynthesisJob,
} from "@/api/module_synthesis/synthesis";
import { getDatasetOptions } from "@/api/module_synthesis/dataset";

const { t } = useI18n();

interface DisturbParam {
  key: string;
  label: string;
  lo: number;
  hi: number;
  min: number;
  max: number;
  step: number;
}
interface DisturbDef {
  key: string;
  label: string;
  params: DisturbParam[];
}

const disturbanceDefs = ref<DisturbDef[]>([]);

const form = reactive({
  plate_type: "blue",
  dataset_id: undefined as number | undefined,
  count: 8,
  seed: undefined as number | undefined,
  upload: true,
  with_annotation: true,
  disturbances: {} as Record<string, boolean>,
  params: {} as Record<string, [number, number]>,
});

function initDisturbances(defs: DisturbDef[]) {
  disturbanceDefs.value = defs;
  const dist: Record<string, boolean> = {};
  const prm: Record<string, [number, number]> = {};
  for (const d of defs) {
    dist[d.key] = true;
    for (const p of d.params) prm[p.key] = [p.lo, p.hi];
  }
  form.disturbances = dist;
  form.params = prm;
}

function resetParams() {
  for (const d of disturbanceDefs.value) {
    for (const p of d.params) form.params[p.key] = [p.lo, p.hi];
  }
}

const activeDisturbs = ref<string[]>([]);

function disturbSummary(d: DisturbDef) {
  return d.params
    .map((p) => {
      const v = form.params[p.key];
      return v ? `${p.label} ${v[0]}~${v[1]}` : p.label;
    })
    .join("  ");
}

function toggleAll() {
  activeDisturbs.value = activeDisturbs.value.length ? [] : disturbanceDefs.value.map((d) => d.key);
}

function precisionOf(step: number) {
  const s = String(step);
  const i = s.indexOf(".");
  return i < 0 ? 0 : s.length - i - 1;
}

const formRef = ref();
const datasetOptions = ref<any[]>([]);
const plateTypes = ref<PlateTypeOption[]>([{ key: "blue", label: t("synthesis.plateTypeBlue") }]);
const items = ref<GeneratedPlateItem[]>([]);
const jobs = ref<SynthesisJob[]>([]);
const loading = ref(false);
const uploaded = ref(false);
const lastJobId = ref<number | null>(null);

function fmt(v?: number) {
  return v == null ? "-" : v.toFixed(2);
}
function statusText(s: string) {
  const map: Record<string, string> = {
    completed: t("synthesis.statusCompleted"),
    running: t("synthesis.statusRunning"),
    failed: t("synthesis.statusFailed"),
    pending: t("synthesis.statusPending"),
  };
  return map[s] || s;
}
function plateTypeLabel(key: string) {
  return plateTypes.value.find((t) => t.key === key)?.label || key;
}
function paramText(row: any) {
  const p = row.params || {};
  return `${plateTypeLabel(p.plate_type || "blue")} · ${t("synthesis.jobParamText", {
    count: p.count || row.total,
    mode: p.upload ? t("synthesis.store") : t("synthesis.preview"),
  })}`;
}

async function loadProviders() {
  try {
    const res = await SynthesisAPI.getProviders();
    const prov = res.data?.data?.find((p) => p.key === "license_plate");
    if (prov?.plate_types?.length) plateTypes.value = prov.plate_types;
    if (prov?.disturbances?.length) initDisturbances(prov.disturbances);
  } catch {
    /* ignore */
  }
}
async function loadDatasets() {
  try {
    const res = await getDatasetOptions();
    datasetOptions.value = res.data?.data?.items ?? [];
  } catch {
    datasetOptions.value = [];
  }
}
async function loadJobs() {
  try {
    const res = await SynthesisAPI.getJobs();
    const list = res.data?.data?.items ?? [];
    jobs.value = list.map((j) => ({
      ...j,
      plate_type_label: plateTypeLabel(j.params?.plate_type),
    }));
  } catch {
    jobs.value = [];
  }
}

async function onGenerate() {
  loading.value = true;
  try {
    const res = await SynthesisAPI.generatePlate({
      dataset_id: form.dataset_id,
      count: form.count,
      seed: form.seed,
      plate_type: form.plate_type,
      disturbances: { ...form.disturbances, params: form.params },
      upload: form.upload && !!form.dataset_id,
      with_annotation: form.with_annotation,
    });
    items.value = res.data?.data?.items ?? [];
    uploaded.value = !!res.data?.data?.uploaded;
    lastJobId.value = res.data?.data?.job_id ?? null;
    ElMessage.success(t("synthesis.generateSuccess", { count: items.value.length }));
    loadJobs();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("synthesis.generateFailed"));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadProviders();
  loadDatasets();
  loadJobs();
});
</script>

<style lang="scss" scoped>
.synthesis-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.disturb-collapse {
  border-top: none;
  .disturb-title {
    display: flex;
    align-items: center;
    gap: 8px;
    .disturb-name {
      font-weight: 600;
    }
    .disturb-sum {
      margin-left: 6px;
      font-size: var(--el-font-size-extra-small);
      color: var(--el-text-color-secondary);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
  .param-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 3px 0;
    .param-label {
      flex: 1 1 auto;
      min-width: 88px;
      font-size: var(--el-font-size-small);
      color: var(--el-text-color-regular);
    }
    .param-num {
      width: 110px;
      flex: 0 0 auto;
    }
    .param-tilde {
      color: var(--el-text-color-secondary);
    }
  }
}
.disturb-hint {
  margin-left: 8px;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
// 开关 label 与表单 label 一致（el-switch 自带 500，这里降到 400）
:deep(.el-switch__label) {
  font-weight: 400;
  color: var(--el-text-color-regular);
}
.config-card,
.result-card,
.history-card {
  .card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    .card-sub {
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }
}
.config-tip {
  margin-left: 12px;
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
.result-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  overflow: hidden;
  margin-bottom: 12px;
  .result-img {
    display: block;
    width: 100%;
    height: 130px;
    object-fit: cover;
    background: #000;
  }
  .result-meta {
    padding: 8px;
    .result-text {
      margin-bottom: 4px;
    }
    .result-sub {
      font-size: 12px;
      color: var(--el-text-color-secondary);
      line-height: 1.4;
    }
  }
}
.dim {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
