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
            :perm-create="['module_video:event:create']"
            :perm-delete="['module_video:event:delete']"
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

    <ElDialog v-model="dialogVisible.visible" :title="dialogVisible.title" width="640px" :close-on-click-modal="false">
      <ElForm ref="dataFormRef" :model="formData" label-width="110px">
        <ElFormItem label="联动名称" prop="name">
          <ElInput v-model="formData.name" placeholder="例如：入侵检测联动录像" />
        </ElFormItem>
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="触发事件" prop="trigger_event">
              <ElSelect v-model="formData.trigger_event" style="width:100%">
                <ElOption label="告警触发" value="ALARM" />
                <ElOption label="移动侦测" value="MOTION" />
                <ElOption label="设备离线" value="OFFLINE" />
                <ElOption label="设备上线" value="ONLINE" />
                <ElOption label="视频丢失" value="VIDEO_LOST" />
                <ElOption label="定时触发" value="SCHEDULE" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="动作类型" prop="action_type">
              <ElSelect v-model="formData.action_type" style="width:100%">
                <ElOption label="启动录像" value="RECORD" />
                <ElOption label="发送告警" value="ALERT" />
                <ElOption label="云台控制" value="PTZ" />
                <ElOption label="消息推送" value="PUSH" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>
        <ElFormItem label="关联摄像机" prop="trigger_camera_ids">
          <ElSelect v-model="formData.trigger_camera_ids" multiple filterable style="width:100%" placeholder="选择摄像机（可选，不选则对所有摄像机生效）">
            <ElOption v-for="c in cameras" :key="c.id" :label="c.name" :value="c.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="动作参数" prop="action_params">
          <ElInput v-model="actionParamsText" type="textarea" :rows="3" placeholder='JSON格式动作参数，例如：{"storage_days": 30}' />
        </ElFormItem>
        <ElFormItem label="状态" prop="status"><ElSwitch v-model="formData.status" /></ElFormItem>
        <ElFormItem label="描述" prop="description">
          <ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选描述" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h } from "vue";
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

defineOptions({ name: "VideoEvent", inheritAttrs: false });

const { hasAuth } = useAuth();
const cameras = ref<any[]>([]);

function eventLabel(type: string) {
  return ({ ALARM: "告警触发", MOTION: "移动侦测", OFFLINE: "设备离线", ONLINE: "设备上线", VIDEO_LOST: "视频丢失", SCHEDULE: "定时触发" } as any)[type] || type;
}
function eventTag(type: string) {
  return ({ ALARM: "danger", MOTION: "warning", OFFLINE: "info", ONLINE: "success", VIDEO_LOST: "danger", SCHEDULE: "primary" } as any)[type] || "";
}
function actionLabel(type: string) {
  return ({ RECORD: "启动录像", ALERT: "发送告警", PTZ: "云台控制", PUSH: "消息推送" } as any)[type] || type;
}
function actionTag(type: string) {
  return ({ RECORD: "primary", ALERT: "danger", PTZ: "warning", PUSH: "success" } as any)[type] || "";
}

function buildRowActions(row: any, ctx: { onEdit: (id: number) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const all: TableOperationAction[] = [
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_video:event:update", run: () => ctx.onEdit(row.id!) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:event:delete", run: () => ctx.onDelete(row.id!) },
  ];
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; trigger_event?: string; action_type?: string }>({ name: undefined, trigger_event: undefined, action_type: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "联动名称", key: "name", type: "input", placeholder: "请输入联动名称", clearable: true, span: 6 },
  {
    label: "触发事件", key: "trigger_event", type: "select",
    props: { placeholder: "请选择触发事件", clearable: true, options: [
      { label: "告警触发", value: "ALARM" }, { label: "移动侦测", value: "MOTION" }, { label: "设备离线", value: "OFFLINE" },
      { label: "设备上线", value: "ONLINE" }, { label: "视频丢失", value: "VIDEO_LOST" }, { label: "定时触发", value: "SCHEDULE" },
    ] },
    span: 6,
  },
  {
    label: "动作类型", key: "action_type", type: "select",
    props: { placeholder: "请选择动作类型", clearable: true, options: [
      { label: "启动录像", value: "RECORD" }, { label: "发送告警", value: "ALERT" }, { label: "云台控制", value: "PTZ" }, { label: "消息推送", value: "PUSH" },
    ] },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteEvent([id]);
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
    await VideoAPI.deleteEvent(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ } finally { batchDeleting.value = false; }
}

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  trigger_event: "ALARM",
  action_type: "RECORD",
  trigger_camera_ids: [] as number[],
  action_params: undefined as Record<string, any> | undefined,
  status: true,
  description: undefined as string | undefined,
});
const actionParamsText = ref("");
const initialFormData = { id: undefined, name: undefined, trigger_event: "ALARM", action_type: "RECORD", trigger_camera_ids: [], action_params: undefined, status: true, description: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑联动";
    const res = await VideoAPI.listEvent({ page_no: 1, page_size: 100 });
    const item = (res.data?.data?.items || []).find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, item);
      actionParamsText.value = item.action_params ? JSON.stringify(item.action_params, null, 2) : "";
    }
  } else {
    dialogVisible.title = "新建联动";
    Object.assign(formData, initialFormData);
    actionParamsText.value = "";
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    if (actionParamsText.value) {
      try { formData.action_params = JSON.parse(actionParamsText.value); }
      catch { ElMessage.warning("动作参数JSON格式错误，已忽略"); formData.action_params = {}; }
    }
    if (id) await VideoAPI.updateEvent(id, { ...formData });
    else await VideoAPI.createEvent({ ...formData });
    ElMessage.success("保存成功");
    dialogVisible.visible = false;
    await refreshData();
  } catch { /* ignore */ } finally { submitLoading.value = false; }
}

const opCtx = {
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDelete: deleteRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshRemove } = useTable({
  core: {
    apiFn: VideoAPI.listEvent,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "联动名称", minWidth: 160, showOverflowTooltip: true },
      { prop: "trigger_event", label: "触发事件", width: 120, align: "center", formatter: (row: any) => h(ElTag, { type: eventTag(row.trigger_event), size: "small", effect: "plain" }, () => eventLabel(row.trigger_event)) },
      { prop: "action_type", label: "动作类型", width: 120, align: "center", formatter: (row: any) => h(ElTag, { type: actionTag(row.action_type), size: "small", effect: "plain" }, () => actionLabel(row.action_type)) },
      { prop: "trigger_camera_ids", label: "关联摄像机", width: 110, formatter: (row: any) => `${row.trigger_camera_ids?.length || 0}台` },
      { prop: "status", label: "状态", width: 80, align: "center", formatter: (row: any) => h(ElTag, { type: row.status ? "success" : "danger", size: "small" }, () => row.status ? "启用" : "停用") },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation", label: "操作", width: 140, fixed: "right", align: "right",
        formatter: (row: any) => renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string; trigger_event?: string; action_type?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, trigger_event: undefined, action_type: undefined };
  void resetSearchParams();
}

VideoAPI.listCamera({ page_size: 100 }).then(r => { cameras.value = r.data?.data?.items || r.data?.data || []; }).catch(() => {});
</script>
