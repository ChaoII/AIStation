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

    <el-card shadow="never" class="ov-recent-card" style="margin-bottom: 12px">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>Compass 全局数据目录</span>
          <div class="ov-usage-row">
            <span class="ai-sub">搜索 表 / 对象 / 指标 / 术语</span>
          </div>
        </div>
      </template>
      <div class="compass-bar">
        <el-input
          v-model="compassKw"
          placeholder="输入关键词，如 摄像头 / 告警 / 订单"
          clearable
          class="flex-1"
          @keyup.enter="runCompass"
        />
        <el-button type="primary" :loading="compassLoading" @click="runCompass">搜索</el-button>
      </div>
      <template v-if="compassResult">
        <div v-if="compassResult.assets?.length" class="gov-section mt-2">
          表（{{ compassResult.assets.length }}）
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
          对象（{{ compassResult.objects.length }}）
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
          指标（{{ compassResult.metrics.length }}）
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
          术语（{{ compassResult.terms.length }}）
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
          description="无匹配结果"
        />
      </template>
    </el-card>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="15">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>调用趋势（近 7 天）</template>
          <div ref="trendRef" class="ov-chart" />
        </el-card>
      </el-col>
      <el-col :md="9">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>模型用量对比</template>
          <div ref="modelRef" class="ov-chart" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="ov-body">
      <el-col :md="12">
        <el-card shadow="never" class="ov-chart-card">
          <template #header>快捷入口</template>
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
          <template #header>用量与成本</template>
          <div class="ov-usage-list">
            <div class="ov-usage-row">
              <span>调用模型</span>
              <b>{{ (stats.by_model || []).length }}</b>
            </div>
            <div class="ov-usage-row">
              <span>总输入 token</span>
              <b>{{ sumTokens(stats.by_model, "prompt_tokens") }}</b>
            </div>
            <div class="ov-usage-row">
              <span>总输出 token</span>
              <b>{{ sumTokens(stats.by_model, "completion_tokens") }}</b>
            </div>
            <div class="ov-usage-row">
              <span>总成本(元)</span>
              <b>{{ sumCost(stats.by_model) }}</b>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="ov-recent-card">
      <template #header>最近调用</template>
      <el-table
        :data="stats.recent_calls || []"
        size="small"
        max-height="320"
        :show-overflow-tooltip="true"
      >
        <el-table-column prop="created_time" label="时间" min-width="160" />
        <el-table-column prop="model_name" label="模型" min-width="150" />
        <el-table-column prop="usage" label="用途" width="100" />
        <el-table-column prop="latency_ms" label="耗时" width="90" align="center">
          <template #default="{ row }">{{ row.latency_ms }} ms</template>
        </el-table-column>
        <el-table-column label="结果" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.result === 'success' ? 'success' : 'danger'" size="small">
              {{ row.result === "success" ? "成功" : "失败" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error" label="错误" min-width="200" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>系统运行监控</template>
      <el-row v-if="runtime" :gutter="12">
        <el-col :span="4"><el-statistic title="应用" :value="runtime.apps ?? 0" /></el-col>
        <el-col :span="4"><el-statistic title="工作流" :value="runtime.workflows ?? 0" /></el-col>
        <el-col :span="4"><el-statistic title="模型" :value="runtime.models ?? 0" /></el-col>
        <el-col :span="4"><el-statistic title="智能体" :value="runtime.agents ?? 0" /></el-col>
        <el-col :span="4">
          <div class="ov-usage-row">
            <span>AI健康</span>
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
                  ? "健康"
                  : runtime.health?.status === "warning"
                    ? "预警"
                    : "严重"
              }}
            </el-tag>
          </div>
        </el-col>
        <el-col :span="4">
          <el-statistic title="近7天调用" :value="runtime.health?.calls ?? 0" />
        </el-col>
      </el-row>
      <div v-if="runtime" class="gov-section mt-2">管道运行状态</div>
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
          暂无管道运行
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>AIP 控制台 · 运行追踪</span>
          <span class="ai-sub">Agent/AI 调用运行追踪 · 用途分布 · 人工审核队列</span>
        </div>
      </template>
      <el-row v-if="aip" :gutter="12" class="mb-2">
        <el-col :span="8"><el-statistic title="运行记录" :value="aip.total ?? 0" /></el-col>
        <el-col :span="8">
          <el-statistic title="人工审核待办" :value="aip.pending_review ?? 0" />
        </el-col>
        <el-col :span="8">
          <div style="display: flex; align-items: center; gap: 6px">
            <span class="ai-sub">用途分布</span>
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
      <el-table :data="aip?.runs || []" size="small" max-height="360">
        <el-table-column prop="time" label="时间" width="100" />
        <el-table-column prop="model" label="模型" min-width="130" show-overflow-tooltip />
        <el-table-column prop="usage" label="用途" width="110" />
        <el-table-column prop="latency_ms" label="耗时(ms)" width="90" />
        <el-table-column label="结果" width="90" align="center">
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
        <el-table-column label="Tokens" width="110" align="center">
          <template #default="{ row }">
            {{ row.prompt_tokens ?? 0 }} / {{ row.completion_tokens ?? 0 }}
          </template>
        </el-table-column>
        <el-table-column label="费用(元)" width="90" align="center">
          <template #default="{ row }">{{ row.cost ?? 0 }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>Agent 编排运行看板</span>
          <span class="ai-sub">运行量/错误率/延迟 + 绑定工具·技能·能力矩阵</span>
        </div>
      </template>
      <el-row v-if="agentDash" :gutter="12" class="mb-2">
        <el-col :span="8">
          <el-statistic title="智能体总数" :value="agentDash.total_agents ?? 0" />
        </el-col>
        <el-col :span="8">
          <el-statistic title="已启用" :value="agentDash.enabled_agents ?? 0" />
        </el-col>
        <el-col :span="8">
          <el-statistic title="累计运行" :value="agentDash.total_runs ?? 0" />
        </el-col>
      </el-row>
      <el-table :data="agentDash?.agents || []" size="small" max-height="300">
        <el-table-column prop="name" label="智能体" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="runs" label="运行" width="70" align="center" />
        <el-table-column label="错误率" width="90" align="center">
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
        <el-table-column prop="avg_latency" label="延迟(ms)" width="90" align="center" />
        <el-table-column label="编排矩阵" min-width="200">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" class="mr-1 mb-1">工具 {{ row.tools }}</el-tag>
            <el-tag size="small" type="warning" effect="plain" class="mr-1 mb-1">
              技能 {{ row.skills }}
            </el-tag>
            <el-tag size="small" type="info" effect="plain" class="mr-1 mb-1">
              知识 {{ row.knowledge }}
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
          <span>安全与合规姿态</span>
          <span class="ai-sub">敏感识别 / 权限覆盖 / 数据域 / 数据质量 / 审批积压 / 调用合规</span>
        </div>
      </template>
      <div v-if="posture" class="ov-usage-row" style="margin-bottom: 8px; gap: 12px">
        <span>综合评分</span>
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
            posture.level === "excellent" ? "优秀" : posture.level === "good" ? "良好" : "需关注"
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
      <div v-if="posture" class="gov-section mt-2">整改项</div>
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
          <span>多智能体协作编排</span>
          <span class="ai-sub">输入问题，按本体能力分解子任务并匹配合适智能体</span>
        </div>
      </template>
      <div class="compass-bar">
        <el-input
          v-model="orchInput"
          placeholder="如：今天有多少条告警？"
          clearable
          class="flex-1"
          @keyup.enter="runOrchestrate"
        />
        <el-button type="primary" :loading="orchLoading" @click="runOrchestrate">编排</el-button>
      </div>
      <template v-if="orchResult">
        <div class="gov-section mt-2">识别意图：{{ orchResult.intent }}</div>
        <el-steps :active="orchResult.steps.length" direction="vertical" style="margin-top: 4px">
          <el-step
            v-for="(s, i) in orchResult.steps"
            :key="i"
            :title="s.task"
            :description="`能力要求：${s.capability}`"
          />
        </el-steps>
        <div class="gov-section mt-2">可参与智能体（{{ orchResult.agents_involved.length }}）</div>
        <div>
          <el-tag v-if="!orchResult.agents_involved.length" size="small" type="info" effect="plain">
            未匹配到启用且具备能力属性的智能体
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
          <span>AIP Autopilot 自主行动</span>
          <span class="ai-sub">规则扫描治理/质量/安全/审批，生成候选自主行动</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="autoLoading" @click="loadAutopilot">重新扫描</el-button>
        <el-button size="small" type="danger" :loading="autoFixing" @click="runAutoFix">
          一键自动修复
        </el-button>
        <el-tag size="small" type="info" effect="plain">候选 {{ autopilot?.total ?? 0 }} 项</el-tag>
        <el-tag
          v-if="!autopilot?.actions?.length && !autoLoading"
          size="small"
          type="success"
          effect="plain"
        >
          暂无风险建议
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
            自动处理
          </el-button>
          <el-button v-else size="small" @click="runAutopilot('none', '')">查看</el-button>
        </div>
      </template>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>Ontology 派生指标</span>
          <span class="ai-sub">基于基础指标自动推导派生指标（分子/分母/除数规则引擎）</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="derivedLoading" @click="loadDerived">刷新</el-button>
      </div>
      <el-table :data="derived" size="small" border>
        <el-table-column prop="name" label="派生指标" min-width="120" />
        <el-table-column prop="formula" label="规则" min-width="180" show-overflow-tooltip />
        <el-table-column label="基础指标" min-width="160">
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
        <el-table-column label="计算值" width="110" align="center">
          <template #default="{ row }">
            <span v-if="derivedValues[row.key]?.ok">
              {{ derivedValues[row.key].value }} {{ row.unit }}
            </span>
            <span v-else class="ai-sub">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="computeDerived(row.key)">
              计算
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>数据安全与访问审计</span>
          <span class="ai-sub">敏感资产 · 数据源只读 · ABAC 规则 · 访问审计日志</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="securityLoading" @click="loadSecurity">刷新</el-button>
        <el-tag size="small" type="info" effect="plain">
          基础数据 {{ security?.assets ?? 0 }} 表 · 敏感字段 {{ security?.sensitive_fields ?? 0 }}
        </el-tag>
        <el-tag
          v-if="security"
          size="small"
          :type="security.score >= 80 ? 'success' : security.score >= 60 ? 'warning' : 'danger'"
          effect="plain"
        >
          安全评分 {{ security.score }}
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
        访问审计日志（近 {{ security.log_count }} 条）
      </div>
      <el-table
        v-if="security?.log_count"
        :data="security.action_logs"
        size="small"
        max-height="260"
      >
        <el-table-column prop="time" label="时间" width="120" />
        <el-table-column prop="action" label="动作" min-width="110" show-overflow-tooltip />
        <el-table-column prop="table" label="对象表" min-width="130" show-overflow-tooltip />
        <el-table-column label="结果" width="90" align="center">
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
        <el-table-column prop="operator" label="操作人" width="90" />
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>Ontology 派生对象</span>
          <span class="ai-sub">从启用对象的数据资产，按数据域聚类派生对象并汇总派生属性</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" :loading="derivedObjLoading" @click="loadDerivedObj">
          刷新
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          基础对象 {{ derivedObj?.base_objects ?? 0 }} · 派生 {{ derivedObj?.total_derived ?? 0 }}
        </el-tag>
      </div>
      <el-table :data="derivedObj?.derived_objects || []" size="small" border>
        <el-table-column prop="name" label="派生对象" min-width="120" />
        <el-table-column label="基础对象" min-width="180">
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
        <el-table-column prop="count" label="对象数" width="80" align="center" />
        <el-table-column label="派生属性" min-width="180">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain" class="mr-1 mb-1">
              列 {{ row.attributes?.total_columns ?? 0 }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain" class="mr-1 mb-1">
              敏感 {{ row.attributes?.sensitive_fields ?? 0 }}
            </el-tag>
            <el-tag size="small" type="success" effect="plain" class="mr-1 mb-1">
              血缘 {{ row.attributes?.lineage_count ?? 0 }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>Compass 收藏与 AIP 插件</span>
          <span class="ai-sub">个人收藏引用 · AIP 插件/工具市场</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">我的收藏（{{ favorites.length }}）</div>
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
              <el-button link type="danger" size="small" @click="removeFav(f.id)">移除</el-button>
            </div>
          </div>
          <div v-else class="gov-empty">暂无收藏，可在资产/对象/指标处收藏</div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">AIP 插件（{{ plugins.length }}）</div>
          <el-tag v-for="p in plugins" :key="p.key" size="small" effect="plain" class="mr-1 mb-1">
            {{ p.name }} · {{ p.kind }}
          </el-tag>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>AI 异常检测与决策中心</span>
          <span class="ai-sub">按日聚合对比基线识别异常 · 汇聚行动决策建议</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadAnomaly">重扫异常</el-button>
        <el-button size="small" type="primary" @click="loadDecision">刷新决策</el-button>
      </div>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">异常（{{ anomaly?.total ?? 0 }}）</div>
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
          <el-empty v-else-if="anomaly" :image-size="30" description="未见异常" />
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">决策建议（{{ decision?.total ?? 0 }}）</div>
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
                  <el-button size="small" type="primary" link @click="runDecision(d)">
                    执行
                  </el-button>
                </div>
              </div>
              <div class="decision-reason">{{ d.reason }}</div>
              <div class="decision-action">→ {{ d.action }}</div>
            </div>
          </div>
          <el-empty v-else-if="decision" :image-size="30" description="暂无待决策项" />
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>影响传播与数据质量规则</span>
          <span class="ai-sub">端到端影响传播（下游表/指标） · 数据质量规则引擎</span>
        </div>
      </template>
      <div class="compass-bar mb-2">
        <el-input
          v-model="propTable"
          placeholder="输入主表名，如 video_alarm_records"
          class="flex-1"
          @keyup.enter="runPropagate"
        />
        <el-button type="primary" :loading="propLoading" @click="runPropagate">影响传播</el-button>
        <el-button @click="loadDqRules">刷新规则</el-button>
      </div>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">受影响下游（{{ propResult?.affected_count ?? 0 }}）</div>
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
          <div v-if="propResult?.affected_metrics?.length" class="gov-section">受影响指标</div>
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
          <div class="gov-section">数据质量规则</div>
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
              校验
            </el-button>
          </div>
          <div v-if="dqRunResult" style="margin-top: 4px">
            <el-tag size="small" :type="dqRunResult.passed ? 'success' : 'danger'" effect="plain">
              {{ dqRunResult.rule }} · 通过率 {{ dqRunResult.pass_rate }}% ·
              {{ dqRunResult.valid }}/{{ dqRunResult.total }}
            </el-tag>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>我的数据分享</span>
          <span class="ai-sub">共享链接 · 一键复制 / 撤销</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadShares">刷新</el-button>
        <el-tag size="small" type="info" effect="plain">{{ shares.length }} 条分享</el-tag>
      </div>
      <el-table v-if="shares.length" :data="shares" size="small" border>
        <el-table-column prop="table" label="数据集" min-width="150" show-overflow-tooltip />
        <el-table-column prop="time" label="分享时间" width="150" />
        <el-table-column prop="token" label="Token" width="120" show-overflow-tooltip />
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="copyShare(row)">复制</el-button>
            <el-button link type="danger" size="small" @click="revokeShare(row.id)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-else class="gov-empty">暂无分享，可在数据资产表格「分享」生成链接</div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>统一活动时间线</span>
          <span class="ai-sub">AI 调用 / 动作 / 审批 统一时间线（近 7 天）</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadTimeline">刷新</el-button>
        <el-tag size="small" type="info" effect="plain">{{ timeline?.total ?? 0 }} 条事件</el-tag>
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
      <div v-else class="gov-empty">近 7 天暂无活动</div>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>Compass 目录 · 对象关系 · 访问演练</span>
          <span class="ai-sub">数据目录分类 / 对象关系图 / 数据访问沙箱</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="8">
          <div class="gov-section">Compass 目录分类（{{ catalog?.category_count ?? 0 }}）</div>
          <el-button size="small" class="mb-1" :loading="catalogLoading" @click="loadCatalog">
            刷新
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
            对象关系图（{{ objRel?.edge_count ?? 0 }} 边 / {{ objRel?.node_count ?? 0 }} 对象）
          </div>
          <el-button size="small" class="mb-1" :loading="objRelLoading" @click="loadObjRel">
            刷新
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
          <div v-else>暂无对象关系</div>
        </el-col>
        <el-col :sm="24" :md="8">
          <div class="gov-section">数据访问演练（用户 {{ walkthroughId }}）</div>
          <div class="compass-bar mb-1">
            <el-input-number v-model="walkthroughId" :min="0" size="small" style="width: 110px" />
            <el-button size="small" :loading="walkLoading" @click="loadWalkthrough">演练</el-button>
          </div>
          <div v-if="walkthrough" class="ov-usage-row mb-1">
            <el-tag size="small" type="success" effect="plain">
              可访问 {{ walkthrough.allowed_count }}
            </el-tag>
            <el-tag size="small" type="danger" effect="plain">
              受限 {{ walkthrough.blocked_count }}
            </el-tag>
            <el-tag size="small" type="info" effect="plain">
              敏感可见 {{ walkthrough.can_see_sensitive ? "是" : "否" }}
            </el-tag>
          </div>
          <div v-if="walkthrough?.allowed?.length" class="ai-sub ai-ellipsis">
            可访问：{{ walkthrough.allowed.map((x: any) => x.alias || x.table).join("、") }}
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>AIP 安全护栏</span>
          <span class="ai-sub">ABAC / 数据域 / 敏感剔除 / 审批 / 审计 / 版本 护栏状态</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button size="small" @click="loadGuardrails">刷新</el-button>
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
          <span>对象数据浏览器</span>
          <span class="ai-sub">真实表数据分页浏览（对象实例预览）</span>
        </div>
      </template>
      <div class="compass-bar mb-2">
        <el-input
          v-model="browseTable"
          placeholder="输入表名，如 video_alarm_records"
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
          浏览
        </el-button>
      </div>
      <template v-if="browse?.ok">
        <div class="ov-usage-row mb-1">
          <el-tag size="small" type="info" effect="plain">
            共 {{ browse.total }} 行 · 第 {{ browse.page }} 页
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
        <el-table :data="browse.rows" size="small" border max-height="320" class="w-full">
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
          <span>AIP 数据治理报告</span>
          <span class="ai-sub">一键聚合治理总览 / 合规 / 安全 / 护栏，生成并导出 Markdown</span>
        </div>
      </template>
      <div class="ov-usage-row mb-2">
        <el-button type="primary" :loading="reportLoading" @click="loadReport">生成报告</el-button>
        <el-button :disabled="!report" @click="downloadReport">导出 MD</el-button>
        <el-tag v-if="report" size="small" type="info" effect="plain">
          {{ report.generated_at }}
        </el-tag>
      </div>
      <template v-if="report">
        <el-row :gutter="12" class="mb-2">
          <el-col :span="8"><el-statistic title="合规" :value="report.scores.compliance" /></el-col>
          <el-col :span="8"><el-statistic title="安全" :value="report.scores.security" /></el-col>
          <el-col :span="8"><el-statistic title="护栏" :value="report.scores.guardrails" /></el-col>
        </el-row>
        <div class="gov-section">摘要</div>
        <div v-for="(s, i) in report.summary" :key="i" class="report-line">• {{ s }}</div>
      </template>
    </el-card>

    <el-card shadow="never" class="ov-recent-card mt-3">
      <template #header>
        <div class="ov-usage-row flex justify-between">
          <span>资产热点与对象生命周期</span>
          <span class="ai-sub">被指标引用排行 · 对象发布状态概览</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">数据资产热点（按指标引用）</div>
          <el-button size="small" class="mb-1" @click="loadHotspots">刷新</el-button>
          <div
            v-for="h in (hotspots?.hot || []).slice(0, 8)"
            :key="h.table"
            class="ov-usage-row"
            style="justify-content: space-between; margin-bottom: 3px"
          >
            <span class="ai-ellipsis">
              {{ h.alias || h.table }}
            </span>
            <el-tag size="small" type="info" effect="plain">引用 {{ h.refs }}</el-tag>
          </div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">对象生命周期</div>
          <el-button size="small" class="mb-1" @click="loadLifecycle">刷新</el-button>
          <div v-if="lifecycle" class="ov-usage-row" style="margin-bottom: 6px">
            <el-tag size="small" type="success" effect="plain">对象 {{ lifecycle.objects }}</el-tag>
            <el-tag size="small" type="primary" effect="plain">
              已发布 {{ lifecycle.published }}
            </el-tag>
            <el-tag size="small" type="warning" effect="plain">草稿 {{ lifecycle.draft }}</el-tag>
            <el-tag size="small" type="danger" effect="plain">
              敏感 {{ lifecycle.sensitive_objects }}
            </el-tag>
          </div>
          <div v-if="lifecycle" class="gov-section">对象列表</div>
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
          <span>AIP 评测基准与统一审计</span>
          <span class="ai-sub">制品化回归对比 · 跨模块全链路审计</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :sm="24" :md="12">
          <div class="gov-section">评测基准（制品化回归）</div>
          <div class="ov-usage-row mb-1">
            <el-button size="small" type="primary" @click="runBench">运行并固化</el-button>
            <el-button size="small" :loading="benchLoading" @click="loadBench">刷新</el-button>
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
                  · {{ b.total }} 例 · {{ b.time }}
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
          <div v-else class="gov-empty">暂无评测记录</div>
        </el-col>
        <el-col :sm="24" :md="12">
          <div class="gov-section">统一审计（近 {{ unified?.days ?? 7 }} 天）</div>
          <div v-if="unified" class="ov-usage-row" style="margin-bottom: 6px">
            <el-tag size="small" type="info" effect="plain">AI调用 {{ unified.ai_calls }}</el-tag>
            <el-tag size="small" type="danger" effect="plain">失败 {{ unified.ai_errors }}</el-tag>
            <el-tag size="small" type="success" effect="plain">动作 {{ unified.actions }}</el-tag>
            <el-tag size="small" type="warning" effect="plain">
              待审批 {{ unified.approvals }}
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
          <span>AI 能力评估（影子回归）</span>
          <span class="ai-sub">
            每行 {input, expected_keywords[], actual}，命中关键断言即通过，输出精度
          </span>
        </div>
      </template>
      <el-input
        v-model="evalSamplesText"
        type="textarea"
        :rows="5"
        placeholder='示例：[{"input":"订单金额总和","expected_keywords":["90500"],"actual":"订单金额总和是 90500"}]'
      />
      <div class="ops-bar mt-2">
        <el-button type="primary" size="small" :loading="evalLoading" @click="runEval">
          运行评估
        </el-button>
        <el-button size="small" @click="loadEvalTemplate">载入示例</el-button>
        <el-tag v-if="evalResult" size="small" type="info" effect="plain">
          精度 {{ (evalResult.precision * 100).toFixed(1) }}% · {{ evalResult.passed }}/{{
            evalResult.total
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
      >
        <el-table-column prop="input" label="输入" min-width="180" show-overflow-tooltip />
        <el-table-column label="通过" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ok ? 'success' : 'danger'" effect="plain">
              {{ row.ok ? "通过" : "未过" }}
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
              <span>AI 健康（近 {{ health?.days ?? 7 }} 天）</span>
              <el-button size="small" @click="loadHealth">刷新</el-button>
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
                health.status === "healthy" ? "健康" : health.status === "warning" ? "预警" : "严重"
              }}
            </el-tag>
            <div class="ov-usage-row mt-2">
              <span>调用</span>
              <b>{{ health.calls }}</b>
              <span>错误率</span>
              <b>{{ (health.error_rate * 100).toFixed(1) }}%</b>
              <span>平均延迟</span>
              <b>{{ health.avg_latency_ms }}ms</b>
              <span>成本</span>
              <b>{{ health.total_cost }}元</b>
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
            <el-empty v-if="!health.alerts.length" :image-size="30" description="无告警" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>
            <div class="ov-usage-row flex justify-between">
              <span>合规审计（近 {{ audit?.days ?? 7 }} 天）</span>
              <el-button size="small" @click="loadAudit">刷新</el-button>
            </div>
          </template>
          <div v-if="audit">
            <el-tag size="small" :type="audit.compliant ? 'success' : 'warning'" effect="plain">
              {{ audit.compliant ? "合规" : "存在风险" }}
            </el-tag>
            <div class="ov-usage-row mt-2">
              <span>调用</span>
              <b>{{ audit.total }}</b>
              <span>未鉴权</span>
              <b style="color: var(--el-color-danger)">{{ audit.anonymous_calls }}</b>
              <span>失败</span>
              <b style="color: var(--el-color-warning)">{{ audit.error_calls }}</b>
              <span>高成本</span>
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
            <el-empty v-if="!audit.issues.length" :image-size="30" description="无合规问题" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
const router = useRouter();
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

defineOptions({ name: "AiOverview" });

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
      ElMessage.success(r.data?.data?.msg || "已执行");
      loadDecision();
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "执行失败");
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
    ElMessage.info("该行动为人工处理项，请在对应模块处理");
    return;
  }
  autoExecuting.value = executable + table;
  try {
    const r = await autopilotExecute(executable, table);
    ElMessage.success(r.data?.data?.msg || "已执行");
    loadAutopilot();
  } catch (e: any) {
    ElMessage.error(e?.msg || "执行失败");
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
    ElMessage.error(e?.msg || "计算失败");
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
    await ElMessageBox.confirm(
      "将自动执行所有可修复项（敏感扫描/补全描述/DQ重扫），是否继续？",
      "AIP 自主修复",
      { type: "warning", confirmButtonText: "执行修复", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  autoFixing.value = true;
  try {
    const r = await autopilotAutoFix();
    autoFixed.value = r.data?.data || null;
    ElMessage.success(
      `修复完成：${autoFixed.value?.fixed ?? 0}/${autoFixed.value?.attempted ?? 0}`
    );
    loadAutopilot();
  } catch (e: any) {
    ElMessage.error(e?.msg || "自动修复失败");
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
    ElMessage.error(e?.msg || "移除失败");
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
    ElMessage.error(e?.msg || "规则校验失败");
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
    ElMessage.error(e?.msg || "撤销失败");
  }
}
async function copyShare(row: any) {
  const link = `${location.origin}${row.link || ""}`;
  try {
    await navigator.clipboard.writeText(link);
    ElMessage.success("已复制分享链接");
  } catch {
    ElMessageBox.alert(`分享链接：${link}`, "数据集分享", { confirmButtonText: "复制" });
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
  a.download = `治理报告_${report.value.generated_at?.replace(/[ :]/g, "-") || "now"}.md`;
  a.click();
  URL.revokeObjectURL(url);
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
      { input: "今天多少告警", expected_keywords: ["告警"], actual: "今日告警 100 条" },
    ];
    await runEvalBench(samples, "控制台基准");
    ElMessage.success("评测已固化");
    loadBench();
  } catch (e: any) {
    ElMessage.error(e?.msg || "评测失败");
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
    { input: "订单金额总和", expected_keywords: ["90500"], actual: "订单金额总和是 90500" },
    { input: "设备健康度", expected_keywords: ["%"], actual: "设备健康度为 95.5%" },
  ]);
}
async function runEval() {
  evalLoading.value = true;
  try {
    let samples: any[] = [];
    try {
      samples = JSON.parse(evalSamplesText.value || "[]");
    } catch {
      ElMessage.warning("样本 JSON 格式有误");
      return;
    }
    const r = await runAiEval(samples);
    evalResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.message || "评估失败");
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
  { key: "models", title: "模型配置", hint: "已接入大模型", route: "/ai/model", icon: Cpu },
  { key: "providers", title: "供应商", hint: "模型服务商", route: "/ai/provider", icon: Link },
  {
    key: "knowledge_bases",
    title: "知识库",
    hint: "RAG 知识库",
    route: "/ai/knowledge",
    icon: Collection,
  },
  { key: "apps", title: "组件", hint: "应用/智能体", route: "/ai/app", icon: MagicStick },
  { key: "workflows", title: "工作流", hint: "编排流程", route: "/ai/workflow", icon: SetUp },
  { key: "calls", title: "累计调用", hint: "全部 AI 调用", route: "/ai/logs", icon: Message },
  { key: "today_calls", title: "今日调用", hint: "今日次数", route: "/ai/logs", icon: Coin },
  { key: "success_rate", title: "成功率", hint: "调用成功率", route: "/ai/logs", icon: Files },
];

const entries = [
  { name: "知识库", desc: "RAG + 引用溯源 + 图谱", path: "/ai/knowledge", icon: Collection },
  { name: "组件", desc: "聊天/智能体/工作流/知识库", path: "/ai/app", icon: MagicStick },
  { name: "工作流", desc: "编排/调试/HITL", path: "/ai/workflow", icon: SetUp },
  { name: "模型配置", desc: "接入与管理大模型", path: "/ai/model", icon: Cpu },
  { name: "供应商", desc: "模型服务商管理", path: "/ai/provider", icon: Link },
  { name: "调用日志", desc: "统计/详情/导出", path: "/ai/logs", icon: Message },
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
    const t = stats.trend || [];
    trendChart.setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["调用", "失败"] },
      grid: { left: 40, right: 16, top: 30, bottom: 24 },
      xAxis: { type: "category", data: t.map((x: any) => x.date) },
      yAxis: { type: "value" },
      series: [
        {
          name: "调用",
          type: "bar",
          data: t.map((x: any) => x.count),
          itemStyle: { color: "#409eff" },
        },
        { name: "失败", type: "line", smooth: true, data: t.map((x: any) => x.error) },
      ],
    });
  }
  if (modelRef.value) {
    modelChart = modelChart || echarts.init(modelRef.value);
    const m = stats.by_model || [];
    modelChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 16, top: 30, bottom: 40 },
      xAxis: { type: "category", data: m.map((x: any) => x.name), axisLabel: { rotate: 20 } },
      yAxis: { type: "value" },
      series: [
        {
          name: "调用",
          type: "bar",
          data: m.map((x: any) => x.count),
          itemStyle: { color: "#67c23a" },
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
  padding: 12px;
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
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>
