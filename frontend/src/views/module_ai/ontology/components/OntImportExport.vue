<!--
  对象类型 → 导入 / 导出 子页
  说明：导出/导入作用于「当前整个本体（domain）」，不限于本对象类型；在详情页提供入口仅为集中管理。
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">导入 / 导出</span>
    </div>
    <el-alert
      type="warning"
      :closable="false"
      class="ont-obj__note"
      :title="`导出/导入作用于当前本体「${currentDomainName}」（整个 domain），不限于本对象类型。`"
    />

    <!-- 导出 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">导出本体</div>
      <el-button size="small" type="primary" :loading="transferLoading" @click="doExport">
        导出 JSON
      </el-button>
      <span class="ont-hint">下载当前本体的对象/属性/关系/动作定义，可用于迁移或备份</span>
    </div>

    <!-- 导入 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">导入本体</div>
      <el-upload :show-file-list="false" :auto-upload="false" accept=".json" @change="onImportFile">
        <el-button size="small" :icon="Upload">选择 JSON 文件</el-button>
      </el-upload>
      <el-input
        v-model="importText"
        type="textarea"
        :rows="6"
        class="ont-imp__area"
        placeholder="粘贴本体 JSON，或点上方「选择 JSON 文件」读取。格式与导出一致。"
      />
      <div class="ont-imp__actions">
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :loading="transferLoading"
          @click="doImport('stage')"
        >
          暂存导入
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          type="danger"
          :loading="transferLoading"
          @click="doImport('apply')"
        >
          直接导入
        </el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-obj__note"
        title="暂存导入 = 改动先进待保存列表；直接导入 = 立即写入并可能覆盖同名定义（会二次确认）。"
      />
    </div>

    <!-- 数据源批量导入 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">从数据源批量导入</div>
      <div class="ont-imp__row">
        <el-select
          v-model="impDs"
          size="small"
          filterable
          placeholder="选择数据源"
          style="width: 260px"
          @change="onImportDsChange"
        >
          <el-option
            v-for="d in datasources"
            :key="d.id"
            :label="`${d.name}（${d.table_count} 表）`"
            :value="d.id"
          />
        </el-select>
        <el-tag v-if="impDs" size="small" effect="plain">{{ impTableCount }} 张表</el-tag>
        <el-checkbox v-model="impIncludeTechnical" size="small">含技术字段</el-checkbox>
        <el-button
          size="small"
          type="primary"
          :disabled="!impDs"
          :loading="impLoading"
          @click="doBatchImport"
        >
          开始导入
        </el-button>
      </div>
      <span class="ont-hint">从数据源的表结构按列映射生成对象类型与属性</span>
    </div>

    <!-- 行业模板 -->
    <div class="ont-imp__block">
      <div class="ont-sec__title">应用行业模板</div>
      <div v-for="t in industryTemplates" :key="t.id" class="ont-imp__template">
        <div class="ont-imp__template-info">
          <div class="ont-imp__template-name">{{ t.name }}</div>
          <div class="ont-hint">{{ t.description }}</div>
        </div>
        <el-button
          size="small"
          type="primary"
          :loading="tplLoading === t.id"
          @click="applyTemplate(t)"
        >
          应用
        </el-button>
      </div>
      <el-empty v-if="!industryTemplates.length" :image-size="40" description="暂无行业模板" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import { Upload } from "@element-plus/icons-vue";
import { exportOntology, importOntology } from "@/api/module_ai/ontology";
import {
  getQueryDatasources,
  getQueryDatasourceSchema,
  importDsAsOntologyBatch,
  getIndustryTemplates,
  applyIndustryTemplate,
} from "@/api/module_ai/query";
import { useOntologyData } from "../composables/useOntologyData";

defineProps<{ code: string }>();

const { currentDomain, currentDomainName, reloadAll, refreshWip } = useOntologyData();

const transferLoading = ref(false);
const importText = ref("");

const datasources = ref<any[]>([]);
const impDs = ref<number | null>(null);
const impTableCount = ref(0);
const impIncludeTechnical = ref(false);
const impLoading = ref(false);

const industryTemplates = ref<any[]>([]);
const tplLoading = ref("");

async function doExport() {
  transferLoading.value = true;
  try {
    const r = await exportOntology(currentDomain.value || undefined);
    const data = r.data?.data || {};
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ontology-${data.domain_code || "all"}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
    const c = data.counts || {};
    ElMessage.success(
      `已导出 ${c.objects || 0} 对象 / ${c.properties || 0} 属性 / ${c.links || 0} 关系 / ${c.actions || 0} 动作`
    );
  } catch (e: any) {
    ElMessage.error(e?.msg || "导出失败");
  } finally {
    transferLoading.value = false;
  }
}

async function doImport(mode: "stage" | "apply") {
  let payload: any;
  try {
    payload = JSON.parse(importText.value || "{}");
  } catch {
    return ElMessage.error("JSON 解析失败，请检查粘贴内容");
  }
  if (!payload.objects) return ElMessage.error("不是合法的本体定义（缺少 objects）");
  if (mode === "apply") {
    try {
      await ElMessageBox.confirm(
        "将把导入内容**直接写入**本体（不经过待保存列表），可能覆盖现有同名定义。确认直接导入？",
        "直接导入",
        { type: "warning", confirmButtonText: "直接导入", cancelButtonText: "取消" }
      );
    } catch {
      return;
    }
  }
  transferLoading.value = true;
  try {
    const r = await importOntology(payload, mode);
    ElMessage.success(r.data?.msg || "已导入");
    await reloadAll();
    await refreshWip();
    if (mode === "stage") importText.value = "";
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
  } finally {
    transferLoading.value = false;
  }
}

async function onImportFile(uploadFile: UploadFile) {
  const f = uploadFile.raw;
  if (!f) return;
  importText.value = await f.text();
}

async function loadPanel() {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
    if (!impDs.value && datasources.value.length) {
      const best = [...datasources.value].sort(
        (a: any, b: any) => (b.table_count || 0) - (a.table_count || 0)
      )[0];
      impDs.value = best.id;
      await onImportDsChange(impDs.value);
    }
  } catch {
    datasources.value = [];
  }
  try {
    const t = await getIndustryTemplates();
    industryTemplates.value = t.data?.data || [];
  } catch {
    industryTemplates.value = [];
  }
}

async function onImportDsChange(id: number | null) {
  if (!id) {
    impTableCount.value = 0;
    return;
  }
  try {
    const r = await getQueryDatasourceSchema(id);
    impTableCount.value = (r.data?.data || []).length;
  } catch {
    impTableCount.value = 0;
  }
}

async function doBatchImport() {
  if (!impDs.value) return;
  impLoading.value = true;
  try {
    const r = await importDsAsOntologyBatch(impDs.value, null, impIncludeTechnical.value);
    const d = r.data?.data || {};
    ElMessage.success(r.data?.msg || `已导入 ${d.imported ?? 0} 个对象`);
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "导入失败");
  } finally {
    impLoading.value = false;
  }
}

async function applyTemplate(t: any) {
  tplLoading.value = t.id;
  try {
    const r = await applyIndustryTemplate(t.id);
    ElMessage.success(r.data?.msg || `已应用模板「${t.name}」`);
    await reloadAll();
  } catch (e: any) {
    ElMessage.error(e?.msg || "应用失败");
  } finally {
    tplLoading.value = "";
  }
}

onMounted(loadPanel);
</script>

<style scoped lang="scss">
.ont-obj__note {
  margin-bottom: 8px;
}
.ont-imp__block {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.ont-imp__area {
  margin-top: 8px;
}
.ont-imp__actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.ont-imp__row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-top: 8px;
}
.ont-imp__template {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ont-imp__template-name {
  font-size: var(--el-font-size-base);
  font-weight: 500;
}
.ont-hint {
  font-size: var(--el-font-size-extra-small);
  color: var(--el-text-color-secondary);
}
</style>
