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
        <span class="ont-sec__title">场景</span>
        <el-tag size="small" effect="plain">{{ rows.length }} 个</el-tag>
        <el-button class="ont-sec__op" type="primary" size="small" :icon="Plus" @click="openForm()">
          新建场景
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :disabled="checked.length < 2"
          @click="doCompare"
        >
          对比选中（{{ checked.length }}）
        </el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          size="small"
          :icon="Delete"
          :loading="expiring"
          @click="doExpire"
        >
          清理过期场景
        </el-button>
        <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="场景里的编辑只存在于沙箱中，不会影响真实数据；读取场景时看到的是「基线 + 场景差异」。合并时才会以单事务写回主本体。"
      />

      <el-table
        v-loading="loading"
        :data="rows"
        size="small"
        border
        max-height="520"
        @selection-change="(v: any[]) => (checked = v.map((x) => x.code))"
      >
        <template #empty><el-empty :image-size="60" description="还没有场景" /></template>
        <el-table-column type="selection" width="44" />
        <el-table-column label="场景" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.name }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
              {{ row.status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="编辑数" width="110" align="center">
          <template #default="{ row }">
            <span class="ont-mono">{{ row.edit_count }} / {{ row.edit_limit }}</span>
          </template>
        </el-table-column>
        <el-table-column label="涉及对象" width="100" align="center">
          <template #default="{ row }">{{ row.object_count }}</template>
        </el-table-column>
        <el-table-column label="动作数" width="90" align="center">
          <template #default="{ row }">
            <span class="ont-mono">
              {{ (row.action_codes || []).length }} / {{ row.action_limit }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="110" show-overflow-tooltip />
        <el-table-column prop="created_time" label="创建时间" width="150" show-overflow-tooltip />
        <el-table-column label="过期时间" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span :class="{ 'ont-scn__expiring': row.is_expired }">
              {{ row.expires_at || "—" }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="row.status === 'active'"
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="success"
              size="small"
              @click="doApply(row)"
            >
              合并
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="primary"
              size="small"
              @click="doDuplicate(row)"
            >
              复制
            </el-button>
            <el-button
              v-if="row.status === 'active'"
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="warning"
              size="small"
              @click="doDiscard(row)"
            >
              丢弃
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:edit'"
              link
              type="danger"
              size="small"
              @click="doRemove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑 -->
    <el-dialog v-model="formVisible" title="场景" width="620px" append-to-body>
      <el-form :model="form" label-width="120px">
        <el-form-item label="场景名称" required>
          <el-input v-model="form.name" placeholder="如 方案A-先改名观察" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="合并动作">
          <el-select v-model="form.merge_action_code" filterable clearable style="width: 100%">
            <el-option
              v-for="a in actions"
              :key="a.code"
              :label="`${a.name}（${a.code}）`"
              :value="a.code"
            />
          </el-select>
          <div class="ont-hint">
            官方：场景**通过动作类型合并**，该动作的提交条件决定谁有权合并（留空则不限）
          </div>
        </el-form-item>
        <el-form-item label="可编辑范围">
          <el-select
            v-model="form.scopeTypes"
            multiple
            filterable
            clearable
            style="width: 100%"
            placeholder="留空 = 不限制对象类型"
          >
            <el-option v-for="o in objects" :key="o.code" :label="o.name" :value="o.code" />
          </el-select>
          <div class="ont-hint">官方：创建合并动作时要划定场景编辑的 对象类型范围</div>
        </el-form-item>
        <el-form-item label="寿命（天）">
          <el-input-number v-model="form.ttl_days" :min="1" :max="365" />
          <span class="ont-hint">官方默认 31 天，到期自动删除</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:edit'"
          type="primary"
          :loading="saving"
          @click="doSave"
        >
          保存
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情：差异预览 -->
    <el-drawer v-model="detailVisible" :title="detail?.name || '场景详情'" size="62%">
      <template v-if="detail">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="编码">
            <span class="ont-mono">{{ detail.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="statusTagType(detail.status)" effect="plain">
              {{ detail.status_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="编辑数">
            {{ detail.edit_count }} / {{ detail.edit_limit }}
          </el-descriptions-item>
          <el-descriptions-item label="动作数">
            {{ (detail.action_codes || []).length }} / {{ detail.action_limit }}
          </el-descriptions-item>
          <el-descriptions-item label="创建">
            {{ detail.created_by }} · {{ detail.created_time }}
          </el-descriptions-item>
          <el-descriptions-item label="过期">
            {{ detail.expires_at || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="合并动作">
            <span class="ont-mono">{{ detail.merge_action_code || "—" }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="可编辑范围">
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
            <span v-else class="ont-none">不限制</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.applied_at" label="合并于" :span="2">
            {{ detail.applied_by }} · {{ detail.applied_at }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">合并后会变成什么</span>
          <el-tag size="small" effect="plain">{{ diff?.objects_changed || 0 }} 个对象</el-tag>
        </div>
        <el-table :data="diff?.changes || []" size="small" border max-height="360">
          <template #empty>
            <el-empty :image-size="50" description="该场景还没有任何编辑" />
          </template>
          <el-table-column label="对象" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="ont-mono">{{ objectLabel(row.object_code) }}#{{ row.object_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="kind_label" label="变更" width="130" />
          <el-table-column label="字段变化" min-width="320">
            <template #default="{ row }">
              <div class="ont-scn__diff">
                <span v-for="(v, k) in row.changed" :key="k" class="ont-mono">
                  {{ k }}: {{ fmt(v.before) }} → {{ fmt(v.after) }}
                </span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="来源动作" width="150" show-overflow-tooltip>
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
          :title="`有 ${diff.model_results.length} 条模型预测结果；${diff.model_result_note}`"
        />

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">编辑明细</span>
          <el-tag size="small" effect="plain">{{ detail.edits?.length || 0 }}</el-tag>
        </div>
        <el-table :data="detail.edits || []" size="small" border max-height="300">
          <el-table-column label="对象" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="ont-mono">{{ objectLabel(row.object_code) }}#{{ row.object_key }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="kind_label" label="种类" width="130" />
          <el-table-column prop="action_code" label="动作" width="140" show-overflow-tooltip />
          <el-table-column prop="created_time" label="时间" width="150" />
        </el-table>

        <div class="ont-scn__actions">
          <el-button
            v-if="detail.status === 'active'"
            v-hasPerm="'module_ai:ontology:edit'"
            type="success"
            @click="doApply(detail)"
          >
            合并到主本体
          </el-button>
          <el-button
            v-if="detail.status === 'active'"
            v-hasPerm="'module_ai:ontology:edit'"
            @click="doDiscard(detail)"
          >
            丢弃
          </el-button>
          <el-button v-hasPerm="'module_ai:ontology:edit'" @click="doDuplicate(detail)">
            复制
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 多场景对比 -->
    <el-dialog v-model="compareVisible" title="多场景对比" width="820px" append-to-body>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="同一个对象在不同场景下会变成什么样——用来权衡不同方案"
      />
      <el-table :data="compare?.rows || []" size="small" border max-height="420">
        <el-table-column label="对象" min-width="170" show-overflow-tooltip>
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
            <span v-else class="ont-none">未改动</span>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
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

const emit = defineEmits<{ (e: "refresh"): void }>();

const { objects, actions, objectLabel } = useOntologyData();

function statusTagType(s: string) {
  return ({ active: "primary", applied: "success", discarded: "info", expired: "warning" }[s] ||
    "info") as any;
}
function fmt(v: any) {
  if (v === null || v === undefined) return "空";
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
    ElMessage.error(e?.msg || "加载场景失败");
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
  if (!form.name?.trim()) return ElMessage.warning("请填场景名称");
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
    ElMessage.success(r.data?.msg || "已保存");
    formVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
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
    `将把场景「${row.name}」的 ${n ?? "?"} 个对象改动**以单事务写入真实数据表**，` +
      "任一失败则全部回滚。此操作不可自动撤销。确认合并？",
    "合并场景",
    { type: "warning", confirmButtonText: "合并", cancelButtonText: "取消" }
  );
  try {
    const r = await applyOntScenario(row.code);
    ElMessage.success(r.data?.msg || "已合并");
    detailVisible.value = false;
    await load();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || "合并失败");
  }
}

async function doDiscard(row: any) {
  await ElMessageBox.confirm(
    `将丢弃场景「${row.name}」的 ${row.edit_count} 处编辑，这些改动不会生效。确认丢弃？`,
    "丢弃场景",
    { type: "warning", confirmButtonText: "丢弃", cancelButtonText: "取消" }
  );
  try {
    const r = await discardOntScenario(row.code);
    ElMessage.success(r.data?.msg || "已丢弃");
    detailVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  }
}

async function doDuplicate(row: any) {
  try {
    const r = await duplicateOntScenario(row.code);
    ElMessage.success(r.data?.msg || "已复制");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "复制失败");
  }
}

async function doRemove(row: any) {
  await ElMessageBox.confirm(
    `将删除场景「${row.name}」及其 ${row.edit_count} 处编辑记录，且不可恢复（真实数据不受影响）。确认删除？`,
    "删除场景",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  try {
    const r = await removeOntScenario(row.code);
    ElMessage.success(r.data?.msg || "已删除");
    detailVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

/* ---------------- 对比 ---------------- */
const compareVisible = ref(false);
const compare = ref<any>(null);

async function doCompare() {
  if (checked.value.length < 2) return ElMessage.warning("至少选择 2 个场景");
  try {
    const r = await compareOntScenarios(checked.value);
    compare.value = r.data?.data || null;
    compareVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.msg || "对比失败");
  }
}

/* ---------------- 过期清理（TTL） ---------------- */
const expiring = ref(false);
async function doExpire() {
  await ElMessageBox.confirm(
    "将把所有**已超过寿命（TTL）**的场景置为「已过期」，并删除它们的编辑记录（官方默认寿命 31 天）。" +
      "过期的改动不会生效，且不可恢复。确认清理？",
    "清理过期场景",
    { type: "warning", confirmButtonText: "清理", cancelButtonText: "取消" }
  );
  expiring.value = true;
  try {
    const r = await expireOntScenarios();
    const n = r.data?.data?.expired ?? 0;
    if (n > 0) ElMessage.success(r.data?.msg || `已过期 ${n} 个场景`);
    else ElMessage.info("没有已过期的场景，无需清理");
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "清理失败");
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
