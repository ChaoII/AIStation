<!-- 审核中心：待审核/已审核 + 通过/驳回 + 精选开关 -->
<template>
  <div class="market-review">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-radio-group v-model="status" @change="handleStatusChange">
          <el-radio-button value="pending">待审核</el-radio-button>
          <el-radio-button value="approved">已上架</el-radio-button>
          <el-radio-button value="rejected">已驳回</el-radio-button>
          <el-radio-button value="offline">已下架</el-radio-button>
        </el-radio-group>
        <el-tag size="small" type="info" effect="plain">共 {{ total }} 条</el-tag>
        <div v-if="status === 'pending'" class="batch-actions">
          <el-button
            size="small"
            type="primary"
            :disabled="!selectedRows.length"
            @click="batchReview('approve')"
          >
            批量通过
          </el-button>
          <el-button
            size="small"
            type="danger"
            :disabled="!selectedRows.length"
            @click="batchReview('reject')"
          >
            批量驳回
          </el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="items"
        border
        stripe
        @selection-change="onSelectionChange"
      >
        <el-table-column type="expand" width="40">
          <template #default="{ row }">
            <div class="payload-panel">
              <div class="payload-meta">
                <el-tag size="small" effect="plain">{{ assetLabel(row.asset_type) }}</el-tag>
                <span>版本：{{ row.version || "—" }}</span>
                <span>提交者：{{ row.owner_name || (row.is_official ? "官方" : "—") }}</span>
              </div>
              <pre class="payload-pre">{{ prettyPayload(row as any) }}</pre>
            </div>
          </template>
        </el-table-column>
        <el-table-column v-if="status === 'pending'" type="selection" width="48" />
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
              <el-button
                size="small"
                type="primary"
                :icon="Check"
                @click="openReview(row as any, 'approve')"
              >
                通过
              </el-button>
              <el-button size="small" :icon="Close" @click="openReview(row as any, 'reject')">
                驳回
              </el-button>
            </template>
            <el-button
              v-else-if="row.status === 'approved'"
              v-hasPerm="'module_ai:market:review'"
              size="small"
              :icon="Remove"
              @click="openReview(row as any, 'offline')"
            >
              下架
            </el-button>
            <span v-else class="done-text">已处理</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !items.length" description="暂无审核记录" />
      <div v-if="total > page_size" class="pager">
        <el-pagination
          v-model:current-page="page_no"
          :page-size="page_size"
          :total="total"
          layout="prev, pager, next"
          background
          @current-change="load"
        />
      </div>
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
            :placeholder="action === 'approve' ? '可选' : '请说明驳回/下架原因'"
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
  reviewMarketBatch,
  reviewMarketItem,
  setMarketFeatured,
  type MarketItem,
} from "@/api/module_ai/market";

defineOptions({ name: "MarketReview" });

const loading = ref(false);
const status = ref("pending");
const items = ref<MarketItem[]>([]);
const page_no = ref(1);
const page_size = ref(20);
const total = ref(0);
const selectedRows = ref<MarketItem[]>([]);

const dialogVisible = ref(false);
const submitting = ref(false);
const current = ref<MarketItem | null>(null);
const action = ref("approve");
const remark = ref("");

/** 批量审核单条结果（后端逐条返回，不因单条失败中断） */
interface BatchResult {
  item_id: number;
  ok: boolean;
  msg?: string;
}

const dialogTitle = computed(() => {
  if (action.value === "approve") return "审核通过";
  if (action.value === "offline") return "下架商品";
  return "驳回商品";
});

function assetLabel(type: string) {
  return { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" }[type] || type;
}

/** 审核时展示提交快照（后端已脱敏），未展开不请求接口 */
function prettyPayload(row: MarketItem) {
  try {
    return JSON.stringify(row.payload ?? {}, null, 2);
  } catch {
    return String(row.payload ?? "");
  }
}

function statusLabel(s: string) {
  return { pending: "待审核", approved: "已上架", rejected: "已驳回", offline: "已下架" }[s] || s;
}

function statusTagType(s: string): "primary" | "success" | "warning" | "info" | "danger" {
  return ({ pending: "warning", approved: "success", rejected: "danger", offline: "info" }[s] ||
    "info") as "primary" | "success" | "warning" | "info" | "danger";
}

function handleStatusChange() {
  page_no.value = 1;
  selectedRows.value = [];
  load();
}

function onSelectionChange(rows: MarketItem[]) {
  selectedRows.value = rows;
}

async function load() {
  loading.value = true;
  try {
    const res: any = await getMarketReviewList({
      status: status.value,
      page_no: page_no.value,
      page_size: page_size.value,
    });
    const data = res.data?.data || {};
    items.value = data.items || [];
    total.value = data.total || 0;
  } finally {
    loading.value = false;
  }
}

async function batchReview(act: "approve" | "reject") {
  if (!selectedRows.value.length) return;
  const names = selectedRows.value.map((r) => r.name).join("、");
  const confirmText =
    act === "approve"
      ? `将批量通过并上架 ${selectedRows.value.length} 个商品：${names}。是否继续？`
      : `将批量驳回 ${selectedRows.value.length} 个商品：${names}（可在意见中说明原因）。是否继续？`;
  const confirmed = await ElMessageBox.confirm(confirmText, "批量审核确认", {
    confirmButtonText: act === "approve" ? "批量通过" : "批量驳回",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => true)
    .catch(() => false);
  if (!confirmed) return;
  const byId = new Map(selectedRows.value.map((r) => [r.id, r.name]));
  try {
    const res: any = await reviewMarketBatch({
      items: selectedRows.value.map((r) => ({
        item_id: r.id,
        action: act,
        remark: act === "reject" ? "批量驳回" : "",
      })),
    });
    const results: BatchResult[] = res.data?.data?.results || [];
    const failed = results.filter((r) => !r.ok);
    const okCount = results.length - failed.length;
    if (failed.length) {
      const detail = failed
        .slice(0, 3)
        .map((f) => `${byId.get(f.item_id) || `#${f.item_id}`}：${f.msg || "未知原因"}`)
        .join("；");
      ElMessage.warning(
        `成功 ${okCount} 个，失败 ${failed.length} 个。${detail}${failed.length > 3 ? "…" : ""}`
      );
    } else {
      ElMessage.success(`已批量${act === "approve" ? "通过" : "驳回"} ${okCount} 个商品`);
    }
  } finally {
    selectedRows.value = [];
    load();
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
  if (action.value !== "approve" && !remark.value.trim()) {
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
    ElMessage.success(
      action.value === "approve" ? "已通过并上架" : action.value === "offline" ? "已下架" : "已驳回"
    );
    dialogVisible.value = false;
    load();
  } finally {
    submitting.value = false;
  }
}

async function toggleFeatured(row: MarketItem, value: any) {
  const on = Boolean(value);
  if (on) {
    const confirmed = await ElMessageBox.confirm(
      `将「${row.name}」设为精选后会展示在能力市场首页推荐位。是否继续？`,
      "精选确认",
      { confirmButtonText: "设为精选", cancelButtonText: "取消", type: "info" }
    )
      .then(() => true)
      .catch(() => false);
    if (!confirmed) return;
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

.batch-actions {
  display: flex;
  gap: 8px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.done-text {
  color: var(--el-text-color-secondary);
}

.payload-panel {
  padding: 4px 16px;
}

.payload-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
}

.payload-pre {
  margin: 0;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
  color: var(--el-text-color-primary);
  font-size: var(--el-font-size-small);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
