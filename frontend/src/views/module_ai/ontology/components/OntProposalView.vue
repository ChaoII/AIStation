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
        <span class="ont-sec__title">{{ i18nT("ai_ontology.proposal") }}</span>
        <el-tag size="small" effect="plain">
          {{ i18nT("ai_ontology.countUnit", { count: items.length }) }}
        </el-tag>
        <el-button class="ont-sec__op" size="small" type="primary" :icon="Plus" @click="openCreate">
          {{ i18nT("ai_ontology.newBranchProposal") }}
        </el-button>
        <el-button size="small" :icon="Refresh" @click="load">
          {{ i18nT("ai_ontology.refresh") }}
        </el-button>
      </div>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.proposalInfoAlert')"
      />

      <el-tabs v-model="tab" @tab-change="load">
        <el-tab-pane v-for="t in tabs" :key="t.value" :label="t.label" :name="t.value" />
      </el-tabs>

      <el-table v-loading="loading" :data="items" size="small" border max-height="520" stripe>
        <template #empty>
          <el-empty :image-size="60" :description="i18nT('ai_ontology.noProposalsYet')" />
        </template>
        <el-table-column
          :label="i18nT('ai_ontology.proposal')"
          min-width="220"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">{{ row.title }}</el-button>
          </template>
        </el-table-column>
        <el-table-column :label="i18nT('ai_ontology.stage')" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="stageTag(row.stage)">
              {{ row.stage_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          :label="i18nT('ai_ontology.taskApprovalStatus')"
          width="190"
          align="center"
        >
          <template #default="{ row }">
            <span class="ont-mono">
              {{ row.approved }} / {{ row.rejected }} / {{ row.pending }}
            </span>
            <span class="ont-hint">
              {{ i18nT("ai_ontology.totalCountParen", { count: row.task_count }) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column
          :label="i18nT('ai_ontology.reviewer2')"
          min-width="130"
          show-overflow-tooltip
        >
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
        <el-table-column prop="created_by" :label="i18nT('ai_ontology.createdBy')" width="100" />
        <el-table-column
          prop="created_time"
          :label="i18nT('ai_ontology.createdTime')"
          width="150"
          show-overflow-tooltip
        />
        <el-table-column
          :label="i18nT('ai_ontology.operations')"
          width="230"
          align="center"
          fixed="right"
        >
          <template #default="{ row }">
            <el-button icon="View" link type="primary" size="small" @click="openDetail(row)">
              {{ i18nT("ai_ontology.details") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:manage'"
              icon="Connection"
              link
              type="success"
              size="small"
              :disabled="!row.can_merge"
              @click="doMerge(row)"
            >
              {{ i18nT("ai_ontology.merge") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:ontology:manage'"
              icon="Close"
              link
              type="danger"
              size="small"
              :disabled="row.stage === 'merged' || row.stage === 'closed'"
              @click="doClose(row)"
            >
              {{ i18nT("ai_ontology.close") }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建 -->
    <el-dialog
      v-model="createVisible"
      :title="i18nT('ai_ontology.newBranchProposal')"
      width="600px"
      append-to-body
    >
      <el-form label-width="90px">
        <el-form-item :label="i18nT('ai_ontology.title')" required>
          <el-input
            v-model="createForm.title"
            :placeholder="i18nT('ai_ontology.eGAddAMaintenanceStatusFieldToCameras')"
          />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.note')">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="
          i18nT(
            'ai_ontology.creatingABranchAutoGeneratesAProposalOfficialEachDefinitionChangeBecomesATaskInTheProposal'
          )
        "
      />
      <template #footer>
        <el-button @click="createVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doCreate"
        >
          {{ i18nT("ai_ontology.create") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-drawer
      v-model="detailVisible"
      :title="detail?.title || i18nT('ai_ontology.proposalDetail')"
      size="66%"
    >
      <template v-if="detail">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item :label="i18nT('ai_ontology.code')">
            <span class="ont-mono">{{ detail.code }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.branch')">
            <span class="ont-mono">{{ detail.branch_code }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.stage')">
            <el-tag size="small" effect="plain" :type="stageTag(detail.stage)">
              {{ detail.stage_label }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.create')">
            {{ detail.created_by }} · {{ detail.created_time }}
          </el-descriptions-item>
          <el-descriptions-item :label="i18nT('ai_ontology.reviewer2')" :span="2">
            <el-tag
              v-for="r in detail.reviewers"
              :key="r"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ r }}
            </el-tag>
            <span v-if="!detail.reviewers?.length" class="ont-none">
              {{ i18nT("ai_ontology.unassigned") }}
            </span>
            <el-button link type="primary" size="small" class="ont-pr__ml" @click="openReviewers">
              {{ i18nT("ai_ontology.assignReviewer") }}
            </el-button>
          </el-descriptions-item>
        </el-descriptions>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.tasks") }}</span>
          <el-tag size="small" effect="plain">
            {{ i18nT("ai_ontology.countUnit", { count: detail.tasks?.length || 0 }) }}
          </el-tag>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            class="ont-sec__op"
            size="small"
            type="success"
            :disabled="detail.stage === 'merged' || detail.stage === 'closed'"
            @click="doReviewAll(true)"
          >
            {{ i18nT("ai_ontology.batchApprove") }}
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            size="small"
            type="danger"
            plain
            :disabled="detail.stage === 'merged' || detail.stage === 'closed'"
            @click="doReviewAll(false)"
          >
            {{ i18nT("ai_ontology.batchReject") }}
          </el-button>
        </div>
        <el-table :data="detail.tasks || []" size="small" border max-height="320" stripe>
          <template #empty>
            <el-empty :image-size="50" :description="i18nT('ai_ontology.noChangesOnThisBranch')" />
          </template>
          <el-table-column
            :label="i18nT('ai_ontology.resource')"
            min-width="200"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              <span class="ont-mono">{{ row.resource_kind }}</span>
              {{ row.resource_name }}
            </template>
          </el-table-column>
          <el-table-column
            prop="change_kind_label"
            :label="i18nT('ai_ontology.changes')"
            width="80"
          />
          <el-table-column :label="i18nT('ai_ontology.fieldDiff')" min-width="260">
            <template #default="{ row }">
              <div class="ont-pr__diff">
                <span v-for="d in diffOf(row)" :key="d.field" class="ont-mono">
                  {{ d.field }}: {{ fmt(d.before) }} → {{ fmt(d.after) }}
                </span>
                <span v-if="!diffOf(row).length" class="ont-none">—</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="i18nT('ai_ontology.status')" width="90">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="taskTag(row.status)">
                {{ row.status_label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reviewed_by" :label="i18nT('ai_ontology.reviewer')" width="100" />
          <el-table-column :label="i18nT('ai_ontology.operations')" width="180" align="center">
            <template #default="{ row }">
              <el-button
                v-hasPerm="'module_ai:ontology:manage'"
                icon="Check"
                link
                type="success"
                size="small"
                :disabled="row.status === 'approved' || detail.stage === 'merged'"
                @click="doReview(row, true)"
              >
                {{ i18nT("ai_ontology.approve") }}
              </el-button>
              <el-button
                v-hasPerm="'module_ai:ontology:manage'"
                icon="Close"
                link
                type="danger"
                size="small"
                :disabled="row.status === 'rejected' || detail.stage === 'merged'"
                @click="doReview(row, false)"
              >
                {{ i18nT("ai_ontology.reject2") }}
              </el-button>
              <el-button
                v-hasPerm="'module_ai:ontology:manage'"
                icon="Delete"
                link
                type="info"
                size="small"
                :disabled="detail.stage === 'merged'"
                @click="doDiscard(row)"
              >
                {{ i18nT("ai_ontology.discard") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="ont-sec__head ont-sec__head--mt">
          <span class="ont-sec__title">{{ i18nT("ai_ontology.changeLog") }}</span>
          <span class="ont-hint">{{ i18nT("ai_ontology.whoChangedWhatWhen") }}</span>
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
                {{
                  i18nT("ai_ontology.editCountWithAuthors", {
                    count: c.edit_count,
                    authors: (c.authors || []).join("、"),
                  })
                }}
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
          <span class="ont-sec__title">{{ i18nT("ai_ontology.discussion") }}</span>
          <el-tag size="small" effect="plain">
            {{ i18nT("ai_ontology.commentsCount", { count: (detail.comments || []).length }) }}
          </el-tag>
        </div>
        <el-empty
          v-if="!(detail.comments || []).length"
          :image-size="50"
          :description="i18nT('ai_ontology.noCommentsYet')"
        />
        <div v-else class="ont-pr__comments">
          <div v-for="c in detail.comments" :key="c.id" class="ont-pr__comment">
            <div class="ont-pr__comment-head">
              <span class="ont-pr__comment-author">
                {{ c.author || i18nT("ai_ontology.anonymous") }}
              </span>
              <span class="ont-hint">{{ c.created_time }}</span>
              <el-tag v-if="c.task_id" size="small" effect="plain">
                {{ i18nT("ai_ontology.taskHash", { id: c.task_id }) }}
              </el-tag>
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
            :placeholder="i18nT('ai_ontology.commentPlaceholder')"
          />
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            type="primary"
            :loading="commenting"
            :disabled="!commentBody.trim()"
            @click="doComment"
          >
            {{ i18nT("ai_ontology.comment") }}
          </el-button>
        </div>

        <div class="ont-pr__actions">
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            type="success"
            :disabled="!canMerge"
            @click="doMerge(detail)"
          >
            {{ i18nT("ai_ontology.mergeToPrimaryOntology") }}
          </el-button>
          <el-button
            :disabled="detail.stage === 'in_review' || detail.stage === 'merged'"
            @click="openReviewers"
          >
            {{ i18nT("ai_ontology.requestReview") }}
          </el-button>
          <el-button
            v-hasPerm="'module_ai:ontology:manage'"
            type="danger"
            plain
            :disabled="detail.stage === 'merged' || detail.stage === 'closed'"
            @click="doClose(detail)"
          >
            {{ i18nT("ai_ontology.closeProposal") }}
          </el-button>
        </div>
      </template>
    </el-drawer>

    <!-- 指派审查者 -->
    <el-dialog
      v-model="reviewerVisible"
      :title="i18nT('ai_ontology.assignReviewer')"
      width="520px"
      append-to-body
    >
      <el-select
        v-model="reviewers"
        multiple
        filterable
        style="width: 100%"
        :placeholder="i18nT('ai_ontology.selectReviewer')"
      >
        <el-option
          v-for="u in users"
          :key="u.id"
          :label="i18nT('ai_ontology.userNameWithUsername', { name: u.name, username: u.username })"
          :value="u.username"
        />
      </el-select>
      <el-alert
        type="warning"
        :closable="false"
        class="ont-note"
        :title="
          i18nT(
            'ai_ontology.reviewersAreNotifiedWhenAProposalEntersReviewApprovingATaskNeedsEditPermissionOnTheResource'
          )
        "
      />
      <template #footer>
        <el-button @click="reviewerVisible = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button
          v-hasPerm="'module_ai:ontology:manage'"
          type="primary"
          :loading="busy"
          @click="doRequestReview"
        >
          {{ i18nT("ai_ontology.requestReview") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
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

const { t: i18nT } = useI18n();

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
  if (v === null || v === undefined || v === "") return i18nT("ai_ontology.empty");
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
    ElMessage.error(e?.msg || i18nT("ai_ontology.loadProposalFailed"));
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
  if (!createForm.value.title.trim())
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterTitle"));
  busy.value = true;
  try {
    const r = await createOntBranch(createForm.value.title, createForm.value.description);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.created"));
    createVisible.value = false;
    await load();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.createFailed"));
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
  if (!body) return ElMessage.warning(i18nT("ai_ontology.pleaseWriteAComment"));
  commenting.value = true;
  try {
    const r = await commentOntProposal(detail.value.code, body);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.commented"));
    commentBody.value = "";
    await refreshDetail();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.commentFailed"));
  } finally {
    commenting.value = false;
  }
}

/* ---------------- 审查 ---------------- */
async function doReview(row: any, approve: boolean) {
  try {
    const r = await reviewOntProposalTask(row.id, approve);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || i18nT("ai_ontology.processed"));
    await refreshDetail();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.reviewFailed"));
  }
}

async function doReviewAll(approve: boolean) {
  const r = await reviewAllOntProposalTasks(detail.value.code, approve);
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.processed"));
  await refreshDetail();
}

async function doDiscard(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.discardTaskConfirm", {
      resource: `${row.resource_kind} ${row.resource_name}`,
    }),
    i18nT("ai_ontology.discardTasks"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.discard"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  const r = await discardOntProposalTask(row.id);
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.discarded"));
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
  if (!reviewers.value.length)
    return ElMessage.warning(i18nT("ai_ontology.pleaseSelectAtLeastOneReviewer"));
  busy.value = true;
  try {
    const r = await requestOntProposalReview(detail.value.code, reviewers.value);
    ElMessage.success(r.data?.msg || i18nT("ai_ontology.reviewRequested"));
    reviewerVisible.value = false;
    await refreshDetail();
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.requestFailed"));
  } finally {
    busy.value = false;
  }
}

/* ---------------- 合并 / 关闭 ---------------- */
async function doMerge(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.mergeProposalConfirm", {
      title: row.title,
      count: row.task_count ?? (detail.value?.tasks || []).length,
    }),
    i18nT("ai_ontology.mergeProposal"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.merge"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  try {
    const r = await mergeOntProposal(row.code);
    if (r.data?.data?.ok === false) ElMessage.warning(r.data.msg);
    else ElMessage.success(r.data?.msg || i18nT("ai_ontology.merged"));
    detailVisible.value = false;
    await load();
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.msg || i18nT("ai_ontology.mergeFailed"));
  }
}

async function doClose(row: any) {
  await ElMessageBox.confirm(
    i18nT("ai_ontology.closeProposalConfirm", {
      title: row.title,
      count: row.task_count ?? 0,
    }),
    i18nT("ai_ontology.closeProposal"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.close"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  const r = await closeOntProposal(row.code);
  ElMessage.success(r.data?.msg || i18nT("ai_ontology.closed"));
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
