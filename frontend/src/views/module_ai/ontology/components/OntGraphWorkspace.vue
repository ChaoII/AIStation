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
        placeholder="搜索对象类型"
        clearable
        :prefix-icon="Search"
        class="ont-gw__search"
        @input="doSearch"
      />
      <el-select v-model="layout" size="small" class="ont-gw__layout">
        <el-option label="力导向" value="cose" />
        <el-option label="同心布局" value="concentric" />
        <el-option label="树形布局" value="breadthfirst" />
        <el-option label="网格布局" value="grid" />
        <el-option label="环形布局" value="circle" />
      </el-select>
      <el-select v-model="theme" size="small" class="ont-gw__theme">
        <el-option v-for="t in THEME_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-checkbox v-model="onlyConnected" size="small" class="ont-gw__connected">
        只显示有关联
      </el-checkbox>
      <el-switch v-model="physicsMode" size="small" active-text="物理" />
      <el-switch
        v-model="shortestMode"
        size="small"
        active-text="最短路径"
        @change="onModeChange"
      />
      <el-switch v-model="multiSelect" size="small" active-text="多选" @change="onModeChange" />
      <el-button-group size="small">
        <el-button :icon="Refresh" title="重新布局" @click="relayout" />
        <el-button :icon="FullScreen" title="适合页面" @click="graphRef?.fit()" />
        <el-button :icon="Aim" title="居中" @click="graphRef?.center?.()" />
        <el-button :icon="ZoomIn" title="放大" @click="graphRef?.zoom(1.25)" />
        <el-button :icon="ZoomOut" title="缩小" @click="graphRef?.zoom(0.8)" />
        <el-button :icon="Download" title="导出图片" @click="exportImage" />
      </el-button-group>
      <el-button
        v-if="multiSelect && selectedNames.length"
        v-hasPerm="'module_ai:ontology:edit'"
        size="small"
        type="danger"
        plain
        @click="batchDelete"
      >
        批量删除{{ selectedNames.length ? ` (${selectedNames.length})` : "" }}
      </el-button>
      <el-button v-if="multiSelect && selectedNames.length" size="small" @click="clearSelection">
        清空选择
      </el-button>
      <el-tag size="small" type="info" effect="plain">
        {{ nodes.length }} 类型 / {{ edges.length }} 关系
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
        <el-button size="small" :icon="View">视图</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="save">保存当前视图</el-dropdown-item>
            <el-dropdown-item command="manage:active">管理已加载视图…</el-dropdown-item>
            <el-dropdown-item command="refresh" divided>刷新列表</el-dropdown-item>
            <el-dropdown-item
              v-for="v in mySavedViews"
              :key="v.code"
              :command="`load:${v.code}`"
              divided
            >
              <span>{{ v.name || v.code }}</span>
              <el-tag v-if="v.is_default" size="small" type="success">默认</el-tag>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-dropdown size="small" trigger="click" @command="onTemplateCmd">
        <el-button size="small" :icon="Brush">模板</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="save">存为图模板</el-dropdown-item>
            <el-dropdown-item command="refresh" divided>刷新列表</el-dropdown-item>
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
      <el-empty v-else :image-size="70" description="该本体暂无对象类型，右键点空白处新建" />

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
          <div class="ont-gw__ctx-item" @click="ctxEdit">编辑元数据</div>
          <div class="ont-gw__ctx-item" @click="ctxMaterialize">物化为表</div>
          <div class="ont-gw__ctx-item ont-gw__ctx-danger" @click="ctxDelete">删除对象类型</div>
        </template>
        <template v-else>
          <div class="ont-gw__ctx-item" @click="ctxCreate">新建对象类型</div>
        </template>
      </div>
    </div>

    <!-- 多选提示条 -->
    <div v-if="multiSelect && selectedNames.length" class="ont-gw__selbar">
      已选 {{ selectedNames.length }} 个对象类型（可批量删除 / 清空）
    </div>

    <!-- 保存视图 / 存模板命名弹窗 -->
    <el-dialog
      v-model="viewDialog.visible"
      :title="viewDialog.kind === 'template' ? '存为图模板' : '保存视图'"
      width="520px"
      append-to-body
    >
      <el-form label-width="70px">
        <el-form-item label="名称">
          <el-input v-model="viewDialog.name" placeholder="给这个视图起个名字" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="viewDialog.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="viewDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="confirmSaveView">保存</el-button>
      </template>
    </el-dialog>

    <!-- 管理已加载视图：分享 / 版本 / 设默认 / 删除 -->
    <el-dialog v-model="manageDialog.visible" title="管理视图" width="520px" append-to-body>
      <el-descriptions v-if="manageDialog.view" :column="1" size="small" border>
        <el-descriptions-item label="名称">
          {{ manageDialog.view.name || manageDialog.view.code }}
        </el-descriptions-item>
        <el-descriptions-item label="类型">
          {{ manageDialog.view.graph_kind === "template" ? "图模板" : "保存视图" }}
        </el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">共享给角色</el-divider>
      <el-select
        v-model="manageDialog.roles"
        multiple
        filterable
        allow-create
        default-first-option
        placeholder="输入/选择角色编码"
        style="width: 100%"
      />
      <el-button size="small" type="primary" style="margin-top: 8px" @click="confirmShare">
        保存共享设置
      </el-button>
      <el-divider content-position="left">版本历史</el-divider>
      <el-scrollbar max-height="160px">
        <div v-for="ver in manageDialog.versions" :key="ver.version" class="ont-gw__ver">
          <span>v{{ ver.version }} · {{ ver.created_time }}</span>
          <el-button size="small" @click="doRestoreVersion(ver.version)">回滚</el-button>
        </div>
        <el-empty v-if="!manageDialog.versions.length" :image-size="40" description="暂无版本" />
      </el-scrollbar>
      <template #footer>
        <el-button
          v-if="manageDialog.view && manageDialog.view.graph_kind === 'saved'"
          @click="confirmDefault"
        >
          设为默认
        </el-button>
        <el-button type="danger" plain @click="confirmRemoveView(manageDialog.view)">
          删除
        </el-button>
        <el-button @click="manageDialog.visible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
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
  { label: "默认", value: "default" },
  { label: "海洋", value: "ocean" },
  { label: "森林", value: "forest" },
  { label: "落日", value: "sunset" },
  { label: "单色", value: "mono" },
];

/** 维护面板入口：图标 + 面板键 + 标签 */
const MAINT_ITEMS = [
  { label: "索引", panel: "index", icon: Collection },
  { label: "提案", panel: "proposals", icon: Files },
  { label: "场景", panel: "scenarios", icon: Tickets },
  { label: "决策", panel: "decisions", icon: Operation },
  { label: "对象探索", panel: "explore", icon: Guide },
  { label: "对象类型组", panel: "groups", icon: FolderOpened },
  { label: "值类型", panel: "valueTypes", icon: DataLine },
  { label: "共享属性", panel: "shared", icon: Share },
  { label: "接口", panel: "interfaces", icon: Link },
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
  if (length < 0) ElMessage.info(`「${a}」与「${b}」之间未找到路径`);
  else ElMessage.success(`最短路径：${a} → ${b}，${length} 跳`);
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
  a.download = `本体图谱.png`;
  a.click();
  ElMessage.success("已导出图片");
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
    ElMessage.warning("请先选择左侧的本体域再保存视图");
    return;
  }
  try {
    const r = await saveGraphView({
      name: viewDialog.name || `视图 ${new Date().toLocaleString()}`,
      description: viewDialog.description,
      graph_kind: viewDialog.kind,
      domain_code,
      state: collectState(),
    });
    viewDialog.visible = false;
    ElMessage.success(r?.data?.msg || "已保存");
    loadGraphViews();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || "保存失败");
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
    ElMessage.success(`已加载「${v.name || v.code}」`);
    // 布局是异步的，等渲染完成后再应用视口
    setTimeout(() => {
      graphRef.value?.setLayout?.(layout.value);
      graphRef.value?.setViewport?.({ zoom: s.zoom, pan: s.pan });
    }, 350);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || "加载失败");
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
    ElMessage.error(e?.response?.data?.msg || e?.message || "加载失败");
  }
}

async function confirmShare() {
  const view = manageDialog.view;
  if (!view) return;
  try {
    const r = await shareGraphView(view.code, "roles", manageDialog.roles);
    ElMessage.success(r?.data?.msg || "已设置共享");
    openManage(view.code);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || "设置失败");
  }
}

async function confirmDefault() {
  const view = manageDialog.view;
  if (!view) return;
  try {
    await setDefaultGraphView(view.code, view.domain_code || currentDomain.value || "");
    ElMessage.success("已设为默认");
    manageDialog.visible = false;
    loadGraphViews();
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || "设置失败");
  }
}

async function doRestoreVersion(version: number) {
  const view = manageDialog.view;
  if (!view) return;
  try {
    await restoreGraphView(view.code, version);
    ElMessage.success("已回滚");
    openManage(view.code);
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.msg || e?.message || "回滚失败");
  }
}

function confirmRemoveView(view: any) {
  if (!view) return;
  ElMessageBox.confirm(
    `将删除图视图「${view.name || view.code}」及其全部版本记录，且不可恢复。`,
    "删除视图",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  )
    .then(async () => {
      try {
        await removeGraphView(view.code);
        ElMessage.success("已删除");
        manageDialog.visible = false;
        loadGraphViews();
      } catch (e: any) {
        ElMessage.error(e?.response?.data?.msg || e?.message || "删除失败");
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
