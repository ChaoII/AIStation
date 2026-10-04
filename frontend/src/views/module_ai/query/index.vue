<!-- 智能问数：会话式问答 + 快/慢路径结果 + 指标/术语/数据源运营 -->
<template>
  <div class="app-container ai-query-page">
    <div class="query-layout">
      <!-- 左侧：会话 / 数据源 -->
      <div class="query-side">
        <div class="query-side__hd">
          <el-button type="primary" size="small" :icon="Plus" @click="newSession">新会话</el-button>
          <el-button size="small" :icon="Setting" @click="openOps">指标运营</el-button>
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
              </div>

              <div v-if="m.summary" class="msg-a__summary">{{ m.summary }}</div>

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
    <el-drawer v-model="opsVisible" title="智能问数 · 指标运营" size="720px" append-to-body>
      <el-tabs v-model="opsTab">
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
      </el-tabs>
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
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Delete, Setting, Loading } from "@element-plus/icons-vue";
import ECharts from "@/components/ECharts/index.vue";
import {
  queryAsk,
  getQuerySessions,
  getQueryMessages,
  deleteQuerySession,
  getQueryMetrics,
  saveQueryMetric,
  deleteQueryMetrics,
  getQueryTerms,
  saveQueryTerm,
  deleteQueryTerms,
  getQueryDatasources,
  saveQueryDatasource,
  deleteQueryDatasources,
  testQueryDatasource,
  syncQueryDatasourceSchema,
  getQueryRoles,
  queryFeedback,
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
  // 立即展示提问气泡
  const pending = { id: `tmp-${Date.now()}`, question: q, _showSql: false };
  messages.value.push(pending);
  scrollBottom();
  try {
    const r = await queryAsk({ question: q, session_id: currentSession.value, datasource: ds });
    const data = r.data?.data || {};
    messages.value.pop();
    const msg = { ...data, _showSql: false };
    messages.value.push(msg);
    if (data.session_id) {
      currentSession.value = data.session_id;
      loadSessions();
    }
  } catch (e: any) {
    messages.value.pop();
    messages.value.push({
      id: `err-${Date.now()}`,
      question: q,
      is_error: true,
      summary: e?.msg || e?.message || "查询失败",
      path: "slow",
      _showSql: false,
    });
  } finally {
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
});
</script>

<style scoped>
.ai-query-page {
  height: 100%;
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
.msg-a__summary {
  margin-bottom: 8px;
  color: var(--el-text-color-primary);
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
</style>
