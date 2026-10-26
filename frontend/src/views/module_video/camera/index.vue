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
          :perm-create="['module_video:camera:create']"
          :perm-delete="['module_video:camera:delete']"
          :perm-patch="['module_video:camera:patch']"
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
              :label="t('video.common.name')"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'device_type')?.show"
              key="device_type"
              :label="t('video.common.type')"
              prop="device_type"
              width="120"
            >
              <template #default="scope">
                <el-tag :type="deviceTypeTag(scope.row.device_type)" size="small" effect="plain">
                  {{ deviceTypeLabel(scope.row.device_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              :label="t('video.common.status')"
              prop="reachable"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag v-if="scope.row.reachable === true" type="success" size="small">
                  <span class="status-dot" style="background: #67c23a" />
                  {{ t("video.common.online") }}
                </el-tag>
                <el-tag v-else-if="scope.row.reachable === false" type="danger" size="small">
                  <span class="status-dot" style="background: #f56c6c" />
                  {{ t("video.common.offline") }}
                </el-tag>
                <el-tag v-else type="info" size="small">
                  <span class="status-dot" style="background: #909399" />
                  {{ t("video.camera.noStream") }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'location')?.show"
              key="location"
              :label="t('video.common.location')"
              prop="location"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'brand')?.show"
              key="brand"
              :label="t('video.common.brand')"
              prop="brand"
              width="100"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'stream_id')?.show"
              key="stream_id"
              :label="t('video.camera.flowStatus')"
              prop="stream_id"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag
                  v-if="scope.row.stream_id && scope.row.stream_source === 'SYSTEM'"
                  type="success"
                  size="small"
                >
                  {{ t("video.camera.streaming") }}
                </el-tag>
                <el-tag
                  v-else-if="scope.row.stream_id && scope.row.stream_source === 'EXTERNAL'"
                  type="primary"
                  size="small"
                >
                  {{ t("video.camera.externalStream") }}
                </el-tag>
                <el-tag v-else type="info" size="small">{{ t("video.camera.noStream") }}</el-tag>
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
              min-width="270"
            >
              <template #default="scope">
                <el-button
                  v-if="!scope.row.stream_id"
                  v-hasPerm="['module_video:camera:stream']"
                  size="small"
                  type="primary"
                  link
                  icon="VideoPlay"
                  @click="handleStartStream(scope.row)"
                >
                  {{ t("video.camera.pushStream") }}
                </el-button>
                <el-button
                  v-else-if="scope.row.stream_source === 'SYSTEM'"
                  v-hasPerm="['module_video:camera:stream']"
                  size="small"
                  type="warning"
                  link
                  icon="VideoPause"
                  @click="handleStopStream(scope.row)"
                >
                  {{ t("video.camera.stop") }}
                </el-button>
                <el-button
                  v-if="scope.row.rtsp_url_main || scope.row.stream_id"
                  v-hasPerm="['module_video:camera:query']"
                  size="small"
                  type="success"
                  link
                  icon="VideoPlay"
                  @click="handlePlayTest(scope.row)"
                >
                  {{ t("video.camera.playTest") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_video:camera:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("video.common.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_video:camera:delete']"
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
      width="720px"
      @close="handleCloseDialog"
    >
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-width="100px"
        size="default"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('video.common.name')" prop="name">
              <el-input v-model="formData.name" :placeholder="t('video.camera.enterCameraName')" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('video.camera.deviceType')" prop="device_type">
              <el-select v-model="formData.device_type" style="width: 100%">
                <el-option label="IP Camera" value="IP_CAMERA" />
                <el-option label="GB28181" value="GB28181" />
                <el-option label="ONVIF" value="ONVIF" />
                <el-option label="NVR" value="NVR" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('video.camera.mainRtsp')" prop="rtsp_url_main">
          <el-input v-model="formData.rtsp_url_main" placeholder="rtsp://..." />
        </el-form-item>
        <el-form-item :label="t('video.camera.subRtsp')" prop="rtsp_url_sub">
          <el-input v-model="formData.rtsp_url_sub" placeholder="rtsp://..." />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('video.camera.username')" prop="username">
              <el-input
                v-model="formData.username"
                :placeholder="t('video.camera.loginUsername')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('video.camera.password')" prop="password">
              <el-input
                v-model="formData.password"
                type="password"
                show-password
                :placeholder="t('video.camera.loginPassword')"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('video.camera.installLocation')" prop="location">
              <el-input
                v-model="formData.location"
                :placeholder="t('video.camera.locationExample')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('video.common.sortOrder')" prop="sort_order">
              <el-input-number v-model="formData.sort_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('video.camera.group')" prop="group_id">
              <el-tree-select
                v-model="formData.group_id"
                :data="groupOptions"
                :props="{ children: 'children', label: 'label', disabled: 'disabled' }"
                value-key="value"
                :placeholder="t('video.camera.selectGroup')"
                clearable
                filterable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('video.common.brand')" prop="brand">
              <el-input v-model="formData.brand" :placeholder="t('video.camera.brandExample')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item :label="t('video.camera.model')" prop="model_name">
              <el-input
                v-model="formData.model_name"
                :placeholder="t('video.camera.modelExample')"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('video.camera.remark')" prop="description">
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

    <el-dialog
      v-model="playerVisible"
      :title="t('video.camera.playTest')"
      width="720px"
      append-to-body
      destroy-on-close
      @close="handlePlayerClose"
    >
      <div class="player-test-dialog">
        <div class="player-test-info">
          <span class="test-camera-name">{{ playerCamera?.name }}</span>
          <div class="test-urls">
            <div v-for="(url, proto) in playerUrls" :key="proto" class="test-url-row">
              <el-tag :type="protoTag(proto)" size="small" class="url-tag">{{ proto }}</el-tag>
              <el-input :model-value="url" readonly size="small" class="url-value">
                <template #append>
                  <el-button size="small" @click="copyUrl(url)">
                    {{ t("video.camera.copy") }}
                  </el-button>
                </template>
              </el-input>
            </div>
          </div>
        </div>
        <div class="player-test-stage">
          <div v-if="!playerReady" class="player-placeholder">
            <el-icon :size="48" color="#ccc"><VideoCamera /></el-icon>
            <span>{{ playerLoadingText }}</span>
          </div>
          <LivePlayer v-if="playerReady" :stream-id="playerStreamId" class="player-test-inner" />
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount } from "vue";
import { ElMessage } from "element-plus";
import { useClipboard } from "@vueuse/core";
import { useI18n } from "vue-i18n";
import { VideoCamera } from "@element-plus/icons-vue";
import LivePlayer from "@/components/Video/LivePlayer.vue";
import {
  getCameraList,
  getCameraDetail,
  createCamera,
  updateCamera,
  deleteCamera,
  startStream,
  stopStream,
  getStreamUrls,
  getCameraGroupList,
} from "@/api/module_video/camera";
import { formatTree } from "@/utils/common";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const { t } = useI18n();

const groupOptions = ref<any[]>([]);

onBeforeMount(async () => {
  try {
    const res = await getCameraGroupList();
    groupOptions.value = formatTree(res.data.data || []);
  } catch {
    groupOptions.value = [];
  }
});

const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:camera",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("video.common.name"),
      type: "input",
      attrs: { placeholder: t("video.camera.enterCameraName"), clearable: true },
    },
    {
      prop: "device_type",
      label: t("video.camera.deviceType"),
      type: "select",
      options: [
        { label: "IP Camera", value: "IP_CAMERA" },
        { label: "GB28181", value: "GB28181" },
        { label: "ONVIF", value: "ONVIF" },
        { label: "NVR", value: "NVR" },
      ],
      attrs: {
        placeholder: t("video.camera.selectDeviceType"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "status",
      label: t("video.common.status"),
      type: "select",
      options: [
        { label: t("video.common.online"), value: "ONLINE" },
        { label: t("video.common.offline"), value: "OFFLINE" },
        { label: t("video.common.abnormal"), value: "ERROR" },
      ],
      attrs: {
        placeholder: t("video.camera.selectStatus"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
    {
      prop: "location",
      label: t("video.common.location"),
      type: "input",
      attrs: { placeholder: t("video.camera.enterLocation"), clearable: true },
    },
  ],
});

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "name", label: t("video.common.name"), show: true },
  { prop: "device_type", label: t("video.common.type"), show: true },
  { prop: "status", label: t("video.common.status"), show: true },
  { prop: "location", label: t("video.common.location"), show: true },
  { prop: "brand", label: t("video.common.brand"), show: true },
  { prop: "stream_id", label: t("video.camera.flowStatus"), show: true },
  { prop: "created_time", label: t("video.common.createdTime"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:camera",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getCameraList(params as TablePageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: async (ids) => {
    await deleteCamera(
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

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  device_type: "IP_CAMERA",
  rtsp_url_main: undefined as string | undefined,
  rtsp_url_sub: undefined as string | undefined,
  username: undefined as string | undefined,
  password: undefined as string | undefined,
  location: undefined as string | undefined,
  sort_order: 0,
  brand: undefined as string | undefined,
  model_name: undefined as string | undefined,
  description: undefined as string | undefined,
  group_id: undefined as number | undefined,
});

const initialFormData = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  device_type: "IP_CAMERA",
  rtsp_url_main: undefined as string | undefined,
  rtsp_url_sub: undefined as string | undefined,
  username: undefined as string | undefined,
  password: undefined as string | undefined,
  location: undefined as string | undefined,
  sort_order: 0,
  brand: undefined as string | undefined,
  model_name: undefined as string | undefined,
  description: undefined as string | undefined,
  group_id: undefined as number | undefined,
};

const rules = reactive({
  name: [{ required: true, message: t("video.camera.enterCameraName"), trigger: "blur" }],
});

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = t("video.camera.editCamera");
    const res = await getCameraDetail(id);
    Object.assign(formData, res.data.data);
  } else {
    dialogVisible.title = t("video.camera.addCamera");
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        if (id) {
          await updateCamera(id, formData);
        } else {
          await createCamera(formData);
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
  });
}

async function handleStartStream(row: any) {
  try {
    await startStream(row.id);
    ElMessage.success(t("video.common.started"));
    refreshList();
  } catch {
    /* 拦截器已提示错误 */
  }
}

async function handleStopStream(row: any) {
  try {
    await stopStream(row.id);
    ElMessage.success(t("video.common.stopped"));
    refreshList();
  } catch {
    /* 拦截器已提示错误 */
  }
}

const playerVisible = ref(false);
const playerCamera = ref<any>(null);
const playerStreamId = ref("");
const playerUrls = ref<Record<string, string>>({});
const playerReady = ref(false);
const playerLoadingText = ref(t("video.camera.preparing"));

const { copy } = useClipboard();

function copyUrl(url: string) {
  copy(url);
  ElMessage.success(t("video.common.copied"));
}

async function handlePlayTest(row: any) {
  playerCamera.value = row;
  playerStreamId.value = row.stream_id || "";
  playerVisible.value = true;
  playerReady.value = false;
  playerLoadingText.value = t("video.camera.getPlayAddr");
  try {
    if (row.stream_id) {
      const res = await getStreamUrls(row.id);
      playerUrls.value = res.data.data.play_urls || {};
    } else {
      const res = await startStream(row.id);
      const data = res.data.data || {};
      playerUrls.value = data.play_urls || {};
      playerStreamId.value = data.stream_id || "";
    }
    if (playerStreamId.value || Object.keys(playerUrls.value).length > 0) {
      playerReady.value = true;
      refreshList();
    } else {
      playerLoadingText.value = t("video.camera.getPlayUrlFail");
    }
  } catch (e: any) {
    playerLoadingText.value = e?.message || t("video.camera.startPushFail");
    setTimeout(() => {
      playerVisible.value = false;
    }, 2000);
  }
}

function handlePlayerClose() {
  playerReady.value = false;
  playerUrls.value = {};
}

function protoTag(
  proto: string
): "primary" | "success" | "warning" | "info" | "danger" | undefined {
  const map: Record<string, "primary" | "success" | "warning" | "info" | "danger"> = {
    flv: "primary",
    hls: "success",
    webrtc: "warning",
    ws_flv: "info",
    rtmp: "danger",
  };
  return map[proto];
}

function deviceTypeLabel(type: string) {
  const map: Record<string, string> = {
    IP_CAMERA: t("video.camera.ipCamera"),
    GB28181: "GB28181",
    ONVIF: "ONVIF",
    NVR: "NVR",
  };
  return map[type] || type;
}

function deviceTypeTag(type: string): any {
  const map: Record<string, string> = {
    IP_CAMERA: "",
    GB28181: "success",
    ONVIF: "warning",
    NVR: "info",
  };
  return map[type] || "";
}
</script>

<style scoped>
.player-test-dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.player-test-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.test-camera-name {
  font-size: var(--el-font-size-base);
  font-weight: 600;
}

.test-urls {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.test-url-row {
  display: flex;
  gap: 4px;
  align-items: center;
}

.url-tag {
  flex-shrink: 0;
  width: 56px;
  font-size: 11px;
  text-align: center;
}

.url-tag {
  min-width: 52px;
  font-family: monospace;
  font-weight: 600;
  text-align: center;
  text-transform: uppercase;
}

.url-value {
  flex: 1;
}

.player-test-stage {
  position: relative;
  width: 100%;
  height: 360px;
  overflow: hidden;
  background: #000;
  border-radius: 6px;
}

.player-placeholder {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 14px;
  color: #999;
}

.player-test-inner {
  width: 100%;
  height: 100%;
}

.url-proto {
  min-width: 60px;
  font-family: monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
}

.url-value {
  flex: 1;
}

.player-test-stage {
  position: relative;
  width: 100%;
  height: 360px;
  overflow: hidden;
  background: #000;
  border-radius: 6px;
}

.player-placeholder {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: 14px;
  color: #999;
}

.player-test-inner {
  width: 100%;
  height: 100%;
}

.player-test-protocols {
  display: flex;
  justify-content: center;
}
.status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}
</style>
