<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_video:record:create']"
          :perm-delete="['module_video:record:delete']"
          :perm-patch="['module_video:record:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              type="index"
              fixed
              label="序号"
              min-width="60"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'camera')?.show"
              key="camera"
              label="摄像机"
              min-width="160"
            >
              <template #default="scope">
                {{ scope.row.camera?.name || `#${scope.row.camera_id}` }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'plan_type')?.show"
              key="plan_type"
              label="计划类型"
              width="110"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="planTypeTag(scope.row.plan_type) as any" size="small" effect="plain">
                  {{ planTypeLabel(scope.row.plan_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'schedule')?.show"
              key="schedule"
              label="录制时段"
              min-width="200"
            >
              <template #default="scope">
                <span v-if="scope.row.plan_type === 'CONTINUOUS'" class="schedule-summary">
                  全天
                </span>
                <span
                  v-else-if="scope.row.plan_type === 'SCHEDULE' && scope.row.schedule_json"
                  class="schedule-summary"
                >
                  {{ scheduleSummary(scope.row.schedule_json) }}
                </span>
                <span v-else-if="scope.row.plan_type === 'EVENT'" class="schedule-summary">
                  事件触发
                </span>
                <span v-else-if="scope.row.plan_type === 'ALARM'" class="schedule-summary">
                  告警触发
                </span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'pre_record_sec')?.show"
              key="pre_record_sec"
              label="预录"
              width="70"
              align="center"
            >
              <template #default="scope">{{ scope.row.pre_record_sec }}s</template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'post_record_sec')?.show"
              key="post_record_sec"
              label="延录"
              width="70"
              align="center"
            >
              <template #default="scope">{{ scope.row.post_record_sec }}s</template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'storage_days')?.show"
              key="storage_days"
              label="存储"
              width="70"
              align="center"
            >
              <template #default="scope">{{ scope.row.storage_days }}天</template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'stream_type')?.show"
              key="stream_type"
              label="码流"
              width="70"
              align="center"
            >
              <template #default="scope">
                <el-tag size="small">{{ scope.row.stream_type === "MAIN" ? "主" : "子" }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
              width="70"
              align="center"
            >
              <template #default="scope">
                <el-switch v-model="scope.row.status" disabled />
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              label="创建时间"
              prop="created_time"
              min-width="170"
              sortable
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="150"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_video:record:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:record:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="720px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px" size="default">
        <div class="form-section">
          <div class="form-section-title">基础信息</div>
          <el-form-item label="摄像机" prop="camera_id">
            <el-select
              v-model="formData.camera_id"
              filterable
              placeholder="请选择摄像机"
              style="width: 300px"
            >
              <el-option v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="计划类型" prop="plan_type">
            <el-select v-model="formData.plan_type" style="width: 300px" @change="onPlanTypeChange">
              <el-option label="全天录制" value="CONTINUOUS" />
              <el-option label="定时录制" value="SCHEDULE" />
              <el-option label="事件录制" value="EVENT" />
              <el-option label="告警录制" value="ALARM" />
            </el-select>
          </el-form-item>
        </div>

        <!-- SCHEDULE: weekly time grid -->
        <div v-if="formData.plan_type === 'SCHEDULE'" class="form-section">
          <div class="form-section-title">
            录制时段
            <span class="form-section-desc">点击或拖拽选择需要录像的时间段</span>
          </div>
          <div class="schedule-grid-wrapper">
            <div class="schedule-header-row">
              <div class="schedule-corner" />
              <div v-for="h in 24" :key="h" class="schedule-header-cell">
                {{ String(h - 1).padStart(2, "0") }}
              </div>
            </div>
            <div v-for="day in 7" :key="day" class="schedule-row">
              <div class="schedule-day-label">{{ weekDays[day - 1] }}</div>
              <div
                v-for="hour in 24"
                :key="hour"
                class="schedule-cell"
                :class="{ active: isSlotActive(day - 1, hour - 1) }"
                @mousedown.prevent="onCellMouseDown(day - 1, hour - 1, $event)"
                @mouseenter="onCellMouseEnter(day - 1, hour - 1)"
              />
            </div>
          </div>
          <div class="schedule-actions">
            <el-button size="small" @click="fillSchedule(true)">全选</el-button>
            <el-button size="small" @click="fillSchedule(false)">清空</el-button>
            <el-button size="small" @click="fillWorkHours">工作日 08-18</el-button>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            录制参数
            <span class="form-section-desc">
              <template v-if="formData.plan_type === 'CONTINUOUS'">
                全天不间断录像，无需预录/延录
              </template>
              <template v-else-if="formData.plan_type === 'SCHEDULE'">
                按上方时间表执行，无需预录/延录
              </template>
              <template v-else>事件触发时根据设置提前/延后录制</template>
            </span>
          </div>

          <template v-if="formData.plan_type === 'EVENT' || formData.plan_type === 'ALARM'">
            <el-form-item label="事件前录制" prop="pre_record_sec">
              <div class="config-field">
                <el-input-number
                  v-model="formData.pre_record_sec"
                  :min="0"
                  :max="30"
                  :step="1"
                  controls-position="right"
                  style="width: 130px"
                />
                <span class="config-unit">秒</span>
                <span class="config-hint">事件触发前开始录制</span>
                <el-tooltip
                  content="设为 5 秒则事件触发时，实际保存了前 5 秒的录像"
                  placement="top"
                >
                  <el-icon class="config-help"><WarningFilled /></el-icon>
                </el-tooltip>
              </div>
            </el-form-item>
            <el-form-item label="事件后录制" prop="post_record_sec">
              <div class="config-field">
                <el-input-number
                  v-model="formData.post_record_sec"
                  :min="0"
                  :max="30"
                  :step="1"
                  controls-position="right"
                  style="width: 130px"
                />
                <span class="config-unit">秒</span>
                <span class="config-hint">事件结束后继续录制</span>
                <el-tooltip content="设为 10 秒则事件结束后继续录 10 秒再停止" placement="top">
                  <el-icon class="config-help"><WarningFilled /></el-icon>
                </el-tooltip>
              </div>
            </el-form-item>
          </template>

          <el-form-item label="录像保存" prop="storage_days">
            <div class="config-field">
              <el-input-number
                v-model="formData.storage_days"
                :min="1"
                :max="365"
                :step="1"
                controls-position="right"
                style="width: 130px"
              />
              <span class="config-unit">天</span>
              <span class="config-hint">硬盘保留期限，超期自动覆盖</span>
              <el-tooltip content="建议根据硬盘容量设置，全天录制推荐 7~30 天" placement="top">
                <el-icon class="config-help"><WarningFilled /></el-icon>
              </el-tooltip>
            </div>
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">其他设置</div>
          <el-form-item label="录制码流" prop="stream_type">
            <el-radio-group v-model="formData.stream_type">
              <el-radio value="MAIN">主码流（高清）</el-radio>
              <el-radio value="SUB">子码流（流畅）</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="状态" prop="status">
            <el-switch v-model="formData.status" />
          </el-form-item>
          <el-form-item label="备注" prop="description">
            <el-input
              v-model="formData.description"
              type="textarea"
              :rows="2"
              placeholder="可选备注"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";
import { WarningFilled } from "@element-plus/icons-vue";
import {
  getRecordPlanList,
  createRecordPlan,
  updateRecordPlan,
  deleteRecordPlan,
} from "@/api/module_video/record";
import { getCameraList } from "@/api/module_video/camera";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();
const cameraOptions = ref<any[]>([]);
const scheduleGrid = ref<boolean[][]>(Array.from({ length: 7 }, () => Array(24).fill(false)));
const dragState = ref<{ active: boolean; mode: "set" | "clear" }>({ active: false, mode: "set" });

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:record",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "camera_id",
      label: "摄像机",
      type: "select",
      options: [],
      attrs: {
        placeholder: "请选择摄像机",
        clearable: true,
        filterable: true,
        style: { width: "200px" },
      },
    },
    {
      prop: "plan_type",
      label: "计划类型",
      type: "select",
      options: [
        { label: "全天录制", value: "CONTINUOUS" },
        { label: "定时录制", value: "SCHEDULE" },
        { label: "事件录制", value: "EVENT" },
        { label: "告警录制", value: "ALARM" },
      ],
      attrs: { placeholder: "请选择", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "camera", label: "摄像机", show: true },
  { prop: "plan_type", label: "计划类型", show: true },
  { prop: "schedule", label: "录制时段", show: true },
  { prop: "pre_record_sec", label: "预录", show: true },
  { prop: "post_record_sec", label: "延录", show: true },
  { prop: "storage_days", label: "存储", show: true },
  { prop: "stream_type", label: "码流", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:record",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getRecordPlanList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deletePlan(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  camera_id: undefined as number | undefined,
  plan_type: "CONTINUOUS" as string,
  pre_record_sec: 5,
  post_record_sec: 5,
  storage_days: 30,
  stream_type: "MAIN" as string,
  status: true,
  description: undefined as string | undefined,
});

const initialFormData = {
  id: undefined as number | undefined,
  camera_id: undefined as number | undefined,
  plan_type: "CONTINUOUS" as const,
  pre_record_sec: 5,
  post_record_sec: 5,
  storage_days: 30,
  stream_type: "MAIN" as const,
  status: true,
  description: undefined as string | undefined,
};

function isSlotActive(day: number, hour: number): boolean {
  return scheduleGrid.value[day]?.[hour] || false;
}

function setSlot(day: number, hour: number, val: boolean) {
  scheduleGrid.value[day][hour] = val;
}

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

function onDragEnd() {
  dragState.value.active = false;
}

function fillSchedule(val: boolean) {
  for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) scheduleGrid.value[d][h] = val;
}

function fillWorkHours() {
  fillSchedule(false);
  for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) scheduleGrid.value[d][h] = true;
}

function scheduleGridToJson(): any {
  const slots: { day: number; start: number; end: number }[] = [];
  for (let d = 0; d < 7; d++) {
    let start = -1;
    for (let h = 0; h <= 24; h++) {
      const active = h < 24 && scheduleGrid.value[d][h];
      if (active && start === -1) start = h;
      if (!active && start !== -1) {
        slots.push({ day: d, start, end: h });
        start = -1;
      }
    }
  }
  return { type: "weekly", slots };
}

function jsonToScheduleGrid(json: any) {
  scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  if (!json?.slots) return;
  for (const slot of json.slots) {
    if (slot.day >= 0 && slot.day < 7) {
      for (let h = slot.start; h < slot.end && h < 24; h++) {
        scheduleGrid.value[slot.day][h] = true;
      }
    }
  }
}

function onPlanTypeChange() {
  if (formData.plan_type !== "SCHEDULE") {
    scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  }
}

function scheduleSummary(json: any): string {
  if (!json?.slots?.length) return "未配置";
  const totalHours = json.slots.reduce((sum: number, s: any) => sum + (s.end - s.start), 0);
  return `每周 ${totalHours} 小时`;
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑计划";
    const res = await getRecordPlanList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, {
        id: item.id,
        camera_id: item.camera_id,
        plan_type: item.plan_type,
        pre_record_sec: item.pre_record_sec,
        post_record_sec: item.post_record_sec,
        storage_days: item.storage_days,
        stream_type: item.stream_type,
        status: item.status,
        description: item.description,
      });
      if (item.schedule_json) jsonToScheduleGrid(item.schedule_json);
    }
  } else {
    dialogVisible.title = "新增计划";
    await resetForm();
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      const payload: any = { ...formData };
      if (formData.plan_type === "SCHEDULE") {
        payload.schedule_json = scheduleGridToJson();
      }
      try {
        if (id) {
          await updateRecordPlan(id, payload);
        } else {
          await createRecordPlan(payload);
        }
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch {
        /* noop */
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

function planTypeLabel(type: string) {
  const map: Record<string, string> = {
    CONTINUOUS: "全天录制",
    SCHEDULE: "定时录制",
    EVENT: "事件录制",
    ALARM: "告警录制",
  };
  return map[type] || type;
}

function planTypeTag(type: string): any {
  const map: Record<string, string> = {
    CONTINUOUS: "primary",
    SCHEDULE: "success",
    EVENT: "warning",
    ALARM: "danger",
  };
  return map[type] || "";
}

async function deletePlan(ids: number[]) {
  await deleteRecordPlan(ids);
}

onBeforeMount(async () => {
  try {
    const res = await getCameraList({ page_size: 100 });
    cameraOptions.value = res.data?.data?.items || [];
    // Populate search camera options
    const searchItem: any = searchConfig.formItems.find((i: any) => i.prop === "camera_id");
    if (searchItem) {
      searchItem.options = cameraOptions.value.map((c: any) => ({ label: c.name, value: c.id }));
    }
  } catch {
    cameraOptions.value = [];
  }
  document.addEventListener("mouseup", onDragEnd);
});

onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onDragEnd);
});
</script>

<style scoped>
.schedule-grid-wrapper {
  padding-bottom: 4px;
  overflow-x: auto;
}

.schedule-header-row {
  display: flex;
  gap: 2px;
  margin-bottom: 2px;
}

.schedule-corner {
  flex-shrink: 0;
  width: 44px;
}

.schedule-header-cell {
  flex-shrink: 0;
  width: 24px;
  font-size: 10px;
  line-height: 20px;
  color: var(--el-text-color-placeholder);
  text-align: center;
}

.schedule-row {
  display: flex;
  gap: 2px;
  align-items: center;
  margin-bottom: 2px;
}

.schedule-day-label {
  flex-shrink: 0;
  width: 44px;
  padding-right: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: right;
}

.schedule-cell {
  flex-shrink: 0;
  width: 24px;
  height: 20px;
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 2px;
  transition: all 0.15s;
}

.schedule-cell:hover {
  border-color: var(--el-color-primary);
}

.schedule-cell.active {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.schedule-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.schedule-summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ==================== Dialog Form Sections ==================== */
.form-section {
  padding-bottom: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.form-section:last-child {
  padding-bottom: 0;
  margin-bottom: 0;
  border-bottom: none;
}

.form-section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 14px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.form-section-desc {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-placeholder);
}

.config-field {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.config-unit {
  min-width: 20px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.config-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

.config-help {
  flex-shrink: 0;
  font-size: 14px;
  color: var(--el-text-color-placeholder);
  cursor: help;
}
.config-help:hover {
  color: var(--el-color-primary);
}

/* ==================== Schedule Grid ==================== */
.schedule-grid-wrapper {
  padding-bottom: 4px;
  overflow-x: auto;
}

.schedule-header-row {
  display: flex;
  gap: 2px;
  margin-bottom: 2px;
}

.config-field {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.config-unit {
  min-width: 20px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.config-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.config-help {
  flex-shrink: 0;
  font-size: 14px;
  color: var(--el-text-color-placeholder);
  cursor: help;
}
.config-help:hover {
  color: var(--el-color-primary);
}
</style>
