<!-- 分享给我：收到的/发出的分享 + 接收/拒绝 -->
<template>
  <div class="market-shared">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-radio-group v-model="direction" @change="load">
          <el-radio-button value="in">收到的</el-radio-button>
          <el-radio-button value="out">发出的</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="status"
          class="status-select"
          placeholder="全部状态"
          clearable
          @change="load"
        >
          <el-option label="待处理" value="pending" />
          <el-option label="已接收" value="accepted" />
          <el-option label="已拒绝" value="rejected" />
        </el-select>
        <el-button type="primary" :icon="Refresh" @click="load">刷新</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" border stripe>
        <el-table-column label="商品" min-width="200">
          <template #default="{ row }">
            <span class="item-icon">{{ row.item_icon || "📦" }}</span>
            <span>{{ row.item_name }}</span>
            <el-tag size="small" effect="plain" class="type-tag">
              {{ assetLabel(row.item_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分享人" width="140">
          <template #default="{ row }">{{ row.from_user_name || row.from_user_id }}</template>
        </el-table-column>
        <el-table-column label="接收人" width="140">
          <template #default="{ row }">{{ row.to_user_name || row.to_user_id }}</template>
        </el-table-column>
        <el-table-column prop="message" label="留言" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="direction === 'in'" label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="primary" :icon="Check" @click="accept(row as any)">
                接收
              </el-button>
              <el-button size="small" :icon="Close" @click="reject(row as any)">拒绝</el-button>
            </template>
            <span v-else class="done-text">已处理</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length" description="暂无分享记录" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { Check, Close, Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref } from "vue";

import {
  acceptMarketShare,
  getMarketShares,
  rejectMarketShare,
  type MarketShare,
} from "@/api/module_ai/market";

defineOptions({ name: "MarketShared" });

const loading = ref(false);
const direction = ref("in");
const status = ref("");
const items = ref<MarketShare[]>([]);

function assetLabel(type: string) {
  return { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" }[type] || type;
}

function statusLabel(s: string) {
  return { pending: "待处理", accepted: "已接收", rejected: "已拒绝" }[s] || s;
}

function statusTagType(s: string): "primary" | "success" | "warning" | "info" | "danger" {
  return ({ pending: "warning", accepted: "success", rejected: "info" }[s] || "info") as
    "primary" | "success" | "warning" | "info" | "danger";
}

async function load() {
  loading.value = true;
  try {
    const res: any = await getMarketShares({
      direction: direction.value,
      status: status.value || undefined,
    });
    items.value = res.data?.data?.items || [];
  } finally {
    loading.value = false;
  }
}

async function accept(row: MarketShare) {
  await ElMessageBox.confirm(
    `接收后「${row.item_name}」会复制为你自己的资产（可在对应管理页维护）。是否接收？`,
    "接收确认",
    { confirmButtonText: "接收", cancelButtonText: "取消", type: "info" }
  );
  await acceptMarketShare(row.id);
  ElMessage.success("已接收，资产已添加到你的账户");
  load();
}

async function reject(row: MarketShare) {
  await ElMessageBox.confirm(`确定拒绝「${row.item_name}」的分享吗？`, "拒绝确认", {
    confirmButtonText: "拒绝",
    cancelButtonText: "取消",
    type: "warning",
  });
  await rejectMarketShare(row.id);
  ElMessage.success("已拒绝");
  load();
}

onMounted(load);
</script>

<style lang="scss" scoped>
.toolbar-card {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-select {
  width: 160px;
}

.item-icon {
  margin-right: 6px;
}

.type-tag {
  margin-left: 6px;
}

.done-text {
  color: var(--el-text-color-secondary);
}
</style>
