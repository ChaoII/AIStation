<template>
  <div class="app-container">
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane label="告警记录" name="record">
        <PageSearch
          ref="recordSearchRef"
          :search-config="recordSearchConfig"
          @query-click="handleRecordQuery"
          @reset-click="handleRecordReset"
        />

        <PageContent ref="recordContentRef" :content-config="recordContentConfig">
          <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
            <CrudToolbarLeft
              :remove-ids="removeIds"
              :perm-delete="['module_video:alarm:delete']"
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
                <template #empty>
                  <el-empty :image-size="80" description="暂无数据" />
                </template>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'selection')?.show"
                  type="selection"
                  width="55"
                  align="center"
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'index')?.show"
                  fixed
                  label="序号"
                  width="60"
                >
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'alarm_time')?.show"
                  key="alarm_time"
                  label="告警时间"
                  prop="alarm_time"
                  width="160"
                  sortable
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'camera')?.show"
                  key="camera"
                  label="摄像机"
                  min-width="130"
                  show-overflow-tooltip
                >
                  <template #default="scope">
                    {{ scope.row.camera?.name || `#${scope.row.camera_id}` }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'rule')?.show"
                  key="rule"
                  label="触发规则"
                  min-width="120"
                  show-overflow-tooltip
                >
                  <template #default="scope">
                    {{ scope.row.rule?.name || "-" }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'alarm_type')?.show"
                  key="alarm_type"
                  label="告警类型"
                  prop="alarm_type"
                  width="110"
                  show-overflow-tooltip
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'severity')?.show"
                  key="severity"
                  label="级别"
                  prop="severity"
                  width="80"
                  align="center"
                >
                  <template #default="scope">
                    <el-tag :type="severityTag(scope.row.severity)" size="small" effect="dark">
                      {{ scope.row.severity }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'status')?.show"
                  key="status"
                  label="状态"
                  prop="status"
                  width="100"
                  align="center"
                >
                  <template #default="scope">
                    <el-tag :type="statusTag(scope.row.status)" size="small">
                      {{ statusLabel(scope.row.status) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'description')?.show"
                  key="description"
                  label="描述"
                  prop="description"
                  min-width="160"
                  show-overflow-tooltip
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'operation')?.show"
                  fixed="right"
                  label="操作"
                  align="center"
                  min-width="200"
                >
                  <template #default="scope">
                    <el-button
                      size="small"
                      type="primary"
                      link
                      @click="handleViewDetail(scope.row)"
                    >
                      详情
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'PENDING'"
                      v-hasPerm="['module_video:alarm:confirm']"
                      size="small"
                      type="success"
                      plain
                      @click="handleConfirm(scope.row.id, 'CONFIRMED')"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'PENDING'"
                      v-hasPerm="['module_video:alarm:confirm']"
                      size="small"
                      plain
                      @click="handleConfirm(scope.row.id, 'FALSE_ALARM')"
                    >
                      误报
                    </el-button>
                    <el-button
                      v-hasPerm="['module_video:alarm:delete']"
                      size="small"
                      type="danger"
                      link
                      @click="handleRecordDelete(scope.row.id)"
                    >
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </PageContent>
      </el-tab-pane>

      <el-tab-pane label="告警规则" name="rule">
        <PageSearch
          ref="ruleSearchRef"
          :search-config="ruleSearchConfig"
          @query-click="handleRuleQuery"
          @reset-click="handleRuleReset"
        />

        <PageContent ref="ruleContentRef" :content-config="ruleContentConfig">
          <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
            <CrudToolbarLeft
              :remove-ids="removeIds"
              :perm-create="['module_video:alarm_rule:create']"
              :perm-delete="['module_video:alarm_rule:delete']"
              :perm-patch="['module_video:alarm_rule:patch']"
              @add="handleOpenRuleDialog('create')"
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
                <template #empty>
                  <el-empty :image-size="80" description="暂无数据" />
                </template>
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'selection')?.show"
                  type="selection"
                  width="55"
                  align="center"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'index')?.show"
                  fixed
                  label="序号"
                  width="60"
                >
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'name')?.show"
                  key="name"
                  label="规则名称"
                  prop="name"
                  min-width="150"
                  show-overflow-tooltip
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'alarm_type')?.show"
                  key="alarm_type"
                  label="告警类型"
                  prop="alarm_type"
                  width="120"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'severity')?.show"
                  key="severity"
                  label="级别"
                  prop="severity"
                  width="80"
                  align="center"
                >
                  <template #default="scope">
                    <el-tag :type="severityTag(scope.row.severity)" size="small" effect="dark">
                      {{ scope.row.severity }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'sensitivity')?.show"
                  key="sensitivity"
                  label="灵敏度"
                  prop="sensitivity"
                  width="80"
                  align="center"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'interval_seconds')?.show"
                  key="interval_seconds"
                  label="间隔(秒)"
                  prop="interval_seconds"
                  width="90"
                  align="center"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'status')?.show"
                  key="status"
                  label="状态"
                  prop="status"
                  width="80"
                  align="center"
                >
                  <template #default="scope">
                    <el-switch v-model="scope.row.status" disabled />
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'operation')?.show"
                  fixed="right"
                  label="操作"
                  align="center"
                  min-width="160"
                >
                  <template #default="scope">
                    <el-button
                      v-hasPerm="['module_video:alarm_rule:update']"
                      type="primary"
                      size="small"
                      link
                      icon="edit"
                      @click="handleOpenRuleDialog('update', scope.row.id)"
                    >
                      编辑
                    </el-button>
                    <el-button
                      v-hasPerm="['module_video:alarm_rule:delete']"
                      type="danger"
                      size="small"
                      link
                      icon="delete"
                      @click="handleRuleDelete(scope.row.id)"
                    >
                      删除
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </PageContent>
      </el-tab-pane>
    </el-tabs>

    <EnhancedDialog
      v-model="ruleDialogVisible.visible"
      :title="ruleDialogVisible.title"
      append-to-body
      width="600px"
      @close="handleCloseRuleDialog"
    >
      <el-form ref="ruleFormRef" :model="ruleForm" label-width="100px" size="default">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="ruleForm.name" placeholder="请输入规则名称" />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="告警类型" prop="alarm_type">
              <el-select v-model="ruleForm.alarm_type" style="width: 100%">
                <el-option label="运动检测" value="MOTION" />
                <el-option label="越界检测" value="LINE_CROSSING" />
                <el-option label="区域入侵" value="INTRUSION" />
                <el-option label="人脸识别" value="FACE_DETECT" />
                <el-option label="移动侦测" value="MOVEMENT" />
                <el-option label="视频遮挡" value="VIDEO_BLOCK" />
                <el-option label="视频丢失" value="VIDEO_LOST" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="级别" prop="severity">
              <el-select v-model="ruleForm.severity" style="width: 100%">
                <el-option label="严重" value="CRITICAL" />
                <el-option label="警告" value="WARNING" />
                <el-option label="信息" value="INFO" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="灵敏度" prop="sensitivity">
              <el-slider v-model="ruleForm.sensitivity" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="间隔(秒)" prop="interval_seconds">
              <el-input-number
                v-model="ruleForm.interval_seconds"
                :min="1"
                :max="3600"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态" prop="status">
          <el-switch v-model="ruleForm.status" />
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input
            v-model="ruleForm.description"
            type="textarea"
            :rows="2"
            placeholder="可选描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseRuleDialog">取消</el-button>
        <el-button type="primary" :loading="ruleSubmitLoading" @click="handleSubmitRule">
          保存
        </el-button>
      </template>
    </EnhancedDialog>

    <el-drawer
      v-model="detailDrawer.visible"
      :title="detailDrawer.title"
      size="500px"
      @close="detailDrawer.visible = false"
    >
      <template v-if="detailDrawer.data">
        <div class="detail-snapshot">
          <el-image
            v-if="detailDrawer.data.snapshot_path"
            :src="detailDrawer.data.snapshot_path"
            style="width: 100%; height: 200px"
            fit="contain"
            :preview-src-list="[detailDrawer.data.snapshot_path]"
            preview-teleported
          >
            <template #error>
              <div class="detail-snapshot-empty">无截图</div>
            </template>
          </el-image>
          <div v-else class="detail-snapshot-empty">无截图</div>
        </div>

        <el-descriptions :column="1" border class="detail-info">
          <el-descriptions-item label="告警时间">
            {{ detailDrawer.data.alarm_time }}
          </el-descriptions-item>
          <el-descriptions-item label="摄像机">
            {{ detailDrawer.data.camera?.name || detailDrawer.data.camera_id }}
          </el-descriptions-item>
          <el-descriptions-item label="触发规则">
            {{ detailDrawer.data.rule?.name || "-" }}
          </el-descriptions-item>
          <el-descriptions-item label="告警类型">
            {{ detailDrawer.data.alarm_type }}
          </el-descriptions-item>
          <el-descriptions-item label="严重级别">
            <el-tag :type="severityTag(detailDrawer.data.severity)" size="small" effect="dark">
              {{ detailDrawer.data.severity }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTag(detailDrawer.data.status)" size="small">
              {{ statusLabel(detailDrawer.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="detailDrawer.data.confirm_time" label="确认时间">
            {{ detailDrawer.data.confirm_time }}
          </el-descriptions-item>
          <el-descriptions-item v-if="detailDrawer.data.confirm_user" label="确认人">
            {{ detailDrawer.data.confirm_user }}
          </el-descriptions-item>
          <el-descriptions-item label="录像片段">
            <span v-if="detailDrawer.data.video_clip_path">
              {{ detailDrawer.data.video_clip_path }}
            </span>
            <span v-else class="text-muted">无</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="detailDrawer.data.ai_result" label="AI识别">
            <pre class="ai-result">{{ JSON.stringify(detailDrawer.data.ai_result, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>

        <div class="detail-actions">
          <el-button
            v-if="detailDrawer.data.status === 'PENDING'"
            type="success"
            @click="handleConfirm(detailDrawer.data.id, 'CONFIRMED')"
          >
            确认告警
          </el-button>
          <el-button
            v-if="detailDrawer.data.status === 'PENDING'"
            @click="handleConfirm(detailDrawer.data.id, 'FALSE_ALARM')"
          >
            标记误报
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount } from "vue";
import { ElMessage } from "element-plus";
import { getCameraList } from "@/api/module_video/camera";
import {
  getAlarmRecordList,
  getAlarmRuleList,
  confirmAlarm,
  deleteAlarmRecord,
  deleteAlarmRule,
  createAlarmRule,
  updateAlarmRule,
} from "@/api/module_video/alarm";
import type { ISearchConfig, IContentConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const activeTab = ref("record");

const {
  searchRef: recordSearchRef,
  contentRef: recordContentRef,
  handleQueryClick: handleRecordQuery,
  handleResetClick: handleRecordReset,
} = useCrudList();

const {
  searchRef: ruleSearchRef,
  contentRef: ruleContentRef,
  handleQueryClick: handleRuleQuery,
  handleResetClick: handleRuleReset,
  refreshList: refreshRuleList,
} = useCrudList();

const ruleSubmitLoading = ref(false);
const ruleFormRef = ref();
const cameraOptions = ref<any[]>([]);

const detailDrawer = reactive({
  visible: false,
  title: "",
  data: null as any,
});

function handleViewDetail(row: any) {
  detailDrawer.data = row;
  detailDrawer.title = `告警详情 - ${row.alarm_type}`;
  detailDrawer.visible = true;
}

const recordSearchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:alarm",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "camera_id",
      label: "摄像机",
      type: "select",
      options: [],
      attrs: {
        placeholder: "请选择摄像机",
        clearable: true,
        filterable: true,
        style: { width: "180px" },
      },
    },
    {
      prop: "severity",
      label: "级别",
      type: "select",
      options: [
        { label: "严重", value: "CRITICAL" },
        { label: "警告", value: "WARNING" },
        { label: "信息", value: "INFO" },
      ],
      attrs: { placeholder: "请选择级别", clearable: true, style: { width: "140px" } },
    },
    {
      prop: "status",
      label: "状态",
      type: "select",
      options: [
        { label: "待处理", value: "PENDING" },
        { label: "已确认", value: "CONFIRMED" },
        { label: "已忽略", value: "IGNORED" },
        { label: "误报", value: "FALSE_ALARM" },
      ],
      attrs: { placeholder: "请选择状态", clearable: true, style: { width: "140px" } },
    },
  ],
});

const recordCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "alarm_time", label: "告警时间", show: true },
  { prop: "camera", label: "摄像机", show: true },
  { prop: "rule", label: "触发规则", show: true },
  { prop: "alarm_type", label: "类型", show: true },
  { prop: "severity", label: "级别", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const recordContentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:alarm",
  pk: "id",
  cols: recordCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAlarmRecordList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteAlarmRecord(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

const ruleSearchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:alarm_rule",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "规则名称",
      type: "input",
      attrs: { placeholder: "请输入规则名称", clearable: true },
    },
    {
      prop: "alarm_type",
      label: "告警类型",
      type: "select",
      options: [
        { label: "运动检测", value: "MOTION" },
        { label: "越界检测", value: "LINE_CROSSING" },
        { label: "区域入侵", value: "INTRUSION" },
        { label: "人脸识别", value: "FACE_DETECT" },
        { label: "移动侦测", value: "MOVEMENT" },
        { label: "视频遮挡", value: "VIDEO_BLOCK" },
        { label: "视频丢失", value: "VIDEO_LOST" },
      ],
      attrs: { placeholder: "请选择告警类型", clearable: true, style: { width: "167.5px" } },
    },
  ],
});

const ruleCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "name", label: "规则名称", show: true },
  { prop: "alarm_type", label: "告警类型", show: true },
  { prop: "severity", label: "级别", show: true },
  { prop: "sensitivity", label: "灵敏度", show: true },
  { prop: "interval_seconds", label: "间隔(秒)", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "operation", label: "操作", show: true },
]);

const ruleContentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:alarm_rule",
  pk: "id",
  cols: ruleCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getAlarmRuleList(params as TablePageQuery);
    return { total: res.data.data.total, list: res.data.data.items };
  },
  deleteAction: async (ids) => {
    await deleteAlarmRule(
      ids
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除该项数据?", type: "warning" },
});

function handleRecordDelete(id: number) {
  recordContentRef.value?.handleDelete(id);
}

function handleRuleDelete(id: number) {
  ruleContentRef.value?.handleDelete(id);
}

const ruleDialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const ruleForm = reactive({
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  alarm_type: "MOTION",
  severity: "WARNING",
  sensitivity: 50,
  interval_seconds: 30,
  status: true,
  description: undefined as string | undefined,
});

const initialRuleForm = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  alarm_type: "MOTION" as const,
  severity: "WARNING" as const,
  sensitivity: 50,
  interval_seconds: 30,
  status: true,
  description: undefined as string | undefined,
};

async function resetRuleForm() {
  if (ruleFormRef.value) {
    ruleFormRef.value.resetFields();
    ruleFormRef.value.clearValidate();
  }
  Object.assign(ruleForm, initialRuleForm);
}

async function handleCloseRuleDialog() {
  ruleDialogVisible.visible = false;
  await resetRuleForm();
}

async function handleOpenRuleDialog(type: "create" | "update", id?: number) {
  ruleDialogVisible.type = type;
  if (id && type === "update") {
    ruleDialogVisible.title = "编辑规则";
    const res = await getAlarmRuleList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) Object.assign(ruleForm, item);
  } else {
    ruleDialogVisible.title = "新增规则";
    ruleForm.id = undefined;
  }
  ruleDialogVisible.visible = true;
}

async function handleSubmitRule() {
  ruleSubmitLoading.value = true;
  const id = ruleForm.id;
  try {
    if (id) {
      await updateAlarmRule(id, { id, ...ruleForm });
    } else {
      await createAlarmRule(ruleForm);
    }
    ruleDialogVisible.visible = false;
    await resetRuleForm();
    refreshRuleList();
  } catch {
    //
  } finally {
    ruleSubmitLoading.value = false;
  }
}

async function handleConfirm(id: number, status: string) {
  try {
    await confirmAlarm(id, status);
    ElMessage.success(status === "CONFIRMED" ? "已确认告警" : "已标记为误报");
    recordContentRef.value?.fetchPageData();
  } catch {
    //
  }
}

function severityTag(severity: string) {
  const map: Record<string, string> = { CRITICAL: "danger", WARNING: "warning", INFO: "info" };
  return map[(severity || "").toUpperCase()] || "info";
}

function statusTag(status: string) {
  const map: Record<string, string> = {
    PENDING: "danger",
    CONFIRMED: "success",
    IGNORED: "info",
    FALSE_ALARM: "warning",
  };
  return map[(status || "").toUpperCase()] || "info";
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    PENDING: "待处理",
    CONFIRMED: "已确认",
    IGNORED: "已忽略",
    FALSE_ALARM: "误报",
  };
  return map[(status || "").toUpperCase()] || status;
}

// Populate camera search options
async function loadCameraOptions() {
  try {
    const res = await getCameraList({ page_size: 100 });
    cameraOptions.value = res.data?.data?.items || [];
    const searchItem: any = recordSearchConfig.formItems.find((i: any) => i.prop === "camera_id");
    if (searchItem) {
      searchItem.options = cameraOptions.value.map((c: any) => ({ label: c.name, value: c.id }));
    }
  } catch {
    /* noop */
  }
}

onBeforeMount(() => {
  loadCameraOptions();
});
</script>

<style scoped lang="scss">
.page-tabs {
  display: flex;
  flex: 1;
  flex-direction: column;
  width: 100%;
  min-height: 0;

  :deep(.el-tabs__header) {
    flex-shrink: 0;
  }

  :deep(.el-tabs__content) {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }

  :deep(.el-tab-pane) {
    box-sizing: border-box;
    display: flex;
    flex: 1;
    flex-direction: column;
    min-height: 0;
  }
}

.detail-snapshot {
  margin-bottom: 16px;
  overflow: hidden;
  background: #000;
  border-radius: 6px;
}
.detail-snapshot-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  font-size: 14px;
  color: #666;
  background: var(--el-fill-color);
}

.detail-info {
  margin-bottom: 16px;
}
.detail-info :deep(.el-descriptions__label) {
  width: 100px;
  font-weight: 500;
}

.ai-result {
  max-height: 200px;
  padding: 8px;
  margin: 0;
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}
</style>
