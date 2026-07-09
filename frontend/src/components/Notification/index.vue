<template>
  <el-popover placement="bottom" :width="360" trigger="click" @show="fetchList">
    <template #reference>
      <el-badge :value="unread" :hidden="unread === 0" :max="99" style="cursor:pointer;display:inline-flex;align-items:center">
        <div class="i-svg:bell" />
      </el-badge>
    </template>

    <div style="max-height:400px;overflow:hidden;display:flex;flex-direction:column">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:0 0 8px;border-bottom:1px solid #ebeef5">
        <span style="font-weight:600;font-size:14px;color:#303133">通知</span>
        <el-button v-if="unread > 0" text size="small" @click="handleMarkAllRead">全部已读</el-button>
      </div>

      <div v-if="loading" style="text-align:center;padding:20px;color:#909399;font-size:13px">加载中...</div>
      <div v-else-if="list.length === 0" style="text-align:center;padding:20px;color:#c0c4cc;font-size:13px">暂无通知</div>
      <div v-else style="overflow-y:auto;max-height:300px;margin:0 -12px">
        <div
          v-for="item in list" :key="item.id"
          @click="handleClick(item)"
          style="display:flex;align-items:flex-start;gap:8px;padding:10px 12px;cursor:pointer;border-bottom:1px solid #f2f2f2;transition:background .15s"
          :style="!item.is_read ? { background:'#f0f7ff' } : {}"
        >
          <div v-if="!item.is_read" style="width:6px;height:6px;border-radius:50%;background:#409eff;flex-shrink:0;margin-top:6px" />
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;color:#303133;line-height:1.4;word-break:break-all">{{ item.title }}</div>
            <div style="font-size:11px;color:#c0c4cc;margin-top:2px">{{ timeAgo(item.created_time) }}</div>
          </div>
        </div>
      </div>
      <div v-if="hasMore" @click="viewAll" style="text-align:center;padding:8px 0 0;font-size:12px;color:#409eff;cursor:pointer;border-top:1px solid #ebeef5">查看全部通知</div>
    </div>
  </el-popover>

  <el-dialog v-model="noticeDialogVisible" title="通知公告" width="800px" custom-class="notification-detail">
    <div v-if="noticeDetail" class="p-x-20px">
      <div class="flex-y-center mb-16px text-13px text-color-secondary">
        <span class="flex-y-center"><el-icon><User /></el-icon>{{ noticeDetail.created_by?.name }}</span>
        <span class="ml-2 flex-y-center"><el-icon><Timer /></el-icon>{{ noticeDetail.created_time }}</span>
      </div>
      <div class="max-h-60vh pt-16px mb-24px overflow-y-auto border-t border-solid border-color">
        <div v-html="noticeDetail.notice_content"></div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { User, Timer, ArrowRight } from "@element-plus/icons-vue";
import { NotificationAPI } from "@/api/module_system/notification";
import NoticeAPI, { NoticeTable } from "@/api/module_system/notice";
import { useNoticeStore } from "@/store";

const router = useRouter();
const noticeStore = useNoticeStore();

const unread = ref(0);
const list = ref<any[]>([]);
const loading = ref(false);
const hasMore = ref(false);

const noticeList = ref<NoticeTable[]>([]);
const noticeDialogVisible = ref(false);
const noticeDetail = ref<NoticeTable | null>(null);

function timeAgo(t: string) {
  if (!t) return "";
  const diff = Math.floor((Date.now() - new Date(t).getTime()) / 1000);
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
  await NotificationAPI.markAllRead();
  unread.value = 0;
  list.value.forEach((i: any) => (i.is_read = true));
}

function viewAll() { router.push("/notification"); }

let pollTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  fetchUnread();
  featchMyNotice();
  pollTimer = setInterval(fetchUnread, 30000);
});
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); });

async function featchMyNotice() {
  await noticeStore.getNotice();
  noticeList.value = noticeStore.noticeList;
}

function handleViewMoreNotice() { router.push({ name: "Notice" }); }

function handleMarkAllAsRead() {
  const ids = noticeList.value.map((item) => item.id).filter((id): id is number => id !== undefined);
  NoticeAPI.batchNotice({ ids, status: "1" }).then(async () => {
    await noticeStore.getNotice();
    noticeList.value = noticeStore.noticeList;
  });
}
</script>
