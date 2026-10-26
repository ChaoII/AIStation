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
          :perm-create="['module_video:event:create']"
          :perm-delete="['module_video:event:delete']"
          :perm-patch="['module_video:event:patch']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange, pagination }">
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
              fixed
              :label="t('video.common.sequence')"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              :label="t('video.event.linkageName')"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'trigger_event')?.show"
              key="trigger_event"
              :label="t('video.event.triggerEvent')"
              prop="trigger_event"
              width="130"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="eventTag(scope.row.trigger_event)" size="small" effect="plain">
                  {{ eventLabel(scope.row.trigger_event) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'action_type')?.show"
              key="action_type"
              :label="t('video.event.actionType')"
              prop="action_type"
              width="130"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="actionTag(scope.row.action_type)" size="small" effect="plain">
                  {{ actionLabel(scope.row.action_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'trigger_camera_ids')?.show"
              key="trigger_camera_ids"
              :label="t('video.event.linkCamera')"
              prop="trigger_camera_ids"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="scope">
                <span>
                  {{
                    t("video.event.cameraCount", {
                      count: scope.row.trigger_camera_ids?.length || 0,
                    })
                  }}
                </span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('video.common.status')"
              prop="status"
              width="80"
              align="center"
            >
              <template #default="scope">
                <el-switch v-model="scope.row.status" disabled />
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
              min-width="160"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_video:event:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("video.common.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_video:event:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleRowDelete(scope.row.id)"
                >
                  {{ t("video.common.delete") }}
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
      width="640px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px" size="default">
        <el-form-item :label="t('video.event.linkageName')" prop="name">
          <el-input v-model="formData.name" :placeholder="t('video.event.nameExample')" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('video.event.triggerEvent')" prop="trigger_event">
              <el-select v-model="formData.trigger_event" style="width: 100%">
                <el-option :label="t('video.event.alarmTrigger')" value="ALARM" />
                <el-option :label="t('video.event.motionDetect')" value="MOTION" />
                <el-option :label="t('video.event.deviceOffline')" value="OFFLINE" />
                <el-option :label="t('video.event.deviceOnline')" value="ONLINE" />
                <el-option :label="t('video.event.videoLost')" value="VIDEO_LOST" />
                <el-option :label="t('video.event.scheduleTrigger')" value="SCHEDULE" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('video.event.actionType')" prop="action_type">
              <el-select v-model="formData.action_type" style="width: 100%">
                <el-option :label="t('video.event.startRecord')" value="RECORD" />
                <el-option :label="t('video.event.sendAlarm')" value="ALERT" />
                <el-option :label="t('video.event.ptzControl')" value="PTZ" />
                <el-option :label="t('video.event.msgPush')" value="PUSH" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('video.event.linkCamera')" prop="trigger_camera_ids">
          <el-select
            v-model="formData.trigger_camera_ids"
            multiple
            filterable
            style="width: 100%"
            :placeholder="t('video.event.selectCameraHint')"
            @visible-change="(v: boolean) => v && ensureCameras()"
          >
            <el-option v-for="c in cameras" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('video.event.actionParams')" prop="action_params">
          <div class="action-params">
            <template v-if="formData.action_type === 'RECORD'">
              <div class="action-params__row">
                <span class="action-params__label">{{ t("video.event.recordRetention") }}</span>
                <el-input-number
                  v-model="formData.action_params.storage_days"
                  :min="1"
                  :max="365"
                />
              </div>
            </template>
            <template v-else-if="formData.action_type === 'PTZ'">
              <div class="action-params__row">
                <span class="action-params__label">{{ t("video.event.presetId") }}</span>
                <el-input-number v-model="formData.action_params.preset_id" :min="0" />
              </div>
            </template>
            <template v-else-if="formData.action_type === 'ALERT'">
              <div class="action-params__row">
                <span class="action-params__label">{{ t("video.event.alarmLevel") }}</span>
                <el-select v-model="formData.action_params.level" style="width: 140px">
                  <el-option :label="t('video.event.middle')" value="middle" />
                  <el-option :label="t('video.event.high')" value="high" />
                  <el-option :label="t('video.event.critical')" value="critical" />
                </el-select>
              </div>
            </template>
            <template v-else-if="formData.action_type === 'PUSH'">
              <div class="action-params__row">
                <span class="action-params__label">{{ t("video.event.pushChannel") }}</span>
                <el-input
                  v-model="formData.action_params.channel"
                  :placeholder="t('video.event.channelExample')"
                  style="width: 200px"
                />
              </div>
            </template>
            <el-collapse class="action-params__advanced">
              <el-collapse-item :title="t('video.event.advancedJson')">
                <el-input
                  v-model="actionParamsText"
                  type="textarea"
                  :rows="2"
                  :placeholder="t('video.event.advancedJsonPlaceholder')"
                />
              </el-collapse-item>
            </el-collapse>
          </div>
        </el-form-item>
        <el-form-item :label="t('video.common.status')" prop="status">
          <el-switch v-model="formData.status" />
        </el-form-item>
        <el-form-item :label="t('video.common.description')" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            :placeholder="t('video.common.optionalRemark')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">{{ t("video.common.cancel") }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ t("video.common.save") }}
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { getCameraList } from "@/api/module_video/camera";
import { getEventList, createEvent, updateEvent, deleteEvent } from "@/api/module_video/event";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import { cachedOptions } from "@/composables/useOptions";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const { t } = useI18n();

const submitLoading = ref(false);
const dataFormRef = ref();
const cameras = ref<any[]>([]);

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:event",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("video.event.linkageName"),
      type: "input",
      attrs: { placeholder: t("video.event.enterLinkageName"), clearable: true },
    },
    {
      prop: "trigger_event",
      label: t("video.event.triggerEvent"),
      type: "select",
      options: [
        { label: t("video.event.alarmTrigger"), value: "ALARM" },
        { label: t("video.event.motionDetect"), value: "MOTION" },
        { label: t("video.event.deviceOffline"), value: "OFFLINE" },
        { label: t("video.event.deviceOnline"), value: "ONLINE" },
        { label: t("video.event.videoLost"), value: "VIDEO_LOST" },
        { label: t("video.event.scheduleTrigger"), value: "SCHEDULE" },
      ],
      attrs: {
        placeholder: t("video.event.selectTriggerEvent"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "action_type",
      label: t("video.event.actionType"),
      type: "select",
      options: [
        { label: t("video.event.startRecord"), value: "RECORD" },
        { label: t("video.event.sendAlarm"), value: "ALERT" },
        { label: t("video.event.ptzControl"), value: "PTZ" },
        { label: t("video.event.msgPush"), value: "PUSH" },
      ],
      attrs: {
        placeholder: t("video.event.selectActionType"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "name", label: t("video.event.linkageName"), show: true },
  { prop: "trigger_event", label: t("video.event.triggerEvent"), show: true },
  { prop: "action_type", label: t("video.event.actionType"), show: true },
  { prop: "trigger_camera_ids", label: t("video.event.linkCamera"), show: true },
  { prop: "status", label: t("video.common.status"), show: true },
  { prop: "created_time", label: t("video.common.createdTime"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:event",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getEventList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteEvent(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
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

async function ensureCameras() {
  if (cameras.value.length) return;
  try {
    cameras.value = await cachedOptions(
      "video:cameras",
      async () => (await getCameraList({ page_size: 100 })).data?.data?.items || []
    );
  } catch {
    //
  }
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  trigger_event: "ALARM",
  action_type: "RECORD",
  trigger_camera_ids: [] as number[],
  action_params: {} as Record<string, any>,
  status: true,
  description: undefined as string | undefined,
});

const actionParamsText = ref("");

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  trigger_event: "ALARM" as const,
  action_type: "RECORD" as const,
  trigger_camera_ids: [] as number[],
  action_params: {} as Record<string, any>,
  status: true,
  description: undefined as string | undefined,
};

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  formData.action_params = {};
  actionParamsText.value = "";
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  ensureCameras();
  if (id && type === "update") {
    dialogVisible.title = t("video.event.editLinkage");
    const res = await getEventList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, item);
      formData.action_params = item.action_params || {};
      actionParamsText.value = item.action_params
        ? JSON.stringify(item.action_params, null, 2)
        : "";
    }
  } else {
    dialogVisible.title = t("video.event.newLinkage");
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    if (actionParamsText.value && actionParamsText.value.trim()) {
      try {
        formData.action_params = JSON.parse(actionParamsText.value);
      } catch {
        ElMessage.warning(t("video.event.jsonFormatError"));
      }
    }
    if (id) {
      await updateEvent(id, formData);
    } else {
      await createEvent(formData);
    }
    ElMessage.success(t("video.common.saveSuccess"));
    dialogVisible.visible = false;
    await resetForm();
    refreshList();
  } catch {
    //
  } finally {
    submitLoading.value = false;
  }
}

function eventLabel(type: string) {
  const map: Record<string, string> = {
    ALARM: t("video.event.alarmTrigger"),
    MOTION: t("video.event.motionDetect"),
    OFFLINE: t("video.event.deviceOffline"),
    ONLINE: t("video.event.deviceOnline"),
    VIDEO_LOST: t("video.event.videoLost"),
    SCHEDULE: t("video.event.scheduleTrigger"),
  };
  return map[type] || type;
}

function eventTag(type: string): any {
  const map: Record<string, string> = {
    ALARM: "danger",
    MOTION: "warning",
    OFFLINE: "info",
    ONLINE: "success",
    VIDEO_LOST: "danger",
    SCHEDULE: "primary",
  };
  return map[type] || "";
}

function actionLabel(type: string) {
  const map: Record<string, string> = {
    RECORD: t("video.event.startRecord"),
    ALERT: t("video.event.sendAlarm"),
    PTZ: t("video.event.ptzControl"),
    PUSH: t("video.event.msgPush"),
  };
  return map[type] || type;
}

function actionTag(type: string): any {
  const map: Record<string, string> = {
    RECORD: "primary",
    ALERT: "danger",
    PTZ: "warning",
    PUSH: "success",
  };
  return map[type] || "";
}
</script>

<style scoped>
.action-params {
  width: 100%;
}
.action-params__row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.action-params__label {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.action-params__advanced {
  border-top: 1px dashed var(--el-border-color-lighter);
}
</style>
