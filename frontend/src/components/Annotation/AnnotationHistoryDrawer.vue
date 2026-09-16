<template>
  <el-drawer v-model="visible" title="标注历史" size="560px">
    <el-table v-loading="loading" :data="rows" border size="small">
      <el-table-column label="版本" prop="version" width="80" align="center" />
      <el-table-column label="时间" prop="created_time" min-width="170" />
      <el-table-column label="标注数" width="90" align="center">
        <template #default="{ row }">{{ (row.annotation_data || []).length }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="restore(row.version)">
            恢复此版本
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && rows.length === 0" description="暂无历史版本" />
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { AnnotationAPI } from "@/api/module_annotation";

const emit = defineEmits<{ (e: "restored"): void }>();

const visible = ref(false);
const loading = ref(false);
const rows = ref<any[]>([]);
let taskId = 0;
let imageId = 0;

async function load() {
  loading.value = true;
  try {
    const res = await AnnotationAPI.getAnnotationHistory(taskId, imageId);
    rows.value = res.data?.data || [];
  } finally {
    loading.value = false;
  }
}

async function open(tid: number, iid: number) {
  taskId = tid;
  imageId = iid;
  visible.value = true;
  await load();
}

async function restore(version: number) {
  await ElMessageBox.confirm(`确认恢复到版本 v${version}？将生成新版本。`, "提示", {
    type: "warning",
  });
  await AnnotationAPI.rollbackAnnotation(imageId, { task_id: taskId, version });
  ElMessage.success("已恢复");
  await load();
  emit("restored");
}

defineExpose({ open });
</script>
