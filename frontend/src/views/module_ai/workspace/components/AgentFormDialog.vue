<!-- 智能体新建/编辑弹窗（工作台内嵌复用；独立菜单页已并入工作台，不再跳转 /ai/agent） -->
<template>
  <el-dialog
    :model-value="modelValue"
    :title="editingAgent ? '编辑智能体' : '新建智能体'"
    width="620px"
    append-to-body
    destroy-on-close
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form v-loading="loadingOptions" :model="form" label-width="90px" size="default">
      <el-form-item label="名称" required>
        <el-input v-model="form.agent_name" placeholder="智能体名称" />
      </el-form-item>
      <el-form-item label="角色描述">
        <el-input
          v-model="form.agent_role"
          type="textarea"
          :rows="2"
          placeholder="这个智能体是做什么的"
        />
      </el-form-item>
      <el-form-item label="分类">
        <el-select v-model="form.category_id" clearable placeholder="选择分类" style="width: 100%">
          <el-option v-for="c in categories" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="运行方式">
        <el-radio-group v-model="form.runMode" @change="onRunModeChange">
          <el-radio value="workflow">绑定工作流</el-radio>
          <el-radio value="model">模型+提示词</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.runMode === 'workflow'" label="工作流">
        <el-select
          v-model="form.workflow_id"
          clearable
          placeholder="选择工作流"
          style="width: 100%"
        >
          <el-option v-for="w in workflowOptions" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
      </el-form-item>
      <template v-else>
        <el-form-item label="模型">
          <el-select v-model="form.model_id" clearable placeholder="选择模型" style="width: 100%">
            <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="提示词">
          <el-select
            v-model="form.prompt_id"
            clearable
            placeholder="选择提示词"
            style="width: 100%"
          >
            <el-option v-for="p in promptOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="工具">
          <el-select
            v-model="form.tool_ids"
            multiple
            filterable
            placeholder="选择工具"
            style="width: 100%"
          >
            <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="本体工具">
          <el-select
            v-model="form.capabilities"
            multiple
            filterable
            placeholder="绑定本体函数/动作（Agent 装配工具时按此生成）"
            style="width: 100%"
          >
            <el-option v-for="c in ontToolOptions" :key="c.code" :label="c.label" :value="c.code" />
          </el-select>
          <div class="ws-form-hint">
            勾选后 Agent 会得到对应的本体函数/动作工具；执行时仍按调用者本人的本体权限校验
          </div>
        </el-form-item>
        <el-form-item label="技能">
          <el-select
            v-model="form.skill_ids"
            multiple
            filterable
            placeholder="绑定技能广场技能"
            style="width: 100%"
          >
            <el-option v-for="s in skillOptions" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="知识库">
          <el-select
            v-model="form.knowledge_ids"
            multiple
            filterable
            placeholder="绑定知识库（RAG）"
            style="width: 100%"
          >
            <el-option v-for="k in knowledgeOptions" :key="k.id" :label="k.name" :value="k.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="MCP">
          <el-select
            v-model="form.mcp_ids"
            multiple
            filterable
            placeholder="绑定 MCP 服务器"
            style="width: 100%"
          >
            <el-option
              v-for="m in mcpOptions"
              :key="m.id"
              :label="`${m.name}（${m.transport}${m.enabled ? '' : ' · 未启用'}）`"
              :value="m.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="智能问数">
          <el-switch v-model="form.query_enabled" />
          <span style="margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px">
            启用后可回答基于系统数据的业务问题
          </span>
        </el-form-item>
        <el-form-item v-if="form.query_enabled" label="问数数据源">
          <el-select v-model="form.query_datasource" style="width: 100%">
            <el-option label="系统数据" value="system" />
            <el-option
              v-for="d in queryDatasources"
              :key="d.id"
              :label="d.name"
              :value="String(d.id)"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="温度">
          <el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
        </el-form-item>
      </template>
      <el-form-item label="主题色">
        <el-color-picker v-model="form.color" />
      </el-form-item>
      <el-form-item label="Markdown">
        <el-switch v-model="form.markdown" />
      </el-form-item>
      <el-form-item label="启用">
        <el-switch v-model="form.enabled" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { reactive, watch, ref } from "vue";
import { ElMessage } from "element-plus";

import { createAiAgent, updateAiAgent, getAgentCategoryList } from "@/api/module_ai/agent";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiPromptList } from "@/api/module_ai/prompt";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiWorkflowList } from "@/api/module_ai/workflow";
import { getAiSkillList } from "@/api/module_ai/skill";
import { getMcpList } from "@/api/module_ai/mcp";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";
import { getQueryDatasources } from "@/api/module_ai/query";
import { getOntActions, getOntFunctions } from "@/api/module_ai/ontology";

defineOptions({ name: "AgentFormDialog" });

const props = defineProps<{ modelValue: boolean; agent?: any }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void; (e: "refresh"): void }>();

const loadingOptions = ref(false);
const saving = ref(false);
const editingAgent = ref<any>(undefined);
const categories = ref<any[]>([]);
const modelOptions = ref<{ id: number; name: string }[]>([]);
const promptOptions = ref<{ id: number; name: string }[]>([]);
const toolOptions = ref<{ id: number; name: string }[]>([]);
const workflowOptions = ref<{ id: number; name: string }[]>([]);
const skillOptions = ref<{ id: number; name: string }[]>([]);
const knowledgeOptions = ref<{ id: number; name: string }[]>([]);
const mcpOptions = ref<{ id: number; name: string; transport: string; enabled: boolean }[]>([]);

// 本体工具：本体函数/动作的编码（Agent 按此装配 ont_fn__* / ont_action__* 工具）
const ontToolOptions = ref<{ code: string; label: string }[]>([]);
const queryDatasources = ref<any[]>([]);

const form = reactive<any>({});

function resetForm() {
  Object.assign(form, {
    agent_name: "",
    agent_role: "",
    category_id: null,
    runMode: "model",
    workflow_id: null,
    model_id: null,
    prompt_id: null,
    tool_ids: [],
    capabilities: [],
    skill_ids: [],
    knowledge_ids: [],
    mcp_ids: [],
    query_enabled: false,
    query_datasource: "system",
    temperature: 0.7,
    color: "#409eff",
    markdown: true,
    enabled: true,
    order: 0,
  });
}

async function loadOptions() {
  loadingOptions.value = true;
  try {
    const [cr, mr, pr, tr, wr, sr, kr, mcr, dr] = await Promise.all([
      getAgentCategoryList(),
      getAiModelList({}),
      getAiPromptList({}),
      getAiToolList({}),
      getAiWorkflowList(),
      getAiSkillList({}),
      getAiKnowledgeList(),
      getMcpList(),
      getQueryDatasources(),
    ]);
    categories.value = cr.data?.data || [];
    modelOptions.value = (mr.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
    promptOptions.value = (pr.data?.data || []).map((p: any) => ({ id: p.id, name: p.name }));
    toolOptions.value = (tr.data?.data || []).map((t: any) => ({ id: t.id, name: t.name }));
    workflowOptions.value = (wr.data?.data || []).map((w: any) => ({ id: w.id, name: w.name }));
    skillOptions.value = (sr.data?.data || []).map((s: any) => ({ id: s.id, name: s.name }));
    knowledgeOptions.value = (kr.data?.data || []).map((k: any) => ({ id: k.id, name: k.name }));
    mcpOptions.value = (mcr.data?.data || []).map((m: any) => ({
      id: m.id,
      name: m.name,
      transport: m.transport,
      enabled: m.enabled !== false,
    }));
    queryDatasources.value = dr.data?.data || [];
    // 本体工具选项：函数 + 动作（修前智能体表单**没有**本体能力入口，
    // 想让 Agent 用本体工具只能改数据库）
    try {
      const [fnr, actr] = await Promise.all([getOntFunctions(), getOntActions()]);
      const fns = ((fnr.data?.data || []) as any[]).map((f: any) => ({
        code: f.code,
        label: `函数：${f.name || f.code}`,
      }));
      const acts = ((actr.data?.data || []) as any[]).map((a: any) => ({
        code: a.code,
        label: `动作：${a.name || a.code}`,
      }));
      ontToolOptions.value = [...fns, ...acts];
    } catch {
      ontToolOptions.value = [];
    }
  } catch (e: any) {
    ElMessage.error(e?.message || "加载选项失败");
  } finally {
    loadingOptions.value = false;
  }
}

// 打开时：编辑则带入 agent，新建则清空；并加载选项
watch(
  () => props.modelValue,
  (open) => {
    if (!open) return;
    loadOptions();
    editingAgent.value = props.agent || undefined;
    if (props.agent) {
      Object.assign(form, {
        ...props.agent,
        runMode: props.agent.workflow_id ? "workflow" : "model",
        temperature: props.agent.temperature ?? 0.7,
      });
    } else {
      resetForm();
    }
  }
);

function onRunModeChange(mode: any) {
  const m = String(mode);
  if (m === "workflow") {
    form.workflow_id = null;
  } else {
    form.model_id = null;
    form.prompt_id = null;
    form.tool_ids = [];
    form.capabilities = [];
  }
}

async function save() {
  if (!form.agent_name) {
    ElMessage.warning("请填写智能体名称");
    return;
  }
  saving.value = true;
  try {
    const isModel = form.runMode === "model";
    const payload: any = {
      agent_name: form.agent_name,
      agent_role: form.agent_role,
      category_id: form.category_id,
      workflow_id: isModel ? null : form.workflow_id,
      model_id: isModel ? form.model_id : null,
      prompt_id: isModel ? form.prompt_id : null,
      capabilities: isModel ? form.capabilities || [] : [],
      tool_ids: isModel ? form.tool_ids : [],
      skill_ids: isModel ? form.skill_ids : [],
      knowledge_ids: isModel ? form.knowledge_ids : [],
      mcp_ids: isModel ? form.mcp_ids || [] : [],
      query_enabled: isModel ? form.query_enabled : false,
      query_datasource: isModel ? form.query_datasource || "system" : "system",
      temperature: isModel ? form.temperature : null,
      color: form.color,
      markdown: form.markdown,
      enabled: form.enabled,
      order: form.order || 0,
    };
    if (editingAgent.value) {
      await updateAiAgent(editingAgent.value.id, payload);
    } else {
      await createAiAgent(payload);
    }
    ElMessage.success("保存成功");
    emit("update:modelValue", false);
    emit("refresh");
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>
