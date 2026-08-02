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
            :perm-create="['module_video:layout:create']"
            :perm-delete="['module_video:layout:delete']"
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

    <ElDialog v-model="dialogVisible.visible" :title="dialogVisible.title" width="540px" :close-on-click-modal="false">
      <ElForm ref="dataFormRef" :model="formData" label-width="100px">
        <ElFormItem label="布局名称" prop="name"><ElInput v-model="formData.name" placeholder="例如：4路默认" /></ElFormItem>
        <ElFormItem label="画面数" prop="grid_type">
          <div class="grid-type-picker">
            <button v-for="g in gridOptions" :key="g.value" class="grid-type-btn" :class="{ active: formData.grid_type === g.value }" type="button" @click="formData.grid_type = g.value">
              <div class="grid-type-mini" v-html="layoutSvg(g.value)" />
              <span>{{ g.label }}</span>
            </button>
          </div>
        </ElFormItem>
        <ElFormItem label="设为默认"><ElSwitch v-model="formData.is_default" /></ElFormItem>
        <ElFormItem label="标记为模板"><ElSwitch v-model="formData.is_template" /></ElFormItem>
        <ElFormItem label="轮巡间隔" prop="patrol_interval">
          <div style="display:flex;align-items:center;gap:8px">
            <ElInputNumber v-model="formData.patrol_interval" :min="0" :max="3600" :step="5" controls-position="right" style="width:140px" />
            <span style="font-size:12px;color:var(--el-text-color-placeholder)">秒（0 表示不轮巡）</span>
          </div>
        </ElFormItem>
        <ElFormItem label="备注" prop="description"><ElInput v-model="formData.description" type="textarea" :rows="2" placeholder="可选描述" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="dialogVisible.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">保存</ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="previewVisible" :title="previewTitle" width="660px" :close-on-click-modal="false">
      <div class="preview-grid" :style="previewGridStyle()">
        <div v-for="i in previewCount" :key="i" class="preview-cell" :class="{ 'preview-cell-occupied': previewWindows[`w${i}`], 'preview-cell-empty': !previewWindows[`w${i}`] }">
          <div v-if="previewWindows[`w${i}`]" class="preview-cell-inner">
            <span class="preview-cell-name">{{ cameraName(previewWindows[`w${i}`]) }}</span>
            <span class="preview-cell-id">#{{ previewWindows[`w${i}`] }}</span>
          </div>
          <div v-else class="preview-cell-inner"><span class="preview-cell-empty-icon">空</span></div>
          <div class="preview-cell-edit">
            <ElSelect v-model="previewWindows[`w${i}`]" placeholder="选择摄像机" size="small" clearable filterable style="width:100%" @change="(v: any) => onWindowChange(i, v)">
              <ElOption v-for="c in allCameras" :key="c.id" :label="c.name" :value="c.id" />
            </ElSelect>
          </div>
        </div>
      </div>
      <template #footer>
        <ElButton @click="previewVisible = false">关闭</ElButton>
        <ElButton type="primary" :loading="savingWindows" @click="handleSaveWindows">保存窗口分配</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, h } from "vue";
import { useRouter } from "vue-router";
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

defineOptions({ name: "VideoLayout", inheritAttrs: false });

const router = useRouter();
const { hasAuth } = useAuth();
const allCameras = ref<any[]>([]);

const gridOptions = [
  { label: "1路", value: "1" }, { label: "4路", value: "4" }, { label: "6路", value: "6" },
  { label: "8路", value: "8" }, { label: "9路", value: "9" }, { label: "13路", value: "13" }, { label: "16路", value: "16" },
];
function gridCols(type: string): number {
  return ({ "1": 1, "4": 2, "6": 3, "8": 4, "9": 3, "13": 4, "16": 4 } as any)[type] || 2;
}
const svgPreviews: Record<string, string> = {
  "1": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="15" height="15" rx="1.5" fill="currentColor"/></svg>',
  "4": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="7" height="7" rx="1" fill="currentColor"/><rect x="8.5" y="0.5" width="7" height="7" rx="1" fill="currentColor"/><rect x="0.5" y="8.5" width="7" height="7" rx="1" fill="currentColor"/><rect x="8.5" y="8.5" width="7" height="7" rx="1" fill="currentColor"/></svg>',
  "6": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="10" height="10" rx="1.5" fill="currentColor"/><rect x="11.5" y="0.5" width="4" height="4.3" rx="0.8" fill="currentColor"/><rect x="11.5" y="5.8" width="4" height="4.3" rx="0.8" fill="currentColor"/><rect x="0.5" y="11.5" width="4.3" height="4" rx="0.8" fill="currentColor"/><rect x="5.8" y="11.5" width="4.3" height="4" rx="0.8" fill="currentColor"/><rect x="11.2" y="11.5" width="4.3" height="4" rx="0.8" fill="currentColor"/></svg>',
  "8": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="11.5" height="11.5" rx="1.5" fill="currentColor"/><rect x="12.8" y="0.5" width="2.8" height="3.3" rx="0.8" fill="currentColor"/><rect x="12.8" y="4.8" width="2.8" height="3.3" rx="0.8" fill="currentColor"/><rect x="12.8" y="9.2" width="2.8" height="3.3" rx="0.8" fill="currentColor"/><rect x="0.5" y="12.8" width="3.3" height="2.8" rx="0.8" fill="currentColor"/><rect x="4.8" y="12.8" width="3.3" height="2.8" rx="0.8" fill="currentColor"/><rect x="9.2" y="12.8" width="3.3" height="2.8" rx="0.8" fill="currentColor"/><rect x="12.8" y="12.8" width="2.8" height="2.8" rx="0.8" fill="currentColor"/></svg>',
  "9": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="5.8" y="0.5" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="11.2" y="0.5" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="0.5" y="5.8" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="5.8" y="5.8" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="11.2" y="5.8" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="0.5" y="11.2" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="5.8" y="11.2" width="4.3" height="4.3" rx="1" fill="currentColor"/><rect x="11.2" y="11.2" width="4.3" height="4.3" rx="1" fill="currentColor"/></svg>',
  "13": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="4.5" width="7" height="7" rx="1.5" fill="currentColor"/><rect x="12.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/></svg>',
  "16": '<svg width="60" height="40" viewBox="0 0 16 16"><rect x="0.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="0.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="4.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="8.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="0.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="4.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="8.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/><rect x="12.5" y="12.5" width="3" height="3" rx="0.8" fill="currentColor"/></svg>',
};
function layoutSvg(type: string): string {
  return svgPreviews[type] || svgPreviews["4"];
}

function buildRowActions(row: any, ctx: { onPreview: (row: any) => void; onApply: (row: any) => void; onBig: (row: any) => void; onEdit: (id: number) => void; onDuplicate: (row: any) => void; onDefault: (row: any) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const all: TableOperationAction[] = [
    { key: "preview", label: "预览", artType: "view", icon: "ri:eye-line", run: () => ctx.onPreview(row) },
    { key: "apply", label: "应用", artType: "view", icon: "ri:play-circle-line", iconColor: "var(--el-color-success)", run: () => ctx.onApply(row) },
    { key: "big", label: "大屏", artType: "view", icon: "ri:tv-2-line", run: () => ctx.onBig(row) },
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", run: () => ctx.onEdit(row.id!) },
    { key: "duplicate", label: "复制", artType: "view", icon: "ri:file-copy-line", run: () => ctx.onDuplicate(row) },
  ];
  if (!row.is_default) all.push({ key: "default", label: "设为默认", artType: "view", icon: "ri:star-line", run: () => ctx.onDefault(row) });
  all.push({ key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:layout:delete", run: () => ctx.onDelete(row.id!) });
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const searchForm = ref<{ name?: string; grid_type?: string }>({ name: undefined, grid_type: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};
const searchItems = computed<SearchFormItem[]>(() => [
  { label: "布局名称", key: "name", type: "input", placeholder: "请输入布局名称", clearable: true, span: 6 },
  { label: "画面数", key: "grid_type", type: "select", props: { placeholder: "请选择画面数", clearable: true, options: gridOptions }, span: 6 },
]);

const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<any>();

async function deleteRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteLayout([id]);
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
    await VideoAPI.deleteLayout(ids);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch { /* cancel */ } finally { batchDeleting.value = false; }
}

const previewVisible = ref(false);
const previewTitle = ref("");
const previewCount = ref(4);
const previewWindows = ref<Record<string, number>>({});
const previewLayoutId = ref<number | null>(null);
const savingWindows = ref(false);
function previewGridStyle() {
  const cols = gridCols(String(previewCount.value));
  const is169 = previewCount.value === 6 || previewCount.value === 8;
  const rows = is169 ? 2 : Math.ceil(previewCount.value / cols);
  return { display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)`, gap: "8px", aspectRatio: `${is169 ? 16 : cols} / ${is169 ? 9 : rows}`, maxHeight: "420px" } as any;
}
function cameraName(id: number): string {
  const cam = allCameras.value.find((c: any) => c.id === id);
  return cam ? cam.name : `#${id}`;
}
function handlePreview(row: any) {
  previewCount.value = Number(row.grid_type) || 4;
  previewTitle.value = row.name;
  previewLayoutId.value = row.id;
  previewWindows.value = { ...(row.layout_config?.windows || {}) };
  previewVisible.value = true;
}
function onWindowChange(index: number, value: number | undefined) {
  if (value === undefined || value === null) delete previewWindows.value[`w${index}`];
  else previewWindows.value[`w${index}`] = value;
}
async function handleSaveWindows() {
  if (!previewLayoutId.value) return;
  savingWindows.value = true;
  try {
    await VideoAPI.updateLayout(previewLayoutId.value, { layout_config: { windows: { ...previewWindows.value }, grid_type: String(previewCount.value) } });
    ElMessage.success("窗口分配已保存");
    previewVisible.value = false;
    await refreshData();
  } catch { /* ignore */ } finally { savingWindows.value = false; }
}

function handleApply(row: any) { router.push({ path: "/video/live", query: { layout_id: row.id } }); }
function handleBig(row: any) { ElMessage.info("大屏功能请访问实时预览页"); }

const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const formData = reactive({ id: undefined as number | undefined, name: undefined as string | undefined, grid_type: "4", is_default: false, description: undefined as string | undefined, is_template: false, patrol_interval: undefined as number | undefined });
const initialFormData = { id: undefined, name: undefined, grid_type: "4", is_default: false, description: undefined, is_template: false, patrol_interval: undefined };
const dataFormRef = ref<any>(null);
const submitLoading = ref(false);

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑布局";
    const res = await VideoAPI.listLayout({ page_no: 1, page_size: 100 });
    const item = (res.data?.data?.items || []).find((i: any) => i.id === id);
    if (item) Object.assign(formData, item);
  } else {
    dialogVisible.title = "新建布局";
    Object.assign(formData, initialFormData);
  }
  dialogVisible.visible = true;
}
async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    if (id) await VideoAPI.updateLayout(id, { ...formData });
    else await VideoAPI.createLayout({ ...formData });
    ElMessage.success("保存成功");
    dialogVisible.visible = false;
    await refreshData();
  } catch { /* ignore */ } finally { submitLoading.value = false; }
}

const opCtx = {
  onPreview: handlePreview,
  onApply: handleApply,
  onBig: handleBig,
  onEdit: (id: number) => void handleOpenDialog("update", id),
  onDuplicate: async (row: any) => {
    await VideoAPI.createLayout({ name: `${row.name} (副本)`, grid_type: row.grid_type, layout_config: row.layout_config, is_default: false, is_template: false, description: row.description });
    ElMessage.success("已复制布局");
    await refreshData();
  },
  onDefault: async (row: any) => {
    await VideoAPI.updateLayout(row.id, { is_default: true });
    ElMessage.success("已设为默认布局");
    await refreshData();
  },
  onDelete: deleteRow,
};

const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshRemove } = useTable({
  core: {
    apiFn: VideoAPI.listLayout,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "布局名称", minWidth: 140, showOverflowTooltip: true },
      { prop: "grid_type", label: "画面数", width: 80, align: "center", formatter: (row: any) => `${row.grid_type}路` },
      { prop: "preview", label: "预览", width: 120, align: "center", formatter: (row: any) => h("span", { class: "preview-svg", innerHTML: layoutSvg(row.grid_type) }) },
      { prop: "is_template", label: "模板", width: 60, align: "center", formatter: (row: any) => row.is_template ? h(ElTag, { type: "warning", size: "small" }, () => "模板") : "—" },
      { prop: "is_default", label: "默认", width: 60, align: "center", formatter: (row: any) => row.is_default ? h(ElTag, { type: "success", size: "small" }, () => "默认") : "—" },
      { prop: "patrol_interval", label: "轮巡", width: 80, align: "center", formatter: (row: any) => row.patrol_interval ? `${row.patrol_interval}s` : "—" },
      { prop: "description", label: "描述", minWidth: 140, showOverflowTooltip: true },
      {
        prop: "operation", label: "操作", width: 220, fixed: "right", align: "right",
        formatter: (row: any) => renderTableOperationCell(buildRowActions(row, opCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }),
      },
    ],
  },
});

function handleSearch(params: { name?: string; grid_type?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, grid_type: undefined };
  void resetSearchParams();
}

onMounted(() => {
  VideoAPI.listCamera({ page_size: 100 }).then(r => { allCameras.value = r.data?.data?.items || []; }).catch(() => {});
});
</script>

<style scoped>
.grid-type-picker { display: flex; gap: 8px; flex-wrap: wrap; }
.grid-type-btn { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 8px 8px 6px; cursor: pointer; color: var(--el-text-color-secondary); background: var(--el-fill-color); border: 1px solid var(--el-border-color); border-radius: 6px; transition: all 0.15s; min-width: 68px; }
.grid-type-btn:hover { border-color: var(--el-color-primary-light-5); }
.grid-type-btn.active { color: var(--el-color-primary); border-color: var(--el-color-primary); }
.grid-type-btn svg { display: block; width: 52px; height: 34px; color: var(--el-color-primary-light-3); }
.grid-type-btn.active svg { color: var(--el-color-primary); }
.grid-type-btn span { font-size: 11px; line-height: 1; }
.preview-svg { display: flex; justify-content: center; color: var(--el-color-primary); opacity: 0.5; }
.preview-grid { display: grid; gap: 8px; width: 100%; margin: 0 auto; }
.preview-cell { position: relative; border-radius: 6px; overflow: hidden; min-height: 80px; }
.preview-cell-occupied { background: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-5); }
.preview-cell-empty { background: var(--el-fill-color); border: 1px solid var(--el-border-color); }
.preview-cell-inner { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; position: absolute; inset: 0; padding: 4px; z-index: 1; pointer-events: none; }
.preview-cell-name { font-size: 13px; font-weight: 500; color: var(--el-text-color-primary); text-align: center; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.preview-cell-id { font-size: 10px; color: var(--el-text-color-placeholder); font-family: "SF Mono", monospace; }
.preview-cell-empty-icon { font-size: 12px; color: var(--el-text-color-disabled); }
.preview-cell-edit { position: absolute; bottom: 4px; left: 4px; right: 4px; z-index: 2; opacity: 0; transition: opacity 0.15s; }
.preview-cell:hover .preview-cell-edit { opacity: 1; }
</style>
