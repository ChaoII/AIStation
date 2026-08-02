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
            :perm-create="['module_video:camera:create']"
            :perm-delete="['module_video:camera:delete']"
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

    <ElDialog v-model="dialogVisible.visible" :title="dialogVisible.title" width="720px" :close-on-click-modal="false">
      <ElForm ref="dataFormRef" :model="formData" :rules="rules" label-width="100px">
        <ElRow :gutter="20">
          <ElCol :span="12"><ElFormItem label="名称" prop="name"><ElInput v-model="formData.name" placeholder="请输入摄像机名称" /></ElFormItem></ElCol>
          <ElCol :span="12">
            <ElFormItem label="设备类型" prop="device_type">
              <ElSelect v-model="formData.device_type" style="width:100%">
                <ElOption label="IP Camera" value="IP_CAMERA" />
                <ElOption label="GB28181" value="GB28181" />
                <ElOption label="ONVIF" value="ONVIF" />
                <ElOption label="NVR" value="NVR" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>
        <ElFormItem label="主码流RTSP" prop="rtsp_url_main"><ElInput v-model="formData.rtsp_url_main" placeholder="rtsp://..." /></ElFormItem>
        <ElFormItem label="子码流RTSP" prop="rtsp_url_sub"><ElInput v-model="formData.rtsp_url_sub" placeholder="rtsp://..." /></ElFormItem>
        <ElRow :gutter="20">
          <ElCol :span="12"><ElFormItem label="用户名" prop="username"><ElInput v-model="formData.username" placeholder="登录用户名" /></ElFormItem></ElCol>
          <ElCol :span="12"><ElFormItem label="密码" prop="password"><ElInput v-model="formData.password" type="password" show-password placeholder="登录密码" /></ElFormItem></ElCol>
        </ElRow>
        <ElRow :gutter="20">
          <ElCol :span="12"><ElFormItem label="安装位置" prop="location"><ElInput v-model="formData.location" placeholder="例如：一楼大厅" /></ElFormItem></ElCol>
          <ElCol :span="12"><ElFormItem label="排序" prop="sort_order"><ElInputNumber v-model="formData.sort_order" :min="0" style="width:100%" /></ElFormItem></ElCol>
        </ElRow>
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="所属分组" prop="group_id">
              <ElTreeSelect v-model="formData.group_id" :data="groupOptions" :props="{ children: 'children', label: 'label', disabled: 'disabled' }" value-key="value" placeholder="请选择分组" clearable filterable style="width:100%" />
            </ElFormItem>
          </ElCol>
          <ElCol :span="12"><ElFormItem label="品牌" prop="brand"><ElInput v-model="formData.brand" placeholder="例如：海康威视" /></ElFormItem></ElCol>
        </ElRow>
        <ElRow :gutter="20">
          <ElCol :span="12"><ElFormItem label="型号" prop="model_name"><ElInput v-model="formData.model_name" placeholder="例如：DS-2CD3T86" /></ElFormItem></ElCol>
        </ElRow>
        <ElFormItem label="备注" prop="description"><ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选备注信息" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">保存</ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="playerVisible" title="播放测试" width="720px" :close-on-click-modal="false" @close="handlePlayerClose">
      <div class="player-test-dialog">
        <div class="player-test-info">
          <span class="test-camera-name">{{ playerCamera?.name }}</span>
          <div class="test-urls">
            <div v-for="(url, proto) in playerUrls" :key="proto" class="test-url-row">
              <ElTag :type="protoTag(proto)" size="small" class="url-tag">{{ proto }}</ElTag>
              <ElInput :model-value="url" readonly size="small" class="url-value">
                <template #append><ElButton size="small" @click="copyUrl(url)">复制</ElButton></template>
              </ElInput>
            </div>
          </div>
        </div>
        <div class="player-test-stage">
          <div v-if="!playerReady" class="player-placeholder">
            <ElIcon :size="48" color="#ccc"><VideoCamera /></ElIcon>
            <span>{{ playerLoadingText }}</span>
          </div>
          <FaVideoPlayer v-if="playerReady" :player-id="'camera-test-' + (playerCamera?.id || 0)" :video-url="primaryPlayUrl" :poster-url="''" />
        </div>
      </div>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeMount, h } from "vue";
import { ElMessage, ElTag } from "element-plus";
import { VideoCamera } from "@element-plus/icons-vue";
import { useTable } from "@/hooks/core/useTable";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { cleanEmptyArrayParams } from "@/utils/query";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import { formatTree } from "@utils";
import type { ColumnOption } from "@/types/component";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import FaVideoPlayer from "@/components/media/fa-video-player/index.vue";
import { VideoAPI } from "@/api/module_video";

defineOptions({ name: "VideoCamera", inheritAttrs: false });

const { hasAuth } = useAuth();
const groupOptions = ref<any[]>([]);

onBeforeMount(async () => {
  try {
    const res = await VideoAPI.listCameraGroup();
    groupOptions.value = formatTree(res.data?.data || []);
  } catch { groupOptions.value = []; }
});

function deviceTypeLabel(type: string) {
  return ({ IP_CAMERA: "IP摄像机", GB28181: "GB28181", ONVIF: "ONVIF", NVR: "NVR" } as any)[type] || type;
}
function deviceTypeTag(type: string) {
  return ({ IP_CAMERA: "primary", GB28181: "success", ONVIF: "warning", NVR: "info" } as any)[type] || "info";
}
function streamCell(row: any) {
  if (row.stream_id && row.stream_source === "SYSTEM") return h(ElTag, { type: "success", size: "small" }, () => "推流中");
  if (row.stream_id && row.stream_source === "EXTERNAL") return h(ElTag, { type: "primary", size: "small" }, () => "外部流");
  return h(ElTag, { type: "info", size: "small" }, () => "未推流");
}
function statusCell(row: any) {
  if (row.reachable === true) return h(ElTag, { type: "success", size: "small" }, () => "在线");
  if (row.reachable === false) return h(ElTag, { type: "danger", size: "small" }, () => "离线");
  return h(ElTag, { type: "info", size: "small" }, () => "未推流");
}

function buildRowActions(row: any, ctx: { onStart: (id: number) => void; onStop: (id: number) => void; onPlay: (row: any) => void; onEdit: (id: number) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const actions: TableOperationAction[] = [];
  if (!row.stream_id) actions.push({ key: "start", label: "推流", artType: "view", icon: "ri:play-circle-line", iconColor: "var(--el-color-primary)", perm: "module_video:camera:stream", run: () => ctx.onStart(row.id!) });
  else if (row.stream_source === "SYSTEM") actions.push({ key: "stop", label: "停止", artType: "view", icon: "ri:stop-circle-line", iconColor: "var(--el-color-warning)", perm: "module_video:camera:stream", run: () => ctx.onStop(row.id!) });
  if (row.rtsp_url_main || row.stream_id) actions.push({ key: "play", label: "播放测试", artType: "view", icon: "ri:video-line", iconColor: "var(--el-color-success)", perm: "module_video:camera:query", run: () => ctx.onPlay(row) });
  actions.push(
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_video:camera:update", run: () => ctx.onEdit(row.id!) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:camera:delete", run: () => ctx.onDelete(row.id!) },
  );
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; device_type?: string; location?: string }>({ name: undefined, device_type: undefined, location: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};
const searchItems = computed<SearchFormItem[]>(() => [
  { label: "名称", key: "name", type: "input", placeholder: "请输入摄像机名称", clearable: true, span: 6 },
  { label: "设备类型", key: "device_type", type: "select", props: { placeholder: "请选择设备类型", clearable: true, options: [{ label: "IP Camera", value: "IP_CAMERA" }, { label: "GB28181", value: "GB28181" }, { label: "ONVIF", value: "ONVIF" }, { label: "NVR", value: "NVR" }] }, span: 6 },
  { label: "位置", key: "location", type: "input", placeholder: "请输入安装位置", clearable: true, span: 6 },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteCamera([id]);
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
    await VideoAPI.deleteCamera(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ } finally { batchDeleting.value = false; }
}

async function handleStartStream(id: number) {
  try {
    await VideoAPI.startStream(id);
    ElMessage.success("推流启动成功");
    await refreshData();
  } catch (e: any) { ElMessage.error(e?.message || "推流启动失败"); }
}
async function handleStopStream(id: number) {
  try {
    await VideoAPI.stopStream(id);
    ElMessage.success("推流已停止");
    await refreshData();
  } catch (e: any) { ElMessage.error(e?.message || "停止推流失败"); }
}

const playerVisible = ref(false);
const playerCamera = ref<any>(null);
const playerUrls = ref<Record<string, string>>({});
const playerReady = ref(false);
const playerLoadingText = ref("准备中...");
const primaryPlayUrl = computed(() => Object.values(playerUrls.value)[0] || "");

function copyUrl(url: string) {
  navigator.clipboard.writeText(url).then(() => ElMessage.success("已复制")).catch(() => {});
}
function protoTag(proto: string): "primary" | "success" | "warning" | "info" | "danger" | undefined {
  return ({ flv: "primary", hls: "success", webrtc: "warning", ws_flv: "info", rtmp: "danger" } as any)[proto];
}

async function handlePlayTest(row: any) {
  playerCamera.value = row;
  playerVisible.value = true;
  playerReady.value = false;
  playerLoadingText.value = "获取播放地址...";
  try {
    if (row.stream_id) {
      const res = await VideoAPI.getStreamUrls(row.id);
      playerUrls.value = res.data?.data?.play_urls || {};
    } else {
      const res = await VideoAPI.startStream(row.id);
      const data = res.data?.data || {};
      playerUrls.value = data.play_urls || {};
    }
    if (Object.keys(playerUrls.value).length > 0) {
      playerReady.value = true;
      await refreshData();
    } else {
      playerLoadingText.value = "获取播放地址失败";
    }
  } catch (e: any) {
    playerLoadingText.value = e?.message || "启动推流失败";
    setTimeout(() => { playerVisible.value = false; }, 2000);
  }
}
function handlePlayerClose() {
  playerReady.value = false;
  playerUrls.value = {};
}

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({
  id: undefined as number | undefined, name: undefined as string | undefined, device_type: "IP_CAMERA",
  rtsp_url_main: undefined as string | undefined, rtsp_url_sub: undefined as string | undefined,
  username: undefined as string | undefined, password: undefined as string | undefined,
  location: undefined as string | undefined, sort_order: 0, brand: undefined as string | undefined,
  model_name: undefined as string | undefined, description: undefined as string | undefined, group_id: undefined as number | undefined,
});
const initialFormData = { id: undefined, name: undefined, device_type: "IP_CAMERA", rtsp_url_main: undefined, rtsp_url_sub: undefined, username: undefined, password: undefined, location: undefined, sort_order: 0, brand: undefined, model_name: undefined, description: undefined, group_id: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);
const rules = reactive({ name: [{ required: true, message: "请输入摄像机名称", trigger: "blur" }] });

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑摄像机";
    const res = await VideoAPI.detailCamera(id);
    Object.assign(formData, res.data?.data || {});
  } else {
    dialogVisible.title = "新增摄像机";
    Object.assign(formData, initialFormData);
  }
  dialogVisible.visible = true;
}
async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    submitLoading.value = true;
    const id = formData.id;
    try {
      if (id) await VideoAPI.updateCamera(id, { ...formData });
      else await VideoAPI.createCamera({ ...formData });
      ElMessage.success("保存成功");
      dialogVisible.visible = false;
      await refreshData();
    } catch { /* ignore */ } finally { submitLoading.value = false; }
  });
}

const opCtx = {
  onStart: handleStartStream,
  onStop: handleStopStream,
  onPlay: handlePlayTest,
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDelete: deleteRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshRemove } = useTable({
  core: {
    apiFn: VideoAPI.listCamera,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "名称", minWidth: 140, showOverflowTooltip: true },
      { prop: "device_type", label: "类型", width: 120, formatter: (row: any) => h(ElTag, { type: deviceTypeTag(row.device_type), size: "small", effect: "plain" }, () => deviceTypeLabel(row.device_type)) },
      { prop: "reachable", label: "状态", width: 100, align: "center", formatter: (row: any) => statusCell(row) },
      { prop: "location", label: "位置", minWidth: 120, showOverflowTooltip: true },
      { prop: "brand", label: "品牌", width: 100, showOverflowTooltip: true },
      { prop: "stream_id", label: "流状态", width: 100, align: "center", formatter: (row: any) => streamCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation", label: "操作", width: 240, fixed: "right", align: "right",
        formatter: (row: any) => renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string; device_type?: string; location?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, device_type: undefined, location: undefined };
  void resetSearchParams();
}
</script>

<style scoped>
.player-test-dialog { display: flex; flex-direction: column; gap: 12px; }
.player-test-info { display: flex; flex-direction: column; gap: 8px; }
.test-camera-name { font-size: 15px; font-weight: 600; }
.test-urls { display: flex; flex-direction: column; gap: 4px; }
.test-url-row { display: flex; gap: 4px; align-items: center; }
.url-tag { flex-shrink: 0; width: 56px; font-size: 11px; text-align: center; }
.url-value { flex: 1; }
.player-test-stage { position: relative; width: 100%; height: 360px; overflow: hidden; background: #000; border-radius: 6px; }
.player-placeholder { display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; width: 100%; height: 100%; font-size: 14px; color: #999; }
</style>
