<template>
  <el-popover placement="bottom" :width="360" trigger="click" @show="fetchList">
    <template #reference>
      <el-badge :value="unread" :hidden="unread === 0" :max="99" class="notif-badge">
        <el-icon :size="20"><Bell /></el-icon>
      </el-badge>
    </template>

    <div class="notif-popover">
      <div class="notif-header">
        <span class="notif-title">通知</span>
        <el-button v-if="unread > 0" text size="small" @click="handleMarkAllRead">全部已读</el-button>
      </div>
      <div v-if="loading" style="text-align:center;padding:20px;color:#909399">加载中...</div>
      <div v-else-if="list.length === 0" style="text-align:center;padding:20px;color:#c0c4cc">暂无通知</div>
      <div v-else class="notif-list">
        <div
          v-for="item in list" :key="item.id"
          class="notif-item" :class="{ 'notif-item--unread': !item.is_read }"
          @click="handleClick(item)"
        >
          <div class="notif-item__dot" v-if="!item.is_read" />
          <div class="notif-item__body">
            <div class="notif-item__title">{{ item.title }}</div>
            <div class="notif-item__time">{{ timeAgo(item.created_time) }}</div>
          </div>
        </div>
      </div>
      <div v-if="hasMore" class="notif-footer" @click="viewAll">查看全部</div>
    </div>
  </el-popover>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { Bell } from "@element-plus/icons-vue";
import { NotificationAPI } from "@/api/module_system/notification";

const router = useRouter();
const unread = ref(0);
const list = ref<any[]>([]);
const loading = ref(false);
const hasMore = ref(false);

function timeAgo(t: string) {
  if (!t) return "";
  const n = Date.now();
  const d = new Date(t).getTime();
  const diff = Math.floor((n - d) / 1000);
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}天前`;
  return t.slice(0, 10);
}

async function fetchList() {
  loading.value = true;
  try {
    const r = await NotificationAPI.list(1, 5);
    const d = r.data?.data;
    list.value = d?.items || [];
    hasMore.value = d?.has_next || false;
  } catch { list.value = []; }
  finally { loading.value = false; }
}

async function fetchUnread() {
  try {
    const r = await NotificationAPI.unreadCount();
    unread.value = r.data?.data?.count || 0;
  } catch { /* */ }
}

async function handleClick(item: any) {
  if (!item.is_read) {
    await NotificationAPI.markRead(item.id);
    item.is_read = true;
    unread.value = Math.max(0, unread.value - 1);
  }
  if (item.module === "train" && item.module_id) {
    router.push(`/train/task/${item.module_id}`);
  }
}

async function handleMarkAllRead() {
  const r = await NotificationAPI.markAllRead();
  unread.value = 0;
  list.value.forEach((i: any) => (i.is_read = true));
}

function viewAll() {
  router.push("/notification");
}

let pollTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  fetchUnread();
  pollTimer = setInterval(fetchUnread, 30000);
});
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); });
</script>

<style scoped>
.notif-badge { cursor: pointer; display: inline-flex; align-items: center; }
.notif-popover { max-height: 400px; overflow: hidden; display: flex; flex-direction: column; }
.notif-header { display: flex; align-items: center; justify-content: space-between; padding: 0 0 8px; border-bottom: 1px solid #ebeef5; }
.notif-title { font-weight: 600; font-size: 14px; color: #303133; }
.notif-list { overflow-y: auto; max-height: 300px; margin: 0 -12px; }
.notif-item { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; cursor: pointer; border-bottom: 1px solid #f2f2f2; transition: background .15s; }
.notif-item:hover { background: #f5f7fa; }
.notif-item--unread { background: #f0f7ff; }
.notif-item--unread:hover { background: #e6f0ff; }
.notif-item__dot { width: 6px; height: 6px; border-radius: 50%; background: #409eff; flex-shrink: 0; margin-top: 6px; }
.notif-item__body { flex: 1; min-width: 0; }
.notif-item__title { font-size: 13px; color: #303133; line-height: 1.4; word-break: break-all; }
.notif-item__time { font-size: 11px; color: #c0c4cc; margin-top: 2px; }
.notif-footer { text-align: center; padding: 8px 0 0; font-size: 12px; color: #409eff; cursor: pointer; border-top: 1px solid #ebeef5; }
</style>
