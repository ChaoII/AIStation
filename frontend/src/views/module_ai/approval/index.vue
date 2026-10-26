<template>
  <div class="app-container approval-page">
    <el-card class="approval-shell" shadow="never">
      <div class="ap-head">
        <div class="t">
          <h2>审批中心</h2>
          <p>待处理 <span class="num">{{ total }}</span> 项：动作写回 {{ actions.length }} · 本体发布 {{ versions.length }}</p>
        </div>
        <div class="acts">
          <el-button :loading="loading" @click="loadAll">刷新</el-button>
        </div>
      </div>

      <el-tabs v-model="tab" class="ap-tabs">
        <el-tab-pane :label="`动作写回 (${actions.length})`" name="action">
          <el-table :data="actions" border stripe height="100%" v-loading="loading">
            <el-table-column prop="action" label="动作" min-width="150" show-overflow-tooltip />
            <el-table-column prop="table" label="对象表" min-width="130" show-overflow-tooltip />
            <el-table-column prop="key" label="对象键" min-width="120" show-overflow-tooltip />
            <el-table-column label="写回参数" min-width="220">
              <template #default="{ row }">
                <span class="mono">{{ brief(row.params) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="operator" label="申请人" width="110" />
            <el-table-column prop="time" label="申请时间" width="170" />
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button v-hasPerm="'module_ai:query:ask'" link type="primary" @click="approveAction(row)">批准</el-button>
                <el-button v-hasPerm="'module_ai:query:ask'" link type="danger" @click="rejectAction(row)">驳回</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" description="没有待审批的动作写回" />
            </template>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`本体发布 (${versions.length})`" name="version">
          <el-table :data="versions" border stripe height="100%" v-loading="loading">
            <el-table-column prop="object_code" label="对象类型" min-width="160" show-overflow-tooltip />
            <el-table-column label="版本信息" min-width="260">
              <template #default="{ row }">
                <span class="mono">{{ brief(row.detail) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_time" label="申请时间" width="180" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button v-hasPerm="'module_ai:ontology:manage'" link type="primary" @click="approveVersion(row)">批准发布</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" description="没有待发布的本体版本" />
            </template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { approveAction as apiApproveAction, getPendingActions, rejectAction as apiRejectAction } from "@/api/module_ai/query";
import { approveOntVersion, getOntVersionPending } from "@/api/module_ai/ontology";

const tab = ref<"action" | "version">("action");
const loading = ref(false);
const actions = ref<any[]>([]);
const versions = ref<any[]>([]);

const total = computed(() => actions.value.length + versions.value.length);

/** 参数太长就截断，表格里不撑爆 */
function brief(v: any): string {
  if (!v) return "—";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 80 ? s.slice(0, 80) + "…" : s;
}

async function loadAll() {
  loading.value = true;
  try {
    const [a, v]: any[] = await Promise.all([getPendingActions(50), getOntVersionPending()]);
    actions.value = a?.data?.data || a?.data || [];
    versions.value = v?.data?.data || v?.data || [];
  } catch (e: any) {
    ElMessage.error(e?.message || "加载待审批列表失败");
  } finally {
    loading.value = false;
  }
}

async function approveAction(row: any) {
  try {
    await ElMessageBox.confirm(
      `将执行「${row.action}」对 ${row.table} 的写回（对象键 ${row.key}），写回后不可撤回。确认批准？`,
      "批准写回",
      { type: "warning", confirmButtonText: "批准并执行", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  const res: any = await apiApproveAction({ approval_id: row.id });
  const ok = res?.data?.data?.ok !== false;
  ElMessage[ok ? "success" : "error"](res?.data?.data?.msg || (ok ? "已批准" : "批准失败"));
  loadAll();
}

async function rejectAction(row: any) {
  try {
    await ElMessageBox.confirm(
      `将驳回「${row.action}」的写回申请（对象键 ${row.key}），该申请不会执行。确认驳回？`,
      "驳回申请",
      { type: "warning", confirmButtonText: "驳回", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  const res: any = await apiRejectAction({ approval_id: row.id });
  ElMessage.success(res?.data?.msg || "已驳回");
  loadAll();
}

async function approveVersion(row: any) {
  try {
    await ElMessageBox.confirm(
      `将把「${row.object_code}」的待发布版本正式发布，发布后对外可见。确认批准？`,
      "批准发布",
      { type: "warning", confirmButtonText: "批准发布", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  const res: any = await approveOntVersion(row.id);
  const r = res?.data?.data || {};
  if (r.ok === false) ElMessage.error(r.msg || "批准失败");
  else ElMessage.success(r.msg || "已批准发布");
  loadAll();
}

onMounted(loadAll);
</script>

<style lang="scss">
.approval-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  overflow: hidden;
  box-sizing: border-box;

  .approval-shell {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--el-border-color-light);
    border-radius: 4px;
  }
  .approval-shell :deep(.el-card__body) {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    padding: 16px;
  }
  .ap-head {
    flex: 0 0 auto;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    padding-bottom: 8px;
  }
  .ap-head h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }
  .ap-head p {
    margin: 6px 0 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  .ap-head .num {
    color: var(--el-text-color-regular);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .ap-tabs {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .ap-tabs :deep(.el-tabs__content) {
    flex: 1 1 auto;
    min-height: 0;
  }
  .ap-tabs :deep(.el-tab-pane) {
    height: 100%;
  }
  .mono {
    font-family: var(--el-font-family-mono, monospace);
    font-size: 12px;
    color: var(--el-text-color-regular);
  }
}
</style>
