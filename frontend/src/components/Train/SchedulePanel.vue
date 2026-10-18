<template>
  <div class="schedule-panel">
    <div class="toolbar">
      <el-button type="primary" @click="openCreate">新建定时计划</el-button>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border>
      <el-table-column label="名称" prop="name" min-width="140" show-overflow-tooltip />
      <el-table-column label="框架" prop="framework" width="120" />
      <el-table-column label="触发方式" min-width="240">
        <template #default="{ row }">
          <div class="trigger-cell">
            <el-tag size="small">{{ triggerLabel(row.trigger) }}</el-tag>
            <span class="trigger-cell__desc">{{ triggerDesc(row) }}</span>
            <!-- 迁移被跳过（无表达式）或表达式按新校验不通过：不静默停摆，显式提示人工改写 -->
            <el-tag v-if="row.needs_review" size="small" type="warning">需人工确认</el-tag>
          </div>
          <div class="trigger-cell__next">下次运行：{{ row.next_run_time || "—" }}</div>
        </template>
      </el-table-column>
      <el-table-column label="启用" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? "启用" : "停用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上次运行" prop="last_run_at" min-width="170" />
      <el-table-column label="操作" width="140" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <EnhancedDialog
      v-model="dialogVisible"
      :title="form.id ? '编辑定时计划' : '新建定时计划'"
      append-to-body
      width="680px"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="计划名称" required>
          <el-input v-model="form.name" placeholder="如：每晚 2 点训练" />
        </el-form-item>
        <el-form-item label="框架">
          <!-- Ultralytics / PaddleX 已退场，定时训练只支持自研平台。 -->
          <el-radio-group v-model="form.framework">
            <el-radio value="torchkiln">TorchKiln（自研）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="数据集" required>
          <el-select
            v-model="form.dataset_id"
            filterable
            style="width: 100%"
            placeholder="选择数据集"
            @visible-change="(v: boolean) => v && loadDatasets()"
          >
            <el-option v-for="d in datasets" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <!-- 统一触发配置组件：定时/间隔/单次/立即四种类型 + 后端统一层产出的描述与下次运行时间 -->
        <el-form-item label="触发方式" required>
          <TriggerEditor
            v-model:trigger="form.trigger"
            v-model:trigger-args="form.trigger_args"
            @error="form.triggerError = $event"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import TriggerEditor from "@/components/TriggerEditor/index.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";
import { cachedOptions } from "@/composables/useOptions";

/** 触发类型 → 中文标签（与后端 TriggerUtil.TRIGGERS 一一对应） */
const TRIGGER_LABELS: Record<string, string> = {
  cron: "定时",
  interval: "间隔",
  date: "单次",
  now: "立即",
};

const rows = ref<any[]>([]);
const datasets = ref<any[]>([]);
const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);

/**
 * 触发方式展示：`trigger` 为 NULL 的历史行由后端按 `cron` 兜底，这里保持一致口径。
 */
function triggerLabel(trigger?: string | null) {
  const key = String(trigger || "cron");
  return TRIGGER_LABELS[key] || key;
}

/**
 * 触发方式的「人话描述」：优先用后端下发的描述字段（统一层唯一口径）；
 * 列表接口暂未提供描述时，按控制者裁决回退为 `trigger_args` 原样展示（不做前端自算）。
 */
function triggerDesc(row: any) {
  const text = row?.trigger_describe ?? row?.describe;
  if (text) return String(text);
  const args = row?.trigger_args ?? (row?.trigger === "cron" ? row?.cron_expr : "");
  if (args === null || args === undefined || args === "") return "—";
  return typeof args === "string" ? args : JSON.stringify(args);
}

/**
 * 表单模型：`trigger`/`trigger_args` 是统一契约的新字段，`triggerError` 承载 TriggerEditor
 * 上抛的校验原因（非空即拦截保存，不在前端另做一套校验）。
 */
const emptyForm = () => ({
  id: 0,
  name: "",
  framework: "torchkiln",
  dataset_id: null as number | null,
  trigger: "cron",
  // 空值交给 TriggerEditor 规范化为默认表达式，避免前后端两套默认值
  trigger_args: "" as unknown,
  triggerError: "",
  enabled: true,
});
const form = reactive<any>(emptyForm());

async function load() {
  loading.value = true;
  try {
    const res = await TrainAPI.getTrainScheduleList();
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

let datasetsLoaded = false;
async function loadDatasets() {
  if (datasetsLoaded) return;
  datasetsLoaded = true;
  try {
    datasets.value = await cachedOptions(
      "annotation:datasets",
      async () =>
        (await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 })).data?.data?.items || []
    );
  } catch {
    datasetsLoaded = false;
  }
}

function openCreate() {
  Object.assign(form, emptyForm());
  loadDatasets();
  dialogVisible.value = true;
}

function openEdit(row: any) {
  const trigger = row.trigger || "cron";
  Object.assign(form, {
    id: row.id,
    name: row.name,
    framework: row.framework || "torchkiln",
    dataset_id: row.dataset_id,
    trigger,
    // 兼容旧字段：历史行的 trigger_args 可能为空，cron 回退用 cron_expr；非 cron 无参数（null）
    trigger_args: row.trigger_args ?? (trigger === "cron" ? (row.cron_expr ?? "") : null),
    triggerError: "",
    enabled: row.enabled !== false,
  });
  loadDatasets();
  dialogVisible.value = true;
}

async function submit() {
  if (!form.name) {
    ElMessage.warning("请填写计划名称");
    return;
  }
  if (!form.dataset_id) {
    ElMessage.warning("请选择数据集");
    return;
  }
  // TriggerEditor 已按后端统一层校验：原因非空即拦截，保存时后端仍会再校验一次
  if (form.triggerError) {
    ElMessage.warning(form.triggerError);
    return;
  }
  saving.value = true;
  try {
    // 触发契约：cron = 5 段表达式、interval = JSON、date = 时间串、now = 无参数（null）
    const args = form.trigger === "now" ? null : form.trigger_args;
    const payload = {
      name: form.name,
      framework: form.framework,
      dataset_id: form.dataset_id,
      // 新契约字段（优先）：后端按 trigger + trigger_args 落库与注册作业
      trigger: form.trigger,
      trigger_args: args,
      // 兼容字段：非 cron 触发无 cron 表达式，置空（旧前端/旧接口读它）
      cron_expr: form.trigger === "cron" ? String(args ?? "") : "",
      enabled: form.enabled,
    };
    if (form.id) await TrainAPI.updateTrainSchedule(form.id, payload);
    else await TrainAPI.createTrainSchedule(payload);
    dialogVisible.value = false;
    await load();
  } finally {
    saving.value = false;
  }
}

async function remove(row: any) {
  try {
    await ElMessageBox.confirm(
      `将删除定时计划「${row.name}」并移除其调度作业，删除后不可恢复。`,
      "删除定时计划",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return; // 用户取消
  }
  await TrainAPI.deleteTrainSchedule([row.id]);
  ElMessage.success("已删除");
  await load();
}

onMounted(async () => {
  await load();
});

defineExpose({ load });
</script>

<style scoped>
.schedule-panel {
  padding: 8px 0;
}

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.trigger-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.trigger-cell__desc {
  color: var(--el-text-color-regular);
  word-break: break-all;
}

.trigger-cell__next {
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-secondary);
}
</style>
