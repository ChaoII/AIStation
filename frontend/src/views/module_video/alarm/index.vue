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
                  v-if="recordCols.find((col) => col.prop === 'snapshot')?.show"
                  key="snapshot"
                  label="快照"
                  width="72"
                  align="center"
                >
                  <template #default="scope">
                    <SnapshotImage
                      :src="scope.row.snapshot_url || scope.row.snapshot_path"
                      :width="48"
                      :height="32"
                    />
                  </template>
                </el-table-column>
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

      <el-tab-pane label="告警规则" name="rule" lazy>
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
                  v-if="ruleCols.find((col) => col.prop === 'scope')?.show"
                  key="scope"
                  label="作用域"
                  min-width="150"
                  show-overflow-tooltip
                >
                  <template #default="scope">
                    {{ ruleScopeLabel(scope.row) }}
                  </template>
                </el-table-column>
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
      width="960px"
      @close="handleCloseRuleDialog"
    >
      <el-form ref="ruleFormRef" :model="ruleForm" label-width="100px" size="default">
        <el-form-item label="规则名称" prop="name">
          <el-input v-model="ruleForm.name" placeholder="请输入规则名称" />
        </el-form-item>
        <el-form-item label="算法布控任务" prop="algorithm_task_id">
          <el-select
            v-model="ruleForm.algorithm_task_id"
            filterable
            clearable
            placeholder="可选—关联智能布控任务"
            style="width: 100%"
          >
            <el-option
              v-for="t in algorithmTaskOptions"
              :key="t.id"
              :label="(t.camera?.name || '?') + ' — ' + (t.algorithm?.name || '?')"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="规则场景" prop="scene_type">
          <RuleEditor
            ref="ruleEditorRef"
            v-model="ruleEditorModel"
            :scene-type="ruleForm.scene_type"
            @update:scene-type="handleSceneTypeChange"
          />
        </el-form-item>
        <el-form-item label="级别" prop="severity">
          <el-select v-model="ruleForm.severity" style="width: 100%">
            <el-option label="严重" value="CRITICAL" />
            <el-option label="警告" value="WARNING" />
            <el-option label="信息" value="INFO" />
          </el-select>
        </el-form-item>
        <el-form-item label="通知方式" prop="notify_channels">
          <div style="width: 100%">
            <el-checkbox-group v-model="ruleChannelSelection">
              <el-checkbox label="WS_PUSH">WS 推送</el-checkbox>
              <el-checkbox label="SMS">短信</el-checkbox>
              <el-checkbox label="EMAIL">邮件</el-checkbox>
              <el-checkbox label="WEBHOOK">Webhook/REST API</el-checkbox>
            </el-checkbox-group>
            <div v-if="ruleChannelSelection.includes('EMAIL')" class="notify-config-block">
              <div class="notify-config-label">邮件收件人</div>
              <el-input
                v-model="ruleChannelEmailTo"
                placeholder="admin@example.com, ops@example.com（逗号分隔）"
                clearable
                size="small"
              />
            </div>
            <div v-if="ruleChannelSelection.includes('SMS')" class="notify-config-block">
              <div class="notify-config-label">短信接收号码</div>
              <el-input
                v-model="ruleChannelSmsPhones"
                placeholder="13800138000, 13900139000（逗号分隔）"
                clearable
                size="small"
              />
            </div>
            <div v-if="ruleChannelSelection.includes('WEBHOOK')" class="notify-config-block">
              <div class="notify-config-label">Webhook URL</div>
              <div class="notify-webhook-row">
                <el-select v-model="ruleChannelWebhookMethod" size="small" style="width: 100px">
                  <el-option label="POST" value="POST" />
                  <el-option label="GET" value="GET" />
                </el-select>
                <el-input
                  v-model="ruleChannelWebhookUrl"
                  placeholder="https://hooks.example.com/alarm"
                  clearable
                  size="small"
                />
              </div>
              <div class="notify-config-label" style="margin-top: 6px">签名密钥（可选）</div>
              <el-input
                v-model="ruleChannelWebhookSecret"
                placeholder="留空则使用全局配置"
                clearable
                size="small"
                type="password"
                show-password
              />
              <div class="notify-config-label" style="margin-top: 6px">
                自定义请求头（JSON 格式，可选）
              </div>
              <el-input
                v-model="ruleChannelWebhookHeaders"
                placeholder='{"Authorization": "Bearer xxx"}'
                clearable
                size="small"
                :rows="2"
                type="textarea"
              />
              <div class="notify-config-label" style="margin-top: 6px">
                请求体模板（可选，支持变量替换）
              </div>
              <el-input
                v-model="ruleChannelWebhookTemplate"
                placeholder='留空则发送完整JSON: {"alarm_id":1,"alarm_type":"INTRUSION",...}'
                clearable
                size="small"
                :rows="3"
                type="textarea"
              />
              <div class="notify-config-hint">
                可用变量:
                <code>{{ alarm_vars.alarm_type }}</code>
                <code>{{ alarm_vars.severity }}</code>
                <code>{{ alarm_vars.camera_name }}</code>
                <code>{{ alarm_vars.alarm_time }}</code>
                <code>{{ alarm_vars.description }}</code>
                <code>{{ alarm_vars.rule_name }}</code>
                <code>{{ alarm_vars.snapshot_url }}</code>
                <code>{{ alarm_vars.payload }}</code>
              </div>
            </div>
          </div>
        </el-form-item>
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
        <el-form-item label="生效时段">
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
                :class="{ active: ruleScheduleGrid[day - 1]?.[hour - 1] }"
                @mousedown.prevent="onRuleCellMouseDown(day - 1, hour - 1, $event)"
                @mouseenter="onRuleCellMouseEnter(day - 1, hour - 1)"
              />
            </div>
          </div>
          <div class="schedule-actions">
            <el-button size="small" @click="fillRuleSchedule(true)">全选</el-button>
            <el-button size="small" @click="fillRuleSchedule(false)">清空</el-button>
            <el-button size="small" @click="fillRuleWorkHours">工作日 08-18</el-button>
          </div>
        </el-form-item>
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
          <SnapshotOverlayViewer
            :src="detailDrawer.data.snapshot_url || detailDrawer.data.snapshot_path"
            :objects="
              detailDrawer.data.ai_result?.objects ?? detailDrawer.data.ai_result?.detections ?? []
            "
            height="420px"
          />
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
          <el-descriptions-item label="规则作用域">
            {{ ruleScopeText(detailDrawer.data.rule_id) }}
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
import { ref, reactive, onBeforeMount, computed } from "vue";
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import { getAlgorithmTaskList } from "@/api/module_video/deploy";
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
import { cachedOptions } from "@/composables/useOptions";
import SnapshotImage from "@/components/Common/SnapshotImage.vue";
import SnapshotOverlayViewer from "@/components/SnapshotOverlayViewer/index.vue";
import type { AlarmRuleScope } from "@/api/module_video/alarm";
import RuleEditor, { type RuleEditorValue } from "./components/RuleEditor.vue";

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
/** 相机组选项（扁平化，用于规则作用域选择与列表/详情展示） */
const groupOptions = ref<any[]>([]);
/** 规则 id → 规则原始数据（告警详情里展示触发规则的作用域） */
const ruleLookup = ref<Record<number, any>>({});
let ruleLookupLoaded = false;
const algorithmTaskOptions = ref<any[]>([]);
const ruleScheduleGrid = ref<boolean[][]>(Array.from({ length: 7 }, () => Array(24).fill(false)));
const ruleDragState = ref<{ active: boolean; mode: "set" | "clear" }>({
  active: false,
  mode: "set",
});
const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

const ruleChannelSelection = ref<string[]>([]);
const ruleChannelEmailTo = ref("");
const ruleChannelSmsPhones = ref("");
const ruleChannelWebhookUrl = ref("");
const ruleChannelWebhookMethod = ref("POST");
const ruleChannelWebhookSecret = ref("");
const ruleChannelWebhookHeaders = ref("");
const ruleChannelWebhookTemplate = ref("");

const alarm_vars = computed(() => ({
  alarm_type: "{{alarm_type}}",
  severity: "{{severity}}",
  camera_name: "{{camera_name}}",
  alarm_time: "{{alarm_time}}",
  description: "{{description}}",
  rule_name: "{{rule_name}}",
  snapshot_url: "{{snapshot_url}}",
  payload: "{{payload}}",
}));

const detailDrawer = reactive({
  visible: false,
  title: "",
  data: null as any,
});

function handleViewDetail(row: any) {
  detailDrawer.data = row;
  detailDrawer.title = `告警详情 - ${row.alarm_type}`;
  detailDrawer.visible = true;
  ensureGroupOptions();
  ensureRuleLookup();
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
        onVisibleChange: (v: boolean) => {
          if (v) ensureCameraOptions();
        },
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
  { prop: "snapshot", label: "快照", show: true },
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
  { prop: "scope", label: "作用域", show: true },
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
  // 作用域：相机 / 相机组（camera_id 与 group_id 恰有其一）
  scope: "camera" as AlarmRuleScope,
  camera_id: undefined as number | undefined,
  group_id: undefined as number | undefined,
  algorithm_task_id: undefined as number | undefined,
  alarm_type: "MOTION",
  severity: "WARNING",
  sensitivity: 50,
  interval_seconds: 30,
  notify_channels: [] as string[],
  schedule_json: null as any,
  status: true,
  description: undefined as string | undefined,
  // 场景规则编辑器新增字段（spec §4.6）
  scene_type: undefined as string | undefined,
  params: {} as Record<string, unknown>,
  conditions: null as Record<string, unknown> | null,
});

const initialRuleForm = {
  id: undefined as number | undefined,
  name: undefined as string | undefined,
  scope: "camera" as AlarmRuleScope,
  camera_id: undefined as number | undefined,
  group_id: undefined as number | undefined,
  algorithm_task_id: undefined as number | undefined,
  alarm_type: "MOTION" as const,
  severity: "WARNING" as const,
  sensitivity: 50,
  interval_seconds: 30,
  notify_channels: [] as string[],
  schedule_json: null as any,
  status: true,
  description: undefined as string | undefined,
};

const ruleEditorRef = ref<InstanceType<typeof RuleEditor> | null>(null);

/** RuleEditor 的 v-model：作用域 / 目标 / 参数 / 条件直接落到 ruleForm */
const ruleEditorModel = computed<RuleEditorValue>({
  get: () => ({
    scope: ruleForm.scope,
    camera_id: ruleForm.camera_id,
    group_id: ruleForm.group_id,
    params: ruleForm.params,
    conditions: ruleForm.conditions,
  }),
  set: (v) => {
    ruleForm.scope = v?.scope ?? "camera";
    ruleForm.camera_id = v?.camera_id;
    ruleForm.group_id = v?.group_id;
    ruleForm.params = v?.params ?? {};
    ruleForm.conditions = v?.conditions ?? null;
  },
});

/** 相机组选项加载（扁平化树） */
async function ensureGroupOptions() {
  if (groupOptions.value.length) return;
  try {
    const res = await getCameraGroupList();
    groupOptions.value = flattenGroupTree(res.data?.data || []);
  } catch {
    /* noop */
  }
}

function flattenGroupTree(nodes: any[], out: any[] = []): any[] {
  for (const node of nodes || []) {
    if (node?.id !== undefined) out.push({ id: node.id, name: node.name });
    if (Array.isArray(node?.children)) flattenGroupTree(node.children, out);
  }
  return out;
}

/** 规则列表「作用域」列文案：相机名 / 组名 */
function ruleScopeLabel(row: any): string {
  if (row?.group_id) {
    const g = groupOptions.value.find((x) => x.id === row.group_id);
    return `相机组：${g?.name || `#${row.group_id}`}`;
  }
  if (row?.camera_id) {
    return `相机：${row?.camera?.name || `#${row.camera_id}`}`;
  }
  return "-";
}

/** 懒加载规则数据，供告警详情展示触发规则的作用域 */
async function ensureRuleLookup() {
  if (ruleLookupLoaded) return;
  try {
    const res = await getAlarmRuleList({ page_no: 1, page_size: 200 });
    const map: Record<number, any> = {};
    for (const item of res.data?.data?.items ?? []) map[item.id] = item;
    ruleLookup.value = map;
    ruleLookupLoaded = true;
  } catch {
    /* noop */
  }
}

/** 告警详情「规则作用域」文案（按触发规则解析） */
function ruleScopeText(ruleId?: number): string {
  const rule = ruleId != null ? ruleLookup.value[ruleId] : undefined;
  if (!rule) return "-";
  return ruleScopeLabel(rule);
}

/** 场景码即告警类型（后端以 alarm_type 作为场景/算法类型持久化） */
function handleSceneTypeChange(code: string) {
  ruleForm.scene_type = code || undefined;
  ruleForm.alarm_type = code || ruleForm.alarm_type;
}

function onRuleCellMouseDown(day: number, hour: number, e: MouseEvent) {
  if (e.button !== 0) return;
  const current = ruleScheduleGrid.value[day][hour];
  ruleDragState.value = { active: true, mode: current ? "clear" : "set" };
  ruleScheduleGrid.value[day][hour] = !current;
}

function onRuleCellMouseEnter(day: number, hour: number) {
  if (!ruleDragState.value.active) return;
  ruleScheduleGrid.value[day][hour] = ruleDragState.value.mode === "set";
}

function onRuleDragEnd() {
  ruleDragState.value.active = false;
}

function fillRuleSchedule(val: boolean) {
  for (let d = 0; d < 7; d++) for (let h = 0; h < 24; h++) ruleScheduleGrid.value[d][h] = val;
}

function fillRuleWorkHours() {
  fillRuleSchedule(false);
  for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) ruleScheduleGrid.value[d][h] = true;
}

function ruleScheduleGridToJson() {
  const slots: { day: number; start: number; end: number }[] = [];
  for (let d = 0; d < 7; d++) {
    let start = -1;
    for (let h = 0; h <= 24; h++) {
      const active = h < 24 && ruleScheduleGrid.value[d][h];
      if (active && start === -1) start = h;
      if (!active && start !== -1) {
        slots.push({ day: d, start, end: h });
        start = -1;
      }
    }
  }
  return slots.length ? { type: "weekly", slots } : null;
}

function jsonToRuleScheduleGrid(json: any) {
  ruleScheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  if (!json?.slots) return;
  for (const slot of json.slots) {
    if (slot.day >= 0 && slot.day < 7) {
      for (let h = slot.start; h < slot.end && h < 24; h++) {
        ruleScheduleGrid.value[slot.day][h] = true;
      }
    }
  }
}

async function resetRuleForm() {
  if (ruleFormRef.value) {
    ruleFormRef.value.resetFields();
    ruleFormRef.value.clearValidate();
  }
  Object.assign(ruleForm, initialRuleForm);
  // 场景编辑器字段单独重置，避免与 initialRuleForm 共享引用
  ruleForm.scene_type = undefined;
  ruleForm.params = {};
  ruleForm.conditions = null;
  ruleScheduleGrid.value = Array.from({ length: 7 }, () => Array(24).fill(false));
  ruleChannelSelection.value = [];
  ruleChannelEmailTo.value = "";
  ruleChannelSmsPhones.value = "";
  ruleChannelWebhookUrl.value = "";
  ruleChannelWebhookMethod.value = "POST";
  ruleChannelWebhookSecret.value = "";
  ruleChannelWebhookHeaders.value = "";
  ruleChannelWebhookTemplate.value = "";
}

async function handleCloseRuleDialog() {
  ruleDialogVisible.visible = false;
  await resetRuleForm();
}

async function handleOpenRuleDialog(type: "create" | "update", id?: number) {
  ruleDialogVisible.type = type;
  ensureCameraOptions();
  ensureGroupOptions();
  ensureAlgorithmTaskOptions();
  if (id && type === "update") {
    ruleDialogVisible.title = "编辑规则";
    const res = await getAlarmRuleList({ page_no: 1, page_size: 100 });
    const item = res.data.data.items.find((i: any) => i.id === id);
    if (item) {
      Object.assign(ruleForm, item);
      // 回填作用域：有 group_id 即组规则，否则相机规则（camera_id/group_id 恰有其一）
      ruleForm.scope = item.group_id ? "group" : "camera";
      ruleForm.camera_id = item.camera_id ?? undefined;
      ruleForm.group_id = item.group_id ?? undefined;
      // 回填场景规则：场景码存于 alarm_type，params/conditions 原样取回（无 detail 接口，走列表）
      ruleForm.params = item.params || {};
      ruleForm.conditions = item.conditions || null;
      ruleForm.scene_type = item.alarm_type || undefined;
      jsonToRuleScheduleGrid(ruleForm.schedule_json);
      // Parse notify_channels into selection + per-channel config
      const channels = item.notify_channels || [];
      ruleChannelSelection.value = [];
      ruleChannelEmailTo.value = "";
      ruleChannelSmsPhones.value = "";
      ruleChannelWebhookUrl.value = "";
      ruleChannelWebhookMethod.value = "POST";
      ruleChannelWebhookSecret.value = "";
      ruleChannelWebhookHeaders.value = "";
      ruleChannelWebhookTemplate.value = "";
      for (const entry of channels) {
        if (typeof entry === "string") {
          ruleChannelSelection.value.push(entry);
        } else if (typeof entry === "object" && entry.channel) {
          ruleChannelSelection.value.push(entry.channel);
          if (entry.channel === "EMAIL" && entry.recipients) {
            ruleChannelEmailTo.value = (entry.recipients as string[]).join(", ");
          }
          if (entry.channel === "SMS" && entry.phones) {
            ruleChannelSmsPhones.value = (entry.phones as string[]).join(", ");
          }
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
  }
  ruleDialogVisible.visible = true;
}

function buildNotifyChannels(): any[] {
  const result: any[] = [];
  for (const ch of ruleChannelSelection.value) {
    if (ch === "EMAIL" && ruleChannelEmailTo.value.trim()) {
      result.push({
        channel: "EMAIL",
        recipients: ruleChannelEmailTo.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
    } else if (ch === "SMS" && ruleChannelSmsPhones.value.trim()) {
      result.push({
        channel: "SMS",
        phones: ruleChannelSmsPhones.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
    } else if (ch === "WEBHOOK" && ruleChannelWebhookUrl.value.trim()) {
      const entry: any = {
        channel: "WEBHOOK",
        url: ruleChannelWebhookUrl.value.trim(),
        method: ruleChannelWebhookMethod.value,
      };
      if (ruleChannelWebhookSecret.value.trim())
        entry.secret = ruleChannelWebhookSecret.value.trim();
      if (ruleChannelWebhookHeaders.value.trim()) {
        try {
          entry.headers = JSON.parse(ruleChannelWebhookHeaders.value.trim());
        } catch {
          /* skip invalid json */
        }
      }
      if (ruleChannelWebhookTemplate.value.trim())
        entry.template = ruleChannelWebhookTemplate.value.trim();
      result.push(entry);
    } else {
      result.push(ch);
    }
  }
  return result;
}

async function handleSubmitRule() {
  // 场景规则校验（未配置场景数据时可跳过，保持既有规则创建路径可用）
  if (ruleEditorRef.value && !ruleEditorRef.value.validate()) return;
  ruleSubmitLoading.value = true;
  const id = ruleForm.id;
  try {
    // 作用域：camera_id 与 group_id 恰有其一（另一个显式置 null 以支持编辑时切换作用域）
    const isGroupScope = ruleForm.scope === "group";
    const payload: any = {
      name: ruleForm.name,
      camera_id: isGroupScope ? null : (ruleForm.camera_id ?? null),
      group_id: isGroupScope ? (ruleForm.group_id ?? null) : null,
      scope: ruleForm.scope,
      algorithm_task_id: ruleForm.algorithm_task_id || null,
      alarm_type: ruleForm.alarm_type,
      severity: ruleForm.severity,
      sensitivity: ruleForm.sensitivity,
      interval_seconds: ruleForm.interval_seconds,
      notify_channels: buildNotifyChannels(),
      schedule_json: ruleScheduleGridToJson(),
      status: ruleForm.status,
      description: ruleForm.description || null,
      // 场景规则：算法/场景类型 + 参数原值 + 条件树（后端编译展开后落库）
      algorithm_type: ruleForm.scene_type,
      params: ruleForm.params || {},
      conditions: ruleForm.conditions || null,
    };
    if (id) {
      await updateAlarmRule(id, payload);
    } else {
      await createAlarmRule(payload);
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
    recordContentRef.value?.fetchPageData();
  } catch {
    //
  }
}

function severityTag(severity: string): any {
  const map: Record<string, string> = { CRITICAL: "danger", WARNING: "warning", INFO: "info" };
  return map[(severity || "").toUpperCase()] || "info";
}

function statusTag(status: string): any {
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

// 摄像机/算法任务下拉：懒加载 + 缓存
async function ensureCameraOptions() {
  if (cameraOptions.value.length) return;
  try {
    cameraOptions.value = await cachedOptions(
      "video:cameras",
      async () => (await getCameraList({ page_size: 100 })).data?.data?.items || []
    );
    const searchItem: any = (recordSearchConfig.formItems || []).find(
      (i: any) => i.prop === "camera_id"
    );
    if (searchItem) {
      searchItem.options = cameraOptions.value.map((c: any) => ({ label: c.name, value: c.id }));
    }
  } catch {
    /* noop */
  }
}

async function ensureAlgorithmTaskOptions() {
  if (algorithmTaskOptions.value.length) return;
  try {
    algorithmTaskOptions.value = await cachedOptions(
      "video:algorithmTasks",
      async () => (await getAlgorithmTaskList({ page_size: 100 })).data?.data?.items || []
    );
  } catch {
    /* noop */
  }
}

onBeforeMount(() => {
  document.addEventListener("mouseup", onRuleDragEnd);
  // 规则列表「作用域」列需展示组名，进页即预加载组选项
  ensureGroupOptions();
});
onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onRuleDragEnd);
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

/* Schedule Grid */
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
.notify-config-block {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.notify-config-label {
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.notify-webhook-row {
  display: flex;
  gap: 8px;
}
.notify-config-hint {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.6;
  color: var(--el-text-color-placeholder);
}
.notify-config-hint code {
  padding: 0 2px;
  font-family: monospace;
  color: var(--el-color-primary);
  background: var(--el-fill-color);
  border-radius: 2px;
}
</style>
