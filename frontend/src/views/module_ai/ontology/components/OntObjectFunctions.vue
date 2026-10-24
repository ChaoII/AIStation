<!--
  对象类型 → 函数 子页（本体计算函数管理）
  从 index.vue 整体迁入：函数清单 + 新建/编辑/删除/校验/运行
-->
<template>
  <section class="ont-sec">
    <div class="ont-sec__head">
      <span class="ont-sec__title">{{ i18nT("ai_ontology.ontologyComputeFunctions") }}</span>
      <el-tag size="small" type="info" effect="plain">{{ list.length }}</el-tag>
      <el-button
        class="ont-sec__op"
        size="small"
        type="primary"
        :icon="Plus"
        @click="openFuncEdit()"
      >
        {{ i18nT("ai_ontology.newFunction") }}
      </el-button>
    </div>
    <el-alert
      type="info"
      :closable="false"
      class="ont-obj__note"
      :title="i18nT('ai_ontology.fnExposedHint')"
    />
    <el-table :data="list" size="small" border max-height="460" class="ont-fn__table" stripe>
      <template #empty>
        <el-empty
          :image-size="50"
          :description="i18nT('ai_ontology.noFunctionsClickNewFunctionAtTopRight')"
        />
      </template>
      <el-table-column
        prop="name"
        :label="i18nT('ai_ontology.functionName')"
        min-width="140"
        show-overflow-tooltip
      />
      <el-table-column
        prop="code"
        :label="i18nT('ai_ontology.code')"
        min-width="130"
        show-overflow-tooltip
      />
      <el-table-column :label="i18nT('ai_ontology.shape')" width="110">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ fnKindLabel(row.kind) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column
        prop="description"
        :label="i18nT('ai_ontology.description')"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column :label="i18nT('ai_ontology.operations')" width="200" align="center">
        <template #default="{ row }">
          <el-button icon="VideoPlay" link type="primary" size="small" @click="openFnRun(row)">
            {{ i18nT("ai_ontology.run") }}
          </el-button>
          <el-button icon="edit" link type="primary" size="small" @click="openFuncEdit(row)">
            {{ i18nT("ai_ontology.edit") }}
          </el-button>
          <el-button link type="danger" size="small" @click="removeFunc(row)">
            {{ i18nT("ai_ontology.delete") }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建 / 编辑函数 -->
    <el-dialog
      v-model="funcDialog"
      :title="i18nT('ai_ontology.ontologyComputeFunctions')"
      width="900px"
      append-to-body
    >
      <el-form :model="funcForm" label-width="140px">
        <el-form-item :label="i18nT('ai_ontology.functionName')" required>
          <el-input v-model="funcForm.name" :placeholder="i18nT('ai_ontology.fnNamePlaceholder')" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.code')" required>
          <el-input v-model="funcForm.code" placeholder="cam_online_rate" />
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.owningObjectType')" required>
          <el-tag size="small" type="primary" effect="dark">{{ objectLabel(props.code) }}</el-tag>
        </el-form-item>
        <el-form-item :label="i18nT('ai_ontology.functionShape')" required>
          <el-radio-group v-model="funcForm.kind">
            <el-radio-button v-for="k in FN_KINDS" :key="k.value" :value="k.value">
              {{ k.label }}
            </el-radio-button>
          </el-radio-group>
          <div class="ont-hint">{{ fnKindHint }}</div>
        </el-form-item>

        <el-form-item
          v-if="funcForm.kind === 'expression'"
          :label="i18nT('ai_ontology.expression')"
        >
          <el-input
            v-model="funcForm.expr"
            type="textarea"
            :rows="2"
            :placeholder="i18nT('ai_ontology.fnExprPlaceholder')"
          />
          <div class="ont-hint">
            {{ i18nT("ai_ontology.exprBuiltinsHint", { count: fnBuiltins.length }) }}
            <el-button
              :icon="showBuiltins ? 'ArrowUp' : 'View'"
              type="primary"
              link
              @click="showBuiltins = !showBuiltins"
            >
              {{ showBuiltins ? i18nT("ai_ontology.collapse") : i18nT("ai_ontology.viewBuiltins") }}
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

        <el-form-item :label="i18nT('ai_ontology.inputsJson')">
          <el-input
            v-model="funcForm.parametersText"
            type="textarea"
            :rows="5"
            :placeholder="fnParamsPlaceholder"
          />
          <div class="ont-hint">
            {{ i18nT("ai_ontology.paramsSourceHint") }}
          </div>
        </el-form-item>

        <el-form-item :label="i18nT('ai_ontology.outputsJson')">
          <el-input
            v-model="funcForm.outputsText"
            type="textarea"
            :rows="2"
            placeholder='[{"key":"rate","name":"在线率(%)","type":"number"}]'
          />
          <div class="ont-hint">{{ i18nT("ai_ontology.outputsHint") }}</div>
        </el-form-item>

        <el-form-item
          v-if="funcForm.kind !== 'expression'"
          :label="i18nT('ai_ontology.configJson')"
        >
          <el-input
            v-model="funcForm.configText"
            type="textarea"
            :rows="7"
            :placeholder="fnConfigPlaceholder"
          />
          <div class="ont-hint">{{ fnConfigHint }}</div>
        </el-form-item>

        <el-form-item :label="i18nT('ai_ontology.description')">
          <el-input v-model="funcForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="Tool description">
          <el-input
            v-model="funcForm.tool_description"
            type="textarea"
            :rows="2"
            :placeholder="i18nT('ai_ontology.fnToolDescriptionPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="funcDialog = false">{{ i18nT("ai_ontology.cancel") }}</el-button>
        <el-button v-hasPerm="'module_ai:ontology:edit'" :loading="fnChecking" @click="checkFunc">
          {{ i18nT("ai_ontology.validateDefinition") }}
        </el-button>
        <el-button type="primary" :loading="savingObj" @click="saveFunc">
          {{ i18nT("ai_ontology.save") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 函数运行 / 试运行 -->
    <el-dialog
      v-model="fnRunDialog"
      :title="i18nT('ai_ontology.runFunctionWritesNoData')"
      width="600px"
      append-to-body
    >
      <el-alert
        type="info"
        :closable="false"
        class="ont-note"
        :title="
          i18nT('ai_ontology.functionColonName', {
            name: fnRunTarget?.name || '',
            kind: fnKindLabel(fnRunTarget?.kind),
          })
        "
      />
      <el-form label-width="130px">
        <el-form-item v-if="fnRunNeedsObjectKey" :label="i18nT('ai_ontology.objectRowId')">
          <el-input
            v-model="fnRunForm.object_key"
            :placeholder="i18nT('ai_ontology.fnAggObjectKeyPlaceholder')"
          />
        </el-form-item>
        <el-form-item v-for="p in fnRunInputs" :key="p.key" :label="p.name || p.key">
          <el-input v-model="fnRunForm.args[p.key]" :placeholder="p.description || p.key" />
          <div v-if="p.required" class="ont-hint">{{ i18nT("ai_ontology.required") }}</div>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="fnRunInputs.some((p: any) => p.inferred)"
        type="info"
        :closable="false"
        class="ont-note"
        :title="i18nT('ai_ontology.fnInferredParamsHint')"
      />
      <el-button
        v-hasPerm="'module_ai:ontology:edit'"
        type="primary"
        :loading="fnRunning"
        @click="runFunc"
      >
        {{ i18nT("ai_ontology.run") }}
      </el-button>
      <template v-if="fnRunResult">
        <el-divider />
        <el-alert
          :type="fnRunResult.ok ? 'success' : 'error'"
          :closable="false"
          :title="
            fnRunResult.ok
              ? i18nT('ai_ontology.runSuccess')
              : fnRunResult.msg || i18nT('ai_ontology.executeFailed')
          "
        />
        <template v-if="fnRunResult.ok">
          <div class="ont-test__block">
            <div class="ont-sec__title">{{ i18nT("ai_ontology.returnValue") }}</div>
            <pre class="ont-run__out">{{ JSON.stringify(fnRunResult.value, null, 2) }}</pre>
          </div>
          <div class="ont-test__block">
            <div class="ont-sec__title">{{ i18nT("ai_ontology.actualInputs") }}</div>
            <pre class="ont-run__out">{{ JSON.stringify(fnRunResult.inputs, null, 2) }}</pre>
          </div>
        </template>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { checkOntFunction, getOntFunctionBuiltins, runOntFunction } from "@/api/module_ai/ontology";
import { useOntologyData } from "../composables/useOntologyData";

const { t: i18nT } = useI18n();

const props = defineProps<{ code: string }>();

const { functionsOf, stage, reloadAll, objectLabel } = useOntologyData();

const list = computed(() => functionsOf(props.code));

/* ---------------- 函数形态 ---------------- */
const FN_KINDS = [
  { value: "expression", label: i18nT("ai_ontology.expression") },
  { value: "aggregate", label: i18nT("ai_ontology.relatedAggregate") },
  { value: "http", label: i18nT("ai_ontology.externalService") },
  { value: "model", label: i18nT("ai_ontology.modelCall") },
];
function fnKindLabel(k: string) {
  return FN_KINDS.find((x) => x.value === k)?.label || k || i18nT("ai_ontology.expression");
}
const fnKindHint = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return i18nT("ai_ontology.fnKindAggregateHint");
    case "http":
      return i18nT("ai_ontology.fnKindHttpHint");
    case "model":
      return i18nT("ai_ontology.fnKindModelHint");
    default:
      return i18nT("ai_ontology.fnKindExprHint");
  }
});
const fnParamsPlaceholder = computed(() => {
  switch (funcForm.kind) {
    case "aggregate":
      return JSON.stringify([
        { key: "object_key", name: i18nT("ai_ontology.objectId"), type: "string", required: true },
      ]);
    case "http":
      return JSON.stringify([
        { key: "text", name: i18nT("ai_ontology.text"), type: "string", required: true },
      ]);
    case "model":
      return JSON.stringify([
        { key: "text", name: i18nT("ai_ontology.text"), type: "string", required: true },
      ]);
    default:
      return JSON.stringify([
        {
          key: "online_count",
          name: i18nT("ai_ontology.onlineCount"),
          type: "number",
          required: true,
          description: i18nT("ai_ontology.currentOnlineCameras"),
        },
      ]);
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
        {
          model_id: 1,
          system: i18nT("ai_ontology.youAreAConciseAssistant"),
          prompt: i18nT("ai_ontology.summarizePrompt"),
          temperature: 0.2,
        },
        null,
        2
      );
  }
});
const fnConfigHint = computed(() =>
  funcForm.kind === "aggregate"
    ? i18nT("ai_ontology.fnConfigHintAggregate")
    : funcForm.kind === "http"
      ? i18nT("ai_ontology.fnConfigHintHttp")
      : i18nT("ai_ontology.fnConfigHintModel")
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
    throw new Error(i18nT("ai_ontology.notValidJson", { label }));
  }
  if (!Array.isArray(v)) throw new Error(i18nT("ai_ontology.mustBeJsonArray", { label }));
  return v;
}

/** 解析弹窗里的三段 JSON，出错时返回 null */
function funcPayload(): Record<string, any> | null {
  let parameters: any[] = [];
  let outputs: any[] = [];
  let config: Record<string, any> = {};
  try {
    parameters = parseJsonList(funcForm.parametersText, i18nT("ai_ontology.inputs"));
    outputs = parseJsonList(funcForm.outputsText, i18nT("ai_ontology.outputs"));
    const raw = (funcForm.configText || "").trim();
    if (raw) {
      const v = JSON.parse(raw);
      if (typeof v !== "object" || Array.isArray(v))
        throw new Error(i18nT("ai_ontology.configMustBeJsonObject"));
      config = v;
    }
  } catch (e: any) {
    ElMessage.error(e.message || i18nT("ai_ontology.jsonParseFailed"));
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
  if (missing.length)
    errs.push(i18nT("ai_ontology.exprVarsNotDeclared", { vars: missing.join("、") }));
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
    if (!errs.length) ElMessage.success(i18nT("ai_ontology.definitionCorrect"));
    else
      ElMessageBox.alert(
        errs.map((e: string) => `· ${e}`).join("<br/>"),
        i18nT("ai_ontology.foundTheFollowingIssues"),
        {
          dangerouslyUseHTMLString: true,
        }
      );
  } finally {
    fnChecking.value = false;
  }
}

const savingObj = ref(false);
async function saveFunc() {
  if (!funcForm.code?.trim() || !funcForm.name?.trim() || !funcForm.object_code)
    return ElMessage.warning(i18nT("ai_ontology.pleaseEnterFunctionNameCodeAndOwningObjectType"));
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
    i18nT("ai_ontology.deleteFunctionConfirm", { name: f.name }),
    i18nT("ai_ontology.deleteFunction"),
    {
      type: "warning",
      confirmButtonText: i18nT("ai_ontology.delete2"),
      cancelButtonText: i18nT("ai_ontology.cancel"),
    }
  );
  await stage(
    "function",
    "delete",
    { id: f.id, code: f.code, name: f.name },
    i18nT("ai_ontology.deleteStaged")
  );
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
    ElMessage.error(e?.msg || i18nT("ai_ontology.runFailed"));
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
