<!-- 我的资产：个人真实资产 + 提交市场 / 分享 / 撤回 -->
<template>
  <div class="market-mine">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-radio-group v-model="assetType" @change="load">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="tool">工具</el-radio-button>
          <el-radio-button value="skill">技能</el-radio-button>
          <el-radio-button value="mcp">MCP</el-radio-button>
          <el-radio-button value="plugin">插件</el-radio-button>
        </el-radio-group>
        <el-tag size="small" type="info" effect="plain">共 {{ items.length }} 项资产</el-tag>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="items" border stripe>
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ assetLabel(row.asset_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="120">
          <template #default="{ row }">{{ row.category || "—" }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? "启用" : "停用" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="市场状态" width="200">
          <template #default="{ row }">
            <template v-if="row.market">
              <el-tag size="small" :type="statusTagType(row.market.status)" effect="plain">
                {{ statusLabel(row.market.status) }}
              </el-tag>
              <span class="market-count">{{ row.market.install_count }} 次安装</span>
            </template>
            <span v-else class="market-none">未提交</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
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
          </template>
        </el-table-column>
      </el-table>
      <el-empty
        v-if="!loading && !items.length"
        description="暂无资产，可先在工具/技能/MCP 页创建"
      />
    </el-card>

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
import { Remove, Share, Upload } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type FormInstance } from "element-plus";
import { onMounted, reactive, ref } from "vue";

import {
  getMyAssets,
  shareMarketItem,
  submitMarketItem,
  withdrawMarketItem,
  type MyAsset,
} from "@/api/module_ai/market";
import UserAPI from "@/api/module_system/user";

defineOptions({ name: "MarketMine" });

const loading = ref(false);
const items = ref<MyAsset[]>([]);
const assetType = ref("");

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

function openSubmit(row: MyAsset) {
  submitForm.asset_type = row.asset_type;
  submitForm.source_id = row.real_id;
  submitForm.name = row.name;
  submitForm.category = row.category || "";
  submitForm.icon = "";
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
.toolbar-card {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.market-count {
  margin-left: 6px;
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
