<template>
  <div class="app-container">
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane :label="t('video.alarm.recordTab')" name="record">
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
                  <el-empty :image-size="80" :description="t('video.common.noData')" />
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
                  :label="t('video.common.sequence')"
                  width="60"
                >
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'alarm_time')?.show"
                  key="alarm_time"
                  :label="t('video.alarm.alarmTime')"
                  prop="alarm_time"
                  width="160"
                  sortable
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'snapshot')?.show"
                  key="snapshot"
                  :label="t('video.alarm.snapshot')"
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
                  :label="t('video.alarm.camera')"
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
                  :label="t('video.alarm.triggerRule')"
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
                  :label="t('video.alarm.alarmType')"
                  prop="alarm_type"
                  width="110"
                  show-overflow-tooltip
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'severity')?.show"
                  key="severity"
                  :label="t('video.alarm.severity')"
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
                  :label="t('video.common.status')"
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
                  :label="t('video.common.description')"
                  prop="description"
                  min-width="160"
                  show-overflow-tooltip
                />
                <el-table-column
                  v-if="recordCols.find((col) => col.prop === 'operation')?.show"
                  fixed="right"
                  :label="t('video.common.operation')"
                  align="center"
                  min-width="200"
                >
                  <template #default="scope">
                    <el-button
                      icon="View"
                      size="small"
                      type="primary"
                      link
                      @click="handleViewDetail(scope.row)"
                    >
                      {{ t("video.alarm.detail") }}
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'PENDING'"
                      v-hasPerm="['module_video:alarm:confirm']"
                      size="small"
                      type="success"
                      plain
                      @click="handleConfirm(scope.row.id, 'CONFIRMED')"
                    >
                      {{ t("video.alarm.confirm") }}
                    </el-button>
                    <el-button
                      v-if="scope.row.status === 'PENDING'"
                      v-hasPerm="['module_video:alarm:confirm']"
                      size="small"
                      plain
                      @click="handleConfirm(scope.row.id, 'FALSE_ALARM')"
                    >
                      {{ t("video.alarm.falseAlarm") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_video:alarm:delete']"
                      icon="delete"
                      size="small"
                      type="danger"
                      link
                      @click="handleRecordDelete(scope.row.id)"
                    >
                      {{ t("video.common.delete") }}
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </PageContent>
      </el-tab-pane>

      <el-tab-pane :label="t('video.alarm.ruleTab')" name="rule" lazy>
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
                  <el-empty :image-size="80" :description="t('video.common.noData')" />
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
                  :label="t('video.common.sequence')"
                  width="60"
                >
                  <template #default="scope">
                    {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'name')?.show"
                  key="name"
                  :label="t('video.alarm.ruleName')"
                  prop="name"
                  min-width="150"
                  show-overflow-tooltip
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'scope')?.show"
                  key="scope"
                  :label="t('video.alarm.scope')"
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
                  :label="t('video.alarm.alarmType')"
                  prop="alarm_type"
                  width="120"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'severity')?.show"
                  key="severity"
                  :label="t('video.alarm.severity')"
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
                  :label="t('video.alarm.sensitivity')"
                  prop="sensitivity"
                  width="80"
                  align="center"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'interval_seconds')?.show"
                  key="interval_seconds"
                  :label="t('video.alarm.interval')"
                  prop="interval_seconds"
                  width="90"
                  align="center"
                />
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'rollout')?.show"
                  key="rollout"
                  :label="t('video.alarm.rollout')"
                  min-width="190"
                  show-overflow-tooltip
                >
                  <template #default="scope">
                    <span v-if="ruleRolloutSummary(scope.row)">
                      {{ ruleRolloutSummary(scope.row) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column
                  v-if="ruleCols.find((col) => col.prop === 'status')?.show"
                  key="status"
                  :label="t('video.common.status')"
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
                  :label="t('video.common.operation')"
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
                      {{ t("video.common.edit") }}
                    </el-button>
                    <el-button
                      v-hasPerm="['module_video:alarm_rule:delete']"
                      type="danger"
                      size="small"
                      link
                      icon="delete"
                      @click="handleRuleDelete(scope.row.id)"
                    >
                      {{ t("video.common.delete") }}
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
        <el-form-item :label="t('video.alarm.ruleName')" prop="name">
          <el-input v-model="ruleForm.name" :placeholder="t('video.alarm.enterRuleName')" />
        </el-form-item>
        <el-form-item :label="t('video.alarm.algoTask')" prop="algorithm_task_id">
          <el-select
            v-model="ruleForm.algorithm_task_id"
            filterable
            clearable
            :placeholder="t('video.alarm.selectTask')"
            style="width: 100%"
          >
            <el-option
              v-for="task in algorithmTaskOptions"
              :key="task.id"
              :label="(task.camera?.name || '?') + ' — ' + (task.algorithm?.name || '?')"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('video.alarm.ruleScene')" prop="scene_type">
          <RuleEditor
            ref="ruleEditorRef"
            v-model="ruleEditorModel"
            :scene-type="ruleForm.scene_type"
            @update:scene-type="handleSceneTypeChange"
          />
        </el-form-item>
        <el-form-item :label="t('video.alarm.severity')" prop="severity">
          <el-select v-model="ruleForm.severity" style="width: 100%">
            <el-option :label="t('video.alarm.severityCritical')" value="CRITICAL" />
            <el-option :label="t('video.alarm.severityWarning')" value="WARNING" />
            <el-option :label="t('video.alarm.severityInfo')" value="INFO" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('video.alarm.notifyChannels')" prop="notify_channels">
          <div style="width: 100%">
            <el-checkbox-group v-model="ruleChannelSelection">
              <el-checkbox label="WS_PUSH">{{ t("video.alarm.wsPush") }}</el-checkbox>
              <el-checkbox label="SMS">{{ t("video.alarm.sms") }}</el-checkbox>
              <el-checkbox label="EMAIL">{{ t("video.alarm.email") }}</el-checkbox>
              <el-checkbox label="WEBHOOK">{{ t("video.alarm.webhook") }}</el-checkbox>
            </el-checkbox-group>
            <div v-if="ruleChannelSelection.includes('EMAIL')" class="notify-config-block">
              <div class="notify-config-label">{{ t("video.alarm.emailRecipients") }}</div>
              <el-input
                v-model="ruleChannelEmailTo"
                :placeholder="t('video.alarm.emailPlaceholder')"
                clearable
                size="small"
              />
            </div>
            <div v-if="ruleChannelSelection.includes('SMS')" class="notify-config-block">
              <div class="notify-config-label">{{ t("video.alarm.smsPhones") }}</div>
              <el-input
                v-model="ruleChannelSmsPhones"
                :placeholder="t('video.alarm.smsPlaceholder')"
                clearable
                size="small"
              />
            </div>
            <div v-if="ruleChannelSelection.includes('WEBHOOK')" class="notify-config-block">
              <div class="notify-config-label">{{ t("video.alarm.webhookUrl") }}</div>
              <div class="notify-webhook-row">
                <el-select v-model="ruleChannelWebhookMethod" size="small" style="width: 100px">
                  <el-option label="POST" value="POST" />
                  <el-option label="GET" value="GET" />
                </el-select>
                <el-input
                  v-model="ruleChannelWebhookUrl"
                  :placeholder="t('video.alarm.webhookUrlPlaceholder')"
                  clearable
                  size="small"
                />
              </div>
              <div class="notify-config-label" style="margin-top: 6px">
                {{ t("video.alarm.webhookSecret") }}
              </div>
              <el-input
                v-model="ruleChannelWebhookSecret"
                :placeholder="t('video.alarm.webhookSecretPlaceholder')"
                clearable
                size="small"
                type="password"
                show-password
              />
              <div class="notify-config-label" style="margin-top: 6px">
                {{ t("video.alarm.webhookHeaders") }}
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
                {{ t("video.alarm.webhookTemplate") }}
              </div>
              <el-input
                v-model="ruleChannelWebhookTemplate"
                :placeholder="t('video.alarm.webhookTemplatePlaceholder')"
                clearable
                size="small"
                :rows="3"
                type="textarea"
              />
              <div class="notify-config-hint">
                {{ t("video.alarm.availableVars") }}
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
            <el-form-item :label="t('video.alarm.sensitivity')" prop="sensitivity">
              <el-slider v-model="ruleForm.sensitivity" :min="1" :max="100" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('video.alarm.interval')" prop="interval_seconds">
              <el-input-number
                v-model="ruleForm.interval_seconds"
                :min="1"
                :max="3600"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('video.common.status')" prop="status">
          <el-switch v-model="ruleForm.status" />
        </el-form-item>
        <el-form-item :label="t('video.common.description')" prop="description">
          <el-input
            v-model="ruleForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('video.common.optionalRemark')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseRuleDialog">{{ t("video.common.cancel") }}</el-button>
        <el-button type="primary" :loading="ruleSubmitLoading" @click="handleSubmitRule">
          {{ t("video.common.save") }}
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
          <el-descriptions-item :label="t('video.alarm.alarmTime')">
            {{ detailDrawer.data.alarm_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.alarm.camera')">
            {{ detailDrawer.data.camera?.name || detailDrawer.data.camera_id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.alarm.triggerRule')">
            {{ detailDrawer.data.rule?.name || "-" }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.alarm.ruleScopeDetail')">
            {{ ruleScopeText(detailDrawer.data.rule_id) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.alarm.alarmType')">
            {{ detailDrawer.data.alarm_type }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.alarm.severeLevel')">
            <el-tag :type="severityTag(detailDrawer.data.severity)" size="small" effect="dark">
              {{ detailDrawer.data.severity }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.common.status')">
            <el-tag :type="statusTag(detailDrawer.data.status)" size="small">
              {{ statusLabel(detailDrawer.data.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailDrawer.data.confirm_time"
            :label="t('video.alarm.confirmTime')"
          >
            {{ detailDrawer.data.confirm_time }}
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailDrawer.data.confirm_user"
            :label="t('video.alarm.confirmUser')"
          >
            {{ detailDrawer.data.confirm_user }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('video.alarm.videoClip')">
            <span v-if="detailDrawer.data.video_clip_path">
              {{ detailDrawer.data.video_clip_path }}
            </span>
            <span v-else class="text-muted">{{ t("video.alarm.none") }}</span>
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detailDrawer.data.ai_result"
            :label="t('video.alarm.aiResult')"
          >
            <pre class="ai-result">{{ JSON.stringify(detailDrawer.data.ai_result, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>

        <div class="detail-actions">
          <el-button
            v-if="detailDrawer.data.status === 'PENDING'"
            type="success"
            @click="handleConfirm(detailDrawer.data.id, 'CONFIRMED')"
          >
            {{ t("video.alarm.confirmAlarm") }}
          </el-button>
          <el-button
            v-if="detailDrawer.data.status === 'PENDING'"
            @click="handleConfirm(detailDrawer.data.id, 'FALSE_ALARM')"
          >
            {{ t("video.alarm.markFalse") }}
          </el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onBeforeMount, computed } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import { getAlgorithmTaskList } from "@/api/module_video/deploy";
import {
  getAlarmRecordList,
  getAlarmRuleList,
  getAlarmRuleDetail,
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
import type { AlarmRuleRollout, AlarmRuleScope } from "@/api/module_video/alarm";
import RuleEditor, { type RuleEditorValue } from "./components/RuleEditor.vue";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const activeTab = ref("record");
const { t } = useI18n();

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
  detailDrawer.title = t("video.alarm.detailTitle", { type: row.alarm_type });
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
      label: t("video.alarm.camera"),
      type: "select",
      options: [],
      attrs: {
        placeholder: t("video.alarm.selectCamera"),
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
      label: t("video.alarm.severity"),
      type: "select",
      options: [
        { label: t("video.alarm.severityCritical"), value: "CRITICAL" },
        { label: t("video.alarm.severityWarning"), value: "WARNING" },
        { label: t("video.alarm.severityInfo"), value: "INFO" },
      ],
      attrs: {
        placeholder: t("video.alarm.selectSeverity"),
        clearable: true,
        style: { width: "140px" },
      },
    },
    {
      prop: "status",
      label: t("video.common.status"),
      type: "select",
      options: [
        { label: t("video.alarm.pending"), value: "PENDING" },
        { label: t("video.alarm.confirmed"), value: "CONFIRMED" },
        { label: t("video.alarm.ignored"), value: "IGNORED" },
        { label: t("video.alarm.falseAlarm"), value: "FALSE_ALARM" },
      ],
      attrs: {
        placeholder: t("video.alarm.selectStatus"),
        clearable: true,
        style: { width: "140px" },
      },
    },
  ],
});

const recordCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "alarm_time", label: t("video.alarm.alarmTime"), show: true },
  { prop: "snapshot", label: t("video.alarm.snapshot"), show: true },
  { prop: "camera", label: t("video.alarm.camera"), show: true },
  { prop: "rule", label: t("video.alarm.triggerRule"), show: true },
  { prop: "alarm_type", label: t("video.alarm.alarmType"), show: true },
  { prop: "severity", label: t("video.alarm.severity"), show: true },
  { prop: "status", label: t("video.common.status"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
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
  deleteConfirm: {
    title: t("video.common.warning"),
    message: t("video.common.deleteConfirmMsg"),
    type: "warning",
  },
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
      label: t("video.alarm.ruleName"),
      type: "input",
      attrs: { placeholder: t("video.alarm.enterRuleName"), clearable: true },
    },
    {
      prop: "alarm_type",
      label: t("video.alarm.alarmType"),
      type: "select",
      options: [
        { label: t("video.alarm.motionDetect"), value: "MOTION" },
        { label: t("video.alarm.lineCrossing"), value: "LINE_CROSSING" },
        { label: t("video.alarm.areaIntrusion"), value: "INTRUSION" },
        { label: t("video.alarm.faceDetect"), value: "FACE_DETECT" },
        { label: t("video.alarm.movement"), value: "MOVEMENT" },
        { label: t("video.alarm.videoBlock"), value: "VIDEO_BLOCK" },
        { label: t("video.alarm.videoLost"), value: "VIDEO_LOST" },
      ],
      attrs: {
        placeholder: t("video.alarm.selectAlarmType"),
        clearable: true,
        style: { width: "167.5px" },
      },
    },
  ],
});

const ruleCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: t("video.common.selection"), show: true },
  { prop: "index", label: t("video.common.sequence"), show: true },
  { prop: "name", label: t("video.alarm.ruleName"), show: true },
  { prop: "scope", label: t("video.alarm.scope"), show: true },
  { prop: "alarm_type", label: t("video.alarm.alarmType"), show: true },
  { prop: "severity", label: t("video.alarm.severity"), show: true },
  { prop: "sensitivity", label: t("video.alarm.sensitivity"), show: true },
  { prop: "interval_seconds", label: t("video.alarm.interval"), show: true },
  { prop: "rollout", label: t("video.alarm.rollout"), show: true },
  { prop: "status", label: t("video.common.status"), show: true },
  { prop: "operation", label: t("video.common.operation"), show: true },
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
  deleteConfirm: {
    title: t("video.common.warning"),
    message: t("video.common.deleteConfirmMsg"),
    type: "warning",
  },
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
  rollout: {} as AlarmRuleRollout,
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
  rollout: {} as AlarmRuleRollout,
  status: true,
  description: undefined as string | undefined,
};

const ruleEditorRef = ref<InstanceType<typeof RuleEditor> | null>(null);

/** RuleEditor 的 v-model：作用域 / 目标 / 参数 / 条件 / 灰度直接落到 ruleForm */
const ruleEditorModel = computed<RuleEditorValue>({
  get: () => ({
    scope: ruleForm.scope,
    camera_id: ruleForm.camera_id,
    group_id: ruleForm.group_id,
    params: ruleForm.params,
    conditions: ruleForm.conditions,
    schedule_json: ruleForm.schedule_json,
    rollout: ruleForm.rollout,
  }),
  set: (v) => {
    ruleForm.scope = v?.scope ?? "camera";
    ruleForm.camera_id = v?.camera_id;
    ruleForm.group_id = v?.group_id;
    ruleForm.params = v?.params ?? {};
    ruleForm.conditions = v?.conditions ?? null;
    ruleForm.schedule_json = v?.schedule_json ?? null;
    ruleForm.rollout = v?.rollout ?? {};
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
    return t("video.alarm.ruleScopeGroup", { name: g?.name || `#${row.group_id}` });
  }
  if (row?.camera_id) {
    return t("video.alarm.ruleScopeCamera", { name: row?.camera?.name || `#${row.camera_id}` });
  }
  return "-";
}

/** 懒加载规则数据，供告警详情展示触发规则的作用域 */
async function ensureRuleLookup() {
  if (ruleLookupLoaded) return;
  try {
    // 分页静默拉取（后端 page_size 上限 100），避免一次性加载大量数据
    const map: Record<number, any> = {};
    let pageNo = 1;
    const pageSize = 100;
    for (;;) {
      const res = await getAlarmRuleList(
        { page_no: pageNo, page_size: pageSize },
        { silent: true }
      );
      const items = res.data?.data?.items ?? [];
      for (const item of items) map[item.id] = item;
      if (!res.data?.data?.has_next || items.length === 0) break;
      pageNo += 1;
    }
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

const WEEK_DAY_LABELS = [
  t("video.common.monday"),
  t("video.common.tuesday"),
  t("video.common.wednesday"),
  t("video.common.thursday"),
  t("video.common.friday"),
  t("video.common.saturday"),
  t("video.common.sunday"),
];

/** 生效时间段摘要：相同窗口的连续天合并，如「周一至周五 09:00-18:00」；无配置返回空串 */
function ruleScheduleSummary(json: any): string {
  const slots: any[] = Array.isArray(json?.slots) ? json.slots : [];
  if (!slots.length) return "";
  const byDay = new Map<number, string>();
  for (const slot of slots) {
    const day = Number(slot?.day);
    const start = Number(slot?.start);
    const end = Number(slot?.end);
    if (!Number.isInteger(day) || day < 0 || day > 6 || !(end > start)) continue;
    const text = `${String(start).padStart(2, "0")}:00-${String(end).padStart(2, "0")}:00`;
    byDay.set(day, byDay.has(day) ? `${byDay.get(day)}、${text}` : text);
  }
  if (!byDay.size) return "";
  const parts: string[] = [];
  let start = -1;
  let end = -1;
  let win = "";
  const flush = () => {
    if (start < 0) return;
    const label =
      start === end
        ? WEEK_DAY_LABELS[start]
        : t("video.alarm.mondayToFriday", {
            start: WEEK_DAY_LABELS[start],
            end: WEEK_DAY_LABELS[end],
          });
    parts.push(`${label} ${win}`);
  };
  for (let d = 0; d < 7; d++) {
    const cur = byDay.get(d);
    if (!cur) {
      flush();
      start = -1;
      end = -1;
      win = "";
      continue;
    }
    if (start >= 0 && cur === win && d === end + 1) {
      end = d;
    } else {
      flush();
      start = d;
      end = d;
      win = cur;
    }
  }
  flush();
  return parts.join("，");
}

/** 规则灰度摘要：比例 / 白名单 / 黑名单 / 生效时段；无任何灰度配置返回空串（列表不显示） */
function ruleRolloutSummary(row: any): string {
  const rollout = row?.rollout || {};
  const parts: string[] = [];
  const percent = rollout.percent;
  if (typeof percent === "number" && percent < 100) {
    parts.push(percent <= 0 ? t("video.alarm.notEffective") : `${percent}%`);
  }
  if (Array.isArray(rollout.whitelist) && rollout.whitelist.length) {
    parts.push(t("video.alarm.whitelist", { count: rollout.whitelist.length }));
  }
  if (Array.isArray(rollout.blacklist) && rollout.blacklist.length) {
    parts.push(t("video.alarm.blacklist", { count: rollout.blacklist.length }));
  }
  const schedule = ruleScheduleSummary(row?.schedule_json);
  if (schedule) parts.push(schedule);
  return parts.join(" · ");
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
  ruleForm.schedule_json = null;
  ruleForm.rollout = {};
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
    ruleDialogVisible.title = t("video.alarm.editRule");
    // 按 id 精确取回（不再只取前 100 条做匹配：规则数 >100 时会把编辑误判为新建）
    let item: any = null;
    try {
      const res = await getAlarmRuleDetail(id);
      item = res.data?.data ?? null;
    } catch {
      ElMessage.error(t("video.alarm.ruleNotExist"));
      return;
    }
    if (!item) {
      ElMessage.error(t("video.alarm.ruleNotExist"));
      return;
    }
    // 无条件回填 id：即便后续字段异常也绝不允许退化为「新建」
    ruleForm.id = id;
    Object.assign(ruleForm, item);
    ruleForm.id = id;
    // 回填作用域：有 group_id 即组规则，否则相机规则（camera_id/group_id 恰有其一）
    ruleForm.scope = item.group_id ? "group" : "camera";
    ruleForm.camera_id = item.camera_id ?? undefined;
    ruleForm.group_id = item.group_id ?? undefined;
    // 回填场景规则：场景码存于 alarm_type，params/conditions 原样取回
    ruleForm.params = item.params || {};
    ruleForm.conditions = item.conditions || null;
    ruleForm.scene_type = item.alarm_type || undefined;
    // 灰度配置回填：缺省 {} 表示全量生效
    ruleForm.schedule_json = item.schedule_json || null;
    ruleForm.rollout = item.rollout || {};
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
  } else {
    ruleDialogVisible.title = t("video.alarm.addRule");
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
      schedule_json: ruleForm.schedule_json || null,
      // 灰度配置：{percent, whitelist, blacklist}，{} = 全量生效
      rollout: ruleForm.rollout || {},
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
    ElMessage.success(t("video.common.saveSuccess"));
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
    PENDING: t("video.alarm.pending"),
    CONFIRMED: t("video.alarm.confirmed"),
    IGNORED: t("video.alarm.ignored"),
    FALSE_ALARM: t("video.alarm.falseAlarm"),
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
  // 规则列表「作用域」列需展示组名，进页即预加载组选项
  ensureGroupOptions();
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
