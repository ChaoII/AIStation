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
              <el-empty :image-size="80" description="暂无数据" />
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
              label="序号"
              width="60"
              align="center"
            />
            <el-table-column label="设备名称" prop="name" min-width="130" show-overflow-tooltip />
            <el-table-column label="设备编码" prop="code" min-width="130" show-overflow-tooltip />
            <el-table-column label="状态" width="100" align="center">
              <template #default="scope">
                <el-tag :type="statusTag(scope.row.status)" size="small">
                  {{ statusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="在跑/上限" width="110" align="center">
              <template #default="scope">
                {{ runningOf(scope.row) }} / {{ scope.row.capabilities?.max_channels ?? "-" }}
              </template>
            </el-table-column>
            <el-table-column
              label="最后心跳"
              prop="last_heartbeat"
              width="170"
              show-overflow-tooltip
            />
            <el-table-column
              label="控制地址"
              prop="control_url"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="edgeCols.find((c) => c.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="160"
            >
              <template #default="scope">
                <el-button type="primary" size="small" link @click="handleViewDetail(scope.row)">
                  详情
                </el-button>
                <el-button
                  v-hasPerm="['module_video:edge:update']"
                  type="primary"
                  size="small"
                  link
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:edge:delete']"
                  type="danger"
                  size="small"
                  link
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
      width="620px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item
          label="设备名称"
          prop="name"
          :rules="[{ required: true, message: '请输入设备名称', trigger: 'blur' }]"
        >
          <el-input v-model="formData.name" placeholder="如：一号车间边缘盒" />
        </el-form-item>
        <el-form-item
          label="设备编码"
          prop="code"
          :rules="[{ required: true, message: '请输入设备编码', trigger: 'blur' }]"
        >
          <el-input v-model="formData.code" placeholder="唯一编码，如 edge-01" />
        </el-form-item>
        <el-form-item label="控制地址" prop="control_url">
          <el-input v-model="formData.control_url" placeholder="http://192.168.1.10:8080" />
        </el-form-item>
        <el-form-item label="鉴权密钥" prop="secret">
          <el-input
            v-model="formData.secret"
            type="password"
            show-password
            :placeholder="dialogVisible.type === 'update' ? '留空表示不变更' : 'Agent 控制面密钥'"
          />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <el-drawer v-model="detailDrawer.visible" title="边缘设备详情" size="560px">
      <template v-if="detailDrawer.data">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="名称">{{ detailDrawer.data.name }}</el-descriptions-item>
          <el-descriptions-item label="编码">{{ detailDrawer.data.code }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(detailDrawer.data.status)" size="small">
              {{ statusLabel(detailDrawer.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="控制地址">
            {{ detailDrawer.data.control_url || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="最后心跳">
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
      label: "设备名称",
      type: "input",
      attrs: { placeholder: "设备名称", clearable: true, style: { width: "180px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "在线", value: "online" },
        { label: "离线", value: "offline" },
        { label: "繁忙", value: "busy" },
        { label: "异常", value: "error" },
      ],
      attrs: { placeholder: "全部", clearable: true, style: { width: "120px" } },
    },
  ],
});

const edgeCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "operation", label: "操作", show: true },
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
  deleteConfirm: { title: "警告", message: "确认删除该边缘设备?", type: "warning" },
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
    { online: "在线", offline: "离线", busy: "繁忙", error: "异常" }[status] || status || "未知"
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
    dialogVisible.title = "编辑边缘设备";
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
    dialogVisible.title = "新增边缘设备";
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
