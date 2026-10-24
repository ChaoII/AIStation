<!-- 治理面板（Governance / Oversight）：驾驶舱 + ABAC + DQ + 数据域 + 本体对象。
     作为「数据与集成」的一个内嵌区块，承载原「治理」菜单的 5 个子模块。 -->
<template>
  <div class="gp-wrap">
    <el-tabs v-model="tab" @tab-change="onTab">
      <!-- 驾驶舱 -->
      <el-tab-pane :label="t('ai_workflow.ig_govOverview')" name="overview">
        <el-card shadow="never" style="margin-bottom: 12px">
          <template #header>{{ t("ai_workflow.ig_govTitle") }}</template>
          <el-row :gutter="12">
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govObject')"
                :value="g.overview?.objects ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_datasource')"
                :value="g.overview?.datasources ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govPipeline')"
                :value="g.overview?.pipelines ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govAbac')"
                :value="g.overview?.access_rules ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govDomain')"
                :value="g.overview?.domains ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govAgent')"
                :value="g.overview?.agents ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govActionAudit')"
                :value="g.overview?.action_logs ?? 0"
              />
            </el-col>
            <el-col :span="3">
              <el-statistic
                :title="t('ai_workflow.ig_govAvgScore')"
                :value="g.overview?.dq?.avg_score ?? 0"
                :precision="1"
              />
            </el-col>
          </el-row>
        </el-card>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header>
                <div class="gp-head">
                  <span>{{ t("ai_workflow.ig_govDqTitle") }}</span>
                  <el-tag v-if="(g.overview?.dq_alerts ?? 0) > 0" size="small" type="danger">
                    {{ t("ai_workflow.ig_govAlertCount", { count: g.overview.dq_alerts }) }}
                  </el-tag>
                </div>
              </template>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item :label="t('ai_workflow.ig_govAvgScore')">
                  {{ g.overview?.dq?.avg_score ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_govHealthWarnTotal')">
                  {{ g.overview?.dq?.healthy ?? 0 }} / {{ g.overview?.dq?.risk ?? 0 }} /
                  {{ g.overview?.dq?.total ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
              <div class="gp-section">{{ t("ai_workflow.ig_govQualityAlerts") }}</div>
              <div v-for="a in g.overview?.alert_list || []" :key="a.table" class="gp-alert">
                <el-tag size="small" type="danger">{{ a.alias }}</el-tag>
                <span class="gp-score">
                  {{ t("ai_workflow.ig_govHealthScore", { score: a.score }) }}
                </span>
                <div class="gp-down">
                  <el-tag
                    v-for="o in a.downstream.objects"
                    :key="o"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    {{ t("ai_workflow.ig_govObjectItem", { object: o }) }}
                  </el-tag>
                  <el-tag
                    v-for="m in a.downstream.metrics"
                    :key="m"
                    size="small"
                    type="primary"
                    effect="plain"
                  >
                    {{ t("ai_workflow.ig_govMetricItem", { metric: m }) }}
                  </el-tag>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header>{{ t("ai_workflow.ig_govAssetsTitle") }}</template>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item :label="t('ai_workflow.ig_metric')">
                  {{ g.overview?.metrics ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_term')">
                  {{ g.overview?.terms ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_govOntConcept')">
                  {{ g.overview?.concepts ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_govObjectApp')">
                  {{ g.overview?.workshop_apps ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_govActionDef')">
                  {{ g.overview?.actions ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item :label="t('ai_workflow.ig_govActionAudit')">
                  {{ g.overview?.action_logs ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
              <div class="gp-section">{{ t("ai_workflow.ig_govRecentRuns") }}</div>
              <el-table
                :data="g.overview?.pipeline_runs || []"
                size="small"
                max-height="200"
                border
                stripe
              >
                <el-table-column
                  prop="name"
                  :label="t('ai_workflow.ig_pipeline')"
                  min-width="120"
                />
                <el-table-column :label="t('ai_workflow.ig_govStatus')" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.status === 'success' ? 'success' : 'info'">
                      {{ row.status }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="at"
                  :label="t('ai_workflow.ig_govRunTime')"
                  min-width="140"
                  show-overflow-tooltip
                />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ABAC 权限 -->
      <el-tab-pane :label="t('ai_workflow.ig_govAccess')" name="access">
        <div class="gp-bar">
          <el-button type="primary" size="small" :icon="Plus" @click="openAccess()">
            {{ t("ai_workflow.ig_govNewPolicy") }}
          </el-button>
          <el-button size="small" @click="openMatrix">
            {{ t("ai_workflow.ig_govMatrix") }}
          </el-button>
          <el-button size="small" @click="openSandbox">
            {{ t("ai_workflow.ig_govSandbox") }}
          </el-button>
          <el-tag size="small" type="info" effect="plain">
            {{ t("ai_workflow.ig_govPolicyCount", { count: accessRules.length }) }}
          </el-tag>
        </div>
        <el-alert
          type="info"
          :closable="false"
          style="margin-bottom: 10px"
          :title="t('ai_workflow.ig_govAbacAlert')"
        />
        <el-table :data="accessRules" size="small" border stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoPolicy')" :image-size="60" />
          </template>
          <el-table-column
            prop="name"
            :label="t('ai_workflow.ig_govPolicy')"
            min-width="130"
            show-overflow-tooltip
          />
          <el-table-column prop="attribute" :label="t('ai_workflow.ig_govAttribute')" width="80" />
          <el-table-column
            prop="value"
            :label="t('ai_workflow.ig_govAttributeValue')"
            width="120"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.ig_govAllowedObjects')" min-width="150">
            <template #default="{ row }">
              <el-tag
                v-for="titem in row.allowed_tables"
                :key="titem"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ titem }}
              </el-tag>
              <el-tag v-if="!row.allowed_tables?.length" size="small" type="info" effect="plain">
                {{ t("ai_workflow.ig_all") }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_govSensitiveOk')" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.sensitive_ok ? 'success' : 'info'" effect="plain">
                {{ row.sensitive_ok ? t("ai_workflow.ig_yes") : t("ai_workflow.ig_no") }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_action')" width="110" align="center">
            <template #default="{ row }">
              <el-button icon="edit" link type="primary" size="small" @click="editAccess(row)">
                {{ t("ai_workflow.ig_edit") }}
              </el-button>
              <el-button link type="danger" size="small" @click="delAccess(row)">
                {{ t("ai_workflow.ig_govDel") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 数据质量 -->
      <el-tab-pane :label="t('ai_workflow.ig_govDq')" name="dq">
        <div class="gp-bar">
          <el-button
            type="primary"
            size="small"
            :icon="Refresh"
            :loading="dqScanning"
            @click="scanAll"
          >
            {{ t("ai_workflow.ig_govScanAll") }}
          </el-button>
          <el-tag size="small" type="info" effect="plain">
            {{
              t("ai_workflow.ig_govDqSummary", {
                avg: dqData.avg_score ?? "-",
                healthy: dqData.healthy ?? 0,
                risk: dqData.risk ?? 0,
              })
            }}
          </el-tag>
        </div>
        <div v-if="dqAlerts.length" class="gp-alert gp-alert--warn">
          <el-alert
            type="warning"
            :closable="false"
            :title="t('ai_workflow.ig_govDqAlert', { count: dqAlerts.length })"
            show-icon
          />
        </div>
        <el-table :data="dqData.items || []" size="small" border stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoDq')" :image-size="60" />
          </template>
          <el-table-column
            prop="alias"
            :label="t('ai_workflow.ig_govObject')"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column
            prop="table"
            :label="t('ai_workflow.ig_tableName')"
            min-width="140"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.ig_govQuality')" width="170">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.score || 0)"
                :color="
                  (row.score || 0) >= 80
                    ? 'var(--el-color-success)'
                    : (row.score || 0) >= 60
                      ? 'var(--el-color-warning)'
                      : 'var(--el-color-danger)'
                "
                :stroke-width="10"
              />
            </template>
          </el-table-column>
          <el-table-column prop="total" :label="t('ai_workflow.ig_govRowCount')" width="80" />
          <el-table-column :label="t('ai_workflow.ig_govIssue')" min-width="180">
            <template #default="{ row }">
              <el-tag
                v-for="(i, k) in row.issues || []"
                :key="k"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                {{ i }}
              </el-tag>
              <span v-if="!(row.issues || []).length" class="gp-empty">
                {{ t("ai_workflow.ig_none") }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 数据域 -->
      <el-tab-pane :label="t('ai_workflow.ig_govDomain')" name="domain">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
          :title="t('ai_workflow.ig_govDomainAlert')"
        />
        <div class="gp-bar">
          <el-button type="primary" size="small" :icon="Plus" @click="openDomain()">
            {{ t("ai_workflow.ig_govNewDomain") }}
          </el-button>
          <el-tag size="small" type="info" effect="plain">
            {{
              t("ai_workflow.ig_govDomainCount", {
                count: domainView.domains?.length || 0,
                unassigned: domainView.unassigned?.length || 0,
              })
            }}
          </el-tag>
        </div>
        <el-row :gutter="12">
          <el-col v-for="d in domainView.domains || []" :key="d.id" :span="12">
            <el-card shadow="never" style="margin-bottom: 12px">
              <template #header>
                <div class="gp-head">
                  <span>
                    <el-tag size="small" type="primary" effect="dark">{{ d.name }}</el-tag>
                    <el-tag size="small" type="info" effect="plain" style="margin-left: 6px">
                      {{ d.code }}
                    </el-tag>
                  </span>
                  <el-button icon="edit" link type="primary" size="small" @click="editDomain(d)">
                    {{ t("ai_workflow.ig_edit") }}
                  </el-button>
                  <el-button link type="danger" size="small" @click="delDomain(d)">
                    {{ t("ai_workflow.ig_govDel") }}
                  </el-button>
                </div>
              </template>
              <div class="gp-section">
                {{ t("ai_workflow.ig_govObjCount", { count: d.objects.length }) }}
              </div>
              <el-tag
                v-for="o in d.objects"
                :key="o.table"
                size="small"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                {{ o.alias }}
              </el-tag>
              <div class="gp-section">{{ t("ai_workflow.ig_govMemberIds") }}</div>
              <el-tag
                v-for="m in d.members"
                :key="m"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 0 3px 4px 0"
              >
                #{{ m }}
              </el-tag>
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 本体对象 -->
      <el-tab-pane :label="t('ai_workflow.ig_govOnt')" name="ontgov">
        <div class="gp-bar">
          <el-tag size="small" type="info" effect="plain">
            {{ t("ai_workflow.ig_govOntSummary", { avg: ontGov.avg_score ?? "-" }) }}
          </el-tag>
        </div>
        <el-table :data="ontGov.items || []" size="small" border stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoOnt')" :image-size="60" />
          </template>
          <el-table-column
            prop="name"
            :label="t('ai_workflow.ig_govOnt')"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column
            prop="table"
            :label="t('ai_workflow.ig_tableName')"
            min-width="110"
            show-overflow-tooltip
          />
          <el-table-column prop="rows" :label="t('ai_workflow.ig_govRowCount')" width="80" />
          <el-table-column :label="t('ai_workflow.ig_govQuality')" width="170">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.score || 0)"
                :color="
                  (row.score || 0) >= 80
                    ? 'var(--el-color-success)'
                    : (row.score || 0) >= 60
                      ? 'var(--el-color-warning)'
                      : 'var(--el-color-danger)'
                "
                :stroke-width="10"
              />
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_govSourcePipeline')" min-width="120">
            <template #default="{ row }">
              <el-tag
                v-for="p in row.source_pipelines"
                :key="p"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ p }}
              </el-tag>
              <span v-if="!row.source_pipelines.length" class="gp-empty">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_govDownstream')" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="m in row.downstream_metrics"
                :key="m"
                size="small"
                type="primary"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ t("ai_workflow.ig_govMetricItem", { metric: m }) }}
              </el-tag>
              <el-tag
                v-for="c in row.downstream_concepts"
                :key="c"
                size="small"
                type="success"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ t("ai_workflow.ig_govConceptItem", { concept: c }) }}
              </el-tag>
              <span
                v-if="!row.downstream_metrics.length && !row.downstream_concepts.length"
                class="gp-empty"
              >
                —
              </span>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_govIssue')" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="(i, k) in row.issues"
                :key="k"
                size="small"
                type="warning"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ i }}
              </el-tag>
              <span v-if="!row.issues.length" class="gp-empty">{{ t("ai_workflow.ig_none") }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 表级写回（旧版）：写回动作的待审批/定义/审计；新动作请到 本体 → 动作类型 -->
      <el-tab-pane :label="t('ai_workflow.ig_govAction')" name="action">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
          :title="t('ai_workflow.ig_govActionAlert')"
        />
        <div class="gp-bar">
          <el-tag size="small" type="info" effect="plain">
            {{
              t("ai_workflow.ig_govPendingCount", {
                pending: pendingActions.length,
                defs: actionList.length,
              })
            }}
          </el-tag>
        </div>
        <div class="gp-section">{{ t("ai_workflow.ig_govPendingSection") }}</div>
        <el-table :data="pendingActions" size="small" border style="margin-bottom: 16px" stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoPending')" :image-size="50" />
          </template>
          <el-table-column
            prop="action"
            :label="t('ai_workflow.ig_govAction')"
            width="120"
            show-overflow-tooltip
          />
          <el-table-column
            prop="table"
            :label="t('ai_workflow.ig_tableName')"
            min-width="130"
            show-overflow-tooltip
          />
          <el-table-column prop="key" :label="t('ai_workflow.ig_govRecord')" width="80" />
          <el-table-column :label="t('ai_workflow.ig_govParams')" min-width="160">
            <template #default="{ row }">
              <div class="gp-params">{{ JSON.stringify(row.params || {}) }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="operator" :label="t('ai_workflow.ig_operator')" width="80" />
          <el-table-column
            prop="time"
            :label="t('ai_workflow.ig_time')"
            min-width="150"
            show-overflow-tooltip
          />
          <el-table-column
            :label="t('ai_workflow.ig_action')"
            width="130"
            align="center"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button icon="Check" link type="primary" size="small" @click="apAction(row, true)">
                {{ t("ai_workflow.ig_govApprove") }}
              </el-button>
              <el-button icon="Close" link type="danger" size="small" @click="apAction(row, false)">
                {{ t("ai_workflow.ig_govReject") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="gp-section">{{ t("ai_workflow.ig_govDefSection") }}</div>
        <el-table :data="actionList" size="small" border stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoActionDef')" :image-size="50" />
          </template>
          <el-table-column
            prop="name"
            :label="t('ai_workflow.ig_govAction')"
            width="120"
            show-overflow-tooltip
          />
          <el-table-column
            prop="object_table"
            :label="t('ai_workflow.ig_tableName')"
            min-width="130"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.ig_govWritableCols')" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="c in row.writable_cols"
                :key="c"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ c }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            prop="validation"
            :label="t('ai_workflow.ig_govValidation')"
            min-width="120"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.ig_govNeedApprove')" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.approve ? 'warning' : 'info'" effect="plain">
                {{ row.approve ? t("ai_workflow.ig_yes") : t("ai_workflow.ig_no") }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_enabled')" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
                {{ row.enabled ? t("ai_workflow.ig_yes") : t("ai_workflow.ig_no") }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="gp-section">{{ t("ai_workflow.ig_govAuditLogSection") }}</div>
        <el-table :data="actionLogs" size="small" border max-height="260" stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoAuditLog')" :image-size="50" />
          </template>
          <el-table-column
            prop="action"
            :label="t('ai_workflow.ig_govAction')"
            width="120"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.ig_govResult')" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'approved' ? 'success' : 'info'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="operator" :label="t('ai_workflow.ig_operator')" width="80" />
          <el-table-column
            prop="time"
            :label="t('ai_workflow.ig_time')"
            min-width="150"
            show-overflow-tooltip
          />
        </el-table>
      </el-tab-pane>

      <!-- 交付命题：五步交付 / 影子校验（原 FDE 后端能力接入） -->
      <el-tab-pane :label="t('ai_workflow.ig_govFde')" name="fde">
        <div class="gp-bar">
          <el-button type="primary" size="small" :icon="Plus" @click="openFde()">
            {{ t("ai_workflow.ig_govNewFde") }}
          </el-button>
          <el-button size="small" @click="loadFde">{{ t("ai_workflow.ig_govRefresh") }}</el-button>
          <el-tag size="small" type="info" effect="plain">
            {{ t("ai_workflow.ig_govFdeCount", { count: fdeList.length }) }}
          </el-tag>
        </div>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 10px"
          :title="t('ai_workflow.ig_govFdeAlert')"
        />
        <el-table :data="fdeList" size="small" border stripe>
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoFde')" :image-size="60" />
          </template>
          <el-table-column
            prop="title"
            :label="t('ai_workflow.ig_govProposition')"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column
            prop="owner"
            :label="t('ai_workflow.ig_govOwner')"
            width="100"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.ig_govFiveSteps')" min-width="240">
            <template #default="{ row }">
              <el-tag
                v-for="(v, k) in row.steps"
                :key="k"
                size="small"
                :type="v === 'done' ? 'success' : v === 'doing' ? 'warning' : 'info'"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ FDE_STEP_LABELS[k] || k }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.ig_govShadow')" width="110" align="center">
            <template #default="{ row }">
              <el-tag
                v-if="row.shadow_result"
                size="small"
                :type="row.shadow_result === 'pass' ? 'success' : 'danger'"
                effect="plain"
              >
                {{ row.shadow_result }}
              </el-tag>
              <span v-else class="gp-empty">{{ t("ai_workflow.ig_govNotRun") }}</span>
            </template>
          </el-table-column>
          <el-table-column
            :label="t('ai_workflow.ig_action')"
            width="190"
            align="center"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button icon="edit" link type="primary" size="small" @click="openFde(row)">
                {{ t("ai_workflow.ig_edit") }}
              </el-button>
              <el-button
                icon="Checked"
                link
                type="primary"
                size="small"
                :disabled="!row.shadow_metric"
                @click="runFdeShadow(row)"
              >
                {{ t("ai_workflow.ig_govShadowCheck") }}
              </el-button>
              <el-button link type="danger" size="small" @click="removeFde(row)">
                {{ t("ai_workflow.ig_govDel") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 数据生命周期：对象发布/草稿/敏感/血缘概览 -->
      <el-tab-pane :label="t('ai_workflow.ig_govLifecycle')" name="lifecycle">
        <div class="gp-bar">
          <el-button size="small" @click="loadLifecycle">
            {{ t("ai_workflow.ig_govRefresh") }}
          </el-button>
          <el-tag size="small" type="info" effect="plain">
            {{ t("ai_workflow.ig_govLifecycleBoard") }}
          </el-tag>
        </div>
        <el-descriptions v-if="lifecycle" :column="5" border size="small">
          <el-descriptions-item :label="t('ai_workflow.ig_govTotalObjects')">
            {{ lifecycle.objects }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_workflow.ig_govPublished')">
            {{ lifecycle.published }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_workflow.ig_govDraft')">
            {{ lifecycle.draft }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_workflow.ig_govSensitiveObjects')">
            {{ lifecycle.sensitive_objects }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_workflow.ig_govTotalLineage')">
            {{ lifecycle.total_lineage }}
          </el-descriptions-item>
        </el-descriptions>
        <el-table
          :data="lifecycle?.objects_list || []"
          size="small"
          border
          style="margin-top: 12px"
          max-height="420"
          stripe
        >
          <template #empty>
            <el-empty :description="t('ai_workflow.ig_govNoPublished')" :image-size="60" />
          </template>
          <el-table-column
            prop="table"
            :label="t('ai_workflow.ig_tableName')"
            min-width="200"
            show-overflow-tooltip
          />
          <el-table-column
            prop="alias"
            :label="t('ai_workflow.ig_chineseName')"
            min-width="160"
            show-overflow-tooltip
          />
          <el-table-column
            prop="dq"
            :label="t('ai_workflow.ig_govQualityScore')"
            width="90"
            align="center"
          />
          <el-table-column
            prop="sens"
            :label="t('ai_workflow.ig_govSensitiveFields')"
            width="100"
            align="center"
          />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 权限策略编辑 -->
    <el-dialog
      v-model="accessDialog"
      :title="t('ai_workflow.ig_govAbacTitle')"
      width="520px"
      append-to-body
    >
      <el-form :model="accessForm" label-width="100px">
        <el-form-item :label="t('ai_workflow.ig_govPolicyName')" required>
          <el-input
            v-model="accessForm.name"
            :placeholder="t('ai_workflow.ig_govPolicyNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govAttribute')">
          <el-select v-model="accessForm.attribute" style="width: 100%">
            <el-option :label="t('ai_workflow.ig_govRoleOption')" value="role" />
            <el-option :label="t('ai_workflow.ig_govDeptOption')" value="dept" />
            <el-option :label="t('ai_workflow.ig_govDomainOption')" value="domain" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govAttributeValue')" required>
          <el-input
            v-model="accessForm.value"
            :placeholder="t('ai_workflow.ig_govValuePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govAllowedObjects')">
          <el-select
            v-model="accessForm.allowed_tables"
            multiple
            clearable
            filterable
            :placeholder="t('ai_workflow.ig_govEmptyAll')"
            style="width: 100%"
          >
            <el-option
              v-for="o in govObjects"
              :key="o.table"
              :label="(o.alias || o.table) + ' (' + o.table + ')'"
              :value="o.table"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govSensitiveOk')">
          <el-switch v-model="accessForm.sensitive_ok" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accessDialog = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" @click="saveAccessForm()">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 权限矩阵（按角色） -->
    <el-dialog
      v-model="matrixDialog"
      :title="t('ai_workflow.ig_govMatrixTitle')"
      width="900px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 10px"
        :title="t('ai_workflow.ig_govMatrixAlert')"
      />
      <el-table
        v-loading="matrixLoading"
        :data="matrixRows"
        size="small"
        border
        max-height="420"
        stripe
      >
        <template #empty>
          <el-empty :description="t('ai_workflow.ig_govNoRole')" :image-size="60" />
        </template>
        <el-table-column
          prop="name"
          :label="t('ai_workflow.ig_role')"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="t('ai_workflow.ig_code')"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_workflow.ig_govRestricted')" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.restricted ? 'warning' : 'info'" effect="plain">
              {{
                row.restricted
                  ? t("ai_workflow.ig_govRestricted")
                  : t("ai_workflow.ig_govUnrestricted")
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_workflow.ig_govQueryable')" min-width="200">
          <template #default="{ row }">
            <el-tag v-if="!row.restricted" size="small" type="info" effect="plain">
              {{ t("ai_workflow.ig_all") }}
            </el-tag>
            <template v-else>
              <el-tag
                v-for="tbl in row.tables.slice(0, 6)"
                :key="tbl"
                size="small"
                effect="plain"
                style="margin: 0 2px"
              >
                {{ tbl }}
              </el-tag>
              <el-text v-if="row.tables.length > 6" size="small" type="info">
                +{{ row.tables.length - 6 }}
              </el-text>
              <el-text v-if="!row.tables.length" size="small" type="info">
                {{ t("ai_workflow.ig_none") }}
              </el-text>
            </template>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_workflow.ig_govSensitiveOk')" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.sensitive_ok ? 'success' : 'info'" effect="plain">
              {{ row.sensitive_ok ? t("ai_workflow.ig_yes") : t("ai_workflow.ig_no") }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 权限预览 Check Access（按用户/角色预览可查表） -->
    <el-dialog
      v-model="sandboxDialog"
      :title="t('ai_workflow.ig_govSandboxTitle')"
      width="900px"
      append-to-body
    >
      <el-form label-width="80px" inline>
        <el-form-item :label="t('ai_workflow.ig_govByUser')">
          <el-input-number
            v-model="sandboxUserId"
            :min="0"
            :controls="false"
            style="width: 110px"
          />
          <el-button
            size="small"
            type="primary"
            :loading="sandboxLoading"
            style="margin-left: 8px"
            @click="runSandboxUser"
          >
            {{ t("ai_workflow.ig_govPreview") }}
          </el-button>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govByRole')">
          <el-select
            v-model="sandboxRole"
            size="small"
            clearable
            :placeholder="t('ai_workflow.ig_govSelectRole')"
            style="width: 160px"
          >
            <el-option v-for="r in matrixRows" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
          <el-button
            size="small"
            type="primary"
            :loading="sandboxLoading"
            style="margin-left: 8px"
            @click="runSandboxRole"
          >
            {{ t("ai_workflow.ig_govPreview") }}
          </el-button>
        </el-form-item>
      </el-form>
      <el-descriptions v-if="sandboxResult" :column="2" size="small" border>
        <el-descriptions-item :label="t('ai_workflow.ig_govSubject')">
          {{ sandboxResult.label }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.ig_govRestricted')">
          <el-tag size="small" :type="sandboxResult.restricted ? 'warning' : 'info'" effect="plain">
            {{
              sandboxResult.restricted
                ? t("ai_workflow.ig_govRestricted")
                : t("ai_workflow.ig_govUnrestricted")
            }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.ig_govQueryableCount')">
          {{ sandboxResult.count }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.ig_govSensitiveOk')">
          <el-tag
            size="small"
            :type="sandboxResult.sensitive_ok ? 'success' : 'info'"
            effect="plain"
          >
            {{ sandboxResult.sensitive_ok ? t("ai_workflow.ig_yes") : t("ai_workflow.ig_no") }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div v-if="sandboxResult" style="margin-top: 10px">
        <el-tag
          v-for="tbl in sandboxResult.tables"
          :key="tbl"
          size="small"
          effect="plain"
          style="margin: 2px"
        >
          {{ tbl }}
        </el-tag>
        <el-text v-if="!sandboxResult.tables.length" size="small" type="info">
          {{ t("ai_workflow.ig_govNoQueryable") }}
        </el-text>
      </div>
      <el-empty v-else :description="t('ai_workflow.ig_govSandboxEmpty')" :image-size="60" />
    </el-dialog>

    <!-- 交付命题编辑 -->
    <el-dialog
      v-model="fdeDlg"
      :title="fdeForm.id ? t('ai_workflow.ig_govEditFde') : t('ai_workflow.ig_govNewFdeTitle')"
      width="600px"
      append-to-body
    >
      <el-form :model="fdeForm" label-width="100px">
        <el-form-item :label="t('ai_workflow.ig_govFdeTitle')" required>
          <el-input
            v-model="fdeForm.title"
            :placeholder="t('ai_workflow.ig_govFdeTitlePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_description')">
          <el-input v-model="fdeForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govAcceptance')">
          <el-input v-model="fdeForm.criteria" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govOwner')">
          <el-input v-model="fdeForm.owner" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govFiveStepProgress')">
          <div class="gp-fde-steps">
            <div v-for="(label, k) in FDE_STEP_LABELS" :key="k" class="gp-fde-step">
              <span>{{ label }}</span>
              <el-select v-model="fdeForm.steps[k]" size="small" style="width: 100px">
                <el-option :label="t('ai_workflow.ig_govTodo')" value="todo" />
                <el-option :label="t('ai_workflow.ig_govDoing')" value="doing" />
                <el-option :label="t('ai_workflow.ig_govDone')" value="done" />
              </el-select>
            </div>
          </div>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govShadowMetric')">
          <el-input
            v-model="fdeForm.shadow_metric"
            :placeholder="t('ai_workflow.ig_govShadowMetricPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govGoldenStandard')">
          <el-input
            v-model="fdeForm.shadow_golden"
            :placeholder="t('ai_workflow.ig_govExpected')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govTolerance')">
          <el-input
            v-model="fdeForm.shadow_tolerance"
            :placeholder="t('ai_workflow.ig_govTolerancePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govDeliveryAssets')">
          <el-input
            v-model="fdeAssetsText"
            type="textarea"
            :rows="2"
            :placeholder="t('ai_workflow.ig_govDeliveryAssetsPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fdeDlg = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" :loading="savingFde" @click="saveFde">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 数据域编辑 -->
    <el-dialog
      v-model="domainDialog"
      :title="t('ai_workflow.ig_govDomainTitle')"
      width="520px"
      append-to-body
    >
      <el-form :model="domainForm" label-width="100px">
        <el-form-item :label="t('ai_workflow.ig_govDomainName')" required>
          <el-input
            v-model="domainForm.name"
            :placeholder="t('ai_workflow.ig_govDomainNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govDomainCode')">
          <el-input
            v-model="domainForm.code"
            :placeholder="t('ai_workflow.ig_govDomainCodePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_description')">
          <el-input v-model="domainForm.description" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govDomainObjects')">
          <el-select
            v-model="domainForm.tables"
            multiple
            filterable
            clearable
            :placeholder="t('ai_workflow.ig_govDomainObjectsPlaceholder')"
            style="width: 100%"
          >
            <el-option
              v-for="o in govObjects"
              :key="o.table"
              :label="(o.alias || o.table) + ' (' + o.table + ')'"
              :value="o.table"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.ig_govMemberUsers')">
          <el-select
            v-model="domainForm.members"
            multiple
            filterable
            clearable
            allow-create
            :placeholder="t('ai_workflow.ig_govMemberUsersPlaceholder')"
            style="width: 100%"
          >
            <el-option
              v-for="i in 5"
              :key="i"
              :label="t('ai_workflow.ig_govUserItem', { id: i })"
              :value="i"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="domainDialog = false">{{ t("ai_workflow.ig_cancel") }}</el-button>
        <el-button type="primary" @click="saveDomainForm()">
          {{ t("ai_workflow.ig_save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";

import {
  getGovernanceOverview,
  getOntologyGovernance,
  getAccessRules,
  getAccessMatrix,
  accessPreview,
  accessPreviewRole,
  getDqOverview,
  getDqAlert,
  scanAllDq,
  getDomainObjects,
  saveAccessRule,
  saveDomain,
  removeAccessRule,
  removeDomain,
  getQueryObjects,
  getActionList,
  getPendingActions,
  getActionLogs,
  approveAction,
  rejectAction,
  getFdeList,
  saveFdeProposition,
  deleteFdePropositions,
  fdeShadowCheck,
  getObjectLifecycle,
} from "@/api/module_ai/query";

defineOptions({ name: "GovernancePanel" });

const { t } = useI18n();

const tab = ref("overview");
const g = ref<any>({ overview: {} });
const accessRules = ref<any[]>([]);
// 权限矩阵 / 沙箱
const matrixDialog = ref(false);
const matrixRows = ref<any[]>([]);
const matrixLoading = ref(false);
const sandboxDialog = ref(false);
const sandboxUserId = ref(1);
const sandboxRole = ref("");
const sandboxLoading = ref(false);
const sandboxResult = ref<any>(null);

async function openMatrix() {
  matrixDialog.value = true;
  matrixLoading.value = true;
  try {
    const r = await getAccessMatrix();
    matrixRows.value = r.data?.data?.roles || [];
  } catch {
    matrixRows.value = [];
  } finally {
    matrixLoading.value = false;
  }
}

function openSandbox() {
  sandboxDialog.value = true;
  sandboxResult.value = null;
}

async function runSandboxUser() {
  sandboxLoading.value = true;
  try {
    const r = await accessPreview(sandboxUserId.value);
    const d = r.data?.data || {};
    sandboxResult.value = {
      label: t("ai_workflow.ig_govUserLabel", {
        id: d.user_id,
        role: d.superuser
          ? t("ai_workflow.ig_govSuperuser")
          : (d.roles || []).join("/") || t("ai_workflow.ig_govNoRoleText"),
      }),
      restricted: !!d.domain_restricted,
      count: d.count || 0,
      sensitive_ok: !!d.superuser,
      tables: d.allowed_tables || [],
    };
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_previewFail"));
  } finally {
    sandboxLoading.value = false;
  }
}

async function runSandboxRole() {
  if (!sandboxRole.value) {
    ElMessage.warning(t("ai_workflow.ig_govSelectRole"));
    return;
  }
  sandboxLoading.value = true;
  try {
    const r = await accessPreviewRole(sandboxRole.value);
    const d = r.data?.data || {};
    sandboxResult.value = {
      label: t("ai_workflow.ig_govRoleLabel", { role: d.role }),
      restricted: !!d.restricted,
      count: d.count || 0,
      sensitive_ok: !!d.sensitive_ok,
      tables: d.allowed_tables || [],
    };
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_previewFail"));
  } finally {
    sandboxLoading.value = false;
  }
}

// 交付命题（原 FDE 后端能力接入治理面板）
const FDE_STEP_LABELS: Record<string, string> = {
  diagnosis: t("ai_workflow.ig_govStepDiagnosis"),
  modeling: t("ai_workflow.ig_govStepModeling"),
  assembly: t("ai_workflow.ig_govStepAssembly"),
  shadow: t("ai_workflow.ig_govStepShadow"),
  handover: t("ai_workflow.ig_govStepHandover"),
};
const fdeList = ref<any[]>([]);
const fdeDlg = ref(false);
const fdeForm = ref<any>({});
const fdeAssetsText = ref("");
const savingFde = ref(false);

async function loadFde() {
  try {
    const r = await getFdeList();
    fdeList.value = r.data?.data || [];
  } catch {
    fdeList.value = [];
  }
}

function openFde(row?: any) {
  fdeForm.value = row
    ? { ...row, steps: { ...(row.steps || {}) } }
    : {
        title: "",
        description: "",
        criteria: "",
        owner: "",
        steps: {
          diagnosis: "todo",
          modeling: "todo",
          assembly: "todo",
          shadow: "todo",
          handover: "todo",
        },
        shadow_metric: "",
        shadow_golden: "",
        shadow_tolerance: "",
      };
  fdeAssetsText.value = (row?.delivery_assets || []).join("\n");
  fdeDlg.value = true;
}

async function saveFde() {
  if (!fdeForm.value.title?.trim()) {
    ElMessage.warning(t("ai_workflow.ig_govFdeTitleRequired"));
    return;
  }
  savingFde.value = true;
  try {
    const s = fdeForm.value.steps || {};
    await saveFdeProposition({
      ...fdeForm.value,
      step_diagnosis: s.diagnosis,
      step_modeling: s.modeling,
      step_assembly: s.assembly,
      step_shadow: s.shadow,
      step_handover: s.handover,
      delivery_assets: fdeAssetsText.value
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
    });
    ElMessage.success(t("ai_workflow.ig_saveSuccess"));
    fdeDlg.value = false;
    await loadFde();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    savingFde.value = false;
  }
}

async function removeFde(row: any) {
  await ElMessageBox.confirm(
    t("ai_workflow.ig_govDelFdeConfirm", { name: row.title }),
    t("ai_workflow.ig_govDelFdeTitle"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  );
  try {
    await deleteFdePropositions([row.id]);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    await loadFde();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_delFail"));
  }
}

async function runFdeShadow(row: any) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.ig_govShadowConfirm", {
        title: row.title,
        golden: row.shadow_golden || "-",
      }),
      t("ai_workflow.ig_govShadowTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.ig_govCheck"),
        cancelButtonText: t("ai_workflow.ig_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    const r = await fdeShadowCheck(row.id);
    const d = r.data?.data || {};
    ElMessage.success(
      t("ai_workflow.ig_govShadowResult", { result: d.result || t("ai_workflow.ig_govDone") })
    );
    await loadFde();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_govCheckFail"));
  }
}
const dqData = ref<any>({ avg_score: 0, healthy: 0, risk: 0, items: [] });
const lifecycle = ref<any>(null);

async function loadLifecycle() {
  try {
    const r = await getObjectLifecycle();
    lifecycle.value = r.data?.data || null;
  } catch {
    lifecycle.value = null;
  }
}
const dqAlerts = ref<any[]>([]);
const dqScanning = ref(false);
const domainView = ref<any>({ domains: [], unassigned: [], total_objects: 0 });
const ontGov = ref<any>({ avg_score: 0, items: [] });
const govObjects = ref<any[]>([]);
// 动作审批
const pendingActions = ref<any[]>([]);
const actionList = ref<any[]>([]);
const actionLogs = ref<any[]>([]);

async function loadOverview() {
  const r = await getGovernanceOverview();
  g.value = { overview: r.data?.data || {} };
}
async function loadOntGov() {
  const r = await getOntologyGovernance();
  ontGov.value = r.data?.data || { avg_score: 0, items: [] };
}
async function loadAccess() {
  const r = await getAccessRules();
  accessRules.value = r.data?.data || [];
}
async function loadDq() {
  const r = await getDqOverview();
  dqData.value = r.data?.data || { avg_score: 0, healthy: 0, risk: 0, items: [] };
}
async function loadDqAlert() {
  const r = await getDqAlert();
  dqAlerts.value = r.data?.data?.alerts || [];
}
async function loadDomain() {
  const r = await getDomainObjects();
  domainView.value = r.data?.data || { domains: [], unassigned: [], total_objects: 0 };
}
async function loadObjects() {
  const r = await getQueryObjects();
  govObjects.value = r.data?.data || [];
}

function onTab(name: any) {
  if (name === "overview") loadOverview();
  else if (name === "access") loadAccess();
  else if (name === "dq") {
    loadDq();
    loadDqAlert();
  } else if (name === "domain") loadDomain();
  else if (name === "ontgov") loadOntGov();
  else if (name === "action") loadAction();
  else if (name === "fde") loadFde();
  else if (name === "lifecycle") loadLifecycle();
}

// 动作审批：待审批/定义/日志
async function loadAction() {
  try {
    const [pa, al, lg] = await Promise.all([
      getPendingActions(50),
      getActionList(),
      getActionLogs(50),
    ]);
    pendingActions.value = pa.data?.data || [];
    actionList.value = al.data?.data || [];
    actionLogs.value = lg.data?.data || [];
  } catch {
    pendingActions.value = [];
    actionList.value = [];
    actionLogs.value = [];
  }
}

async function apAction(row: any, approve: boolean) {
  try {
    await (approve ? approveAction : rejectAction)({ approval_id: row.id });
    ElMessage.success(approve ? t("ai_workflow.ig_govApproved") : t("ai_workflow.ig_govRejected"));
    await loadAction();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_govOpFail"));
  }
}
async function scanAll() {
  dqScanning.value = true;
  try {
    await scanAllDq();
    ElMessage.success(t("ai_workflow.ig_govScanned"));
    await loadDq();
    await loadDqAlert();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_govScanFail"));
  } finally {
    dqScanning.value = false;
  }
}
function openAccess() {
  Object.assign(accessForm, {
    id: null,
    name: "",
    attribute: "role",
    value: "",
    allowed_tables: [],
    sensitive_ok: false,
    enabled: true,
  });
  accessDialog.value = true;
}
function openDomain() {
  Object.assign(domainForm, {
    id: null,
    name: "",
    code: "",
    description: "",
    tables: [],
    members: [],
    enabled: true,
  });
  domainDialog.value = true;
}
const accessDialog = ref(false);
const accessForm = reactive<any>({
  id: null,
  name: "",
  attribute: "role",
  value: "",
  allowed_tables: [],
  sensitive_ok: false,
  enabled: true,
});
async function saveAccessForm() {
  if (!accessForm.name?.trim() || !accessForm.value?.trim())
    return ElMessage.warning(t("ai_workflow.ig_govPolicyRequired"));
  await saveAccessRule({ ...accessForm });
  ElMessage.success(t("ai_workflow.ig_saveSuccess"));
  accessDialog.value = false;
  loadAccess();
  loadOverview();
}
const domainDialog = ref(false);
const domainForm = reactive<any>({
  id: null,
  name: "",
  code: "",
  description: "",
  tables: [],
  members: [],
  enabled: true,
});
async function saveDomainForm() {
  if (!domainForm.name?.trim()) return ElMessage.warning(t("ai_workflow.ig_govDomainNameRequired"));
  await saveDomain({ ...domainForm });
  ElMessage.success(t("ai_workflow.ig_saveSuccess"));
  domainDialog.value = false;
  loadDomain();
  loadOverview();
}
function editAccess(row: any) {
  Object.assign(accessForm, { ...row });
  accessDialog.value = true;
}
function editDomain(row: any) {
  Object.assign(domainForm, { ...row });
  domainDialog.value = true;
}
function delAccess(row: any) {
  ElMessageBox.confirm(
    t("ai_workflow.ig_govDelPolicyConfirm", { name: row.name }),
    t("ai_workflow.ig_confirm"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  ).then(async () => {
    await removeAccessRule(row.id);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    loadAccess();
  });
}
function delDomain(row: any) {
  ElMessageBox.confirm(
    t("ai_workflow.ig_govDelDomainConfirm", { name: row.name }),
    t("ai_workflow.ig_confirm"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.ig_delete"),
      cancelButtonText: t("ai_workflow.ig_cancel"),
    }
  ).then(async () => {
    await removeDomain(row.id);
    ElMessage.success(t("ai_workflow.ig_deleted"));
    loadDomain();
  });
}

onMounted(() => {
  loadOverview();
  loadObjects();
});
</script>

<style lang="scss" scoped>
.gp-wrap {
  padding: 12px;
}
.gp-section {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin: 8px 0 4px;
}
.gp-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.gp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gp-bar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.gp-fde-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.gp-fde-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.gp-alert {
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
}
.gp-alert--warn {
  padding: 4px;
}
.gp-score {
  margin-left: 8px;
  font-size: var(--el-font-size-small);
  color: var(--el-color-warning);
}
.gp-down {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gp-params {
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-family: monospace;
  word-break: break-all;
}
</style>
