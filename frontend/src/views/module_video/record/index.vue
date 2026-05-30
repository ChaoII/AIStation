<template>
  <div class="app-container record-page">
    <div class="record-tabs">
      <button class="rtab" :class="{ active: activeTab === 'plan' }" @click="activeTab = 'plan'">
        录像计划
      </button>
      <button
        class="rtab"
        :class="{ active: activeTab === 'log' }"
        @click="
          activeTab = 'log';
          fetchLogs();
        "
      >
        执行日志
      </button>
    </div>

    <!-- ============ 录像计划 ============ -->
    <template v-if="activeTab === 'plan'">
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
              <template #empty><el-empty :image-size="80" description="暂无数据" /></template>
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
                  <el-tag
                    :type="planTypeTag(scope.row.plan_type) as any"
                    size="small"
                    effect="plain"
                  >
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
                width="100"
                align="center"
              >
                <template #default="scope">
                  <div style="display: flex; align-items: center; gap: 4px; justify-content: center">
                    <span
                      class="status-dot"
                      :class="scope.row.is_running ? 'running' : 'stopped'"
                    />
                    <span style="font-size: 12px">{{ scope.row.is_running ? '录制中' : '已停止' }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'enabled')?.show"
                key="enabled"
                label="启用"
                width="60"
                align="center"
              >
                <template #default="scope">
                  <el-switch
                    :model-value="scope.row.status"
                    :loading="scope.row._toggling"
                    size="small"
                    @click.stop
                    @change="(v: boolean) => togglePlan(scope.row, v)"
                  />
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
                min-width="220"
              >
                <template #default="scope">
                  <div style="display: flex; gap: 4px; justify-content: center; flex-wrap: wrap">
                    <el-button
                      v-if="!scope.row.is_running"
                      v-hasPerm="['module_video:record:update']"
                      type="success"
                      size="small"
                      link
                      icon="VideoPlay"
                      :loading="scope.row._executing"
                      @click="executePlan(scope.row)"
                    >
                      执行
                    </el-button>
                    <el-button
                      v-if="scope.row.is_running"
                      v-hasPerm="['module_video:record:update']"
                      type="warning"
                      size="small"
                      link
                      icon="VideoPause"
                      :loading="scope.row._stopping"
                      @click="stopPlan(scope.row)"
                    >
                      停止
                    </el-button>
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
                  </div>
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
              <el-select
                v-model="formData.plan_type"
                style="width: 300px"
                @change="onPlanTypeChange"
              >
                <el-option label="全天录制" value="CONTINUOUS" />
                <el-option label="定时录制" value="SCHEDULE" />
                <el-option label="事件录制" value="EVENT" />
                <el-option label="告警录制" value="ALARM" />
              </el-select>
            </el-form-item>
          </div>
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
            <div class="form-section-title">录制参数</div>
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
                <span class="config-hint">硬盘保留期限</span>
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
    </template>

    <!-- ============ 执行日志 ============ -->
    <template v-if="activeTab === 'log'">
      <PageSearch
        ref="logSearchRef"
        :search-config="logSearchConfig"
        @query-click="fetchLogs"
        @reset-click="resetLogFilter"
      />
      <PageContent ref="logContentRef" :content-config="logContentConfig">
        <template #table="{ data, loading, tableRef, pagination }">
          <div class="data-table__content">
            <el-table
              :ref="tableRef as any"
              v-loading="loading"
              :data="data"
              height="100%"
              border
              stripe
            >
              <template #empty><el-empty :image-size="80" description="暂无日志" /></template>
              <el-table-column type="index" label="序号" width="60" align="center" />
              <el-table-column label="摄像机" min-width="140">
                <template #default="{ row }">{{ row.camera?.name || `#${row.camera_id}` }}</template>
              </el-table-column>
              <el-table-column prop="stream_id" label="流ID" min-width="160">
                <template #default="{ row }">
                  <span class="mono">{{ row.stream_id }}</span>
                </template>
              </el-table-column>
              <el-table-column label="触发方式" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="triggerTagType(row.trigger_type)" size="small" effect="plain">
                    {{ triggerLabel(row.trigger_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="开始时间" prop="start_time" width="170" sortable>
                <template #default="{ row }">
                  <span class="mono">{{ row.start_time }}</span>
                </template>
              </el-table-column>
              <el-table-column label="结束时间" prop="end_time" width="170" sortable>
                <template #default="{ row }">
                  <span class="mono">{{ row.end_time || "-" }}</span>
                </template>
              </el-table-column>
              <el-table-column label="时长" width="90" align="center">
                <template #default="{ row }">{{ row.duration ? `${row.duration}s` : "-" }}</template>
              </el-table-column>
              <el-table-column label="文件数" width="80" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="row.file_count > 0"
                    type="primary"
                    size="small"
                    link
                    @click="showLogFiles(row)"
                  >
                    {{ row.file_count }}个
                  </el-button>
                  <span v-else class="log-none">-</span>
                </template>
              </el-table-column>
              <el-table-column label="错误信息" min-width="160">
                <template #default="{ row }">
                  <span v-if="row.error_msg" class="log-error">{{ row.error_msg }}</span>
                  <span v-else class="log-none">-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <div class="data-table__pagination">
            <el-pagination
              v-model:current-page="logPage.page_no"
              v-model:page-size="logPage.page_size"
              :page-sizes="[10, 20, 30, 50]"
              :total="logTotal"
              layout="total, sizes, prev, pager, next, jumper"
              background
              small
              @current-change="fetchLogs"
              @size-change="fetchLogs"
            />
          </div>
        </template>
      </PageContent>
    </template>

    <!-- 录制文件预览对话框 -->
    <el-dialog v-model="filePreviewVisible" title="录制文件" width="660px" append-to-body destroy-on-close>
      <el-table :data="filePreviewItems" border stripe v-loading="filePreviewLoading" max-height="400">
        <template #empty><el-empty :image-size="60" description="暂无文件" /></template>
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column label="文件大小" width="100" align="center">
          <template #default="{ row }">{{ (row.file_size / 1048576).toFixed(1) }}MB</template>
        </el-table-column>
        <el-table-column label="开始时间" prop="start_time" width="170" />
        <el-table-column label="时长" width="80" align="center">
          <template #default="{ row }">{{ row.duration ? `${row.duration}s` : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button type="primary" size="small" link @click="playRecordFile(row)">播放</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import {
  getRecordPlanList,
  createRecordPlan,
  updateRecordPlan,
  deleteRecordPlan,
  getRecordLogList,
  getRecordFileList,
  toggleRecordPlan,
  executeRecordPlan,
  stopRecordPlan,
} from "@/api/module_video/record";
import { getCameraList } from "@/api/module_video/camera";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

const activeTab = ref("plan");

// ===== Plan CRUD =====
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
  { prop: "enabled", label: "启用", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<any>>({
  permPrefix: "module_video:record",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params: any) => {
    const res = await getRecordPlanList(params);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids: string) => {
    await deleteRecordPlan(
      ids
        .split(",")
        .map(Number)
        .filter((n) => !isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function togglePlan(row: any, val: boolean) {
  row._toggling = true;
  try {
    await toggleRecordPlan(row.id);
    row.status = val;
  } catch {}
  row._toggling = false;
}

async function executePlan(row: any) {
  row._executing = true;
  try {
    const res = await executeRecordPlan(row.id);
    row.is_running = true;
    ElMessage.success("计划已触发执行");
  } catch {}
  row._executing = false;
}

async function stopPlan(row: any) {
  row._stopping = true;
  try {
    await stopRecordPlan(row.id);
    row.is_running = false;
    ElMessage.success("计划已停止");
  } catch {}
  row._stopping = false;
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

const initialFormData = { ...formData };

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
      for (let h = slot.start; h < slot.end && h < 24; h++) scheduleGrid.value[slot.day][h] = true;
    }
  }
}

function onPlanTypeChange() {
  if (formData.plan_type !== "SCHEDULE")
    scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
}

function scheduleSummary(json: any): string {
  if (!json?.slots?.length) return "未配置";
  const total = json.slots.reduce((s: number, x: any) => s + (x.end - x.start), 0);
  return `每周 ${total} 小时`;
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
    if (!valid) return;
    submitLoading.value = true;
    const id = formData.id;
    const payload: any = { ...formData };
    if (formData.plan_type === "SCHEDULE") payload.schedule_json = scheduleGridToJson();
    try {
      if (id) await updateRecordPlan(id, payload);
      else await createPlan(payload);
      dialogVisible.visible = false;
      await resetForm();
      refreshList();
    } catch {}
    submitLoading.value = false;
  });
}

async function createPlan(data: any) {
  await createRecordPlan(data);
}
async function deletePlan(ids: number[]) {
  await deleteRecordPlan(ids);
}
function planTypeLabel(type: string) {
  return (
    (
      {
        CONTINUOUS: "全天录制",
        SCHEDULE: "定时录制",
        EVENT: "事件录制",
        ALARM: "告警录制",
      } as Record<string, string>
    )[type] || type
  );
}
function planTypeTag(type: string): any {
  return (
    (
      { CONTINUOUS: "primary", SCHEDULE: "success", EVENT: "warning", ALARM: "danger" } as Record<
        string,
        string
      >
    )[type] || ""
  );
}

// ===== Execution Log =====
const logSearchRef = ref();
const logContentRef = ref();
const logTotal = ref(0);
const logPage = reactive({ page_no: 1, page_size: 20 });

const logSearchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:record",
  colon: true,
  isExpandable: true,
  showNumber: 3,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "camera_id",
      label: "摄像机",
      type: "select",
      options: [],
      attrs: { placeholder: "请选择摄像机", clearable: true, filterable: true, style: { width: "180px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "录制中", value: "RECORDING" },
        { label: "已完成", value: "COMPLETED" },
        { label: "失败", value: "FAILED" },
        { label: "已停止", value: "STOPPED" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "140px" } },
    },
    {
      prop: "trigger_type",
      label: "触发方式",
      type: "select",
      options: [
        { label: "定时", value: "SCHEDULED" },
        { label: "手动", value: "MANUAL" },
        { label: "告警", value: "ALARM" },
      ],
      attrs: { placeholder: "请选择触发方式", clearable: true, style: { width: "140px" } },
    },
    {
      prop: "start_time",
      label: "时间范围",
      type: "daterange",
      attrs: {
        rangeSeparator: "至", startPlaceholder: "开始日期", endPlaceholder: "结束日期",
        valueFormat: "YYYY-MM-DD HH:mm:ss", style: { width: "260px" },
      },
    },
  ],
});

const logContentConfig = reactive<IContentConfig<any>>({
  permPrefix: "module_video:record",
  pk: "id",
  cols: [],
  hideColumnFilter: true,
  toolbar: [],
  defaultToolbar: ["refresh"],
  pagination: { pageSize: 20, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const p: any = { ...params };
    const sf = logSearchRef.value?.searchData;
    if (sf?.camera_id) p.camera_id = sf.camera_id;
    if (sf?.status) p.status = sf.status;
    if (sf?.trigger_type) p.trigger_type = sf.trigger_type;
    if (sf?.start_time?.length === 2) {
      p.start_time = sf.start_time[0];
      p.end_time = sf.start_time[1];
    }
    const res = await getRecordLogList(p);
    logTotal.value = res.data?.data?.total || 0;
    return { total: res.data?.data?.total || 0, list: res.data?.data?.items || [] };
  },
  deleteAction: async () => {},
});

function resetLogFilter() {
  logSearchRef.value?.resetSearch();
}

function triggerLabel(t: string) {
  return ({ SCHEDULED: "定时", MANUAL: "手动", ALARM: "告警" } as Record<string, string>)[t] || t;
}
function triggerTagType(t: string): any {
  return ({ SCHEDULED: "success", MANUAL: "primary", ALARM: "danger" } as Record<string, string>)[t] || "";
}
function statusLabel(s: string) {
  return ({ RECORDING: "录制中", COMPLETED: "已完成", FAILED: "失败", STOPPED: "已停止" } as Record<string, string>)[s] || s;
}
function statusTagType(s: string): any {
  return ({ RECORDING: "warning", COMPLETED: "success", FAILED: "danger", STOPPED: "info" } as Record<string, string>)[s] || "";
}

async function fetchLogs() {
  logContentRef.value?.handleQuery();
}

// File preview
const filePreviewVisible = ref(false);
const filePreviewLoading = ref(false);
const filePreviewItems = ref<any[]>([]);

async function showLogFiles(logRow: any) {
  filePreviewVisible.value = true;
  filePreviewLoading.value = true;
  filePreviewItems.value = [];
  try {
    const res = await getRecordFileList({ camera_id: logRow.camera_id, page_size: 100 });
    filePreviewItems.value = res.data?.data?.items || [];
  } catch {}
  filePreviewLoading.value = false;
}

function playRecordFile(file: any) {
  const router = useRouter();
  router.push({ path: "/video/playback", query: { camera_id: file.camera_id } });
}

onBeforeMount(async () => {
  try {
    const res = await getCameraList({ page_size: 100 });
    cameraOptions.value = res.data?.data?.items || [];
    const opts = cameraOptions.value.map((c: any) => ({ label: c.name, value: c.id }));
    const si: any = searchConfig.formItems.find((i: any) => i.prop === "camera_id");
    if (si) si.options = opts;
    const li: any = logSearchConfig.formItems.find((i: any) => i.prop === "camera_id");
    if (li) li.options = opts;
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
.record-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.record-tabs {
  display: flex;
  gap: 0;
  flex-shrink: 0;
  border-bottom: 1px solid var(--el-border-color-light);
}
.rtab {
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
  margin-bottom: -1px;
}
.rtab:hover {
  color: var(--el-text-color-primary);
}
.rtab.active {
  color: var(--el-color-primary);
  border-bottom-color: var(--el-color-primary);
}

/* ===== Log Tab ===== */
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.running {
  background: var(--el-color-success);
  box-shadow: 0 0 6px var(--el-color-success);
}
.status-dot.stopped {
  background: var(--el-text-color-placeholder);
}
.mono {
  font-family: "SF Mono", "Cascadia Code", monospace;
  font-size: 12px;
}
.log-error {
  color: var(--el-color-danger);
  font-size: 12px;
}
.log-none {
  color: var(--el-text-color-placeholder);
}

/* ===== Plan form ===== */
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
</style>
