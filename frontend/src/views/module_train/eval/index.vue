<template>
  <div class="app-container">
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, cols }">
        <div class="data-table__toolbar--left">
          <el-select v-model="evalDatasetId" placeholder="选择评估数据集" filterable style="width:220px" size="small" clearable>
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
          <el-button type="primary" size="small" :disabled="!evalDatasetId" :loading="creating" @click="handleCreateEval">
            创建评估
          </el-button>
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, pagination }">
        <div class="data-table__content">
          <el-table :ref="tableRef as any" v-loading="loading" row-key="id" :data="data" border stripe>
            <template #empty>
              <el-empty :image-size="80" description="暂无评估记录" />
            </template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column fixed label="序号" width="60">
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column label="评估数据集" prop="eval_dataset_id" width="120" />
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="tagType(row.status)" size="small" effect="plain">{{ tagLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="评估指标" min-width="300">
              <template #default="{ row }">
                <div v-if="row.metrics" style="display:flex;flex-wrap:wrap;gap:4px">
                  <el-tag v-for="(v, k) in row.metrics" :key="k" size="small" style="font-family:monospace;font-size:12px">
                    {{ k }}: {{ typeof v === 'number' ? v.toFixed(4) : v }}
                  </el-tag>
                </div>
                <span v-else style="color:var(--el-text-color-secondary)">--</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_time" label="创建时间" width="170" />
          </el-table>
        </div>
      </template>
    </PageContent>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import type { IContentConfig } from "@/components/CURD/types";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery { page_no: number; page_size: number; [key: string]: any }

const route = useRoute();
const modelRepoId = Number(route.query.model_repo_id || 0);

const contentRef = ref();
const creating = ref(false);
const evalDatasetId = ref<number | null>(null);
const datasets = ref<any[]>([]);

(async () => {
  const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
  datasets.value = dsRes.data?.data?.items || [];
})();

const allEvals = ref<any[]>([]);

async function reloadEvalData() {
  if (!modelRepoId) return;
  const r = await TrainAPI.getEvalList(modelRepoId);
  allEvals.value = r.data?.data || [];
}

onMounted(async () => {
  await reloadEvalData();
  contentRef.value?.fetchPageData({}, true);
});

function tagType(s: string): "info" | "warning" | "success" | "danger" | undefined {
  return ({ pending: "info", running: "warning", success: "success", failed: "danger" } as Record<string, any>)[s];
}
function tagLabel(s: string) {
  return ({ pending: "待开始", running: "评估中", success: "已完成", failed: "失败" } as any)[s] || s;
}

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  pk: "id",
  cols: [
    { prop: "selection", label: "选择框", show: true },
    { prop: "index", label: "序号", show: true },
    { prop: "eval_dataset_id", label: "评估数据集", show: true },
    { prop: "status", label: "状态", show: true },
    { prop: "metrics", label: "评估指标", show: true },
    { prop: "created_time", label: "创建时间", show: true },
  ],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    await reloadEvalData();
    const data = allEvals.value;
    return {
      total: data.length,
      list: data.slice((params.page_no - 1) * params.page_size, params.page_no * params.page_size),
    };
  },
  initialFetch: false,
  defaultToolbar: ["refresh", "filter"],
});

async function handleCreateEval() {
  if (!evalDatasetId.value) return;
  creating.value = true;
  try {
    await TrainAPI.createEval({ model_repo_id: modelRepoId, eval_dataset_id: evalDatasetId.value });
    ElMessage.success("评估任务已创建");
    evalDatasetId.value = null;
    const r = await TrainAPI.getEvalList(modelRepoId);
    allEvals.value = r.data?.data || [];
    contentRef.value?.fetchPageData({}, true);
  } finally {
    creating.value = false;
  }
}
</script>
