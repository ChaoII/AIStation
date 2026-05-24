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
              label="联动名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'trigger_event')?.show"
              key="trigger_event"
              label="触发事件"
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
              label="动作类型"
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
              label="关联摄像机"
              prop="trigger_camera_ids"
              min-width="120"
              show-overflow-tooltip
            >
              <template #default="scope">
                <span>{{ scope.row.trigger_camera_ids?.length || 0 }}台</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
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
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:event:delete']"
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
      width="640px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px" size="default">
        <el-form-item label="联动名称" prop="name">
          <el-input v-model="formData.name" placeholder="例如：入侵检测联动录像" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="触发事件" prop="trigger_event">
              <el-select v-model="formData.trigger_event" style="width: 100%">
                <el-option label="告警触发" value="ALARM" />
                <el-option label="移动侦测" value="MOTION" />
                <el-option label="设备离线" value="OFFLINE" />
                <el-option label="设备上线" value="ONLINE" />
                <el-option label="视频丢失" value="VIDEO_LOST" />
                <el-option label="定时触发" value="SCHEDULE" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="动作类型" prop="action_type">
              <el-select v-model="formData.action_type" style="width: 100%">
                <el-option label="启动录像" value="RECORD" />
                <el-option label="发送告警" value="ALERT" />
                <el-option label="云台控制" value="PTZ" />
                <el-option label="消息推送" value="PUSH" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="关联摄像机" prop="trigger_camera_ids">
          <el-select
            v-model="formData.trigger_camera_ids"
            multiple
            filterable
            style="width: 100%"
            placeholder="选择摄像机（可选，不选则对所有摄像机生效）"
          >
            <el-option v-for="c in cameras" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="动作参数" prop="action_params">
          <el-input
            v-model="actionParamsText"
            type="textarea"
            :rows="3"
            placeholder='JSON格式动作参数，例如：{"storage_days": 30}'
          />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-switch v-model="formData.status" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="2"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { getCameraList } from "@/api/module_video/camera";
import { getEventList, createEvent, updateEvent, deleteEvent } from "@/api/module_video/event";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

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
      label: "联动名称",
      type: "input",
      attrs: { placeholder: "请输入联动名称", clearable: true },
    },
    {
      prop: "trigger_event",
      label: "触发事件",
      type: "select",
      options: [
        { label: "告警触发", value: "ALARM" },
        { label: "移动侦测", value: "MOTION" },
        { label: "设备离线", value: "OFFLINE" },
        { label: "设备上线", value: "ONLINE" },
        { label: "视频丢失", value: "VIDEO_LOST" },
        { label: "定时触发", value: "SCHEDULE" },
      ],
      attrs: { placeholder: "请选择触发事件", clearable: true, style: { width: "167.5px" } },
    },
    {
      prop: "action_type",
      label: "动作类型",
      type: "select",
      options: [
        { label: "启动录像", value: "RECORD" },
        { label: "发送告警", value: "ALERT" },
        { label: "云台控制", value: "PTZ" },
        { label: "消息推送", value: "PUSH" },
      ],
      attrs: { placeholder: "请选择动作类型", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "联动名称", show: true },
  { prop: "trigger_event", label: "触发事件", show: true },
  { prop: "action_type", label: "动作类型", show: true },
  { prop: "trigger_camera_ids", label: "关联摄像机", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "created_time", label: "创建时间", show: true },
  { prop: "operation", label: "操作", show: true },
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
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 100 });
    cameras.value = res.data?.items || [];
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
  action_params: {} as Record<string, any> | undefined,
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
  action_params: undefined as Record<string, any> | undefined,
  status: true,
  description: undefined as string | undefined,
};

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  actionParamsText.value = "";
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑联动";
    const res = await getEventList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, item);
      actionParamsText.value = item.action_params
        ? JSON.stringify(item.action_params, null, 2)
        : "";
    }
  } else {
    dialogVisible.title = "新建联动";
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    if (actionParamsText.value) {
      try {
        formData.action_params = JSON.parse(actionParamsText.value);
      } catch {
        ElMessage.warning("动作参数JSON格式错误，已忽略");
        formData.action_params = {};
      }
    }
    if (id) {
      await updateEvent(id, { id, ...formData });
    } else {
      await createEvent(formData);
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

function eventLabel(type: string) {
  const map: Record<string, string> = {
    ALARM: "告警触发",
    MOTION: "移动侦测",
    OFFLINE: "设备离线",
    ONLINE: "设备上线",
    VIDEO_LOST: "视频丢失",
    SCHEDULE: "定时触发",
  };
  return map[type] || type;
}

function eventTag(type: string) {
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
    RECORD: "启动录像",
    ALERT: "发送告警",
    PTZ: "云台控制",
    PUSH: "消息推送",
  };
  return map[type] || type;
}

function actionTag(type: string) {
  const map: Record<string, string> = {
    RECORD: "primary",
    ALERT: "danger",
    PTZ: "warning",
    PUSH: "success",
  };
  return map[type] || "";
}

fetchCameras();
</script>
