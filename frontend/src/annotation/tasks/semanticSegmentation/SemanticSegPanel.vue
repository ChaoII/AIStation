<template>
  <div class="seg-panel">
    <el-select
      v-model="bgId"
      placeholder="选择背景类别"
      size="small"
      style="width: 160px"
      clearable
      @change="onBgChange"
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
import { ref, onUnmounted } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import type { PluginPanelContext, Annotation } from "../../core/types";
import { segBackgroundClassId, resetSegBackgroundClassId } from "./sharedState";

const props = defineProps<{ ctx: PluginPanelContext }>();
const bgId = ref<number | null>(null);

function onBgChange() {
  segBackgroundClassId.value = bgId.value;
}

function clsName(id: number): string {
  return props.ctx.classes?.find?.((c) => c.id === id)?.name ?? "";
}

/** 判断是否为同类别、取满四角、整图范围的背景标注 */
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
  segBackgroundClassId.value = bg;
  ElMessage.success("已填充背景");
}

// 进入时若已有背景选择则回填控件
if (segBackgroundClassId.value != null) bgId.value = segBackgroundClassId.value;

// 插件跨会话清理，避免模块级 ref 残留到无关任务
onUnmounted(() => {
  resetSegBackgroundClassId();
});
</script>
