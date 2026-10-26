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
          :perm-create="['module_video:edge:create']"
          :perm-delete="['module_video:edge:delete']"
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
              v-if="edgeCols.find((c) => c.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="edgeCols.find((c) => c.prop === 'index')?.show"
              type="index"
              fixed
              :label="t('video.common.sequence')"
              width="60"
              align="center"
            />
            <el-table-column
              :label="t('video.edge.deviceName')"
              prop="name"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('video.edge.deviceCode')"
              prop="code"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column :label="t('video.common.status')" width="100" align="center">
              <template #default="scope">
                <el-tag :type="statusTag(scope.row.status)" size="small">
                  {{ statusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('video.edge.runningCap')" width="110" align="center">
              <template #default="scope">
                {{ runningOf(scope.row) }} / {{ scope.row.capabilities?.max_channels ?? "-" }}
              </template>
            </el-table-column>
            <el-table-column
              :label="t('video.edge.lastHeartbeat')"
              prop="last_heartbeat"
              width="170"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('video.edge.controlUrl')"
              prop="control_url"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="edgeCols.find((c) => c.prop === 'operation')?.show"
              fixed="right"
              :label="t('video.common.operation')"
              align="center"
              min-width="160"
            >
              <template #default="scope">
                <el-button
                  icon="View"
                  type="primary"
                  size="small"
                  link
                  @click="handleViewDetail(scope.row)"
                >
                  {{ t("video.edge.detail") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_video:edge:update']"
                  icon="edit"
                  type="primary"
                  size="small"
                  link
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  {{ t("video.common.edit") }}
                </el-button>
                <el-button
                  v-hasPerm="['module_video:edge:delete']"
                  icon="delete"
                  type="danger"
                  size="small"
                  link
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
      width="620px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item
          :label="t('video.edge.deviceName')"
          prop="name"
          :rules="[{ required: true, message: t('video.edge.enterDeviceName'), trigger: 'blur' }]"
        >
          <el-input v-model="formData.name" :placeholder="t('video.edge.nameExample')" />
        </el-form-item>
        <el-form-item
          :label="t('video.edge.deviceCode')"
          prop="code"
          :rules="[{ required: true, message: t('video.edge.enterDeviceCode'), trigger: 'blur' }]"
        >
          <el-input v-model="formData.code" :placeholder="t('video.edge.codeExample')" />
        </el-form-item>
        <el-form-item :label="t('video.edge.controlUrl')" prop="control_url">
          <el-input
            v-model="formData.control_url"
            :placeholder="t('video.edge.controlUrlExample')"
          />
        </el-form-item>
        <el-form-item :label="t('video.edge.authSecret')" prop="secret">
          <el-input
            v-model="formData.secret"
            type="password"
            show-password
            :placeholder="
              dialogVisible.type === 'update'
                ? t('video.edge.leaveBlank')
                : t('video.edge.agentSecret')
            "
          />
        </el-form-item>
        <el-form-item :label="t('video.edge.remark')" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">{{ t("video.common.cancel") }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ t("video.common.save") }}
        </el-button>
      </template>
    </EnhancedDialog>

    <el-drawer v-model="detailDrawer.visible" :title="t('video.edge.edgeDetail')" size="560px">
      <template v-if="detailDrawer.data">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item :label="t('video.common.name')">
            {{ detailDrawer.data.name }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.edge.deviceCode')">
            {{ detailDrawer.data.code }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.common.status')">
            <el-tag :type="statusTag(detailDrawer.data.status)" size="small">
              {{ statusLabel(detailDrawer.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.edge.controlUrl')">
            {{ detailDrawer.data.control_url || "-" }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.edge.lastHeartbeat')">
            {{ detailDrawer.data.last_heartbeat || "-" }}
          </el-descriptions-item>
        </el-descriptions>
        <EdgeCapabilityPanel
          class="edge-detail-cap"
          :capabilities="detailDrawer.data.capabilities"
          :metrics="detailDrawer.data.metrics"
        />
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  getEdgeDeviceList,
  getEdgeDeviceDetail,
  createEdgeDevice,
  updateEdgeDevice,
  deleteEdgeDevice,
} from "@/api/module_video/edge";
import EdgeCapabilityPanel from "@/components/Edge/EdgeCapabilityPanel.vue";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const { t } = useI18n();

const submitLoading = ref(false);
const dataFormRef = ref();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:edge",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("video.edge.deviceName"),
      type: "input",
      attrs: {
        placeholder: t("video.edge.deviceName"),
        clearable: true,
        style: { width: "180px" },
      },
    },
    {
      prop: "status",
      label: t("video.common.status"),
      type: "select",
      options: [
        { label: t("video.common.online"), value: "online" },
        { label: t("video.common.offline"), value: "offline" },
        { label: t("video.edge.busy"), value: "busy" },
        { label: t("video.common.abnormal"), value: "error" },
      ],
      attrs: { placeholder: t("video.common.all"), clearable: true, style: { width: "120px" } },
    },
  ],
});

const edgeCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:edge",
  pk: "id",
  cols: edgeCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getEdgeDeviceList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteEdgeDevice(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { type: "warning" },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: "",
  code: "",
  control_url: undefined as string | undefined,
  secret: undefined as string | undefined,
  description: undefined as string | undefined,
});

const initialFormData = { ...formData };

const detailDrawer = reactive<{ visible: boolean; data: any }>({ visible: false, data: null });

function statusTag(status: string): "success" | "info" | "warning" | "danger" {
  if (status === "online") return "success";
  if (status === "busy") return "warning";
  if (status === "error") return "danger";
  return "info";
}

function statusLabel(status: string): string {
  return (
    {
      online: t("video.common.online"),
      offline: t("video.common.offline"),
      busy: t("video.edge.busy"),
      error: t("video.common.abnormal"),
    }[status] ||
    status ||
    t("video.common.unknown")
  );
}

function runningOf(row: any): number | string {
  const m = row?.metrics || {};
  return m.running_channels ?? m.running ?? "-";
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

async function handleViewDetail(row: any) {
  detailDrawer.data = row;
  detailDrawer.visible = true;
  try {
    const res = await getEdgeDeviceDetail(row.id);
    if (res.data?.data) detailDrawer.data = res.data.data;
  } catch {
    /* 保留列表行数据 */
  }
}

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
    dialogVisible.title = t("video.edge.editDevice");
    const res = await getEdgeDeviceDetail(id);
    const item = res.data?.data;
    if (item) {
      formData.id = item.id;
      formData.name = item.name;
      formData.code = item.code;
      formData.control_url = item.control_url;
      formData.description = item.description;
      formData.secret = undefined;
    }
  } else {
    dialogVisible.title = t("video.edge.addDevice");
    await resetForm();
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    submitLoading.value = true;
    const id = formData.id;
    const payload: any = {
      name: formData.name,
      code: formData.code,
      control_url: formData.control_url || null,
      description: formData.description || null,
    };
    if (formData.secret) payload.secret = formData.secret;
    try {
      if (id) {
        await updateEdgeDevice(id, payload);
      } else {
        await createEdgeDevice(payload);
      }
      ElMessage.success(t("video.common.saveSuccess"));
      dialogVisible.visible = false;
      await resetForm();
      refreshList();
    } finally {
      submitLoading.value = false;
    }
  });
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

async function pollDevices() {
  if (document.hidden || dialogVisible.visible) return;
  try {
    await refreshList();
  } catch {
    /* 轮询失败静默 */
  }
}

onBeforeMount(() => {
  pollTimer = setInterval(pollDevices, 15_000);
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
});
</script>

<style scoped>
.edge-detail-cap {
  margin-top: 12px;
}
</style>
