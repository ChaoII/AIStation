<!-- 分享给我：收到的/发出的分享 + 接收/拒绝 -->
<template>
  <div class="market-shared">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-radio-group v-model="direction" @change="load">
          <el-radio-button value="in">{{ t("ai_market.received") }}</el-radio-button>
          <el-radio-button value="out">{{ t("ai_market.sent") }}</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="status"
          class="status-select"
          :placeholder="t('ai_market.allStatus')"
          clearable
          @change="load"
        >
          <el-option :label="t('ai_market.statusPending')" value="pending" />
          <el-option :label="t('ai_market.statusAccepted')" value="accepted" />
          <el-option :label="t('ai_market.statusRejected')" value="rejected" />
        </el-select>
        <el-button type="primary" :icon="Refresh" @click="load">
          {{ t("ai_market.refresh") }}
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" border stripe>
        <el-table-column :label="t('ai_market.productLabel')" min-width="200">
          <template #default="{ row }">
            <span class="item-icon">{{ row.item_icon || "📦" }}</span>
            <span>{{ row.item_name }}</span>
            <el-tag size="small" effect="plain" class="type-tag">
              {{ assetLabel(row.item_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('ai_market.fromUser')" width="140">
          <template #default="{ row }">{{ row.from_user_name || row.from_user_id }}</template>
        </el-table-column>
        <el-table-column :label="t('ai_market.toUser')" width="140">
          <template #default="{ row }">{{ row.to_user_name || row.to_user_id }}</template>
        </el-table-column>
        <el-table-column
          prop="message"
          :label="t('ai_market.messageLabel')"
          min-width="140"
          show-overflow-tooltip
        />
        <el-table-column :label="t('ai_market.statusLabel')" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-if="direction === 'in'"
          :label="t('ai_market.actionLabel')"
          width="180"
          fixed="right"
        >
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button
                v-hasPerm="'module_ai:market:manage'"
                size="small"
                type="primary"
                :icon="Check"
                @click="accept(row as any)"
              >
                {{ t("ai_market.accept") }}
              </el-button>
              <el-button
                v-hasPerm="'module_ai:market:manage'"
                size="small"
                :icon="Close"
                @click="reject(row as any)"
              >
                {{ t("ai_market.reject") }}
              </el-button>
              <span v-if="!hasPerm('module_ai:market:manage')" class="done-text">
                {{ t("ai_market.noReceivePerm") }}
              </span>
            </template>
            <span v-else class="done-text">{{ t("ai_market.handled") }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length" :description="t('ai_market.noShareRecords')" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { Check, Close, Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

import {
  acceptMarketShare,
  getMarketShares,
  rejectMarketShare,
  type MarketShare,
} from "@/api/module_ai/market";
import { ROLE_ROOT } from "@/constants";
import { useUserStore } from "@/store";

defineOptions({ name: "MarketShared" });

const { t } = useI18n();

const loading = ref(false);
const direction = ref("in");
const status = ref("");
const items = ref<MarketShare[]>([]);

function hasPerm(perm: string): boolean {
  const store = useUserStore();
  const roles = store.basicInfo.roles;
  if (roles && roles.some((r) => r.code === ROLE_ROOT)) return true;
  return store.prems.includes(perm);
}

function assetLabel(type: string) {
  return (
    {
      tool: t("ai_market.assetTool"),
      skill: t("ai_market.assetSkill"),
      mcp: t("ai_market.assetMcp"),
      plugin: t("ai_market.assetPlugin"),
    }[type] || type
  );
}

function statusLabel(s: string) {
  return (
    {
      pending: t("ai_market.statusPending"),
      accepted: t("ai_market.statusAccepted"),
      rejected: t("ai_market.statusRejected"),
    }[s] || s
  );
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
    t("ai_market.acceptConfirm", { name: row.item_name }),
    t("ai_market.acceptConfirmTitle"),
    {
      confirmButtonText: t("ai_market.accept"),
      cancelButtonText: t("ai_market.cancel"),
      type: "info",
    }
  );
  await acceptMarketShare(row.id);
  ElMessage.success(t("ai_market.acceptSuccess"));
  load();
}

async function reject(row: MarketShare) {
  await ElMessageBox.confirm(
    t("ai_market.rejectConfirm", { name: row.item_name }),
    t("ai_market.rejectConfirmTitle"),
    {
      confirmButtonText: t("ai_market.reject"),
      cancelButtonText: t("ai_market.cancel"),
      type: "warning",
    }
  );
  await rejectMarketShare(row.id);
  ElMessage.success(t("ai_market.rejected"));
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
