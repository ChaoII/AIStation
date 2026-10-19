<!--
  分支与提案（对齐官方 ontologies-proposals）

  · 分支：从主版本派生的独立版本，实验不影响主分支
  · 提案：**创建分支时自动生成**；每个被改资源 = 一个 task
  · 阶段：准备中 → 审查中 → 已合并；批准者必须是该资源的 editor/owner
  · 变更记录：按任务展开，看谁在什么时候改了什么
-->
<template>
  <div class="ont-pr">
    <el-card shadow="never">
      <div class="ont-sec__head">
        <span class="ont-sec__title">提案</span>
        <el-tag size="small" effect="plain">{{ items.length }} 个</el-tag>
        <el-button class="ont-sec__op" size="small" type="primary" :icon="Plus" @click="openCreate">
          新建分支 / 提案
        </el-button>
        <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="提案像拉取请求：改动先落在分支上，不影响主本体；按任务逐个审查批准后，才合并回主本体。提案一旦关闭不能重新打开。"
      />

      <el-tabs v-model="tab" @tab-change="load">
        <el-tab-pane v-for="t in tabs" :key="t.value" :label="t.label" :name="t.value" />
      </el-tabs>

      <el-table v-loading="loading" :data="items" size="small" border max-height="520">
        <template #empty><el-empty :image-size="60" description="还没有提案" /></template>
        <el-table-column label="提案" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.title }}</el-button>
          </template>
        </el-table-column>
        <el-table-column label="阶段" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="stageTag(row.stage)">
              {{ row.stage_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务（批准/拒绝/待审）" width="190" align="center">
          <template #default="{ row }">
            <span class="ont-mono">
              {{ row.approved }} / {{ row.rejected }} / {{ row.pending }}
            </span>
            <span class="ont-hint">（共 {{ row.task_count }}）</span>
          </template>
        </el-table-column>
        <el-table-column label="审查者" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag
              v-for="r in row.reviewers"
              :key="r"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ r }}
            </el-tag>
            <span v-if="!row.reviewers?.length" class="ont-none">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="100" />
        <el-table-column prop="created_time" label="创建时间" width="150" show-overflow-tooltip />
        <el-table-column label="操作" width="230" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:manage'"
              link
              type="success"
              size="small"
              :disabled="!row.can_merge"
              @click="doMerge(row)"
            >
              合并
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:manage'"
              link
              type="danger"
              size="small"
              :disabled="row.stage === 'merged' || row.stage === 'closed'"
              @click="doClose(row)"
            >
              关闭
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建 -->
    <el-dialog v-model="createVisible" title="新建分支 / 提案" width="560px" append-to-body>
      <el-form label-width="90px">
        <el-form-item label="标题" required>
          <el-input v-model="createForm.title" placeholder="如 给摄像机加维护状态字段" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        title="创建分支时会自动生成对应提案（官方行为）。之后在分支上做的每处定义改动，都会在提案里形成一个任务。"
      />
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doCreate"
        >
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-drawer v-model="detailVisible" :title="detail?.title || '提案详情'" size="66%">
      <template v-if="detail">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="编码">
            <span class="ont-mono">{{ detail.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="分支">
            <span class="ont-mono">{{ detail.branch_code }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="阶段">
            <el-tag size="small" effect="plain" :type="stageTag(detail.stage)">
              {{ detail.stage_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建">
            {{ detail.created_by }} · {{ detail.created_time }}
          </el-descriptions-item>
          <el-descriptions-item label="审查者" :span="2">
            <el-tag
              v-for="r in detail.reviewers"
              :key="r"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ r }}
            </el-tag>
            <span v-if="!detail.reviewers?.length" class="ont-none">未指派</span>
            <el-button link type="primary" size="small" class="ont-pr__ml" @click="openReviewers">
              指派审查者
            </el-button>
          </el-descriptions-item>
        </el-descriptions>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">任务</span>
          <el-tag size="small" effect="plain">{{ detail.tasks?.length || 0 }} 个</el-tag>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            class="ont-sec__op"
            size="small"
            type="success"
            :disabled="detail.stage === 'merged' || detail.stage === 'closed'"
            @click="doReviewAll(true)"
          >
            批量批准
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            size="small"
            type="danger"
            plain
            :disabled="detail.stage === 'merged' || detail.stage === 'closed'"
            @click="doReviewAll(false)"
          >
            批量拒绝
          </el-button>
        </div>
        <el-table :data="detail.tasks || []" size="small" border max-height="320">
          <template #empty><el-empty :image-size="50" description="分支上还没有改动" /></template>
          <el-table-column label="资源" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="ont-mono">{{ row.resource_kind }}</span>
              {{ row.resource_name }}
            </template>
          </el-table-column>
          <el-table-column prop="change_kind_label" label="变更" width="80" />
          <el-table-column label="字段差异" min-width="260">
            <template #default="{ row }">
              <div class="ont-pr__diff">
                <span v-for="d in diffOf(row)" :key="d.field" class="ont-mono">
                  {{ d.field }}: {{ fmt(d.before) }} → {{ fmt(d.after) }}
                </span>
                <span v-if="!diffOf(row).length" class="ont-none">—</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="taskTag(row.status)">
                {{ row.status_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reviewed_by" label="审查人" width="100" />
          <el-table-column label="操作" width="180" align="center">
            <template #default="{ row }">
              <el-button
                v-hasPerm="'module_ai:ontology:manage'"
                link
                type="success"
                size="small"
                :disabled="row.status === 'approved' || detail.stage === 'merged'"
                @click="doReview(row, true)"
              >
                批准
              </el-button>
              <el-button
                v-hasPerm="'module_ai:ontology:manage'"
                link
                type="danger"
                size="small"
                :disabled="row.status === 'rejected' || detail.stage === 'merged'"
                @click="doReview(row, false)"
              >
                拒绝
              </el-button>
              <el-button
                v-hasPerm="'module_ai:ontology:manage'"
                link
                type="info"
                size="small"
                :disabled="detail.stage === 'merged'"
                @click="doDiscard(row)"
              >
                丢弃
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">变更记录</span>
          <span class="ont-hint">谁在什么时候改了什么</span>
        </div>
        <el-collapse>
          <el-collapse-item
            v-for="c in detail.changelog || []"
            :key="`${c.resource_kind}-${c.resource_code}`"
          >
            <template #title>
              <span class="ont-mono">{{ c.resource_kind }}</span>
              <span class="ont-pr__ml">{{ c.resource_name }}</span>
              <el-tag size="small" effect="plain" class="ont-tag-gap">{{ c.status_label }}</el-tag>
              <span class="ont-hint ont-pr__ml">
                {{ c.edit_count }} 次编辑 · {{ (c.authors || []).join("、") }}
              </span>
            </template>
            <div v-for="(e, i) in c.edits" :key="i" class="ont-pr__edit">
              <el-tag size="small" effect="plain">{{ e.change_kind_label }}</el-tag>
              <span class="ont-hint">{{ e.created_by }} · {{ e.created_time }}</span>
              <div class="ont-pr__diff">
                <span v-for="d in e.diff" :key="d.field" class="ont-mono">
                  {{ d.field }}: {{ fmt(d.before) }} → {{ fmt(d.after) }}
                </span>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">讨论</span>
          <el-tag size="small" effect="plain">{{ (detail.comments || []).length }} 条留言</el-tag>
        </div>
        <el-empty
          v-if="!(detail.comments || []).length"
          :image-size="50"
          description="还没有留言"
        />
        <div v-else class="ont-pr__comments">
          <div v-for="c in detail.comments" :key="c.id" class="ont-pr__comment">
            <div class="ont-pr__comment-head">
              <span class="ont-pr__comment-author">{{ c.author || "匿名" }}</span>
              <span class="ont-hint">{{ c.created_time }}</span>
              <el-tag v-if="c.task_id" size="small" effect="plain">任务 #{{ c.task_id }}</el-tag>
            </div>
            <div class="ont-pr__comment-body">{{ c.body }}</div>
          </div>
        </div>
        <div class="ont-pr__comment-form">
          <el-input
            v-model="commentBody"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="写下你的意见、审查结论或补充说明…"
          />
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            type="primary"
            :loading="commenting"
            :disabled="!commentBody.trim()"
            @click="doComment"
          >
            留言
          </el-button>
        </div>

        <div class="ont-pr__actions">
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            type="success"
            :disabled="!canMerge"
            @click="doMerge(detail)"
          >
            合并到主本体
          </el-button>
          <el-button
            :disabled="detail.stage === 'in_review' || detail.stage === 'merged'"
            @click="openReviewers"
          >
            请求审查
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            type="danger"
            plain
            :disabled="detail.stage === 'merged' || detail.stage === 'closed'"
            @click="doClose(detail)"
          >
            关闭提案
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 指派审查者 -->
    <el-dialog v-model="reviewerVisible" title="指派审查者" width="520px" append-to-body>
      <el-select
        v-model="reviewers"
        multiple
        filterable
        style="width: 100%"
        placeholder="选择审查者"
      >
        <el-option
          v-for="u in users"
          :key="u.id"
          :label="`${u.name}（${u.username}）`"
          :value="u.username"
        />
      </el-select>
      <el-alert
        type="warning"
        :closable="false"
        class="ont-note"
        title="审查者只有在提案进入「审查中」阶段时才会收到通知。批准任务还需要对该资源有编辑权限。"
      />
      <template #footer>
        <el-button @click="reviewerVisible = false">取消</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doRequestReview"
        >
          请求审查
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import {
  closeOntProposal,
  commentOntProposal,
  createOntBranch,
  discardOntProposalTask,
  getOntProposal,
  getOntProposals,
  getOntSecuritySubjects,
  mergeOntProposal,
  requestOntProposalReview,
  reviewAllOntProposalTasks,
  reviewOntProposalTask,
} from "@/api/module_ai/ontology";

const emit = defineEmits<{ (e: "refresh"): void }>();

const loading = ref(false);
const busy = ref(false);
const items = ref<any[]>([]);
const tabs = ref<any[]>([]);
const tab = ref("in_review");
const users = ref<any[]>([]);

function stageTag(s: string) {
  return ({ preparing: "info", in_review: "warning", merged: "success", closed: "danger" }[s] ||
    "info") as any;
}
function taskTag(s: string) {
  return ({ pending: "info", approved: "success", rejected: "danger" }[s] || "info") as any;
}
function fmt(v: any) {
  if (v === null || v === undefined || v === "") return "空";
  const s = typeof v === "object" ? JSON.stringify(v) : String(v);
  return s.length > 30 ? s.slice(0, 27) + "…" : s;
}
function diffOf(row: any) {
  const b = row.before || {};
  const a = row.after || {};
  return Object.keys({ ...b, ...a })
    .filter((k) => b[k] !== a[k])
    .map((k) => ({ field: k, before: b[k], after: a[k] }));
}

async function load() {
  loading.value = true;
  try {
    const [r, sub] = await Promise.all([getOntProposals(tab.value), getOntSecuritySubjects()]);
    items.value = r.data?.data?.items || [];
    tabs.value = r.data?.data?.tabs || [];
    users.value = sub.data?.data?.users || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载提案失败");
  } finally {
    loading.value = false;
  }
}

/* ---------------- 新建 ---------------- */
const createVisible = ref(false);
const createForm = ref({ title: "", description: "" });

function openCreate() {
  createForm.value = { title: "", description: "" };
  createVisible.value = true;
}

async function doCreate() {
  if (!createForm.value.title.trim()) return ElMessage.warning("请填标题");
  busy.value = true;
  try {
    const r = await createOntBranch(createForm.value.title, createForm.value.description);
    ElMessage.success(r.data?.msg || "已创建");
    createVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || "创建失败");
  } finally {
    busy.value = false;
  }
}

/* ---------------- 详情 ---------------- */
const detailVisible = ref(false);
const detail = ref<any>(null);
const canMerge = computed(() => {
  const t = detail.value?.tasks || [];
  return (
    t.length > 0 &&
    t.every((x: any) => x.status === "approved") &&
    detail.value?.stage !== "merged" &&
    detail.value?.stage !== "closed"
  );
});

/* ---------------- 留言（讨论） ---------------- */
const commentBody = ref("");
const commenting = ref(false);

async function openDetail(row: any) {
  const r = await getOntProposal(row.code);
  detail.value = r.data?.data || null;
  commentBody.value = "";
  detailVisible.value = true;
}

async function doComment() {
  const body = commentBody.value.trim();
  if (!body) return ElMessage.warning("请先写留言内容");
  commenting.value = true;
  try {
    const r = await commentOntProposal(detail.value.code, body);
    ElMessage.success(r.data?.msg || "已留言");
    commentBody.value = "";
    await refreshDetail();
  } catch (e: any) {
    ElMessage.error(e?.msg || "留言失败");
  } finally {
    commenting.value = false;
  }
}

/* ---------------- 审查 ---------------- */
async function doReview(row: any, approve: boolean) {
  try {
    const r = await reviewOntProposalTask(row.id, approve);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || "已处理");
    await refreshDetail();
  } catch (e: any) {
    ElMessage.error(e?.msg || "审查失败");
  }
}

async function doReviewAll(approve: boolean) {
  const r = await reviewAllOntProposalTasks(detail.value.code, approve);
  ElMessage.success(r.data?.msg || "已处理");
  await refreshDetail();
}

async function doDiscard(row: any) {
  await ElMessageBox.confirm(
    `将丢弃任务「${row.resource_kind} ${row.resource_name}」的改动（分支上不再包含它）。确认？`,
    "丢弃任务",
    { type: "warning", confirmButtonText: "丢弃", cancelButtonText: "取消" }
  );
  const r = await discardOntProposalTask(row.id);
  ElMessage.success(r.data?.msg || "已丢弃");
  await refreshDetail();
}

async function refreshDetail() {
  if (!detail.value) return;
  const r = await getOntProposal(detail.value.code);
  detail.value = r.data?.data || detail.value;
  await load();
}

/* ---------------- 审查者 ---------------- */
const reviewerVisible = ref(false);
const reviewers = ref<string[]>([]);

function openReviewers() {
  reviewers.value = [...(detail.value?.reviewers || [])];
  reviewerVisible.value = true;
}

async function doRequestReview() {
  if (!reviewers.value.length) return ElMessage.warning("请至少选一名审查者");
  busy.value = true;
  try {
    const r = await requestOntProposalReview(detail.value.code, reviewers.value);
    ElMessage.success(r.data?.msg || "已请求审查");
    reviewerVisible.value = false;
    await refreshDetail();
  } catch (e: any) {
    ElMessage.error(e?.msg || "请求失败");
  } finally {
    busy.value = false;
  }
}

/* ---------------- 合并 / 关闭 ---------------- */
async function doMerge(row: any) {
  await ElMessageBox.confirm(
    `将把提案「${row.title}」的 ${row.task_count ?? (detail.value?.tasks || []).length} 个改动` +
      "**写入主本体**（不可自动撤销，要撤销必须逐项反向修改）。确认合并？",
    "合并提案",
    { type: "warning", confirmButtonText: "合并", cancelButtonText: "取消" }
  );
  try {
    const r = await mergeOntProposal(row.code);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || "已合并");
    detailVisible.value = false;
    await load();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || "合并失败");
  }
}

async function doClose(row: any) {
  await ElMessageBox.confirm(
    `将关闭提案「${row.title}」，其 ${row.task_count ?? 0} 个改动不会生效。` +
      "**关闭后不能重新打开。** 确认关闭？",
    "关闭提案",
    { type: "warning", confirmButtonText: "关闭", cancelButtonText: "取消" }
  );
  const r = await closeOntProposal(row.code);
  ElMessage.success(r.data?.msg || "已关闭");
  detailVisible.value = false;
  await load();
}

onMounted(load);
</script>

<style lang="scss" scoped>
.ont-pr__diff {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ont-pr__edit {
  margin-bottom: 8px;
}

.ont-pr__actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.ont-pr__ml {
  margin-left: 8px;
}

.ont-pr .ont-sec__head .ont-hint {
  margin-left: 8px;
}

.ont-pr__comments {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow: auto;
}

.ont-pr__comment {
  padding: 8px;
  border-radius: var(--el-border-radius-base);
  background: var(--el-fill-color-light);
}

.ont-pr__comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ont-pr__comment-author {
  font-weight: 600;
}

.ont-pr__comment-body {
  margin-top: 4px;
  white-space: pre-wrap;
  word-break: break-word;
}

.ont-pr__comment-form {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
