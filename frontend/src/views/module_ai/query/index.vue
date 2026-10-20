<template>
  <div class="app-container ai-query-page">
    <el-row :gutter="12">
      <!-- 左侧：会话列表 -->
      <el-col :xs="24" :sm="24" :md="7" :lg="6">
        <el-card shadow="never" class="q-side">
          <template #header>
            <div class="q-side__head">
              <span>会话</span>
              <el-button link type="primary" size="small" @click="newSession">新对话</el-button>
            </div>
          </template>
          <el-empty v-if="!sessions.length" description="还没有会话" :image-size="60" />
          <div
            v-for="s in sessions"
            :key="s.id"
            class="q-sess"
            :class="{ 'is-active': s.id === sessionId }"
            @click="openSession(s.id)"
          >
            <div class="q-sess__title">{{ s.title || "未命名" }}</div>
            <div class="q-sess__meta">
              <span>{{ s.created_time || "" }}</span>
              <el-button link type="danger" size="small" @click.stop="removeSession(s)">
                删除
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
              <span>智能问数</span>
              <div class="q-head__ops">
                <el-select
                  v-model="datasource"
                  size="small"
                  placeholder="数据源"
                  style="width: 190px"
                >
                  <el-option label="系统库（本体支撑表）" value="system" />
                  <el-option
                    v-for="d in datasources"
                    :key="d.code || d.id"
                    :label="d.name"
                    :value="d.code || `ds:${d.id}`"
                  />
                </el-select>
                <el-button link type="primary" size="small" @click="goOntology">查看本体</el-button>
                <el-button link type="primary" size="small" @click="openSettings">
                  问数设置
                </el-button>
                <el-button link type="primary" size="small" @click="openStats">使用统计</el-button>
                <el-dropdown @command="goSub">
                  <el-button link type="primary" size="small">
                    <el-icon style="margin-right: 4px"><Grid /></el-icon>
                    数据管理
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="/ai/integration">数据与集成</el-dropdown-item>
                      <el-dropdown-item command="/ai/eval">问数评测</el-dropdown-item>
                      <el-dropdown-item command="/ai/query/reports">报表模板</el-dropdown-item>
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
            :title="`当前对象上下文：${objectCode}${objectKey ? ' #' + objectKey : ''}（提问会自动带上它，无需重复说明）`"
            @close="clearObjectContext"
          />

          <el-alert
            v-if="!tipHidden"
            type="info"
            :closable="true"
            show-icon
            class="q-tip"
            title="问数会复用本体的语义与权限：业务对象名、字段中文名、表间关系都来自本体；行级/列级策略会在生成 SQL 时下推到子查询。"
            @close="hideTip"
          />

          <div class="q-ask">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="用业务语言提问，例如：各部门的销售额是多少"
              @keydown.enter.exact.prevent="ask"
            />
            <el-button type="primary" :loading="asking" @click="ask">提问</el-button>
          </div>

          <div class="q-examples">
            <span class="q-examples__label">示例：</span>
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

          <el-empty v-if="!messages.length" description="还没有提问记录" :image-size="70" />

          <div v-for="(m, i) in messages" :key="m.id || i" class="q-msg">
            <div class="q-msg__q">
              <el-tag size="small" effect="dark">问</el-tag>
              <span>{{ m.question }}</span>
            </div>
            <el-alert
              v-if="m.is_error"
              type="error"
              :closable="false"
              :title="m.summary || '查询失败'"
              class="q-msg__err"
            />
            <template v-else>
              <div v-if="m.reasoning" class="q-msg__reason">
                <el-collapse v-model="reasonOpen">
                  <el-collapse-item title="思考过程" name="r">
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
                  指标：{{ m.metric.name }}
                </el-tag>
                <span v-if="m.evidence?.source" class="q-msg__src">
                  {{ m.evidence.source }}
                </span>
                <span v-if="m.result_rows">共 {{ m.result_rows }} 行</span>
                <span v-if="m.took_ms">{{ m.took_ms }} ms</span>
                <span v-if="m.cached">命中缓存</span>
              </div>
              <el-collapse v-if="m.sql" class="q-msg__sql">
                <el-collapse-item title="查看生成的 SQL" name="sql">
                  <pre class="q-sql">{{ m.sql }}</pre>
                </el-collapse-item>
              </el-collapse>
              <el-collapse v-if="irOf(m)" class="q-msg__sql">
                <el-collapse-item title="查看对象查询（语义执行）" name="ir">
                  <pre class="q-sql">{{ JSON.stringify(irOf(m), null, 2) }}</pre>
                  <div class="q-msg__ir-note">
                    由本体实例层确定性执行（不生成 SQL）；对象/字段均来自授权且检索命中的范围。
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
                <el-button link size="small" @click="feedback(m, 'up')">有用</el-button>
                <el-button link size="small" @click="openCorrect(m)">没用</el-button>
                <el-button
                  v-if="m.sql && !m.is_error"
                  link
                  type="primary"
                  size="small"
                  @click="openSaveReport(m)"
                >
                  存为报表
                </el-button>
                <el-button
                  v-if="m.sql && !m.is_error"
                  link
                  type="primary"
                  size="small"
                  @click="openPromote(m)"
                >
                  沉淀为指标
                </el-button>
              </div>
              <div v-if="recalledOf(m).length || ontologyOf(m).length" class="q-msg__ont">
                <template v-if="ontologyOf(m).length">
                  <span class="q-msg__ont-label">本体对象：</span>
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
                  <span class="q-msg__ont-label">召回的表：</span>
                  <el-tag
                    v-for="t in recalledOf(m).slice(0, 8)"
                    :key="`t-${t}`"
                    size="small"
                    effect="plain"
                  >
                    {{ t }}
                  </el-tag>
                  <span v-if="recalledOf(m).length > 8" class="q-msg__ont-more">
                    等 {{ recalledOf(m).length }} 张
                  </span>
                </template>
              </div>
            </template>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="clarifyVisible" title="需要确认一下" width="520px" append-to-body>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="这个问题有歧义，选一个更准的口径（选完会按你的选择重新查询）。"
        class="q-fb-tip"
      />
      <div class="q-fb-q">{{ clarify?.question }}</div>
      <el-radio-group v-model="clarifyPick">
        <el-radio v-for="o in clarify?.options || []" :key="o.value" :label="o.value">
          {{ o.label }}
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="clarifyVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!clarifyPick" @click="answerClarify">
          按这个口径查
        </el-button>
      </template>
    </el-dialog>

    <!-- 报表建议：未命中时，推荐已沉淀的报表供用户选择执行 -->
    <el-dialog v-model="reportSuggestVisible" title="帮你找到相关报表" width="560px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="系统没有直接命中指标，但有已沉淀的报表可能正好覆盖你的问题，选一个即可直接出结果。"
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
              {{ r.params }} 参数
            </el-tag>
            <el-tag v-else size="small" type="success" effect="plain">直接出结果</el-tag>
          </div>
          <div v-if="r.description" class="q-report-item__desc">{{ r.description }}</div>
          <div v-if="r.question" class="q-report-item__q">对应问题：{{ r.question }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="reportSuggestVisible = false">算了，继续用问答</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="srVisible" title="存为报表" width="520px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="存下来后同类问题可长期复用（一次沉淀、长期复用）。确认后才进入正式报表列表。"
        class="q-fb-tip"
      />
      <el-form label-width="80px">
        <el-form-item label="报表名">
          <el-input v-model="srName" placeholder="例如：各煤种月度化验汇总" />
        </el-form-item>
        <el-form-item label="来源问题">
          <el-input :model-value="srMsg?.question || ''" readonly />
        </el-form-item>
        <el-form-item v-if="srParams.length" label="参数">
          <el-tag v-for="k in srParams" :key="k" size="small" effect="plain" class="q-sr__p">
            {{ k }}
          </el-tag>
          <div class="q-sr__hint">
            模板里检测到
            {{ srParams.length }} 个参数；保存后可在「报表模板」页调整中文名/类型/必填
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="srVisible = false">取消</el-button>
        <el-button type="primary" :loading="srLoading" @click="submitSaveReport">
          保存草稿
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="pmVisible" title="沉淀为指标" width="520px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="把这条已验证问答沉淀为「可复用指标」：同类问题下次直接走确定性快路径（秒级、口径统一），不再依赖模型生成。"
        class="q-fb-tip"
      />
      <el-form label-width="80px">
        <el-form-item label="指标显示名">
          <el-input v-model="pmName" placeholder="例如：各煤种月度化验汇总" />
        </el-form-item>
        <el-form-item label="指标编码">
          <el-input v-model="pmKey" placeholder="仅字母/数字/下划线，如 assay_by_coal_type" />
        </el-form-item>
        <el-form-item label="来源问题">
          <el-input :model-value="pmMsg?.question || ''" readonly />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pmVisible = false">取消</el-button>
        <el-button type="primary" :loading="pmLoading" @click="submitPromote">沉淀</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="statsVisible" title="问数使用统计" width="480px" append-to-body>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-statistic title="总问答" :value="stats.total" />
        </el-col>
        <el-col :span="12">
          <el-statistic title="快路径（确定性）" :value="stats.fast" />
        </el-col>
        <el-col :span="12" style="margin-top: 12px">
          <el-statistic title="慢路径（NL2SQL）" :value="stats.slow" />
        </el-col>
        <el-col :span="12" style="margin-top: 12px">
          <el-statistic title="失败" :value="stats.errors" />
        </el-col>
      </el-row>
      <div class="q-stats__hint">快路径占比 {{ fastPct }}%（越高说明语义层沉淀越充分）</div>
    </el-dialog>

    <el-dialog v-model="fbVisible" title="纠正这次查询" width="600px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="填上正确的 SQL 会存进示例库，同类问题以后能复用（不填也可以只标记「没用」）。"
        class="q-fb-tip"
      />
      <div class="q-fb-q">{{ fbMsg?.question }}</div>
      <el-input
        v-model="fbSql"
        type="textarea"
        :rows="6"
        placeholder='正确的 SQL，例如：SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY"'
      />
      <template #footer>
        <el-button @click="fbVisible = false">取消</el-button>
        <el-button @click="submitFeedback(false)">仅标记没用</el-button>
        <el-button type="primary" :loading="fbLoading" @click="submitFeedback(true)">
          提交纠正
        </el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="setVisible" title="问数设置" width="620px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="这些是问数的工程开关，保存后即时生效。标「实验」的默认关闭，需先做对比验证再开启。"
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
            placeholder="留空=默认"
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
        <el-button @click="setVisible = false">取消</el-button>
        <el-button type="primary" :loading="setSaving" @click="saveSettings">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
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
  "销售订单总共有多少笔",
  "各部门的销售额是多少",
  "统计摄像机的状态分布",
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
  if (m?.path === "fast") return "指标";
  if (m?.path === "object") return "对象查询";
  if (m?.path === "slow") return "NL2SQL";
  if (m?.path === "report") return "报表";
  if (m?.path === "report_suggest") return "报表建议";
  return m?.path || "查询";
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
    `将删除会话「${s.title || "未命名"}」及其全部问答记录，且不可恢复。`,
    "删除会话",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await deleteQuerySession(s.id);
  ElMessage.success("已删除");
  if (sessionId.value === s.id) newSession();
  await loadSessions();
}

async function ask() {
  const q = question.value.trim();
  if (!q) {
    ElMessage.warning("请先输入问题");
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
      const t = ev?.type;
      const d = ev?.data || {};
      if (t === "meta") {
        if (d.session_id && !sessionId.value) sessionId.value = d.session_id;
        cur.datasource = d.datasource || cur.datasource;
      } else if (t === "reasoning") {
        cur.reasoning += d.delta || "";
      } else if (t === "reasoning_done") {
        flush();
      } else if (t === "sql_delta") {
        cur.sql += d.delta || "";
      } else if (t === "sql_final") {
        cur.sql = d.sql || cur.sql;
        cur.path = "slow";
      } else if (t === "tool_start") {
        cur.tools.push({ name: d.name || "工具", status: "running" });
      } else if (t === "tool_result" || t === "tool_error") {
        const last = cur.tools[cur.tools.length - 1];
        if (last) last.status = t === "tool_result" ? "done" : "error";
      } else if (t === "ir") {
        cur.ir = d.ir || {};
        cur.path = "object";
        if (d.pending_clarify) cur.pending_clarify = d.pending_clarify;
        flush();
      } else if (t === "result") {
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
      } else if (t === "clarify") {
        cur.path = "clarify";
        cur.clarify = d.clarify || {};
      } else if (t === "report_suggest") {
        cur.path = "report_suggest";
        cur.reports = d.reports || [];
      } else if (t === "answer") {
        cur.summary = d.summary || "";
        flush();
      } else if (t === "error") {
        cur.is_error = true;
        cur.summary = d.message || d || "查询失败";
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
    if (cur.is_error) ElMessage.error(cur.summary || "查询失败");
    else ElMessage.success(hasResult ? "查询完成" : "已完成");
    await loadSessions();
  } catch (e: any) {
    cur.streaming = false;
    cur.is_error = true;
    cur.summary = e?.data?.msg || e?.msg || e?.message || "提问失败";
    flush();
    ElMessage.error(e?.data?.msg || e?.msg || "提问失败");
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
  question.value = `${c._q}\n【澄清】分组口径使用 ${label}`;
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
    ElMessage.warning("这次没有可保存的 SQL");
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
    ElMessage.success("已存为报表草稿，可在报表列表确认");
    srVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "保存失败");
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
    label: "对象查询（语义执行）",
    type: "bool",
    tip: "LLM 只输出结构化对象查询 IR，由本体实例层确定性执行（不生成 SQL）；失败自动回退 SQL 生成。默认关闭，需对比验证后再开启。",
  },
  {
    key: "query_cost_enabled",
    label: "查询代价护栏",
    type: "bool",
    tip: "执行前用 EXPLAIN 预估行数，超过上限则拒绝并重新生成。",
  },
  {
    key: "object_query_auto_index_enabled",
    label: "对象查询 · 自动建索引",
    type: "bool",
    tip: "对象查询命中次数达阈值后，后台按建议为高频对象自动补索引（复用本体索引模块）。默认关闭。",
  },
  {
    key: "object_query_model",
    label: "对象查询 · IR 模型",
    type: "text",
    tip: "生成对象查询 IR 用哪个模型：留空=与 NL2SQL 同源。可填更快的模型名（如 LLM-27B-FP8）或模型 id。实测同一提示词：284B≈29s、27B≈9s、deepseek-flash≈4.4s。",
  },
  {
    key: "empty_self_correct",
    label: "空结果自纠错",
    type: "bool",
    tip: "查询结果为空时，带提示重新生成一次。",
  },
  {
    key: "recall_enabled",
    label: "多路召回（RRF 融合）",
    type: "bool",
    tip: "向量 / 关键词 / 本体 / 实体四路召回融合后再选表。",
  },
  {
    key: "two_stage_planning",
    label: "两段式规划（真分解）",
    type: "bool",
    tip: "先出执行计划再写 SQL。实测负收益（留出法 −7.55 分），默认关闭。",
  },
  {
    key: "agno_tool_agent",
    label: "工具化 Agent",
    type: "bool",
    tip: "让模型自主调用检索工具；多轮往返较慢，默认关闭。",
  },
  {
    key: "self_consistency_n",
    label: "自一致性候选数",
    type: "int",
    tip: "大于 1 时多次采样投票，提升稳定性但更慢。",
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
    ElMessage.error(e?.data?.msg || e?.msg || "读取问数设置失败");
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
      ElMessage.info("没有需要保存的改动");
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
    ElMessage.success(`已保存 ${changed.length} 项设置`);
    setVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "保存设置失败");
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
    ElMessage.warning("请填写指标显示名与编码");
    return;
  }
  if (!/^[A-Za-z0-9_]+$/.test(pmKey.value.trim())) {
    ElMessage.warning("指标编码仅允许字母/数字/下划线");
    return;
  }
  pmLoading.value = true;
  try {
    await promoteQueryMetric({
      message_id: pmMsg.value.id,
      name: pmName.value.trim(),
      key: pmKey.value.trim(),
    });
    ElMessage.success("已沉淀为指标，同类问题将走确定性快路径");
    pmVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "沉淀失败");
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
    ElMessage.success("已记录反馈");
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "反馈失败");
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
    ElMessage.info("该报表带参数，请到「报表模板」页运行并填写参数");
    return;
  }
  try {
    const res: any = await runQueryReport(r.id, {});
    const d = res.data?.data;
    reportSuggestVisible.value = false;
    messages.value = [
      ...messages.value,
      {
        question: `[报表] ${r.name}`,
        path: "report",
        columns: d?.columns || [],
        rows: d?.rows || [],
        summary: d?.summary || (d?.ok === false ? d?.msg : `已执行报表「${r.name}」`),
        sql: d?.sql || "",
        is_error: d?.ok === false,
      },
    ];
    await loadSessions();
  } catch (e: any) {
    ElMessage.error(e?.message || "报表执行失败");
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
    if (d.sunk) ElMessage.success("已记录，并沉淀进示例库");
    else if (d.reason) ElMessage.warning(d.reason);
    else ElMessage.success("已记录反馈");
    fbVisible.value = false;
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "反馈失败");
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
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 10px;
  .el-tag {
    flex: 0 0 auto;
  }
  span {
    max-width: 78%;
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-7);
    border-radius: var(--el-border-radius-base) var(--el-border-radius-base) 0
      var(--el-border-radius-base);
    padding: 8px 12px;
    color: var(--el-text-color-primary);
    font-weight: 500;
    line-height: 1.6;
    overflow-wrap: anywhere;
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
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
  transition: all 0.2s;
  &:hover {
    border-color: var(--el-color-primary-light-5);
    background: var(--el-color-primary-light-9);
  }
}
.q-report-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.q-report-item__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.q-report-item__desc {
  margin-top: 4px;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
}
.q-report-item__q {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
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
