<template>
  <div class="app-container">
    <PageSearch
      ref="algoSearchRef"
      :search-config="algoSearchConfig"
      @query-click="handleAlgoQuery"
      @reset-click="handleAlgoReset"
    />

    <PageContent ref="algoContentRef" :content-config="algoContentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_video:algorithm:create']"
          :perm-delete="['module_video:algorithm:delete']"
          :perm-patch="['module_video:algorithm:patch']"
          @add="handleOpenAlgoDialog('create')"
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
              v-if="algoCols.find((col) => col.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'index')?.show"
              type="index"
              fixed
              label="序号"
              min-width="60"
              align="center"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'name')?.show"
              key="name"
              label="算法名称"
              prop="name"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'code')?.show"
              key="code"
              label="编码"
              prop="code"
              width="140"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'version')?.show"
              key="version"
              label="版本"
              prop="version"
              width="90"
              align="center"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'algorithm_type')?.show"
              key="algorithm_type"
              label="算法类型"
              prop="algorithm_type"
              width="120"
            />
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
              prop="status"
              width="80"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status ? 'success' : 'info'" size="small">
                  {{ scope.row.status ? "启用" : "停用" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="algoCols.find((col) => col.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="160"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_video:algorithm:update']"
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenAlgoDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:algorithm:delete']"
                  type="danger"
                  size="small"
                  link
                  icon="delete"
                  @click="handleAlgoDelete(scope.row.id)"
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
      v-model="algoDialogVisible.visible"
      :title="algoDialogVisible.title"
      append-to-body
      width="760px"
      @close="handleCloseAlgoDialog"
    >
      <el-form ref="algoFormRef" :model="algoForm" label-width="110px" size="default">
        <div class="form-section">
          <div class="form-section-title">基础信息</div>
          <el-form-item label="算法名称" prop="name">
            <el-input v-model="algoForm.name" placeholder="请输入算法名称" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="编码" prop="code">
                <el-input v-model="algoForm.code" placeholder="唯一编码" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="算法类型" prop="algorithm_type">
                <el-select
                  v-model="algoForm.algorithm_type"
                  style="width: 100%"
                  @change="onAlgoTypeChange"
                >
                  <el-option
                    v-for="(label, val) in algoTypeOpts"
                    :key="val"
                    :label="label"
                    :value="val"
                  />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="版本" prop="version">
            <el-input v-model="algoForm.version" placeholder="1.0.0" style="width: 200px" />
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">模型文件与配置</div>
          <el-form-item label="模型文件" prop="model_path">
            <div class="file-upload-row">
              <el-input
                v-model="algoForm.model_path"
                placeholder="模型文件路径或上传"
                class="file-path-input"
              />
              <el-upload
                accept=".onnx,.engine,.pt,.pth,.trt,.rknn,.om"
                :auto-upload="false"
                :show-file-list="false"
                @change="handleModelUpload"
              >
                <el-button size="default">
                  <el-icon><Upload /></el-icon>
                  上传
                </el-button>
              </el-upload>
            </div>
          </el-form-item>
          <el-form-item label="插件路径" prop="plugin_path">
            <el-input v-model="algoForm.plugin_path" placeholder="C++ SDK 插件路径（可选）" />
          </el-form-item>
          <el-form-item label="配置文件">
            <div class="config-toolbar">
              <el-upload
                accept=".json,.yaml,.yml"
                :auto-upload="false"
                :show-file-list="false"
                @change="handleConfigUpload"
              >
                <el-button size="small" type="primary">
                  <el-icon><Upload /></el-icon>
                  上传配置
                </el-button>
              </el-upload>
              <el-button size="small" @click="loadConfigTemplate">
                <el-icon><Document /></el-icon>
                加载模板
              </el-button>
              <el-button size="small" @click="formatConfigJson">
                <el-icon><Checked /></el-icon>
                格式化
              </el-button>
            </div>
          </el-form-item>
          <el-form-item label="配置内容">
            <div class="code-editor-wrap">
              <CodeEditor
                v-model="algoForm.configJson"
                language="json"
                :theme="codeTheme"
                height="360px"
                border
              />
            </div>
          </el-form-item>
        </div>

        <div class="form-section">
          <div class="form-section-title">其他</div>
          <el-form-item label="状态" prop="status">
            <el-switch v-model="algoForm.status" />
          </el-form-item>
          <el-form-item label="描述" prop="description">
            <el-input
              v-model="algoForm.description"
              type="textarea"
              :rows="2"
              placeholder="可选描述"
            />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseAlgoDialog">取消</el-button>
        <el-button type="primary" :loading="algoSubmitLoading" @click="handleSubmitAlgo">
          保存
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeMount } from "vue";
import { Upload, Document, Checked } from "@element-plus/icons-vue";
import {
  getAlgorithmList,
  createAlgorithm,
  updateAlgorithm,
  deleteAlgorithm,
} from "@/api/module_video/algorithm";
import { configTemplates, algoTypeLabels } from "@/config/algoTemplates";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import CodeEditor from "@/components/CodeEditor/index.vue";
import { useSettingsStore } from "@/store";
import { ThemeMode } from "@/enums/settings/theme.enum";

const settingsStore = useSettingsStore();

const algoSubmitLoading = ref(false);
const algoFormRef = ref();
const algoList = ref<any[]>([]);
const algoTypeOpts = algoTypeLabels;
const codeTheme = computed(() => (settingsStore.theme === ThemeMode.DARK ? "one-dark" : "default"));
const algoDialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});
const algoSearchRef = ref();
const algoContentRef = ref();
const refreshAlgoList = () => algoContentRef.value?.fetchPageData?.();

const algoSearchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:algorithm",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "算法名称",
      type: "input",
      attrs: { placeholder: "请输入算法名称", clearable: true },
    },
    {
      prop: "algorithm_type",
      label: "算法类型",
      type: "select",
      options: [
        { label: "入侵检测", value: "INTRUSION" },
        { label: "越界检测", value: "LINE_CROSSING" },
        { label: "人脸识别", value: "FACE_DETECT" },
        { label: "人数统计", value: "CROWD_COUNT" },
        { label: "烟火检测", value: "FIRE_SMOKE" },
        { label: "车辆识别", value: "VEHICLE_DETECT" },
        { label: "行为分析", value: "BEHAVIOR_ANALYSIS" },
        { label: "物品遗留", value: "OBJECT_LEFT" },
      ],
      attrs: { placeholder: "请选择算法类型", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const algoCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "算法名称", show: true },
  { prop: "code", label: "编码", show: true },
  { prop: "version", label: "版本", show: true },
  { prop: "algorithm_type", label: "算法类型", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "operation", label: "操作", show: true },
]);

interface TablePageQuery extends Record<string, any> {
  page_no: number;
  page_size: number;
}

const algoContentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:algorithm",
  pk: "id",
  cols: algoCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAlgorithmList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteAlgorithm(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleAlgoDelete(id: number) {
  algoContentRef.value?.handleDelete(id);
}
function handleAlgoQuery() {
  algoContentRef.value?.fetchPageData({ page_no: 1 });
}
function handleAlgoReset() {
  algoContentRef.value?.fetchPageData({ page_no: 1 });
}

const algoForm = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  code: undefined as string | undefined,
  version: "1.0.0",
  algorithm_type: "INTRUSION",
  model_path: undefined as string | undefined,
  plugin_path: undefined as string | undefined,
  configJson: JSON.stringify(configTemplates.INTRUSION, null, 2),
  status: true,
  description: undefined as string | undefined,
});

const initialAlgoForm = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  code: undefined as string | undefined,
  version: "1.0.0" as const,
  algorithm_type: "INTRUSION" as const,
  model_path: undefined as string | undefined,
  plugin_path: undefined as string | undefined,
  configJson: JSON.stringify(configTemplates.INTRUSION, null, 2),
  status: true,
  description: undefined as string | undefined,
};

async function resetAlgoForm() {
  if (algoFormRef.value) {
    algoFormRef.value.resetFields();
    algoFormRef.value.clearValidate();
  }
  Object.assign(algoForm, initialAlgoForm);
}

function loadConfigTemplate() {
  const tmpl = configTemplates[algoForm.algorithm_type];
  if (tmpl) {
    algoForm.configJson = JSON.stringify(tmpl, null, 2);
  }
}

function onAlgoTypeChange() {
  loadConfigTemplate();
}

function handleModelUpload(uploadFile: any) {
  const file = uploadFile.raw;
  if (file) algoForm.model_path = file.name;
}

function formatConfigJson() {
  try {
    const parsed = JSON.parse(algoForm.configJson);
    algoForm.configJson = JSON.stringify(parsed, null, 2);
  } catch {
    /* noop */
  }
}

function handleConfigUpload(uploadFile: any) {
  const file = uploadFile.raw;
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const content = e.target?.result as string;
    if (!content) return;
    try {
      JSON.parse(content);
      algoForm.configJson = content;
    } catch {
      algoForm.configJson = content;
    }
  };
  reader.readAsText(file);
}

async function handleCloseAlgoDialog() {
  algoDialogVisible.visible = false;
  await resetAlgoForm();
}

async function handleOpenAlgoDialog(type: "create" | "update", id?: number) {
  algoDialogVisible.type = type;
  if (id && type === "update") {
    algoDialogVisible.title = "编辑算法";
    const res = await getAlgorithmList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      algoForm.id = item.id;
      algoForm.name = item.name;
      algoForm.code = item.code;
      algoForm.version = item.version;
      algoForm.algorithm_type = item.algorithm_type;
      algoForm.model_path = item.model_path;
      algoForm.plugin_path = item.plugin_path;
      algoForm.status = item.status;
      algoForm.description = item.description;
      // Reconstruct configJson from stored fields
      const config: any = { algorithm_type: item.algorithm_type, version: item.version };
      config.model = { format: item.model_file_config?.format || "onnx" };
      if (item.model_file_config?.encrypt) config.model.encrypt = item.model_file_config.encrypt;
      config.runtime = item.runtime_config || configTemplates[item.algorithm_type]?.runtime;
      config.params = item.preset_params || configTemplates[item.algorithm_type]?.params;
      config.output = item.output_schema || configTemplates[item.algorithm_type]?.output;
      algoForm.configJson = JSON.stringify(config, null, 2);
    }
  } else {
    algoDialogVisible.title = "新增算法";
    algoForm.id = undefined;
    loadConfigTemplate();
  }
  algoDialogVisible.visible = true;
}

async function handleSubmitAlgo() {
  algoSubmitLoading.value = true;
  const id = algoForm.id;
  try {
    let config: any = {};
    try {
      config = JSON.parse(algoForm.configJson);
    } catch {
      config = {};
    }
    const payload: any = {
      name: algoForm.name,
      code: algoForm.code,
      version: algoForm.version,
      algorithm_type: algoForm.algorithm_type,
      model_path: algoForm.model_path || null,
      plugin_path: algoForm.plugin_path || null,
      model_file_config: config.model || {},
      runtime_config: config.runtime || {},
      preset_params: config.params || {},
      output_schema: config.output || {},
      status: algoForm.status,
      description: algoForm.description || "",
    };
    if (id) {
      await updateAlgorithm(id, payload);
    } else {
      await createAlgorithm(payload);
    }
    algoDialogVisible.visible = false;
    await resetAlgoForm();
    refreshAlgoList();
  } catch {
    //
  } finally {
    algoSubmitLoading.value = false;
  }
}

onBeforeMount(async () => {
  try {
    const algoRes = await getAlgorithmList({ page_size: 100 });
    algoList.value = algoRes.data.data.items || [];
  } catch {
    /* noop */
  }
});
</script>

<style scoped lang="scss">
.form-section {
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.form-section:last-child {
  padding-bottom: 0;
  margin-bottom: 0;
  border-bottom: none;
}
.form-section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.form-section-desc {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-placeholder);
}
.config-value {
  min-width: 40px;
  font-size: 13px;
  font-weight: 500;
  color: var(--el-color-primary);
  text-align: right;
}
.config-unit {
  margin-left: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.config-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.file-upload-row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.file-path-input {
  flex: 1;
}

.code-editor-wrap {
  width: 100%;
  overflow: hidden;
  border-radius: 4px;
}
</style>
