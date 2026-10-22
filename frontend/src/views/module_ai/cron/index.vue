<!-- AI 定时任务：独立模块，卡片网格（信息模板统一：触发/下次/上次/目标 + 描述区固定两行）。
     数据全部复用 /ai/workspace/cron/*（含 needs_review 与人话描述，口径来自后端统一层）。 -->
<template>
  <div class="app-container ai-cron-page">
    <el-card shadow="never" class="cron-main">
      <div class="cron-toolbar">
        <div class="cron-toolbar-left">
          <el-select
            v-model="triggerFilter"
            clearable
            placeholder="触发方式"
            style="width: 130px"
            @change="page = 1"
          >
            <el-option
              v-for="t in triggerOptions"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
          <el-select
            v-model="targetFilter"
            clearable
            placeholder="执行目标"
            style="width: 130px"
            @change="page = 1"
          >
            <el-option
              v-for="t in targetOptions"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </div>
        <div class="cron-toolbar-right">
          <el-input
            v-model="keyword"
            placeholder="搜索任务"
            clearable
            :prefix-icon="Search"
            style="width: 220px"
            @clear="page = 1"
          />
          <el-button
            v-hasPerm="'module_ai:cron:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            新建
          </el-button>
        </div>
      </div>

      <div v-loading="loading" class="cron-grid-wrap">
        <el-row :gutter="16" class="cron-card-grid">
          <el-col v-for="row in pagedRows" :key="row.id" :xs="24" :sm="12" :md="12" :lg="8" :xl="6">
            <div class="cron-card">
              <div class="cron-card__head">
                <div class="cron-card__icon">
                  <el-icon><Timer /></el-icon>
                </div>
                <div class="cron-card__title">
                  <div class="cron-card__name">{{ row.name }}</div>
                </div>
                <el-switch
                  :model-value="row.enabled"
                  size="small"
                  @change="(v: any) => onToggleEnabled(row, v)"
                />
              </div>

              <!-- 固定子行：触发方式 tag + 需人工确认（占位固定，保证各卡等高） -->
              <div class="cron-card__sub">
                <el-tag size="small" effect="plain" :type="triggerMeta(row.trigger).type">
                  {{ triggerMeta(row.trigger).text }}
                </el-tag>
                <el-tag v-if="row.needs_review" size="small" type="warning">需人工确认</el-tag>
              </div>

              <!-- 描述：固定两行高度（无描述显示占位符），保证卡片大小统一 -->
              <div class="cron-card__desc" :class="{ 'is-empty': !row.description }">
                {{ row.description || "—" }}
              </div>

              <!-- 统一信息行：触发描述 / 下次运行 / 上次运行 -->
              <div class="cron-card__info">
                <div class="cron-card__info-row">
                  <span class="cron-card__label">触发：</span>
                  <span class="cron-card__value">
                    {{ row.trigger_describe || argsFallback(row) }}
                  </span>
                </div>
                <div class="cron-card__info-row">
                  <span class="cron-card__label">下次：</span>
                  <span class="cron-card__value" :class="{ 'is-empty': !row.next_run_time }">
                    {{ row.next_run_time || "—" }}
                  </span>
                </div>
                <div class="cron-card__info-row">
                  <span class="cron-card__label">上次：</span>
                  <span class="cron-card__value" :class="{ 'is-empty': !row.last_run_time }">
                    {{ row.last_run_time || "—" }}
                  </span>
                </div>
              </div>

              <div class="cron-card__foot">
                <span class="cron-card__target">
                  <span class="cron-card__label">目标：</span>
                  <el-tag size="small" effect="plain" :type="targetMeta(row.target_type).type">
                    {{ targetMeta(row.target_type).text }}
                  </el-tag>
                  <span class="cron-card__target-id">#{{ row.target_id }}</span>
                </span>
                <div class="cron-card__actions">
                  <el-button
                    v-hasPerm="'module_ai:cron:query'"
                    type="primary"
                    size="small"
                    link
                    :icon="Clock"
                    @click="openHistory(row)"
                  >
                    历史
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:cron:run'"
                    type="warning"
                    size="small"
                    link
                    :icon="VideoPlay"
                    :loading="runLoadingId === row.id"
                    @click="handleRun(row)"
                  >
                    立即执行
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:cron:update'"
                    type="primary"
                    size="small"
                    link
                    :icon="Edit"
                    @click="openEdit(row)"
                  >
                    编辑
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:cron:delete'"
                    type="danger"
                    size="small"
                    link
                    :icon="Delete"
                    @click="handleDelete(row)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </div>
          </el-col>
          <el-col v-if="!loading && !pagedRows.length" :span="24">
            <el-empty description="暂无定时任务" />
          </el-col>
        </el-row>
      </div>

      <div v-if="filteredRows.length > pageSize" class="cron-pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="filteredRows.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </el-card>

    <!-- 新建/编辑（触发方式统一走 TriggerEditor，描述与下次运行来自后端统一层） -->
    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="600px"
      @close="handleCloseDialog"
    >
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-suffix=":"
        label-width="90px"
        label-position="right"
      >
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入任务名称" :maxlength="64" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="formData.description"
            :rows="3"
            :maxlength="255"
            type="textarea"
            placeholder="请输入任务描述"
          />
        </el-form-item>
        <el-form-item label="触发方式">
          <TriggerEditor
            v-model:trigger="formData.trigger"
            v-model:trigger-args="formData.trigger_args"
            preview-url="/ai/workspace/trigger/preview"
            @error="cronError = $event"
          />
        </el-form-item>
        <el-form-item label="执行目标">
          <el-select v-model="formData.target_type" style="width: 100%">
            <el-option label="智能体" value="agent" />
            <el-option label="工作流" value="workflow" />
            <el-option label="应用" value="app" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标ID">
          <el-input-number v-model="formData.target_id" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">取消</el-button>
          <el-button
            v-hasPerm="[
              dialogVisible.type === 'create' ? 'module_ai:cron:create' : 'module_ai:cron:update',
            ]"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            保存
          </el-button>
        </div>
      </template>
    </EnhancedDialog>

    <!-- 执行历史：每次调度/立即执行的成败、耗时、错误与输出摘要（此前只有「上次运行时间」） -->
    <EnhancedDialog v-model="historyVisible" :title="historyTitle" width="720px">
      <el-table
        v-loading="historyLoading"
        :data="historyRows"
        border
        stripe
        max-height="420"
        size="small"
      >
        <el-table-column prop="created_time" label="执行时间" width="160" />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="light"
              :type="row.result === 'success' ? 'success' : 'danger'"
            >
              {{ row.result === "success" ? "成功" : "失败" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="90">
          <template #default="{ row }">{{ (Number(row.latency_ms || 0) / 1000).toFixed(1) }}s</template>
        </el-table-column>
        <el-table-column label="错误 / 输出摘要" min-width="320">
          <template #default="{ row }">
            <span v-if="row.error" class="cron-history__error">{{ row.error }}</span>
            <span v-else-if="row.reply_preview" class="cron-history__reply">
              {{ row.reply_preview }}
            </span>
            <span v-else class="cron-history__empty">（无输出）</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :image-size="60" description="暂无执行记录（点「立即执行」或等待调度触发）" />
        </template>
      </el-table>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { Clock, Delete, Edit, Plus, Search, Timer, VideoPlay } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import {
  createWorkspaceCron,
  deleteWorkspaceCron,
  getCronRuns,
  getWorkspaceCronList,
  runWorkspaceCron,
  updateWorkspaceCron,
  type WorkspaceCronRow,
} from "@/api/module_ai/workspace";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import TriggerEditor from "@/components/TriggerEditor/index.vue";

defineOptions({ name: "AiCron" });

const loading = ref(false);
const submitLoading = ref(false);
const runLoadingId = ref<number | null>(null);
const dataFormRef = ref();

const rows = ref<WorkspaceCronRow[]>([]);
const keyword = ref("");
const triggerFilter = ref("");
const targetFilter = ref("");
const page = ref(1);
const pageSize = 12;

/** 触发类型 → 中文名 + 标签色（与 TriggerEditor 的四种类型一一对应） */
type TagType = "primary" | "success" | "warning" | "info" | "danger";
const triggerOptions = [
  { label: "定时", value: "cron" },
  { label: "间隔", value: "interval" },
  { label: "单次", value: "date" },
  { label: "立即", value: "now" },
];
const targetOptions = [
  { label: "智能体", value: "agent" },
  { label: "工作流", value: "workflow" },
  { label: "应用", value: "app" },
];
const TRIGGER_LABELS: Record<string, { text: string; type: TagType }> = {
  cron: { text: "定时", type: "primary" },
  interval: { text: "间隔", type: "success" },
  date: { text: "单次", type: "warning" },
  now: { text: "立即", type: "info" },
};
function triggerMeta(trigger: string): { text: string; type: TagType } {
  return TRIGGER_LABELS[trigger] || { text: trigger || "未配置", type: "info" };
}

const TARGET_LABELS: Record<string, { text: string; type: TagType }> = {
  agent: { text: "智能体", type: "primary" },
  workflow: { text: "工作流", type: "success" },
  app: { text: "应用", type: "info" },
};
function targetMeta(t: string): { text: string; type: TagType } {
  return TARGET_LABELS[t] || { text: t || "—", type: "info" };
}

/** 人话描述缺失（脏数据）时的兜底：原样展示契约值，不自算 */
function argsFallback(row: WorkspaceCronRow): string {
  const args = row.trigger_args;
  if (args === null || args === undefined || args === "") {
    return row.trigger === "now" ? "—" : "未配置";
  }
  return typeof args === "string" ? args : JSON.stringify(args);
}

const filteredRows = computed(() => {
  let list = rows.value;
  if (triggerFilter.value) list = list.filter((r) => r.trigger === triggerFilter.value);
  if (targetFilter.value) list = list.filter((r) => r.target_type === targetFilter.value);
  if (keyword.value) list = list.filter((r) => (r.name || "").includes(keyword.value));
  return list;
});
const pagedRows = computed(() =>
  filteredRows.value.slice((page.value - 1) * pageSize, page.value * pageSize)
);

async function loadRows() {
  loading.value = true;
  try {
    const res: any = await getWorkspaceCronList();
    rows.value = res.data?.data?.items || [];
  } finally {
    loading.value = false;
  }
}

onMounted(loadRows);

// ---- 启停 / 立即执行 / 删除 ----

/** 启停：行数据本地更新（不整表刷新），失败回滚原值 */
async function onToggleEnabled(row: WorkspaceCronRow, val: boolean) {
  const prev = row.enabled;
  row.enabled = val;
  try {
    await updateWorkspaceCron(row.id, { enabled: val });
    ElMessage.success(val ? "已启用" : "已停用");
  } catch {
    row.enabled = prev;
  }
}

/** 立即执行：二次确认后入队（接口只入队，执行走后台，与调度器同一路径） */
async function handleRun(row: WorkspaceCronRow) {
  await ElMessageBox.confirm(
    `将立即执行一次「${row.name}」，绑定目标会真实运行一次，是否继续？`,
    "立即执行",
    { confirmButtonText: "执行", cancelButtonText: "取消", type: "warning" }
  );
  runLoadingId.value = row.id;
  try {
    await runWorkspaceCron(row.id);
    ElMessage.success("已触发执行");
    // 状态跃迁后刷新一次（上次运行时间由执行回写，不周期轮询）
    await loadRows();
  } finally {
    runLoadingId.value = null;
  }
}

// ---- 执行历史 ----
const historyVisible = ref(false);
const historyLoading = ref(false);
const historyTitle = ref("执行历史");
const historyRows = ref<Array<Record<string, unknown>>>([]);

/** 打开执行历史：列出该定时任务每次调度/立即执行的结果。 */
async function openHistory(row: WorkspaceCronRow) {
  historyTitle.value = `执行历史 · ${row.name}`;
  historyRows.value = [];
  historyVisible.value = true;
  historyLoading.value = true;
  try {
    const res: any = await getCronRuns(row.id);
    // 拦截器返回 AxiosResponse（res.data = 后端 body）；items 在后端 data 层，
    // 这里对两种形态都做兼容，避免把对象传给 el-table（会 render 崩溃、空态不显示）。
    const body = res?.data ?? res;
    const payload = body?.data ?? body;
    const items = Array.isArray(payload) ? payload : payload?.items;
    historyRows.value = Array.isArray(items) ? items : [];
  } catch {
    ElMessage.error("执行历史加载失败");
  } finally {
    historyLoading.value = false;
  }
}

async function handleDelete(row: WorkspaceCronRow) {
  await ElMessageBox.confirm(
    `将删除定时任务「${row.name}」，其调度将同步停止且不可恢复，是否继续？`,
    "删除确认",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  );
  await deleteWorkspaceCron(row.id);
  ElMessage.success("已删除");
  await loadRows();
}

// ---- 新建/编辑弹窗 ----

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: "",
  description: "",
  /** 触发类型：cron / interval / date / now（TriggerEditor 的四种类型） */
  trigger: "cron",
  /** 触发参数：cron 为 5 段表达式，interval 为对象，date 为时间字符串，now 为 null */
  trigger_args: "" as unknown,
  target_type: "agent",
  target_id: 1,
  enabled: true,
});

const rules = reactive({
  name: [{ required: true, message: "请输入任务名称", trigger: "blur" }],
});

/** TriggerEditor 上抛的非法原因（非空即拦截保存）；空串表示配置合法 */
const cronError = ref("");

function openCreate() {
  dialogVisible.type = "create";
  dialogVisible.title = "新建定时任务";
  cronError.value = "";
  formData.id = undefined;
  formData.name = "";
  formData.description = "";
  // 参数留空：TriggerEditor 会按类型回落到规范默认值（定时 → 每天 09:00）
  formData.trigger = "cron";
  formData.trigger_args = "";
  formData.target_type = "agent";
  formData.target_id = 1;
  formData.enabled = true;
  dialogVisible.visible = true;
}

function openEdit(row: WorkspaceCronRow) {
  dialogVisible.type = "update";
  dialogVisible.title = "编辑定时任务";
  cronError.value = "";
  formData.id = row.id;
  formData.name = row.name || "";
  formData.description = row.description || "";
  formData.trigger = row.trigger || "cron";
  // 列表接口已把 interval 的 JSON 串还原为对象（TriggerEditor 直接可用）
  formData.trigger_args = row.trigger_args ?? "";
  formData.target_type = row.target_type || "agent";
  formData.target_id = row.target_id ?? 1;
  formData.enabled = Boolean(row.enabled);
  dialogVisible.visible = true;
}

function handleCloseDialog() {
  dialogVisible.visible = false;
}

/**
 * 保存用的 `trigger_args`：与后端存储契约一致——
 * interval 落 JSON 字符串（后端 `TriggerUtil` 两种形态都认），date 落时间字符串，now 无参数。
 */
function serializeTriggerArgs(trigger: string, args: unknown): string | null {
  if (trigger === "now") return null;
  if (trigger === "interval") return JSON.stringify(args ?? {});
  return typeof args === "string" ? args : String(args ?? "");
}

async function handleSubmit() {
  const valid: any = await dataFormRef.value?.validate().catch(() => false);
  if (!valid) return;
  if (cronError.value) {
    ElMessage.error(cronError.value);
    return;
  }
  submitLoading.value = true;
  try {
    const trigger = formData.trigger;
    const triggerArgs = serializeTriggerArgs(trigger, formData.trigger_args);
    // 先落到变量再传参：与 api 模块类型声明解耦（新字段尚未全部进类型）
    const payload = {
      name: formData.name,
      description: formData.description,
      trigger,
      trigger_args: triggerArgs,
      // 兼容字段：仅「定时」时带表达式，其余类型留空（避免被当成另一套调度语义）
      cron: trigger === "cron" ? String(triggerArgs ?? "") : "",
      target_type: formData.target_type,
      target_id: formData.target_id,
      enabled: formData.enabled,
    };
    const isEdit = Boolean(formData.id);
    if (isEdit) await updateWorkspaceCron(formData.id!, payload);
    else await createWorkspaceCron(payload);
    dialogVisible.visible = false;
    ElMessage.success(isEdit ? "已保存" : "定时任务已创建");
    await loadRows();
  } finally {
    submitLoading.value = false;
  }
}
</script>

<style lang="scss">
/* 单卡片容器（本页无分类树，工具栏与卡片网格同处一个内容面板，边界清晰） */
.app-container.ai-cron-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  overflow: hidden;
}

.ai-cron-page .cron-main {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-cron-page .cron-main > .el-card__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-cron-page .cron-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.ai-cron-page .cron-toolbar-left,
.ai-cron-page .cron-toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.ai-cron-page .cron-grid-wrap {
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 16px;
  overflow-x: hidden;
  overflow-y: auto;
}

.ai-cron-page .cron-card-grid {
  row-gap: 16px;
}

/* 卡片：统一信息模板（描述固定两行、触发/下次/上次/目标各一行）→ 各卡等高 */
.ai-cron-page .cron-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 14px 16px;
  background: var(--el-color-white);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
}

.ai-cron-page .cron-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 6px 16px rgb(0 0 0 / 6%);
}

.ai-cron-page .cron-card__head {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.ai-cron-page .cron-card__icon {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-size: 16px;
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-7);
  border-radius: var(--el-border-radius-base);
}

.ai-cron-page .cron-card__title {
  flex: 1 1 auto;
  min-width: 0;
}

.ai-cron-page .cron-card__name {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 1;
  font-weight: 600;
  line-height: 1.5;
  -webkit-box-orient: vertical;
}

/* 触发 tag + 需人工确认：固定子行，保证头部高度一致 */
.ai-cron-page .cron-card__sub {
  display: flex;
  gap: 6px;
  align-items: center;
  height: 22px;
  margin-top: 8px;
}

/* 描述：固定两行高度（无描述显示占位符），各卡大小统一 */
.ai-cron-page .cron-card__desc {
  display: -webkit-box;
  height: 40px;
  margin-top: 8px;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font-size: 12px;
  line-height: 20px;
  color: var(--el-text-color-regular);
  -webkit-box-orient: vertical;
}

.ai-cron-page .cron-card__desc.is-empty {
  color: var(--el-text-color-placeholder);
}

/* 统一信息行：触发 / 下次 / 上次 */
.ai-cron-page .cron-card__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 8px;
  margin-top: 8px;
  font-size: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ai-cron-page .cron-card__info-row {
  display: flex;
  gap: 4px;
  align-items: center;
  min-width: 0;
  line-height: 18px;
}

.ai-cron-page .cron-card__label {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
}

.ai-cron-page .cron-card__value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.ai-cron-page .cron-card__value.is-empty {
  color: var(--el-text-color-placeholder);
}

.ai-cron-page .cron-card__foot {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  margin-top: auto;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ai-cron-page .cron-card__target {
  display: flex;
  gap: 4px;
  align-items: center;
  min-width: 0;
  font-size: 12px;
}

.ai-cron-page .cron-card__target-id {
  color: var(--el-text-color-secondary);
}

.ai-cron-page .cron-card__actions {
  display: flex;
  flex: 0 0 auto;
  gap: 8px;
  align-items: center;
}

.ai-cron-page .cron-pagination {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  padding-top: 8px;
}

/* 执行历史弹窗内容样式（唯一类名，避免与页面其它 block 冲突） */
.cron-history__error {
  color: var(--el-color-danger);
  word-break: break-all;
}
.cron-history__reply {
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}
.cron-history__empty {
  color: var(--el-text-color-placeholder);
}
</style>
