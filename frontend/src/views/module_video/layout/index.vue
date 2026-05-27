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
          :perm-create="['module_video:layout:create']"
          :perm-delete="['module_video:layout:delete']"
          :perm-patch="['module_video:layout:patch']"
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
            <template #empty><el-empty :image-size="80" description="暂无数据" /></template>
            <el-table-column v-if="contentCols.find((c) => c.prop === 'selection')?.show" type="selection" width="55" align="center" />
            <el-table-column v-if="contentCols.find((c) => c.prop === 'index')?.show" fixed label="序号" width="60">
              <template #default="scope">{{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}</template>
            </el-table-column>
            <el-table-column v-if="contentCols.find((c) => c.prop === 'name')?.show" key="name" label="布局名称" prop="name" min-width="140" show-overflow-tooltip />
            <el-table-column v-if="contentCols.find((c) => c.prop === 'grid_type')?.show" key="grid_type" label="画面数" width="100" align="center">
              <template #default="scope">{{ scope.row.grid_type }}路</template>
            </el-table-column>
            <el-table-column key="preview" label="预览" width="140" align="center">
              <template #default="scope">
                <div class="grid-mini" :style="miniGridStyle(scope.row.grid_type)">
                  <div v-for="i in Number(scope.row.grid_type)" :key="i" class="grid-mini-cell" />
                </div>
              </template>
            </el-table-column>
            <el-table-column v-if="contentCols.find((c) => c.prop === 'is_default')?.show" key="is_default" label="默认" width="80" align="center">
              <template #default="scope">
                <el-tag v-if="scope.row.is_default" type="success" size="small">默认</el-tag>
                <span v-else style="color:var(--el-text-color-placeholder)">-</span>
              </template>
            </el-table-column>
            <el-table-column v-if="contentCols.find((c) => c.prop === 'description')?.show" key="description" label="描述" prop="description" min-width="140" show-overflow-tooltip />
            <el-table-column v-if="contentCols.find((c) => c.prop === 'operation')?.show" fixed="right" label="操作" align="center" min-width="200">
              <template #default="scope">
                <el-button size="small" type="info" link icon="View" @click="handlePreview(scope.row)">预览</el-button>
                <el-button v-hasPerm="['module_video:layout:update']" type="primary" size="small" link icon="edit" @click="handleOpenDialog('update', scope.row.id)">编辑</el-button>
                <el-button v-hasPerm="['module_video:layout:delete']" type="danger" size="small" link icon="delete" @click="handleRowDelete(scope.row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog v-model="dialogVisible.visible" :title="dialogVisible.title" append-to-body width="500px" @close="handleCloseDialog">
      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item label="布局名称" prop="name">
          <el-input v-model="formData.name" placeholder="例如：4路默认" />
        </el-form-item>
        <el-form-item label="画面数" prop="grid_type">
          <div class="grid-type-picker">
            <button
              v-for="g in gridOptions" :key="g.value"
              class="grid-type-btn"
              :class="{ active: formData.grid_type === g.value }"
              @click="formData.grid_type = g.value"
            >
              <div class="grid-type-mini" :style="miniGridStyle(g.value)">
                <div v-for="i in Number(g.value)" :key="i" class="grid-type-cell" />
              </div>
              <span>{{ g.label }}</span>
            </button>
          </div>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="600px" destroy-on-close>
      <div class="preview-grid" :style="previewGridStyle()">
        <div
          v-for="i in previewCount" :key="i"
          class="preview-cell"
          :class="{ 'preview-cell-occupied': previewWindows[`w${i}`], 'preview-cell-empty': !previewWindows[`w${i}`] }"
        >
          <div class="preview-cell-inner">
            <template v-if="previewWindows[`w${i}`]">
              <span class="preview-cell-name">{{ cameraName(previewWindows[`w${i}`]) }}</span>
              <span class="preview-cell-id">#{{ previewWindows[`w${i}`] }}</span>
            </template>
            <template v-else>
              <span class="preview-cell-empty-icon">空</span>
            </template>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { getLayoutList, createLayout, updateLayout, deleteLayout } from "@/api/module_video/layout";
import { getCameraList } from "@/api/module_video/camera";
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

const gridOptions = [
  { label: "1路", value: "1" },
  { label: "4路", value: "4" },
  { label: "6路", value: "6" },
  { label: "8路", value: "8" },
  { label: "9路", value: "9" },
  { label: "16路", value: "16" },
];

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:layout",
  colon: true, isExpandable: true, showNumber: 2, form: { labelWidth: "auto" },
  formItems: [
    { prop: "name", label: "布局名称", type: "input", attrs: { placeholder: "请输入布局名称", clearable: true } },
    { prop: "grid_type", label: "画面数", type: "select",
      options: gridOptions,
      attrs: { placeholder: "请选择画面数", clearable: true, style: { width: "167.5px" } } },
  ],
});

const contentCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "布局名称", show: true },
  { prop: "grid_type", label: "画面数", show: true },
  { prop: "is_default", label: "默认布局", show: true },
  { prop: "description", label: "描述", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:layout",
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getLayoutList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteLayout(ids.split(",").map((s: string) => Number(s.trim())).filter((n: number) => !isNaN(n)));
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRowDelete(id: number) { contentRef.value?.handleDelete(id); }

// Grid column count per grid type
function gridCols(type: string): number {
  const m: Record<string, number> = { "1": 1, "4": 2, "6": 3, "8": 4, "9": 3, "16": 4 };
  return m[type] || 2;
}

function miniGridStyle(type: string) {
  const cols = gridCols(type);
  return { display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: "2px", width: "72px", height: "48px" };
}

// Preview dialog
const previewVisible = ref(false);
const previewTitle = ref("");
const previewCount = ref(4);
const previewWindows = ref<Record<string, number>>({});
const allCameras = ref<any[]>([]);

function previewGridStyle() {
  const cols = gridCols(String(previewCount.value));
  const is169 = previewCount.value === 6 || previewCount.value === 8;
  const rows = is169 ? 2 : Math.ceil(previewCount.value / cols);
  return {
    display: "grid",
    gridTemplateColumns: `repeat(${cols}, 1fr)`,
    gridTemplateRows: `repeat(${rows}, 1fr)`,
    gap: "8px",
    aspectRatio: `${is169 ? 16 : cols} / ${is169 ? 9 : rows}`,
    maxHeight: "420px",
  } as any;
}

function cameraName(id: number): string {
  const cam = allCameras.value.find((c: any) => c.id === id);
  return cam ? cam.name : `#${id}`;
}

function handlePreview(row: any) {
  previewCount.value = Number(row.grid_type) || 4;
  previewTitle.value = `${row.name}（${row.grid_type}路）`;
  previewWindows.value = row.layout_config?.windows || {};
  previewVisible.value = true;
}

// CRUD dialog
const dialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  grid_type: "4",
  is_default: false,
  description: undefined as string | undefined,
});

const initialFormData = { ...formData };

async function resetForm() {
  if (dataFormRef.value) { dataFormRef.value.resetFields(); dataFormRef.value.clearValidate(); }
  Object.assign(formData, initialFormData);
}

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 100 });
    allCameras.value = res.data?.data?.items || [];
  } catch {}
}

onMounted(() => {
  fetchCameras();
});

async function handleCloseDialog() { dialogVisible.visible = false; await resetForm(); }

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑布局";
    const res = await getLayoutList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) Object.assign(formData, item);
  } else {
    dialogVisible.title = "新建布局";
    formData.id = undefined;
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  submitLoading.value = true;
  const id = formData.id;
  try {
    if (id) await updateLayout(id, { ...formData, id });
    else await createLayout(formData);
    dialogVisible.visible = false;
    await resetForm();
    refreshList();
  } catch {}
  submitLoading.value = false;
}
</script>

<style scoped>
/* Grid type picker (dialog) */
.grid-type-picker { display: flex; gap: 8px; flex-wrap: wrap; }
.grid-type-btn {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 8px 6px 6px; cursor: pointer;
  background: var(--el-fill-color); border: 1px solid var(--el-border-color); border-radius: 6px;
  transition: all 0.15s; min-width: 64px;
}
.grid-type-btn:hover { border-color: var(--el-color-primary-light-5); }
.grid-type-btn.active { background: color-mix(in srgb, var(--el-color-primary) 8%, transparent); border-color: var(--el-color-primary); }
.grid-type-btn span { font-size: 11px; color: var(--el-text-color-secondary); }
.grid-type-btn.active span { color: var(--el-color-primary); font-weight: 500; }
.grid-type-mini { display: grid; gap: 2px; width: 44px; height: 32px; }
.grid-type-cell { background: var(--el-border-color); border-radius: 1px; }
.grid-type-btn.active .grid-type-cell { background: var(--el-color-primary-light-5); }

/* Mini grid in table */
.grid-mini { display: grid; gap: 2px; width: 72px; height: 48px; margin: 0 auto; }
.grid-mini-cell { background: var(--el-border-color); border-radius: 2px; }

/* Preview dialog */
.preview-grid { display: grid; gap: 8px; width: 100%; margin: 0 auto; }
.preview-cell { position: relative; border-radius: 6px; overflow: hidden; min-height: 80px; }
.preview-cell-occupied { background: var(--el-color-primary-light-9); border: 1px solid var(--el-color-primary-light-5); }
.preview-cell-empty { background: var(--el-fill-color); border: 1px solid var(--el-border-color); }
.preview-cell-inner {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  position: absolute; inset: 0; padding: 4px;
}
.preview-cell-name { font-size: 13px; font-weight: 500; color: var(--el-text-color-primary); text-align: center; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.preview-cell-id { font-size: 10px; color: var(--el-text-color-placeholder); font-family: "SF Mono", monospace; }
.preview-cell-empty-icon { font-size: 12px; color: var(--el-text-color-disabled); }
</style>
