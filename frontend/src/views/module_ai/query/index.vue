<!-- 智能问数：会话式问答 + 快/慢路径结果 + 指标/术语/数据源运营 -->
<template>
  <div class="app-container ai-query-page">
    <div class="query-layout">
      <!-- 左侧：会话 / 数据源 -->
      <div class="query-side">
        <div class="query-side__hd">
          <el-button type="primary" size="small" :icon="Plus" @click="newSession">新会话</el-button>
          <el-button size="small" :icon="Setting" @click="openOps">指标运营</el-button>
          <el-button size="small" :icon="DataBoard" @click="openGovDashboard">治理驾驶舱</el-button>
        </div>
        <div class="query-ds">
          <span class="query-ds__label">数据源</span>
          <el-select v-model="datasource" size="small" style="width: 100%" @change="onDsChange">
            <el-option label="本系统数据" value="system" />
            <el-option v-for="d in datasources" :key="d.id" :label="d.name" :value="`ds:${d.id}`" />
            <el-option label="＋ 管理数据源" value="__manage__" />
          </el-select>
        </div>
        <div class="session-list">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === currentSession }"
            @click="openSession(s.id)"
          >
            <span class="session-item__title">{{ s.title }}</span>
            <el-icon class="session-item__del" @click.stop="removeSession(s.id)">
              <Delete />
            </el-icon>
          </div>
          <el-empty v-if="!sessions.length" :image-size="50" description="暂无会话" />
        </div>
      </div>

      <!-- 主区域 -->
      <div class="query-main">
        <div ref="chatRef" class="query-chat">
          <div v-for="m in messages" :key="m.id" class="msg-row">
            <div class="msg-q">{{ m.question }}</div>
            <div class="msg-a">
              <div class="msg-a__head">
                <el-tag
                  :type="m.is_error ? 'danger' : m.path === 'fast' ? 'success' : 'warning'"
                  size="small"
                >
                  {{ m.is_error ? "失败" : m.path === "fast" ? "精准命中" : "智能生成" }}
                </el-tag>
                <span v-if="m.took_ms" class="msg-a__time">{{ m.took_ms }} ms</span>
                <el-tooltip v-if="m.confidence != null" :content="`置信度 ${(m.confidence*100).toFixed(0)}% · 依据：${m.evidence?.source || ''}`">
                  <el-tag size="small" :type="m.confidence >= 0.9 ? 'success' : m.confidence >= 0.7 ? 'warning' : 'info'" effect="plain">
                    置信度 {{ (m.confidence * 100).toFixed(0) }}%
                  </el-tag>
                </el-tooltip>
                <span v-if="m.sql" class="msg-a__sql" @click="toggleSql(m)">
                  {{ m._showSql ? "收起 SQL" : "查看 SQL" }}
                </span>
                <span
                  v-if="m.path === 'slow' && !m.is_error"
                  class="msg-a__fb"
                  @click="feedback(m, 'up')"
                >
                  赞
                </span>
                <span class="msg-a__fb" @click="feedback(m, 'down')">踩</span>
                <span
                  v-if="m.columns?.length && (m.rows || []).length"
                  class="msg-a__export"
                  @click="exportCsv(m)"
                >
                  导出CSV
                </span>
                <span
                  v-if="m.path === 'slow' && !m.is_error && m.sql"
                  class="msg-a__export msg-a__promote"
                  @click="openPromote(m)"
                >
                  沉淀为指标
                </span>
              </div>

              <!-- 使用本体（问答 grounding 溯源） -->
              <div v-if="ontName(m).length" class="msg-a__ont">
                <el-icon class="msg-a__ont-icon"><Files /></el-icon>
                <span class="msg-a__ont-label">使用本体</span>
                <el-tag
                  v-for="o in ontName(m)"
                  :key="o.table"
                  size="small"
                  effect="plain"
                  style="margin: 0 3px 4px 0"
                  class="msg-a__ont-tag"
                  @click="gotoOntology(o)"
                >
                  {{ o.name }}（{{ o.table }}）
                </el-tag>
              </div>

              <!-- 召回 schema（混合检索锁定的表/字段，grounding 可观测） -->
              <div v-if="m.retrieved && m.retrieved.tables?.length" class="msg-a__ont">
                <el-icon class="msg-a__ont-icon"><Search /></el-icon>
                <span class="msg-a__ont-label">召回表</span>
                <el-tooltip
                  v-for="t in m.retrieved.tables"
                  :key="t"
                  :content="(m.retrieved.fields?.[t] || []).join('、')"
                  placement="top"
                >
                  <el-tag size="small" effect="plain" style="margin: 0 3px 4px 0">{{ t }}</el-tag>
                </el-tooltip>
              </div>

              <!-- 思考过程 / 工具调用链（流式） -->
              <div v-if="m._running || m._reasoning || m._trace?.length" class="msg-a__trace">
                <div v-if="m._reasoning" class="trace-reasoning">
                  <div class="trace-title">
                    <el-icon><MagicStick /></el-icon>
                    思考过程
                  </div>
                  <pre class="trace-pre">{{ m._reasoning }}</pre>
                </div>
                <template v-for="(t, ti) in m._trace" :key="ti">
                  <div v-if="t.kind === 'tool_start'" class="trace-call">
                    <el-tag size="small" type="warning">调用工具</el-tag>
                    <span class="trace-name">{{ t.name }}</span>
                    <code class="trace-args">{{ JSON.stringify(t.args) }}</code>
                  </div>
                  <div v-else-if="t.kind === 'tool_result'" class="trace-out">
                    <el-tag size="small" type="info">工具输出</el-tag>
                    <pre class="trace-pre trace-pre--out">{{ t.result }}</pre>
                  </div>
                  <div v-else-if="t.kind === 'tool_error'" class="trace-err">
                    <el-tag size="small" type="danger">工具报错</el-tag>
                    <span>{{ t.error }}</span>
                  </div>
                </template>
              </div>

              <!-- 实时生成的 SQL（运行中） -->
              <div v-if="m._running && m._sqlLive" class="msg-a__code msg-a__code--live">
                <pre>{{ m._sqlLive }}</pre>
              </div>

              <div v-if="m.summary" class="msg-a__summary">{{ m.summary }}</div>

              <!-- DQ 警告：问数涉及数据质量风险表（温和提示） -->
              <el-alert
                v-if="m.dq_warning?.length"
                type="warning"
                :closable="false"
                show-icon
                class="msg-a__dq"
                :title="`数据质量提示：以下对象健康分较低，结果可能受数据质量影响（${m.dq_warning.map((x: any) => x.table + ' ' + x.score).join('、')}）`"
              />

              <template v-if="showChart(m)">
                <div class="msg-a__chart-title">可视化</div>
                <ECharts :options="chartOption(m)" height="240px" />
              </template>

              <div v-if="m._showSql" class="msg-a__code">
                <pre>{{ m.sql }}</pre>
              </div>

              <el-table
                v-if="m.columns?.length && (m.rows || []).length"
                :data="rowsToItems(m)"
                size="small"
                border
                max-height="320"
                class="msg-a__table"
              >
                <el-table-column
                  v-for="c in m.columns"
                  :key="c"
                  :prop="String(c)"
                  :label="String(c)"
                  min-width="120"
                />
              </el-table>
              <el-empty
                v-else-if="m.columns?.length && !m.is_error"
                :image-size="40"
                description="查询无结果"
              />
              <div v-if="m.is_error" class="msg-a__err">{{ m.summary }}</div>
            </div>
          </div>

          <div v-if="loading" class="msg-loading">
            <el-icon class="is-loading"><Loading /></el-icon>
            解析并查询中…
          </div>
        </div>

        <div class="query-input">
          <div class="query-examples">
            <span class="query-examples__label">试试问：</span>
            <el-tag
              v-for="q in examples"
              :key="q"
              size="small"
              effect="plain"
              class="query-examples__tag"
              @click="quickAsk(q)"
            >
              {{ q }}
            </el-tag>
          </div>
          <div class="query-input__row">
            <el-input
              v-model="input"
              placeholder="输入数据问题，如：今天告警数是多少"
              clearable
              @keyup.enter="send"
            />
            <el-button type="primary" :loading="loading" @click="send">查询</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 指标 / 术语 / 数据源 运营抽屉 -->
    <el-drawer v-model="opsVisible" title="智能问数 · 指标运营" size="920px" append-to-body>
      <el-tabs v-model="opsTab" @tab-click="onOpsTabClick">
        <el-tab-pane label="指标" name="metric">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openMetricEdit()">
              新增指标
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              已配置 {{ metrics.length }} 个指标
            </el-tag>
          </div>
          <el-table :data="metrics" size="small" border>
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column prop="key" label="key" min-width="120" show-overflow-tooltip />
            <el-table-column prop="agg" label="聚合" width="80" />
            <el-table-column prop="unit" label="单位" width="70" />
            <el-table-column label="权限影响" min-width="150">
              <template #default="{ row }">
                <el-tag size="small" :type="metricAccess(row).restricted ? 'warning' : 'success'" effect="plain">
                  {{ metricAccess(row).restricted ? "受限" : "全角色可查" }}
                </el-tag>
                <span v-if="metricAccess(row).restricted" class="msg-a__time" style="margin-left: 4px">
                  {{ metricAccess(row).tables.join("、") }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" @change="saveMetric(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openMetricEdit(row)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="removeMetric(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="术语" name="term">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openTermEdit()">
              新增术语
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              已配置 {{ terms.length }} 条术语
            </el-tag>
          </div>
          <el-table :data="terms" size="small" border>
            <el-table-column prop="term" label="术语" min-width="100" />
            <el-table-column prop="metric_key" label="映射指标" min-width="140" />
            <el-table-column prop="field_path" label="映射字段" min-width="140" />
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openTermEdit(row)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="removeTerm(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="数据源" name="ds">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openDsEdit()">
              新增数据源
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              系统 + {{ datasources.length }} 个自定义
            </el-tag>
            <el-radio-group v-model="dsView" size="small">
              <el-radio-button value="card">卡片</el-radio-button>
              <el-radio-button value="table">表格</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="dsView === 'card'" class="asset-catalog">
            <el-card v-for="d in datasources" :key="d.id" shadow="never" class="asset-card">
              <div class="asset-card__head">
                <b class="asset-card__name">{{ d.name }}</b>
                <el-tag size="small" type="info" effect="plain">{{ d.type }}</el-tag>
                <div style="flex:1"></div>
                <el-switch v-model="d.enabled" size="small" />
              </div>
              <div class="asset-card__meta">{{ d.database || "—" }}<template v-if="d.host"> · {{ d.host }}:{{ d.port }}</template></div>
              <div class="asset-card__desc">{{ d.remark || "连接器" }}</div>
              <div class="asset-card__actions">
                <el-button link type="primary" size="small" :loading="testingDsId === d.id" @click="testDs(d)">测试</el-button>
                <el-button link type="primary" size="small" :loading="syncingDsId === d.id" @click="syncDs(d)">同步结构</el-button>
                <el-button link type="primary" size="small" @click="openDsEdit(d)">编辑</el-button>
                <el-button link type="danger" size="small" @click="removeDs(d)">删除</el-button>
              </div>
            </el-card>
            <el-empty v-if="!datasources.length" :image-size="50" description="暂无数据源" />
          </div>
          <el-table :data="datasources" size="small" border>
            <el-table-column prop="name" label="名称" min-width="120" />
            <el-table-column prop="type" label="类型" width="90" />
            <el-table-column prop="database" label="库/文件" min-width="140" />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="testingDsId === row.id"
                  @click="testDs(row)"
                >
                  测试
                </el-button>
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="syncingDsId === row.id"
                  @click="syncDs(row)"
                >
                  同步结构
                </el-button>
                <el-button link type="primary" size="small" @click="openDsEdit(row)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="removeDs(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="数据资产" name="asset">
          <div class="ops-bar">
            <el-button
              type="primary"
              size="small"
              :icon="Refresh"
              :loading="syncingAssets"
              @click="syncAssets"
            >
              从数据库同步
            </el-button>
            <el-button
              size="small"
              :icon="MagicStick"
              :loading="generatingDesc"
              @click="generateDesc(false)"
            >
              LLM 生成中文描述
            </el-button>
            <el-button
              size="small"
              :icon="Refresh"
              :loading="generatingDesc"
              @click="generateDesc(true)"
            >
              重生成(全部)
            </el-button>
            <el-button size="small" :loading="extractingObj" @click="extractObjects">
              抽取业务对象
            </el-button>
            <el-button size="small" :loading="inferringRel" @click="inferRel">
              自动推断字段关联
            </el-button>
            <el-button size="small" :loading="rebuildingKg" @click="rebuildKg">
              重建知识图谱
            </el-button>
            <el-input
              v-model="assetSearch"
              size="small"
              placeholder="搜索表名/别名/业务域"
              clearable
              style="width: 220px"
            />
            <el-tag size="small" type="info" effect="plain">
              已纳入 {{ assets.filter((a) => a.included).length }}/{{ assets.length }} 张表
            </el-tag>
            <el-tag v-if="kgStats" size="small" type="success" effect="plain">
              图谱 {{ kgStats.nodes }} 节点 / {{ kgStats.edges }} 边
            </el-tag>
            <el-radio-group v-model="assetView" size="small">
              <el-radio-button value="card">卡片</el-radio-button>
              <el-radio-button value="table">表格</el-radio-button>
            </el-radio-group>
          </div>
          <div v-if="assetView === 'card'" class="asset-catalog">
            <el-card
              v-for="a in filteredAssets"
              :key="a.table_name"
              shadow="never"
              class="asset-card"
              @click="openAssetColumns(a)"
            >
              <div class="asset-card__head">
                <b class="asset-card__name">{{ a.alias || a.table_name }}</b>
                <el-tag size="small" type="info" effect="plain">{{ a.table_name }}</el-tag>
                <div style="flex:1"></div>
                <el-tag v-if="a.object_enabled" size="small" type="success" effect="plain">对象</el-tag>
                <el-tag v-if="(a.sensitive_count || 0) > 0" size="small" type="danger" effect="plain">
                  {{ a.sensitive_count }}敏感
                </el-tag>
                <el-tag v-if="a.dq_score != null" size="small" :type="a.dq_score >= 80 ? 'success' : a.dq_score >= 60 ? 'warning' : 'danger'" effect="plain">
                  DQ {{ a.dq_score }}
                </el-tag>
              </div>
              <div class="asset-card__meta">{{ a.domain || "—" }} · {{ a.column_count }} 列 · 血缘 {{ a.lineage_count ?? 0 }}</div>
              <div class="asset-card__desc">{{ a.description || "暂无描述" }}</div>
            </el-card>
            <el-empty v-if="!filteredAssets.length" :image-size="50" description="无匹配资产" />
          </div>
          <el-table :data="filteredAssets" size="small" border max-height="400">
            <el-table-column prop="table_name" label="表名" min-width="140" show-overflow-tooltip />
            <el-table-column
              prop="alias"
              label="中文名/别名"
              min-width="90"
              show-overflow-tooltip
            />
            <el-table-column prop="domain" label="业务域" width="80" show-overflow-tooltip />
            <el-table-column label="中文描述" min-width="150">
              <template #default="{ row }">
                <el-input
                  v-model="row.description"
                  size="small"
                  placeholder="表是干什么的"
                  @change="saveAsset(row)"
                />
              </template>
            </el-table-column>
            <el-table-column
              prop="business_scenarios"
              label="业务场景"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column label="纳入" width="68" align="center">
              <template #default="{ row }">
                <el-switch v-model="row.included" @change="saveAsset(row)" />
              </template>
            </el-table-column>
            <el-table-column label="业务对象" width="96" align="center">
              <template #default="{ row }">
                <el-switch v-model="row.object_enabled" @change="saveAsset(row)" />
              </template>
            </el-table-column>
            <el-table-column label="字段" width="90" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openAssetColumns(row)">
                  {{ row.included_columns }}/{{ row.column_count }}
                </el-button>
              </template>
            </el-table-column>
            <el-table-column label="敏感度" width="120" align="center">
              <template #default="{ row }">
                <el-tooltip :content="(row.sensitive_fields || []).join('、') || '无敏感字段'" placement="top">
                  <el-tag size="small" :type="(row.sensitive_count || 0) > 0 ? 'danger' : 'info'" effect="plain">
                    {{ (row.sensitive_count || 0) > 0 ? `${row.sensitive_count} 个敏感` : '无' }}
                  </el-tag>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openAssetEdit(row)">
                  编辑
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="智能推荐" name="suggest">
          <div class="ops-bar">
            <el-button
              type="primary"
              size="small"
              :icon="MagicStick"
              :loading="suggesting"
              @click="loadSuggest"
            >
              生成指标/术语建议
            </el-button>
            <el-tag size="small" type="info" effect="plain">基于数据字典，支持一键采纳</el-tag>
          </div>
          <div v-if="suggested.metrics?.length || suggested.terms?.length">
            <el-divider content-position="left">指标建议</el-divider>
            <el-table :data="suggested.metrics" size="small" border>
              <el-table-column prop="name" label="指标名" min-width="140" />
              <el-table-column prop="sql" label="SQL" min-width="240" show-overflow-tooltip />
              <el-table-column label="采纳" width="80" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="adoptSugMetric(row)">
                    采纳
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-divider content-position="left">术语建议</el-divider>
            <el-table :data="suggested.terms" size="small" border>
              <el-table-column prop="term" label="术语" min-width="120" />
              <el-table-column prop="target" label="对应(指标/字段)" min-width="180" />
              <el-table-column label="采纳" width="80" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="adoptSugTerm(row)">
                    采纳
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
          <el-empty v-else description="点击「生成指标/术语建议」" :image-size="50" />
        </el-tab-pane>

        <el-tab-pane label="示例工程" name="fewshot">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openFewshotEdit()">
              新增示例
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              {{ fewshots.length }} 条 · 按相关问题动态注入 NL2SQL
            </el-tag>
          </div>
          <el-table :data="fewshots" size="small" border>
            <el-table-column
              prop="question"
              label="示例问题"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column prop="sql" label="正确 SQL" min-width="240" show-overflow-tooltip />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" @change="saveFewshot(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openFewshotEdit(row)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="removeFewshot(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="反馈统计" name="stats">
          <el-row :gutter="12" class="ops-stats">
            <el-col :span="6"><el-statistic title="累计问答" :value="stats.total" /></el-col>
            <el-col :span="6"><el-statistic title="快路径" :value="stats.fast" /></el-col>
            <el-col :span="6"><el-statistic title="慢路径(NL2SQL)" :value="stats.slow" /></el-col>
            <el-col :span="6"><el-statistic title="失败" :value="stats.errors" /></el-col>
          </el-row>
          <el-alert
            type="success"
            :closable="false"
            show-icon
            title="反馈闭环：在问答结果里「点赞」并填正确 SQL 会沉淀为示例，供后续动态复用"
          />
        </el-tab-pane>

        <el-tab-pane label="查询限额" name="settings">
          <el-form :model="settingsForm" label-width="140px" size="default">
            <el-form-item label="结果最大行数">
              <el-input-number
                v-model="settingsForm.query_max_rows"
                :min="10"
                :max="10000"
                :step="100"
              />
            </el-form-item>
            <el-form-item label="查询超时(秒)">
              <el-input-number
                v-model="settingsForm.query_timeout_sec"
                :min="1"
                :max="120"
                :step="1"
              />
            </el-form-item>
            <el-form-item label="NL2SQL 自纠错轮数">
              <el-input-number v-model="settingsForm.nl2sql_retry" :min="0" :max="5" :step="1" />
            </el-form-item>
            <el-form-item label="NL2SQL max_tokens">
              <el-input-number
                v-model="settingsForm.nl2sql_max_tokens"
                :min="256"
                :max="8192"
                :step="128"
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingSettings" @click="saveSettings">
                保存限额
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="工程配置" name="engine">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="Schema 链接 / 提示词策略等工程参数，技术维护。保存后即时生效（进程级缓存自动失效）。"
          />
          <el-form :model="engForm" label-width="160px" size="default">
            <el-divider content-position="left">Schema 链接</el-divider>
            <el-form-item label="schema_top_k（表数上限）">
              <el-input-number v-model="engForm.schema_top_k" :min="4" :max="40" :step="1" />
            </el-form-item>
            <el-form-item label="语义检索权重">
              <el-input-number
                v-model="engForm.schema_semantic_weight"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
              />
            </el-form-item>
            <el-form-item label="关键词检索权重">
              <el-input-number
                v-model="engForm.schema_keyword_weight"
                :min="0"
                :max="1"
                :step="0.05"
                :precision="2"
              />
            </el-form-item>
            <el-divider content-position="left">策略开关</el-divider>
            <el-form-item label="实体名词→表 基线">
              <el-switch v-model="engForm.entity_enabled" />
            </el-form-item>
            <el-form-item label="枚举取值注入">
              <el-switch v-model="engForm.enum_hint_enabled" />
            </el-form-item>
            <el-form-item label="全量实体不截断(LIMIT)">
              <el-switch v-model="engForm.full_entity_no_limit" />
            </el-form-item>
            <el-form-item label="实体查询 JOIN 取 name">
              <el-switch v-model="engForm.entity_name_rule" />
            </el-form-item>
            <el-form-item label="语义检索走 Agno">
              <el-switch v-model="engForm.agno_semantic_enabled" />
            </el-form-item>
            <el-divider content-position="left">高级策略</el-divider>
            <el-form-item label="分解式规划">
              <el-switch v-model="engForm.decomposed_planning" />
            </el-form-item>
            <el-form-item label="自一致性(候选数)">
              <el-input-number v-model="engForm.self_consistency_n" :min="1" :max="5" :step="1" />
            </el-form-item>
            <el-form-item label="查询代价护栏">
              <el-switch v-model="engForm.query_cost_enabled" />
            </el-form-item>
            <el-form-item label="代价护栏预估行数上限">
              <el-input-number
                v-model="engForm.query_cost_max_rows"
                :min="1000"
                :max="5000000"
                :step="1000"
              />
            </el-form-item>
            <el-form-item label="反馈正例自动沉淀">
              <el-switch v-model="engForm.fewshot_auto_curate" />
            </el-form-item>
            <el-form-item label="结果为空时自纠错">
              <el-switch v-model="engForm.empty_self_correct" />
            </el-form-item>
            <el-form-item label="工具化 Agent(自主取schema)">
              <el-switch v-model="engForm.agno_tool_agent" />
            </el-form-item>
            <el-form-item label="知识图谱召回">
              <el-switch v-model="engForm.kg_enabled" />
            </el-form-item>
            <el-divider content-position="left">实体名词→表 映射（行式编辑，覆盖默认）</el-divider>
            <div class="emap-editor">
              <div v-for="(row, idx) in engRows" :key="idx" class="emap-row">
                <el-input
                  v-model="row.noun"
                  placeholder="实体名词，如：摄像头"
                  style="width: 190px"
                />
                <el-input
                  v-model="row.tables"
                  placeholder="关联表，逗号分隔，如：video_cameras,video_camera_groups"
                  class="emap-tables"
                />
                <el-button :icon="Delete" circle text type="danger" @click="removeEngRow(idx)" />
              </div>
              <el-button type="primary" plain :icon="Plus" @click="addEngRow">新增一行</el-button>
              <div class="emap-hint">保存时自动转为 JSON 存储；留空实体名词的行会被忽略。</div>
            </div>
            <el-form-item>
              <el-button type="primary" :loading="savingEngine" @click="saveEngineConfig">
                保存工程配置
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="基准测试" name="benchmark">
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="对内置 20 道快路径 + 60 道复杂报表基准，逐一用真实 LLM 跑一遍并输出精度/耗时。约需数分钟，请保持页面打开。"
          />
          <div class="bm-actions">
            <el-button
              type="primary"
              :loading="bmRunning"
              :disabled="bmRunning"
              @click="runBenchmark"
            >
              {{ bmRunning ? "基准运行中…" : "运行基准测试" }}
            </el-button>
            <el-progress
              v-if="bmRunning || bmFinished"
              :percentage="bmPercent"
              :status="bmError ? 'exception' : bmFinished ? 'success' : ''"
              style="flex: 1"
            />
          </div>
          <div v-if="bmState" class="bm-meta">
            阶段：{{ bmStage }} | 当前：{{ bmState.current || "-" }} | 进度：{{ bmDoneCount }}/{{
              bmTotal
            }}
          </div>
          <template v-if="bmReport">
            <el-divider content-position="left">快路径（指标模板）</el-divider>
            <el-row :gutter="12" class="ops-stats">
              <el-col :span="6"><el-statistic title="题数" :value="bmReport.fast.total" /></el-col>
              <el-col :span="6">
                <el-statistic title="语义精度" :value="bmReport.fast.semantic_accuracy" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="快路径命中" :value="bmReport.fast.fast_path_rate" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="P50" :value="bmReport.fast.p50_ms" :suffix="'ms'" />
              </el-col>
            </el-row>
            <el-divider content-position="left">NL2SQL 复杂报表（宽松比对）</el-divider>
            <el-row :gutter="12" class="ops-stats">
              <el-col :span="6">
                <el-statistic title="题数" :value="bmReport.nl2sql.total" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="数据精度" :value="bmReport.nl2sql.accuracy" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="慢路径占比" :value="bmReport.nl2sql.slow_rate" />
              </el-col>
              <el-col :span="6">
                <el-statistic title="P50" :value="bmReport.nl2sql.p50_ms" :suffix="'ms'" />
              </el-col>
            </el-row>
            <div v-if="Object.keys(bmReport.nl2sql.by_tag || {}).length" class="bm-tags">
              <el-tag
                v-for="(b, tag) in bmReport.nl2sql.by_tag"
                :key="tag"
                :type="b.acc >= 0.8 ? 'success' : b.acc >= 0.5 ? 'warning' : 'danger'"
                class="bm-tag"
              >
                {{ tag }} {{ b.correct }}/{{ b.total }} = {{ (b.acc * 100).toFixed(0) }}%
              </el-tag>
            </div>
            <el-divider content-position="left">逐题明细</el-divider>
            <el-table :data="bmFailRows" size="small" border>
              <el-table-column prop="q" label="问题" min-width="200" show-overflow-tooltip />
              <el-table-column prop="tag" label="类别" width="90" />
              <el-table-column label="结果" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.correct ? 'success' : 'danger'" size="small">
                    {{ row.correct ? "通过" : "失败" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="ms" label="耗时(ms)" width="90" />
            </el-table>
          </template>
          <el-alert
            v-if="bmError"
            type="error"
            :closable="false"
            show-icon
            :title="bmError"
            style="margin-top: 8px"
          />
        </el-tab-pane>
        <el-tab-pane label="图谱" name="kg">
          <div class="ops-bar">
            <el-radio-group v-model="kgScope" size="small" @change="loadUnifiedGraph">
              <el-radio-button value="all">全部</el-radio-button>
              <el-radio-button value="schema">数据schema</el-radio-button>
              <el-radio-button value="knowledge">知识库</el-radio-button>
            </el-radio-group>
            <el-select
              v-if="kgScope !== 'schema'"
              v-model="kgKb"
              size="small"
              placeholder="选择知识库"
              clearable
              style="width: 190px"
              @change="loadUnifiedGraph"
            >
              <el-option v-for="b in kgKbs" :key="b.id" :label="b.name" :value="b.id" />
            </el-select>
            <el-button size="small" :icon="Refresh" :loading="loadingKg" @click="loadUnifiedGraph">
              刷新
            </el-button>
            <el-button size="small" :loading="linkingKg" @click="autoLinkKg">
              实体↔表自动打边
            </el-button>
            <el-tag v-if="kgNodes.length" size="small" type="info" effect="plain">
              {{ kgNodes.length }} 节点 / {{ kgEdges.length }} 边
            </el-tag>
          </div>
          <GraphCanvas
            v-if="kgNodes.length"
            :nodes="kgNodes"
            :edges="kgEdges"
            height="520px"
            layout-name="cose"
            use-preset
          />
          <el-empty
            v-else-if="!loadingKg"
            description="暂无图谱数据，可切换来源或先构建知识库图谱"
          />
        </el-tab-pane>
        <el-tab-pane label="本体" name="concept">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openConceptEdit()">
              新增概念
            </el-button>
            <el-select
              v-model="industryTpl"
              size="small"
              placeholder="行业模板"
              style="width: 200px"
            >
              <el-option v-for="t in industryTemplates" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
            <el-button size="small" :loading="applyingTpl" @click="applyTpl">应用模板</el-button>
            <el-tag size="small" type="info" effect="plain">
              已维护 {{ concepts.length }} 个业务概念
            </el-tag>
          </div>
          <el-table :data="concepts" size="small" border max-height="400">
            <el-table-column prop="name" label="概念" min-width="110" show-overflow-tooltip />
            <el-table-column
              prop="description"
              label="定义"
              min-width="180"
              show-overflow-tooltip
            />
            <el-table-column prop="synonyms" label="同义词" min-width="120" show-overflow-tooltip />
            <el-table-column
              prop="parent_name"
              label="上级概念"
              width="100"
              show-overflow-tooltip
            />
            <el-table-column prop="domain" label="业务域" width="90" show-overflow-tooltip />
            <el-table-column prop="metric_key" label="指标" width="110" show-overflow-tooltip />
            <el-table-column prop="tables" label="关联表" min-width="150">
              <template #default="{ row }">
                <el-tag
                  v-for="t in row.tables || []"
                  :key="t"
                  size="small"
                  effect="plain"
                  style="margin: 0 2px"
                >
                  {{ t }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openConceptEdit(row)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="deleteConcept(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="交付" name="fde">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openFdeEdit()">
              新增命题
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              共 {{ fdList.length }} 个交付命题
            </el-tag>
          </div>
          <el-table :data="fdList" size="small" border max-height="400">
            <el-table-column prop="title" label="命题" min-width="150" show-overflow-tooltip />
            <el-table-column prop="owner" label="责任人" width="90" show-overflow-tooltip />
            <el-table-column label="五步" min-width="200">
              <template #default="{ row }">
                <el-tag
                  v-for="(v, k) in row.steps"
                  :key="k"
                  size="small"
                  :type="v === 'done' ? 'success' : v === 'doing' ? 'warning' : 'info'"
                  effect="plain"
                  style="margin: 0 2px"
                >
                  {{
                    {
                      diagnosis: "诊断",
                      modeling: "建模",
                      assembly: "组装",
                      shadow: "影子",
                      handover: "移交",
                    }[k]
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'done' ? 'success' : 'warning'">
                  {{ row.status === "done" ? "已交付" : "进行中" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="影子结果" min-width="200">
              <template #default="{ row }">
                <template v-if="row.shadow_result">
                  <el-tag size="small" :type="row.shadow_result === 'pass' ? 'success' : 'danger'" effect="plain">
                    {{ row.shadow_result === "pass" ? "通过" : "未通过" }}
                  </el-tag>
                  <span class="fde-shadow-detail">
                    实际 {{ row.shadow_actual ?? "-" }} vs 金标 {{ row.shadow_golden || "-" }}
                    <template v-if="row.shadow_tolerance">（±{{ row.shadow_tolerance }}）</template>
                  </span>
                  <el-tag size="small" type="info" effect="plain" style="margin-left: 4px">
                    {{ row.shadow_at?.slice(0, 10) }}
                  </el-tag>
                </template>
                <el-tag v-else size="small" type="info" effect="plain">未运行</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="210" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="runFdeShadow(row)">
                  影子运行
                </el-button>
                <el-button link type="primary" size="small" @click="openFdeEdit(row)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="deleteFde(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="动作" name="action">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openActionEdit()">
              新增动作
            </el-button>
            <el-tag size="small" type="info" effect="plain">共 {{ actions.length }} 个动作</el-tag>
          </div>
          <el-table :data="actions" size="small" border max-height="260">
            <el-table-column prop="name" label="名称" min-width="110" show-overflow-tooltip />
            <el-table-column
              prop="object_table"
              label="目标对象"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column label="可写字段" min-width="150">
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
            <el-table-column label="审批" width="70" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.approve ? 'warning' : 'success'">
                  {{ row.approve ? "需审批" : "直接执行" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openActionRun(row)">
                  执行
                </el-button>
                <el-button link size="small" @click="openActionEdit(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="ops-bar" style="margin-top: 10px">
            <span class="trace-title">审计日志</span>
            <el-button size="small" @click="loadActionLogs">刷新</el-button>
          </div>
          <el-table :data="actionLogs" size="small" border max-height="180">
            <el-table-column prop="action" label="动作" width="100" show-overflow-tooltip />
            <el-table-column prop="table" label="对象" width="110" show-overflow-tooltip />
            <el-table-column prop="key" label="键" width="90" show-overflow-tooltip />
            <el-table-column label="参数" min-width="120">
              <template #default="{ row }">{{ JSON.stringify(row.params) }}</template>
            </el-table-column>
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.result === 'success' ? 'success' : 'info'">
                  {{ row.result }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="time" label="时间" width="150" show-overflow-tooltip />
          </el-table>
          <div class="ops-bar" style="margin-top: 10px">
            <span class="trace-title">审批待办</span>
            <el-button size="small" @click="loadPendingActions">刷新</el-button>
            <el-tag v-if="pendingActions.length" size="small" type="warning" effect="plain">
              {{ pendingActions.length }} 条待审批
            </el-tag>
          </div>
          <el-table v-if="pendingActions.length" :data="pendingActions" size="small" border max-height="200">
            <el-table-column prop="action" label="动作" width="100" show-overflow-tooltip />
            <el-table-column prop="table" label="对象" width="110" show-overflow-tooltip />
            <el-table-column prop="key" label="键" width="90" show-overflow-tooltip />
            <el-table-column label="参数" min-width="120">
              <template #default="{ row }">{{ JSON.stringify(row.params) }}</template>
            </el-table-column>
            <el-table-column prop="operator" label="申请人" width="80" show-overflow-tooltip />
            <el-table-column prop="time" label="时间" width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="160" align="center">
              <template #default="{ row }">
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="approvingId === row.id"
                  @click="doApprove(row)"
                >
                  批准并执行
                </el-button>
                <el-button link type="danger" size="small" @click="doReject(row)">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="40" description="暂无待审批动作" />
        </el-tab-pane>
        <el-tab-pane label="审批" name="approval">
          <div class="ops-bar">
            <span class="trace-title">审批中心（待审批）</span>
            <el-button size="small" @click="loadApprovalCenter">刷新</el-button>
            <el-tag v-if="approvalCenter.total > 0" size="small" type="warning" effect="plain">
              {{ approvalCenter.total }} 条待审批
            </el-tag>
          </div>
          <el-alert type="info" :closable="false" show-icon title="统一审批：动作写回 + 本体版本发布的高危操作，需超管批准后执行/发布。" />
          <div class="gov-section" style="margin-top: 10px">动作写回（{{ (approvalCenter.actions || []).length }}）</div>
          <el-table v-if="(approvalCenter.actions || []).length" :data="approvalCenter.actions" size="small" border max-height="220">
            <el-table-column prop="action" label="动作" width="110" show-overflow-tooltip />
            <el-table-column prop="table" label="对象" width="110" show-overflow-tooltip />
            <el-table-column prop="key" label="键" width="90" show-overflow-tooltip />
            <el-table-column label="参数" min-width="120">
              <template #default="{ row }">{{ JSON.stringify(row.params) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" :loading="approvingId === row.id" @click="doApprove(row)">批准执行</el-button>
                <el-button link type="danger" size="small" @click="doReject(row)">驳回</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="30" description="无待审批动作" />
          <div class="gov-section" style="margin-top: 10px">本体发布（{{ (approvalCenter.versions || []).length }}）</div>
          <el-table v-if="(approvalCenter.versions || []).length" :data="approvalCenter.versions" size="small" border max-height="220">
            <el-table-column prop="object_code" label="对象" width="140" show-overflow-tooltip />
            <el-table-column prop="created_time" label="时间" width="170" show-overflow-tooltip />
            <el-table-column label="操作" width="160" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="approveVersion(row)">批准发布</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else :image-size="30" description="无待审批发布" />
        </el-tab-pane>
        <el-tab-pane label="治理" name="governance">
          <div class="ops-bar">
            <el-select
              v-model="govTable"
              size="small"
              filterable
              placeholder="选择业务对象"
              style="width: 200px"
            >
              <el-option
                v-for="o in govObjects"
                :key="o.table"
                :label="o.alias || o.table"
                :value="o.table"
              />
            </el-select>
            <el-button size="small" :icon="Refresh" @click="loadGov">加载</el-button>
          </div>
          <el-row v-if="govTable" :gutter="12">
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>影响分析（{{ govTable }}）</template>
                <div class="gov-section">用到的指标</div>
                <el-tag
                  v-for="m in govImpact.metrics"
                  :key="m.key"
                  size="small"
                  type="primary"
                  effect="plain"
                  style="margin: 0 3px 4px 0"
                >
                  {{ m.name }}
                </el-tag>
                <div v-if="!govImpact.metrics?.length" class="gov-empty">无</div>
                <div class="gov-section">入向关联（引用本表字段）</div>
                <div v-for="(r, i) in govImpact.incoming_relations" :key="i" class="gov-rel">
                  <el-tag size="small" effect="plain">{{ "表" + r.from + "." + r.field }}</el-tag>
                  ← {{ r.column }}
                </div>
                <div v-if="!govImpact.incoming_relations?.length" class="gov-empty">无</div>
                <div class="gov-section">对象链接</div>
                <el-tag
                  v-for="o in govImpact.object_links"
                  :key="o.object"
                  size="small"
                  type="warning"
                  effect="plain"
                  style="margin: 0 3px 4px 0"
                >
                  {{ o.alias }}
                </el-tag>
                <div v-if="!govImpact.object_links?.length" class="gov-empty">无</div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>版本历史</template>
                <el-table :data="govVersions" size="small">
                  <el-table-column prop="version" label="版本" width="60" />
                  <el-table-column prop="time" label="时间" width="150" show-overflow-tooltip />
                  <el-table-column label="操作" width="90" align="center">
                    <template #default="{ row }">
                      <el-button link type="warning" size="small" @click="rollGov(row)">
                        回滚
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div v-if="!govVersions.length" class="gov-empty">暂无版本（保存过资产即有）</div>
              </el-card>
            </el-col>
          </el-row>
          <el-card v-if="govTable" shadow="never" style="margin-top: 12px">
            <template #header>完整血缘（{{ govTable }}）</template>
            <div class="gov-section">字段（{{ govLineage?.fields?.length || 0 }}）</div>
            <el-tag
              v-for="f in (govLineage?.fields || []).slice(0, 12)"
              :key="f"
              size="small"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              {{ f }}
            </el-tag>
            <el-tag
              v-if="(govLineage?.fields?.length || 0) > 12"
              size="small"
              type="info"
              effect="plain"
            >
              +{{ govLineage.fields.length - 12 }}
            </el-tag>
            <div class="gov-section">用到本表的指标 / 关联概念</div>
            <el-tag
              v-for="m in govLineage?.metrics || []"
              :key="m.key"
              size="small"
              type="primary"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              {{ m.name }}
            </el-tag>
            <el-tag
              v-for="c in govLineage?.concepts || []"
              :key="c.name"
              size="small"
              type="success"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              {{ c.name }}
            </el-tag>
            <div
              v-if="!(govLineage?.metrics?.length || govLineage?.concepts?.length)"
              class="gov-empty"
            >
              无
            </div>
            <div class="gov-section">依赖对象 / 入向管道</div>
            <el-tag
              v-for="o in govLineage?.dependent_objects || []"
              :key="o.object"
              size="small"
              type="warning"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              {{ o.alias }}
            </el-tag>
            <el-tag
              v-for="p in govLineage?.pipelines || []"
              :key="p.name"
              size="small"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              管道 {{ p.name }} ← {{ p.source }}
            </el-tag>
            <div
              v-if="!(govLineage?.dependent_objects?.length || govLineage?.pipelines?.length)"
              class="gov-empty"
            >
              无
            </div>
          </el-card>
          <el-card v-if="govTable && govLineageGraph.nodes.length" shadow="never" style="margin-top: 12px">
            <template #header>血缘图（{{ govTable }}）</template>
            <GraphCanvas
              :nodes="govLineageGraph.nodes"
              :edges="govLineageGraph.edges"
              height="360px"
              layout-name="cose"
              use-preset
            />
          </el-card>
          <el-empty v-else description="请选择业务对象查看治理信息" :image-size="40" />
        </el-tab-pane>
        <el-tab-pane label="数据管道" name="pipeline">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openPipeEdit()">
              新建管道
            </el-button>
            <el-tag size="small" type="info" effect="plain">共 {{ pipes.length }} 条管道</el-tag>
          </div>
          <el-table :data="pipes" size="small" border max-height="320">
            <el-table-column prop="name" label="管道" min-width="120" show-overflow-tooltip />
            <el-table-column
              prop="source_connection"
              label="源连接"
              width="110"
              show-overflow-tooltip
            />
            <el-table-column prop="source_table" label="源表" width="130" show-overflow-tooltip />
            <el-table-column label="→ 目标对象" width="140">
              <template #default="{ row }">
                <el-tag size="small" type="success" effect="plain">{{ row.target_object }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="映射" min-width="150">
              <template #default="{ row }">
                <el-tag
                  v-for="m in row.mappings"
                  :key="m.source_col"
                  size="small"
                  effect="plain"
                  style="margin: 0 2px"
                >
                  {{ m.source_col }}→{{ m.target_col }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="上次" width="130">
              <template #default="{ row }">
                <el-tag size="small" :type="row.last_status === 'success' ? 'success' : 'info'">
                  {{ row.last_status || "-" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="180" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="runPipe(row)">运行</el-button>
                <el-button link size="small" @click="viewPipeData(row)">数据</el-button>
                <el-button link size="small" @click="openPipeEdit(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-card shadow="never" style="margin-top: 12px">
            <template #header>
              <div class="ont-head">
                <span>数据管道编排图（源表 → 管道 → 本体对象）</span>
                <el-button size="small" @click="loadPipelineGraph">刷新</el-button>
              </div>
            </template>
            <GraphCanvas
              v-if="pipelineGraph.nodes.length"
              :nodes="pipelineGraph.nodes as any"
              :edges="pipelineGraph.edges as any"
              height="360px"
              layout-name="preset"
              :node-style="{ sizeMode: 'weight', labelSize: 12 }"
              :edge-style="{ label: 'show', colorMode: 'type' }"
            />
            <el-empty v-else :image-size="60" description="暂无管道，新建数据管道后即可查看编排图" />
          </el-card>
        </el-tab-pane>
        <el-tab-pane label="应用" name="workshop">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openWorkshopEdit()">
              新建应用
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              共 {{ wsApps.length }} 个对象应用
            </el-tag>
          </div>
          <el-table :data="wsApps" size="small" border max-height="320">
            <el-table-column prop="name" label="应用" min-width="140" show-overflow-tooltip />
            <el-table-column
              prop="object_table"
              label="对象"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column prop="view_type" label="视图" width="80">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">
                  {{ row.view_type === "form" ? "表单" : "看板" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="列" min-width="180">
              <template #default="{ row }">
                <el-tag
                  v-for="c in row.columns"
                  :key="c"
                  size="small"
                  effect="plain"
                  style="margin: 0 2px"
                >
                  {{ c }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="previewWorkshop(row)">
                  预览
                </el-button>
                <el-button link size="small" @click="openWorkshopEdit(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="权限" name="access">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openAccessEdit()">
              新建策略
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              共 {{ accessRules.length }} 条 ABAC 策略
            </el-tag>
          </div>
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 10px"
            title="ABAC 属性访问控制：超管默认可见全部；命中「敏感放行」策略可查看标记为敏感的对象字段，否则 resolve/问数将自动剔除敏感字段。"
          />
          <el-table :data="accessRules" size="small" border max-height="300">
            <el-table-column prop="name" label="策略" min-width="130" show-overflow-tooltip />
            <el-table-column prop="attribute" label="属性" width="80" />
            <el-table-column prop="value" label="属性值" width="120" show-overflow-tooltip />
            <el-table-column label="允许对象" min-width="160">
              <template #default="{ row }">
                <el-tag
                  v-for="t in row.allowed_tables"
                  :key="t"
                  size="small"
                  effect="plain"
                  style="margin: 0 2px"
                >
                  {{ t }}
                </el-tag>
                <el-tag v-if="!row.allowed_tables?.length" size="small" type="info" effect="plain">
                  全部
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="敏感放行" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.sensitive_ok ? 'success' : 'info'" effect="plain">
                  {{ row.sensitive_ok ? "是" : "否" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="70" align="center">
              <template #default="{ row }">
                <el-switch v-model="row.enabled" size="small" @change="saveAccess(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openAccessEdit(row)">
                  编辑
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-divider content-position="left">数据域权限矩阵（角色 → 可查表 / 敏感）</el-divider>
          <el-button size="small" @click="loadAccessMatrix">刷新矩阵</el-button>
          <el-table :data="accessMatrix" size="small" border max-height="260" style="margin-top: 8px">
            <el-table-column prop="name" label="角色" min-width="110" show-overflow-tooltip />
            <el-table-column prop="code" label="编码" width="110" show-overflow-tooltip />
            <el-table-column label="是否受限" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.restricted ? 'warning' : 'success'" effect="plain">
                  {{ row.restricted ? "受限" : "全开" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="允许对象" min-width="160">
              <template #default="{ row }">
                <el-tag
                  v-for="t in row.tables"
                  :key="t"
                  size="small"
                  effect="plain"
                  style="margin: 0 2px"
                >
                  {{ t }}
                </el-tag>
                <el-tag v-if="!row.restricted" size="small" type="info" effect="plain">
                  全部对象
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="敏感放行" width="90" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="row.sensitive_ok ? 'success' : 'info'" effect="plain">
                  {{ row.sensitive_ok ? "是" : "否" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="预览" width="80" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="previewRole(row)">预览</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!accessMatrix.length" :image-size="40" description="暂无角色矩阵" />
          <div v-if="rolePreview" class="ops-bar" style="margin-top: 8px">
            <el-tag size="small" type="info" effect="plain">
              角色 {{ rolePreview.role }} · {{ rolePreview.restricted ? "受限" : "全开" }} · 敏感放行
              {{ rolePreview.sensitive_ok ? "是" : "否" }} · 可查 {{ rolePreview.count }} 张表
            </el-tag>
          </div>
          <el-table v-if="rolePreview" :data="rolePreview.allowed_tables" size="small" border max-height="200" style="margin-top: 6px">
            <el-table-column label="该角色可查表" min-width="200">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ row }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-divider content-position="left">权限沙箱（按用户ID预览其可查表）</el-divider>
          <div class="ops-bar">
            <el-input-number
              v-model="previewUserId"
              :min="0"
              placeholder="用户ID"
              style="width: 150px"
              controls-position="right"
            />
            <el-button size="small" :loading="previewLoading" @click="loadPreview">
              模拟预览可查表
            </el-button>
            <el-tag v-if="preview" size="small" type="info" effect="plain">
              超管 {{ preview.superuser ? "是" : "否" }} · 角色 {{ (preview.roles || []).join(",") || "无" }}
              · 域受限 {{ preview.domain_restricted ? "是" : "否" }} · 可查 {{ preview.count }} 张表
            </el-tag>
          </div>
          <el-table v-if="preview" :data="preview.allowed_tables" size="small" border max-height="240" style="margin-top: 8px">
            <el-table-column label="该用户可查表" min-width="200">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ row }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="数据质量" name="dq">
          <div class="ops-bar">
            <el-button
              type="primary"
              size="small"
              :icon="Refresh"
              :loading="dqScanning"
              @click="scanAllDqSync"
            >
              扫描全部对象
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              平均分 {{ dqData.avg_score ?? "-" }} · 健康 {{ dqData.healthy ?? 0 }} · 风险
              {{ dqData.risk ?? 0 }}
            </el-tag>
          </div>
          <el-row :gutter="12" style="margin-bottom: 10px">
            <el-col :span="8">
              <el-card shadow="never" body-style="padding:12px">
                <el-statistic title="平均健康分" :value="dqData.avg_score ?? 0" :precision="1" />
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" body-style="padding:12px">
                <el-statistic title="健康对象" :value="dqData.healthy ?? 0" />
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never" body-style="padding:12px">
                <el-statistic title="风险对象" :value="dqData.risk ?? 0" />
              </el-card>
            </el-col>
          </el-row>
          <div v-if="dqAlerts.length" class="dq-alert">
            <el-alert
              type="warning"
              :closable="false"
              :title="`质量预警：${dqAlerts.length} 个对象健康分低于 60，见下方下游影响`"
              show-icon
            />
            <div v-for="a in dqAlerts" :key="a.table" class="dq-alert__item">
              <el-tag size="small" type="danger">{{ a.alias }}</el-tag>
              <span class="dq-alert__score">健康分 {{ a.score }}</span>
              <div class="dq-alert__down">
                <span class="dq-alert__label">下游影响</span>
                <el-tag
                  v-for="o in a.downstream.objects"
                  :key="o"
                  size="small"
                  type="warning"
                  effect="plain"
                  style="margin: 0 3px 3px 0"
                >
                  对象 {{ o }}
                </el-tag>
                <el-tag
                  v-for="m in a.downstream.metrics"
                  :key="m"
                  size="small"
                  type="primary"
                  effect="plain"
                  style="margin: 0 3px 3px 0"
                >
                  指标 {{ m }}
                </el-tag>
                <el-tag
                  v-for="c in a.downstream.concepts"
                  :key="c"
                  size="small"
                  type="success"
                  effect="plain"
                  style="margin: 0 3px 3px 0"
                >
                  概念 {{ c }}
                </el-tag>
                <span
                  v-if="
                    !a.downstream.objects.length &&
                    !a.downstream.metrics.length &&
                    !a.downstream.concepts.length
                  "
                  class="dq-alert__none"
                >
                  无下游
                </span>
              </div>
              <div class="dq-alert__issues">
                <el-tag
                  v-for="(i, k) in a.issues"
                  :key="k"
                  size="small"
                  type="info"
                  effect="plain"
                  style="margin: 0 3px 3px 0"
                >
                  {{ i }}
                </el-tag>
              </div>
            </div>
          </div>
          <el-table :data="dqData.items || []" size="small" border max-height="300">
            <el-table-column prop="alias" label="对象" min-width="120" show-overflow-tooltip />
            <el-table-column prop="table" label="表" min-width="150" show-overflow-tooltip />
            <el-table-column label="健康分" width="170">
              <template #default="{ row }">
                <el-progress
                  :percentage="Math.round(row.score || 0)"
                  :color="
                    (row.score || 0) >= 80
                      ? '#67c23a'
                      : (row.score || 0) >= 60
                        ? '#e6a23c'
                        : '#f56c6c'
                  "
                  :stroke-width="10"
                />
              </template>
            </el-table-column>
            <el-table-column prop="total" label="行数" width="80" />
            <el-table-column label="问题" min-width="200">
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
                <span v-if="!(row.issues || []).length" class="gov-empty">无</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="scanDq(row)">扫描</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="数据域" name="domain">
          <div class="ops-bar">
            <el-button type="primary" size="small" :icon="Plus" @click="openDomainEdit()">
              新建数据域
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              共 {{ domainView.domains?.length || 0 }} 个域 ·
              {{ domainView.total_objects || 0 }} 个对象 · 未归属
              {{ domainView.unassigned?.length || 0 }}
            </el-tag>
            <el-button size="small" :loading="reconciling" @click="loadReconcile">
              对象对账
            </el-button>
          </div>
          <el-alert
            v-if="reconcileResult?.issue_count > 0"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 8px"
            :title="`数据域对账：${reconcileResult.issue_count} 个域引用对象未登记`"
          />
          <el-table
            v-if="reconcileResult?.issues?.length"
            :data="reconcileResult.issues"
            size="small"
            border
            max-height="160"
            style="margin-bottom: 10px"
          >
            <el-table-column prop="domain" label="域" width="120" show-overflow-tooltip />
            <el-table-column prop="table" label="未登记对象" min-width="160" show-overflow-tooltip />
          </el-table>
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 10px"
            title="数据域隔离：对象按数据域归属，成员用户只能访问其所在域的对象；ABAC 结合 domain 属性在解析/问数时过滤。"
          />
          <el-row :gutter="12">
            <el-col v-for="d in domainView.domains || []" :key="d.id" :span="12">
              <el-card shadow="never" style="margin-bottom: 12px">
                <template #header>
                  <div class="domain-head">
                    <div>
                      <el-tag size="small" type="primary" effect="dark">{{ d.name }}</el-tag>
                      <el-tag size="small" type="info" effect="plain" style="margin-left: 6px">
                        {{ d.code }}
                      </el-tag>
                    </div>
                    <el-button link type="primary" size="small" @click="openDomainEdit(d)">
                      编辑
                    </el-button>
                  </div>
                </template>
                <div class="domain-meta">{{ d.description || "—" }}</div>
                <div class="gov-section">对象（{{ d.objects.length }}）</div>
                <el-tag
                  v-for="o in d.objects"
                  :key="o.table"
                  size="small"
                  effect="plain"
                  style="margin: 0 3px 4px 0"
                >
                  {{ o.alias }}
                </el-tag>
                <div v-if="!d.objects.length" class="gov-empty">未分配对象</div>
                <div v-if="d.metrics?.length" class="gov-section">该域表用到的指标</div>
                <el-tag
                  v-for="m in d.metrics || []"
                  :key="m.key"
                  size="small"
                  type="primary"
                  effect="plain"
                  style="margin: 0 3px 4px 0"
                >
                  {{ m.name }}
                </el-tag>
                <div v-if="d.pipelines?.length" class="gov-section">写入该域的管道</div>
                <el-tag
                  v-for="p in d.pipelines || []"
                  :key="p.name"
                  size="small"
                  effect="plain"
                  style="margin: 0 3px 4px 0"
                >
                  管道 {{ p.name }} ← {{ p.source }}
                </el-tag>
                <div class="gov-section">成员用户ID</div>
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
          <el-card v-if="(domainView.unassigned || []).length" shadow="never">
            <template #header>未归属对象</template>
            <el-tag
              v-for="o in domainView.unassigned"
              :key="o.table"
              size="small"
              effect="plain"
              style="margin: 0 3px 4px 0"
            >
              {{ o.alias }}
            </el-tag>
          </el-card>
        </el-tab-pane>
      </el-tabs>
    </el-drawer>

    <!-- P3-⑩ 治理驾驶舱 -->
    <el-drawer
      v-model="govDashVisible"
      title="治理驾驶舱 · Governance Overview"
      size="90%"
      append-to-body
    >
      <div v-loading="govDashLoading" class="govdash">
        <el-row :gutter="12">
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="业务对象" :value="gov.overview?.objects ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="数据源" :value="gov.overview?.datasources ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="数据管道" :value="gov.overview?.pipelines ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="ABAC 策略" :value="gov.overview?.access_rules ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="数据域" :value="gov.overview?.domains ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="智能体" :value="gov.overview?.agents ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic title="动作审计" :value="gov.overview?.action_logs ?? 0" />
            </el-card>
          </el-col>
          <el-col :span="3">
            <el-card shadow="never" body-style="padding:14px">
              <el-statistic
                title="平均健康分"
                :value="gov.overview?.dq?.avg_score ?? 0"
                :precision="1"
              />
            </el-card>
          </el-col>
        </el-row>

        <el-row :gutter="12" style="margin-top: 12px">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header>
                <div class="govdash-head">
                  <span>数据质量健康度</span>
                  <el-tag v-if="(gov.overview?.dq_alerts ?? 0) > 0" size="small" type="danger">
                    预警 {{ gov.overview.dq_alerts }}
                  </el-tag>
                </div>
              </template>
              <div class="govdash-dq">
                <el-progress
                  type="dashboard"
                  :percentage="Math.round(gov.overview?.dq?.avg_score ?? 0)"
                  :color="
                    (gov.overview?.dq?.avg_score ?? 0) >= 80
                      ? '#67c23a'
                      : (gov.overview?.dq?.avg_score ?? 0) >= 60
                        ? '#e6a23c'
                        : '#f56c6c'
                  "
                >
                  <template #default>
                    <span class="govdash-dq__label">{{ gov.overview?.dq?.avg_score ?? 0 }}</span>
                  </template>
                </el-progress>
                <div class="govdash-dq__meta">
                  <el-tag size="small" type="success" effect="plain">
                    健康 {{ gov.overview?.dq?.healthy ?? 0 }}
                  </el-tag>
                  <el-tag size="small" type="warning" effect="plain">
                    预警 {{ gov.overview?.dq?.risk ?? 0 }}
                  </el-tag>
                  <el-tag size="small" type="info" effect="plain">
                    共 {{ gov.overview?.dq?.total ?? 0 }}
                  </el-tag>
                </div>
              </div>
              <div class="gov-section">
                质量预警（{{ (gov.overview?.alert_list || []).length }}）
              </div>
              <div v-for="a in gov.overview?.alert_list || []" :key="a.table" class="govdash-alert">
                <el-tag size="small" type="danger">{{ a.alias }}</el-tag>
                <span class="govdash-alert__score">健康分 {{ a.score }}</span>
                <div class="govdash-alert__down">
                  <el-tag
                    v-for="o in a.downstream.objects"
                    :key="o"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    对象 {{ o }}
                  </el-tag>
                  <el-tag
                    v-for="m in a.downstream.metrics"
                    :key="m"
                    size="small"
                    type="primary"
                    effect="plain"
                  >
                    指标 {{ m }}
                  </el-tag>
                  <span
                    v-if="!a.downstream.objects.length && !a.downstream.metrics.length"
                    class="dq-alert__none"
                  >
                    无下游
                  </span>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header>资产与语义资产</template>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item label="指标">
                  {{ gov.overview?.metrics ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="术语">
                  {{ gov.overview?.terms ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="本体概念">
                  {{ gov.overview?.concepts ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="对象应用">
                  {{ gov.overview?.workshop_apps ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="动作定义">
                  {{ gov.overview?.actions ?? 0 }}
                </el-descriptions-item>
                <el-descriptions-item label="动作审计">
                  {{ gov.overview?.action_logs ?? 0 }}
                </el-descriptions-item>
              </el-descriptions>
              <div class="gov-section">最近管道运行</div>
              <el-table :data="gov.overview?.pipeline_runs || []" size="small" max-height="180">
                <el-table-column prop="name" label="管道" min-width="120" />
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.status === 'success' ? 'success' : 'info'">
                      {{ row.status }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="at" label="运行时间" min-width="140" show-overflow-tooltip />
              </el-table>
            </el-card>
          </el-col>
        </el-row>
      </div>
      <template #footer>
        <el-button @click="govDashVisible = false">关闭</el-button>
        <el-button type="primary" :loading="govDashLoading" @click="loadGovDash">刷新</el-button>
      </template>
    </el-drawer>

    <!-- 指标编辑 -->
    <el-dialog
      v-model="metricEditVisible"
      :title="metricForm.id ? '编辑指标' : '新增指标'"
      width="640px"
      append-to-body
    >
      <el-form :model="metricForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="metricForm.name" placeholder="如：今日告警数" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="指标 key" required>
              <el-input v-model="metricForm.key" placeholder="如 alert_count_today" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="聚合方式">
              <el-select v-model="metricForm.agg" style="width: 100%">
                <el-option label="count" value="count" />
                <el-option label="sum" value="sum" />
                <el-option label="avg" value="avg" />
                <el-option label="group" value="group" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="SQL 模板" required>
          <el-input
            v-model="metricForm.sql_template"
            type="textarea"
            :rows="4"
            placeholder="支持 {参数} 占位，如 SELECT COUNT(*) ... WHERE created_time >= CURRENT_DATE - INTERVAL '{days}' DAY"
          />
        </el-form-item>
        <el-form-item label="口径说明">
          <el-input v-model="metricForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="单位">
              <el-input v-model="metricForm.unit" placeholder="如 条 / 台" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="缓存(秒)">
              <el-input-number v-model="metricForm.cache_ttl" :min="0" :step="30" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="启用">
          <el-switch v-model="metricForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="metricEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveMetric(metricForm)">保存</el-button>
      </template>
    </el-dialog>

    <!-- 字段资产抽屉 -->
    <el-drawer
      v-model="assetColumnsVisible"
      :title="`字段资产 · ${assetColumnsTable}`"
      size="900px"
      append-to-body
    >
      <div class="ops-bar">
        <el-input
          v-model="assetColumnSearch"
          size="small"
          placeholder="搜索字段/描述/关联表"
          clearable
          style="width: 240px"
        />
        <el-tag size="small" type="info" effect="plain">
          已纳入 {{ assetColumns.filter((c) => c.included).length }}/{{ assetColumns.length }} 字段
        </el-tag>
      </div>
      <el-table :data="filteredAssetColumns" size="small" border max-height="68vh">
        <el-table-column prop="column_name" label="字段名" min-width="130" show-overflow-tooltip />
        <el-table-column label="中文描述" min-width="170">
          <template #default="{ row }">
            <el-input
              v-model="row.description"
              size="small"
              placeholder="字段是干什么的"
              @change="saveAssetColumn(row)"
            />
          </template>
        </el-table-column>
        <el-table-column
          prop="business_scenarios"
          label="业务场景"
          min-width="160"
          show-overflow-tooltip
        />
        <el-table-column
          prop="related_table"
          label="关联表"
          min-width="130"
          show-overflow-tooltip
        />
        <el-table-column
          prop="related_field"
          label="关联字段"
          min-width="110"
          show-overflow-tooltip
        />
        <el-table-column label="纳入" width="64" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.included" @change="saveAssetColumn(row)" />
          </template>
        </el-table-column>
        <el-table-column label="敏感" width="58" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.sensitive" @change="saveAssetColumn(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="76" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openColEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <!-- 表元数据编辑 -->
    <el-dialog v-model="assetEditVisible" title="表元数据标注" width="640px" append-to-body>
      <el-form :model="assetForm" label-width="110px">
        <el-form-item label="表名" required>
          <el-input v-model="assetForm.table_name" disabled />
        </el-form-item>
        <el-form-item label="中文名/别名">
          <el-input v-model="assetForm.alias" placeholder="如：视频告警记录" />
        </el-form-item>
        <el-form-item label="业务域">
          <el-input v-model="assetForm.domain" placeholder="如：视频监控/模型训练/数据标注" />
        </el-form-item>
        <el-form-item label="中文描述">
          <el-input
            v-model="assetForm.description"
            type="textarea"
            :rows="3"
            placeholder="这张表是干什么的、包含什么信息"
          />
        </el-form-item>
        <el-form-item label="业务场景">
          <el-input
            v-model="assetForm.business_scenarios"
            type="textarea"
            :rows="3"
            placeholder="哪些业务/报表会用到这张表"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="assetForm.remark" placeholder="备注" />
        </el-form-item>
        <el-form-item label="纳入可查目录">
          <el-switch v-model="assetForm.included" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assetEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAssetMeta">保存</el-button>
      </template>
    </el-dialog>

    <!-- 字段元数据编辑 -->
    <el-dialog v-model="colEditVisible" title="字段元数据标注" width="640px" append-to-body>
      <el-form :model="colForm" label-width="110px">
        <el-form-item label="字段名" required>
          <el-input v-model="colForm.column_name" disabled />
        </el-form-item>
        <el-form-item label="中文描述">
          <el-input
            v-model="colForm.description"
            type="textarea"
            :rows="2"
            placeholder="这个字段是干什么的"
          />
        </el-form-item>
        <el-form-item label="业务场景">
          <el-input
            v-model="colForm.business_scenarios"
            type="textarea"
            :rows="2"
            placeholder="哪些业务/报表需要查这个字段"
          />
        </el-form-item>
        <el-form-item label="关联表">
          <el-input
            v-model="colForm.related_table"
            placeholder="联表查询的实体表，如 video_cameras"
          />
        </el-form-item>
        <el-form-item label="关联字段">
          <el-input
            v-model="colForm.related_field"
            placeholder="对应关联表的字段，如 camera_id / id"
          />
        </el-form-item>
        <el-form-item label="纳入">
          <el-switch v-model="colForm.included" />
        </el-form-item>
        <el-form-item label="敏感字段">
          <el-switch v-model="colForm.sensitive" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="colEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveColMeta">保存</el-button>
      </template>
    </el-dialog>

    <!-- 示例编辑 -->
    <el-dialog
      v-model="fewshotEditVisible"
      :title="fewshotForm.id ? '编辑示例' : '新增示例'"
      width="560px"
      append-to-body
    >
      <el-form :model="fewshotForm" label-width="90px">
        <el-form-item label="示例问题" required>
          <el-input v-model="fewshotForm.question" placeholder="如：每个摄像头组的告警数量" />
        </el-form-item>
        <el-form-item label="正确 SQL" required>
          <el-input v-model="fewshotForm.sql" type="textarea" :rows="4" placeholder="SELECT ..." />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="fewshotForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fewshotEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveFewshot(fewshotForm)">
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 术语编辑 -->
    <el-dialog
      v-model="termEditVisible"
      :title="termForm.id ? '编辑术语' : '新增术语'"
      width="480px"
      append-to-body
    >
      <el-form :model="termForm" label-width="100px">
        <el-form-item label="术语" required>
          <el-input v-model="termForm.term" placeholder="如：在线设备" />
        </el-form-item>
        <el-form-item label="映射指标">
          <el-select v-model="termForm.metric_key" clearable filterable style="width: 100%">
            <el-option v-for="m in metrics" :key="m.key" :label="m.name" :value="m.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="termForm.type" style="width: 100%">
            <el-option label="指标" value="metric" />
            <el-option label="维度" value="dimension" />
            <el-option label="术语" value="term" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="termEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTerm(termForm)">保存</el-button>
      </template>
    </el-dialog>

    <!-- 数据源编辑 -->
    <el-dialog
      v-model="dsEditVisible"
      :title="dsForm.id ? '编辑数据源' : '新增数据源'"
      width="520px"
      append-to-body
    >
      <el-form :model="dsForm" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="dsForm.name" placeholder="如：业务库" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="dsForm.type" style="width: 100%">
            <el-option label="PostgreSQL" value="postgres" />
            <el-option label="MySQL" value="mysql" />
            <el-option label="SQLite" value="sqlite" />
            <el-option label="CSV/文件" value="file" />
            <el-option label="HTTP 接口" value="api" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="16">
            <el-form-item label="主机">
              <el-input v-model="dsForm.host" placeholder="如 127.0.0.1" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="端口">
              <el-input-number v-model="dsForm.port" :min="0" :max="65535" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="库/文件">
          <el-input v-model="dsForm.database" placeholder="数据库名或文件路径" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="dsForm.username" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="dsForm.password" type="password" show-password />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="只读">
          <el-switch v-model="dsForm.read_only" />
        </el-form-item>
        <el-form-item label="授权角色">
          <el-select
            v-model="dsForm.allowed_roles"
            multiple
            clearable
            filterable
            placeholder="不选=所有角色可访问"
            style="width: 100%"
          >
            <el-option v-for="r in queryRoles" :key="r.code" :label="r.name" :value="r.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dsForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dsEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveDs(dsForm)">保存</el-button>
      </template>
    </el-dialog>

    <!-- 本体/概念编辑 -->
    <el-dialog v-model="conceptDialog" title="本体/概念" width="600px" append-to-body>
      <el-form :model="conceptForm" label-width="90px">
        <el-form-item label="概念名称" required>
          <el-input v-model="conceptForm.name" placeholder="如：在线率 / 活跃设备 / 告警" />
        </el-form-item>
        <el-form-item label="业务定义">
          <el-input
            v-model="conceptForm.description"
            type="textarea"
            :rows="2"
            placeholder="这个概念的业务口径/含义"
          />
        </el-form-item>
        <el-form-item label="同义词">
          <el-input v-model="conceptForm.synonyms" placeholder="逗号分隔，如：报警,预警" />
        </el-form-item>
        <el-form-item label="上级概念">
          <el-input v-model="conceptForm.parent_name" placeholder="如：设备" />
        </el-form-item>
        <el-form-item label="业务域">
          <el-input v-model="conceptForm.domain" placeholder="如：安防" />
        </el-form-item>
        <el-form-item label="关联指标">
          <el-input
            v-model="conceptForm.metric_key"
            placeholder="指标 key，如 camera_online_count"
          />
        </el-form-item>
        <el-form-item label="关联表">
          <el-select
            v-model="conceptForm.tables"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入表名"
            style="width: 100%"
          >
            <el-option
              v-for="a in assets"
              :key="a.table_name"
              :label="a.table_name"
              :value="a.table_name"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="conceptDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingConcept" @click="saveConcept">保存</el-button>
      </template>
    </el-dialog>

    <!-- FDE 交付命题编辑 -->
    <el-dialog v-model="fdDialog" title="交付命题" width="640px" append-to-body>
      <el-form :model="fdForm" label-width="90px">
        <el-form-item label="命题标题" required>
          <el-input v-model="fdForm.title" placeholder="如：某车间设备OEE看板" />
        </el-form-item>
        <el-form-item label="业务描述">
          <el-input v-model="fdForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="验收标准">
          <el-input
            v-model="fdForm.criteria"
            type="textarea"
            :rows="2"
            placeholder="可测指标/口径"
          />
        </el-form-item>
        <el-form-item label="责任人">
          <el-input v-model="fdForm.owner" placeholder="FDE/业务负责人" />
        </el-form-item>
        <el-form-item label="FDE 角色">
          <div class="fde-roles">
            <el-input v-model="fdForm.fde_translator" placeholder="业务翻译官" />
            <el-input v-model="fdForm.fde_data" placeholder="数据/本体工程师" />
            <el-input v-model="fdForm.fde_app" placeholder="应用交付工程师" />
          </div>
        </el-form-item>
        <el-form-item label="影子运行">
          <div class="shadow-fields">
            <el-select
              v-model="fdForm.shadow_metric"
              filterable
              allow-create
              placeholder="校验指标"
              style="width: 210px"
            >
              <el-option v-for="mt in metrics" :key="mt.key" :label="mt.name" :value="mt.key" />
            </el-select>
            <el-input v-model="fdForm.shadow_golden" placeholder="黄金值" style="width: 110px" />
            <el-input
              v-model="fdForm.shadow_tolerance"
              placeholder="容差(如2%或5)"
              style="width: 100px"
            />
            <el-tag
              v-if="fdForm.shadow_result"
              size="small"
              :type="fdForm.shadow_result === 'pass' ? 'success' : 'danger'"
            >
              {{ fdForm.shadow_result === "pass" ? "PASS" : "FAIL" }}（实测
              {{ fdForm.shadow_actual }}）
            </el-tag>
          </div>
        </el-form-item>
        <el-form-item label="五步">
          <div class="fde-steps">
            <div v-for="(v, k) in fdForm.steps" :key="k" class="fde-step">
              <span>
                {{
                  {
                    diagnosis: "诊断",
                    modeling: "建模",
                    assembly: "组装",
                    shadow: "影子",
                    handover: "移交",
                  }[k]
                }}
              </span>
              <el-select v-model="fdForm.steps[k]" size="small" style="width: 110px">
                <el-option label="待办" value="todo" />
                <el-option label="进行中" value="doing" />
                <el-option label="已完成" value="done" />
              </el-select>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="fdForm.status">
            <el-radio value="open">进行中</el-radio>
            <el-radio value="done">已交付</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fdDialog = false">取消</el-button>
        <el-button type="primary" @click="saveFde">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作定义编辑 -->
    <el-dialog v-model="actionDialog" title="动作定义" width="560px" append-to-body>
      <el-form :model="actionForm" label-width="90px">
        <el-form-item label="动作名称" required>
          <el-input v-model="actionForm.name" placeholder="如 cam_note" />
        </el-form-item>
        <el-form-item label="目标对象" required>
          <el-input
            v-model="actionForm.object_table"
            placeholder="业务对象表名，如 video_cameras"
          />
        </el-form-item>
        <el-form-item label="可写字段">
          <el-select
            v-model="actionForm.writable_cols"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入受控可写字段"
            style="width: 100%"
          >
            <el-option
              v-for="a in assets"
              :key="a.table_name"
              :label="a.table_name"
              :value="a.table_name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="按角色可写">
          <div class="role-writable-editor" style="width: 100%">
            <div v-for="(rw, rk) in actionForm.writable_by_role" :key="rk" class="rw-row">
              <el-input
                v-model="rw.role"
                placeholder="角色 code，如 ANNOTATOR"
                style="width: 150px"
                @change="normalizeRoleWritable"
              />
              <el-select
                v-model="rw.cols"
                multiple
                filterable
                allow-create
                default-first-option
                placeholder="该角色可写字段"
                style="flex: 1"
              >
                <el-option
                  v-for="c in actionForm.writable_cols"
                  :key="c"
                  :label="c"
                  :value="c"
                />
              </el-select>
              <el-button :icon="Delete" circle text type="danger" @click="removeRoleWritable(rk)" />
            </div>
            <el-button type="primary" plain size="small" :icon="Plus" @click="addRoleWritable">
              新增角色字段
            </el-button>
            <div class="rw-hint">
              配置后，非超管仅能写其角色允许的字段；未填则默认使用上方全局可写字段。
            </div>
          </div>
        </el-form-item>
        <el-form-item label="校验规则">
          <el-input v-model="actionForm.validation" placeholder="如：备注不超过100字" />
        </el-form-item>
        <el-form-item label="需审批">
          <el-switch v-model="actionForm.approve" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionDialog = false">取消</el-button>
        <el-button type="primary" @click="saveActionFn">保存</el-button>
      </template>
    </el-dialog>

    <!-- 动作执行 -->
    <el-dialog v-model="runDialog" title="执行动作" width="560px" append-to-body>
      <el-form :model="runForm" label-width="90px">
        <el-form-item label="动作">
          <el-tag type="warning" effect="plain">{{ runForm.name }}</el-tag>
          <span style="margin-left: 8px; color: var(--el-text-color-secondary)">
            目标 {{ runForm.object_table }}
          </span>
        </el-form-item>
        <el-form-item label="对象关键值" required>
          <el-input v-model="runForm.object_key" placeholder="对象主键值，如 21" />
        </el-form-item>
        <el-form-item v-for="(v, k) in runForm.params" :key="String(k)" :label="String(k)">
          <el-input v-model="runForm.params[k]" placeholder="新值" />
        </el-form-item>
        <el-form-item label="批准执行">
          <el-switch v-model="runForm.approve" />
          <span class="query-hint">该动作需审批，勾选“批准执行”后才会写回</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runDialog = false">取消</el-button>
        <el-button type="primary" @click="runActionFn">执行</el-button>
      </template>
    </el-dialog>

    <!-- 数据管道编辑 -->
    <el-dialog v-model="pipeDialog" title="数据管道" width="620px" append-to-body>
      <el-form :model="pipeForm" label-width="100px">
        <el-form-item label="管道名称" required>
          <el-input v-model="pipeForm.name" placeholder="如 MES工单接入" />
        </el-form-item>
        <el-form-item label="源连接">
          <el-select
            v-model="pipeForm.source_connection"
            filterable
            placeholder="选择数据源(外部系统)或留空=本系统"
            style="width: 100%"
          >
            <el-option label="本系统 (platform)" value="" />
            <el-option
              v-for="d in datasources"
              :key="d.id"
              :label="`${d.name} (${d.type})`"
              :value="String(d.id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="源表" required>
          <el-input v-model="pipeForm.source_table" placeholder="如 train_tasks / orders" />
        </el-form-item>
        <el-form-item label="目标对象" required>
          <el-input v-model="pipeForm.target_object" placeholder="业务对象表，如 train_tasks" />
        </el-form-item>
        <el-form-item label="列映射">
          <el-button size="small" @click="addPipeMapping">+ 添加映射</el-button>
          <div v-for="(m, i) in pipeForm.mappings" :key="i" class="pipe-mapping">
            <el-input v-model="m.source_col" placeholder="源列" style="width: 160px" />
            <span>→</span>
            <el-input v-model="m.target_col" placeholder="目标列" style="width: 160px" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pipeDialog = false">取消</el-button>
        <el-button type="primary" @click="savePipe">保存</el-button>
      </template>
    </el-dialog>

    <!-- P3-⑤ 管道落库数据 -->
    <el-dialog v-model="pipeDataVisible" title="管道落库数据" width="720px" append-to-body>
      <el-table
        v-if="pipeData && pipeData.ok && pipeData.rows && pipeData.rows.length"
        :data="
          pipeData.rows.map((r: any[], i: number) => {
            const o: any = { __i: i };
            (pipeData.columns || []).forEach((c: string, ci: number) => (o[c] = r[ci]));
            return o;
          })
        "
        size="small"
        border
        max-height="400"
      >
        <el-table-column
          v-for="c in pipeData.columns"
          :key="c"
          :prop="String(c)"
          :label="String(c)"
          min-width="110"
        />
      </el-table>
      <el-alert
        v-else-if="pipeData && !pipeData.ok"
        type="error"
        :title="pipeData.msg"
        :closable="false"
      />
      <el-empty v-else description="暂无落库数据（先运行管道）" :image-size="40" />
    </el-dialog>

    <!-- Workshop 应用编辑 -->
    <el-dialog v-model="wsDialog" title="对象应用" width="600px" append-to-body>
      <el-form :model="wsForm" label-width="100px">
        <el-form-item label="应用名称" required>
          <el-input v-model="wsForm.name" placeholder="如 摄像头监控看板" />
        </el-form-item>
        <el-form-item label="业务对象" required>
          <el-select
            v-model="wsForm.object_table"
            filterable
            placeholder="选择业务对象"
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
        <el-form-item label="视图类型">
          <el-radio-group v-model="wsForm.view_type">
            <el-radio value="table">看板</el-radio>
            <el-radio value="form">表单</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="展示列">
          <el-select
            v-model="wsForm.columns"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="选择/输入列(空=全部)"
            style="width: 100%"
          >
            <el-option v-for="o in govObjects" :key="o.table" :label="o.table" :value="o.table" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wsDialog = false">取消</el-button>
        <el-button type="primary" @click="saveWorkshop">保存</el-button>
      </template>
    </el-dialog>

    <!-- Workshop 预览 -->
    <el-dialog v-model="wsPreviewVisible" title="对象应用预览" width="720px" append-to-body>
      <el-table
        v-if="wsPreview && wsPreview.rows && wsPreview.rows.length"
        :data="
          wsPreview.rows.map((r: any[], i: number) => {
            const o: any = { __i: i };
            (wsPreview.columns || []).forEach((c: string, ci: number) => (o[c] = r[ci]));
            return o;
          })
        "
        size="small"
        border
        max-height="400"
      >
        <el-table-column
          v-for="c in wsPreview.columns"
          :key="c"
          :prop="String(c)"
          :label="String(c)"
          min-width="110"
        />
      </el-table>
      <el-alert
        v-else-if="wsPreview && !wsPreview.ok"
        type="error"
        :title="wsPreview.msg"
        :closable="false"
      />
      <el-empty v-else description="暂无数据" :image-size="40" />
    </el-dialog>

    <!-- ABAC 权限策略编辑 -->
    <el-dialog v-model="accessDialog" title="ABAC 权限策略" width="520px" append-to-body>
      <el-form :model="accessForm" label-width="100px">
        <el-form-item label="策略名称" required>
          <el-input v-model="accessForm.name" placeholder="如 生产部可看敏感" />
        </el-form-item>
        <el-form-item label="属性">
          <el-select v-model="accessForm.attribute" style="width: 100%">
            <el-option label="角色 role" value="role" />
            <el-option label="部门 dept" value="dept" />
            <el-option label="数据域 domain" value="domain" />
          </el-select>
        </el-form-item>
        <el-form-item label="属性值" required>
          <el-input v-model="accessForm.value" placeholder="如 production / 生产部" />
        </el-form-item>
        <el-form-item label="允许对象">
          <el-select
            v-model="accessForm.allowed_tables"
            multiple
            clearable
            filterable
            placeholder="空 = 全部对象"
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
        <el-form-item label="敏感放行">
          <el-switch v-model="accessForm.sensitive_ok" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="accessDialog = false">取消</el-button>
        <el-button type="primary" @click="saveAccess(accessForm)">保存</el-button>
      </template>
    </el-dialog>

    <!-- 数据域编辑 -->
    <el-dialog v-model="domainDialog" title="数据域" width="520px" append-to-body>
      <el-form :model="domainForm" label-width="100px">
        <el-form-item label="域名称" required>
          <el-input v-model="domainForm.name" placeholder="如 生产域" />
        </el-form-item>
        <el-form-item label="域编码">
          <el-input v-model="domainForm.code" placeholder="如 prod" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="domainForm.description" placeholder="数据域用途" />
        </el-form-item>
        <el-form-item label="对象">
          <el-select
            v-model="domainForm.tables"
            multiple
            filterable
            clearable
            placeholder="选择本域归属的对象"
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
        <el-form-item label="成员用户">
          <el-select
            v-model="domainForm.members"
            multiple
            filterable
            clearable
            allow-create
            placeholder="成员用户ID（可输入）"
            style="width: 100%"
          >
            <el-option v-for="i in 5" :key="i" :label="`用户 #${i}`" :value="i" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="domainDialog = false">取消</el-button>
        <el-button type="primary" @click="saveDomainForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 沉淀为指标（FDE 复用闭环）：把已验证问答固化为确定性快路径指标 -->
    <el-dialog v-model="promoteVisible" title="沉淀为可复用指标" width="620px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="沉淀后，下次问同类问题会直接命中该指标（确定性快路径，秒级且 100% 可复现），不再走 LLM 生成。"
        style="margin-bottom: 12px"
      />
      <el-descriptions :column="1" border size="small" style="margin-bottom: 12px">
        <el-descriptions-item label="问题">
          {{ promoteForm.question }}
        </el-descriptions-item>
        <el-descriptions-item label="执行 SQL">
          <pre class="promote-sql">{{ promoteForm.sql }}</pre>
        </el-descriptions-item>
        <el-descriptions-item v-if="promoteForm.grounding?.tables?.length" label="召回表">
          <el-tag
            v-for="t in promoteForm.grounding.tables"
            :key="t"
            size="small"
            effect="plain"
            style="margin: 0 3px 4px 0"
          >
            {{ t }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-form :model="promoteForm" label-width="110px" size="default">
        <el-form-item label="指标名称" required>
          <el-input v-model="promoteForm.name" placeholder="如：按品牌摄像头数量" />
        </el-form-item>
        <el-form-item label="指标 key" required>
          <el-input
            v-model="promoteForm.key"
            placeholder="仅字母/数字/下划线，如 camera_by_brand"
          />
        </el-form-item>
        <el-form-item label="同步登记术语">
          <el-switch v-model="promoteForm.bindTerm" />
          <span class="promote-hint">把该问题登记为术语（业务黑话 → 该指标），下次直接命中</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="promoteVisible = false">取消</el-button>
        <el-button type="primary" :loading="promoteLoading" @click="confirmPromote">
          沉淀为指标
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Plus,
  Delete,
  Setting,
  Loading,
  Refresh,
  MagicStick,
  DataBoard,
  Files,
  Search,
} from "@element-plus/icons-vue";
import { getOntObjects } from "@/api/module_ai/ontology";
import ECharts from "@/components/ECharts/index.vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import {
  streamQuery,
  getQuerySessions,
  getQueryMessages,
  deleteQuerySession,
  getQueryMetrics,
  saveQueryMetric,
  deleteQueryMetrics,
  promoteQueryMetric,
  getQueryTerms,
  saveQueryTerm,
  deleteQueryTerms,
  getQueryDatasources,
  saveQueryDatasource,
  deleteQueryDatasources,
  testQueryDatasource,
  syncQueryDatasourceSchema,
  getQueryRoles,
  syncQueryAssets,
  getQueryAssets,
  getQueryAssetColumns,
  saveQueryAsset,
  saveQueryAssetColumn,
  generateQueryAssetDesc,
  inferQueryAssetRelations,
  suggestQueryAssets,
  rebuildQueryKg,
  getQueryKgStats,
  getQueryKgUnified,
  getQueryKgKbs,
  autoLinkQueryKg,
  getQueryConcepts,
  saveQueryConcept,
  deleteQueryConcepts,
  getFdeList,
  saveFdeProposition,
  deleteFdePropositions,
  fdeShadowCheck,
  getQueryObjects,
  getActionList,
  saveAction,
  executeAction,
  getActionLogs,
  getPendingActions,
  getApprovalCenter,
  approveVersionPublish,
  approveAction,
  rejectAction,
  getAssetVersions,
  rollbackAssetVersion,
  getAssetImpact,
  extractQueryObjects,
  getIndustryTemplates,
  applyIndustryTemplate,
  getPipelineList,
  getPipelineGraph,
  savePipeline,
  runPipeline,
  getPipelineData,
  getWorkshopList,
  saveWorkshopApp,
  workshopPreview,
  getAssetLineage,
  getAccessRules,
  getAccessMatrix,
  accessPreview,
  accessPreviewRole,
  saveAccessRule,
  getDqOverview,
  runDq,
  scanAllDq,
  getDqAlert,
  saveDomain,
  getDomainObjects,
  domainReconcile,
  getGovernanceOverview,  getQueryFewshots,
  saveQueryFewshot,
  deleteQueryFewshots,
  getQueryStats,
  getQuerySettings,
  saveQuerySetting,
  queryFeedback,
  runQueryBenchmark,
  getQueryBenchmarkStatus,
} from "@/api/module_ai/query";

defineOptions({ name: "AiQuery" });

const examples = [
  "今天告警数",
  "本月告警数",
  "在线摄像头数",
  "训练任务总数",
  "近7天模型调用量",
  "系统用户数",
];

const datasource = ref("system");
const datasources = ref<any[]>([]);
const sessions = ref<any[]>([]);
const currentSession = ref<number | null>(null);
const messages = ref<any[]>([]);
const input = ref("");
const loading = ref(false);
const chatRef = ref();

async function loadDatasources() {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
}
async function loadSessions() {
  try {
    const r = await getQuerySessions();
    sessions.value = r.data?.data || [];
  } catch {
    sessions.value = [];
  }
}
async function openSession(id: number) {
  currentSession.value = id;
  try {
    const r = await getQueryMessages(id);
    messages.value = (r.data?.data || []).map((m: any) => ({ ...m, _showSql: false }));
    scrollBottom();
  } catch {
    messages.value = [];
  }
}
async function newSession() {
  currentSession.value = null;
  messages.value = [];
}
async function removeSession(id: number) {
  try {
    await ElMessageBox.confirm("确认删除该会话？删除后不可恢复。", "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }
  await deleteQuerySession(id);
  if (currentSession.value === id) newSession();
  loadSessions();
}
function onDsChange(v: any) {
  if (v === "__manage__") {
    openOps();
    datasource.value = "system";
    return;
  }
  datasource.value = v;
}
function quickAsk(q: string) {
  input.value = q;
  send();
}
async function send() {
  const q = (input.value || "").trim();
  if (!q || loading.value) return;
  const ds = datasource.value === "__manage__" ? "system" : datasource.value;
  input.value = "";
  loading.value = true;
  const m: any = reactive({
    id: `tmp-${Date.now()}`,
    question: q,
    path: "slow",
    _showSql: false,
    _running: true,
    // 打字机：_reasoningBuf/_sqlBuf 累积原始流，_reasoning/_sqlLive 为已逐字reveal的显示态
    _reasoningBuf: "",
    _reasoning: "",
    _sqlBuf: "",
    _sqlLive: "",
    _trace: [] as any[],
    sql: "",
    columns: [] as string[],
    rows: [] as any[][],
    summary: "",
    is_error: false,
  });
  messages.value.push(m);
  scrollBottom();
  // 打字机 reveal：逐帧匀速把 buf 字符reveal到显示态；流结束后继续吐剩余积压，避免跳变
  const REVEAL_PER_FRAME = 6;
  let rafId = 0;
  const tick = () => {
    let changed = false;
    if (m._reasoning.length < m._reasoningBuf.length) {
      m._reasoning = m._reasoningBuf.slice(0, m._reasoning.length + REVEAL_PER_FRAME);
      changed = true;
    }
    if (m._sqlLive.length < m._sqlBuf.length) {
      m._sqlLive = m._sqlBuf.slice(0, m._sqlLive.length + REVEAL_PER_FRAME);
      changed = true;
    }
    if (changed) scrollBottom();
    const caught =
      m._reasoning.length >= m._reasoningBuf.length && m._sqlLive.length >= m._sqlBuf.length;
    if (!caught || m._running) {
      rafId = requestAnimationFrame(tick);
    } else {
      rafId = 0;
    }
  };
  const ensureTick = () => {
    if (!rafId) rafId = requestAnimationFrame(tick);
  };
  try {
    for await (const ev of streamQuery({
      question: q,
      session_id: currentSession.value,
      datasource: ds,
    })) {
      const d = ev.data || {};
      switch (ev.type) {
        case "meta":
          if (d.session_id) {
            currentSession.value = d.session_id;
          }
          break;
        case "reasoning_start":
          m._reasoningBuf = "";
          m._reasoning = "";
          break;
        case "reasoning":
          m._reasoningBuf += d.delta || "";
          ensureTick();
          break;
        case "tool_start":
          m._trace.push({ kind: "tool_start", name: d.name, args: d.args });
          break;
        case "tool_result":
          m._trace.push({ kind: "tool_result", name: d.name, result: d.result });
          break;
        case "tool_error":
          m._trace.push({ kind: "tool_error", name: d.name, error: d.error });
          break;
        case "sql_delta":
          m._sqlBuf += d.delta || "";
          ensureTick();
          break;
        case "sql_final":
          m._sqlBuf = d.sql || "";
          m.sql = d.sql || "";
          ensureTick();
          break;
        case "result":
          m.columns = d.columns || [];
          m.rows = d.rows || [];
          m.ontology_used = d.ontology_used || m.ontology_used || [];
          m.retrieved = d.retrieved || m.retrieved || null;
          m.dq_warning = d.dq_warning || m.dq_warning || null;
          m.confidence = d.confidence ?? m.confidence ?? null;
          m.evidence = d.evidence || m.evidence || null;
          ensureTick();
          break;
        case "answer":
          m.summary = d.summary || "";
          break;
        case "done":
          m._running = false;
          ensureTick();
          break;
        case "error":
          m.is_error = true;
          m.summary = d.message || "查询失败";
          break;
      }
      scrollBottom();
    }
    m._running = false;
    ensureTick();
    loadSessions();
  } catch (e: any) {
    m.is_error = true;
    m.summary = e?.msg || e?.message || "查询失败";
    m._running = false;
    ensureTick();
  } finally {
    m._running = false;
    loading.value = false;
    scrollBottom();
  }
}
function rowsToItems(m: any) {
  return (m.rows || []).map((row: any[], i: number) => {
    const o: Record<string, any> = { __index: i };
    (m.columns || []).forEach((c: string, ci: number) => (o[c] = row[ci]));
    return o;
  });
}
function toggleSql(m: any) {
  m._showSql = !m._showSql;
}

// ---- 沉淀为指标（FDE 复用闭环） ----
const promoteVisible = ref(false);
const promoteLoading = ref(false);
const promoteForm = reactive<any>({ message_id: 0, question: "", sql: "", grounding: null, name: "", key: "", bindTerm: true });
function openPromote(m: any) {
  promoteForm.message_id = m.id;
  promoteForm.question = m.question || "";
  promoteForm.sql = m.sql || "";
  promoteForm.grounding = m.grounding || null;
  promoteForm.name = m.question || "";
  // 由问题生成建议 key：取中文/字母数字，转下划线
  promoteForm.key = (m.question || "")
    .replace(/[^\u4e00-\u9fa5A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40) || "query_metric";
  promoteForm.bindTerm = true;
  promoteVisible.value = true;
}
async function confirmPromote() {
  if (!promoteForm.name || !promoteForm.key) {
    ElMessage.warning("请填写指标名称与 key");
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(promoteForm.key)) {
    ElMessage.warning("指标 key 仅允许字母/数字/下划线");
    return;
  }
  promoteLoading.value = true;
  try {
    const res = await promoteQueryMetric({
      message_id: promoteForm.message_id,
      name: promoteForm.name,
      key: promoteForm.key,
    });
    promoteVisible.value = false;
    ElMessage.success(`已沉淀为可复用指标「${res?.data?.name || promoteForm.name}」`);
    await loadMetrics(); // 刷新指标列表
  } catch (e: any) {
    ElMessage.error(e?.message || "沉淀失败");
  } finally {
    promoteLoading.value = false;
  }
}

// ---- 可视化 ----
function showChart(m: any) {
  return !m.is_error && (m.columns || []).length >= 2 && (m.rows || []).length >= 2;
}
function isNumeric(v: any) {
  return typeof v === "number" || (typeof v === "string" && v !== "" && !Number.isNaN(Number(v)));
}
const chartOption = (m: any) => {
  const cols = m.columns || [];
  const rows = m.rows || [];
  const xData = rows.map((r: any[]) => String(r[0]));
  const series = cols.slice(1).map((c: string, ci: number) => ({
    name: String(c),
    type: "bar",
    barMaxWidth: 30,
    data: rows.map((r: any[]) => Number(r[ci + 1]) || 0),
  }));
  const allNum = series.length > 0 && rows.every((r: any[]) => isNumeric(r[1]));
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: "category",
      data: xData,
      axisLabel: { interval: 0, rotate: xData.length > 8 ? 30 : 0 },
    },
    yAxis: { type: "value" },
    series: allNum ? series : [],
  };
};

// ---- 导出 CSV ----
function exportCsv(m: any) {
  const cols = m.columns || [];
  const rows = m.rows || [];
  const escape = (v: any) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [cols.map(escape).join(","), ...rows.map((r: any[]) => r.map(escape).join(","))];
  const blob = new Blob(["\uFEFF" + lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `问数结果_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "")}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}
async function feedback(m: any, fb: string) {
  if (m.id == null || String(m.id).startsWith("tmp") || String(m.id).startsWith("err")) return;
  await queryFeedback({ message_id: m.id, feedback: fb });
  ElMessage.success("感谢反馈");
}
function scrollBottom() {
  nextTick(() => {
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight;
  });
}

// ---- 指标运营 ----
const opsVisible = ref(false);
const opsTab = ref("metric");
const metrics = ref<any[]>([]);
const terms = ref<any[]>([]);
const saving = ref(false);
async function loadMetrics() {
  const r = await getQueryMetrics({});
  metrics.value = r.data?.data || [];
}
async function loadTerms() {
  const r = await getQueryTerms({});
  terms.value = r.data?.data || [];
}
async function openOps() {
  opsVisible.value = true;
  loadMetrics();
  loadTerms();
  loadFewshots();
  loadStats();
  loadSettings();
  loadAssets();
}
const metricEditVisible = ref(false);
const metricForm = reactive<any>({});
function emptyMetric() {
  return {
    id: undefined,
    datasource: datasource.value === "system" ? "system" : datasource.value,
    key: "",
    name: "",
    description: "",
    sql_template: "",
    params: [],
    dimensions: [],
    agg: "count",
    unit: "",
    permission_tag: "",
    enabled: true,
    sort: 0,
    cache_ttl: 0,
  };
}
function openMetricEdit(row?: any) {
  if (row) Object.assign(metricForm, row);
  else Object.assign(metricForm, emptyMetric());
  metricEditVisible.value = true;
}
async function saveMetric(row: any) {
  if (!row.name || !row.key || !row.sql_template) {
    ElMessage.warning("请填写名称、key 与 SQL 模板");
    return;
  }
  saving.value = true;
  try {
    await saveQueryMetric({
      datasource: row.datasource || "system",
      key: row.key,
      name: row.name,
      description: row.description || "",
      sql_template: row.sql_template,
      params: row.params || [],
      dimensions: row.dimensions || [],
      agg: row.agg || "count",
      unit: row.unit || "",
      permission_tag: row.permission_tag || "",
      enabled: row.enabled !== false,
      sort: row.sort || 0,
      cache_ttl: row.cache_ttl || 0,
    });
    ElMessage.success("已保存");
    metricEditVisible.value = false;
    loadMetrics();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}
async function removeMetric(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除指标「${row.name}」？`, "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }
  await deleteQueryMetrics([row.id]);
  loadMetrics();
}

// ---- 术语 ----
const termEditVisible = ref(false);
const termForm = reactive<any>({});
function openTermEdit(row?: any) {
  if (row) Object.assign(termForm, row);
  else
    Object.assign(termForm, {
      id: undefined,
      datasource: "system",
      term: "",
      metric_key: "",
      field_path: "",
      type: "metric",
    });
  termEditVisible.value = true;
}
async function saveTerm(row: any) {
  if (!row.term) {
    ElMessage.warning("请填写术语");
    return;
  }
  saving.value = true;
  try {
    await saveQueryTerm({
      datasource: row.datasource || "system",
      term: row.term,
      metric_key: row.metric_key || "",
      field_path: row.field_path || "",
      type: row.type || "term",
    });
    ElMessage.success("已保存");
    termEditVisible.value = false;
    loadTerms();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}
async function removeTerm(row: any) {
  await deleteQueryTerms([row.id]);
  loadTerms();
}

// ---- 数据资产目录 ----
const assets = ref<any[]>([]);
const syncingAssets = ref(false);
const assetSearch = ref("");
const assetView = ref("card");
const dsView = ref("card");
const filteredAssets = computed(() => {
  const q = (assetSearch.value || "").trim().toLowerCase();
  if (!q) return assets.value;
  return assets.value.filter(
    (a) =>
      (a.table_name || "").toLowerCase().includes(q) ||
      (a.alias || "").toLowerCase().includes(q) ||
      (a.domain || "").toLowerCase().includes(q)
  );
});
async function loadAssets() {
  try {
    const r = await getQueryAssets();
    assets.value = r.data?.data || [];
  } catch {
    assets.value = [];
  }
}
async function syncAssets() {
  syncingAssets.value = true;
  try {
    const r = await syncQueryAssets();
    const d = r.data?.data || {};
    ElMessage.success(`同步完成：${d.tables ?? 0} 表 / ${d.columns ?? 0} 字段`);
    loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "同步失败");
  } finally {
    syncingAssets.value = false;
  }
}
const generatingDesc = ref(false);
async function generateDesc(force = false) {
  generatingDesc.value = true;
  try {
    const r = await generateQueryAssetDesc(force);
    const d = r.data?.data || {};
    ElMessage.success(`已生成：${d.tables ?? 0} 表 / ${d.columns ?? 0} 字段描述，请人工校对`);
    loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "生成失败");
  } finally {
    generatingDesc.value = false;
  }
}
const rebuildingKg = ref(false);
const kgStats = ref<any>(null);
async function rebuildKg() {
  rebuildingKg.value = true;
  try {
    const r = await rebuildQueryKg();
    kgStats.value = r.data?.data || null;
    ElMessage.success(
      `知识图谱已重建：${kgStats.value?.nodes ?? 0} 节点 / ${kgStats.value?.edges ?? 0} 边`
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || "重建知识图谱失败");
  } finally {
    rebuildingKg.value = false;
  }
}
async function loadKgStats() {
  try {
    const r = await getQueryKgStats();
    kgStats.value = r.data?.data || null;
  } catch {
    /* 静默 */
  }
}
// ---- 统一图谱（数据schema图 + 知识库图）----
const kgScope = ref("all");
const kgKb = ref<number | null>(null);
const kgKbs = ref<any[]>([]);
const kgNodes = ref<any[]>([]);
const kgEdges = ref<any[]>([]);
const loadingKg = ref(false);
async function loadUnifiedGraph() {
  loadingKg.value = true;
  try {
    const r = await getQueryKgUnified(kgKb.value, kgScope.value);
    const d = r.data?.data || {};
    kgNodes.value = d.nodes || [];
    kgEdges.value = d.edges || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载图谱失败");
  } finally {
    loadingKg.value = false;
  }
}
async function loadKgKbs() {
  try {
    const r = await getQueryKgKbs();
    kgKbs.value = r.data?.data || [];
  } catch {
    /* 静默 */
  }
}
const linkingKg = ref(false);
async function autoLinkKg() {
  linkingKg.value = true;
  try {
    const r = await autoLinkQueryKg();
    ElMessage.success(`已自动打边 ${r.data?.data?.linked ?? 0} 条`);
    loadUnifiedGraph();
  } catch (e: any) {
    ElMessage.error(e?.msg || "自动打边失败");
  } finally {
    linkingKg.value = false;
  }
}
// ---- 本体/概念 ----
const concepts = ref<any[]>([]);
const industryTpl = ref("");
const industryTemplates = ref<any[]>([]);
const applyingTpl = ref(false);
async function loadIndustryTemplates() {
  try {
    const r = await getIndustryTemplates();
    industryTemplates.value = r.data?.data || [];
  } catch {
    industryTemplates.value = [];
  }
}
async function applyTpl() {
  if (!industryTpl.value) return ElMessage.warning("请选择行业模板");
  applyingTpl.value = true;
  try {
    const r = await applyIndustryTemplate(industryTpl.value);
    const d = r.data?.data || {};
    ElMessage.success(`已应用「${d.template}」，预建 ${d.created ?? 0} 个标准概念`);
    loadConcepts();
  } catch (e: any) {
    ElMessage.error(e?.msg || "应用失败");
  } finally {
    applyingTpl.value = false;
  }
}
const conceptDialog = ref(false);
const conceptForm = reactive<any>({
  id: null,
  name: "",
  description: "",
  synonyms: "",
  parent_name: "",
  domain: "",
  metric_key: "",
  tables: [],
});
const savingConcept = ref(false);
async function loadConcepts() {
  try {
    const r = await getQueryConcepts();
    concepts.value = r.data?.data || [];
  } catch {
    /* 静默 */
  }
}
function openConceptEdit(row?: any) {
  Object.assign(
    conceptForm,
    row || {
      id: null,
      name: "",
      description: "",
      synonyms: "",
      parent_name: "",
      domain: "",
      metric_key: "",
      tables: [],
    }
  );
  conceptDialog.value = true;
}
async function saveConcept() {
  if (!conceptForm.name?.trim()) {
    ElMessage.warning("概念名称不能为空");
    return;
  }
  savingConcept.value = true;
  try {
    await saveQueryConcept({ ...conceptForm, tables: conceptForm.tables || [] });
    ElMessage.success("概念已保存");
    conceptDialog.value = false;
    loadConcepts();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingConcept.value = false;
  }
}
async function deleteConcept(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认删除概念「${row.name}」？删除后该概念将不再注入问数上下文。`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await deleteQueryConcepts([row.id]);
    ElMessage.success("已删除");
    loadConcepts();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}
// ---- FDE 交付工作台 ----
const fdList = ref<any[]>([]);
const fdDialog = ref(false);
const fdForm = reactive<any>({
  id: null,
  title: "",
  description: "",
  criteria: "",
  owner: "",
  status: "open",
  steps: {
    diagnosis: "todo",
    modeling: "todo",
    assembly: "todo",
    shadow: "todo",
    handover: "todo",
  },
  gap: [],
  delivery_assets: [],
});
async function loadFde() {
  try {
    const r = await getFdeList();
    fdList.value = r.data?.data || [];
  } catch {
    fdList.value = [];
  }
}
function openFdeEdit(row?: any) {
  Object.assign(
    fdForm,
    row
      ? {
          ...row,
          steps: row.steps || fdForm.steps,
          gap: row.gap || [],
          delivery_assets: row.delivery_assets || [],
        }
      : {
          id: null,
          title: "",
          description: "",
          criteria: "",
          owner: "",
          status: "open",
          steps: {
            diagnosis: "todo",
            modeling: "todo",
            assembly: "todo",
            shadow: "todo",
            handover: "todo",
          },
          gap: [],
          delivery_assets: [],
          fde_translator: "",
          fde_data: "",
          fde_app: "",
          shadow_metric: "",
          shadow_golden: "",
          shadow_tolerance: "",
          shadow_result: "",
          shadow_actual: "",
        }
  );
  fdDialog.value = true;
}
async function runFdeShadow(row: any) {
  try {
    const r = await fdeShadowCheck(row.id);
    const d = r.data?.data || {};
    if (!d.ok) return ElMessage.error(d.msg || "校验失败");
    ElMessage[d.result === "pass" ? "success" : "error"](
      "影子运行 " + d.result.toUpperCase() + "，实测 " + d.actual + " vs 黄金 " + d.golden
    );
    loadFde();
  } catch (e: any) {
    ElMessage.error(e?.msg || "校验失败");
  }
}
async function saveFde() {
  if (!fdForm.title?.trim()) return ElMessage.warning("请输入命题标题");
  try {
    await saveFdeProposition({ ...fdForm });
    ElMessage.success("已保存");
    fdDialog.value = false;
    loadFde();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
async function deleteFde(row: any) {
  try {
    await ElMessageBox.confirm(`确认删除命题「${row.title}」？`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deleteFdePropositions([row.id]);
    ElMessage.success("已删除");
    loadFde();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}
// ---- Action(写回+审计) ----
const actions = ref<any[]>([]);
const actionLogs = ref<any[]>([]);
const actionDialog = ref(false);
const actionForm = reactive<any>({
  id: null,
  name: "",
  object_table: "",
  writable_cols: [],
  writable_by_role: [],
  validation: "",
  approve: true,
  enabled: true,
});
const runDialog = ref(false);
const runForm = reactive<any>({ name: "", object_key: "", params: {}, approve: false });
async function loadActions() {
  try {
    const r = await getActionList();
    actions.value = r.data?.data || [];
  } catch {
    actions.value = [];
  }
}
async function loadActionLogs() {
  try {
    const r = await getActionLogs();
    actionLogs.value = r.data?.data || [];
  } catch {
    actionLogs.value = [];
  }
}
const pendingActions = ref<any[]>([]);
const approvingId = ref<number | null>(null);
async function loadPendingActions() {
  try {
    const r = await getPendingActions();
    pendingActions.value = r.data?.data || [];
  } catch {
    pendingActions.value = [];
  }
}
const approvalCenter = ref<any>({ actions: [], versions: [], total: 0 });
async function loadApprovalCenter() {
  try {
    const r = await getApprovalCenter();
    approvalCenter.value = r.data?.data || { actions: [], versions: [], total: 0 };
  } catch {
    approvalCenter.value = { actions: [], versions: [], total: 0 };
  }
}
async function approveVersion(row: any) {
  try {
    await ElMessageBox.confirm(`批准发布本体对象「${row.object_code}」？`, "审批确认", { type: "warning", confirmButtonText: "批准发布", cancelButtonText: "取消" });
  } catch { return; }
  try {
    const r = await approveVersionPublish(row.id);
    if (r.data?.ok) ElMessage.success("已批准发布"); else ElMessage.error(r.data?.msg || "批准失败");
  } catch (e: any) { ElMessage.error(e?.message || "批准失败"); }
  await loadApprovalCenter();
}
async function doApprove(row: any) {
  try {
    await ElMessageBox.confirm(
      `批准执行动作「${row.action}」→ ${row.table}#${row.key}？将真实写回数据并留痕。`,
      "审批确认",
      { type: "warning", confirmButtonText: "批准并执行", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  approvingId.value = row.id;
  try {
    const r = await approveAction({ approval_id: row.id });
    if (r.data?.ok) {
      ElMessage.success(r.data.msg || "已批准");
    } else {
      ElMessage.error(r.data?.msg || "审批失败");
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "审批失败");
  } finally {
    approvingId.value = null;
    await loadPendingActions();
    await loadActionLogs();
  }
}
async function doReject(row: any) {
  try {
    await ElMessageBox.confirm(`驳回动作「${row.action}」#${row.key}？`, "驳回确认", {
      type: "warning",
      confirmButtonText: "驳回",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    const r = await rejectAction({ approval_id: row.id });
    ElMessage.success(r.data?.msg || "已驳回");
  } catch (e: any) {
    ElMessage.error(e?.message || "驳回失败");
  }
  await loadPendingActions();
}
function openActionEdit(row?: any) {
  const src = row || {
    id: null,
    name: "",
    object_table: "",
    writable_cols: [],
    validation: "",
    approve: true,
    enabled: true,
  };
  const wrMap = src.writable_by_role || {};
  const wrArr = Object.entries(wrMap).map(([role, cols]) => ({ role, cols: cols || [] }));
  Object.assign(actionForm, src, { writable_by_role: wrArr, id: src.id, name: src.name });
  actionDialog.value = true;
}
function addRoleWritable() {
  actionForm.writable_by_role.push({ role: "", cols: [] });
}
function removeRoleWritable(idx: number) {
  actionForm.writable_by_role.splice(idx, 1);
}
function normalizeRoleWritable() {
  // 忽略空角色：提交时由 saveActionFn 转 {role: []}
}
async function saveActionFn() {
  if (!actionForm.name?.trim() || !actionForm.object_table?.trim())
    return ElMessage.warning("请填写名称和目标对象");
  // [{role,cols}] → {role: [cols]}
  const writableByRole: Record<string, string[]> = {};
  for (const rw of actionForm.writable_by_role || []) {
    if (rw.role?.trim()) writableByRole[rw.role.trim()] = (rw.cols || []).map((c: string) => c);
  }
  try {
    await saveAction({ ...actionForm, writable_by_role: writableByRole });
    ElMessage.success("已保存");
    actionDialog.value = false;
    loadActions();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
function openActionRun(row: any) {
  Object.assign(runForm, {
    name: row.name,
    object_table: row.object_table,
    object_key: "",
    params: {},
    approve: false,
  });
  // 为可写字段初始化空值输入
  runForm.params = Object.fromEntries((row.writable_cols || []).map((c: string) => [c, ""]));
  runDialog.value = true;
}
async function runActionFn() {
  if (!runForm.object_key?.trim()) return ElMessage.warning("请输入对象关键值");
  try {
    const r = await executeAction({
      name: runForm.name,
      object_key: runForm.object_key,
      params: runForm.params,
      approve: runForm.approve,
    });
    const d = r.data?.data || {};
    if (d.needs_approval) {
      ElMessage.warning("该操作需审批，请勾选“批准执行”后重试");
    } else ElMessage[d.ok ? "success" : "error"](d.msg || "执行完成");
    runDialog.value = false;
    loadActionLogs();
  } catch (e: any) {
    ElMessage.error(e?.msg || "执行失败");
  }
}
// 本体对象映射（用于「使用本体」溯源展示）
const ontMap = ref<any>({});
async function loadOntMap() {
  try {
    const r = await getOntObjects();
    const map: any = {};
    (r.data?.data || []).forEach((o: any) => (map[o.code] = o));
    ontMap.value = map;
  } catch {
    ontMap.value = {};
  }
}
function ontName(m: any) {
  const used = new Set<string>(m.ontology_used || []);
  // 直接从 SQL 扫描 ont_* 表（流式场景兜底）
  if (m.sql) {
    (m.sql.match(/ont_[A-Za-z0-9_]+/g) || []).forEach((t: string) => used.add(t));
  }
  return [...used].filter(Boolean).map((t: string) => {
    const code = t.replace(/^ont_/, "");
    const obj = ontMap.value[code];
    return { table: t, code, name: obj ? obj.name : code };
  });
}
function gotoOntology(o: any) {
  window.location.hash = `#/ai/ontology?code=${encodeURIComponent(o.code || "")}`;
}
// ---- 治理(版本/回滚/影响分析) ----
const govTable = ref("");
const govObjects = ref<any[]>([]);
const govImpact = ref<any>({ metrics: [], incoming_relations: [], object_links: [] });
const govVersions = ref<any[]>([]);
const govLineage = ref<any>(null);
const govLineageGraph = computed(() => {
  const L = govLineage.value || {};
  const nodes: any[] = [];
  const edges: any[] = [];
  const center = govTable.value;
  if (!center) return { nodes, edges };
  nodes.push({ id: center, label: center });
  const seen = new Set<string>([center]);
  const addNode = (id: string, label: string) => {
    if (seen.has(id)) return;
    seen.add(id);
    nodes.push({ id, label });
  };
  const addEdge = (s: string, t: string) => edges.push({ id: `${s}->${t}`, source: s, target: t });
  // 入向关联表 / 依赖对象
  (L.incoming_relations || []).forEach((_r: any, i: number) => {
    const f = _r.from?.table || _r.from || `t${i}`;
    addNode(f, f);
    addEdge(f, center);
  });
  (L.dependent_objects || []).forEach((o: any) => {
    const id = o.object || o.alias;
    addNode(id, o.alias || id);
    addEdge(center, id);
  });
  (L.pipelines || []).forEach((p: any) => {
    const id = `pipe:${p.name}`;
    addNode(id, `管道:${p.name}`);
    addEdge(id, center);
  });
  (L.metrics || []).forEach((m: any) => {
    const id = `metric:${m.key}`;
    addNode(id, m.name || m.key);
    addEdge(center, id);
  });
  (L.concepts || []).forEach((c: any) => {
    const id = `concept:${c.name}`;
    addNode(id, c.name);
    addEdge(center, id);
  });
  return { nodes, edges };
});
async function loadGovObjects() {
  try {
    const r = await getQueryObjects();
    govObjects.value = r.data?.data || [];
  } catch {
    govObjects.value = [];
  }
}
async function loadGov() {
  if (!govTable.value) return;
  try {
    const [imp, ver, lin] = await Promise.all([
      getAssetImpact(govTable.value),
      getAssetVersions(govTable.value),
      getAssetLineage(govTable.value),
    ]);
    govImpact.value = imp.data?.data || { metrics: [], incoming_relations: [], object_links: [] };
    govVersions.value = ver.data?.data || [];
    govLineage.value = lin.data?.data || null;
  } catch {
    govImpact.value = { metrics: [], incoming_relations: [], object_links: [] };
    govVersions.value = [];
  }
}
async function rollGov(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认回滚「${govTable.value}」到版本 ${row.version}？当前改动将被覆盖。`,
      "回滚确认",
      { type: "warning", confirmButtonText: "回滚", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    const r = await rollbackAssetVersion(row.id);
    ElMessage.success(r.data?.data?.msg || "已回滚");
    loadGov();
    loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "回滚失败");
  }
}
const inferringRel = ref(false);
const extractingObj = ref(false);
async function extractObjects() {
  extractingObj.value = true;
  try {
    const r = await extractQueryObjects();
    const d = r.data?.data || {};
    ElMessage.success(`已抽取 ${d.extracted ?? 0} 个业务对象（含别名/名称列消歧）`);
    loadAssets();
    loadGovObjects();
  } catch (e: any) {
    ElMessage.error(e?.msg || "抽取失败");
  } finally {
    extractingObj.value = false;
  }
}
// ---- 数据管道 ----
const pipes = ref<any[]>([]);
const pipeDialog = ref(false);
const pipeForm = reactive<any>({
  id: null,
  name: "",
  source_connection: "",
  source_table: "",
  target_object: "",
  mappings: [],
  enabled: true,
});
async function loadPipes() {
  try {
    const r = await getPipelineList();
    pipes.value = r.data?.data || [];
  } catch {
    pipes.value = [];
  }
}
const pipelineGraph = ref<any>({ nodes: [], edges: [] });
async function loadPipelineGraph() {
  try {
    const r = await getPipelineGraph();
    const g = r.data?.data || { nodes: [], edges: [] };
    // 给节点加预设网格坐标，避免 GraphCanvas 布局把节点放视口外/重叠
    (g.nodes || []).forEach((n: any, i: number) => {
      n.x = (i % 4) * 160;
      n.y = Math.floor(i / 4) * 120;
    });
    pipelineGraph.value = g;
  } catch {
    pipelineGraph.value = { nodes: [], edges: [] };
  }
}
function openPipeEdit(row?: any) {
  Object.assign(
    pipeForm,
    row || {
      id: null,
      name: "",
      source_connection: "",
      source_table: "",
      target_object: "",
      mappings: [],
      enabled: true,
    }
  );
  pipeDialog.value = true;
}
function addPipeMapping() {
  pipeForm.mappings.push({ source_col: "", target_col: "" });
}
async function savePipe() {
  if (!pipeForm.name?.trim() || !pipeForm.source_table?.trim() || !pipeForm.target_object?.trim())
    return ElMessage.warning("请填管道名/源表/目标对象");
  try {
    await savePipeline({ ...pipeForm });
    ElMessage.success("已保存");
    pipeDialog.value = false;
    loadPipes();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
async function runPipe(row: any) {
  try {
    const r = await runPipeline(row.id);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](d.msg || "已运行");
    loadPipes();
  } catch (e: any) {
    ElMessage.error(e?.msg || "运行失败");
  }
}
// P3-⑤ 查看管道落库数据
const pipeData = ref<any>(null);
const pipeDataVisible = ref(false);
async function viewPipeData(row: any) {
  try {
    const r = await getPipelineData(row.id, 20);
    pipeData.value = r.data?.data || {};
    pipeDataVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.msg || "获取数据失败");
  }
}
// ---- Workshop 对象应用 ----
const wsApps = ref<any[]>([]);
const wsDialog = ref(false);
const wsForm = reactive<any>({
  id: null,
  name: "",
  object_table: "",
  view_type: "table",
  columns: [],
  enabled: true,
});
const wsPreview = ref<any>(null);
const wsPreviewVisible = ref(false);
async function loadWorkshop() {
  try {
    const r = await getWorkshopList();
    wsApps.value = r.data?.data || [];
  } catch {
    wsApps.value = [];
  }
}
function openWorkshopEdit(row?: any) {
  Object.assign(
    wsForm,
    row || { id: null, name: "", object_table: "", view_type: "table", columns: [], enabled: true }
  );
  wsDialog.value = true;
}
async function saveWorkshop() {
  if (!wsForm.name?.trim() || !wsForm.object_table?.trim())
    return ElMessage.warning("请填写应用名/对象");
  try {
    await saveWorkshopApp({ ...wsForm });
    ElMessage.success("已保存");
    wsDialog.value = false;
    loadWorkshop();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
async function previewWorkshop(row: any) {
  try {
    const r = await workshopPreview(row.id, 20);
    wsPreview.value = r.data?.data || {};
    wsPreviewVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.msg || "预览失败");
  }
}
// ---- ABAC 权限策略 ----
const accessRules = ref<any[]>([]);
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
async function loadAccessRules() {
  try {
    const r = await getAccessRules();
    accessRules.value = r.data?.data || [];
  } catch {
    accessRules.value = [];
  }
}
const accessMatrix = ref<any[]>([]);
async function loadAccessMatrix() {
  try {
    const r = await getAccessMatrix();
    accessMatrix.value = r.data?.data?.roles || [];
  } catch {
    accessMatrix.value = [];
  }
}
const previewUserId = ref(1);
const preview = ref<any>(null);
const previewLoading = ref(false);
async function loadPreview() {
  previewLoading.value = true;
  try {
    const r = await accessPreview(previewUserId.value || 0);
    preview.value = r.data?.data || null;
  } catch (e: any) {
    preview.value = null;
    ElMessage.error(e?.message || "预览失败");
  } finally {
    previewLoading.value = false;
  }
}
const rolePreview = ref<any>(null);
async function previewRole(row: any) {
  try {
    const r = await accessPreviewRole(row.code);
    rolePreview.value = r.data?.data || null;
  } catch (e: any) {
    rolePreview.value = null;
    ElMessage.error(e?.message || "预览失败");
  }
}
function metricAccess(m: any) {
  // 指标权限影响：sql_template 涉及的表，若存在「受限」角色（accessMatrix restricted）的表 → 受限
  const sql = m.sql_template || "";
  const tables = (sql.match(/\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)/gi) || []).map((x: string) =>
    x.replace(/\b(?:from|join)\s+/i, "")
  );
  const restricted = new Set<string>();
  for (const role of accessMatrix.value || []) {
    if (role.restricted) (role.tables || []).forEach((t: string) => restricted.add(t));
  }
  const hit = tables.filter((t: string) => restricted.has(t));
  return { restricted: hit.length > 0, tables: hit };
}
function openAccessEdit(row?: any) {
  Object.assign(
    accessForm,
    row || {
      id: null,
      name: "",
      attribute: "role",
      value: "",
      allowed_tables: [],
      sensitive_ok: false,
      enabled: true,
    }
  );
  accessDialog.value = true;
}
async function saveAccess(row: any) {
  if (!(row?.name || "").trim() || !(row?.value || "").trim())
    return ElMessage.warning("请填写策略名/属性值");
  try {
    await saveAccessRule({ ...row });
    ElMessage.success("已保存");
    accessDialog.value = false;
    loadAccessRules();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
// ---- P3-⑦ 数据质量 DQ ----
const dqData = ref<any>({ avg_score: 0, healthy: 0, risk: 0, items: [] });
const dqScanning = ref(false);
async function loadDq() {
  try {
    const r = await getDqOverview();
    dqData.value = r.data?.data || { avg_score: 0, healthy: 0, risk: 0, items: [] };
  } catch {
    dqData.value = { avg_score: 0, healthy: 0, risk: 0, items: [] };
  }
}
async function scanAllDqSync() {
  dqScanning.value = true;
  try {
    await scanAllDq();
    ElMessage.success("已全量扫描");
    await loadDq();
    await loadDqAlert();
  } catch (e: any) {
    ElMessage.error(e?.msg || "扫描失败");
  } finally {
    dqScanning.value = false;
  }
}
async function scanDq(row: any) {
  try {
    const r = await runDq(row.table);
    const d = r.data?.data || {};
    ElMessage[d.ok ? "success" : "error"](d.ok ? `${row.alias} 扫描完成，得分 ${d.score}` : d.msg);
    loadDq();
  } catch (e: any) {
    ElMessage.error(e?.msg || "扫描失败");
  }
}
// ---- P3-⑧ DQ 预警 ----
const dqAlerts = ref<any[]>([]);
async function loadDqAlert() {
  try {
    const r = await getDqAlert();
    dqAlerts.value = r.data?.data?.alerts || [];
  } catch {
    dqAlerts.value = [];
  }
}
// ---- P3-⑨ 数据域 ----
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
const domainView = ref<any>({ domains: [], unassigned: [], total_objects: 0 });
async function loadDomains() {
  try {
    const r = await getDomainObjects();
    domainView.value = r.data?.data || { domains: [], unassigned: [], total_objects: 0 };
  } catch {
    domainView.value = { domains: [], unassigned: [], total_objects: 0 };
  }
}
const reconcileResult = ref<any>(null);
const reconciling = ref(false);
async function loadReconcile() {
  reconciling.value = true;
  try {
    const r = await domainReconcile();
    reconcileResult.value = r.data?.data || null;
  } catch {
    reconcileResult.value = null;
  } finally {
    reconciling.value = false;
  }
}
function openDomainEdit(d?: any) {
  Object.assign(
    domainForm,
    d || { id: null, name: "", code: "", description: "", tables: [], members: [], enabled: true }
  );
  domainDialog.value = true;
}
async function saveDomainForm() {
  if (!domainForm.name?.trim()) return ElMessage.warning("请填写域名称");
  try {
    await saveDomain({ ...domainForm });
    ElMessage.success("已保存");
    domainDialog.value = false;
    loadDomains();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
function onOpsTabClick(tab: any) {
  const name = tab?.name || tab?.paneName || tab?.props?.name || "";
  if (name === "dq") {
    loadDq();
    loadDqAlert();
  } else if (name === "domain") {
    loadDomains();
  } else if (name === "action") {
    loadPendingActions();
  } else if (name === "access") {
    loadAccessRules();
    loadAccessMatrix();
  } else if (name === "pipeline") {
    loadPipes();
    loadPipelineGraph();
  } else if (name === "approval") {
    loadApprovalCenter();
  }
}
watch(opsTab, async (v) => {
  if (v === "dq") {
    await loadDq();
    await loadDqAlert();
  } else if (v === "domain") {
    loadDomains();
  } else if (v === "action") {
    await loadPendingActions();
  } else if (v === "access") {
    loadAccessRules();
    loadAccessMatrix();
  } else if (v === "pipeline") {
    loadPipes();
    loadPipelineGraph();
  } else if (v === "approval") {
    loadApprovalCenter();
  }
});
// ---- P3-⑩ 治理驾驶舱 ----
const govDashVisible = ref(false);
const govDashLoading = ref(false);
const gov = ref<any>({ overview: {} });
function openGovDashboard() {
  govDashVisible.value = true;
  loadGovDash();
}
async function loadGovDash() {
  govDashLoading.value = true;
  try {
    const r = await getGovernanceOverview();
    gov.value = { overview: r.data?.data || {} };
  } catch {
    gov.value = { overview: {} };
  } finally {
    govDashLoading.value = false;
  }
}
async function inferRel() {
  inferringRel.value = true;
  try {
    const r = await inferQueryAssetRelations();
    const d = r.data?.data || {};
    ElMessage.success(`已推断 ${d.relations ?? 0} 处字段关联，请人工校对`);
    loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "推断失败");
  } finally {
    inferringRel.value = false;
  }
}
async function saveAsset(row: any) {
  try {
    await saveQueryAsset({
      table_name: row.table_name,
      alias: row.alias || "",
      domain: row.domain || "",
      description: row.description || "",
      business_scenarios: row.business_scenarios || "",
      included: row.included,
      remark: row.remark || "",
      object_enabled: !!row.object_enabled,
      object_key_col: row.object_key_col || "id",
      object_name_col: row.object_name_col || "name",
      object_icon: row.object_icon || "el-icon-Box",
    });
    ElMessage.success(`已保存「${row.table_name}」`);
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
const assetEditVisible = ref(false);
const assetForm = reactive<any>({});
function openAssetEdit(row: any) {
  Object.assign(assetForm, row);
  assetEditVisible.value = true;
}
async function saveAssetMeta() {
  try {
    await saveQueryAsset({
      table_name: assetForm.table_name,
      alias: assetForm.alias || "",
      domain: assetForm.domain || "",
      description: assetForm.description || "",
      business_scenarios: assetForm.business_scenarios || "",
      included: assetForm.included,
      remark: assetForm.remark || "",
    });
    ElMessage.success("已保存表元数据");
    assetEditVisible.value = false;
    loadAssets();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
const assetColumnsVisible = ref(false);
const assetColumns = ref<any[]>([]);
const assetColumnsTable = ref("");
const assetColumnSearch = ref("");
const filteredAssetColumns = computed(() => {
  const q = (assetColumnSearch.value || "").trim().toLowerCase();
  if (!q) return assetColumns.value;
  return assetColumns.value.filter(
    (c) =>
      (c.column_name || "").toLowerCase().includes(q) ||
      (c.description || "").toLowerCase().includes(q) ||
      (c.related_table || "").toLowerCase().includes(q)
  );
});
async function openAssetColumns(row: any) {
  assetColumnsTable.value = row.table_name;
  assetColumnSearch.value = "";
  try {
    const r = await getQueryAssetColumns(row.table_name);
    assetColumns.value = r.data?.data || [];
  } catch {
    assetColumns.value = [];
  }
  assetColumnsVisible.value = true;
}
async function saveAssetColumn(col: any) {
  try {
    await saveQueryAssetColumn({
      table_name: assetColumnsTable.value,
      column_name: col.column_name,
      description: col.description || "",
      business_scenarios: col.business_scenarios || "",
      related_table: col.related_table || "",
      related_field: col.related_field || "",
      included: col.included,
      sensitive: col.sensitive,
    });
    ElMessage.success(`字段「${col.column_name}」已保存`);
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}
const colEditVisible = ref(false);
const colForm = reactive<any>({});
function openColEdit(row: any) {
  Object.assign(colForm, row, { table_name: assetColumnsTable.value });
  colEditVisible.value = true;
}
async function saveColMeta() {
  try {
    await saveQueryAssetColumn({
      table_name: assetColumnsTable.value,
      column_name: colForm.column_name,
      description: colForm.description || "",
      business_scenarios: colForm.business_scenarios || "",
      related_table: colForm.related_table || "",
      related_field: colForm.related_field || "",
      included: colForm.included,
      sensitive: colForm.sensitive,
    });
    ElMessage.success("已保存字段元数据");
    colEditVisible.value = false;
    await openAssetColumns({ table_name: assetColumnsTable.value });
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  }
}

// ---- 智能推荐 ----
const suggesting = ref(false);
const suggested = ref<any>({ metrics: [], terms: [] });
async function loadSuggest() {
  suggesting.value = true;
  try {
    const r = await suggestQueryAssets();
    suggested.value = r.data?.data || { metrics: [], terms: [] };
    if (!suggested.value.metrics?.length && !suggested.value.terms?.length) {
      ElMessage.warning("暂无建议，可先同步/维护数据资产描述");
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "生成失败");
  } finally {
    suggesting.value = false;
  }
}
async function adoptSugMetric(row: any) {
  const key = (row.name || "").replace(/[^a-z0-9_]/gi, "_").toLowerCase() || `metric_${Date.now()}`;
  try {
    await saveQueryMetric({
      datasource: "system",
      key,
      name: row.name,
      description: row.description || "智能推荐",
      sql_template: (row.sql || "").includes("SELECT")
        ? row.sql
        : `SELECT COUNT(*) AS 数值 FROM ${row.sql}`,
      params: [],
      dimensions: [],
      agg: row.agg || "count",
      unit: row.unit || "",
      enabled: true,
      sort: 0,
      cache_ttl: 0,
    });
    ElMessage.success(`已采纳指标「${row.name}」`);
    loadMetrics();
  } catch (e: any) {
    ElMessage.error(e?.msg || "采纳失败");
  }
}
async function adoptSugTerm(row: any) {
  try {
    await saveQueryTerm({
      datasource: "system",
      term: row.term,
      metric_key: "",
      field_path: row.target || "",
      type: row.type === "dimension" ? "dimension" : "metric",
    });
    ElMessage.success(`已采纳术语「${row.term}」`);
    loadTerms();
  } catch (e: any) {
    ElMessage.error(e?.msg || "采纳失败");
  }
}

// ---- 示例工程（few-shot）----
const fewshots = ref<any[]>([]);
async function loadFewshots() {
  try {
    const r = await getQueryFewshots({});
    fewshots.value = r.data?.data || [];
  } catch {
    fewshots.value = [];
  }
}
const fewshotEditVisible = ref(false);
const fewshotForm = reactive<any>({});
function openFewshotEdit(row?: any) {
  if (row) Object.assign(fewshotForm, row);
  else
    Object.assign(fewshotForm, {
      id: undefined,
      datasource: "system",
      question: "",
      sql: "",
      enabled: true,
    });
  fewshotEditVisible.value = true;
}
async function saveFewshot(row: any) {
  if (!row.question || !row.sql) {
    ElMessage.warning("请填写问题与正确 SQL");
    return;
  }
  saving.value = true;
  try {
    await saveQueryFewshot({
      datasource: row.datasource || "system",
      question: row.question,
      sql: row.sql,
      enabled: row.enabled !== false,
    });
    ElMessage.success("已保存");
    fewshotEditVisible.value = false;
    loadFewshots();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}
async function removeFewshot(row: any) {
  await deleteQueryFewshots([row.id]);
  loadFewshots();
}

// ---- 反馈统计 / 限额 ----
const stats = ref({ total: 0, fast: 0, slow: 0, errors: 0 });
async function loadStats() {
  try {
    const r = await getQueryStats();
    stats.value = r.data?.data || stats.value;
  } catch {
    /* 忽略 */
  }
}
const settingsForm = reactive<any>({});
const savingSettings = ref(false);
async function loadSettings() {
  try {
    const r = await getQuerySettings();
    const d = r.data?.data || {};
    settingsForm.query_max_rows = Number(d.query_max_rows || 1000);
    settingsForm.query_timeout_sec = Number(d.query_timeout_sec || 10);
    settingsForm.nl2sql_retry = Number(d.nl2sql_retry || 2);
    settingsForm.nl2sql_max_tokens = Number(d.nl2sql_max_tokens || 1200);
    loadEngineForm(d);
  } catch {
    /* 忽略 */
  }
}
async function saveSettings() {
  savingSettings.value = true;
  try {
    await saveQuerySetting({
      key: "query_max_rows",
      value: String(settingsForm.query_max_rows),
      remark: "结果最大行数",
    });
    await saveQuerySetting({
      key: "query_timeout_sec",
      value: String(settingsForm.query_timeout_sec),
      remark: "查询超时秒",
    });
    await saveQuerySetting({
      key: "nl2sql_retry",
      value: String(settingsForm.nl2sql_retry),
      remark: "NL2SQL 自纠错轮数",
    });
    await saveQuerySetting({
      key: "nl2sql_max_tokens",
      value: String(settingsForm.nl2sql_max_tokens),
      remark: "NL2SQL max_tokens",
    });
    ElMessage.success("已保存限额");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingSettings.value = false;
  }
}

// ---- 工程配置 ----
const engForm = reactive<any>({});
const savingEngine = ref(false);
const engDef = {
  schema_top_k: 16,
  schema_semantic_weight: 0.6,
  schema_keyword_weight: 0.4,
  entity_enabled: true,
  enum_hint_enabled: true,
  full_entity_no_limit: true,
  entity_name_rule: true,
  agno_semantic_enabled: true,
  decomposed_planning: true,
  self_consistency_n: 1,
  query_cost_enabled: true,
  query_cost_max_rows: 50000,
  fewshot_auto_curate: true,
  empty_self_correct: true,
  agno_tool_agent: true,
  kg_enabled: true,
  entity_map: "{}",
};
// 内置默认实体名词→表 映射（仅作编辑起点，可在界面增删改并持久化覆盖）
const DEFAULT_ENTITY_MAP: Record<string, string[]> = {
  摄像头: ["video_cameras", "video_camera_groups"],
  设备: ["video_edge_devices"],
  算法: ["video_algorithms"],
  任务: ["video_algorithm_tasks", "annotation_task", "train_tasks"],
  数据集: ["annotation_dataset"],
  规则: ["video_alarm_rules"],
  标注: ["annotation_dataset", "annotation_task", "annotation_record"],
  告警: ["video_alarm_records"],
  报警: ["video_alarm_records"],
  事件: ["video_edge_events"],
  模型: ["ai_models", "ai_call_logs"],
  用户: ["sys_user"],
  合成: ["synthesis_job"],
  报表: ["ai_reports"],
  工作流: ["ai_workflows"],
};
const engRows = ref<Array<{ noun: string; tables: string }>>([]);
function parseEngRows(raw: string) {
  let over: Record<string, any> = {};
  try {
    over = JSON.parse(raw || "{}") || {};
  } catch {
    over = {};
  }
  const merged: Record<string, string[]> = {};
  // 先放默认，再被后端覆盖
  for (const [n, ts] of Object.entries(DEFAULT_ENTITY_MAP)) merged[n] = [...ts];
  for (const [n, ts] of Object.entries(over)) {
    merged[n] = Array.isArray(ts)
      ? ts.map(String)
      : String(ts)
          .split(/[,，]/)
          .map((s) => s.trim())
          .filter(Boolean);
  }
  engRows.value = Object.entries(merged).map(([noun, tables]) => ({
    noun,
    tables: tables.join(", "),
  }));
}
function addEngRow() {
  engRows.value.push({ noun: "", tables: "" });
}
function removeEngRow(idx: number) {
  engRows.value.splice(idx, 1);
}
function engRowsToJson(): string {
  const obj: Record<string, string[]> = {};
  for (const r of engRows.value) {
    const noun = (r.noun || "").trim();
    if (!noun) continue;
    const tables = (r.tables || "")
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (tables.length) obj[noun] = tables;
  }
  return JSON.stringify(obj);
}
function loadEngineForm(d: any) {
  engForm.schema_top_k = Number(d.schema_top_k ?? engDef.schema_top_k);
  engForm.schema_semantic_weight = Number(
    d.schema_semantic_weight ?? engDef.schema_semantic_weight
  );
  engForm.schema_keyword_weight = Number(d.schema_keyword_weight ?? engDef.schema_keyword_weight);
  engForm.entity_enabled = String(d.entity_enabled ?? "true") !== "0";
  engForm.enum_hint_enabled = String(d.enum_hint_enabled ?? "true") !== "0";
  engForm.full_entity_no_limit = String(d.full_entity_no_limit ?? "true") !== "0";
  engForm.entity_name_rule = String(d.entity_name_rule ?? "true") !== "0";
  engForm.agno_semantic_enabled = String(d.agno_semantic_enabled ?? "true") !== "0";
  engForm.decomposed_planning = String(d.decomposed_planning ?? "true") !== "0";
  engForm.self_consistency_n = Number(d.self_consistency_n ?? 1);
  engForm.query_cost_enabled = String(d.query_cost_enabled ?? "true") !== "0";
  engForm.query_cost_max_rows = Number(d.query_cost_max_rows ?? 50000);
  engForm.fewshot_auto_curate = String(d.fewshot_auto_curate ?? "true") !== "0";
  engForm.empty_self_correct = String(d.empty_self_correct ?? "true") !== "0";
  engForm.agno_tool_agent = String(d.agno_tool_agent ?? "true") !== "0";
  engForm.kg_enabled = String(d.kg_enabled ?? "true") !== "0";
  engForm.entity_map = d.entity_map ?? "{}";
  parseEngRows(engForm.entity_map);
}
async function saveEngineConfig() {
  savingEngine.value = true;
  try {
    // 布尔开关转 'true'/'false' 字符串
    await saveQuerySetting({
      key: "schema_top_k",
      value: String(engForm.schema_top_k),
      remark: "schema 表数上限",
    });
    await saveQuerySetting({
      key: "schema_semantic_weight",
      value: String(engForm.schema_semantic_weight),
      remark: "语义检索权重",
    });
    await saveQuerySetting({
      key: "schema_keyword_weight",
      value: String(engForm.schema_keyword_weight),
      remark: "关键词检索权重",
    });
    await saveQuerySetting({
      key: "self_consistency_n",
      value: String(engForm.self_consistency_n),
      remark: "自一致性候选数",
    });
    await saveQuerySetting({
      key: "query_cost_max_rows",
      value: String(engForm.query_cost_max_rows),
      remark: "代价护栏行数上限",
    });
    const bools: Record<string, boolean> = {
      entity_enabled: engForm.entity_enabled,
      enum_hint_enabled: engForm.enum_hint_enabled,
      full_entity_no_limit: engForm.full_entity_no_limit,
      entity_name_rule: engForm.entity_name_rule,
      agno_semantic_enabled: engForm.agno_semantic_enabled,
      decomposed_planning: engForm.decomposed_planning,
      query_cost_enabled: engForm.query_cost_enabled,
      fewshot_auto_curate: engForm.fewshot_auto_curate,
      empty_self_correct: engForm.empty_self_correct,
      agno_tool_agent: engForm.agno_tool_agent,
      kg_enabled: engForm.kg_enabled,
    };
    for (const [k, v] of Object.entries(bools)) {
      await saveQuerySetting({ key: k, value: v ? "true" : "false", remark: k });
    }
    const entityMap = engRowsToJson();
    await saveQuerySetting({
      key: "entity_map",
      value: entityMap,
      remark: "实体映射JSON",
    });
    engForm.entity_map = entityMap;
    ElMessage.success("已保存工程配置");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    savingEngine.value = false;
  }
}
const bmRunning = ref(false);
const bmFinished = ref(false);
const bmError = ref("");
const bmState = ref<any>(null);
const bmReport = ref<any>(null);
const bmRunId = ref("");
const bmTimer = ref<any>(null);
const bmTotal = computed(() => bmState.value?.total || 80);
const bmDoneCount = computed(() => bmState.value?.done || 0);
const bmPercent = computed(() => {
  const t = bmTotal.value;
  return t ? Math.round((bmDoneCount.value / t) * 100) : 0;
});
const bmStage = computed(() => {
  const s = bmState.value?.stage;
  if (s === "fast") return "快路径";
  if (s === "nl2sql") return "NL2SQL 复杂报表";
  return s || "-";
});
const bmFailRows = computed(() => {
  const rs = bmReport.value?.nl2sql?.results || [];
  return rs.slice().sort((a: any, b: any) => (a.correct === b.correct ? 0 : a.correct ? 1 : -1));
});

function clearBmTimer() {
  if (bmTimer.value) {
    clearInterval(bmTimer.value);
    bmTimer.value = null;
  }
}
async function pollBenchmark() {
  try {
    const r = await getQueryBenchmarkStatus(bmRunId.value);
    const d = r.data?.data;
    bmState.value = d;
    if (d?.status === "done" && d.report) {
      bmReport.value = d.report;
      bmFinished.value = true;
      bmRunning.value = false;
      clearBmTimer();
      ElMessage.success("基准测试完成");
    } else if (d?.status === "error") {
      bmError.value = d.error || "运行失败";
      bmRunning.value = false;
      clearBmTimer();
    }
  } catch (e: any) {
    bmError.value = e?.msg || "轮询失败";
    bmRunning.value = false;
    clearBmTimer();
  }
}
async function runBenchmark() {
  try {
    bmRunning.value = true;
    bmFinished.value = false;
    bmError.value = "";
    bmReport.value = null;
    const r = await runQueryBenchmark();
    bmRunId.value = r.data?.data?.run_id || "";
    bmState.value = { status: "running", stage: "fast", done: 0, total: 80 };
    clearBmTimer();
    bmTimer.value = setInterval(pollBenchmark, 3000);
  } catch (e: any) {
    bmRunning.value = false;
    ElMessage.error(e?.msg || "启动基准失败");
  }
}

// ---- 数据源 ----
const dsEditVisible = ref(false);
const dsForm = reactive<any>({});
const queryRoles = ref<any[]>([]);
async function loadQueryRoles() {
  try {
    const r = await getQueryRoles();
    queryRoles.value = r.data?.data || [];
  } catch {
    queryRoles.value = [];
  }
}
function openDsEdit(row?: any) {
  if (row) Object.assign(dsForm, row);
  else
    Object.assign(dsForm, {
      id: undefined,
      name: "",
      type: "postgres",
      host: "",
      port: 5432,
      database: "",
      username: "",
      password: "",
      read_only: true,
      enabled: true,
      allowed_roles: [],
      remark: "",
    });
  loadQueryRoles();
  dsEditVisible.value = true;
}
async function saveDs(row: any) {
  if (!row.name) {
    ElMessage.warning("请填写名称");
    return;
  }
  saving.value = true;
  try {
    await saveQueryDatasource({
      name: row.name,
      code: row.code || `ds_${Date.now()}`,
      type: row.type,
      host: row.host || "",
      port: row.port || 0,
      database: row.database || "",
      username: row.username || "",
      password: row.password || "",
      read_only: row.read_only !== false,
      enabled: row.enabled !== false,
      allowed_roles: row.allowed_roles || [],
      remark: row.remark || "",
    });
    ElMessage.success("已保存");
    dsEditVisible.value = false;
    loadDatasources();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}
async function removeDs(row: any) {
  await deleteQueryDatasources([row.id]);
  loadDatasources();
}
const testingDsId = ref<number | null>(null);
const syncingDsId = ref<number | null>(null);
async function testDs(row: any) {
  testingDsId.value = row.id;
  try {
    const r = await testQueryDatasource(row.id);
    const d = r.data?.data || {};
    if (d.ok) ElMessage.success(d.message || "连接成功");
    else ElMessage.error(d.message || "连接失败");
  } catch (e: any) {
    ElMessage.error(e?.msg || "测试失败");
  } finally {
    testingDsId.value = null;
  }
}
async function syncDs(row: any) {
  syncingDsId.value = row.id;
  try {
    const r = await syncQueryDatasourceSchema(row.id);
    const d = r.data?.data || {};
    ElMessage.success(`同步完成，共 ${d.tables ?? 0} 张表`);
    row.syncedTables = d.tables ?? 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || "同步失败");
  } finally {
    syncingDsId.value = null;
  }
}

onMounted(() => {
  loadDatasources();
  loadSessions();
  loadKgStats();
  loadKgKbs();
  loadUnifiedGraph();
  loadConcepts();
  loadFde();
  loadActions();
  loadActionLogs();
  loadGovObjects();
  loadOntMap();
  loadIndustryTemplates();
  loadPipes();
  loadWorkshop();
  loadAccessRules();
});
</script>

<style scoped>
.ai-query-page {
  height: 100%;
}
.fde-steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.fde-step {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.gov-section {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin: 8px 0 4px;
}
.gov-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
.dq-alert {
  margin-bottom: 10px;
}
.dq-alert__item {
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  padding: 8px 10px;
  margin-top: 8px;
}
.dq-alert__score {
  margin-left: 8px;
  font-size: 13px;
  color: var(--el-color-warning);
}
.dq-alert__down {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}
.dq-alert__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}
.dq-alert__none {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.dq-alert__issues {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
}
.domain-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.domain-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.govdash-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.govdash-dq {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 6px;
}
.govdash-dq__label {
  font-size: 22px;
  font-weight: 600;
}
.govdash-dq__meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.govdash-alert {
  border: 1px solid var(--el-color-warning-light-5);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
}
.govdash-alert__score {
  margin-left: 8px;
  font-size: 13px;
  color: var(--el-color-warning);
}
.govdash-alert__down {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.gov-rel {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-bottom: 3px;
}
.fde-roles {
  display: flex;
  gap: 6px;
  width: 100%;
}
.shadow-fields {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.pipe-mapping {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.query-layout {
  display: flex;
  height: 100%;
  gap: 12px;
}
.query-side {
  width: 240px;
  flex-shrink: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  overflow: auto;
}
.query-side__hd {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.query-ds {
  margin-bottom: 12px;
}
.query-ds__label {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.session-item:hover {
  background: var(--el-fill-color-light);
}
.session-item.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.session-item__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.session-item__del {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}
.session-item__del:hover {
  color: var(--el-color-danger);
}
.query-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.query-chat {
  flex: 1;
  overflow: auto;
  padding: 16px;
}
.msg-row {
  margin-bottom: 18px;
}
.msg-q {
  font-weight: 600;
  margin-bottom: 8px;
}
.msg-a {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--el-bg-color);
}
.msg-a__ont {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
}
.msg-a__ont-icon {
  color: var(--el-color-primary);
}
.msg-a__ont-label {
  font-size: 12px;
  color: var(--el-color-primary);
  font-weight: 600;
  margin-right: 4px;
}
.msg-a__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.msg-a__time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.msg-a__sql,
.msg-a__fb,
.msg-a__export {
  font-size: 12px;
  color: var(--el-color-primary);
  cursor: pointer;
  margin-left: 4px;
}
.msg-a__export:hover {
  color: var(--el-color-primary-light-3);
}
.promote-sql {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.promote-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.rw-row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}
.rw-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.fde-shadow-detail {
  margin-left: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.asset-catalog {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-top: 10px;
}
.asset-card {
  border: 1px solid var(--el-border-color-light);
  cursor: pointer;
  transition: box-shadow 0.2s;
}
.asset-card:hover {
  box-shadow: var(--el-box-shadow-light);
  border-color: var(--el-color-primary-light-7);
}
.asset-card__head {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.asset-card__name {
  font-size: 14px;
}
.asset-card__meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.asset-card__desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.asset-card__actions {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.msg-a__summary {
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
}
.msg-a__dq {
  margin-bottom: 8px;
}
.msg-a__ont-tag {
  cursor: pointer;
}
.msg-a__ont-tag:hover {
  opacity: 0.8;
}
.msg-a__trace {
  margin: 4px 0 8px;
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  background: var(--el-fill-color-blank);
}
.trace-reasoning {
  margin-bottom: 8px;
}
.trace-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-color-primary);
  margin-bottom: 4px;
}
.trace-pre {
  margin: 0;
  padding: 6px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 160px;
  overflow: auto;
  color: var(--el-text-color-regular);
}
.trace-call {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 2px;
}
.trace-name {
  font-weight: 600;
  font-size: 12px;
  color: var(--el-text-color-primary);
}
.trace-args {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  padding: 2px 6px;
  border-radius: 4px;
  word-break: break-all;
}
.trace-out {
  margin: 2px 0 6px 12px;
}
.trace-pre--out {
  border-left: 2px solid var(--el-color-info);
}
.trace-err {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-color-danger);
  font-size: 12px;
  margin: 4px 0 6px 12px;
}
.msg-a__code--live {
  border: 1px dashed var(--el-border-color);
}
.msg-a__export {
  margin-left: 8px;
  color: var(--el-color-success);
}
.msg-a__chart-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.msg-a__code {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
  overflow: auto;
}
.msg-a__code pre {
  margin: 0;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
  white-space: pre-wrap;
}
.msg-a__table {
  margin-top: 4px;
}
.msg-a__err {
  color: var(--el-color-danger);
}
.msg-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  padding: 8px 0;
}
.query-input {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px;
}
.query-examples {
  margin-bottom: 8px;
}
.query-examples__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 4px;
}
.query-examples__tag {
  cursor: pointer;
  margin-right: 6px;
}
.query-input__row {
  display: flex;
  gap: 8px;
}
.ops-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.emap-editor {
  padding: 8px 12px 12px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  margin-bottom: 4px;
}
.emap-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.emap-tables {
  flex: 1;
}
.emap-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
