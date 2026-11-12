<template>
  <div class="app-container ai-query-page">
    <el-row :gutter="12">
      <!-- 左侧：会话列表 -->
      <el-col :xs="24" :sm="24" :md="7" :lg="6">
        <el-card shadow="never" class="q-side">
          <template #header>
            <div class="q-side__head">
              <span>{{ t("ai_logs.sessions") }}</span>
              <el-button link type="primary" size="small" @click="newSession">
                {{ t("ai_logs.newChat") }}
              </el-button>
            </div>
          </template>
          <el-empty
            v-if="!sessions.length"
            :description="t('ai_logs.noSessions')"
            :image-size="60"
          />
          <div
            v-for="s in sessions"
            :key="s.id"
            class="q-sess"
            :class="{ 'is-active': s.id === sessionId }"
            @click="openSession(s.id)"
          >
            <div class="q-sess__title">{{ s.title || t("ai_logs.unnamed") }}</div>
            <div class="q-sess__meta">
              <span>{{ s.created_time || "" }}</span>
              <el-button
                icon="delete"
                link
                type="danger"
                size="small"
                @click.stop="removeSession(s)"
              >
                {{ t("ai_logs.delete") }}
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：问答区 -->
      <el-col :xs="24" :sm="24" :md="17" :lg="18">
        <el-card shadow="never">
          <template #header>
            <div class="q-head">
              <span>{{ t("ai_logs.smartQuery") }}</span>
              <div class="q-head__ops">
                <el-select
                  v-model="datasource"
                  size="small"
                  :placeholder="t('ai_logs.datasource')"
                  style="width: 190px"
                >
                  <el-option :label="t('ai_logs.systemDsLabel')" value="system" />
                  <el-option
                    v-for="d in datasources"
                    :key="d.code || d.id"
                    :label="d.name"
                    :value="d.code || `ds:${d.id}`"
                  />
                </el-select>
                <el-button icon="Collection" link type="primary" size="small" @click="goOntology">
                  {{ t("ai_logs.viewOntology") }}
                </el-button>
                <el-button icon="Setting" link type="primary" size="small" @click="openSettings">
                  {{ t("ai_logs.querySettings") }}
                </el-button>
                <el-button icon="DataLine" link type="primary" size="small" @click="openStats">
                  {{ t("ai_logs.usageStats") }}
                </el-button>
                <el-dropdown @command="goSub">
                  <el-button link type="primary" size="small">
                    <el-icon style="margin-right: 4px"><Grid /></el-icon>
                    {{ t("ai_logs.dataManagement") }}
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="/ai/integration">
                        {{ t("ai_logs.dataIntegration") }}
                      </el-dropdown-item>
                      <el-dropdown-item command="/ai/eval">
                        {{ t("ai_logs.queryEval") }}
                      </el-dropdown-item>
                      <el-dropdown-item command="/ai/query/reports">
                        {{ t("ai_logs.reportTemplates") }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </template>

          <ChatShell>
            <ChatOutline
              :items="outlineItems"
              container=".chat-shell__body"
              :title="t('ai_chat.chatOutline_title')"
            />
            <div class="q-chat__scroll">
              <el-alert
                v-if="objectCode"
                class="q-tip"
                type="success"
                :closable="true"
                show-icon
                :title="
                  t('ai_logs.objectContext', {
                    code: objectCode,
                    key: objectKey ? ' #' + objectKey : '',
                  })
                "
                @close="clearObjectContext"
              />

              <el-alert
                v-if="!tipHidden"
                type="info"
                :closable="true"
                show-icon
                class="q-tip"
                :title="t('ai_logs.queryReuseTip')"
                @close="hideTip"
              />

              <el-empty
                v-if="!messages.length"
                :description="t('ai_logs.noQueries')"
                :image-size="70"
              />

              <div v-for="(m, i) in messages" :id="`q-turn-${i}`" :key="m.id || i" class="q-turn">
                <ChatMessage role="user">{{ m.question }}</ChatMessage>

                <el-alert
                  v-if="m.is_error"
                  type="error"
                  :closable="false"
                  :title="m.summary || t('ai_logs.queryFailed')"
                  class="q-msg__err"
                />

                <ChatMessage
                  v-else
                  role="assistant"
                  :name="t('ai_logs.assistant')"
                  :streaming="!!m.streaming"
                  :live-label="t('ai_logs.thinking')"
                >
                  <template #reasoning>
                    <!-- 思考：公共组件，流式时自动展开、结束后收成摘要 -->
                    <ReasoningBlock
                      v-if="m.reasoning || m.streaming"
                      :text="m.reasoning || t('ai_logs.thinking')"
                      :streaming="!!m.streaming && !m.sql"
                    />
                  </template>

                  <template #tools>
                    <!-- 工具调用：公共时间线（可展开入参/出参） -->
                    <ToolCallTimeline v-if="m.tools && m.tools.length" :parts="partsOf(m)" />
                  </template>

                  <div v-if="m.summary && !(m.columns && m.columns.length)" class="q-msg__sum">
                    {{ m.summary }}
                  </div>

                  <!-- SQL -->
                  <div v-if="m.sql || (m.streaming && m.path === 'slow')" class="q-block">
                    <div class="q-block__title">{{ t("ai_logs.generatedSql") }}</div>
                    <CodeBlock :code="m.sql || '…'" language="sql" />
                  </div>

                  <!-- 对象查询 IR（排查细节，折叠） -->
                  <el-collapse v-if="irOf(m)" class="q-block">
                    <el-collapse-item :title="t('ai_logs.viewObjectQuery')" name="ir">
                      <pre class="q-sql">{{ JSON.stringify(irOf(m), null, 2) }}</pre>
                      <div class="q-msg__ir-note">
                        {{ t("ai_logs.objectQueryNote") }}
                        <span v-if="m.object_query?.note">· {{ m.object_query.note }}</span>
                      </div>
                    </el-collapse-item>
                  </el-collapse>

                  <!-- 结果 -->
                  <div v-if="m.columns && m.columns.length" class="q-block">
                    <div class="q-block__title">
                      {{ t("ai_logs.resultTitle") }}
                      <el-tag size="small" type="info" effect="plain">
                        {{ t("ai_logs.totalRows", { count: m.result_rows }) }}
                      </el-tag>
                      <span v-if="m.took_ms" class="q-block__badge">{{ m.took_ms }} ms</span>
                    </div>
                    <el-table
                      :data="rowsOf(m)"
                      size="small"
                      border
                      max-height="340"
                      :style="m.columns.length <= 2 ? 'max-width: 460px' : ''"
                      stripe
                    >
                      <el-table-column
                        v-for="c in m.columns"
                        :key="c"
                        :prop="c"
                        :label="c"
                        min-width="120"
                        show-overflow-tooltip
                      />
                    </el-table>
                  </div>

                  <!-- 本体依据：这次用了哪些本体对象、召回了哪些表（可点开看全量） -->
                  <div v-if="ontologyOf(m).length || recalledOf(m).length" class="q-onto">
                    <div class="q-onto__head" @click="toggleOnto(i)">
                      <span class="q-onto__title">{{ t("ai_logs.ontologyBasis") }}</span>
                      <el-tag v-if="ontologyOf(m).length" size="small" type="success" effect="dark">
                        {{ t("ai_logs.ontologyUsedCount", { count: ontologyOf(m).length }) }}
                      </el-tag>
                      <el-tag v-if="recalledOf(m).length" size="small" effect="plain">
                        {{ t("ai_logs.recallCount", { count: recalledOf(m).length }) }}
                      </el-tag>
                      <el-tag v-if="m.metric?.name" size="small" type="warning" effect="plain">
                        {{ t("ai_logs.metricBasis") }}·{{ m.metric.name }}
                      </el-tag>
                      <span class="q-onto__toggle">{{ ontoOpen(i) ? "收起" : "详情" }}</span>
                    </div>

                    <div v-show="ontoOpen(i)" class="q-onto__body">
                      <div
                        v-if="!ontologyOf(m).length && recalledOf(m).length"
                        class="q-onto__hint"
                      >
                        {{ t("ai_logs.ontologyMissHint") }}
                      </div>

                      <div v-if="ontologyOf(m).length" class="q-onto__row">
                        <span class="q-onto__label">{{ t("ai_logs.ontologyObjects") }}</span>
                        <el-tag
                          v-for="t in ontologyOf(m)"
                          :key="`o-${t}`"
                          size="small"
                          type="success"
                          effect="plain"
                        >
                          {{ t }}
                        </el-tag>
                      </div>

                      <div v-if="recalledOf(m).length" class="q-onto__row">
                        <span class="q-onto__label">{{ t("ai_logs.recalledTables") }}</span>
                        <el-tag
                          v-for="t in recalledOf(m)"
                          :key="`t-${t}`"
                          size="small"
                          effect="plain"
                        >
                          {{ t }}
                        </el-tag>
                      </div>
                    </div>
                  </div>

                  <template #meta>
                    <el-tag size="small" effect="plain">{{ pathLabel(m) }}</el-tag>
                    <el-tag v-if="m.metric?.name" size="small" type="success" effect="plain">
                      {{ t("ai_logs.metric", { name: m.metric.name }) }}
                    </el-tag>
                    <span v-if="m.cached" class="q-msg__src">{{ t("ai_logs.cacheHit") }}</span>
                  </template>

                  <template #footer>
                    <div v-if="m.id" class="q-msg__fb">
                      <el-button v-if="m.sql || m.took_ms" link size="small" @click="openTrace(m)">
                        {{ t("ai_logs.traceTitle") }}
                      </el-button>
                      <el-button icon="Select" link size="small" @click="feedback(m, 'up')">
                        {{ t("ai_logs.useful") }}
                      </el-button>
                      <el-button icon="Close" link size="small" @click="openCorrect(m)">
                        {{ t("ai_logs.useless") }}
                      </el-button>
                      <el-button
                        v-if="m.sql && !m.is_error"
                        icon="Document"
                        link
                        type="primary"
                        size="small"
                        @click="openSaveReport(m)"
                      >
                        {{ t("ai_logs.saveAsReport") }}
                      </el-button>
                      <el-button
                        v-if="m.sql && !m.is_error"
                        icon="DataAnalysis"
                        link
                        type="primary"
                        size="small"
                        @click="openPromote(m)"
                      >
                        {{ t("ai_logs.promoteMetric") }}
                      </el-button>
                    </div>
                  </template>
                </ChatMessage>
              </div>
            </div>

            <template #footer>
              <div class="q-chat__composer">
                <div class="q-composer">
                  <el-input
                    v-model="question"
                    type="textarea"
                    :rows="2"
                    resize="none"
                    :placeholder="t('ai_logs.questionPlaceholder')"
                    @keydown.enter.exact.prevent="ask"
                  />
                  <el-button type="primary" :loading="asking" @click="ask">
                    {{ t("ai_logs.ask") }}
                  </el-button>
                </div>
                <div class="q-examples">
                  <span class="q-examples__label">{{ t("ai_logs.examples") }}</span>
                  <el-tag
                    v-for="e in examples"
                    :key="e"
                    class="q-examples__tag"
                    effect="plain"
                    size="small"
                    @click="question = e"
                  >
                    {{ e }}
                  </el-tag>
                </div>
              </div>
            </template>
          </ChatShell>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog
      v-model="clarifyVisible"
      :title="t('ai_logs.confirmNeeded')"
      width="520px"
      append-to-body
    >
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        :title="t('ai_logs.clarifyTip')"
        class="q-fb-tip"
      />
      <div class="q-fb-q">{{ clarify?.question }}</div>
      <el-radio-group v-model="clarifyPick">
        <el-radio v-for="o in clarify?.options || []" :key="o.value" :label="o.value">
          {{ o.label }}
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="clarifyVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button type="primary" :disabled="!clarifyPick" @click="answerClarify">
          {{ t("ai_logs.queryByChoice") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 报表建议：未命中时，推荐已沉淀的报表供用户选择执行 -->
    <el-dialog
      v-model="reportSuggestVisible"
      :title="t('ai_logs.foundReports')"
      width="600px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.reportSuggestTip')"
        class="q-fb-tip"
      />
      <div class="q-report-suggest">
        <div
          v-for="r in reportSuggestList"
          :key="r.id"
          class="q-report-item"
          @click="pickReport(r)"
        >
          <div class="q-report-item__head">
            <span class="q-report-item__name">{{ r.name }}</span>
            <el-tag v-if="r.params" size="small" type="warning" effect="plain">
              {{ r.params }} {{ t("ai_logs.params") }}
            </el-tag>
            <el-tag v-else size="small" type="success" effect="plain">
              {{ t("ai_logs.directResult") }}
            </el-tag>
          </div>
          <div v-if="r.description" class="q-report-item__desc">{{ r.description }}</div>
          <div v-if="r.question" class="q-report-item__q">
            {{ t("ai_logs.correspondingQuestion", { q: r.question }) }}
          </div>
        </div>
        <el-empty v-if="!reportSuggestList.length" :image-size="56" description="暂无可选报表" />
      </div>
      <template #footer>
        <el-button @click="reportSuggestVisible = false">{{ t("ai_logs.skipQa") }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="srVisible" :title="t('ai_logs.saveAsReport')" width="520px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.saveReportTip')"
        class="q-fb-tip"
      />
      <el-form label-width="80px">
        <el-form-item :label="t('ai_logs.reportName')">
          <el-input v-model="srName" :placeholder="t('ai_logs.reportNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_logs.sourceQuestion')">
          <el-input :model-value="srMsg?.question || ''" readonly />
        </el-form-item>
        <el-form-item v-if="srParams.length" :label="t('ai_logs.params')">
          <el-tag v-for="k in srParams" :key="k" size="small" effect="plain" class="q-sr__p">
            {{ k }}
          </el-tag>
          <div class="q-sr__hint">
            {{ t("ai_logs.srParamHint", { count: srParams.length }) }}
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="srVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button type="primary" :loading="srLoading" @click="submitSaveReport">
          {{ t("ai_logs.saveDraft") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="pmVisible" :title="t('ai_logs.promoteMetric')" width="520px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.promoteTip')"
        class="q-fb-tip"
      />
      <el-form label-width="80px">
        <el-form-item :label="t('ai_logs.metricDisplayName')">
          <el-input v-model="pmName" :placeholder="t('ai_logs.reportNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_logs.metricCode')">
          <el-input v-model="pmKey" :placeholder="t('ai_logs.metricCodePlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('ai_logs.sourceQuestion')">
          <el-input :model-value="pmMsg?.question || ''" readonly />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pmVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button type="primary" :loading="pmLoading" @click="submitPromote">
          {{ t("ai_logs.promote") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="statsVisible"
      :title="t('ai_logs.queryUsageStats')"
      width="520px"
      append-to-body
    >
      <el-row :gutter="12">
        <el-col :span="12">
          <el-statistic :title="t('ai_logs.totalQa')" :value="stats.total" />
        </el-col>
        <el-col :span="12">
          <el-statistic :title="t('ai_logs.fastPath')" :value="stats.fast" />
        </el-col>
        <el-col :span="12" style="margin-top: 12px">
          <el-statistic :title="t('ai_logs.slowPath')" :value="stats.slow" />
        </el-col>
        <el-col :span="12" style="margin-top: 12px">
          <el-statistic :title="t('ai_logs.failed')" :value="stats.errors" />
        </el-col>
      </el-row>
      <div class="q-stats__hint">{{ t("ai_logs.fastPathHint", { pct: fastPct }) }}</div>
    </el-dialog>

    <el-dialog v-model="fbVisible" :title="t('ai_logs.correctQuery')" width="600px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.correctQueryTip')"
        class="q-fb-tip"
      />
      <div class="q-fb-q">{{ fbMsg?.question }}</div>
      <el-input
        v-model="fbSql"
        type="textarea"
        :rows="6"
        :placeholder="t('ai_logs.correctSqlPlaceholder')"
      />
      <template #footer>
        <el-button @click="fbVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button @click="submitFeedback(false)">{{ t("ai_logs.markUselessOnly") }}</el-button>
        <el-button type="primary" :loading="fbLoading" @click="submitFeedback(true)">
          {{ t("ai_logs.submitCorrect") }}
        </el-button>
      </template>
    </el-dialog>
    <el-dialog
      v-model="setVisible"
      :title="t('ai_logs.querySettings')"
      width="760px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="t('ai_logs.settingTip')"
        class="q-fb-tip"
      />
      <div v-loading="setLoading">
        <el-input
          v-model="setSearch"
          size="small"
          clearable
          :placeholder="t('ai_logs.settingSearchPlaceholder')"
          class="q-set__search"
        />
        <div class="q-set__toolbar">
          <el-radio-group v-model="setMode" size="small">
            <el-radio-button label="simple">{{ t("ai_logs.settingModeSimple") }}</el-radio-button>
            <el-radio-button label="expert">{{ t("ai_logs.settingModeExpert") }}</el-radio-button>
          </el-radio-group>
          <el-checkbox v-model="showChanged" size="small" class="q-set__changed-only">
            {{ t("ai_logs.settingChangedOnly") }}
          </el-checkbox>
          <el-button
            size="small"
            class="q-set__probe"
            style="margin-left: auto"
            @click="probeVisible = true"
          >
            召回探针
          </el-button>
          <el-button size="small" @click="openPromptRules">生成规则</el-button>
          <el-button size="small" @click="openEntityMap">实体映射</el-button>
          <el-button size="small" @click="openLanguageRules">语言规则</el-button>
          <el-button size="small" @click="openAudit">指标体检</el-button>
          <el-button size="small" @click="mapVisible = true">配置地图</el-button>
        </div>
        <div v-for="g in visibleGroups" :key="g.name" class="q-set__group">
          <div class="q-set__group-title" @click="toggleGroup(g.name)">
            <span class="q-set__caret">{{ collapsedGroups[g.name] ? "▸" : "▾" }}</span>
            {{ g.name }}
            <span class="q-set__count">{{ g.items.length }}</span>
          </div>
          <div v-show="!collapsedGroups[g.name]">
            <div
              v-for="d in g.items"
              :key="d.key"
              class="q-set__row"
              :class="{ 'is-changed': isChanged(d.key) }"
            >
              <div class="q-set__main">
                <div class="q-set__label">
                  {{ d.label }}
                  <span v-if="setMode === 'expert' && d.rawKey !== d.label" class="q-set__key">
                    {{ d.rawKey }}
                  </span>
                </div>
                <div v-if="d.tip" class="q-set__tip">{{ d.tip }}</div>
              </div>
              <el-switch
                v-if="d.type === 'bool'"
                v-model="setForm[d.key]"
                active-value="true"
                inactive-value="false"
              />
              <el-select
                v-else-if="d.options"
                v-model="setForm[d.key]"
                size="small"
                style="width: 200px"
              >
                <el-option v-for="o in d.options" :key="o" :label="o" :value="o" />
              </el-select>
              <el-input
                v-else-if="d.type === 'text'"
                v-model="setForm[d.key]"
                size="small"
                clearable
                :placeholder="t('ai_logs.leaveEmptyDefault')"
                style="width: 200px"
              />
              <el-input-number
                v-else
                :model-value="Number(setForm[d.key] || 1)"
                :min="'min' in d ? d.min : 0"
                :max="'max' in d ? d.max : 100000"
                size="small"
                style="width: 120px"
                @update:model-value="(v: number | undefined) => (setForm[d.key] = String(v ?? 1))"
              />
              <el-button
                v-if="isChanged(d.key) && setDefaults[d.key] !== undefined"
                link
                size="small"
                class="q-set__reset"
                @click="resetOne(d)"
              >
                {{ t("ai_logs.settingReset") }}
              </el-button>
              <span v-if="isChanged(d.key)" class="q-set__dot" />
            </div>
          </div>
        </div>
        <el-empty v-if="!visibleGroups.length" :image-size="56" description="没有匹配的配置项" />
      </div>
      <template #footer>
        <el-button class="q-set__reset-all" @click="resetAll">
          {{ t("ai_logs.settingResetAll") }}
        </el-button>
        <el-button @click="setVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button type="primary" :loading="setSaving" @click="saveSettings">
          {{ t("ai_logs.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 实体映射：业务词 → 表（召回「实体通道」；命中哪个词就把哪张表排前面） -->
    <el-dialog v-model="entVisible" title="实体映射（业务词 → 表）" width="900px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="用户说这些词时，把对应表优先召回。改完下一句问数立即生效；不填的表仍按语义/关键词召回。"
        class="q-fb-tip"
      />
      <div v-loading="entLoading" class="q-ent">
        <div v-for="(row, i) in entForm" :key="i" class="q-ent__row">
          <el-input
            v-model="row.noun"
            size="small"
            placeholder="业务词，如 矿点"
            style="width: 180px"
          />
          <el-select
            v-model="row.tables"
            multiple
            filterable
            allow-create
            default-first-option
            size="small"
            placeholder="对应表（可多选，也可直接输入表名）"
            style="flex: 1 1 auto"
          >
            <el-option v-for="t in entTables" :key="t" :label="t" :value="t" />
          </el-select>
          <el-button link type="danger" size="small" @click="entForm.splice(i, 1)">删除</el-button>
        </div>
        <el-empty v-if="!entForm.length" :image-size="60" description="还没有映射，点下面新增" />
        <div class="q-rules__bar">
          <el-button size="small" @click="entForm.push({ noun: '', tables: [] })">
            新增映射
          </el-button>
          <span class="q-rules__hint" style="margin-left: 8px">
            共 {{ entForm.length }} 条；表选项来自资产目录（{{ entTables.length }} 张）
          </span>
        </div>
      </div>
      <template #footer>
        <el-button @click="entVisible = false">取消</el-button>
        <el-button :loading="entSaving" @click="resetEntityMap">恢复默认</el-button>
        <el-button type="primary" :loading="entSaving" @click="saveEntityMap">保存</el-button>
      </template>
    </el-dialog>

    <!-- 指标体检：自动生成的脏指标 / 抢答题；可停用，改名去指标页 -->
    <el-dialog v-model="auditVisible" title="指标体检" width="980px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="`共 ${auditStats.total_metrics || 0} 个启用指标，可疑 ${auditStats.suspect || 0} 个（抢答 ${auditStats.hijacking || 0} 个）。停用只关开关，不改口径。`"
        class="q-fb-tip"
      />
      <el-table
        v-loading="auditLoading"
        :data="auditRows"
        border
        stripe
        size="small"
        max-height="460"
      >
        <el-table-column prop="name" label="指标名" min-width="220" show-overflow-tooltip />
        <el-table-column prop="table" label="绑定表/对象" min-width="180" show-overflow-tooltip />
        <el-table-column label="问题" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="r in row.reasons"
              :key="r"
              size="small"
              type="warning"
              effect="plain"
              style="margin-right: 4px"
            >
              {{ r }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="抢答（留出集）" width="110" align="center">
          <template #default="{ row }">{{ row.questions?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center">
          <template #default="{ row }">
            <el-button
              link
              type="danger"
              size="small"
              :loading="row._saving"
              @click="toggleMetric(row)"
            >
              停用
            </el-button>
            <el-button link type="primary" size="small" @click="goConfig('/ai/integration')">
              去改名
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :image-size="60" description="没有可疑指标" />
        </template>
      </el-table>
      <template #footer>
        <el-button @click="auditVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 语言规则：词表可配（计数/物理量/排序/列举/全量） -->
    <el-dialog v-model="langVisible" title="语言规则（词表可配）" width="1000px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="这些词决定「这句话走不走指标快路径」「要不要全量列举」。改说法用它；改判定算法才动代码。"
        class="q-fb-tip"
      />
      <div v-loading="langLoading" class="q-lang">
        <div class="q-lang__switches">
          <el-checkbox v-for="s in LANG_SWITCHES" :key="s.key" v-model="langForm.switches[s.key]">
            {{ s.label }}
          </el-checkbox>
        </div>
        <div class="q-lang__grid">
          <div v-for="g in LANG_WORD_GROUPS" :key="g.key" class="q-lang__item">
            <div class="q-lang__label">
              {{ g.label }}
              <span class="q-rules__hint">{{ g.tip }}</span>
            </div>
            <el-select
              v-model="langForm[g.key]"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              style="width: 100%"
            >
              <el-option v-for="w in langForm[g.key] || []" :key="w" :label="w" :value="w" />
            </el-select>
          </div>
        </div>
        <el-divider content-position="left">指标护栏（计数型指标必须"问的就是这张表"）</el-divider>
        <div class="q-lang__grid">
          <div class="q-lang__item">
            <div class="q-lang__label">
              兄弟表限定词
              <span class="q-rules__hint">问句里点到、指标名里没有 → 不参战</span>
            </div>
            <el-select
              v-model="langGuard.sibling_qualifiers"
              multiple
              filterable
              allow-create
              default-first-option
              size="small"
              style="width: 100%"
            >
              <el-option v-for="w in langGuard.sibling_qualifiers" :key="w" :label="w" :value="w" />
            </el-select>
          </div>
          <div class="q-lang__item">
            <div class="q-lang__label">最小别名长度 / 最小核心名长度</div>
            <div style="display: flex; gap: 8px">
              <el-input-number v-model="langGuard.min_alias_len" :min="2" :max="12" size="small" />
              <el-input-number v-model="langGuard.min_core_len" :min="2" :max="12" size="small" />
            </div>
          </div>
        </div>
        <el-divider content-position="left">试一句（按当前草稿判定，不用先保存）</el-divider>
        <div class="q-rules__ab">
          <el-input
            v-model="langProbeQ"
            size="small"
            placeholder="例如：本月一共有多少份合同？"
            style="flex: 1 1 auto"
          />
          <el-button size="small" type="primary" :loading="langProbing" @click="runLangProbe">
            试一句
          </el-button>
        </div>
        <div v-if="langProbeResult" class="q-lang__probe">
          <el-tag
            v-for="t in langProbeTags"
            :key="t.label"
            :type="t.hit ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{ t.label }}：{{ t.hit ? "是" : "否" }}
          </el-tag>
          <div class="q-rules__hint">命中片段：{{ langProbeMatched }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="langVisible = false">取消</el-button>
        <el-button :loading="langLoading" @click="loadLanguageRules(true)">恢复默认</el-button>
        <el-button type="primary" :loading="langSaving" @click="saveLanguageRules">保存</el-button>
      </template>
    </el-dialog>

    <!-- 配置地图：这些「业务口径/语义」都在界面里维护，改完不用发版 -->
    <el-dialog v-model="mapVisible" title="配置地图：要改什么，去哪改" width="980px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="下面每一项都在界面里维护，改完即时生效、不用改代码。先想清楚「改的是什么」，再按「在哪改」找入口。"
        class="q-fb-tip"
      />
      <el-table :data="configMap" border stripe size="small" max-height="460">
        <el-table-column prop="what" label="要改什么" min-width="170" />
        <el-table-column prop="where" label="在哪改" min-width="240" show-overflow-tooltip />
        <el-table-column prop="when" label="什么时候用它" min-width="300" show-overflow-tooltip />
        <el-table-column label="入口" width="90" align="center">
          <template #default="{ row }">
            <el-button v-if="row.path" link type="primary" size="small" @click="goConfig(row.path)">
              前往
            </el-button>
            <span v-else class="q-rules__hint">当前页</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="mapVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 生成规则：拼进 NL2SQL 提示词的 SQL 书写规范（可启停/改文案/调顺序） -->
    <el-dialog v-model="rulesVisible" title="生成规则" width="1040px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="这些规则会拼进问数的提示词，影响模型怎么写 SQL。停用/改文案立即生效（无需重启），可在改完后用评测对比。"
        class="q-fb-tip"
      />
      <div class="q-rules__bar">
        <span class="q-rules__hint">共 {{ promptRules.length }} 条可配置规则</span>
        <el-button size="small" style="margin-left: auto" @click="openPreview">
          预览生效规则
        </el-button>
        <el-button size="small" type="primary" @click="openRuleEdit(null)">新增规则</el-button>
      </div>
      <el-table
        v-loading="rulesLoading"
        :data="promptRules"
        border
        stripe
        size="small"
        max-height="340"
      >
        <el-table-column prop="priority" label="顺序" width="70" align="center" />
        <el-table-column prop="title" label="标题" min-width="140" show-overflow-tooltip />
        <el-table-column prop="body" label="规则内容" min-width="330" show-overflow-tooltip />
        <el-table-column label="作用域" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ scopeLabel(row) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="70" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              size="small"
              :loading="row._saving"
              @change="(v: any) => toggleRule(row, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openRuleEdit(row)">编辑</el-button>
            <el-button
              v-if="!row.is_custom"
              link
              type="primary"
              size="small"
              @click="restoreRule(row)"
            >
              恢复默认
            </el-button>
            <el-button
              v-if="row.is_custom"
              link
              type="danger"
              size="small"
              @click="removeRule(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :image-size="60" description="暂无规则" />
        </template>
      </el-table>
      <div class="q-rules__core">
        <div class="q-rules__core-title">核心安全约束（只读，不可关闭）</div>
        <div v-for="(c, i) in coreRules" :key="i" class="q-rules__core-item">· {{ c }}</div>
      </div>

      <!-- A/B：本轮临时禁用若干规则去跑评测，跑完到「问数评测 → 报告」对比两次运行 -->
      <div class="q-rules__core">
        <div class="q-rules__core-title">A/B 对比（只影响这一轮评测，不改线上配置）</div>
        <div class="q-rules__ab">
          <el-select
            v-model="abDisabled"
            multiple
            collapse-tags
            clearable
            size="small"
            placeholder="选择本轮要禁用的规则"
            style="flex: 1 1 auto"
          >
            <el-option v-for="r in promptRules" :key="r.code" :label="r.title" :value="r.code" />
          </el-select>
          <el-input-number v-model="abLimit" :min="1" :max="200" size="small" />
          <el-button size="small" type="primary" :loading="abStarting" @click="startAbRun">
            启动对比评测
          </el-button>
        </div>
        <div class="q-rules__hint">
          完成后到「问数评测 → 报告 → 对比运行」选择本轮与基线，即可看到逐题翻转与准确率变化。
        </div>
      </div>
      <template #footer>
        <el-button @click="rulesVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 生效规则预览：作用域/开关是运行时过滤，列表看不出最终拼进提示词的样子 -->
    <el-dialog v-model="previewVisible" title="生效规则预览" width="760px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="`当前数据源下共 ${previewRules.length} 条规则会拼进提示词（不含核心安全约束）`"
        class="q-fb-tip"
      />
      <pre class="q-rules__preview">{{ previewText }}</pre>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 规则编辑 -->
    <el-dialog
      v-model="ruleEditVisible"
      :title="ruleForm.id ? '编辑规则' : '新增规则'"
      width="620px"
      append-to-body
    >
      <el-form :model="ruleForm" label-width="90px">
        <el-form-item label="标题">
          <el-input v-model="ruleForm.title" maxlength="120" placeholder="给规则起个短名字" />
        </el-form-item>
        <el-form-item label="规则内容">
          <el-input
            v-model="ruleForm.body"
            type="textarea"
            :rows="6"
            placeholder="直接用中文写清要求，会原样拼进提示词"
          />
        </el-form-item>
        <el-form-item label="作用域">
          <el-select v-model="ruleForm.scope" size="small" style="width: 150px">
            <el-option label="全部数据源" value="all" />
            <el-option label="仅指定数据源" value="datasource" />
            <el-option label="仅指定方言" value="dialect" />
          </el-select>
          <el-select
            v-if="ruleForm.scope === 'datasource'"
            v-model="ruleForm.scope_value"
            size="small"
            clearable
            placeholder="选择数据源"
            style="width: 220px; margin-left: 8px"
          >
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="`ds:${d.id}`"
            />
          </el-select>
          <el-select
            v-else-if="ruleForm.scope === 'dialect'"
            v-model="ruleForm.scope_value"
            size="small"
            clearable
            placeholder="选择方言"
            style="width: 160px; margin-left: 8px"
          >
            <el-option v-for="d in DIALECTS" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="顺序">
          <el-input-number v-model="ruleForm.priority" :min="1" :max="9999" size="small" />
          <span class="q-rules__hint" style="margin-left: 8px">数字小的排在前面</span>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="ruleForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleEditVisible = false">取消</el-button>
        <el-button type="primary" :loading="ruleSaving" @click="saveRule">保存</el-button>
      </template>
    </el-dialog>

    <!-- 召回探针：语义召回到底选了哪些表（排查"答错表/漏表"用） -->
    <el-dialog v-model="probeVisible" title="召回探针" width="640px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="输入一个问题，查看语义召回最终选中的表（四通道融合后的结果）"
        class="q-fb-tip"
      />
      <div class="q-probe__bar">
        <el-input
          v-model="probeQuestion"
          placeholder="例如：上个月入厂煤量总和"
          clearable
          @keyup.enter="runProbe"
        />
        <el-button type="primary" :loading="probeLoading" @click="runProbe">开始探测</el-button>
      </div>
      <div v-if="probeDone" class="q-probe__result">
        <div class="q-probe__count">命中 {{ probeTables.length }} 张表</div>
        <div class="q-probe__tags">
          <el-tag v-for="t2 in probeTables" :key="t2" size="small" effect="plain">{{ t2 }}</el-tag>
          <el-empty v-if="!probeTables.length" :image-size="48" description="没有召回任何表" />
        </div>
      </div>
      <template #footer>
        <el-button :loading="probeRebuilding" @click="doRebuildRecall">重建召回单元</el-button>
        <el-button @click="probeVisible = false">{{ t("ai_logs.cancel") }}</el-button>
      </template>
    </el-dialog>
  </div>

  <el-drawer v-model="traceVisible" :title="t('ai_logs.traceTitle')" size="560px" append-to-body>
    <template v-if="traceMsg">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item :label="t('ai_logs.tracePath')">
          {{ traceMsg.path || "-" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.traceTook')">
          {{ traceMsg.took_ms ?? 0 }} ms · {{ traceMsg.result_rows ?? 0 }} 行
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.traceApplied')">
          <el-tag
            v-for="(a, i) in traceMsg.applied || []"
            :key="i"
            size="small"
            type="warning"
            effect="plain"
            style="margin-right: 4px"
          >
            {{ Object.values(a).join(" · ") }}
          </el-tag>
          <span v-if="!(traceMsg.applied || []).length">—</span>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.tracePolicy')">
          {{ (traceMsg.policy_ids || []).join(", ") || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.traceRecall')">
          {{ (traceMsg.grounding?.retrieved || []).join("、") || "—" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_logs.traceOntology')">
          {{ (traceMsg.grounding?.ontology_used || []).join("、") || "—" }}
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="traceMsg.is_error"
        :title="traceMsg.error || traceMsg.summary || t('ai_logs.traceError')"
        type="error"
        :closable="false"
        show-icon
        style="margin-top: 10px"
      />
      <div v-if="traceMsg.sql" class="q-trace__sql">
        <CodeBlock :code="traceMsg.sql" language="sql" />
      </div>
      <div class="q-trace__actions">
        <el-button size="small" @click="copyTrace">{{ t("ai_logs.traceCopyDiag") }}</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import ChatShell from "@/components/chat/ChatShell.vue";
import ChatMessage from "@/components/chat/ChatMessage.vue";
import CodeBlock from "@/components/chat/CodeBlock.vue";
import ChatOutline from "@/components/chat/ChatOutline.vue";
import ReasoningBlock from "@/views/module_ai/chat/components/ReasoningBlock.vue";
import ToolCallTimeline from "@/views/module_ai/chat/components/ToolCallTimeline.vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createPromptRule,
  deletePromptRule,
  deleteQuerySession,
  getPromptRules,
  getQueryDatasources,
  getEntityMap,
  getQueryAssets,
  getLanguageRules,
  getMetricsAudit,
  getQueryFewshots,
  getQueryMessages,
  getQuerySessions,
  getQuerySettings,
  getQuerySettingsDefaults,
  queryFeedback,
  promoteQueryMetric,
  getQueryStats,
  previewPromptRules,
  probeLanguageRules,
  resetPromptRule,
  runQueryReport,
  saveQueryReport,
  saveQuerySetting,
  setMetricEnabled,
  startEvalRun,
  streamQuery,
  recallProbe,
  rebuildRecall,
  updatePromptRule,
} from "@/api/module_ai/query";

defineOptions({ name: "AiQuery" });

const { t } = useI18n();

const router = useRouter();
const route = useRoute();

const sessions = ref<any[]>([]);
const messages = ref<any[]>([]);

const datasources = ref<any[]>([]);
const sessionId = ref<number | null>(null);
const datasource = ref("system");
const question = ref("");
const asking = ref(false);
// 当前对象上下文（从本体/实例页跳转而来）：作为**确定性上下文**注入，不是让模型自己找
const objectCode = ref("");
const objectKey = ref("");

const examples = ref<string[]>([
  t("ai_logs.example1"),
  t("ai_logs.example2"),
  t("ai_logs.example3"),
]);

/** 把「列 + 二维数组」转成 el-table 需要的对象数组。 */
function rowsOf(m: any) {
  const cols: string[] = m.columns || [];
  return (m.rows || []).map((r: any[]) => {
    const o: Record<string, any> = {};
    cols.forEach((c, i) => {
      o[c] = r[i];
    });
    return o;
  });
}

/** 生成路径标签：指标模板 / 对象查询 / NL2SQL / 报表。 */
function pathLabel(m: any): string {
  if (m?.path === "fast") return t("ai_logs.pathMetric");
  if (m?.path === "object") return t("ai_logs.pathObjectQuery");
  if (m?.path === "slow") return "NL2SQL";
  if (m?.path === "report") return t("ai_logs.pathReport");
  if (m?.path === "report_suggest") return t("ai_logs.pathReportSuggest");
  if (m?.path === "clarify") return t("ai_logs.pathClarify");
  return m?.path || t("ai_logs.pathQuery");
}

/** 对象查询 IR —— 优先读落库的 grounding（历史消息也有），其次兼容即时响应。 */
function irOf(m: any): any | null {
  return m?.grounding?.ir || m?.ir || null;
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
  sessionId.value = id;
  try {
    const r = await getQueryMessages(id);
    messages.value = r.data?.data || [];
  } catch {
    messages.value = [];
  }
}

function newSession() {
  sessionId.value = null;
  messages.value = [];
  question.value = "";
}

async function removeSession(s: any) {
  await ElMessageBox.confirm(
    t("ai_logs.removeSessionMsg", { title: s.title || t("ai_logs.unnamed") }),
    t("ai_logs.removeSession"),
    {
      type: "warning",
      confirmButtonText: t("ai_logs.delete"),
      cancelButtonText: t("ai_logs.cancel"),
    }
  );
  await deleteQuerySession(s.id);
  ElMessage.success(t("ai_logs.deleted"));
  if (sessionId.value === s.id) newSession();
  await loadSessions();
}

// 本体依据默认收起：召回表一多就是一堵墙，需要时再展开
const ontoOpenMap = ref<Record<number, boolean>>({});
const ontoOpen = (i: number) => !!ontoOpenMap.value[i];
function toggleOnto(i: number) {
  ontoOpenMap.value = { ...ontoOpenMap.value, [i]: !ontoOpen(i) };
}

/** 问数的工具状态 → 公共 ToolCallTimeline 需要的 AiUIPart 形状 */
function partsOf(m: any) {
  return (m.tools || []).map((tool: any, i: number) => ({
    type: `tool-${tool.name || "tool"}`,
    toolName: tool.name || "tool",
    toolCallId: `q-${i}`,
    state:
      tool.status === "error"
        ? "output-error"
        : tool.status === "running"
          ? "input-available"
          : "output-available",
    input: tool.input,
    output: tool.output,
    errorText: tool.error,
  }));
}

/** 长会话导航：按顺序列出用户提过的每个问题 */
const outlineItems = computed(() =>
  (messages.value || []).map((m: any, i: number) => ({
    id: `q-turn-${i}`,
    text: String(m.question || "").slice(0, 80),
  }))
);

async function ask() {
  const q = question.value.trim();
  if (!q) {
    ElMessage.warning(t("ai_logs.pleaseInputQuestion"));
    return;
  }
  asking.value = true;
  const cur: any = {
    question: q,
    streaming: true,
    reasoning: "",
    tools: [],
    sql: "",
    columns: [],
    rows: [],
    result_rows: 0,
    summary: "",
    path: "",
  };
  messages.value = [...messages.value, cur];
  // 局部刷新占位消息（触发渲染）
  const flush = () => {
    messages.value = messages.value.map((x) => (x === cur ? { ...cur } : x));
  };
  try {
    let hasResult = false;
    for await (const ev of streamQuery({
      question: q,
      session_id: sessionId.value || null,
      datasource: datasource.value || null,
      object_code: objectCode.value || null,
      object_key: objectKey.value || null,
    })) {
      const evt = ev?.type;
      const d = ev?.data || {};
      if (evt === "meta") {
        if (d.session_id && !sessionId.value) sessionId.value = d.session_id;
        cur.datasource = d.datasource || cur.datasource;
      } else if (evt === "reasoning") {
        cur.reasoning += d.delta || "";
      } else if (evt === "reasoning_done") {
        flush();
      } else if (evt === "sql_delta") {
        cur.sql += d.delta || "";
      } else if (evt === "sql_final") {
        cur.sql = d.sql || cur.sql;
        cur.path = "slow";
      } else if (evt === "tool_start") {
        cur.tools.push({ name: d.name || t("ai_logs.tool"), status: "running" });
      } else if (evt === "tool_result" || evt === "tool_error") {
        const last = cur.tools[cur.tools.length - 1];
        if (last) last.status = evt === "tool_result" ? "done" : "error";
      } else if (evt === "ir") {
        cur.ir = d.ir || {};
        cur.path = "object";
        if (d.pending_clarify) cur.pending_clarify = d.pending_clarify;
        flush();
      } else if (evt === "result") {
        cur.columns = d.columns || [];
        cur.rows = d.rows || [];
        cur.result_rows = d.result_rows ?? (d.rows || []).length;
        cur.took_ms = d.took_ms;
        cur.sql = d.sql || cur.sql;
        cur.applied = d.applied || [];
        cur.policy_ids = d.policy_ids || [];
        cur.path = cur.path || d.path || "result";
        // 后端字段名是 retrieved / ontology_used，渲染函数（recalledOf/ontologyOf）只认
        // grounding 这一层；之前这里读的是 d.recalled / d.ontology（两个都不存在），
        // 也没落到 grounding → 直播期间标签永远不出现，必须刷新才看得到。
        if (d.retrieved || d.ontology_used) {
          cur.grounding = {
            ...(cur.grounding || {}),
            retrieved: d.retrieved,
            ontology_used: d.ontology_used,
          };
        }
        // message_id：「有用/没用/存为报表/沉淀为指标」按钮按 v-if="m.id" 门控，
        // 不带上它就必须刷新或点开旧会话才能看到（反馈闭环断在最关键时刻）。
        if (d.message_id) cur.id = d.message_id;
        hasResult = true;
        flush();
      } else if (evt === "clarify") {
        cur.path = "clarify";
        cur.clarify = d.clarify || {};
      } else if (evt === "report_suggest") {
        cur.path = "report_suggest";
        cur.reports = d.reports || [];
      } else if (evt === "answer") {
        cur.summary = d.summary || "";
        flush();
      } else if (evt === "error") {
        cur.is_error = true;
        cur.summary = d.message || d || t("ai_logs.queryFailed");
      }
    }
    cur.streaming = false;
    flush();
    question.value = "";
    if (cur.path === "clarify" && cur.clarify) {
      clarify.value = { ...cur.clarify, _q: q };
      clarifyPick.value = "";
      clarifyVisible.value = true;
      return;
    }
    if (cur.path === "report_suggest" && cur.reports?.length) {
      reportSuggestList.value = cur.reports;
      reportSuggestVisible.value = true;
      return;
    }
    if (cur.is_error) ElMessage.error(cur.summary || t("ai_logs.queryFailed"));
    else ElMessage.success(hasResult ? t("ai_logs.queryDone") : t("ai_logs.done"));
    await loadSessions();
  } catch (e: any) {
    cur.streaming = false;
    cur.is_error = true;
    cur.summary = e?.data?.msg || e?.msg || e?.message || t("ai_logs.askFailed");
    flush();
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.askFailed"));
  } finally {
    asking.value = false;
  }
}

/** 用户回答澄清：把选择拼回问句再问一次（复用同一链路，形成多轮）。 */
async function answerClarify() {
  const c = clarify.value;
  if (!c || !clarifyPick.value) return;
  const label =
    (c.options || []).find((o: any) => o.value === clarifyPick.value)?.label || clarifyPick.value;
  clarifyVisible.value = false;
  question.value = `${c._q}\n${t("ai_logs.clarifyGroup", { label })}`;
  await ask();
}

/** 把这次问答沉淀成报表模板（草稿，需人工确认后才长期复用）。 */
function openSaveReport(m: any) {
  srMsg.value = m;
  srName.value = "";
  srVisible.value = true;
}

async function submitSaveReport() {
  const m = srMsg.value;
  if (!m?.sql) {
    ElMessage.warning(t("ai_logs.noSaveableSql"));
    return;
  }
  srLoading.value = true;
  try {
    const key = `r_${Date.now().toString(36)}`;
    await saveQueryReport({
      key,
      name: srName.value.trim() || m.question.slice(0, 20),
      datasource: m.datasource || datasource.value || "system",
      question: m.question,
      sql_template: m.sql,
      columns: (m.columns || []).map((c: string) => ({ name: c, label: c })),
      verified: false,
    });
    ElMessage.success(t("ai_logs.savedReportDraft"));
    srVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.saveFailed"));
  } finally {
    srLoading.value = false;
  }
}

/** 本轮召回的表——**优先读落库的 `grounding`**（历史消息也有），其次兼容即时响应。 */
function recalledOf(m: any): string[] {
  const fromGrounding = m?.grounding?.retrieved?.tables || [];
  if (fromGrounding.length) return fromGrounding;
  const rt = m?.evidence?.retrieved_tables || [];
  if (rt.length) return rt;
  return m?.ontology_used || [];
}

/** 命中的**本体对象**（本体物化表 `ont_*`）：证明"本体确实参与了这个回答"。 */
function ontologyOf(m: any): string[] {
  const fromGrounding = m?.grounding?.ontology_used || [];
  if (fromGrounding.length) return fromGrounding;
  return m?.ontology_used || [];
}

/** 双向闭环：问数 → 本体（去核对语义定义）。 */
function goOntology() {
  router.push("/ai/ontology");
}
function goSub(path: string) {
  router.push(path);
}
const tipHidden = ref(localStorage.getItem("q_tip_hidden") === "1");
function hideTip() {
  tipHidden.value = true;
  localStorage.setItem("q_tip_hidden", "1");
}
async function loadExamples() {
  try {
    const r = await getQueryFewshots({});
    const list = r.data?.data || [];
    const qs = list
      .filter((x: any) => x.enabled !== false && x.question)
      .map((x: any) => x.question);
    if (qs.length) examples.value = qs.slice(0, 8);
  } catch {
    /* 保留默认示例 */
  }
}

// ---------------------------------------------------------------------------
// 问数设置（工程开关）：对象查询（语义执行）等
// ---------------------------------------------------------------------------
const SETTING_DEFS = [
  {
    key: "object_query_enabled",
    label: t("ai_logs.settingObjectQuery"),
    type: "bool",
    tip: t("ai_logs.settingObjectQueryTip"),
  },
  {
    key: "query_cost_enabled",
    label: t("ai_logs.settingQueryCost"),
    type: "bool",
    tip: t("ai_logs.settingQueryCostTip"),
  },
  {
    key: "object_query_auto_index_enabled",
    label: t("ai_logs.settingAutoIndex"),
    type: "bool",
    tip: t("ai_logs.settingAutoIndexTip"),
  },
  {
    key: "object_query_model",
    label: t("ai_logs.settingIrModel"),
    type: "text",
    tip: t("ai_logs.settingIrModelTip"),
  },
  {
    key: "empty_self_correct",
    label: t("ai_logs.settingEmptySelfCorrect"),
    type: "bool",
    tip: t("ai_logs.settingEmptySelfCorrectTip"),
  },
  {
    key: "recall_enabled",
    label: t("ai_logs.settingRecall"),
    type: "bool",
    tip: t("ai_logs.settingRecallTip"),
  },
  {
    key: "two_stage_planning",
    label: t("ai_logs.settingTwoStage"),
    type: "bool",
    tip: t("ai_logs.settingTwoStageTip"),
  },
  {
    key: "agno_tool_agent",
    label: t("ai_logs.settingToolAgent"),
    type: "bool",
    tip: t("ai_logs.settingToolAgentTip"),
  },
  {
    key: "self_consistency_n",
    label: t("ai_logs.settingSelfConsistency"),
    type: "int",
    min: 1,
    max: 9,
    tip: t("ai_logs.settingSelfConsistencyTip"),
  },
  // ---- 本轮补的 6 个开关 ----
  // 这 6 个 key 后端一直在读，但**之前没有界面入口**：想改只能自己去 UPDATE
  // ai_query_settings 表。其中「列裁剪 / 值匹配纠错」还是我做的 A/B 开关，
  // 说好"可回退"却没有回退按钮 —— 这属于典型的"逻辑写了、入口没接"。
  {
    key: "schema_column_prune_enabled",
    label: t("ai_logs.settingColumnPrune"),
    type: "bool",
    tip: t("ai_logs.settingColumnPruneTip"),
  },
  {
    key: "literal_fix_enabled",
    label: t("ai_logs.settingLiteralFix"),
    type: "bool",
    tip: t("ai_logs.settingLiteralFixTip"),
  },
  {
    key: "recall_top_k",
    label: t("ai_logs.settingRecallTopK"),
    type: "int",
    min: 1,
    max: 30,
    tip: t("ai_logs.settingRecallTopKTip"),
  },
  {
    key: "nl2sql_retry",
    label: t("ai_logs.settingNl2sqlRetry"),
    type: "int",
    min: 1,
    max: 5,
    tip: t("ai_logs.settingNl2sqlRetryTip"),
  },
  {
    key: "query_timeout_sec",
    label: t("ai_logs.settingQueryTimeout"),
    type: "int",
    min: 1,
    max: 600,
    tip: t("ai_logs.settingQueryTimeoutTip"),
  },
  {
    key: "lineage_enabled",
    label: t("ai_logs.settingLineage"),
    type: "bool",
    tip: t("ai_logs.settingLineageTip"),
  },
  {
    key: "sql_softdelete_rewrite_enabled",
    label: t("ai_logs.settingSoftDeleteRewrite"),
    type: "bool",
    tip: t("ai_logs.settingSoftDeleteRewriteTip"),
  },
  {
    key: "query_max_rows",
    label: t("ai_logs.settingMaxRows"),
    type: "int",
    min: 1,
    max: 5000,
    tip: t("ai_logs.settingMaxRowsTip"),
  },
] as const;

const setVisible = ref(false);
const setLoading = ref(false);
const setSaving = ref(false);
const setLoaded = ref<Record<string, string>>({});
const setForm = ref<Record<string, string>>({});

// 召回探针：输入一个问题，看语义召回选中了哪些表（调语义层用），并支持重建召回单元
const probeVisible = ref(false);
const probeLoading = ref(false);
const probeRebuilding = ref(false);
const probeQuestion = ref("");
const probeTables = ref<string[]>([]);
const probeDone = ref(false);

async function runProbe() {
  const q = probeQuestion.value.trim();
  if (!q) {
    ElMessage.warning("请输入一个问题");
    return;
  }
  probeLoading.value = true;
  probeDone.value = false;
  try {
    const r: any = await recallProbe(q);
    probeTables.value = r.data?.data?.final || [];
    probeDone.value = true;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "召回探测失败");
  } finally {
    probeLoading.value = false;
  }
}

async function doRebuildRecall() {
  try {
    await ElMessageBox.confirm(
      "将按当前资产、术语与指标重建语义召回单元；重建期间召回可能短暂不完整。是否继续？",
      "重建召回单元",
      { type: "warning", confirmButtonText: "重建", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  probeRebuilding.value = true;
  try {
    await rebuildRecall();
    ElMessage.success("召回单元已重建");
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "重建失败");
  } finally {
    probeRebuilding.value = false;
  }
}

async function openSettings() {
  setVisible.value = true;
  setLoading.value = true;
  // 先用默认值铺底：**必须在 await 之前**赋值，否则弹窗渲染时开关绑定到 undefined，
  // Element Plus 会报 "[ElSwitch] model-value must be active-value or inactive-value"。
  const base: Record<string, string> = {};
  ALL_DEFS.forEach((d: any) => {
    base[d.key] = d.type === "bool" ? "false" : d.type === "text" ? "" : "1";
  });
  setForm.value = { ...base };
  setLoaded.value = { ...base };
  try {
    const [r, rd] = await Promise.all([getQuerySettings(), getQuerySettingsDefaults()]);
    const d = r.data?.data || {};
    const rawDefaults = rd.data?.data || {};
    setDefaults.value = Object.fromEntries(
      Object.entries(rawDefaults).map(([k, v]) => [k, String(v ?? "")])
    );
    const merged: Record<string, string> = { ...base };
    ALL_DEFS.forEach((x: any) => {
      if (d[x.key] !== undefined && d[x.key] !== null) merged[x.key] = String(d[x.key]);
    });
    setLoaded.value = { ...merged };
    setForm.value = { ...merged };
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.readSettingsFailed"));
  } finally {
    setLoading.value = false;
  }
}

function resetOne(d: any) {
  const v = setDefaults.value[d.key];
  if (v !== undefined) setForm.value[d.key] = v;
}

async function resetAll() {
  try {
    await ElMessageBox.confirm(t("ai_logs.settingResetConfirm"), t("ai_logs.settingResetAll"), {
      type: "warning",
      confirmButtonText: t("ai_logs.settingResetAll"),
      cancelButtonText: t("ai_logs.cancel"),
    });
  } catch {
    return;
  }
  const next: Record<string, string> = { ...setForm.value };
  ALL_DEFS.forEach((d: any) => {
    if (setDefaults.value[d.key] !== undefined) next[d.key] = setDefaults.value[d.key];
  });
  setForm.value = next;
}

async function saveSettings() {
  setSaving.value = true;
  try {
    const changed = ALL_DEFS.filter(
      (d) => (setForm.value[d.key] ?? "") !== (setLoaded.value[d.key] ?? "")
    );
    if (!changed.length) {
      ElMessage.info(t("ai_logs.noSettingsChanged"));
      setVisible.value = false;
      return;
    }
    for (const d of changed) {
      await saveQuerySetting({
        key: d.key,
        value: String(setForm.value[d.key] ?? ""),
        remark: d.label,
      });
    }
    ElMessage.success(t("ai_logs.savedSettingsCount", { count: changed.length }));
    setVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.saveSettingsFailed"));
  } finally {
    setSaving.value = false;
  }
}

// ---- 实体映射（业务词 → 表）：召回「实体通道」用 ----
const entVisible = ref(false);
const entLoading = ref(false);
const entSaving = ref(false);
const entForm = ref<Array<{ noun: string; tables: string[] }>>([]);
const entTables = ref<string[]>([]);

async function openEntityMap() {
  entVisible.value = true;
  entLoading.value = true;
  try {
    const [r, assets] = await Promise.all([getEntityMap(), getQueryAssets()]);
    const eff = r.data?.data?.effective || {};
    entForm.value = Object.keys(eff)
      .sort()
      .map((k) => ({ noun: k, tables: [...(eff[k] || [])] }));
    const list = assets.data?.data || [];
    entTables.value = Array.from(
      new Set(list.map((x: any) => String(x.table_name || x.table || "")).filter(Boolean))
    ).sort() as string[];
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "加载实体映射失败");
  } finally {
    entLoading.value = false;
  }
}

async function saveEntityMap() {
  const map: Record<string, string[]> = {};
  for (const row of entForm.value) {
    const noun = String(row.noun || "").trim();
    const tables = (row.tables || []).map((t) => String(t).trim()).filter(Boolean);
    if (noun && tables.length) map[noun] = tables;
  }
  entSaving.value = true;
  try {
    await saveQuerySetting({
      key: "entity_map",
      value: JSON.stringify(map),
      remark: "实体名词→表",
    });
    ElMessage.success("已保存，下一句问数立即生效");
    entVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "保存失败");
  } finally {
    entSaving.value = false;
  }
}

async function resetEntityMap() {
  entSaving.value = true;
  try {
    await saveQuerySetting({ key: "entity_map", value: "{}", remark: "恢复默认实体映射" });
    ElMessage.success("已恢复默认（代码内置映射）");
    await openEntityMap();
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "恢复失败");
  } finally {
    entSaving.value = false;
  }
}

// ---- 指标体检（脏指标/抢答题）----
const auditVisible = ref(false);
const auditLoading = ref(false);
const auditRows = ref<any[]>([]);
const auditStats = ref<any>({});

async function openAudit() {
  auditVisible.value = true;
  auditLoading.value = true;
  try {
    const ds = currentDs() || "ds:6";
    const r = await getMetricsAudit({ datasource: ds, top: 100 });
    const d = r.data?.data || {};
    auditStats.value = d;
    auditRows.value = (d.items || []).map((x: any) => ({ ...x, _saving: false }));
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "加载指标体检失败");
  } finally {
    auditLoading.value = false;
  }
}

async function toggleMetric(row: any) {
  try {
    await ElMessageBox.confirm(
      `将停用指标「${row.name}」。停用后该指标不再参与快路径，可随时在指标页重新启用。`,
      "停用指标",
      { type: "warning", confirmButtonText: "停用", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  row._saving = true;
  try {
    await setMetricEnabled({ key: row.key, enabled: false });
    ElMessage.success("已停用");
    await openAudit();
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "停用失败");
  } finally {
    row._saving = false;
  }
}

// ---- 语言规则（词表可配）：改说法不用发版 ----
const langVisible = ref(false);
const langLoading = ref(false);
const langSaving = ref(false);
const langProbing = ref(false);
const langForm = ref<any>({ switches: {} });
const langProbeQ = ref("");
const langProbeResult = ref<any>(null);
const langGuard = ref<any>({ sibling_qualifiers: [], min_alias_len: 4, min_core_len: 3 });
const LANG_SWITCHES = [
  { key: "count_intent", label: "计数意图（多少份/多少个）" },
  { key: "physical_qty", label: "物理量优先（库存/合计/吨数）" },
  { key: "rowcount", label: "明确问条数（多少条/记录数）" },
  { key: "order", label: "排序诉求（排序/前N/最高）" },
  { key: "listing", label: "列举类（哪些/列出）" },
  { key: "all_list", label: "全量列举（每个/所有）" },
];
const LANG_WORD_GROUPS = [
  { key: "count_quantifiers", label: "计数·疑问词", tip: "多少 / 几" },
  { key: "count_units", label: "计数·量词", tip: "条 / 份 / 个…" },
  { key: "count_nouns", label: "计数·名词", tip: "数量 / 条数…" },
  { key: "physical_qty_words", label: "物理量词", tip: "库存 / 合计 / 吨数…" },
  { key: "rowcount_ask_words", label: "明确问条数", tip: "多少条 / 记录数…" },
  { key: "order_words", label: "排序词", tip: "排序 / 升序 / 最高…" },
  { key: "non_count_prefixes", label: "非计数指标前缀", tip: "平均 / 最大…" },
  { key: "listing_words", label: "列举词", tip: "哪些 / 列出…" },
  { key: "listing_verbs", label: "列举动词", tip: "列出 / 清单…" },
  { key: "count_override_words", label: "计数覆盖词", tip: "条数 / 合计…" },
  { key: "all_list_words", label: "全量列举词", tip: "每个 / 所有…" },
  { key: "agg_over_groups_words", label: "组上聚合词", tip: "平均 / 占比…" },
  { key: "group_words", label: "分组词", tip: "每个 / 各…" },
  { key: "group_nouns", label: "分组触发名词", tip: "数量 / 统计…" },
];
const LANG_PROBE_LABELS: Record<string, string> = {
  count_intent: "计数意图",
  physical_qty: "物理量",
  rowcount_ask: "问条数",
  order: "排序",
  listing: "列举",
  all_list: "全量列举",
  grouping: "分组",
  non_count_prefix: "非计数前缀",
  listing_verb: "列举动词",
  count_override: "计数覆盖",
  agg_over_groups: "组上聚合",
};

async function loadLanguageRules(useDefaults = false) {
  langLoading.value = true;
  try {
    const r = await getLanguageRules();
    const d = r.data?.data || {};
    const src = useDefaults ? d.defaults : d.effective;
    langForm.value = { switches: { ...(src?.switches || {}) } };
    LANG_WORD_GROUPS.forEach((g) => {
      langForm.value[g.key] = Array.isArray(src?.[g.key]) ? [...src[g.key]] : [];
    });
    langProbeResult.value = null;
    // 指标护栏参数：后端返回**生效值**（默认 + 覆盖），界面显示的就是实际在用的
    const g = (r.data?.data?.guard || {}) as any;
    langGuard.value = {
      sibling_qualifiers: Array.isArray(g.sibling_qualifiers) ? g.sibling_qualifiers : [],
      min_alias_len: Number(g.min_alias_len || 4),
      min_core_len: Number(g.min_core_len || 3),
    };
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "加载语言规则失败");
  } finally {
    langLoading.value = false;
  }
}

function openLanguageRules() {
  langVisible.value = true;
  loadLanguageRules(false);
}

async function saveLanguageRules() {
  langSaving.value = true;
  try {
    const payload: any = { switches: { ...langForm.value.switches } };
    LANG_WORD_GROUPS.forEach((g) => {
      payload[g.key] = langForm.value[g.key] || [];
    });
    await saveQuerySetting({
      key: "query_language_rules",
      value: JSON.stringify(payload),
      remark: "语言规则（词表可配）",
    });
    await saveQuerySetting({
      key: "metric_guard_rules",
      value: JSON.stringify(langGuard.value),
      remark: "指标护栏参数",
    });
    ElMessage.success("已保存，下一句问数立即生效");
    await loadLanguageRules(false);
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "保存失败");
  } finally {
    langSaving.value = false;
  }
}

const langProbeTags = computed(() => {
  const res = langProbeResult.value || {};
  return Object.keys(LANG_PROBE_LABELS).map((k) => ({
    label: LANG_PROBE_LABELS[k],
    hit: !!res[k],
  }));
});

const langProbeMatched = computed(() => {
  const m = langProbeResult.value?.matched || {};
  const parts = Object.entries(m)
    .filter(([, v]) => !!v)
    .map(([k, v]) => `${LANG_PROBE_LABELS[k] || k}=${v}`);
  return parts.length ? parts.join("，") : "（没有命中词）";
});

async function runLangProbe() {
  const q = String(langProbeQ.value || "").trim();
  if (!q) {
    ElMessage.warning("先输入一句话");
    return;
  }
  langProbing.value = true;
  try {
    const payload: any = { switches: { ...langForm.value.switches } };
    LANG_WORD_GROUPS.forEach((g) => {
      payload[g.key] = langForm.value[g.key] || [];
    });
    const r = await probeLanguageRules({ question: q, rules: payload });
    langProbeResult.value = r.data?.data || {};
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "预览失败");
  } finally {
    langProbing.value = false;
  }
}

// ---- 配置地图：业务口径/语义各自在哪维护（避免「界面功能很多但不知道怎么用」）----
const mapVisible = ref(false);
const configMap = [
  {
    what: "业务术语 / 同义词",
    where: "数据与集成 → 术语",
    when: "用户说的词和字段名对不上（如「全水分」「热值」）",
    path: "/ai/integration",
  },
  {
    what: "指标口径",
    where: "数据与集成 → 指标",
    when: "同一个业务数字有固定算法（库存、总量、合同数量）",
    path: "/ai/integration",
  },
  {
    what: "表/字段含义、别名、枚举",
    where: "数据与集成 → 表与字段",
    when: "模型选错表、看不懂某列是什么意思",
    path: "/ai/integration",
  },
  {
    what: "对象 / 属性 / 关系 / 业务函数",
    where: "知识与本体 → 本体",
    when: "要按业务对象查，或有公司自己的计算公式",
    path: "/ai/ontology",
  },
  {
    what: "表间关联 / 影响面",
    where: "数据与集成 → 数据关系图",
    when: "多表联查、想知道改一张表会波及谁",
    path: "/ai/integration",
  },
  {
    what: "示例问答（few-shot）",
    where: "数据与集成 → 示例工程",
    when: "某类问法反复答错，且你能写出标准 SQL",
    path: "/ai/integration",
  },
  {
    what: "实体名词 → 表",
    where: "问数设置 → 实体映射",
    when: "用户说的业务词没把正确的表召回（如说「矿点」要优先查供应商矿点表）",
    path: "",
  },
  {
    what: "语言规则（词表）",
    where: "问数设置 → 语言规则",
    when: "「多少份/清单/合计」这类说法判得不对，或要关掉某类判定",
    path: "",
  },
  {
    what: "提示词书写规范",
    where: "问数设置 → 生成规则",
    when: "想让 SQL 带中文别名、换行、排序排除空值等",
    path: "",
  },
  {
    what: "软删列名 / 「已删除」的说法",
    where: "数据与集成 → 数据源 → 编辑 → 软删口径",
    when: "业务表不是 ISDELETED，或说法不是「已删除」",
    path: "/ai/integration",
  },
  {
    what: "时间口径（周起始 / 月份）",
    where: "数据与集成 → 数据源 → 编辑 → 时间口径",
    when: "「本周」按周日起，或「上个月」按滚动 30 天",
    path: "/ai/integration",
  },
  {
    what: "开关与阈值",
    where: "问数设置（简单 / 专家模式）",
    when: "召回数量、超时、重试、思考档位等",
    path: "",
  },
  {
    what: "权限（表 / 行 / 列 / 模块）",
    where: "问数设置 → 权限策略 / 治理",
    when: "某角色只能看部分表、部分行或部分列",
    path: "",
  },
];

function goConfig(path: string) {
  mapVisible.value = false;
  router.push(path);
}

// ---- 生成规则（可配置提示词规则）----
const rulesVisible = ref(false);
const rulesLoading = ref(false);
const promptRules = ref<any[]>([]);
const coreRules = ref<string[]>([]);
const ruleEditVisible = ref(false);
const ruleSaving = ref(false);
const ruleForm = ref<any>({
  id: null,
  title: "",
  body: "",
  priority: 900,
  enabled: true,
});

async function loadPromptRules() {
  rulesLoading.value = true;
  try {
    const r = await getPromptRules();
    promptRules.value = (r.data?.data?.items || []).map((x: any) => ({ ...x, _saving: false }));
    coreRules.value = r.data?.data?.core_rules || [];
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "加载生成规则失败");
  } finally {
    rulesLoading.value = false;
  }
}

async function openPromptRules() {
  rulesVisible.value = true;
  await loadPromptRules();
}

function openRuleEdit(row: any | null) {
  ruleForm.value = row
    ? {
        id: row.id,
        title: row.title,
        body: row.body,
        priority: row.priority,
        enabled: row.enabled,
        scope: row.scope || "all",
        scope_value: row.scope_value || "",
      }
    : {
        id: null,
        title: "",
        body: "",
        priority: 900,
        enabled: true,
        scope: "all",
        scope_value: "",
      };
  ruleEditVisible.value = true;
}

async function toggleRule(row: any, value: any) {
  row._saving = true;
  try {
    await updatePromptRule(row.id, { enabled: !!value });
    ElMessage.success(value ? "已启用" : "已停用");
  } catch (e: any) {
    row.enabled = !value;
    ElMessage.error(e?.data?.msg || e?.msg || "保存失败");
  } finally {
    row._saving = false;
  }
}

async function saveRule() {
  if (!String(ruleForm.value.body || "").trim()) {
    ElMessage.warning("规则内容不能为空");
    return;
  }
  ruleSaving.value = true;
  try {
    if (ruleForm.value.id) {
      await updatePromptRule(ruleForm.value.id, {
        title: ruleForm.value.title,
        body: ruleForm.value.body,
        priority: ruleForm.value.priority,
        enabled: ruleForm.value.enabled,
        scope: ruleForm.value.scope,
        scope_value: ruleForm.value.scope === "all" ? "" : ruleForm.value.scope_value,
      });
    } else {
      await createPromptRule({
        title: ruleForm.value.title,
        body: ruleForm.value.body,
        priority: ruleForm.value.priority,
        enabled: ruleForm.value.enabled,
        scope: ruleForm.value.scope,
        scope_value: ruleForm.value.scope === "all" ? "" : ruleForm.value.scope_value,
      });
    }
    ElMessage.success("已保存");
    ruleEditVisible.value = false;
    await loadPromptRules();
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "保存失败");
  } finally {
    ruleSaving.value = false;
  }
}

async function restoreRule(row: any) {
  try {
    await ElMessageBox.confirm(
      `将把「${row.title}」恢复为内置默认文案，你改过的内容会丢失。`,
      "恢复默认",
      { type: "warning", confirmButtonText: "恢复默认", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await resetPromptRule(row.id);
    ElMessage.success("已恢复默认");
    await loadPromptRules();
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "恢复失败");
  }
}

async function removeRule(row: any) {
  try {
    await ElMessageBox.confirm(`将删除自定义规则「${row.title}」，删除后不可恢复。`, "删除规则", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deletePromptRule(row.id);
    ElMessage.success("已删除");
    await loadPromptRules();
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "删除失败");
  }
}

// ---- 生成规则：作用域 / 预览 / A/B ----
const DIALECTS = ["PostgreSQL", "MySQL", "SQLite"];
const previewVisible = ref(false);
const previewRules = ref<string[]>([]);
const previewText = ref("");
const abDisabled = ref<string[]>([]);
const abLimit = ref(105);
const abStarting = ref(false);

function scopeLabel(row: any) {
  const scope = row.scope || "all";
  if (scope === "datasource") return `数据源：${row.scope_value || "未指定"}`;
  if (scope === "dialect") return `方言：${row.scope_value || "未指定"}`;
  return "全部";
}

/** 当前页面选中的数据源 → 内部标识（ds:{id}）；system/空 → 空串（评测不限数据源） */
function currentDs(): string {
  const v = datasource.value;
  if (!v || v === "system") return "";
  if (/^ds:\d+$/.test(v)) return v;
  const hit = datasources.value.find((d: any) => (d.code || `ds:${d.id}`) === v);
  return hit ? `ds:${hit.id}` : "";
}

async function openPreview() {
  try {
    const r = await previewPromptRules({ datasource: currentDs() });
    previewRules.value = r.data?.data?.rules || [];
    previewText.value = r.data?.data?.text || "（当前没有会生效的规则）";
  } catch (e: any) {
    previewText.value = e?.data?.msg || e?.msg || "预览失败";
  }
  previewVisible.value = true;
}

async function startAbRun() {
  if (!abDisabled.value.length) {
    ElMessage.warning("先选一条要禁用的规则（不选等于原样跑一轮）");
    return;
  }
  const ds = currentDs();
  const ids = promptRules.value
    .filter((r: any) => abDisabled.value.includes(r.code))
    .map((r: any) => r.title);
  try {
    await ElMessageBox.confirm(
      `将按「禁用：${ids.join("、")}」跑 ${abLimit.value} 道题（每轮约 15~20 分钟）。` +
        `跑完到「问数评测 → 报告 → 对比运行」选择本轮与基线看差异。`,
      "启动对比评测",
      { type: "info", confirmButtonText: "启动", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  abStarting.value = true;
  try {
    const filter: any = { limit: abLimit.value, rules_disable: [...abDisabled.value] };
    if (ds) filter.datasource = ds;
    const r = await startEvalRun({ filter, mode: "full" });
    const runId = r.data?.data?.run_id;
    ElMessage.success(`已启动：${runId || "-"}（可在问数评测页看进度）`);
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "启动失败");
  } finally {
    abStarting.value = false;
  }
}

// 沉淀为指标（FDE 复用闭环）：把已验证问答落为确定性指标
const traceVisible = ref(false);
const traceMsg = ref<any>(null);

async function copyTrace() {
  const m = traceMsg.value || {};
  const lines = [
    `path: ${m.path || "-"}`,
    `took_ms: ${m.took_ms ?? 0}, rows: ${m.result_rows ?? 0}`,
    `applied: ${JSON.stringify(m.applied || [])}`,
    `policy_ids: ${JSON.stringify(m.policy_ids || [])}`,
    `retrieved: ${JSON.stringify(m.grounding?.retrieved || [])}`,
    `ontology: ${JSON.stringify(m.grounding?.ontology_used || [])}`,
    `sql: ${m.sql || ""}`,
    m.is_error ? `error: ${m.error || m.summary || ""}` : "",
  ].filter(Boolean);
  try {
    await navigator.clipboard.writeText(lines.join("\n"));
    ElMessage.success(t("ai_logs.traceCopied"));
  } catch {
    ElMessage.error(t("ai_logs.traceCopyFail"));
  }
}

function openTrace(m: any) {
  traceMsg.value = m;
  traceVisible.value = true;
}

const pmVisible = ref(false);
const pmName = ref("");
const pmKey = ref("");
const pmMsg = ref<any>(null);
const pmLoading = ref(false);

// 使用统计
const statsVisible = ref(false);
const stats = ref<any>({ total: 0, fast: 0, slow: 0, errors: 0, ok: 0 });
const fastPct = computed(() =>
  stats.value.total ? Math.round((stats.value.fast / stats.value.total) * 100) : 0
);
async function openStats() {
  statsVisible.value = true;
  try {
    const r = await getQueryStats();
    stats.value = r.data?.data || stats.value;
  } catch {
    /* 忽略 */
  }
}

function openPromote(m: any) {
  pmMsg.value = m;
  pmName.value = m?.question ? String(m.question).slice(0, 30) : "";
  pmKey.value = "";
  pmVisible.value = true;
}

async function submitPromote() {
  if (!pmName.value.trim() || !pmKey.value.trim()) {
    ElMessage.warning(t("ai_logs.promoteNameKeyRequired"));
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(pmKey.value.trim())) {
    ElMessage.warning(t("ai_logs.metricCodeInvalid"));
    return;
  }
  pmLoading.value = true;
  try {
    await promoteQueryMetric({
      message_id: pmMsg.value.id,
      name: pmName.value.trim(),
      key: pmKey.value.trim(),
    });
    ElMessage.success(t("ai_logs.promoted"));
    pmVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.promoteFailed"));
  } finally {
    pmLoading.value = false;
  }
}

/** 「存为报表」时提示模板里检测到的参数（与后端 extract_params 同一规则）。 */
const srParams = computed<string[]>(() => {
  const sql = srMsg.value?.sql || "";
  return [...new Set([...sql.matchAll(/\{(\w+)\}/g)].map((m) => m[1]))];
});

async function feedback(m: any, kind: string) {
  try {
    await queryFeedback({ message_id: m.id, feedback: kind });
    ElMessage.success(t("ai_logs.feedbackRecorded"));
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.feedbackFailed"));
  }
}

// 「没用」→ 让用户填正确 SQL（人工反馈是最宝贵的样本，且不会像评测题那样泄漏）
const fbVisible = ref(false);
const fbLoading = ref(false);
const fbSql = ref("");
const fbMsg = ref<any>(null);

// 澄清反问（系统不确定时先问，不猜）
const clarifyVisible = ref(false);
const reportSuggestVisible = ref(false);
const reportSuggestList = ref<any[]>([]);

async function pickReport(r: any) {
  if (r.params) {
    ElMessage.info(t("ai_logs.reportHasParams"));
    return;
  }
  try {
    const res: any = await runQueryReport(r.id, {});
    const d = res.data?.data;
    reportSuggestVisible.value = false;
    messages.value = [
      ...messages.value,
      {
        question: `${t("ai_logs.reportTag")} ${r.name}`,
        path: "report",
        columns: d?.columns || [],
        rows: d?.rows || [],
        summary:
          d?.summary || (d?.ok === false ? d?.msg : t("ai_logs.executedReport", { name: r.name })),
        sql: d?.sql || "",
        is_error: d?.ok === false,
      },
    ];
    await loadSessions();
  } catch (e: any) {
    ElMessage.error(e?.message || t("ai_logs.reportRunFailed"));
  }
}
const clarifyPick = ref("");
const clarify = ref<any>(null);

// 存为报表模板
const srVisible = ref(false);
const srLoading = ref(false);
const srName = ref("");
const srMsg = ref<any>(null);

function openCorrect(m: any) {
  fbMsg.value = m;
  fbSql.value = "";
  fbVisible.value = true;
}

async function submitFeedback(withSql: boolean) {
  if (!fbMsg.value) return;
  fbLoading.value = true;
  try {
    const r = await queryFeedback({
      message_id: fbMsg.value.id,
      feedback: "down",
      ...(withSql && fbSql.value.trim() ? { correct_sql: fbSql.value.trim() } : {}),
    });
    const d = r.data?.data || {};
    if (d.sunk) ElMessage.success(t("ai_logs.feedbackSunk"));
    else if (d.reason) ElMessage.warning(d.reason);
    else ElMessage.success(t("ai_logs.feedbackRecorded"));
    fbVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || t("ai_logs.feedbackFailed"));
  } finally {
    fbLoading.value = false;
  }
}

/** 清除当前对象上下文（用户主动摘掉），并同步清掉地址栏参数。 */
function clearObjectContext() {
  objectCode.value = "";
  objectKey.value = "";
  const q = { ...(route.query || {}) } as Record<string, any>;
  delete q.object_code;
  delete q.object_key;
  router.replace({ path: route.path, query: q });
}

onMounted(async () => {
  // 从本体/实例页跳转而来时带上「当前对象」（对齐 Palantir Fixed Object Set）
  const q = (route.query || {}) as Record<string, any>;
  if (q.object_code) objectCode.value = String(q.object_code);
  if (q.object_key) objectKey.value = String(q.object_key);
  // 本体页「去问数验证」会带 ?datasource=ds:4：不接这个参数，页面会停在默认的
  // system 库上，燃料库的问题全部变成 relation "DTXY_PMXX" does not exist。
  if (q.datasource) datasource.value = String(q.datasource);
  await loadSessions();
  await loadExamples();
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
    // 数据源有两套标识：内部 `ds:4`（schema/消息里用的）与 `code`（下拉的 value，如
    // ezdcs_pg）。本体页传的是 ds:{id}，这里统一归一化成下拉认识的值；
    // 找不到（已删/无权限）才回落 system。
    const dsValue = (d: any) => d.code || `ds:${d.id}`;
    const want = datasource.value;
    const hit =
      datasources.value.find((d: any) => dsValue(d) === want) ||
      (/^ds:\d+$/.test(want) ? datasources.value.find((d: any) => `ds:${d.id}` === want) : null);
    datasource.value = hit ? dsValue(hit) : "system";
  } catch {
    datasources.value = [];
  }
});

// 其余参数只在「专家」档显示；label 用配置键本身，避免逐项翻译失真。

const EXTRA_LABEL: Record<string, string> = {
  nl2sql_max_tokens: "生成最大 token",
  nl2sql_call_timeout: "生成超时（秒）",
  nl2sql_thinking_mode: "思考模式（off/low/on）",
  llm_keepalive_enabled: "模型保活",
  llm_keepalive_interval: "保活间隔（秒）",
  schema_top_k: "召回表数量",
  schema_semantic_weight: "语义权重",
  schema_keyword_weight: "关键词权重",
  entity_enabled: "实体识别",
  enum_hint_enabled: "枚举取值提示",
  full_entity_no_limit: "全实体不截断",
  entity_name_rule: "实体名规则",
  entity_map: "实体映射（JSON）",
  agno_semantic_enabled: "Agno 语义检索",
  query_cost_max_rows: "费用查询行上限",
  fewshot_auto_curate: "Few-shot 自动沉淀",
  decomposed_planning: "多步分解",
  kg_enabled: "知识图谱",
  recall_top_k: "召回条数",
  recall_min_score: "召回阈值",
  recall_w_vector: "向量权重",
  recall_w_keyword: "关键词权重",
  recall_w_ontology: "本体权重",
  recall_w_entity: "实体权重",
  object_query_max_objects: "对象查询对象数",
  object_query_call_timeout: "IR 生成超时（秒）",
  object_query_max_traverse_depth: "关系遍历深度",
  object_query_auto_index_after: "自动索引触发次数",
  multi_dialect_enabled: "多方言支持",
  query_rewrite_enabled: "查询改写",
  query_rewrite_call_timeout: "改写超时（秒）",
  schema_asset_meta_enabled: "资产描述进提示词",
  recall_expand_cap: "召回扩展上限",
  object_query_max_tokens: "对象查询 token",
  policy_engine: "权限引擎（legacy/shadow/enforce）",
  service_principal_user_id: "服务主体用户 id",
};

const EXTRA_HELP: Record<string, string> = {
  recall_top_k: "影响选表召回，改动前先跑评测对比",
  recall_min_score: "低于该分数的召回结果会被丢弃",
  schema_top_k: "拼进提示词的表数量，过大拖慢生成",
  object_query_enabled: "IR 两阶段规划，实测无收益时保持关闭",
  policy_engine: "enforce 需先配好策略，否则会大面积拒答",
  query_rewrite_enabled: "多一次模型调用，实测收益不稳定",
  service_principal_user_id: "空=不启用；填用户 id 后定时任务/嵌入聊天按该用户权限执行",
  nl2sql_thinking_mode: "off 更快，复杂问题可试 low",
};

const EXTRA_KEYS = [
  "nl2sql_max_tokens",
  "nl2sql_call_timeout",
  "nl2sql_thinking_mode",
  "llm_keepalive_enabled",
  "llm_keepalive_interval",
  "schema_top_k",
  "schema_semantic_weight",
  "schema_keyword_weight",
  "entity_enabled",
  "enum_hint_enabled",
  "full_entity_no_limit",
  "entity_name_rule",
  "entity_map",
  "agno_semantic_enabled",
  "query_cost_max_rows",
  "fewshot_auto_curate",
  "decomposed_planning",
  "kg_enabled",
  "recall_top_k",
  "recall_min_score",
  "recall_w_vector",
  "recall_w_keyword",
  "recall_w_ontology",
  "recall_w_entity",
  "object_query_max_objects",
  "object_query_call_timeout",
  "object_query_max_traverse_depth",
  "object_query_auto_index_after",
  "multi_dialect_enabled",
  "query_rewrite_enabled",
  "query_rewrite_call_timeout",
  "schema_asset_meta_enabled",
  "recall_expand_cap",
  "object_query_max_tokens",
  "policy_engine",
  "service_principal_user_id",
];

function guessType(key: string): "bool" | "int" | "text" {
  if (/(enabled|self_correct|planning|auto_curate|multi_dialect|no_limit)$/.test(key))
    return "bool";
  if (
    /(max|min|top_k|timeout|interval|weight|after|retry|rows|cap|tokens|depth|objects)$/.test(key)
  )
    return "int";
  return "text";
}

function guessGroup(key: string): string {
  if (key.startsWith("policy")) return t("ai_logs.settingGroupSecurity");
  if (
    /^(recall|schema_top_k|schema_semantic|schema_keyword|entity|enum_hint|kg_|agno_semantic)/.test(
      key
    )
  )
    return t("ai_logs.settingGroupRecall");
  if (
    /^(nl2sql|two_stage|decomposed|empty_self_correct|query_rewrite|fewshot|object_query|query_cost)/.test(
      key
    )
  )
    return t("ai_logs.settingGroupGenerate");
  if (/^llm_keepalive/.test(key)) return t("ai_logs.settingGroupRuntime");
  return t("ai_logs.settingGroupExecute");
}

const EXTRA_ENUMS: Record<string, string[]> = {
  policy_engine: ["legacy", "shadow", "enforce"],
  nl2sql_thinking_mode: ["off", "low", "on"],
};

const ALL_DEFS = [
  ...SETTING_DEFS.map((d: any) => ({
    ...d,
    expert: false,
    rawKey: d.key,
    group: guessGroup(d.key),
  })),
  ...EXTRA_KEYS.map((k) => ({
    key: k,
    label: EXTRA_LABEL[k] || k,
    rawKey: k,
    type: guessType(k),
    tip: EXTRA_HELP[k] || "",
    options: EXTRA_ENUMS[k],
    expert: true,
    group: guessGroup(k),
  })),
];

const setMode = ref<"simple" | "expert">("simple");
const setSearch = ref("");
const setDefaults = ref<Record<string, string>>({});
const showChanged = ref(false);
const COLLAPSE_KEY = "ai_query_setting_collapsed";

function loadCollapsed(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COLLAPSE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function persistCollapsed(v: Record<string, boolean>) {
  try {
    localStorage.setItem(COLLAPSE_KEY, JSON.stringify(v));
  } catch {
    /* 隐私模式下 localStorage 不可用，忽略 */
  }
}

const collapsedGroups = ref<Record<string, boolean>>(loadCollapsed());
const changedKeys = computed(() => {
  const set = new Set<string>();
  ALL_DEFS.forEach((d: any) => {
    if ((setForm.value[d.key] ?? "") !== (setLoaded.value[d.key] ?? "")) set.add(d.key);
  });
  return set;
});

function isChanged(key: string) {
  return changedKeys.value.has(key);
}

function toggleGroup(name: string) {
  collapsedGroups.value = { ...collapsedGroups.value, [name]: !collapsedGroups.value[name] };
  persistCollapsed(collapsedGroups.value);
}

const visibleDefs = computed(() => {
  const kw = setSearch.value.trim().toLowerCase();
  return ALL_DEFS.filter((d: any) => {
    if (setMode.value !== "expert" && d.expert) return false;
    if (showChanged.value && !changedKeys.value.has(d.key)) return false;
    if (!kw) return true;
    return [d.label, d.key, d.tip].some((x) =>
      String(x || "")
        .toLowerCase()
        .includes(kw)
    );
  });
});
const visibleGroups = computed(() => {
  const out: { name: string; items: any[] }[] = [];
  for (const d of visibleDefs.value) {
    let g = out.find((x) => x.name === d.group);
    if (!g) {
      g = { name: d.group, items: [] };
      out.push(g);
    }
    g.items.push(d);
  }
  return out;
});
</script>

<!-- 布局统一（非 scoped + 唯一类名，避免 data-v 在 keep-alive/HMR 下失效）：
     1) 页面撑满：app-container → el-row → el-col → el-card → body 全链 height/min-height；
     2) 左栏固定 240px（与工作台/个人工作空间/本体一致），不用栅格百分比。 -->
<style lang="scss">
.app-container.ai-query-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.ai-query-page > .el-row {
  flex: 1 1 auto;
  flex-wrap: nowrap;
  gap: 12px;
  margin: 0 !important;
  min-height: 0;
}

.ai-query-page > .el-row > .el-col {
  height: 100%;
  min-height: 0;
  padding: 0 !important;
}

.ai-query-page > .el-row > .el-col:first-child {
  flex: 0 0 240px;
  max-width: 240px;
}

.ai-query-page > .el-row > .el-col:last-child {
  flex: 1 1 auto;
  max-width: 100%;
}

.ai-query-page > .el-row > .el-col > .el-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.ai-query-page > .el-row > .el-col > .el-card > .el-card__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
</style>

<style lang="scss" scoped>
.q-trace__actions {
  margin-top: 12px;
  text-align: right;
}

.q-trace__sql {
  margin-top: 12px;
}

.q-set__mode {
  margin-bottom: 10px;
}

.q-set__search {
  margin-bottom: 8px;
}

.q-set__count {
  display: inline-block;
  min-width: 18px;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
  font-weight: 400;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  border-radius: 9px;
}

.q-set__key {
  margin-left: 6px;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.q-set__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.q-set__changed-only {
  margin-right: 2px;
}

/* 生成规则：工具条 + 核心约束说明 */
.q-rules__bar {
  display: flex;
  align-items: center;
  margin: 4px 0 8px;
}
.q-rules__hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.q-rules__core {
  margin-top: 12px;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-lighter);
}
.q-rules__core-title {
  font-weight: 600;
  margin-bottom: 4px;
}
.q-rules__core-item {
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.6;
}
.q-ent {
  max-height: 56vh;
  overflow-y: auto;
}
.q-ent__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.q-lang {
  max-height: 62vh;
  overflow-y: auto;
  padding-right: 4px;
}
.q-lang__switches {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 4px 0 10px;
}
.q-lang__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.q-lang__item {
  min-width: 0;
}
.q-lang__label {
  margin-bottom: 2px;
}
.q-lang__probe {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.q-rules__ab {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
}
.q-rules__preview {
  max-height: 420px;
  overflow: auto;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-lighter);
  color: var(--el-text-color-regular);
  font-family: var(--el-font-family);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.q-probe__bar {
  display: flex;
  gap: 8px;
}
.q-probe__result {
  margin-top: 12px;
}
.q-probe__count {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.q-probe__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.q-set__caret {
  display: inline-block;
  width: 14px;
  color: var(--el-text-color-secondary);
}

.q-set__reset {
  margin-left: 8px;
  font-size: 12px;
}

.q-set__reset-all {
  float: left;
}

.q-set__dot {
  width: 6px;
  height: 6px;
  margin-left: 8px;
  background: var(--el-color-warning);
  border-radius: 50%;
  flex: 0 0 auto;
}

.q-set__row.is-changed {
  background: var(--el-color-warning-light-9);
  border-radius: 6px;
}

.q-set__group-title {
  cursor: pointer;
  user-select: none;
  margin: 14px 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
}

.q-side__head,
.q-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.q-head__ops {
  display: flex;
  gap: 8px;
  align-items: center;
}

.q-tip {
  margin-bottom: 12px;
}

.q-sess {
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
}

.q-sess:hover {
  background: var(--el-fill-color-light);
}

.q-sess.is-active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}

.q-sess__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.q-sess__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-ask {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.q-examples {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 8px;
}

.q-examples__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-examples__tag {
  cursor: pointer;
}

.q-msg {
  padding: 12px 0;
}

.q-msg__q {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-bottom: 10px;
  .el-tag {
    flex: 0 0 auto;
  }
  span {
    max-width: 78%;
    padding: 8px 12px;
    font-weight: 500;
    line-height: 1.6;
    color: var(--el-text-color-primary);
    overflow-wrap: anywhere;
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-7);
    border-radius: var(--el-border-radius-base) var(--el-border-radius-base) 0
      var(--el-border-radius-base);
  }
}

.q-msg__sum {
  margin-bottom: 6px;
  color: var(--el-text-color-regular);
}

.q-msg__reason {
  margin-bottom: 6px;
}
.q-msg__reason :deep(.el-collapse) {
  border: none;
}
.q-msg__reason :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: transparent;
}
.q-msg__tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}

.q-report-suggest {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}
.q-report-item {
  padding: 10px 14px;
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  transition: all 0.2s;
  &:hover {
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary-light-5);
  }
}
.q-report-item__head {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: 600;
}
.q-report-item__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.q-report-item__desc {
  margin-top: 4px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.q-report-item__q {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-msg__meta {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-msg__sql {
  margin-bottom: 8px;
}

.q-msg__table {
  margin-bottom: 6px;
}

.q-msg__err {
  margin-bottom: 6px;
}

.q-sql {
  padding: 8px;
  margin: 0;
  overflow-x: auto;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
  white-space: pre-wrap;
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
}

.q-fb-tip {
  margin-bottom: 12px;
}

.q-msg__ont {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
}

.q-msg__ont-label {
  color: var(--el-text-color-secondary);
}

.q-msg__ont-more {
  color: var(--el-text-color-secondary);
}

.q-sr__p {
  margin-right: 4px;
}

.q-sr__hint {
  width: 100%;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-stats__hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-fb-q {
  margin-bottom: 8px;
  font-weight: 600;
}

.q-msg__src {
  color: var(--el-text-color-secondary);
}

.q-msg__ir-note {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.q-set__row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.q-set__row:last-child {
  border-bottom: none;
}

.q-set__main {
  flex: 1;
  min-width: 0;
}

.q-set__label {
  font-weight: 500;
}

.q-set__tip {
  line-height: 1.45;
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
</style>

<style lang="scss">
/* 问数页：聊天式布局（消息区自适应高度 + 输入区吸底）
   非 scoped + 唯一类名，避免 keep-alive / HMR 下 data-v 失效 */
.ai-query-page > .el-row > .el-col:last-child > .el-card > .el-card__body {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* flex 子项默认 min-width:auto，长表名/长标签会把右栏顶出屏幕（1440 下实测破版） */
.ai-query-page > .el-row > .el-col:last-child {
  min-width: 0;
}

.ai-query-page .q-chat,
.ai-query-page .q-chat__scroll {
  min-width: 0;
}

.ai-query-page .q-chat__scroll {
  padding: 4px 4px 12px;
}

.ai-query-page .q-chat__composer {
  flex: 0 0 auto;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ai-query-page .q-composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 8px 8px 8px 12px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  transition: border-color 0.2s;
}

.ai-query-page .q-composer:focus-within {
  border-color: var(--el-color-primary);
}

.ai-query-page .q-composer .el-textarea__inner {
  padding: 6px 0;
  box-shadow: none;
  border: none;
  background: transparent;
  resize: none;
}

.ai-query-page .q-xcomposer .el-button,
.ai-query-page .q-composer .el-button {
  margin-bottom: 2px;
}

.ai-query-page .q-examples {
  margin-top: 8px;
  gap: 6px;
}

.ai-query-page .q-examples__tag {
  cursor: pointer;
  max-width: 100%;
}

/* 会话列表：去掉卡片感，做成列表项；删除按钮悬停才出现，平时不抢眼 */
.ai-query-page .q-sess__meta .el-button {
  opacity: 0;
  transition: opacity 0.15s;
}

.ai-query-page .q-sess:hover .q-sess__meta .el-button {
  opacity: 1;
}

.ai-query-page .q-sess {
  padding: 7px 10px;
}

.ai-query-page .q-sess__title {
  font-size: 13px;
  line-height: 1.5;
}

.ai-query-page .q-sess__meta {
  margin-top: 2px;
  line-height: 1.4;
}

/* 会话列表：去掉卡片感，做成列表项 */
.ai-query-page .q-sess {
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--el-border-radius-base);
}

.ai-query-page .q-sess:hover {
  border-color: var(--el-border-color-lighter);
}

.ai-query-page .q-sess.is-active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
  box-shadow: inset 3px 0 0 var(--el-color-primary);
}

/* 对话字号按项目规范统一：正文 14（--el-font-size-base）、次要 12
   之前消息正文是 16px，比系统其它页面大一档，看着"虚"。 */
.ai-query-page .chat-msg__body,
.ai-query-page .chat-msg__bubble {
  font-size: var(--el-font-size-base);
  line-height: 1.7;
}

.ai-query-page .chat-msg__name {
  font-size: var(--el-font-size-base);
}

/* 本体依据块 */
.ai-query-page .q-onto {
  margin-top: 10px;
  padding: 8px 10px;
  font-size: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: var(--el-border-radius-base);
}

.ai-query-page .q-onto__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  cursor: pointer;
  user-select: none;
}

.ai-query-page .q-onto__toggle {
  margin-left: auto;
  color: var(--el-color-primary);
}

.ai-query-page .q-onto__body {
  padding: 4px 0 6px;
}

.ai-query-page .q-onto__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ai-query-page .q-onto__row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
}

.ai-query-page .q-onto__label {
  color: var(--el-text-color-secondary);
}

.ai-query-page .q-onto__hint {
  color: var(--el-text-color-secondary);
}

.ai-query-page .q-onto__more {
  color: var(--el-text-color-secondary);
}

/* 过程时间线：一眼看到 思考 → 工具 → SQL → 结果 */
.ai-query-page .q-steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.ai-query-page .q-step__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}

.ai-query-page .q-step__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.ai-query-page .q-step__badge {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.ai-query-page .q-step__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-success);
  flex: 0 0 auto;
}

.ai-query-page .q-step__dot.is-running {
  background: var(--el-color-primary);
  animation: q-pulse 1s ease-in-out infinite;
}

.ai-query-page .q-step__dot.is-done {
  background: var(--el-color-success);
}

@keyframes q-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.35;
    transform: scale(0.75);
  }
}

.ai-query-page .q-step__body {
  margin: 0 0 6px 16px;
}

.ai-query-page .q-pre {
  max-height: 220px;
  overflow: auto;
  padding: 10px 12px;
  font-family: var(--el-font-family-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
}

.ai-query-page .q-code {
  color: var(--el-text-color-primary);
  background: var(--el-fill-color);
}

.ai-query-page .q-tools {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ai-query-page .q-tool {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.ai-query-page .q-tool__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--el-color-success);
}

.ai-query-page .q-tool__dot.is-running {
  background: var(--el-color-warning);
  animation: q-pulse 1s ease-in-out infinite;
}

.ai-query-page .q-tool__dot.is-error {
  background: var(--el-color-danger);
}

.ai-query-page .q-tool__status {
  color: var(--el-text-color-secondary);
}

/* 消息 */
.ai-query-page .q-msg {
  padding: 10px 0 14px;
}

.ai-query-page .q-msg + .q-msg {
  border-top: 1px dashed var(--el-border-color-lighter);
}

.ai-query-page .q-msg__q {
  margin-bottom: 12px;
}

.ai-query-page .q-msg__q span {
  max-width: 72%;
  padding: 9px 14px;
  border-radius: var(--el-border-radius-base);
  border-bottom-right-radius: 2px;
}

.ai-query-page .q-msg__meta {
  gap: 8px;
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
}

.ai-query-page .q-msg__sum {
  margin-bottom: 8px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
}

.ai-query-page .q-msg__table {
  margin-top: 4px;
  margin-bottom: 4px;
}

.ai-query-page .q-msg__sql {
  margin-top: 4px;
}

/* 反馈按钮：与正文拉开、按钮之间留空隙（原来 6px 贴在一起） */
.ai-query-page .q-msg__fb {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  align-items: center;
  margin-top: 12px;
}

/* 顶部提示条压扁 */
.ai-query-page .q-tip {
  margin-bottom: 8px;
}

.ai-query-page .q-tip .el-alert__title {
  font-size: 12px;
}
</style>
