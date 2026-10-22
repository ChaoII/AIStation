<!--
  对象类型 → 函数 子页（本体计算函数管理）
  从 index.vue 整体迁入：函数清单 + 新建/编辑/删除/校验/运行
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">本体计算函数</span>
      <el-tag size="small" type="info" effect="plain">{{ list.length }}</el-tag>
      <el-button
        class="ont-sec__op"
        size="small"
        type="primary"
        :icon="Plus"
        @click="openFuncEdit()"
      >
        新建函数
      </el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      class="ont-obj__note"
      title="函数会作为 Agent 的能力（工具）暴露给 AI 使用。改动进入待保存列表，点「保存」后生效。"
    />
    <el-table :data="list" size="small" border max-height="460" class="ont-fn__table" stripe>
      <template #empty>
        <el-empty :image-size="50" description="暂无函数，点右上角「新建函数」" />
      </template>
      <el-table-column prop="name" label="函数名" min-width="140" show-overflow-tooltip />
      <el-table-column prop="code" label="编码" min-width="130" show-overflow-tooltip />
      <el-table-column label="形态" width="110">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ fnKindLabel(row.kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="200" align="center">
        <template #default="{ row }">
          <el-button icon="VideoPlay" link type="primary" size="small" @click="openFnRun(row)">
            运行
          </el-button>
          <el-button icon="edit" link type="primary" size="small" @click="openFuncEdit(row)">
            编辑
          </el-button>
          <el-button link type="danger" size="small" @click="removeFunc(row)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建 / 编辑函数 -->
    <el-dialog v-model="funcDialog" title="本体计算函数" width="900px" append-to-body>
      <el-form :model="funcForm" label-width="140px">
        <el-form-item label="函数名" required>
          <el-input v-model="funcForm.name" placeholder="如 摄像机在线率（%）" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input v-model="funcForm.code" placeholder="cam_online_rate" />
        </el-form-item>
        <el-form-item label="所属对象类型" required>
          <el-tag size="small" type="primary" effect="dark">{{ objectLabel(props.code) }}</el-tag>
        </el-form-item>
        <el-form-item label="函数形态" required>
          <el-radio-group v-model="funcForm.kind">
            <el-radio-button v-for="k in FN_KINDS" :key="k.value" :value="k.value">
              {{ k.label }}
            </el-radio-button>
          </el-radio-group>
          <div class="ont-hint">{{ fnKindHint }}</div>
        </el-form-item>

        <el-form-item v-if="funcForm.kind === 'expression'" label="表达式">
          <el-input
            v-model="funcForm.expr"
            type="textarea"
            :rows="2"
            placeholder="如 round(percent(online_count, total_count), 1)"
          />
          <div class="ont-hint">
            支持 + - * / 与比较、三元表达式，以及 {{ fnBuiltins.length }} 个内置函数。
            <el-button
              :icon="showBuiltins ? 'ArrowUp' : 'View'"
              type="primary"
              link
              @click="showBuiltins = !showBuiltins"
            >
              {{ showBuiltins ? "收起" : "查看内置函数" }}
            </el-button>
          </div>
          <div v-if="showBuiltins" class="ont-builtins">
            <el-tag
              v-for="b in fnBuiltins"
              :key="b"
              size="small"
              effect="plain"
              class="ont-tag-gap"
            >
              {{ b }}
            </el-tag>
          </div>
        </el-form-item>

        <el-form-item label="入参（JSON）">
          <el-input
            v-model="funcForm.parametersText"
            type="textarea"
            :rows="5"
            :placeholder="fnParamsPlaceholder"
          />
          <div class="ont-hint">
            声明后生成 Agent 工具入参。
            <code>source</code>
            可为 parameter（调用方传入）、 object_property（取对象属性，需填
            <code>object_property</code>
            ）、static、 current_user、current_time。
          </div>
        </el-form-item>

        <el-form-item label="出参（JSON）">
          <el-input
            v-model="funcForm.outputsText"
            type="textarea"
            :rows="2"
            placeholder='[{"key":"rate","name":"在线率(%)","type":"number"}]'
          />
          <div class="ont-hint">声明返回值结构，会写进 Agent 工具说明</div>
        </el-form-item>

        <el-form-item v-if="funcForm.kind !== 'expression'" label="形态配置（JSON）">
          <el-input
            v-model="funcForm.configText"
            type="textarea"
            :rows="7"
            :placeholder="fnConfigPlaceholder"
          />
          <div class="ont-hint">{{ fnConfigHint }}</div>
        </el-form-item>

        <el-form-item label="描述">
          <el-input v-model="funcForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Tool description">
          <el-input
            v-model="funcForm.tool_description"
            type="textarea"
            :rows="2"
            placeholder="给 AI 看的工具描述：这个函数算什么、什么时候该调用。留空则回退到「描述」"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="funcDialog = false">取消</el-button>
        <el-button v-hasPerm="'module_ai:ontology:edit'" :loading="fnChecking" @click="checkFunc">
          校验定义
        </el-button>
        <el-button type="primary" :loading="savingObj" @click="saveFunc">保存</el-button>
      </template>
    </el-dialog>

    <!-- 函数运行 / 试运行 -->
    <el-dialog
      v-model="fnRunDialog"
      title="运行函数（不会写入任何数据）"
      width="600px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="`函数：${fnRunTarget?.name || ''}（${fnKindLabel(fnRunTarget?.kind)}）`"
      />
      <el-form label-width="130px">
        <el-form-item v-if="fnRunNeedsObjectKey" label="对象行 ID">
          <el-input v-model="fnRunForm.object_key" placeholder="聚合/对象上下文的实例主键" />
        </el-form-item>
        <el-form-item v-for="p in fnRunInputs" :key="p.key" :label="p.name || p.key">
          <el-input v-model="fnRunForm.args[p.key]" :placeholder="p.description || p.key" />
          <div v-if="p.required" class="ont-hint">必填</div>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="fnRunInputs.some((p: any) => p.inferred)"
        type="info"
        :closable="false"
        class="ont-note"
        title="该函数未声明入参，下面按表达式里的变量推断。建议到「编辑」里正式声明入参，这样 AI 调用时也能正确传值。"
      />
      <el-button
        v-hasPerm="'module_ai:ontology:edit'"
        type="primary"
        :loading="fnRunning"
        @click="runFunc"
      >
        运行
      </el-button>
      <template v-if="fnRunResult">
        <el-divider />
        <el-alert
          :type="fnRunResult.ok ? 'success' : 'error'"
          :closable="false"
          :title="fnRunResult.ok ? '执行成功' : fnRunResult.msg || '执行失败'"
        />
        <template v-if="fnRunResult.ok">
          <div class="ont-test__block">
            <div class="ont-sec__title">返回值</div>
            <pre class="ont-run__out">{{ JSON.stringify(fnRunResult.value, null, 2) }}</pre>
          </div>
          <div class="ont-test__block">
            <div class="ont-sec__title">实际入参</div>
            <pre class="ont-run__out">{{ JSON.stringify(fnRunResult.inputs, null, 2) }}</pre>
          </div>
        </template>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { checkOntFunction, getOntFunctionBuiltins, runOntFunction } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const props = defineProps<{ code: string }>();

const { functionsOf, stage, reloadAll, objectLabel } = useOntologyData();

const list = computed(() => functionsOf(props.code));

/* ---------------- 函数形态 ---------------- */
const FN_KINDS = [
  { value: "expression", label: "表达式" },
  { value: "aggregate", label: "关联聚合" },
  { value: "http", label: "外部服务" },
  { value: "model", label: "模型调用" },
];
function fnKindLabel(k: string) {
  return FN_KINDS.find((x) => x.value === k)?.label || k || "表达式";
}
const fnKindHint = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return "沿关系链在关联对象上聚合（count/sum/avg/min/max/first/last/collect_list/collect_set），需要对象主键作上下文";
    case "http":
      return "调用外部 REST API，按 result_path 从响应里取值";
    case "model":
      return "调用平台已登记的模型（AI 管理 → 模型配置），把响应文本作为返回值";
    default:
      return "受控表达式：算术、比较、三元表达式 + 内置函数；无字段访问、无任意代码执行";
  }
});
const fnParamsPlaceholder = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return '[{"key":"object_key","name":"对象ID","type":"string","required":true}]';
    case "http":
      return '[{"key":"text","name":"文本","type":"string","required":true}]';
    case "model":
      return '[{"key":"text","name":"文本","type":"string","required":true}]';
    default:
      return '[{"key":"online_count","name":"在线路数","type":"number","required":true,"description":"当前在线摄像机数量"}]';
  }
});
const fnConfigPlaceholder = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return JSON.stringify(
        {
          from_object: "video_cameras",
          source_object: "video_alarm_records",
          link_path: [27],
          aggregation: "count",
          property: "",
          limit: 10,
        },
        null,
        2
      );
    case "http":
      return JSON.stringify(
        {
          url: "https://example.com/api/score",
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body_template: '{"text":"{{text}}"}',
          result_path: "data.score",
          timeout: 10,
        },
        null,
        2
      );
    default:
      return JSON.stringify(
        { model_id: 1, system: "你是简洁的助手", prompt: "概括：{{text}}", temperature: 0.2 },
        null,
        2
      );
  }
});
const fnConfigHint = computed(() =>
  funcForm.kind === "aggregate"
    ? "link_path 是关系 ID 数组（最多 3 层）；property 在 count 时可留空"
    : funcForm.kind === "http"
      ? "URL 必须是 http/https；body_template 支持 {{参数名}} 占位"
      : "model_id 留空则用默认模型；prompt 支持 {{参数名}} 占位"
);
const fnBuiltins = ref<string[]>([]);
const showBuiltins = ref(false);
const fnChecking = ref(false);

const funcDialog = ref(false);

const funcBlank = () => ({
  id: null,
  object_code: props.code || "",
  name: "",
  code: "",
  kind: "expression",
  expr: "",
  description: "",
  tool_description: "",
  parametersText: "",
  outputsText: "",
  configText: "",
});
const funcForm = reactive<any>(funcBlank());
function openFuncEdit(f?: any) {
  Object.assign(funcForm, funcBlank(), f ? { ...f } : {});
  funcForm.kind = f?.kind || "expression";
  funcForm.parametersText = f?.parameters?.length ? JSON.stringify(f.parameters, null, 2) : "";
  funcForm.outputsText = f?.outputs?.length ? JSON.stringify(f.outputs, null, 2) : "";
  funcForm.configText =
    f?.config && Object.keys(f.config).length ? JSON.stringify(f.config, null, 2) : "";
  funcDialog.value = true;
}

/** JSON 文本框解析（空 → []，非法 → 抛错由调用方提示） */
function parseJsonList(text: string, label: string): any[] {
  const s = (text || "").trim();
  if (!s) return [];
  let v: any;
  try {
    v = JSON.parse(s);
  } catch {
    throw new Error(`${label}不是合法 JSON`);
  }
  if (!Array.isArray(v)) throw new Error(`${label}必须是 JSON 数组`);
  return v;
}

/** 解析弹窗里的三段 JSON，出错时返回 null */
function funcPayload(): Record<string, any> | null {
  let parameters: any[] = [];
  let outputs: any[] = [];
  let config: Record<string, any> = {};
  try {
    parameters = parseJsonList(funcForm.parametersText, "入参");
    outputs = parseJsonList(funcForm.outputsText, "出参");
    const raw = (funcForm.configText || "").trim();
    if (raw) {
      const v = JSON.parse(raw);
      if (typeof v !== "object" || Array.isArray(v)) throw new Error("形态配置必须是 JSON 对象");
      config = v;
    }
  } catch (e: any) {
    ElMessage.error(e.message || "JSON 解析失败");
    return null;
  }
  const payload: Record<string, any> = {};
  Object.keys(funcForm).forEach((k) => {
    if (!["parametersText", "outputsText", "configText"].includes(k)) payload[k] = funcForm[k];
  });
  payload.parameters = parameters;
  payload.outputs = outputs;
  payload.config = config;
  return payload;
}

/** 只做前端粗校验：表达式变量必须在入参里、且不能是内置函数名 */
function funcLocalErrors(payload: Record<string, any>): string[] {
  const errs: string[] = [];
  if (payload.kind !== "expression") return errs;
  const declared: string[] = (payload.parameters || []).map((p: any) => p.key).filter(Boolean);
  const ids: string[] = Array.from(
    new Set<string>(((funcForm.expr as string) || "").match(/[A-Za-z_][A-Za-z0-9_]*/g) || [])
  );
  const missing = ids.filter((v) => !declared.includes(v) && !fnBuiltins.value.includes(v));
  if (missing.length) errs.push(`表达式里的变量 ${missing.join("、")} 未在入参中声明`);
  return errs;
}

async function checkFunc() {
  const payload = funcPayload();
  if (!payload) return;
  const local = funcLocalErrors(payload);
  fnChecking.value = true;
  try {
    const r = await checkOntFunction(payload);
    const errs = [...local, ...((r.data?.data?.errors as string[]) || [])];
    if (!errs.length) ElMessage.success("定义正确");
    else
      ElMessageBox.alert(errs.map((e: string) => `· ${e}`).join("<br/>"), "发现以下问题", {
        dangerouslyUseHTMLString: true,
      });
  } finally {
    fnChecking.value = false;
  }
}

const savingObj = ref(false);
async function saveFunc() {
  if (!funcForm.code?.trim() || !funcForm.name?.trim() || !funcForm.object_code)
    return ElMessage.warning("请填函数名、编码与所属对象类型");
  const payload = funcPayload();
  if (!payload) return;
  const errs = funcLocalErrors(payload);
  if (errs.length) return ElMessage.error(errs.join("；"));
  savingObj.value = true;
  try {
    const ok = await stage("function", payload.id ? "update" : "create", payload);
    if (ok) funcDialog.value = false;
  } finally {
    savingObj.value = false;
  }
}
async function removeFunc(f: any) {
  await ElMessageBox.confirm(
    `将删除函数「${f.name}」，引用它的智能体能力会失效。改动会先进入待保存列表，确认删除？`,
    "删除函数",
    { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
  );
  await stage("function", "delete", { id: f.id, code: f.code, name: f.name }, "已暂存删除");
  await reloadAll();
}

/* ---------------- 函数运行 ---------------- */
const fnRunDialog = ref(false);
const fnRunning = ref(false);
const fnRunTarget = ref<any>(null);
const fnRunResult = ref<any>(null);
const fnRunForm = reactive<{ object_key: string; args: Record<string, any> }>({
  object_key: "",
  args: {},
});
const fnRunInputs = computed(() => {
  const f = fnRunTarget.value;
  if (!f) return [];
  const declared: any[] = (f.parameters || []).filter((p: any) => p.source !== "object_property");
  if (declared.length) return declared;
  if ((f.kind || "expression") !== "expression") return [];
  const ids = Array.from(
    new Set<string>(((f.expr as string) || "").match(/[A-Za-z_][A-Za-z0-9_]*/g) || [])
  ).filter((v) => !fnBuiltins.value.includes(v));
  return ids.map((v) => ({ key: v, name: v, type: "number", required: true, inferred: true }));
});
const fnRunNeedsObjectKey = computed(() => {
  const f = fnRunTarget.value;
  if (!f) return false;
  if ((f.kind || "expression") !== "expression") return true;
  return (f.parameters || []).some((p: any) => p.source === "object_property");
});
function openFnRun(f: any) {
  fnRunTarget.value = f;
  fnRunResult.value = null;
  fnRunForm.object_key = "";
  const args: Record<string, any> = {};
  fnRunInputs.value.forEach((p: any) => (args[p.key] = ""));
  fnRunForm.args = args;
  fnRunDialog.value = true;
}
async function runFunc() {
  if (!fnRunTarget.value) return;
  fnRunning.value = true;
  try {
    const args: Record<string, any> = {};
    Object.keys(fnRunForm.args).forEach((k) => {
      if (fnRunForm.args[k] !== "") args[k] = fnRunForm.args[k];
    });
    const r = await runOntFunction({
      code: fnRunTarget.value.code,
      args,
      object_key: fnRunForm.object_key,
    });
    fnRunResult.value = r.data?.data || null;
  } catch (e: any) {
    ElMessage.error(e?.msg || "运行失败");
  } finally {
    fnRunning.value = false;
  }
}

onMounted(async () => {
  try {
    const b = await getOntFunctionBuiltins();
    fnBuiltins.value = b.data?.data || [];
  } catch {
    fnBuiltins.value = [];
  }
});
</script>

<style scoped lang="scss">
.ont-fn__table {
  margin-top: 8px;
}
.ont-obj__note {
  margin-bottom: 8px;
}
</style>
