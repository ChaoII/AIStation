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
            <el-button size="small" @click="load">{{ $t("ai_workflow.eval_refresh") }}</el-button>
            <el-button size="small" type="primary" plain @click="openCreate">
              {{ $t("ai_workflow.eval_addCase") }}
            </el-button>
            <el-button size="small" type="primary" @click="genVisible = true">
              {{ $t("ai_workflow.eval_genCase") }}
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
  upsertEvalCase,
} from "@/api/module_ai/query";
import { DIFFICULTIES, FORMS, difficultyTag, diffKey, formKey, type EvalCase } from "../types";

defineOptions({ name: "AiEvalCases" });

const { t } = useI18n();

const cases = ref<EvalCase[]>([]);
const datasources = ref<any[]>([]);
const loading = ref(false);
const selection = ref<EvalCase[]>([]);
const filters = ref<any>({ datasource: "", difficulty: "", form: "" });

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
    const r = await getEvalCases(params);
    cases.value = r.data?.data || [];
  } catch {
    cases.value = [];
  } finally {
    loading.value = false;
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
