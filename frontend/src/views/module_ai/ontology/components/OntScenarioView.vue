<!--
  场景（P5）——沙箱式"假设分析"

  对齐官方 ontology/overview-ontology-scenario：
  · 场景 = 在真实数据之上叠加编辑的沙箱，**不影响主本体**
  · 读场景 = 基线数据 + 场景差异
  · 可多场景并排对比；合并是**单事务**（失败全回滚）
  · 官方限额：30,000 处编辑 / 50 个动作 / 默认 31 天寿命
-->
<template>
  <div class="ont-scn">
    <el-card shadow="never">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.scenario") }}</span>
        <el-tag size="small" effect="plain">
          {{ i18nT("ai_ontology.countUnit", { count: rows.length }) }}
        </el-tag>
        <el-button class="ont-sec__op" type="primary" size="small" :icon="Plus" @click="openForm()">
          {{ i18nT("ai_ontology.newScenario") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :disabled="checked.length < 2"
          @click="doCompare"
        >
          {{ i18nT("ai_ontology.compareSelectedCount", { count: checked.length }) }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :icon="Delete"
          :loading="expiring"
          @click="doExpire"
        >
          {{ i18nT("ai_ontology.cleanExpiredScenarios") }}
        </el-button>
        <el-button size="small" :icon="Refresh" @click="load">
          {{ i18nT("ai_ontology.refresh") }}
        </el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.scenarioInfoAlert')"
      />

      <el-table
        v-loading="loading"
        :data="rows"
        size="small"
        border
        stripe
        max-height="520"
        @selection-change="(v: any[]) => (checked = v.map((x) => x.code))"
      >
        <template #empty>
          <el-empty :image-size="60" :description="i18nT('ai_ontology.noScenariosYet')" />
        </template>
        <el-table-column type="selection" width="44" />
        <el-table-column
          :label="i18nT('ai_ontology.scenario')"
          min-width="220"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.status')" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.edits')" width="110" align="center">
          <template #default="{ row }">
            <span class="ont-mono">{{ row.edit_count }} / {{ row.edit_limit }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.involvedObjects')" width="100" align="center">
          <template #default="{ row }">{{ row.object_count }}</template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.actions')" width="90" align="center">
          <template #default="{ row }">
            <span class="ont-mono">
              {{ (row.action_codes || []).length }} / {{ row.action_limit }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          prop="created_by"
          :label="i18nT('ai_ontology.createdBy')"
          width="110"
          show-overflow-tooltip
        />
        <el-table-column
          prop="created_time"
          :label="i18nT('ai_ontology.createdTime')"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.expiryTime')" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'ont-scn__expiring': row.is_expired }">
              {{ row.expires_at || "—" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          :label="i18nT('ai_ontology.operations')"
          width="250"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button icon="View" link type="primary" size="small" @click="openDetail(row)">
              {{ i18nT("ai_ontology.details") }}
            </el-button>
            <el-button
              v-if="row.status === 'active'"
              v-hasPerm="'module_ai:ontology:edit'"
              icon="Connection"
              link
              type="success"
              size="small"
              @click="doApply(row)"
            >
              {{ i18nT("ai_ontology.merge") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              icon="CopyDocument"
              link
              type="primary"
              size="small"
              @click="doDuplicate(row)"
            >
              {{ i18nT("ai_ontology.copy") }}
            </el-button>
            <el-button
              v-if="row.status === 'active'"
              v-hasPerm="'module_ai:ontology:edit'"
              icon="Delete"
              link
              type="warning"
              size="small"
              @click="doDiscard(row)"
            >
              {{ i18nT("ai_ontology.discard") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              icon="delete"
              link
              type="danger"
              size="small"
              @click="doRemove(row)"
            >
              {{ i18nT("ai_ontology.delete2") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑 -->
    <el-dialog
      v-model="formVisible"
      :title="i18nT('ai_ontology.scenario')"
      width="600px"
      append-to-body
    >
      <el-form :model="form" label-width="120px">
        <el-form-item :label="i18nT('ai_ontology.scenarioName')" required>
          <el-input
            v-model="form.name"
            :placeholder="i18nT('ai_ontology.scenarioNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.note')">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.mergeAction')">
          <el-select v-model="form.merge_action_code" filterable clearable style="width: 100%">
            <el-option
              v-for="a in actions"
              :key="a.code"
              :label="`${a.name}（${a.code}）`"
              :value="a.code"
            />
          </el-select>
          <div class="ont-hint">
            {{ i18nT("ai_ontology.mergeActionHint") }}
          </div>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.editableScope')">
          <el-select
            v-model="form.scopeTypes"
            multiple
            filterable
            clearable
            style="width: 100%"
            :placeholder="i18nT('ai_ontology.leaveEmptyNoObjectTypeLimit')"
          >
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
          <div class="ont-hint">
            {{
              i18nT(
                "ai_ontology.officialDefineTheObjectTypeScopeOfScenarioEditsWhenCreatingAMergeAction"
              )
            }}
          </div>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.ttlDays')">
          <el-input-number v-model="form.ttl_days" :min="1" :max="365" />
          <span class="ont-hint">{{ i18nT("ai_ontology.ttlDaysHint") }}</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="saving"
          @click="doSave"
        >
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情：差异预览 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.name || i18nT('ai_ontology.scenarioDetail')"
      size="62%"
    >
      <template v-if="detail">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item :label="i18nT('ai_ontology.code')">
            <span class="ont-mono">{{ detail.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.status')">
            <el-tag size="small" :type="statusTagType(detail.status)" effect="plain">
              {{ detail.status_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.edits')">
            {{ detail.edit_count }} / {{ detail.edit_limit }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.actions')">
            {{ (detail.action_codes || []).length }} / {{ detail.action_limit }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.create')">
            {{ detail.created_by }} · {{ detail.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.expired')">
            {{ detail.expires_at || "—" }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.mergeAction')">
            <span class="ont-mono">{{ detail.merge_action_code || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.editableScope')">
            <template v-if="detail.scope?.object_types?.length">
              <el-tag
                v-for="t in detail.scope.object_types"
                :key="t"
                size="small"
                effect="plain"
                class="ont-tag-gap"
              >
                {{ objectLabel(t) }}
              </el-tag>
            </template>
            <span v-else class="ont-none">{{ i18nT("ai_ontology.unlimited") }}</span>
          </el-descriptions-item>
          <el-descriptions-item
            v-if="detail.applied_at"
            :label="i18nT('ai_ontology.mergedAt')"
            :span="2"
          >
            {{ detail.applied_by }} · {{ detail.applied_at }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.whatItBecomesAfterMerge") }}</span>
          <el-tag size="small" effect="plain">
            {{ i18nT("ai_ontology.objectCount", { count: diff?.objects_changed || 0 }) }}
          </el-tag>
        </div>
        <el-table :data="diff?.changes || []" size="small" border max-height="360" stripe>
          <template #empty>
            <el-empty
              :image-size="50"
              :description="i18nT('ai_ontology.noEditsInThisScenarioYet')"
            />
          </template>
          <el-table-column
            :label="i18nT('ai_ontology.object')"
            min-width="180"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="ont-mono">{{ objectLabel(row.object_code) }}#{{ row.object_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="kind_label" :label="i18nT('ai_ontology.changes')" width="130" />
          <el-table-column :label="i18nT('ai_ontology.fieldChange')" min-width="320">
            <template #default="{ row }">
              <div class="ont-scn__diff">
                <span v-for="(v, k) in row.changed" :key="k" class="ont-mono">
                  {{ k }}: {{ fmt(v.before) }} → {{ fmt(v.after) }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            :label="i18nT('ai_ontology.sourceAction')"
            width="150"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="ont-mono">{{ (row.actions || []).join("、") || "—" }}</span>
            </template>
          </el-table-column>
        </el-table>

        <el-alert
          v-if="(diff?.model_results || []).length"
          type="warning"
          :closable="false"
          class="ont-note"
          :title="
            i18nT('ai_ontology.modelResultsNotice', {
              count: diff.model_results.length,
              note: diff.model_result_note,
            })
          "
        />

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.editDetails") }}</span>
          <el-tag size="small" effect="plain">{{ detail.edits?.length || 0 }}</el-tag>
        </div>
        <el-table :data="detail.edits || []" size="small" border max-height="300" stripe>
          <el-table-column
            :label="i18nT('ai_ontology.object')"
            min-width="160"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="ont-mono">{{ objectLabel(row.object_code) }}#{{ row.object_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="kind_label" :label="i18nT('ai_ontology.kind')" width="130" />
          <el-table-column
            prop="action_code"
            :label="i18nT('ai_ontology.action')"
            width="140"
            show-overflow-tooltip
          />
          <el-table-column prop="created_time" :label="i18nT('ai_ontology.time')" width="150" />
        </el-table>

        <div class="ont-scn__actions">
          <el-button
            v-if="detail.status === 'active'"
            v-hasPerm="'module_ai:ontology:edit'"
            type="success"
            @click="doApply(detail)"
          >
            {{ i18nT("ai_ontology.mergeToPrimaryOntology") }}
          </el-button>
          <el-button
            v-if="detail.status === 'active'"
            v-hasPerm="'module_ai:ontology:edit'"
            @click="doDiscard(detail)"
          >
            {{ i18nT("ai_ontology.discard") }}
          </el-button>
          <el-button v-hasPerm="'module_ai:ontology:edit'" @click="doDuplicate(detail)">
            {{ i18nT("ai_ontology.copy") }}
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 多场景对比 -->
    <el-dialog
      v-model="compareVisible"
      :title="i18nT('ai_ontology.multiScenarioCompare')"
      width="900px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.compareAlert')"
      />
      <el-table :data="compare?.rows || []" size="small" border max-height="420" stripe>
        <el-table-column :label="i18nT('ai_ontology.object')" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="ont-mono">{{ objectLabel(row.object_code) }}#{{ row.object_key }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="s in compare?.scenarios || []"
          :key="s.code"
          :label="s.name"
          min-width="200"
        >
          <template #default="{ row }">
            <div v-if="row.scenarios[s.code]" class="ont-scn__diff">
              <span v-for="(v, k) in row.scenarios[s.code].changed" :key="k" class="ont-mono">
                {{ k }}: {{ fmt(v.before) }} → {{ fmt(v.after) }}
              </span>
            </div>
            <span v-else class="ont-none">{{ i18nT("ai_ontology.unchanged") }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Delete, Plus, Refresh } from "@element-plus/icons-vue";
import {
  applyOntScenario,
  compareOntScenarios,
  discardOntScenario,
  duplicateOntScenario,
  expireOntScenarios,
  getOntScenario,
  getOntScenarios,
  removeOntScenario,
  saveOntScenario,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const emit = defineEmits<{ (e: "refresh"): void }>();

const { objects, actions, objectLabel } = useOntologyData();

function statusTagType(s: string) {
  return ({ active: "primary", applied: "success", discarded: "info", expired: "warning" }[s] ||
    "info") as any;
}
function fmt(v: any) {
  if (v === null || v === undefined) return i18nT("ai_ontology.empty");
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return s.length > 40 ? s.slice(0, 37) + "…" : s;
}

const loading = ref(false);
const saving = ref(false);
const rows = ref<any[]>([]);
const checked = ref<string[]>([]);

async function load() {
  loading.value = true;
  try {
    const r = await getOntScenarios({ limit: 300 });
    rows.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.loadScenarioFailed"));
  } finally {
    loading.value = false;
  }
}

/* ---------------- 新建 / 编辑 ---------------- */
const formVisible = ref(false);
const form = reactive<any>({
  code: "",
  name: "",
  description: "",
  merge_action_code: "",
  scopeTypes: [] as string[],
  ttl_days: 31,
});

function openForm() {
  Object.assign(form, {
    code: "",
    name: "",
    description: "",
    merge_action_code: "",
    scopeTypes: [],
    ttl_days: 31,
  });
  formVisible.value = true;
}

async function doSave() {
  if (!form.name?.trim()) return ElMessage.warning(i18nT("ai_ontology.pleaseEnterScenarioName"));
  saving.value = true;
  try {
    const r = await saveOntScenario({
      code: form.code,
      name: form.name,
      description: form.description,
      merge_action_code: form.merge_action_code,
      scope: { object_types: form.scopeTypes },
      ttl_days: form.ttl_days,
    });
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.saved"));
    formVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    saving.value = false;
  }
}

/* ---------------- 详情 ---------------- */
const detailVisible = ref(false);
const detail = ref<any>(null);
const diff = ref<any>(null);

async function openDetail(row: any) {
  const r = await getOntScenario(row.code);
  detail.value = r.data?.data || null;
  diff.value = detail.value?.diff || null;
  detailVisible.value = true;
}

/* ---------------- 合并 / 丢弃 / 复制 / 删除 ---------------- */
async function doApply(row: any) {
  const n = row.object_count ?? (await getOntScenario(row.code)).data?.data?.diff?.objects_changed;
  await ElMessageBox.confirm(
    i18nT("ai_ontology.mergeScenarioConfirm", { name: row.name, count: n ?? "?" }),
    i18nT("ai_ontology.mergeScenario"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.merge"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  try {
    const r = await applyOntScenario(row.code);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.merged"));
    detailVisible.value = false;
    await load();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.mergeFailed"));
  }
}

async function doDiscard(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.discardScenarioConfirm", { name: row.name, count: row.edit_count }),
    i18nT("ai_ontology.discardScenario"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.discard"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  try {
    const r = await discardOntScenario(row.code);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.discarded"));
    detailVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.operationFailed"));
  }
}

async function doDuplicate(row: any) {
  try {
    const r = await duplicateOntScenario(row.code);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.copied"));
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.copyFailed"));
  }
}

async function doRemove(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deleteScenarioConfirm", { name: row.name, count: row.edit_count }),
    i18nT("ai_ontology.deleteScenario"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  try {
    const r = await removeOntScenario(row.code);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.deleted"));
    detailVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.deleteFailed"));
  }
}

/* ---------------- 对比 ---------------- */
const compareVisible = ref(false);
const compare = ref<any>(null);

async function doCompare() {
  if (checked.value.length < 2)
    return ElMessage.warning(i18nT("ai_ontology.selectAtLeastTwoScenarios"));
  try {
    const r = await compareOntScenarios(checked.value);
    compare.value = r.data?.data || null;
    compareVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.compareFailed"));
  }
}

/* ---------------- 过期清理（TTL） ---------------- */
const expiring = ref(false);
async function doExpire() {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.expireScenariosConfirm"),
    i18nT("ai_ontology.cleanExpiredScenarios"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.cleanup"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  expiring.value = true;
  try {
    const r = await expireOntScenarios();
    const n = r.data?.data?.expired ?? 0;
    if (n > 0)
      ElMessage.success(r.data?.msg || i18nT("ai_ontology.expiredScenarios", { count: n }));
    else ElMessage.info(i18nT("ai_ontology.noExpiredScenariosNothingToClean"));
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.cleanupFailed"));
  } finally {
    expiring.value = false;
  }
}

onMounted(load);
</script>

<style lang="scss" scoped>
.ont-scn__expiring {
  color: var(--el-color-danger);
}

.ont-scn__diff {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ont-scn__actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.ont-scn .ont-sec__head .ont-hint {
  margin-left: 8px;
}
</style>
