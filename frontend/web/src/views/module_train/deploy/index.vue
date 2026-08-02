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
      <FaTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <FaTableHeaderLeft
            :remove-ids="selectedIds"
            :perm-create="['module_train:model:query']"
            :perm-delete="['module_train:model:delete']"
            :delete-loading="batchDeleting"
            @add="showCreateDialog = true"
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

    <ElDialog v-model="showCreateDialog" title="新建部署" width="500px">
      <ElForm label-width="120px">
        <ElFormItem label="选择模型" required>
          <ElSelect v-model="createForm.modelId" filterable style="width:100%" placeholder="选择模型版本">
            <ElOption v-for="m in models" :key="m.id" :label="`${m.name} v${m.version}`" :value="m.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="部署名称">
          <ElInput v-model="createForm.name" placeholder="留空自动生成" />
        </ElFormItem>
        <ElFormItem label="GPU 设备">
          <ElInput v-model="createForm.device" placeholder="如: 0 或 cpu" />
        </ElFormItem>
        <ElFormItem label="端口">
          <ElInputNumber v-model="createForm.hostPort" :min="9001" :max="9999" />
        </ElFormItem>
        <ElDivider>推理参数</ElDivider>
        <ElFormItem label="conf"><ElInputNumber v-model="createForm.hyperparams.conf" :min="0.01" :max="1" :step="0.05" /></ElFormItem>
        <ElFormItem label="iou"><ElInputNumber v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" /></ElFormItem>
        <ElFormItem label="imgsz"><ElInputNumber v-model="createForm.hyperparams.imgsz" :min="32" :step="32" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="showCreateDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="creating" @click="handleCreate">创建</ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="showKeyDialog" title="部署成功" width="480px" :close-on-click-modal="false">
      <ElAlert type="success" :title="'API URL: ' + (keyInfo.apiUrl || '待启动')" show-icon style="margin-bottom:16px" />
      <div style="margin-bottom:8px;font-weight:600">API Key（请立即复制，关闭后不再显示）：</div>
      <ElInput v-model="keyInfo.apiKey" readonly style="font-family:monospace">
        <template #append>
          <ElButton @click="copyText(keyInfo.apiKey)">复制</ElButton>
        </template>
      </ElInput>
      <template #footer>
        <ElButton type="primary" @click="showKeyDialog = false">我已保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h } from "vue";
import { ElMessage, ElMessageBox, ElTag } from "element-plus";
import { useTable } from "@/hooks/core/useTable";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { cleanEmptyArrayParams } from "@/utils/query";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import type { ColumnOption } from "@/types/component";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import { TrainAPI, type TrainDeployTable, type TablePageQuery } from "@/api/module_train";

defineOptions({ name: "TrainDeploy", inheritAttrs: false });

const { hasAuth } = useAuth();

const models = ref<any[]>([]);
const creating = ref(false);
const showCreateDialog = ref(false);
const showKeyDialog = ref(false);
const keyInfo = reactive({ apiKey: "", apiUrl: "" });

const createForm = reactive({
  modelId: null as number | null,
  name: "",
  device: "0",
  hostPort: null as number | null,
  hyperparams: { conf: 0.25, iou: 0.45, imgsz: 640 },
});

TrainAPI.listModel({ page_no: 1, page_size: 100 })
  .then(r => { models.value = r.data?.data?.items || []; })
  .catch(() => {});

function statusTag(s?: string) {
  const map: Record<string, { type: "info" | "success" | "warning" | "danger"; text: string }> = {
    pending: { type: "info", text: "待部署" },
    deploying: { type: "warning", text: "部署中" },
    running: { type: "success", text: "运行中" },
    stopped: { type: "info", text: "已停止" },
    failed: { type: "danger", text: "失败" },
  };
  const c = map[s || ""] || { type: "info" as const, text: s || "—" };
  return h(ElTag, { type: c.type }, () => c.text);
}

async function handleCreate() {
  if (!createForm.modelId) { ElMessage.warning("请选择模型"); return; }
  creating.value = true;
  try {
    const r = await TrainAPI.createDeploy({
      model_id: createForm.modelId,
      name: createForm.name || undefined,
      device: createForm.device || "0",
      host_port: createForm.hostPort || undefined,
      hyperparams: createForm.hyperparams,
    });
    const d = r.data?.data;
    keyInfo.apiKey = d?.api_key || "";
    keyInfo.apiUrl = d?.api_url || "";
    showCreateDialog.value = false;
    showKeyDialog.value = true;
    createForm.modelId = null;
    createForm.name = "";
    createForm.device = "0";
    createForm.hostPort = null;
    createForm.hyperparams = { conf: 0.25, iou: 0.45, imgsz: 640 };
    await refreshData();
  } finally {
    creating.value = false;
  }
}

function copyText(t: string) {
  navigator.clipboard.writeText(t).then(() => ElMessage.success("已复制")).catch(() => ElMessage.warning("复制失败，请手动复制"));
}

function buildRowActions(
  row: TrainDeployTable,
  ctx: { onDeploy: (id: number) => void; onStop: (id: number) => void; onRenew: (id: number) => void; onDelete: (id: number) => void }
): TableOperationAction[] {
  const actions: TableOperationAction[] = [];
  if (row.status === "pending") {
    actions.push({
      key: "deploy",
      label: "部署",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      run: () => ctx.onDeploy(row.id!),
    });
  }
  if (row.status === "running") {
    actions.push({
      key: "stop",
      label: "停止",
      artType: "view",
      icon: "ri:stop-circle-line",
      iconColor: "var(--el-color-danger)",
      run: () => ctx.onStop(row.id!),
    });
    actions.push({
      key: "renew",
      label: "更新Key",
      artType: "view",
      icon: "ri:key-2-line",
      run: () => ctx.onRenew(row.id!),
    });
  }
  if (row.status === "failed" || row.status === "stopped") {
    actions.push({
      key: "redeploy",
      label: "重新部署",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      run: () => ctx.onDeploy(row.id!),
    });
  }
  actions.push({
    key: "delete",
    label: "删除",
    artType: "delete",
    icon: "ri:delete-bin-4-line",
    perm: "module_train:model:delete",
    run: () => ctx.onDelete(row.id!),
  });
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; status?: string }>({ name: undefined, status: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "部署名称", key: "name", type: "input", placeholder: "请输入部署名称", clearable: true, span: 6 },
  {
    label: "状态",
    key: "status",
    type: "select",
    props: { placeholder: "请选择状态", clearable: true, options: [
      { label: "待部署", value: "pending" },
      { label: "部署中", value: "deploying" },
      { label: "运行中", value: "running" },
      { label: "已停止", value: "stopped" },
      { label: "失败", value: "failed" },
    ] },
    span: 6,
  },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<TrainDeployTable>();

async function deploy(id: number) {
  try {
    await TrainAPI.startDeploy(id);
    ElMessage.success("部署已启动");
    await refreshData();
  } catch (e: any) {
    ElMessage.error(e?.msg || "部署失败");
  }
}
async function stopDeploy(id: number) {
  try {
    await ElMessageBox.confirm("确定停止该部署？", "提示", { type: "warning" });
    await TrainAPI.stopDeploy(id);
    ElMessage.success("部署已停止");
    await refreshData();
  } catch {
    // cancel
  }
}
async function renewKey(id: number) {
  try {
    const r = await TrainAPI.renewDeployKey(id);
    const newKey = r.data?.data?.api_key;
    if (newKey) {
      keyInfo.apiKey = newKey;
      keyInfo.apiUrl = "";
      showKeyDialog.value = true;
    }
    await refreshData();
  } catch {
    // ignore
  }
}
async function deleteDeployRow(id: number) {
  try {
    await confirmDelete();
    await TrainAPI.deleteDeploy([id]);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  }
}
async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    batchDeleting.value = true;
    await TrainAPI.deleteDeploy(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  } finally {
    batchDeleting.value = false;
  }
}

const opCtx = {
  onDeploy: deploy,
  onStop: stopDeploy,
  onRenew: renewKey,
  onDelete: deleteDeployRow,
};

const { columns, columnChecks, data, loading, pagination, searchParams, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshCreate, refreshUpdate, refreshRemove } = useTable({
  core: {
    apiFn: TrainAPI.listDeploy,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<TrainDeployTable>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "部署名称", minWidth: 160, showOverflowTooltip: true },
      { prop: "model_name", label: "模型", minWidth: 120, showOverflowTooltip: true },
      { prop: "model_version", label: "版本", width: 80 },
      { prop: "framework", label: "框架", width: 100, formatter: (row: TrainDeployTable) => h(ElTag, { type: row.framework === "ultralytics" ? "success" : "primary" }, () => row.framework === "ultralytics" ? "YOLO" : "PaddleX") },
      { prop: "api_url", label: "API URL", minWidth: 180, showOverflowTooltip: true, formatter: (row: TrainDeployTable) => row.api_url ? h("span", { style: "font-family:monospace;font-size:12px" }, row.api_url) : "—" },
      { prop: "host_port", label: "端口", width: 80 },
      { prop: "status", label: "状态", width: 100, formatter: (row: TrainDeployTable) => statusTag(row.status) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 220,
        fixed: "right",
        align: "right",
        formatter: (row: TrainDeployTable) =>
          renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string; status?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, status: undefined };
  void resetSearchParams();
}
</script>
