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
        <el-table-column prop="name" label="报表名" min-width="180" show-overflow-tooltip />
        <el-table-column prop="key" label="标识" width="150" show-overflow-tooltip />
        <el-table-column prop="datasource" label="数据源" width="100" />
        <el-table-column prop="question" label="来源问题" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.verified" size="small" type="success">已确认</el-tag>
            <el-tag v-else size="small" type="warning">草稿</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openRun(row)">运行</el-button>
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
      <el-form v-if="(cur?.params || []).length" label-width="100px">
        <el-form-item v-for="p in cur?.params || []" :key="p.key" :label="p.label || p.key">
          <el-input v-model="paramValues[p.key]" :placeholder="String(p.default ?? '')" />
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
  paramValues.value = {};
  (row.params || []).forEach((p: any) => {
    paramValues.value[p.key] = p.default ?? "";
  });
  result.value = { columns: [], rows: [] };
  runVisible.value = true;
}

async function doRun() {
  if (!cur.value) return;
  running.value = true;
  try {
    const r = await runQueryReport(cur.value.id, paramValues.value);
    const d = r.data?.data || {};
    result.value = { columns: d.columns || [], rows: d.rows || [] };
    ElMessage.success(`执行完成，共 ${result.value.rows.length} 行`);
  } catch (e: any) {
    ElMessage.error(e?.msg || "执行失败");
  } finally {
    running.value = false;
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
</style>
