<!-- 筛选规则工作台：配置 / 实时预览 / 前后对比 / 概览（首期无大模型）
     数据流：由父级传入选中数据源（列表行，含 id/name），此处用 getDatasourceDetail 拉全量详情（含 filter_rules），
     草稿规则在「规则配置」区编辑，编辑即防抖刷新预览；「保存规则/保存并应用」会覆盖已保存规则，须二次确认。 -->
<template>
  <div class="frwb">
    <!-- 顶栏：命中摘要 + 操作 -->
    <div class="frwb-bar">
      <el-descriptions :column="4" size="small" border class="frwb-summary">
        <el-descriptions-item label="系统表">
          {{ preview?.summary?.system_tables ?? "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="业务表">
          {{ preview?.summary?.business_tables ?? "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="审计字段">
          {{ preview?.summary?.audit_fields ?? "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="业务字段">
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
          保存规则
        </el-button>
        <el-button
          v-hasPerm="['module_ai:query:ask']"
          size="small"
          type="primary"
          :loading="saving"
          :disabled="!dsDetail"
          @click="confirmSave(true)"
        >
          保存并应用
        </el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="frwb-note"
      title="规则一改即自动刷新下方预览（只读，不影响已保存规则）；确认无误后再点「保存规则 / 保存并应用」。"
    />

    <!-- 内部子 tab -->
    <el-tabs v-model="innerTab" class="frwb-tabs">
      <!-- 1) 规则配置 -->
      <el-tab-pane label="规则配置" name="config">
        <div v-loading="loading" class="frwb-pane">
          <ElForm :model="rules" label-width="110px" size="small" class="frwb-form">
            <ElFormItem label="启用规则">
              <el-switch v-model="rules.enabled" @change="scheduleRefresh" />
              <span class="frwb-hint">关闭后不按规则自动打标系统表 / 审计字段</span>
            </ElFormItem>
            <el-divider content-position="left" class="frwb-divider">系统表识别</el-divider>
            <ElFormItem label="表名前缀">
              <el-select
                v-model="rules.system_table.prefixes"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                placeholder="回车新增，如 SYS_ / FUEL_"
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
            <ElFormItem label="表名关键词">
              <el-select
                v-model="rules.system_table.keywords"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                placeholder="回车新增，如 _BAK / log"
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
            <ElFormItem label="精确表名">
              <el-select
                v-model="rules.system_table.exact"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                placeholder="回车新增，如 alembic_version"
                style="width: 100%"
                @change="scheduleRefresh"
              >
                <el-option v-for="e in rules.system_table.exact" :key="e" :label="e" :value="e" />
              </el-select>
            </ElFormItem>
            <ElFormItem label="表名正则">
              <el-input
                v-model="rules.system_table.regex"
                placeholder="可空，如 ^TMP_"
                @change="scheduleRefresh"
              />
            </ElFormItem>
            <el-divider content-position="left" class="frwb-divider">审计字段识别</el-divider>
            <ElFormItem label="审计字段">
              <el-select
                v-model="rules.audit_fields"
                multiple
                filterable
                allow-create
                default-first-option
                :multiple-limit="0"
                placeholder="回车新增，如 created_time / is_deleted"
                style="width: 100%"
                @change="scheduleRefresh"
              >
                <el-option v-for="a in rules.audit_fields" :key="a" :label="a" :value="a" />
              </el-select>
            </ElFormItem>
          </ElForm>
          <div class="frwb-foot">
            <el-tag size="small" type="info" effect="plain">
              当前草稿：{{ enabledText }}；保存后可作为「前后对比」基准
            </el-tag>
          </div>
        </div>
      </el-tab-pane>

      <!-- 2) 实时预览 -->
      <el-tab-pane label="实时预览" name="preview">
        <div v-loading="loading" class="frwb-pane frwb-preview">
          <el-alert
            type="success"
            :closable="false"
            class="frwb-note"
            title="以下为当前草稿规则命中的结果（只读），不会影响已保存规则。"
          />
          <el-card shadow="never" class="frwb-card">
            <template #header>
              <span class="frwb-card__title">表清单（{{ preview?.tables?.length ?? 0 }}）</span>
            </template>
            <el-table :data="preview?.tables || []" size="small" border height="300">
              <template #empty>
                <el-empty description="暂无表数据，请先同步表结构" :image-size="50" />
              </template>
              <el-table-column label="表名" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="frwb-mono">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="系统·业务" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.is_system ? 'info' : 'success'" effect="plain">
                    {{ row.is_system ? "系统" : "业务" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="命中规则" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.reason || "—" }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          <el-card shadow="never" class="frwb-card">
            <template #header>
              <span class="frwb-card__title">字段清单（{{ preview?.fields?.length ?? 0 }}）</span>
            </template>
            <el-table :data="preview?.fields || []" size="small" border height="300">
              <template #empty>
                <el-empty description="暂无字段数据，请先同步表结构" :image-size="50" />
              </template>
              <el-table-column label="字段名" min-width="200" show-overflow-tooltip>
                <template #default="{ row }">
                  <span class="frwb-mono">{{ row.name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="审计·业务" width="110" align="center">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.is_audit ? 'info' : 'success'" effect="plain">
                    {{ row.is_audit ? "审计" : "业务" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="命中规则" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ row.reason || "—" }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- 3) 前后对比 -->
      <el-tab-pane label="前后对比" name="compare">
        <div v-loading="compareLoading" class="frwb-pane">
          <div class="frwb-bar frwb-bar--left">
            <el-button
              size="small"
              :icon="Refresh"
              :loading="compareLoading"
              @click="loadSavedPreview"
            >
              刷新对比
            </el-button>
            <el-tag size="small" type="info" effect="plain">
              已保存规则 vs 当前草稿（命中标记发生变化的表 / 字段）
            </el-tag>
          </div>

          <!-- 基础计数对比 -->
          <el-descriptions :column="4" size="small" border class="frwb-summary frwb-summary--cmp">
            <el-descriptions-item label="系统表">
              已保存 {{ baseCounts.saved.sys }} / 草稿 {{ baseCounts.draft.sys }}
            </el-descriptions-item>
            <el-descriptions-item label="业务表">
              已保存 {{ baseCounts.saved.biz }} / 草稿 {{ baseCounts.draft.biz }}
            </el-descriptions-item>
            <el-descriptions-item label="审计字段">
              已保存 {{ baseCounts.saved.audit }} / 草稿 {{ baseCounts.draft.audit }}
            </el-descriptions-item>
            <el-descriptions-item label="业务字段">
              已保存 {{ baseCounts.saved.bizf }} / 草稿 {{ baseCounts.draft.bizf }}
            </el-descriptions-item>
          </el-descriptions>

          <el-alert
            v-if="!compareLoaded && !compareLoading"
            type="info"
            :closable="false"
            class="frwb-note"
            title="尚未对比：点「刷新对比」后，再查看已保存规则与当前草稿的命中差异。"
          />
          <el-alert
            v-else-if="!compareItems.length"
            type="success"
            :closable="false"
            class="frwb-note"
            title="已保存规则与当前草稿一致，无命中变化。"
          />
          <el-table v-else :data="compareItems" size="small" border height="320">
            <template #empty>
              <el-empty description="暂无差异（先点「刷新对比」或修改草稿规则）" :image-size="50" />
            </template>
            <el-table-column label="类型" width="80" align="center">
              <template #default="{ row }">
                <el-tag
                  size="small"
                  :type="row.kind === '表' ? 'warning' : 'primary'"
                  effect="plain"
                >
                  {{ row.kind }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="名称" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="frwb-mono">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="命中变化" width="160" align="center">
              <template #default="{ row }">
                <span class="frwb-change">{{ row.from }}</span>
                <el-icon class="frwb-arrow"><Right /></el-icon>
                <span class="frwb-change frwb-change--to">{{ row.to }}</span>
              </template>
            </el-table-column>
            <el-table-column
              label="命中规则（已保存 → 草稿）"
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
      <el-tab-pane label="概览" name="overview">
        <div v-loading="loading" class="frwb-pane">
          <el-row :gutter="12">
            <el-col :xs="24" :sm="12">
              <el-card shadow="never" class="frwb-card">
                <template #header>
                  <span class="frwb-card__title">系统 vs 业务表</span>
                </template>
                <VChart
                  v-if="tablePieOption"
                  :option="tablePieOption"
                  style="height: 260px"
                  autoresize
                />
                <el-empty v-else description="暂无数据" :image-size="60" />
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-card shadow="never" class="frwb-card">
                <template #header>
                  <span class="frwb-card__title">审计 vs 业务字段</span>
                </template>
                <VChart
                  v-if="fieldPieOption"
                  :option="fieldPieOption"
                  style="height: 260px"
                  autoresize
                />
                <el-empty v-else description="暂无数据" :image-size="60" />
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- 5) 大模型辅助：生成候选 / 自然语言配置 / 逐表逐字段建议 -->
      <el-tab-pane label="大模型辅助" name="llm">
        <div v-loading="llmLoading" class="frwb-pane frwb-llm">
          <el-alert
            type="info"
            :closable="false"
            class="frwb-note"
            title="以下三区均由大模型辅助生成候选规则 / 建议；「应用到草稿」仅写入前端草稿（未落库），确认后可回「规则配置」微调再保存。"
          />

          <!-- 5.1) 生成候选规则 -->
          <el-card shadow="never" class="frwb-card frwb-llm__card">
            <template #header>
              <div class="frwb-llm__head">
                <span class="frwb-card__title">生成候选规则</span>
                <el-button size="small" :loading="llmLoading" @click="doSuggest">
                  生成候选规则
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
                  应用到草稿
                </el-button>
              </div>
            </template>
            <el-empty
              v-else
              description="点「生成候选规则」让大模型给出候选规则"
              :image-size="60"
            />
          </el-card>

          <!-- 5.2) 自然语言配置 -->
          <el-card shadow="never" class="frwb-card frwb-llm__card">
            <template #header>
              <span class="frwb-card__title">自然语言配置</span>
            </template>
            <el-input
              v-model="llmText"
              type="textarea"
              :rows="3"
              placeholder="用自然语言描述规则，例如：把 SYS_ 前缀的表当系统表，created_time / is_deleted 当审计字段"
            />
            <div class="frwb-llm__foot">
              <el-button
                size="small"
                type="primary"
                :loading="llmLoading"
                :disabled="!llmText.trim()"
                @click="doParse"
              >
                解析
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
                  应用到草稿
                </el-button>
              </div>
            </template>
            <el-empty
              v-else
              description="输入自然语言后点「解析」转换为筛选规则"
              :image-size="60"
            />
          </el-card>

          <!-- 5.3) 逐表逐字段建议 -->
          <el-card shadow="never" class="frwb-card frwb-llm__card">
            <template #header>
              <div class="frwb-llm__head">
                <span class="frwb-card__title">逐表逐字段建议</span>
                <el-button size="small" :loading="llmLoading" @click="doClassify">
                  获取分类建议
                </el-button>
              </div>
            </template>
            <template v-if="classifyResult">
              <div class="frwb-llm__subtitle">
                系统表建议（{{ classifyResult.system_suggest?.length || 0 }}）
              </div>
              <el-table :data="classifyResult.system_suggest || []" size="small" border>
                <el-table-column label="表名" prop="name" min-width="200" show-overflow-tooltip />
                <el-table-column
                  label="建议原因"
                  prop="reason"
                  min-width="260"
                  show-overflow-tooltip
                />
              </el-table>
              <div class="frwb-llm__subtitle">
                审计字段建议（{{ classifyResult.audit_suggest?.length || 0 }}）
              </div>
              <el-table :data="classifyResult.audit_suggest || []" size="small" border>
                <el-table-column label="字段名" prop="name" min-width="200" show-overflow-tooltip />
                <el-table-column
                  label="建议原因"
                  prop="reason"
                  min-width="260"
                  show-overflow-tooltip
                />
              </el-table>
              <el-alert
                type="warning"
                :closable="false"
                class="frwb-note"
                title="此处为逐项分类建议，非完整规则，仅作参考，不回填草稿。"
              />
            </template>
            <el-empty v-else description="点「获取分类建议」查看逐表逐字段建议" :image-size="60" />
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
        h(ElFormItem, { label: "启用" }, () => [
          h("span", props.rules?.enabled === false ? "停用" : "启用"),
        ]),
        h(ElFormItem, { label: "表名前缀" }, () => [
          h("span", fmt(props.rules?.system_table?.prefixes)),
        ]),
        h(ElFormItem, { label: "表名关键词" }, () => [
          h("span", fmt(props.rules?.system_table?.keywords)),
        ]),
        h(ElFormItem, { label: "精确表名" }, () => [
          h("span", fmt(props.rules?.system_table?.exact)),
        ]),
        h(ElFormItem, { label: "表名正则" }, () => [
          h("span", props.rules?.system_table?.regex || "—"),
        ]),
        h(ElFormItem, { label: "审计字段" }, () => [h("span", fmt(props.rules?.audit_fields))]),
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

const enabledText = computed(() => (rules.value?.enabled ? "已启用" : "已停用"));

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
        kind: "表",
        name: t.name,
        from: s.is_system ? "系统" : "业务",
        to: t.is_system ? "系统" : "业务",
        // 同时展示已保存侧与草稿侧命中原因：翻转方向（如系统→业务 / 审计→业务）时，
        // 草稿侧为空，用户仍能看到「它之前为何被判为系统/审计」（已保存侧原因）。
        reason: `已保存 ${s.reason || "—"} → 草稿 ${t.reason || "—"}`,
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
        kind: "字段",
        name: f.name,
        from: s.is_audit ? "审计" : "业务",
        to: f.is_audit ? "审计" : "业务",
        // 同表：叠加展示已保存侧与草稿侧命中原因，翻转方向时也不丢失历史依据
        reason: `已保存 ${s.reason || "—"} → 草稿 ${f.reason || "—"}`,
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
          { name: "系统表", value: s.system_tables || 0 },
          { name: "业务表", value: s.business_tables || 0 },
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
          { name: "审计字段", value: s.audit_fields || 0 },
          { name: "业务字段", value: s.business_fields || 0 },
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
    ElMessage.error(e?.msg || "预览失败");
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
    ElMessage.warning("未返回有效规则，已取消应用");
    return;
  }
  rules.value = normalizeRules(r);
  doRefreshPreview();
  ElMessage.success("已应用到草稿（未落库），可回「规则配置」微调后再保存");
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
    ElMessage.error(e?.msg || "生成候选规则失败");
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
    ElMessage.error(e?.msg || "解析失败");
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
    ElMessage.error(e?.msg || "获取分类建议失败");
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
      ElMessage.error(e?.msg || "加载数据源详情失败");
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
    ElMessage.error(e?.msg || "对比加载失败");
  } finally {
    if (myGen === gen) compareLoading.value = false;
  }
}

// 保存（覆盖已保存规则，必须二次确认，并写明不可逆）
async function confirmSave(apply: boolean) {
  try {
    await ElMessageBox.confirm(
      "将用当前草稿覆盖该数据源已保存的筛选规则，保存后原规则将被替换且不可恢复，是否继续？",
      apply ? "保存并应用" : "保存规则",
      {
        type: "warning",
        confirmButtonText: apply ? "保存并应用" : "保存",
        cancelButtonText: "取消",
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
    ElMessage.success(apply ? "规则已保存并应用" : "规则已保存");
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
