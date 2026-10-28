<!-- AI 集成开放平台：应用管理 / 调用日志 / MCP 会话 / 接入文档 -->
<template>
  <div class="app-container ai-develop-page">
    <el-card shadow="never" class="develop-shell" :body-style="{ padding: '0 16px 12px' }">
      <el-tabs v-model="activeTab" class="develop-tabs" @tab-change="onTabChange">
        <!-- ============ 应用管理 ============ -->
        <el-tab-pane :label="t('ai_workflow.develop_tabApps')" name="apps" class="develop-apps-pane">
          <div class="develop-head">
            <el-form :inline="true" :model="appSearch" class="develop-search">
              <el-form-item :label="t('ai_workflow.develop_keyword')">
                <el-input
                  v-model="appSearch.keyword"
                  :placeholder="t('ai_workflow.develop_keywordPlaceholder')"
                  clearable
                  style="width: 220px"
                  @keyup.enter="loadApps()"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Search" @click="loadApps()">
                  {{ t("ai_workflow.develop_query") }}
                </el-button>
              </el-form-item>
            </el-form>
            <el-button
              v-hasPerm="['module_ai:develop:create']"
              type="primary"
              :icon="Plus"
              @click="openCreate"
            >
              {{ t("ai_workflow.develop_newApp") }}
            </el-button>
          </div>

          <el-alert
            v-if="stats.apps.expiring?.length"
            type="warning"
            :closable="false"
            show-icon
            class="docs-alert develop-alert"
            :title="
              t('ai_workflow.develop_alertExpiringTitle', { count: stats.apps.expiring_soon })
            "
            :description="
              stats.apps.expiring
                .map((a: any) =>
                  t('ai_workflow.develop_expiringItem', { name: a.name, expire: a.expire_at })
                )
                .join('、') +
              (stats.apps.expiring_soon > stats.apps.expiring.length
                ? t('ai_workflow.develop_etc')
                : '')
            "
          />

          <!-- 应用卡片网格（替代表格） -->
          <div v-loading="appLoading" class="app-grid">
            <div v-for="row in apps" :key="row.id" class="app-card">
              <div class="app-card__head">
                <div class="app-card__title" :title="row.name">{{ row.name }}</div>
                <el-switch
                  v-hasPerm="['module_ai:develop:update']"
                  :model-value="row.enabled !== false"
                  @change="(v) => onToggle(row, Boolean(v))"
                />
              </div>
              <div class="app-card__appid">
                <span class="appid-cell__value">{{ row.appid_masked || "—" }}</span>
                <el-tooltip :content="t('ai_workflow.develop_copyAppid')" placement="top">
                  <el-button text type="primary" size="small" @click="copyText(row.appid)">
                    <el-icon><CopyDocument /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>
              <div class="app-card__meta">
                <div class="app-card__meta-item">
                  <span class="app-card__meta-label">
                    {{ t("ai_workflow.develop_expireTime") }}
                  </span>
                  <span
                    :class="{ 'text-muted': !row.expire_at, 'text-warn': isExpiringSoon(row) }"
                  >
                    {{ fmtDateTime(row.expire_at) }}
                  </span>
                </div>
                <div class="app-card__meta-item">
                  <span class="app-card__meta-label">
                    {{ t("ai_workflow.develop_callCount") }}
                  </span>
                  <span>{{ row.call_count ?? 0 }}</span>
                </div>
              </div>
              <div class="app-card__caps">
                <template v-if="row.capabilities && row.capabilities.length">
                  <el-tooltip
                    v-for="perm in row.capabilities"
                    :key="perm"
                    :content="perm"
                    placement="top"
                  >
                    <el-tag size="small" effect="plain" class="cap-tag">
                      {{ perm.replace("integration:", "") }}
                    </el-tag>
                  </el-tooltip>
                </template>
                <span v-else class="text-muted">—</span>
              </div>
              <div class="app-card__actions">
                <el-tooltip :content="t('ai_workflow.develop_embed')" placement="top">
                  <el-button
                    v-hasPerm="['module_ai:develop:query']"
                    text
                    class="app-act"
                    @click="openEmbed(row)"
                  >
                    <i class="ri-code-s-slash-line" />
                  </el-button>
                </el-tooltip>
                <el-tooltip :content="t('ai_workflow.develop_try')" placement="top">
                  <el-button
                    v-hasPerm="['module_ai:develop:query']"
                    text
                    class="app-act"
                    @click="openTry(row)"
                  >
                    <i class="ri-play-circle-line" />
                  </el-button>
                </el-tooltip>
                <el-tooltip :content="t('ai_workflow.develop_edit')" placement="top">
                  <el-button
                    v-hasPerm="['module_ai:develop:update']"
                    text
                    class="app-act"
                    @click="openEdit(row)"
                  >
                    <i class="ri-edit-line" />
                  </el-button>
                </el-tooltip>
                <el-tooltip content="AppKey" placement="top">
                  <el-button
                    v-hasPerm="['module_ai:develop:reset']"
                    text
                    class="app-act"
                    @click="openKeyDialog(row)"
                  >
                    <i class="ri-key-2-line" />
                  </el-button>
                </el-tooltip>
                <el-tooltip :content="t('ai_workflow.develop_delete')" placement="top">
                  <el-button
                    v-hasPerm="['module_ai:develop:delete']"
                    text
                    class="app-act app-act--danger"
                    @click="onDelete(row)"
                  >
                    <i class="ri-delete-bin-line" />
                  </el-button>
                </el-tooltip>
              </div>
            </div>
            <el-empty
              v-if="!apps.length && !appLoading"
              :image-size="80"
              :description="t('ai_workflow.develop_noData')"
            />
          </div>

          <div v-if="appTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="appPage"
              v-model:page-size="appPageSize"
              :total="appTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadApps(false)"
              @size-change="
                () => {
                  appPage = 1;
                  loadApps(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ 调用日志 ============ -->
        <el-tab-pane :label="t('ai_workflow.develop_tabLogs')" name="logs" class="develop-table-pane">
          <el-card shadow="never" class="trend-card">
            <template #header>
              <div class="trend-card__head">
                <span class="trend-card__title">{{ t("ai_workflow.develop_trendTitle") }}</span>
                <span class="trend-card__range">{{ t("ai_workflow.develop_recent7") }}</span>
              </div>
            </template>
            <div class="overview-stats">
              <div v-for="s in statCards" :key="s.label" class="overview-stat">
                <el-icon class="overview-stat__icon" :size="16">
                  <component :is="s.icon" />
                </el-icon>
                <span class="overview-stat__value">
                  {{ s.value }}<span class="overview-stat__suffix">{{ s.suffix }}</span>
                </span>
                <span class="overview-stat__label">{{ s.label }}</span>
              </div>
            </div>
            <TrendLineChart :points="logTrendPoints" :height="140" />
          </el-card>
          <el-form :inline="true" :model="logFilter" class="develop-search">
            <el-form-item :label="t('ai_workflow.develop_appLabel')">
              <el-select
                v-model="logFilter.app_id"
                :placeholder="t('ai_workflow.develop_all')"
                clearable
                filterable
                style="width: 180px"
              >
                <el-option v-for="a in appOptions" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('ai_workflow.develop_category')">
              <el-select
                v-model="logFilter.category"
                :placeholder="t('ai_workflow.develop_all')"
                clearable
                style="width: 140px"
              >
                <el-option
                  v-for="(label, code) in CATEGORIES"
                  :key="code"
                  :label="label"
                  :value="code"
                />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('ai_workflow.develop_method')">
              <el-select
                v-model="logFilter.method"
                :placeholder="t('ai_workflow.develop_all')"
                clearable
                style="width: 140px"
              >
                <el-option label="REST" value="REST" />
                <el-option label="MCP" value="MCP" />
                <el-option label="EMBED" value="EMBED" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('ai_workflow.develop_status')">
              <el-select
                v-model="logFilter.status"
                :placeholder="t('ai_workflow.develop_all')"
                clearable
                style="width: 140px"
              >
                <el-option :label="t('ai_workflow.develop_success')" value="success" />
                <el-option :label="t('ai_workflow.develop_failed')" value="failed" />
                <el-option :label="t('ai_workflow.develop_denied')" value="denied" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('ai_workflow.develop_timeRange')">
              <el-date-picker
                v-model="logFilter.range"
                type="datetimerange"
                :range-separator="t('ai_workflow.develop_to')"
                :start-placeholder="t('ai_workflow.develop_startTime')"
                :end-placeholder="t('ai_workflow.develop_endTime')"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 340px"
              />
              <el-button-group style="margin-left: 8px">
                <el-button
                  v-for="q in RANGE_PRESETS"
                  :key="q.days"
                  size="small"
                  @click="setQuickRange(q.days)"
                >
                  {{ q.label }}
                </el-button>
              </el-button-group>
            </el-form-item>
            <el-form-item :label="t('ai_workflow.develop_capability')">
              <el-select
                v-model="logFilter.capability"
                :placeholder="t('ai_workflow.develop_all')"
                clearable
                filterable
                style="width: 170px"
                @change="loadLogs()"
              >
                <el-option
                  v-for="cap in capabilities"
                  :key="cap.code"
                  :label="cap.code"
                  :value="cap.code"
                />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="loadLogs()">
                {{ t("ai_workflow.develop_query") }}
              </el-button>
              <el-button :icon="Download" @click="onExportLogs">
                {{ t("ai_workflow.develop_exportCsv") }}
              </el-button>
            </el-form-item>
          </el-form>

          <div class="table-flow">
            <el-table
              v-loading="logLoading"
              :data="logs"
              row-key="id"
              border
              stripe
              height="100%"
              class="log-table"
              @row-click="openLogDetail"
            >
            <el-table-column
              :label="t('ai_workflow.develop_time')"
              width="165"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ fmtDateTime(row.created_time) }}</template>
            </el-table-column>
            <el-table-column label="AppID" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.appid || "—" }}</template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.develop_category')" width="85">
              <template #default="{ row }">
                {{ CATEGORIES[row.category || ""] || row.category }}
              </template>
            </el-table-column>
            <el-table-column
              prop="capability"
              :label="t('ai_workflow.develop_capability')"
              min-width="145"
              show-overflow-tooltip
            />
            <el-table-column :label="t('ai_workflow.develop_method')" width="90">
              <template #default="{ row }">{{ methodLabel(row.method) }}</template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.develop_status')" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="logStatusType(row.status)">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="latency_ms"
              :label="t('ai_workflow.develop_latency')"
              width="85"
              align="right"
            />
            <el-table-column prop="cost_tokens" label="Tokens" width="78" align="right" />
            <el-table-column
              prop="request_path"
              :label="t('ai_workflow.develop_requestPath')"
              min-width="145"
              show-overflow-tooltip
            />
            <el-table-column
              prop="result_summary"
              :label="t('ai_workflow.develop_resultSummary')"
              min-width="145"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_workflow.develop_noLogs')" />
            </template>
          </el-table>
          </div>

          <div v-if="logTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="logPage"
              v-model:page-size="logPageSize"
              :total="logTotal"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadLogs(false)"
              @size-change="
                () => {
                  logPage = 1;
                  loadLogs(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ MCP 会话 ============ -->
        <el-tab-pane :label="t('ai_workflow.develop_tabMcp')" name="mcp" class="develop-table-pane">
          <el-card shadow="never" class="trend-card">
            <template #header>
              <div class="trend-card__head">
                <span class="trend-card__title">{{ t("ai_workflow.develop_trendTitle") }}</span>
                <span class="trend-card__range">
                  {{ t("ai_workflow.develop_recentDays", { days: mcpStats.days }) }}
                </span>
              </div>
            </template>
            <div class="overview-stats">
              <div v-for="s in mcpStatCards" :key="s.label" class="overview-stat">
                <el-icon class="overview-stat__icon" :size="16">
                  <component :is="s.icon" />
                </el-icon>
                <span class="overview-stat__value">
                  {{ s.value }}<span class="overview-stat__suffix">{{ s.suffix }}</span>
                </span>
                <span class="overview-stat__label">{{ s.label }}</span>
              </div>
            </div>
            <TrendLineChart :points="mcpTrendPoints" :height="140" />
          </el-card>
          <el-form :inline="true" :model="mcpFilter" class="develop-search">
            <el-form-item :label="t('ai_workflow.develop_appLabel')">
              <el-select
                v-model="mcpFilter.app_id"
                :placeholder="t('ai_workflow.develop_all')"
                clearable
                filterable
                style="width: 180px"
              >
                <el-option v-for="a in appOptions" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="loadMcps()">
                {{ t("ai_workflow.develop_query") }}
              </el-button>
            </el-form-item>
          </el-form>

          <div class="table-flow">
          <el-table v-loading="mcpLoading" :data="mcps" row-key="id" border stripe height="100%">
            <el-table-column label="AppID" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.appid || "—" }}</template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.develop_sessionId')"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span class="mono-text">{{ row.session_id || "—" }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.develop_transport')" width="100">
              <template #default="{ row }">{{ transportLabel(row.transport) }}</template>
            </el-table-column>
            <el-table-column
              prop="client_info"
              :label="t('ai_workflow.develop_client')"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column :label="t('ai_workflow.develop_startTime')" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.develop_endTime')" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.ended_at, "—") }}</template>
            </el-table-column>
            <el-table-column
              prop="duration_s"
              :label="t('ai_workflow.develop_duration')"
              width="80"
              align="right"
            />
            <el-table-column
              prop="tool_calls"
              :label="t('ai_workflow.develop_toolCalls')"
              width="85"
              align="right"
            />
            <el-table-column
              prop="close_reason"
              :label="t('ai_workflow.develop_closeReason')"
              min-width="120"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_workflow.develop_noMcp')" />
            </template>
          </el-table>
          </div>

          <div v-if="mcpTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="mcpPage"
              v-model:page-size="mcpPageSize"
              :total="mcpTotal"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadMcps(false)"
              @size-change="
                () => {
                  mcpPage = 1;
                  loadMcps(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ 用量报告 ============ -->
        <el-tab-pane :label="t('ai_workflow.develop_tabUsage')" name="usage" class="develop-table-pane">
          <el-form :inline="true" class="develop-search">
            <el-form-item :label="t('ai_workflow.develop_usageRange')">
              <el-button-group>
                <el-button
                  v-for="d in [7, 30, 90]"
                  :key="d"
                  :type="usageDays === d ? 'primary' : 'default'"
                  size="small"
                  @click="loadUsage(d)"
                >
                  {{ t("ai_workflow.develop_recentDaysValue", { days: d }) }}
                </el-button>
              </el-button-group>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="loadUsage()">
                {{ t("ai_workflow.develop_query") }}
              </el-button>
              <el-button :icon="Download" @click="onExportUsage">
                {{ t("ai_workflow.develop_exportCsv") }}
              </el-button>
            </el-form-item>
          </el-form>

          <div class="table-flow">
          <el-table v-loading="usageLoading" :data="usageItems" row-key="app_id" border stripe height="100%">
            <el-table-column
              prop="name"
              :label="t('ai_workflow.develop_appLabel')"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column prop="appid" label="AppID" width="130" show-overflow-tooltip />
            <el-table-column
              prop="calls"
              :label="t('ai_workflow.develop_calls')"
              width="80"
              align="right"
            />
            <el-table-column
              prop="success"
              :label="t('ai_workflow.develop_success')"
              width="80"
              align="right"
            />
            <el-table-column :label="t('ai_workflow.develop_successRate')" width="90" align="right">
              <template #default="{ row }">{{ (row.success_rate * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column
              prop="quota_hits"
              :label="t('ai_workflow.develop_quotaHits')"
              width="100"
              align="right"
            />
            <el-table-column
              prop="rate_limited"
              :label="t('ai_workflow.develop_rateLimited')"
              width="90"
              align="right"
            />
            <el-table-column :label="t('ai_workflow.develop_topCapabilitiesShort')" min-width="240">
              <template #default="{ row }">
                <el-tag
                  v-for="t in row.top"
                  :key="t.capability"
                  size="small"
                  effect="plain"
                  class="cap-tag"
                >
                  {{ t.capability }} · {{ t.calls }}
                </el-tag>
                <span v-if="!row.top.length" class="text-muted">—</span>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_workflow.develop_noUsage')" />
            </template>
          </el-table>
          </div>
        </el-tab-pane>

        <!-- ============ 调用审批 ============ -->
        <el-tab-pane :label="t('ai_workflow.develop_tabApprovals')" name="approvals" class="develop-table-pane">
          <div class="develop-head">
            <el-form :inline="true" :model="approvalFilter" class="develop-search">
              <el-form-item :label="t('ai_workflow.develop_status')">
                <el-select
                  v-model="approvalFilter.status"
                  :placeholder="t('ai_workflow.develop_all')"
                  clearable
                  style="width: 140px"
                  @change="loadApprovals(true)"
                >
                  <el-option
                    v-for="(label, code) in APPROVAL_STATUS"
                    :key="code"
                    :label="label"
                    :value="code"
                  />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :icon="Search" @click="loadApprovals(true)">
                  {{ t("ai_workflow.develop_query") }}
                </el-button>
              </el-form-item>
            </el-form>
            <div class="develop-head__actions">
              <el-tag size="small" type="warning" effect="plain" class="summary-tag">
                {{ t("ai_workflow.develop_approvalPending", { count: approvalPendingCount }) }}
              </el-tag>
              <el-button
                v-hasPerm="['module_ai:develop:approve']"
                type="primary"
                :disabled="!approvalSelection.length"
                @click="onBatchApprove"
              >
                {{ t("ai_workflow.develop_batchApprove", { count: approvalSelection.length }) }}
              </el-button>
              <el-button
                v-hasPerm="['module_ai:develop:update']"
                :icon="Setting"
                @click="openNotifyCfg"
              >
                {{ t("ai_workflow.develop_notifyCfg") }}
              </el-button>
            </div>
          </div>

          <div class="table-flow">
          <el-table
            ref="approvalTableRef"
            v-loading="approvalLoading"
            :data="approvals"
            row-key="id"
            border
            stripe
            height="100%"
            @selection-change="(rows: any[]) => (approvalSelection = rows)"
          >
            <el-table-column
              type="selection"
              width="46"
              :selectable="(row: any) => row.status === 'pending'"
            />
            <el-table-column :label="t('ai_workflow.develop_applyTime')" width="155">
              <template #default="{ row }">{{ fmtDateTime(row.created_time) }}</template>
            </el-table-column>
            <el-table-column prop="appid" label="AppID" width="130" show-overflow-tooltip />
            <el-table-column
              prop="capability"
              :label="t('ai_workflow.develop_capability')"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column :label="t('ai_workflow.develop_category')" width="95">
              <template #default="{ row }">
                {{ CATEGORIES[row.category] || row.category }}
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.develop_status')" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="approvalStatusType(row.status)">
                  {{ APPROVAL_STATUS[row.status] || row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.develop_reviewTime')" width="155">
              <template #default="{ row }">{{ fmtDateTime(row.reviewed_at, "—") }}</template>
            </el-table-column>
            <el-table-column
              prop="review_note"
              :label="t('ai_workflow.develop_reviewNote')"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              :label="t('ai_workflow.develop_action')"
              width="150"
              :fixed="fixedAction"
            >
              <template #default="{ row }">
                <el-tooltip :content="t('ai_workflow.develop_detail')" placement="top">
                  <el-button text type="primary" class="app-act" @click="openApprovalDetail(row)">
                    <i class="ri-file-list-line" />
                  </el-button>
                </el-tooltip>
                <template v-if="row.status === 'pending'">
                  <el-tooltip :content="t('ai_workflow.develop_approve')" placement="top">
                    <el-button
                      v-hasPerm="'module_ai:develop:approve'"
                      text
                      type="primary"
                      class="app-act"
                      @click="onReviewApproval(row, true)"
                    >
                      <i class="ri-check-line" />
                    </el-button>
                  </el-tooltip>
                  <el-tooltip :content="t('ai_workflow.develop_reject')" placement="top">
                    <el-button
                      v-hasPerm="'module_ai:develop:approve'"
                      text
                      type="danger"
                      class="app-act"
                      @click="onReviewApproval(row, false)"
                    >
                      <i class="ri-close-line" />
                    </el-button>
                  </el-tooltip>
                </template>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" :description="t('ai_workflow.develop_noApprovals')" />
            </template>
          </el-table>
          </div>

          <div v-if="approvalTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="approvalPage"
              v-model:page-size="approvalPageSize"
              :total="approvalTotal"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadApprovals(false)"
              @size-change="
                () => {
                  approvalPage = 1;
                  loadApprovals(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ 接入文档 ============ -->
        <el-tab-pane :label="t('ai_workflow.develop_tabDocs')" name="docs">
          <div class="docs-wrap">
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>{{ t("ai_workflow.develop_restCard") }}</span>
                  <el-tag size="small">HTTP</el-tag>
                </div>
              </template>
              <pre class="doc-code">{{ REST_EXAMPLE }}</pre>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>{{ t("ai_workflow.develop_mcpCard") }}</span>
                  <el-tag size="small" type="success">Streamable HTTP</el-tag>
                </div>
              </template>
              <pre class="doc-code">{{ MCP_EXAMPLE }}</pre>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>{{ t("ai_workflow.develop_capListCard") }}</span>
                  <el-tag size="small" type="info">
                    {{ t("ai_workflow.develop_capCount", { count: capabilities.length }) }}
                  </el-tag>
                </div>
              </template>
              <el-table v-loading="capLoading" :data="capabilities" border stripe>
                <el-table-column
                  prop="name"
                  :label="t('ai_workflow.develop_capabilityName')"
                  min-width="130"
                  show-overflow-tooltip
                />
                <el-table-column
                  prop="code"
                  :label="t('ai_workflow.develop_capabilityCode')"
                  width="130"
                />
                <el-table-column :label="t('ai_workflow.develop_category')" width="100">
                  <template #default="{ row }">
                    {{ CATEGORIES[row.category] || row.category }}
                  </template>
                </el-table-column>
                <el-table-column
                  prop="perm"
                  :label="t('ai_workflow.develop_requiredPerm')"
                  width="200"
                />
                <el-table-column
                  prop="mcp_tool"
                  :label="t('ai_workflow.develop_mcpToolName')"
                  width="140"
                >
                  <template #default="{ row }">
                    <span v-if="row.mcp_tool" class="mono-text">{{ row.mcp_tool }}</span>
                    <span v-else class="text-muted">—</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="description"
                  :label="t('ai_workflow.develop_desc')"
                  min-width="240"
                  show-overflow-tooltip
                />
                <template #empty>
                  <el-empty
                    :image-size="80"
                    :description="t('ai_workflow.develop_noCapabilities')"
                  />
                </template>
              </el-table>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>{{ t("ai_workflow.develop_embedCard") }}</span>
                  <el-tag size="small">Embed</el-tag>
                </div>
              </template>
              <pre class="doc-code">{{ EMBED_EXAMPLE }}</pre>
              <div class="doc-events">
                <span class="doc-events__label">
                  {{ t("ai_workflow.develop_postMessageEvents") }}
                </span>
                <el-tag
                  v-for="e in docEvents"
                  :key="e.name"
                  size="small"
                  effect="plain"
                  class="doc-events__tag"
                  :title="e.desc"
                >
                  {{ e.name }}
                </el-tag>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ============ 调用日志详情抽屉 ============ -->
    <el-drawer
      v-model="logDetail.visible"
      :title="t('ai_workflow.develop_logDetailTitle')"
      size="520px"
      append-to-body
    >
      <el-descriptions v-if="logDetail.row" :column="1" border size="small">
        <el-descriptions-item :label="t('ai_workflow.develop_time')">
          {{ fmtDateTime(logDetail.row.created_time) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_appLabel')">
          {{ logDetail.row.appid }}（ID {{ logDetail.row.app_id }}）
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_capability')">
          {{ logDetail.row.capability }}
          <el-tag size="small" effect="plain" class="cap-tag">
            {{ CATEGORIES[logDetail.row.category || ""] || logDetail.row.category }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_methodStatus')">
          {{ methodLabel(logDetail.row.method) }} ·
          <el-tag size="small" :type="logStatusType(logDetail.row.status)">
            {{ statusLabel(logDetail.row.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_latencyTokens')">
          {{ logDetail.row.latency_ms }} ms · {{ logDetail.row.cost_tokens }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_requestPath')">
          {{ logDetail.row.request_path || "—" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="logDetail.row.error" :label="t('ai_workflow.develop_error')">
          <span class="text-danger">{{ logDetail.row.error }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <template v-if="logDetail.row">
        <p class="doc-card__desc">{{ t("ai_workflow.develop_requestBody") }}</p>
        <pre class="doc-code">{{ prettyJson(logDetail.row.request_body) }}</pre>
        <p class="doc-card__desc">{{ t("ai_workflow.develop_resultSummary") }}</p>
        <pre class="doc-code">{{ logDetail.row.result_summary || "—" }}</pre>
      </template>
    </el-drawer>

    <!-- ============ 能力试调弹窗 ============ -->
    <el-dialog
      v-model="tryDialog.visible"
      :title="t('ai_workflow.develop_tryTitle')"
      width="640px"
      append-to-body
    >
      <el-form label-width="90px" class="try-form">
        <el-form-item :label="t('ai_workflow.develop_capability')">
          <el-select
            v-model="tryDialog.capability"
            :placeholder="t('ai_workflow.develop_selectCapability')"
            filterable
            style="width: 100%"
            @change="onTryCapabilityChange"
          >
            <el-option
              v-for="cap in capabilities"
              :key="cap.code"
              :label="`${cap.name}（${cap.code}）`"
              :value="cap.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_payloadJson')">
          <el-input
            v-model="tryDialog.payloadText"
            type="textarea"
            :rows="8"
            spellcheck="false"
            :placeholder="t('ai_workflow.develop_payloadPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template v-if="tryDialog.resultObj">
        <p class="doc-card__desc">{{ t("ai_workflow.develop_result") }}</p>
        <el-descriptions :column="2" border size="small" class="try-result">
          <el-descriptions-item
            v-for="field in tryDialog.resultFields"
            :key="field.label"
            :label="field.label"
          >
            {{ field.value }}
          </el-descriptions-item>
        </el-descriptions>
        <p class="doc-card__desc">{{ t("ai_workflow.develop_rawResponse") }}</p>
        <pre class="doc-code">{{ tryDialog.resultText }}</pre>
      </template>
      <template v-else-if="tryDialog.resultText">
        <p class="doc-card__desc">{{ t("ai_workflow.develop_response") }}</p>
        <pre class="doc-code">{{ tryDialog.resultText }}</pre>
      </template>
      <template #footer>
        <el-button @click="tryDialog.visible = false">
          {{ t("ai_workflow.develop_close") }}
        </el-button>
        <el-button type="primary" :loading="tryDialog.loading" @click="submitTry">
          {{ t("ai_workflow.develop_send") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 审批通知配置弹窗 ============ -->
    <el-dialog
      v-model="notifyCfg.visible"
      :title="t('ai_workflow.develop_notifyCfgTitle')"
      width="580px"
      append-to-body
    >
      <el-form label-width="90px">
        <el-form-item :label="t('ai_workflow.develop_enableChannels')">
          <el-checkbox-group v-model="notifyCfg.channels">
            <el-checkbox v-for="ch in NOTIFY_CHANNELS" :key="ch" :value="ch">
              {{ notifyCfg.labels[ch] || ch }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <template v-for="ch in notifyCfg.channels" :key="'cfg-' + ch">
          <el-form-item
            :label="t('ai_workflow.develop_channelConfig', { name: notifyCfg.labels[ch] || ch })"
          >
            <el-input
              v-model="notifyCfg.configs[ch]"
              type="textarea"
              :rows="4"
              :placeholder="NOTIFY_CONFIG_PLACEHOLDERS[ch]"
              spellcheck="false"
            />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="notifyCfg.visible = false">
          {{ t("ai_workflow.develop_close") }}
        </el-button>
        <el-button type="primary" :loading="notifyCfg.loading" @click="saveNotifyCfg">
          {{ t("ai_workflow.develop_save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 审批详情弹窗 ============ -->
    <el-dialog
      v-model="approvalDetail.visible"
      :title="t('ai_workflow.develop_approvalDetailTitle')"
      width="600px"
      append-to-body
    >
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item :label="t('ai_workflow.develop_capability')">
          {{ approvalDetail.row?.capability }}
          <el-tag size="small" effect="plain" class="cap-tag">
            {{ CATEGORIES[approvalDetail.row?.category || ""] || approvalDetail.row?.category }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_appLabel')">
          {{ approvalDetail.row?.appid }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_status')">
          <el-tag size="small" :type="approvalStatusType(approvalDetail.row?.status)">
            {{ APPROVAL_STATUS[approvalDetail.row?.status || ""] || approvalDetail.row?.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_applyTime')">
          {{ fmtDateTime(approvalDetail.row?.created_time) }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="approvalDetail.row?.reviewed_at"
          :label="t('ai_workflow.develop_reviewTime')"
        >
          {{ fmtDateTime(approvalDetail.row?.reviewed_at) }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="approvalDetail.row?.review_note"
          :label="t('ai_workflow.develop_reviewNote')"
        >
          {{ approvalDetail.row?.review_note }}
        </el-descriptions-item>
      </el-descriptions>
      <p class="doc-card__desc">{{ t("ai_workflow.develop_requestBodyShort") }}</p>
      <pre class="doc-code">{{ prettyJson(approvalDetail.row?.payload) }}</pre>
      <template v-if="approvalDetail.row?.result">
        <p class="doc-card__desc">{{ t("ai_workflow.develop_execResult") }}</p>
        <pre class="doc-code">{{ prettyJson(approvalDetail.row?.result) }}</pre>
      </template>
      <el-alert
        v-if="approvalDetail.row?.error"
        type="error"
        :closable="false"
        show-icon
        :title="t('ai_workflow.develop_execFailTitle', { error: approvalDetail.row?.error })"
      />
      <template #footer>
        <el-button @click="approvalDetail.visible = false">
          {{ t("ai_workflow.develop_close") }}
        </el-button>
        <template v-if="approvalDetail.row?.status === 'pending'">
          <el-button
            v-hasPerm="'module_ai:develop:approve'"
            type="danger"
            plain
            @click="onReviewApproval(approvalDetail.row, false)"
          >
            {{ t("ai_workflow.develop_reject") }}
          </el-button>
          <el-button
            v-hasPerm="'module_ai:develop:approve'"
            type="primary"
            @click="onReviewApproval(approvalDetail.row, true)"
          >
            {{ t("ai_workflow.develop_approveExecute") }}
          </el-button>
        </template>
      </template>
    </el-dialog>

    <!-- ============ 新增 / 编辑应用弹窗 ============ -->
    <EnhancedDialog
      v-model="dialog.visible"
      :title="dialog.title"
      append-to-body
      width="640px"
      dialog-class="develop-app-dialog"
      @close="dialog.visible = false"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item :label="t('ai_workflow.develop_name')" required>
          <el-input v-model="form.name" :placeholder="t('ai_workflow.develop_namePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_desc')">
          <el-input
            v-model="form.description"
            :placeholder="t('ai_workflow.develop_descPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_authCaps')">
          <div class="cap-groups">
            <div v-for="(catLabel, catCode) in CATEGORIES" :key="catCode" class="cap-group">
              <div class="cap-group__title">
                {{ catLabel }}
                <span class="cap-group__count">
                  {{ selectedCount(CATEGORY_PERMS[catCode]) }}/{{ CATEGORY_PERMS[catCode].length }}
                </span>
              </div>
              <el-checkbox-group v-model="form.capabilities">
                <el-checkbox
                  v-for="perm in CATEGORY_PERMS[catCode]"
                  :key="perm"
                  :value="perm"
                  class="cap-check"
                >
                  {{ perm.replace("integration:", "") }}
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </div>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_expireTime')">
          <el-date-picker
            v-model="form.expire_at"
            type="datetime"
            :placeholder="t('ai_workflow.develop_expirePlaceholder')"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_requiresApproval')">
          <el-switch v-model="form.requires_approval" />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_dailyQuota')">
          <div class="quota-grid">
            <div v-for="(label, cat) in QUOTA_CATEGORIES" :key="cat" class="quota-item">
              <span class="quota-item__label">{{ label }}</span>
              <el-input-number
                v-model="form.quota[cat]"
                :min="0"
                :max="1000000"
                :step="100"
                controls-position="right"
                :placeholder="t('ai_workflow.develop_unlimited')"
                style="width: 110px"
              />
              <span class="quota-item__usage">
                {{ t("ai_workflow.develop_todayUsage", { usage: form.usage[cat] ?? 0 }) }}
              </span>
            </div>
          </div>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.develop_enabled')">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">{{ t("ai_workflow.develop_cancel") }}</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
          {{ t("ai_workflow.develop_save") }}
        </el-button>
      </template>
    </EnhancedDialog>

    <!-- ============ AppKey 查看 / 重置弹窗 ============ -->
    <el-dialog
      v-model="keyDialog.visible"
      :title="t('ai_workflow.develop_keyTitle', { name: keyDialog.name })"
      width="520px"
      append-to-body
      @close="closeKeyDialog"
    >
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="AppID">
          <div class="appid-cell">
            <span class="mono-text">{{ keyDialog.appid || "—" }}</span>
            <el-button text type="primary" size="small" @click="copyText(keyDialog.appid)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="AppKey">
          <template v-if="keyDialog.appkey">
            <div class="appid-cell">
              <span class="mono-text key-text">{{ keyDialog.appkey }}</span>
              <el-button text type="primary" size="small" @click="copyText(keyDialog.appkey)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
          </template>
          <span v-else class="text-muted">
            {{ t("ai_workflow.develop_keyEncrypted") }}
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="keyDialog.visible = false">
          {{ t("ai_workflow.develop_close") }}
        </el-button>
        <el-button
          v-hasPerm="['module_ai:develop:reset']"
          type="primary"
          :loading="keyLoading"
          @click="onResetKey(keyDialog.row)"
        >
          {{ t("ai_workflow.develop_resetKey") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 创建成功：一次性展示 AppKey ============ -->
    <el-dialog
      v-model="reveal.visible"
      :title="t('ai_workflow.develop_createSuccessTitle')"
      width="520px"
      append-to-body
      :close-on-click-modal="false"
      @close="closeReveal"
    >
      <el-alert
        :title="t('ai_workflow.develop_saveKeyAlert')"
        type="warning"
        :closable="false"
        show-icon
        class="docs-alert"
      />
      <el-descriptions :column="1" border size="small" class="reveal-desc">
        <el-descriptions-item label="AppID">
          <div class="appid-cell">
            <span class="mono-text">{{ reveal.appid || "—" }}</span>
            <el-button text type="primary" size="small" @click="copyText(reveal.appid)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="AppKey">
          <div class="appid-cell">
            <span class="mono-text key-text">{{ reveal.appkey || "—" }}</span>
            <el-button text type="primary" size="small" @click="copyText(reveal.appkey)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="reveal.visible = false">
          {{ t("ai_workflow.develop_iSaved") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 嵌入管理弹窗 ============ -->
    <EmbedDialog v-model="embedVisible" :app="embedRow" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { Download, Plus, Search, CopyDocument, Setting } from "@element-plus/icons-vue";
import { useWindowSize } from "@vueuse/core";
import {
  batchReviewApprovals,
  createApp,
  deleteApp,
  exportCallLogs,
  exportUsageReport,
  getAppUsage,
  getApprovals,
  getCallLogs,
  getCapabilities,
  getDevelopAppList,
  getDevelopStats,
  getMcpSessions,
  getMcpStats,
  getNotifyConfig,
  getUsageReport,
  resetAppkey,
  reviewApproval,
  saveNotifyConfig,
  toggleApp,
  tryCapability,
  updateApp,
} from "@/api/module_ai/develop";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import EmbedDialog from "./components/EmbedDialog.vue";
import { EMBED_EXAMPLE, MCP_EXAMPLE, REST_EXAMPLE } from "./examples";
import TrendLineChart from "./TrendLineChart.vue";

defineOptions({ name: "AiDevelopManage" });

const { t } = useI18n();

//: 窄屏（<1280）不把操作列固定在右侧——否则会盖住相邻列的内容（1024 下状态标签被切）。
const { width: viewportWidth } = useWindowSize();
const fixedAction = computed<"right" | undefined>(() =>
  viewportWidth.value >= 1280 ? "right" : undefined
);

// ---- 能力品类目录（与后端 capabilities.py 保持一致） ----
const CATEGORIES: Record<string, string> = {
  train: t("ai_workflow.develop_catTrain"),
  agent: t("ai_workflow.develop_catAgent"),
  chat: t("ai_workflow.develop_catChat"),
  bot: t("ai_workflow.develop_catBot"),
  embed: t("ai_workflow.develop_catEmbed"),
};
const CATEGORY_PERMS: Record<string, string[]> = {
  train: [
    "integration:train:create",
    "integration:train:query",
    "integration:train:start",
    "integration:train:stop",
  ],
  agent: [
    "integration:agent:create",
    "integration:agent:query",
    "integration:agent:update",
    "integration:agent:delete",
  ],
  chat: ["integration:chat:send", "integration:chat:query"],
  bot: ["integration:bot:use"],
  embed: ["integration:embed:use"],
};

interface AppRow {
  id: number;
  appid: string;
  appid_masked?: string;
  name: string;
  description?: string;
  enabled: boolean;
  expire_at?: string | null;
  capabilities?: string[];
  call_count?: number;
}
interface LogRow {
  id: number;
  created_time?: string;
  appid?: string;
  category?: string;
  capability?: string;
  method?: string;
  status?: string;
  latency_ms?: number;
  cost_tokens?: number;
  request_path?: string;
  result_summary?: string;
}
interface McpRow {
  id: number;
  created_time?: string;
  appid?: string;
  session_id?: string;
  transport?: string;
  client_info?: string;
  started_at?: string;
  ended_at?: string;
  duration_s?: number;
  tool_calls?: number;
  close_reason?: string;
}

const activeTab = ref("apps");
const route = useRoute();

// ============ 应用管理 ============
const appLoading = ref(false);
const apps = ref<AppRow[]>([]);
const appTotal = ref(0);
const appPage = ref(1);
const appPageSize = ref(10);
const appSearch = reactive({ keyword: "" });

// 用于日志/MCP 过滤的应用下拉选项
const appOptions = ref<{ id: number; name: string }[]>([]);

async function loadAppOptions() {
  try {
    const res = await getDevelopAppList({ page_no: 1, page_size: 100 });
    const items = res.data?.data?.items || [];
    appOptions.value = items.map((i: any) => ({ id: i.id, name: i.name }));
  } catch {
    // 下拉仅作过滤辅助，加载失败不阻断主列表
  }
}

async function loadApps(resetPage = true) {
  if (resetPage) appPage.value = 1;
  appLoading.value = true;
  try {
    const res = await getDevelopAppList({
      keyword: appSearch.keyword || undefined,
      page_no: appPage.value,
      page_size: appPageSize.value,
    });
    const d = res.data?.data || {};
    apps.value = d.items || [];
    appTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_loadFail"));
  } finally {
    appLoading.value = false;
  }
}

// ---- 新增 / 编辑弹窗 ----
const dialog = reactive({ visible: false, title: "" });
const isEdit = ref(false);
const submitLoading = ref(false);
const form = reactive({
  id: undefined as number | undefined,
  name: "",
  description: "",
  capabilities: [] as string[],
  expire_at: "" as string,
  enabled: true,
  requires_approval: true,
  quota: {} as Record<string, number | undefined>,
  usage: {} as Record<string, number>,
});

//: 可配置「按日调用配额」的品类（与开放面限流/配额口径一致）。
const QUOTA_CATEGORIES: Record<string, string> = {
  agent: t("ai_workflow.develop_catAgent"),
  chat: t("ai_workflow.develop_catChat"),
  train: t("ai_workflow.develop_catTrain"),
  bot: t("ai_workflow.develop_catBot"),
  embed: t("ai_workflow.develop_catEmbed"),
};

function resetForm() {
  Object.assign(form, {
    id: undefined,
    name: "",
    description: "",
    capabilities: [],
    expire_at: "",
    enabled: true,
    requires_approval: true,
    quota: {},
    usage: {},
  });
}

function selectedCount(perms: string[]) {
  return form.capabilities.filter((p) => perms.includes(p)).length;
}

function openCreate() {
  resetForm();
  isEdit.value = false;
  dialog.title = t("ai_workflow.develop_newApp");
  dialog.visible = true;
}

function openEdit(row: any) {
  resetForm();
  isEdit.value = true;
  dialog.title = t("ai_workflow.develop_editAppTitle", { name: row.name });
  Object.assign(form, {
    id: row.id,
    name: row.name,
    description: row.description || "",
    capabilities: row.capabilities || [],
    expire_at: row.expire_at ? fmtDateTime(row.expire_at) : "",
    enabled: row.enabled !== false,
    requires_approval: row.requires_approval !== false,
    quota: { ...(row.quota || {}) },
    usage: {},
  });
  dialog.visible = true;
  // 今日用量（配额可视化，失败静默）
  getAppUsage(row.id)
    .then((res: any) => {
      form.usage = res.data?.data?.usage || {};
    })
    .catch(() => {});
}

async function handleSubmit() {
  if (!form.name.trim()) {
    ElMessage.warning(t("ai_workflow.develop_nameRequired"));
    return;
  }
  // 配额只提交 >0 的品类；全空 = 不限（后端按自然日统计）
  const quota: Record<string, number> = {};
  Object.entries(form.quota || {}).forEach(([cat, value]) => {
    if (typeof value === "number" && value > 0) quota[cat] = value;
  });
  const payload: any = {
    name: form.name.trim(),
    description: form.description?.trim() || null,
    capabilities: form.capabilities,
    expire_at: form.expire_at || null,
    enabled: form.enabled,
    requires_approval: form.requires_approval,
    quota: Object.keys(quota).length ? quota : null,
  };
  submitLoading.value = true;
  try {
    if (form.id) {
      await updateApp(form.id, payload);
      dialog.visible = false;
      ElMessage.success(t("ai_workflow.develop_saveSuccess"));
      await loadApps(false);
      await loadStats();
    } else {
      const res = await createApp(payload);
      dialog.visible = false;
      // 创建成功：一次性展示明文 AppKey
      const d = res.data?.data || {};
      Object.assign(reveal, { visible: true, appid: d.appid || "", appkey: d.appkey || "" });
      await loadApps(false);
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_saveFail"));
  } finally {
    submitLoading.value = false;
  }
}

// ---- 启用 / 停用：局部刷新，只更新对应行 ----
async function onToggle(row: any, enabled: boolean) {
  try {
    await toggleApp(row.id, enabled);
    row.enabled = enabled;
    ElMessage.success(
      enabled ? t("ai_workflow.develop_enabledMsg") : t("ai_workflow.develop_disabledMsg")
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_opFail"));
  }
}

// ---- 删除：二次确认 ----
async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.develop_deleteConfirm", { name: row.name }),
      t("ai_workflow.develop_deleteConfirmTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.develop_delete"),
        cancelButtonText: t("ai_workflow.develop_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    await deleteApp([row.id]);
    await loadApps(false);
    ElMessage.success(t("ai_workflow.develop_deleteSuccess"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_deleteFail"));
  }
}

// ---- AppKey 查看 / 重置 ----
const keyDialog = reactive({
  visible: false,
  row: null as AppRow | null,
  name: "",
  appid: "",
  appkey: "",
});
const keyLoading = ref(false);

function openKeyDialog(row: any) {
  keyDialog.row = row;
  keyDialog.name = row.name;
  keyDialog.appid = row.appid;
  keyDialog.appkey = "";
  keyDialog.visible = true;
}
function closeKeyDialog() {
  // 不持久化明文 AppKey
  keyDialog.appkey = "";
  keyDialog.row = null;
}
async function onResetKey(row: any) {
  if (!row) return;
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.develop_resetKeyConfirm", { name: row.name }),
      t("ai_workflow.develop_resetKeyTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.develop_reset"),
        cancelButtonText: t("ai_workflow.develop_cancel"),
      }
    );
  } catch {
    return;
  }
  keyLoading.value = true;
  try {
    const res = await resetAppkey(row.id);
    const d = res.data?.data || {};
    keyDialog.appid = d.appid || row.appid;
    keyDialog.appkey = d.appkey || "";
    ElMessage.success(t("ai_workflow.develop_keyResetSuccess"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_keyResetFail"));
  } finally {
    keyLoading.value = false;
  }
}

// ---- 创建成功 reveal 弹窗 ----
const reveal = reactive({ visible: false, appid: "", appkey: "" });
function closeReveal() {
  // 一次性展示，关闭后清空，不持久化
  reveal.appid = "";
  reveal.appkey = "";
}

// ============ 调用日志 ============
const logLoading = ref(false);
const logs = ref<LogRow[]>([]);
const logTotal = ref(0);
const logPage = ref(1);
const logPageSize = ref(10);
const logFilter = reactive({
  capability: "",
  app_id: undefined as number | undefined,
  category: "",
  method: "",
  status: "",
  range: [] as string[],
});

// ---- 调用概览（统计卡 + 7 天迷你趋势 + Top 能力） ----
const stats = reactive<{
  today: any;
  series: any[];
  top_capabilities: any[];
  apps: any;
  approvals: any;
}>({ today: {}, series: [], top_capabilities: [], apps: {}, approvals: {} });

const statCards = computed(() => [
  {
    icon: "Phone",
    label: t("ai_workflow.develop_statTodayCalls"),
    value: stats.today.calls ?? 0,
    suffix: t("ai_workflow.develop_suffixCount"),
  },
  {
    icon: "CircleCheck",
    label: t("ai_workflow.develop_statSuccessRate"),
    value: ((stats.today.success_rate ?? 0) * 100).toFixed(1),
    suffix: "%",
  },
  {
    icon: "Timer",
    label: t("ai_workflow.develop_statAvgLatency"),
    value: stats.today.avg_latency_ms ?? 0,
    suffix: " ms",
  },
  {
    icon: "Warning",
    label: t("ai_workflow.develop_statPending"),
    value: stats.approvals.pending ?? 0,
    suffix: t("ai_workflow.develop_suffixRecords"),
  },
]);

// 近 7 天调用趋势（折线图数据源）
const logTrendPoints = computed(() =>
  (stats.series || []).map((d: any) => ({
    label: String(d.date).slice(5),
    value: Number(d.calls) || 0,
  }))
);

function isExpiringSoon(row: any) {
  if (!row?.expire_at) return false;
  const ts = new Date(String(row.expire_at).replace(" ", "T")).getTime();
  if (Number.isNaN(ts)) return false;
  return ts - Date.now() <= 7 * 24 * 3600 * 1000;
}

async function loadStats() {
  try {
    const res = await getDevelopStats(7);
    const d = res.data?.data || {};
    stats.today = d.today || {};
    stats.series = d.series || [];
    stats.top_capabilities = d.top_capabilities || [];
    stats.apps = d.apps || {};
    stats.approvals = d.approvals || {};
  } catch {
    // 统计失败不打断日志列表（静默降级）
  }
}

//: 时间范围快捷预设（当天 0 点 → 现在）。
const RANGE_PRESETS = [
  { label: t("ai_workflow.develop_today"), days: 1 },
  { label: t("ai_workflow.develop_recent7"), days: 7 },
  { label: t("ai_workflow.develop_recent30"), days: 30 },
];

function setQuickRange(days: number) {
  const pad = (n: number) => String(n).padStart(2, "0");
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (days - 1));
  logFilter.range = [fmt(start), fmt(now)];
  loadLogs();
}

// ---- 用量报告 ----
const usageLoading = ref(false);
const usageDays = ref(7);
const usageItems = ref<any[]>([]);

async function loadUsage(days?: number) {
  if (days) usageDays.value = days;
  usageLoading.value = true;
  try {
    const res = await getUsageReport(usageDays.value);
    usageItems.value = res.data?.data?.items || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_usageLoadFail"));
  } finally {
    usageLoading.value = false;
  }
}

// ---- 日志详情抽屉 + 导出 ----
const logDetail = reactive({ visible: false, row: null as any });

function openLogDetail(row: any) {
  logDetail.row = row;
  logDetail.visible = true;
}

async function onExportLogs() {
  try {
    const params = {
      app_id: toNum(logFilter.app_id),
      category: logFilter.category || undefined,
      method: logFilter.method || undefined,
      status: logFilter.status || undefined,
      start_time: logFilter.range?.[0] || undefined,
      end_time: logFilter.range?.[1] || undefined,
      capability: logFilter.capability || undefined,
    };
    const res = await exportCallLogs(params);
    downloadBlob(res, `ai-call-logs-${Date.now()}.csv`);
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_exportFail"));
  }
}

/** 下载 blob 响应（CSV 等导出公用）。 */
function downloadBlob(res: any, fallbackName: string) {
  const blob = res?.data instanceof Blob ? res.data : new Blob([res?.data]);
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fallbackName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
  ElMessage.success(t("ai_workflow.develop_downloadStarted"));
}

async function onExportUsage() {
  try {
    const res = await exportUsageReport(usageDays.value);
    downloadBlob(res, `ai-usage-report-${Date.now()}.csv`);
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_exportFail"));
  }
}

// ---- 能力试调 ----
const tryDialog = reactive({
  visible: false,
  app: null as any,
  capability: "",
  payloadText: "{}",
  resultText: "",
  resultObj: null as any,
  resultFields: [] as { label: string; value: string }[],
  loading: false,
});

//: 试调结果的关键字段（白名单映射，其余留在「原始响应」里）。
const TRY_RESULT_KEYS: [string, string][] = [
  ["id", "ID"],
  ["task_id", t("ai_workflow.develop_resultTaskId")],
  ["deleted", t("ai_workflow.develop_resultDeletedId")],
  ["agent_name", t("ai_workflow.develop_resultName")],
  ["name", t("ai_workflow.develop_resultName")],
  ["reply", t("ai_workflow.develop_resultReply")],
  ["sid", t("ai_workflow.develop_resultSid")],
  ["session_id", t("ai_workflow.develop_resultSessionId")],
  ["total", t("ai_workflow.develop_resultTotal")],
  ["status", t("ai_workflow.develop_resultStatus")],
  ["enabled", t("ai_workflow.develop_resultEnabled")],
  ["source_app_id", t("ai_workflow.develop_resultSourceApp")],
  ["items", t("ai_workflow.develop_resultItemsCount")],
];

function summarizeResult(obj: any): { label: string; value: string }[] {
  if (!obj || typeof obj !== "object") return [];
  const out: { label: string; value: string }[] = [];
  for (const [key, label] of TRY_RESULT_KEYS) {
    const value = obj[key];
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      out.push({ label, value: `${value.length} ${t("ai_workflow.develop_itemsUnit")}` });
    } else if (typeof value === "boolean") {
      out.push({
        label,
        value: value ? t("ai_workflow.develop_yes") : t("ai_workflow.develop_no"),
      });
    } else if (typeof value === "object") {
      out.push({ label, value: JSON.stringify(value) });
    } else {
      out.push({ label, value: String(value) });
    }
  }
  return out;
}

async function openTry(row: any) {
  if (!capabilities.value.length) await loadCapabilities();
  tryDialog.app = row;
  tryDialog.capability = "";
  tryDialog.payloadText = "{}";
  tryDialog.resultText = "";
  tryDialog.resultObj = null;
  tryDialog.resultFields = [];
  tryDialog.visible = true;
}

function onTryCapabilityChange(code: string) {
  const cap = capabilities.value.find((c: any) => c.code === code);
  if (!cap) return;
  // 用 schema 的 required 字段生成一个最小模板，降低手写 JSON 的成本
  const props = cap.input_schema?.properties || {};
  const required: string[] = cap.input_schema?.required || [];
  const template: Record<string, any> = {};
  required.forEach((key) => {
    const type = props[key]?.type;
    template[key] = type === "integer" || type === "number" ? 0 : type === "boolean" ? false : "";
  });
  tryDialog.payloadText = JSON.stringify(template, null, 2);
}

async function submitTry() {
  if (!tryDialog.capability) {
    ElMessage.warning(t("ai_workflow.develop_selectCapabilityRequired"));
    return;
  }
  let payload: any;
  try {
    payload = tryDialog.payloadText.trim() ? JSON.parse(tryDialog.payloadText) : {};
  } catch {
    ElMessage.error(t("ai_workflow.develop_invalidJson"));
    return;
  }
  tryDialog.loading = true;
  tryDialog.resultText = "";
  try {
    const res = await tryCapability(tryDialog.app.id, {
      capability: tryDialog.capability,
      payload,
    });
    const data = res.data?.data ?? res.data;
    tryDialog.resultObj = data && typeof data === "object" ? data : null;
    tryDialog.resultFields = summarizeResult(tryDialog.resultObj);
    tryDialog.resultText = prettyJson(data);
    ElMessage.success(t("ai_workflow.develop_trySuccess"));
    await loadLogs(false);
    await loadStats();
  } catch (e: any) {
    const code = e?.code ? `[${e.code}] ` : "";
    tryDialog.resultObj = null;
    tryDialog.resultFields = [];
    tryDialog.resultText = t("ai_workflow.develop_tryError", {
      code,
      msg: e?.msg || t("ai_workflow.develop_tryFailMsg"),
    });
  } finally {
    tryDialog.loading = false;
  }
}

async function loadLogs(resetPage = true) {
  if (resetPage) logPage.value = 1;
  logLoading.value = true;
  try {
    const res = await getCallLogs({
      app_id: toNum(logFilter.app_id),
      category: logFilter.category || undefined,
      method: logFilter.method || undefined,
      status: logFilter.status || undefined,
      capability: logFilter.capability || undefined,
      start_time: logFilter.range?.[0] || undefined,
      end_time: logFilter.range?.[1] || undefined,
      page_no: logPage.value,
      page_size: logPageSize.value,
    });
    const d = res.data?.data || {};
    logs.value = d.items || [];
    logTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_loadFail"));
  } finally {
    logLoading.value = false;
  }
}

function logStatusType(status?: string): "success" | "danger" | "warning" | "info" {
  if (status === "success" || status === "approved") return "success";
  if (status === "failed" || status === "error") return "danger";
  if (status === "denied" || status === "pending") return "warning";
  return "info";
}

//: 调用日志/会话里的英文枚举 → 中文（管理端不直接暴露协议名）。
const METHOD_LABELS: Record<string, string> = {
  REST: "REST",
  MCP: "MCP",
  EMBED: t("ai_workflow.develop_catEmbed"),
};
const STATUS_LABELS: Record<string, string> = {
  success: t("ai_workflow.develop_success"),
  failed: t("ai_workflow.develop_failed"),
  error: t("ai_workflow.develop_errorStatus"),
  denied: t("ai_workflow.develop_denied"),
  pending: t("ai_workflow.develop_pendingStatus"),
  approved: t("ai_workflow.develop_approvedStatus"),
  rejected: t("ai_workflow.develop_rejectedStatus"),
};
const TRANSPORT_LABELS: Record<string, string> = {
  "streamable-http": t("ai_workflow.develop_transportStreamable"),
  stdio: t("ai_workflow.develop_transportStdio"),
  sse: "SSE",
};

function methodLabel(method?: string) {
  return METHOD_LABELS[method || ""] || method || "—";
}

function statusLabel(status?: string) {
  return STATUS_LABELS[status || ""] || status || "—";
}

function transportLabel(transport?: string) {
  return TRANSPORT_LABELS[transport || ""] || transport || "—";
}

// ============ MCP 会话 ============
const mcpLoading = ref(false);
const mcps = ref<McpRow[]>([]);
const mcpTotal = ref(0);
const mcpPage = ref(1);
const mcpPageSize = ref(10);
const mcpFilter = reactive({ app_id: undefined as number | undefined });

async function loadMcps(resetPage = true) {
  if (resetPage) mcpPage.value = 1;
  mcpLoading.value = true;
  try {
    const res = await getMcpSessions({
      app_id: toNum(mcpFilter.app_id),
      page_no: mcpPage.value,
      page_size: mcpPageSize.value,
    });
    const d = res.data?.data || {};
    mcps.value = d.items || [];
    mcpTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_loadFail"));
  } finally {
    mcpLoading.value = false;
  }
}

// ---- 调用审批（敏感能力「先审批后执行」） ----
const APPROVAL_STATUS: Record<string, string> = {
  pending: t("ai_workflow.develop_approvalPendingStatus"),
  approved: t("ai_workflow.develop_approvedStatus"),
  rejected: t("ai_workflow.develop_rejectedStatus"),
  expired: t("ai_workflow.develop_expiredStatus"),
  failed: t("ai_workflow.develop_execFailStatus"),
};

const approvals = ref<any[]>([]);
const approvalTotal = ref(0);
const approvalPendingCount = ref(0);
const approvalPage = ref(1);
const approvalPageSize = ref(10);
const approvalLoading = ref(false);
const approvalFilter = reactive({ status: undefined as string | undefined });
const approvalTableRef = ref();
const approvalSelection = ref<any[]>([]);

async function onBatchApprove() {
  const ids = approvalSelection.value.map((r) => r.id);
  if (!ids.length) return;
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.develop_batchApproveConfirm", { count: ids.length }),
      t("ai_workflow.develop_batchApproveTitle", { count: ids.length }),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.develop_approveExecute"),
        cancelButtonText: t("ai_workflow.develop_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    const res = await batchReviewApprovals({ ids });
    const data = res.data?.data || { ok: [], failed: [] };
    const failed = (data.failed || []) as { id: number; msg: string }[];
    if (failed.length) {
      ElMessage.warning(
        t("ai_workflow.develop_batchApprovePartial", {
          ok: data.ok?.length || 0,
          failed: failed.length,
          msg: failed[0]?.msg || "",
        })
      );
    } else {
      ElMessage.success(
        res.data?.msg ||
          t("ai_workflow.develop_batchApproveSuccess", { count: data.ok?.length || 0 })
      );
    }
    approvalTableRef.value?.clearSelection();
    await loadApprovals(false);
    await loadStats();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_batchApproveFail"));
  }
}
const approvalDetail = reactive({ visible: false, row: null as any });

function approvalStatusType(status?: string) {
  const map: Record<string, "warning" | "success" | "info" | "danger"> = {
    pending: "warning",
    approved: "success",
    rejected: "info",
    expired: "info",
    failed: "danger",
  };
  return map[status || ""] || "info";
}

function prettyJson(value: any) {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value);
  }
}

async function loadApprovals(resetPage = true) {
  if (resetPage) approvalPage.value = 1;
  approvalLoading.value = true;
  try {
    const res = await getApprovals({
      status: approvalFilter.status || undefined,
      page_no: approvalPage.value,
      page_size: approvalPageSize.value,
    });
    const d = res.data?.data || {};
    approvals.value = d.items || [];
    approvalTotal.value = d.total || 0;
    approvalPendingCount.value = approvals.value.filter((r) => r.status === "pending").length;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_approvalLoadFail"));
  } finally {
    approvalLoading.value = false;
  }
}

function openApprovalDetail(row: any) {
  approvalDetail.row = row;
  approvalDetail.visible = true;
}

async function onReviewApproval(row: any, approve: boolean) {
  const action = approve
    ? t("ai_workflow.develop_reviewApproveAction")
    : t("ai_workflow.develop_reject");
  try {
    await ElMessageBox.confirm(
      approve
        ? t("ai_workflow.develop_reviewApproveConfirm", {
            capability: row.capability,
            appid: row.appid,
          })
        : t("ai_workflow.develop_reviewRejectConfirm", { capability: row.capability }),
      t("ai_workflow.develop_reviewConfirmTitle", { action }),
      {
        type: approve ? "warning" : "info",
        confirmButtonText: action,
        cancelButtonText: t("ai_workflow.develop_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    const res = await reviewApproval(row.id, { approve });
    ElMessage.success(res.data?.msg || t("ai_workflow.develop_processed"));
    if (approvalDetail.visible) approvalDetail.visible = false;
    await loadApprovals(false);
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_processFail"));
  }
}

// ---- MCP 会话概览（统计卡 + 近 N 天工具调用趋势） ----
const mcpStats = reactive<{ days: number; series: any[]; total: any }>({
  days: 7,
  series: [],
  total: {},
});

const mcpStatCards = computed(() => [
  {
    icon: "ChatDotRound",
    label: t("ai_workflow.develop_mcpStatSessions"),
    value: mcpStats.total?.sessions ?? 0,
    suffix: t("ai_workflow.develop_suffixItems"),
  },
  {
    icon: "Tools",
    label: t("ai_workflow.develop_mcpStatToolCalls"),
    value: mcpStats.total?.tool_calls ?? 0,
    suffix: t("ai_workflow.develop_suffixCount"),
  },
  {
    icon: "Timer",
    label: t("ai_workflow.develop_mcpStatAvgDuration"),
    value: mcpStats.total?.avg_duration_s ?? 0,
    suffix: " s",
  },
]);

// 近 N 天工具调用趋势（折线图数据源）
const mcpTrendPoints = computed(() =>
  (mcpStats.series || []).map((d: any) => ({
    label: String(d.date).slice(5),
    value: Number(d.tool_calls) || 0,
  }))
);

async function loadMcpStats() {
  try {
    const res = await getMcpStats(7);
    const d = res.data?.data || {};
    mcpStats.days = d.days || 7;
    mcpStats.series = d.series || [];
    mcpStats.total = d.total || {};
  } catch {
    // 概览失败不打断会话列表（静默降级）
  }
}

// ---- 审批通知配置（开关 + 各通道 JSON） ----
const NOTIFY_CHANNELS = ["email", "webhook", "sms"];
const NOTIFY_CONFIG_PLACEHOLDERS: Record<string, string> = {
  email: '{"recipients": ["admin@example.com"]}',
  webhook: '{"url": "https://example.com/hook", "method": "POST"}',
  sms: "{}",
};
const notifyCfg = reactive({
  visible: false,
  loading: false,
  channels: [] as string[],
  labels: {} as Record<string, string>,
  configs: {} as Record<string, string>,
});

async function openNotifyCfg() {
  notifyCfg.visible = true;
  notifyCfg.loading = true;
  try {
    const res = await getNotifyConfig();
    const d = res.data?.data || {};
    notifyCfg.channels = d.channels || [];
    notifyCfg.labels = d.labels || {};
    const raw = d.configs || {};
    const mapped: Record<string, string> = {};
    NOTIFY_CHANNELS.forEach((ch) => {
      mapped[ch] = raw[ch] && Object.keys(raw[ch]).length ? JSON.stringify(raw[ch], null, 2) : "";
    });
    notifyCfg.configs = mapped;
    if (d.broken?.length) {
      ElMessage.warning(t("ai_workflow.develop_notifyBroken", { broken: d.broken.join("、") }));
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_notifyLoadFail"));
    notifyCfg.visible = false;
  } finally {
    notifyCfg.loading = false;
  }
}

async function saveNotifyCfg() {
  const configs: Record<string, any> = {};
  for (const ch of notifyCfg.channels) {
    const text = (notifyCfg.configs[ch] || "").trim();
    if (!text) {
      configs[ch] = {};
      continue;
    }
    try {
      configs[ch] = JSON.parse(text);
    } catch {
      ElMessage.error(
        t("ai_workflow.develop_notifyInvalidJson", { name: notifyCfg.labels[ch] || ch })
      );
      return;
    }
  }
  notifyCfg.loading = true;
  try {
    const res = await saveNotifyConfig({ channels: notifyCfg.channels, configs });
    notifyCfg.visible = false;
    ElMessage.success(res.data?.msg || t("ai_workflow.develop_saved"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_saveFail"));
  } finally {
    notifyCfg.loading = false;
  }
}

function onTabChange(name: string | number) {
  const key = String(name);
  if (key === "logs") {
    if (!capabilities.value.length) loadCapabilities();
    loadLogs(false);
    loadStats();
  } else if (key === "mcp") {
    loadMcps(false);
    loadMcpStats();
  } else if (key === "approvals") loadApprovals(false);
  else if (key === "usage" && !usageItems.value.length) loadUsage();
  else if (key === "docs" && !capabilities.value.length) loadCapabilities();
}

// ---- 开放能力清单（接入文档页签） ----
const capabilities = ref<any[]>([]);
const capLoading = ref(false);

async function loadCapabilities() {
  capLoading.value = true;
  try {
    const res = await getCapabilities();
    capabilities.value = res.data?.data?.items || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_capLoadFail"));
  } finally {
    capLoading.value = false;
  }
}

// ---- 通用工具 ----
function fmtDateTime(v?: string | null, emptyText = t("ai_workflow.develop_forever")): string {
  if (!v) return emptyText;
  return String(v).replace("T", " ").slice(0, 19);
}

function toNum(v: unknown): number | undefined {
  if (v === "" || v === null || v === undefined) return undefined;
  const n = Number(v);
  return Number.isNaN(n) ? undefined : n;
}

async function copyText(text?: string) {
  if (!text) return;
  const doCopy = async () => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    throw new Error("clipboard unavailable");
  };
  try {
    await doCopy();
    ElMessage.success(t("ai_workflow.develop_copied"));
  } catch {
    // 降级方案：兼容非 https / 非 localhost 场景
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      ElMessage.success(t("ai_workflow.develop_copied"));
    } catch {
      ElMessage.error(t("ai_workflow.develop_copyFailManual"));
    } finally {
      document.body.removeChild(ta);
    }
  }
}

/** postMessage 事件契约（完整载荷见「嵌入」弹窗）。 */
const docEvents = [
  { name: "ready", desc: t("ai_workflow.develop_eventReady") },
  { name: "user_message", desc: t("ai_workflow.develop_eventUserMessage") },
  { name: "reply_start", desc: t("ai_workflow.develop_eventReplyStart") },
  { name: "reply_delta", desc: t("ai_workflow.develop_eventReplyDelta") },
  { name: "reply_done", desc: t("ai_workflow.develop_eventReplyDone") },
  { name: "error", desc: t("ai_workflow.develop_eventError") },
  { name: "token_expired", desc: t("ai_workflow.develop_eventTokenExpired") },
];

// ---- 嵌入管理弹窗 ----
const embedVisible = ref(false);
const embedRow = ref<any>(null);
function openEmbed(row: any) {
  embedRow.value = row;
  embedVisible.value = true;
}

onMounted(() => {
  loadApps();
  loadStats();
  loadAppOptions();
  // 支持从通知点击直达「调用审批」页签（?tab=approvals）
  if (route.query.tab === "approvals") {
    activeTab.value = "approvals";
    onTabChange("approvals");
  }
});
</script>

<style scoped>
.develop-search {
  margin-bottom: 4px;
}

/* 应用管理头部：搜索在左、「新增应用」在右 */
.develop-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}

.develop-head .develop-search {
  margin-bottom: 0;
}

.develop-head__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding-top: 1px;
}

.develop-head__actions .summary-tag {
  margin-left: 0;
}

.develop-alert {
  margin-bottom: 12px;
}

/* 应用卡片网格（替代表格）：卡片保持自然高度、顶部对齐；网格区撑满剩余高度、超出内部滚动，分页固定底部 */
.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  align-content: start;
  align-items: stretch;
}

.app-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  background: var(--el-bg-color);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.app-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.app-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.app-card__title {
  overflow: hidden;
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-card__appid {
  display: flex;
  align-items: center;
  gap: 4px;
}

.app-card__meta {
  display: flex;
  gap: 24px;
}

.app-card__meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.app-card__meta-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.app-card__caps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 24px;
}

.app-card__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.app-act {
  font-size: 16px;
  padding: 4px;
  color: var(--el-text-color-regular);
}

.app-act:hover {
  color: var(--el-color-primary);
}

.app-act--danger,
.app-act--danger:hover {
  color: var(--el-color-danger);
}

.develop-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.develop-toolbar__left {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.develop-toolbar__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.summary-tag {
  flex-shrink: 0;
}

.develop-pagination {
  display: flex;
  flex: 0 0 auto;
  justify-content: flex-end;
  margin-top: 12px;
}

.cap-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.appid-cell {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.appid-cell__value {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.mono-text {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.key-text {
  color: var(--el-color-primary);
  word-break: break-all;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

.text-warn {
  color: var(--el-color-warning);
}

.cap-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

/* 配额配置：与能力勾选区保持同一视觉语言（浅边框分组） */
.quota-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(240px, 1fr));
  gap: 8px 16px;
  width: 100%;
}

.quota-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.quota-item__label {
  min-width: 56px;
  color: var(--el-text-color-regular);
}

/* 调用概览：统计卡 + 7 天迷你柱 + Top 能力 */
.overview-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px 16px;
  margin-bottom: 4px;
}

.overview-stat {
  display: flex;
  align-items: center;
  gap: 6px;
}

.overview-stat__icon {
  color: var(--el-color-primary);
}

.overview-stat__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.overview-stat__value {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.overview-stat__suffix {
  margin-left: 2px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

/* 折线趋势卡（调用日志 / MCP 会话共用） */
.trend-card {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
}

.trend-card :deep(.el-card__header) {
  padding: 10px 12px;
}

.trend-card :deep(.el-card__body) {
  padding: 2px 12px 10px;
}

.trend-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.trend-card__title {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.trend-card__range {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.log-table :deep(.el-table__row) {
  cursor: pointer;
}

.try-result {
  width: 100%;
}

.quota-item__usage {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.try-form {
  margin-top: 12px;
}

.form-tip {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.cap-group {
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.cap-group__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.cap-group__count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.cap-check {
  margin-right: 12px;
}

.docs-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.docs-alert {
  margin-bottom: 0;
}

.doc-card {
  border: 1px solid var(--el-border-color-lighter);
}

.doc-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.doc-card__desc {
  margin: 0 0 12px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}

.doc-code {
  padding: 12px 14px;
  margin: 0;
  overflow-x: auto;
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.reveal-desc {
  margin-top: 12px;
}
.doc-events {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 10px;
}

.doc-events__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.doc-events__tag {
  font-family: var(--el-font-family-mono, monospace);
}

.doc-card__desc--foot {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.doc-card__desc--foot code {
  padding: 0 3px;
  font-family: var(--el-font-family-mono, monospace);
}
</style>
<style lang="scss">
/* 页面外壳与「能力市场」一致：12px 留白 + 白色面板 + 页签独立滚动 */
.app-container.ai-develop-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  overflow: hidden;
}

.ai-develop-page .develop-shell {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
}

.ai-develop-page .develop-shell > .el-card__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ai-develop-page .develop-tabs {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-develop-page .develop-tabs > .el-tabs__header {
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.ai-develop-page .develop-tabs > .el-tabs__content {
  flex: 1 1 auto;
  min-height: 0;
  padding-top: 4px;
  padding-right: 4px;
  overflow-y: auto;
}

/* 应用管理页签：纵向弹性布局——搜索在上、卡片网格区撑满剩余高度（内部滚动）、分页固定底部 */
.ai-develop-page .develop-apps-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* 表格页签（调用日志/MCP/用量/审批）：内容纵向撑满——表格区 flex:1、分页固定底部 */
.ai-develop-page .develop-table-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.ai-develop-page .table-flow {
  flex: 1 1 auto;
  min-height: 0;
}
</style>

<style lang="scss">
/* 应用表单较长（能力分组 + 配额）：限高并内部滚动，避免撑出视口 */
.develop-app-dialog {
  display: flex;
  flex-direction: column;
  max-height: 88vh;
}

.develop-app-dialog .el-dialog__body {
  min-height: 0;
  overflow-y: auto;
}
</style>
