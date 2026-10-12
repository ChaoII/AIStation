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
                <el-button link type="primary" size="small" @click="goOntology">
                  查看本体
                </el-button>
              </div>
            </div>
          </template>

          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="q-tip"
            title="问数会复用本体的语义与权限：业务对象名、字段中文名、表间关系都来自本体；行级/列级策略会在生成 SQL 时下推到子查询。"
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
              <div v-if="m.summary" class="q-msg__sum">{{ m.summary }}</div>
              <div class="q-msg__meta">
                <el-tag size="small" effect="plain">
                  {{ m.path === "slow" ? "NL2SQL" : "指标" }}
                </el-tag>
                <span v-if="m.result_rows">共 {{ m.result_rows }} 行</span>
                <span v-if="m.took_ms">{{ m.took_ms }} ms</span>
                <span v-if="m.cached">命中缓存</span>
              </div>
              <el-collapse v-if="m.sql" class="q-msg__sql">
                <el-collapse-item title="查看生成的 SQL" name="sql">
                  <pre class="q-sql">{{ m.sql }}</pre>
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
            模板里检测到 {{ srParams.length }} 个参数；保存后可在「自定义报表」页调整中文名/类型/必填
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteQuerySession,
  getQueryDatasources,
  getQueryMessages,
  getQuerySessions,
  queryAsk,
  queryFeedback,
  saveQueryReport,
} from "@/api/module_ai/query";

defineOptions({ name: "AiQuery" });

const router = useRouter();

const sessions = ref<any[]>([]);
const messages = ref<any[]>([]);
const datasources = ref<any[]>([]);
const sessionId = ref<number | null>(null);
const datasource = ref("system");
const question = ref("");
const asking = ref(false);

const examples = ["销售订单总共有多少笔", "各部门的销售额是多少", "统计摄像机的状态分布"];

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
  try {
    const r = await queryAsk({
      question: q,
      session_id: sessionId.value,
      datasource: datasource.value || null,
    });
    const d = r.data?.data || {};
    if (d.session_id && !sessionId.value) sessionId.value = d.session_id;
    // 澄清反问：系统不确定（如"按原煤仓分组"而表里有名称/编号两列）→ 先问用户，不猜
    if (d.path === "clarify" && d.clarify) {
      clarify.value = { ...d.clarify, _q: q };
      clarifyPick.value = "";
      clarifyVisible.value = true;
      return;
    }
    // 局部刷新：只把这一条问答追加进列表，不重拉整个会话
    messages.value = [...messages.value, { ...d, question: q }];
    question.value = "";
    if (d.is_error) ElMessage.error(d.summary || d.answer || "查询失败");
    else ElMessage.success("查询完成");
    await loadSessions();
  } catch (e: any) {
    ElMessage.error(e?.msg || "提问失败");
  } finally {
    asking.value = false;
  }
}

/** 用户回答澄清：把选择拼回问句再问一次（复用同一链路，形成多轮）。 */
async function answerClarify() {
  const c = clarify.value;
  if (!c || !clarifyPick.value) return;
  const label = (c.options || []).find((o: any) => o.value === clarifyPick.value)?.label
    || clarifyPick.value;
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
    ElMessage.error(e?.msg || "保存失败");
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
    ElMessage.error(e?.msg || "反馈失败");
  }
}

// 「没用」→ 让用户填正确 SQL（人工反馈是最宝贵的样本，且不会像评测题那样泄漏）
const fbVisible = ref(false);
const fbLoading = ref(false);
const fbSql = ref("");
const fbMsg = ref<any>(null);

// 澄清反问（系统不确定时先问，不猜）
const clarifyVisible = ref(false);
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
    ElMessage.error(e?.msg || "反馈失败");
  } finally {
    fbLoading.value = false;
  }
}

onMounted(async () => {
  await loadSessions();
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
  padding: 10px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.q-msg__q {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin-bottom: 8px;
  font-weight: 500;
}

.q-msg__sum {
  margin-bottom: 6px;
  color: var(--el-text-color-regular);
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

.q-fb-q {
  margin-bottom: 8px;
  font-weight: 600;
}
</style>
