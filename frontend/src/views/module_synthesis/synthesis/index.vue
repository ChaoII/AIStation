<template>
  <div class="synthesis-page">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-header">
          <span>车牌数据合成</span>
          <span class="card-sub">生成国内各类车牌（蓝/新能源/黄/双层/黑/教练/警用），带透视、旋转、噪点、污渍、遮挡、模糊等扰动，并产出检测框标注</span>
        </div>
      </template>

      <el-form ref="formRef" :model="form" label-width="100px" size="default">
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

        <el-form-item label="扰动开关">
          <el-checkbox v-for="d in disturbanceDefs" :key="d.key" v-model="form.disturbances[d.key]" :label="d.key">
            {{ d.label }}
          </el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-switch v-model="form.upload" active-text="写入数据集" inactive-text="仅预览" style="margin-right: 16px" />
          <el-switch v-model="form.with_annotation" active-text="写标注" inactive-text="不写标注" />
          <el-button type="primary" :loading="loading" :icon="MagicStick" style="margin-left: 16px" @click="onGenerate">
            开始合成
          </el-button>
        </el-form-item>
        <div class="config-tip">
          提示：未选择数据集或关闭「写入数据集」时仅预览；选择数据集并开启写入后，合成图会入库并自动建立检测标注任务。
        </div>
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

const disturbanceDefs = [
  { key: "perspective", label: "透视" },
  { key: "noise", label: "噪点" },
  { key: "mottle", label: "污渍" },
  { key: "occlusion", label: "遮挡" },
  { key: "blur", label: "模糊" },
  { key: "motion_blur", label: "运动模糊" },
  { key: "photon", label: "光照" },
  { key: "shadow", label: "投影" },
];

const form = reactive({
  plate_type: "blue",
  dataset_id: undefined as number | undefined,
  count: 8,
  seed: undefined as number | undefined,
  upload: true,
  with_annotation: true,
  disturbances: Object.fromEntries(disturbanceDefs.map((d) => [d.key, true])) as Record<string, boolean>,
});

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
      disturbances: form.disturbances,
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
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 100px;
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
