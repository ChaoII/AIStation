<template>
  <div class="app-container">
    <el-card>
      <template #header>
        <div style="display:flex;align-items:center;gap:12px">
          <el-button text @click="router.back()">← 返回</el-button>
          <span style="font-weight:600">{{ task?.name }}</span>
          <el-tag v-if="task" :type="statusTag(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
          <span v-if="task?.framework" class="text-sm text-gray-400">{{ task.framework === 'ultralytics' ? 'Ultralytics' : 'PaddleX' }}</span>
        </div>
      </template>
      <div class="log-container" ref="logRef">
        <pre class="log-text">{{ logText || '等待日志...' }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const router = useRouter();
const task = ref<any>(null);
const logText = ref("");
const logRef = ref<HTMLElement | null>(null);
let ws: WebSocket | null = null;

function statusTag(s: string) {
  return { pending: "info", running: "warning", success: "success", failed: "danger", cancelled: "info" }[s] || "info";
}
function statusLabel(s: string) {
  return { pending: "待开始", running: "训练中", success: "已完成", failed: "失败", cancelled: "已取消" }[s] || s;
}

onMounted(async () => {
  const id = Number(route.params.id);
  if (!id) return;
  const r = await TrainAPI.getTaskDetail(id);
  task.value = r.data?.data;

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/api/v1/train/ws/train/logs?task_id=${id}`);
  ws.onmessage = (e: MessageEvent) => {
    logText.value += e.data + "\n";
    setTimeout(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight; }, 50);
  };
  ws.onerror = () => {};
});

onBeforeUnmount(() => { ws?.close(); });
</script>

<style scoped>
.log-container { height: 600px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 16px; }
.log-text { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
