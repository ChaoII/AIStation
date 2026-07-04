<template>
  <div class="app-container">
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #header>
        <div style="display: flex; align-items: center; gap: 12px">
          <el-button text @click="router.back()">← 返回</el-button>
          <span style="font-weight: 600">模型评估</span>
          <span class="text-sm text-gray-400">模型ID: {{ modelRepoId }}</span>
        </div>
      </template>

      <template #toolbar="{ toolbarRight, onToolbar, cols }">
        <div class="data-table__toolbar--left">
          <el-select
            v-model="evalDatasetId"
            placeholder="选择评估数据集"
            filterable
            style="width: 280px"
          >
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
          <el-button
            v-hasPerm="['module_train:model:query']"
            type="primary"
            :disabled="!evalDatasetId"
            :loading="creating"
            @click="handleCreateEval"
          >
            创建评估
          </el-button>
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, pagination }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
          >
            <template #empty>
              <el-empty :image-size="80" description="暂无数据" />
            </template>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'index')?.show"
              fixed
              label="序号"
              width="60"
            >
              <template #default="scope">
                {{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'eval_dataset_id')?.show"
              key="eval_dataset_id"
              label="评估数据集ID"
              prop="eval_dataset_id"
              width="120"
            />
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'status')?.show"
              key="status"
              label="状态"
              prop="status"
              width="100"
              align="center"
            >
              <template #default="scope">
                <el-tag :type="statusTag(scope.row.status)" size="small">
                  {{ statusLabel(scope.row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'metrics')?.show"
              key="metrics"
              label="评估指标"
              min-width="280"
            >
              <template #default="scope">
                <pre
                  v-if="scope.row.metrics"
                  style="margin: 0; font-size: 12px; white-space: pre-wrap"
                  >{{ JSON.stringify(scope.row.metrics, null, 2) }}</pre>
                <span v-else class="text-gray-400">--</span>
              </template>
            </el-table-column>
            <el-table-column
              v-if="contentCols.find((col) => col.prop === 'created_time')?.show"
              key="created_time"
              label="创建时间"
              prop="created_time"
              width="170"
            />
          </el-table>
        </div>
      </template>
    </PageContent>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import type { IContentConfig } from "@/components/CURD/types";
import CrudToolbarRight from "@/components/CURD/CrudToolbarRight.vue";
import { TrainAPI } from "@/api/module_train";
import { AnnotationAPI } from "@/api/module_annotation";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const route = useRoute();
const router = useRouter();
const modelRepoId = Number(route.query.model_repo_id || 0);

const contentRef = ref();
const creating = ref(false);
const evalDatasetId = ref<number | null>(null);

const datasets = ref<any[]>([]);
(async () => {
  const dsRes = await AnnotationAPI.getDatasetList({ page_no: 1, page_size: 100 });
  datasets.value = dsRes.data?.data?.items || [];
})();

const contentCols = reactive<
  Array<{
    prop?: string;
    label?: string;
    show?: boolean;
  }>
>([
  { prop: "index", label: "序号", show: true },
  { prop: "eval_dataset_id", label: "评估数据集ID", show: true },
  { prop: "status", label: "状态", show: true },
  { prop: "metrics", label: "评估指标", show: true },
  { prop: "created_time", label: "创建时间", show: true },
]);

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  pk: "id",
  cols: contentCols as IContentConfig["cols"],
  hideColumnFilter: true,
  pagination: {
    pageSize: 10,
    pageSizes: [10, 20, 30, 50],
  },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async () => {
    const res = await TrainAPI.getEvalList(modelRepoId);
    return {
      total: (res.data?.data || []).length,
      list: res.data?.data || [],
    };
  },
  initialFetch: modelRepoId > 0,
});

function statusTag(s: string): "primary" | "success" | "warning" | "info" | "danger" | undefined {
  return (
    (
      { pending: "info", running: "warning", success: "success", failed: "danger" } as Record<
        string,
        "info" | "warning" | "success" | "danger"
      >
    )[s] || "info"
  );
}

function statusLabel(s: string) {
  return { pending: "待开始", running: "评估中", success: "已完成", failed: "失败" }[s] || s;
}

async function handleCreateEval() {
  if (!evalDatasetId.value) return;
  creating.value = true;
  try {
    await TrainAPI.createEval({ model_repo_id: modelRepoId, eval_dataset_id: evalDatasetId.value });
    ElMessage.success("评估任务已创建");
    contentRef.value?.fetchPageData({}, true);
  } finally {
    creating.value = false;
  }
}
</script>

<style scoped>
.text-gray-400 {
  color: #909399;
}
</style>
