<template>
  <div class="app-container ai-query-reports">
    <el-card shadow="never">
      <template #header>
        <div class="r-head">
          <span>自定义报表</span>
          <div class="r-head__ops">
            <el-select
              v-model="datasource"
              size="small"
              clearable
              placeholder="全部数据源"
              style="width: 180px"
              @change="load"
            >
              <el-option label="系统库（本体支撑表）" value="system" />
              <el-option
                v-for="d in datasources"
                :key="d.code || d.id"
                :label="d.name"
                :value="d.code || `ds:${d.id}`"
              />
            </el-select>
            <el-checkbox v-model="verifiedOnly" size="small" @change="load">
              只看已确认
            </el-checkbox>
            <el-button size="small" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="报表由「智能问数」结果页的「存为报表」沉淀而来。确认后才是正式报表；困难题因此可一次沉淀、长期复用。"
        class="r-tip"
      />

      <el-table v-loading="loading" :data="rows" size="small" border>
        <el-table-column type="index" label="#" width="52" />
        <el-table-column prop="name" label="报表名" min-width="170" show-overflow-tooltip />
        <el-table-column prop="key" label="标识" width="120" show-overflow-tooltip />
        <el-table-column prop="datasource" label="数据源" width="90" />
        <el-table-column prop="question" label="来源问题" min-width="190" show-overflow-tooltip />
        <el-table-column label="参数" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="(row.params || []).length" size="small" effect="plain">
              {{ row.params.length }} 个
            </el-tag>
            <span v-else class="r-dim">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.verified" size="small" type="success">已确认</el-tag>
            <el-tag v-else size="small" type="warning">草稿</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openRun(row)">运行</el-button>
            <el-button link size="small" @click="openParams(row)">参数</el-button>
            <el-button
              v-if="!row.verified"
              link
              type="success"
              size="small"
              @click="verify(row)"
            >
              确认
            </el-button>
            <el-button link type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="r-total">共 {{ rows.length }} 个报表</div>
    </el-card>

    <el-dialog v-model="runVisible" :title="`运行报表：${cur?.name || ''}`" width="720px" append-to-body>
      <el-alert
        v-if="runError"
        type="error"
        :closable="false"
        show-icon
        :title="runError"
        class="r-tip"
      />
      <el-form v-if="(cur?.params || []).length" label-width="110px">
        <el-form-item
          v-for="p in cur?.params || []"
          :key="p.key"
          :label="p.label || p.key"
          :required="p.required !== false"
        >
          <el-input-number
            v-if="p.type === 'number'"
            v-model="paramValues[p.key]"
            :controls="false"
            class="r-param"
            :placeholder="String(p.default ?? '')"
          />
          <el-date-picker
            v-else-if="p.type === 'date'"
            v-model="paramValues[p.key]"
            type="date"
            value-format="YYYY-MM-DD"
            class="r-param"
            :placeholder="String(p.default ?? '')"
          />
          <el-input
            v-else
            v-model="paramValues[p.key]"
            class="r-param"
            :placeholder="String(p.default ?? '')"
          />
        </el-form-item>
      </el-form>
      <el-alert v-else type="info" :closable="false" show-icon title="该报表无需参数" class="r-tip" />
      <el-button type="primary" size="small" :loading="running" @click="doRun">执行</el-button>
      <el-table
        v-if="result.columns.length"
        :data="resultRows"
        size="small"
        border
        max-height="360"
        class="r-result"
      >
        <el-table-column
          v-for="c in result.columns"
          :key="c"
          :prop="c"
          :label="c"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <template #footer>
        <el-button @click="runVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="paramVisible"
      :title="`参数定义：${cur?.name || ''}`"
      width="720px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="参数来自 SQL 模板里的 {占位符}（保存时自动抽取）。这里可改中文名/类型/必填/默认值，运行时会按此校验。"
        class="r-tip"
      />
      <el-table :data="paramDefs" size="small" border>
        <el-table-column label="占位符 key" width="150">
          <template #default="{ row }">
            <el-input v-model="row.key" size="small" placeholder="如 start_date" />
          </template>
        </el-table-column>
        <el-table-column label="中文名" width="140">
          <template #default="{ row }">
            <el-input v-model="row.label" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-select v-model="row.type" size="small">
              <el-option label="文本" value="text" />
              <el-option label="数字" value="number" />
              <el-option label="日期" value="date" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="必填" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.required" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="默认值" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.default" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="paramDefs.splice($index, 1)">
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button link type="primary" size="small" class="r-addparam" @click="addParam">
        + 添加参数
      </el-button>
      <template #footer>
        <el-button @click="paramVisible = false">取消</el-button>
        <el-button type="primary" :loading="paramSaving" @click="saveParams">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteQueryReports,
  getQueryDatasources,
  getQueryReports,
  runQueryReport,
  saveQueryReport,
  verifyQueryReport,
} from "@/api/module_ai/query";

defineOptions({ name: "AiQueryReports" });

const rows = ref<any[]>([]);
const datasources = ref<any[]>([]);
const loading = ref(false);
const datasource = ref("");
const verifiedOnly = ref(false);

const runVisible = ref(false);
const running = ref(false);
const cur = ref<any>(null);
const paramValues = ref<Record<string, any>>({});
const result = ref<{ columns: string[]; rows: any[][] }>({ columns: [], rows: [] });

const resultRows = computed(() =>
  (result.value.rows || []).map((r) => {
    const o: Record<string, any> = {};
    (result.value.columns || []).forEach((c, i) => {
      o[c] = r[i];
    });
    return o;
  })
);

async function load() {
  loading.value = true;
  try {
    const params: any = {};
    if (datasource.value) params.datasource = datasource.value;
    if (verifiedOnly.value) params.verified_only = true;
    const r = await getQueryReports(params);
    rows.value = r.data?.data || [];
  } catch {
    rows.value = [];
  } finally {
    loading.value = false;
  }
}

function openRun(row: any) {
  cur.value = row;
  runError.value = "";
  paramValues.value = {};
  (row.params || []).forEach((p: any) => {
    const hasDefault = p.default !== "" && p.default != null;
    paramValues.value[p.key] = hasDefault ? p.default : p.type === "number" ? undefined : "";
  });
  result.value = { columns: [], rows: [] };
  runVisible.value = true;
}

async function doRun() {
  if (!cur.value) return;
  // 前端先校验必填（后端同样校验：双保险，且提示更贴近操作）
  const missing = (cur.value.params || []).find((p: any) => {
    if (p.required === false) return false;
    const v = paramValues.value[p.key];
    return v === undefined || v === null || String(v).trim() === "";
  });
  if (missing) {
    runError.value = `请填写必填参数「${missing.label || missing.key}」`;
    return;
  }
  runError.value = "";
  running.value = true;
  try {
    const r = await runQueryReport(cur.value.id, paramValues.value);
    const d = r.data?.data || {};
    result.value = { columns: d.columns || [], rows: d.rows || [] };
    ElMessage.success(`执行完成，共 ${result.value.rows.length} 行`);
  } catch (e: any) {
    runError.value = e?.msg || "执行失败";
    ElMessage.error(runError.value);
  } finally {
    running.value = false;
  }
}

// —— 参数定义（占位符 key / 中文名 / 类型 / 必填 / 默认值）——
const paramVisible = ref(false);
const paramSaving = ref(false);
const paramDefs = ref<any[]>([]);
const runError = ref("");

function openParams(row: any) {
  cur.value = row;
  paramDefs.value = (row.params || []).map((p: any) => ({
    key: p.key || "",
    label: p.label || "",
    type: p.type || "text",
    required: p.required !== false,
    default: p.default ?? "",
  }));
  paramVisible.value = true;
}

function addParam() {
  paramDefs.value = [
    ...paramDefs.value,
    { key: "", label: "", type: "text", required: true, default: "" },
  ];
}

async function saveParams() {
  if (!cur.value) return;
  if (paramDefs.value.some((p) => !String(p.key || "").trim())) {
    ElMessage.warning("参数占位符 key 不能为空");
    return;
  }
  paramSaving.value = true;
  try {
    await saveQueryReport({
      key: cur.value.key,
      name: cur.value.name,
      description: cur.value.description,
      datasource: cur.value.datasource,
      question: cur.value.question,
      sql_template: cur.value.sql_template,
      columns: cur.value.columns,
      chart: cur.value.chart,
      params: paramDefs.value,
      verified: cur.value.verified,
    });
    ElMessage.success("参数已保存");
    paramVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    paramSaving.value = false;
  }
}

async function verify(row: any) {
  await ElMessageBox.confirm(
    `确认报表「${row.name}」后，同类问题会被推荐使用它（正式生效）。`,
    "确认报表",
    { type: "warning", confirmButtonText: "确认", cancelButtonText: "取消" }
  );
  try {
    await verifyQueryReport(row.id);
    ElMessage.success("已确认");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "确认失败");
  }
}

async function remove(row: any) {
  await ElMessageBox.confirm(`将删除报表「${row.name}」，且不可恢复。`, "删除报表", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  try {
    await deleteQueryReports([row.id]);
    ElMessage.success("已删除");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

onMounted(async () => {
  await load();
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
});
</script>

<style scoped>
.r-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.r-head__ops {
  display: flex;
  align-items: center;
  gap: 12px;
}
.r-tip {
  margin-bottom: 12px;
}
.r-total {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.r-result {
  margin-top: 12px;
}
.r-dim {
  color: var(--el-text-color-placeholder);
}
.r-param {
  width: 100%;
}
.r-addparam {
  margin-top: 8px;
}
</style>
