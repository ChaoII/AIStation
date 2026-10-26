<!--
  本体图谱工作区（cytoscape）
  节点 = 对象类型（按所属本体上色），边 = 关系类型（按关系名上色、平滑曲线、线宽随量化）。
  工具条：搜索 / 布局 / 物理模式 / 主题 / 重排 / 缩放适配 / 导出图片 / 多选 / 最短路径，
  以及一排「维护面板」图标按钮（索引/提案/场景/决策/对象探索/对象类型组/值类型/共享属性/接口）。
  点节点 → node-tap 上抛父级弹对象详情抽屉。
-->
<template>
  <div class="ont-gw">
    <!-- 工具条 -->
    <div class="ont-gw__bar">
      <el-input
        v-model="search"
        size="small"
        :placeholder="i18nT('ai_ontology.searchObjectTypes')"
        clearable
        :prefix-icon="Search"
        class="ont-gw__search"
        @input="doSearch"
      />
      <el-select v-model="layout" size="small" class="ont-gw__layout">
        <el-option :label="i18nT('ai_ontology.forceDirected')" value="cose" />
        <el-option :label="i18nT('ai_ontology.concentricLayout')" value="concentric" />
        <el-option :label="i18nT('ai_ontology.treeLayout')" value="breadthfirst" />
        <el-option :label="i18nT('ai_ontology.gridLayout')" value="grid" />
        <el-option :label="i18nT('ai_ontology.ringLayout')" value="circle" />
      </el-select>
      <el-select v-model="theme" size="small" class="ont-gw__theme">
        <el-option v-for="t in THEME_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-checkbox v-model="onlyConnected" size="small" class="ont-gw__connected">
        {{ i18nT("ai_ontology.showRelatedOnly") }}
      </el-checkbox>
      <el-switch v-model="physicsMode" size="small" :active-text="i18nT('ai_ontology.physics')" />
      <el-switch
        v-model="shortestMode"
        size="small"
        :active-text="i18nT('ai_ontology.shortestPath')"
        @change="onModeChange"
      />
      <el-switch
        v-model="multiSelect"
        size="small"
        :active-text="i18nT('ai_ontology.multiSelect')"
        @change="onModeChange"
      />
      <el-button-group size="small">
        <el-button :icon="Refresh" :title="i18nT('ai_ontology.reLayout')" @click="relayout" />
        <el-button
          :icon="FullScreen"
          :title="i18nT('ai_ontology.fitPage')"
          @click="graphRef?.fit()"
        />
        <el-button :icon="Aim" :title="i18nT('ai_ontology.center')" @click="graphRef?.center?.()" />
        <el-button
          :icon="ZoomIn"
          :title="i18nT('ai_ontology.zoomIn')"
          @click="graphRef?.zoom(1.25)"
        />
        <el-button
          :icon="ZoomOut"
          :title="i18nT('ai_ontology.zoomOut')"
          @click="graphRef?.zoom(0.8)"
        />
        <el-button
          :icon="Download"
          :title="i18nT('ai_ontology.exportImage')"
          @click="exportImage"
        />
      </el-button-group>
      <el-button
        v-if="multiSelect && selectedNames.length"
        v-hasPerm="'module_ai:ontology:edit'"
        size="small"
        type="danger"
        plain
        @click="batchDelete"
      >
        {{ i18nT("ai_ontology.batchDeleteSelected", { count: selectedNames.length }) }}
      </el-button>
      <el-button v-if="multiSelect && selectedNames.length" size="small" @click="clearSelection">
        {{ i18nT("ai_ontology.clearSelection") }}
      </el-button>
      <el-tag size="small" type="info" effect="plain">
        {{
          i18nT("ai_ontology.typeRelationCount", {
            typeCount: nodes.length,
            relationCount: edges.length,
          })
        }}
      </el-tag>

      <!-- 维护面板图标按钮 -->
      <div class="ont-gw__maint">
        <el-tooltip v-for="m in MAINT_ITEMS" :key="m.panel" :content="m.label" placement="bottom">
          <el-button
            size="small"
            :icon="m.icon"
            class="ont-gw__maint-btn"
            @click="emit('maintain', m.panel)"
          />
        </el-tooltip>
      </div>

      <!-- 保存视图 / 图模板 -->
      <el-dropdown size="small" trigger="click" @command="onViewCmd">
        <el-button size="small" :icon="View">{{ i18nT("ai_ontology.view") }}</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="save">
              {{ i18nT("ai_ontology.saveCurrentView") }}
            </el-dropdown-item>
            <el-dropdown-item command="manage:active">
              {{ i18nT("ai_ontology.manageLoadedViews") }}
            </el-dropdown-item>
            <el-dropdown-item command="refresh" divided>
              {{ i18nT("ai_ontology.refreshList") }}
            </el-dropdown-item>
            <el-dropdown-item
              v-for="v in mySavedViews"
              :key="v.code"
              :command="`load:${v.code}`"
              divided
            >
              <span>{{ v.name || v.code }}</span>
              <el-tag v-if="v.is_default" size="small" type="success">
                {{ i18nT("ai_ontology.default") }}
              </el-tag>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown size="small" trigger="click" @command="onTemplateCmd">
        <el-button size="small" :icon="Brush">{{ i18nT("ai_ontology.template") }}</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="save">
              {{ i18nT("ai_ontology.saveAsGraphTemplate") }}
            </el-dropdown-item>
            <el-dropdown-item command="refresh" divided>
              {{ i18nT("ai_ontology.refreshList") }}
            </el-dropdown-item>
            <el-dropdown-item
              v-for="t in templates"
              :key="t.code"
              :command="`load:${t.code}`"
              divided
            >
              {{ t.name || t.code }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 图谱 -->
    <div class="ont-gw__canvas" @click="closeCtx" @contextmenu.prevent>
      <GraphCanvas
        v-if="nodes.length"
        :key="layout"
        ref="graphRef"
        :nodes="nodes"
        :edges="edges"
        height="100%"
        link-mode
        :layout-name="layout"
        :physics-mode="physicsMode"
        :shortest-mode="shortestMode"
        :theme="theme"
        :highlight="highlightNodes"
        :node-style="{
          sizeMode: 'weight',
          shapeMode: 'uniform',
          uniformShape: 'round-rectangle',
          labelSize: 12,
          colorMode: 'category',
        }"
        :edge-style="{
          label: 'show',
          colorMode: 'category',
          curve: 'bezier',
          arrow: 'triangle',
          widthMode: 'weight',
          opacity: 0.8,
        }"
        @node-tap="onNodeTap"
        @link-draw="onLinkDraw"
        @edge-ctx="onEdgeCtx"
        @node-ctx="onNodeCtx"
        @blank-ctx="onBlankCtx"
        @path-found="onPathFound"
      />
      <el-empty
        v-else
        :image-size="70"
        :description="i18nT('ai_ontology.thisOntologyHasNoObjectTypesRightClickBlankAreaToCreate')"
      />

      <!-- 右键菜单（**全部是写操作**：编辑/物化/删除/新建 ⇒ 需 edit 权限；
           只读用户看不到这个菜单，也不会点到会 403 的入口） -->
      <div
        v-if="ctxMenu.visible"
        v-hasPerm="'module_ai:ontology:edit'"
        class="ont-gw__ctx"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        @click.stop
        @contextmenu.prevent
      >
        <template v-if="ctxMenu.kind === 'node'">
          <div class="ont-gw__ctx-item" @click="ctxEdit">
            {{ i18nT("ai_ontology.editMetadata") }}
          </div>
          <div class="ont-gw__ctx-item" @click="ctxMaterialize">
            {{ i18nT("ai_ontology.materialize") }}
          </div>
          <div class="ont-gw__ctx-item ont-gw__ctx-danger" @click="ctxDelete">
            {{ i18nT("ai_ontology.deleteObjectType") }}
          </div>
        </template>
        <template v-else>
          <div class="ont-gw__ctx-item" @click="ctxCreate">
            {{ i18nT("ai_ontology.newObjectType") }}
          </div>
        </template>
      </div>
    </div>

    <!-- 多选提示条 -->
    <div v-if="multiSelect && selectedNames.length" class="ont-gw__selbar">
      {{ i18nT("ai_ontology.selectedCountHint", { count: selectedNames.length }) }}
    </div>

    <!-- 保存视图 / 存模板命名弹窗 -->
    <el-dialog
      v-model="viewDialog.visible"
      :title="
        viewDialog.kind === 'template'
          ? i18nT('ai_ontology.saveAsGraphTemplate')
          : i18nT('ai_ontology.saveView')
      "
      width="520px"
      append-to-body
    >
      <el-form label-width="70px">
        <el-form-item :label="i18nT('ai_ontology.name')">
          <el-input v-model="viewDialog.name" :placeholder="i18nT('ai_ontology.nameThisView')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.note')">
          <el-input v-model="viewDialog.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="viewDialog.visible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button type="primary" @click="confirmSaveView">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 管理已加载视图：分享 / 版本 / 设默认 / 删除 -->
    <el-dialog
      v-model="manageDialog.visible"
      :title="i18nT('ai_ontology.manageViews')"
      width="520px"
      append-to-body
    >
      <el-descriptions v-if="manageDialog.view" :column="1" size="small" border>
        <el-descriptions-item :label="i18nT('ai_ontology.name')">
          {{ manageDialog.view.name || manageDialog.view.code }}
        </el-descriptions-item>
        <el-descriptions-item :label="i18nT('ai_ontology.type')">
          {{
            manageDialog.view.graph_kind === "template"
              ? i18nT("ai_ontology.graphTemplate")
              : i18nT("ai_ontology.saveView")
          }}
        </el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">{{ i18nT("ai_ontology.shareToRoles") }}</el-divider>
      <el-select
        v-model="manageDialog.roles"
        multiple
        filterable
        allow-create
        default-first-option
        :placeholder="i18nT('ai_ontology.enterOrSelectRoleCode')"
        style="width: 100%"
      />
      <el-button size="small" type="primary" style="margin-top: 8px" @click="confirmShare">
        {{ i18nT("ai_ontology.saveShareSettings") }}
      </el-button>
      <el-divider content-position="left">{{ i18nT("ai_ontology.versionHistory") }}</el-divider>
      <el-scrollbar max-height="160px">
        <div v-for="ver in manageDialog.versions" :key="ver.version" class="ont-gw__ver">
          <span>v{{ ver.version }} · {{ ver.created_time }}</span>
          <el-button size="small" @click="doRestoreVersion(ver.version)">
            {{ i18nT("ai_ontology.rollback") }}
          </el-button>
        </div>
        <el-empty
          v-if="!manageDialog.versions.length"
          :image-size="40"
          :description="i18nT('ai_ontology.noVersions')"
        />
      </el-scrollbar>
      <template #footer>
        <el-button
          v-if="manageDialog.view && manageDialog.view.graph_kind === 'saved'"
          @click="confirmDefault"
        >
          {{ i18nT("ai_ontology.setAsDefault") }}
        </el-button>
        <el-button type="danger" plain @click="confirmRemoveView(manageDialog.view)">
          {{ i18nT("ai_ontology.delete2") }}
        </el-button>
        <el-button @click="manageDialog.visible = false">
          {{ i18nT("ai_ontology.close") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, reactive, ref, watch } from "vue";
import {
  Aim,
  Brush,
  Collection,
  DataLine,
  Download,
  Files,
  FolderOpened,
  FullScreen,
  Guide,
  Link,
  Operation,
  Refresh,
  Search,
  Share,
  Tickets,
  View,
  ZoomIn,
  ZoomOut,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import GraphCanvas from "@/views/module_ai/knowledge/GraphCanvas.vue";
import {
  getGraphViewDetail,
  getGraphViewList,
  getGraphViewVersions,
  removeGraphView,
  restoreGraphView,
  saveGraphView,
  setDefaultGraphView,
  shareGraphView,
} from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";
import { buildOntGraph } from "../graph";

const { t: i18nT } = useI18n();

const emit = defineEmits<{
  (e: "node-tap", objectCode: string): void;
  (e: "link-draw", sourceCode: string, targetCode: string): void;
  (e: "edge-ctx", sourceCode: string, targetCode: string): void;
  (e: "create-object"): void;
  (e: "edit-object", objectCode: string): void;
  (e: "delete-object", objectCode: string): void;
  (e: "materialize-object", objectCode: string): void;
  (e: "maintain", panel: string): void;
  (e: "batch-delete", objectCodes: string[]): void;
}>();

const { scopedObjects, scopedLinks, currentDomain } = useOntologyData();

const graphRef = ref<any>(null);
const layout = ref("cose");
const theme = ref("default");
const onlyConnected = ref(false);
const physicsMode = ref(false);
const shortestMode = ref(false);
const multiSelect = ref(false);
const search = ref("");

const THEME_OPTIONS = [
  { label: i18nT("ai_ontology.default"), value: "default" },
  { label: i18nT("ai_ontology.ocean"), value: "ocean" },
  { label: i18nT("ai_ontology.forest"), value: "forest" },
  { label: i18nT("ai_ontology.sunset"), value: "sunset" },
  { label: i18nT("ai_ontology.mono"), value: "mono" },
];

/** 维护面板入口：图标 + 面板键 + 标签 */
const MAINT_ITEMS = [
  { label: i18nT("ai_ontology.index"), panel: "index", icon: Collection },
  { label: i18nT("ai_ontology.proposal"), panel: "proposals", icon: Files },
  { label: i18nT("ai_ontology.scenario"), panel: "scenarios", icon: Tickets },
  { label: i18nT("ai_ontology.decision"), panel: "decisions", icon: Operation },
  { label: i18nT("ai_ontology.objectExplorer"), panel: "explore", icon: Guide },
  { label: i18nT("ai_ontology.objectTypeGroup"), panel: "groups", icon: FolderOpened },
  { label: i18nT("ai_ontology.valueType"), panel: "valueTypes", icon: DataLine },
  { label: i18nT("ai_ontology.sharedProperty"), panel: "shared", icon: Share },
  { label: i18nT("ai_ontology.interface"), panel: "interfaces", icon: Link },
];

const graph = computed(() =>
  buildOntGraph(scopedObjects.value, scopedLinks.value, { onlyConnected: onlyConnected.value })
);
const nodes = computed(() => graph.value.nodes);
const edges = computed(() => graph.value.edges);
/** 图谱节点显示名 → 对象编码 */
const codeByName = computed(() => {
  const m: Record<string, string> = {};
  graph.value.nodes.forEach((n) => {
    m[n.name] = n.objectCode;
  });
  return m;
});

/** 多选：选中节点名集合（高亮） */
const selectedNames = ref<string[]>([]);
const highlightNodes = computed(() => [...selectedNames.value]);

/** 右键菜单状态 */
const ctxMenu = reactive({
  visible: false,
  kind: "blank" as "blank" | "node",
  x: 0,
  y: 0,
  code: "",
});

function onModeChange() {
  // 多选与最短路径互斥：都开启会抢「点节点」语义
  if (shortestMode.value && multiSelect.value) multiSelect.value = false;
  if (multiSelect.value && shortestMode.value) shortestMode.value = false;
  clearSelection();
}

function onNodeTap(name: string) {
  if (multiSelect.value) {
    toggleSelect(name);
    return;
  }
  const code = codeByName.value[name];
  if (code) emit("node-tap", code);
}
function onPathFound(a: string, b: string, length: number) {
  if (length < 0) ElMessage.info(i18nT("ai_ontology.noPathFound", { a, b }));
  else ElMessage.success(i18nT("ai_ontology.shortestPathMsg", { a, b, length }));
}
function onLinkDraw(sourceName: string, targetName: string) {
  const s = codeByName.value[sourceName];
  const t = codeByName.value[targetName];
  if (s && t) emit("link-draw", s, t);
}
function onEdgeCtx(sourceName: string, targetName: string) {
  const s = codeByName.value[sourceName];
  const t = codeByName.value[targetName];
  if (s && t) {
    ctxMenu.visible = false;
    emit("edge-ctx", s, t);
  }
}
function onNodeCtx(name: string, x: number, y: number) {
  ctxMenu.kind = "node";
  ctxMenu.code = codeByName.value[name] || "";
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function onBlankCtx(x: number, y: number) {
  ctxMenu.kind = "blank";
  ctxMenu.code = "";
  ctxMenu.x = x;
  ctxMenu.y = y;
  ctxMenu.visible = true;
}
function closeCtx() {
  ctxMenu.visible = false;
}
function ctxEdit() {
  closeCtx();
  if (ctxMenu.code) emit("edit-object", ctxMenu.code);
}
function ctxDelete() {
  closeCtx();
  if (ctxMenu.code) emit("delete-object", ctxMenu.code);
}
function ctxMaterialize() {
  closeCtx();
  if (ctxMenu.code) emit("materialize-object", ctxMenu.code);
}
function ctxCreate() {
  closeCtx();
  emit("create-object");
}

function toggleSelect(name: string) {
  const idx = selectedNames.value.indexOf(name);
  if (idx >= 0) selectedNames.value.splice(idx, 1);
  else selectedNames.value.push(name);
}
function clearSelection() {
  selectedNames.value = [];
}
function batchDelete() {
  const codes = selectedNames.value.map((n) => codeByName.value[n]).filter((c): c is string => !!c);
  emit("batch-delete", codes);
}
function relayout() {
  // 换 key 触发重排（layout 相同也重新布局）
  graphRef.value?.setLayout?.(layout.value);
}
function exportImage() {
  const url = graphRef.value?.png?.();
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.download = `${i18nT("ai_ontology.graphFileName")}.png`;
  a.click();
  ElMessage.success(i18nT("ai_ontology.imageExported"));
}

let searchTimer: any = null;
function doSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  const q = (search.value || "").trim();
  searchTimer = setTimeout(() => {
    graphRef.value?.search(q);
  }, 200);
}

/** 当前图配置快照（保存视图 / 存模板用）。zoom/pan 取 GraphCanvas 视口。 */
function collectState(): Record<string, any> {
  return {
    layout: layout.value,
    theme: theme.value,
    onlyConnected: onlyConnected.value,
    physicsMode: physicsMode.value,
    shortestMode: shortestMode.value,
    multiSelect: multiSelect.value,
    search: search.value,
    selected: [...selectedNames.value],
    ...(graphRef.value?.getViewport?.() ?? { zoom: 1, pan: { x: 0, y: 0 } }),
  };
}

const activeViewCode = ref("");
const mySavedViews = ref<any[]>([]);
const templates = ref<any[]>([]);
/** 保存/存模板命名弹窗 */
const viewDialog = reactive({
  visible: false,
  kind: "saved" as "saved" | "template",
  name: "",
  description: "",
});
/** 管理弹窗：分享 / 版本 / 设默认 / 删除 */
const manageDialog = reactive({
  visible: false,
  view: null as any,
  roles: [] as string[],
  versions: [] as any[],
});

async function loadGraphViews() {
  try {
    const [saved, tpl] = await Promise.all([
      getGraphViewList(currentDomain.value || "", "saved"),
      getGraphViewList("", "template"),
    ]);
    mySavedViews.value = saved?.data?.data || [];
    templates.value = tpl?.data?.data || [];
  } catch {
    /* 列表失败静默，不打断图谱使用 */
  }
}

function openViewDialog(kind: "saved" | "template") {
  viewDialog.kind = kind;
  viewDialog.name = "";
  viewDialog.description = "";
  viewDialog.visible = true;
}

async function confirmSaveView() {
  const domain_code = viewDialog.kind === "saved" ? currentDomain.value || "" : "";
  if (viewDialog.kind === "saved" && !domain_code) {
    ElMessage.warning(i18nT("ai_ontology.pleaseSelectAnOntologyDomainOnTheLeftFirst"));
    return;
  }
  try {
    const r = await saveGraphView({
      name:
        viewDialog.name ||
        i18nT("ai_ontology.viewNameDefault", { time: new Date().toLocaleString() }),
      description: viewDialog.description,
      graph_kind: viewDialog.kind,
      domain_code,
      state: collectState(),
    });
    viewDialog.visible = false;
    ElMessage.success(r?.data?.msg || i18nT("ai_ontology.saved"));
    loadGraphViews();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.saveFailed"));
  }
}

async function loadViewState(code: string) {
  try {
    const r = await getGraphViewDetail(code);
    const v = r?.data?.data;
    if (!v?.state) return;
    const s = v.state;
    if (s.layout) layout.value = s.layout;
    if (s.theme) theme.value = s.theme;
    if (typeof s.onlyConnected === "boolean") onlyConnected.value = s.onlyConnected;
    if (typeof s.physicsMode === "boolean") physicsMode.value = s.physicsMode;
    if (typeof s.shortestMode === "boolean") shortestMode.value = s.shortestMode;
    if (typeof s.multiSelect === "boolean") multiSelect.value = s.multiSelect;
    if (typeof s.search === "string") search.value = s.search;
    if (Array.isArray(s.selected)) selectedNames.value = [...s.selected];
    activeViewCode.value = code;
    ElMessage.success(i18nT("ai_ontology.loadedView", { name: v.name || v.code }));
    // 布局是异步的，等渲染完成后再应用视口
    setTimeout(() => {
      graphRef.value?.setLayout?.(layout.value);
      graphRef.value?.setViewport?.({ zoom: s.zoom, pan: s.pan });
    }, 350);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.loadFailed"));
  }
}

async function openManage(code: string) {
  try {
    const [detail, versions] = await Promise.all([
      getGraphViewDetail(code),
      getGraphViewVersions(code),
    ]);
    manageDialog.view = detail?.data?.data;
    manageDialog.roles = detail?.data?.data?.share_roles || [];
    manageDialog.versions = versions?.data?.data || [];
    manageDialog.visible = true;
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.loadFailed"));
  }
}

async function confirmShare() {
  const view = manageDialog.view;
  if (!view) return;
  try {
    const r = await shareGraphView(view.code, "roles", manageDialog.roles);
    ElMessage.success(r?.data?.msg || i18nT("ai_ontology.shareSet"));
    openManage(view.code);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.setFailed"));
  }
}

async function confirmDefault() {
  const view = manageDialog.view;
  if (!view) return;
  try {
    await setDefaultGraphView(view.code, view.domain_code || currentDomain.value || "");
    ElMessage.success(i18nT("ai_ontology.setAsDefault2"));
    manageDialog.visible = false;
    loadGraphViews();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.setFailed"));
  }
}

async function doRestoreVersion(version: number) {
  const view = manageDialog.view;
  if (!view) return;
  try {
    await restoreGraphView(view.code, version);
    ElMessage.success(i18nT("ai_ontology.rolledBack"));
    openManage(view.code);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.rollbackFailed"));
  }
}

function confirmRemoveView(view: any) {
  if (!view) return;
  ElMessageBox.confirm(
    i18nT("ai_ontology.deleteViewConfirm", { name: view.name || view.code }),
    i18nT("ai_ontology.deleteView"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  )
    .then(async () => {
      try {
        await removeGraphView(view.code);
        ElMessage.success(i18nT("ai_ontology.deleted"));
        manageDialog.visible = false;
        loadGraphViews();
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.msg || e?.message || i18nT("ai_ontology.deleteFailed"));
      }
    })
    .catch(() => {});
}

function onViewCmd(cmd: string) {
  if (cmd === "save") return openViewDialog("saved");
  if (cmd === "refresh") return loadGraphViews();
  if (cmd.startsWith("load:")) return loadViewState(cmd.slice(5));
  if (cmd.startsWith("manage:")) {
    const rest = cmd.slice(7);
    return openManage(rest === "active" ? activeViewCode.value || "" : rest);
  }
}

function onTemplateCmd(cmd: string) {
  if (cmd === "save") return openViewDialog("template");
  if (cmd === "refresh") return loadGraphViews();
  if (cmd.startsWith("load:")) return loadViewState(cmd.slice(5));
}

watch(currentDomain, loadGraphViews, { immediate: true });

defineExpose({ graphRef });
</script>

<style scoped lang="scss">
.ont-gw {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
  flex-direction: column;
}
.ont-gw__bar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.ont-gw__search {
  width: 200px;
}
.ont-gw__layout {
  width: 120px;
}
.ont-gw__theme {
  width: 96px;
}
.ont-gw__maint {
  display: flex;
  gap: 4px;
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--el-border-color-light);
}
.ont-gw__maint-btn {
  padding: 4px 7px;
}
.ont-gw__canvas {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  position: relative;
}
.ont-gw__ctx {
  position: absolute;
  z-index: 20;
  min-width: 150px;
  padding: 4px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
  box-shadow: var(--el-box-shadow-light);
}
.ont-gw__ctx-item {
  padding: 6px 12px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
  border-radius: var(--el-border-radius-base);
  cursor: pointer;
  user-select: none;
}
.ont-gw__ctx-item:hover {
  background: var(--el-fill-color-light);
}
.ont-gw__ctx-danger {
  color: var(--el-color-danger);
}
.ont-gw__ctx-danger:hover {
  background: var(--el-color-danger-light-9);
}
.ont-gw__selbar {
  margin-top: 6px;
  padding: 4px 10px;
  font-size: var(--el-font-size-base);
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: var(--el-border-radius-base);
}
.ont-gw__ver {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
</style>
