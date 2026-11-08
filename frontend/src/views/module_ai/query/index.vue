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
        <el-empty v-if="!visibleGroups.length" :image-size="56" description="没有匹配的配置项" />
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
  deleteQuerySession,
  getQueryDatasources,
  getQueryFewshots,
  getQueryMessages,
  getQuerySessions,
  getQuerySettings,
  getQuerySettingsDefaults,
  queryFeedback,
  promoteQueryMetric,
  getQueryStats,
  runQueryReport,
  saveQueryReport,
  saveQuerySetting,
  streamQuery,
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
