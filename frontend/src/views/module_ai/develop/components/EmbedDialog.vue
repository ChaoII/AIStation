<!--
  应用「嵌入」弹窗：选目标 → 生成 iframe / Script SDK 代码 → 签体验票 → 令牌治理。
  凭证约定：代码内只出现短期 access_token 占位符；appkey 永不进入网页。
  样式与系统管理模块一致：el-form 标签 + el-table + el-tag + el-alert，仅用 --el-* 变量。
-->
<template>
  <el-dialog
    v-model="visible"
    :title="t('ai_workflow.develop_embedTitle', { name: app?.name || '' })"
    width="640px"
    top="6vh"
    append-to-body
    @closed="resetState"
  >
    <el-form label-width="94px" class="embed-dialog">
      <el-form-item :label="t('ai_workflow.develop_embedKind')">
        <el-radio-group v-model="kind" @change="onKindChange">
          <el-radio-button value="agent">Agent</el-radio-button>
          <el-radio-button value="app">{{ t("ai_workflow.develop_embedApp") }}</el-radio-button>
          <el-radio-button value="workflow">
            {{ t("ai_workflow.develop_embedWorkflow") }}
          </el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="t('ai_workflow.develop_embedTarget')">
        <el-select
          v-model="targetId"
          filterable
          clearable
          :loading="loadingTargets"
          :placeholder="t('ai_workflow.develop_embedTargetPlaceholder')"
          class="embed-dialog__select"
          @change="mintedToken = ''"
        >
          <el-option v-for="t in targets" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('ai_workflow.develop_embedCode')">
        <div class="embed-dialog__code">
          <el-tabs v-model="codeTab">
            <el-tab-pane :label="t('ai_workflow.develop_embedTabIframe')" name="iframe">
              <pre class="embed-dialog__pre">{{ codeFor("iframe") }}</pre>
            </el-tab-pane>
            <el-tab-pane label="Script SDK" name="script">
              <pre class="embed-dialog__pre">{{ codeFor("script") }}</pre>
            </el-tab-pane>
          </el-tabs>
          <div class="embed-dialog__actions">
            <el-button size="small" :disabled="!targetId" @click="copyCode">
              <el-icon><CopyDocument /></el-icon>
              {{ t("ai_workflow.develop_embedCopyCode") }}
            </el-button>
            <el-button
              v-hasPerm="'module_ai:develop:create'"
              size="small"
              type="primary"
              plain
              :disabled="!targetId"
              :loading="minting"
              @click="onMint"
            >
              {{ t("ai_workflow.develop_embedMintToken") }}
            </el-button>
          </div>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="embed-dialog__alert"
            :title="t('ai_workflow.develop_embedCredTitle')"
            :description="
              t('ai_workflow.develop_embedCredDesc', {
                access_token: '{access_token}',
                apiBase,
              })
            "
          />
        </div>
      </el-form-item>

      <el-form-item :label="t('ai_workflow.develop_embedIssuedTokens')">
        <el-table
          v-loading="loadingTokens"
          :data="tokens"
          size="small"
          border
          stripe
          max-height="150"
        >
          <template #empty>
            <el-empty :image-size="80" :description="t('ai_workflow.develop_embedNoTokens')" />
          </template>
          <el-table-column :label="t('ai_workflow.develop_embedKindShort')" width="74">
            <template #default="{ row }">
              <div>{{ kindLabel(row.kind) }}</div>
              <div class="embed-dialog__sub">
                {{
                  row.issued_by === "admin"
                    ? t("ai_workflow.develop_embedTrialTicket")
                    : t("ai_workflow.develop_embedIssuedTicket")
                }}
              </div>
            </template>
          </el-table-column>
          <el-table-column
            prop="target_name"
            :label="t('ai_workflow.develop_embedTargetShort')"
            min-width="84"
            show-overflow-tooltip
          />
          <el-table-column :label="t('ai_workflow.develop_embedExpireTime')" width="110">
            <template #default="{ row }">
              <span :title="row.expires_at">{{ fmtShort(row.expires_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="use_count"
            :label="t('ai_workflow.develop_embedUsage')"
            width="50"
            align="right"
          />
          <el-table-column :label="t('ai_workflow.develop_embedStatus')" width="76">
            <template #default="{ row }">
              <el-tag size="small" :type="row.revoked ? 'info' : 'success'" effect="plain">
                {{
                  row.revoked
                    ? t("ai_workflow.develop_embedRevoked")
                    : t("ai_workflow.develop_embedValid")
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.develop_embedAction')" width="56">
            <template #default="{ row }">
              <el-button
                v-if="!row.revoked"
                v-hasPerm="'module_ai:develop:update'"
                link
                type="danger"
                size="small"
                @click="onRevoke(row)"
              >
                {{ t("ai_workflow.develop_embedRevoke") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-form-item>

      <el-form-item :label="t('ai_workflow.develop_embedEvents')">
        <div class="embed-dialog__events">
          <el-tag
            v-for="e in EVENTS"
            :key="e.name"
            size="small"
            effect="plain"
            class="embed-dialog__tag"
            :title="e.desc"
          >
            {{ e.name }}
          </el-tag>
        </div>
        <div class="embed-dialog__note">
          {{ t("ai_workflow.develop_embedEventsNote") }}
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">{{ t("ai_workflow.develop_close") }}</el-button>
    </template>

    <!-- 体验票一次性展示 -->
    <el-dialog
      v-model="reveal.visible"
      :title="t('ai_workflow.develop_embedRevealTitle')"
      width="520px"
      append-to-body
    >
      <el-alert
        :title="t('ai_workflow.develop_embedRevealAlertTitle')"
        type="warning"
        :closable="false"
        show-icon
        :description="t('ai_workflow.develop_embedRevealAlertDesc')"
      />
      <el-descriptions :column="1" border size="small" class="embed-dialog__reveal">
        <el-descriptions-item label="Token">
          <div class="embed-dialog__token">
            <span>{{ reveal.token }}</span>
            <el-button link type="primary" size="small" @click="copyText(reveal.token)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.develop_embedExpireTime')">
          {{ reveal.expiresAt }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="reveal.visible = false">{{ t("ai_workflow.develop_close") }}</el-button>
        <el-button type="primary" @click="applyRevealToken">
          {{ t("ai_workflow.develop_embedApplyCode") }}
        </el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { CopyDocument } from "@element-plus/icons-vue";
import { getAiAgentList } from "@/api/module_ai/agent";
import { getAiAppList } from "@/api/module_ai/app";
import { getAiWorkflowList } from "@/api/module_ai/workflow";
import { getEmbedTokens, mintEmbedToken, revokeEmbedToken } from "@/api/module_ai/develop";

defineOptions({ name: "AiEmbedDialog" });

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  app: Record<string, any> | null;
}>();
const emit = defineEmits<{ (e: "update:modelValue", value: boolean): void }>();

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const apiBase = `${location.origin}/api/v1/ai`;
const webBase = `${location.origin}${import.meta.env.BASE_URL.replace(/\/$/, "")}`;

const EVENTS = [
  { name: "ready", desc: t("ai_workflow.develop_eventReady") },
  { name: "user_message", desc: t("ai_workflow.develop_eventUserMessage") },
  { name: "reply_start", desc: t("ai_workflow.develop_eventReplyStart") },
  { name: "reply_delta", desc: t("ai_workflow.develop_eventReplyDelta") },
  { name: "reply_done", desc: t("ai_workflow.develop_eventReplyDone") },
  { name: "error", desc: t("ai_workflow.develop_eventError") },
  { name: "token_expired", desc: t("ai_workflow.develop_eventTokenExpired") },
];

const kind = ref<"agent" | "app" | "workflow">("agent");
const targetId = ref<number | undefined>(undefined);
const targets = ref<{ id: number; name: string }[]>([]);
const loadingTargets = ref(false);
const codeTab = ref<"iframe" | "script">("iframe");
const mintedToken = ref("");
const minting = ref(false);
const tokens = ref<any[]>([]);
const loadingTokens = ref(false);
const reveal = reactive({ visible: false, token: "", expiresAt: "" });

function kindLabel(k: string): string {
  return (
    {
      agent: "Agent",
      app: t("ai_workflow.develop_embedApp"),
      workflow: t("ai_workflow.develop_embedWorkflow"),
    }[k] || k
  );
}

/** 令牌过期时间：同一天内显示「MM-DD HH:mm」，表格窄列不折行。 */
function fmtShort(v?: string): string {
  if (!v) return "—";
  return v.length >= 16 ? v.slice(5, 16) : v;
}

function normalizeList(res: any): any[] {
  const d = res?.data?.data;
  if (Array.isArray(d)) return d;
  if (Array.isArray(d?.items)) return d.items;
  return [];
}

async function loadTargets() {
  loadingTargets.value = true;
  targetId.value = undefined;
  try {
    const res =
      kind.value === "agent"
        ? await getAiAgentList()
        : kind.value === "app"
          ? await getAiAppList({ page_no: 1, page_size: 100 })
          : await getAiWorkflowList();
    targets.value = normalizeList(res)
      .filter((t: any) => t.enabled !== false)
      .map((t: any) => ({ id: t.id, name: t.name }));
  } catch {
    targets.value = [];
    ElMessage.error(t("ai_workflow.develop_embedTargetsLoadFail"));
  } finally {
    loadingTargets.value = false;
  }
}

function onKindChange() {
  mintedToken.value = "";
  loadTargets();
}

async function loadTokens() {
  if (!props.app?.id) return;
  loadingTokens.value = true;
  try {
    const res = await getEmbedTokens(props.app.id);
    tokens.value = res?.data?.data?.items || [];
  } catch {
    tokens.value = [];
  } finally {
    loadingTokens.value = false;
  }
}

function resetState() {
  kind.value = "agent";
  targetId.value = undefined;
  targets.value = [];
  tokens.value = [];
  codeTab.value = "iframe";
  mintedToken.value = "";
  reveal.visible = false;
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    void loadTargets();
    void loadTokens();
  }
);

/* ---------- 代码模板 ---------- */
function codeFor(tab: "iframe" | "script"): string {
  const token = mintedToken.value || "{access_token}";
  if (tab === "iframe") {
    return `<iframe\n  src="${webBase}/#/embed?token=${token}"\n  width="420" height="620"\n  style="border:0;border-radius:12px"\n  title="${t("ai_workflow.develop_embedIframeTitle")}"\n></iframe>`;
  }
  return (
    `<script src="${apiBase}/embed/sdk.js"></scr` +
    `ipt>\n<div id="ai-assistant" style="width:420px;height:620px"></div>\n<script>\n  AiAssistant.init({\n    container: "#ai-assistant",\n    token: "${token}",\n    apiBase: "${apiBase}",\n    webBase: "${webBase}",\n    theme: { primary: "#409eff" },\n  });\n</scr` +
    `ipt>`
  );
}

function copyText(text?: string) {
  if (!text) return;
  navigator.clipboard?.writeText(text).then(
    () => ElMessage.success(t("ai_workflow.develop_copied")),
    () => ElMessage.error(t("ai_workflow.develop_copyFailManual"))
  );
}

function copyCode() {
  copyText(codeFor(codeTab.value));
}

/* ---------- 体验票 ---------- */
async function onMint() {
  if (!props.app?.id || !targetId.value) return;
  minting.value = true;
  try {
    const res = await mintEmbedToken({
      app_id: props.app.id,
      kind: kind.value,
      target_id: targetId.value,
    });
    const d = res?.data?.data || {};
    reveal.token = d.token || "";
    reveal.expiresAt = d.expires_at || "";
    reveal.visible = true;
    void loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_embedMintFail"));
  } finally {
    minting.value = false;
  }
}

function applyRevealToken() {
  mintedToken.value = reveal.token;
  reveal.visible = false;
  ElMessage.success(t("ai_workflow.develop_embedApplySuccess"));
}

/* ---------- 吊销 ---------- */
async function onRevoke(row: any) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.develop_embedRevokeConfirm"),
      t("ai_workflow.develop_embedRevokeTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.develop_embedRevoke"),
        cancelButtonText: t("ai_workflow.develop_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    await revokeEmbedToken(row.id);
    ElMessage.success(t("ai_workflow.develop_embedRevoked"));
    await loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_embedRevokeFail"));
  }
}
</script>

<style scoped>
.embed-dialog {
  max-height: 70vh;
  padding-right: 6px;
  overflow-y: auto;
}

.embed-dialog :deep(.el-form-item) {
  margin-bottom: 14px;
}

.embed-dialog :deep(.el-form-item:last-child) {
  margin-bottom: 4px;
}

.embed-dialog__select {
  width: 100%;
}

.embed-dialog__code {
  width: 100%;
}

.embed-dialog__code :deep(.el-tabs__content) {
  overflow: visible;
}

.embed-dialog__pre {
  max-height: 150px;
  padding: 10px 12px;
  margin: 0;
  overflow: auto;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.embed-dialog__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 8px;
}

.embed-dialog__alert {
  margin-top: 10px;
}

.embed-dialog__events {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
}

.embed-dialog__tag {
  font-family: var(--el-font-family-mono, monospace);
}

.embed-dialog__sub {
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}

.embed-dialog__note {
  width: 100%;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.embed-dialog__reveal {
  margin-top: 12px;
}

.embed-dialog__token {
  display: flex;
  gap: 6px;
  align-items: center;
  font-family: var(--el-font-family-mono, monospace);
  color: var(--el-color-primary);
  word-break: break-all;
}
</style>
