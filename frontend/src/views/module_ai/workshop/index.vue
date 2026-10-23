<!-- 无代码应用 Workshop：说明引导 + 对象应用卡片 + 页内新建/删除 + 应用运行视图(表格/看板/表单) -->
<template>
  <div class="app-container ai-mod ai-workshop-page">
    <el-card shadow="never" class="ws-shell">
      <!-- 说明横幅：一进来就知道干嘛 -->
      <div class="ws-intro">
        <div class="ws-intro__icon">
          <el-icon :size="22"><Grid /></el-icon>
        </div>
        <div class="ws-intro__text">
          <div class="ws-intro__title">对象应用 · 无代码搞定</div>
          <div class="ws-intro__desc">
            挑一个业务对象（如设备、订单、摄像头），选几列字段，就能得到一个能看、能录数据的应用，不用写代码。
          </div>
          <div class="ws-intro__steps">
            <el-tag size="small" effect="plain" type="primary">① 选对象</el-tag>
            <el-tag size="small" effect="plain" type="success">② 选视图</el-tag>
            <el-tag size="small" effect="plain" type="warning">③ 挑字段</el-tag>
            <el-tag size="small" effect="plain" type="info">④ 保存使用</el-tag>
          </div>
        </div>
      </div>

      <!-- 工具条：标题 + 搜索 + 新建 -->
      <div class="ws-toolbar">
        <span class="ws-toolbar__count">共 {{ apps.length }} 个应用</span>
        <div class="ws-toolbar__right">
          <el-input
            v-model="keyword"
            placeholder="搜索应用名称"
            clearable
            :prefix-icon="Search"
            style="width: 220px"
          />
          <el-button type="primary" :icon="Plus" @click="openCreate">新建应用</el-button>
        </div>
      </div>

      <!-- 应用网格 -->
      <el-row v-if="filteredApps.length" :gutter="16" class="ws-grid">
        <el-col v-for="a in filteredApps" :key="a.id" :xs="24" :sm="12" :md="8" :lg="6">
          <div class="ws-app-card" @click="openRun(a)">
            <div class="ws-app-card__head">
              <div class="ws-app-card__icon" :style="{ background: iconBg(a.view_type) }">
                <el-icon :size="20"><component :is="viewIcon(a.view_type)" /></el-icon>
              </div>
              <div class="ws-app-card__title">
                <div class="ws-app-card__name">{{ a.name }}</div>
                <el-tag size="small" :type="viewTag(a.view_type)" effect="plain">
                  {{ viewLabel(a.view_type) }}
                </el-tag>
              </div>
              <el-dropdown trigger="click" @command="(c: string) => onCardCmd(a, c)">
                <el-button link :icon="MoreFilled" class="ws-app-card__more" @click.stop />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="run" :icon="VideoPlay">打开</el-dropdown-item>
                    <el-dropdown-item command="edit" :icon="Edit">编辑</el-dropdown-item>
                    <el-dropdown-item
                      command="delete"
                      :icon="Delete"
                      divided
                      style="color: var(--el-color-danger)"
                    >
                      删除
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div class="ws-app-card__obj">
              <el-icon><Collection /></el-icon>
              <span>{{ a.object_table }}</span>
            </div>
            <div class="ws-app-card__cols">
              <el-tag
                v-for="c in a.columns"
                :key="c"
                size="small"
                effect="plain"
                class="ws-col-tag"
              >
                {{ c }}
              </el-tag>
              <span v-if="!a.columns?.length" class="ws-app-card__nocols">
                未选字段（预览展示全部列）
              </span>
            </div>
            <div class="ws-app-card__foot">
              <el-button type="primary" size="small" :icon="View" @click.stop="openRun(a)">
                打开
              </el-button>
              <el-button size="small" :icon="Edit" @click.stop="openEdit(a)">编辑</el-button>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 空状态引导 -->
      <el-empty v-else v-loading="loading" description="还没有对象应用">
        <div class="ws-empty-suggest">
          <p>用一点数据就能做成一个可用的应用，试试点右上角「新建应用」</p>
        </div>
      </el-empty>
    </el-card>

    <!-- 新建/编辑抽屉 -->
    <el-drawer
      v-model="createVisible"
      :title="editingId ? '编辑对象应用' : '新建对象应用'"
      size="520px"
    >
      <el-form v-loading="loadingObjects" label-width="84px" class="ws-form">
        <el-form-item label="应用名称" required>
          <el-input v-model="form.name" placeholder="如：摄像头监控看板" />
        </el-form-item>
        <el-form-item label="业务对象" required>
          <el-select
            v-model="form.object_table"
            filterable
            placeholder="搜索并选择一个业务对象"
            style="width: 100%"
            @change="onObjectChange"
          >
            <el-option
              v-for="o in objectOptions"
              :key="o.table"
              :value="o.table"
              :label="`${o.label || o.table}（${o.table}）`"
            />
          </el-select>
          <div class="ws-form-hint">选对象后自动带出它的字段</div>
        </el-form-item>
        <el-form-item label="视图类型">
          <div class="ws-view-opts">
            <div
              v-for="v in viewOptions"
              :key="v.value"
              class="ws-view-opt"
              :class="{ 'is-active': form.view_type === v.value }"
              @click="form.view_type = v.value"
            >
              <el-icon :size="18"><component :is="v.icon" /></el-icon>
              <span>{{ v.label }}</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="展示字段">
          <el-checkbox-group v-if="currentFields.length" v-model="form.columns" class="ws-fields">
            <el-checkbox v-for="f in currentFields" :key="f.name" :value="f.name" class="ws-field">
              <span class="ws-field__name">{{ f.name }}</span>
              <span v-if="f.label" class="ws-field__label">{{ f.label }}</span>
              <el-tag v-if="f.sensitive" size="small" type="danger" effect="plain">敏感</el-tag>
            </el-checkbox>
          </el-checkbox-group>
          <el-empty v-else :image-size="40" description="请先选择业务对象" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-drawer>

    <!-- ===== 应用运行视图：表格 / 看板 / 表单 ===== -->
    <el-drawer
      v-model="runVisible"
      :title="`${runApp?.name || ''}`"
      size="94%"
      destroy-on-close
      class="ws-run-drawer"
    >
      <div v-loading="runLoading" class="ws-run">
        <!-- 顶部 App Bar：记录数 + 视图切换(segmented) + 搜索/分组/刷新 -->
        <div class="ws-run__bar">
          <div class="ws-run__meta">
            <span class="ws-run__obj">
              <el-icon><Collection /></el-icon>
              <b>{{ runApp?.object_table }}</b>
            </span>
            <span class="ws-run__count">{{ runRows.length }} 条记录</span>
          </div>
          <div class="ws-run__switch">
            <el-tag
              v-for="v in RUN_VIEWS"
              :key="v"
              class="ws-run__switch-item"
              :class="{ 'is-active': runView === v }"
              :effect="runView === v ? 'dark' : 'plain'"
              :type="runView === v ? 'primary' : 'info'"
              style="cursor: pointer"
              @click="runView = v"
            >
              <el-icon :size="14"><component :is="viewIcon(v)" /></el-icon>
              {{ viewLabel(v) }}
            </el-tag>
          </div>
          <div class="ws-run__tools">
            <el-input
              v-if="runView === 'table'"
              v-model="runKeyword"
              placeholder="搜索表格"
              clearable
              :prefix-icon="Search"
              style="width: 200px"
            />
            <el-select
              v-else-if="runView === 'kanban'"
              v-model="runGroupBy"
              placeholder="看板分组字段"
              clearable
              style="width: 200px"
            >
              <el-option v-for="c in runCols" :key="c" :label="colLabel(c)" :value="c" />
            </el-select>
            <el-tooltip content="刷新数据" placement="top">
              <el-button circle :icon="Refresh" @click="reloadRun" />
            </el-tooltip>
          </div>
        </div>

        <!-- 表格视图 -->
        <div v-if="runView === 'table'" class="ws-run__table">
          <div class="ws-table-stats">
            <span>
              共
              <b>{{ filteredRunRows.length }}</b>
              条
            </span>
            <span v-if="runKeyword" class="ws-table-stats__filter">已筛选</span>
          </div>
          <el-table
            :data="pagedRunRows"
            border
            stripe
            size="small"
            max-height="66vh"
            class="ws-table"
          >
            <template #empty>
              <el-empty :image-size="60" description="暂无数据" />
            </template>
            <el-table-column
              v-for="c in filteredRunCols"
              :key="c"
              :label="colLabel(c)"
              :prop="c"
              min-width="150"
              show-overflow-tooltip
            />
          </el-table>
          <div class="ws-table-pager">
            <el-pagination
              v-model:current-page="runPage"
              :page-size="runPageSize"
              :total="filteredRunRows.length"
              layout="total, sizes, prev, pager, next"
              background
              small
            />
          </div>
        </div>

        <!-- 看板视图：按分组字段分列，支持拖拽 -->
        <div v-else-if="runView === 'kanban'" class="ws-run__kanban">
          <div v-if="runCols.length" class="ws-kanban">
            <div
              v-for="g in kanbanGroups"
              :key="g.key"
              class="ws-kb-col"
              :style="{ '--kb-color': cardColor(g.key) }"
              @dragover.prevent
              @drop="onDrop(g.key)"
            >
              <div class="ws-kb-head">
                <span class="ws-kb-head__title">{{ g.key === "" ? "未分组" : String(g.key) }}</span>
                <span class="ws-kb-head__count">{{ g.items.length }}</span>
              </div>
              <div class="ws-kb-cards">
                <div
                  v-for="(row, i) in g.items"
                  :key="i"
                  draggable="true"
                  class="ws-kb-card"
                  @dragstart="onDragStart(row)"
                >
                  <div class="ws-kb-card__top">
                    <div class="ws-kb-card__main">
                      {{ row[runGroupBy] ?? row[runCols[0]] ?? "—" }}
                    </div>
                    <el-dropdown trigger="click" @command="(c: string) => onCardRowCmd(g, row, c)">
                      <el-icon class="ws-kb-card__more"><MoreFilled /></el-icon>
                      <template #dropdown>
                        <el-dropdown-menu>
                          <el-dropdown-item command="move">移动到此列</el-dropdown-item>
                        </el-dropdown-menu>
                      </template>
                    </el-dropdown>
                  </div>
                  <div class="ws-kb-card__tags">
                    <el-tag
                      v-for="c in runSubCols"
                      :key="c"
                      size="small"
                      effect="plain"
                      class="ws-kb-tag"
                    >
                      {{ row[c] ?? "—" }}
                    </el-tag>
                  </div>
                  <div class="ws-kb-card__foot">
                    <span class="ws-kb-avatar">
                      {{ (row[runGroupBy] ?? row[runCols[0]] ?? "?").toString().charAt(0) }}
                    </span>
                    <span class="ws-kb-foot-text">{{ runApp?.object_table }}</span>
                  </div>
                </div>
                <div v-if="!g.items.length" class="ws-kb-card ws-kb-card--empty">拖卡片到这里</div>
              </div>
            </div>
          </div>
          <el-empty v-else description="该对象没有可用字段" />
        </div>

        <!-- 表单视图：分组 + 两列 + 必填，提交写入 -->
        <div v-else class="ws-run__form">
          <div v-if="runFields.length">
            <div class="ws-form-section">
              <span class="ws-form-section__title">{{ runApp?.object_table }} · 新增记录</span>
            </div>
            <el-form :model="formData" label-position="top" class="ws-run-form">
              <el-row :gutter="16">
                <el-col v-for="f in runFields" :key="f.name" :xs="24" :sm="12">
                  <el-form-item :label="colLabel(f.name)" :required="fieldRequired(f)">
                    <el-input
                      v-if="!isNum(f) && !isDate(f) && !isBool(f)"
                      v-model="formData[f.name]"
                      clearable
                    />
                    <el-input-number
                      v-else-if="isNum(f)"
                      v-model="formData[f.name]"
                      :controls="false"
                      style="width: 100%"
                    />
                    <el-date-picker
                      v-else-if="isDate(f)"
                      v-model="formData[f.name]"
                      type="datetime"
                      style="width: 100%"
                    />
                    <el-switch v-else-if="isBool(f)" v-model="formData[f.name]" />
                  </el-form-item>
                </el-col>
              </el-row>
              <div class="ws-run-form-actions">
                <el-button type="primary" :loading="formSubmitting" @click="submitForm">
                  保存到对象表
                </el-button>
                <el-button @click="formData = {}">清空</el-button>
                <span class="ws-run-form-hint">演示：仅 ont_orders 支持写入</span>
              </div>
            </el-form>
          </div>
          <el-empty v-else :image-size="60" description="该应用未配置字段" />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Collection,
  Delete,
  Edit,
  Grid,
  Menu,
  MoreFilled,
  Plus,
  Refresh,
  Search,
  VideoPlay,
  View,
} from "@element-plus/icons-vue";

import {
  deleteWorkshopApp,
  getWorkshopList,
  getWorkshopObjects,
  saveWorkshopApp,
  submitWorkshopApp,
  workshopPreview,
} from "@/api/module_ai/query";

defineOptions({ name: "AiWorkshop" });

const loading = ref(false);
const apps = ref<any[]>([]);
const keyword = ref("");

// 对象/字段元数据
const objectOptions = ref<any[]>([]);
const loadingObjects = ref(false);

// 新建/编辑
const createVisible = ref(false);
const editingId = ref<number | null>(null);
const saving = ref(false);
const form = ref<any>({
  name: "",
  object_table: "",
  view_type: "table",
  columns: [],
});
const viewOptions = [
  { value: "table", label: "表格", icon: Grid },
  { value: "kanban", label: "看板", icon: Menu },
  { value: "form", label: "表单", icon: Edit },
];

// 运行视图
const runVisible = ref(false);
const runApp = ref<any>(null);
const runLoading = ref(false);
const runRows = ref<any[]>([]);
const runCols = ref<string[]>([]);
const runView = ref<"table" | "kanban" | "form">("table");
//: 运行视图形态（用 as const 保留字面量类型，避免 v-for 变量退化成 string）
const RUN_VIEWS = ["table", "kanban", "form"] as const;
const runKeyword = ref("");
const runGroupBy = ref("");
const runPage = ref(1);
const runPageSize = 20;
// 表单视图状态
const runFields = ref<any[]>([]);
const formData = ref<any>({});
const formSubmitting = ref(false);

const filteredApps = computed(() => {
  if (!keyword.value) return apps.value;
  return apps.value.filter((a) => (a.name || "").includes(keyword.value));
});

const currentFields = computed(() => {
  const obj = objectOptions.value.find((o) => o.table === form.value.object_table);
  return (obj?.fields || []).filter((f: any) => !f.sensitive || true);
});

// ---- 视图映射 ----
function viewLabel(v: string) {
  return { table: "表格", kanban: "看板", form: "表单" }[v] || v;
}
function viewTag(v: string) {
  const MAP: Record<string, "success" | "warning" | "primary" | "info"> = {
    table: "success",
    kanban: "warning",
    form: "primary",
  };
  return MAP[v] || "info";
}
function viewIcon(v: string) {
  return { table: Grid, kanban: Menu, form: Edit }[v] || Grid;
}
function iconBg(v: string) {
  return { table: "#f0f9eb", kanban: "#fdf6ec", form: "#ecf5ff" }[v] || "#f4f4f5";
}

// 运行数据
const filteredRunRows = computed(() => {
  const kw = runKeyword.value.trim().toLowerCase();
  if (!kw) return runRows.value;
  return runRows.value.filter((r) =>
    runCols.value.some((c) =>
      String(r[c] ?? "")
        .toLowerCase()
        .includes(kw)
    )
  );
});
const pagedRunRows = computed(() => {
  const start = (runPage.value - 1) * runPageSize;
  return filteredRunRows.value.slice(start, start + runPageSize);
});
const filteredRunCols = computed<string[]>(() => {
  if (!runApp.value?.columns?.length) return runCols.value;
  return runApp.value.columns;
});
const runSubCols = computed(() => {
  const all = filteredRunCols.value;
  const main = runGroupBy.value || all[0];
  return all.filter((c) => c !== main).slice(0, 3);
});
const kanbanGroups = computed(() => {
  const key = runGroupBy.value || runCols.value[0] || "id";
  const map: Record<string, any[]> = {};
  for (const r of runRows.value) {
    const k = r[key] ?? "";
    (map[k] ||= []).push(r);
  }
  return Object.keys(map).map((k) => ({ key: k, items: map[k] }));
});

function colLabel(c: string) {
  const obj = objectOptions.value.find((o) => o.table === runApp.value?.object_table);
  const f = obj?.fields?.find((x: any) => x.name === c);
  return f?.label ? `${c} · ${f.label}` : c;
}
function cardColor(k: any) {
  const palette = [
    "var(--el-color-primary)",
    "var(--el-color-success)",
    "var(--el-color-warning)",
    "var(--el-color-danger)",
    "#909399",
    "#9b59b6",
    "#2f9e95",
  ];
  let h = 0;
  const s = String(k ?? "");
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

// ---- 看板拖拽 ----
const dragRow = ref<any>(null);
function onDragStart(row: any) {
  dragRow.value = row;
}
function onDrop(key: any) {
  if (!dragRow.value) return;
  const k = runGroupBy.value || runCols.value[0] || "";
  if (k) dragRow.value[k] = key;
  dragRow.value = null;
}
function onCardRowCmd(_g: any, row: any, cmd: string) {
  if (cmd === "move") {
    // 演示：将卡片移动到「未分组」列（拖拽已支持跨列，这里仅提示）
    ElMessage.info("拖动卡片列头即可移动（演示，刷新还原）");
  }
}

// ---- 表单字段类型 ----
function isNum(field: any) {
  return /(int|numeric|double|real|decimal)/i.test(field.type || "");
}
function isDate(field: any) {
  return /(timestamp|date|time)/i.test(field.type || "");
}
function isBool(field: any) {
  return /bool/i.test(field.type || "");
}
function fieldRequired(field: any) {
  return /(name|id|no)$/i.test(field.name || "");
}

// ---- 加载 ----
async function load() {
  loading.value = true;
  try {
    const r = await getWorkshopList();
    apps.value = r.data?.data || [];
  } catch {
    apps.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadObjects() {
  loadingObjects.value = true;
  try {
    const r = await getWorkshopObjects();
    objectOptions.value = r.data?.data || [];
  } catch {
    objectOptions.value = [];
  } finally {
    loadingObjects.value = false;
  }
}

function openCreate() {
  editingId.value = null;
  form.value = { name: "", object_table: "", view_type: "table", columns: [] };
  createVisible.value = true;
  loadObjects();
}

function openEdit(a: any) {
  editingId.value = a.id;
  form.value = {
    name: a.name || "",
    object_table: a.object_table || "",
    view_type: a.view_type || "table",
    columns: [...(a.columns || [])],
  };
  createVisible.value = true;
  loadObjects();
}

function onObjectChange(table: string) {
  const obj = objectOptions.value.find((o) => o.table === table);
  if (!obj) return;
  form.value.columns = (obj.fields || []).map((f: any) => f.name);
  if (!form.value.name) form.value.name = `${obj.label || obj.table}`;
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning("请填写应用名称");
  if (!form.value.object_table) return ElMessage.warning("请选择业务对象");
  saving.value = true;
  try {
    await saveWorkshopApp({
      id: editingId.value || undefined,
      name: form.value.name,
      object_table: form.value.object_table,
      view_type: form.value.view_type,
      columns: form.value.columns,
      enabled: true,
    });
    ElMessage.success(editingId.value ? "已更新" : "已创建");
    createVisible.value = false;
    load();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

// 打开应用运行视图
async function openRun(a: any) {
  runApp.value = a;
  runVisible.value = true;
  runView.value = (a.view_type === "form" ? "form" : a.view_type) as "table" | "kanban" | "form";
  runKeyword.value = "";
  runGroupBy.value = "";
  runPage.value = 1;
  runLoading.value = true;
  await reloadRun();
}

async function reloadRun() {
  if (!runApp.value) return;
  runLoading.value = true;
  try {
    const r = await workshopPreview(runApp.value.id, 200);
    const d = r.data?.data;
    if (d?.ok) {
      runCols.value = d.columns || [];
      runRows.value = (d.rows || []).map((row: any[]) =>
        Object.fromEntries((d.columns || []).map((c: string, i: number) => [c, row[i]]))
      );
      runGroupBy.value =
        ["status", "location", "state", "type", "category"].find((f) =>
          (runApp.value.columns || []).includes(f)
        ) ||
        runApp.value.columns?.[0] ||
        runCols.value[0] ||
        "";
      // 表单字段：基于实际列，类型从对象元数据补
      let obj = objectOptions.value.find((o) => o.table === runApp.value.object_table);
      if (!obj) {
        await loadObjects();
        obj = objectOptions.value.find((o) => o.table === runApp.value.object_table);
      }
      const fmap = new Map((obj?.fields || []).map((f: any) => [f.name, f]));
      runFields.value = runCols.value.map(
        (c: string) => fmap.get(c) || { name: c, type: "", label: "" }
      );
      formData.value = {};
    } else {
      runCols.value = [];
      runRows.value = [];
      ElMessage.warning(d?.msg || "加载失败");
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    runLoading.value = false;
  }
}

async function submitForm() {
  if (!runApp.value) return;
  formSubmitting.value = true;
  try {
    await submitWorkshopApp(runApp.value.id, formData.value);
    ElMessage.success("已保存到对象表");
    await reloadRun();
  } catch (e: any) {
    ElMessage.error(e?.message || "提交失败");
  } finally {
    formSubmitting.value = false;
  }
}

async function onCardCmd(a: any, cmd: string) {
  if (cmd === "run") return openRun(a);
  if (cmd === "edit") return openEdit(a);
  if (cmd === "delete") {
    await ElMessageBox.confirm(`将删除应用「${a.name}」，此操作不可恢复。是否继续？`, "删除确认", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    });
    await deleteWorkshopApp(a.id);
    ElMessage.success("已删除");
    load();
  }
}

onMounted(() => {
  load();
});
</script>

<style lang="scss">
.app-container.ai-workshop-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
</style>

<style lang="scss" scoped>
.ai-workshop-page .ws-shell {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.ai-workshop-page .ws-shell :deep(.el-card__body) {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: auto;
}

/* 说明横幅 */
.ws-intro {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 16px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
}
.ws-intro__icon {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 10px;
}
.ws-intro__title {
  margin-bottom: 4px;
  font-weight: 600;
}
.ws-intro__desc {
  margin-bottom: 8px;
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.ws-intro__steps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* 列表工具条 */
.ws-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.ws-toolbar__count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.ws-toolbar__right {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 应用卡片 */
.ws-grid {
  row-gap: 16px;
}
.ws-app-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 18px;
  cursor: pointer;
  background: var(--el-color-white);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  transition:
    box-shadow 0.2s,
    transform 0.2s,
    border-color 0.2s;
  &:hover {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 6px 18px rgb(0 0 0 / 8%);
    transform: translateY(-2px);
  }
}
.ws-app-card__head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
/* 「更多」：link 图标按钮（去掉 circle 边框，与工作台卡片一致） */
.ws-app-card__more {
  color: var(--el-text-color-secondary);
}
.ws-app-card__more:hover {
  color: var(--el-color-primary);
}
.ws-app-card__icon {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
}
.ws-app-card__title {
  flex: 1;
  min-width: 0;
}
.ws-app-card__name {
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  line-height: 1.5;
  white-space: nowrap;
}
.ws-app-card__obj {
  display: flex;
  gap: 6px;
  align-items: center;
  margin: 12px 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  white-space: nowrap;
}
.ws-app-card__cols {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 24px;
  margin-bottom: 12px;
}
.ws-col-tag {
  max-width: 100%;
}
.ws-app-card__nocols {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
.ws-app-card__foot {
  display: flex;
  gap: 8px;
  padding-top: 10px;
  margin-top: auto;
  border-top: 1px solid var(--el-border-color-lighter);
}
.ws-empty-suggest {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 新建表单 */
.ws-form-hint {
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}
.ws-view-opts {
  display: flex;
  gap: 10px;
}
.ws-view-opt {
  display: flex;
  flex: 1;
  gap: 6px;
  align-items: center;
  justify-content: center;
  padding: 10px 0;
  color: var(--el-text-color-regular);
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  transition: all 0.2s;
  &.is-active {
    font-weight: 600;
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary);
  }
}
.ws-fields {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  max-height: 300px;
  overflow: auto;
}
.ws-field {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-right: 0;
  white-space: nowrap;
}
.ws-field__name {
  font-weight: 600;
}
.ws-field__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ===== 运行视图 ===== */
.ws-run {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.ws-run__bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  padding-bottom: 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ws-run__meta {
  display: flex;
  gap: 10px;
  align-items: center;
}
.ws-run__obj {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: var(--el-font-size-base);
  font-weight: 600;
}
.ws-run__count {
  padding: 2px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-radius: 10px;
}
.ws-run__switch {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.ws-run__switch-item {
  display: inline-flex !important;
  gap: 4px;
  align-items: center;
  cursor: pointer;
  border-radius: 6px !important;
}
.ws-run__tools {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

/* 表格 */
.ws-table-stats {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  b {
    color: var(--el-text-color-primary);
  }
}
.ws-table-stats__filter {
  color: var(--el-color-primary);
}
.ws-run__table :deep(.el-table) {
  border-radius: 10px;
}
.ws-run__table :deep(.el-table th.el-table__cell) {
  font-weight: 600;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
}
.ws-run__table :deep(.el-table__row) {
  &:hover > td {
    background: var(--el-color-primary-light-9);
  }
}
.ws-table-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

/* 看板 */
.ws-run__kanban {
  flex: 1;
  overflow: auto;
}
.ws-kanban {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding-bottom: 12px;
  overflow-x: auto;
}
.ws-kb-col {
  position: relative;
  display: flex;
  flex: 0 0 240px;
  flex-direction: column;
  min-height: 200px;
  padding: 12px 10px 10px;
  overflow: hidden;
  background: var(--el-fill-color-light);
  border-radius: 12px;
  transition: background 0.2s;
}
.ws-kb-head {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  margin-bottom: 10px;
  font-weight: 600;
  color: #fff;
  background: var(--kb-color, var(--el-color-primary));
  border-radius: 8px;
}
.ws-kb-head__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-kb-head__count {
  margin-left: auto;
  font-size: 12px;
  color: #fff;
  opacity: 0.85;
}
.ws-kb-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ws-kb-card {
  padding: 10px 12px;
  cursor: grab;
  background: var(--el-color-white);
  border-radius: 10px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 6%);
  transition:
    box-shadow 0.2s,
    transform 0.2s;
  &:hover {
    box-shadow: 0 4px 12px rgb(0 0 0 / 10%);
    transform: translateY(-1px);
  }
  &:active {
    cursor: grabbing;
  }
}
.ws-kb-card__top {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  justify-content: space-between;
}
.ws-kb-card__main {
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 600;
  white-space: nowrap;
}
.ws-kb-card__more {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.ws-kb-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.ws-kb-tag {
  max-width: 100%;
}
.ws-kb-card__foot {
  display: flex;
  gap: 6px;
  align-items: center;
  padding-top: 8px;
  margin-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.ws-kb-avatar {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: 12px;
  color: #fff;
  background: var(--kb-color, var(--el-color-primary));
  border-radius: 50%;
}
.ws-kb-foot-text {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.ws-kb-card--empty {
  color: var(--el-text-color-placeholder);
  text-align: center;
  cursor: default;
}

/* 表单 */
.ws-run__form {
  max-width: 860px;
}
.ws-form-section {
  margin-bottom: 14px;
}
.ws-form-section__title {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ws-run-form {
  padding: 20px 24px 8px;
  background: var(--el-color-white);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
}
.ws-run-form :deep(.el-form-item__label) {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.ws-run-form-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin: 8px 0 16px;
}
.ws-run-form-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
