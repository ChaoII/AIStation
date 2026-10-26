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
            :placeholder="t('ai_workflow.cron_triggerPlaceholder')"
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
            :placeholder="t('ai_workflow.cron_targetPlaceholder')"
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
            :placeholder="t('ai_workflow.cron_searchPlaceholder')"
            clearable
            :prefix-icon="Search"
            style="width: 220px"
            @input="page = 1"
            @clear="page = 1"
          />
          <el-button
            v-hasPerm="'module_ai:cron:create'"
            type="primary"
            :icon="Plus"
            @click="openCreate"
          >
            {{ t("ai_workflow.cron_new") }}
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
                <el-tag v-if="row.needs_review" size="small" type="warning">
                  {{ t("ai_workflow.cron_needsReview") }}
                </el-tag>
                <el-tag
                  v-if="row.auto_disabled"
                  size="small"
                  type="danger"
                  :title="`连续失败 ${row.fail_limit || 3} 次已自动停用；修好后打开开关会重新计数`"
                >
                  已自动停用
                </el-tag>
                <el-tag v-else-if="row.fail_streak" size="small" type="warning">
                  连续失败 {{ row.fail_streak }} 次
                </el-tag>
              </div>

              <!-- 描述：固定两行高度（无描述显示占位符），保证卡片大小统一 -->
              <div class="cron-card__desc" :class="{ 'is-empty': !row.description }">
                {{ row.description || "—" }}
              </div>

              <!-- 统一信息行：触发描述 / 下次运行 / 上次运行 -->
              <div class="cron-card__info">
                <div class="cron-card__info-row">
                  <span class="cron-card__label">{{ t("ai_workflow.cron_triggerLabel") }}</span>
                  <span class="cron-card__value">
                    {{ row.trigger_describe || argsFallback(row) }}
                  </span>
                </div>
                <div class="cron-card__info-row">
                  <span class="cron-card__label">{{ t("ai_workflow.cron_nextLabel") }}</span>
                  <span class="cron-card__value" :class="{ 'is-empty': !row.next_run_time }">
                    {{ row.next_run_time || "—" }}
                  </span>
                </div>
                <div class="cron-card__info-row">
                  <span class="cron-card__label">{{ t("ai_workflow.cron_lastLabel") }}</span>
                  <span class="cron-card__value" :class="{ 'is-empty': !row.last_run_time }">
                    <span>{{ row.last_run_time || "—" }}</span>
                    <el-tag v-if="isRunning(row.id)" size="small" type="warning" effect="plain">
                      执行中…
                    </el-tag>
                    <el-tag
                      v-else-if="row.last_status"
                      size="small"
                      effect="plain"
                      :type="row.last_status === 'success' ? 'success' : 'danger'"
                    >
                      {{ row.last_status === "success" ? "成功" : "失败" }}
                    </el-tag>
                    <span v-if="row.last_duration_ms && !isRunning(row.id)" class="cron-card__cost">
                      {{ fmtSecs(row.last_duration_ms) }}
                    </span>
                    <el-button
                      v-if="row.last_run_id"
                      link
                      type="primary"
                      size="small"
                      @click="openTrace(row)"
                    >
                      过程
                    </el-button>
                  </span>
                </div>
                <!-- 上次执行结果：成功是正文摘要，失败是错误信息（单行，保持各卡等高） -->
                <div class="cron-card__info-row cron-card__result">
                  <span class="cron-card__label">结果：</span>
                  <span
                    class="cron-card__value"
                    :class="{ 'is-empty': !row.last_message }"
                    :title="row.last_message || ''"
                  >
                    {{ row.last_message || "—" }}
                  </span>
                </div>
              </div>

              <div class="cron-card__foot">
                <span class="cron-card__target">
                  <span class="cron-card__label">{{ t("ai_workflow.cron_targetLabel") }}</span>
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
                    {{ t("ai_workflow.cron_history") }}
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:cron:run'"
                    type="warning"
                    size="small"
                    link
                    :icon="VideoPlay"
                    :loading="runLoadingId === row.id || isRunning(row.id)"
                    @click="handleRun(row)"
                  >
                    {{ t("ai_workflow.cron_runNow") }}
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:cron:update'"
                    type="primary"
                    size="small"
                    link
                    :icon="Edit"
                    @click="openEdit(row)"
                  >
                    {{ t("ai_workflow.cron_edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:cron:delete'"
                    type="danger"
                    size="small"
                    link
                    :icon="Delete"
                    @click="handleDelete(row)"
                  >
                    {{ t("ai_workflow.cron_delete") }}
                  </el-button>
                </div>
              </div>
            </div>
          </el-col>
          <el-col v-if="!loading && !pagedRows.length" :span="24">
            <el-empty :description="t('ai_workflow.cron_noData')" />
          </el-col>
        </el-row>
      </div>

      <div v-if="filteredRows.length > pageSize" class="cron-pagination">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="filteredRows.length"
          layout="total, sizes, prev, pager, next"
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
        <el-form-item :label="t('ai_workflow.cron_taskName')" prop="name">
          <el-input
            v-model="formData.name"
            :placeholder="t('ai_workflow.cron_taskNamePlaceholder')"
            :maxlength="64"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.cron_description')">
          <el-input
            v-model="formData.description"
            :rows="3"
            :maxlength="255"
            type="textarea"
            :placeholder="t('ai_workflow.cron_descriptionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.cron_trigger')">
          <TriggerEditor
            v-model:trigger="formData.trigger"
            v-model:trigger-args="formData.trigger_args"
            preview-url="/ai/workspace/trigger/preview"
            @error="cronError = $event"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.cron_target')">
          <el-select v-model="formData.target_type" style="width: 100%">
            <el-option :label="t('ai_workflow.cron_agent')" value="agent" />
            <el-option :label="t('ai_workflow.cron_workflow')" value="workflow" />
            <el-option :label="t('ai_workflow.cron_app')" value="app" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.cron_targetId')">
          <el-input-number v-model="formData.target_id" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.cron_enabled')">
          <el-switch v-model="formData.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("ai_workflow.cron_cancel") }}</el-button>
          <el-button
            v-hasPerm="[
              dialogVisible.type === 'create' ? 'module_ai:cron:create' : 'module_ai:cron:update',
            ]"
            type="primary"
            :loading="submitLoading"
            @click="handleSubmit"
          >
            {{ t("ai_workflow.cron_save") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>

    <!-- 上次执行过程：直接读 ai_run_steps，与「AI 办公室」同一份数据 -->
    <el-dialog
      v-model="traceVisible"
      :title="traceTitle"
      width="640px"
      append-to-body
      class="cron-trace-dialog"
    >
      <div v-loading="traceLoading" class="cron-trace">
        <el-timeline v-if="traceSteps.length">
          <el-timeline-item
            v-for="st in traceSteps"
            :key="st.seq"
            :timestamp="st.time || ''"
            :type="st.ok === false ? 'danger' : 'primary'"
            placement="top"
          >
            <div class="cron-trace__t">
              <el-tag size="small" effect="plain" :type="kindMeta(st.kind).type">
                {{ kindMeta(st.kind).text }}
              </el-tag>
              <span class="cron-trace__name">{{ st.title }}</span>
              <el-tag v-if="st.duration_ms" size="small" effect="plain">
                {{ fmtSecs(st.duration_ms) }}
              </el-tag>
              <el-button
                v-if="st.detail && st.detail !== st.title"
                link
                type="primary"
                size="small"
                @click="toggleStep(st)"
              >
                {{ st.open ? "收起" : "明细" }}
              </el-button>
            </div>
            <!-- 工具调用：参数 / 结果分开看，等宽字体保留换行 -->
            <pre v-if="st.open && st.detail" class="cron-trace__pre">{{ st.detail }}</pre>
          </el-timeline-item>
        </el-timeline>
        <el-empty
          v-else-if="!traceLoading"
          :description="traceError || '这一轮没有步骤记录'"
          :image-size="70"
        />
      </div>
      <template #footer>
        <el-button @click="traceVisible = false">关闭</el-button>
      </template>
    </el-dialog>

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
        <el-table-column prop="created_time" :label="t('ai_workflow.cron_runTime')" width="160" />
        <el-table-column :label="t('ai_workflow.cron_result')" width="90">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="light"
              :type="row.result === 'success' ? 'success' : 'danger'"
            >
              {{
                row.result === "success"
                  ? t("ai_workflow.cron_success")
                  : t("ai_workflow.cron_fail")
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_workflow.cron_latency')" width="90">
          <template #default="{ row }">
            {{ (Number(row.latency_ms || 0) / 1000).toFixed(1) }}s
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_workflow.cron_errorSummary')" min-width="320">
          <template #default="{ row }">
            <span v-if="row.error" class="cron-history__error">{{ row.error }}</span>
            <span v-else-if="row.reply_preview" class="cron-history__reply">
              {{ row.reply_preview }}
            </span>
            <span v-else class="cron-history__empty">{{ t("ai_workflow.cron_noOutput") }}</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :image-size="60" :description="t('ai_workflow.cron_noRun')" />
        </template>
      </el-table>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { Clock, Delete, Edit, Plus, Search, Timer, VideoPlay } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";

import {
  createWorkspaceCron,
  deleteWorkspaceCron,
  getCronRuns,
  getWorkspaceCronList,
  runWorkspaceCron,
  updateWorkspaceCron,
  type WorkspaceCronRow,
} from "@/api/module_ai/workspace";
import { getOfficeSteps } from "@/api/module_ai/agent";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import TriggerEditor from "@/components/TriggerEditor/index.vue";

defineOptions({ name: "AiCron" });

/** 页面还活着吗：轮询是 fire-and-forget，离开后不该再弹提示 */
let alive = true;
onBeforeUnmount(() => {
  alive = false;
});

const { t } = useI18n();

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
  { label: t("ai_workflow.cron_cron"), value: "cron" },
  { label: t("ai_workflow.cron_interval"), value: "interval" },
  { label: t("ai_workflow.cron_date"), value: "date" },
  { label: t("ai_workflow.cron_now"), value: "now" },
];
const targetOptions = [
  { label: t("ai_workflow.cron_agent"), value: "agent" },
  { label: t("ai_workflow.cron_workflow"), value: "workflow" },
  { label: t("ai_workflow.cron_app"), value: "app" },
];
const TRIGGER_LABELS: Record<string, { text: string; type: TagType }> = {
  cron: { text: t("ai_workflow.cron_cron"), type: "primary" },
  interval: { text: t("ai_workflow.cron_interval"), type: "success" },
  date: { text: t("ai_workflow.cron_date"), type: "warning" },
  now: { text: t("ai_workflow.cron_now"), type: "info" },
};
function triggerMeta(trigger: string): { text: string; type: TagType } {
  return (
    TRIGGER_LABELS[trigger] || {
      text: trigger || t("ai_workflow.cron_notConfigured"),
      type: "info",
    }
  );
}

const TARGET_LABELS: Record<string, { text: string; type: TagType }> = {
  agent: { text: t("ai_workflow.cron_agent"), type: "primary" },
  workflow: { text: t("ai_workflow.cron_workflow"), type: "success" },
  app: { text: t("ai_workflow.cron_app"), type: "info" },
};
function targetMeta(t2: string): { text: string; type: TagType } {
  return TARGET_LABELS[t2] || { text: t2 || "—", type: "info" };
}

/** 人话描述缺失（脏数据）时的兜底：原样展示契约值，不自算 */
function argsFallback(row: WorkspaceCronRow): string {
  const args = row.trigger_args;
  if (args === null || args === undefined || args === "") {
    return row.trigger === "now" ? "—" : t("ai_workflow.cron_notConfigured");
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
    ElMessage.success(val ? t("ai_workflow.cron_enabledMsg") : t("ai_workflow.cron_disabledMsg"));
  } catch {
    row.enabled = prev;
  }
}

/** 正在跑的定时任务（本地状态：卡片上显示「执行中…」，按钮转圈） */
const runningIds = ref<number[]>([]);
function isRunning(id: number): boolean {
  return runningIds.value.includes(id);
}

/** 立即执行：二次确认后入队（接口只入队，执行走后台，与调度器同一路径） */
async function handleRun(row: WorkspaceCronRow) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.cron_runConfirm", { name: row.name }),
      t("ai_workflow.cron_runNowTitle"),
      {
        confirmButtonText: t("ai_workflow.cron_execute"),
        cancelButtonText: t("ai_workflow.cron_cancel"),
        type: "warning"
      }
    );
  } catch {
    return;   // 点了取消：什么都不做（别把 confirm 的 reject 抛到控制台）
  }
  const before = row.last_run_time || "";
  runLoadingId.value = row.id;
  try {
    await runWorkspaceCron(row.id);
  } catch (e: any) {
    ElMessage.warning(e?.message || "触发失败");
    return;
  } finally {
    runLoadingId.value = null;
  }
  ElMessage.success("已触发执行，跑完会自动更新这张卡");
  runningIds.value = [...runningIds.value, row.id];
  pollCronResult(row.id, before);
}

/**
 * 盯住刚触发的那一条：每 3 秒取一次列表，`last_run_time` 变了就**只替换这一张卡**，
 * 不整表刷新（避免闪烁、丢滚动位置）。最多等 2 分钟，超时就放开按钮等用户手动刷。
 */
async function pollCronResult(id: number, before: string) {
  try {
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      if (!alive) return;   // 用户已经离开这一页：别再打接口、也别弹提示
      const res: any = await getWorkspaceCronList();
      const fresh = (res?.data?.data?.items || []).find((x: any) => x.id === id);
      if (!fresh) break;
      if ((fresh.last_run_time || "") !== before) {
        const idx = rows.value.findIndex((r) => r.id === id);
        if (idx >= 0) rows.value[idx] = { ...rows.value[idx], ...fresh };
        if (fresh.last_status === "error") {
          ElMessage.warning(`「${fresh.name}」执行失败：${fresh.last_message || "详见过程"}`);
        } else {
          ElMessage.success(`「${fresh.name}」执行完成`);
        }
        break;
      }
    }
  } catch {
    /* 单次拉取失败不打断，继续等 */
  } finally {
    runningIds.value = runningIds.value.filter((x) => x !== id);
  }
}

/** 步骤类型 → 中文 + 标签色（和后端 ai_run_steps.kind 对应） */
const KIND_META: Record<string, { text: string; type: TagType }> = {
  plan: { text: "接活", type: "primary" },
  tool: { text: "工具", type: "info" },
  retry: { text: "重试", type: "warning" },
  summary: { text: "完成", type: "success" },
  error: { text: "失败", type: "danger" },
};
function kindMeta(kind: string): { text: string; type: TagType } {
  return KIND_META[kind] || { text: kind || "步骤", type: "info" };
}

/** 展开/收起某一步的明细（工具参数与结果可能很长） */
function toggleStep(st: any) {
  st.open = !st.open;
}

/** 毫秒 → 「12.7 秒」/「820 毫秒」 */
function fmtSecs(ms: number): string {
  const v = Number(ms || 0);
  if (!v) return "";
  return v < 1000 ? `${v} 毫秒` : `${(v / 1000).toFixed(1)} 秒`;
}

// ---- 上次执行过程（ai_run_steps，与 AI 办公室同源） ----
const traceVisible = ref(false);
const traceLoading = ref(false);
const traceTitle = ref("");
const traceSteps = ref<any[]>([]);
const traceError = ref("");

async function openTrace(row: WorkspaceCronRow) {
  if (!row.last_run_id) return;
  traceTitle.value = `执行过程 · ${row.name}`;
  traceSteps.value = [];
  traceError.value = "";
  traceVisible.value = true;
  traceLoading.value = true;
  try {
    const res: any = await getOfficeSteps({ run_id: row.last_run_id, limit: 60 });
    traceSteps.value = (res?.data?.data || [])
      .slice()
      .sort((a: any, b: any) => a.seq - b.seq)
      .map((x: any) => ({ ...x, open: false }));
  } catch {
    traceSteps.value = [];
    traceError.value = "读取执行过程失败（可能没有 AI 办公室的查看权限）";
  } finally {
    traceLoading.value = false;
  }
}

// ---- 执行历史 ----
const historyVisible = ref(false);
const historyLoading = ref(false);
const historyTitle = ref(t("ai_workflow.cron_historyTitle"));
const historyRows = ref<Array<Record<string, unknown>>>([]);

/** 打开执行历史：列出该定时任务每次调度/立即执行的结果。 */
async function openHistory(row: WorkspaceCronRow) {
  historyTitle.value = t("ai_workflow.cron_historyTitleWithName", { name: row.name });
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
    ElMessage.error(t("ai_workflow.cron_historyLoadFail"));
  } finally {
    historyLoading.value = false;
  }
}

async function handleDelete(row: WorkspaceCronRow) {
  await ElMessageBox.confirm(
    t("ai_workflow.cron_deleteConfirm", { name: row.name }),
    t("ai_workflow.cron_deleteConfirmTitle"),
    {
      confirmButtonText: t("ai_workflow.cron_delete"),
      cancelButtonText: t("ai_workflow.cron_cancel"),
      type: "warning",
    }
  );
  await deleteWorkspaceCron(row.id);
  ElMessage.success(t("ai_workflow.cron_deleted"));
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
  name: [{ required: true, message: t("ai_workflow.cron_taskNamePlaceholder"), trigger: "blur" }],
});

/** TriggerEditor 上抛的非法原因（非空即拦截保存）；空串表示配置合法 */
const cronError = ref("");

function openCreate() {
  dialogVisible.type = "create";
  dialogVisible.title = t("ai_workflow.cron_createTitle");
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
  dialogVisible.title = t("ai_workflow.cron_editTitle");
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
    ElMessage.success(isEdit ? t("ai_workflow.cron_saved") : t("ai_workflow.cron_created"));
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

.ai-cron-page /* 上次结果：单行省略，卡片高度保持一致 */
.cron-card__result .cron-card__value {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cron-card__cost {
  color: var(--el-text-color-secondary);
  font-variant-numeric: tabular-nums;
}

.cron-trace__t {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-primary);
}
.cron-trace__name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.cron-trace__pre {
  margin: 6px 0 0;
  padding: 8px 10px;
  max-height: 240px;
  overflow: auto;
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  font-family: var(--el-font-family-mono, Consolas, monospace);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.cron-trace__d {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.cron-card__target-id {
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
