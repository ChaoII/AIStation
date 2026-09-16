<template>
  <div class="edge-cap-panel">
    <el-descriptions :column="2" border size="small" title="硬件">
      <el-descriptions-item label="平台">{{ hardware.platform || "-" }}</el-descriptions-item>
      <el-descriptions-item label="GPU 型号">{{ hardware.gpu_model || "-" }}</el-descriptions-item>
      <el-descriptions-item label="显存(MB)">{{ hardware.vram_mb ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="TPU">{{ hardware.tpu || "-" }}</el-descriptions-item>
    </el-descriptions>

    <el-descriptions :column="1" border size="small" title="能力" class="edge-cap-block">
      <el-descriptions-item label="推理后端">
        <el-tag v-for="b in backends" :key="b" size="small" class="edge-cap-tag">{{ b }}</el-tag>
        <span v-if="!backends.length" class="edge-cap-muted">-</span>
      </el-descriptions-item>
      <el-descriptions-item label="模型族">
        <el-tag
          v-for="m in modelFamilies"
          :key="m"
          size="small"
          type="success"
          class="edge-cap-tag"
        >
          {{ m }}
        </el-tag>
        <span v-if="!modelFamilies.length" class="edge-cap-muted">-</span>
      </el-descriptions-item>
      <el-descriptions-item label="最大并发路数">{{ maxChannels ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="解码">
        {{ codecList(codecs.decode) }} ｜ 编码: {{ codecList(codecs.encode) }}
      </el-descriptions-item>
    </el-descriptions>

    <el-descriptions :column="2" border size="small" title="实时指标" class="edge-cap-block">
      <el-descriptions-item label="CPU">{{ fmtPercent(metrics.cpu) }}</el-descriptions-item>
      <el-descriptions-item label="GPU">{{ fmtPercent(metrics.gpu) }}</el-descriptions-item>
      <el-descriptions-item label="显存(MB)">{{ metrics.vram_mb ?? "-" }}</el-descriptions-item>
      <el-descriptions-item label="在跑路数">
        {{ metrics.running_channels ?? metrics.running ?? "-" }}
      </el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  capabilities?: Record<string, any> | null;
  metrics?: Record<string, any> | null;
}>();

const hardware = computed(() => props.capabilities?.hardware || {});
const backends = computed<string[]>(() => props.capabilities?.backends || []);
const modelFamilies = computed<string[]>(() => props.capabilities?.model_families || []);
const maxChannels = computed<number | undefined>(() => props.capabilities?.max_channels);
const codecs = computed<Record<string, any>>(() => props.capabilities?.codecs || {});
const metrics = computed<Record<string, any>>(() => props.metrics || {});

function codecList(val: any): string {
  return Array.isArray(val) && val.length ? val.join("/") : "-";
}

function fmtPercent(val: any): string {
  if (val === undefined || val === null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return String(val);
  return n <= 1 ? `${Math.round(n * 100)}%` : `${round1(n)}%`;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}
</script>

<style scoped>
.edge-cap-panel {
  font-size: 12px;
}
.edge-cap-block {
  margin-top: 10px;
}
.edge-cap-tag {
  margin-right: 4px;
}
.edge-cap-muted {
  color: var(--el-text-color-placeholder);
}
</style>
