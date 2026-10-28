<!--
  工作台「资产嵌入」弹窗：固定当前 agent/工作流，展示三种嵌入形式
  （聊天气泡 Script SDK / iframe / 运行 API），分层管理令牌：接入代码 / 令牌管理 / 使用日志。
  令牌与开放平台应用无关（不出现 appid/appkey 换票）。样式与系统管理一致，仅用 --el-* 变量。
-->
<template>
  <el-dialog
    v-model="visible"
    :title="t('ai_workflow.asset_embed_title', { name: props.name || '' })"
    width="640px"
    top="6vh"
    append-to-body
    @closed="resetState"
  >
    <el-tabs v-model="section" class="asset-embed-dialog__tabs">
      <!-- ============ 1. 接入代码 ============ -->
      <el-tab-pane :label="t('ai_workflow.asset_embed_section_code')" name="code">
        <el-form label-width="94px" class="asset-embed-dialog">
          <el-form-item :label="t('ai_workflow.asset_embed_form')">
            <el-radio-group v-model="formTab">
              <el-radio-button value="bubble">
                {{ t("ai_workflow.asset_embed_chatBubble") }}
              </el-radio-button>
              <el-radio-button value="iframe">iframe</el-radio-button>
              <el-radio-button value="run">
                {{ t("ai_workflow.asset_embed_runApi") }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item :label="t('ai_workflow.asset_embed_code')">
            <div class="asset-embed-dialog__code">
              <pre class="asset-embed-dialog__pre hljs"><code v-html="highlightedCode"></code></pre>
              <div class="asset-embed-dialog__actions">
                <el-button size="small" :icon="CopyDocument" @click="copyCode">
                  {{ t("ai_workflow.develop_embedCopyCode") }}
                </el-button>
                <el-button
                  v-hasPerm="'module_ai:asset_embed:manage'"
                  size="small"
                  type="primary"
                  plain
                  :loading="minting"
                  @click="openMint"
                >
                  {{ t("ai_workflow.asset_embed_mint") }}
                </el-button>
              </div>
            </div>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- ============ 2. 令牌管理 ============ -->
      <el-tab-pane :label="t('ai_workflow.asset_embed_section_tokens')" name="tokens">
        <div class="asset-embed-dialog__toolbar">
          <el-button
            v-hasPerm="'module_ai:asset_embed:manage'"
            size="small"
            type="primary"
            :icon="Plus"
            @click="openMint"
          >
            {{ t("ai_workflow.asset_embed_mint") }}
          </el-button>
        </div>
        <el-table
          v-loading="loadingTokens"
          :data="tokens"
          size="small"
          border
          stripe
          max-height="320"
        >
          <template #empty>
            <el-empty :image-size="80" :description="t('ai_workflow.asset_embed_noTokens')" />
          </template>
          <el-table-column :label="t('ai_workflow.asset_embed_issuer')" width="78">
            <template #default="{ row }">
              <span class="asset-embed-dialog__sub">{{ row.issued_by || "admin" }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.asset_embed_expireTime')" width="100">
            <template #default="{ row }">
              <span :title="row.expires_at">{{ fmtShort(row.expires_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="use_count"
            :label="t('ai_workflow.asset_embed_usage')"
            width="46"
            align="right"
          />
          <el-table-column :label="t('ai_workflow.asset_embed_status')" width="66">
            <template #default="{ row }">
              <el-tag size="small" :type="row.revoked ? 'info' : 'success'" effect="plain">
                {{
                  row.revoked
                    ? t("ai_workflow.asset_embed_revoked")
                    : t("ai_workflow.asset_embed_valid")
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.asset_embed_whitelist')" min-width="84">
            <template #default="{ row }">
              <span class="asset-embed-dialog__sub" :title="whitelistText(row)">
                {{ whitelistText(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.asset_embed_action')" width="212" fixed="right">
            <template #default="{ row }">
              <el-button
                v-hasPerm="'module_ai:asset_embed:manage'"
                link
                type="primary"
                size="small"
                @click="openEditWhitelist(row)"
              >
                {{ t("ai_workflow.asset_embed_editWhitelist") }}
              </el-button>
              <el-button link type="primary" size="small" @click="viewLogs(row)">
                {{ t("ai_workflow.asset_embed_viewLogs") }}
              </el-button>
              <el-button
                v-if="!row.revoked"
                v-hasPerm="'module_ai:asset_embed:manage'"
                link
                type="danger"
                size="small"
                @click="onRevoke(row)"
              >
                {{ t("ai_workflow.asset_embed_revoke") }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ============ 3. 使用日志 ============ -->
      <el-tab-pane :label="t('ai_workflow.asset_embed_section_logs')" name="logs">
        <el-table v-loading="loadingLogs" :data="logs" size="small" border stripe max-height="320">
          <template #empty>
            <el-empty :image-size="80" :description="t('ai_workflow.asset_embed_noLogs')" />
          </template>
          <el-table-column :label="t('ai_workflow.asset_embed_time')" width="150">
            <template #default="{ row }">
              <span class="asset-embed-dialog__logtime">{{ row.created_time || "—" }}</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="client_ip"
            :label="t('ai_workflow.asset_embed_clientIp')"
            width="120"
          />
          <el-table-column :label="t('ai_workflow.asset_embed_result')" width="90">
            <template #default="{ row }">
              <el-tag
                size="small"
                :type="row.result_status === 'success' ? 'success' : 'danger'"
                effect="plain"
              >
                {{
                  row.result_status === "success"
                    ? t("ai_workflow.asset_embed_resultSuccess")
                    : t("ai_workflow.asset_embed_resultError")
                }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('ai_workflow.asset_embed_latency')" width="80" align="right">
            <template #default="{ row }">
              <span class="asset-embed-dialog__sub">{{ row.latency_ms ?? 0 }} ms</span>
            </template>
          </el-table-column>
          <el-table-column
            prop="message"
            :label="t('ai_workflow.asset_embed_message')"
            min-width="120"
            show-overflow-tooltip
          />
        </el-table>
        <div class="asset-embed-dialog__pager">
          <el-pagination
            v-model:current-page="logPage"
            v-model:page-size="logSize"
            :total="logTotal"
            :page-sizes="[10, 20, 50]"
            background
            layout="total, sizes, prev, pager, next"
            @current-change="loadTokenLogs"
            @size-change="loadTokenLogs"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="visible = false">{{ t("ai_workflow.develop_close") }}</el-button>
    </template>

    <!-- 令牌一次性展示 -->
    <el-dialog
      v-model="reveal.visible"
      :title="t('ai_workflow.asset_embed_revealTitle')"
      width="520px"
      append-to-body
    >
      <el-alert
        :title="t('ai_workflow.asset_embed_revealAlertTitle')"
        type="warning"
        :closable="false"
        show-icon
        :description="t('ai_workflow.asset_embed_revealAlertDesc')"
      />
      <el-descriptions :column="1" border size="small" class="asset-embed-dialog__reveal">
        <el-descriptions-item label="Token">
          <div class="asset-embed-dialog__token">
            <span>{{ reveal.token }}</span>
            <el-button link type="primary" size="small" @click="copyText(reveal.token)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item :label="t('ai_workflow.asset_embed_expireTime')">
          {{ reveal.expiresAt }}
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="reveal.visible = false">{{ t("ai_workflow.develop_close") }}</el-button>
        <el-button type="primary" @click="applyRevealToken">
          {{ t("ai_workflow.asset_embed_applyCode") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 生成令牌 -->
    <el-dialog
      v-model="mint.visible"
      :title="t('ai_workflow.asset_embed_mintFormTitle')"
      width="520px"
      append-to-body
    >
      <el-form :model="mint.form" label-width="94px">
        <el-form-item :label="t('ai_workflow.asset_embed_ttl')">
          <el-select v-model="mint.form.tier" style="width: 100%">
            <el-option
              v-for="opt in ttlOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('ai_workflow.asset_embed_allowDomains')">
          <el-input
            v-model="mint.form.allow_domains"
            :placeholder="t('ai_workflow.asset_embed_whitelistPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.asset_embed_allowIps')">
          <el-input
            v-model="mint.form.allow_ips"
            :placeholder="t('ai_workflow.asset_embed_whitelistPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="mint.visible = false">{{ t("ai_workflow.develop_cancel") }}</el-button>
        <el-button type="primary" :loading="minting" @click="submitMint">
          {{ t("ai_workflow.asset_embed_mint") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 编辑白名单 -->
    <el-dialog
      v-model="edit.visible"
      :title="t('ai_workflow.asset_embed_editWhitelist')"
      width="520px"
      append-to-body
    >
      <el-form :model="edit.form" label-width="94px">
        <el-form-item :label="t('ai_workflow.asset_embed_allowDomains')">
          <el-input
            v-model="edit.form.allow_domains"
            :placeholder="t('ai_workflow.asset_embed_whitelistPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('ai_workflow.asset_embed_allowIps')">
          <el-input
            v-model="edit.form.allow_ips"
            :placeholder="t('ai_workflow.asset_embed_whitelistPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="edit.visible = false">{{ t("ai_workflow.develop_cancel") }}</el-button>
        <el-button type="primary" :loading="edit.saving" @click="submitEditWhitelist">
          {{ t("ai_workflow.asset_embed_save") }}
        </el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElMessageBox } from "element-plus";
import { CopyDocument, Plus } from "@element-plus/icons-vue";
import hljs from "highlight.js";
import "highlight.js/styles/atom-one-light.css";
import {
  issueAssetToken,
  listAssetTokens,
  listAssetTokenLogs,
  revokeAssetToken,
  updateAssetToken,
} from "@/api/module_ai/assetEmbed";

defineOptions({ name: "AssetEmbedDialog" });

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  kind: "agent" | "workflow";
  targetId: number;
  name?: string;
}>();
const emit = defineEmits<{ (e: "update:modelValue", value: boolean): void }>();

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit("update:modelValue", v),
});

const apiBase = `${location.origin}/api/v1/ai`;
const webBase = `${location.origin}${import.meta.env.BASE_URL.replace(/\/$/, "")}`;

const section = ref<"code" | "tokens" | "logs">("code");
const formTab = ref<"bubble" | "iframe" | "run">("bubble");
const mintedToken = ref("");
const minting = ref(false);
const tokens = ref<any[]>([]);
const loadingTokens = ref(false);
const reveal = reactive({ visible: false, token: "", expiresAt: "" });

/* ---------- 生成 / 编辑白名单 子弹窗 ---------- */
const ttlOptions = computed(() => [
  { label: t("ai_workflow.asset_embed_ttl_1h"), value: "1h", ttl: 3600, permanent: false },
  { label: t("ai_workflow.asset_embed_ttl_24h"), value: "24h", ttl: 86400, permanent: false },
  { label: t("ai_workflow.asset_embed_ttl_7d"), value: "7d", ttl: 604800, permanent: false },
  { label: t("ai_workflow.asset_embed_ttl_30d"), value: "30d", ttl: 2592000, permanent: false },
  { label: t("ai_workflow.asset_embed_ttl_forever"), value: "forever", ttl: null, permanent: true },
]);

const mint = reactive({
  visible: false,
  form: { tier: "24h", allow_domains: "", allow_ips: "" },
});
const edit = reactive({
  visible: false,
  saving: false,
  id: 0,
  form: { allow_domains: "", allow_ips: "" },
});

/* ---------- 使用日志 ---------- */
const logs = ref<any[]>([]);
const loadingLogs = ref(false);
const logPage = ref(1);
const logSize = ref(10);
const logTotal = ref(0);
const logTokenId = ref<number | null>(null);

function fmtShort(v?: string): string {
  if (!v) return "—";
  return v.length >= 16 ? v.slice(5, 16) : v;
}

function whitelistText(row: any): string {
  const d = row.allow_domains || "";
  const i = row.allow_ips || "";
  if (!d && !i) return t("ai_workflow.asset_embed_unbounded");
  const parts: string[] = [];
  if (d) parts.push(`域名:${d}`);
  if (i) parts.push(`IP:${i}`);
  return parts.join(" / ");
}

async function loadTokens() {
  loadingTokens.value = true;
  try {
    const res = await listAssetTokens(props.kind, props.targetId);
    tokens.value = res?.data?.data?.items || [];
  } catch {
    tokens.value = [];
  } finally {
    loadingTokens.value = false;
  }
}

async function loadTokenLogs() {
  if (logTokenId.value == null) return;
  loadingLogs.value = true;
  try {
    const res = await listAssetTokenLogs(logTokenId.value, {
      page_no: logPage.value,
      page_size: logSize.value,
    });
    const d = res?.data?.data || {};
    logs.value = d.items || [];
    logTotal.value = d.total || 0;
  } catch {
    logs.value = [];
    logTotal.value = 0;
  } finally {
    loadingLogs.value = false;
  }
}

function resetState() {
  section.value = "code";
  formTab.value = "bubble";
  mintedToken.value = "";
  tokens.value = [];
  reveal.visible = false;
  mint.visible = false;
  edit.visible = false;
  logs.value = [];
  logTokenId.value = null;
  logPage.value = 1;
  logTotal.value = 0;
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void loadTokens();
  }
);

/* ---------- 三种形式的接入代码（含 {token} 占位与已生成令牌） ---------- */
function codeFor(tab: "bubble" | "iframe" | "run"): string {
  const token = mintedToken.value || "{token}";
  if (tab === "iframe") {
    return `<iframe\n  src="${webBase}/#/embed?token=${token}"\n  width="420" height="620"\n  style="border:0;border-radius:12px"\n  title="${props.name || "嵌入对话"}"\n></iframe>`;
  }
  if (tab === "run") {
    return `# 运行 API：直接把该 agent/工作流 的对话接口以 SSE 暴露给外部
curl -N "https://<host>/api/v1/ai/embed/run" \\
  -H "Authorization: Bearer ${token}" \\
  -H "Content-Type: application/json" \\
  -d '{"sid": "your-session-id", "message": "你好"}'

# 浏览器端用 fetch 消费 SSE（自行渲染回复流）
const resp = await fetch("/api/v1/ai/embed/run", {
  method: "POST",
  headers: { "Authorization": "Bearer ${token}", "Content-Type": "application/json" },
  body: JSON.stringify({ sid: "your-session-id", message: "你好" }),
});
// 读取 resp.body 流，按行解析 SSE（data: {type:"reply_delta", delta:"..."})`;
  }
  return (
    `<script src="${apiBase}/embed/sdk.js"></scr` +
    `ipt>\n<div id="ai-assistant" style="width:420px;height:620px"></div>\n<script>\n  AiAssistant.init({\n    container: "#ai-assistant",\n    token: "${token}",\n    apiBase: "${apiBase}",\n    webBase: "${webBase}",\n  });\n</scr` +
    `ipt>`
  );
}

/* ---------- 接入代码语法高亮（与「接入文档」一致的 hljs） ---------- */
const codeLang = (tab: "bubble" | "iframe" | "run"): string => (tab === "run" ? "bash" : "xml");

const highlightedCode = computed(() => {
  const code = codeFor(formTab.value);
  try {
    return hljs.highlight(code, {
      language: codeLang(formTab.value),
      ignoreIllegals: true,
    }).value;
  } catch {
    return code.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
});

function copyText(text?: string) {
  if (!text) return;
  navigator.clipboard?.writeText(text).then(
    () => ElMessage.success(t("ai_workflow.develop_copied")),
    () => ElMessage.error(t("ai_workflow.develop_copyFailManual"))
  );
}

function copyCode() {
  copyText(codeFor(formTab.value));
}

/* ---------- 生成令牌 ---------- */
function openMint() {
  mint.form = { tier: "24h", allow_domains: "", allow_ips: "" };
  mint.visible = true;
}

async function submitMint() {
  const opt = ttlOptions.value.find((o) => o.value === mint.form.tier) || ttlOptions.value[1];
  minting.value = true;
  try {
    const payload: any = {
      kind: props.kind,
      target_id: props.targetId,
      allow_domains: mint.form.allow_domains || null,
      allow_ips: mint.form.allow_ips || null,
    };
    if (opt.value === "forever") {
      payload.permanent = true;
    } else {
      payload.ttl = opt.ttl;
    }
    const res = await issueAssetToken(payload);
    const d = res?.data?.data || {};
    reveal.token = d.token || "";
    reveal.expiresAt = d.expires_at || "";
    mint.visible = false;
    reveal.visible = true;
    void loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.asset_embed_mintFail"));
  } finally {
    minting.value = false;
  }
}

function applyRevealToken() {
  mintedToken.value = reveal.token;
  reveal.visible = false;
  ElMessage.success(t("ai_workflow.asset_embed_applySuccess"));
}

/* ---------- 编辑白名单 ---------- */
function openEditWhitelist(row: any) {
  edit.id = row.id;
  edit.form = {
    allow_domains: row.allow_domains || "",
    allow_ips: row.allow_ips || "",
  };
  edit.visible = true;
}

async function submitEditWhitelist() {
  edit.saving = true;
  try {
    await updateAssetToken(edit.id, {
      allow_domains: edit.form.allow_domains,
      allow_ips: edit.form.allow_ips,
    });
    ElMessage.success(t("ai_workflow.asset_embed_updateSuccess"));
    edit.visible = false;
    await loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.asset_embed_updateFail"));
  } finally {
    edit.saving = false;
  }
}

/* ---------- 查看日志 ---------- */
async function viewLogs(row: any) {
  logTokenId.value = row.id;
  logPage.value = 1;
  section.value = "logs";
  await loadTokenLogs();
}

/* ---------- 吊销 ---------- */
async function onRevoke(row: any) {
  try {
    await ElMessageBox.confirm(
      t("ai_workflow.asset_embed_revokeConfirm"),
      t("ai_workflow.asset_embed_revokeTitle"),
      {
        type: "warning",
        confirmButtonText: t("ai_workflow.asset_embed_revoke"),
        cancelButtonText: t("ai_workflow.develop_cancel"),
      }
    );
  } catch {
    return;
  }
  try {
    await revokeAssetToken(row.id);
    ElMessage.success(t("ai_workflow.asset_embed_revoked"));
    await loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.asset_embed_revokeFail"));
  }
}
</script>

<style scoped>
.asset-embed-dialog__tabs .el-tabs__content {
  overflow: visible;
}

.asset-embed-dialog {
  max-height: 60vh;
  padding-right: 6px;
  overflow-y: auto;
}

.asset-embed-dialog :deep(.el-form-item) {
  margin-bottom: 14px;
}

.asset-embed-dialog :deep(.el-form-item:last-child) {
  margin-bottom: 4px;
}

.asset-embed-dialog__toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}

.asset-embed-dialog__pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.asset-embed-dialog__code {
  width: 100%;
}

.asset-embed-dialog__pre {
  max-height: 200px;
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

  code {
    padding: 0;
    font-family: inherit;
    font-size: inherit;
    background: transparent;
    white-space: pre;
    color: inherit;
  }
}

.asset-embed-dialog__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 8px;
}

.asset-embed-dialog__sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.asset-embed-dialog__logtime {
  font-size: 12px;
  color: var(--el-text-color-regular);
}

.asset-embed-dialog__reveal {
  margin-top: 12px;
}

.asset-embed-dialog__token {
  display: flex;
  gap: 6px;
  align-items: center;
  font-family: var(--el-font-family-mono, monospace);
  color: var(--el-color-primary);
  word-break: break-all;
}
</style>
