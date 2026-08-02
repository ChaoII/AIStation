<template>
  <div class="fa-full-height record-page">
    <div class="record-tabs">
      <button class="rtab" :class="{ active: activeTab === 'plan' }" @click="activeTab = 'plan'">录像计划</button>
      <button class="rtab" :class="{ active: activeTab === 'log' }" @click="activeTab = 'log'; fetchLogs()">执行日志</button>
    </div>

    <!-- 录像计划 -->
    <template v-if="activeTab === 'plan'">
      <FaSearchBar
        v-show="showSearchBar"
        ref="searchBarRef"
        v-model="searchForm"
        :items="searchItems"
        :rules="searchBarRules"
        :is-expand="false"
        :show-expand="true"
        :show-reset="true"
        :show-search="true"
        :default-expanded="false"
        @search="handleSearch"
        @reset="onResetSearch"
      />
      <ElCard shadow="hover" class="fa-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
        <FaTableHeader v-model:columns="columnChecks" v-model:showSearchBar="showSearchBar" :loading="loading" @refresh="refreshData">
          <template #left>
            <FaTableHeaderLeft
              :remove-ids="selectedIds"
              :perm-create="['module_video:record:create']"
              :perm-delete="['module_video:record:delete']"
              :delete-loading="batchDeleting"
              @add="handleOpenDialog('create')"
              @delete="handleBatchDelete"
            />
          </template>
        </FaTableHeader>
        <FaTable
          ref="faTableRef"
          :loading="loading"
          :data="data"
          :columns="columns"
          :pagination="pagination"
          @selection-change="onTableSelectionChange"
          @pagination:size-change="handleSizeChange"
          @pagination:current-change="handleCurrentChange"
        />
      </ElCard>
    </template>

    <!-- 执行日志 -->
    <template v-if="activeTab === 'log'">
      <ElCard shadow="hover" class="fa-table-card">
        <ElTable v-loading="logLoading" :data="logItems" border stripe height="70vh">
          <template #empty><ElEmpty :image-size="60" description="暂无日志" /></template>
          <ElTableColumn type="index" label="序号" width="60" align="center" />
          <ElTableColumn label="摄像机" min-width="140"><template #default="{ row }">{{ row.camera?.name || `#${row.camera_id}` }}</template></ElTableColumn>
          <ElTableColumn label="流ID" min-width="160"><template #default="{ row }"><span class="mono">{{ row.stream_id }}</span></template></ElTableColumn>
          <ElTableColumn label="触发方式" width="90" align="center"><template #default="{ row }"><ElTag :type="triggerTagType(row.trigger_type)" size="small" effect="plain">{{ triggerLabel(row.trigger_type) }}</ElTag></template></ElTableColumn>
          <ElTableColumn label="状态" width="90" align="center"><template #default="{ row }"><ElTag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</ElTag></template></ElTableColumn>
          <ElTableColumn label="开始时间" width="170"><template #default="{ row }"><span class="mono">{{ row.start_time }}</span></template></ElTableColumn>
          <ElTableColumn label="结束时间" width="170"><template #default="{ row }"><span class="mono">{{ row.end_time || "-" }}</span></template></ElTableColumn>
          <ElTableColumn label="时长" width="90" align="center"><template #default="{ row }">{{ row.duration ? `${row.duration}s` : "-" }}</template></ElTableColumn>
          <ElTableColumn label="错误信息" min-width="160"><template #default="{ row }"><span v-if="row.error_msg" class="log-error">{{ row.error_msg }}</span><span v-else class="log-none">-</span></template></ElTableColumn>
        </ElTable>
        <div style="display:flex;justify-content:flex-end;padding:12px">
          <ElPagination v-model:current-page="logPage.page_no" v-model:page-size="logPage.page_size" :page-sizes="[10,20,30,50]" :total="logTotal" layout="total, sizes, prev, pager, next, jumper" background small @current-change="fetchLogs" @size-change="fetchLogs" />
        </div>
      </ElCard>
    </template>

    <!-- 计划弹窗 -->
    <ElDialog v-model="dialogVisible.visible" :title="dialogVisible.title" width="720px" :close-on-click-modal="false">
      <ElForm ref="dataFormRef" :model="formData" label-width="110px">
        <div class="form-section-title">基础信息</div>
        <ElFormItem label="摄像机" prop="camera_id">
          <ElSelect v-model="formData.camera_id" filterable placeholder="请选择摄像机" style="width:300px">
            <ElOption v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="计划类型" prop="plan_type">
          <ElSelect v-model="formData.plan_type" style="width:300px" @change="onPlanTypeChange">
            <ElOption label="全天录制" value="CONTINUOUS" />
            <ElOption label="定时录制" value="SCHEDULE" />
            <ElOption label="事件录制" value="EVENT" />
            <ElOption label="告警录制" value="ALARM" />
          </ElSelect>
        </ElFormItem>
        <div v-if="formData.plan_type === 'SCHEDULE'">
          <div class="form-section-title">录制时段</div>
          <div class="schedule-grid-wrapper">
            <div class="schedule-header-row"><div class="schedule-corner" /><div v-for="h in 24" :key="h" class="schedule-header-cell">{{ String(h - 1).padStart(2, "0") }}</div></div>
            <div v-for="day in 7" :key="day" class="schedule-row">
              <div class="schedule-day-label">{{ weekDays[day - 1] }}</div>
              <div v-for="hour in 24" :key="hour" class="schedule-cell" :class="{ active: isSlotActive(day - 1, hour - 1) }" @mousedown.prevent="onCellMouseDown(day - 1, hour - 1, $event)" @mouseenter="onCellMouseEnter(day - 1, hour - 1)" />
            </div>
          </div>
          <div class="schedule-actions">
            <ElButton size="small" @click="fillSchedule(true)">全选</ElButton>
            <ElButton size="small" @click="fillSchedule(false)">清空</ElButton>
            <ElButton size="small" @click="fillWorkHours">工作日 08-18</ElButton>
          </div>
        </div>
        <div class="form-section-title">录制参数</div>
        <template v-if="formData.plan_type === 'EVENT' || formData.plan_type === 'ALARM'">
          <ElFormItem label="事件前录制"><ElInputNumber v-model="formData.pre_record_sec" :min="0" :max="30" controls-position="right" style="width:130px" /><span style="margin-left:8px;font-size:12px;color:#909399">秒</span></ElFormItem>
          <ElFormItem label="事件后录制"><ElInputNumber v-model="formData.post_record_sec" :min="0" :max="30" controls-position="right" style="width:130px" /><span style="margin-left:8px;font-size:12px;color:#909399">秒</span></ElFormItem>
        </template>
        <ElFormItem label="录像保存"><ElInputNumber v-model="formData.storage_days" :min="1" :max="365" controls-position="right" style="width:130px" /><span style="margin-left:8px;font-size:12px;color:#909399">天</span></ElFormItem>
        <div class="form-section-title">其他设置</div>
        <ElFormItem label="录制码流">
          <ElRadioGroup v-model="formData.stream_type">
            <ElRadio value="MAIN">主码流（高清）</ElRadio>
            <ElRadio value="SUB">子码流（流畅）</ElRadio>
          </ElRadioGroup>
        </ElFormItem>
        <ElFormItem label="状态" prop="status"><ElSwitch v-model="formData.status" /></ElFormItem>
        <ElFormItem label="备注" prop="description"><ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选备注" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeMount, onBeforeUnmount, h } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElTag } from "element-plus";
import { useTable } from "@/hooks/core/useTable";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { cleanEmptyArrayParams } from "@/utils/query";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import type { ColumnOption } from "@/types/component";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import { VideoAPI } from "@/api/module_video";

defineOptions({ name: "VideoRecord", inheritAttrs: false });

const router = useRouter();
const { hasAuth } = useAuth();
const activeTab = ref("plan");
const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const cameraOptions = ref<any[]>([]);
const scheduleGrid = ref<boolean[][]>(Array.from({ length: 7 }, () => Array(24).fill(false)));
const dragState = ref<{ active: boolean; mode: "set" | "clear" }>({ active: false, mode: "set" });

function planTypeLabel(type: string) {
  return ({ CONTINUOUS: "全天录制", SCHEDULE: "定时录制", EVENT: "事件录制", ALARM: "告警录制" } as any)[type] || type;
}
function planTypeTag(type: string) {
  return ({ CONTINUOUS: "primary", SCHEDULE: "success", EVENT: "warning", ALARM: "danger" } as any)[type] || "info";
}
function scheduleSummary(json: any): string {
  if (!json?.slots?.length) return "未配置";
  const total = json.slots.reduce((s: number, x: any) => s + (x.end - x.start), 0);
  return `每周 ${total} 小时`;
}
function scheduleCell(row: any) {
  if (row.plan_type === "CONTINUOUS") return "全天";
  if (row.plan_type === "SCHEDULE" && row.schedule_json) return scheduleSummary(row.schedule_json);
  if (row.plan_type === "EVENT") return "事件触发";
  if (row.plan_type === "ALARM") return "告警触发";
  return "—";
}
function statusCell(row: any) {
  return h("span", { style: "display:flex;align-items:center;gap:4px;justify-content:center" }, [
    h("span", { class: `status-dot ${row.is_running ? "running" : "stopped"}` }),
    h("span", { style: "font-size:12px" }, row.is_running ? "录制中" : "已停止"),
  ]);
}

function buildRowActions(row: any, ctx: { onExec: (row: any) => void; onStop: (row: any) => void; onToggle: (row: any, v: boolean) => void; onEdit: (id: number) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const actions: TableOperationAction[] = [];
  if (!row.is_running) actions.push({ key: "exec", label: "执行", artType: "view", icon: "ri:play-circle-line", iconColor: "var(--el-color-success)", perm: "module_video:record:update", run: () => ctx.onExec(row) });
  else actions.push({ key: "stop", label: "停止", artType: "view", icon: "ri:stop-circle-line", iconColor: "var(--el-color-warning)", perm: "module_video:record:update", run: () => ctx.onStop(row) });
  actions.push(
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_video:record:update", run: () => ctx.onEdit(row.id!) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:record:delete", run: () => ctx.onDelete(row.id!) },
  );
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ camera_id?: number; plan_type?: string }>({ camera_id: undefined, plan_type: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};
const searchItems = computed<SearchFormItem[]>(() => [
  { label: "摄像机", key: "camera_id", type: "select", props: { placeholder: "请选择摄像机", clearable: true, filterable: true, options: cameraOptions.value.map(c => ({ label: c.name, value: c.id })) }, span: 6 },
  { label: "计划类型", key: "plan_type", type: "select", props: { placeholder: "请选择", clearable: true, options: [{ label: "全天录制", value: "CONTINUOUS" }, { label: "定时录制", value: "SCHEDULE" }, { label: "事件录制", value: "EVENT" }, { label: "告警录制", value: "ALARM" }] }, span: 6 },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteRecordPlan([id]);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ }
}
async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    batchDeleting.value = true;
    await VideoAPI.deleteRecordPlan(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ } finally { batchDeleting.value = false; }
}

async function togglePlan(row: any, val: boolean) {
  try { await VideoAPI.toggleRecordPlan(row.id); row.status = val; await refreshData(); } catch { /* ignore */ }
}
async function executePlan(row: any) {
  try { await VideoAPI.executeRecordPlan(row.id); row.is_running = true; ElMessage.success("计划已触发执行"); await refreshData(); } catch { /* ignore */ }
}
async function stopPlan(row: any) {
  try { await VideoAPI.stopRecordPlan(row.id); row.is_running = false; ElMessage.success("计划已停止"); await refreshData(); } catch { /* ignore */ }
}

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({
  id: undefined as number | undefined, camera_id: undefined as number | undefined, plan_type: "CONTINUOUS" as string,
  pre_record_sec: 5, post_record_sec: 5, storage_days: 30, stream_type: "MAIN" as string, status: true, description: undefined as string | undefined,
});
const initialFormData = { id: undefined, camera_id: undefined, plan_type: "CONTINUOUS", pre_record_sec: 5, post_record_sec: 5, storage_days: 30, stream_type: "MAIN", status: true, description: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);

function isSlotActive(day: number, hour: number): boolean { return scheduleGrid.value[day]?.[hour] || false; }
function setSlot(day: number, hour: number, val: boolean) { scheduleGrid.value[day][hour] = val; }
function onCellMouseDown(day: number, hour: number, e: MouseEvent) {
  if (e.button !== 0) return;
  const current = scheduleGrid.value[day][hour];
  dragState.value = { active: true, mode: current ? "clear" : "set" };
  setSlot(day, hour, !current);
}
function onCellMouseEnter(day: number, hour: number) { if (dragState.value.active) setSlot(day, hour, dragState.value.mode === "set"); }
function onDragEnd() { dragState.value.active = false; }
function fillSchedule(val: boolean) { for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) scheduleGrid.value[d][h] = val; }
function fillWorkHours() { fillSchedule(false); for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) scheduleGrid.value[d][h] = true; }
function scheduleGridToJson(): any {
  const slots: { day: number; start: number; end: number }[] = [];
  for (let d = 0; d < 7; d++) {
    let start = -1;
    for (let h = 0; h <= 24; h++) {
      const active = h < 24 && scheduleGrid.value[d][h];
      if (active && start === -1) start = h;
      if (!active && start !== -1) { slots.push({ day: d, start, end: h }); start = -1; }
    }
  }
  return { type: "weekly", slots };
}
function jsonToScheduleGrid(json: any) {
  scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  if (!json?.slots) return;
  for (const slot of json.slots) {
    if (slot.day >= 0 && slot.day < 7) for (let h = slot.start; h < slot.end && h < 24; h++) scheduleGrid.value[slot.day][h] = true;
  }
}
function onPlanTypeChange() {
  if (formData.plan_type !== "SCHEDULE") scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑计划";
    const res = await VideoAPI.listRecordPlan({ page_no: 1, page_size: 100 });
    const item = (res.data?.data?.items || []).find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id, camera_id: item.camera_id, plan_type: item.plan_type,
        pre_record_sec: item.pre_record_sec, post_record_sec: item.post_record_sec,
        storage_days: item.storage_days, stream_type: item.stream_type, status: item.status, description: item.description,
      });
      if (item.schedule_json) jsonToScheduleGrid(item.schedule_json);
    }
  } else {
    dialogVisible.title = "新增计划";
    Object.assign(formData, initialFormData);
    scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  }
  dialogVisible.visible = true;
}
async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    submitLoading.value = true;
    const id = formData.id;
    const payload: any = { ...formData };
    if (formData.plan_type === "SCHEDULE") payload.schedule_json = scheduleGridToJson();
    try {
      if (id) await VideoAPI.updateRecordPlan(id, payload);
      else await VideoAPI.createRecordPlan(payload);
      ElMessage.success("保存成功");
      dialogVisible.visible = false;
      await refreshData();
    } catch { /* ignore */ } finally { submitLoading.value = false; }
  });
}

const opCtx = {
  onExec: executePlan, onStop: stopPlan, onToggle: togglePlan,
  onEdit: (id: number) => void handleOpenDialog("update", id), onDelete: deleteRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshRemove } = useTable({
  core: {
    apiFn: VideoAPI.listRecordPlan,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "camera_name", label: "摄像机", minWidth: 160, formatter: (row: any) => row.camera?.name || `#${row.camera_id}` },
      { prop: "plan_type", label: "计划类型", width: 110, align: "center", formatter: (row: any) => h(ElTag, { type: planTypeTag(row.plan_type), size: "small", effect: "plain" }, () => planTypeLabel(row.plan_type)) },
      { prop: "schedule", label: "录制时段", minWidth: 200, formatter: (row: any) => scheduleCell(row) },
      { prop: "pre_record_sec", label: "预录", width: 70, align: "center", formatter: (row: any) => `${row.pre_record_sec}s` },
      { prop: "post_record_sec", label: "延录", width: 70, align: "center", formatter: (row: any) => `${row.post_record_sec}s` },
      { prop: "storage_days", label: "存储", width: 70, align: "center", formatter: (row: any) => `${row.storage_days}天` },
      { prop: "stream_type", label: "码流", width: 70, align: "center", formatter: (row: any) => h(ElTag, { size: "small" }, () => row.stream_type === "MAIN" ? "主" : "子") },
      { prop: "status", label: "状态", width: 100, align: "center", formatter: (row: any) => statusCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      { prop: "operation", label: "操作", width: 200, fixed: "right", align: "right", formatter: (row: any) => renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }) },
    ],
  },
});

// Log tab
const logItems = ref<any[]>([]);
const logTotal = ref(0);
const logLoading = ref(false);
const logPage = reactive({ page_no: 1, page_size: 20 });
async function fetchLogs() {
  logLoading.value = true;
  try {
    const res = await VideoAPI.listRecordLog({ ...logPage });
    logItems.value = res.data?.data?.items || [];
    logTotal.value = res.data?.data?.total || 0;
  } catch { /* ignore */ } finally { logLoading.value = false; }
}
function triggerLabel(t: string) { return ({ SCHEDULED: "定时", MANUAL: "手动", ALARM: "告警" } as any)[t] || t; }
function triggerTagType(t: string) { return ({ SCHEDULED: "success", MANUAL: "primary", ALARM: "danger" } as any)[t] || "info"; }
function statusLabel(s: string) { return ({ RECORDING: "录制中", COMPLETED: "已完成", FAILED: "失败", STOPPED: "已停止" } as any)[s] || s; }
function statusTagType(s: string) { return ({ RECORDING: "warning", COMPLETED: "success", FAILED: "danger", STOPPED: "info" } as any)[s] || "info"; }

function handleSearch(params: { camera_id?: number; plan_type?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { camera_id: undefined, plan_type: undefined };
  void resetSearchParams();
}

onBeforeMount(() => {
  VideoAPI.listCamera({ page_size: 100 }).then(r => { cameraOptions.value = r.data?.data?.items || []; }).catch(() => {});
  document.addEventListener("mouseup", onDragEnd);
});
onBeforeUnmount(() => { document.removeEventListener("mouseup", onDragEnd); });
</script>

<style scoped>
.record-page { display: flex; flex-direction: column; height: 100%; }
.record-tabs { display: flex; flex-shrink: 0; border-bottom: 1px solid var(--el-border-color-light); }
.rtab { padding: 10px 20px; font-size: 14px; font-weight: 500; color: var(--el-text-color-secondary); cursor: pointer; background: transparent; border: none; border-bottom: 2px solid transparent; transition: all 0.15s; margin-bottom: -1px; }
.rtab:hover { color: var(--el-text-color-primary); }
.rtab.active { color: var(--el-color-primary); border-bottom-color: var(--el-color-primary); }
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.status-dot.running { background: var(--el-color-success); box-shadow: 0 0 6px var(--el-color-success); }
.status-dot.stopped { background: var(--el-text-color-placeholder); }
.mono { font-family: "SF Mono", "Cascadia Code", monospace; font-size: 12px; }
.log-error { color: var(--el-color-danger); font-size: 12px; }
.log-none { color: var(--el-text-color-placeholder); }
.schedule-grid-wrapper { padding-bottom: 4px; overflow-x: auto; }
.schedule-header-row { display: flex; gap: 2px; margin-bottom: 2px; }
.schedule-corner { flex-shrink: 0; width: 44px; }
.schedule-header-cell { flex-shrink: 0; width: 24px; font-size: 10px; line-height: 20px; color: var(--el-text-color-placeholder); text-align: center; }
.schedule-row { display: flex; gap: 2px; align-items: center; margin-bottom: 2px; }
.schedule-day-label { flex-shrink: 0; width: 44px; padding-right: 6px; font-size: 12px; color: var(--el-text-color-secondary); text-align: right; }
.schedule-cell { flex-shrink: 0; width: 24px; height: 20px; cursor: pointer; background: var(--el-fill-color); border: 1px solid var(--el-border-color-lighter); border-radius: 2px; transition: all 0.15s; }
.schedule-cell:hover { border-color: var(--el-color-primary); }
.schedule-cell.active { background: var(--el-color-primary); border-color: var(--el-color-primary); }
.schedule-actions { display: flex; gap: 6px; margin-top: 8px; }
.form-section-title { font-weight: 600; font-size: 13px; color: #303133; margin: 12px 0 8px; border-bottom: 1px solid #ebeef5; padding-bottom: 6px; }
</style>
