<template>
  <div class="ev-cases">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>{{ $t("ai_workflow.eval_casesTitle") }}</span>
          <div class="ev-head__ops">
            <el-select
              v-model="filters.datasource"
              size="small"
              clearable
              :placeholder="$t('ai_workflow.eval_datasource')"
              style="width: 170px"
              @change="load"
            >
              <el-option :label="$t('ai_workflow.eval_systemDs')" value="system" />
              <el-option
                v-for="d in datasources"
                :key="d.code || d.id"
                :label="d.name"
                :value="d.code || `ds:${d.id}`"
              />
            </el-select>
            <el-select
              v-model="filters.difficulty"
              size="small"
              clearable
              :placeholder="$t('ai_workflow.eval_difficulty')"
              style="width: 110px"
              @change="load"
            >
              <el-option
                v-for="d in DIFFICULTIES"
                :key="d"
                :label="$t('ai_workflow.' + diffKey(d))"
                :value="d"
              />
            </el-select>
            <el-select
              v-model="filters.form"
              size="small"
              clearable
              :placeholder="$t('ai_workflow.eval_form')"
              style="width: 140px"
              @change="load"
            >
              <el-option
                v-for="f in FORMS"
                :key="f"
                :label="$t('ai_workflow.' + formKey(f))"
                :value="f"
              />
            </el-select>
            <el-select
              v-model="filters.enabled"
              size="small"
              clearable
              :placeholder="$t('ai_workflow.eval_enabled')"
              style="width: 110px"
              @change="load"
            >
              <el-option :label="$t('ai_workflow.eval_all')" value="" />
              <el-option :label="$t('ai_workflow.eval_enabledOn')" value="true" />
              <el-option :label="$t('ai_workflow.eval_enabledOff')" value="false" />
            </el-select>
            <el-input
              v-model="filters.dataset"
              size="small"
              clearable
              :placeholder="$t('ai_workflow.eval_dataset')"
              style="width: 140px"
              @keyup.enter="load"
              @clear="load"
            />
            <el-button size="small" @click="load">{{ $t("ai_workflow.eval_refresh") }}</el-button>
            <el-button size="small" type="primary" plain @click="openCreate">
              {{ $t("ai_workflow.eval_addCase") }}
            </el-button>
            <el-button size="small" type="primary" @click="genVisible = true">
              {{ $t("ai_workflow.eval_genCase") }}
            </el-button>
            <el-button size="small" @click="importVisible = true">
              {{ $t("ai_workflow.eval_import") }}
            </el-button>
            <el-button size="small" :loading="verifying" @click="doVerify">
              {{ $t("ai_workflow.eval_verify") }}
            </el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="!selection.length"
              @click="removeSelected"
            >
              {{ $t("ai_workflow.eval_batchDelete") }}
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="cases"
        size="small"
        border
        stripe
        @selection-change="selection = $event"
      >
        <el-table-column type="selection" width="44" />
        <el-table-column type="index" label="#" width="52" />
        <el-table-column
          prop="question"
          :label="$t('ai_workflow.eval_question')"
          min-width="280"
          show-overflow-tooltip
        />
        <el-table-column prop="datasource" :label="$t('ai_workflow.eval_datasource')" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.datasource }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="difficulty" :label="$t('ai_workflow.eval_difficulty')" width="88">
          <template #default="{ row }">
            <el-tag size="small" :type="difficultyTag(row.difficulty)">
              {{ $t("ai_workflow." + diffKey(row.difficulty)) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="form" :label="$t('ai_workflow.eval_form')" width="120">
          <template #default="{ row }">
            {{ $t("ai_workflow." + formKey(row.form)) }}
          </template>
        </el-table-column>
        <el-table-column
          prop="scenario"
          :label="$t('ai_workflow.eval_scenario')"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="dataset"
          :label="$t('ai_workflow.eval_dataset')"
          width="130"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <el-tag v-if="row.dataset" size="small" effect="plain">{{ row.dataset }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_enabled')" width="80" align="center">
          <template #default="{ row }">
            <el-switch
              v-model="row.enabled"
              size="small"
              @change="(v: any) => toggleEnabled(row, v)"
            />
          </template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_goldSql')" width="88">
          <template #default="{ row }">
            <el-tag v-if="row.verified" size="small" type="success" effect="plain">
              {{ $t("ai_workflow.eval_verified") }}
            </el-tag>
            <el-tag v-else size="small" type="info" effect="plain">
              {{ $t("ai_workflow.eval_unverified") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="$t('ai_workflow.eval_action')" width="150" fixed="right">
          <template #default="{ row }">
            <el-button icon="Document" link type="primary" size="small" @click="viewSql(row)">
              {{ $t("ai_workflow.eval_goldSql") }}
            </el-button>
            <el-button icon="edit" link type="primary" size="small" @click="openEdit(row)">
              {{ $t("ai_workflow.app_edit") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="ev-total">
        {{ $t("ai_workflow.eval_totalCount", { count: cases.length }) }}
      </div>
    </el-card>

    <el-dialog
      v-model="importVisible"
      :title="$t('ai_workflow.eval_importTitle')"
      width="680px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="$t('ai_workflow.eval_importHint')"
        class="ev-alert"
      />
      <el-form :model="importForm" label-width="90px">
        <el-form-item :label="$t('ai_workflow.eval_datasource')">
          <el-select v-model="importForm.datasource" style="width: 100%">
            <el-option :label="$t('ai_workflow.eval_systemDs')" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_importFormat')">
          <el-radio-group v-model="importForm.format" size="small">
            <el-radio-button label="csv">CSV</el-radio-button>
            <el-radio-button label="json">JSON</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_importContent')">
          <el-input
            v-model="importForm.text"
            type="textarea"
            :rows="10"
            :placeholder="$t('ai_workflow.eval_importPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importVisible = false">{{ $t("ai_workflow.app_cancel") }}</el-button>
        <el-button type="primary" :loading="importing" @click="doImport">
          {{ $t("ai_workflow.eval_importDo") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="verifyVisible"
      :title="$t('ai_workflow.eval_verifyResultTitle')"
      width="720px"
      append-to-body
    >
      <div class="ev-hint">
        {{
          $t("ai_workflow.eval_verifyResult", {
            total: verifyReport.total || 0,
            passed: verifyReport.passed || 0,
            failed: verifyReport.failed || 0,
          })
        }}
      </div>
      <el-table :data="verifyReport.items || []" size="small" border max-height="360" stripe>
        <el-table-column
          prop="question"
          :label="$t('ai_workflow.eval_question')"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column :label="$t('ai_workflow.eval_result')" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.ok ? 'success' : 'danger'" effect="plain">
              {{ row.ok ? $t("ai_workflow.eval_verified") : $t("ai_workflow.eval_unverified") }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rows" :label="$t('ai_workflow.eval_rows')" width="80" />
        <el-table-column
          prop="error"
          :label="$t('ai_workflow.eval_errorDetail')"
          min-width="200"
          show-overflow-tooltip
        />
      </el-table>
    </el-dialog>

    <el-dialog
      v-model="genVisible"
      :title="$t('ai_workflow.eval_genTitle')"
      width="520px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="$t('ai_workflow.eval_genAlert')"
        class="ev-alert"
      />
      <el-form :model="genForm" label-width="80px">
        <el-form-item :label="$t('ai_workflow.eval_datasource')">
          <el-select v-model="genForm.datasource" style="width: 100%">
            <el-option :label="$t('ai_workflow.eval_systemDs')" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_difficulty')">
          <el-select v-model="genForm.difficulty" style="width: 100%">
            <el-option
              v-for="d in DIFFICULTIES"
              :key="d"
              :label="$t('ai_workflow.' + diffKey(d))"
              :value="d"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_form')">
          <el-select v-model="genForm.form" style="width: 100%">
            <el-option
              v-for="f in FORMS"
              :key="f"
              :label="$t('ai_workflow.' + formKey(f))"
              :value="f"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_count')">
          <el-input-number v-model="genForm.n" :min="1" :max="20" />
          <span class="ev-hint">{{ $t("ai_workflow.eval_roundHint") }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genVisible = false">{{ $t("ai_workflow.app_cancel") }}</el-button>
        <el-button type="primary" :loading="genLoading" @click="doGenerate">
          {{ $t("ai_workflow.eval_startGenerate") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="sqlVisible"
      :title="$t('ai_workflow.eval_goldSql')"
      width="600px"
      append-to-body
    >
      <div class="ev-q">{{ current?.question }}</div>
      <el-input v-model="currentSql" type="textarea" :rows="9" readonly />
    </el-dialog>

    <el-dialog
      v-model="editVisible"
      :title="editing ? $t('ai_workflow.eval_editTitle') : $t('ai_workflow.eval_addTitle')"
      width="600px"
      append-to-body
    >
      <el-form :model="editForm" label-width="80px">
        <el-form-item :label="$t('ai_workflow.eval_question')" required>
          <el-input
            v-model="editForm.question"
            type="textarea"
            :rows="2"
            :placeholder="$t('ai_workflow.eval_questionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_goldSql')" required>
          <el-input
            v-model="editForm.gold_sql"
            type="textarea"
            :rows="6"
            placeholder="SELECT ..."
          />
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_datasource')">
          <el-select v-model="editForm.datasource" style="width: 100%">
            <el-option :label="$t('ai_workflow.eval_systemDs')" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_difficulty')">
          <el-select v-model="editForm.difficulty" style="width: 100%">
            <el-option
              v-for="d in DIFFICULTIES"
              :key="d"
              :label="$t('ai_workflow.' + diffKey(d))"
              :value="d"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_form')">
          <el-select v-model="editForm.form" style="width: 100%">
            <el-option
              v-for="f in FORMS"
              :key="f"
              :label="$t('ai_workflow.' + formKey(f))"
              :value="f"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="$t('ai_workflow.eval_scenario')">
          <el-input
            v-model="editForm.scenario"
            :placeholder="$t('ai_workflow.eval_scenarioPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{ $t("ai_workflow.app_cancel") }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveCase">
          {{ $t("ai_workflow.app_save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  deleteEvalCases,
  generateEvalRound,
  getEvalCases,
  getQueryDatasources,
  importEvalCases,
  upsertEvalCase,
  verifyEvalCases,
} from "@/api/module_ai/query";
import { DIFFICULTIES, FORMS, difficultyTag, diffKey, formKey, type EvalCase } from "../types";

defineOptions({ name: "AiEvalCases" });

const { t } = useI18n();

const cases = ref<EvalCase[]>([]);
const datasources = ref<any[]>([]);
const loading = ref(false);
const selection = ref<EvalCase[]>([]);
const filters = ref<any>({ datasource: "", difficulty: "", form: "", dataset: "", enabled: "" });

const genVisible = ref(false);
const genLoading = ref(false);
const genForm = ref({
  datasource: "system",
  difficulty: DIFFICULTIES[0],
  form: FORMS[0],
  n: 5,
});

const sqlVisible = ref(false);
const current = ref<EvalCase | null>(null);
const currentSql = ref("");

const importVisible = ref(false);
const importing = ref(false);
const importForm = ref({ datasource: "system", format: "csv" as "csv" | "json", text: "" });

const verifying = ref(false);
const verifyVisible = ref(false);
const verifyReport = ref<any>({ total: 0, passed: 0, failed: 0, items: [] });

/** 批量导入：CSV（含表头 question,gold_sql,…）或 JSON 数组。 */
async function doImport() {
  const raw = importForm.value.text.trim();
  if (!raw) {
    ElMessage.warning(t("ai_workflow.eval_importEmpty"));
    return;
  }
  importing.value = true;
  try {
    const payload: any = { datasource: importForm.value.datasource };
    if (importForm.value.format === "json") {
      let items: any;
      try {
        items = JSON.parse(raw);
      } catch {
        ElMessage.error(t("ai_workflow.eval_importJsonInvalid"));
        return;
      }
      payload.items = Array.isArray(items) ? items : items.items || [];
      if (!payload.items.length) {
        ElMessage.warning(t("ai_workflow.eval_importEmpty"));
        return;
      }
    } else {
      payload.csv = raw;
    }
    const r = await importEvalCases(payload);
    const d = r.data?.data || {};
    ElMessage.success(
      t("ai_workflow.eval_importDone", { saved: d.saved || 0, skipped: d.skipped || 0 })
    );
    importVisible.value = false;
    importForm.value.text = "";
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_importFail"));
  } finally {
    importing.value = false;
  }
}

/** 校验金标：选中优先，否则按当前筛选条件批量校验。 */
async function doVerify() {
  verifying.value = true;
  try {
    const payload: any = {};
    if (selection.value.length) payload.ids = selection.value.map((x) => x.id);
    if (filters.value.datasource) payload.datasource = filters.value.datasource;
    if (filters.value.dataset) payload.dataset = filters.value.dataset;
    const r = await verifyEvalCases(payload);
    verifyReport.value = r.data?.data || { total: 0, passed: 0, failed: 0, items: [] };
    verifyVisible.value = true;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_verifyFail"));
  } finally {
    verifying.value = false;
  }
}

const editVisible = ref(false);
const saving = ref(false);
const editing = ref<number | null>(null);
const editForm = ref({
  question: "",
  gold_sql: "",
  datasource: "system",
  difficulty: DIFFICULTIES[0],
  form: FORMS[0],
  scenario: "",
});

async function load() {
  loading.value = true;
  try {
    const params: any = {};
    if (filters.value.datasource) params.datasource = filters.value.datasource;
    if (filters.value.difficulty) params.difficulty = filters.value.difficulty;
    if (filters.value.form) params.form = filters.value.form;
    if (filters.value.dataset) params.dataset = filters.value.dataset;
    // 启用状态：'' = 全部；'true'/'false' 转成布尔（后端按 enabled 过滤）
    if (filters.value.enabled !== "" && filters.value.enabled !== undefined) {
      params.enabled = filters.value.enabled === "true";
    }
    const r = await getEvalCases(params);
    cases.value = r.data?.data || [];
  } catch {
    cases.value = [];
  } finally {
    loading.value = false;
  }
}

/** 行内启用/停用：评测只跑 enabled 的题，必须能在列表里直接切。 */
async function toggleEnabled(row: any, val: boolean) {
  try {
    await upsertEvalCase({ ...row, enabled: val });
    ElMessage.success(t("ai_workflow.eval_saved"));
  } catch (e: any) {
    row.enabled = !val; // 失败回滚开关状态
    ElMessage.error(e?.msg || t("ai_workflow.eval_saveFail"));
  }
}

async function loadDatasources() {
  try {
    const r = await getQueryDatasources();
    datasources.value = r.data?.data || [];
  } catch {
    datasources.value = [];
  }
}

async function doGenerate() {
  genLoading.value = true;
  try {
    const r = await generateEvalRound({ ...genForm.value });
    const d = r.data?.data || {};
    const saved = d.saved || 0;
    const rejected = d.rejected || 0;
    if (saved > 0) ElMessage.success(t("ai_workflow.eval_genSuccess", { saved, rejected }));
    else ElMessage.warning(t("ai_workflow.eval_genNoNew", { rejected }));
    genVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_genFail"));
  } finally {
    genLoading.value = false;
  }
}

function viewSql(row: any) {
  current.value = row as EvalCase;
  currentSql.value = row.gold_sql || "";
  sqlVisible.value = true;
}

function openCreate() {
  editing.value = null;
  editForm.value = {
    question: "",
    gold_sql: "",
    datasource: "system",
    difficulty: DIFFICULTIES[0],
    form: FORMS[0],
    scenario: "",
  };
  editVisible.value = true;
}

function openEdit(row: any) {
  editing.value = row.id;
  editForm.value = {
    question: row.question || "",
    gold_sql: row.gold_sql || "",
    datasource: row.datasource || "system",
    difficulty: row.difficulty || DIFFICULTIES[0],
    form: row.form || FORMS[0],
    scenario: row.scenario || "",
  };
  editVisible.value = true;
}

async function saveCase() {
  if (!editForm.value.question.trim()) {
    ElMessage.warning(t("ai_workflow.eval_fillQuestion"));
    return;
  }
  if (!editForm.value.gold_sql.trim()) {
    ElMessage.warning(t("ai_workflow.eval_fillGoldSql"));
    return;
  }
  saving.value = true;
  try {
    await upsertEvalCase({ ...editForm.value, id: editing.value ?? undefined });
    ElMessage.success(editing.value ? t("ai_workflow.eval_saved") : t("ai_workflow.eval_added"));
    editVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_saveFail"));
  } finally {
    saving.value = false;
  }
}

async function removeSelected() {
  const n = selection.value.length;
  if (!n) return;
  await ElMessageBox.confirm(
    t("ai_workflow.eval_deleteConfirmMsg", { count: n }),
    t("ai_workflow.eval_deleteConfirmTitle"),
    {
      type: "warning",
      confirmButtonText: t("ai_workflow.app_delete"),
      cancelButtonText: t("ai_workflow.app_cancel"),
    }
  );
  try {
    const r = await deleteEvalCases(selection.value.map((x) => x.id));
    ElMessage.success(t("ai_workflow.eval_deletedMsg", { count: r.data?.data?.deleted ?? n }));
    selection.value = [];
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.eval_deleteFail"));
  }
}

onMounted(async () => {
  await Promise.all([load(), loadDatasources()]);
});
</script>

<style scoped>
.ev-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.ev-head__ops {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ev-total {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ev-q {
  margin-bottom: 8px;
  font-weight: 600;
}
.ev-hint {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ev-alert {
  margin-bottom: 12px;
}
</style>
