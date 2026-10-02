<!-- 工作流节点：统一渲染 start/llm/knowledge/tool/code/condition/variable/end -->
<template>
  <div
    class="wf-node"
    :style="{ '--node-color': def.color }"
    :class="{ selected, branch: def.branch }"
  >
    <Handle
      v-if="def.type !== 'start'"
      type="target"
      :position="Position.Left"
      class="wf-handle"
      :connectable="true"
    />
    <div class="wf-node__head">
      <el-icon class="wf-node__icon" :color="def.color"><component :is="def.icon" /></el-icon>
      <span class="wf-node__label">{{ def.label }}</span>
      <span v-if="def.type === 'condition'" class="wf-node__branch-tag">分支</span>
    </div>
    <div class="wf-node__body">
      <template v-if="def.type === 'start'">
        <div v-if="(data.variables || []).length === 0" class="wf-node__empty">定义输入变量</div>
        <div v-else class="wf-node__chips">
          <el-tag v-for="v in data.variables || []" :key="v.name" size="small" effect="plain">
            {{ v.name }}
          </el-tag>
        </div>
      </template>
      <template v-else-if="def.type === 'llm'">
        <div class="wf-node__text">{{ data.prompt ? "提示词已配置" : "未配置提示词" }}</div>
        <div v-if="(data.tools || []).length" class="wf-node__chips">
          <el-tag size="small" effect="plain" type="primary">
            {{ (data.tools || []).length }} 个工具
          </el-tag>
        </div>
      </template>
      <template v-else-if="def.type === 'knowledge'">
        <div class="wf-node__text">{{ data.query ? data.query : "检索知识库" }}</div>
      </template>
      <template v-else-if="def.type === 'tool'">
        <div class="wf-node__text">{{ data.tool_name || "选择工具" }}</div>
      </template>
      <template v-else-if="def.type === 'code'">
        <div class="wf-node__text">
          {{ data.output_variable ? `输出：${data.output_variable}` : "Python 转换" }}
        </div>
      </template>
      <template v-else-if="def.type === 'condition'">
        <div class="wf-node__text">{{ data.expression || "设置条件" }}</div>
      </template>
      <template v-else-if="def.type === 'variable'">
        <div class="wf-node__text">{{ data.name ? `${data.name} = 值` : "变量赋值" }}</div>
      </template>
      <template v-else-if="def.type === 'end'">
        <div class="wf-node__text">{{ data.output_template ? "模板已配置" : "输出最终回复" }}</div>
      </template>
    </div>
    <!-- 输出句柄：条件节点出 true/false 两条 -->
    <Handle
      v-if="def.type !== 'end'"
      type="source"
      :position="Position.Right"
      class="wf-handle"
      :connectable="true"
    />
    <template v-if="def.type === 'condition'">
      <Handle id="true" type="source" :position="Position.Left" class="wf-handle wf-handle--true" />
      <Handle
        id="false"
        type="source"
        :position="Position.Right"
        class="wf-handle wf-handle--false"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Handle, Position } from "@vue-flow/core";
import {
  Promotion,
  Cpu,
  DocumentCopy,
  Tools,
  Operation,
  SwitchFilled,
  DataLine,
  Connection,
  Refresh,
  CircleCheckFilled,
} from "@element-plus/icons-vue";
import { nodeDefOf, type WorkflowNodeType } from "../nodes";

const props = defineProps<{
  id: string;
  type: string;
  data: Record<string, any>;
  selected?: boolean;
}>();

const def = computed(() => {
  const d = nodeDefOf(props.type);
  const iconMap: Record<WorkflowNodeType, any> = {
    start: Promotion,
    llm: Cpu,
    knowledge: DocumentCopy,
    tool: Tools,
    code: Operation,
    condition: SwitchFilled,
    variable: DataLine,
    http: Connection,
    iteration: Refresh,
    end: CircleCheckFilled,
  };
  return { ...d, icon: iconMap[d.type] || Cpu };
});
</script>

<style scoped lang="scss">
.wf-node {
  --node-color: #409eff;
  position: relative;
  width: 200px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);

  &.selected {
    border-color: var(--node-color);
    box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
  }

  .wf-node__head {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }

  .wf-node__icon {
    font-size: 16px;
  }

  .wf-node__label {
    flex: 1;
    font-size: var(--el-font-size-base);
    font-weight: 600;
  }

  .wf-node__branch-tag {
    padding: 1px 6px;
    font-size: 11px;
    color: #fff;
    background: #f56c6c;
    border-radius: 4px;
  }

  .wf-node__body {
    font-size: var(--el-font-size-small);
  }

  .wf-node__text {
    color: var(--el-text-color-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .wf-node__empty {
    color: var(--el-text-color-placeholder);
  }

  .wf-node__chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
  }
}

.wf-handle {
  width: 10px;
  height: 10px;
  background: #909399;
  border: 2px solid #fff;
}

.wf-handle--true {
  top: 50%;
  left: 0;
  background: #67c23a;
}

.wf-handle--false {
  top: 50%;
  right: 0;
  background: #f56c6c;
}
</style>
