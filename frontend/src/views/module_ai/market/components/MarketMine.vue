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
      <el-tag size="small" type="info" effect="plain">共 {{ items.length }} 项资产</el-tag>
    </div>

    <el-row v-loading="loading" :gutter="12" class="card-grid">
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
            <el-tooltip :content="row.enabled ? '停用' : '启用'" placement="top">
              <el-switch
                :model-value="row.enabled"
                @change="(v: any) => toggleAsset(row as any, v)"
              />
            </el-tooltip>
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

          <div class="mine-actions">
            <el-button
              v-hasPerm="['module_ai:market:submit']"
              size="small"
              type="primary"
              :icon="Upload"
              :disabled="!!row.market && row.market.status !== 'offline'"
              @click="openSubmit(row as any)"
            >
              提交市场
            </el-button>
            <el-button
              v-hasPerm="['module_ai:market:share']"
              size="small"
              :icon="Share"
              @click="openShare(row as any)"
            >
              分享
            </el-button>
            <el-button
              v-if="row.market && row.market.status !== 'offline'"
              v-hasPerm="['module_ai:market:submit']"
              size="small"
              :icon="Remove"
              @click="withdraw(row as any)"
            >
              撤回
            </el-button>
            <el-button size="small" type="danger" :icon="Delete" @click="removeAsset(row as any)">
              删除
            </el-button>
          </div>
        </div>
      </el-col>
    </el-row>
    <el-empty
      v-if="!loading && !items.length"
      description="暂无资产：可在「能力市场」安装，或到技能广场导入"
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
  </div>
</template>

<script setup lang="ts">
  import { Delete, Remove, Share, Upload } from "@element-plus/icons-vue";
  import { ElMessage, ElMessageBox, type FormInstance } from "element-plus";
  import { onMounted, reactive, ref } from "vue";

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

  import IconTile from "./IconTile.vue";

  defineOptions({ name: "MarketMine" });

  const loading = ref(false);
  const items = ref<MyAsset[]>([]);
  const assetType = ref("");

  const typeOptions = [
    { label: "工具", value: "tool" },
    { label: "技能", value: "skill" },
    { label: "MCP", value: "mcp" },
    { label: "插件", value: "plugin" },
  ];

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
    return (
      { pending: "warning", approved: "success", rejected: "danger", offline: "info" }[status] ||
      "info"
    ) as "primary" | "success" | "warning" | "info" | "danger";
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
    if (!row.market) {
      ElMessage.warning("请先提交市场，审核通过后即可分享");
      return;
    }
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
      await shareMarketItem({
        item_id: shareTarget.value!.market!.item_id,
        to_user_id: shareForm.to_user_id,
        message: shareForm.message,
      });
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

  .type-tabs {
    display: flex;
    align-items: center;
    gap: 18px;
  }

  .type-tab {
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    cursor: pointer;
    padding: 2px 0;
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
    row-gap: 22px;
    margin-bottom: 8px;
  }

  /* 与能力市场卡片保持一致的外观 */
  .market-card {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 18px 20px;
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
    margin: 14px 0 16px;
    color: var(--el-text-color-regular);
    font-size: var(--el-font-size-base);
    line-height: 1.7;
    min-height: 48px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .market-card__foot {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--el-border-color-lighter);
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .market-none {
    color: var(--el-text-color-secondary);
  }

  .mine-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
  }

  .user-select {
    width: 100%;
  }
</style>
