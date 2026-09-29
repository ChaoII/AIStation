<template>
  <div class="synthesis-page">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-header">
          <span>车牌数据合成</span>
          <span class="card-sub">生成国内各类车牌（蓝/新能源/黄/双层/黑/教练/警用），带透视、旋转、噪点、污渍、遮挡、模糊等扰动，并产出检测框标注</span>
        </div>
      </template>

      <el-form ref="formRef" :model="form" label-width="100px">
        <el-row :gutter="12">
          <el-col :xs="24" :md="8">
            <el-form-item label="车牌类型">
              <el-select v-model="form.plate_type" style="width: 100%">
                <el-option v-for="t in plateTypes" :key="t.key" :label="t.label" :value="t.key" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :md="8">
            <el-form-item label="目标数据集">
              <el-select v-model="form.dataset_id" placeholder="写入的数据集" clearable style="width: 100%">
                <el-option v-for="d in datasetOptions" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="12" :md="4">
            <el-form-item label="生成数量">
              <el-input-number v-model="form.count" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :xs="12" :md="4">
            <el-form-item label="随机种子">
              <el-input-number v-model="form.seed" :min="0" :max="999999" controls-position="right" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="扰动">
          <div style="width: 100%">
            <el-collapse v-model="activeDisturbs" class="disturb-collapse">
              <el-collapse-item v-for="d in disturbanceDefs" :key="d.key" :name="d.key">
                <template #title>
                  <span class="disturb-title">
                    <span @click.stop>
                      <el-switch v-model="form.disturbances[d.key]" />
                    </span>
                    <span class="disturb-name">{{ d.label }}</span>
                    <el-tag v-if="form.disturbances[d.key] === false" size="small" type="info" effect="plain">已关闭</el-tag>
                    <span class="disturb-sum">{{ disturbSummary(d) }}</span>
                  </span>
                </template>
                <el-row :gutter="12">
                  <el-col v-for="pm in d.params" :key="pm.key" :xs="24" :md="12">
                    <div class="param-row">
                      <span class="param-label">{{ pm.label }}</span>
                      <el-input-number v-model="form.params[pm.key][0]" :min="pm.min" :max="pm.max" :step="pm.step" :precision="precisionOf(pm.step)" controls-position="right" class="param-num" />
                      <span class="param-tilde">~</span>
                      <el-input-number v-model="form.params[pm.key][1]" :min="pm.min" :max="pm.max" :step="pm.step" :precision="precisionOf(pm.step)" controls-position="right" class="param-num" />
                    </div>
                  </el-col>
                </el-row>
              </el-collapse-item>
            </el-collapse>
            <div style="margin-top: 6px">
              <el-button size="small" link type="primary" @click="resetParams">恢复默认</el-button>
              <el-button size="small" link @click="toggleAll">{{ activeDisturbs.length ? "收起全部" : "展开全部" }}</el-button>
              <span class="disturb-hint">关闭的扰动不参与生成；参数为随机区间 [下限 ~ 上限]</span>
            </div>
          </div>
        </el-form-item>

        <el-form-item label="输出">
          <el-switch v-model="form.upload" active-text="写入数据集" inactive-text="仅预览" style="margin-right: 20px" />
          <el-switch v-model="form.with_annotation" active-text="写标注" inactive-text="不写标注" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" :icon="MagicStick" @click="onGenerate">
            开始合成
          </el-button>
          <span class="config-tip">
            提示：未选择数据集或关闭「写入数据集」时仅预览；选择数据集并开启写入后，合成图会入库并自动建立检测标注任务。
          </span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="items.length" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>合成结果（{{ items.length }} 张）</span>
          <span class="card-sub">{{ uploaded ? "已写入数据集" : "未写入（仅预览）" }} · 任务 #{{ lastJobId }}</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col v-for="it in items" :key="it.filename" :xs="24" :sm="12" :md="8" :lg="6">
          <div class="result-item">
            <img :src="it.preview_base64" alt="合成车牌" class="result-img" />
            <div class="result-meta">
              <div class="result-text">
                <el-tag size="small" effect="plain">{{ it.text || it.label }}</el-tag>
              </div>
              <div class="result-sub">bbox ({{ fmt(it.bbox.x1) }}, {{ fmt(it.bbox.y1) }}, {{ fmt(it.bbox.x2) }}, {{ fmt(it.bbox.y2) }})</div>
              <div v-if="it.image_id" class="result-sub">已入库 #{{ it.image_id }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="history-card">
      <template #header>
        <div class="card-header">
          <span>合成任务历史</span>
          <el-button size="small" :icon="Refresh" @click="loadJobs">刷新</el-button>
        </div>
      </template>
      <el-table :data="jobs" size="default" empty-text="暂无合成任务">
        <el-table-column prop="id" label="任务ID" width="80" />
        <el-table-column prop="plate_type_label" label="车牌类型" width="150" />
        <el-table-column prop="params" label="参数" min-width="180">
          <template #default="{ row }">
            <span class="dim">{{ paramText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="total" label="数量" width="70" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'completed' ? 'success' : row.status === 'running' ? 'warning' : row.status === 'failed' ? 'danger' : 'info'">
              {{ statusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_time" label="创建时间" width="170" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { MagicStick, Refresh } from "@element-plus/icons-vue";
import { SynthesisAPI, type GeneratedPlateItem, type PlateTypeOption, type SynthesisJob } from "@/api/module_synthesis/synthesis";
import { getDatasetOptions } from "@/api/module_synthesis/dataset";

interface DisturbParam { key: string; label: string; lo: number; hi: number; min: number; max: number; step: number }
interface DisturbDef { key: string; label: string; params: DisturbParam[] }

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
const plateTypes = ref<PlateTypeOption[]>([{ key: "blue", label: "蓝牌(小型汽车)" }]);
const items = ref<GeneratedPlateItem[]>([]);
const jobs = ref<SynthesisJob[]>([]);
const loading = ref(false);
const uploaded = ref(false);
const lastJobId = ref<number | null>(null);

function fmt(v?: number) {
  return v == null ? "-" : v.toFixed(2);
}
function statusText(s: string) {
  return ({ completed: "已完成", running: "进行中", failed: "失败", pending: "待生成" } as Record<string, string>)[s] || s;
}
function plateTypeLabel(key: string) {
  return plateTypes.value.find((t) => t.key === key)?.label || key;
}
function paramText(row: any) {
  const p = row.params || {};
  return `${plateTypeLabel(p.plate_type || "blue")} · 生成${p.count || row.total}张·${p.upload ? "入库" : "预览"}`;
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
    jobs.value = list.map((j) => ({ ...j, plate_type_label: plateTypeLabel(j.params?.plate_type) }));
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
    ElMessage.success(`合成完成，共 ${items.value.length} 张`);
    loadJobs();
  } catch (e: any) {
    ElMessage.error(e?.msg || "合成失败");
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
