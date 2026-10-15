<!-- 审核中心：待审核/已审核 + 通过/驳回 + 精选开关 -->
<template>
  <div class="market-review">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-radio-group v-model="status" @change="load">
          <el-radio-button value="pending">待审核</el-radio-button>
          <el-radio-button value="approved">已上架</el-radio-button>
          <el-radio-button value="rejected">已驳回</el-radio-button>
        </el-radio-group>
        <el-tag size="small" type="info" effect="plain">共 {{ items.length }} 条</el-tag>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" border stripe>
        <el-table-column label="商品" min-width="200">
          <template #default="{ row }">
            <span class="item-icon">{{ row.icon || "📦" }}</span>
            <span>{{ row.name }}</span>
            <el-tag size="small" effect="plain" class="type-tag">
              {{ assetLabel(row.asset_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="120">
          <template #default="{ row }">{{ row.category || "—" }}</template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column label="精选" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.featured"
              :disabled="row.status !== 'approved'"
              @change="(v: any) => toggleFeatured(row as any, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="audit_remark" label="审核意见" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.audit_remark || "—" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button size="small" type="primary" :icon="Check" @click="openReview(row as any, 'approve')">
                通过
              </el-button>
              <el-button size="small" :icon="Close" @click="openReview(row as any, 'reject')">驳回</el-button>
            </template>
            <el-button
              v-else-if="row.status === 'approved'"
              size="small"
              :icon="Remove"
              @click="openReview(row as any, 'reject')"
            >
              下架
            </el-button>
            <span v-else class="done-text">已处理</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length" description="暂无审核记录" />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="商品">
          <span>{{ current?.name }}</span>
        </el-form-item>
        <el-form-item label="意见">
          <el-input
            v-model="remark"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            :placeholder="action === 'reject' ? '请说明驳回/下架原因' : '可选'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="confirmReview">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
  import { Check, Close, Remove } from "@element-plus/icons-vue";
  import { ElMessage, ElMessageBox } from "element-plus";
  import { computed, onMounted, ref } from "vue";

  import {
    getMarketReviewList,
    reviewMarketItem,
    setMarketFeatured,
    type MarketItem,
  } from "@/api/module_ai/market";

  defineOptions({ name: "MarketReview" });

  const loading = ref(false);
  const status = ref("pending");
  const items = ref<MarketItem[]>([]);

  const dialogVisible = ref(false);
  const submitting = ref(false);
  const current = ref<MarketItem | null>(null);
  const action = ref("approve");
  const remark = ref("");

  const dialogTitle = computed(() => {
    if (action.value === "approve") return "审核通过";
    return current.value?.status === "approved" ? "下架商品" : "驳回商品";
  });

  function assetLabel(type: string) {
    return { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" }[type] || type;
  }

  function statusLabel(s: string) {
    return { pending: "待审核", approved: "已上架", rejected: "已驳回", offline: "已下架" }[s] || s;
  }

  function statusTagType(s: string): "primary" | "success" | "warning" | "info" | "danger" {
    return ({ pending: "warning", approved: "success", rejected: "danger", offline: "info" }[s] ||
      "info") as "primary" | "success" | "warning" | "info" | "danger";
  }

  async function load() {
    loading.value = true;
    try {
      const res: any = await getMarketReviewList({ status: status.value });
      items.value = res.data?.items || [];
    } finally {
      loading.value = false;
    }
  }

  function openReview(row: MarketItem, act: string) {
    current.value = row;
    action.value = act;
    remark.value = "";
    dialogVisible.value = true;
  }

  async function confirmReview() {
    if (!current.value) return;
    if (action.value === "reject" && !remark.value.trim()) {
      ElMessage.warning("驳回/下架请填写原因");
      return;
    }
    submitting.value = true;
    try {
      await reviewMarketItem({
        item_id: current.value.id,
        action: action.value,
        remark: remark.value,
      });
      ElMessage.success(action.value === "approve" ? "已通过并上架" : "已驳回/下架");
      dialogVisible.value = false;
      load();
    } finally {
      submitting.value = false;
    }
  }

  async function toggleFeatured(row: MarketItem, value: any) {
    const on = Boolean(value);
    if (on) {
      await ElMessageBox.confirm(
        `将「${row.name}」设为精选后会展示在能力市场首页推荐位。是否继续？`,
        "精选确认",
        { confirmButtonText: "设为精选", cancelButtonText: "取消", type: "info" }
      );
    }
    await setMarketFeatured(row.id, on);
    row.featured = on;
    ElMessage.success(on ? "已设为精选" : "已取消精选");
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
