<template>
  <el-drawer v-model="visible" title="导出历史" size="640px">
    <el-table v-loading="loading" :data="rows" border size="small">
      <el-table-column label="格式" prop="format" width="90" />
      <el-table-column label="导出时间" prop="export_time" min-width="170" />
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="导出人" prop="exported_by" width="90" />
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-link v-if="row.download_url" type="primary" :href="row.download_url" target="_blank">
            下载
          </el-link>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无导出记录" />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { AnnotationAPI } from "@/api/module_annotation";

const visible = ref(false);
const loading = ref(false);
const rows = ref<any[]>([]);

async function open(datasetId: number) {
  visible.value = true;
  loading.value = true;
  try {
    const res = await AnnotationAPI.getExportHistory(datasetId);
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

function formatSize(n?: number): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

defineExpose({ open });
</script>

<style scoped>
.text-muted {
  color: var(--el-text-color-placeholder);
}
</style>
