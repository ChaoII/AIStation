<template>
  <div class="seg-panel">
    <el-select
      v-model="bgId"
      placeholder="选择背景类别(stuff)"
      size="small"
      style="width: 160px"
      clearable
    >
      <el-option v-for="c in ctx.classes" :key="c.id" :label="c.name" :value="c.id" />
    </el-select>
    <el-button
      v-hasPerm="['module_annotation:task:workbench']"
      size="small"
      type="primary"
      :disabled="bgId == null"
      @click="fillBackground"
    >
      填充背景
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import type { PluginPanelContext, Annotation } from "../../core/types";
import { panopticClasses, resetPanopticClasses } from "./sharedState";

const props = defineProps<{ ctx: PluginPanelContext }>();
const bgId = ref<number | null>(null);

onMounted(() => {
  panopticClasses.value = props.ctx.classes || [];
});

function clsName(id: number): string {
  return props.ctx.classes?.find?.((c) => c.id === id)?.name ?? "";
}

function isFullImageBg(ann: Annotation): boolean {
  const pts = ann.points ?? [];
  if (pts.length < 4) return false;
  const has = (x: number, y: number) =>
    pts.some((p: { x: number; y: number }) => Math.abs(p.x - x) < 1e-4 && Math.abs(p.y - y) < 1e-4);
  return has(0, 0) && has(1, 0) && has(1, 1) && has(0, 1);
}

async function fillBackground() {
  const bg = bgId.value;
  if (bg == null) return;
  const existing = (props.ctx.annotations ?? []).filter(
    (a) => a.class_id === bg && isFullImageBg(a)
  );
  if (existing.length) {
    await ElMessageBox.confirm(
      `当前整图已有类别「${clsName(bg) || bg}」的背景标注，再次填充将删除旧背景并整体替换为新的背景。是否覆盖？`,
      "覆盖已有背景",
      { confirmButtonText: "覆盖", cancelButtonText: "取消", type: "warning" }
    );
    props.ctx.remove?.(existing.map((a) => a.id));
  } else {
    await ElMessageBox.confirm(
      "将把整图填充为背景类别，未标注处将显示为背景色（可撤销）。是否继续？",
      "填充背景",
      { confirmButtonText: "填充", cancelButtonText: "取消", type: "warning" }
    );
  }
  const ann: Annotation = {
    id: crypto.randomUUID(),
    type: "Polygon",
    class_id: bg,
    points: [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ],
  };
  props.ctx.commit(ann);
  ElMessage.success("已填充背景");
}

onUnmounted(() => {
  resetPanopticClasses();
});
</script>
