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
            <el-table-column
              v-if="contentCols.find((c) => c.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="contentCols.find((c) => c.prop === 'index')?.show"
              fixed
              label="序号"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((c) => c.prop === 'name')?.show"
              key="name"
              label="布局名称"
              prop="name"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="contentCols.find((c) => c.prop === 'grid_type')?.show"
              key="grid_type"
              label="画面数"
              width="80"
              align="center"
            >
              <template #default="scope">{{ scope.row.grid_type }}路</template>
            </el-table-column>
            <el-table-column key="preview" label="预览" width="120" align="center">
              <template #default="scope">
                <span class="preview-svg" v-html="layoutSvg(scope.row.grid_type)" />
              </template>
            </el-table-column>
            <el-table-column label="模板" width="60" align="center">
              <template #default="scope">
                <el-tag v-if="scope.row.is_template" type="warning" size="small">模板</el-tag>
                <span v-else style="color: var(--el-text-color-placeholder)">-</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((c) => c.prop === 'is_default')?.show"
              key="is_default"
              label="默认"
              width="60"
              align="center"
            >
              <template #default="scope">
                <el-tag v-if="scope.row.is_default" type="success" size="small">默认</el-tag>
                <span v-else style="color: var(--el-text-color-placeholder)">-</span>
              </template>
            </el-table-column>
            <el-table-column label="轮巡" width="80" align="center">
              <template #default="scope">
                <span v-if="scope.row.patrol_interval" style="font-size: 12px">
                  {{ scope.row.patrol_interval }}s
                </span>
                <span v-else style="color: var(--el-text-color-placeholder)">-</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((c) => c.prop === 'description')?.show"
              key="description"
              label="描述"
              prop="description"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column fixed="right" label="操作" align="center" min-width="200">
              <template #default="scope">
                <div style="display: flex; flex-direction: column; gap: 4px">
                  <div style="display: flex; gap: 4px; justify-content: center">
                    <el-button
                      size="small"
                      type="primary"
                      link
                      icon="View"
                      @click="handlePreview(scope.row)"
                    >
                      预览
                    </el-button>
                    <el-button
                      size="small"
                      type="success"
                      link
                      icon="VideoPlay"
                      @click="handleApplyLayout(scope.row)"
                    >
                      应用
                    </el-button>
                  </div>
                  <div style="display: flex; gap: 4px; justify-content: center">
                    <el-button
                      size="small"
                      type="info"
                      link
                      icon="FullScreen"
                      @click="handleBigScreen(scope.row)"
                    >
                      大屏
                    </el-button>
                    <el-dropdown
                      trigger="click"
                      @command="(cmd: string) => handleMoreAction(cmd, scope.row)"
                    >
                      <el-button size="small" type="info" link icon="MoreFilled">更多</el-button>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="edit" icon="edit">编辑</el-dropdown-item>
                          <el-dropdown-item command="duplicate" icon="CopyDocument">
                            复制
                          </el-dropdown-item>
                          <el-dropdown-item
                            v-if="!scope.row.is_default"
                            command="setDefault"
                            icon="Star"
                          >
                            设为默认
                          </el-dropdown-item>
                          <el-dropdown-item
                            command="delete"
                            icon="delete"
                            divided
                            style="color: var(--el-color-danger)"
                          >
                            删除
                          </el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <!-- Create/Edit Dialog -->
    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="540px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item label="布局名称" prop="name">
          <el-input v-model="formData.name" placeholder="例如：4路默认" />
        </el-form-item>
        <el-form-item label="画面数" prop="grid_type">
          <div class="grid-type-picker">
            <button
              v-for="g in gridOptions"
              :key="g.value"
              class="grid-type-btn"
              :class="{ active: formData.grid_type === g.value }"
              @click="formData.grid_type = g.value"
            >
              <div class="grid-type-mini" v-html="layoutSvg(g.value)" />
              <span>{{ g.label }}</span>
            </button>
          </div>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="formData.is_default" />
        </el-form-item>
        <el-form-item label="标记为模板">
          <el-switch v-model="formData.is_template" />
        </el-form-item>
        <el-form-item label="轮巡间隔" prop="patrol_interval">
          <div style="display: flex; align-items: center; gap: 8px">
            <el-input-number
              v-model="formData.patrol_interval"
              :min="0"
              :max="3600"
              :step="5"
              controls-position="right"
              style="width: 140px"
              placeholder="0 表示不轮巡"
            />
            <span style="font-size: 12px; color: var(--el-text-color-placeholder)">
              秒（0 表示不轮巡）
            </span>
          </div>
        </el-form-item>
        <el-form-item label="备注" prop="description">
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

    <!-- Editable Preview Dialog -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="660px" destroy-on-close>
      <div class="preview-grid" :style="previewGridStyle()">
        <div
          v-for="i in previewCount"
          :key="i"
          class="preview-cell"
          :class="{
            'preview-cell-occupied': previewWindows[`w${i}`],
            'preview-cell-empty': !previewWindows[`w${i}`],
          }"
        >
          <div v-if="previewWindows[`w${i}`]" class="preview-cell-inner">
            <span class="preview-cell-name">{{ cameraName(previewWindows[`w${i}`]) }}</span>
            <span class="preview-cell-id">#{{ previewWindows[`w${i}`] }}</span>
          </div>
          <div v-else class="preview-cell-inner">
            <span class="preview-cell-empty-icon">空</span>
          </div>
          <div class="preview-cell-edit">
            <el-select
              v-model="previewWindows[`w${i}`]"
              placeholder="选择摄像机"
              size="small"
              clearable
              filterable
              style="width: 100%"
              @change="(v: any) => onWindowChange(i, v)"
            >
              <el-option v-for="c in allCameras" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" :loading="savingWindows" @click="handleSaveWindows">
          保存窗口分配
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRouter } from "vue-router";
import { getLayoutList, createLayout, updateLayout, deleteLayout } from "@/api/module_video/layout";
import { getCameraList } from "@/api/module_video/camera";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import { ElMessage } from "element-plus";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const router = useRouter();

const submitLoading = ref(false);
const dataFormRef = ref();

const gridOptions = [
  { label: "1路", value: "1" },
  { label: "4路", value: "4" },
  { label: "6路", value: "6" },
  { label: "8路", value: "8" },
  { label: "9路", value: "9" },
  { label: "13路", value: "13" },
  { label: "16路", value: "16" },
];

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:layout",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "布局名称",
      type: "input",
      attrs: { placeholder: "请输入布局名称", clearable: true },
    },
    {
      prop: "grid_type",
      label: "画面数",
      type: "select",
      options: gridOptions,
      attrs: { placeholder: "请选择画面数", clearable: true, style: { width: "167.5px" } },
    },
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
    await deleteLayout(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

// Grid column count per grid type
function gridCols(type: string): number {
  const m: Record<string, number> = { "1": 1, "4": 2, "6": 3, "8": 4, "9": 3, "13": 4, "16": 4 };
  return m[type] || 2;
}

function miniGridStyle(type: string) {
  const cols = gridCols(type);
  return {
    display: "grid",
    gridTemplateColumns: `repeat(${cols}, 1fr)`,
    gap: "2px",
    width: "72px",
    height: "48px",
  };
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

// Editable Preview dialog
const previewVisible = ref(false);
const previewTitle = ref("");
const previewCount = ref(4);
const previewWindows = ref<Record<string, number>>({});
const previewLayoutId = ref<number | null>(null);
const savingWindows = ref(false);
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
  previewTitle.value = row.name;
  previewLayoutId.value = row.id;
  previewWindows.value = { ...(row.layout_config?.windows || {}) };
  previewVisible.value = true;
}

function onWindowChange(index: number, value: number | undefined) {
  if (value === undefined || value === null) {
    delete previewWindows.value[`w${index}`];
  } else {
    previewWindows.value[`w${index}`] = value;
  }
}

async function handleSaveWindows() {
  if (!previewLayoutId.value) return;
  savingWindows.value = true;
  try {
    await updateLayout(previewLayoutId.value, {
      layout_config: {
        windows: { ...previewWindows.value },
        grid_type: String(previewCount.value),
      },
    });
    ElMessage.success("窗口分配已保存");
    previewVisible.value = false;
    refreshList();
  } catch {
    /* empty */
  }
  savingWindows.value = false;
}

function handleApplyLayout(row: any) {
  router.push({ name: "VideoLive", query: { layout_id: row.id } });
}

function handleBigScreen(row: any) {
  router.push({ name: "VideoBigScreen", query: { layout_id: row.id } });
}

async function handleMoreAction(cmd: string, row: any) {
  if (cmd === "edit") {
    handleOpenDialog("update", row.id);
  } else if (cmd === "delete") {
    handleRowDelete(row.id);
  } else if (cmd === "duplicate") {
    await createLayout({
      name: `${row.name} (副本)`,
      grid_type: row.grid_type,
      layout_config: row.layout_config,
      is_default: false,
      is_template: false,
      description: row.description,
    });
    ElMessage.success("已复制布局");
    refreshList();
  } else if (cmd === "setDefault") {
    await updateLayout(row.id, { is_default: true });
    ElMessage.success("已设为默认布局");
    refreshList();
  }
}

// CRUD dialog
const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  grid_type: "4",
  is_default: false,
  description: undefined as string | undefined,
  is_template: false,
  patrol_interval: undefined as number | undefined,
});

const initialFormData = { ...formData };

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
}

async function fetchCameras() {
  try {
    const res = await getCameraList({ page_size: 100 });
    allCameras.value = res.data?.data?.items || [];
  } catch {
    /* empty */
  }
}

onMounted(() => {
  fetchCameras();
});

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

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
  } catch {
    /* empty */
  }
  submitLoading.value = false;
}
</script>

<style scoped>
/* Grid type picker (dialog) */
.grid-type-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.grid-type-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 8px 8px 6px;
  cursor: pointer;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  transition: all 0.15s;
  min-width: 68px;
}
.grid-type-btn:hover {
  border-color: var(--el-color-primary-light-5);
}
.grid-type-btn.active {
  color: var(--el-color-primary);
  background: color-mix(in srgb, var(--el-color-primary) 8%, transparent);
  border-color: var(--el-color-primary);
}
.grid-type-btn svg {
  display: block;
  width: 52px;
  height: 34px;
  color: var(--el-color-primary-light-3);
}
.grid-type-btn.active svg {
  color: var(--el-color-primary);
}
.grid-type-btn span {
  font-size: 11px;
  line-height: 1;
}
.grid-type-btn svg {
  display: block;
  width: 52px;
  height: 34px;
}
.grid-type-btn span {
  font-size: 11px;
  line-height: 1;
}
.grid-type-mini {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Mini grid in table */
.preview-svg {
  display: flex;
  justify-content: center;
  color: var(--el-color-primary);
  opacity: 0.5;
}
.grid-mini {
  display: grid;
  gap: 2px;
  width: 72px;
  height: 48px;
  margin: 0 auto;
}
.grid-mini-cell {
  background: var(--el-border-color);
  border-radius: 2px;
}

/* Preview dialog */
.preview-grid {
  display: grid;
  gap: 8px;
  width: 100%;
  margin: 0 auto;
}
.preview-cell {
  position: relative;
  border-radius: 6px;
  overflow: hidden;
  min-height: 80px;
}
.preview-cell-occupied {
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
}
.preview-cell-empty {
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color);
}
.preview-cell-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  position: absolute;
  inset: 0;
  padding: 4px;
  z-index: 1;
  pointer-events: none;
}
.preview-cell-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  text-align: center;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.preview-cell-id {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  font-family: "SF Mono", monospace;
}
.preview-cell-empty-icon {
  font-size: 12px;
  color: var(--el-text-color-disabled);
}
.preview-cell-edit {
  position: absolute;
  bottom: 4px;
  left: 4px;
  right: 4px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.15s;
}
.preview-cell:hover .preview-cell-edit {
  opacity: 1;
}
.preview-cell-edit :deep(.el-select) {
  --el-select-input-color: transparent;
}
.preview-cell-edit :deep(.el-select .el-input__wrapper) {
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
}
</style>
