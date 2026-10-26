<!--
  对象探索（Object Explorer）+ 对象视图（Object View）

  与「实例图」的区别（对齐官方）：
  - 本组件面向**真实数据行**（实例层）：搜索、筛选、批量执行动作、沿关系跳转（Pivot）
  - 「类型层图」面向对象类型/关系类型的定义，见 OntTypeLinkGraph.vue
-->
<template>
  <div class="ont-explore">
    <!-- 工具条 -->
    <div class="ont-bar">
      <el-select
        v-model="code"
        filterable
        size="small"
        :placeholder="i18nT('ai_ontology.selectObjectType')"
        class="ont-explore__pick"
        @change="onObjectChange"
      >
        <el-option
          v-for="o in materializedObjects"
          :key="o.code"
          :label="i18nT('ai_ontology.nameWithCode', { name: o.name, code: o.code })"
          :value="o.code"
        />
      </el-select>
      <el-input
        v-model="keyword"
        size="small"
        clearable
        :placeholder="i18nT('ai_ontology.searchInstancesFuzzyMatchOnTitleProperty')"
        class="ont-explore__kw"
        @keyup.enter="doSearch(0)"
      />
      <el-button size="small" type="primary" :icon="Search" :loading="loading" @click="doSearch(0)">
        {{ i18nT("ai_ontology.search") }}
      </el-button>
      <!-- 场景（P5）：选中后所有实例读/图谱/动作执行都读写该场景的差异 -->
      <el-select
        v-model="scen"
        size="small"
        clearable
        :placeholder="i18nT('ai_ontology.primaryOntology')"
        class="ont-explore__scen"
        @visible-change="onScenOpen"
        @change="doSearch(0)"
      >
        <el-option :label="i18nT('ai_ontology.primaryOntologyNoScenarioOverlay')" value="" />
        <el-option v-for="s in scenOptions" :key="s.code" :label="s.name" :value="s.code" />
      </el-select>
      <el-tag v-if="scen" size="small" type="warning" effect="plain">
        {{ i18nT("ai_ontology.inScenarios") }}
      </el-tag>
      <el-tag v-if="total" size="small" type="info" effect="plain">
        {{ i18nT("ai_ontology.totalCountShort", { count: total }) }}
      </el-tag>
      <span class="ont-hint">
        {{ i18nT("ai_ontology.hereIs") }}
        <strong>{{ i18nT("ai_ontology.instanceLevel") }}</strong>
        {{ i18nT("ai_ontology.instanceVsTypeLevelHint") }}
        <strong>{{ i18nT("ai_ontology.typeLevel") }}</strong>
        {{ i18nT("ai_ontology.differentDefinition") }}
      </span>
    </div>

    <!-- 批量动作 -->
    <div class="ont-bar">
      <el-button
        v-hasPerm="'module_ai:ontology:execute'"
        size="small"
        type="warning"
        :disabled="!selection.length"
        @click="openBulk"
      >
        {{ i18nT("ai_ontology.batchExecuteActionCount", { count: selection.length }) }}
      </el-button>
      <el-button size="small" :disabled="!selection.length" @click="openGraphOfSelected">
        {{ i18nT("ai_ontology.viewInstanceGraph") }}
      </el-button>
      <el-tag v-if="notMaterialized" size="small" type="warning" effect="plain">
        {{ i18nT("ai_ontology.thisObjectTypeIsNotMaterializedYet") }}
      </el-tag>
    </div>

    <!-- 实例表 -->
    <el-table
      v-loading="loading"
      :data="items"
      size="small"
      border
      max-height="420"
      stripe
      @selection-change="onSelect"
    >
      <template #empty>
        <el-empty :image-size="50" :description="i18nT('ai_ontology.noMatchingInstances')" />
      </template>
      <el-table-column type="selection" width="44" />
      <el-table-column prop="key" :label="i18nT('ai_ontology.primaryKey')" width="90" />
      <el-table-column
        prop="label"
        :label="i18nT('ai_ontology.title')"
        min-width="180"
        show-overflow-tooltip
      />
      <el-table-column
        v-for="c in previewCols"
        :key="c"
        :label="colLabel(c)"
        min-width="130"
        show-overflow-tooltip
      >
        <template #default="{ row }">
          <span :class="{ 'ont-none': row.props[c] == null || row.props[c] === '' }">
            {{ row.props[c] == null || row.props[c] === "" ? "—" : row.props[c] }}
          </span>
        </template>
      </el-table-column>
      <el-table-column
        :label="i18nT('ai_ontology.operations')"
        width="210"
        align="center"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button icon="View" link type="primary" size="small" @click="openView(row)">
            {{ i18nT("ai_ontology.view") }}
          </el-button>
          <el-button link type="primary" size="small" @click="openGraph(row)">
            {{ i18nT("ai_ontology.graph") }}
          </el-button>
          <el-button icon="Search" link type="success" size="small" @click="goQuery(row)">
            {{ i18nT("ai_ontology.askData") }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      class="ont-explore__page"
      small
      layout="prev, pager, next, total"
      :total="total"
      :page-size="pageSize"
      :current-page="pageNo"
      @current-change="onPage"
    />

    <!-- 单实例：对象视图 -->
    <el-drawer v-model="viewDrawer" size="52%" :title="viewTitle">
      <div v-if="inst" class="ont-view">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="pm in visibleProps" :key="pm.code" :label="pm.name">
            <span
              :class="{ 'ont-none': inst.props[pm.code] == null || inst.props[pm.code] === '' }"
            >
              {{ display(inst.props[pm.code], pm) }}
            </span>
            <el-tag v-if="pm.edit_only" size="small" type="info" effect="plain">
              {{ i18nT("ai_ontology.actionFilledOnly") }}
            </el-tag>
            <el-tag v-if="pm.sensitive" size="small" type="danger" effect="plain">
              {{ i18nT("ai_ontology.sensitive") }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Writeback -->
        <div class="ont-view__sec">
          <div class="ont-view__title">
            {{ i18nT("ai_ontology.editPropertiesWriteback") }}
            <el-tag v-if="!inst.edits_enabled" size="small" type="info" effect="plain">
              {{ i18nT("ai_ontology.notEnabled") }}
            </el-tag>
          </div>
          <el-alert
            v-if="!inst.edits_enabled"
            type="info"
            :closable="false"
            :title="
              i18nT(
                'ai_ontology.thisObjectTypeIsNotEditableEnableEditableWritebackInItsDetailsToEditHere'
              )
            "
          />
          <template v-else>
            <el-form label-width="120px" size="small">
              <el-form-item v-for="pm in editableProps" :key="pm.code" :label="pm.name">
                <el-input v-model="editForm[pm.code]" />
              </el-form-item>
            </el-form>
            <el-button
              v-hasPerm="'module_ai:ontology:execute'"
              type="primary"
              size="small"
              :loading="savingWb"
              :disabled="!editableProps.length"
              @click="doWriteback"
            >
              {{ i18nT("ai_ontology.saveChanges") }}
            </el-button>
            <span class="ont-hint">
              {{
                i18nT("ai_ontology.onlyNonSensitiveNonActionFilledPropertiesCanBeWrittenWithAudit")
              }}
            </span>
          </template>
        </div>

        <!-- 关系跳转（Pivot） -->
        <div class="ont-view__sec">
          <div class="ont-view__title">{{ i18nT("ai_ontology.relationJump") }}</div>
          <div v-for="lk in inst.links" :key="lk.id" class="ont-view__link">
            <el-tag
              size="small"
              :type="lk.direction === 'out' ? 'primary' : 'success'"
              effect="plain"
            >
              {{ lk.direction_label }}
            </el-tag>
            <span class="ont-view__linkname">{{ lk.name }}</span>
            <span class="ont-none">{{ lk.other_label }}</span>
            <el-button icon="Right" link type="primary" size="small" @click="doPivot(lk)">
              {{ i18nT("ai_ontology.jump") }}
            </el-button>
          </div>
        </div>

        <!-- 可执行动作 -->
        <div class="ont-view__sec">
          <div class="ont-view__title">{{ i18nT("ai_ontology.executableActions") }}</div>
          <el-button
            v-for="a in inst.actions"
            :key="a.code"
            v-hasPerm="'module_ai:ontology:execute'"
            size="small"
            class="ont-view__act"
            @click="openAction(a, [inst.key])"
          >
            {{ a.name }}
            <el-tag v-if="a.approval" size="small" type="warning" effect="plain">
              {{ i18nT("ai_ontology.requiresApproval") }}
            </el-tag>
          </el-button>
          <div v-if="!inst.actions.length" class="ont-none">
            {{ i18nT("ai_ontology.thisObjectTypeHasNoActions") }}
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 跳转结果 -->
    <el-dialog v-model="pivotDialog" :title="pivotTitle" width="900px" append-to-body>
      <el-table :data="pivotItems" size="small" border max-height="420" stripe>
        <template #empty>
          <el-empty :image-size="50" :description="i18nT('ai_ontology.noRelatedInstances')" />
        </template>
        <el-table-column prop="key" :label="i18nT('ai_ontology.primaryKey')" width="90" />
        <el-table-column
          prop="label"
          :label="i18nT('ai_ontology.title')"
          min-width="200"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.operations')" width="110" align="center">
          <template #default="{ row }">
            <el-button icon="VideoPlay" link type="primary" size="small" @click="drillInto(row)">
              {{ i18nT("ai_ontology.continue") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 实例图 -->
    <el-dialog
      v-model="graphDialog"
      :title="i18nT('ai_ontology.instanceLevelGraphRealObjectsAsNodes')"
      width="86%"
      append-to-body
    >
      <div class="ont-bar">
        <el-select
          v-model="graphDepth"
          size="small"
          class="ont-explore__pick"
          @change="reloadGraph"
        >
          <el-option :value="1" :label="i18nT('ai_ontology.expandSteps', { count: 1 })" />
          <el-option :value="2" :label="i18nT('ai_ontology.expandSteps', { count: 2 })" />
          <el-option :value="3" :label="i18nT('ai_ontology.expandSteps', { count: 3 })" />
        </el-select>
        <el-select
          v-model="graphLinkIds"
          multiple
          collapse-tags
          size="small"
          class="ont-explore__pick"
          :placeholder="i18nT('ai_ontology.allRelations')"
          @change="reloadGraph"
        >
          <el-option
            v-for="lk in graphLinks"
            :key="lk.id"
            :label="
              i18nT('ai_ontology.linkLabelFull', {
                name: lk.name,
                direction: lk.direction_label,
                other: lk.other_label,
              })
            "
            :value="lk.id"
          />
        </el-select>
        <el-button size="small" @click="() => graphRef?.fit?.()">
          {{ i18nT("ai_ontology.fit") }}
        </el-button>
        <el-button size="small" @click="() => graphRef?.center?.()">
          {{ i18nT("ai_ontology.center") }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">{{ graphMsg }}</el-tag>
      </div>
      <div class="ont-explore__timeline">
        <el-select
          v-model="timelineProp"
          size="small"
          clearable
          :placeholder="i18nT('ai_ontology.selectTimeProperty')"
          class="ont-explore__pick"
          @change="onTimelinePropChange"
        >
          <el-option
            v-for="tp in timelinePropsList"
            :key="`${tp.object_code}:${tp.prop_code}`"
            :label="`${tp.object_name}.${tp.prop_name}`"
            :value="`${tp.object_code}:${tp.prop_code}`"
          />
        </el-select>
        <template v-if="timelineProp && timelineMax > timelineMin">
          <el-slider
            v-model="timelineRange"
            range
            :min="timelineMin"
            :max="timelineMax"
            style="flex: 1; margin: 0 12px"
          />
          <span class="ont-explore__tl-label">
            {{ fmtTime(timelineRange[0]) }} ~ {{ fmtTime(timelineRange[1]) }}
          </span>
        </template>
        <el-empty
          v-else-if="timelineProp"
          :image-size="30"
          :description="i18nT('ai_ontology.selectedTimePropertyHasNoTimeValues')"
        />
      </div>
      <GraphCanvas
        ref="graphRef"
        :nodes="graphNodes"
        :edges="graphEdges"
        :dimmed="dimmedNames"
        height="560px"
        layout-name="force"
        @node-tap="onNodeTap"
      />
      <div class="ont-hint">
        {{ i18nT("ai_ontology.nodeIs") }}
        <strong>{{ i18nT("ai_ontology.realDataRows") }}</strong>
        {{ i18nT("ai_ontology.instanceGraphHint") }}
      </div>
    </el-dialog>

    <!-- 选择要执行的动作 -->
    <el-dialog
      v-model="chooserDialog"
      :title="i18nT('ai_ontology.selectActionToExecute')"
      width="520px"
      append-to-body
    >
      <el-table :data="chooserActs" size="small" border max-height="360" stripe>
        <template #empty>
          <el-empty
            :image-size="50"
            :description="i18nT('ai_ontology.thisObjectTypeHasNoActions')"
          />
        </template>
        <el-table-column
          prop="name"
          :label="i18nT('ai_ontology.action')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column
          prop="code"
          :label="i18nT('ai_ontology.code')"
          min-width="120"
          show-overflow-tooltip
        />
        <el-table-column :label="i18nT('ai_ontology.approval')" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.approval" size="small" type="warning" effect="plain">
              {{ i18nT("ai_ontology.requiresApproval") }}
            </el-tag>
            <span v-else class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.operations')" width="90" align="center">
          <template #default="{ row }">
            <el-button icon="Check" link type="primary" size="small" @click="pickAction(row)">
              {{ i18nT("ai_ontology.selectIt") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="ont-hint">
        {{ i18nT("ai_ontology.willExecuteOnSelected", { count: chooserKeys.length }) }}
      </div>
    </el-dialog>

    <!-- 执行动作 -->
    <el-dialog v-model="actDialog" :title="actTitle" width="600px" append-to-body>
      <el-alert
        v-if="actTarget?.approval"
        type="warning"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.thisActionHasAnApprovalGateCheckConfirmedToWrite')"
      />
      <el-form label-width="120px" size="small">
        <el-form-item
          v-for="f in actFields"
          :key="f"
          :label="fieldLabel(f)"
          :required="isRequired(f)"
        >
          <el-input v-model="actForm[f]" />
        </el-form-item>
        <el-alert
          v-if="actTarget?.approval"
          type="warning"
          :closable="false"
          show-icon
          :title="
            i18nT(
              'ai_ontology.thisActionNeedsManualApprovalAdminsApproveBeforeExecutionExecutorCannotSelfApprove'
            )
          "
        />
        <el-form-item :label="i18nT('ai_ontology.targetInstance')">
          <el-tag size="small" type="info" effect="plain">
            {{
              i18nT("ai_ontology.targetInstanceCount", {
                count: actKeys.length,
                keys: actKeys.slice(0, 6).join("、") + (actKeys.length > 6 ? "…" : ""),
              })
            }}
          </el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" :loading="actRunning" @click="runAction">
          {{ i18nT("ai_ontology.execute") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import {
  executeOntAction,
  getOntActions,
  getOntInstance,
  getOntInstanceGraph,
  getOntScenarios,
  getTimelineProps,
  pivotOntInstance,
  searchOntInstances,
  writebackOntInstance,
} from "@/api/module_ai/ontology";

const { t: i18nT } = useI18n();

interface ObjItem {
  code: string;
  name: string;
  property_count?: number;
}

const props = defineProps<{ objects: ObjItem[] }>();

const router = useRouter();

/** 带着「当前对象」去问数：该对象会作为**确定性上下文**注入，用户不必重复说明。 */
function goQuery(row: any) {
  router.push({
    path: "/ai/query",
    query: { object_code: code.value, object_key: String(row?.key ?? "") },
  });
}

/** 只有物化过（有支撑表）的对象类型才有实例可看 */
const materializedObjects = computed(() =>
  (props.objects || []).filter((o: any) => (o.property_count || 0) > 0)
);

const code = ref("");
const keyword = ref("");
// 场景（P5）：留空 = 主本体；选中后所有实例读/图谱/动作执行都读写该场景的差异
const scen = ref("");
const scenOptions = ref<{ code: string; name: string; status: string }[]>([]);

/** 下拉打开时才拉场景列表（避免组件一进来就多打一个接口）。 */
async function onScenOpen(open: boolean) {
  if (!open || scenOptions.value.length) return;
  try {
    const r = await getOntScenarios({ limit: 300 });
    scenOptions.value = ((r.data?.data || []) as any[])
      .filter((s: any) => s.status === "active")
      .map((s: any) => ({ code: s.code, name: s.name, status: s.status }));
  } catch {
    scenOptions.value = [];
  }
}
const items = ref<any[]>([]);
const total = ref(0);
const loading = ref(false);
const pageNo = ref(1);
const pageSize = 50;
const selection = ref<any[]>([]);
const notMaterialized = ref(false);
const colMeta = ref<any[]>([]);
const columns = ref<string[]>([]);

const previewCols = computed(() => columns.value.filter((c) => c !== "id").slice(0, 5));
function colLabel(c: string) {
  return colMeta.value.find((m) => m.code === c)?.name || c;
}

async function doSearch(offset = 0) {
  if (!code.value) return ElMessage.warning(i18nT("ai_ontology.pleaseSelectObjectTypeFirst"));
  loading.value = true;
  try {
    const r = await searchOntInstances(code.value, {
      keyword: keyword.value,
      limit: pageSize,
      offset,
      scenario: scen.value,
    });
    const d = r.data?.data || {};
    notMaterialized.value = !d.ok && /物化/.test(d.msg || "");
    items.value = d.items || [];
    total.value = d.total || 0;
    columns.value = d.columns || [];
    colMeta.value = d.columns_meta || [];
    pageNo.value = Math.floor(offset / pageSize) + 1;
    if (!d.ok && d.msg) ElMessage.warning(d.msg);
  } finally {
    loading.value = false;
  }
}
function onObjectChange() {
  keyword.value = "";
  selection.value = [];
  doSearch(0);
}
function onPage(p: number) {
  doSearch((p - 1) * pageSize);
}
function onSelect(rows: any[]) {
  selection.value = rows;
}

/* ---------- 对象视图 ---------- */
const viewDrawer = ref(false);
const inst = ref<any>(null);
const editForm = ref<Record<string, any>>({});
const savingWb = ref(false);
const viewTitle = computed(() =>
  inst.value ? `${inst.value.object_name} · ${inst.value.label}` : i18nT("ai_ontology.objectView")
);
const visibleProps = computed(() =>
  (inst.value?.properties_meta || []).filter((p: any) => p.visibility !== "hidden")
);
const editableProps = computed(() =>
  (inst.value?.properties_meta || []).filter(
    (p: any) => !p.sensitive && !p.edit_only && p.visibility !== "hidden"
  )
);
function display(v: any, pm: any) {
  if (pm.sensitive) return "••••••";
  if (v == null || v === "") return "—";
  return String(v);
}
async function openView(row: any) {
  const r = await getOntInstance(code.value, row.key, scen.value);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.error(d.msg || i18nT("ai_ontology.readInstanceFailed"));
  inst.value = d;
  const f: Record<string, any> = {};
  editableProps.value.forEach((p: any) => {
    f[p.code] = d.props[p.code] ?? "";
  });
  editForm.value = f;
  viewDrawer.value = true;
}
async function doWriteback() {
  savingWb.value = true;
  try {
    const changed: Record<string, any> = {};
    Object.keys(editForm.value).forEach((k) => {
      if (String(editForm.value[k] ?? "") !== String(inst.value.props[k] ?? "")) {
        changed[k] = editForm.value[k];
      }
    });
    if (!Object.keys(changed).length)
      return ElMessage.info(i18nT("ai_ontology.noPropertiesModified"));
    const r = await writebackOntInstance({
      object_code: code.value,
      key: inst.value.key,
      props: changed,
    });
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.writtenBack"));
    await doSearch((pageNo.value - 1) * pageSize);
    await openView({ key: inst.value.key });
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.writebackFailed"));
  } finally {
    savingWb.value = false;
  }
}

/* ---------- Pivot ---------- */
const pivotDialog = ref(false);
const pivotItems = ref<any[]>([]);
const pivotTitle = ref("");
const pivotCode = ref("");
async function doPivot(lk: any) {
  const r = await pivotOntInstance(code.value, inst.value.key, lk.id, 100, scen.value);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(d.msg || i18nT("ai_ontology.jumpFailed"));
  if (!d.items?.length) return ElMessage.info(d.msg || i18nT("ai_ontology.noRelatedInstances"));
  pivotItems.value = d.items;
  pivotCode.value = d.other_object;
  pivotTitle.value = i18nT("ai_ontology.pivotFound", {
    name: lk.name,
    count: d.items.length,
    other: d.other_name || d.other_object,
  });
  pivotDialog.value = true;
}
function drillInto(row: any) {
  pivotDialog.value = false;
  code.value = pivotCode.value;
  keyword.value = row.label;
  doSearch(0);
}

/* ---------- 实例图 ---------- */
const graphDialog = ref(false);
const graphRef = ref<any>(null);
const graphNodes = ref<any[]>([]);
const graphEdges = ref<any[]>([]);
const graphMsg = ref("");
const graphDepth = ref(1);
const graphLinkIds = ref<number[]>([]);
const graphLinks = ref<any[]>([]);
const graphRoot = ref<{ code: string; key: string } | null>(null);

async function openGraph(row: any) {
  // 关系列表来自该实例详情（这样就知道有哪些可扩展的关系）
  const r = await getOntInstance(code.value, row.key, scen.value);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.error(d.msg || i18nT("ai_ontology.readInstanceFailed"));
  graphLinks.value = d.links || [];
  graphLinkIds.value = [];
  graphRoot.value = { code: code.value, key: String(row.key) };
  graphDialog.value = true;
  await reloadGraph();
  await loadTimelineProps();
}
async function reloadGraph() {
  if (!graphRoot.value) return;
  const r = await getOntInstanceGraph({
    object_code: graphRoot.value.code,
    key: graphRoot.value.key,
    link_ids: graphLinkIds.value.length ? graphLinkIds.value : undefined,
    depth: graphDepth.value,
    limit: 150,
    scenario: scen.value,
  });
  const d = r.data?.data || {};
  graphNodes.value = d.nodes || [];
  graphEdges.value = d.edges || [];
  graphMsg.value = d.msg || "";
}
function openGraphOfSelected() {
  const row = selection.value[0];
  if (!row) return ElMessage.warning(i18nT("ai_ontology.pleaseSelectARowFirst"));
  openGraph(row);
}
function onNodeTap(name: string) {
  const n = graphNodes.value.find((x) => x.name === name);
  if (!n) return;
  ElMessage.info(
    i18nT("ai_ontology.instanceInfo", { name: n.name, code: n.object_code, key: n.key })
  );
}

/* ---------- 时间轴（按实例时间属性在图上淡化范围外节点） ---------- */
const timelinePropsList = ref<any[]>([]);
const timelineProp = ref(""); // "object_code:prop_code"
const timelineRange = ref<[number, number]>([0, 0]);
const timelineMin = ref(0);
const timelineMax = ref(0);

async function loadTimelineProps() {
  try {
    const r = await getTimelineProps("");
    timelinePropsList.value = r?.data?.data || [];
  } catch {
    timelinePropsList.value = [];
  }
}

function onTimelinePropChange(code: string) {
  if (!code) {
    timelineRange.value = [0, 0];
    return;
  }
  const [ocode, pcode] = code.split(":");
  const times: number[] = [];
  for (const n of graphNodes.value) {
    if (n.object_code !== ocode) continue;
    const v = n.props?.[pcode];
    if (v == null || v === "") continue;
    const t = new Date(String(v)).getTime();
    if (!Number.isNaN(t)) times.push(t);
  }
  if (!times.length) {
    timelineRange.value = [0, 0];
    return;
  }
  timelineMin.value = Math.min(...times);
  timelineMax.value = Math.max(...times);
  timelineRange.value = [timelineMin.value, timelineMax.value];
}

const dimmedNames = computed<string[]>(() => {
  if (!timelineProp.value) return [];
  const [ocode, pcode] = timelineProp.value.split(":");
  const out: string[] = [];
  for (const n of graphNodes.value) {
    if (n.object_code !== ocode) continue;
    const v = n.props?.[pcode];
    if (v == null || v === "") continue;
    const t = new Date(String(v)).getTime();
    if (Number.isNaN(t)) continue;
    if (t < timelineRange.value[0] || t > timelineRange.value[1]) out.push(n.name);
  }
  return out;
});

function fmtTime(v: number) {
  if (!v) return "";
  const d = new Date(v);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* ---------- 批量执行动作 ---------- */
const actDialog = ref(false);
const actTitle = ref("");
const actTarget = ref<any>(null);
const actKeys = ref<string[]>([]);
const actForm = ref<Record<string, string>>({});
const actFields = ref<string[]>([]);
const actRunning = ref(false);

function fieldLabel(f: string) {
  const a = (actTarget.value?.parameters || []).find((p: any) => p.key === f);
  return a?.label || f;
}
function isRequired(f: string) {
  return !!(actTarget.value?.parameters || []).find((p: any) => p.key === f && p.required);
}
/** 动作的可填字段：优先参数声明，回退可写白名单 */
async function openAction(a: any, keys: string[]) {
  const r = await getOntActions(code.value);
  const acts = r.data?.data || [];
  const detail = acts.find((x: any) => x.code === a.code) || a;
  actTarget.value = detail;
  const params = (detail.parameters || []).map((p: any) => p.key);
  actFields.value = params.length ? params : detail.white_fields || [];
  const f: Record<string, string> = {};
  actFields.value.forEach((k: string) => (f[k] = ""));
  if ((detail.method || "update") === "update") {
    if (!actFields.value.includes("object_key")) actFields.value.unshift("object_key");
    f.object_key = keys[0] ?? "";
  }
  actForm.value = f;
  actKeys.value = keys;
  actTitle.value = i18nT("ai_ontology.actionTitleWithCount", {
    name: detail.name || a.name,
    count: keys.length,
  });
  actDialog.value = true;
}
function openBulk() {
  chooseAction(selection.value.map((r) => String(r.key)));
}
const chooserDialog = ref(false);
const chooserActs = ref<any[]>([]);
const chooserKeys = ref<string[]>([]);
async function chooseAction(keys: string[]) {
  const r = await getOntActions(code.value);
  chooserActs.value = (r.data?.data || []).filter((a: any) => a.visibility !== "hidden");
  chooserKeys.value = keys;
  chooserDialog.value = true;
}
async function pickAction(a: any) {
  chooserDialog.value = false;
  await openAction(a, chooserKeys.value);
}
async function runAction() {
  if (!actTarget.value?.code) return;
  actRunning.value = true;
  let ok = 0;
  const errs: string[] = [];
  for (const k of actKeys.value) {
    const params: Record<string, any> = {};
    Object.keys(actForm.value).forEach((key) => {
      if (key === "object_key") return;
      if (actForm.value[key] !== "") params[key] = actForm.value[key];
    });
    try {
      const r = await executeOntAction({
        code: actTarget.value.code,
        object_key:
          actTarget.value.method === "update" ? String(k) : String(actForm.value.object_key || k),
        params,
        scenario: scen.value,
      });
      const d = r.data?.data || {};
      if (d.ok) ok += 1;
      else errs.push(`${k}: ${r.data?.msg || d.msg || i18nT("ai_ontology.failed")}`);
    } catch (e: any) {
      errs.push(`${k}: ${e?.msg || i18nT("ai_ontology.failed")}`);
    }
  }
  actRunning.value = false;
  actDialog.value = false;
  if (ok) ElMessage.success(i18nT("ai_ontology.executedCount", { count: ok }));
  if (errs.length)
    ElMessage.warning(
      i18nT("ai_ontology.failedCount", { count: errs.length, details: errs.slice(0, 2).join("；") })
    );
  await doSearch((pageNo.value - 1) * pageSize);
}
</script>

<style scoped lang="scss">
.ont-explore {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.ont-explore__pick {
  width: 260px;
}
.ont-explore__timeline {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.ont-explore__tl-label {
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}
.ont-explore__kw {
  width: 240px;
}
.ont-explore__scen {
  width: 160px;
}
.ont-explore__page {
  justify-content: flex-end;
}
.ont-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ont-view__sec {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ont-view__title {
  display: flex;
  gap: 6px;
  align-items: center;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ont-view__link {
  display: flex;
  gap: 6px;
  align-items: center;
}
.ont-view__linkname {
  font-weight: 600;
}
.ont-view__act {
  margin-right: 8px;
}
</style>
