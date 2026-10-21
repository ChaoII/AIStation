<!--
  应用「嵌入」弹窗：选目标 → 生成 iframe / Script SDK 代码 → 签体验票 → 令牌治理。
  凭证约定：代码内只出现短期 access_token 占位符；appkey 永不进入网页。
-->
<template>
  <el-dialog
    v-model="visible"
    :title="`嵌入对话 · ${app?.name || ''}`"
    width="640px"
    top="6vh"
    append-to-body
    class="embed-dialog-host"
    @closed="resetState"
  >
    <div class="embed-dialog">
      <!-- 目标 -->
      <section class="embed-dialog__section">
        <div class="embed-dialog__label">嵌入目标</div>
        <div class="embed-dialog__target">
          <el-radio-group v-model="kind" size="small" @change="onKindChange">
            <el-radio-button value="agent">Agent</el-radio-button>
            <el-radio-button value="app">AI 应用</el-radio-button>
            <el-radio-button value="workflow">工作流</el-radio-button>
          </el-radio-group>
          <el-select
            v-model="targetId"
            filterable
            clearable
            :loading="loadingTargets"
            placeholder="选择要嵌入的目标"
            class="embed-dialog__select"
            @change="mintedToken = ''"
          >
            <el-option v-for="t in targets" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </div>
      </section>

      <!-- 嵌入代码 -->
      <section class="embed-dialog__section">
        <div class="embed-dialog__head">
          <span class="embed-dialog__label">嵌入代码</span>
          <el-button
            v-hasPerm="'module_ai:develop:create'"
            size="small"
            :loading="minting"
            :disabled="!targetId"
            @click="onMint"
          >
            生成体验 Token（2 小时）
          </el-button>
        </div>
        <el-tabs v-model="codeTab" class="embed-dialog__tabs">
          <el-tab-pane label="iframe 直嵌" name="iframe">
            <pre class="embed-dialog__code">{{ codeFor("iframe") }}</pre>
          </el-tab-pane>
          <el-tab-pane label="Script SDK" name="script">
            <pre class="embed-dialog__code">{{ codeFor("script") }}</pre>
          </el-tab-pane>
        </el-tabs>
        <div class="embed-dialog__hint">
          <el-icon><InfoFilled /></el-icon>
          <span>
            <code>{access_token}</code>
            为短期凭证占位符：请由宿主服务端用 appid/appkey 调
            <code>POST {{ apiBase }}/develop-api/auth/token</code>
            换票获取；
            <b>切勿把 appkey 写入网页</b>
            。过期后宿主重新换票并调用
            <code>setToken()</code>
            即可续期。
          </span>
        </div>
        <div class="embed-dialog__actions">
          <el-button size="small" :disabled="!targetId" @click="copyCode">
            <el-icon><CopyDocument /></el-icon>
            复制代码
          </el-button>
        </div>
      </section>

      <!-- 令牌列表 -->
      <section class="embed-dialog__section">
        <div class="embed-dialog__label">已签发令牌</div>
        <el-table
          v-loading="loadingTokens"
          :data="tokens"
          size="small"
          max-height="204"
          empty-text="暂无令牌（换票与体验票都会出现在这里）"
        >
          <el-table-column label="形态" width="88">
            <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
          </el-table-column>
          <el-table-column prop="target_name" label="目标" min-width="110" show-overflow-tooltip />
          <el-table-column label="签发" width="76">
            <template #default="{ row }">
              {{ row.issued_by === "admin" ? "体验票" : "换票" }}
            </template>
          </el-table-column>
          <el-table-column prop="expires_at" label="过期时间" width="158" />
          <el-table-column prop="use_count" label="使用" width="62" align="right" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="row.revoked ? 'info' : 'success'" effect="plain">
                {{ row.revoked ? "已吊销" : "有效" }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="!row.revoked"
                v-hasPerm="'module_ai:develop:update'"
                link
                type="danger"
                size="small"
                @click="onRevoke(row)"
              >
                吊销
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <!-- 事件契约 -->
      <section class="embed-dialog__section">
        <div class="embed-dialog__label">postMessage 事件（source = ai-embed，version = 1）</div>
        <div class="embed-dialog__events">
          <span v-for="e in EVENTS" :key="e.name" class="embed-dialog__event" :title="e.desc">
            <code>{{ e.name }}</code>
          </span>
        </div>
        <p class="embed-dialog__note">完整载荷与下行命令见「接入文档」页签。</p>
      </section>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 体验票一次性展示 -->
    <el-dialog v-model="reveal.visible" title="体验 Token" width="520px" append-to-body>
      <el-alert
        title="请复制后立即填入代码"
        type="warning"
        :closable="false"
        show-icon
        description="令牌明文仅在这里显示一次；过期后重新签发即可。"
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
        <el-descriptions-item label="过期时间">{{ reveal.expiresAt }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="reveal.visible = false">关闭</el-button>
        <el-button type="primary" @click="applyRevealToken">填入代码</el-button>
      </template>
    </el-dialog>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CopyDocument, InfoFilled } from "@element-plus/icons-vue";
import { getAiAgentList } from "@/api/module_ai/agent";
import { getAiAppList } from "@/api/module_ai/app";
import { getAiWorkflowList } from "@/api/module_ai/workflow";
import { getEmbedTokens, mintEmbedToken, revokeEmbedToken } from "@/api/module_ai/develop";

defineOptions({ name: "AiEmbedDialog" });

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
  { name: "ready", desc: "嵌入页初始化完成（含目标名与过期时间）" },
  { name: "user_message", desc: "用户发出消息" },
  { name: "reply_start", desc: "开始流式回复" },
  { name: "reply_delta", desc: "流式增量文本（高频）" },
  { name: "reply_done", desc: "回复完成（全量文本）" },
  { name: "error", desc: "业务/网络/限流错误" },
  { name: "token_expired", desc: "凭证过期，宿主需换票后 setToken" },
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
  return { agent: "Agent", app: "AI 应用", workflow: "工作流" }[k] || k;
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
    ElMessage.error("加载目标列表失败");
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
    return `<iframe\n  src="${webBase}/#/embed?token=${token}"\n  width="420" height="620"\n  style="border:0;border-radius:12px"\n  title="AI 对话"\n></iframe>`;
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
    () => ElMessage.success("已复制"),
    () => ElMessage.error("复制失败，请手动复制")
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
    ElMessage.error(e?.msg || "签发失败");
  } finally {
    minting.value = false;
  }
}

function applyRevealToken() {
  mintedToken.value = reveal.token;
  reveal.visible = false;
  ElMessage.success("已填入代码，可直接复制使用");
}

/* ---------- 吊销 ---------- */
async function onRevoke(row: any) {
  try {
    await ElMessageBox.confirm(
      `吊销后该令牌立即失效，使用它的嵌入页面将无法继续对话，且不可恢复。是否继续？`,
      "吊销令牌",
      { type: "warning", confirmButtonText: "吊销", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await revokeEmbedToken(row.id);
    ElMessage.success("已吊销");
    await loadTokens();
  } catch (e: any) {
    ElMessage.error(e?.msg || "吊销失败");
  }
}
</script>

<style scoped>
.embed-dialog {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-height: 64vh;
  padding-right: 6px;
  overflow-y: auto;
}

.embed-dialog__section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.embed-dialog__label {
  font-size: var(--el-font-size-base);
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.embed-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.embed-dialog__target {
  display: flex;
  gap: 10px;
  align-items: center;
}

.embed-dialog__select {
  flex: 1;
}

.embed-dialog__tabs :deep(.el-tabs__content) {
  margin-top: 4px;
}

.embed-dialog__code {
  max-height: 180px;
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

.embed-dialog__hint {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}

.embed-dialog__hint code {
  padding: 0 3px;
  font-family: var(--el-font-family-mono, monospace);
  color: var(--el-color-primary);
}

.embed-dialog__actions {
  display: flex;
  justify-content: flex-end;
}

.embed-dialog__events {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.embed-dialog__event {
  padding: 2px 8px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: help;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.embed-dialog__event code {
  font-family: var(--el-font-family-mono, monospace);
}

.embed-dialog__note {
  margin: 0;
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
