<!-- AI 集成开放平台：应用管理 / 调用日志 / MCP 会话 / 接入文档 -->
<template>
  <div class="app-container ai-develop-page">
    <el-card shadow="never" class="develop-shell" :body-style="{ padding: '0 16px 12px' }">
      <el-tabs v-model="activeTab" class="develop-tabs" @tab-change="onTabChange">
        <!-- ============ 应用管理 ============ -->
        <el-tab-pane label="应用管理" name="apps">
          <el-form :inline="true" :model="appSearch" class="develop-search">
            <el-form-item label="关键字">
              <el-input
                v-model="appSearch.keyword"
                placeholder="名称 / appid"
                clearable
                style="width: 220px"
                @keyup.enter="loadApps()"
              />
            </el-form-item>
            <el-form-item>
              <el-button :icon="Search" @click="loadApps()">查询</el-button>
            </el-form-item>
          </el-form>

          <el-alert
            v-if="stats.apps.expiring?.length"
            type="warning"
            :closable="false"
            show-icon
            class="docs-alert"
            :title="`${
              stats.apps.expiring_soon
            } 个应用凭证将在 7 天内到期，请及时续期或关闭到期时间`"
            :description="
              stats.apps.expiring.map((a: any) => `${a.name}（${a.expire_at}）`).join('、') +
              (stats.apps.expiring_soon > stats.apps.expiring.length ? ' 等' : '')
            "
          />
          <div class="develop-toolbar">
            <div class="develop-toolbar__left">
              <span class="develop-toolbar__hint">
                为外部平台创建接入应用，分配能力权限点并下发凭证。
              </span>
              <el-tag size="small" type="info" effect="plain" class="summary-tag">
                共 {{ appTotal }} 个应用
              </el-tag>
            </div>
            <el-button
              v-hasPerm="['module_ai:develop:create']"
              type="primary"
              :icon="Plus"
              @click="openCreate"
            >
              新增应用
            </el-button>
          </div>

          <el-table v-loading="appLoading" :data="apps" row-key="id" border stripe>
            <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
            <el-table-column label="AppID" min-width="170">
              <template #default="{ row }">
                <div class="appid-cell">
                  <span class="appid-cell__value">{{ row.appid_masked || "—" }}</span>
                  <el-tooltip content="复制完整 AppID" placement="top">
                    <el-button text type="primary" size="small" @click="copyText(row.appid)">
                      <el-icon><CopyDocument /></el-icon>
                    </el-button>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-switch
                  v-hasPerm="['module_ai:develop:update']"
                  :model-value="row.enabled !== false"
                  @change="(v) => onToggle(row, Boolean(v))"
                />
              </template>
            </el-table-column>
            <el-table-column label="到期时间" width="150">
              <template #default="{ row }">
                <span :class="{ 'text-muted': !row.expire_at, 'text-warn': isExpiringSoon(row) }">
                  {{ fmtDateTime(row.expire_at) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="权限点" min-width="200">
              <template #default="{ row }">
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
              </template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="90" align="center" />
            <el-table-column label="操作" width="300" :fixed="fixedAction">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:develop:query']"
                  link
                  type="primary"
                  @click="openEmbed(row)"
                >
                  嵌入
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:query']"
                  link
                  type="primary"
                  @click="openTry(row)"
                >
                  试调
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:update']"
                  link
                  type="primary"
                  @click="openEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:reset']"
                  link
                  type="primary"
                  @click="openKeyDialog(row)"
                >
                  AppKey
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:delete']"
                  link
                  type="danger"
                  @click="onDelete(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" description="暂无应用，点击「新增应用」创建" />
            </template>
          </el-table>

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
        <el-tab-pane label="调用日志" name="logs">
          <el-row :gutter="12" class="stat-row">
            <el-col v-for="card in statCards" :key="card.label" :xs="12" :sm="6">
              <el-card shadow="never" class="stat-card">
                <div class="stat-card__label">{{ card.label }}</div>
                <div class="stat-card__value">
                  {{ card.value }}
                  <span class="stat-card__suffix">{{ card.suffix }}</span>
                </div>
              </el-card>
            </el-col>
          </el-row>
          <div v-if="stats.series.length" class="spark-row">
            <span class="spark-row__label">最近 7 天</span>
            <div
              v-for="day in stats.series"
              :key="day.date"
              class="spark"
              :title="`${day.date}：${day.calls} 次`"
            >
              <div class="spark__bar" :style="{ height: sparkHeight(day.calls) }" />
              <span class="spark__label">{{ day.date.slice(5) }}</span>
            </div>
            <div v-if="stats.top_capabilities.length" class="spark-row__top">
              <span class="spark-row__label">Top 能力</span>
              <el-tag
                v-for="item in stats.top_capabilities"
                :key="item.capability + item.category"
                size="small"
                effect="plain"
                class="cap-tag"
              >
                {{ item.capability }} · {{ item.calls }}
              </el-tag>
            </div>
          </div>
          <el-form :inline="true" :model="logFilter" class="develop-search">
            <el-form-item label="应用">
              <el-select
                v-model="logFilter.app_id"
                placeholder="全部"
                clearable
                filterable
                style="width: 180px"
              >
                <el-option v-for="a in appOptions" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="品类">
              <el-select
                v-model="logFilter.category"
                placeholder="全部"
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
            <el-form-item label="出海口">
              <el-select
                v-model="logFilter.method"
                placeholder="全部"
                clearable
                style="width: 140px"
              >
                <el-option label="REST" value="REST" />
                <el-option label="MCP" value="MCP" />
                <el-option label="EMBED" value="EMBED" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select
                v-model="logFilter.status"
                placeholder="全部"
                clearable
                style="width: 140px"
              >
                <el-option label="成功" value="success" />
                <el-option label="失败" value="failed" />
                <el-option label="拒绝" value="denied" />
              </el-select>
            </el-form-item>
            <el-form-item label="时间范围">
              <el-date-picker
                v-model="logFilter.range"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 340px"
              />
            </el-form-item>
            <el-form-item>
              <el-button :icon="Search" @click="loadLogs()">查询</el-button>
              <el-button :icon="Download" @click="onExportLogs">导出 CSV</el-button>
            </el-form-item>
          </el-form>

          <el-table
            v-loading="logLoading"
            :data="logs"
            row-key="id"
            border
            stripe
            class="log-table"
            @row-click="openLogDetail"
          >
            <el-table-column label="时间" width="165" show-overflow-tooltip>
              <template #default="{ row }">{{ fmtDateTime(row.created_time) }}</template>
            </el-table-column>
            <el-table-column label="AppID" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.appid || "—" }}</template>
            </el-table-column>
            <el-table-column label="品类" width="85">
              <template #default="{ row }">
                {{ CATEGORIES[row.category || ""] || row.category }}
              </template>
            </el-table-column>
            <el-table-column prop="capability" label="能力" min-width="145" show-overflow-tooltip />
            <el-table-column label="出海口" width="90">
              <template #default="{ row }">{{ methodLabel(row.method) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="logStatusType(row.status)">
                  {{ statusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="latency_ms" label="耗时(ms)" width="85" align="right" />
            <el-table-column prop="cost_tokens" label="Tokens" width="78" align="right" />
            <el-table-column
              prop="request_path"
              label="请求路径"
              min-width="145"
              show-overflow-tooltip
            />
            <el-table-column
              prop="result_summary"
              label="结果摘要"
              min-width="145"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" description="暂无调用日志" />
            </template>
          </el-table>

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
        <el-tab-pane label="MCP 会话" name="mcp">
          <el-form :inline="true" :model="mcpFilter" class="develop-search">
            <el-form-item label="应用">
              <el-select
                v-model="mcpFilter.app_id"
                placeholder="全部"
                clearable
                filterable
                style="width: 180px"
              >
                <el-option v-for="a in appOptions" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button :icon="Search" @click="loadMcps()">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="mcpLoading" :data="mcps" row-key="id" border stripe>
            <el-table-column label="AppID" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.appid || "—" }}</template>
            </el-table-column>
            <el-table-column label="会话ID" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono-text">{{ row.session_id || "—" }}</span>
              </template>
            </el-table-column>
            <el-table-column label="传输" width="100">
              <template #default="{ row }">{{ transportLabel(row.transport) }}</template>
            </el-table-column>
            <el-table-column
              prop="client_info"
              label="客户端"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column label="开始时间" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="结束时间" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.ended_at, "—") }}</template>
            </el-table-column>
            <el-table-column prop="duration_s" label="时长(s)" width="80" align="right" />
            <el-table-column prop="tool_calls" label="工具调用" width="85" align="right" />
            <el-table-column
              prop="close_reason"
              label="关闭原因"
              min-width="120"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" description="暂无 MCP 会话" />
            </template>
          </el-table>

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

        <!-- ============ 调用审批 ============ -->
        <el-tab-pane label="调用审批" name="approvals">
          <el-form :inline="true" :model="approvalFilter" class="develop-search">
            <el-form-item label="状态">
              <el-select
                v-model="approvalFilter.status"
                placeholder="全部"
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
              <el-button :icon="Search" @click="loadApprovals(true)">查询</el-button>
            </el-form-item>
          </el-form>

          <div class="develop-toolbar">
            <div class="develop-toolbar__left">
              <span class="develop-toolbar__hint">
                应用开启「需人工审批」后，删除智能体、训练任务创建/启停等敏感调用会先进入这里；
                批准后立即以原应用身份执行，超过 24 小时未处理由系统自动关闭为「已过期」。
                产生待审批时会给管理员发站内通知；如需外发，配置
                APPROVAL_NOTIFY_CHANNELS（email/webhook/sms）并配系统参数
                ai_approval_notify_{channel}（JSON）。
              </span>
              <el-tag size="small" type="warning" effect="plain" class="summary-tag">
                待审批 {{ approvalPendingCount }} 条
              </el-tag>
            </div>
          </div>

          <el-table v-loading="approvalLoading" :data="approvals" row-key="id" border stripe>
            <el-table-column label="申请时间" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.created_time) }}</template>
            </el-table-column>
            <el-table-column prop="appid" label="AppID" width="130" show-overflow-tooltip />
            <el-table-column prop="capability" label="能力" min-width="150" show-overflow-tooltip />
            <el-table-column label="品类" width="95">
              <template #default="{ row }">
                {{ CATEGORIES[row.category] || row.category }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="approvalStatusType(row.status)">
                  {{ APPROVAL_STATUS[row.status] || row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="审批时间" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.reviewed_at, "—") }}</template>
            </el-table-column>
            <el-table-column
              prop="review_note"
              label="审批意见"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column label="操作" width="190" :fixed="fixedAction">
              <template #default="{ row }">
                <el-button link type="primary" @click="openApprovalDetail(row)">详情</el-button>
                <template v-if="row.status === 'pending'">
                  <el-button
                    v-hasPerm="'module_ai:develop:approve'"
                    link
                    type="primary"
                    @click="onReviewApproval(row, true)"
                  >
                    批准
                  </el-button>
                  <el-button
                    v-hasPerm="'module_ai:develop:approve'"
                    link
                    type="danger"
                    @click="onReviewApproval(row, false)"
                  >
                    拒绝
                  </el-button>
                </template>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" description="暂无调用审批" />
            </template>
          </el-table>

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
        <el-tab-pane label="接入文档" name="docs">
          <div class="docs-wrap">
            <el-alert
              title="接入凭证说明"
              type="info"
              :closable="false"
              show-icon
              class="docs-alert"
              description="AppID / AppKey 仅用于服务端调用：开放 REST 与 MCP 直接带 Authorization: Bearer {appid}:{appkey}；网页嵌入则由宿主服务端调 POST /api/v1/ai/develop-api/auth/token 换取短期 access_token，浏览器只持票。切勿把 AppKey 写入网页或嵌入代码；AppKey 仅在创建或重置时展示一次。"
            />
            <el-alert
              title="审批与配额"
              type="warning"
              :closable="false"
              show-icon
              class="docs-alert"
              description="应用开启「需人工审批」后，敏感能力（删除智能体、训练任务创建/启停）会先进入「调用审批」页签，管理员批准后才执行；「按日调用配额」按品类限制自然日调用次数（0/空 = 不限），超限返回 429。"
            />
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>REST 接入</span>
                  <el-tag size="small">HTTP</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                服务端持
                <code>appid:appkey</code>
                调用：能力清单、能力调用（统一入口
                <code>/capabilities/{code}</code>
                ）、对话与网页嵌入换票。响应统一为
                <code>{ code, msg, data }</code>
                。
              </p>
              <pre class="doc-code">{{ restExample }}</pre>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>MCP 接入</span>
                  <el-tag size="small" type="success">Streamable HTTP</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                平台同时是 MCP Server：工具即能力，
                <code>tools/list</code>
                只返回该应用已授权的能力，调用与 REST 共用同一套鉴权、限流与审计。
              </p>
              <pre class="doc-code">{{ mcpExample }}</pre>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>开放能力清单</span>
                  <el-tag size="small" type="info">共 {{ capabilities.length }} 项</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                能力与权限点一一对应：应用只有被授予对应权限点，才会在能力清单与 MCP
                工具列表里看到它。
              </p>
              <el-table v-loading="capLoading" :data="capabilities" border stripe>
                <el-table-column prop="name" label="能力" min-width="130" show-overflow-tooltip />
                <el-table-column prop="code" label="能力码" width="130" />
                <el-table-column label="品类" width="100">
                  <template #default="{ row }">
                    {{ CATEGORIES[row.category] || row.category }}
                  </template>
                </el-table-column>
                <el-table-column prop="perm" label="所需权限点" width="200" />
                <el-table-column prop="mcp_tool" label="MCP 工具名" width="140">
                  <template #default="{ row }">
                    <span v-if="row.mcp_tool" class="mono-text">{{ row.mcp_tool }}</span>
                    <span v-else class="text-muted">—</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="description"
                  label="说明"
                  min-width="240"
                  show-overflow-tooltip
                />
                <template #empty>
                  <el-empty :image-size="80" description="暂无开放能力" />
                </template>
              </el-table>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>网页嵌入</span>
                  <el-tag size="small">Embed</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                两种嵌入形态（iframe 直嵌 / Script SDK）。token
                由服务端换票下发；过期时宿主重新换票并调用
                <code>setToken()</code>
                续期，对话不中断。
              </p>
              <pre class="doc-code">{{ embedExample }}</pre>
              <div class="doc-events">
                <span class="doc-events__label">postMessage 事件</span>
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
              <p class="doc-card__desc doc-card__desc--foot">
                完整契约见「应用管理 → 嵌入」弹窗与下方示例注释；上行信封
                <code>{ source: "ai-embed", version: 1, event, payload }</code>
                。
              </p>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ============ 调用日志详情抽屉 ============ -->
    <el-drawer v-model="logDetail.visible" title="调用详情" size="520px" append-to-body>
      <el-descriptions v-if="logDetail.row" :column="1" border size="small">
        <el-descriptions-item label="时间">
          {{ fmtDateTime(logDetail.row.created_time) }}
        </el-descriptions-item>
        <el-descriptions-item label="应用">
          {{ logDetail.row.appid }}（ID {{ logDetail.row.app_id }}）
        </el-descriptions-item>
        <el-descriptions-item label="能力">
          {{ logDetail.row.capability }}
          <el-tag size="small" effect="plain" class="cap-tag">
            {{ CATEGORIES[logDetail.row.category || ""] || logDetail.row.category }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="出海口 / 状态">
          {{ methodLabel(logDetail.row.method) }} ·
          <el-tag size="small" :type="logStatusType(logDetail.row.status)">
            {{ statusLabel(logDetail.row.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="耗时 / Tokens">
          {{ logDetail.row.latency_ms }} ms · {{ logDetail.row.cost_tokens }}
        </el-descriptions-item>
        <el-descriptions-item label="请求路径">
          {{ logDetail.row.request_path || "—" }}
        </el-descriptions-item>
        <el-descriptions-item v-if="logDetail.row.error" label="错误">
          <span class="text-danger">{{ logDetail.row.error }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <template v-if="logDetail.row">
        <p class="doc-card__desc">请求参数（已脱敏）</p>
        <pre class="doc-code">{{ prettyJson(logDetail.row.request_body) }}</pre>
        <p class="doc-card__desc">结果摘要</p>
        <pre class="doc-code">{{ logDetail.row.result_summary || "—" }}</pre>
      </template>
    </el-drawer>

    <!-- ============ 能力试调弹窗 ============ -->
    <el-dialog v-model="tryDialog.visible" title="能力试调" width="640px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="docs-alert"
        title="以该应用身份调用一次能力：跳过审批门禁，但仍校验权限并写入调用日志，便于接入前自测。"
      />
      <el-form label-width="90px" class="try-form">
        <el-form-item label="能力">
          <el-select
            v-model="tryDialog.capability"
            placeholder="选择能力"
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
        <el-form-item label="参数 JSON">
          <el-input
            v-model="tryDialog.payloadText"
            type="textarea"
            :rows="8"
            spellcheck="false"
            placeholder='例如 {"agent_name": "试调助手"}'
          />
        </el-form-item>
      </el-form>
      <template v-if="tryDialog.resultText">
        <p class="doc-card__desc">响应</p>
        <pre class="doc-code">{{ tryDialog.resultText }}</pre>
      </template>
      <template #footer>
        <el-button @click="tryDialog.visible = false">关闭</el-button>
        <el-button type="primary" :loading="tryDialog.loading" @click="submitTry">发送</el-button>
      </template>
    </el-dialog>

    <!-- ============ 审批详情弹窗 ============ -->
    <el-dialog v-model="approvalDetail.visible" title="调用审批详情" width="600px" append-to-body>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="能力">
          {{ approvalDetail.row?.capability }}
          <el-tag size="small" effect="plain" class="cap-tag">
            {{ CATEGORIES[approvalDetail.row?.category || ""] || approvalDetail.row?.category }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="应用">{{ approvalDetail.row?.appid }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="approvalStatusType(approvalDetail.row?.status)">
            {{ APPROVAL_STATUS[approvalDetail.row?.status || ""] || approvalDetail.row?.status }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="申请时间">
          {{ fmtDateTime(approvalDetail.row?.created_time) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="approvalDetail.row?.reviewed_at" label="审批时间">
          {{ fmtDateTime(approvalDetail.row?.reviewed_at) }}
        </el-descriptions-item>
        <el-descriptions-item v-if="approvalDetail.row?.review_note" label="审批意见">
          {{ approvalDetail.row?.review_note }}
        </el-descriptions-item>
      </el-descriptions>
      <p class="doc-card__desc">请求参数</p>
      <pre class="doc-code">{{ prettyJson(approvalDetail.row?.payload) }}</pre>
      <template v-if="approvalDetail.row?.result">
        <p class="doc-card__desc">执行结果</p>
        <pre class="doc-code">{{ prettyJson(approvalDetail.row?.result) }}</pre>
      </template>
      <el-alert
        v-if="approvalDetail.row?.error"
        type="error"
        :closable="false"
        show-icon
        :title="`执行失败：${approvalDetail.row?.error}`"
      />
      <template #footer>
        <el-button @click="approvalDetail.visible = false">关闭</el-button>
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
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：合作伙伴平台接入" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="可选" />
        </el-form-item>
        <el-form-item label="授权能力">
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
        <el-form-item label="凭证过期时间">
          <el-date-picker
            v-model="form.expire_at"
            type="datetime"
            placeholder="留空表示永久有效"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="需人工审批">
          <el-switch v-model="form.requires_approval" />
          <span class="form-tip">
            开启后，删除智能体、训练任务创建/启停等敏感调用先进入「调用审批」页签，批准后才执行。
          </span>
        </el-form-item>
        <el-form-item label="按日调用配额">
          <div class="quota-grid">
            <div v-for="(label, cat) in QUOTA_CATEGORIES" :key="cat" class="quota-item">
              <span class="quota-item__label">{{ label }}</span>
              <el-input-number
                v-model="form.quota[cat]"
                :min="0"
                :max="1000000"
                :step="100"
                controls-position="right"
                placeholder="不限"
                style="width: 110px"
              />
              <span class="quota-item__usage">今日 {{ form.usage[cat] ?? 0 }}</span>
            </div>
          </div>
          <span class="form-tip">0 或留空表示不限；按自然日统计（对应品类的开放调用）。</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- ============ AppKey 查看 / 重置弹窗 ============ -->
    <el-dialog
      v-model="keyDialog.visible"
      :title="`AppKey · ${keyDialog.name || ''}`"
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
            AppKey 已加密存储，仅在创建或重置时显示一次，请先点击「重置 AppKey」获取。
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="keyDialog.visible = false">关闭</el-button>
        <el-button
          v-hasPerm="['module_ai:develop:reset']"
          type="primary"
          :loading="keyLoading"
          @click="onResetKey(keyDialog.row)"
        >
          重置 AppKey
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 创建成功：一次性展示 AppKey ============ -->
    <el-dialog
      v-model="reveal.visible"
      title="创建成功"
      width="520px"
      append-to-body
      :close-on-click-modal="false"
      @close="closeReveal"
    >
      <el-alert
        title="请立即保存 AppKey"
        type="warning"
        :closable="false"
        show-icon
        class="docs-alert"
        description="AppKey 仅在此处显示一次，关闭后将无法再次查看，请及时复制并妥善保存。"
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
        <el-button type="primary" @click="reveal.visible = false">我已保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 嵌入管理弹窗 ============ -->
    <EmbedDialog v-model="embedVisible" :app="embedRow" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search, CopyDocument, Download } from "@element-plus/icons-vue";
import { useWindowSize } from "@vueuse/core";
import {
  createApp,
  deleteApp,
  exportCallLogs,
  getAppUsage,
  getApprovals,
  getCallLogs,
  getCapabilities,
  getDevelopAppList,
  getDevelopStats,
  getMcpSessions,
  resetAppkey,
  reviewApproval,
  toggleApp,
  tryCapability,
  updateApp,
} from "@/api/module_ai/develop";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import EmbedDialog from "./components/EmbedDialog.vue";

defineOptions({ name: "AiDevelopManage" });

//: 窄屏（<1280）不把操作列固定在右侧——否则会盖住相邻列的内容（1024 下状态标签被切）。
const { width: viewportWidth } = useWindowSize();
const fixedAction = computed<"right" | undefined>(() =>
  viewportWidth.value >= 1280 ? "right" : undefined
);

// ---- 能力品类目录（与后端 capabilities.py 保持一致） ----
const CATEGORIES: Record<string, string> = {
  train: "模型训练",
  agent: "智能体",
  chat: "对话",
  bot: "机器人",
  embed: "网页嵌入",
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
    ElMessage.error(e?.msg || "加载失败");
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
  agent: "智能体",
  chat: "对话",
  train: "模型训练",
  bot: "机器人",
  embed: "网页嵌入",
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
  dialog.title = "新增应用";
  dialog.visible = true;
}

function openEdit(row: any) {
  resetForm();
  isEdit.value = true;
  dialog.title = `编辑应用：${row.name}`;
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
    ElMessage.warning("请填写应用名称");
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
      ElMessage.success("保存成功");
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
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

// ---- 启用 / 停用：局部刷新，只更新对应行 ----
async function onToggle(row: any, enabled: boolean) {
  try {
    await toggleApp(row.id, enabled);
    row.enabled = enabled;
    ElMessage.success(enabled ? "已启用" : "已停用");
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  }
}

// ---- 删除：二次确认 ----
async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认删除应用「${row.name}」？删除后其 AppID/AppKey 立即失效，历史调用日志与 MCP 会话将无法关联该应用，且不可恢复。`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await deleteApp([row.id]);
    await loadApps(false);
    ElMessage.success("删除成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
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
      `重置后应用「${row.name}」的原 AppKey 将立即失效，所有已下发的调用凭证都需更换，且不可恢复。是否继续？`,
      "重置 AppKey",
      { type: "warning", confirmButtonText: "重置", cancelButtonText: "取消" }
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
    ElMessage.success("AppKey 已重置");
  } catch (e: any) {
    ElMessage.error(e?.msg || "重置失败");
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
  { label: "今日调用", value: stats.today.calls ?? 0, suffix: " 次" },
  { label: "成功率", value: ((stats.today.success_rate ?? 0) * 100).toFixed(1), suffix: "%" },
  { label: "平均耗时", value: stats.today.avg_latency_ms ?? 0, suffix: " ms" },
  { label: "待审批", value: stats.approvals.pending ?? 0, suffix: " 条" },
]);

const sparkMax = computed(() => Math.max(1, ...stats.series.map((d: any) => Number(d.calls) || 0)));

function sparkHeight(calls: number) {
  return `${Math.max(2, Math.round(((Number(calls) || 0) / sparkMax.value) * 36))}px`;
}

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
    };
    const res = await exportCallLogs(params);
    const blob = res.data instanceof Blob ? res.data : new Blob([res.data]);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ai-call-logs-${Date.now()}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    ElMessage.success("已开始下载");
  } catch (e: any) {
    ElMessage.error(e?.msg || "导出失败");
  }
}

// ---- 能力试调 ----
const tryDialog = reactive({
  visible: false,
  app: null as any,
  capability: "",
  payloadText: "{}",
  resultText: "",
  loading: false,
});

async function openTry(row: any) {
  if (!capabilities.value.length) await loadCapabilities();
  tryDialog.app = row;
  tryDialog.capability = "";
  tryDialog.payloadText = "{}";
  tryDialog.resultText = "";
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
    ElMessage.warning("请选择能力");
    return;
  }
  let payload: any;
  try {
    payload = tryDialog.payloadText.trim() ? JSON.parse(tryDialog.payloadText) : {};
  } catch {
    ElMessage.error("参数不是合法 JSON");
    return;
  }
  tryDialog.loading = true;
  tryDialog.resultText = "";
  try {
    const res = await tryCapability(tryDialog.app.id, {
      capability: tryDialog.capability,
      payload,
    });
    tryDialog.resultText = prettyJson(res.data?.data ?? res.data);
    ElMessage.success("调用成功");
    await loadLogs(false);
    await loadStats();
  } catch (e: any) {
    const code = e?.code ? `[${e.code}] ` : "";
    tryDialog.resultText = `错误 ${code}${e?.msg || "调用失败"}`;
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
      start_time: logFilter.range?.[0] || undefined,
      end_time: logFilter.range?.[1] || undefined,
      page_no: logPage.value,
      page_size: logPageSize.value,
    });
    const d = res.data?.data || {};
    logs.value = d.items || [];
    logTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
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
const METHOD_LABELS: Record<string, string> = { REST: "REST", MCP: "MCP", EMBED: "网页嵌入" };
const STATUS_LABELS: Record<string, string> = {
  success: "成功",
  failed: "失败",
  error: "异常",
  denied: "拒绝",
  pending: "待审批",
  approved: "已批准",
  rejected: "已拒绝",
};
const TRANSPORT_LABELS: Record<string, string> = {
  "streamable-http": "流式 HTTP",
  stdio: "本地进程",
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
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    mcpLoading.value = false;
  }
}

// ---- 调用审批（敏感能力「先审批后执行」） ----
const APPROVAL_STATUS: Record<string, string> = {
  pending: "待审批",
  approved: "已批准",
  rejected: "已拒绝",
  expired: "已过期",
  failed: "执行失败",
};

const approvals = ref<any[]>([]);
const approvalTotal = ref(0);
const approvalPendingCount = ref(0);
const approvalPage = ref(1);
const approvalPageSize = ref(10);
const approvalLoading = ref(false);
const approvalFilter = reactive({ status: undefined as string | undefined });
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
    ElMessage.error(e?.msg || "审批列表加载失败");
  } finally {
    approvalLoading.value = false;
  }
}

function openApprovalDetail(row: any) {
  approvalDetail.row = row;
  approvalDetail.visible = true;
}

async function onReviewApproval(row: any, approve: boolean) {
  const action = approve ? "批准并立即执行" : "拒绝";
  try {
    await ElMessageBox.confirm(
      approve
        ? `将批准该「${row.capability}」调用，并**立即以 ${row.appid} 身份执行**（可能产生真实资源变更）。`
        : `将拒绝该「${row.capability}」调用，申请方不会得到执行结果。`,
      `确认${action}？`,
      { type: approve ? "warning" : "info", confirmButtonText: action, cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    const res = await reviewApproval(row.id, { approve });
    ElMessage.success(res.data?.msg || "已处理");
    await loadApprovals(false);
  } catch (e: any) {
    ElMessage.error(e?.msg || "处理失败");
  }
}

function onTabChange(name: string | number) {
  const key = String(name);
  if (key === "logs") {
    loadLogs(false);
    loadStats();
  } else if (key === "mcp") loadMcps(false);
  else if (key === "approvals") loadApprovals(false);
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
    ElMessage.error(e?.msg || "能力清单加载失败");
  } finally {
    capLoading.value = false;
  }
}

// ---- 通用工具 ----
function fmtDateTime(v?: string | null, emptyText = "永久"): string {
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
    ElMessage.success("已复制");
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
      ElMessage.success("已复制");
    } catch {
      ElMessage.error("复制失败，请手动复制");
    } finally {
      document.body.removeChild(ta);
    }
  }
}

// ---- 接入文档示例（纯文本，避免模板解析脚本标签） ----
const restExample = `# 1. 凭证校验：确认应用状态与已授权能力
curl -X GET "https://<host>/api/v1/ai/develop-api/auth/verify" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 2. 能力清单：只返回本应用**已授权**的能力
curl -X GET "https://<host>/api/v1/ai/develop-api/capabilities" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 3. 调用能力（统一入口）：code 取自能力清单，body 固定为 {"payload": {...}}
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/agent.create" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"agent_name": "外部创建助手"}}'

# 4. 对话（聚合回复，非流式）
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/chat.send" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"kind": "workflow", "target_id": 12, "message": "你好"}}'

# 5. 网页嵌入换票（浏览器面不接触 appkey）
curl -X POST "https://<host>/api/v1/ai/develop-api/auth/token" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"kind": "agent", "target_id": 123}'`;

const mcpExample = `// 端点（Streamable HTTP）：https://<host>/api/v1/ai/develop-api/mcp
// 鉴权：请求头 Authorization: Bearer {appid}:{appkey}（与 REST 同一套凭证）

// 方式一：客户端原生支持自定义请求头（推荐）
{
  "mcpServers": {
    "aistation": {
      "type": "http",
      "url": "https://<host>/api/v1/ai/develop-api/mcp",
      "headers": { "Authorization": "Bearer {appid}:{appkey}" }
    }
  }
}

// 方式二：客户端只支持 stdio（用 mcp-remote 代理转发请求头）
{
  "mcpServers": {
    "aistation": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://<host>/api/v1/ai/develop-api/mcp",
        "--header", "Authorization: Bearer {appid}:{appkey}"
      ]
    }
  }
}

// 工具 = 能力：tools/list 只返回该应用已授权的能力；每次调用都写审计。`;

const embedExample =
  `<!-- 方式一：iframe 直嵌（token 由服务端换票注入） -->
<iframe src="https://<host>/web/#/embed?token={access_token}"
        width="420" height="620" style="border:0;border-radius:12px"></iframe>

<!-- 方式二：Script SDK（推荐：事件回调 + 续期） -->
<script src="https://<host>/api/v1/ai/embed/sdk.js"></scr` +
  `ipt>
<div id="ai-assistant" style="width:420px;height:620px"></div>
<script>
  const ai = AiAssistant.init({
    container: "#ai-assistant",
    token: "{access_token}",
    apiBase: "https://<host>/api/v1/ai",
    webBase: "https://<host>/web",
    theme: { primary: "#409eff" }
  });
  ai.on("token_expired", async () => {
    ai.setToken(await fetchTokenFromYourBackend());  // 服务端重新换票
  });
</scr` +
  `ipt>`;

/** postMessage 事件契约（完整载荷见「嵌入」弹窗）。 */
const docEvents = [
  { name: "ready", desc: "初始化完成" },
  { name: "user_message", desc: "用户消息" },
  { name: "reply_start", desc: "开始回复" },
  { name: "reply_delta", desc: "流式增量" },
  { name: "reply_done", desc: "回复完成" },
  { name: "error", desc: "错误（网络/限流）" },
  { name: "token_expired", desc: "凭证过期" },
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
});
</script>

<style scoped>
.develop-search {
  margin-bottom: 4px;
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
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-secondary);
}

.summary-tag {
  flex-shrink: 0;
}

.develop-pagination {
  display: flex;
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
.stat-row {
  margin-bottom: 8px;
}

.stat-card {
  border: 1px solid var(--el-border-color-lighter);
}

.stat-card :deep(.el-card__body) {
  padding: 10px 12px;
}

.stat-card__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.stat-card__value {
  margin-top: 2px;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--el-text-color-primary);
}

.stat-card__suffix {
  margin-left: 2px;
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.spark-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-end;
  margin-bottom: 10px;
}

.spark-row__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.spark {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  width: 34px;
}

.spark__bar {
  width: 12px;
  background: var(--el-color-primary-light-5);
  border-radius: 2px;
}

.spark__label {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.spark-row__top {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-left: 8px;
}

.log-table :deep(.el-table__row) {
  cursor: pointer;
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
  padding: 12px;
  overflow: hidden;
}

.ai-develop-page .develop-shell {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
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
