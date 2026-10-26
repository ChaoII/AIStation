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

          <div class="q-ask">
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
              @click="question = e"
            >
              {{ e }}
            </el-tag>
          </div>

          <el-divider />

          <el-empty
            v-if="!messages.length"
            :description="t('ai_logs.noQueries')"
            :image-size="70"
          />

          <div v-for="(m, i) in messages" :key="m.id || i" class="q-msg">
            <div class="q-msg__q">
              <el-tag size="small" effect="dark">{{ t("ai_logs.ask") }}</el-tag>
              <span>{{ m.question }}</span>
            </div>
            <el-alert
              v-if="m.is_error"
              type="error"
              :closable="false"
              :title="m.summary || t('ai_logs.queryFailed')"
              class="q-msg__err"
            />
            <template v-else>
              <div v-if="m.reasoning" class="q-msg__reason">
                <el-collapse v-model="reasonOpen">
                  <el-collapse-item :title="t('ai_logs.thinkingProcess')" name="r">
                    <pre class="q-sql">{{ m.reasoning }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
              <div v-if="m.tools?.length" class="q-msg__tools">
                <el-tag
                  v-for="(t, ti) in m.tools"
                  :key="ti"
                  size="small"
                  effect="plain"
                  :type="
                    t.status === 'error' ? 'danger' : t.status === 'running' ? 'warning' : 'success'
                  "
                >
                  {{ t.name }}{{ t.status === "running" ? "…" : "" }}
                </el-tag>
              </div>
              <div v-if="m.summary" class="q-msg__sum">{{ m.summary }}</div>
              <div class="q-msg__meta">
                <el-tag size="small" effect="plain">
                  {{ pathLabel(m) }}
                </el-tag>
                <el-tag v-if="m.metric?.name" size="small" type="success" effect="plain">
                  {{ t("ai_logs.metric", { name: m.metric.name }) }}
                </el-tag>
                <span v-if="m.evidence?.source" class="q-msg__src">
                  {{ m.evidence.source }}
                </span>
                <span v-if="m.result_rows">
                  {{ t("ai_logs.totalRows", { count: m.result_rows }) }}
                </span>
                <span v-if="m.took_ms">{{ m.took_ms }} ms</span>
                <span v-if="m.cached">{{ t("ai_logs.cacheHit") }}</span>
              </div>
              <el-collapse v-if="m.sql" class="q-msg__sql">
                <el-collapse-item :title="t('ai_logs.viewSql')" name="sql">
                  <pre class="q-sql">{{ m.sql }}</pre>
                </el-collapse-item>
              </el-collapse>
              <el-collapse v-if="irOf(m)" class="q-msg__sql">
                <el-collapse-item :title="t('ai_logs.viewObjectQuery')" name="ir">
                  <pre class="q-sql">{{ JSON.stringify(irOf(m), null, 2) }}</pre>
                  <div class="q-msg__ir-note">
                    {{ t("ai_logs.objectQueryNote") }}
                    <span v-if="m.object_query?.note">· {{ m.object_query.note }}</span>
                  </div>
                </el-collapse-item>
              </el-collapse>
              <el-table
                v-if="m.columns && m.columns.length"
                :data="rowsOf(m)"
                size="small"
                border
                max-height="340"
                class="q-msg__table"
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
              <div v-if="m.id" class="q-msg__fb">
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
              <div v-if="recalledOf(m).length || ontologyOf(m).length" class="q-msg__ont">
                <template v-if="ontologyOf(m).length">
                  <span class="q-msg__ont-label">{{ t("ai_logs.ontologyObjects") }}</span>
                  <el-tag
                    v-for="t in ontologyOf(m)"
                    :key="`o-${t}`"
                    size="small"
                    type="success"
                    effect="plain"
                  >
                    {{ t }}
                  </el-tag>
                </template>
                <template v-if="recalledOf(m).length">
                  <span class="q-msg__ont-label">{{ t("ai_logs.recalledTables") }}</span>
                  <el-tag
                    v-for="t in recalledOf(m).slice(0, 8)"
                    :key="`t-${t}`"
                    size="small"
                    effect="plain"
                  >
                    {{ t }}
                  </el-tag>
                  <span v-if="recalledOf(m).length > 8" class="q-msg__ont-more">
                    {{ t("ai_logs.andMoreTables", { count: recalledOf(m).length }) }}
                  </span>
                </template>
              </div>
            </template>
          </div>
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
      width="600px"
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
        <div v-for="d in SETTING_DEFS" :key="d.key" class="q-set__row">
          <div class="q-set__main">
            <div class="q-set__label">{{ d.label }}</div>
            <div class="q-set__tip">{{ d.tip }}</div>
          </div>
          <el-switch
            v-if="d.type === 'bool'"
            v-model="setForm[d.key]"
            active-value="true"
            inactive-value="false"
          />
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
            :min="1"
            :max="9"
            size="small"
            style="width: 120px"
            @update:model-value="(v: number | undefined) => (setForm[d.key] = String(v ?? 1))"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="setVisible = false">{{ t("ai_logs.cancel") }}</el-button>
        <el-button type="primary" :loading="setSaving" @click="saveSettings">
          {{ t("ai_logs.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteQuerySession,
  getQueryDatasources,
  getQueryFewshots,
  getQueryMessages,
  getQuerySessions,
  getQuerySettings,
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
const reasonOpen = ref<any[]>([]);
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
    tip: t("ai_logs.settingSelfConsistencyTip"),
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
  SETTING_DEFS.forEach((d) => {
    base[d.key] = d.type === "bool" ? "false" : d.type === "text" ? "" : "1";
  });
  setForm.value = { ...base };
  setLoaded.value = { ...base };
  try {
    const r = await getQuerySettings();
    const d = r.data?.data || {};
    const merged: Record<string, string> = { ...base };
    SETTING_DEFS.forEach((x) => {
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

async function saveSettings() {
  setSaving.value = true;
  try {
    const changed = SETTING_DEFS.filter(
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
  await loadSessions();
  await loadExamples();
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
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
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
</style>
