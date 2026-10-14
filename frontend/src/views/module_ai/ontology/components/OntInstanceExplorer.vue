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
        placeholder="选择对象类型"
        class="ont-explore__pick"
        @change="onObjectChange"
      >
        <el-option
          v-for="o in materializedObjects"
          :key="o.code"
          :label="`${o.name}（${o.code}）`"
          :value="o.code"
        />
      </el-select>
      <el-input
        v-model="keyword"
        size="small"
        clearable
        placeholder="搜索实例（标题属性模糊匹配）"
        class="ont-explore__kw"
        @keyup.enter="doSearch(0)"
      />
      <el-button size="small" type="primary" :icon="Search" :loading="loading" @click="doSearch(0)">
        搜索
      </el-button>
      <el-tag v-if="total" size="small" type="info" effect="plain">共 {{ total }}</el-tag>
      <span class="ont-hint">
        这里是
        <strong>实例层</strong>
        （真实数据行），与「对象类型 / 关系类型」的
        <strong>类型层</strong>
        定义不同
      </span>
    </div>

    <!-- 批量动作 -->
    <div class="ont-bar">
      <el-button size="small" type="warning" :disabled="!selection.length" @click="openBulk">
        批量执行动作（已选 {{ selection.length }}）
      </el-button>
      <el-button size="small" :disabled="!selection.length" @click="openGraphOfSelected">
        查看实例图
      </el-button>
      <el-tag v-if="notMaterialized" size="small" type="warning" effect="plain">
        该对象类型尚未物化，无法浏览实例
      </el-tag>
    </div>

    <!-- 实例表 -->
    <el-table
      v-loading="loading"
      :data="items"
      size="small"
      border
      max-height="420"
      @selection-change="onSelect"
    >
      <template #empty>
        <el-empty :image-size="50" description="没有匹配的实例" />
      </template>
      <el-table-column type="selection" width="44" />
      <el-table-column prop="key" label="主键" width="90" />
      <el-table-column prop="label" label="标题" min-width="180" show-overflow-tooltip />
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
      <el-table-column label="操作" width="210" align="center" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="openView(row)">视图</el-button>
          <el-button link type="primary" size="small" @click="openGraph(row)">图</el-button>
          <el-button link type="success" size="small" @click="goQuery(row)">问数</el-button>
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
            <el-tag v-if="pm.edit_only" size="small" type="info" effect="plain">仅动作填充</el-tag>
            <el-tag v-if="pm.sensitive" size="small" type="danger" effect="plain">敏感</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Writeback -->
        <div class="ont-view__sec">
          <div class="ont-view__title">
            编辑属性（Writeback）
            <el-tag v-if="!inst.edits_enabled" size="small" type="info" effect="plain">
              未开启
            </el-tag>
          </div>
          <el-alert
            v-if="!inst.edits_enabled"
            type="info"
            :closable="false"
            title="该对象类型未开启可编辑。在对象类型详情里打开「可编辑（Writeback）」后，这里就能直接改属性值。"
          />
          <template v-else>
            <el-form label-width="120px" size="small">
              <el-form-item v-for="pm in editableProps" :key="pm.code" :label="pm.name">
                <el-input v-model="editForm[pm.code]" />
              </el-form-item>
            </el-form>
            <el-button
              type="primary"
              size="small"
              :loading="savingWb"
              :disabled="!editableProps.length"
              @click="doWriteback"
            >
              保存修改
            </el-button>
            <span class="ont-hint">只允许写非敏感、非「仅动作填充」的属性，且会留痕</span>
          </template>
        </div>

        <!-- 关系跳转（Pivot） -->
        <div class="ont-view__sec">
          <div class="ont-view__title">关系跳转（Search Around）</div>
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
            <el-button link type="primary" size="small" @click="doPivot(lk)">跳转</el-button>
          </div>
        </div>

        <!-- 可执行动作 -->
        <div class="ont-view__sec">
          <div class="ont-view__title">可执行动作</div>
          <el-button
            v-for="a in inst.actions"
            :key="a.code"
            size="small"
            class="ont-view__act"
            @click="openAction(a, [inst.key])"
          >
            {{ a.name }}
            <el-tag v-if="a.approval" size="small" type="warning" effect="plain">需审批</el-tag>
          </el-button>
          <div v-if="!inst.actions.length" class="ont-none">该对象类型没有动作</div>
        </div>
      </div>
    </el-drawer>

    <!-- 跳转结果 -->
    <el-dialog v-model="pivotDialog" :title="pivotTitle" width="720px" append-to-body>
      <el-table :data="pivotItems" size="small" border max-height="420">
        <template #empty><el-empty :image-size="50" description="没有关联实例" /></template>
        <el-table-column prop="key" label="主键" width="90" />
        <el-table-column prop="label" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="drillInto(row)">继续</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 实例图 -->
    <el-dialog v-model="graphDialog" title="实例层图（真实对象为节点）" width="86%" append-to-body>
      <div class="ont-bar">
        <el-select
          v-model="graphDepth"
          size="small"
          class="ont-explore__pick"
          @change="reloadGraph"
        >
          <el-option :value="1" label="扩展 1 步" />
          <el-option :value="2" label="扩展 2 步" />
          <el-option :value="3" label="扩展 3 步" />
        </el-select>
        <el-select
          v-model="graphLinkIds"
          multiple
          collapse-tags
          size="small"
          class="ont-explore__pick"
          placeholder="全部关系"
          @change="reloadGraph"
        >
          <el-option
            v-for="lk in graphLinks"
            :key="lk.id"
            :label="`${lk.name}（${lk.direction_label}${lk.other_label}）`"
            :value="lk.id"
          />
        </el-select>
        <el-button size="small" @click="() => graphRef?.fit?.()">适配</el-button>
        <el-button size="small" @click="() => graphRef?.center?.()">居中</el-button>
        <el-tag size="small" type="info" effect="plain">{{ graphMsg }}</el-tag>
      </div>
      <GraphCanvas
        ref="graphRef"
        :nodes="graphNodes"
        :edges="graphEdges"
        height="560px"
        layout-name="force"
        @node-tap="onNodeTap"
      />
      <div class="ont-hint">
        节点是
        <strong>真实数据行</strong>
        （如某台摄像机、某条告警记录），边是按关系类型实际连出来的；
        点节点可跳到该实例。类型层图请看「关系类型 → 可视化」。
      </div>
    </el-dialog>

    <!-- 选择要执行的动作 -->
    <el-dialog v-model="chooserDialog" title="选择要执行的动作" width="520px" append-to-body>
      <el-table :data="chooserActs" size="small" border max-height="360">
        <template #empty><el-empty :image-size="50" description="该对象类型没有动作" /></template>
        <el-table-column prop="name" label="动作" min-width="150" show-overflow-tooltip />
        <el-table-column prop="code" label="编码" min-width="120" show-overflow-tooltip />
        <el-table-column label="审批" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.approval" size="small" type="warning" effect="plain">需审批</el-tag>
            <span v-else class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="pickAction(row)">选它</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="ont-hint">将对已选的 {{ chooserKeys.length }} 个实例逐个执行</div>
    </el-dialog>

    <!-- 执行动作 -->
    <el-dialog v-model="actDialog" :title="actTitle" width="560px" append-to-body>
      <el-alert
        v-if="actTarget?.approval"
        type="warning"
        :closable="false"
        class="ont-note"
        title="该动作开启了审批门禁：需要勾选「已确认」才会真正写库"
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
        <el-form-item v-if="actTarget?.approval" label="已确认">
          <el-switch v-model="actApprove" />
        </el-form-item>
        <el-form-item label="作用实例">
          <el-tag size="small" type="info" effect="plain">
            {{ actKeys.length }} 个：{{ actKeys.slice(0, 6).join("、")
            }}{{ actKeys.length > 6 ? "…" : "" }}
          </el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actDialog = false">取消</el-button>
        <el-button type="primary" :loading="actRunning" @click="runAction">执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
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
  pivotOntInstance,
  searchOntInstances,
  writebackOntInstance,
} from "@/api/module_ai/ontology";

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
  if (!code.value) return ElMessage.warning("请先选择对象类型");
  loading.value = true;
  try {
    const r = await searchOntInstances(code.value, {
      keyword: keyword.value,
      limit: pageSize,
      offset,
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
  inst.value ? `${inst.value.object_name} · ${inst.value.label}` : "对象视图"
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
  const r = await getOntInstance(code.value, row.key);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.error(d.msg || "读取实例失败");
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
    if (!Object.keys(changed).length) return ElMessage.info("没有修改任何属性");
    const r = await writebackOntInstance({
      object_code: code.value,
      key: inst.value.key,
      props: changed,
    });
    ElMessage.success(r.data?.msg || "已写回");
    await doSearch((pageNo.value - 1) * pageSize);
    await openView({ key: inst.value.key });
  } catch (e: any) {
    ElMessage.error(e?.msg || "写回失败");
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
  const r = await pivotOntInstance(code.value, inst.value.key, lk.id, 100);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.warning(d.msg || "跳转失败");
  if (!d.items?.length) return ElMessage.info(d.msg || "没有关联实例");
  pivotItems.value = d.items;
  pivotCode.value = d.other_object;
  pivotTitle.value = `沿「${lk.name}」找到 ${d.items.length} 个${d.other_name || d.other_object}`;
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
  const r = await getOntInstance(code.value, row.key);
  const d = r.data?.data || {};
  if (!d.ok) return ElMessage.error(d.msg || "读取实例失败");
  graphLinks.value = d.links || [];
  graphLinkIds.value = [];
  graphRoot.value = { code: code.value, key: String(row.key) };
  graphDialog.value = true;
  await reloadGraph();
}
async function reloadGraph() {
  if (!graphRoot.value) return;
  const r = await getOntInstanceGraph({
    object_code: graphRoot.value.code,
    key: graphRoot.value.key,
    link_ids: graphLinkIds.value.length ? graphLinkIds.value : undefined,
    depth: graphDepth.value,
    limit: 150,
  });
  const d = r.data?.data || {};
  graphNodes.value = d.nodes || [];
  graphEdges.value = d.edges || [];
  graphMsg.value = d.msg || "";
}
function openGraphOfSelected() {
  const row = selection.value[0];
  if (!row) return ElMessage.warning("请先选择一行");
  openGraph(row);
}
function onNodeTap(name: string) {
  const n = graphNodes.value.find((x) => x.name === name);
  if (!n) return;
  ElMessage.info(`实例：${n.name}（${n.object_code} #${n.key}）`);
}

/* ---------- 批量执行动作 ---------- */
const actDialog = ref(false);
const actTitle = ref("");
const actTarget = ref<any>(null);
const actKeys = ref<string[]>([]);
const actForm = ref<Record<string, string>>({});
const actFields = ref<string[]>([]);
const actApprove = ref(false);
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
  actApprove.value = false;
  actTitle.value = `${detail.name || a.name}（${keys.length} 个实例）`;
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
        approve: actApprove.value,
      });
      const d = r.data?.data || {};
      if (d.ok) ok += 1;
      else errs.push(`${k}: ${r.data?.msg || d.msg || "失败"}`);
    } catch (e: any) {
      errs.push(`${k}: ${e?.msg || "失败"}`);
    }
  }
  actRunning.value = false;
  actDialog.value = false;
  if (ok) ElMessage.success(`已执行 ${ok} 个实例的动作并留痕`);
  if (errs.length) ElMessage.warning(`${errs.length} 个失败：${errs.slice(0, 2).join("；")}`);
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
.ont-explore__kw {
  width: 240px;
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
