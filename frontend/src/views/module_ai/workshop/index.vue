<!-- 无代码应用 Workshop：说明引导 + 对象应用卡片 + 页内新建/预览/删除 -->
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
          <div class="ws-app-card">
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
                <el-button size="small" circle :icon="MoreFilled" @click.stop />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="preview">预览</el-dropdown-item>
                    <el-dropdown-item command="edit">编辑</el-dropdown-item>
                    <el-dropdown-item command="delete" style="color: #f56c6c" divided>
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
              <el-button type="primary" size="small" :icon="View" @click="preview(a)">
                预览
              </el-button>
              <el-button size="small" :icon="Edit" @click="openEdit(a)">编辑</el-button>
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

    <!-- 预览抽屉 -->
    <el-drawer v-model="previewVisible" :title="`预览 · ${previewApp?.name || ''}`" size="720px">
      <el-table :data="previewRows" border stripe size="small" max-height="70vh">
        <template #empty>
          <el-empty :image-size="60" description="暂无数据或读取失败" />
        </template>
        <el-table-column
          v-for="c in previewCols"
          :key="c"
          :label="c"
          :prop="c"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <div class="ws-preview-foot">共读取 {{ previewRows.length }} 行（最多 50 行）</div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Collection,
  Edit,
  Grid,
  Menu,
  MoreFilled,
  Plus,
  Search,
  View,
} from "@element-plus/icons-vue";

import {
  deleteWorkshopApp,
  getWorkshopList,
  getWorkshopObjects,
  saveWorkshopApp,
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

// 预览
const previewVisible = ref(false);
const previewApp = ref<any>(null);
const previewCols = ref<string[]>([]);
const previewRows = ref<any[]>([]);

const filteredApps = computed(() => {
  if (!keyword.value) return apps.value;
  return apps.value.filter((a) => (a.name || "").includes(keyword.value));
});

const currentFields = computed(() => {
  const obj = objectOptions.value.find((o) => o.table === form.value.object_table);
  return (obj?.fields || []).filter((f: any) => !f.sensitive || true);
});

// ---- 视图映射：table→表格、kanban→看板、form→表单 ----
function viewLabel(v: string) {
  return { table: "表格", kanban: "看板", form: "表单" }[v] || v;
}
function viewTag(v: string) {
  return { table: "success", kanban: "warning", form: "primary" }[v] || "info";
}
function viewIcon(v: string) {
  return { table: Grid, kanban: Menu, form: Edit }[v] || Grid;
}
function iconBg(v: string) {
  return { table: "#f0f9eb", kanban: "#fdf6ec", form: "#ecf5ff" }[v] || "#f4f4f5";
}

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
  form.value = {
    name: "",
    object_table: "",
    view_type: "table",
    columns: [],
  };
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
  // 默认全选该对象字段；若无字段则留空
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

async function preview(a: any) {
  try {
    const r = await workshopPreview(a.id, 50);
    const d = r.data?.data;
    previewApp.value = a;
    if (d?.ok) {
      previewCols.value = d.columns || [];
      previewRows.value = (d.rows || []).map((row: any[]) =>
        Object.fromEntries((d.columns || []).map((c: string, i: number) => [c, row[i]]))
      );
    } else {
      previewCols.value = [];
      previewRows.value = [];
      ElMessage.warning(d?.msg || "预览失败");
    }
    previewVisible.value = true;
  } catch (e: any) {
    ElMessage.error(e?.message || "预览失败");
  }
}

async function onCardCmd(a: any, cmd: string) {
  if (cmd === "preview") return preview(a);
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

<style lang="scss" scoped>
.ai-workshop-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ai-workshop-page .ws-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.ai-workshop-page .ws-shell :deep(.el-card__body) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

/* 说明横幅 */
.ws-intro {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-light);
  margin-bottom: 16px;
}
.ws-intro__icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}
.ws-intro__title {
  font-weight: 600;
  margin-bottom: 4px;
}
.ws-intro__desc {
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 8px;
}
.ws-intro__steps {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* 工具条 */
.ws-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.ws-toolbar__count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.ws-toolbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
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
  align-items: flex-start;
  gap: 12px;
}
.ws-app-card__icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}
.ws-app-card__title {
  min-width: 0;
  flex: 1;
}
.ws-app-card__name {
  font-weight: 600;
  line-height: 1.5;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-app-card__obj {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 8px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
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
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.ws-empty-suggest {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

/* 表单 */
.ws-form-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.ws-view-opts {
  display: flex;
  gap: 10px;
}
.ws-view-opt {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 0;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  cursor: pointer;
  color: var(--el-text-color-regular);
  transition: all 0.2s;
  &.is-active {
    border-color: var(--el-color-primary);
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    font-weight: 600;
  }
}
.ws-fields {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 300px;
  overflow: auto;
}
.ws-field {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-right: 0;
  white-space: nowrap;
}
.ws-field__name {
  font-weight: 600;
}
.ws-field__label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.ws-preview-foot {
  margin-top: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
