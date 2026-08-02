<template>
  <div class="fa-full-height">
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
            :perm-create="['module_video:algorithm:create']"
            :perm-delete="['module_video:algorithm:delete']"
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

    <ElDialog v-model="dialogVisible.visible" :title="dialogVisible.title" width="680px" :close-on-click-modal="false">
      <ElForm ref="dataFormRef" :model="formData" label-width="110px">
        <div class="form-section-title">布控配置</div>
        <ElFormItem label="监控点位" prop="camera_id">
          <ElSelect v-model="formData.camera_id" filterable placeholder="选择摄像机" style="width:280px">
            <ElOption v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="智能算法" prop="algorithm_id">
          <ElSelect v-model="formData.algorithm_id" filterable placeholder="选择算法" style="width:280px" @change="handleAlgorithmChange">
            <ElOption v-for="a in algorithmOptions" :key="a.id" :label="a.name" :value="a.id" />
          </ElSelect>
        </ElFormItem>
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="分析码流" prop="stream_type">
              <ElSelect v-model="formData.stream_type" style="width:100%">
                <ElOption label="主码流（高清）" value="MAIN" />
                <ElOption label="子码流（流畅）" value="SUB" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="灵敏度" prop="sensitivity">
              <ElInputNumber v-model="formData.sensitivity" :min="1" :max="100" controls-position="right" style="width:100%" />
            </ElFormItem>
          </ElCol>
        </ElRow>

        <div class="form-section-title">布控时段<span style="font-size:12px;font-weight:400;color:var(--el-text-color-placeholder);margin-left:8px">选择算法生效的时间段</span></div>
        <div class="schedule-grid-wrapper">
          <div class="schedule-header-row">
            <div class="schedule-corner" />
            <div v-for="h in 24" :key="h" class="schedule-header-cell">{{ String(h - 1).padStart(2, "0") }}</div>
          </div>
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

        <div class="form-section-title">其他</div>
        <ElFormItem label="状态" prop="statusBool"><ElSwitch v-model="formData.statusBool" active-text="运行中" inactive-text="已停止" /></ElFormItem>
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

defineOptions({ name: "VideoDeploy", inheritAttrs: false });

const { hasAuth } = useAuth();
const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const cameraOptions = ref<any[]>([]);
const algorithmOptions = ref<any[]>([]);

const scheduleGrid = ref<boolean[][]>(Array.from({ length: 7 }, () => Array(24).fill(false)));
const dragState = ref<{ active: boolean; mode: "set" | "clear" }>({ active: false, mode: "set" });

function scheduleSummary(json: any): string {
  if (!json?.slots?.length) return "未配置";
  const totalHours = json.slots.reduce((sum: number, s: any) => sum + (s.end - s.start), 0);
  return `每周 ${totalHours} 小时`;
}
function isSlotActive(day: number, hour: number): boolean {
  return scheduleGrid.value[day]?.[hour] || false;
}
function setSlot(day: number, hour: number, val: boolean) { scheduleGrid.value[day][hour] = val; }
function onCellMouseDown(day: number, hour: number, e: MouseEvent) {
  if (e.button !== 0) return;
  const current = scheduleGrid.value[day][hour];
  dragState.value = { active: true, mode: current ? "clear" : "set" };
  setSlot(day, hour, !current);
}
function onCellMouseEnter(day: number, hour: number) {
  if (!dragState.value.active) return;
  setSlot(day, hour, dragState.value.mode === "set");
}
function onDragEnd() { dragState.value.active = false; }
function fillSchedule(val: boolean) {
  for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) scheduleGrid.value[d][h] = val;
}
function fillWorkHours() {
  fillSchedule(false);
  for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) scheduleGrid.value[d][h] = true;
}
const scheduleGridToJson = () => {
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
};
const jsonToScheduleGrid = (json: any) => {
  scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  if (!json?.slots) return;
  for (const slot of json.slots) {
    if (slot.day >= 0 && slot.day < 7) {
      for (let h = slot.start; h < slot.end && h < 24; h++) scheduleGrid.value[slot.day][h] = true;
    }
  }
};

function buildRowActions(row: any, ctx: { onEdit: (id: number) => void; onToggle: (row: any) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const actions: TableOperationAction[] = [
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", run: () => ctx.onEdit(row.id!) },
    { key: "toggle", label: row.status === "RUNNING" ? "停止" : "启动", artType: "view", icon: row.status === "RUNNING" ? "ri:stop-circle-line" : "ri:play-circle-line", iconColor: row.status === "RUNNING" ? "var(--el-color-warning)" : "var(--el-color-success)", run: () => ctx.onToggle(row) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:algorithm:delete", run: () => ctx.onDelete(row.id!) },
  ];
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ camera_id?: number; status?: string }>({ camera_id: undefined, status: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};
const searchItems = computed<SearchFormItem[]>(() => [
  { label: "监控点位", key: "camera_id", type: "select", props: { placeholder: "选择摄像机", clearable: true, filterable: true, options: cameraOptions.value.map(c => ({ label: c.name, value: c.id })) }, span: 6 },
  { label: "状态", key: "status", type: "select", props: { placeholder: "全部", clearable: true, options: [{ label: "运行中", value: "RUNNING" }, { label: "已停止", value: "STOPPED" }] }, span: 6 },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteAlgorithmTask([id]);
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
    await VideoAPI.deleteAlgorithmTask(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ } finally { batchDeleting.value = false; }
}

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({
  id: undefined as number | undefined, camera_id: undefined as number | undefined, algorithm_id: undefined as number | undefined,
  stream_type: "SUB", sensitivity: 50, statusBool: true, description: undefined as string | undefined,
});
const initialFormData = { id: undefined, camera_id: undefined, algorithm_id: undefined, stream_type: "SUB", sensitivity: 50, statusBool: true, description: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);

async function handleAlgorithmChange(algoId: number) {
  if (!algoId) return;
  try {
    const res = await VideoAPI.listAlgorithm({ page_size: 100 });
    const algo = (res.data?.data?.items || []).find((a: any) => a.id === algoId);
  } catch { /* noop */ }
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑布控计划";
    const res = await VideoAPI.listAlgorithmTask({ page_no: 1, page_size: 100 });
    const item = (res.data?.data?.items || []).find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id, camera_id: item.camera_id, algorithm_id: item.algorithm_id,
        stream_type: item.stream_type, sensitivity: item.sensitivity,
        statusBool: item.status === "RUNNING", description: item.description,
      });
      if (item.schedule_json) jsonToScheduleGrid(item.schedule_json);
    }
  } else {
    dialogVisible.title = "新增布控计划";
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
    const payload: any = {
      camera_id: formData.camera_id,
      algorithm_id: formData.algorithm_id,
      stream_type: formData.stream_type,
      sensitivity: formData.sensitivity,
      status: formData.statusBool ? "RUNNING" : "STOPPED",
      description: formData.description,
      schedule_json: scheduleGridToJson(),
    };
    try {
      if (id) await VideoAPI.updateAlgorithmTask(id, payload);
      else await VideoAPI.createAlgorithmTask(payload);
      ElMessage.success("保存成功");
      dialogVisible.visible = false;
      await refreshData();
    } catch { /* ignore */ } finally { submitLoading.value = false; }
  });
}

async function handleToggleInference(row: any) {
  try {
    if (row.status === "RUNNING") { await VideoAPI.stopInferenceTask(row.id); ElMessage.success("推理已停止"); }
    else { await VideoAPI.startInferenceTask(row.id); ElMessage.success("推理已启动"); }
    await refreshData();
  } catch { ElMessage.error("操作失败"); }
}

const opCtx = {
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onToggle: handleToggleInference,
  onDelete: deleteRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshRemove } = useTable({
  core: {
    apiFn: VideoAPI.listAlgorithmTask,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "camera_name", label: "监控点位", minWidth: 150, formatter: (row: any) => row.camera?.name || `#${row.camera_id}` },
      { prop: "algorithm_name", label: "智能算法", minWidth: 140, formatter: (row: any) => row.algorithm?.name || `#${row.algorithm_id}` },
      { prop: "schedule", label: "布控时段", minWidth: 160, formatter: (row: any) => scheduleSummary(row.schedule_json) },
      { prop: "sensitivity", label: "灵敏度", width: 80, align: "center" },
      { prop: "stream_type", label: "码流", width: 70, align: "center", formatter: (row: any) => h(ElTag, { size: "small" }, () => row.stream_type === "MAIN" ? "主" : "子") },
      { prop: "status", label: "状态", width: 100, align: "center", formatter: (row: any) => h(ElTag, { type: row.status === "RUNNING" ? "success" : "info", size: "small" }, () => row.status === "RUNNING" ? "运行中" : "已停止") },
      {
        prop: "operation", label: "操作", width: 180, fixed: "right", align: "right",
        formatter: (row: any) => renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { camera_id?: number; status?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { camera_id: undefined, status: undefined };
  void resetSearchParams();
}

onBeforeMount(() => {
  Promise.all([VideoAPI.listCamera({ page_size: 100 }), VideoAPI.listAlgorithm({ page_size: 100 })])
    .then(([c, a]) => {
      cameraOptions.value = c.data?.data?.items || [];
      algorithmOptions.value = a.data?.data?.items || [];
    })
    .catch(() => {});
  document.addEventListener("mouseup", onDragEnd);
});
onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onDragEnd);
});
</script>

<style scoped>
.form-section-title { font-weight: 600; font-size: 13px; color: #303133; margin: 12px 0 8px; }
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
</style>
