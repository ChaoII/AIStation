<!-- 节点属性面板：按所选节点类型渲染对应配置表单 -->
<template>
  <el-form
    label-position="top"
    size="small"
    @focus.capture="onPanelFocus"
    @input.capture="onVarInput"
  >
    <!-- 启用 / 禁用 -->
    <el-form-item :label="t('ai_workflow.p_enable_node')">
      <el-switch
        v-model="nodeEnabled"
        inline-prompt
        :active-text="t('ai_workflow.p_active_text')"
        :inactive-text="t('ai_workflow.p_inactive_text')"
      />
      <span v-if="!nodeEnabled" class="node-disabled-tip">{{ t("ai_workflow.p_skip_tip") }}</span>
    </el-form-item>
    <!-- 节点备注 -->
    <el-form-item :label="t('ai_workflow.p_node_note')">
      <el-input v-model="d.note" :placeholder="t('ai_workflow.p_node_note_ph')" size="small" />
    </el-form-item>
    <!-- 失败重试次数 -->
    <el-form-item :label="t('ai_workflow.p_retry_count')">
      <el-input-number v-model="d.retry" :min="0" :max="5" size="small" />
      <span class="node-disabled-tip">{{ t("ai_workflow.p_retry_tip") }}</span>
    </el-form-item>
    <!-- 上游调用链 -->
    <el-form-item
      v-if="props.nodeChain && props.nodeChain.length > 1"
      :label="t('ai_workflow.p_upstream_chain')"
    >
      <div class="chain-text">{{ props.nodeChain.join(" → ") }}</div>
    </el-form-item>
    <!-- 插入变量 -->
    <el-form-item
      v-if="availableVars && availableVars.length"
      :label="t('ai_workflow.p_insert_var')"
    >
      <el-dropdown trigger="click" @command="insertVar">
        <el-button size="small" :icon="MagicStick">{{ t("ai_workflow.p_insert_var") }}</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item v-for="v in availableVars" :key="v.name" :command="v.name">
              <span class="var-item">{{ v.label }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <div class="var-tip">
        {{ t("ai_workflow.p_insert_var_tip") }}
        <code v-pre>{{ 变量 }}</code>
      </div>
    </el-form-item>

    <!-- 输入 / 输出 静态信息 -->
    <el-form-item :label="t('ai_workflow.p_input_vars')">
      <div class="io-var-list">
        <el-tag v-if="!refVars.length" size="small" type="info">
          {{ t("ai_workflow.p_no_ref") }}
        </el-tag>
        <el-tag
          v-for="v in refVars"
          :key="v"
          size="small"
          effect="plain"
          :type="unknownVars.includes(v) ? 'warning' : props.varSources?.[v] ? undefined : 'info'"
          :title="
            unknownVars.includes(v)
              ? t('ai_workflow.p_undefined_var')
              : props.varSources?.[v]
                ? t('ai_workflow.p_from_source', { src: props.varSources[v] })
                : t('ai_workflow.p_no_source')
          "
        >
          {{ v }}
          <span v-if="props.varSources?.[v]" class="io-var-src">← {{ props.varSources[v] }}</span>
        </el-tag>
      </div>
      <el-alert
        v-if="unknownVars.length"
        type="warning"
        :closable="false"
        show-icon
        class="io-var-warn"
      >
        {{ t("ai_workflow.p_undefined_warn", { vars: unknownVars.join(", ") }) }}
      </el-alert>
    </el-form-item>
    <el-form-item :label="t('ai_workflow.p_output_var')">
      <el-tag v-if="d.output_variable" size="small" type="success">{{ d.output_variable }}</el-tag>
      <el-tag v-else size="small" type="info">{{ t("ai_workflow.p_not_set") }}</el-tag>
      <el-button
        v-if="d.output_variable"
        icon="CopyDocument"
        link
        size="small"
        type="primary"
        @click="copyVarRef(d.output_variable)"
      >
        {{ t("ai_workflow.p_copy_ref") }}
      </el-button>
    </el-form-item>

    <!-- start：输入变量 -->
    <template v-if="type === 'start'">
      <el-form-item :label="t('ai_workflow.p_input_vars')">
        <el-button size="small" :icon="Plus" @click="addVar">
          {{ t("ai_workflow.p_add_var") }}
        </el-button>
      </el-form-item>
      <div v-for="(v, i) in vars" :key="i" class="start-var">
        <div class="start-var__row">
          <el-input
            v-model="v.name"
            :placeholder="t('ai_workflow.p_var_name')"
            size="small"
            class="start-var__name"
          />
          <el-select v-model="v.type" size="small" class="start-var__type">
            <el-option :label="t('ai_workflow.p_type_text')" value="string" />
            <el-option :label="t('ai_workflow.p_type_number')" value="number" />
            <el-option :label="t('ai_workflow.p_type_boolean')" value="boolean" />
            <el-option :label="t('ai_workflow.p_type_object')" value="object" />
            <el-option :label="t('ai_workflow.p_type_array')" value="array" />
          </el-select>
          <el-checkbox v-model="v.required" size="small">
            {{ t("ai_workflow.p_required") }}
          </el-checkbox>
          <el-button link type="danger" :icon="Delete" @click="vars.splice(i, 1)" />
        </div>
        <div class="start-var__row">
          <el-input
            v-model="v.default"
            :placeholder="t('ai_workflow.p_default_ph')"
            size="small"
            class="start-var__default"
          />
          <el-input
            v-model="v.desc"
            :placeholder="t('ai_workflow.p_desc_ph')"
            size="small"
            class="start-var__desc"
          />
        </div>
      </div>
    </template>

    <!-- llm：模型 + 提示词 + 温度 + 工具 -->
    <template v-else-if="type === 'llm'">
      <el-form-item :label="t('ai_workflow.p_model')">
        <el-select
          v-model="d.model_id"
          filterable
          :placeholder="t('ai_workflow.p_select_model')"
          style="width: 100%"
        >
          <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_prompt_with_var')">
        <el-input
          v-model="d.prompt"
          type="textarea"
          :rows="4"
          :placeholder="t('ai_workflow.p_prompt_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_temperature')">
        <el-slider v-model="d.temperature" :min="0" :max="2" :step="0.1" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_bind_tools')">
        <el-select
          v-model="d.tools"
          multiple
          filterable
          :placeholder="t('ai_workflow.p_select_tool')"
          style="width: 100%"
        >
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_hitl')">
        <el-switch v-model="d.require_approval" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_opt')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_for_downstream')" />
      </el-form-item>
    </template>

    <!-- knowledge：知识检索（阶段 3 落地） -->
    <template v-else-if="type === 'knowledge'">
      <el-form-item :label="t('ai_workflow.p_bind_kb')">
        <el-select
          v-model="d.knowledge_ids"
          multiple
          filterable
          :placeholder="t('ai_workflow.p_select_kb')"
          style="width: 100%"
        >
          <el-option v-for="kb in kbOptions" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_kb_query_tpl')">
        <el-input v-model="d.query" :placeholder="t('ai_workflow.p_kb_query_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_top_k')">
        <el-input-number v-model="d.top_k" :min="1" :max="10" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_opt')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_output_var_kb_ph')" />
      </el-form-item>
    </template>

    <!-- tool：工具调用 -->
    <template v-else-if="type === 'tool'">
      <el-form-item :label="t('ai_workflow.p_tool_name')">
        <el-select
          v-model="d.tool_name"
          filterable
          :placeholder="t('ai_workflow.p_select_tool')"
          style="width: 100%"
        >
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_args_json')">
        <el-input v-model="argsText" type="textarea" :rows="3" placeholder='{"path":"/x"}' />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" />
      </el-form-item>
    </template>

    <!-- code：代码转换 -->
    <template v-else-if="type === 'code'">
      <el-form-item :label="t('ai_workflow.p_python_code')">
        <CodeEditor v-model="d.code" language="python" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_input_map_json')">
        <CodeEditor v-model="codeInputsText" language="json" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" />
      </el-form-item>
      <el-alert :title="t('ai_workflow.p_code_ns_alert')" type="info" :closable="false" show-icon />
    </template>

    <!-- condition：条件分支 -->
    <template v-else-if="type === 'condition'">
      <el-form-item :label="t('ai_workflow.p_cond_build')">
        <div class="cond-logic">
          <el-radio-group v-model="condLogic" size="small">
            <el-radio-button label="and">{{ t("ai_workflow.p_cond_and") }}</el-radio-button>
            <el-radio-button label="or">{{ t("ai_workflow.p_cond_or") }}</el-radio-button>
          </el-radio-group>
        </div>
        <div v-for="(c, i) in conditions" :key="i" class="cond-row">
          <el-select
            v-model="c.var"
            :placeholder="t('ai_workflow.p_cond_var')"
            filterable
            class="cond-var"
          >
            <el-option v-for="v in availableVars" :key="v.name" :label="v.name" :value="v.name" />
          </el-select>
          <el-select v-model="c.op" class="cond-op" :placeholder="t('ai_workflow.p_cond_op')">
            <el-option v-for="o in COND_OPS" :key="o.v" :label="o.label" :value="o.v" />
          </el-select>
          <el-input v-model="c.val" class="cond-val" :placeholder="t('ai_workflow.p_cond_val')" />
          <el-button link type="danger" :icon="Delete" @click="conditions.splice(i, 1)" />
        </div>
        <div class="cond-actions">
          <el-button size="small" :icon="Plus" @click="addCond">
            {{ t("ai_workflow.p_add_cond") }}
          </el-button>
          <el-button size="small" type="primary" @click="applyCond">
            {{ t("ai_workflow.p_gen_expr") }}
          </el-button>
        </div>
        <div class="cond-hint">
          {{ t("ai_workflow.p_cond_hint_1") }}
          <code v-pre>{{ 变量 }}</code>
          {{ t("ai_workflow.p_cond_hint_2") }}
        </div>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_cond_expr')">
        <el-input v-model="d.expression" :placeholder="t('ai_workflow.p_cond_expr_ph')" />
      </el-form-item>
      <el-alert
        :title="t('ai_workflow.p_cond_handle_alert')"
        type="info"
        :closable="false"
        show-icon
      />
    </template>

    <!-- variable：变量赋值 -->
    <template v-else-if="type === 'variable'">
      <el-form-item :label="t('ai_workflow.p_var_name')">
        <el-input v-model="d.name" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_var_value')">
        <el-input v-model="d.value" :placeholder="t('ai_workflow.p_var_value_ph')" />
      </el-form-item>
    </template>

    <!-- http：外部请求 -->
    <template v-else-if="type === 'http'">
      <el-form-item :label="t('ai_workflow.p_method')">
        <el-select v-model="d.method" style="width: 120px">
          <el-option
            v-for="m in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']"
            :key="m"
            :label="m"
            :value="m"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_url_with_var')">
        <el-input v-model="d.url" :placeholder="t('ai_workflow.p_url_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_headers_kv')">
        <div v-for="(h, i) in headerRows" :key="i" class="http-kv">
          <el-input
            v-model="h.key"
            :placeholder="t('ai_workflow.p_header_name')"
            size="small"
            class="http-kv__k"
          />
          <el-input
            v-model="h.value"
            :placeholder="t('ai_workflow.p_header_val')"
            size="small"
            class="http-kv__v"
          />
          <el-button link type="danger" :icon="Delete" @click="headerRows.splice(i, 1)" />
        </div>
        <el-button size="small" :icon="Plus" @click="headerRows.push({ key: '', value: '' })">
          {{ t("ai_workflow.p_add_header") }}
        </el-button>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_body_json')">
        <CodeEditor v-model="bodyText" language="json" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" />
      </el-form-item>
      <el-alert
        :title="t('ai_workflow.p_http_resp_alert')"
        type="info"
        :closable="false"
        show-icon
      />
    </template>

    <!-- iteration：迭代/批量 -->
    <template v-else-if="type === 'iteration'">
      <el-form-item :label="t('ai_workflow.p_iterate_list')">
        <el-input
          v-model="itemsText"
          type="textarea"
          :rows="2"
          :placeholder="t('ai_workflow.p_iterate_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_tool')">
        <el-select
          v-model="d.tool_name"
          filterable
          :placeholder="t('ai_workflow.p_select_tool')"
          style="width: 100%"
        >
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_tool_args_item')">
        <el-input
          v-model="iterArgsText"
          type="textarea"
          :rows="2"
          placeholder='{"id":"{{item}}"}'
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_max_iterations')">
        <el-input-number v-model="d.max_iterations" :min="1" :max="100" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_result_array')" />
      </el-form-item>
    </template>

    <!-- classifier：问题分类器 -->
    <template v-else-if="type === 'classifier'">
      <el-form-item :label="t('ai_workflow.p_categories_label')">
        <el-input
          v-model="categoriesText"
          type="textarea"
          :rows="2"
          :placeholder="t('ai_workflow.p_categories_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_input_with_var')">
        <el-input v-model="d.query" :placeholder="t('ai_workflow.p_input_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_hit_category')" />
      </el-form-item>
    </template>

    <!-- extractor：参数提取 -->
    <template v-else-if="type === 'extractor'">
      <el-form-item :label="t('ai_workflow.p_extract_fields')">
        <el-input
          v-model="schemaText"
          type="textarea"
          :rows="2"
          :placeholder="t('ai_workflow.p_extract_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_input_with_var')">
        <el-input
          v-model="d.query"
          type="textarea"
          :rows="2"
          :placeholder="t('ai_workflow.p_input_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_json_object')" />
      </el-form-item>
    </template>

    <!-- template：模板转换 -->
    <template v-else-if="type === 'template'">
      <el-form-item :label="t('ai_workflow.p_template_with_var')">
        <el-input
          v-model="d.template"
          type="textarea"
          :rows="3"
          :placeholder="t('ai_workflow.p_template_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_convert_result')" />
      </el-form-item>
    </template>

    <!-- variable_aggregator：变量聚合 -->
    <template v-else-if="type === 'variable_aggregator'">
      <el-form-item :label="t('ai_workflow.p_agg_fields')">
        <el-space v-for="(f, i) in aggFields" :key="i" fill>
          <el-input
            v-model="f.name"
            :placeholder="t('ai_workflow.p_field_name')"
            style="width: 120px"
          />
          <el-input
            v-model="f.value"
            :placeholder="t('ai_workflow.p_field_val_ph')"
            style="flex: 1"
          />
          <el-button link type="danger" :icon="Delete" @click="aggFields.splice(i, 1)" />
        </el-space>
        <el-button
          size="small"
          :icon="Plus"
          style="margin-top: 4px"
          @click="aggFields.push({ name: '', value: '' })"
        >
          {{ t("ai_workflow.p_add_field") }}
        </el-button>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_agg_result_obj')" />
      </el-form-item>
    </template>

    <!-- answer：回答 -->
    <template v-else-if="type === 'answer'">
      <el-form-item :label="t('ai_workflow.p_answer_output_with_var')">
        <el-input
          v-model="d.output_template"
          type="textarea"
          :rows="3"
          :placeholder="t('ai_workflow.p_answer_ph')"
        />
      </el-form-item>
    </template>

    <!-- sub_workflow：子工作流 -->
    <template v-else-if="type === 'sub_workflow'">
      <el-form-item :label="t('ai_workflow.p_select_sub_wf')">
        <el-select
          v-model="d.workflow_id"
          filterable
          :placeholder="t('ai_workflow.p_select_workflow')"
          style="width: 100%"
        >
          <el-option v-for="w in workflowOptions" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_sub_wf_reply')" />
      </el-form-item>
    </template>

    <!-- agent：子智能体 -->
    <template v-else-if="type === 'agent'">
      <el-form-item :label="t('ai_workflow.p_select_sub_agent')">
        <el-select
          v-model="d.agent_id"
          filterable
          :placeholder="t('ai_workflow.p_select_agent')"
          style="width: 100%"
        >
          <el-option v-for="a in agentOptions" :key="a.id" :label="a.agent_name" :value="a.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_input_with_var')">
        <el-input
          v-model="d.query"
          type="textarea"
          :rows="2"
          :placeholder="t('ai_workflow.p_input_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_agent_reply')" />
      </el-form-item>
    </template>

    <!-- loop：循环 -->
    <template v-else-if="type === 'loop'">
      <el-form-item :label="t('ai_workflow.p_loop_body_wf')">
        <el-select
          v-model="d.body_workflow_id"
          filterable
          :placeholder="t('ai_workflow.p_select_loop_body')"
          style="width: 100%"
        >
          <el-option v-for="w in workflowOptions" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_loop_items')">
        <el-input
          v-model="d.items"
          type="textarea"
          :rows="3"
          :placeholder="t('ai_workflow.p_loop_items_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_max_loop')">
        <el-input-number v-model="d.max_iterations" :min="1" :max="100" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_agg_list_result')" />
      </el-form-item>
      <el-alert type="info" :closable="false" show-icon>
        {{ t("ai_workflow.p_loop_alert_1") }}
        <code v-pre>{{ item }}</code>
        {{ t("ai_workflow.p_loop_alert_2") }}
      </el-alert>
    </template>

    <!-- parallel：并行 -->
    <template v-else-if="type === 'parallel'">
      <el-form-item :label="t('ai_workflow.p_parallel_branches')">
        <div v-for="(b, i) in d.branches" :key="i" class="parallel-branch">
          <el-input
            v-model="b.name"
            size="small"
            :placeholder="t('ai_workflow.p_branch_name')"
            style="width: 100px"
          />
          <el-select
            v-model="b.workflow_id"
            size="small"
            filterable
            :placeholder="t('ai_workflow.p_select_workflow')"
            style="flex: 1"
          >
            <el-option v-for="w in workflowOptions" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
          <el-button size="small" :icon="Delete" circle @click="d.branches.splice(i, 1)" />
        </div>
        <el-button
          size="small"
          :icon="Plus"
          style="margin-top: 4px"
          @click="d.branches.push({ name: '', workflow_id: null })"
        >
          {{ t("ai_workflow.p_add_branch") }}
        </el-button>
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input
          v-model="d.output_variable"
          :placeholder="t('ai_workflow.p_parallel_output_ph')"
        />
      </el-form-item>
      <el-alert type="info" :closable="false" show-icon>
        {{ t("ai_workflow.p_parallel_alert_1") }}
        <code>{分支名: 结果}</code>
        {{ t("ai_workflow.p_parallel_alert_2") }}
      </el-alert>
    </template>

    <!-- doc_extractor：文档提取 -->
    <template v-else-if="type === 'doc_extractor'">
      <el-form-item :label="t('ai_workflow.p_url_with_var')">
        <el-input v-model="d.url" :placeholder="t('ai_workflow.p_doc_url_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_inline_text')">
        <el-input
          v-model="d.source"
          type="textarea"
          :rows="3"
          :placeholder="t('ai_workflow.p_inline_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_pure_text')" />
      </el-form-item>
    </template>

    <!-- web_search：网页搜索 -->
    <template v-else-if="type === 'web_search'">
      <el-form-item :label="t('ai_workflow.p_search_query')">
        <el-input v-model="d.query" :placeholder="t('ai_workflow.p_search_query_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_endpoint')">
        <el-input v-model="d.endpoint" placeholder="https://api.example.com/search?q={{query}}" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_api_key')">
        <el-input
          v-model="d.api_key"
          type="password"
          show-password
          :placeholder="t('ai_workflow.p_api_key_ph')"
        />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input
          v-model="d.output_variable"
          :placeholder="t('ai_workflow.p_search_result_format')"
        />
      </el-form-item>
    </template>

    <!-- database：数据库查询 -->
    <template v-else-if="type === 'database'">
      <el-form-item :label="t('ai_workflow.p_conn_dsn')">
        <el-input v-model="d.dsn" :placeholder="t('ai_workflow.p_dsn_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_sql_with_var')">
        <CodeEditor v-model="d.sql" language="sql" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_output_var_name')">
        <el-input v-model="d.output_variable" :placeholder="t('ai_workflow.p_row_array')" />
      </el-form-item>
    </template>

    <!-- end：结束输出 -->
    <template v-else-if="type === 'end'">
      <el-form-item :label="t('ai_workflow.p_output_template')">
        <el-input
          v-model="d.output_template"
          type="textarea"
          :rows="3"
          :placeholder="t('ai_workflow.p_output_template_ph')"
        />
      </el-form-item>
    </template>

    <!-- note：注释框 -->
    <template v-else-if="type === 'note'">
      <el-form-item :label="t('ai_workflow.p_note_title')">
        <el-input v-model="d.title" :placeholder="t('ai_workflow.p_note_title_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_note_content')">
        <el-input
          v-model="d.content"
          type="textarea"
          :rows="3"
          :placeholder="t('ai_workflow.p_note_content_ph')"
        />
      </el-form-item>
    </template>

    <!-- group：分组容器 -->
    <template v-else-if="type === 'group'">
      <el-form-item :label="t('ai_workflow.p_group_title')">
        <el-input v-model="d.title" :placeholder="t('ai_workflow.p_group_title_ph')" />
      </el-form-item>
      <el-form-item :label="t('ai_workflow.p_group_size')">
        <el-space>
          <el-input-number
            v-model="d.width"
            :min="200"
            :max="2000"
            :step="20"
            size="small"
            controls-position="right"
          />
          <el-input-number
            v-model="d.height"
            :min="120"
            :max="2000"
            :step="20"
            size="small"
            controls-position="right"
          />
        </el-space>
      </el-form-item>
      <el-alert type="info" :closable="false" show-icon>
        {{ t("ai_workflow.p_group_alert") }}
      </el-alert>
    </template>

    <!-- {{ 变量内联提示 -->
    <div
      v-if="suggestVisible && varSuggest.length"
      class="var-suggest"
      :style="{ left: suggestPos.x + 'px', top: suggestPos.y + 'px' }"
      @blur="onVarBlur"
      @mousedown.prevent
    >
      <div
        v-for="v in varSuggest"
        :key="v.name"
        class="var-suggest__item"
        @mousedown.prevent
        @click="pickVar(v.name)"
      >
        <code>{{ varToken(v.name) }}</code>
        <span class="var-suggest__label">{{ v.label }}</span>
      </div>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { Plus, Delete, MagicStick } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import type { Node } from "@vue-flow/core";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";
import { getAiWorkflowList } from "@/api/module_ai/workflow";
import { getAiAgentList } from "@/api/module_ai/agent";
import CodeEditor from "./CodeEditor.vue";

const props = defineProps<{
  node: Node;
  availableVars?: { name: string; label: string }[];
  varSources?: Record<string, string>;
  nodeChain?: string[];
}>();
const emit = defineEmits(["change"]);
const { t } = useI18n();

// ---------- 插入变量 ----------
const focusedEl = ref<HTMLTextAreaElement | HTMLInputElement | null>(null);
function onPanelFocus(e: FocusEvent) {
  const t = e.target as HTMLElement;
  if (t instanceof HTMLTextAreaElement || t instanceof HTMLInputElement) {
    focusedEl.value = t;
  }
}
function insertVar(name: string) {
  const el = focusedEl.value;
  const token = `{{${name}}}`;
  if (!el) {
    ElMessage.info(t("ai_workflow.p_select_input_first"));
    return;
  }
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? el.value.length;
  el.value = el.value.slice(0, start) + token + el.value.slice(end);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  const pos = start + token.length;
  el.setSelectionRange(pos, pos);
  el.focus();
  focusedEl.value = el;
}

// ---------- {{ 变量内联提示 ----------
const varSuggest = ref<{ name: string; label: string }[]>([]);
const suggestVisible = ref(false);
const suggestPos = ref({ x: 0, y: 0 });

function _inputFor(e: Event): HTMLTextAreaElement | HTMLInputElement | null {
  const t = e.target as HTMLElement;
  return t instanceof HTMLTextAreaElement || t instanceof HTMLInputElement ? t : null;
}

function onVarInput(e: Event) {
  const el = _inputFor(e);
  if (!el) return;
  focusedEl.value = el;
  const caret = el.selectionStart ?? el.value.length;
  const before = el.value.slice(0, caret);
  const m = /{{\s*([\w\u4e00-\u9fa5]*)$/.exec(before);
  if (!m) {
    suggestVisible.value = false;
    return;
  }
  const q = m[1] || "";
  const opts = (props.availableVars || []).filter((v) => !q || v.name.includes(q));
  if (!opts.length) {
    suggestVisible.value = false;
    return;
  }
  varSuggest.value = opts;
  const rect = el.getBoundingClientRect();
  suggestPos.value = { x: rect.left, y: rect.bottom + 4 };
  suggestVisible.value = true;
}

function pickVar(name: string) {
  const el = focusedEl.value;
  if (!el) return;
  const caret = el.selectionStart ?? el.value.length;
  const before = el.value.slice(0, caret);
  const m = /{{\s*([\w\u4e00-\u9fa5]*)$/.exec(before);
  const start = m ? caret - m[0].length : caret;
  el.value = el.value.slice(0, start) + `{{${name}}}` + el.value.slice(caret);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.setSelectionRange(start + name.length + 2, start + name.length + 2);
  el.focus();
  suggestVisible.value = false;
}

function onVarBlur() {
  // 延后隐藏，避免点击选项前被关闭
  window.setTimeout(() => {
    suggestVisible.value = false;
  }, 150);
}

function varToken(name: string) {
  return `{{${name}}}`;
}

function copyVarRef(name: string) {
  navigator.clipboard.writeText(`{{${name}}}`).then(
    () => ElMessage.success(t("ai_workflow.p_copied_ref")),
    () => ElMessage.error(t("ai_workflow.p_copy_fail"))
  );
}

const type = computed(() => props.node.type || "llm");
const d = reactive<Record<string, any>>({ ...((props.node.data || {}) as any) });
// start 变量用本地数组代理（避免直接改 reactive 复杂结构）
const vars = ref<
  Array<{ name: string; type: string; default?: any; required?: boolean; desc?: string }>
>([]);
const argsText = ref("");
const codeInputsText = ref("");
const headersText = ref("");
const headerRows = ref<{ key: string; value: string }[]>([]);
const bodyText = ref("");
const itemsText = ref("");
const iterArgsText = ref("");
const categoriesText = ref("");
const schemaText = ref("");
const aggFields = ref<{ name: string; value: string }[]>([]);

function _jsonText(v: any): string {
  return v && typeof v === "object" ? JSON.stringify(v, null, 0) : v || "";
}

// 切换到新节点时重设表单（组件复用不重挂载，必须显式同步）
function syncFromNode() {
  const nd = props.node;
  if (!nd) return;
  const data = (nd.data || {}) as any;
  Object.keys(d).forEach((k) => delete d[k]);
  Object.assign(d, data);
  vars.value = (data.variables || []).map((v: any) => ({
    name: v.name || "",
    type: v.type || "string",
    default: v.default ?? "",
    required: !!v.required,
    desc: v.desc || "",
  }));
  argsText.value = _jsonText(data.args);
  codeInputsText.value = _jsonText(data.inputs);
  headersText.value = _jsonText(data.headers);
  headerRows.value = Object.entries((data.headers || {}) as Record<string, any>).map(([k, v]) => ({
    key: k,
    value: typeof v === "string" ? v : JSON.stringify(v),
  }));
  bodyText.value = _jsonText(data.body);
  itemsText.value = Array.isArray(data.items)
    ? JSON.stringify(data.items, null, 0)
    : data.items || "";
  iterArgsText.value = _jsonText(data.args);
  categoriesText.value = Array.isArray(data.categories)
    ? data.categories.join(", ")
    : data.categories || "";
  schemaText.value = Array.isArray(data.schema)
    ? JSON.stringify(data.schema, null, 0)
    : data.schema || "";
  aggFields.value = Array.isArray(data.fields)
    ? data.fields.map((f: any) => ({ name: f.name || "", value: f.value || "" }))
    : [];
}
syncFromNode();
watch(
  () => props.node,
  () => syncFromNode()
);

const modelOptions = ref<{ id: number; name: string }[]>([]);
const toolOptions = ref<{ id: number; name: string }[]>([]);
const kbOptions = ref<{ id: number; name: string }[]>([]);
const workflowOptions = ref<{ id: number; name: string }[]>([]);
const agentOptions = ref<{ id: number; agent_name: string }[]>([]);

// 节点启用开关（默认启用）
const nodeEnabled = computed({
  get: () => d.enabled !== false,
  set: (v: boolean) => {
    d.enabled = !!v;
  },
});

// 条件节点：参数化构建（多条件 AND/OR）
const COND_OPS = computed(() => [
  { v: "==", label: t("ai_workflow.p_cond_op_eq") },
  { v: "!=", label: t("ai_workflow.p_cond_op_neq") },
  { v: ">", label: t("ai_workflow.p_cond_op_gt") },
  { v: "<", label: t("ai_workflow.p_cond_op_lt") },
  { v: ">=", label: t("ai_workflow.p_cond_op_gte") },
  { v: "<=", label: t("ai_workflow.p_cond_op_lte") },
  { v: "in", label: t("ai_workflow.p_cond_op_in") },
  { v: "not in", label: t("ai_workflow.p_cond_op_nin") },
  { v: "contains", label: t("ai_workflow.p_cond_op_contains") },
]);
const condLogic = ref<"and" | "or">("and");
const conditions = ref<{ var: string; op: string; val: string }[]>([]);
function addCond() {
  conditions.value.push({ var: "", op: "==", val: "" });
}
function _buildLiteral(raw: string): any {
  if (raw === "true") return true;
  if (raw === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(raw)) return Number(raw);
  return JSON.stringify(raw);
}
function _buildOne(c: { var: string; op: string; val: string }): string {
  const v = c.var.trim();
  const op = c.op;
  const raw = c.val.trim();
  if (op === "in" || op === "not in") {
    let arr: any = [];
    try {
      arr = JSON.parse(raw || "[]");
    } catch {
      arr = raw ? raw.split(/[,，]/).map((s) => s.trim()) : [];
    }
    return `${v} ${op} ${JSON.stringify(arr)}`;
  }
  if (op === "contains") {
    return `${JSON.stringify(raw)} in ${v}`;
  }
  return `${v} ${op} ${_buildLiteral(raw)}`;
}
function applyCond() {
  const parts = conditions.value.filter((c) => c.var.trim()).map((c) => _buildOne(c));
  if (!parts.length) {
    ElMessage.warning(t("ai_workflow.p_no_condition"));
    return;
  }
  d.expression = parts.join(condLogic.value === "and" ? " and " : " or ");
}

// 本节点引用到的输入变量（从 data 的字符串值中提取 {{var}}）
const refVars = computed(() => {
  const found = new Set<string>();
  const walk = (val: any) => {
    if (typeof val === "string") {
      const re = /\{\{\s*([\w\u4e00-\u9fa5]+)\s*\}\}/g;
      let m: RegExpExecArray | null;
      while ((m = re.exec(val))) found.add(m[1]);
    } else if (Array.isArray(val)) {
      val.forEach(walk);
    } else if (val && typeof val === "object") {
      Object.values(val).forEach(walk);
    }
  };
  walk(d);
  return Array.from(found);
});

// 引用但未定义/无来源的变量（提示校验）
const unknownVars = computed(() => {
  const known = new Set((props.availableVars || []).map((v) => v.name));
  return refVars.value.filter((v) => !known.has(v));
});

function addVar() {
  vars.value.push({ name: "", type: "string", default: "", required: false, desc: "" });
}

function emitChange() {
  const data: Record<string, any> = { ...d };
  if (type.value === "start") data.variables = vars.value;
  if (type.value === "tool") {
    try {
      data.args = argsText.value ? JSON.parse(argsText.value) : {};
    } catch {
      data.args = {};
    }
  }
  if (type.value === "code") {
    try {
      data.inputs = codeInputsText.value ? JSON.parse(codeInputsText.value) : {};
    } catch {
      data.inputs = {};
    }
  }
  if (type.value === "http") {
    data.headers = Object.fromEntries(
      headerRows.value.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value])
    );
    try {
      data.body = bodyText.value ? JSON.parse(bodyText.value) : {};
    } catch {
      data.body = {};
    }
  }
  if (type.value === "iteration") {
    try {
      const v: any = itemsText.value ? JSON.parse(itemsText.value) : [];
      data.items = Array.isArray(v) ? v : v;
    } catch {
      data.items = itemsText.value;
    }
    try {
      data.args = iterArgsText.value ? JSON.parse(iterArgsText.value) : {};
    } catch {
      data.args = {};
    }
  }
  if (type.value === "classifier") {
    data.categories = (categoriesText.value || "")
      .split(/[,，\n]/)
      .map((s: string) => s.trim())
      .filter(Boolean);
  }
  if (type.value === "extractor") {
    try {
      const v: any = schemaText.value ? JSON.parse(schemaText.value) : [];
      data.schema = Array.isArray(v) ? v : [];
    } catch {
      data.schema = [];
    }
  }
  if (type.value === "variable_aggregator") {
    data.fields = aggFields.value
      .map((f) => ({ name: f.name, value: f.value }))
      .filter((f) => f.name);
  }
  emit("change", data);
}

watch(
  [
    d,
    vars,
    argsText,
    codeInputsText,
    headersText,
    headerRows,
    bodyText,
    itemsText,
    iterArgsText,
    categoriesText,
    schemaText,
    aggFields,
  ],
  emitChange,
  { deep: true }
);

onMounted(async () => {
  try {
    const [mr, tr, kr, wr, ar] = await Promise.all([
      getAiModelList({}),
      getAiToolList({}),
      getAiKnowledgeList(),
      getAiWorkflowList(),
      getAiAgentList(),
    ]);
    modelOptions.value = (mr.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
    toolOptions.value = (tr.data?.data || []).map((t: any) => ({ id: t.id, name: t.name }));
    kbOptions.value = (kr.data?.data || []).map((k: any) => ({ id: k.id, name: k.name }));
    workflowOptions.value = (wr.data?.data || []).map((w: any) => ({ id: w.id, name: w.name }));
    agentOptions.value = (ar.data?.data || []).map((a: any) => ({
      id: a.id,
      agent_name: a.agent_name,
    }));
  } catch {
    /* ignore */
  }
});
</script>

<style scoped>
.var-item {
  max-width: 180px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.var-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.var-tip code {
  padding: 1px 4px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
}

.io-var-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.io-var-src {
  margin-left: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.io-var-warn {
  margin-top: 6px;
}

.node-disabled-tip {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chain-text {
  padding: 6px 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  word-break: break-word;
}

.cond-logic {
  margin-bottom: 8px;
}

.cond-row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;

  .cond-var {
    flex: 1.2;
  }
  .cond-op {
    width: 120px;
  }
  .cond-val {
    flex: 1;
  }
}

.cond-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.cond-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.http-kv {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;

  .http-kv__k {
    width: 180px;
  }
  .http-kv__v {
    flex: 1;
  }
}

.parallel-branch {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}

.start-var {
  margin-bottom: 10px;
  padding: 8px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;

  .start-var__row {
    display: flex;
    gap: 6px;
    align-items: center;

    + .start-var__row {
      margin-top: 6px;
    }
  }

  .start-var__name {
    width: 120px;
  }
  .start-var__type {
    width: 88px;
  }
  .start-var__default {
    flex: 1;
  }
  .start-var__desc {
    flex: 1;
  }
}

.var-suggest {
  position: fixed;
  z-index: 3000;
  width: 260px;
  max-height: 220px;
  overflow: auto;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: var(--el-box-shadow-light);
}
.var-suggest__item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
}
.var-suggest__item:hover {
  background: var(--el-fill-color-light);
}
.var-suggest__item code {
  padding: 1px 4px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  font-size: 12px;
}
.var-suggest__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
