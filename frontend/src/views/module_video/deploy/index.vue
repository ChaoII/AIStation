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
          :perm-create="['module_video:algorithm:create']"
          :perm-delete="['module_video:algorithm:delete']"
          :perm-patch="['module_video:algorithm:patch']"
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
              v-if="deployCols.find((c) => c.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'index')?.show"
              type="index"
              fixed
              label="序号"
              min-width="60"
              align="center"
            />
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'camera')?.show"
              key="camera"
              label="监控点位"
              min-width="150"
            >
              <template #default="scope">
                {{ scope.row.camera?.name || `#${scope.row.camera_id}` }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'algorithm')?.show"
              key="algorithm"
              label="智能算法"
              min-width="140"
            >
              <template #default="scope">
                {{ scope.row.algorithm?.name || `#${scope.row.algorithm_id}` }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'schedule')?.show"
              key="schedule"
              label="布控时段"
              min-width="160"
              show-overflow-tooltip
            >
              <template #default="scope">
                <span v-if="!scope.row.schedule_json?.slots?.length" class="text-muted">全天</span>
                <span v-else class="schedule-summary">
                  {{ scheduleSummary(scope.row.schedule_json) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'sensitivity')?.show"
              key="sensitivity"
              label="灵敏度"
              prop="sensitivity"
              width="80"
              align="center"
            />
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'stream_type')?.show"
              key="stream_type"
              label="码流"
              width="70"
              align="center"
            >
              <template #default="scope">
                <el-tag size="small">{{ scope.row.stream_type === "MAIN" ? "主" : "子" }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'status')?.show"
              key="status"
              label="状态"
              width="90"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="scope.row.status === 'RUNNING' ? 'success' : 'info'" size="small">
                  {{ scope.row.status === "RUNNING" ? "运行中" : "已停止" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="deployCols.find((c) => c.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="130"
            >
              <template #default="scope">
                <el-button
                  type="primary"
                  size="small"
                  link
                  icon="edit"
                  @click="handleOpenDialog('update', scope.row.id)"
                >
                  编辑
                </el-button>
                <el-button
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
      width="680px"
      @close="handleCloseDialog"
    >
      <el-form ref="dataFormRef" :model="formData" label-width="110px" size="default">
        <div class="form-section">
          <div class="form-section-title">布控配置</div>
          <el-form-item label="监控点位" prop="camera_id">
            <el-select
              v-model="formData.camera_id"
              filterable
              placeholder="选择摄像机"
              style="width: 280px"
            >
              <el-option v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="智能算法" prop="algorithm_id">
            <el-select
              v-model="formData.algorithm_id"
              filterable
              placeholder="选择算法"
              style="width: 280px"
            >
              <el-option v-for="a in algorithmOptions" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
          </el-form-item>
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="分析码流" prop="stream_type">
                <el-select v-model="formData.stream_type" style="width: 100%">
                  <el-option label="主码流（高清）" value="MAIN" />
                  <el-option label="子码流（流畅）" value="SUB" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="灵敏度" prop="sensitivity">
                <el-input-number
                  v-model="formData.sensitivity"
                  :min="1"
                  :max="100"
                  :step="1"
                  controls-position="right"
                  style="width: 100%"
                />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <div class="form-section">
          <div class="form-section-title">
            布控时段
            <span class="form-section-desc">选择算法生效的时间段</span>
          </div>
          <div class="schedule-grid-wrapper">
            <div class="schedule-header-row">
              <div class="schedule-corner" />
              <div v-for="h in 24" :key="h" class="schedule-header-cell">
                {{ String(h - 1).padStart(2, "0") }}
              </div>
            </div>
            <div v-for="day in 7" :key="day" class="schedule-row">
              <div class="schedule-day-label">{{ weekDays[day - 1] }}</div>
              <div
                v-for="hour in 24"
                :key="hour"
                class="schedule-cell"
                :class="{ active: isSlotActive(day - 1, hour - 1) }"
                @mousedown.prevent="onCellMouseDown(day - 1, hour - 1, $event)"
                @mouseenter="onCellMouseEnter(day - 1, hour - 1)"
              />
            </div>
          </div>
          <div class="schedule-actions">
            <el-button size="small" @click="fillSchedule(true)">全选</el-button>
            <el-button size="small" @click="fillSchedule(false)">清空</el-button>
            <el-button size="small" @click="fillWorkHours">工作日 08-18</el-button>
          </div>
        </div>

        <div class="form-section">
          <div class="form-section-title">其他</div>
          <el-form-item label="状态" prop="status">
            <el-switch v-model="formData.statusBool" active-text="运行中" inactive-text="已停止" />
          </el-form-item>
          <el-form-item label="备注" prop="description">
            <el-input
              v-model="formData.description"
              type="textarea"
              :rows="2"
              placeholder="可选备注"
            />
          </el-form-item>
        </div>

        <div v-if="algoConfig" class="form-section">
          <div class="form-section-title">
            算法参数覆盖
            <span class="form-section-desc">不填则使用算法预设值</span>
          </div>
          <div class="algo-config-display">
            <div class="config-block">
              <div class="config-block-title">模型</div>
              <div class="config-item">格式: {{ algoConfig.model?.format || "-" }}</div>
              <div v-if="algoConfig.model?.encrypt?.enabled" class="config-item">
                加密: {{ algoConfig.model.encrypt.method }}
              </div>
            </div>
            <div class="config-block">
              <div class="config-block-title">运行时</div>
              <div class="config-item">引擎: {{ algoConfig.runtime?.engine }}</div>
              <div class="config-item">
                GPU:
                {{
                  algoConfig.runtime?.gpu?.enabled
                    ? "设备" + algoConfig.runtime.gpu.device_id
                    : "关闭"
                }}
              </div>
            </div>
            <div class="config-block">
              <div class="config-block-title">算法参数</div>
              <div v-for="(val, key) in algoConfig.params" :key="key" class="config-override-row">
                <span class="override-label">{{ paramLabel(key) }}</span>
                <el-input-number
                  v-if="typeof val === 'number'"
                  v-model="overrideParams[key]"
                  :placeholder="String(val)"
                  controls-position="right"
                  size="small"
                  style="width: 120px"
                />
                <el-switch
                  v-else-if="typeof val === 'boolean'"
                  v-model="overrideParams[key]"
                  size="small"
                />
                <el-input
                  v-else
                  v-model="overrideParams[key]"
                  :placeholder="String(val)"
                  size="small"
                  style="width: 150px"
                />
                <span class="override-default">预设: {{ val }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, onBeforeUnmount } from "vue";
import { getCameraList } from "@/api/module_video/camera";
import { getAlgorithmList } from "@/api/module_video/algorithm";
import {
  getAlgorithmTaskList,
  createAlgorithmTask,
  updateAlgorithmTask,
  deleteAlgorithmTask,
} from "@/api/module_video/deploy";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

const paramLabels: Record<string, string> = {
  confidence: "置信度阈值",
  nms_threshold: "NMS 阈值",
  max_count: "人数上限",
  min_face_size: "最小人脸",
  similarity_threshold: "相似度阈值",
  alert_threshold: "告警阈值",
  max_face_size: "最大人脸",
  vehicle_types: "车辆类型",
  behaviors: "行为类型",
  alert_cooldown: "告警冷却(秒)",
  idle_seconds: "滞留秒数",
  min_object_area: "最小面积(像素)",
  direction: "检测方向",
};

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

const submitLoading = ref(false);
const dataFormRef = ref();
const cameraOptions = ref<any[]>([]);
const algorithmOptions = ref<any[]>([]);
const algoConfig = ref<any>(null);
const overrideParams = ref<Record<string, any>>({});
let suppressOverrideReset = false;

function paramLabel(key: any): string {
  return (paramLabels as Record<string, string>)[key] || key;
}

const scheduleGrid = ref<boolean[][]>(Array.from({ length: 7 }, () => Array(24).fill(false)));
const dragState = ref<{ active: boolean; mode: "set" | "clear" }>({ active: false, mode: "set" });

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:algorithm",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "camera_id",
      label: "监控点位",
      type: "select",
      options: [],
      attrs: {
        placeholder: "选择摄像机",
        clearable: true,
        filterable: true,
        style: { width: "180px" },
      },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "运行中", value: "RUNNING" },
        { label: "已停止", value: "STOPPED" },
      ],
      attrs: { placeholder: "全部", clearable: true, style: { width: "120px" } },
    },
  ],
});

const deployCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "camera", label: "监控点位", show: true },
  { prop: "algorithm", label: "智能算法", show: true },
  { prop: "schedule", label: "布控时段", show: true },
  { prop: "sensitivity", label: "灵敏度", show: true },
  { prop: "stream_type", label: "码流", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:algorithm",
  pk: "id",
  cols: deployCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAlgorithmTaskList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteAlgorithmTask(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该布控计划?", type: "warning" },
});

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  camera_id: undefined as number | undefined,
  algorithm_id: undefined as number | undefined,
  stream_type: "SUB",
  sensitivity: 50,
  statusBool: true,
  description: undefined as string | undefined,
});

const initialFormData = { ...formData };

watch(
  () => formData.algorithm_id,
  async (newId) => {
    algoConfig.value = null;
    overrideParams.value = {};
    if (!newId) return;
    try {
      const res = await getAlgorithmList({ page_size: 100 });
      const algo = res.data?.data?.items?.find((a: any) => a.id === newId);
      if (algo) {
        const config: any = {};
        if (algo.model_file_config) config.model = algo.model_file_config;
        if (algo.runtime_config) config.runtime = algo.runtime_config;
        if (algo.preset_params) config.params = algo.preset_params;
        if (algo.output_schema) config.output = algo.output_schema;
        algoConfig.value = config;
        if (config.params && !suppressOverrideReset) {
          overrideParams.value = { ...config.params };
        }
        suppressOverrideReset = false;
      }
    } catch {
      /* noop */
    }
  }
);

const scheduleGridToJson = () => {
  const slots: { day: number; start: number; end: number }[] = [];
  for (let d = 0; d < 7; d++) {
    let start = -1;
    for (let h = 0; h <= 24; h++) {
      const active = h < 24 && scheduleGrid.value[d][h];
      if (active && start === -1) start = h;
      if (!active && start !== -1) {
        slots.push({ day: d, start, end: h });
        start = -1;
      }
    }
  }
  return { type: "weekly", slots };
};

const jsonToScheduleGrid = (json: any) => {
  scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  if (!json?.slots) return;
  for (const slot of json.slots) {
    if (slot.day >= 0 && slot.day < 7) {
      for (let h = slot.start; h < slot.end && h < 24; h++) {
        scheduleGrid.value[slot.day][h] = true;
      }
    }
  }
};

function isSlotActive(day: number, hour: number): boolean {
  return scheduleGrid.value[day]?.[hour] || false;
}
function setSlot(day: number, hour: number, val: boolean) {
  scheduleGrid.value[day][hour] = val;
}

function onCellMouseDown(day: number, hour: number, e: MouseEvent) {
  if (e.button !== 0) return;
  const current = scheduleGrid.value[day][hour];
  dragState.value = { active: true, mode: current ? "clear" : "set" };
  setSlot(day, hour, !current);
}

function onCellMouseEnter(day: number, hour: number) {
  if (!dragState.value.active) return;
  setSlot(day, hour, dragState.value.mode === "set");
}

function onDragEnd() {
  dragState.value.active = false;
}

function fillSchedule(val: boolean) {
  for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) scheduleGrid.value[d][h] = val;
}
function fillWorkHours() {
  fillSchedule(false);
  for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) scheduleGrid.value[d][h] = true;
}

function scheduleSummary(json: any): string {
  if (!json?.slots?.length) return "未配置";
  const totalHours = json.slots.reduce((sum: number, s: any) => sum + (s.end - s.start), 0);
  return `每周 ${totalHours} 小时`;
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
  scheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

async function handleOpenDialog(type: "create" | "update", id?: number) {
  dialogVisible.type = type;
  if (id && type === "update") {
    dialogVisible.title = "编辑布控计划";
    const res = await getAlgorithmTaskList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      suppressOverrideReset = true;
      formData.id = item.id;
      formData.camera_id = item.camera_id;
      formData.algorithm_id = item.algorithm_id;
      formData.stream_type = item.stream_type;
      formData.sensitivity = item.sensitivity;
      formData.statusBool = item.status === "RUNNING";
      formData.description = item.description;
      if (item.schedule_json) jsonToScheduleGrid(item.schedule_json);
      // Load existing overrides
      if (item.params_overrides || item.runtime_overrides) {
        const merged = { ...item.params_overrides, ...item.runtime_overrides };
        overrideParams.value = merged;
      }
    }
  } else {
    dialogVisible.title = "新增布控计划";
    await resetForm();
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (valid) {
      submitLoading.value = true;
      const id = formData.id;
      // Build overrides: only send non-null values
      const paramsOverrides: Record<string, any> = {};
      const runtimeOverrides: Record<string, any> = {};
      for (const [k, v] of Object.entries(overrideParams.value)) {
        if (v !== null && v !== undefined && v !== "") {
          paramsOverrides[k] = v;
        }
      }
      const payload: any = {
        camera_id: formData.camera_id,
        algorithm_id: formData.algorithm_id,
        stream_type: formData.stream_type,
        sensitivity: formData.sensitivity,
        status: formData.statusBool ? "RUNNING" : "STOPPED",
        description: formData.description,
        schedule_json: scheduleGridToJson(),
        params_overrides: Object.keys(paramsOverrides).length > 0 ? paramsOverrides : null,
        runtime_overrides: Object.keys(runtimeOverrides).length > 0 ? runtimeOverrides : null,
      };
      try {
        if (id) {
          await updateAlgorithmTask(id, payload);
        } else {
          await createAlgorithmTask(payload);
        }
        dialogVisible.visible = false;
        await resetForm();
        refreshList();
      } catch {
        /* noop */
      } finally {
        submitLoading.value = false;
      }
    }
  });
}

async function loadOptions() {
  try {
    const [camRes, algRes] = await Promise.all([
      getCameraList({ page_size: 100 }),
      getAlgorithmList({ page_size: 100 }),
    ]);
    cameraOptions.value = camRes.data?.data?.items || [];
    algorithmOptions.value = algRes.data?.data?.items || [];
    const searchItem: any = searchConfig.formItems?.find((i: any) => i.prop === "camera_id");
    if (searchItem)
      searchItem.options = cameraOptions.value.map((c: any) => ({ label: c.name, value: c.id }));
  } catch {
    /* noop */
  }
}

onBeforeMount(() => {
  loadOptions();
  document.addEventListener("mouseup", onDragEnd);
});
onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onDragEnd);
});
</script>

<style scoped>
.form-section {
  padding-bottom: 14px;
  margin-bottom: 18px;
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

.schedule-grid-wrapper {
  padding-bottom: 4px;
  overflow-x: auto;
}
.schedule-header-row {
  display: flex;
  gap: 2px;
  margin-bottom: 2px;
}
.schedule-corner {
  flex-shrink: 0;
  width: 44px;
}
.schedule-header-cell {
  flex-shrink: 0;
  width: 24px;
  font-size: 10px;
  line-height: 20px;
  color: var(--el-text-color-placeholder);
  text-align: center;
}
.schedule-row {
  display: flex;
  gap: 2px;
  align-items: center;
  margin-bottom: 2px;
}
.schedule-day-label {
  flex-shrink: 0;
  width: 44px;
  padding-right: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: right;
}
.schedule-cell {
  flex-shrink: 0;
  width: 24px;
  height: 20px;
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 2px;
  transition: all 0.15s;
}
.schedule-cell:hover {
  border-color: var(--el-color-primary);
}
.schedule-cell.active {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}
.schedule-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.schedule-summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.text-muted {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.algo-config-display {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.config-block-title {
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.config-item {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.config-override-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}
.override-label {
  min-width: 100px;
  font-size: 12px;
  color: var(--el-text-color-primary);
}
.override-default {
  margin-left: 4px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
</style>
