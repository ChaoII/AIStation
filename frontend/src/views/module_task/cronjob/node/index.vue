<template>
  <div class="app-container">
    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <PageContent
      ref="contentRef"
      :content-config="contentConfig"
      @add-click="handleOpenDialog('create')"
    >
      <template #table="{ data, loading, tableRef, onSelectionChange, pagination }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" :description="t('task.noData')" />
            </template>
            <el-table-column type="selection" align="center" min-width="55" />
            <el-table-column type="index" fixed :label="t('task.serial')" min-width="60">
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column :label="t('task.nodeName')" prop="name" min-width="140" />
            <el-table-column :label="t('task.nodeCode')" prop="code" min-width="120" />
            <el-table-column :label="t('task.jobstore')" prop="jobstore" min-width="80" />
            <el-table-column :label="t('task.executor')" prop="executor" min-width="80" />
            <el-table-column
              :label="t('task.createdTime')"
              prop="created_time"
              min-width="180"
              sortable
            />

            <OperationColumn :list-data-length="data.length">
              <template #default="scope">
                <el-space class="flex">
                  <el-button
                    v-hasPerm="['module_task:cronjob:node:execute']"
                    type="warning"
                    size="small"
                    link
                    icon="VideoPlay"
                    @click="handleOpenExecuteDialog(scope.row as NodeTable)"
                  >
                    {{ t("task.debug") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_task:cronjob:node:update']"
                    type="primary"
                    size="small"
                    link
                    icon="edit"
                    @click="handleOpenDialog('update', scope.row.id)"
                  >
                    {{ t("task.edit") }}
                  </el-button>
                  <el-button
                    v-hasPerm="['module_task:cronjob:node:delete']"
                    type="danger"
                    size="small"
                    link
                    icon="delete"
                    @click="handleRowDelete(scope.row.id)"
                  >
                    {{ t("task.delete") }}
                  </el-button>
                </el-space>
              </template>
            </OperationColumn>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      width="1000px"
      @close="handleCloseDialog"
    >
      <el-splitter direction="horizontal" style="height: 500px">
        <el-splitter-panel size="300px" :min="200" :max="400">
          <el-scrollbar style="height: 100%">
            <el-form
              ref="dataFormRef"
              :model="formData"
              :rules="rules"
              label-suffix=":"
              label-width="auto"
              style="padding: 0 10px"
            >
              <el-form-item :label="t('task.nodeName')" prop="name">
                <el-input
                  v-model="formData.name"
                  :placeholder="t('task.inputNodeName')"
                  :maxlength="50"
                />
              </el-form-item>
              <el-form-item :label="t('task.nodeCode')" prop="code">
                <el-input
                  v-model="formData.code"
                  :placeholder="t('task.inputNodeCode')"
                  :maxlength="32"
                />
              </el-form-item>
              <el-form-item :label="t('task.jobstore')" prop="jobstore">
                <el-select v-model="formData.jobstore" :placeholder="t('task.selectJobstore')">
                  <el-option
                    v-for="item in dictStore.getDictArray('sys_job_store')"
                    :key="item.dict_value"
                    :label="item.dict_label"
                    :value="item.dict_value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('task.executor')" prop="executor">
                <el-select v-model="formData.executor" :placeholder="t('task.selectExecutor')">
                  <el-option
                    v-for="item in dictStore.getDictArray('sys_job_executor')"
                    :key="item.dict_value"
                    :label="item.dict_label"
                    :value="item.dict_value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('task.positionalArgs')" prop="args">
                <div class="dynamic-params">
                  <div v-for="(_item, index) in argsList" :key="index" class="param-item">
                    <el-input v-model="argsList[index]" :placeholder="t('task.paramValue')" />
                    <el-button
                      type="danger"
                      icon="Delete"
                      circle
                      @click="argsList.splice(index, 1)"
                    />
                  </div>
                  <el-button type="primary" icon="Plus" @click="argsList.push('')">
                    {{ t("task.addPositionalArg") }}
                  </el-button>
                </div>
              </el-form-item>
              <el-form-item :label="t('task.kwArgs')" prop="kwargs">
                <div class="dynamic-params">
                  <div v-for="(item, index) in kwargsList" :key="index" class="param-item">
                    <el-input v-model="item.key" :placeholder="t('task.key')" />
                    <el-input v-model="item.value" :placeholder="t('task.value')" />
                    <el-button
                      type="danger"
                      icon="Delete"
                      circle
                      @click="kwargsList.splice(index, 1)"
                    />
                  </div>
                  <el-button
                    type="primary"
                    icon="Plus"
                    @click="kwargsList.push({ key: '', value: '' })"
                  >
                    {{ t("task.addKeywordArg") }}
                  </el-button>
                </div>
              </el-form-item>
              <el-form-item :label="t('task.coalesce')" prop="coalesce">
                <el-radio-group v-model="formData.coalesce">
                  <el-radio :value="true">{{ t("task.yes") }}</el-radio>
                  <el-radio :value="false">{{ t("task.no") }}</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item :label="t('task.maxInstances')" prop="max_instances">
                <el-input-number
                  v-model="formData.max_instances"
                  controls-position="right"
                  :min="1"
                  :max="10"
                />
              </el-form-item>
            </el-form>
          </el-scrollbar>
        </el-splitter-panel>

        <el-splitter-panel>
          <div class="code-editor-container">
            <div class="code-editor-header">
              <span class="code-editor-title">{{ t("task.processor") }}</span>
              <span class="code-editor-tip">{{ t("task.processorTip") }}</span>
            </div>
            <CodeEditor
              ref="codeEditorRef"
              v-model="formData.func"
              language="python"
              theme="one-dark"
              :height="`calc(100% - 40px)`"
              border
            />
          </div>
        </el-splitter-panel>
      </el-splitter>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="handleCloseDialog">{{ t("task.cancel") }}</el-button>
          <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
            {{ t("task.confirm") }}
          </el-button>
        </div>
      </template>
    </EnhancedDialog>

    <EnhancedDialog
      v-model="executeDialogVisible"
      :title="t('task.executeNodeTitle')"
      width="700px"
      @close="handleCloseExecuteDialog"
    >
      <el-form
        ref="executeFormRef"
        :model="executeFormData"
        :rules="executeRules"
        label-suffix=":"
        label-width="auto"
      >
        <el-form-item :label="t('task.nodeNameValue')">
          <el-input :value="currentExecuteNode?.name" disabled />
        </el-form-item>
        <!-- 触发配置统一走 TriggerEditor（四类型 + 预览 + 非法拦截），不再各自维护输入控件 -->
        <el-form-item :label="t('task.trigger')" prop="trigger">
          <TriggerEditor
            v-model:trigger="executeFormData.trigger"
            v-model:trigger-args="executeFormData.trigger_args"
            preview-url="/task/cronjob/node/trigger/preview"
            @error="handleTriggerError"
          />
        </el-form-item>

        <template
          v-if="executeFormData.trigger === 'cron' || executeFormData.trigger === 'interval'"
        >
          <el-form-item :label="t('task.startDate')" prop="start_date">
            <el-date-picker
              v-model="executeFormData.start_date"
              type="datetime"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              :placeholder="t('task.selectStartDate')"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item :label="t('task.endDate')" prop="end_date">
            <el-date-picker
              v-model="executeFormData.end_date"
              type="datetime"
              format="YYYY-MM-DD HH:mm:ss"
              value-format="YYYY-MM-DD HH:mm:ss"
              :placeholder="t('task.selectEndDate')"
              style="width: 100%"
            />
          </el-form-item>
        </template>
      </el-form>

      <template #footer>
        <el-button @click="handleCloseExecuteDialog">{{ t("task.cancel") }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleExecuteNode">
          {{ t("task.confirm") }}
        </el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script lang="ts" setup>
defineOptions({
  name: "Node",
  inheritAttrs: false,
});

const { t } = useI18n();

import NodeAPI, {
  NodeTable,
  NodeForm,
  NodePageQuery,
  TriggerType,
  ExecuteNodeParams,
} from "@/api/module_task/cronjob/node";
import { useDictStore } from "@/store/index";
import PageSearch from "@/components/CURD/PageSearch.vue";
import PageContent from "@/components/CURD/PageContent.vue";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import OperationColumn from "@/components/OperationColumn/index.vue";
import TriggerEditor from "@/components/TriggerEditor/index.vue";
import CodeEditor from "@/components/CodeEditor/index.vue";

const dictStore = useDictStore();

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();
const dataFormRef = ref();
const executeFormRef = ref();
const submitLoading = ref(false);
const codeEditorRef = ref();
/** TriggerEditor 上抛的非法原因（非空时拦截调试提交） */
const triggerError = ref("");

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_task:cronjob:node",
  colon: true,
  isExpandable: false,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: t("task.nodeName"),
      type: "input",
      attrs: { placeholder: t("task.inputNodeName"), clearable: true },
    },
    {
      prop: "code",
      label: t("task.nodeCode"),
      type: "input",
      attrs: { placeholder: t("task.inputNodeCode"), clearable: true },
    },
  ],
});

const contentConfig = reactive<IContentConfig<NodePageQuery>>({
  permPrefix: "module_task:cronjob:node",
  cols: [],
  hideColumnFilter: true,
  toolbar: ["add", "delete"],
  defaultToolbar: ["refresh", "filter"],
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await NodeAPI.listNode(params as NodePageQuery);
    return {
      total: res.data.data.total,
      list: res.data.data.items,
    };
  },
  deleteAction: (ids) =>
    NodeAPI.deleteNode(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n) && n > 0)
    ),
  deleteConfirm: {
    title: t("task.warn"),
    message: t("task.deleteNodeConfirm"),
    type: "warning",
  },
});

const defaultCodeBlock = `def handler(*args, **kwargs):
    """
    Demo: ${t("task.demoCallEngineMethod")}
    
    ${t("task.demoShowHow")}:
    1. ${t("task.demoImportMethod")}
    2. ${t("task.demoCallProcessor")}
    3. ${t("task.demoReturnResult")}
    """
    
    # ${t("task.demoImportMethod")}
    from app.plugin.module_task.cronjob.node.handlers.demo_handler import (
        demo_handler,
        process_data
    )
    
    print("=" * 50)
    print("Demo ${t("task.demoTaskStart")}")
    print("=" * 50)
    
    # 1. ${t("task.demoCall")} demo_handler
    print("1. ${t("task.demoCall")} demo_handler:")
    result1 = demo_handler("${t("task.demoParam")}1", "${t("task.demoParam")}2", key="value")
    print(f"   ${t("task.demoReturn")}: {result1}")
    
    # 2. ${t("task.demoCall")} process_data ${t("task.demoCalcAvg")}
    print("2. ${t("task.demoDataProcess")} - ${t("task.demoCalcAvg")}:")
    numbers = [10, 20, 30, 40, 50]
    result2 = process_data(numbers, operation="avg")
    print(f"   ${t("task.demoInput")}: {numbers}")
    print(f"   ${t("task.demoResult")}: {result2}")
    
    # 3. ${t("task.demoCall")} process_data ${t("task.demoCalcSum")}
    print("3. ${t("task.demoDataProcess")} - ${t("task.demoCalcSum")}:")
    result3 = process_data(numbers, operation="sum")
    print(f"   ${t("task.demoInput")}: {numbers}")
    print(f"   ${t("task.demoResult")}: {result3}")
    
    print("=" * 50)
    print("Demo ${t("task.demoTaskComplete")}")
    print("=" * 50)
    
    return {
        "status": "success",
        "demo_result": result1,
        "avg_result": result2,
        "sum_result": result3
    }
`;

const formData = reactive<NodeForm>({
  id: undefined,
  name: "",
  code: undefined,
  jobstore: "default",
  executor: "default",
  func: defaultCodeBlock,
  args: undefined,
  kwargs: undefined,
  coalesce: false,
  max_instances: 1,
  start_date: undefined,
  end_date: undefined,
});

const argsList = ref<string[]>([]);
const kwargsList = ref<{ key: string; value: string }[]>([]);

const executeDialogVisible = ref(false);
const currentExecuteNode = ref<NodeTable | null>(null);
const executeFormData = reactive<{
  trigger: TriggerType;
  /** 触发参数：cron 为 5 段字符串、interval 为对象、date 为时间字符串、now 为 null */
  trigger_args?: unknown;
  start_date?: string;
  end_date?: string;
}>({
  trigger: "now",
  trigger_args: null,
  start_date: undefined,
  end_date: undefined,
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update" | "detail",
});

const rules = reactive({
  name: [{ required: true, message: t("task.inputNodeName"), trigger: "blur" }],
  code: [{ required: true, message: t("task.inputNodeCode"), trigger: "blur" }],
});

const executeRules = reactive({
  trigger: [{ required: true, message: t("task.selectTrigger"), trigger: "change" }],
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const initialFormData: Partial<NodeForm> = {
  id: undefined,
  name: "",
  code: undefined,
  jobstore: "sqlalchemy",
  executor: "default",
  func: defaultCodeBlock,
  args: undefined,
  kwargs: undefined,
  coalesce: false,
  max_instances: 5,
  start_date: undefined,
  end_date: undefined,
};

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  argsList.value = [];
  kwargsList.value = [];
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id) {
    const response = await NodeAPI.detailNode(id);
    dialogVisible.title = t("task.editNode");
    Object.assign(formData, response.data.data);
    const data = response.data.data;
    argsList.value = data.args ? data.args.split(",").map((v: string) => v.trim()) : [];
    kwargsList.value = data.kwargs
      ? Object.entries(JSON.parse(data.kwargs)).map(([key, value]) => ({
          key,
          value: String(value),
        }))
      : [];
  } else {
    dialogVisible.title = t("task.createNode");
    formData.id = undefined;
    argsList.value = [];
    kwargsList.value = [];
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: any) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      try {
        const submitData = {
          ...formData,
          args: argsList.value.filter((v) => v.trim()).join(",") || undefined,
          kwargs:
            kwargsList.value.filter((v) => v.key.trim()).length > 0
              ? JSON.stringify(
                  Object.fromEntries(
                    kwargsList.value.filter((v) => v.key.trim()).map((v) => [v.key, v.value])
                  )
                )
              : undefined,
        };
        if (id) {
          await NodeAPI.updateNode(id, submitData);
        } else {
          await NodeAPI.createNode(submitData);
        }
        dialogVisible.visible = false;
        resetForm();
        refreshList();
      } catch (error: any) {
        console.log(error);
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

/** TriggerEditor 的非法原因：非空即拦截调试提交并就地提示 */
function handleTriggerError(message: string) {
  triggerError.value = message;
}

/**
 * 把 TriggerEditor 的参数收敛成接口契约：
 * - interval 为对象 → 序列化成 JSON 字符串（后端 schema 的 `trigger_args` 是字符串）；
 * - cron / date 已是字符串，原样透传；
 * - now 无参数。
 */
function serializeTriggerArgs(trigger: TriggerType, args: unknown): string | undefined {
  if (trigger === "interval") {
    // 组件只 emit 对象；字符串分支仅作防御性兜底（兼容历史遗留的 JSON 串），正常不会走到
    return typeof args === "string" ? args : JSON.stringify(args ?? {});
  }
  return typeof args === "string" && args ? args : undefined;
}

function handleOpenExecuteDialog(row: NodeTable) {
  currentExecuteNode.value = row;
  executeFormData.trigger = "now";
  executeFormData.trigger_args = null;
  executeFormData.start_date = undefined;
  executeFormData.end_date = undefined;
  triggerError.value = "";
  executeDialogVisible.value = true;
}

function handleCloseExecuteDialog() {
  executeDialogVisible.value = false;
  currentExecuteNode.value = null;
  triggerError.value = "";
  if (executeFormRef.value) {
    executeFormRef.value.resetFields();
  }
}

async function handleExecuteNode() {
  // 触发配置非法（TriggerEditor 预览结论）时先拦截，避免把必然失败的请求打到后端
  if (triggerError.value) {
    ElMessage.error({ message: triggerError.value, type: "error", duration: 3000 });
    return;
  }

  // 单次触发：未选时间时 serializeTriggerArgs 返回 undefined，后端 422 的 detail 不是 msg，
  // 兜底只会显示笼统的「调试失败」；这里本地判空拦截并给出准确提示。
  if (executeFormData.trigger === "date" && !executeFormData.trigger_args) {
    ElMessage.error({ message: t("task.selectExecTime"), type: "error", duration: 3000 });
    return;
  }

  if (executeFormData.trigger !== "now") {
    const valid = await executeFormRef.value?.validate().catch(() => false);
    if (!valid) return;
  }

  try {
    submitLoading.value = true;
    const params: ExecuteNodeParams = {
      trigger: executeFormData.trigger,
    };

    if (executeFormData.trigger !== "now") {
      params.trigger_args = serializeTriggerArgs(
        executeFormData.trigger,
        executeFormData.trigger_args
      );
      params.start_date = executeFormData.start_date;
      params.end_date = executeFormData.end_date;
    }

    await NodeAPI.executeNode(currentExecuteNode.value?.id as number, params);

    handleCloseExecuteDialog();

    refreshList();
  } catch (error: any) {
    ElMessage.error({
      message: error.response?.data?.msg || t("task.debugFailed"),
      type: "error",
      duration: 3000,
    });
    console.error(error);
  } finally {
    submitLoading.value = false;
  }
}

onMounted(async () => {
  await dictStore.getDict(["sys_job_store", "sys_job_executor"]);
  refreshList();
});
</script>

<style scoped>
.code-editor-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding-left: 16px;
}

.code-editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
}

.code-editor-title {
  font-size: 14px;
  font-weight: 600;
}

.code-editor-tip {
  font-size: 12px;
}

.dynamic-params {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.code-preview {
  max-height: 200px;
  padding: 10px;
  overflow-y: auto;
  font-family: monospace;
  word-break: break-all;
  white-space: pre-wrap;
  border-radius: 4px;
}

.execution-log-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.pagination-container {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
