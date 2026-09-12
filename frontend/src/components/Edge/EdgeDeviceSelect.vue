<template>
  <el-select
    :model-value="modelValue ?? LOCAL_ID"
    filterable
    clearable
    placeholder="本机 / 纯云端"
    style="width: 280px"
    @update:model-value="onChange"
  >
    <el-option :value="LOCAL_ID" label="本机 / 纯云端（不使用边缘设备）" />
    <el-option v-for="d in devices" :key="d.id" :value="d.id" :label="d.name">
      <span class="edge-opt">
        <span class="edge-opt-dot" :class="d.status" />
        {{ d.name }}
        <span class="edge-opt-code">({{ d.code }})</span>
        <span class="edge-opt-meta">
          {{ runningOf(d) }}/{{ d.capabilities?.max_channels ?? "-" }}
        </span>
      </span>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getEdgeDeviceList } from "@/api/module_video/edge";

defineProps<{ modelValue: number | null }>();
const emit = defineEmits<{ (e: "update:modelValue", val: number | null): void }>();

/** 本机/纯云端哨兵值（设备 id 为正整数，-1 不会冲突）。 */
const LOCAL_ID = -1;

const devices = ref<any[]>([]);

function runningOf(d: any): number | string {
  const m = d?.metrics || {};
  return m.running_channels ?? m.running ?? "-";
}

function onChange(val: number | null | undefined) {
  emit("update:modelValue", val === LOCAL_ID || val === null || val === undefined ? null : val);
}

onMounted(async () => {
  try {
    const res = await getEdgeDeviceList({ page_no: 1, page_size: 100 });
    devices.value = res.data?.data?.items || [];
  } catch {
    /* 加载失败保持空列表 */
  }
});
</script>

<style scoped>
.edge-opt {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.edge-opt-dot {
  width: 8px;
  height: 8px;
  background: var(--el-color-info);
  border-radius: 50%;
}

.edge-opt-dot.online {
  background: var(--el-color-success);
}

.edge-opt-dot.busy {
  background: var(--el-color-warning);
}

.edge-opt-dot.error {
  background: var(--el-color-danger);
}

.edge-opt-code {
  color: var(--el-text-color-placeholder);
}

.edge-opt-meta {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
