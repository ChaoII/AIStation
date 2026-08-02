<template>
  <div class="fa-full-height page-tabs-wrap">
    <ElTabs v-model="activeTab" class="page-tabs">
      <ElTabPane label="告警记录" name="record">
        <FaSearchBar
          v-show="recordShowSearch"
          v-model="recordSearchForm"
          :items="recordSearchItems"
          :rules="recordSearchRules"
          :is-expand="false"
          :show-expand="true"
          :show-reset="true"
          :show-search="true"
          :default-expanded="false"
          @search="handleRecordSearch"
          @reset="onRecordResetSearch"
        />
        <ElCard shadow="hover" class="fa-table-card" :style="{ 'margin-top': recordShowSearch ? '12px' : '0' }">
          <FaTableHeader v-model:columns="recordColChecks" v-model:showSearchBar="recordShowSearch" :loading="recordLoading" @refresh="refreshRecordData">
            <template #left>
              <FaTableHeaderLeft :remove-ids="recordSelectedIds" :perm-delete="['module_video:alarm:delete']" :delete-loading="recordBatchDeleting" @delete="handleRecordBatchDelete" />
            </template>
          </FaTableHeader>
          <FaTable
            ref="recordTableRef"
            :loading="recordLoading"
            :data="recordData"
            :columns="recordColumns"
            :pagination="recordPagination"
            @selection-change="onRecordTableSelectionChange"
            @pagination:size-change="handleRecordSizeChange"
            @pagination:current-change="handleRecordCurrentChange"
          />
        </ElCard>
      </ElTabPane>

      <ElTabPane label="告警规则" name="rule">
        <FaSearchBar
          v-show="ruleShowSearch"
          v-model="ruleSearchForm"
          :items="ruleSearchItems"
          :rules="ruleSearchRules"
          :is-expand="false"
          :show-expand="true"
          :show-reset="true"
          :show-search="true"
          :default-expanded="false"
          @search="handleRuleSearch"
          @reset="onRuleResetSearch"
        />
        <ElCard shadow="hover" class="fa-table-card" :style="{ 'margin-top': ruleShowSearch ? '12px' : '0' }">
          <FaTableHeader v-model:columns="ruleColChecks" v-model:showSearchBar="ruleShowSearch" :loading="ruleLoading" @refresh="refreshRuleData">
            <template #left>
              <FaTableHeaderLeft :remove-ids="ruleSelectedIds" :perm-create="['module_video:alarm_rule:create']" :perm-delete="['module_video:alarm_rule:delete']" :delete-loading="ruleBatchDeleting" @add="handleOpenRuleDialog('create')" @delete="handleRuleBatchDelete" />
            </template>
          </FaTableHeader>
          <FaTable
            ref="ruleTableRef"
            :loading="ruleLoading"
            :data="ruleData"
            :columns="ruleColumns"
            :pagination="rulePagination"
            @selection-change="onRuleTableSelectionChange"
            @pagination:size-change="handleRuleSizeChange"
            @pagination:current-change="handleRuleCurrentChange"
          />
        </ElCard>
      </ElTabPane>
    </ElTabs>

    <ElDialog v-model="ruleDialogVisible.visible" :title="ruleDialogVisible.title" width="620px" :close-on-click-modal="false">
      <ElForm ref="ruleFormRef" :model="ruleForm" label-width="100px">
        <ElFormItem label="规则名称" prop="name"><ElInput v-model="ruleForm.name" placeholder="请输入规则名称" /></ElFormItem>
        <ElFormItem label="关联摄像机" prop="camera_id">
          <ElSelect v-model="ruleForm.camera_id" filterable placeholder="选择摄像机" style="width:100%">
            <ElOption v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="算法布控任务" prop="algorithm_task_id">
          <ElSelect v-model="ruleForm.algorithm_task_id" filterable clearable placeholder="可选—关联智能布控任务" style="width:100%">
            <ElOption v-for="t in algorithmTaskOptions" :key="t.id" :label="(t.camera?.name || '?') + ' — ' + (t.algorithm?.name || '?')" :value="t.id" />
          </ElSelect>
        </ElFormItem>
        <ElRow :gutter="20">
          <ElCol :span="12">
            <ElFormItem label="告警类型" prop="alarm_type">
              <ElSelect v-model="ruleForm.alarm_type" style="width:100%">
                <ElOption v-for="a in alarmTypeOptions" :key="a.value" :label="a.label" :value="a.value" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
          <ElCol :span="12">
            <ElFormItem label="级别" prop="severity">
              <ElSelect v-model="ruleForm.severity" style="width:100%">
                <ElOption label="严重" value="CRITICAL" /><ElOption label="警告" value="WARNING" /><ElOption label="信息" value="INFO" />
              </ElSelect>
            </ElFormItem>
          </ElCol>
        </ElRow>
        <ElFormItem label="通知方式" prop="notify_channels">
          <div style="width:100%">
            <ElCheckboxGroup v-model="ruleChannelSelection">
              <ElCheckbox label="WS_PUSH">WS 推送</ElCheckbox>
              <ElCheckbox label="SMS">短信</ElCheckbox>
              <ElCheckbox label="EMAIL">邮件</ElCheckbox>
              <ElCheckbox label="WEBHOOK">Webhook/REST API</ElCheckbox>
            </ElCheckboxGroup>
            <div v-if="ruleChannelSelection.includes('EMAIL')" class="notify-config-block">
              <div class="notify-config-label">邮件收件人</div>
              <ElInput v-model="ruleChannelEmailTo" placeholder="admin@example.com, ops@example.com（逗号分隔）" clearable size="small" />
            </div>
            <div v-if="ruleChannelSelection.includes('SMS')" class="notify-config-block">
              <div class="notify-config-label">短信接收号码</div>
              <ElInput v-model="ruleChannelSmsPhones" placeholder="13800138000, 13900139000（逗号分隔）" clearable size="small" />
            </div>
            <div v-if="ruleChannelSelection.includes('WEBHOOK')" class="notify-config-block">
              <div class="notify-config-label">Webhook URL</div>
              <div class="notify-webhook-row">
                <ElSelect v-model="ruleChannelWebhookMethod" size="small" style="width:100px"><ElOption label="POST" value="POST" /><ElOption label="GET" value="GET" /></ElSelect>
                <ElInput v-model="ruleChannelWebhookUrl" placeholder="https://hooks.example.com/alarm" clearable size="small" />
              </div>
              <div class="notify-config-label" style="margin-top:6px">签名密钥（可选）</div>
              <ElInput v-model="ruleChannelWebhookSecret" placeholder="留空则使用全局配置" clearable size="small" type="password" show-password />
              <div class="notify-config-label" style="margin-top:6px">自定义请求头（JSON 格式，可选）</div>
              <ElInput v-model="ruleChannelWebhookHeaders" placeholder='{"Authorization": "Bearer xxx"}' clearable size="small" :rows="2" type="textarea" />
              <div class="notify-config-label" style="margin-top:6px">请求体模板（可选，支持变量替换）</div>
              <ElInput v-model="ruleChannelWebhookTemplate" placeholder='留空则发送完整JSON' clearable size="small" :rows="3" type="textarea" />
              <div class="notify-config-hint">可用变量: <code>{{ alarm_vars.alarm_type }}</code> <code>{{ alarm_vars.severity }}</code> <code>{{ alarm_vars.camera_name }}</code> <code>{{ alarm_vars.alarm_time }}</code> <code>{{ alarm_vars.description }}</code> <code>{{ alarm_vars.rule_name }}</code> <code>{{ alarm_vars.snapshot_url }}</code> <code>{{ alarm_vars.payload }}</code></div>
            </div>
          </div>
        </ElFormItem>
        <ElRow :gutter="20">
          <ElCol :span="12"><ElFormItem label="灵敏度" prop="sensitivity"><ElSlider v-model="ruleForm.sensitivity" :min="1" :max="100" /></ElFormItem></ElCol>
          <ElCol :span="12"><ElFormItem label="间隔(秒)" prop="interval_seconds"><ElInputNumber v-model="ruleForm.interval_seconds" :min="1" :max="3600" style="width:100%" /></ElFormItem></ElCol>
        </ElRow>
        <ElFormItem label="生效时段">
          <div class="schedule-grid-wrapper">
            <div class="schedule-header-row"><div class="schedule-corner" /><div v-for="h in 24" :key="h" class="schedule-header-cell">{{ String(h - 1).padStart(2, "0") }}</div></div>
            <div v-for="day in 7" :key="day" class="schedule-row">
              <div class="schedule-day-label">{{ weekDays[day - 1] }}</div>
              <div v-for="hour in 24" :key="hour" class="schedule-cell" :class="{ active: ruleScheduleGrid[day - 1]?.[hour - 1] }" @mousedown.prevent="onRuleCellMouseDown(day - 1, hour - 1, $event)" @mouseenter="onRuleCellMouseEnter(day - 1, hour - 1)" />
            </div>
          </div>
          <div class="schedule-actions">
            <ElButton size="small" @click="fillRuleSchedule(true)">全选</ElButton>
            <ElButton size="small" @click="fillRuleSchedule(false)">清空</ElButton>
            <ElButton size="small" @click="fillRuleWorkHours">工作日 08-18</ElButton>
          </div>
        </ElFormItem>
        <ElFormItem label="状态" prop="status"><ElSwitch v-model="ruleForm.status" /></ElFormItem>
        <ElFormItem label="描述" prop="description"><ElInput v-model="ruleForm.description" type="textarea" :rows="2" placeholder="可选描述" /></ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="ruleDialogVisible.visible = false">取消</ElButton>
        <ElButton type="primary" :loading="ruleSubmitLoading" @click="handleSubmitRule">保存</ElButton>
      </template>
    </ElDialog>

    <ElDrawer v-model="detailDrawer.visible" :title="detailDrawer.title" size="500px">
      <template v-if="detailDrawer.data">
        <div class="detail-snapshot">
          <ElImage v-if="detailDrawer.data.snapshot_path" :src="detailDrawer.data.snapshot_path" style="width:100%;height:200px" fit="contain" :preview-src-list="[detailDrawer.data.snapshot_path]" preview-teleported>
            <template #error><div class="detail-snapshot-empty">无截图</div></template>
          </ElImage>
          <div v-else class="detail-snapshot-empty">无截图</div>
        </div>
        <ElDescriptions :column="1" border class="detail-info">
          <ElDescriptionsItem label="告警时间">{{ detailDrawer.data.alarm_time }}</ElDescriptionsItem>
          <ElDescriptionsItem label="摄像机">{{ detailDrawer.data.camera?.name || detailDrawer.data.camera_id }}</ElDescriptionsItem>
          <ElDescriptionsItem label="触发规则">{{ detailDrawer.data.rule?.name || "-" }}</ElDescriptionsItem>
          <ElDescriptionsItem label="告警类型">{{ detailDrawer.data.alarm_type }}</ElDescriptionsItem>
          <ElDescriptionsItem label="严重级别"><ElTag :type="severityTag(detailDrawer.data.severity)" size="small" effect="dark">{{ detailDrawer.data.severity }}</ElTag></ElDescriptionsItem>
          <ElDescriptionsItem label="状态"><ElTag :type="statusTag(detailDrawer.data.status)" size="small">{{ statusLabel(detailDrawer.data.status) }}</ElTag></ElDescriptionsItem>
          <ElDescriptionsItem v-if="detailDrawer.data.confirm_time" label="确认时间">{{ detailDrawer.data.confirm_time }}</ElDescriptionsItem>
          <ElDescriptionsItem v-if="detailDrawer.data.confirm_user" label="确认人">{{ detailDrawer.data.confirm_user }}</ElDescriptionsItem>
          <ElDescriptionsItem label="录像片段"><span v-if="detailDrawer.data.video_clip_path">{{ detailDrawer.data.video_clip_path }}</span><span v-else class="text-muted">无</span></ElDescriptionsItem>
          <ElDescriptionsItem v-if="detailDrawer.data.ai_result" label="AI识别"><pre class="ai-result">{{ JSON.stringify(detailDrawer.data.ai_result, null, 2) }}</pre></ElDescriptionsItem>
        </ElDescriptions>
        <div class="detail-actions">
          <ElButton v-if="detailDrawer.data.status === 'PENDING'" type="success" @click="handleConfirm(detailDrawer.data.id, 'CONFIRMED')">确认告警</ElButton>
          <ElButton v-if="detailDrawer.data.status === 'PENDING'" @click="handleConfirm(detailDrawer.data.id, 'FALSE_ALARM')">标记误报</ElButton>
        </div>
      </template>
    </ElDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeMount, onBeforeUnmount, h } from "vue";
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

defineOptions({ name: "VideoAlarm", inheritAttrs: false });

const { hasAuth } = useAuth();
const activeTab = ref("record");
const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
const alarmTypeOptions = [
  { label: "运动检测", value: "MOTION" }, { label: "越界检测", value: "LINE_CROSSING" }, { label: "区域入侵", value: "INTRUSION" },
  { label: "人脸识别", value: "FACE_DETECT" }, { label: "移动侦测", value: "MOVEMENT" }, { label: "视频遮挡", value: "VIDEO_BLOCK" }, { label: "视频丢失", value: "VIDEO_LOST" },
];

const cameraOptions = ref<any[]>([]);
const algorithmTaskOptions = ref<any[]>([]);

function severityTag(severity: string) {
  return ({ CRITICAL: "danger", WARNING: "warning", INFO: "info" } as any)[(severity || "").toUpperCase()] || "info";
}
function statusTag(status: string) {
  return ({ PENDING: "danger", CONFIRMED: "success", IGNORED: "info", FALSE_ALARM: "warning" } as any)[(status || "").toUpperCase()] || "info";
}
function statusLabel(status: string) {
  return ({ PENDING: "待处理", CONFIRMED: "已确认", IGNORED: "已忽略", FALSE_ALARM: "误报" } as any)[(status || "").toUpperCase()] || status;
}

// ===== 告警记录 =====
function buildRecordActions(row: any, ctx: { onDetail: (row: any) => void; onConfirm: (id: number, status: string) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const actions: TableOperationAction[] = [
    { key: "detail", label: "详情", artType: "view", icon: "ri:eye-line", run: () => ctx.onDetail(row) },
  ];
  if (row.status === "PENDING") {
    actions.push(
      { key: "confirm", label: "确认", artType: "view", icon: "ri:check-double-line", iconColor: "var(--el-color-success)", perm: "module_video:alarm:confirm", run: () => ctx.onConfirm(row.id, "CONFIRMED") },
      { key: "false", label: "误报", artType: "view", icon: "ri:close-circle-line", iconColor: "var(--el-color-warning)", perm: "module_video:alarm:confirm", run: () => ctx.onConfirm(row.id, "FALSE_ALARM") },
    );
  }
  actions.push({ key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:alarm:delete", run: () => ctx.onDelete(row.id) });
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const recordSearchForm = ref<{ camera_id?: number; severity?: string; status?: string }>({ camera_id: undefined, severity: undefined, status: undefined });
const recordShowSearch = ref(true);
const recordSearchRules: Record<string, unknown> = {};
const recordSearchItems = computed<SearchFormItem[]>(() => [
  { label: "摄像机", key: "camera_id", type: "select", props: { placeholder: "请选择摄像机", clearable: true, filterable: true, options: cameraOptions.value.map(c => ({ label: c.name, value: c.id })) }, span: 6 },
  { label: "级别", key: "severity", type: "select", props: { placeholder: "请选择级别", clearable: true, options: [{ label: "严重", value: "CRITICAL" }, { label: "警告", value: "WARNING" }, { label: "信息", value: "INFO" }] }, span: 6 },
  { label: "状态", key: "status", type: "select", props: { placeholder: "请选择状态", clearable: true, options: [{ label: "待处理", value: "PENDING" }, { label: "已确认", value: "CONFIRMED" }, { label: "已忽略", value: "IGNORED" }, { label: "误报", value: "FALSE_ALARM" }] }, span: 6 },
]);

const recordTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds: recordSelectedIds, batchDeleting: recordBatchDeleting, onTableSelectionChange: onRecordTableSelectionChange } = useTableSelection<any>();

async function deleteRecordRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteAlarmRecord([id]);
    ElMessage.success("删除成功");
    recordTableRef.value?.elTableRef?.clearSelection();
    await refreshRecordRemove();
  } catch { /* cancel */ }
}
async function handleRecordBatchDelete() {
  const ids = recordSelectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    recordBatchDeleting.value = true;
    await VideoAPI.deleteAlarmRecord(ids);
    ElMessage.success("删除成功");
    recordTableRef.value?.elTableRef?.clearSelection();
    await refreshRecordRemove();
  } catch { /* cancel */ } finally { recordBatchDeleting.value = false; }
}
async function handleConfirm(id: number, status: string) {
  try {
    await VideoAPI.confirmAlarm(id, status);
    ElMessage.success(status === "CONFIRMED" ? "已确认告警" : "已标记为误报");
    await refreshRecordData();
    if (detailDrawer.visible) detailDrawer.data.status = status;
  } catch { /* ignore */ }
}

const detailDrawer = reactive({ visible: false, title: "", data: null as any });
function handleViewDetail(row: any) {
  detailDrawer.data = row;
  detailDrawer.title = `告警详情 - ${row.alarm_type}`;
  detailDrawer.visible = true;
}

const recordOpCtx = {
  onDetail: handleViewDetail, onConfirm: handleConfirm, onDelete: deleteRecordRow,
};

const { columns: recordColumns, columnChecks: recordColChecks, data: recordData, loading: recordLoading, pagination: recordPagination, getData: getRecordData, replaceSearchParams: replaceRecordSearchParams, resetSearchParams: resetRecordSearchParams, handleSizeChange: handleRecordSizeChange, handleCurrentChange: handleRecordCurrentChange, refreshData: refreshRecordData, refreshRemove: refreshRecordRemove } = useTable({
  core: {
    apiFn: VideoAPI.listAlarmRecord,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "alarm_time", label: "告警时间", width: 160, showOverflowTooltip: true },
      { prop: "camera_name", label: "摄像机", minWidth: 130, showOverflowTooltip: true, formatter: (row: any) => row.camera?.name || `#${row.camera_id}` },
      { prop: "rule_name", label: "触发规则", minWidth: 120, showOverflowTooltip: true, formatter: (row: any) => row.rule?.name || "-" },
      { prop: "alarm_type", label: "类型", width: 110, showOverflowTooltip: true },
      { prop: "severity", label: "级别", width: 80, align: "center", formatter: (row: any) => h(ElTag, { type: severityTag(row.severity), size: "small", effect: "dark" }, () => row.severity) },
      { prop: "status", label: "状态", width: 100, align: "center", formatter: (row: any) => h(ElTag, { type: statusTag(row.status), size: "small" }, () => statusLabel(row.status)) },
      { prop: "description", label: "描述", minWidth: 160, showOverflowTooltip: true },
      { prop: "operation", label: "操作", width: 200, fixed: "right", align: "right", formatter: (row: any) => renderTableOperationCell(buildRecordActions(row, recordOpCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }) },
    ],
  },
});
function handleRecordSearch(params: { camera_id?: number; severity?: string; status?: string }) {
  replaceRecordSearchParams(cleanEmptyArrayParams({ ...params }));
  getRecordData();
}
function onRecordResetSearch() {
  recordSearchForm.value = { camera_id: undefined, severity: undefined, status: undefined };
  void resetRecordSearchParams();
}

// ===== 告警规则 =====
function buildRuleActions(row: any, ctx: { onEdit: (id: number) => void; onDelete: (id: number) => void }): TableOperationAction[] {
  const actions: TableOperationAction[] = [
    { key: "edit", label: "编辑", artType: "edit", icon: "ri:edit-2-line", perm: "module_video:alarm_rule:update", run: () => ctx.onEdit(row.id) },
    { key: "delete", label: "删除", artType: "delete", icon: "ri:delete-bin-4-line", perm: "module_video:alarm_rule:delete", run: () => ctx.onDelete(row.id) },
  ];
  return actions.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

const ruleSearchForm = ref<{ name?: string; alarm_type?: string }>({ name: undefined, alarm_type: undefined });
const ruleShowSearch = ref(true);
const ruleSearchRules: Record<string, unknown> = {};
const ruleSearchItems = computed<SearchFormItem[]>(() => [
  { label: "规则名称", key: "name", type: "input", props: { placeholder: "请输入规则名称", clearable: true }, span: 6 },
  { label: "告警类型", key: "alarm_type", type: "select", props: { placeholder: "请选择告警类型", clearable: true, options: alarmTypeOptions }, span: 6 },
]);

const ruleTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds: ruleSelectedIds, batchDeleting: ruleBatchDeleting, onTableSelectionChange: onRuleTableSelectionChange } = useTableSelection<any>();

async function deleteRuleRow(id: number) {
  try {
    await confirmDelete();
    await VideoAPI.deleteAlarmRule([id]);
    ElMessage.success("删除成功");
    ruleTableRef.value?.elTableRef?.clearSelection();
    await refreshRuleRemove();
  } catch { /* cancel */ }
}
async function handleRuleBatchDelete() {
  const ids = ruleSelectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    ruleBatchDeleting.value = true;
    await VideoAPI.deleteAlarmRule(ids);
    ElMessage.success("删除成功");
    ruleTableRef.value?.elTableRef?.clearSelection();
    await refreshRuleRemove();
  } catch { /* cancel */ } finally { ruleBatchDeleting.value = false; }
}

const ruleDialogVisible = reactive({ title: "", visible: false, type: "create" as "create" | "update" });
const ruleForm = reactive({
  id: undefined as number | undefined, name: undefined as string | undefined, camera_id: undefined as number | undefined,
  algorithm_task_id: undefined as number | undefined, alarm_type: "MOTION", severity: "WARNING", sensitivity: 50,
  interval_seconds: 30, notify_channels: [] as string[], schedule_json: null as any, status: true, description: undefined as string | undefined,
});
const ruleSubmitLoading = ref(false);
const ruleFormRef = ref<any>(null);
const ruleChannelSelection = ref<string[]>([]);
const ruleChannelEmailTo = ref("");
const ruleChannelSmsPhones = ref("");
const ruleChannelWebhookUrl = ref("");
const ruleChannelWebhookMethod = ref("POST");
const ruleChannelWebhookSecret = ref("");
const ruleChannelWebhookHeaders = ref("");
const ruleChannelWebhookTemplate = ref("");
const alarm_vars = computed(() => ({
  alarm_type: "{{alarm_type}}", severity: "{{severity}}", camera_name: "{{camera_name}}", alarm_time: "{{alarm_time}}",
  description: "{{description}}", rule_name: "{{rule_name}}", snapshot_url: "{{snapshot_url}}", payload: "{{payload}}",
}));

const ruleScheduleGrid = ref<boolean[][]>(Array.from({ length: 7 }, () => Array(24).fill(false)));
const ruleDragState = ref<{ active: boolean; mode: "set" | "clear" }>({ active: false, mode: "set" });
function onRuleCellMouseDown(day: number, hour: number, e: MouseEvent) {
  if (e.button !== 0) return;
  const current = ruleScheduleGrid.value[day][hour];
  ruleDragState.value = { active: true, mode: current ? "clear" : "set" };
  ruleScheduleGrid.value[day][hour] = !current;
}
function onRuleCellMouseEnter(day: number, hour: number) { if (ruleDragState.value.active) ruleScheduleGrid.value[day][hour] = ruleDragState.value.mode === "set"; }
function onRuleDragEnd() { ruleDragState.value.active = false; }
function fillRuleSchedule(val: boolean) { for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) ruleScheduleGrid.value[d][h] = val; }
function fillRuleWorkHours() { fillRuleSchedule(false); for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) ruleScheduleGrid.value[d][h] = true; }
function ruleScheduleGridToJson() {
  const slots: { day: number; start: number; end: number }[] = [];
  for (let d = 0; d < 7; d++) {
    let start = -1;
    for (let h = 0; h <= 24; h++) {
      const active = h < 24 && ruleScheduleGrid.value[d][h];
      if (active && start === -1) start = h;
      if (!active && start !== -1) { slots.push({ day: d, start, end: h }); start = -1; }
    }
  }
  return slots.length ? { type: "weekly", slots } : null;
}
function jsonToRuleScheduleGrid(json: any) {
  ruleScheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  if (!json?.slots) return;
  for (const slot of json.slots) if (slot.day >= 0 && slot.day < 7) for (let h = slot.start; h < slot.end && h < 24; h++) ruleScheduleGrid.value[slot.day][h] = true;
}
function resetRuleChannels() {
  ruleChannelSelection.value = [];
  ruleChannelEmailTo.value = ""; ruleChannelSmsPhones.value = ""; ruleChannelWebhookUrl.value = "";
  ruleChannelWebhookMethod.value = "POST"; ruleChannelWebhookSecret.value = ""; ruleChannelWebhookHeaders.value = ""; ruleChannelWebhookTemplate.value = "";
}

async function handleOpenRuleDialog(type: "create" | "update", id?: number) {
  ruleDialogVisible.type = type;
  if (id && type === "update") {
    ruleDialogVisible.title = "编辑规则";
    const res = await VideoAPI.listAlarmRule({ page_no: 1, page_size: 100 });
    const item = (res.data?.data?.items || []).find((i: any) => i.id === id);
    if (item) {
      Object.assign(ruleForm, item);
      jsonToRuleScheduleGrid(ruleForm.schedule_json);
      resetRuleChannels();
      for (const entry of item.notify_channels || []) {
        if (typeof entry === "string") ruleChannelSelection.value.push(entry);
        else if (typeof entry === "object" && entry.channel) {
          ruleChannelSelection.value.push(entry.channel);
          if (entry.channel === "EMAIL" && entry.recipients) ruleChannelEmailTo.value = (entry.recipients as string[]).join(", ");
          if (entry.channel === "SMS" && entry.phones) ruleChannelSmsPhones.value = (entry.phones as string[]).join(", ");
          if (entry.channel === "WEBHOOK") {
            ruleChannelWebhookUrl.value = entry.url || "";
            ruleChannelWebhookMethod.value = entry.method || "POST";
            ruleChannelWebhookSecret.value = entry.secret || "";
            ruleChannelWebhookHeaders.value = entry.headers ? JSON.stringify(entry.headers) : "";
            ruleChannelWebhookTemplate.value = entry.template || "";
          }
        }
      }
    }
  } else {
    ruleDialogVisible.title = "新增规则";
    ruleForm.id = undefined;
    ruleForm.camera_id = undefined;
    ruleForm.algorithm_task_id = undefined;
    ruleForm.schedule_json = null;
    ruleScheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
    resetRuleChannels();
  }
  ruleDialogVisible.visible = true;
}
function buildNotifyChannels(): any[] {
  const result: any[] = [];
  for (const ch of ruleChannelSelection.value) {
    if (ch === "EMAIL" && ruleChannelEmailTo.value.trim()) result.push({ channel: "EMAIL", recipients: ruleChannelEmailTo.value.split(",").map(s => s.trim()).filter(Boolean) });
    else if (ch === "SMS" && ruleChannelSmsPhones.value.trim()) result.push({ channel: "SMS", phones: ruleChannelSmsPhones.value.split(",").map(s => s.trim()).filter(Boolean) });
    else if (ch === "WEBHOOK" && ruleChannelWebhookUrl.value.trim()) {
      const entry: any = { channel: "WEBHOOK", url: ruleChannelWebhookUrl.value.trim(), method: ruleChannelWebhookMethod.value };
      if (ruleChannelWebhookSecret.value.trim()) entry.secret = ruleChannelWebhookSecret.value.trim();
      if (ruleChannelWebhookHeaders.value.trim()) { try { entry.headers = JSON.parse(ruleChannelWebhookHeaders.value.trim()); } catch { /* skip */ } }
      if (ruleChannelWebhookTemplate.value.trim()) entry.template = ruleChannelWebhookTemplate.value.trim();
      result.push(entry);
    } else result.push(ch);
  }
  return result;
}
async function handleSubmitRule() {
  ruleSubmitLoading.value = true;
  const id = ruleForm.id;
  try {
    const payload: any = {
      name: ruleForm.name, camera_id: ruleForm.camera_id, algorithm_task_id: ruleForm.algorithm_task_id || null,
      alarm_type: ruleForm.alarm_type, severity: ruleForm.severity, sensitivity: ruleForm.sensitivity,
      interval_seconds: ruleForm.interval_seconds, notify_channels: buildNotifyChannels(),
      schedule_json: ruleScheduleGridToJson(), status: ruleForm.status, description: ruleForm.description || null,
    };
    if (id) await VideoAPI.updateAlarmRule(id, payload);
    else await VideoAPI.createAlarmRule(payload);
    ElMessage.success("保存成功");
    ruleDialogVisible.visible = false;
    await refreshRuleData();
  } catch { /* ignore */ } finally { ruleSubmitLoading.value = false; }
}

const ruleOpCtx = { onEdit: (id: number) => void handleOpenRuleDialog("update", id), onDelete: deleteRuleRow };

const { columns: ruleColumns, columnChecks: ruleColChecks, data: ruleData, loading: ruleLoading, pagination: rulePagination, getData: getRuleData, replaceSearchParams: replaceRuleSearchParams, resetSearchParams: resetRuleSearchParams, handleSizeChange: handleRuleSizeChange, handleCurrentChange: handleRuleCurrentChange, refreshData: refreshRuleData, refreshRemove: refreshRuleRemove } = useTable({
  core: {
    apiFn: VideoAPI.listAlarmRule,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<any>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "规则名称", minWidth: 150, showOverflowTooltip: true },
      { prop: "alarm_type", label: "告警类型", width: 120 },
      { prop: "severity", label: "级别", width: 80, align: "center", formatter: (row: any) => h(ElTag, { type: severityTag(row.severity), size: "small", effect: "dark" }, () => row.severity) },
      { prop: "sensitivity", label: "灵敏度", width: 80, align: "center" },
      { prop: "interval_seconds", label: "间隔(秒)", width: 90, align: "center" },
      { prop: "status", label: "状态", width: 80, align: "center" },
      { prop: "operation", label: "操作", width: 140, fixed: "right", align: "right", formatter: (row: any) => renderTableOperationCell(buildRuleActions(row, ruleOpCtx), { wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1" }) },
    ],
  },
});
function handleRuleSearch(params: { name?: string; alarm_type?: string }) {
  replaceRuleSearchParams(cleanEmptyArrayParams({ ...params }));
  getRuleData();
}
function onRuleResetSearch() {
  ruleSearchForm.value = { name: undefined, alarm_type: undefined };
  void resetRuleSearchParams();
}

onBeforeMount(() => {
  Promise.all([VideoAPI.listCamera({ page_size: 100 }), VideoAPI.listAlgorithmTask({ page_size: 100 })])
    .then(([c, t]) => { cameraOptions.value = c.data?.data?.items || []; algorithmTaskOptions.value = t.data?.data?.items || []; })
    .catch(() => {});
  document.addEventListener("mouseup", onRuleDragEnd);
});
onBeforeUnmount(() => { document.removeEventListener("mouseup", onRuleDragEnd); });
</script>

<style scoped>
.page-tabs { display: flex; flex: 1; flex-direction: column; width: 100%; min-height: 0; }
.page-tabs :deep(.el-tabs__header) { flex-shrink: 0; }
.page-tabs :deep(.el-tabs__content) { display: flex; flex: 1; flex-direction: column; min-height: 0; overflow: hidden; }
.page-tabs :deep(.el-tab-pane) { box-sizing: border-box; display: flex; flex: 1; flex-direction: column; min-height: 0; }
.detail-snapshot { margin-bottom: 16px; overflow: hidden; background: #000; border-radius: 6px; }
.detail-snapshot-empty { display: flex; align-items: center; justify-content: center; height: 200px; font-size: 14px; color: #666; background: var(--el-fill-color); }
.detail-info { margin-bottom: 16px; }
.ai-result { max-height: 200px; padding: 8px; margin: 0; overflow-y: auto; font-size: 12px; line-height: 1.5; color: var(--el-text-color-secondary); background: var(--el-fill-color-lighter); border-radius: 4px; }
.detail-actions { display: flex; gap: 8px; }
.text-muted { color: var(--el-text-color-placeholder); }
.schedule-grid-wrapper { padding-bottom: 4px; overflow-x: auto; }
.schedule-header-row { display: flex; gap: 2px; margin-bottom: 2px; }
.schedule-corner { flex-shrink: 0; width: 44px; }
.schedule-header-cell { flex-shrink: 0; width: 24px; font-size: 10px; line-height: 20px; color: var(--el-text-color-placeholder); text-align: center; }
.schedule-row { display: flex; gap: 2px; align-items: center; margin-bottom: 2px; }
.schedule-day-label { flex-shrink: 0; width: 44px; padding-right: 6px; font-size: 12px; color: var(--el-text-color-secondary); text-align: right; }
.schedule-cell { flex-shrink: 0; width: 24px; height: 20px; cursor: pointer; background: var(--el-fill-color); border: 1px solid var(--el-border-color-lighter); border-radius: 2px; transition: all 0.15s; }
.schedule-cell:hover { border-color: var(--el-color-primary); }
.schedule-cell.active { background: var(--el-color-primary); border-color: var(--el-color-primary); }
.schedule-actions { display: flex; gap: 6px; margin-top: 8px; }
.notify-config-block { margin-top: 8px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.notify-config-label { margin-bottom: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.notify-webhook-row { display: flex; gap: 8px; }
.notify-config-hint { margin-top: 4px; font-size: 11px; line-height: 1.6; color: var(--el-text-color-placeholder); }
.notify-config-hint code { padding: 0 2px; font-family: monospace; color: var(--el-color-primary); background: var(--el-fill-color); border-radius: 2px; }
</style>
