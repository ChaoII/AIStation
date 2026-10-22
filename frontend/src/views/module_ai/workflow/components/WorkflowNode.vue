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
      'is-disabled': data.enabled === false,
      'is-note': def.type === 'note',
      'is-group': def.type === 'group',
    }"
  >
    <Handle
      v-if="def.type !== 'start' && def.type !== 'note' && def.type !== 'group'"
      type="target"
      :position="Position.Left"
      class="wf-handle"
      :connectable="true"
    />
    <div class="wf-node__head">
      <el-icon
        v-if="def.type !== 'note' && def.type !== 'group'"
        class="wf-node__icon"
        :color="def.color"
      >
        <component :is="def.icon" />
      </el-icon>
      <span v-if="def.type !== 'note' && def.type !== 'group'" class="wf-node__label">
        {{ def.label }}
      </span>
      <span v-if="def.type === 'condition'" class="wf-node__branch-tag">分支</span>
      <span v-if="data.enabled === false" class="wf-node__disable-tag">禁用</span>
      <span v-if="data.__runError" class="wf-node__err-badge" :title="data.__runError">!</span>
      <span v-if="data.__runOrder != null" class="wf-node__order">{{ data.__runOrder }}</span>
    </div>
    <div class="wf-node__body">
      <template v-if="def.type === 'group'">
        <div class="wf-group__title">{{ data.title || "分组" }}</div>
        <div class="wf-group__hint">双击收缩/展开；右键节点可「加入/移出分组」</div>
      </template>
      <div v-if="data.output_variable" class="wf-node__outvar">→ {{ data.output_variable }}</div>
      <template v-if="def.type === 'note'">
        <div v-if="data.title" class="wf-note__title">{{ data.title }}</div>
        <div v-if="data.content" class="wf-note__content">{{ data.content }}</div>
      </template>
      <div v-if="data.note && def.type !== 'note'" class="wf-node__note" :title="data.note">
        {{ data.note }}
      </div>
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
      <!-- 运行后：节点卡片直接展示输出 / 报错（Dify 式） -->
      <div v-if="data.__runError" class="wf-node__out is-err" :title="data.__runError">
        {{ data.__runError }}
      </div>
      <div
        v-else-if="data.__runStatus === 'success' && data.__runOutput != null"
        class="wf-node__out"
        :title="shortText(data.__runOutput, 1000)"
      >
        {{ shortText(data.__runOutput) }}
      </div>
      <div v-if="data.__runDuration != null" class="wf-node__dur">{{ data.__runDuration }}ms</div>
    </div>
    <!-- 输出句柄：条件节点出 true/false 两条 -->
    <Handle
      v-if="def.type !== 'end' && def.type !== 'note' && def.type !== 'group'"
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
    note: DocumentCopy,
    group: Collection,
    end: CircleCheckFilled,
  };
  return { ...d, icon: iconMap[d.type] || Cpu };
});

function shortText(v: any, limit = 160): string {
  if (v == null) return "";
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length <= limit ? s : s.slice(0, limit) + "…";
}
</script>

<style scoped lang="scss">
.wf-node {
  --node-color: var(--el-color-primary);
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

  &.is-note {
    width: 240px;
    min-height: 80px;
    background: var(--el-color-warning-light-9);
    border: 1px dashed var(--el-color-warning-light-5);
    box-shadow: none;

    .wf-node__head {
      min-height: 0;
    }

    .wf-note__title {
      font-weight: 600;
      color: var(--el-color-warning-dark-2);
    }
    .wf-note__content {
      margin-top: 4px;
      color: var(--el-text-color-regular);
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12px;
    }
  }

  &.is-group {
    width: 100%;
    height: 100%;
    padding: 20px 16px;
    background: var(--el-color-primary-light-9);
    border: 2px dashed var(--el-color-primary-light-5);
    box-shadow: none;

    .wf-node__head {
      min-height: 0;
      padding: 0;
    }

    .wf-group__title {
      font-weight: 600;
      color: var(--el-color-primary);
    }
    .wf-group__hint {
      margin-top: 4px;
      font-size: 12px;
      color: var(--el-text-color-secondary);
    }
  }

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

  &.is-disabled {
    opacity: 0.5;
    border-style: dashed;
  }

  .wf-node__disable-tag {
    margin-left: 8px;
    padding: 1px 6px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--el-text-color-secondary);
    background: var(--el-fill-color-light);
    border-radius: 4px;
  }

  .wf-node__order {
    position: absolute;
    top: -8px;
    left: -8px;
    width: 18px;
    height: 18px;
    line-height: 18px;
    text-align: center;
    font-size: 12px;
    color: #fff;
    background: var(--el-color-primary);
    border-radius: 50%;
  }

  .wf-node__err-badge {
    margin-left: auto;
    width: 16px;
    height: 16px;
    line-height: 16px;
    text-align: center;
    font-size: 12px;
    color: #fff;
    background: var(--el-color-danger);
    border-radius: 50%;
    cursor: help;
  }

  .wf-node__head {
    display: flex;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }

  .wf-node__icon {
    font-size: var(--el-font-size-medium);
  }

  .wf-node__label {
    flex: 1;
    font-size: var(--el-font-size-base);
    font-weight: 600;
  }

  .wf-node__branch-tag {
    padding: 1px 6px;
    font-size: 12px;
    color: #fff;
    background: var(--el-color-danger);
    border-radius: 4px;
  }

  .wf-node__body {
    font-size: var(--el-font-size-small);
  }

  .wf-node__note {
    margin-bottom: 6px;
    padding: 4px 6px;
    font-size: 12px;
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-radius: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }

  .wf-node__outvar {
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--el-color-success);
  }

  .wf-node__out {
    margin-top: 6px;
    padding: 4px 6px;
    font-size: 12px;
    color: var(--el-text-color-regular);
    background: var(--el-fill-color-light);
    border-radius: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;

    &.is-err {
      color: var(--el-color-danger);
      background: var(--el-color-danger-light-9);
    }
  }

  .wf-node__dur {
    margin-top: 4px;
    font-size: 10px;
    color: var(--el-text-color-placeholder);
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
  background: var(--el-color-success);
}

.wf-handle--false {
  top: 50%;
  right: 0;
  background: var(--el-color-danger);
}
</style>
