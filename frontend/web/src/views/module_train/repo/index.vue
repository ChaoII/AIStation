<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      ref="searchBarRef"
      v-model="searchForm"
      :items="searchItems"
      :rules="searchBarRules"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      :default-expanded="false"
      @search="handleSearch"
      @reset="onResetSearch"
    />

    <ElCard shadow="hover" class="fa-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <FaTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      >
        <template #left>
          <FaTableHeaderLeft
            :remove-ids="selectedIds"
            :perm-create="['module_train:model:create']"
            :perm-delete="['module_train:model:delete']"
            :delete-loading="batchDeleting"
            @add="openCreateDialog"
            @delete="handleBatchDelete"
          />
        </template>
      </FaTableHeader>

      <FaTable
        ref="faTableRef"
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @selection-change="onTableSelectionChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <ElDrawer v-model="versionsDrawer.visible" :title="`${versionsDrawer.repoName} · 版本列表`" size="600px">
      <ElTable v-loading="versionsLoading" :data="versionItems" border stripe>
        <ElTableColumn prop="version" label="版本" width="80" />
        <ElTableColumn label="mAP50" width="100" align="center">
          <template #default="{ row }">{{ row.metrics?.map50 != null ? Number(row.metrics.map50).toFixed(3) : "-" }}</template>
        </ElTableColumn>
        <ElTableColumn prop="format" label="格式" width="110" align="center" />
        <ElTableColumn prop="created_time" label="创建时间" min-width="150" show-overflow-tooltip />
        <ElTableColumn label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <ElButton link type="primary" size="small" @click="goEval(versionsDrawer.repoId, row)">评估</ElButton>
            <ElButton link type="success" size="small" @click="goPredict(versionsDrawer.repoId, row)">推理</ElButton>
            <ElButton link type="warning" size="small" @click="openExport(row)">导出</ElButton>
            <ElButton link type="info" size="small" @click="downloadVersion(row)">下载</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>
      <ElEmpty v-if="!versionsLoading && versionItems.length === 0" :image-size="60" description="该仓库暂无版本" />
    </ElDrawer>

    <ModelExportDialog ref="exportDialogRef" :model-id="exportModelId" :model-name="exportModelName" @done="refreshData" />

    <ElDialog v-model="createDialogVisible" title="新建模型仓库" width="500px">
      <ElForm label-width="120px">
        <ElFormItem label="模型名称" required>
          <ElInput v-model="createForm.name" placeholder="如: 钢板缺陷检测" />
        </ElFormItem>
        <ElFormItem label="框架" required>
          <ElSelect v-model="createForm.framework" style="width:100%" placeholder="选择训练框架">
            <ElOption label="Ultralytics" value="ultralytics" />
            <ElOption label="PaddleX" value="paddlex" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="描述">
          <ElInput v-model="createForm.description" type="textarea" :rows="2" placeholder="可选" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="createDialogVisible = false">取消</ElButton>
        <ElButton type="primary" :loading="creatingRepo" @click="handleCreateRepo">创建</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElTag } from "element-plus";
import { useTable } from "@/hooks/core/useTable";
import { useTableSelection } from "@/hooks/core/useTableSelection";
import { useAuth } from "@/hooks/core/useAuth";
import { confirmDelete, confirmBatchDelete } from "@/hooks/core/useConfirm";
import { cleanEmptyArrayParams } from "@/utils/query";
import { renderTableOperationCell, type TableOperationAction } from "@utils";
import type { ColumnOption } from "@/types/component";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import ModelExportDialog from "@/components/model-export-dialog/index.vue";
import { TrainAPI, type TrainModelRepoTable, type TrainModelVersionTable, type TablePageQuery } from "@/api/module_train";

defineOptions({ name: "TrainModelRepo", inheritAttrs: false });

const route = useRoute();
const router = useRouter();
const { hasAuth } = useAuth();

function frameworkTag(fw?: string) {
  return h(ElTag, { type: fw === "ultralytics" ? "success" : "primary" }, () =>
    fw === "ultralytics" ? "YOLO" : "PaddleX"
  );
}

// ── 版本抽屉 / 版本缓存 ──
const versionsDrawer = reactive({ visible: false, repoId: 0, repoName: "" });
const versionItems = ref<TrainModelVersionTable[]>([]);
const versionsLoading = ref(false);
const versionCache = reactive<Record<number, TrainModelVersionTable[]>>({});
const loadingRepoIds = new Set<number>();

async function openVersionsDrawer(repo: TrainModelRepoTable) {
  versionsDrawer.repoId = repo.id!;
  versionsDrawer.repoName = repo.name || `仓库 #${repo.id}`;
  versionsDrawer.visible = true;
  versionsLoading.value = true;
  versionItems.value = [];
  try {
    const r = await TrainAPI.listModelVersions(repo.id!);
    versionItems.value = r.data?.data || [];
    versionCache[repo.id!] = versionItems.value;
  } catch {
    versionItems.value = [];
  } finally {
    versionsLoading.value = false;
  }
}

async function preloadRepoVersions(repo: TrainModelRepoTable) {
  const repoId = repo.id;
  if (!repoId || versionCache[repoId] || loadingRepoIds.has(repoId)) return;
  loadingRepoIds.add(repoId);
  try {
    const r = await TrainAPI.listModelVersions(repoId);
    versionCache[repoId] = r.data?.data || [];
  } catch {
    /* */
  } finally {
    loadingRepoIds.delete(repoId);
  }
}

function versionCountCell(row: TrainModelRepoTable) {
  const count = row.version_count ?? 0;
  return h("span", { style: "color:var(--el-color-primary);cursor:pointer", onClick: () => openVersionsDrawer(row) }, `${count} 个版本`);
}
function latestVersionCell(row: TrainModelRepoTable) {
  const versions = versionCache[row.id!];
  if (!versions?.length) return h("span", { style: "color:var(--el-text-color-placeholder)" }, "—");
  return h("span", { style: "font-family:monospace;font-size:12px" }, versions[0].version);
}

// ── 跳转 ──
function goEval(repoId: number, version?: TrainModelVersionTable) {
  const q = [`model_repo_id=${repoId}`];
  if (version?.id) q.push(`model_id=${version.id}`);
  router.push(`/train/eval?${q.join("&")}`);
}
function goPredict(repoId: number, version?: TrainModelVersionTable) {
  const q = [`model_repo_id=${repoId}`];
  if (version?.id) q.push(`model_id=${version.id}`);
  router.push(`/train/predict?${q.join("&")}`);
}
function goTrain(row: TrainModelRepoTable) {
  router.push(`/train/task?base_model_id=${row.latest_version_id ?? ""}&framework=${row.framework}`);
}

// ── 行操作 ──
function buildRowActions(row: TrainModelRepoTable): TableOperationAction[] {
  const all: TableOperationAction[] = [
    {
      key: "versions",
      label: "查看版本",
      artType: "view",
      icon: "ri:folder-open-line",
      perm: "module_train:model:query",
      run: () => openVersionsDrawer(row),
    },
    {
      key: "train",
      label: "去训练",
      artType: "view",
      icon: "ri:play-circle-line",
      iconColor: "var(--el-color-primary)",
      perm: "module_train:task:create",
      run: () => goTrain(row),
    },
    {
      key: "eval",
      label: "去评估",
      artType: "view",
      icon: "ri:bar-chart-box-line",
      perm: "module_train:eval:create",
      run: () => goEval(row.id!),
    },
    {
      key: "delete",
      label: "删除",
      artType: "delete",
      icon: "ri:delete-bin-4-line",
      perm: "module_train:model:delete",
      run: () => deleteRepoRow(row),
    },
  ];
  return all.filter(a => (a.perm == null ? true : hasAuth(a.perm)));
}

// ── 搜索 ──
const searchForm = ref<{ name?: string; framework?: string }>({ name: undefined, framework: undefined });
const showSearchBar = ref(true);
const searchBarRef = ref<InstanceType<typeof FaSearchBar> | null>(null);
const searchBarRules: Record<string, unknown> = {};

const searchItems = computed<SearchFormItem[]>(() => [
  { label: "模型名称", key: "name", type: "input", placeholder: "请输入模型名称", clearable: true, span: 6 },
  {
    label: "框架",
    key: "framework",
    type: "select",
    props: {
      placeholder: "请选择框架",
      clearable: true,
      options: [
        { label: "Ultralytics", value: "ultralytics" },
        { label: "PaddleX", value: "paddlex" },
      ],
    },
    span: 6,
  },
]);

// ── 删除 ──
const faTableRef = ref<{ elTableRef?: { clearSelection: () => void } } | null>(null);
const { selectedIds, batchDeleting, onTableSelectionChange } = useTableSelection<TrainModelRepoTable>();

async function deleteRepoRow(repo: TrainModelRepoTable) {
  try {
    await confirmDelete();
    await TrainAPI.deleteModelRepos([repo.id!]);
    delete versionCache[repo.id!];
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  }
}

async function handleBatchDelete() {
  const ids = selectedIds.value;
  if (!ids.length) return;
  try {
    await confirmBatchDelete(ids.length);
    batchDeleting.value = true;
    await TrainAPI.deleteModelRepos(ids);
    ids.forEach(repoId => delete versionCache[repoId]);
    ElMessage.success("删除成功");
    faTableRef.value?.elTableRef?.clearSelection();
    await refreshRemove();
  } catch {
    // cancel
  } finally {
    batchDeleting.value = false;
  }
}

// ── 新建 ──
const createDialogVisible = ref(false);
const creatingRepo = ref(false);
const createForm = reactive({ name: "", framework: "", description: "" });

function openCreateDialog() {
  createForm.name = "";
  createForm.framework = "";
  createForm.description = "";
  createDialogVisible.value = true;
}

async function handleCreateRepo() {
  if (!createForm.name.trim()) { ElMessage.warning("请输入模型名称"); return; }
  if (!createForm.framework) { ElMessage.warning("请选择框架"); return; }
  creatingRepo.value = true;
  try {
    await TrainAPI.createModelRepo({
      name: createForm.name.trim(),
      framework: createForm.framework,
      description: createForm.description || undefined,
    });
    ElMessage.success("创建成功");
    createDialogVisible.value = false;
    await refreshData();
  } catch {
    // error toast handled globally
  } finally {
    creatingRepo.value = false;
  }
}

// ── 表格 ──
const { columns, columnChecks, data, loading, pagination, getData, replaceSearchParams, resetSearchParams, handleSizeChange, handleCurrentChange, refreshData, refreshRemove } = useTable({
  core: {
    apiFn: TrainAPI.listModelRepos,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<TrainModelRepoTable>[] => [
      { type: "selection", width: 48, fixed: "left" },
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "name", label: "模型名称", minWidth: 160, showOverflowTooltip: true },
      { prop: "framework", label: "框架", width: 100, formatter: (row: TrainModelRepoTable) => frameworkTag(row.framework) },
      { prop: "version_count", label: "版本数", width: 110, align: "center", formatter: (row: TrainModelRepoTable) => versionCountCell(row) },
      { prop: "latest_version", label: "最新版本", width: 100, align: "center", formatter: (row: TrainModelRepoTable) => latestVersionCell(row) },
      { prop: "created_time", label: "创建时间", width: 168, showOverflowTooltip: true },
      {
        prop: "operation",
        label: "操作",
        width: 280,
        fixed: "right",
        align: "right",
        formatter: (row: TrainModelRepoTable) =>
          renderTableOperationCell(buildRowActions(row), {
            wrapperClass: "inline-flex flex-wrap items-center justify-end gap-1",
          }),
      },
    ],
  },
});

// 列表加载后：预取当前页仓库的版本（供"最新版本"列），并处理 ?repo_id= 自动打开抽屉
let pendingRepoId = Number(route.query.repo_id || 0);
watch(
  data,
  (rows) => {
    const list = rows as TrainModelRepoTable[];
    if (list.length && pendingRepoId) {
      const repo = list.find(r => r.id === pendingRepoId);
      if (repo) openVersionsDrawer(repo);
      else openVersionsDrawer({ id: pendingRepoId, name: `仓库 #${pendingRepoId}` } as TrainModelRepoTable);
      pendingRepoId = 0;
    }
    list.forEach(repo => {
      if (repo.id && (repo.version_count ?? 0) > 0) preloadRepoVersions(repo);
    });
  },
  { immediate: true }
);

function handleSearch(params: { name?: string; framework?: string }) {
  replaceSearchParams(cleanEmptyArrayParams({ ...params }));
  getData();
}
function onResetSearch() {
  searchForm.value = { name: undefined, framework: undefined };
  void resetSearchParams();
}

// ── 版本操作（抽屉内） ──
const exportDialogRef = ref<InstanceType<typeof ModelExportDialog> | null>(null);
const exportModelId = ref(0);
const exportModelName = ref("");
function openExport(row: TrainModelVersionTable) {
  exportModelId.value = row.id!;
  exportModelName.value = row.name ? `${row.name} v${row.version}` : `v${row.version}`;
  exportDialogRef.value?.open();
}

async function downloadVersion(row: TrainModelVersionTable) {
  if (!row.id) return;
  try {
    const r = await TrainAPI.downloadModel(row.id);
    const url = r.data?.data?.download_url;
    if (url) window.open(url, "_blank");
    else ElMessage.warning("该版本暂无模型文件");
  } catch {
    ElMessage.error("下载失败");
  }
}
</script>
