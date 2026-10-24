<!-- AI 控制台：全局统计聚合 + 调用趋势 + 最近调用 + 快捷入口 -->
<template>
  <div class="app-container ai-overview-page">
    <el-row :gutter="12" class="ov-cards">
      <el-col v-for="c in cards" :key="c.key" :xs="12" :md="6">
        <el-card shadow="never" class="ov-card" @click="go(c.route)">
          <div class="ov-card__inner">
            <el-statistic :title="c.title" :value="stats[c.key]" />
            <div class="ov-card__hint">{{ c.hint }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-hasPerm="'module_ai:report:query'" shadow="never" class="ov-recent-card">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.aiReport") }}</span>
          <div class="flex items-center" style="gap: 10px">
            <span class="ai-sub">{{ t("ai_logs.aiReportSub") }}</span>
            <el-button type="primary" size="small" @click="openReportDrawer">
              {{ t("ai_logs.view") }}
            </el-button>
          </div>
        </div>
      </template>
      <div class="ov-usage-row">
        <span>{{ t("ai_logs.generatedReports") }}</span>
        <b>{{ stats.reports ?? 0 }}</b>
      </div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card" style="margin-bottom: 12px">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.compassCatalog") }}</span>
          <div class="ov-usage-row">
            <span class="ai-sub">{{ t("ai_logs.compassSearchSub") }}</span>
          </div>
        </div>
      </template>
      <div class="compass-bar">
        <el-input
          v-model="compassKw"
          :placeholder="t('ai_logs.compassPlaceholder')"
          clearable
          class="flex-1"
          @keyup.enter="runCompass"
        />
        <el-button type="primary" :loading="compassLoading" @click="runCompass">
          {{ t("ai_logs.search") }}
        </el-button>
      </div>
      <template v-if="compassResult">
        <div v-if="compassResult.assets?.length" class="gov-section mt-2">
          {{ t("ai_logs.tablesCount", { count: compassResult.assets.length }) }}
        </div>
        <div>
          <el-tag
            v-for="a in compassResult.assets"
            :key="a.table"
            size="small"
            effect="plain"
            class="mr-1 mb-1"
          >
            {{ a.alias || a.table }}
          </el-tag>
        </div>
        <div v-if="compassResult.objects?.length" class="gov-section mt-2">
          {{ t("ai_logs.objectsCount", { count: compassResult.objects.length }) }}
        </div>
        <div>
          <el-tag
            v-for="o in compassResult.objects"
            :key="o.code"
            size="small"
            type="warning"
            effect="plain"
            class="mr-1 mb-1"
          >
            {{ o.name }}
          </el-tag>
        </div>
        <div v-if="compassResult.metrics?.length" class="gov-section mt-2">
          {{ t("ai_logs.metricsCount", { count: compassResult.metrics.length }) }}
        </div>
        <div>
          <el-tag
            v-for="m in compassResult.metrics"
            :key="m.key"
            size="small"
            type="primary"
            effect="plain"
            class="mr-1 mb-1"
          >
            {{ m.name }}
          </el-tag>
        </div>
        <div v-if="compassResult.terms?.length" class="gov-section mt-2">
          {{ t("ai_logs.termsCount", { count: compassResult.terms.length }) }}
        </div>
        <div>
          <el-tag
            v-for="t in compassResult.terms"
            :key="t.term"
            size="small"
            type="info"
            effect="plain"
            class="mr-1 mb-1"
          >
            {{ t.term }}
          </el-tag>
        </div>
        <el-empty
          v-if="
            !compassResult.assets?.length &&
            !compassResult.objects?.length &&
            !compassResult.metrics?.length &&
            !compassResult.terms?.length
          "
          :image-size="30"
          :description="t('ai_logs.noMatchResult')"
        />
      </template>
    </el-card>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="15">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>{{ t("ai_logs.callTrendTitle") }}</template>
          <div ref="trendRef" class="ov-chart" />
        </el-card>
      </el-col>
      <el-col :md="9">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>{{ t("ai_logs.modelUsageCompare") }}</template>
          <div ref="modelRef" class="ov-chart" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="12">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>{{ t("ai_logs.quickEntries") }}</template>
          <div class="ov-entry-list">
            <div v-for="e in entries" :key="e.path" class="ov-entry" @click="$router.push(e.path)">
              <el-icon class="ov-entry__icon"><component :is="e.icon" /></el-icon>
              <div>
                <div class="ov-entry__name">{{ e.name }}</div>
                <div class="ov-entry__desc">{{ e.desc }}</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :md="12">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>{{ t("ai_logs.usageAndCost") }}</template>
          <div class="ov-usage-list">
            <div class="ov-usage-row">
              <span>{{ t("ai_logs.calledModels") }}</span>
              <b>{{ (stats.by_model || []).length }}</b>
            </div>
            <div class="ov-usage-row">
              <span>{{ t("ai_logs.totalPromptTokens") }}</span>
              <b>{{ sumTokens(stats.by_model, "prompt_tokens") }}</b>
            </div>
            <div class="ov-usage-row">
              <span>{{ t("ai_logs.totalCompletionTokens") }}</span>
              <b>{{ sumTokens(stats.by_model, "completion_tokens") }}</b>
            </div>
            <div class="ov-usage-row">
              <span>{{ t("ai_logs.totalCostYuan") }}</span>
              <b>{{ sumCost(stats.by_model) }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="ov-recent-card">
      <template #header>{{ t("ai_logs.recentCalls") }}</template>
      <el-table
        :data="stats.recent_calls || []"
        size="small"
        max-height="320"
        :show-overflow-tooltip="true"
        border
        stripe
      >
        <el-table-column prop="created_time" :label="t('ai_logs.time')" min-width="160" />
        <el-table-column prop="model_name" :label="t('ai_logs.model')" min-width="150" />
        <el-table-column prop="usage" :label="t('ai_logs.usage')" width="100" />
        <el-table-column prop="latency_ms" :label="t('ai_logs.latency')" width="90" align="center">
          <template #default="{ row }">{{ row.latency_ms }} ms</template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.result')" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
              {{ row.result === "success" ? t("ai_logs.success") : t("ai_logs.failed") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" :label="t('ai_logs.error')" min-width="200" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>{{ t("ai_logs.runtimeMonitor") }}</template>
      <el-row v-if="runtime" :gutter="12">
        <el-col :span="4">
          <el-statistic :title="t('ai_logs.apps')" :value="runtime.apps ?? 0" />
        </el-col>
        <el-col :span="4">
          <el-statistic :title="t('ai_logs.workflows')" :value="runtime.workflows ?? 0" />
        </el-col>
        <el-col :span="4">
          <el-statistic :title="t('ai_logs.models')" :value="runtime.models ?? 0" />
        </el-col>
        <el-col :span="4">
          <el-statistic :title="t('ai_logs.agents')" :value="runtime.agents ?? 0" />
        </el-col>
        <el-col :span="4">
          <div class="ov-usage-row">
            <span>{{ t("ai_logs.aiHealth") }}</span>
            <el-tag
              size="small"
              :type="
                runtime.health?.status === 'healthy'
                  ? 'success'
                  : runtime.health?.status === 'warning'
                    ? 'warning'
                    : 'danger'
              "
              effect="plain"
            >
              {{
                runtime.health?.status === "healthy"
                  ? t("ai_logs.healthy")
                  : runtime.health?.status === "warning"
                    ? t("ai_logs.warning")
                    : t("ai_logs.severe")
              }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="4">
          <el-statistic :title="t('ai_logs.last7dCalls')" :value="runtime.health?.calls ?? 0" />
        </el-col>
      </el-row>
      <div v-if="runtime" class="gov-section mt-2">{{ t("ai_logs.pipelineStatus") }}</div>
      <div v-if="runtime">
        <el-tag
          v-for="(cnt, st) in runtime.pipeline_status || {}"
          :key="st"
          size="small"
          :type="
            String(st) === 'success' ? 'success' : String(st) === 'failed' ? 'danger' : 'warning'
          "
          effect="plain"
          style="margin: 0 3px"
        >
          {{ st }}: {{ cnt }}
        </el-tag>
        <el-tag
          v-if="!Object.keys(runtime.pipeline_status || {}).length"
          size="small"
          type="info"
          effect="plain"
        >
          {{ t("ai_logs.noPipelineRun") }}
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.aipConsole") }}</span>
          <span class="ai-sub">{{ t("ai_logs.aipConsoleSub") }}</span>
        </div>
      </template>
      <el-row v-if="aip" :gutter="12" class="mb-2">
        <el-col :span="8">
          <el-statistic :title="t('ai_logs.runRecords')" :value="aip.total ?? 0" />
        </el-col>
        <el-col :span="8">
          <el-statistic :title="t('ai_logs.pendingReview')" :value="aip.pending_review ?? 0" />
        </el-col>
        <el-col :span="8">
          <div style="display: flex; align-items: center; gap: 6px">
            <span class="ai-sub">{{ t("ai_logs.usageDist") }}</span>
            <el-tag
              v-for="(n, u) in aip.usage_dist || {}"
              :key="u"
              size="small"
              type="info"
              effect="plain"
            >
              {{ u }}: {{ n }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
      <el-table :data="aip?.runs || []" size="small" max-height="360" border stripe>
        <el-table-column prop="time" :label="t('ai_logs.time')" width="100" />
        <el-table-column
          prop="model"
          :label="t('ai_logs.model')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column prop="usage" :label="t('ai_logs.usage')" width="110" />
        <el-table-column prop="latency_ms" :label="t('ai_logs.latencyMs')" width="90" />
        <el-table-column :label="t('ai_logs.result')" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.result === 'success' ? 'success' : 'danger'"
              effect="plain"
            >
              {{ row.result }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.tokens')" width="110" align="center">
          <template #default="{ row }">
            {{ row.prompt_tokens ?? 0 }} / {{ row.completion_tokens ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.costYuan')" width="90" align="center">
          <template #default="{ row }">{{ row.cost ?? 0 }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.agentDashboard") }}</span>
          <span class="ai-sub">{{ t("ai_logs.agentDashboardSub") }}</span>
        </div>
      </template>
      <el-row v-if="agentDash" :gutter="12" class="mb-2">
        <el-col :span="8">
          <el-statistic :title="t('ai_logs.totalAgents')" :value="agentDash.total_agents ?? 0" />
        </el-col>
        <el-col :span="8">
          <el-statistic
            :title="t('ai_logs.enabledAgents')"
            :value="agentDash.enabled_agents ?? 0"
          />
        </el-col>
        <el-col :span="8">
          <el-statistic :title="t('ai_logs.totalRuns')" :value="agentDash.total_runs ?? 0" />
        </el-col>
      </el-row>
      <el-table :data="agentDash?.agents || []" size="small" max-height="300" border stripe>
        <el-table-column
          prop="name"
          :label="t('ai_logs.agent')"
          min-width="120"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_logs.status')" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? t("ai_logs.enabled") : t("ai_logs.disabled") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="runs" :label="t('ai_logs.runs')" width="70" align="center" />
        <el-table-column :label="t('ai_logs.errorRate')" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.error_rate > 0.05 ? 'danger' : row.error_rate > 0 ? 'warning' : 'success'"
              effect="plain"
            >
              {{ (row.error_rate * 100).toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="avg_latency"
          :label="t('ai_logs.latencyMs')"
          width="90"
          align="center"
        />
        <el-table-column :label="t('ai_logs.orchestrationMatrix')" min-width="200">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" class="mr-1 mb-1">
              {{ t("ai_logs.tools", { count: row.tools }) }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain" class="mr-1 mb-1">
              {{ t("ai_logs.skills", { count: row.skills }) }}
            </el-tag>
            <el-tag size="small" type="info" effect="plain" class="mr-1 mb-1">
              {{ t("ai_logs.knowledge", { count: row.knowledge }) }}
            </el-tag>
            <el-tag
              v-for="cap in (row.capabilities || []).slice(0, 3)"
              :key="cap"
              size="small"
              type="primary"
              effect="plain"
              class="mr-1 mb-1"
            >
              {{ cap }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.securityPosture") }}</span>
          <span class="ai-sub">{{ t("ai_logs.securityPostureSub") }}</span>
        </div>
      </template>
      <div v-if="posture" class="ov-usage-row" style="margin-bottom: 8px; gap: 12px">
        <span>{{ t("ai_logs.compositeScore") }}</span>
        <el-progress
          type="circle"
          :width="90"
          :percentage="posture.score"
          :status="posture.score >= 90 ? 'success' : posture.score >= 70 ? 'warning' : 'exception'"
        />
        <el-tag
          size="small"
          :type="
            posture.level === 'excellent'
              ? 'success'
              : posture.level === 'good'
                ? 'warning'
                : 'danger'
          "
          effect="plain"
        >
          {{
            posture.level === "excellent"
              ? t("ai_logs.excellent")
              : posture.level === "good"
                ? t("ai_logs.good")
                : t("ai_logs.attention")
          }}
        </el-tag>
      </div>
      <el-row v-if="posture" :gutter="12">
        <el-col v-for="d in posture.dims" :key="d.key" :span="4">
          <div
            class="ov-usage-row"
            style="flex-direction: column; align-items: flex-start; gap: 4px"
          >
            <span class="ai-sub">{{ d.name }}</span>
            <el-progress
              :percentage="d.score"
              :show-text="false"
              :status="d.score >= 80 ? 'success' : d.score >= 60 ? 'warning' : 'exception'"
              class="w-full"
            />
            <b>{{ d.score }}</b>
          </div>
        </el-col>
      </el-row>
      <div v-if="posture" class="gov-section mt-2">{{ t("ai_logs.remediationItems") }}</div>
      <div v-if="posture">
        <el-tag
          v-for="(f, i) in posture.findings"
          :key="i"
          size="small"
          :type="f.level"
          effect="plain"
          class="mr-1 mb-1"
        >
          {{ f.msg }}
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.multiAgentOrchestration") }}</span>
          <span class="ai-sub">{{ t("ai_logs.multiAgentSub") }}</span>
        </div>
      </template>
      <div class="compass-bar">
        <el-input
          v-model="orchInput"
          :placeholder="t('ai_logs.orchPlaceholder')"
          clearable
          class="flex-1"
          @keyup.enter="runOrchestrate"
        />
        <el-button type="primary" :loading="orchLoading" @click="runOrchestrate">
          {{ t("ai_logs.orchestrate") }}
        </el-button>
      </div>
      <template v-if="orchResult">
        <div class="gov-section mt-2">
          {{ t("ai_logs.detectIntent", { intent: orchResult.intent }) }}
        </div>
        <el-steps :active="orchResult.steps.length" direction="vertical" style="margin-top: 4px">
          <el-step
            v-for="(s, i) in orchResult.steps"
            :key="i"
            :title="s.task"
            :description="t('ai_logs.capabilityReq', { cap: s.capability })"
          />
        </el-steps>
        <div class="gov-section mt-2">
          {{ t("ai_logs.participantAgents", { count: orchResult.agents_involved.length }) }}
        </div>
        <div>
          <el-tag v-if="!orchResult.agents_involved.length" size="small" type="info" effect="plain">
            {{ t("ai_logs.noParticipantAgent") }}
          </el-tag>
          <el-tag
            v-for="a in orchResult.agents_involved"
            :key="a.id"
            size="small"
            effect="plain"
            class="mr-1 mb-1"
          >
            {{ a.name }}（{{ a.role }}）
          </el-tag>
        </div>
      </template>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.governanceInspection") }}</span>
          <span class="ai-sub">{{ t("ai_logs.governanceInspectionSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="autoLoading" @click="loadAutopilot">
          {{ t("ai_logs.rescan") }}
        </el-button>
        <el-button size="small" type="danger" :loading="autoFixing" @click="runAutoFix">
          {{ t("ai_logs.oneClickFix") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ t("ai_logs.candidatesCount", { count: autopilot?.total ?? 0 }) }}
        </el-tag>
        <el-tag
          v-if="!autopilot?.actions?.length && !autoLoading"
          size="small"
          type="success"
          effect="plain"
        >
          {{ t("ai_logs.noRiskSuggest") }}
        </el-tag>
      </div>
      <template v-if="autopilot?.actions?.length">
        <div
          v-for="a in autopilot.actions"
          :key="a.id"
          class="ov-usage-row"
          style="justify-content: space-between; margin-bottom: 6px"
        >
          <div style="flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0">
            <el-tag
              size="small"
              :type="
                a.severity === 'high' ? 'danger' : a.severity === 'medium' ? 'warning' : 'info'
              "
              effect="plain"
            >
              {{ a.target }}
            </el-tag>
            <span class="ov-aip-sug">{{ a.suggestion }}</span>
          </div>
          <el-button
            v-if="a.executable !== 'none' && a.tables?.length"
            size="small"
            type="primary"
            :loading="autoExecuting === a.executable + a.tables[0]"
            @click="runAutopilot(a.executable, a.tables[0])"
          >
            {{ t("ai_logs.autoHandle") }}
          </el-button>
          <el-button v-else size="small" @click="runAutopilot('none', '')">
            {{ t("ai_logs.view") }}
          </el-button>
        </div>
      </template>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.derivedMetrics") }}</span>
          <span class="ai-sub">{{ t("ai_logs.derivedMetricsSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="derivedLoading" @click="loadDerived">
          {{ t("ai_logs.refresh") }}
        </el-button>
      </div>
      <el-table :data="derived" size="small" border stripe>
        <el-table-column prop="name" :label="t('ai_logs.derivedMetric')" min-width="120" />
        <el-table-column
          prop="formula"
          :label="t('ai_logs.rule')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_logs.baseMetrics')" min-width="160">
          <template #default="{ row }">
            <el-tag
              v-for="b in row.base"
              :key="b.ref"
              size="small"
              type="info"
              effect="plain"
              class="mr-1 mb-1"
            >
              {{ b.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.computedValue')" width="110" align="center">
          <template #default="{ row }">
            <span v-if="derivedValues[row.key]?.ok">
              {{ derivedValues[row.key].value }} {{ row.unit }}
            </span>
            <span v-else class="ai-sub">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_logs.operation')" width="90" align="center">
          <template #default="{ row }">
            <el-button icon="Cpu" size="small" type="primary" link @click="computeDerived(row.key)">
              {{ t("ai_logs.compute") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.securityAudit") }}</span>
          <span class="ai-sub">{{ t("ai_logs.securityAuditSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="securityLoading" @click="loadSecurity">
          {{ t("ai_logs.refresh") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{
            t("ai_logs.securitySummary", {
              tables: security?.assets ?? 0,
              fields: security?.sensitive_fields ?? 0,
            })
          }}
        </el-tag>
        <el-tag
          v-if="security"
          size="small"
          :type="security.score >= 80 ? 'success' : security.score >= 60 ? 'warning' : 'danger'"
          effect="plain"
        >
          {{ t("ai_logs.securityScore", { score: security.score }) }}
        </el-tag>
      </div>
      <el-row v-if="security" :gutter="12">
        <el-col v-for="d in security.dims" :key="d.key" :span="8">
          <div
            class="ov-usage-row"
            style="flex-direction: column; align-items: flex-start; gap: 4px"
          >
            <span class="ai-sub">{{ d.name }}</span>
            <el-progress
              :percentage="d.score"
              :show-text="false"
              :status="d.score >= 80 ? 'success' : d.score >= 60 ? 'warning' : 'exception'"
              class="w-full"
            />
            <b>{{ d.score }}</b>
          </div>
        </el-col>
      </el-row>
      <div v-if="security?.log_count" class="gov-section mt-2">
        {{ t("ai_logs.auditLogCount", { count: security.log_count }) }}
      </div>
      <el-table
        v-if="security?.log_count"
        :data="security.action_logs"
        size="small"
        max-height="260"
        border
        stripe
      >
        <el-table-column prop="time" :label="t('ai_logs.time')" width="120" />
        <el-table-column
          prop="action"
          :label="t('ai_logs.action')"
          min-width="110"
          show-overflow-tooltip
        />
        <el-table-column
          prop="table"
          :label="t('ai_logs.objectTable')"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_logs.result')" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="
                row.result === 'approved'
                  ? 'success'
                  : row.result === 'rejected' || row.result === 'error'
                    ? 'danger'
                    : 'warning'
              "
              effect="plain"
            >
              {{ row.result }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="operator" :label="t('ai_logs.operator')" width="90" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.derivedObjects") }}</span>
          <span class="ai-sub">{{ t("ai_logs.derivedObjectsSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="derivedObjLoading" @click="loadDerivedObj">
          {{ t("ai_logs.refresh") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{
            t("ai_logs.derivedObjSummary", {
              base: derivedObj?.base_objects ?? 0,
              derived: derivedObj?.total_derived ?? 0,
            })
          }}
        </el-tag>
      </div>
      <el-table :data="derivedObj?.derived_objects || []" size="small" border stripe>
        <el-table-column prop="name" :label="t('ai_logs.derivedObject')" min-width="120" />
        <el-table-column :label="t('ai_logs.baseObjects')" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-for="t in row.base_objects"
              :key="t"
              size="small"
              effect="plain"
              class="mr-1 mb-1"
            >
              {{ t }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="count" :label="t('ai_logs.objectCount')" width="80" align="center" />
        <el-table-column :label="t('ai_logs.derivedAttributes')" min-width="180">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain" class="mr-1 mb-1">
              {{ t("ai_logs.columns", { count: row.attributes?.total_columns ?? 0 }) }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain" class="mr-1 mb-1">
              {{ t("ai_logs.sensitive", { count: row.attributes?.sensitive_fields ?? 0 }) }}
            </el-tag>
            <el-tag size="small" type="success" effect="plain" class="mr-1 mb-1">
              {{ t("ai_logs.lineage", { count: row.attributes?.lineage_count ?? 0 }) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.compassFavorites") }}</span>
          <span class="ai-sub">{{ t("ai_logs.compassFavoritesSub") }}</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">{{ t("ai_logs.myFavorites", { count: favorites.length }) }}</div>
          <div v-if="favorites.length">
            <div
              v-for="f in favorites"
              :key="f.id"
              class="ov-usage-row"
              style="justify-content: space-between; margin-bottom: 4px"
            >
              <div style="display: flex; align-items: center; gap: 6px; min-width: 0">
                <el-tag size="small" type="info" effect="plain">{{ f.kind }}</el-tag>
                <span class="ai-ellipsis">
                  {{ f.ref }}
                </span>
              </div>
              <el-button icon="delete" link type="danger" size="small" @click="removeFav(f.id)">
                {{ t("ai_logs.remove") }}
              </el-button>
            </div>
          </div>
          <div v-else class="gov-empty">{{ t("ai_logs.noFavorites") }}</div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">{{ t("ai_logs.aipPlugins", { count: plugins.length }) }}</div>
          <el-tag v-for="p in plugins" :key="p.key" size="small" effect="plain" class="mr-1 mb-1">
            {{ p.name }} · {{ p.kind }}
          </el-tag>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.anomalyCenter") }}</span>
          <span class="ai-sub">{{ t("ai_logs.anomalyCenterSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadAnomaly">{{ t("ai_logs.rescanAnomaly") }}</el-button>
        <el-button size="small" type="primary" @click="loadDecision">
          {{ t("ai_logs.refreshDecision") }}
        </el-button>
      </div>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">
            {{ t("ai_logs.anomalies", { count: anomaly?.total ?? 0 }) }}
          </div>
          <div v-if="anomaly?.anomalies?.length">
            <div v-for="(a, i) in anomaly.anomalies" :key="i" class="ov-usage-row mb-1">
              <el-tag
                size="small"
                :type="a.severity === 'high' ? 'danger' : 'warning'"
                effect="plain"
              >
                {{ a.type }}
              </el-tag>
              <span class="text-xs">{{ a.msg }}</span>
            </div>
          </div>
          <el-empty v-else-if="anomaly" :image-size="30" :description="t('ai_logs.noAnomaly')" />
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">
            {{ t("ai_logs.decisionSuggestions", { count: decision?.total ?? 0 }) }}
          </div>
          <div v-if="decision?.decisions?.length">
            <div v-for="(d, i) in decision.decisions" :key="i" class="decision-item">
              <div class="ov-usage-row flex justify-between">
                <b>{{ d.title }}</b>
                <div class="ov-usage-row">
                  <el-tag
                    size="small"
                    :type="d.pri === 'high' ? 'danger' : 'warning'"
                    effect="plain"
                  >
                    {{ d.pri }}
                  </el-tag>
                  <el-button
                    icon="VideoPlay"
                    size="small"
                    type="primary"
                    link
                    @click="runDecision(d)"
                  >
                    {{ t("ai_logs.execute") }}
                  </el-button>
                </div>
              </div>
              <div class="decision-reason">{{ d.reason }}</div>
              <div class="decision-action">→ {{ d.action }}</div>
            </div>
          </div>
          <el-empty v-else-if="decision" :image-size="30" :description="t('ai_logs.noDecision')" />
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.impactPropagation") }}</span>
          <span class="ai-sub">{{ t("ai_logs.impactPropagationSub") }}</span>
        </div>
      </template>
      <div class="compass-bar mb-2">
        <el-input
          v-model="propTable"
          :placeholder="t('ai_logs.propTablePlaceholder')"
          class="flex-1"
          @keyup.enter="runPropagate"
        />
        <el-button type="primary" :loading="propLoading" @click="runPropagate">
          {{ t("ai_logs.propagate") }}
        </el-button>
        <el-button @click="loadDqRules">{{ t("ai_logs.refreshRules") }}</el-button>
      </div>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">
            {{ t("ai_logs.affectedDownstream", { count: propResult?.affected_count ?? 0 }) }}
          </div>
          <div v-if="propResult?.affected_tables?.length" class="obj-rel-graph">
            <svg :width="propLayout.W" :height="propLayout.H" viewBox="0 0 290 200">
              <g>
                <line
                  v-for="(e, i) in propLayout.edges"
                  :key="'pe' + i"
                  :x1="e.x1"
                  :y1="e.y1"
                  :x2="e.x2"
                  :y2="e.y2"
                  stroke="#909399"
                  stroke-width="1.5"
                  stroke-dasharray="4,2"
                />
              </g>
              <g v-for="n in propLayout.nodes" :key="n.id">
                <circle :cx="n.x" :cy="n.y" r="7" :fill="n.root ? '#F56C6C' : '#E6A23C'" />
                <text :x="n.x + 12" :y="n.y + 4" font-size="11" fill="#303133">{{ n.label }}</text>
              </g>
            </svg>
          </div>
          <div v-if="propResult?.affected_tables?.length">
            <el-tag
              v-for="t in propResult.affected_tables"
              :key="t"
              size="small"
              type="danger"
              effect="plain"
              class="mr-1 mb-1"
            >
              {{ t }}
            </el-tag>
          </div>
          <div v-if="propResult?.affected_metrics?.length" class="gov-section">
            {{ t("ai_logs.affectedMetrics") }}
          </div>
          <div v-if="propResult?.affected_metrics?.length">
            <el-tag
              v-for="m in propResult.affected_metrics"
              :key="m.key"
              size="small"
              type="warning"
              effect="plain"
              class="mr-1 mb-1"
            >
              {{ m.name }}
            </el-tag>
          </div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">{{ t("ai_logs.dqRules") }}</div>
          <div
            v-for="r in dqRules"
            :key="r.key"
            class="ov-usage-row"
            style="justify-content: space-between; margin-bottom: 4px"
          >
            <div>
              <b class="text-xs">{{ r.name }}</b>
              <span class="ai-sub ml-1.5">
                {{ r.desc }}
              </span>
            </div>
            <el-button size="small" :loading="dqRunKey === r.key" @click="runRule(r)">
              {{ t("ai_logs.validate") }}
            </el-button>
          </div>
          <div v-if="dqRunResult" style="margin-top: 4px">
            <el-tag size="small" :type="dqRunResult.passed ? 'success' : 'danger'" effect="plain">
              {{ dqRunResult.rule }} ·
              {{ t("ai_logs.passRate", { rate: dqRunResult.pass_rate }) }} ·
              {{ dqRunResult.valid }}/{{ dqRunResult.total }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.myShares") }}</span>
          <span class="ai-sub">{{ t("ai_logs.mySharesSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadShares">{{ t("ai_logs.refresh") }}</el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ t("ai_logs.sharesCount", { count: shares.length }) }}
        </el-tag>
      </div>
      <el-table v-if="shares.length" :data="shares" size="small" border stripe>
        <el-table-column
          prop="table"
          :label="t('ai_logs.dataset')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column prop="time" :label="t('ai_logs.shareTime')" width="150" />
        <el-table-column
          prop="token"
          :label="t('ai_logs.token')"
          width="120"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_logs.operation')" width="120" align="center">
          <template #default="{ row }">
            <el-button icon="CopyDocument" link type="primary" size="small" @click="copyShare(row)">
              {{ t("ai_logs.copy") }}
            </el-button>
            <el-button
              icon="RefreshLeft"
              link
              type="danger"
              size="small"
              @click="revokeShare(row.id)"
            >
              {{ t("ai_logs.revoke") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="gov-empty">{{ t("ai_logs.noShares") }}</div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.unifiedTimeline") }}</span>
          <span class="ai-sub">{{ t("ai_logs.unifiedTimelineSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadTimeline">{{ t("ai_logs.refresh") }}</el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ t("ai_logs.eventsCount", { count: timeline?.total ?? 0 }) }}
        </el-tag>
      </div>
      <el-timeline v-if="timeline?.events?.length">
        <el-timeline-item
          v-for="(e, i) in timeline.events"
          :key="i"
          :timestamp="e.time"
          placement="top"
        >
          <div class="ov-usage-row flex justify-between">
            <b class="text-xs">{{ e.title }}</b>
            <el-tag
              size="small"
              :type="
                e.result === 'success' || e.result === 'approved'
                  ? 'success'
                  : e.result === 'error' || e.result === 'rejected'
                    ? 'danger'
                    : 'info'
              "
              effect="plain"
            >
              {{ e.result || e.kind }}
            </el-tag>
          </div>
          <div class="ai-sub">{{ e.detail }} · {{ e.actor }}</div>
        </el-timeline-item>
      </el-timeline>
      <div v-else class="gov-empty">{{ t("ai_logs.noActivity") }}</div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.compassRelationsDrill") }}</span>
          <span class="ai-sub">{{ t("ai_logs.compassRelationsSub") }}</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="8">
          <div class="gov-section">
            {{ t("ai_logs.catalogCategories", { count: catalog?.category_count ?? 0 }) }}
          </div>
          <el-button size="small" class="mb-1" :loading="catalogLoading" @click="loadCatalog">
            {{ t("ai_logs.refresh") }}
          </el-button>
          <div
            v-for="c in catalog?.categories || []"
            :key="c.domain"
            class="ov-usage-row"
            style="justify-content: space-between; margin-bottom: 4px"
          >
            <span class="text-xs">{{ c.domain }}</span>
            <el-tag size="small" type="info" effect="plain">{{ c.count }}</el-tag>
          </div>
        </el-col>
        <el-col :sm="24" :md="8">
          <div class="gov-section">
            {{
              t("ai_logs.objectRelations", {
                edges: objRel?.edge_count ?? 0,
                nodes: objRel?.node_count ?? 0,
              })
            }}
          </div>
          <el-button size="small" class="mb-1" :loading="objRelLoading" @click="loadObjRel">
            {{ t("ai_logs.refresh") }}
          </el-button>
          <div v-if="objRel?.edges?.length" class="obj-rel-graph">
            <svg :width="objRelLayout.W" :height="objRelLayout.H" viewBox="0 0 500 300">
              <g>
                <line
                  v-for="(e, i) in objRelLayout.eRows"
                  :key="'e' + i"
                  :x1="e.x1"
                  :y1="e.y1"
                  :x2="e.x2"
                  :y2="e.y2"
                  stroke="#909399"
                  stroke-width="1.5"
                />
              </g>
              <g v-for="n in objRelLayout.items" :key="n.id">
                <circle
                  :cx="n.x"
                  :cy="n.y"
                  r="7"
                  :fill="
                    n.dq != null && n.dq < 60
                      ? '#F56C6C'
                      : n.dq != null && n.dq < 80
                        ? '#E6A23C'
                        : '#67C23A'
                  "
                />
                <text :x="n.x + 12" :y="n.y + 4" font-size="11" fill="#303133">{{ n.label }}</text>
              </g>
            </svg>
          </div>
          <div v-else>{{ t("ai_logs.noObjectRelations") }}</div>
        </el-col>
        <el-col :sm="24" :md="8">
          <div class="gov-section">{{ t("ai_logs.accessDrill", { user: walkthroughId }) }}</div>
          <div class="compass-bar mb-1">
            <el-input-number v-model="walkthroughId" :min="0" size="small" style="width: 110px" />
            <el-button size="small" :loading="walkLoading" @click="loadWalkthrough">
              {{ t("ai_logs.drill") }}
            </el-button>
          </div>
          <div v-if="walkthrough" class="ov-usage-row mb-1">
            <el-tag size="small" type="success" effect="plain">
              {{ t("ai_logs.accessAllowed", { count: walkthrough.allowed_count }) }}
            </el-tag>
            <el-tag size="small" type="danger" effect="plain">
              {{ t("ai_logs.accessRestricted", { count: walkthrough.blocked_count }) }}
            </el-tag>
            <el-tag size="small" type="info" effect="plain">
              {{
                t("ai_logs.sensitiveVisible", {
                  value: walkthrough.can_see_sensitive ? t("ai_logs.yes") : t("ai_logs.no"),
                })
              }}
            </el-tag>
          </div>
          <div v-if="walkthrough?.allowed?.length" class="ai-sub ai-ellipsis">
            {{
              t("ai_logs.accessAllowedList", {
                list: walkthrough.allowed.map((x: any) => x.alias || x.table).join("、"),
              })
            }}
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.aipGuardrails") }}</span>
          <span class="ai-sub">{{ t("ai_logs.aipGuardrailsSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadGuardrails">{{ t("ai_logs.refresh") }}</el-button>
        <el-progress
          :percentage="guardrails?.score ?? 0"
          :show-text="true"
          :stroke-width="12"
          class="flex-1"
          :status="(guardrails?.score ?? 0) >= 80 ? 'success' : 'warning'"
        />
      </div>
      <el-row v-if="guardrails" :gutter="12">
        <el-col v-for="c in guardrails.checks" :key="c.key" :span="4">
          <div class="guardrail-item" :class="{ on: c.enabled }">
            <el-icon style="margin-right: 4px">
              <CircleCheck v-if="c.enabled" />
              <CircleClose v-else />
            </el-icon>
            <b class="text-xs">{{ c.name }}</b>
            <span class="ai-sub">
              {{ c.detail }}
            </span>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.objectBrowser") }}</span>
          <span class="ai-sub">{{ t("ai_logs.objectBrowserSub") }}</span>
        </div>
      </template>
      <div class="compass-bar mb-2">
        <el-input
          v-model="browseTable"
          :placeholder="t('ai_logs.browseTablePlaceholder')"
          class="flex-1"
          @keyup.enter="
            browsePage = 1;
            loadBrowse();
          "
        />
        <el-button
          type="primary"
          :loading="browseLoading"
          @click="
            browsePage = 1;
            loadBrowse();
          "
        >
          {{ t("ai_logs.browse") }}
        </el-button>
      </div>
      <template v-if="browse?.ok">
        <div class="ov-usage-row mb-1">
          <el-tag size="small" type="info" effect="plain">
            {{ t("ai_logs.browseSummary", { total: browse.total, page: browse.page }) }}
          </el-tag>
          <el-pagination
            v-model:current-page="browsePage"
            :page-size="20"
            :total="browse.total"
            layout="prev, pager, next"
            small
            @current-change="loadBrowse"
          />
        </div>
        <el-table :data="browse.rows" size="small" border max-height="320" class="w-full" stripe>
          <el-table-column
            v-for="c in (browse.columns || []).slice(0, 10)"
            :key="c"
            :prop="c"
            :label="c"
            min-width="90"
            show-overflow-tooltip
          />
        </el-table>
      </template>
      <el-alert v-else-if="browse?.msg" type="error" :closable="false" :title="browse.msg" />
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.aipGovernanceReport") }}</span>
          <span class="ai-sub">{{ t("ai_logs.aipGovernanceReportSub") }}</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button type="primary" :loading="reportLoading" @click="loadReport">
          {{ t("ai_logs.generateReport") }}
        </el-button>
        <el-button :disabled="!report" @click="downloadReport">
          {{ t("ai_logs.exportMd") }}
        </el-button>
        <el-tag v-if="report" size="small" type="info" effect="plain">
          {{ report.generated_at }}
        </el-tag>
      </div>
      <template v-if="report">
        <el-row :gutter="12" class="mb-2">
          <el-col :span="8">
            <el-statistic :title="t('ai_logs.compliance')" :value="report.scores.compliance" />
          </el-col>
          <el-col :span="8">
            <el-statistic :title="t('ai_logs.security')" :value="report.scores.security" />
          </el-col>
          <el-col :span="8">
            <el-statistic :title="t('ai_logs.governanceCheck')" :value="report.scores.guardrails" />
          </el-col>
        </el-row>
        <div class="gov-section">{{ t("ai_logs.summary") }}</div>
        <div v-for="(s, i) in report.summary" :key="i" class="report-line">• {{ s }}</div>
      </template>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.assetHotspots") }}</span>
          <span class="ai-sub">{{ t("ai_logs.assetHotspotsSub") }}</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">{{ t("ai_logs.assetHotspotsTitle") }}</div>
          <el-button size="small" class="mb-1" @click="loadHotspots">
            {{ t("ai_logs.refresh") }}
          </el-button>
          <div
            v-for="h in (hotspots?.hot || []).slice(0, 8)"
            :key="h.table"
            class="ov-usage-row"
            style="justify-content: space-between; margin-bottom: 3px"
          >
            <span class="ai-ellipsis">
              {{ h.alias || h.table }}
            </span>
            <el-tag size="small" type="info" effect="plain">
              {{ t("ai_logs.refs", { count: h.refs }) }}
            </el-tag>
          </div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">{{ t("ai_logs.objectLifecycle") }}</div>
          <el-button size="small" class="mb-1" @click="loadLifecycle">
            {{ t("ai_logs.refresh") }}
          </el-button>
          <div v-if="lifecycle" class="ov-usage-row" style="margin-bottom: 6px">
            <el-tag size="small" type="success" effect="plain">
              {{ t("ai_logs.objects", { count: lifecycle.objects }) }}
            </el-tag>
            <el-tag size="small" type="primary" effect="plain">
              {{ t("ai_logs.published", { count: lifecycle.published }) }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain">
              {{ t("ai_logs.draftCount", { count: lifecycle.draft }) }}
            </el-tag>
            <el-tag size="small" type="danger" effect="plain">
              {{ t("ai_logs.sensitiveCount", { count: lifecycle.sensitive_objects }) }}
            </el-tag>
          </div>
          <div v-if="lifecycle" class="gov-section">{{ t("ai_logs.objectList") }}</div>
          <el-tag
            v-for="o in (lifecycle?.objects_list || []).slice(0, 8)"
            :key="o.table"
            size="small"
            effect="plain"
            class="mr-1 mb-1"
          >
            {{ o.alias || o.table }}
          </el-tag>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.evalAndAudit") }}</span>
          <span class="ai-sub">{{ t("ai_logs.evalAndAuditSub") }}</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">{{ t("ai_logs.evalBenchmark") }}</div>
          <div class="ov-usage-row mb-1">
            <el-button size="small" type="primary" @click="runBench">
              {{ t("ai_logs.runAndFix") }}
            </el-button>
            <el-button size="small" :loading="benchLoading" @click="loadBench">
              {{ t("ai_logs.refresh") }}
            </el-button>
          </div>
          <div v-if="bench.length">
            <div
              v-for="b in bench.slice(0, 8)"
              :key="b.id"
              class="ov-usage-row"
              style="justify-content: space-between; margin-bottom: 3px"
            >
              <span class="text-xs">
                {{ b.name }}
                <span style="color: var(--el-text-color-secondary)">
                  · {{ b.total }} {{ t("ai_logs.cases") }} · {{ b.time }}
                </span>
              </span>
              <el-tag
                size="small"
                :type="b.precision >= 0.8 ? 'success' : b.precision >= 0.6 ? 'warning' : 'danger'"
                effect="plain"
              >
                {{ (b.precision * 100).toFixed(1) }}%
              </el-tag>
            </div>
          </div>
          <div v-else class="gov-empty">{{ t("ai_logs.noEvalRecords") }}</div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">
            {{ t("ai_logs.unifiedAuditDays", { days: unified?.days ?? 7 }) }}
          </div>
          <div v-if="unified" class="ov-usage-row" style="margin-bottom: 6px">
            <el-tag size="small" type="info" effect="plain">
              {{ t("ai_logs.aiCalls", { count: unified.ai_calls }) }}
            </el-tag>
            <el-tag size="small" type="danger" effect="plain">
              {{ t("ai_logs.failedCount", { count: unified.ai_errors }) }}
            </el-tag>
            <el-tag size="small" type="success" effect="plain">
              {{ t("ai_logs.actionsCount", { count: unified.actions }) }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain">
              {{ t("ai_logs.pendingApprovals", { count: unified.approvals }) }}
            </el-tag>
          </div>
          <div v-if="unified?.audit_log?.length">
            <div
              v-for="(e, i) in unified.audit_log.slice(0, 8)"
              :key="i"
              class="ov-usage-row"
              style="justify-content: space-between; margin-bottom: 2px"
            >
              <span class="ai-ellipsis">
                {{ e.title }}
              </span>
              <el-tag
                size="small"
                :type="e.result === 'success' ? 'success' : 'danger'"
                effect="plain"
              >
                {{ e.result }}
              </el-tag>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>{{ t("ai_logs.capabilityEval") }}</span>
          <span class="ai-sub">
            {{ t("ai_logs.capabilityEvalSub") }}
          </span>
        </div>
      </template>
      <el-input
        v-model="evalSamplesText"
        type="textarea"
        :rows="5"
        :placeholder="t('ai_logs.evalSamplePlaceholder')"
      />
      <div class="ops-bar mt-2">
        <el-button type="primary" size="small" :loading="evalLoading" @click="runEval">
          {{ t("ai_logs.runEval") }}
        </el-button>
        <el-button size="small" @click="loadEvalTemplate">{{ t("ai_logs.loadSample") }}</el-button>
        <el-tag v-if="evalResult" size="small" type="info" effect="plain">
          {{
            t("ai_logs.evalPrecision", {
              pct: (evalResult.precision * 100).toFixed(1),
              passed: evalResult.passed,
              total: evalResult.total,
            })
          }}
        </el-tag>
      </div>
      <el-table
        v-if="evalResult?.rows?.length"
        :data="evalResult.rows"
        size="small"
        border
        max-height="220"
        class="mt-2"
        stripe
      >
        <el-table-column
          prop="input"
          :label="t('ai_logs.input')"
          min-width="180"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_logs.pass')" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ok ? 'success' : 'danger'" effect="plain">
              {{ row.ok ? t("ai_logs.passed") : t("ai_logs.notPassed") }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-row :gutter="12" class="mt-3">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="ov-usage-row flex justify-between">
              <span>{{ t("ai_logs.aiHealthDays", { days: health?.days ?? 7 }) }}</span>
              <el-button size="small" @click="loadHealth">{{ t("ai_logs.refresh") }}</el-button>
            </div>
          </template>
          <div v-if="health">
            <el-tag
              size="small"
              :type="
                health.status === 'healthy'
                  ? 'success'
                  : health.status === 'warning'
                    ? 'warning'
                    : 'danger'
              "
              effect="plain"
            >
              {{
                health.status === "healthy"
                  ? t("ai_logs.healthy")
                  : health.status === "warning"
                    ? t("ai_logs.warning")
                    : t("ai_logs.severe")
              }}
            </el-tag>
            <div class="ov-usage-row mt-2">
              <span>{{ t("ai_logs.calls") }}</span>
              <b>{{ health.calls }}</b>
              <span>{{ t("ai_logs.errorRate") }}</span>
              <b>{{ (health.error_rate * 100).toFixed(1) }}%</b>
              <span>{{ t("ai_logs.avgLatency") }}</span>
              <b>{{ health.avg_latency_ms }}ms</b>
              <span>{{ t("ai_logs.cost") }}</span>
              <b>{{ t("ai_logs.costYuanValue", { value: health.total_cost }) }}</b>
            </div>
            <div
              v-for="(a, i) in health.alerts"
              :key="i"
              class="dq-alert__item"
              style="margin-top: 4px"
            >
              <el-tag size="small" :type="a.level === 'critical' ? 'danger' : 'warning'">
                {{ a.msg }}
              </el-tag>
            </div>
            <el-empty
              v-if="!health.alerts.length"
              :image-size="30"
              :description="t('ai_logs.noAlerts')"
            />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="ov-usage-row flex justify-between">
              <span>{{ t("ai_logs.complianceAuditDays", { days: audit?.days ?? 7 }) }}</span>
              <el-button size="small" @click="loadAudit">{{ t("ai_logs.refresh") }}</el-button>
            </div>
          </template>
          <div v-if="audit">
            <el-tag size="small" :type="audit.compliant ? 'success' : 'warning'" effect="plain">
              {{ audit.compliant ? t("ai_logs.compliant") : t("ai_logs.riskExists") }}
            </el-tag>
            <div class="ov-usage-row mt-2">
              <span>{{ t("ai_logs.calls") }}</span>
              <b>{{ audit.total }}</b>
              <span>{{ t("ai_logs.unauthenticated") }}</span>
              <b style="color: var(--el-color-danger)">{{ audit.anonymous_calls }}</b>
              <span>{{ t("ai_logs.failed") }}</span>
              <b style="color: var(--el-color-warning)">{{ audit.error_calls }}</b>
              <span>{{ t("ai_logs.highCost") }}</span>
              <b>{{ audit.high_cost_calls }}</b>
            </div>
            <div
              v-for="(a, i) in audit.issues"
              :key="i"
              class="dq-alert__item"
              style="margin-top: 4px"
            >
              <el-tag size="small" type="warning">{{ a.msg }}</el-tag>
            </div>
            <el-empty
              v-if="!audit.issues.length"
              :image-size="30"
              :description="t('ai_logs.noComplianceIssues')"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-drawer
      v-model="reportDrawerVisible"
      :title="t('ai_logs.aiReport')"
      size="600px"
      append-to-body
    >
      <div v-loading="reportListLoading" class="ai-report-drawer">
        <div class="flex items-center justify-between mb-2">
          <span class="ai-report-sub">
            {{ t("ai_logs.reportCount", { count: reportList.length }) }}
          </span>
          <el-button
            v-hasPerm="'module_ai:report:delete'"
            type="danger"
            plain
            size="small"
            :disabled="!reportSelection.length"
            @click="batchDeleteReports"
          >
            {{ t("ai_logs.deleteSelected", { count: reportSelection.length }) }}
          </el-button>
        </div>
        <el-table
          v-if="reportList.length"
          ref="reportTableRef"
          :data="reportList"
          size="small"
          max-height="460"
          border
          stripe
          @selection-change="onReportSelect"
        >
          <el-table-column type="selection" width="46" />
          <el-table-column
            prop="title"
            :label="t('ai_logs.title')"
            min-width="180"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_logs.type')" width="110">
            <template #default="{ row }">
              <el-tag size="small" type="info" effect="plain">{{ reportSourceLabel(row) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_time" :label="t('ai_logs.createdTime')" min-width="150" />
          <el-table-column :label="t('ai_logs.operation')" width="130" align="center">
            <template #default="{ row }">
              <el-button icon="View" link type="primary" size="small" @click="viewReport(row)">
                {{ t("ai_logs.view") }}
              </el-button>
              <el-button
                v-hasPerm="'module_ai:report:delete'"
                icon="delete"
                link
                type="danger"
                size="small"
                @click="deleteReport(row)"
              >
                {{ t("ai_logs.delete") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty
          v-else-if="!reportListLoading"
          :image-size="60"
          :description="t('ai_logs.noAiReports')"
        />
      </div>
    </el-drawer>

    <el-dialog
      v-model="reportDetailVisible"
      :title="reportDetail?.title || t('ai_logs.aiReportDetail')"
      width="600px"
      append-to-body
    >
      <div v-loading="reportDetailLoading" class="ai-report-detail">
        <div class="flex items-center gap-2 mb-2">
          <el-tag size="small" type="info" effect="plain">
            {{ reportSourceLabel(reportDetail) }}
          </el-tag>
          <span class="ai-report-sub">
            {{ t("ai_logs.createdAt", { time: reportDetail?.created_time || "-" }) }}
          </span>
        </div>
        <MarkdownRenderer v-if="reportDetail?.content" :content="reportDetail.content" />
        <el-empty
          v-else-if="!reportDetailLoading"
          :image-size="40"
          :description="t('ai_logs.noContent')"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import * as echarts from "echarts";
import {
  Collection,
  SetUp,
  Cpu,
  MagicStick,
  Coin,
  Message,
  Files,
  Link,
  CircleCheck,
  CircleClose,
} from "@element-plus/icons-vue";
import {
  getAiOverviewStats,
  runAiEval,
  getAiHealth,
  getAiAudit,
  getAiRuntime,
  compassSearch,
  getAiAipControl,
  getAiCompliancePosture,
  getAiAnomaly,
  getAiDecisionCenter,
  getAiActivityTimeline,
  executeDecision,
  runEvalBench,
  getEvalBenchList,
  getUnifiedAudit,
} from "@/api/module_ai/overview";
import { getAiAgentDashboard } from "@/api/module_ai/agent";
import { getAutopilot, autopilotExecute } from "@/api/module_ai/query";
import { getDerivedMetrics, computeDerivedMetric } from "@/api/module_ai/query";
import { getSecurityAudit } from "@/api/module_ai/query";
import { getDerivedObjects, autopilotAutoFix } from "@/api/module_ai/query";
import { getFavorites, removeFavorite, getPlugins } from "@/api/module_ai/query";
import { lineagePropagate, getDqRules, runDqRule } from "@/api/module_ai/query";
import { getShareList, removeShare } from "@/api/module_ai/query";
import {
  getCatalogCategories,
  getObjectRelations,
  getAccessWalkthrough,
} from "@/api/module_ai/query";
import { getGuardrailsStatus } from "@/api/module_ai/query";
import { getGovernanceReport } from "@/api/module_ai/query";
import { getAssetHotspots, getObjectLifecycle } from "@/api/module_ai/query";
import { objectBrowse } from "@/api/module_ai/query";
import { orchestrateAgents } from "@/api/module_ai/agent";
import { getAiReportList, getAiReportDetail, deleteAiReports } from "@/api/module_ai/report";

defineOptions({ name: "AiOverview" });

const { t } = useI18n();

const stats = reactive<any>({});
const evalSamplesText = ref("");
const evalResult = ref<any>(null);
const evalLoading = ref(false);
const health = ref<any>(null);
const audit = ref<any>(null);
const runtime = ref<any>(null);
const compassKw = ref("");
const compassResult = ref<any>(null);
const compassLoading = ref(false);
const aip = ref<any>(null);
async function loadAip() {
  try {
    aip.value = (await getAiAipControl(20)).data?.data || null;
  } catch {
    aip.value = null;
  }
}
const agentDash = ref<any>(null);
async function loadAgentDash() {
  try {
    agentDash.value = (await getAiAgentDashboard()).data?.data || null;
  } catch {
    agentDash.value = null;
  }
}
const posture = ref<any>(null);
async function loadPosture() {
  try {
    posture.value = (await getAiCompliancePosture()).data?.data || null;
  } catch {
    posture.value = null;
  }
}
const anomaly = ref<any>(null);
async function loadAnomaly() {
  try {
    anomaly.value = (await getAiAnomaly(7)).data?.data || null;
  } catch {
    anomaly.value = null;
  }
}
const decision = ref<any>(null);
async function loadDecision() {
  try {
    decision.value = (await getAiDecisionCenter()).data?.data || null;
  } catch {
    decision.value = null;
  }
}
async function runDecision(d: any) {
  try {
    const r = await executeDecision(d.key);
    if (r.data?.data?.navigate) {
      ElMessage.info(r.data?.data?.msg || d.action);
    } else {
      ElMessage.success(r.data?.data?.msg || t("ai_logs.executed"));
      loadDecision();
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.executeFailed"));
  }
}
const timeline = ref<any>(null);
async function loadTimeline() {
  try {
    timeline.value = (await getAiActivityTimeline(7, 60)).data?.data || null;
  } catch {
    timeline.value = null;
  }
}
const orchInput = ref("");
const orchResult = ref<any>(null);
const orchLoading = ref(false);
async function runOrchestrate() {
  if (!orchInput.value.trim()) return;
  orchLoading.value = true;
  try {
    orchResult.value = (await orchestrateAgents(orchInput.value)).data?.data || null;
  } catch {
    orchResult.value = null;
  } finally {
    orchLoading.value = false;
  }
}
const autopilot = ref<any>(null);
const autoLoading = ref(false);
const autoExecuting = ref("");
async function loadAutopilot() {
  autoLoading.value = true;
  try {
    autopilot.value = (await getAutopilot()).data?.data || null;
  } catch {
    autopilot.value = null;
  } finally {
    autoLoading.value = false;
  }
}
async function runAutopilot(executable: string, table: string) {
  if (executable === "none") {
    ElMessage.info(t("ai_logs.manualHandle"));
    return;
  }
  autoExecuting.value = executable + table;
  try {
    const r = await autopilotExecute(executable, table);
    ElMessage.success(r.data?.data?.msg || t("ai_logs.executed"));
    loadAutopilot();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.executeFailed"));
  } finally {
    autoExecuting.value = "";
  }
}
const derived = ref<any[]>([]);
const derivedLoading = ref(false);
const derivedValues = ref<Record<string, any>>({});
async function loadDerived() {
  derivedLoading.value = true;
  try {
    derived.value = (await getDerivedMetrics()).data?.data || [];
  } catch {
    derived.value = [];
  } finally {
    derivedLoading.value = false;
  }
}
async function computeDerived(key: string) {
  try {
    const r = await computeDerivedMetric(key);
    derivedValues.value = { ...derivedValues.value, [key]: r.data?.data || null };
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.computeFailed"));
  }
}
const security = ref<any>(null);
const securityLoading = ref(false);
async function loadSecurity() {
  securityLoading.value = true;
  try {
    security.value = (await getSecurityAudit(30)).data?.data || null;
  } catch {
    security.value = null;
  } finally {
    securityLoading.value = false;
  }
}
const derivedObj = ref<any>(null);
const derivedObjLoading = ref(false);
async function loadDerivedObj() {
  derivedObjLoading.value = true;
  try {
    derivedObj.value = (await getDerivedObjects()).data?.data || null;
  } catch {
    derivedObj.value = null;
  } finally {
    derivedObjLoading.value = false;
  }
}
const autoFixed = ref<any>(null);
const autoFixing = ref(false);
async function runAutoFix() {
  try {
    await ElMessageBox.confirm(t("ai_logs.autoFixConfirm"), t("ai_logs.autoFixTitle"), {
      type: "warning",
      confirmButtonText: t("ai_logs.runFix"),
      cancelButtonText: t("ai_logs.cancel"),
    });
  } catch {
    return;
  }
  autoFixing.value = true;
  try {
    const r = await autopilotAutoFix();
    autoFixed.value = r.data?.data || null;
    ElMessage.success(
      t("ai_logs.autoFixDone", {
        fixed: autoFixed.value?.fixed ?? 0,
        attempted: autoFixed.value?.attempted ?? 0,
      })
    );
    loadAutopilot();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.autoFixFailed"));
  } finally {
    autoFixing.value = false;
  }
}
const favorites = ref<any[]>([]);
async function loadFavorites() {
  try {
    favorites.value = (await getFavorites()).data?.data || [];
  } catch {
    favorites.value = [];
  }
}
const plugins = ref<any[]>([]);
async function loadPlugins() {
  try {
    plugins.value = (await getPlugins()).data?.data || [];
  } catch {
    plugins.value = [];
  }
}
async function removeFav(id: number) {
  try {
    await removeFavorite(id);
    loadFavorites();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.removeFailed"));
  }
}
const propTable = ref("video_alarm_records");
const propResult = ref<any>(null);
const propLoading = ref(false);
async function runPropagate() {
  if (!propTable.value.trim()) return;
  propLoading.value = true;
  try {
    propResult.value = (await lineagePropagate(propTable.value)).data?.data || null;
  } catch {
    propResult.value = null;
  } finally {
    propLoading.value = false;
  }
}
const propLayout = computed(() => {
  const root = propResult.value?.root;
  const affs = (propResult.value?.affected_tables || []).slice(0, 12);
  const W = 290,
    H = 200;
  const nodes: any[] = [];
  const edges: any[] = [];
  const rx = 28,
    ry = H / 2;
  if (root) nodes.push({ id: root, label: root, x: rx, y: ry, root: true });
  const cols = 3,
    colW = 72,
    rowH = 40;
  affs.forEach((t: string, i: number) => {
    const col = i % cols,
      row = Math.floor(i / cols);
    const x = 120 + col * colW,
      y = 24 + row * rowH;
    nodes.push({ id: t, label: t, x, y });
    edges.push({ x1: rx, y1: ry, x2: x, y2: y });
  });
  return { W, H, nodes, edges };
});
const dqRules = ref<any[]>([]);
const dqRunResult = ref<any>(null);
const dqRunKey = ref("");
async function loadDqRules() {
  try {
    dqRules.value = (await getDqRules()).data?.data || [];
  } catch {
    dqRules.value = [];
  }
}
async function runRule(r: any) {
  const table = propTable.value.trim() || "video_alarm_records";
  dqRunKey.value = r.key;
  try {
    dqRunResult.value = (await runDqRule(table, "id", r.key)).data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.ruleValidateFailed"));
  } finally {
    dqRunKey.value = "";
  }
}
const shares = ref<any[]>([]);
async function loadShares() {
  try {
    shares.value = (await getShareList()).data?.data || [];
  } catch {
    shares.value = [];
  }
}
async function revokeShare(id: number) {
  try {
    await removeShare(id);
    loadShares();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.revokeFailed"));
  }
}
async function copyShare(row: any) {
  const link = `${location.origin}${row.link || ""}`;
  try {
    await navigator.clipboard.writeText(link);
    ElMessage.success(t("ai_logs.copiedShareLink"));
  } catch {
    ElMessageBox.alert(t("ai_logs.shareLinkMsg", { link }), t("ai_logs.datasetShare"), {
      confirmButtonText: t("ai_logs.copy"),
    });
  }
}
const catalog = ref<any>(null);
const catalogLoading = ref(false);
async function loadCatalog() {
  catalogLoading.value = true;
  try {
    catalog.value = (await getCatalogCategories()).data?.data || null;
  } catch {
    catalog.value = null;
  } finally {
    catalogLoading.value = false;
  }
}
const objRel = ref<any>(null);
const objRelLoading = ref(false);
async function loadObjRel() {
  objRelLoading.value = true;
  try {
    objRel.value = (await getObjectRelations()).data?.data || null;
  } catch {
    objRel.value = null;
  } finally {
    objRelLoading.value = false;
  }
}
const objRelLayout = computed(() => {
  const nodes = objRel.value?.nodes || [];
  const edges = objRel.value?.edges || [];
  const cols = 4,
    cellW = 120,
    cellH = 46,
    W = 500,
    H = 300;
  const pos: Record<string, { x: number; y: number }> = {};
  const items = nodes.map((n: any, i: number) => {
    const col = i % cols,
      row = Math.floor(i / cols);
    const x = 30 + col * cellW,
      y = 26 + row * cellH;
    pos[n.id] = { x, y };
    return { id: n.id, label: n.label || n.id, x, y, dq: n.dq };
  });
  const eRows = edges
    .filter((e: any) => pos[e.source] && pos[e.target])
    .map((e: any) => ({
      x1: pos[e.source].x,
      y1: pos[e.source].y,
      x2: pos[e.target].x,
      y2: pos[e.target].y,
      source: e.source,
      target: e.target,
    }));
  return { W, H, items, eRows };
});
const walkthrough = ref<any>(null);
const walkthroughId = ref(1);
const walkLoading = ref(false);
async function loadWalkthrough() {
  walkLoading.value = true;
  try {
    walkthrough.value = (await getAccessWalkthrough(walkthroughId.value)).data?.data || null;
  } catch {
    walkthrough.value = null;
  } finally {
    walkLoading.value = false;
  }
}
const guardrails = ref<any>(null);
async function loadGuardrails() {
  try {
    guardrails.value = (await getGuardrailsStatus()).data?.data || null;
  } catch {
    guardrails.value = null;
  }
}
const browseTable = ref("video_alarm_records");
const browsePage = ref(1);
const browse = ref<any>(null);
const browseLoading = ref(false);
async function loadBrowse() {
  if (!browseTable.value.trim()) return;
  browseLoading.value = true;
  try {
    browse.value = (await objectBrowse(browseTable.value, browsePage.value, 20)).data?.data || null;
  } catch {
    browse.value = null;
  } finally {
    browseLoading.value = false;
  }
}
const report = ref<any>(null);
const reportLoading = ref(false);
async function loadReport() {
  reportLoading.value = true;
  try {
    report.value = (await getGovernanceReport()).data?.data || null;
  } catch {
    report.value = null;
  } finally {
    reportLoading.value = false;
  }
}
function downloadReport() {
  if (!report.value?.markdown) return;
  const blob = new Blob([report.value.markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${t("ai_logs.governanceReportFile")}_${report.value.generated_at?.replace(/[ :]/g, "-") || "now"}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---- AI 报告（列表抽屉 / 详情弹窗 / 删除，局部更新） ----
const reportDrawerVisible = ref(false);
const reportList = ref<any[]>([]);
const reportListLoading = ref(false);
const reportSelection = ref<any[]>([]);
const reportTableRef = ref<any>(null);
const reportDetailVisible = ref(false);
const reportDetail = ref<any>(null);
const reportDetailLoading = ref(false);

function reportSourceLabel(row: any): string {
  const raw = row?.source;
  if (!raw) return t("ai_logs.aiReport");
  let obj: any = raw;
  if (typeof raw === "string") {
    try {
      obj = JSON.parse(raw);
    } catch {
      return t("ai_logs.aiReport");
    }
  }
  if (obj?.plugin) {
    const pmap: Record<string, string> = { report_generate: t("ai_logs.reportGenerate") };
    return pmap[obj.plugin] || String(obj.plugin);
  }
  if (obj?.scope) {
    const smap: Record<string, string> = {
      annotation: t("ai_logs.scopeAnnotation"),
      train: t("ai_logs.scopeTrain"),
      video: t("ai_logs.scopeVideo"),
      all: t("ai_logs.scopeAll"),
    };
    return smap[obj.scope] || String(obj.scope);
  }
  if (obj?.topic) return t("ai_logs.topicReport");
  return t("ai_logs.aiReport");
}

async function openReportDrawer() {
  reportDrawerVisible.value = true;
  if (!reportList.value.length) await loadReportList();
}

async function loadReportList() {
  reportListLoading.value = true;
  try {
    const r = await getAiReportList();
    reportList.value = r.data?.data || [];
  } catch {
    reportList.value = [];
  } finally {
    reportListLoading.value = false;
  }
}

function onReportSelect(selection: any[]) {
  reportSelection.value = selection;
}

async function viewReport(row: any) {
  reportDetailLoading.value = true;
  try {
    const r = await getAiReportDetail(row.id);
    reportDetail.value = r.data?.data || null;
    reportDetailVisible.value = true;
  } catch {
    reportDetail.value = null;
  } finally {
    reportDetailLoading.value = false;
  }
}

async function deleteReport(row: any) {
  try {
    await ElMessageBox.confirm(
      t("ai_logs.deleteReportMsg", { title: row.title }),
      t("ai_logs.deleteReport"),
      {
        type: "warning",
        confirmButtonText: t("ai_logs.delete"),
        cancelButtonText: t("ai_logs.cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    await deleteAiReports([row.id]);
    reportList.value = reportList.value.filter((x) => x.id !== row.id);
    reportSelection.value = reportSelection.value.filter((x) => x.id !== row.id);
    stats.reports = Math.max(0, (stats.reports || 0) - 1);
  } catch {
    // 错误提示已由拦截器处理
  }
}

async function batchDeleteReports() {
  const ids = reportSelection.value.map((x) => x.id);
  if (!ids.length) return;
  try {
    await ElMessageBox.confirm(
      t("ai_logs.batchDeleteReportsMsg", { count: ids.length }),
      t("ai_logs.batchDeleteReports"),
      {
        type: "warning",
        confirmButtonText: t("ai_logs.delete"),
        cancelButtonText: t("ai_logs.cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    await deleteAiReports(ids);
    const idSet = new Set(ids);
    reportList.value = reportList.value.filter((x) => !idSet.has(x.id));
    reportSelection.value = [];
    reportTableRef.value?.clearSelection();
    stats.reports = Math.max(0, (stats.reports || 0) - ids.length);
  } catch {
    // 错误提示已由拦截器处理
  }
}

const hotspots = ref<any>(null);
async function loadHotspots() {
  try {
    hotspots.value = (await getAssetHotspots()).data?.data || null;
  } catch {
    hotspots.value = null;
  }
}
const lifecycle = ref<any>(null);
async function loadLifecycle() {
  try {
    lifecycle.value = (await getObjectLifecycle()).data?.data || null;
  } catch {
    lifecycle.value = null;
  }
}
const bench = ref<any[]>([]);
const benchLoading = ref(false);
async function loadBench() {
  benchLoading.value = true;
  try {
    bench.value = (await getEvalBenchList(30)).data?.data || [];
  } catch {
    bench.value = [];
  } finally {
    benchLoading.value = false;
  }
}
async function runBench() {
  try {
    const samples = [
      {
        input: t("ai_logs.benchInput"),
        expected_keywords: [t("ai_logs.benchKw")],
        actual: t("ai_logs.benchActual"),
      },
    ];
    await runEvalBench(samples, t("ai_logs.benchName"));
    ElMessage.success(t("ai_logs.benchDone"));
    loadBench();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_logs.benchFailed"));
  }
}
const unified = ref<any>(null);
async function loadUnified() {
  try {
    unified.value = (await getUnifiedAudit(7)).data?.data || null;
  } catch {
    unified.value = null;
  }
}
async function runCompass() {
  if (!compassKw.value.trim()) {
    compassResult.value = null;
    return;
  }
  compassLoading.value = true;
  try {
    compassResult.value = (await compassSearch(compassKw.value)).data?.data || null;
  } catch {
    compassResult.value = null;
  } finally {
    compassLoading.value = false;
  }
}
async function loadRuntime() {
  try {
    runtime.value = (await getAiRuntime()).data?.data || null;
  } catch {
    runtime.value = null;
  }
}
async function loadHealth() {
  try {
    health.value = (await getAiHealth()).data?.data || null;
  } catch {
    health.value = null;
  }
}
async function loadAudit() {
  try {
    audit.value = (await getAiAudit()).data?.data || null;
  } catch {
    audit.value = null;
  }
}
function loadEvalTemplate() {
  evalSamplesText.value = JSON.stringify([
    {
      input: t("ai_logs.sampleOrderInput"),
      expected_keywords: [t("ai_logs.sampleOrderKw")],
      actual: t("ai_logs.sampleOrderActual"),
    },
    {
      input: t("ai_logs.sampleHealthInput"),
      expected_keywords: ["%"],
      actual: t("ai_logs.sampleHealthActual"),
    },
  ]);
}
async function runEval() {
  evalLoading.value = true;
  try {
    let samples: any[] = [];
    try {
      samples = JSON.parse(evalSamplesText.value || "[]");
    } catch {
      ElMessage.warning(t("ai_logs.sampleJsonError"));
      return;
    }
    const r = await runAiEval(samples);
    evalResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.message || t("ai_logs.evalFailed"));
  } finally {
    evalLoading.value = false;
  }
}
const trendRef = ref<HTMLElement>();
const modelRef = ref<HTMLElement>();
let trendChart: echarts.ECharts | null = null;
let modelChart: echarts.ECharts | null = null;

function sumTokens(list: any[], key: string) {
  return (list || []).reduce((s, x) => s + (x[key] || 0), 0);
}
function sumCost(list: any[]) {
  const v = (list || []).reduce((s, x) => s + (x.cost || 0), 0);
  return v.toFixed(2);
}

const cards = [
  {
    key: "models",
    title: t("ai_logs.cardModels"),
    hint: t("ai_logs.cardModelsHint"),
    route: "/ai/model",
    icon: Cpu,
  },
  {
    key: "providers",
    title: t("ai_logs.cardProviders"),
    hint: t("ai_logs.cardProvidersHint"),
    route: "/ai/provider",
    icon: Link,
  },
  {
    key: "knowledge_bases",
    title: t("ai_logs.cardKnowledge"),
    hint: t("ai_logs.cardKnowledgeHint"),
    route: "/ai/knowledge",
    icon: Collection,
  },
  {
    key: "apps",
    title: t("ai_logs.cardApps"),
    hint: t("ai_logs.cardAppsHint"),
    route: "/ai/app",
    icon: MagicStick,
  },
  {
    key: "workflows",
    title: t("ai_logs.cardWorkflows"),
    hint: t("ai_logs.cardWorkflowsHint"),
    route: "/ai/workflow",
    icon: SetUp,
  },
  {
    key: "calls",
    title: t("ai_logs.cardCalls"),
    hint: t("ai_logs.cardCallsHint"),
    route: "/ai/logs",
    icon: Message,
  },
  {
    key: "today_calls",
    title: t("ai_logs.cardTodayCalls"),
    hint: t("ai_logs.cardTodayCallsHint"),
    route: "/ai/logs",
    icon: Coin,
  },
  {
    key: "success_rate",
    title: t("ai_logs.cardSuccessRate"),
    hint: t("ai_logs.cardSuccessRateHint"),
    route: "/ai/logs",
    icon: Files,
  },
];

const entries = [
  {
    name: t("ai_logs.entryKnowledge"),
    desc: t("ai_logs.entryKnowledgeDesc"),
    path: "/ai/knowledge",
    icon: Collection,
  },
  {
    name: t("ai_logs.entryApps"),
    desc: t("ai_logs.entryAppsDesc"),
    path: "/ai/app",
    icon: MagicStick,
  },
  {
    name: t("ai_logs.entryWorkflows"),
    desc: t("ai_logs.entryWorkflowsDesc"),
    path: "/ai/workflow",
    icon: SetUp,
  },
  {
    name: t("ai_logs.entryModels"),
    desc: t("ai_logs.entryModelsDesc"),
    path: "/ai/model",
    icon: Cpu,
  },
  {
    name: t("ai_logs.entryProviders"),
    desc: t("ai_logs.entryProvidersDesc"),
    path: "/ai/provider",
    icon: Link,
  },
  {
    name: t("ai_logs.entryLogs"),
    desc: t("ai_logs.entryLogsDesc"),
    path: "/ai/logs",
    icon: Message,
  },
];

function go(route?: string) {
  if (route) location.hash = `#${route}`;
}

async function load() {
  try {
    const r = await getAiOverviewStats();
    Object.assign(stats, r.data?.data || {});
    await nextTick();
    render();
  } catch {
    // 统计失败不阻断
  }
}

function render() {
  if (trendRef.value) {
    trendChart = trendChart || echarts.init(trendRef.value);
    const trend = stats.trend || [];
    trendChart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: [t("ai_logs.chartCalls"), t("ai_logs.chartErrors")], top: 0, right: 8 },
      grid: { left: 44, right: 20, top: 36, bottom: 26 },
      xAxis: { type: "category", data: trend.map((x: any) => x.date) },
      yAxis: { type: "value" },
      series: [
        {
          name: t("ai_logs.chartCalls"),
          type: "bar",
          data: trend.map((x: any) => x.count),
          itemStyle: { color: "#409eff" },
        },
        {
          name: t("ai_logs.chartErrors"),
          type: "line",
          smooth: true,
          data: trend.map((x: any) => x.error),
        },
      ],
    });
  }
  if (modelRef.value) {
    modelChart = modelChart || echarts.init(modelRef.value);
    const m = stats.by_model || [];
    // 横向条形：模型名较长（smbs/LLM-284B-MXFP4），竖排 X 轴标签会挤压旋转，改横向更可读
    modelChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 8, right: 24, top: 16, bottom: 8, containLabel: true },
      xAxis: { type: "value" },
      yAxis: {
        type: "category",
        inverse: true,
        data: m.map((x: any) => x.name),
        axisLabel: { width: 120, overflow: "truncate" },
      },
      series: [
        {
          name: t("ai_logs.chartCalls"),
          type: "bar",
          data: m.map((x: any) => x.count),
          itemStyle: { color: "#67c23a" },
          barMaxWidth: 18,
        },
      ],
    });
  }
}

function resize() {
  trendChart?.resize();
  modelChart?.resize();
}

onMounted(() => {
  load();
  loadHealth();
  loadAudit();
  loadRuntime();
  loadAip();
  loadAgentDash();
  loadPosture();
  loadAutopilot();
  loadDerived();
  loadSecurity();
  loadDerivedObj();
  loadFavorites();
  loadPlugins();
  loadAnomaly();
  loadDecision();
  loadDqRules();
  loadShares();
  loadTimeline();
  loadCatalog();
  loadObjRel();
  loadWalkthrough();
  loadGuardrails();
  loadBrowse();
  loadReport();
  loadHotspots();
  loadLifecycle();
  loadBench();
  loadUnified();
  window.addEventListener("resize", resize);
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", resize);
  trendChart?.dispose();
  modelChart?.dispose();
});
</script>

<style scoped>
/* 次要说明文字：统一 12px + 次要色（替代 26 处重复的内联 style） */
.ai-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
/* 单行截断（替代重复的内联 overflow/ellipsis 组合） */
.ai-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-overview-page {
  padding: 16px;
  overflow: auto;
}
.ov-cards {
  margin-bottom: 12px;
}
.ov-card {
  margin-bottom: 12px;
  cursor: pointer;
}
.ov-card__inner {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ov-card__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ov-body {
  margin-bottom: 12px;
}
.ov-chart-card {
  margin-bottom: 12px;
}
.ov-chart {
  height: 300px;
}
.ov-entry-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ov-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
}
.ov-entry:hover {
  background: var(--el-fill-color-light);
}
.ov-entry__icon {
  font-size: 20px;
  color: var(--el-color-primary);
}
.ov-entry__name {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ov-entry__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ov-usage-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}
.ov-usage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.ov-usage-row b {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}
.ov-recent-card {
  margin-bottom: 12px;
}
.compass-bar {
  display: flex;
  gap: 8px;
}
.ov-aip-sug {
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.decision-item {
  margin-bottom: 6px;
  padding: 6px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}
.decision-reason {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-top: 2px;
}
.decision-action {
  font-size: 12px;
  color: var(--el-color-primary);
  margin-top: 2px;
}
.guardrail-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 6px 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 6px;
}
.guardrail-item.on {
  border-color: var(--el-color-success-light-7);
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}
.report-line {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-bottom: 2px;
}
.obj-rel-graph {
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  overflow: hidden;
  max-width: 100%;
}
.obj-rel-graph svg {
  max-width: 100%;
  height: auto;
}
</style>

<style lang="scss">
/* 覆盖全局 .app-container(flex column;height:100%)：控制台改为块级自然流，避免卡片被 flex 压缩/重叠 */
.app-container.ai-overview-page {
  /* 保持 display:block（脱离 flex，防 el-card 被 shrink 压没——AGENTS.md 调试记忆）；
     height/overflow 回归与系统管理参照页同构的「锁视口 + 内部滚动」 */
  display: block !important;
  height: 100% !important;
  overflow: auto !important;
}

/* 控制台单卡内容限高内部滚动：防「最近记录/时间线」大列表把整页撑到上万像素（实测 17241px）。
   已带 max-height 属性的 el-table 走 inline 样式优先，不受此兜底影响。 */
.ai-overview-page .ov-recent-card .el-table__body-wrapper {
  max-height: 360px;
  overflow-y: auto;
}
.ai-overview-page .ov-recent-card .el-timeline {
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

/* 非 scoped：AI 报告抽屉/详情弹窗 append-to-body 后脱离 scoped 作用域，需全局定义 */
.ai-report-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ai-report-drawer {
  padding: 0 4px;
}
</style>
