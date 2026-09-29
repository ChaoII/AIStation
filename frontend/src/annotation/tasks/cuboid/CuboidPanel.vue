<template>
  <div class="cuboid-panel">
    <div class="hint">选中 3D 框后：拖四角改底面平行四边形、拖蓝点沿竖直方向调高度、拖底面内部移动整体。把鼠标放在控制点上可看用途。</div>
    <el-form label-width="72px" size="small">
      <el-form-item label="高度">
        <span style="color: var(--el-text-color-regular)">{{ heightText }}</span>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
import type { PluginPanelContext, Annotation } from "../../core/types";

const props = defineProps<{ ctx: PluginPanelContext }>();
const heightText = ref("0%");

function selectedCuboid(): Annotation | null {
  const cands = (props.ctx.annotations ?? []).filter((a) => a.type === "Cuboid");
  if (cands.length === 0) return null;
  const selId = props.ctx.selectedAnnotationId;
  if (selId) {
    const hit = cands.find((a) => a.id === selId);
    if (hit) return hit;
  }
  const sel = props.ctx.selectedClassId;
  const cls = cands.filter((a) => a.class_id === sel);
  return cls[cls.length - 1] ?? cands[cands.length - 1];
}

function refresh() {
  const cub = selectedCuboid();
  if (!cub) return;
  heightText.value = `${Math.round((cub.depth ?? 0) * 100)}%`;
}

watch(
  () => props.ctx.annotations,
  () => refresh(),
  { deep: true }
);

onMounted(() => refresh());
</script>

<style scoped>
.cuboid-panel .hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
</style>
