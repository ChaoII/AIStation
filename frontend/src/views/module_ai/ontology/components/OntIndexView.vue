<!--
  索引（对齐官方 object-indexing）

  · 索引 = 让数据可被快速检索；由流水线（batch / streaming / direct）编排
  · 状态：未开始 / 构建中 / 就绪（绿勾）/ 失败 / 已过期
  · 失败重试：瞬时错误约 5 分钟后自动重试；终态错误只等新数据
  · 我们的索引是**真的**——构建会在对象类型支撑表上执行 CREATE INDEX
-->
<template>
  <div class="ont-ix">
    <el-card shadow="never">
      <div class="ont-sec__head">
        <span class="ont-sec__title">{{ i18nT("ai_ontology.index") }}</span>
        <el-tag size="small" effect="plain">
          {{ i18nT("ai_ontology.countUnit", { count: summary?.total || 0 }) }}
        </el-tag>
        <el-button class="ont-sec__op" size="small" type="primary" :icon="Plus" @click="openForm()">
          {{ i18nT("ai_ontology.newIndex") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          :icon="MagicStick"
          @click="openSuggest"
        >
          {{ i18nT("ai_ontology.indexSuggestions") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          size="small"
          :loading="busy"
          @click="doBuildAll"
        >
          {{ i18nT("ai_ontology.buildAllPending") }}
        </el-button>
        <el-button v-hasPerm="'module_ai:ontology:manage'" size="small" @click="doRetry">
          {{ i18nT("ai_ontology.retryExpired") }}
        </el-button>
        <el-button size="small" :icon="Refresh" @click="load">
          {{ i18nT("ai_ontology.refresh") }}
        </el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.indexBuildAlert')"
      />

      <el-row :gutter="10" class="ont-ix__stats">
        <el-col v-for="(v, k) in summary?.by_status || {}" :key="k" :xs="12" :sm="8" :md="4">
          <el-card shadow="never" class="ont-ix__stat">
            <div class="ont-ix__statv">{{ v }}</div>
            <div class="ont-ix__statl">{{ statusLabel(String(k)) }}</div>
          </el-card>
        </el-col>
        <el-col :xs="12" :sm="8" :md="4">
          <el-card shadow="never" class="ont-ix__stat">
            <div class="ont-ix__statv">{{ summary?.total_size_human || "0 B" }}</div>
            <div class="ont-ix__statl">{{ i18nT("ai_ontology.size") }}</div>
          </el-card>
        </el-col>
      </el-row>

      <el-tabs v-model="tab">
        <el-tab-pane :label="i18nT('ai_ontology.indexDetails')" name="list">
          <el-table v-loading="loading" :data="rows" size="small" border max-height="520" stripe>
            <template #empty>
              <el-empty :image-size="60" :description="i18nT('ai_ontology.noIndexesYet')" />
            </template>
            <el-table-column
              :label="i18nT('ai_ontology.objectType')"
              min-width="150"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ objectLabel(row.object_code) }}</template>
            </el-table-column>
            <el-table-column
              prop="index_kind_label"
              :label="i18nT('ai_ontology.kind')"
              width="100"
            />
            <el-table-column
              :label="i18nT('ai_ontology.field')"
              min-width="130"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span class="ont-mono">
                  {{ row.prop_code || i18nT("ai_ontology.primaryKeyParen") }}
                </span>
              </template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.status')" width="100">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="statusTag(row.status)">
                  {{ row.status_label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="pipeline_label"
              :label="i18nT('ai_ontology.pipeline')"
              width="110"
            />
            <el-table-column :label="i18nT('ai_ontology.rowsAndSize')" width="140" align="right">
              <template #default="{ row }">
                <span class="ont-mono">{{ row.row_count }} / {{ row.size_human }}</span>
              </template>
            </el-table-column>
            <el-table-column
              prop="build_count"
              :label="i18nT('ai_ontology.buildCount')"
              width="90"
              align="center"
            />
            <el-table-column
              prop="last_built_at"
              :label="i18nT('ai_ontology.lastBuild')"
              width="150"
              show-overflow-tooltip
            />
            <el-table-column
              :label="i18nT('ai_ontology.failureReason')"
              min-width="180"
              show-overflow-tooltip
            >
              <template #default="{ row }">
                <span v-if="row.last_error" class="ont-ix__err">{{ row.last_error }}</span>
                <span v-else class="ont-none">—</span>
                <div v-if="row.auto_retry_at" class="ont-hint">
                  {{ i18nT("ai_ontology.autoRetryAt", { time: row.auto_retry_at }) }}
                </div>
              </template>
            </el-table-column>
            <el-table-column
              :label="i18nT('ai_ontology.operations')"
              width="150"
              align="center"
              fixed="right"
            >
              <template #default="{ row }">
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  icon="Refresh"
                  link
                  type="primary"
                  size="small"
                  :loading="busy"
                  @click="doBuild(row)"
                >
                  {{ i18nT("ai_ontology.build") }}
                </el-button>
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
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
        </el-tab-pane>

        <el-tab-pane :label="i18nT('ai_ontology.byObjectType')" name="objects">
          <el-table :data="summary?.objects || []" size="small" border stripe>
            <template #empty>
              <el-empty :image-size="50" :description="i18nT('ai_ontology.none2')" />
            </template>
            <el-table-column
              prop="object_name"
              :label="i18nT('ai_ontology.objectType')"
              min-width="170"
              show-overflow-tooltip
            />
            <el-table-column :label="i18nT('ai_ontology.readyTotal')" width="120" align="center">
              <template #default="{ row }">{{ row.ready }} / {{ row.total }}</template>
            </el-table-column>
            <el-table-column :label="i18nT('ai_ontology.status')" width="110">
              <template #default="{ row }">
                <el-tag size="small" effect="plain" :type="row.all_ready ? 'success' : 'warning'">
                  {{
                    row.all_ready
                      ? i18nT("ai_ontology.allReady")
                      : i18nT("ai_ontology.partNotReady")
                  }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              prop="rows"
              :label="i18nT('ai_ontology.rows')"
              width="110"
              align="right"
            />
            <el-table-column
              prop="size_human"
              :label="i18nT('ai_ontology.size')"
              width="110"
              align="right"
            />
            <el-table-column :label="i18nT('ai_ontology.operations')" width="180" align="center">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  icon="Refresh"
                  link
                  type="primary"
                  size="small"
                  @click="doBuildObject(row)"
                >
                  {{ i18nT("ai_ontology.buildAll") }}
                </el-button>
                <el-button
                  v-hasPerm="'module_ai:ontology:manage'"
                  icon="Clock"
                  link
                  type="warning"
                  size="small"
                  @click="doStale(row)"
                >
                  {{ i18nT("ai_ontology.markExpired") }}
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 新建索引 -->
    <el-dialog
      v-model="formVisible"
      :title="i18nT('ai_ontology.index')"
      width="600px"
      append-to-body
    >
      <el-form label-width="110px">
        <el-form-item :label="i18nT('ai_ontology.objectType')" required>
          <el-select v-model="form.object_code" filterable style="width: 100%">
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.indexKind')">
          <el-select v-model="form.index_kind" style="width: 100%">
            <el-option
              v-for="k in summary?.kind_meta || []"
              :key="k.value"
              :label="k.label"
              :value="k.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.index_kind !== 'primary'" :label="i18nT('ai_ontology.field')">
          <el-select v-model="form.prop_code" filterable clearable style="width: 100%">
            <el-option
              v-for="p in formProps"
              :key="p.code"
              :label="`${p.name}（${p.code}）`"
              :value="p.code"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.pipeline')">
          <el-select v-model="form.pipeline_kind" style="width: 100%">
            <el-option
              v-for="p in summary?.pipeline_meta || []"
              :key="p.value"
              :label="p.label"
              :value="p.value"
            />
          </el-select>
          <div class="ont-hint">{{ i18nT("ai_ontology.pipelineHint") }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doSave"
        >
          {{ i18nT("ai_ontology.saveAndBuild") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 索引建议 -->
    <el-dialog
      v-model="sugVisible"
      :title="i18nT('ai_ontology.indexSuggestions')"
      width="600px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.indexSuggestAlert')"
      />
      <el-table :data="suggestions" size="small" border max-height="360" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noSuggestions')" />
        </template>
        <el-table-column :label="i18nT('ai_ontology.field')" min-width="140">
          <template #default="{ row }">
            <span class="ont-mono">{{ row.prop_code }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="reason"
          :label="i18nT('ai_ontology.reason')"
          min-width="240"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.priority')" width="90" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              effect="plain"
              :type="row.priority === 'high' ? 'danger' : 'warning'"
            >
              {{
                row.priority === "high"
                  ? i18nT("ai_ontology.highPriority")
                  : i18nT("ai_ontology.mediumPriority")
              }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="sugVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          :loading="busy"
          @click="doApplySuggestions(false)"
        >
          {{ i18nT("ai_ontology.createAll") }}
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doApplySuggestions(true)"
        >
          {{ i18nT("ai_ontology.createHighPriorityOnly") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { MagicStick, Plus, Refresh } from "@element-plus/icons-vue";
import {
  applyOntIndexSuggestions,
  buildAllOntIndexes,
  buildOntIndex,
  getOntIndexes,
  getOntIndexSummary,
  getOntProperties,
  markOntIndexStale,
  removeOntIndex,
  retryOntIndexes,
  saveOntIndex,
  suggestOntIndexes,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const { objects, objectLabel } = useOntologyData();

const loading = ref(false);
const busy = ref(false);
const rows = ref<any[]>([]);
const summary = ref<any>(null);
const tab = ref("list");

const STATUS_LABEL: Record<string, string> = {
  not_started: i18nT("ai_ontology.notStarted"),
  building: i18nT("ai_ontology.building"),
  ready: i18nT("ai_ontology.ready"),
  failed: i18nT("ai_ontology.failed"),
  stale: i18nT("ai_ontology.expired2"),
};
function statusLabel(s: string) {
  return STATUS_LABEL[s] || s;
}
function statusTag(s: string) {
  return ({
    ready: "success",
    failed: "danger",
    stale: "warning",
    building: "primary",
    not_started: "info",
  }[s] || "info") as any;
}

async function load() {
  loading.value = true;
  try {
    const [r, s] = await Promise.all([getOntIndexes({}), getOntIndexSummary()]);
    rows.value = r.data?.data || [];
    summary.value = s.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.loadIndexFailed"));
  } finally {
    loading.value = false;
  }
}

/* ---------------- 新建 ---------------- */
const formVisible = ref(false);
const form = reactive<any>({
  object_code: "",
  prop_code: "",
  index_kind: "property",
  pipeline_kind: "batch",
});
const formProps = ref<any[]>([]);

async function openForm() {
  Object.assign(form, {
    object_code: objects.value[0]?.code || "",
    prop_code: "",
    index_kind: "property",
    pipeline_kind: "batch",
  });
  if (form.object_code) await loadProps(form.object_code);
  formVisible.value = true;
}
async function loadProps(code: string) {
  const r = await getOntProperties(code);
  formProps.value = r.data?.data || [];
}

async function doSave() {
  if (!form.object_code) return ElMessage.warning(i18nT("ai_ontology.pleaseSelectObjectType"));
  busy.value = true;
  try {
    const r = await saveOntIndex({ ...form });
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.saved"));
    const id = r.data?.data?.id;
    formVisible.value = false;
    if (id) {
      const b = await buildOntIndex(id);
      ElMessage.success(b.data?.msg || i18nT("ai_ontology.built"));
    }
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.saveFailed"));
  } finally {
    busy.value = false;
  }
}

/* ---------------- 构建 / 重试 / 过期 ---------------- */
async function doBuild(row: any) {
  busy.value = true;
  try {
    const r = await buildOntIndex(row.id);
    if (r.data?.data?.ok) ElMessage.success(r.data.msg);
    else ElMessage.warning(r.data?.msg || i18nT("ai_ontology.buildFailed"));
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.buildFailed"));
  } finally {
    busy.value = false;
  }
}

async function doBuildAll() {
  busy.value = true;
  try {
    const r = await buildAllOntIndexes("");
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.processed"));
    await load();
  } finally {
    busy.value = false;
  }
}

async function doBuildObject(row: any) {
  busy.value = true;
  try {
    const r = await buildAllOntIndexes(row.object_code);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.processed"));
    await load();
  } finally {
    busy.value = false;
  }
}

async function doRetry() {
  busy.value = true;
  try {
    const r = await retryOntIndexes();
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.processed"));
    await load();
  } finally {
    busy.value = false;
  }
}

async function doStale(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.markExpiredConfirm", { name: row.object_name, count: row.ready }),
    i18nT("ai_ontology.markExpired"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.mark"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  const r = await markOntIndexStale(row.object_code);
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.marked"));
  await load();
}

async function doRemove(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.deleteIndexConfirm", {
      index: `${row.index_kind_label} · ${row.prop_code || i18nT("ai_ontology.primaryKey")}`,
    }),
    i18nT("ai_ontology.deleteIndex"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  const r = await removeOntIndex(row.id);
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.deleted"));
  await load();
}

/* ---------------- 建议 ---------------- */
const sugVisible = ref(false);
const suggestions = ref<any[]>([]);
const sugObject = ref("");

async function openSuggest() {
  const code =
    objects.value.find((o: any) => o.code === "video_cameras")?.code || objects.value[0]?.code;
  if (!code) return;
  sugObject.value = code;
  const r = await suggestOntIndexes(code);
  suggestions.value = r.data?.data?.suggestions || [];
  sugVisible.value = true;
}

async function doApplySuggestions(onlyHigh: boolean) {
  busy.value = true;
  try {
    const r = await applyOntIndexSuggestions(sugObject.value, onlyHigh);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.processed"));
    sugVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.processFailed"));
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<style lang="scss" scoped>
.ont-ix__stats {
  margin-bottom: 10px;
}

.ont-ix__stat {
  text-align: center;
}

.ont-ix__statv {
  font-size: var(--el-font-size-extra-large);
  font-weight: 600;
  color: var(--el-color-primary);
}

.ont-ix__statl {
  color: var(--el-text-color-secondary);
}

.ont-ix__err {
  color: var(--el-color-danger);
}
</style>
