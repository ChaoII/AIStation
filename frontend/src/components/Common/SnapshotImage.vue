<template>
  <el-image
    v-if="displaySrc"
    :src="displaySrc"
    :style="{ width: sizeW, height: sizeH }"
    fit="contain"
    :preview-src-list="previewable ? [displaySrc] : []"
    preview-teleported
  >
    <template #error>
      <div class="snapshot-empty" :style="{ width: sizeW, height: sizeH }">无截图</div>
    </template>
  </el-image>
  <div v-else class="snapshot-empty" :style="{ width: sizeW, height: sizeH }">无截图</div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from "vue";
import request from "@/utils/request";

const props = withDefaults(
  defineProps<{
    src?: string | null;
    width?: string | number;
    height?: string | number;
    previewable?: boolean;
  }>(),
  { src: null, width: "100%", height: "100%", previewable: false }
);

const objectUrl = ref<string | null>(null);
const blobSrc = ref<string | null>(null);

const sizeW = computed(() => (typeof props.width === "number" ? `${props.width}px` : props.width));
const sizeH = computed(() =>
  typeof props.height === "number" ? `${props.height}px` : props.height
);

const displaySrc = computed(() => blobSrc.value || props.src || null);

function revoke() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value);
    objectUrl.value = null;
  }
}

async function load() {
  revoke();
  blobSrc.value = null;
  const url = props.src;
  if (!url) return;
  if (/^(https?:|blob:|data:)/.test(url)) return; // 已可直接访问
  try {
    const res = await request({
      url,
      method: "get",
      responseType: "blob",
      headers: { _silent: "true" },
    });
    const blob = res.data as Blob;
    objectUrl.value = URL.createObjectURL(blob);
    blobSrc.value = objectUrl.value;
  } catch {
    /* 加载失败：展示占位 */
  }
}

watch(() => props.src, load, { immediate: true });
onBeforeUnmount(revoke);
</script>

<style scoped>
.snapshot-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
</style>
