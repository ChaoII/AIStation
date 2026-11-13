<!-- 治理包：资产别名/描述、本体对象别名、业务术语 的导出与导入（先预演再应用） -->
<template>
  <div class="qgb">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="导出是可读 JSON；导入先「预演」再「应用」。应用只更新包里有值的字段，不会清空其它内容。"
      class="qgb__tip"
    />
    <div class="qgb__bar">
      <span class="qgb__label">数据源</span>
      <el-select v-model="ds" size="small" style="width: 220px">
        <el-option v-for="d in dsList" :key="d.code" :label="d.name" :value="d.code" />
      </el-select>
      <el-button size="small" type="primary" :loading="exporting" @click="exportBundle">
        导出治理包
      </el-button>
      <span class="qgb__hint">含：资产别名/描述、本体对象别名、业务术语</span>
    </div>

    <el-input
      v-model="text"
      type="textarea"
      :rows="10"
      placeholder="把导出的 JSON 粘贴到这里（或选择文件）"
      class="qgb__text"
    />
    <div class="qgb__bar">
      <input type="file" accept=".json" class="qgb__file" @change="onFile" />
      <el-button size="small" :loading="loading" @click="preview">预演</el-button>
      <el-button size="small" type="primary" :loading="loading" @click="apply">应用</el-button>
    </div>

    <div v-if="result" class="qgb__result">
      <el-descriptions :column="3" size="small" border>
        <el-descriptions-item label="资产别名/描述">
          新增 {{ result.assets?.add || 0 }} / 更新 {{ result.assets?.update || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="本体别名">
          新增 {{ result.ontology_aliases?.add || 0 }} / 更新
          {{ result.ontology_aliases?.update || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="术语">
          新增 {{ result.terms?.add || 0 }} / 更新 {{ result.terms?.update || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="未知表/对象">
          {{
            (result.unknown_tables?.length || 0) +
            (result.ontology_aliases?.unknown_codes?.length || 0)
          }}
        </el-descriptions-item>
        <el-descriptions-item label="重复行（同名不同大小写）">
          {{ result.assets?.duplicates || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag v-if="result.applied" type="success" size="small">已应用</el-tag>
          <el-tag v-else type="info" size="small">仅预演</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <div v-if="result.applied" class="qgb__hint">已应用，下一句问数立即生效。</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { getGovernanceExport, getQueryDatasources, importGovernance } from "@/api/module_ai/query";

defineOptions({ name: "GovernanceBundlePanel" });

const dsList = ref<any[]>([]);
const ds = ref("ds:6");
const text = ref("");
const loading = ref(false);
const exporting = ref(false);
const result = ref<any>(null);

async function loadDatasources() {
  try {
    const r = await getQueryDatasources();
    // 接口里 code 是 ezdcs_local 这类短名，问数侧统一用 ds:<id>
    const list = (r.data?.data || []).map((d: any) => ({
      code: `ds:${d.id}`,
      name: `${d.name}（${d.type}）`,
    }));
    dsList.value = list;
    if (!dsList.value.some((d: any) => d.code === ds.value) && dsList.value.length) {
      ds.value = dsList.value[0].code;
    }
  } catch {
    // 保留默认 ds:6
  }
}

async function exportBundle() {
  exporting.value = true;
  try {
    const r = await getGovernanceExport({ datasource: ds.value });
    const bundle = r.data?.data || {};
    const content = JSON.stringify(bundle, null, 2);
    text.value = content;
    const blob = new Blob([content], { type: "application/json;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `governance-${ds.value.replace(":", "_")}-${new Date()
      .toISOString()
      .slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    ElMessage.success("已导出");
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "导出失败");
  } finally {
    exporting.value = false;
  }
}

function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const f = input.files?.[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    text.value = String(reader.result || "");
  };
  reader.readAsText(f, "utf-8");
}

function parse(): any | null {
  try {
    return JSON.parse(text.value || "{}");
  } catch {
    ElMessage.error("JSON 格式不对，请检查后重试");
    return null;
  }
}

async function preview() {
  const bundle = parse();
  if (!bundle) return;
  loading.value = true;
  try {
    const r = await importGovernance({ data: bundle, apply: false, datasource: ds.value });
    result.value = r.data?.data || {};
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "预演失败");
  } finally {
    loading.value = false;
  }
}

async function apply() {
  const bundle = parse();
  if (!bundle) return;
  try {
    await ElMessageBox.confirm(
      "将按上面的包更新别名/描述/术语（只更新有值的字段，不删除其它内容）。确认应用？",
      "应用治理包",
      { type: "warning", confirmButtonText: "应用", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  loading.value = true;
  try {
    const r = await importGovernance({ data: bundle, apply: true, datasource: ds.value });
    result.value = r.data?.data || {};
    ElMessage.success("已应用");
  } catch (e: any) {
    ElMessage.error(e?.data?.msg || e?.msg || "应用失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadDatasources);
</script>

<style lang="scss" scoped>
.qgb {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.qgb__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.qgb__label {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.qgb__hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.qgb__file {
  font-size: 12px;
}
.qgb__result {
  margin-top: 4px;
}
</style>
