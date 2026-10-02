<!-- 节点属性面板：按所选节点类型渲染对应配置表单 -->
<template>
  <el-form label-position="top" size="small">
    <!-- start：输入变量 -->
    <template v-if="type === 'start'">
      <el-form-item label="输入变量">
        <el-button size="small" :icon="Plus" @click="addVar">添加变量</el-button>
      </el-form-item>
      <el-form-item v-for="(v, i) in vars" :key="i" label="变量">
        <el-space fill>
          <el-input v-model="v.name" placeholder="变量名" style="width: 140px" />
          <el-select v-model="v.type" style="width: 90px">
            <el-option label="文本" value="string" />
            <el-option label="数字" value="number" />
          </el-select>
          <el-button link type="danger" :icon="Delete" @click="vars.splice(i, 1)" />
        </el-space>
      </el-form-item>
    </template>

    <!-- llm：模型 + 提示词 + 温度 + 工具 -->
    <template v-else-if="type === 'llm'">
      <el-form-item label="模型">
        <el-select v-model="d.model_id" filterable placeholder="选择模型" style="width: 100%">
          <el-option v-for="m in modelOptions" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="提示词（支持 {{变量}} 插值）">
        <el-input
          v-model="d.prompt"
          type="textarea"
          :rows="4"
          placeholder="如：你是助手，回答：{{query}}"
        />
      </el-form-item>
      <el-form-item label="温度">
        <el-slider v-model="d.temperature" :min="0" :max="2" :step="0.1" />
      </el-form-item>
      <el-form-item label="绑定工具">
        <el-select v-model="d.tools" multiple filterable placeholder="选择工具" style="width: 100%">
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="工具调用需人工审批（HITL）">
        <el-switch v-model="d.require_approval" />
      </el-form-item>
      <el-form-item label="输出变量名（可选）">
        <el-input v-model="d.output_variable" placeholder="供下游引用" />
      </el-form-item>
    </template>

    <!-- knowledge：知识检索（阶段 3 落地） -->
    <template v-else-if="type === 'knowledge'">
      <el-form-item label="关联知识库">
        <el-select
          v-model="d.knowledge_ids"
          multiple
          filterable
          placeholder="选择知识库"
          style="width: 100%"
        >
          <el-option v-for="kb in kbOptions" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="检索查询模板">
        <el-input v-model="d.query" placeholder="如：{{query}}" />
      </el-form-item>
      <el-form-item label="返回条数">
        <el-input-number v-model="d.top_k" :min="1" :max="10" />
      </el-form-item>
      <el-form-item label="输出变量名（可选）">
        <el-input v-model="d.output_variable" placeholder="供下游 LLM 用 {{变量}} 引用" />
      </el-form-item>
    </template>

    <!-- tool：工具调用 -->
    <template v-else-if="type === 'tool'">
      <el-form-item label="工具名">
        <el-select v-model="d.tool_name" filterable placeholder="选择工具" style="width: 100%">
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="参数（JSON）">
        <el-input v-model="argsText" type="textarea" :rows="3" placeholder='{"path":"/x"}' />
      </el-form-item>
      <el-form-item label="输出变量名">
        <el-input v-model="d.output_variable" />
      </el-form-item>
    </template>

    <!-- code：代码转换 -->
    <template v-else-if="type === 'code'">
      <el-form-item label="Python 代码">
        <el-input v-model="d.code" type="textarea" :rows="5" placeholder="见下方说明" />
      </el-form-item>
      <el-form-item label="输入变量映射（JSON）">
        <el-input
          v-model="codeInputsText"
          type="textarea"
          :rows="2"
          placeholder='{"x":"{{变量}}"}'
        />
      </el-form-item>
      <el-form-item label="输出变量名">
        <el-input v-model="d.output_variable" />
      </el-form-item>
      <el-alert
        title="在受限命名空间执行，末行表达式结果写入输出变量"
        type="info"
        :closable="false"
        show-icon
      />
    </template>

    <!-- condition：条件分支 -->
    <template v-else-if="type === 'condition'">
      <el-form-item label="条件表达式">
        <el-input v-model="d.expression" placeholder="如：{{v}} == 1" />
      </el-form-item>
      <el-alert
        title="连接时从上（绿=真）/下（红=假）句柄拖出即可区分分支"
        type="info"
        :closable="false"
        show-icon
      />
    </template>

    <!-- variable：变量赋值 -->
    <template v-else-if="type === 'variable'">
      <el-form-item label="变量名">
        <el-input v-model="d.name" />
      </el-form-item>
      <el-form-item label="值">
        <el-input v-model="d.value" placeholder="可引用 {{其他变量}}" />
      </el-form-item>
    </template>

    <!-- http：外部请求 -->
    <template v-else-if="type === 'http'">
      <el-form-item label="方法">
        <el-select v-model="d.method" style="width: 120px">
          <el-option
            v-for="m in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']"
            :key="m"
            :label="m"
            :value="m"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="URL（支持 {{变量}}）">
        <el-input v-model="d.url" placeholder="https://api.example.com/{{id}}" />
      </el-form-item>
      <el-form-item label="请求头（JSON）">
        <el-input
          v-model="headersText"
          type="textarea"
          :rows="2"
          placeholder='{"Authorization":"Bearer {{token}}"}'
        />
      </el-form-item>
      <el-form-item label="请求体（JSON，GET 可留空）">
        <el-input v-model="bodyText" type="textarea" :rows="3" placeholder='{"q":"{{query}}"}' />
      </el-form-item>
      <el-form-item label="输出变量名">
        <el-input v-model="d.output_variable" />
      </el-form-item>
      <el-alert
        title="响应 {status, body, text} 写入输出变量"
        type="info"
        :closable="false"
        show-icon
      />
    </template>

    <!-- iteration：迭代/批量 -->
    <template v-else-if="type === 'iteration'">
      <el-form-item label="遍历列表（JSON 数组）">
        <el-input
          v-model="itemsText"
          type="textarea"
          :rows="2"
          placeholder="[1, 2, 3] 或 {{变量}}"
        />
      </el-form-item>
      <el-form-item label="工具">
        <el-select v-model="d.tool_name" filterable placeholder="选择工具" style="width: 100%">
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="工具参数（JSON，支持 {{item}}）">
        <el-input
          v-model="iterArgsText"
          type="textarea"
          :rows="2"
          placeholder='{"id":"{{item}}"}'
        />
      </el-form-item>
      <el-form-item label="最大迭代次数">
        <el-input-number v-model="d.max_iterations" :min="1" :max="100" />
      </el-form-item>
      <el-form-item label="输出变量名">
        <el-input v-model="d.output_variable" placeholder="结果数组" />
      </el-form-item>
    </template>

    <!-- classifier：问题分类器 -->
    <template v-else-if="type === 'classifier'">
      <el-form-item label="类别（逗号或换行分隔）">
        <el-input v-model="categoriesText" type="textarea" :rows="2" placeholder="查询, 操作" />
      </el-form-item>
      <el-form-item label="输入（支持 {{变量}}）">
        <el-input v-model="d.query" placeholder="如：{{query}}" />
      </el-form-item>
      <el-form-item label="输出变量名">
        <el-input v-model="d.output_variable" placeholder="命中的类别" />
      </el-form-item>
    </template>

    <!-- end：结束输出 -->
    <template v-else-if="type === 'end'">
      <el-form-item label="输出模板">
        <el-input
          v-model="d.output_template"
          type="textarea"
          :rows="3"
          placeholder="留空则取最近一步输出；可写 {{变量}}"
        />
      </el-form-item>
    </template>
  </el-form>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from "vue";
import { Plus, Delete } from "@element-plus/icons-vue";
import type { Node } from "@vue-flow/core";
import { getAiModelList } from "@/api/module_ai/model";
import { getAiToolList } from "@/api/module_ai/tool";
import { getAiKnowledgeList } from "@/api/module_ai/knowledge";

const props = defineProps<{ node: Node }>();
const emit = defineEmits(["change"]);

const type = props.node.type || "llm";
const d = reactive<Record<string, any>>({ ...((props.node.data || {}) as any) });
// start 变量用本地数组代理（避免直接改 reactive 复杂结构）
const vars = ref<Array<{ name: string; type: string }>>(
  (d.variables || []).map((v: any) => ({ name: v.name || "", type: v.type || "string" }))
);
const argsText = ref(
  d.args && typeof d.args === "object" ? JSON.stringify(d.args, null, 0) : d.args || ""
);
const codeInputsText = ref(
  d.inputs && typeof d.inputs === "object" ? JSON.stringify(d.inputs, null, 0) : d.inputs || ""
);
const headersText = ref(
  d.headers && typeof d.headers === "object" ? JSON.stringify(d.headers, null, 0) : d.headers || ""
);
const bodyText = ref(
  d.body && typeof d.body === "object" ? JSON.stringify(d.body, null, 0) : d.body || ""
);
const itemsText = ref(Array.isArray(d.items) ? JSON.stringify(d.items, null, 0) : d.items || "");
const iterArgsText = ref(
  d.args && typeof d.args === "object" ? JSON.stringify(d.args, null, 0) : d.args || ""
);
const categoriesText = ref(
  Array.isArray(d.categories) ? d.categories.join(", ") : d.categories || ""
);

const modelOptions = ref<{ id: number; name: string }[]>([]);
const toolOptions = ref<{ id: number; name: string }[]>([]);
const kbOptions = ref<{ id: number; name: string }[]>([]);

function addVar() {
  vars.value.push({ name: "", type: "string" });
}

function emitChange() {
  const data: Record<string, any> = { ...d };
  if (type === "start") data.variables = vars.value;
  if (type === "tool") {
    try {
      data.args = argsText.value ? JSON.parse(argsText.value) : {};
    } catch {
      data.args = {};
    }
  }
  if (type === "code") {
    try {
      data.inputs = codeInputsText.value ? JSON.parse(codeInputsText.value) : {};
    } catch {
      data.inputs = {};
    }
  }
  if (type === "http") {
    try {
      data.headers = headersText.value ? JSON.parse(headersText.value) : {};
    } catch {
      data.headers = {};
    }
    try {
      data.body = bodyText.value ? JSON.parse(bodyText.value) : {};
    } catch {
      data.body = {};
    }
  }
  if (type === "iteration") {
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
  if (type === "classifier") {
    data.categories = (categoriesText.value || "")
      .split(/[,，\n]/)
      .map((s: string) => s.trim())
      .filter(Boolean);
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
    bodyText,
    itemsText,
    iterArgsText,
    categoriesText,
  ],
  emitChange,
  { deep: true }
);

onMounted(async () => {
  try {
    const [mr, tr, kr] = await Promise.all([
      getAiModelList({}),
      getAiToolList({}),
      getAiKnowledgeList(),
    ]);
    modelOptions.value = (mr.data?.data || []).map((m: any) => ({ id: m.id, name: m.name }));
    toolOptions.value = (tr.data?.data || []).map((t: any) => ({ id: t.id, name: t.name }));
    kbOptions.value = (kr.data?.data || []).map((k: any) => ({ id: k.id, name: k.name }));
  } catch {
    /* ignore */
  }
});
</script>
