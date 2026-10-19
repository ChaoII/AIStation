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
          新建{{ assetLabel(assetType) }}
        </el-button>
        <el-tag size="small" type="info" effect="plain">共 {{ items.length }} 项资产</el-tag>
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
                :content="row.enabled ? '停用' : '启用'"
                placement="top"
              >
                <el-switch
                  :model-value="row.enabled"
                  @change="(v: any) => toggleAsset(row as any, v)"
                />
              </el-tooltip>
              <el-tooltip
                v-if="hasPerm(`module_ai:${row.asset_type}:update`)"
                content="编辑"
                placement="top"
              >
                <el-button size="small" circle :icon="Edit" @click="openEdit(row as any)" />
              </el-tooltip>
              <el-tooltip content="提交市场" placement="top">
                <el-button
                  v-if="hasPerm('module_ai:market:submit')"
                  size="small"
                  circle
                  :icon="Upload"
                  :disabled="!!row.market && row.market.status !== 'offline'"
                  @click="openSubmit(row as any)"
                />
              </el-tooltip>
              <el-tooltip content="分享" placement="top">
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
                content="撤回"
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
              <el-tooltip v-if="hasPerm('module_ai:market:manage')" content="删除" placement="top">
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

          <div class="market-card__desc">{{ row.description || "暂无描述" }}</div>

          <div class="market-card__foot">
            <span class="metric">市场</span>
            <el-tag
              v-if="row.market"
              size="small"
              :type="statusTagType(row.market.status)"
              effect="plain"
            >
              {{ statusLabel(row.market.status) }}
            </el-tag>
            <span v-else class="market-none">未提交</span>
            <span v-if="row.market" class="metric">{{ row.market.install_count }} 次安装</span>
          </div>
        </div>
      </el-col>
    </el-row>
    <el-empty
      v-if="!loading && !items.length"
      description="暂无资产：可在「能力市场」安装，或点击上方「新建」创建"
    />

    <!-- 提交市场 -->
    <el-dialog v-model="submitVisible" title="提交到能力市场" width="560px" append-to-body>
      <el-form ref="submitFormRef" :model="submitForm" :rules="submitRules" label-width="90px">
        <el-form-item label="资产类型">
          <el-tag effect="plain">{{ assetLabel(submitForm.asset_type) }}</el-tag>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="submitForm.name" maxlength="128" placeholder="市场展示名称" />
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-input
            v-model="submitForm.category"
            maxlength="64"
            placeholder="如：效率 / 数据 / 办公"
          />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="submitForm.icon" maxlength="256" placeholder="emoji 或图片 URL" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="submitForm.version" maxlength="16" placeholder="1.0" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="submitForm.description"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="说明这个能力做什么、适用场景"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="confirmSubmit">提交审核</el-button>
      </template>
    </el-dialog>

    <!-- 分享 -->
    <el-dialog v-model="shareVisible" title="分享给用户" width="520px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="资产">
          <span>{{ shareTarget?.name }}</span>
        </el-form-item>
        <el-form-item label="接收人" required>
          <el-select
            v-model="shareForm.to_user_id"
            filterable
            remote
            clearable
            placeholder="输入用户名搜索"
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
        <el-form-item label="留言">
          <el-input v-model="shareForm.message" maxlength="255" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="shareVisible = false">取消</el-button>
        <el-button type="primary" :loading="sharing" @click="confirmShare">发送分享</el-button>
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
      ElMessage.info(`未在「我的资产」中找到「${target.name}」，请手动定位`);
    }
    emit("targetHandled");
  },
  { immediate: true }
);

const loading = ref(false);
const items = ref<MyAsset[]>([]);
const assetType = ref("");

const typeOptions = [
  { label: "工具", value: "tool" },
  { label: "技能", value: "skill" },
  { label: "MCP", value: "mcp" },
  { label: "插件", value: "plugin" },
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
  name: [{ required: true, message: "请输入名称", trigger: "blur" }],
};

const shareVisible = ref(false);
const sharing = ref(false);
const shareTarget = ref<MyAsset | null>(null);
const shareForm = reactive({ to_user_id: undefined as number | undefined, message: "" });
const userOptions = ref<{ id: number; name: string; username: string }[]>([]);
const userLoading = ref(false);

function assetLabel(type: string) {
  return { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" }[type] || type;
}

function statusLabel(status: string) {
  return (
    { pending: "待审核", approved: "已上架", rejected: "已驳回", offline: "已下架" }[status] ||
    status
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
  ElMessage.success(enabled ? "已启用" : "已停用");
}

async function removeAsset(row: MyAsset) {
  await ElMessageBox.confirm(
    `将删除你的${assetLabel(row.asset_type)}「${row.name}」，删除后不可恢复（已安装到智能体的绑定也会失效）。是否继续？`,
    "删除确认",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  );
  await deleteMyAsset(row.asset_type, row.real_id);
  ElMessage.success("已删除");
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
    ElMessage.success("已提交，等待管理员审核");
    submitVisible.value = false;
    load();
  } finally {
    submitting.value = false;
  }
}

async function withdraw(row: MyAsset) {
  await ElMessageBox.confirm(
    `撤回后「${row.name}」将从市场下架，其他用户无法再安装（已安装的副本不受影响）。是否继续？`,
    "撤回确认",
    { confirmButtonText: "撤回", cancelButtonText: "取消", type: "warning" }
  );
  await withdrawMarketItem(row.market!.item_id);
  ElMessage.success("已撤回");
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
    ElMessage.warning("请选择接收人");
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
    ElMessage.success("已发送分享");
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
