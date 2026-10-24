<template>
  <div class="app-container record-page">
    <div class="record-tabs">
      <button class="rtab" :class="{ active: activeTab === 'plan' }" @click="activeTab = 'plan'">
        {{ t("video.record.plan") }}
      </button>
      <button
        class="rtab"
        :class="{ active: activeTab === 'log' }"
        @click="
          activeTab = 'log';
          fetchLogs();
        "
      >
        {{ t("video.record.log") }}
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
              <template #empty>
                <el-empty :image-size="80" :description="t('video.common.noData')" />
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
                :label="t('video.common.sequence')"
                min-width="60"
                align="center"
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'camera')?.show"
                key="camera"
                :label="t('video.record.camera')"
                min-width="160"
              >
                <template #default="scope">
                  {{ scope.row.camera?.name || `#${scope.row.camera_id}` }}
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'plan_type')?.show"
                key="plan_type"
                :label="t('video.record.planType')"
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
                :label="t('video.record.recordPeriod')"
                min-width="200"
              >
                <template #default="scope">
                  <span v-if="scope.row.plan_type === 'CONTINUOUS'" class="schedule-summary">
                    {{ t("video.record.allDay") }}
                  </span>
                  <span
                    v-else-if="scope.row.plan_type === 'SCHEDULE' && scope.row.schedule_json"
                    class="schedule-summary"
                  >
                    {{ scheduleSummary(scope.row.schedule_json) }}
                  </span>
                  <span v-else-if="scope.row.plan_type === 'EVENT'" class="schedule-summary">
                    {{ t("video.record.eventTrigger") }}
                  </span>
                  <span v-else-if="scope.row.plan_type === 'ALARM'" class="schedule-summary">
                    {{ t("video.record.alarmTrigger") }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'pre_record_sec')?.show"
                key="pre_record_sec"
                :label="t('video.record.preRecord')"
                width="70"
                align="center"
              >
                <template #default="scope">{{ scope.row.pre_record_sec }}s</template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'post_record_sec')?.show"
                key="post_record_sec"
                :label="t('video.record.postRecord')"
                width="70"
                align="center"
              >
                <template #default="scope">{{ scope.row.post_record_sec }}s</template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'storage_days')?.show"
                key="storage_days"
                :label="t('video.record.storage')"
                width="70"
                align="center"
              >
                <template #default="scope">
                  {{ scope.row.storage_days }}{{ t("video.record.days") }}
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'stream_type')?.show"
                key="stream_type"
                :label="t('video.record.streamType')"
                width="70"
                align="center"
              >
                <template #default="scope">
                  <el-tag size="small">
                    {{
                      scope.row.stream_type === "MAIN"
                        ? t("video.record.main")
                        : t("video.record.sub")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'status')?.show"
                key="status"
                :label="t('video.common.status')"
                width="100"
                align="center"
              >
                <template #default="scope">
                  <div
                    style="display: flex; align-items: center; gap: 4px; justify-content: center"
                  >
                    <span
                      class="status-dot"
                      :class="scope.row.is_running ? 'running' : 'stopped'"
                    />
                    <span class="record-status-text">
                      {{
                        scope.row.is_running
                          ? t("video.record.recording")
                          : t("video.common.stopped")
                      }}
                    </span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'enabled')?.show"
                key="enabled"
                :label="t('video.common.enabled')"
                width="60"
                align="center"
              >
                <template #default="scope">
                  <el-switch
                    :model-value="scope.row.status"
                    :loading="scope.row._toggling"
                    size="small"
                    @click.stop
                    @change="(v: string | number | boolean) => togglePlan(scope.row, v === true)"
                  />
                </template>
              </el-table-column>
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
                key="created_time"
                :label="t('video.common.createdTime')"
                prop="created_time"
                min-width="170"
                sortable
              />
              <el-table-column
                v-if="contentCols.find((col) => col.prop === 'operation')?.show"
                fixed="right"
                :label="t('video.common.operation')"
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
                      {{ t("video.record.execute") }}
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
                      {{ t("video.camera.stop") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_video:record:update']"
                      type="primary"
                      size="small"
                      link
                      icon="edit"
                      @click="handleOpenDialog('update', scope.row.id)"
                    >
                      {{ t("video.common.edit") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_video:record:delete']"
                      type="danger"
                      size="small"
                      link
                      icon="delete"
                      @click="handleRowDelete(scope.row.id)"
                    >
                      {{ t("video.common.delete") }}
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
            <div class="form-section-title">{{ t("video.record.basicInfo") }}</div>
            <el-form-item :label="t('video.record.camera')" prop="camera_id">
              <el-select
                v-model="formData.camera_id"
                filterable
                :placeholder="t('video.record.selectCamera')"
                style="width: 300px"
                @visible-change="(v: boolean) => v && ensureCameraOptions()"
              >
                <el-option v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('video.record.planType')" prop="plan_type">
              <el-select
                v-model="formData.plan_type"
                style="width: 300px"
                @change="onPlanTypeChange"
              >
                <el-option :label="t('video.record.allDayRecord')" value="CONTINUOUS" />
                <el-option :label="t('video.record.scheduledRecord')" value="SCHEDULE" />
                <el-option :label="t('video.record.eventRecord')" value="EVENT" />
                <el-option :label="t('video.record.alarmRecord')" value="ALARM" />
              </el-select>
            </el-form-item>
          </div>
          <div v-if="formData.plan_type === 'SCHEDULE'" class="form-section">
            <div class="form-section-title">
              {{ t("video.record.recordPeriod") }}
              <span class="form-section-desc">{{ t("video.record.recordPeriodHint") }}</span>
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
              <el-button size="small" @click="fillSchedule(true)">
                {{ t("video.record.selectAll") }}
              </el-button>
              <el-button size="small" @click="fillSchedule(false)">
                {{ t("video.record.clear") }}
              </el-button>
              <el-button size="small" @click="fillWorkHours">
                {{ t("video.record.workday0818") }}
              </el-button>
            </div>
          </div>
          <div class="form-section">
            <div class="form-section-title">{{ t("video.record.recordParams") }}</div>
            <template v-if="formData.plan_type === 'EVENT' || formData.plan_type === 'ALARM'">
              <el-form-item :label="t('video.record.preEventRecord')" prop="pre_record_sec">
                <div class="config-field">
                  <el-input-number
                    v-model="formData.pre_record_sec"
                    :min="0"
                    :max="30"
                    :step="1"
                    controls-position="right"
                    style="width: 130px"
                  />
                  <span class="config-unit">{{ t("video.record.seconds") }}</span>
                  <span class="config-hint">{{ t("video.record.preEventHint") }}</span>
                </div>
              </el-form-item>
              <el-form-item :label="t('video.record.postEventRecord')" prop="post_record_sec">
                <div class="config-field">
                  <el-input-number
                    v-model="formData.post_record_sec"
                    :min="0"
                    :max="30"
                    :step="1"
                    controls-position="right"
                    style="width: 130px"
                  />
                  <span class="config-unit">{{ t("video.record.seconds") }}</span>
                  <span class="config-hint">{{ t("video.record.postEventHint") }}</span>
                </div>
              </el-form-item>
            </template>
            <el-form-item :label="t('video.record.retention')" prop="storage_days">
              <div class="config-field">
                <el-input-number
                  v-model="formData.storage_days"
                  :min="1"
                  :max="365"
                  :step="1"
                  controls-position="right"
                  style="width: 130px"
                />
                <span class="config-unit">{{ t("video.record.days") }}</span>
                <span class="config-hint">{{ t("video.record.diskHint") }}</span>
              </div>
            </el-form-item>
          </div>
          <div class="form-section">
            <div class="form-section-title">{{ t("video.record.otherSettings") }}</div>
            <el-form-item :label="t('video.record.streamType')" prop="stream_type">
              <el-radio-group v-model="formData.stream_type">
                <el-radio value="MAIN">{{ t("video.record.mainStreamHd") }}</el-radio>
                <el-radio value="SUB">{{ t("video.record.subStreamSmooth") }}</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item :label="t('video.common.status')" prop="status">
              <el-switch v-model="formData.status" />
            </el-form-item>
            <el-form-item :label="t('video.cameraGroup.remark')" prop="description">
              <el-input
                v-model="formData.description"
                type="textarea"
                :rows="2"
                :placeholder="t('video.common.optionalRemark')"
              />
            </el-form-item>
          </div>
        </el-form>
        <template #footer>
          <el-button @click="handleCloseDialog">{{ t("video.common.cancel") }}</el-button>
          <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
            {{ t("video.common.save") }}
          </el-button>
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
              <template #empty>
                <el-empty :image-size="80" :description="t('video.record.noLog')" />
              </template>
              <el-table-column
                type="index"
                :label="t('video.common.sequence')"
                width="60"
                align="center"
              />
              <el-table-column :label="t('video.record.camera')" min-width="140">
                <template #default="{ row }">
                  {{ row.camera?.name || `#${row.camera_id}` }}
                </template>
              </el-table-column>
              <el-table-column prop="stream_id" :label="t('video.record.streamId')" min-width="160">
                <template #default="{ row }">
                  <span class="mono">{{ row.stream_id }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('video.record.triggerType')" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="triggerTagType(row.trigger_type)" size="small" effect="plain">
                    {{ triggerLabel(row.trigger_type) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="t('video.common.status')" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" size="small">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('video.record.startTime')"
                prop="start_time"
                width="170"
                sortable
              >
                <template #default="{ row }">
                  <span class="mono">{{ row.start_time }}</span>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('video.record.endTime')"
                prop="end_time"
                width="170"
                sortable
              >
                <template #default="{ row }">
                  <span class="mono">{{ row.end_time || "-" }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('video.record.duration')" width="90" align="center">
                <template #default="{ row }">
                  {{ row.duration ? `${row.duration}s` : "-" }}
                </template>
              </el-table-column>
              <el-table-column :label="t('video.record.fileCount')" width="80" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="row.file_count > 0"
                    type="primary"
                    size="small"
                    link
                    @click="showLogFiles(row)"
                  >
                    {{ row.file_count }}{{ t("video.record.files") }}
                  </el-button>
                  <span v-else class="log-none">-</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('video.record.errorInfo')" min-width="160">
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
    <el-dialog
      v-model="filePreviewVisible"
      :title="t('video.record.recordFiles')"
      width="660px"
      append-to-body
      destroy-on-close
    >
      <el-table
        v-loading="filePreviewLoading"
        :data="filePreviewItems"
        border
        stripe
        max-height="400"
      >
        <template #empty>
          <el-empty :image-size="60" :description="t('video.record.noFiles')" />
        </template>
        <el-table-column
          type="index"
          :label="t('video.common.sequence')"
          width="60"
          align="center"
        />
        <el-table-column :label="t('video.record.fileSize')" width="100" align="center">
          <template #default="{ row }">{{ (row.file_size / 1048576).toFixed(1) }}MB</template>
        </el-table-column>
        <el-table-column :label="t('video.record.startTime')" prop="start_time" width="170" />
        <el-table-column :label="t('video.record.duration')" width="80" align="center">
          <template #default="{ row }">{{ row.duration ? `${row.duration}s` : "-" }}</template>
        </el-table-column>
        <el-table-column :label="t('video.common.operation')" width="120" align="center">
          <template #default="{ row }">
            <el-button
              icon="VideoPlay"
              type="primary"
              size="small"
              link
              @click="playRecordFile(row)"
            >
              {{ t("video.record.play") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
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
import { cachedOptions } from "@/composables/useOptions";

const activeTab = ref("plan");

const { t } = useI18n();

// ===== Plan CRUD =====
const weekDays = [
  t("video.common.monday"),
  t("video.common.tuesday"),
  t("video.common.wednesday"),
  t("video.common.thursday"),
  t("video.common.friday"),
  t("video.common.saturday"),
  t("video.common.sunday"),
];
const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const router = useRouter();

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
      label: t("video.record.camera"),
      type: "select",
      options: [],
      attrs: {
        placeholder: t("video.record.selectCamera"),
        clearable: true,
        filterable: true,
        style: { width: "200px" },
        onVisibleChange: (v: boolean) => {
          if (v) ensureCameraOptions();
        },
      },
    },
    {
      prop: "plan_type",
      label: t("video.record.planType"),
      type: "select",
      options: [
        { label: t("video.record.allDayRecord"), value: "CONTINUOUS" },
        { label: t("video.record.scheduledRecord"), value: "SCHEDULE" },
        { label: t("video.record.eventRecord"), value: "EVENT" },
        { label: t("video.record.alarmRecord"), value: "ALARM" },
      ],
      attrs: {
        placeholder: t("video.record.select"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "camera", label: t("video.record.camera"), show: true },
  { prop: "plan_type", label: t("video.record.planType"), show: true },
  { prop: "schedule", label: t("video.record.recordPeriod"), show: true },
  { prop: "pre_record_sec", label: t("video.record.preRecord"), show: true },
  { prop: "post_record_sec", label: t("video.record.postRecord"), show: true },
  { prop: "storage_days", label: t("video.record.storage"), show: true },
  { prop: "stream_type", label: t("video.record.streamType"), show: true },
  { prop: "status", label: t("video.common.status"), show: true },
  { prop: "enabled", label: t("video.common.enabled"), show: true },
  { prop: "created_time", label: t("video.common.createdTime"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
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
  deleteConfirm: {
    title: t("video.common.warning"),
    message: t("video.common.deleteConfirmMsg"),
    type: "warning",
  },
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
    await executeRecordPlan(row.id);
    row.is_running = true;
  } catch {}
  row._executing = false;
}

async function stopPlan(row: any) {
  row._stopping = true;
  try {
    await stopRecordPlan(row.id);
    ElMessage.success(t("video.common.stopped"));
    row.is_running = false;
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
  if (!json?.slots?.length) return t("video.common.notConfigured");
  const total = json.slots.reduce((s: number, x: any) => s + (x.end - x.start), 0);
  return t("video.record.weeklyHours", { total });
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
  ensureCameraOptions();
  if (id && type === "update") {
    dialogVisible.title = t("video.record.editPlan");
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
    dialogVisible.title = t("video.record.addPlan");
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
      ElMessage.success(t("video.common.saveSuccess"));
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
        CONTINUOUS: t("video.record.allDayRecord"),
        SCHEDULE: t("video.record.scheduledRecord"),
        EVENT: t("video.record.eventRecord"),
        ALARM: t("video.record.alarmRecord"),
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
      label: t("video.record.camera"),
      type: "select",
      options: [],
      attrs: {
        placeholder: t("video.record.selectCamera"),
        clearable: true,
        filterable: true,
        style: { width: "180px" },
        onVisibleChange: (v: boolean) => {
          if (v) ensureCameraOptions();
        },
      },
    },
    {
      prop: "status",
      label: t("video.common.status"),
      type: "select",
      options: [
        { label: t("video.record.recording"), value: "RECORDING" },
        { label: t("video.record.completed"), value: "COMPLETED" },
        { label: t("video.record.failed"), value: "FAILED" },
        { label: t("video.common.stopped"), value: "STOPPED" },
      ],
      attrs: {
        placeholder: t("video.record.selectStatus"),
        clearable: true,
        style: { width: "140px" },
      },
    },
    {
      prop: "trigger_type",
      label: t("video.record.triggerType"),
      type: "select",
      options: [
        { label: t("video.record.scheduled"), value: "SCHEDULED" },
        { label: t("video.record.manual"), value: "MANUAL" },
        { label: t("video.record.alarm"), value: "ALARM" },
      ],
      attrs: {
        placeholder: t("video.record.selectTriggerType"),
        clearable: true,
        style: { width: "140px" },
      },
    },
    {
      prop: "start_time",
      label: t("video.record.timeRange"),
      type: "daterange",
      attrs: {
        rangeSeparator: t("video.record.to"),
        startPlaceholder: t("video.record.startDate"),
        endPlaceholder: t("video.record.endDate"),
        valueFormat: "YYYY-MM-DD HH:mm:ss",
        style: { width: "260px" },
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
    // PageSearch 暴露 getQueryParams（非 searchData）
    const sf = logSearchRef.value?.getQueryParams?.() || {};
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
  // PageContent 暴露 handleRefresh（非 PageSearch 的 resetSearch）
  logContentRef.value?.handleRefresh();
}

function triggerLabel(tt: string) {
  return (
    (
      {
        SCHEDULED: t("video.record.scheduled"),
        MANUAL: t("video.record.manual"),
        ALARM: t("video.record.alarm"),
      } as Record<string, string>
    )[tt] || tt
  );
}
function triggerTagType(t: string): any {
  return (
    ({ SCHEDULED: "success", MANUAL: "primary", ALARM: "danger" } as Record<string, string>)[t] ||
    ""
  );
}
function statusLabel(s: string) {
  return (
    (
      {
        RECORDING: t("video.record.recording"),
        COMPLETED: t("video.record.completed"),
        FAILED: t("video.record.failed"),
        STOPPED: t("video.common.stopped"),
      } as Record<string, string>
    )[s] || s
  );
}
function statusTagType(s: string): any {
  return (
    (
      { RECORDING: "warning", COMPLETED: "success", FAILED: "danger", STOPPED: "info" } as Record<
        string,
        string
      >
    )[s] || ""
  );
}

async function fetchLogs(payload?: any) {
  // PageContent 暴露 fetchPageData（非 handleQuery）；传入搜索 payload
  logContentRef.value?.fetchPageData(payload || {});
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
  router.push({ path: "/video/playback", query: { camera_id: file.camera_id } });
}

// 摄像机下拉：懒加载 + 缓存
async function ensureCameraOptions() {
  if (cameraOptions.value.length) return;
  try {
    cameraOptions.value = await cachedOptions(
      "video:cameras",
      async () => (await getCameraList({ page_size: 100 })).data?.data?.items || []
    );
    const opts = cameraOptions.value.map((c: any) => ({ label: c.name, value: c.id }));
    const si: any = (searchConfig.formItems || []).find((i: any) => i.prop === "camera_id");
    if (si) si.options = opts;
    const li: any = (logSearchConfig.formItems || []).find((i: any) => i.prop === "camera_id");
    if (li) li.options = opts;
  } catch {
    cameraOptions.value = [];
  }
}

onBeforeMount(async () => {
  document.addEventListener("mouseup", onDragEnd);
});

onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onDragEnd);
});
</script>

<style scoped>
/* 录制状态文字（替代内联 style） */
.record-status-text {
  font-size: 12px;
}
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
  font-size: var(--el-font-size-small);
  color: var(--el-text-color-secondary);
}
.config-hint {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}
</style>
