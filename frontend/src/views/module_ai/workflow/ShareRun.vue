<!-- 公开分享运行页：无需登录，凭分享令牌调用受限匿名 share/run，含滑块人机校验 -->
<template>
  <div class="share-page">
    <div class="share-card">
      <div class="share-head">
        <span class="share-title">AI 工作流 · 分享运行</span>
        <span class="share-sub">无登录 · 仅白名单受限节点 · 限流保护</span>
      </div>
      <el-alert
        v-if="!token"
        type="warning"
        :closable="false"
        show-icon
        title="缺少分享令牌，链接无效"
      />
      <div v-else class="share-body">
        <div class="share-messages">
          <div v-if="!messages.length" class="share-empty">
            输入一条消息测试该工作流（运行结果会逐节点展示）。
          </div>
          <div v-for="(m, i) in messages" :key="i" class="share-msg" :class="`is-${m.role}`">
            <div class="share-bubble">
              <div v-if="m.role === 'user'" class="share-msg__user">{{ m.text }}</div>
              <template v-else>
                <div v-if="m.running" class="share-msg__load">运行中…</div>
                <div v-else-if="m.error" class="share-msg__err">{{ m.error }}</div>
                <div v-else class="share-msg__ai">{{ m.text || "(无回复)" }}</div>
                <div v-if="m.trace?.length" class="share-trace">
                  <div class="share-trace__title">节点执行过程</div>
                  <div v-for="(t, ti) in m.trace" :key="ti" class="share-trace__item">
                    <div
                      class="share-trace__head"
                      @click="detail[i + '_' + ti] = !detail[i + '_' + ti]"
                    >
                      <span class="share-trace__chev">{{ detail[i + "_" + ti] ? "▾" : "▸" }}</span>
                      <span class="share-trace__dot" :class="`is-${t.status}`" />
                      <span class="share-trace__label">{{ t.label }}</span>
                      <span class="share-trace__status">{{ statusText(t.status) }}</span>
                    </div>
                    <div v-if="detail[i + '_' + ti]" class="share-trace__detail">
                      <div v-if="t.input && Object.keys(t.input).length" class="kv">
                        <div class="kv-t">输入</div>
                        <pre class="kv-b">{{ formatJson(t.input) }}</pre>
                      </div>
                      <div v-if="t.output != null" class="kv">
                        <div class="kv-t">输出</div>
                        <pre class="kv-b">{{ formatJson(t.output) }}</pre>
                      </div>
                      <div v-if="t.error" class="kv">
                        <div class="kv-t">错误</div>
                        <pre class="kv-b is-err">{{ t.error }}</pre>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
        <div
          v-if="!sliderVerified"
          class="share-slider"
          @pointerdown="onStart"
          @pointermove="onMove"
          @pointerup="onEnd"
          @pointerleave="onEnd"
        >
          <div class="share-slider__track">
            <div class="share-slider__progress" :style="{ width: sliderProgress + '%' }" />
            <span v-if="!sliderVerified" class="share-slider__hint">请按住滑块拖到最右侧</span>
          </div>
          <div class="share-slider__handle" :style="{ left: sliderProgress + '%' }">
            <el-icon><Right /></el-icon>
          </div>
        </div>
        <div class="share-input">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="2"
            maxlength="500"
            show-word-limit
            placeholder="输入消息，回车或点发送……"
            @keydown.enter.exact.prevent="send"
          />
          <el-button type="primary" :loading="running" :disabled="!sliderVerified" @click="send">
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute } from "vue-router";
import { Right } from "@element-plus/icons-vue";

const route = useRoute();
const token = ref("");
const inputText = ref("");
const running = ref(false);
const messages = ref<
  Array<{
    role: "user" | "assistant";
    text: string;
    trace?: any[];
    running?: boolean;
    error?: string;
  }>
>([]);
const detail = ref<Record<string, boolean>>({});

// 滑块人机校验（拖到最右解锁）
const sliderProgress = ref(0);
const sliderVerified = ref(false);
const sliderDragging = ref(false);

function onStart(e: PointerEvent) {
  if (sliderVerified.value) return;
  sliderDragging.value = true;
  (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
}
function onMove(e: PointerEvent) {
  if (!sliderDragging.value || sliderVerified.value) return;
  const track = (e.currentTarget as HTMLElement).querySelector(
    ".share-slider__track"
  ) as HTMLElement;
  if (!track) return;
  const rect = track.getBoundingClientRect();
  const x = Math.max(0, Math.min(e.clientX - rect.left - 22, rect.width - 44));
  sliderProgress.value = Math.round((x / (rect.width - 44)) * 100);
  if (sliderProgress.value >= 100) {
    sliderVerified.value = true;
    sliderDragging.value = false;
  }
}
function onEnd() {
  sliderDragging.value = false;
  if (!sliderVerified.value) sliderProgress.value = 0;
}

function statusText(s: string) {
  return s === "success" ? "完成" : s === "error" ? "失败" : s === "skipped" ? "已跳过" : "执行中";
}
function formatJson(v: any): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

async function stream(resp: Response, onFrame: (o: any) => void) {
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("data:")) continue;
      const raw = t.slice(5).trim();
      if (raw === "[DONE]") continue;
      try {
        onFrame(JSON.parse(raw));
      } catch {
        /* ignore */
      }
    }
  }
}

async function send() {
  const text = inputText.value.trim();
  if (!text) return;
  if (!token.value) return;
  if (!sliderVerified.value) return;
  messages.value.push({ role: "user", text });
  inputText.value = "";
  const msg = { role: "assistant", text: "", trace: [], running: true } as any;
  messages.value.push(msg);
  running.value = true;
  try {
    const base = import.meta.env.VITE_APP_BASE_API || "/api/v1";
    const resp = await fetch(`${base}/ai/workflows/share/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token.value, message: text }),
    });
    if (!resp.ok || !resp.body) {
      msg.error = `请求失败：${resp.status}`;
      return;
    }
    await stream(resp, (obj) => {
      if (obj.type === "text-delta") msg.text += obj.text;
      else if (obj.type === "data-finish") msg.text = obj.reply || msg.text;
      else if (obj.type === "node-status") {
        msg.trace.push({
          label: obj.label || obj.nodeId,
          status: obj.status || "success",
          input: obj.input,
          output: obj.output,
          error: obj.error,
        });
      } else if (obj.type === "error") {
        msg.error = obj.errorText || obj.message || "运行失败";
      }
    });
    if (!msg.text) msg.text = "(无回复)";
  } catch (e: any) {
    msg.error = `运行失败：${e?.message || e}`;
  } finally {
    msg.running = false;
    running.value = false;
  }
}

onMounted(() => {
  token.value = (route.query.token as string) || "";
});
</script>

<style scoped lang="scss">
.share-page {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
}

.share-card {
  width: 520px;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.share-head {
  padding: 14px 20px;
  border-bottom: 1px solid var(--el-border-color-light);

  .share-title {
    display: block;
    font-size: var(--el-font-size-medium);
    font-weight: 600;
  }
  .share-sub {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}

.share-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.share-messages {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
}

.share-empty {
  padding: 30px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: var(--el-font-size-small);
}

.share-msg {
  display: flex;
  margin-bottom: 12px;

  &.is-user {
    justify-content: flex-end;
  }

  .share-bubble {
    max-width: 92%;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: var(--el-font-size-small);
    line-height: 1.6;
  }

  &.is-user .share-bubble {
    background: var(--el-color-primary-light-9);
    border: 1px solid var(--el-color-primary-light-7);
  }
  &.is-assistant .share-bubble {
    width: 100%;
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color-light);
  }

  .share-msg__user,
  .share-msg__ai {
    white-space: pre-wrap;
    word-break: break-word;
  }
  .share-msg__load {
    color: var(--el-text-color-secondary);
  }
  .share-msg__err {
    color: var(--el-color-danger);
  }

  .share-trace {
    margin-top: 10px;
    border-top: 1px dashed var(--el-border-color-lighter);
    padding-top: 6px;

    .share-trace__title {
      font-size: 12px;
      font-weight: 600;
      color: var(--el-text-color-secondary);
      margin-bottom: 4px;
    }

    .share-trace__item {
      margin-bottom: 4px;

      .share-trace__head {
        display: flex;
        gap: 8px;
        align-items: center;
        cursor: pointer;
        font-size: 12px;
      }
      .share-trace__chev {
        color: var(--el-text-color-secondary);
        font-size: 11px;
      }
      .share-trace__dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--el-color-info);
        &.is-success {
          background: var(--el-color-success);
        }
        &.is-error {
          background: var(--el-color-danger);
        }
        &.is-running {
          background: var(--el-color-primary);
        }
      }
      .share-trace__status {
        margin-left: auto;
        color: var(--el-text-color-secondary);
      }

      .share-trace__detail {
        margin: 4px 0 0 18px;

        .kv {
          margin-top: 4px;
          .kv-t {
            font-size: 12px;
            color: var(--el-text-color-secondary);
          }
          .kv-b {
            margin: 4px 0 0;
            max-height: 140px;
            overflow: auto;
            font-size: 12px;
            white-space: pre-wrap;
            word-break: break-word;
            &.is-err {
              color: var(--el-color-danger);
            }
          }
        }
      }
    }
  }
}

.share-slider {
  position: relative;
  height: 40px;
  margin: 0 20px 12px;
  cursor: grab;
  user-select: none;

  .share-slider__track {
    position: relative;
    height: 100%;
    background: var(--el-fill-color-light);
    border: 1px solid var(--el-border-color-lighter);
    border-radius: 20px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;

    .share-slider__progress {
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      background: var(--el-color-primary-light-7);
    }
    .share-slider__hint {
      position: relative;
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }

  .share-slider__handle {
    position: absolute;
    top: 0;
    width: 44px;
    height: 40px;
    background: #fff;
    border: 1px solid var(--el-border-color);
    border-radius: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.12);
    color: var(--el-color-primary);
  }
}

.share-input {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--el-border-color-light);
}
</style>
