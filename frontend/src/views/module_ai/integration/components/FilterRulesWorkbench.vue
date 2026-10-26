<!-- 筛选规则工作台：配置 / 实时预览 / 前后对比 / 概览（首期无大模型）
     数据流：由父级传入选中数据源（列表行，含 id/name），此处用 getDatasourceDetail 拉全量详情（含 filter_rules），
     草稿规则在「规则配置」区编辑，编辑即防抖刷新预览；「保存规则/保存并应用」会覆盖已保存规则，须二次确认。 -->
<template>
  <div class="frwb">
    <!-- 顶栏：命中摘要 + 操作 -->
    <div class="frwb-bar">
      <el-descriptions :column="4" size="small" border class="frwb-summary">
        <el-descriptions-item :label="t('ai_workflow.ig_systemTable')">
          {{ preview?.summary?.system_tables ?? "-" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.ig_businessTable')">
          {{ preview?.summary?.business_tables ?? "-" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.ig_auditField')">
          {{ preview?.summary?.audit_fields ?? "-" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.ig_businessField')">
          {{ preview?.summary?.business_fields ?? "-" }}
        </el-descriptions-item>
      </el-descriptions>
      <div class="frwb-bar__ops">
        <el-button
          v-hasPerm="['module_ai:query:ask']"
          size="small"
          :loading="saving"
          :disabled="!dsDetail"
          @click="confirmSave(false)"
        >
          {{ t("ai_workflow.ig_saveRules") }}
        </el-button>
        <el-button
          v-hasPerm="['module_ai:query:ask']"
          size="small"
          type="primary"
          :loading="saving"
          :disabled="!dsDetail"
          @click="confirmSave(true)"
        >
          {{ t("ai_workflow.ig_saveApplyRules") }}
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="frwb-note"
      :title="t('ai_workflow.ig_frwbHint')"
    />

    <!-- 内部子 tab -->
    <el-tabs v-model="innerTab" class="frwb-tabs">
      <!-- 1) 规则配置 -->
      <el-tab-pane :label="t('ai_workflow.ig_tabRuleConfig')" name="config">
        <div v-loading="loading" class="frwb-pane">
          <ElForm :model="rules" label-width="110px" size="small" class="frwb-form">
            <ElFormItem :label="t('ai_workflow.ig_enableRule')">
              <el-switch v-model="rules.enabled" @change="scheduleRefresh" />
              <span class="frwb-hint">{{ t("ai_workflow.ig_enableRuleHint") }}</span>
            </ElFormItem>
            <el-divider content-position="left" class="frwb-divider">
              {{ t("ai_workflow.ig_sysTableDetect") }}
            </el-divider>
            <ElFormItem :label="t('ai_workflow.ig_sysTablePrefix')">
              <el-select
                v-model="rules.system_table.prefixes"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                :placeholder="t('ai_workflow.ig_enterAddPrefix')"
                style="width: 100%"
                @change="scheduleRefresh"
              >
                <el-option
                  v-for="p in rules.system_table.prefixes"
                  :key="p"
                  :label="p"
                  :value="p"
                />
              </el-select>
            </ElFormItem>
            <ElFormItem :label="t('ai_workflow.ig_sysTableKeyword')">
              <el-select
                v-model="rules.system_table.keywords"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                :placeholder="t('ai_workflow.ig_enterAddKeyword')"
                style="width: 100%"
                @change="scheduleRefresh"
              >
                <el-option
                  v-for="k in rules.system_table.keywords"
                  :key="k"
                  :label="k"
                  :value="k"
                />
              </el-select>
            </ElFormItem>
            <ElFormItem :label="t('ai_workflow.ig_exactTable')">
              <el-select
                v-model="rules.system_table.exact"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                :placeholder="t('ai_workflow.ig_enterAddExact')"
                style="width: 100%"
                @change="scheduleRefresh"
              >
                <el-option v-for="e in rules.system_table.exact" :key="e" :label="e" :value="e" />
              </el-select>
            </ElFormItem>
            <ElFormItem :label="t('ai_workflow.ig_tableRegex')">
              <el-input
                v-model="rules.system_table.regex"
                :placeholder="t('ai_workflow.ig_tableRegexPlaceholder')"
                @change="scheduleRefresh"
              />
            </ElFormItem>
            <el-divider content-position="left" class="frwb-divider">
              {{ t("ai_workflow.ig_auditFieldDetect") }}
            </el-divider>
            <ElFormItem :label="t('ai_workflow.ig_auditField')">
              <el-select
                v-model="rules.audit_fields"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                :placeholder="t('ai_workflow.ig_enterAddAudit')"
                style="width: 100%"
                @change="scheduleRefresh"
              >
                <el-option v-for="a in rules.audit_fields" :key="a" :label="a" :value="a" />
              </el-select>
            </ElFormItem>
          </ElForm>
          <div class="frwb-foot">
            <el-tag size="small" type="info" effect="plain">
              {{ t("ai_workflow.ig_draftStatus", { status: enabledText }) }}
            </el-tag>
          </div>
        </div>
      </el-tab-pane>

      <!-- 2) 实时预览 -->
      <el-tab-pane :label="t('ai_workflow.ig_tabPreview')" name="preview">
        <div v-loading="loading" class="frwb-pane frwb-preview">
          <el-alert
            type="success"
            :closable="false"
            class="frwb-note"
            :title="t('ai_workflow.ig_frwbPreviewHint')"
          />
          <el-card shadow="never" class="frwb-card">
            <template #header>
              <span class="frwb-card__title">
                {{ t("ai_workflow.ig_tableList", { count: preview?.tables?.length ?? 0 }) }}
              </span>
            </template>
            <el-table :data="preview?.tables || []" size="small" border height="300" stripe>
              <template #empty>
                <el-empty :description="t('ai_workflow.ig_noTableData')" :image-size="50" />
              </template>
              <el-table-column
                :label="t('ai_workflow.ig_tableName')"
                min-width="200"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  <span class="frwb-mono">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('ai_workflow.ig_sysBiz')" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.is_system ? 'info' : 'success'" effect="plain">
                    {{
                      row.is_system
                        ? t("ai_workflow.ig_systemTagShort")
                        : t("ai_workflow.ig_businessTagShort")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('ai_workflow.ig_hitRule')"
                min-width="220"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ row.reason || "—" }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          <el-card shadow="never" class="frwb-card">
            <template #header>
              <span class="frwb-card__title">
                {{ t("ai_workflow.ig_fieldList", { count: preview?.fields?.length ?? 0 }) }}
              </span>
            </template>
            <el-table :data="preview?.fields || []" size="small" border height="300" stripe>
              <template #empty>
                <el-empty :description="t('ai_workflow.ig_noFieldData')" :image-size="50" />
              </template>
              <el-table-column
                :label="t('ai_workflow.ig_fieldName')"
                min-width="200"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  <span class="frwb-mono">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="t('ai_workflow.ig_auditBiz')" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.is_audit ? 'info' : 'success'" effect="plain">
                    {{
                      row.is_audit
                        ? t("ai_workflow.ig_auditTagShort")
                        : t("ai_workflow.ig_businessTagShort")
                    }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('ai_workflow.ig_hitRule')"
                min-width="220"
                show-overflow-tooltip
              >
                <template #default="{ row }">
                  {{ row.reason || "—" }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- 3) 前后对比 -->
      <el-tab-pane :label="t('ai_workflow.ig_tabCompare')" name="compare">
        <div v-loading="compareLoading" class="frwb-pane">
          <div class="frwb-bar frwb-bar--left">
            <el-button
              size="small"
              :icon="Refresh"
              :loading="compareLoading"
              @click="loadSavedPreview"
            >
              {{ t("ai_workflow.ig_refreshCompare") }}
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              {{ t("ai_workflow.ig_compareHint") }}
            </el-tag>
          </div>

          <!-- 基础计数对比 -->
          <el-descriptions :column="4" size="small" border class="frwb-summary frwb-summary--cmp">
            <el-descriptions-item :label="t('ai_workflow.ig_systemTable')">
              {{
                t("ai_workflow.ig_savedDraftCount", {
                  saved: baseCounts.saved.sys,
                  draft: baseCounts.draft.sys,
                })
              }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('ai_workflow.ig_businessTable')">
              {{
                t("ai_workflow.ig_savedDraftCount", {
                  saved: baseCounts.saved.biz,
                  draft: baseCounts.draft.biz,
                })
              }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('ai_workflow.ig_auditField')">
              {{
                t("ai_workflow.ig_savedDraftCount", {
                  saved: baseCounts.saved.audit,
                  draft: baseCounts.draft.audit,
                })
              }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('ai_workflow.ig_businessField')">
              {{
                t("ai_workflow.ig_savedDraftCount", {
                  saved: baseCounts.saved.bizf,
                  draft: baseCounts.draft.bizf,
                })
              }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="!compareLoaded && !compareLoading"
            type="info"
            :closable="false"
            class="frwb-note"
            :title="t('ai_workflow.ig_compareEmpty')"
          />
          <el-alert
            v-else-if="!compareItems.length"
            type="success"
            :closable="false"
            class="frwb-note"
            :title="t('ai_workflow.ig_compareSame')"
          />
          <el-table v-else :data="compareItems" size="small" border height="320" stripe>
            <template #empty>
              <el-empty :description="t('ai_workflow.ig_noDiff')" :image-size="50" />
            </template>
            <el-table-column :label="t('ai_workflow.ig_type')" width="80" align="center">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.kind === t('ai_workflow.ig_kgTypeTable') ? 'warning' : 'primary'"
                  effect="plain"
                >
                  {{ row.kind }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.ig_name')"
              min-width="220"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span class="frwb-mono">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('ai_workflow.ig_hitChange')" width="160" align="center">
              <template #default="{ row }">
                <span class="frwb-change">{{ row.from }}</span>
                <el-icon class="frwb-arrow"><Right /></el-icon>
                <span class="frwb-change frwb-change--to">{{ row.to }}</span>
              </template>
            </el-table-column>
            <el-table-column
              :label="t('ai_workflow.ig_hitRuleCompare')"
              min-width="300"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                {{ row.reason || "—" }}
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 4) 概览 -->
      <el-tab-pane :label="t('ai_workflow.ig_tabOverview')" name="overview">
        <div v-loading="loading" class="frwb-pane">
          <el-row :gutter="12">
            <el-col :xs="24" :sm="12">
              <el-card shadow="never" class="frwb-card">
                <template #header>
                  <span class="frwb-card__title">{{ t("ai_workflow.ig_sysVsBiz") }}</span>
                </template>
                <VChart
                  v-if="tablePieOption"
                  :option="tablePieOption"
                  style="height: 260px"
                  autoresize
                />
                <el-empty v-else :description="t('ai_workflow.ig_noData')" :image-size="60" />
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-card shadow="never" class="frwb-card">
                <template #header>
                  <span class="frwb-card__title">{{ t("ai_workflow.ig_auditVsBiz") }}</span>
                </template>
                <VChart
                  v-if="fieldPieOption"
                  :option="fieldPieOption"
                  style="height: 260px"
                  autoresize
                />
                <el-empty v-else :description="t('ai_workflow.ig_noData')" :image-size="60" />
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- 5) 大模型辅助：生成候选 / 自然语言配置 / 逐表逐字段建议 -->
      <el-tab-pane :label="t('ai_workflow.ig_tabLlm')" name="llm">
        <div v-loading="llmLoading" class="frwb-pane frwb-llm">
          <el-alert
            type="info"
            :closable="false"
            class="frwb-note"
            :title="t('ai_workflow.ig_llmHint')"
          />

          <!-- 5.1) 生成候选规则 -->
          <el-card shadow="never" class="frwb-card frwb-llm__card">
            <template #header>
              <div class="frwb-llm__head">
                <span class="frwb-card__title">{{ t("ai_workflow.ig_genCandidateRules") }}</span>
                <el-button size="small" :loading="llmLoading" @click="doSuggest">
                  {{ t("ai_workflow.ig_genCandidateRules") }}
                </el-button>
              </div>
            </template>
            <template v-if="suggestResult">
              <RulePreview :rules="suggestResult" />
              <div class="frwb-llm__foot">
                <el-button
                  v-hasPerm="['module_ai:query:ask']"
                  size="small"
                  type="primary"
                  @click="applyRules(suggestResult)"
                >
                  {{ t("ai_workflow.ig_applyDraft") }}
                </el-button>
              </div>
            </template>
            <el-empty
              v-else
              :description="t('ai_workflow.ig_genCandidateEmpty')"
              :image-size="60"
            />
          </el-card>

          <!-- 5.2) 自然语言配置 -->
          <el-card shadow="never" class="frwb-card frwb-llm__card">
            <template #header>
              <span class="frwb-card__title">{{ t("ai_workflow.ig_nlConfig") }}</span>
            </template>
            <el-input
              v-model="llmText"
              type="textarea"
              :rows="3"
              :placeholder="t('ai_workflow.ig_nlPlaceholder')"
            />
            <div class="frwb-llm__foot">
              <el-button
                size="small"
                type="primary"
                :loading="llmLoading"
                :disabled="!llmText.trim()"
                @click="doParse"
              >
                {{ t("ai_workflow.ig_parse") }}
              </el-button>
            </div>
            <template v-if="parseResult">
              <RulePreview :rules="parseResult" />
              <div class="frwb-llm__foot">
                <el-button
                  v-hasPerm="['module_ai:query:ask']"
                  size="small"
                  type="primary"
                  @click="applyRules(parseResult)"
                >
                  {{ t("ai_workflow.ig_applyDraft") }}
                </el-button>
              </div>
            </template>
            <el-empty v-else :description="t('ai_workflow.ig_parseEmpty')" :image-size="60" />
          </el-card>

          <!-- 5.3) 逐表逐字段建议 -->
          <el-card shadow="never" class="frwb-card frwb-llm__card">
            <template #header>
              <div class="frwb-llm__head">
                <span class="frwb-card__title">{{ t("ai_workflow.ig_perTableSuggest") }}</span>
                <el-button size="small" :loading="llmLoading" @click="doClassify">
                  {{ t("ai_workflow.ig_getClassify") }}
                </el-button>
              </div>
            </template>
            <template v-if="classifyResult">
              <div class="frwb-llm__subtitle">
                {{
                  t("ai_workflow.ig_sysSuggest", {
                    count: classifyResult.system_suggest?.length || 0,
                  })
                }}
              </div>
              <el-table :data="classifyResult.system_suggest || []" size="small" border stripe>
                <el-table-column
                  :label="t('ai_workflow.ig_tableName')"
                  prop="name"
                  min-width="200"
                  show-overflow-tooltip
                />
                <el-table-column
                  :label="t('ai_workflow.ig_suggestReason')"
                  prop="reason"
                  min-width="260"
                  show-overflow-tooltip
                />
              </el-table>
              <div class="frwb-llm__subtitle">
                {{
                  t("ai_workflow.ig_auditSuggest", {
                    count: classifyResult.audit_suggest?.length || 0,
                  })
                }}
              </div>
              <el-table :data="classifyResult.audit_suggest || []" size="small" border stripe>
                <el-table-column
                  :label="t('ai_workflow.ig_fieldName')"
                  prop="name"
                  min-width="200"
                  show-overflow-tooltip
                />
                <el-table-column
                  :label="t('ai_workflow.ig_suggestReason')"
                  prop="reason"
                  min-width="260"
                  show-overflow-tooltip
                />
              </el-table>
              <el-alert
                type="warning"
                :closable="false"
                class="frwb-note"
                :title="t('ai_workflow.ig_classifyHint')"
              />
            </template>
            <el-empty v-else :description="t('ai_workflow.ig_classifyEmpty')" :image-size="60" />
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount, defineComponent, h } from "vue";
import { ElMessage, ElMessageBox, ElForm, ElFormItem } from "element-plus";
import { Refresh, Right } from "@element-plus/icons-vue";
import { useI18n } from "vue-i18n";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { PieChart } from "echarts/charts";
import { CanvasRenderer } from "echarts/renderers";
import { TooltipComponent, LegendComponent } from "echarts/components";
import {
  getDatasourceDetail,
  saveQueryDatasource,
  syncQueryDatasourceSchema,
  previewFilterRules,
  suggestFilterRules,
  parseFilterRules,
  classifyAdvise,
} from "@/api/module_ai/query";

use([PieChart, CanvasRenderer, TooltipComponent, LegendComponent]);

const props = defineProps<{ datasource: any }>();
const { t } = useI18n();

// 规则默认结构：与后端 filter_rules 一致
function defaultRules() {
  return {
    enabled: true,
    system_table: { prefixes: [], keywords: [], exact: [], regex: "" },
    audit_fields: [],
  };
}

// 防御性 normalize：后端返回的 filter_rules 可能缺子字段（如无 system_table），
// 用默认结构逐项补齐，避免模板里 rules.system_table.prefixes 空指针
function normalizeRules(raw: any) {
  const r = raw || {};
  const st = r.system_table || {};
  return {
    enabled: r.enabled !== false,
    system_table: {
      prefixes: Array.isArray(st.prefixes) ? st.prefixes : [],
      keywords: Array.isArray(st.keywords) ? st.keywords : [],
      exact: Array.isArray(st.exact) ? st.exact : [],
      regex: st.regex || "",
    },
    audit_fields: Array.isArray(r.audit_fields) ? r.audit_fields : [],
  };
}

// 深拷贝：规则是结构化对象，避免直接引用同一内存导致草稿与基准互相污染
function deepClone(v: any) {
  return JSON.parse(JSON.stringify(v));
}

// 只读规则预览小部件：复用同一套展示，供「生成候选 / 自然语言解析」两处回显规则
const RulePreview = defineComponent({
  name: "RulePreview",
  props: { rules: { type: Object, required: true } },
  setup(props) {
    // 数组字段取空串兜底，避免展示 undefined
    const fmt = (arr: any) => (Array.isArray(arr) && arr.length ? arr.join("、") : "—");
    return () =>
      h(ElForm, { labelWidth: "110px", size: "small", class: "frwb-llm__preview" }, () => [
        h(ElFormItem, { label: t("ai_workflow.ig_enableRule") }, () => [
          h(
            "span",
            props.rules?.enabled === false
              ? t("ai_workflow.ig_enabledOff")
              : t("ai_workflow.ig_enabledOn")
          ),
        ]),
        h(ElFormItem, { label: t("ai_workflow.ig_sysTablePrefix") }, () => [
          h("span", fmt(props.rules?.system_table?.prefixes)),
        ]),
        h(ElFormItem, { label: t("ai_workflow.ig_sysTableKeyword") }, () => [
          h("span", fmt(props.rules?.system_table?.keywords)),
        ]),
        h(ElFormItem, { label: t("ai_workflow.ig_exactTable") }, () => [
          h("span", fmt(props.rules?.system_table?.exact)),
        ]),
        h(ElFormItem, { label: t("ai_workflow.ig_tableRegex") }, () => [
          h("span", props.rules?.system_table?.regex || "—"),
        ]),
        h(ElFormItem, { label: t("ai_workflow.ig_auditField") }, () => [
          h("span", fmt(props.rules?.audit_fields)),
        ]),
      ]);
  },
});

const innerTab = ref("config");
const dsDetail = ref<any>(null);
const rules = ref<any>(defaultRules());
const preview = ref<any>(null);
const savedRules = ref<any>(defaultRules());
const savedPreview = ref<any>(null);
const loading = ref(false);
const saving = ref(false);
const compareLoading = ref(false);
// 前后对比是否已成功加载过基准（已保存规则的命中结果）
const compareLoaded = ref(false);
// 大模型辅助：共用 loading 标志，避免三区同时重复点击
const llmLoading = ref(false);
// 自然语言输入
const llmText = ref("");
// 生成候选 / 自然语言解析的候选规则结果
const suggestResult = ref<any>(null);
const parseResult = ref<any>(null);
// 逐表逐字段分类建议结果（system_suggest / audit_suggest）
const classifyResult = ref<any>(null);
// 数据源切换代际守卫：仅接受当前代际的异步响应，避免旧数据源晚回覆盖新数据源
let gen = 0;

const enabledText = computed(() =>
  rules.value?.enabled ? t("ai_workflow.ig_enabledOn") : t("ai_workflow.ig_enabledOff")
);

const baseCounts = computed(() => {
  const loaded = !!savedPreview.value;
  const s = savedPreview.value?.summary || {};
  const c = preview.value?.summary || {};
  const num = (v: any) => (loaded ? v || 0 : "—");
  return {
    saved: {
      sys: num(s.system_tables),
      biz: num(s.business_tables),
      audit: num(s.audit_fields),
      bizf: num(s.business_fields),
    },
    draft: {
      sys: c.system_tables || 0,
      biz: c.business_tables || 0,
      audit: c.audit_fields || 0,
      bizf: c.business_fields || 0,
    },
  };
});

// 前后对比：遍历当前草稿命中与已保存命中的表/字段，标记命中类别发生变化者
const compareItems = computed(() => {
  const out: any[] = [];
  const curTables: any[] = preview.value?.tables || [];
  const savedTables: any[] = savedPreview.value?.tables || [];
  const savedByName = new Map(savedTables.map((t: any) => [t.name, t]));
  for (const t of curTables) {
    const s = savedByName.get(t.name);
    if (s && !!s.is_system !== !!t.is_system) {
      out.push({
        kind: t("ai_workflow.ig_kgTypeTable"),
        name: t.name,
        from: s.is_system
          ? t("ai_workflow.ig_systemTagShort")
          : t("ai_workflow.ig_businessTagShort"),
        to: t.is_system ? t("ai_workflow.ig_systemTagShort") : t("ai_workflow.ig_businessTagShort"),
        // 同时展示已保存侧与草稿侧命中原因：翻转方向（如系统→业务 / 审计→业务）时，
        // 草稿侧为空，用户仍能看到「它之前为何被判为系统/审计」（已保存侧原因）。
        reason: t("ai_workflow.ig_reasonCompare", {
          saved: s.reason || "—",
          draft: t.reason || "—",
        }),
      });
    }
  }
  const curFields: any[] = preview.value?.fields || [];
  const savedFields: any[] = savedPreview.value?.fields || [];
  const savedFieldByName = new Map(savedFields.map((f: any) => [f.name, f]));
  for (const f of curFields) {
    const s = savedFieldByName.get(f.name);
    if (s && !!s.is_audit !== !!f.is_audit) {
      out.push({
        kind: t("ai_workflow.ig_kgTypeField"),
        name: f.name,
        from: s.is_audit ? t("ai_workflow.ig_auditTagShort") : t("ai_workflow.ig_businessTagShort"),
        to: f.is_audit ? t("ai_workflow.ig_auditTagShort") : t("ai_workflow.ig_businessTagShort"),
        // 同表：叠加展示已保存侧与草稿侧命中原因，翻转方向时也不丢失历史依据
        reason: t("ai_workflow.ig_reasonCompare", {
          saved: s.reason || "—",
          draft: f.reason || "—",
        }),
      });
    }
  }
  return out;
});

// 概览：两张饼图（系统/业务表、审计/业务字段）
const tablePieOption = computed(() => {
  const s = preview.value?.summary;
  if (!s) return null;
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        center: ["50%", "45%"],
        label: { show: true, formatter: "{b}\n{d}%" },
        data: [
          { name: t("ai_workflow.ig_systemTable"), value: s.system_tables || 0 },
          { name: t("ai_workflow.ig_businessTable"), value: s.business_tables || 0 },
        ],
      },
    ],
  };
});
const fieldPieOption = computed(() => {
  const s = preview.value?.summary;
  if (!s) return null;
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { bottom: 0 },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        center: ["50%", "45%"],
        label: { show: true, formatter: "{b}\n{d}%" },
        data: [
          { name: t("ai_workflow.ig_auditField"), value: s.audit_fields || 0 },
          { name: t("ai_workflow.ig_businessField"), value: s.business_fields || 0 },
        ],
      },
    ],
  };
});

// 实时预览：用当前草稿规则请求命中结果
async function doRefreshPreview() {
  if (!props.datasource?.id) return;
  const myGen = gen;
  const dsId = props.datasource.id;
  loading.value = true;
  try {
    const r = await previewFilterRules(dsId, rules.value);
    if (myGen !== gen) return; // 已切换数据源，丢弃旧响应
    preview.value = r.data?.data || null;
  } catch (e: any) {
    if (myGen !== gen) return;
    ElMessage.error(e?.msg || t("ai_workflow.ig_previewFail"));
  } finally {
    if (myGen === gen) loading.value = false;
  }
}

// 防抖刷新：配置区 @change 触发，避免频繁改动时连续请求
let previewTimer: any = null;
function scheduleRefresh() {
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(() => doRefreshPreview(), 300);
}

// 大模型辅助：把候选/解析规则写入前端草稿（仅改草稿不落库，无需二次确认），并刷新预览、切回「规则配置」
function applyRules(r: any) {
  // 空对象保护：后端可能返回空对象/缺 rules，避免把草稿重置为全默认规则
  const hasRules =
    r &&
    typeof r === "object" &&
    Object.values(r).some((v) => v !== undefined && v !== null && v !== "");
  if (!hasRules) {
    ElMessage.warning(t("ai_workflow.ig_noValidRules"));
    return;
  }
  rules.value = normalizeRules(r);
  doRefreshPreview();
  ElMessage.success(t("ai_workflow.ig_appliedDraft"));
  innerTab.value = "config";
}

// 生成候选规则：基于当前草稿交给大模型生成候选
async function doSuggest() {
  if (!props.datasource?.id) return;
  const myGen = gen; // 代际守卫：数据源切换后丢弃旧响应
  llmLoading.value = true;
  try {
    const r = await suggestFilterRules(props.datasource.id, rules.value);
    if (myGen !== gen) return;
    suggestResult.value = r.data?.data?.rules || null;
  } catch (e: any) {
    if (myGen !== gen) return;
    ElMessage.error(e?.msg || t("ai_workflow.ig_genCandidateFail"));
  } finally {
    if (myGen === gen) llmLoading.value = false;
  }
}

// 自然语言解析：把自然语言描述转成筛选规则
async function doParse() {
  if (!props.datasource?.id || !llmText.value.trim()) return;
  const myGen = gen; // 代际守卫
  llmLoading.value = true;
  try {
    const r = await parseFilterRules(props.datasource.id, llmText.value);
    if (myGen !== gen) return;
    parseResult.value = r.data?.data?.rules || null;
  } catch (e: any) {
    if (myGen !== gen) return;
    ElMessage.error(e?.msg || t("ai_workflow.ig_parseFail"));
  } finally {
    if (myGen === gen) llmLoading.value = false;
  }
}

// 逐表逐字段分类建议：仅展示建议，不回填规则
async function doClassify() {
  if (!props.datasource?.id) return;
  const myGen = gen; // 代际守卫
  llmLoading.value = true;
  try {
    const r = await classifyAdvise(props.datasource.id, rules.value);
    if (myGen !== gen) return;
    classifyResult.value = r.data?.data || null;
  } catch (e: any) {
    if (myGen !== gen) return;
    ElMessage.error(e?.msg || t("ai_workflow.ig_getClassifyFail"));
  } finally {
    if (myGen === gen) llmLoading.value = false;
  }
}

// 进入 / 切换数据源时加载详情与初始预览
function loadAll() {
  if (!props.datasource?.id) return;
  const myGen = ++gen; // 开启新一代际，使旧数据源的在途响应失效
  // 切换数据源前清除 pending 防抖，避免旧 rules + 新 id 触发瞬时脏预览
  if (previewTimer) {
    clearTimeout(previewTimer);
    previewTimer = null;
  }
  getDatasourceDetail(props.datasource.id)
    .then((r) => {
      if (myGen !== gen) return;
      const d = r.data?.data || {};
      dsDetail.value = d;
      const fr = normalizeRules(d.filter_rules);
      rules.value = deepClone(fr);
      savedRules.value = deepClone(fr);
      savedPreview.value = null;
      compareLoaded.value = false;
      doRefreshPreview();
    })
    .catch((e: any) => {
      if (myGen !== gen) return;
      ElMessage.error(e?.msg || t("ai_workflow.ig_loadDsFail"));
    });
}

// 前后对比：用已保存规则重新请求一次命中，作为比对基准
async function loadSavedPreview() {
  if (!props.datasource?.id) return;
  const myGen = gen;
  compareLoading.value = true;
  try {
    const r = await previewFilterRules(props.datasource.id, savedRules.value);
    if (myGen !== gen) return;
    savedPreview.value = r.data?.data || null;
    compareLoaded.value = true;
  } catch (e: any) {
    if (myGen !== gen) return;
    ElMessage.error(e?.msg || t("ai_workflow.ig_compareLoadFail"));
  } finally {
    if (myGen === gen) compareLoading.value = false;
  }
}

// 保存（覆盖已保存规则，必须二次确认，并写明不可逆）
async function confirmSave(apply: boolean) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.ig_confirmSave"),
      apply ? t("ai_workflow.ig_saveApplyRules") : t("ai_workflow.ig_saveRules"),
      {
        type: "warning",
        confirmButtonText: apply ? t("ai_workflow.ig_saveApplyRules") : t("ai_workflow.ig_save"),
        cancelButtonText: t("ai_workflow.ig_cancel"),
      }
    );
  } catch {
    return;
  }
  saving.value = true;
  try {
    // 用快照作为 payload 与保存成功后的基准，避免保存期间用户继续编辑导致基准与实际不同步。
    // 注意：dsDetail（getDatasourceDetail 返回）是 { source:{...}, tables, connector, asset_count }
    // 嵌套结构，顶层没有 name/code；而后端 QueryDatasourceUpsert 要求顶层必填 name/code。
    // 因此这里用父级传入的 props.datasource（列表行 curDs，含 id/name/code/type/host/port/...），
    // Pydantic 会忽略其中的 table_count 等额外字段；password 缺省为空串，可直接保存。
    const snapshot = deepClone(rules.value);
    await saveQueryDatasource({ ...props.datasource, filter_rules: snapshot });
    if (apply) {
      await syncQueryDatasourceSchema(props.datasource.id);
    }
    savedRules.value = deepClone(snapshot);
    savedPreview.value = null;
    compareLoaded.value = false;
    ElMessage.success(apply ? t("ai_workflow.ig_savedApplied") : t("ai_workflow.ig_savedRules"));
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.ig_saveFail"));
  } finally {
    saving.value = false;
  }
}

// 切换数据源时重新加载
watch(
  () => props.datasource?.id,
  () => loadAll(),
  { immediate: true }
);

// 组件卸载时清理 pending 防抖定时器
onBeforeUnmount(() => {
  if (previewTimer) {
    clearTimeout(previewTimer);
    previewTimer = null;
  }
});
</script>

<style lang="scss" scoped>
/* 单根容器：内部子 tab 撑满但不依赖外层 flex，避免被裁剪 */
.frwb {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.frwb-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  margin-bottom: 10px;
}
.frwb-bar--left {
  justify-content: flex-start;
}
.frwb-bar__ops {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.frwb-summary {
  flex: 1 1 auto;
  min-width: 0;
}
.frwb-summary--cmp {
  margin-bottom: 10px;
}
.frwb-note {
  flex-shrink: 0;
  margin-bottom: 10px;
}
.frwb-tabs,
.frwb-tabs :deep(.el-tabs__content),
.frwb-tabs :deep(.el-tab-pane) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}
.frwb-pane {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px 2px;
}
.frwb-preview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.frwb-form {
  max-width: 720px;
}
.frwb-divider {
  margin: 6px 0 10px;
}
.frwb-foot {
  margin-top: 4px;
}
.frwb-card {
  flex-shrink: 0;
}
.frwb-card__title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.frwb-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.frwb-mono {
  font-family: var(--el-font-family-mono, monospace);
  color: var(--el-text-color-primary);
}
.frwb-change {
  color: var(--el-text-color-secondary);
}
.frwb-change--to {
  color: var(--el-color-primary);
  font-weight: 600;
}
.frwb-arrow {
  margin: 0 4px;
  vertical-align: middle;
}
/* 大模型辅助区：卡片纵向堆叠 + 每卡内头部/底部操作行 */
.frwb-llm {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.frwb-llm__card {
  flex-shrink: 0;
}
.frwb-llm__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.frwb-llm__subtitle {
  margin: 10px 0 6px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.frwb-llm__foot {
  display: flex;
  justify-content: flex-start;
  gap: 8px;
  margin-top: 10px;
}
.frwb-llm__preview {
  margin-top: 4px;
}
</style>
