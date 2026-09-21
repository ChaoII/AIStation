<template>
  <div class="cuboid-panel">
    <el-form label-width="72px" size="small">
      <el-form-item label="深度">
        <el-input-number
          v-model="depthVal"
          :min="0"
          :max="1"
          :step="0.05"
          :controls="false"
          @change="applyDepth"
        />
      </el-form-item>
      <el-form-item label="朝向">
        <span style="color: var(--el-text-color-secondary)">{{ yawText }}</span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import type { PluginPanelContext, Annotation } from "../../core/types";

const props = defineProps<{ ctx: PluginPanelContext }>();
const depthVal = ref<number>(0.5);

function selectedCuboid(): Annotation | null {
  const sel = props.ctx.selectedClassId;
  const cands = (props.ctx.annotations ?? []).filter((a) => a.type === "Cuboid");
  if (cands.length === 0) return null;
  // 取最后选中的 cuboid（简化：当前选中类别下最后一个）
  const cls = cands.filter((a) => a.class_id === sel);
  return cls[cls.length - 1] ?? cands[cands.length - 1];
}

function applyDepth() {
  const cub = selectedCuboid();
  if (!cub) return;
  cub.depth = depthVal.value;
  (cub as any).__depthDirty = true;
}

const yawText = ref("");

watch(
  () => props.ctx.annotations,
  () => {
    const cub = selectedCuboid();
    if (cub) {
      depthVal.value = cub.depth ?? 0.5;
      yawText.value = `${(((cub.yaw ?? 0) * 180) / Math.PI).toFixed(1)}°`;
    }
  },
  { deep: true }
);

onMounted(() => {
  const cub = selectedCuboid();
  if (cub) {
    depthVal.value = cub.depth ?? 0.5;
    yawText.value = `${(((cub.yaw ?? 0) * 180) / Math.PI).toFixed(1)}°`;
  }
});
</script>
