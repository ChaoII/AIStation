<template>
  <div class="ev-cases">
    <el-card shadow="never">
      <template #header>
        <div class="ev-head">
          <span>测试集</span>
          <div class="ev-head__ops">
            <el-select
              v-model="filters.datasource"
              size="small"
              clearable
              placeholder="数据源"
              style="width: 170px"
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
            <el-select
              v-model="filters.difficulty"
              size="small"
              clearable
              placeholder="难度"
              style="width: 110px"
              @change="load"
            >
              <el-option v-for="d in DIFFICULTIES" :key="d" :label="d" :value="d" />
            </el-select>
            <el-select
              v-model="filters.form"
              size="small"
              clearable
              placeholder="形式"
              style="width: 140px"
              @change="load"
            >
              <el-option v-for="f in FORMS" :key="f" :label="f" :value="f" />
            </el-select>
            <el-button size="small" @click="load">刷新</el-button>
            <el-button size="small" type="primary" plain @click="openCreate">新增题目</el-button>
            <el-button size="small" type="primary" @click="genVisible = true">生成题目</el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="!selection.length"
              @click="removeSelected"
            >
              批量删除
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
        <el-table-column prop="question" label="问题" min-width="280" show-overflow-tooltip />
        <el-table-column prop="datasource" label="数据源" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.datasource }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="difficulty" label="难度" width="88">
          <template #default="{ row }">
            <el-tag size="small" :type="difficultyTag(row.difficulty)">
              {{ row.difficulty }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="form" label="形式" width="120" />
        <el-table-column prop="scenario" label="场景" width="150" show-overflow-tooltip />
        <el-table-column label="金标" width="88">
          <template #default="{ row }">
            <el-tag v-if="row.verified" size="small" type="success" effect="plain">已校验</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">未校验</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button icon="Document" link type="primary" size="small" @click="viewSql(row)">
              金标 SQL
            </el-button>
            <el-button icon="edit" link type="primary" size="small" @click="openEdit(row)">
              编辑
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="ev-total">共 {{ cases.length }} 题</div>
    </el-card>

    <el-dialog v-model="genVisible" title="生成测试题" width="520px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="由大模型按 schema / 指标 / 术语出题，金标 SQL 会真实执行校验，执行失败或空结果的题不入库。"
        class="ev-alert"
      />
      <el-form :model="genForm" label-width="80px">
        <el-form-item label="数据源">
          <el-select v-model="genForm.datasource" style="width: 100%">
            <el-option label="系统库（本体支撑表）" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="genForm.difficulty" style="width: 100%">
            <el-option v-for="d in DIFFICULTIES" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="形式">
          <el-select v-model="genForm.form" style="width: 100%">
            <el-option v-for="f in FORMS" :key="f" :label="f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="genForm.n" :min="1" :max="20" />
          <span class="ev-hint">一轮 1~20 题，生成期间请勿关闭</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genVisible = false">取消</el-button>
        <el-button type="primary" :loading="genLoading" @click="doGenerate">开始生成</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sqlVisible" title="金标 SQL" width="600px" append-to-body>
      <div class="ev-q">{{ current?.question }}</div>
      <el-input v-model="currentSql" type="textarea" :rows="9" readonly />
    </el-dialog>

    <el-dialog
      v-model="editVisible"
      :title="editing ? '编辑测试题' : '新增测试题'"
      width="600px"
      append-to-body
    >
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="问题" required>
          <el-input
            v-model="editForm.question"
            type="textarea"
            :rows="2"
            placeholder="自然语言问题"
          />
        </el-form-item>
        <el-form-item label="金标 SQL" required>
          <el-input
            v-model="editForm.gold_sql"
            type="textarea"
            :rows="6"
            placeholder="SELECT ..."
          />
        </el-form-item>
        <el-form-item label="数据源">
          <el-select v-model="editForm.datasource" style="width: 100%">
            <el-option label="系统库（本体支撑表）" value="system" />
            <el-option
              v-for="d in datasources"
              :key="d.code || d.id"
              :label="d.name"
              :value="d.code || `ds:${d.id}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="editForm.difficulty" style="width: 100%">
            <el-option v-for="d in DIFFICULTIES" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="形式">
          <el-select v-model="editForm.form" style="width: 100%">
            <el-option v-for="f in FORMS" :key="f" :label="f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="场景">
          <el-input v-model="editForm.scenario" placeholder="业务场景（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveCase">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  deleteEvalCases,
  generateEvalRound,
  getEvalCases,
  getQueryDatasources,
  upsertEvalCase,
} from "@/api/module_ai/query";
import { DIFFICULTIES, FORMS, difficultyTag, type EvalCase } from "../types";

defineOptions({ name: "AiEvalCases" });

const cases = ref<EvalCase[]>([]);
const datasources = ref<any[]>([]);
const loading = ref(false);
const selection = ref<EvalCase[]>([]);
const filters = ref<any>({ datasource: "", difficulty: "", form: "" });

const genVisible = ref(false);
const genLoading = ref(false);
const genForm = ref({ datasource: "system", difficulty: "简单", form: "单维统计", n: 5 });

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
  difficulty: "简单",
  form: "单维统计",
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
    if (saved > 0) ElMessage.success(`生成完成：入库 ${saved} 题，拒绝 ${rejected} 题`);
    else ElMessage.warning(`本轮未入库新题（拒绝 ${rejected} 题），可调整维度后重试`);
    genVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "生成失败");
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
    difficulty: "简单",
    form: "单维统计",
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
    difficulty: row.difficulty || "简单",
    form: row.form || "单维统计",
    scenario: row.scenario || "",
  };
  editVisible.value = true;
}

async function saveCase() {
  if (!editForm.value.question.trim()) {
    ElMessage.warning("请填写问题");
    return;
  }
  if (!editForm.value.gold_sql.trim()) {
    ElMessage.warning("请填写金标 SQL");
    return;
  }
  saving.value = true;
  try {
    await upsertEvalCase({ ...editForm.value, id: editing.value ?? undefined });
    ElMessage.success(editing.value ? "已保存" : "已新增");
    editVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeSelected() {
  const n = selection.value.length;
  if (!n) return;
  await ElMessageBox.confirm(`将删除 ${n} 道测试题（含其金标 SQL），且不可恢复。`, "删除测试题", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  try {
    const r = await deleteEvalCases(selection.value.map((x) => x.id));
    ElMessage.success(`已删除 ${r.data?.data?.deleted ?? n} 题`);
    selection.value = [];
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
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
