<!-- 空间扩容审核：管理员列表 + 通过/驳回（通过即按用户增额） -->
<template>
  <div class="app-container ai-space-quota-page">
    <el-card shadow="never">
      <template #header>
        <span>空间扩容审核</span>
      </template>

      <div class="quota-review-toolbar">
        <el-radio-group v-model="statusFilter" @change="loadList">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="pending">待审核</el-radio-button>
          <el-radio-button label="approved">已通过</el-radio-button>
          <el-radio-button label="rejected">已驳回</el-radio-button>
        </el-radio-group>
        <el-button :icon="Refresh" @click="loadList">刷新</el-button>
      </div>

      <el-table v-loading="loading" :data="list" empty-text="暂无扩容申请">
        <el-table-column label="申请人" width="120">
          <template #default="{ row }">{{ row.username || row.user_id }}</template>
        </el-table-column>
        <el-table-column label="目标配额" width="120">
          <template #default="{ row }">{{ formatQuotaSize(row.target_mb * 1024 * 1024) }}</template>
        </el-table-column>
        <el-table-column label="申请理由" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.reason || "—" }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="申请时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_time) }}</template>
        </el-table-column>
        <el-table-column label="审核备注" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.review_note || "—" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" align="center">
          <template #default="{ row }">
            <template v-if="row.status === 'pending'">
              <el-button
                size="small"
                link
                type="primary"
                @click="openReview(row as SpaceQuotaRequest, true)"
              >
                通过
              </el-button>
              <el-button
                size="small"
                link
                type="danger"
                @click="openReview(row as SpaceQuotaRequest, false)"
              >
                驳回
              </el-button>
            </template>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="reviewVisible"
      :title="reviewApprove ? '通过扩容申请' : '驳回扩容申请'"
      width="520px"
    >
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="申请人">
          <span>{{ current?.username || current?.user_id }}</span>
        </el-form-item>
        <el-form-item label="申请目标">
          <span>{{ current ? formatQuotaSize(current.target_mb * 1024 * 1024) : "—" }}</span>
        </el-form-item>
        <el-form-item label="申请理由">
          <span>{{ current?.reason || "—" }}</span>
        </el-form-item>
        <el-form-item v-if="reviewApprove" label="生效配额">
          <el-input-number v-model="reviewQuotaGb" :min="1" :step="1" :precision="1" />
          <span class="quota-unit">GB</span>
        </el-form-item>
        <el-form-item label="审核备注">
          <el-input
            v-model="reviewNote"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="选填，将展示给申请人。"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button
          :type="reviewApprove ? 'primary' : 'danger'"
          :loading="submitting"
          @click="submitReview"
        >
          {{ reviewApprove ? "通过" : "驳回" }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";

import {
  getSpaceQuotaRequests,
  reviewSpaceQuotaRequest,
  type SpaceQuotaRequest,
} from "@/api/module_ai/space";

// ---------------------------------------------------------------- 状态
const loading = ref(false);
const list = ref<SpaceQuotaRequest[]>([]);
const statusFilter = ref("");

const reviewVisible = ref(false);
const current = ref<SpaceQuotaRequest | null>(null);
const reviewApprove = ref(false);
const reviewQuotaGb = ref(5);
const reviewNote = ref("");
const submitting = ref(false);

// ---------------------------------------------------------------- 工具
function formatQuotaSize(bytes: number): string {
  if (bytes == null || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return i === 0 ? `${bytes} B` : `${v.toFixed(2)} ${units[i]}`;
}

function formatTime(t?: string): string {
  if (!t) return "—";
  return String(t).replace("T", " ").slice(0, 19);
}

function statusLabel(s: string): string {
  if (s === "approved") return "已通过";
  if (s === "rejected") return "已驳回";
  return "待审核";
}

function statusType(s: string): "success" | "danger" | "info" {
  if (s === "approved") return "success";
  if (s === "rejected") return "danger";
  return "info";
}

// ---------------------------------------------------------------- 加载
async function loadList() {
  loading.value = true;
  try {
    const r = await getSpaceQuotaRequests({
      status: statusFilter.value || undefined,
    });
    list.value = r.data?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.message || "加载申请失败");
  } finally {
    loading.value = false;
  }
}

// ---------------------------------------------------------------- 审核
function openReview(row: SpaceQuotaRequest, approve: boolean) {
  current.value = row;
  reviewApprove.value = approve;
  reviewNote.value = "";
  // 通过时默认给到申请目标大小（GB，保留一位小数）
  reviewQuotaGb.value = Number(((row.target_mb * 1024 * 1024) / 1024 / 1024 / 1024).toFixed(1));
  reviewVisible.value = true;
}

async function submitReview() {
  if (!current.value) return;
  const isApprove = reviewApprove.value;
  const targetLabel = formatQuotaSize(current.value.target_mb * 1024 * 1024);
  const userName = current.value.username || `用户 ${current.value.user_id}`;
  const msg = isApprove
    ? `将通过「${userName}」的扩容申请，赋予其 ${reviewQuotaGb.value} GB 配额（原目标 ${targetLabel}），且不可撤销。`
    : `将驳回「${userName}」的扩容申请（目标 ${targetLabel}），其配额保持不变。`;

  try {
    await ElMessageBox.confirm(msg, isApprove ? "通过扩容申请" : "驳回扩容申请", {
      confirmButtonText: isApprove ? "确认通过" : "确认驳回",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch {
    return;
  }

  submitting.value = true;
  try {
    const r = await reviewSpaceQuotaRequest(current.value.id, {
      approve: isApprove,
      quota_mb: isApprove ? Math.round(reviewQuotaGb.value * 1024) : null,
      note: reviewNote.value.trim(),
    });
    ElMessage.success(r.data?.data?.msg || "已处理");
    reviewVisible.value = false;
    await loadList();
  } catch (e: any) {
    ElMessage.error(e?.message || "处理失败");
  } finally {
    submitting.value = false;
  }
}

onMounted(loadList);
</script>

<style lang="scss" scoped>
.ai-space-quota-page {
  display: flex;
  flex-direction: column;
}

.quota-review-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.quota-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}
</style>
