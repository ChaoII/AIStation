<template>
  <el-row v-loading="previewLoading" element-loading-text="正在加载预览…">
    <el-col v-if="!previewLoading && isTreeEmpty" :span="24">
      <el-empty>
        <template #description>
          <p class="mb-1 font-medium">暂无预览文件</p>
          <p class="gencode-preview-empty-tip">
            若刚保存过仍为空，可将「预览范围」改为「全部」；或返回上一步检查字段与主子表后重新进入。
          </p>
        </template>
      </el-empty>
    </el-col>
    <template v-else>
      <el-col :span="24" class="mb-2">
        <div class="flex-y-center gap-3">
          <span class="text-sm color-#909399">预览范围</span>
          <el-radio-group v-model="previewScope" size="small">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="frontend">前端</el-radio-button>
            <el-radio-button value="backend">后端</el-radio-button>
          </el-radio-group>
          <span class="ml-3 text-sm color-#909399">类型</span>
          <el-checkbox-group v-model="previewTypes" size="small">
            <el-checkbox-button v-for="t in previewTypeOptions" :key="t" :value="t">
              {{ t }}
            </el-checkbox-button>
          </el-checkbox-group>
        </div>
      </el-col>
      <el-col :span="6">
        <el-scrollbar max-height="72vh">
          <el-tree
            :data="filteredTreeData"
            default-expand-all
            highlight-current
            @node-click="onTreeNodeClick"
          >
            <template #default="{ data }">
              <div :class="`i-svg:${getFileTreeNodeIcon(data.label)}`" />
              <span class="ml-1" :title="data.full_path || data.label">
                {{ data.label }}
              </span>
            </template>
          </el-tree>
        </el-scrollbar>
      </el-col>
      <el-col :span="18">
        <el-scrollbar max-height="72vh">
          <div class="absolute z-36 right-5 top-2">
            <el-link type="primary" @click="emit('copy-code')">
              <el-icon>
                <CopyDocument />
              </el-icon>
              复制代码
            </el-link>
          </div>
          <CodeEditor
            v-model="code"
            :language="codeLanguage"
            :theme="codeTheme"
            readonly
            height="100%"
            border
          />
        </el-scrollbar>
      </el-col>
    </template>
  </el-row>
</template>

<script setup lang="ts">
import { computed } from "vue";
import CodeEditor from "@/components/CodeEditor/index.vue";
import { CopyDocument } from "@element-plus/icons-vue";
import type { TreeNode } from "../types";

defineOptions({ name: "GenPreviewStep" });

const previewScope = defineModel<"all" | "frontend" | "backend">("previewScope", {
  required: true,
});
const previewTypes = defineModel<string[]>("previewTypes", { required: true });

const props = defineProps<{
  previewLoading: boolean;
  previewTypeOptions: string[];
  filteredTreeData: TreeNode[];
  codeLanguage: string;
  codeTheme: string;
}>();

const isTreeEmpty = computed(() => !props.filteredTreeData || props.filteredTreeData.length === 0);

const code = defineModel<string>("code", { required: true });

const emit = defineEmits<{
  "file-click": [data: TreeNode];
  "copy-code": [];
}>();

function onTreeNodeClick(data: TreeNode) {
  emit("file-click", data);
}

function getFileTreeNodeIcon(label: string): string {
  if (label.endsWith(".py")) return "python";
  if (label.endsWith(".vue")) return "vue";
  if (label.endsWith(".ts")) return "typescript";
  return "file";
}
</script>

<style scoped lang="scss">
.gencode-preview-meta-tip {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}

.gencode-preview-empty-tip {
  max-width: 420px;
  margin: 0 auto;
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
</style>
