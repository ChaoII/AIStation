<!-- 工作流节点：统一渲染 start/llm/knowledge/tool/code/condition/variable/end -->
<template>
  <div
    class="wf-node"
    :style="{ '--node-color': def.color }"
    :class="{
      selected,
      branch: def.branch,
      'is-running': data.__runStatus === 'running',
      'is-ok': data.__runStatus === 'success',
      'is-err': data.__runStatus === 'error',
    }"
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
      <template v-else-if="def.type === 'http'">
        <div class="wf-node__text">
          {{ data.url ? `${data.method || "GET"} ${data.url}` : "HTTP 请求" }}
        </div>
      </template>
      <template v-else-if="def.type === 'iteration'">
        <div class="wf-node__text">
          {{ data.tool_name ? `遍历调用 ${data.tool_name}` : "遍历列表" }}
        </div>
      </template>
      <template v-else-if="def.type === 'classifier'">
        <div class="wf-node__text">
          {{ (data.categories || []).length ? `${data.categories.length} 类路由` : "问题分类" }}
        </div>
      </template>
      <template v-else-if="def.type === 'extractor'">
        <div class="wf-node__text">
          {{ (data.schema || []).length ? `抽取 ${data.schema.length} 字段` : "抽取 JSON" }}
        </div>
      </template>
      <template v-else-if="def.type === 'template'">
        <div class="wf-node__text">{{ data.template ? "模板已配置" : "配置模板" }}</div>
      </template>
      <template v-else-if="def.type === 'variable_aggregator'">
        <div class="wf-node__text">
          {{ (data.fields || []).length ? `聚合 ${data.fields.length} 字段` : "变量聚合" }}
        </div>
      </template>
      <template v-else-if="def.type === 'answer'">
        <div class="wf-node__text">{{ data.output_template ? "文本输出" : "回答节点" }}</div>
      </template>
      <template v-else-if="def.type === 'sub_workflow'">
        <div class="wf-node__text">
          {{ data.workflow_id ? `调用工作流 #${data.workflow_id}` : "选择子工作流" }}
        </div>
      </template>
      <template v-else-if="def.type === 'agent'">
        <div class="wf-node__text">
          {{ data.agent_id ? `调用智能体 #${data.agent_id}` : "选择子智能体" }}
        </div>
      </template>
      <template v-else-if="def.type === 'loop'">
        <div class="wf-node__text">
          {{ data.body_workflow_id ? `循环工作流 #${data.body_workflow_id}` : "选择循环体工作流" }}
        </div>
      </template>
      <template v-else-if="def.type === 'parallel'">
        <div class="wf-node__text">
          {{ (data.branches || []).length ? `并行 ${data.branches.length} 分支` : "选择并行分支" }}
        </div>
      </template>
      <template v-else-if="def.type === 'doc_extractor'">
        <div class="wf-node__text">
          {{ data.url ? "抓取页面文本" : data.source ? "内联文本提取" : "未配置内容源" }}
        </div>
      </template>
      <template v-else-if="def.type === 'web_search'">
        <div class="wf-node__text">{{ data.query ? `搜索：${data.query}` : "未配置搜索词" }}</div>
      </template>
      <template v-else-if="def.type === 'database'">
        <div class="wf-node__text">{{ data.sql ? "SQL 已配置" : "未配置 SQL" }}</div>
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
  Filter,
  Tickets,
  MagicStick,
  Collection,
  ChatDotRound,
  Share,
  User,
  Sort,
  Grid,
  Document,
  Search,
  Coin,
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
    classifier: Filter,
    extractor: Tickets,
    template: MagicStick,
    variable_aggregator: Collection,
    answer: ChatDotRound,
    sub_workflow: Share,
    agent: User,
    loop: Sort,
    parallel: Grid,
    doc_extractor: Document,
    web_search: Search,
    database: Coin,
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
  padding: 10px 12px 10px 14px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(31, 45, 61, 0.08);
  transition:
    box-shadow 0.2s,
    border-color 0.2s;
  cursor: pointer;

  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 10px;
    bottom: 10px;
    width: 3px;
    border-radius: 3px;
    background: var(--node-color);
  }

  &:hover {
    box-shadow: 0 4px 14px rgba(31, 45, 61, 0.14);
  }

  &.selected {
    border-color: var(--node-color);
    box-shadow: 0 0 0 2px color-mix(in srgb, var(--node-color) 25%, transparent);
  }

  &.is-running {
    border-color: var(--el-color-primary);
    box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.25);
  }

  &.is-ok {
    border-color: var(--el-color-success);
    box-shadow: 0 0 0 2px rgba(103, 194, 58, 0.2);
  }

  &.is-err {
    border-color: var(--el-color-danger);
    box-shadow: 0 0 0 2px rgba(245, 108, 108, 0.2);
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
  width: 12px;
  height: 12px;
  background: #909399;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.06);

  &:hover {
    transform: scale(1.2);
  }
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
