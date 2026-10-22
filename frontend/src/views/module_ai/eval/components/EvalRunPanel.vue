<template>
  <div class="ev-run">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>运行评测</span>
          <div class="ev-head__ops">
            <el-button size="small" @click="loadRuns">刷新历史</el-button>
            <el-button
              size="small"
              type="primary"
              :loading="starting"
              :disabled="running"
              @click="start"
            >
              开始评测
            </el-button>
          </div>
        </div>
      </template>

      <el-form :model="form" inline>
        <el-form-item label="数据源">
          <el-select
            v-model="form.datasource"
            size="small"
            clearable
            placeholder="全部"
            style="width: 170px"
          >
            <el-option label="系统库（本体支撑表）" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select
            v-model="form.difficulty"
            size="small"
            clearable
            placeholder="全部"
            style="width: 110px"
          >
            <el-option v-for="d in DIFFICULTIES" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="形式">
          <el-select
            v-model="form.form"
            size="small"
            clearable
            placeholder="全部"
            style="width: 140px"
          >
            <el-option v-for="f in FORMS" :key="f" :label="f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量上限">
          <el-input-number v-model="form.limit" size="small" :min="1" :max="200" />
        </el-form-item>
        <el-form-item label="强制慢路径">
          <el-switch v-model="form.force_slow" size="small" />
        </el-form-item>
      </el-form>

      <el-alert
        v-if="progress"
        :type="progress.status === 'error' ? 'error' : 'info'"
        :closable="false"
        show-icon
        :title="statusTitle"
        class="ev-alert"
      />
      <el-progress
        v-if="progress"
        :percentage="percentage"
        :status="progress.status === 'error' ? 'exception' : undefined"
        :stroke-width="14"
      />
      <el-descriptions v-if="progress" :column="3" size="small" border class="ev-desc">
        <el-descriptions-item label="状态">{{ progress.status }}</el-descriptions-item>
        <el-descriptions-item label="已完成">
          {{ progress.done }} / {{ progress.total }}
        </el-descriptions-item>
        <el-descriptions-item label="当前题">{{ progress.current || "-" }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="progress?.error"
        type="error"
        :closable="false"
        show-icon
        :title="progress.error"
        class="ev-alert"
      />

      <el-divider />

      <div class="ev-sub">历史运行</div>
      <el-table
        v-loading="loadingRuns"
        :data="runs"
        size="small"
        border
        highlight-current-row
        stripe
        @row-click="onRowClick"
      >
        <el-table-column prop="run_id" label="run_id" width="180" show-overflow-tooltip />
        <el-table-column prop="mode" label="模式" width="90" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="
                row.status === 'done' ? 'success' : row.status === 'error' ? 'danger' : 'warning'
              "
            >
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="110">
          <template #default="{ row }">{{ row.done }} / {{ row.total }}</template>
        </el-table-column>
        <el-table-column label="数据准确率" width="120">
          <template #default="{ row }">{{ pct(row.summary?.data_accuracy) }}</template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button
              icon="DataAnalysis"
              link
              type="primary"
              size="small"
              @click.stop="emit('select', row.run_id)"
            >
              查看报表
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  getEvalRuns,
  getEvalStatus,
  getQueryDatasources,
  startEvalRun,
} from "@/api/module_ai/query";
import { DIFFICULTIES, FORMS, pct, type EvalRunItem, type EvalRunProgress } from "../types";

defineOptions({ name: "AiEvalRunPanel" });

const emit = defineEmits<{
  (e: "started", id: string): void;
  (e: "finished", id: string): void;
  (e: "select", id: string): void;
}>();

const datasources = ref<any[]>([]);
const form = ref<any>({ datasource: "", difficulty: "", form: "", limit: 40, force_slow: false });

const starting = ref(false);
const progress = ref<EvalRunProgress | null>(null);
const runs = ref<EvalRunItem[]>([]);
const loadingRuns = ref(false);

/** 轮询句柄（**只在终止时清理**，组件卸载也必须清理）。 */
let timer: ReturnType<typeof setInterval> | null = null;

const running = computed(() => progress.value?.status === "running");
const percentage = computed(() => {
  const p = progress.value;
  if (!p || !p.total) return 0;
  return Math.min(100, Math.round((p.done / p.total) * 100));
});
const statusTitle = computed(() => {
  const p = progress.value;
  if (!p) return "";
  if (p.status === "done") return `评测完成：共 ${p.total} 题`;
  if (p.status === "error") return "评测失败";
  return `评测进行中：${p.done}/${p.total}`;
});

function stopPolling() {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
}

async function poll(runId: string) {
  try {
    const r = await getEvalStatus(runId);
    const d: EvalRunProgress | null = r.data?.data || null;
    progress.value = d;
    if (!d || d.status !== "running") {
      stopPolling();
      await loadRuns();
      if (d && d.status === "done") {
        ElMessage.success("评测完成");
        emit("finished", runId);
      } else if (d && d.status === "error") {
        ElMessage.error(d.error || "评测失败");
      }
    }
  } catch {
    // 单次轮询失败不终止（可能是瞬时网络问题）
  }
}

async function start() {
  starting.value = true;
  try {
    const filter: any = { limit: form.value.limit };
    if (form.value.datasource) filter.datasource = form.value.datasource;
    if (form.value.difficulty) filter.difficulty = form.value.difficulty;
    if (form.value.form) filter.form = form.value.form;
    if (form.value.force_slow) filter.force_slow = true;
    const r = await startEvalRun({ filter, mode: "full" });
    const runId: string = r.data?.data?.run_id;
    if (!runId) {
      ElMessage.error("启动失败：未返回 run_id");
      return;
    }
    progress.value = { run_id: runId, status: "running", total: 0, done: 0, current: "" };
    emit("started", runId);
    stopPolling();
    timer = setInterval(() => poll(runId), 1500);
    await poll(runId);
  } catch (e: any) {
    ElMessage.error(e?.msg || "启动失败");
  } finally {
    starting.value = false;
  }
}

function onRowClick(row: EvalRunItem) {
  emit("select", row.run_id);
}

async function loadRuns() {
  loadingRuns.value = true;
  try {
    const r = await getEvalRuns(30);
    runs.value = r.data?.data || [];
  } catch {
    runs.value = [];
  } finally {
    loadingRuns.value = false;
  }
}

onMounted(async () => {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
  await loadRuns();
});

onUnmounted(stopPolling);
</script>

<style scoped>
.ev-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.ev-head__ops {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ev-desc {
  margin-top: 12px;
}
.ev-alert {
  margin-bottom: 12px;
}
.ev-sub {
  margin-bottom: 8px;
  font-weight: 600;
}
</style>
