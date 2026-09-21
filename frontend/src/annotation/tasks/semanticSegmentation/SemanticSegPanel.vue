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
    <el-button size="small" type="primary" :disabled="bgId == null" @click="fillBackground">
      填充背景
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import type { PluginPanelContext, Annotation } from "../../core/types";
import { segBackgroundClassId } from "./sharedState";

const props = defineProps<{ ctx: PluginPanelContext }>();
const bgId = ref<number | null>(null);

function onBgChange() {
  segBackgroundClassId.value = bgId.value;
}

async function fillBackground() {
  if (bgId.value == null) return;
  await ElMessageBox.confirm(
    "将把整图填充为背景类别，未标注处将显示为背景色（可撤销）。是否继续？",
    "填充背景",
    { confirmButtonText: "填充", cancelButtonText: "取消", type: "warning" }
  );
  const ann: Annotation = {
    id: crypto.randomUUID(),
    type: "Polygon",
    class_id: bgId.value,
    points: [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ],
  };
  props.ctx.commit(ann);
  segBackgroundClassId.value = bgId.value;
  ElMessage.success("已填充背景");
}

// 进入时若已有背景选择则回填控件
if (segBackgroundClassId.value != null) bgId.value = segBackgroundClassId.value;
</script>
