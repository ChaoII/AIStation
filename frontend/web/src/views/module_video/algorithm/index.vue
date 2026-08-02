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
            :perm-create="['module_video:algorithm:create']"
            :perm-delete="['module_video:algorithm:delete']"
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
      <ElForm ref="dataFormRef" :model="formData" label-width="110px">
        <div class="form-section-title">基础信息</div>
        <ElFormItem label="算法名称" prop="name"><ElInput v-model="formData.name" placeholder="请输入算法名称" /></ElFormItem>
        <ElRow :gutter="16">
          <ElCol :span="12"><ElFormItem label="编码" prop="code"><ElInput v-model="formData.code" placeholder="唯一编码" /></ElFormItem></ElCol>
          <ElCol :span="12">
            <ElFormItem label="算法类型" prop="algorithm_type">
              <ElSelect v-model="formData.algorithm_type" style="width:100%">
                <ElOption v-for="(label, val) in algoTypeOpts" :key="val" :label="label" :value="val" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>
        <ElFormItem label="版本" prop="version"><ElInput v-model="formData.version" placeholder="1.0.0" style="width:200px" /></ElFormItem>

        <div class="form-section-title">模型文件与配置</div>
        <ElFormItem label="模型文件" prop="model_path"><ElInput v-model="formData.model_path" placeholder="模型文件路径" /></ElFormItem>
        <ElFormItem label="插件路径" prop="plugin_path"><ElInput v-model="formData.plugin_path" placeholder="C++ SDK 插件路径（可选）" /></ElFormItem>
        <ElFormItem label="配置文件">
          <div class="config-toolbar">
            <ElButton size="small" @click="formatConfigJson">格式化</ElButton>
          </div>
        </ElFormItem>
        <ElFormItem label="配置内容">
          <ElInput v-model="configJson" type="textarea" :rows="10" style="width:100%" placeholder="JSON 配置内容" />
        </ElFormItem>

        <div class="form-section-title">其他</div>
        <ElFormItem label="状态" prop="status"><ElSwitch v-model="formData.status" /></ElFormItem>
        <ElFormItem label="描述" prop="description"><ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选描述" /></ElFormItem>
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

defineOptions({ name: "VideoAlgorithm", inheritAttrs: false });

const { hasAuth } = useAuth();
const algoTypeOpts: Record<string, string> = {
  INTRUSION: "入侵检测", LINE_CROSSING: "越界检测", FACE_DETECT: "人脸识别", CROWD_COUNT: "人数统计",
  FIRE_SMOKE: "烟火检测", VEHICLE_DETECT: "车辆识别", BEHAVIOR_ANALYSIS: "行为分析", OBJECT_LEFT: "物品遗留",
};

function buildRowActions(row: any, ctx: { onEdit: (id: number) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const all: TableOperationAction[] = [
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_video:algorithm:update", run: () => ctx.onEdit(row.id!) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:algorithm:delete", run: () => ctx.onDelete(row.id!) },
  ];
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; algorithm_type?: string }>({ name: undefined, algorithm_type: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};
const searchItems = computed<SearchFormItem[]>(() => [
  { label: "算法名称", key: "name", type: "input", placeholder: "请输入算法名称", clearable: true, span: 6 },
  { label: "算法类型", key: "algorithm_type", type: "select", props: { placeholder: "请选择算法类型", clearable: true, options: Object.entries(algoTypeOpts).map(([value, label]) => ({ label, value })) }, span: 6 },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteAlgorithm([id]);
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
    await VideoAPI.deleteAlgorithm(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ } finally { batchDeleting.value = false; }
}

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  code: undefined as string | undefined,
  version: "1.0.0",
  algorithm_type: "INTRUSION",
  model_path: undefined as string | undefined,
  plugin_path: undefined as string | undefined,
  config: undefined as Record<string, any> | undefined,
  status: true,
  description: undefined as string | undefined,
});
const configJson = ref("");
const initialFormData = { id: undefined, name: undefined, code: undefined, version: "1.0.0", algorithm_type: "INTRUSION", model_path: undefined, plugin_path: undefined, config: undefined, status: true, description: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);

function formatConfigJson() {
  try {
    if (configJson.value.trim()) configJson.value = JSON.stringify(JSON.parse(configJson.value), null, 2);
  } catch { ElMessage.warning("JSON 格式错误"); }
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑算法";
    const res = await VideoAPI.listAlgorithm({ page_no: 1, page_size: 100 });
    const item = (res.data?.data?.items || []).find((i: any) => i.id === id);
    if (item) {
      Object.assign(formData, item);
      configJson.value = item.config ? JSON.stringify(item.config, null, 2) : "";
    }
  } else {
    dialogVisible.title = "新建算法";
    Object.assign(formData, initialFormData);
    configJson.value = "";
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    const payload = { ...formData };
    if (configJson.value.trim()) {
      try { payload.config = JSON.parse(configJson.value); }
      catch { ElMessage.warning("配置 JSON 格式错误，已忽略"); payload.config = {}; }
    }
    if (id) await VideoAPI.updateAlgorithm(id, payload);
    else await VideoAPI.createAlgorithm(payload);
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
    apiFn: VideoAPI.listAlgorithm,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "算法名称", minWidth: 160, showOverflowTooltip: true },
      { prop: "code", label: "编码", width: 140 },
      { prop: "version", label: "版本", width: 90, align: "center" },
      { prop: "algorithm_type", label: "算法类型", width: 120, formatter: (row: any) => algoTypeOpts[row.algorithm_type] || row.algorithm_type || "—" },
      { prop: "status", label: "状态", width: 80, align: "center", formatter: (row: any) => h(ElTag, { type: row.status ? "success" : "info", size: "small" }, () => row.status ? "启用" : "停用") },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation", label: "操作", width: 140, fixed: "right", align: "right",
        formatter: (row: any) => renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string; algorithm_type?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, algorithm_type: undefined };
  void resetSearchParams();
}
</script>

<style scoped>
.form-section-title { font-weight: 600; font-size: 13px; color: #303133; margin: 12px 0 8px; border-bottom: 1px solid #ebeef5; padding-bottom: 6px; }
.config-toolbar { display: flex; gap: 8px; }
</style>
