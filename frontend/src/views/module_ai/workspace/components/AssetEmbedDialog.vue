<!--
  工作台「资产嵌入」弹窗：固定当前 agent/工作流，展示三种嵌入形式
  （聊天气泡 Script SDK / iframe / 运行 API），生成与治理独立绑定该资产的令牌。
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
          <pre class="asset-embed-dialog__pre">{{ codeFor(formTab) }}</pre>
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
              @click="onMint"
            >
              {{ t("ai_workflow.asset_embed_mint") }}
            </el-button>
          </div>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            class="asset-embed-dialog__alert"
            :title="t('ai_workflow.asset_embed_tokenHint')"
            :description="t('ai_workflow.asset_embed_tokenHintDesc')"
          />
        </div>
      </el-form-item>

      <el-form-item :label="t('ai_workflow.asset_embed_issued')">
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
          <el-table-column :label="t('ai_workflow.develop_embedIssuedTicket')" width="110">
            <template #default="{ row }">
              <span class="asset-embed-dialog__sub">{{ row.issued_by || "admin" }}</span>
            </template>
          </el-table-column>
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
          <el-table-column :label="t('ai_workflow.develop_embedAction')" width="72">
            <template #default="{ row }">
              <el-button
                v-if="!row.revoked"
                v-hasPerm="'module_ai:asset_embed:manage'"
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
    </el-form>

    <template #footer>
      <el-button @click="visible = false">{{ t("ai_workflow.develop_close") }}</el-button>
    </template>

    <!-- 令牌一次性展示 -->
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
      <el-descriptions :column="1" border size="small" class="asset-embed-dialog__reveal">
        <el-descriptions-item label="Token">
          <div class="asset-embed-dialog__token">
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
import { issueAssetToken, listAssetTokens, revokeAssetToken } from "@/api/module_ai/assetEmbed";

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

const formTab = ref<"bubble" | "iframe" | "run">("bubble");
const mintedToken = ref("");
const minting = ref(false);
const tokens = ref<any[]>([]);
const loadingTokens = ref(false);
const reveal = reactive({ visible: false, token: "", expiresAt: "" });

function fmtShort(v?: string): string {
  if (!v) return "—";
  return v.length >= 16 ? v.slice(5, 16) : v;
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

function resetState() {
  formTab.value = "bubble";
  mintedToken.value = "";
  tokens.value = [];
  reveal.visible = false;
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
// 读取 resp.body 流，按行解析 SSE（data: {type:"reply_delta", delta:"..."}）`;
  }
  return (
    `<script src="${apiBase}/embed/sdk.js"></scr` +
    `ipt>\n<div id="ai-assistant" style="width:420px;height:620px"></div>\n<script>\n  AiAssistant.init({\n    container: "#ai-assistant",\n    token: "${token}",\n    apiBase: "${apiBase}",\n    webBase: "${webBase}",\n  });\n</scr` +
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
  copyText(codeFor(formTab.value));
}

/* ---------- 生成令牌 ---------- */
async function onMint() {
  minting.value = true;
  try {
    const res = await issueAssetToken({ kind: props.kind, target_id: props.targetId });
    const d = res?.data?.data || {};
    reveal.token = d.token || "";
    reveal.expiresAt = d.expires_at || "";
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
    await revokeAssetToken(row.id);
    ElMessage.success(t("ai_workflow.develop_embedRevoked"));
    await loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || t("ai_workflow.develop_embedRevokeFail"));
  }
}
</script>

<style scoped>
.asset-embed-dialog {
  max-height: 70vh;
  padding-right: 6px;
  overflow-y: auto;
}

.asset-embed-dialog :deep(.el-form-item) {
  margin-bottom: 14px;
}

.asset-embed-dialog :deep(.el-form-item:last-child) {
  margin-bottom: 4px;
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
}

.asset-embed-dialog__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 8px;
}

.asset-embed-dialog__alert {
  margin-top: 10px;
}

.asset-embed-dialog__sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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
