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
              fixed
              label="序号"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'name')?.show"
              key="name"
              label="名称"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'device_type')?.show"
              key="device_type"
              label="类型"
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
              label="状态"
              prop="reachable"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag
                  v-if="scope.row.reachable === true"
                  type="success"
                  size="small"
                >
                  <span class="status-dot" style="background:#67c23a" />
                  在线
                </el-tag>
                <el-tag
                  v-else-if="scope.row.reachable === false"
                  type="danger"
                  size="small"
                >
                  <span class="status-dot" style="background:#f56c6c" />
                  离线
                </el-tag>
                <el-tag
                  v-else
                  type="info"
                  size="small"
                >
                  <span class="status-dot" style="background:#909399" />
                  未推流
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'location')?.show"
              key="location"
              label="位置"
              prop="location"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'brand')?.show"
              key="brand"
              label="品牌"
              prop="brand"
              width="100"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'stream_id')?.show"
              key="stream_id"
              label="流状态"
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
                  推流中
                </el-tag>
                <el-tag
                  v-else-if="scope.row.stream_id && scope.row.stream_source === 'EXTERNAL'"
                  type="primary"
                  size="small"
                >
                  外部流
                </el-tag>
                <el-tag v-else type="info" size="small">未推流</el-tag>
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
                  推流
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
                  停止
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
                  播放测试
                </el-button>
                <el-button
                  v-hasPerm="['module_video:camera:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:camera:delete']"
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
      <el-form
        ref="dataFormRef"
        :model="formData"
        :rules="rules"
        label-width="100px"
        size="default"
      >
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="名称" prop="name">
              <el-input v-model="formData.name" placeholder="请输入摄像机名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备类型" prop="device_type">
              <el-select v-model="formData.device_type" style="width: 100%">
                <el-option label="IP Camera" value="IP_CAMERA" />
                <el-option label="GB28181" value="GB28181" />
                <el-option label="ONVIF" value="ONVIF" />
                <el-option label="NVR" value="NVR" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="主码流RTSP" prop="rtsp_url_main">
          <el-input v-model="formData.rtsp_url_main" placeholder="rtsp://..." />
        </el-form-item>
        <el-form-item label="子码流RTSP" prop="rtsp_url_sub">
          <el-input v-model="formData.rtsp_url_sub" placeholder="rtsp://..." />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="formData.username" placeholder="登录用户名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="formData.password"
                type="password"
                show-password
                placeholder="登录密码"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="安装位置" prop="location">
              <el-input v-model="formData.location" placeholder="例如：一楼大厅" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序" prop="sort_order">
              <el-input-number v-model="formData.sort_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="所属分组" prop="group_id">
              <el-tree-select
                v-model="formData.group_id"
                :data="groupOptions"
                :props="{ children: 'children', label: 'label', disabled: 'disabled' }"
                value-key="value"
                placeholder="请选择分组"
                clearable
                filterable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="品牌" prop="brand">
              <el-input v-model="formData.brand" placeholder="例如：海康威视" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="型号" prop="model_name">
              <el-input v-model="formData.model_name" placeholder="例如：DS-2CD3T86" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="备注" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="可选备注信息"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <el-dialog
      v-model="playerVisible"
      title="播放测试"
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
                  <el-button size="small" @click="copyUrl(url)">复制</el-button>
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
      label: "名称",
      type: "input",
      attrs: { placeholder: "请输入摄像机名称", clearable: true },
    },
    {
      prop: "device_type",
      label: "设备类型",
      type: "select",
      options: [
        { label: "IP Camera", value: "IP_CAMERA" },
        { label: "GB28181", value: "GB28181" },
        { label: "ONVIF", value: "ONVIF" },
        { label: "NVR", value: "NVR" },
      ],
      attrs: { placeholder: "请选择设备类型", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "在线", value: "ONLINE" },
        { label: "离线", value: "OFFLINE" },
        { label: "异常", value: "ERROR" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "location",
      label: "位置",
      type: "input",
      attrs: { placeholder: "请输入安装位置", clearable: true },
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
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "名称", show: true },
  { prop: "device_type", label: "类型", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "location", label: "位置", show: true },
  { prop: "brand", label: "品牌", show: true },
  { prop: "stream_id", label: "流状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
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
    title: "警告",
    message: "确认删除该项数据?",
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
  name: [{ required: true, message: "请输入摄像机名称", trigger: "blur" }],
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
    dialogVisible.title = "编辑摄像机";
    const res = await getCameraDetail(id);
    Object.assign(formData, res.data.data);
  } else {
    dialogVisible.title = "新增摄像机";
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
          await updateCamera(id, { id, ...formData });
        } else {
          await createCamera(formData);
        }
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
    ElMessage.success("推流启动成功");
    refreshList();
  } catch (e: any) {
    ElMessage.error(e?.message || "推流启动失败");
  }
}

async function handleStopStream(row: any) {
  try {
    await stopStream(row.id);
    ElMessage.success("推流已停止");
    refreshList();
  } catch (e: any) {
    ElMessage.error(e?.message || "停止推流失败");
  }
}

const playerVisible = ref(false);
const playerCamera = ref<any>(null);
const playerStreamId = ref("");
const playerUrls = ref<Record<string, string>>({});
const playerReady = ref(false);
const playerLoadingText = ref("准备中...");

const { copy } = useClipboard();

function copyUrl(url: string) {
  copy(url);
  ElMessage.success("已复制");
}

async function handlePlayTest(row: any) {
  playerCamera.value = row;
  playerStreamId.value = row.stream_id || "";
  playerVisible.value = true;
  playerReady.value = false;
  playerLoadingText.value = "获取播放地址...";
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
      playerLoadingText.value = "获取播放地址失败";
    }
  } catch (e: any) {
    playerLoadingText.value = e?.message || "启动推流失败";
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
    IP_CAMERA: "IP摄像机",
    GB28181: "GB28181",
    ONVIF: "ONVIF",
    NVR: "NVR",
  };
  return map[type] || type;
}

function deviceTypeTag(type: string) {
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
  font-size: 15px;
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
