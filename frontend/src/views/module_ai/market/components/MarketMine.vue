<!-- 我的资产：卡片式维护（沿用能力市场样式）+ 启停 / 提交市场 / 分享 / 撤回 / 删除 -->
<template>
  <div class="market-mine">
    <div class="mine-toolbar">
      <div class="type-tabs">
        <span
          v-for="t in typeOptions"
          :key="t.value"
          class="type-tab"
          :class="{ 'is-active': assetType === t.value }"
          @click="switchType(t.value)"
        >
          {{ t.label }}
        </span>
      </div>
      <div class="mine-toolbar__right">
        <el-button
          v-if="assetType && hasPerm(`module_ai:${assetType}:create`)"
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          {{ t("ai_market.mineCreateNew", { asset: assetLabel(assetType) }) }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          {{ t("ai_market.mineAssetCount", { count: items.length }) }}
        </el-tag>
      </div>
    </div>

    <el-row v-loading="loading" :gutter="16" class="card-grid">
      <el-col
        v-for="row in items"
        :key="`${row.asset_type}-${row.real_id}`"
        :xs="24"
        :sm="12"
        :md="8"
        :lg="6"
      >
        <div class="market-card">
          <div class="market-card__head">
            <IconTile :item="{ icon: row.icon, asset_type: row.asset_type }" />
            <div class="market-card__title">
              <div class="market-card__name">{{ row.name }}</div>
              <div class="market-card__sub">
                <el-tag size="small" effect="plain">{{ assetLabel(row.asset_type) }}</el-tag>
                <span v-if="row.category" class="market-card__cat">{{ row.category }}</span>
              </div>
            </div>
            <div class="mine-head-actions">
              <el-tooltip
                v-if="hasPerm('module_ai:market:manage')"
                :content="row.enabled ? t('ai_market.disable') : t('ai_market.enableAction')"
                placement="top"
              >
                <el-switch
                  :model-value="row.enabled"
                  @change="(v: any) => toggleAsset(row as any, v)"
                />
              </el-tooltip>
              <el-tooltip
                v-if="hasPerm(`module_ai:${row.asset_type}:update`)"
                :content="t('ai_market.edit')"
                placement="top"
              >
                <el-button size="small" circle :icon="Edit" @click="openEdit(row as any)" />
              </el-tooltip>
              <el-tooltip :content="t('ai_market.submitMarket')" placement="top">
                <el-button
                  v-if="hasPerm('module_ai:market:submit')"
                  size="small"
                  circle
                  :icon="Upload"
                  :disabled="!!row.market && row.market.status !== 'offline'"
                  @click="openSubmit(row as any)"
                />
              </el-tooltip>
              <el-tooltip :content="t('ai_market.share')" placement="top">
                <el-button
                  v-if="hasPerm('module_ai:market:share')"
                  size="small"
                  circle
                  :icon="Share"
                  @click="openShare(row as any)"
                />
              </el-tooltip>
              <el-tooltip
                v-if="row.market && row.market.status !== 'offline'"
                :content="t('ai_market.withdraw')"
                placement="top"
              >
                <el-button
                  v-if="hasPerm('module_ai:market:submit')"
                  size="small"
                  circle
                  :icon="Remove"
                  @click="withdraw(row as any)"
                />
              </el-tooltip>
              <el-tooltip
                v-if="hasPerm('module_ai:market:manage')"
                :content="t('ai_market.delete')"
                placement="top"
              >
                <el-button
                  size="small"
                  circle
                  type="danger"
                  :icon="Delete"
                  @click="removeAsset(row as any)"
                />
              </el-tooltip>
            </div>
          </div>

          <div class="market-card__desc">{{ row.description || t("ai_market.noDescription") }}</div>

          <div class="market-card__foot">
            <span class="metric">{{ t("ai_market.mineMarket") }}</span>
            <el-tag
              v-if="row.market"
              size="small"
              :type="statusTagType(row.market.status)"
              effect="plain"
            >
              {{ statusLabel(row.market.status) }}
            </el-tag>
            <span v-else class="market-none">{{ t("ai_market.mineNotSubmitted") }}</span>
            <span v-if="row.market" class="metric">
              {{ t("ai_market.mineInstallCount", { count: row.market.install_count }) }}
            </span>
          </div>
        </div>
      </el-col>
    </el-row>
    <el-empty v-if="!loading && !items.length" :description="t('ai_market.mineEmpty')" />

    <!-- 提交市场 -->
    <el-dialog
      v-model="submitVisible"
      :title="t('ai_market.submitTitle')"
      width="600px"
      append-to-body
    >
      <el-form ref="submitFormRef" :model="submitForm" :rules="submitRules" label-width="90px">
        <el-form-item :label="t('ai_market.assetTypeLabel')">
          <el-tag effect="plain">{{ assetLabel(submitForm.asset_type) }}</el-tag>
        </el-form-item>
        <el-form-item :label="t('ai_market.nameLabel')" prop="name">
          <el-input
            v-model="submitForm.name"
            maxlength="128"
            :placeholder="t('ai_market.submitDisplayName')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.category')" prop="category">
          <el-input
            v-model="submitForm.category"
            maxlength="64"
            :placeholder="t('ai_market.categoryPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.iconLabel')">
          <el-input
            v-model="submitForm.icon"
            maxlength="256"
            :placeholder="t('ai_market.iconPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.version')">
          <el-input
            v-model="submitForm.version"
            maxlength="16"
            :placeholder="t('ai_market.versionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_market.description')">
          <el-input
            v-model="submitForm.description"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            :placeholder="t('ai_market.submitDescPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">{{ t("ai_market.cancel") }}</el-button>
        <el-button type="primary" :loading="submitting" @click="confirmSubmit">
          {{ t("ai_market.submitReview") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 分享 -->
    <el-dialog
      v-model="shareVisible"
      :title="t('ai_market.shareTitle')"
      width="520px"
      append-to-body
    >
      <el-form label-width="90px">
        <el-form-item :label="t('ai_market.asset')">
          <span>{{ shareTarget?.name }}</span>
        </el-form-item>
        <el-form-item :label="t('ai_market.recipient')" required>
          <el-select
            v-model="shareForm.to_user_id"
            filterable
            remote
            clearable
            :placeholder="t('ai_market.searchUserPlaceholder')"
            :remote-method="searchUsers"
            :loading="userLoading"
            class="user-select"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :label="`${u.name}（${u.username}）`"
              :value="u.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_market.messageLabel')">
          <el-input
            v-model="shareForm.message"
            maxlength="255"
            :placeholder="t('ai_market.optional')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="shareVisible = false">{{ t("ai_market.cancel") }}</el-button>
        <el-button type="primary" :loading="sharing" @click="confirmShare">
          {{ t("ai_market.sendShare") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 创建 / 编辑各类资产 -->
    <CreateToolDialog v-model="toolVisible" :real-id="editRealId" @saved="onAssetSaved" />
    <CreateMcpDialog v-model="mcpVisible" :real-id="editRealId" @saved="onAssetSaved" />
    <CreateSkillDialog v-model="skillVisible" :real-id="editRealId" @saved="onAssetSaved" />
    <CreatePluginDialog v-model="pluginVisible" :real-id="editRealId" @saved="onAssetSaved" />
  </div>
</template>

<script setup lang="ts">
import { Delete, Edit, Plus, Remove, Share, Upload } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type FormInstance } from "element-plus";
import { onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import {
  deleteMyAsset,
  getMyAssets,
  shareMarketItem,
  submitMarketItem,
  toggleMyAsset,
  withdrawMarketItem,
  type MyAsset,
} from "@/api/module_ai/market";
import UserAPI from "@/api/module_system/user";
import { ROLE_ROOT } from "@/constants";
import { useUserStore } from "@/store";

import IconTile from "./IconTile.vue";
import CreateMcpDialog from "./CreateMcpDialog.vue";
import CreatePluginDialog from "./CreatePluginDialog.vue";
import CreateSkillDialog from "./CreateSkillDialog.vue";
import CreateToolDialog from "./CreateToolDialog.vue";

defineOptions({ name: "MarketMine" });

const props = defineProps<{ target: { asset_type: string; name: string } | null }>();
const emit = defineEmits<{ targetHandled: [] }>();

const { t } = useI18n();

// 安装需密钥资产后跳转而来：切到对应类型并自动打开该资产编辑
watch(
  () => props.target,
  async (target) => {
    if (!target) return;
    assetType.value = target.asset_type;
    await load();
    const hit = items.value.find((r) => r.name === target.name);
    if (hit) {
      openEdit(hit);
    } else {
      ElMessage.info(t("ai_market.mineNotFound", { name: target.name }));
    }
    emit("targetHandled");
  },
  { immediate: true }
);

const loading = ref(false);
const items = ref<MyAsset[]>([]);
const assetType = ref("");

const typeOptions = [
  { label: t("ai_market.assetTool"), value: "tool" },
  { label: t("ai_market.assetSkill"), value: "skill" },
  { label: t("ai_market.assetMcp"), value: "mcp" },
  { label: t("ai_market.assetPlugin"), value: "plugin" },
];

function hasPerm(perm: string): boolean {
  const store = useUserStore();
  const roles = store.basicInfo.roles;
  if (roles && roles.some((r) => r.code === ROLE_ROOT)) return true;
  return store.prems.includes(perm);
}

// ---- 创建 / 编辑各类资产 ----
const toolVisible = ref(false);
const mcpVisible = ref(false);
const skillVisible = ref(false);
const pluginVisible = ref(false);
const editRealId = ref<number | null>(null);

function openCreate() {
  editRealId.value = null;
  if (assetType.value === "tool") toolVisible.value = true;
  else if (assetType.value === "skill") skillVisible.value = true;
  else if (assetType.value === "mcp") mcpVisible.value = true;
  else if (assetType.value === "plugin") pluginVisible.value = true;
}

function openEdit(row: MyAsset) {
  editRealId.value = row.real_id;
  if (row.asset_type === "tool") toolVisible.value = true;
  else if (row.asset_type === "skill") skillVisible.value = true;
  else if (row.asset_type === "mcp") mcpVisible.value = true;
  else if (row.asset_type === "plugin") pluginVisible.value = true;
}

function onAssetSaved() {
  // 创建/编辑成功后刷新列表
  load();
}

const submitVisible = ref(false);
const submitting = ref(false);
const submitFormRef = ref<FormInstance>();
const submitForm = reactive({
  asset_type: "tool",
  source_id: 0,
  name: "",
  category: "",
  icon: "",
  version: "1.0",
  description: "",
});
const submitRules = {
  name: [{ required: true, message: t("ai_market.requiredName"), trigger: "blur" }],
};

const shareVisible = ref(false);
const sharing = ref(false);
const shareTarget = ref<MyAsset | null>(null);
const shareForm = reactive({ to_user_id: undefined as number | undefined, message: "" });
const userOptions = ref<{ id: number; name: string; username: string }[]>([]);
const userLoading = ref(false);

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

function statusLabel(status: string) {
  return (
    {
      pending: t("ai_market.statusPending"),
      approved: t("ai_market.statusApproved"),
      rejected: t("ai_market.statusRejected"),
      offline: t("ai_market.statusOffline"),
    }[status] || status
  );
}

function statusTagType(status: string): "primary" | "success" | "warning" | "info" | "danger" {
  return ({ pending: "warning", approved: "success", rejected: "danger", offline: "info" }[
    status
  ] || "info") as "primary" | "success" | "warning" | "info" | "danger";
}

async function load() {
  loading.value = true;
  try {
    const res: any = await getMyAssets({ asset_type: assetType.value || undefined });
    items.value = res.data?.data?.items || [];
  } finally {
    loading.value = false;
  }
}

function switchType(value: string) {
  // 再点同一类型 = 取消筛选（回到全部，无「全部」页签）
  assetType.value = assetType.value === value ? "" : value;
  load();
}

/** 启停：就地更新该行（不整表刷新） */
async function toggleAsset(row: MyAsset, value: any) {
  const enabled = Boolean(value);
  await toggleMyAsset(row.asset_type, row.real_id, enabled);
  row.enabled = enabled;
  ElMessage.success(enabled ? t("ai_market.toggleEnabled") : t("ai_market.toggleDisabled"));
}

async function removeAsset(row: MyAsset) {
  await ElMessageBox.confirm(
    t("ai_market.mineDeleteConfirm", { asset: assetLabel(row.asset_type), name: row.name }),
    t("ai_market.deleteConfirmTitle"),
    {
      confirmButtonText: t("ai_market.delete"),
      cancelButtonText: t("ai_market.cancel"),
      type: "warning",
    }
  );
  await deleteMyAsset(row.asset_type, row.real_id);
  ElMessage.success(t("ai_market.deleted"));
  load();
}

function openSubmit(row: MyAsset) {
  submitForm.asset_type = row.asset_type;
  submitForm.source_id = row.real_id;
  submitForm.name = row.name;
  submitForm.category = row.category || "";
  submitForm.icon = row.icon || "";
  submitForm.version = "1.0";
  submitForm.description = row.description || "";
  submitVisible.value = true;
}

async function confirmSubmit() {
  if (!submitFormRef.value) return;
  await submitFormRef.value.validate();
  submitting.value = true;
  try {
    await submitMarketItem({ ...submitForm });
    ElMessage.success(t("ai_market.submittedForReview"));
    submitVisible.value = false;
    load();
  } finally {
    submitting.value = false;
  }
}

async function withdraw(row: MyAsset) {
  await ElMessageBox.confirm(
    t("ai_market.withdrawConfirm", { name: row.name }),
    t("ai_market.withdrawConfirmTitle"),
    {
      confirmButtonText: t("ai_market.withdraw"),
      cancelButtonText: t("ai_market.cancel"),
      type: "warning",
    }
  );
  await withdrawMarketItem(row.market!.item_id);
  ElMessage.success(t("ai_market.withdrawn"));
  load();
}

function openShare(row: MyAsset) {
  shareTarget.value = row;
  shareForm.to_user_id = undefined;
  shareForm.message = "";
  userOptions.value = [];
  shareVisible.value = true;
}

async function searchUsers(query: string) {
  if (!query) {
    userOptions.value = [];
    return;
  }
  userLoading.value = true;
  try {
    const res: any = await UserAPI.listUser({ username: query, page_no: 1, page_size: 20 });
    const rows = res.data?.data?.items || [];
    userOptions.value = rows.map((u: any) => ({ id: u.id, name: u.name, username: u.username }));
  } finally {
    userLoading.value = false;
  }
}

async function confirmShare() {
  if (!shareForm.to_user_id) {
    ElMessage.warning(t("ai_market.selectRecipient"));
    return;
  }
  sharing.value = true;
  try {
    const target = shareTarget.value!;
    const payload: {
      item_id?: number;
      asset_type?: string;
      real_id?: number;
      to_user_id: number;
      message?: string;
    } = {
      to_user_id: shareForm.to_user_id,
      message: shareForm.message,
    };
    // 已上架市场商品走 item_id（保留安装/收藏语义）；否则直接分享个人资产（asset_type+real_id）
    const m = target.market;
    if (m && m.item_id && m.status === "approved") {
      payload.item_id = m.item_id;
    } else {
      payload.asset_type = target.asset_type;
      payload.real_id = target.real_id;
    }
    await shareMarketItem(payload);
    ElMessage.success(t("ai_market.sharedSuccess"));
    shareVisible.value = false;
  } finally {
    sharing.value = false;
  }
}

onMounted(load);
</script>

<style lang="scss" scoped>
.mine-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.mine-toolbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.type-tabs {
  display: flex;
  align-items: center;
  gap: 18px;
}

.type-tab {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  cursor: pointer;
  height: 30px;
  line-height: 30px;
  padding: 0 2px;
  border-bottom: 2px solid transparent;

  &:hover {
    color: var(--el-color-primary);
  }

  &.is-active {
    color: var(--el-color-primary);
    font-weight: 600;
    border-bottom-color: var(--el-color-primary);
  }
}

.card-grid {
  min-height: 120px;
  row-gap: 16px;
  margin-bottom: 8px;
}

/* 与能力市场卡片保持一致的外观 */
.market-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 18px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  transition:
    box-shadow 0.2s,
    border-color 0.2s;

  &:hover {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 6px 18px rgb(0 0 0 / 8%);
  }
}

.market-card__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.mine-head-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  padding-top: 2px;
}

.mine-head-actions :deep(.el-button) {
  margin-left: 0;
}

.market-card__title {
  min-width: 0;
  flex: 1;
}

.market-card__name {
  font-weight: 600;
  font-size: var(--el-font-size-base);
  line-height: 1.5;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-card__sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.market-card__cat {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-card__desc {
  margin: 12px 0 12px;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.market-card__foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.market-none {
  color: var(--el-text-color-secondary);
}

.user-select {
  width: 100%;
}
</style>
