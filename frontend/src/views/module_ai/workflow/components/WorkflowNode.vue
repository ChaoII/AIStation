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
      <span v-if="def.type === 'condition'" class="wf-node__branch-tag">
        {{ t("ai_workflow.node_branch_tag") }}
      </span>
      <span v-if="data.enabled === false" class="wf-node__disable-tag">
        {{ t("ai_workflow.node_disabled_tag") }}
      </span>
      <span v-if="data.__runError" class="wf-node__err-badge" :title="data.__runError">!</span>
      <span v-if="data.__runOrder != null" class="wf-node__order">{{ data.__runOrder }}</span>
    </div>
    <div class="wf-node__body">
      <template v-if="def.type === 'group'">
        <div class="wf-group__title">{{ data.title || t("ai_workflow.node_group_default") }}</div>
        <div class="wf-group__hint">{{ t("ai_workflow.group_hint") }}</div>
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
        <div v-if="(data.variables || []).length === 0" class="wf-node__empty">
          {{ t("ai_workflow.node_start_empty") }}
        </div>
        <div v-else class="wf-node__chips">
          <el-tag v-for="v in data.variables || []" :key="v.name" size="small" effect="plain">
            {{ v.name }}
          </el-tag>
        </div>
      </template>
      <template v-else-if="def.type === 'llm'">
        <div class="wf-node__text">
          {{
            data.prompt ? t("ai_workflow.node_llm_prompt_set") : t("ai_workflow.node_llm_no_prompt")
          }}
        </div>
        <div v-if="(data.tools || []).length" class="wf-node__chips">
          <el-tag size="small" effect="plain" type="primary">
            {{ t("ai_workflow.node_tools_count", { count: (data.tools || []).length }) }}
          </el-tag>
        </div>
      </template>
      <template v-else-if="def.type === 'knowledge'">
        <div class="wf-node__text">
          {{ data.query ? data.query : t("ai_workflow.node_knowledge_default") }}
        </div>
      </template>
      <template v-else-if="def.type === 'tool'">
        <div class="wf-node__text">{{ data.tool_name || t("ai_workflow.node_tool_select") }}</div>
      </template>
      <template v-else-if="def.type === 'code'">
        <div class="wf-node__text">
          {{
            data.output_variable
              ? t("ai_workflow.node_code_output", { name: data.output_variable })
              : t("ai_workflow.node_code_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'condition'">
        <div class="wf-node__text">
          {{ data.expression || t("ai_workflow.node_condition_default") }}
        </div>
      </template>
      <template v-else-if="def.type === 'variable'">
        <div class="wf-node__text">
          {{
            data.name
              ? t("ai_workflow.node_var_eq", { name: data.name })
              : t("ai_workflow.node_var_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'http'">
        <div class="wf-node__text">
          {{ data.url ? `${data.method || "GET"} ${data.url}` : t("ai_workflow.node_http") }}
        </div>
      </template>
      <template v-else-if="def.type === 'iteration'">
        <div class="wf-node__text">
          {{
            data.tool_name
              ? t("ai_workflow.node_iter_call", { tool: data.tool_name })
              : t("ai_workflow.node_iter_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'classifier'">
        <div class="wf-node__text">
          {{
            (data.categories || []).length
              ? t("ai_workflow.node_classifier_count", { count: (data.categories || []).length })
              : t("ai_workflow.node_classifier_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'extractor'">
        <div class="wf-node__text">
          {{
            (data.schema || []).length
              ? t("ai_workflow.node_extractor_count", { count: (data.schema || []).length })
              : t("ai_workflow.node_extractor_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'template'">
        <div class="wf-node__text">
          {{
            data.template
              ? t("ai_workflow.node_template_set")
              : t("ai_workflow.node_template_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'variable_aggregator'">
        <div class="wf-node__text">
          {{
            (data.fields || []).length
              ? t("ai_workflow.node_agg_count", { count: (data.fields || []).length })
              : t("ai_workflow.node_agg_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'answer'">
        <div class="wf-node__text">
          {{
            data.output_template
              ? t("ai_workflow.node_answer_output")
              : t("ai_workflow.node_answer_default")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'sub_workflow'">
        <div class="wf-node__text">
          {{
            data.workflow_id
              ? t("ai_workflow.node_sub_wf_call", { id: data.workflow_id })
              : t("ai_workflow.node_sub_wf_select")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'agent'">
        <div class="wf-node__text">
          {{
            data.agent_id
              ? t("ai_workflow.node_agent_call", { id: data.agent_id })
              : t("ai_workflow.node_agent_select")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'loop'">
        <div class="wf-node__text">
          {{
            data.body_workflow_id
              ? t("ai_workflow.node_loop_call", { id: data.body_workflow_id })
              : t("ai_workflow.node_loop_select")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'parallel'">
        <div class="wf-node__text">
          {{
            (data.branches || []).length
              ? t("ai_workflow.node_parallel_count", { count: (data.branches || []).length })
              : t("ai_workflow.node_parallel_select")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'doc_extractor'">
        <div class="wf-node__text">
          {{
            data.url
              ? t("ai_workflow.node_doc_url")
              : data.source
                ? t("ai_workflow.node_doc_inline")
                : t("ai_workflow.node_doc_none")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'web_search'">
        <div class="wf-node__text">
          {{
            data.query
              ? t("ai_workflow.node_web_query", { query: data.query })
              : t("ai_workflow.node_web_none")
          }}
        </div>
      </template>
      <template v-else-if="def.type === 'database'">
        <div class="wf-node__text">
          {{ data.sql ? t("ai_workflow.node_sql_set") : t("ai_workflow.node_sql_none") }}
        </div>
      </template>
      <template v-else-if="def.type === 'end'">
        <div class="wf-node__text">
          {{
            data.output_template
              ? t("ai_workflow.node_template_set")
              : t("ai_workflow.node_end_default")
          }}
        </div>
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
import { useI18n } from "vue-i18n";
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

const { t } = useI18n();

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
  return {
    ...d,
    label: t(`ai_workflow.node_${d.labelKey}`),
    desc: t(`ai_workflow.node_${d.descKey}`),
    icon: iconMap[d.type] || Cpu,
  };
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
