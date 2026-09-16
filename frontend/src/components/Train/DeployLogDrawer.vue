<template>
  <el-drawer v-model="visible" title="部署详情" size="640px">
    <el-descriptions v-if="detail" :column="1" border size="small">
      <el-descriptions-item label="部署名称">{{ detail.name }}</el-descriptions-item>
      <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
      <el-descriptions-item label="端口">{{ detail.host_port ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="API URL">{{ detail.api_url || "待启动" }}</el-descriptions-item>
      <el-descriptions-item label="到期时间">{{ detail.expires_at || "—" }}</el-descriptions-item>
    </el-descriptions>

    <div class="log-head">
      <span class="log-title">部署日志</span>
      <el-button size="small" :loading="loading" @click="loadLogs">刷新</el-button>
    </div>
    <pre class="deploy-log">{{ logs || "暂无日志" }}</pre>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { TrainAPI } from "@/api/module_train";

const visible = ref(false);
const loading = ref(false);
const detail = ref<any>(null);
const logs = ref("");
let currentId = 0;

async function loadLogs() {
  if (!currentId) return;
  loading.value = true;
  try {
    const res = await TrainAPI.getDeployLogs(currentId);
    logs.value = res.data?.data?.logs || "";
  } finally {
    loading.value = false;
  }
}

async function open(row: any) {
  visible.value = true;
  currentId = row.id;
  detail.value = row;
  logs.value = "";
  try {
    const res = await TrainAPI.getDeployDetail(row.id);
    if (res.data?.data) detail.value = res.data.data;
  } catch {
    /* 保留列表行数据 */
  }
  await loadLogs();
}

defineExpose({ open });
</script>

<style scoped>
.log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16px 0 8px;
}

.log-title {
  font-weight: 600;
}

.deploy-log {
  max-height: 360px;
  padding: 12px;
  overflow: auto;
  font-family: "Cascadia Code", "Fira Code", monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #d4d4d4;
  white-space: pre-wrap;
  background: #1e1e1e;
  border-radius: 6px;
}
</style>
