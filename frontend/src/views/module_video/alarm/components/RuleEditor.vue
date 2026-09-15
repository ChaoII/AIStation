<template>
  <div class="rule-editor">
    <el-alert
      v-if="error"
      class="rule-editor__error"
      type="error"
      :closable="false"
      show-icon
      :title="error"
    />

    <!-- @submit.prevent：条件树里的第三方 FilterBuilder 使用原生 <button>（无 type），
         处在 el-form 的 <form> 内点击时会触发原生表单提交并刷新页面（丢失对话框内容），
         故在最内层表单上拦截 submit 事件（事件在 form 上触发并向祖先冒泡）。 -->
    <el-form label-width="100px" size="default" @submit.prevent>
      <el-form-item label="业务场景" required>
        <el-select
          :model-value="sceneType || ''"
          filterable
          clearable
          :loading="loadingScenes"
          :disabled="disabled"
          placeholder="请选择业务场景"
          style="width: 100%"
          @update:model-value="(v: string) => handleSceneChange(v || '')"
        >
          <el-option
            v-for="s in scenes"
            :key="s.code"
            :label="`${s.name}（${s.code}）`"
            :value="s.code"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="场景参数">
        <SceneParamsForm
          v-if="schema.length"
          :schema="schema"
          :background="background"
          :disabled="disabled"
          :model-value="params"
          @update:model-value="updateParams"
        />
        <div v-else class="rule-editor__hint">请先选择业务场景</div>
      </el-form-item>

      <el-form-item label="触发条件">
        <ConditionTree
          :model-value="conditions ?? {}"
          :scene-type="sceneType"
          @update:model-value="updateConditions"
        />
      </el-form-item>

      <el-form-item label="条件预览">
        <pre class="rule-editor__preview">{{ preview }}</pre>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  getSceneCatalog,
  type SceneDefinition,
  type SceneParamSchema,
} from "@/api/module_video/scene";
import SceneParamsForm from "./SceneParamsForm.vue";
import ConditionTree from "./ConditionTree.vue";

/** 编辑器产物：场景参数原值 + 条件树（后端编译后落库） */
export interface RuleEditorValue {
  params: Record<string, unknown>;
  conditions: Record<string, unknown> | null;
}

const props = withDefaults(
  defineProps<{
    /** 场景码（v-model:scene-type） */
    sceneType?: string;
    /** { params, conditions }（v-model） */
    modelValue?: RuleEditorValue;
    /** 网格底图快照 URL（可选） */
    background?: string;
    disabled?: boolean;
  }>(),
  {
    sceneType: "",
    modelValue: () => ({ params: {}, conditions: null }),
    background: "",
    disabled: false,
  }
);

const emit = defineEmits<{
  "update:modelValue": [value: RuleEditorValue];
  "update:sceneType": [value: string];
}>();

const scenes = ref<SceneDefinition[]>([]);
const loadingScenes = ref(false);
/** 校验错误信息（validate() 填充，展示在顶部 alert） */
const error = ref("");

const params = computed<Record<string, unknown>>(() => props.modelValue?.params ?? {});
const conditions = computed<Record<string, unknown> | null>(
  () => props.modelValue?.conditions ?? null
);

const currentScene = computed(() => scenes.value.find((s) => s.code === props.sceneType) ?? null);
const schema = computed<SceneParamSchema[]>(() => currentScene.value?.param_schema ?? []);
const preview = computed(() => {
  try {
    return JSON.stringify(conditions.value ?? {}, null, 2);
  } catch {
    return "{}";
  }
});

/** 条件树是否为空（空对象 / 空 and-or 分组视为未配置） */
function isEmptyTree(tree: Record<string, unknown> | null): boolean {
  if (!tree || !Object.keys(tree).length) return true;
  const kids = (tree as { children?: unknown }).children;
  return Array.isArray(kids) && kids.length === 0;
}

/** 是否已配置场景相关数据（用于决定“是否必须选场景”） */
function hasSceneData(): boolean {
  return Object.keys(params.value).length > 0 || !isEmptyTree(conditions.value);
}

function updateParams(value: Record<string, unknown>) {
  emit("update:modelValue", { params: value, conditions: conditions.value });
}

function updateConditions(value: Record<string, unknown>) {
  emit("update:modelValue", { params: params.value, conditions: value });
}

/** 参数初值：取 schema 中显式声明的 default（含 list 默认项），几何类无默认则不注入 */
function buildParamDefaults(def: SceneDefinition | null): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const item of def?.param_schema ?? []) {
    if (item.default !== undefined && item.default !== null) out[item.key] = item.default;
  }
  return out;
}

function cloneTree<T>(value: T): T {
  return value === undefined || value === null ? value : JSON.parse(JSON.stringify(value));
}

/** 用户显式切换场景：重置参数与条件为场景默认（default_rule） */
function handleSceneChange(code: string) {
  error.value = "";
  emit("update:sceneType", code);
  const def = scenes.value.find((s) => s.code === code) ?? null;
  emit("update:modelValue", {
    params: buildParamDefaults(def),
    conditions: (cloneTree(def?.default_rule) as Record<string, unknown>) ?? null,
  });
}

/** 校验：已配置数据时必须选场景；已绘制的点列需满足最小点数 */
function validate(): boolean {
  error.value = "";
  if (!props.sceneType && hasSceneData()) {
    error.value = "已配置场景参数或触发条件，请先选择业务场景";
    return false;
  }
  for (const item of schema.value) {
    if (!isGeometry(item.type)) continue;
    const pts = params.value[item.key];
    if (pts === undefined) continue;
    const need = item.type === "polygon" ? 3 : 2;
    if (!Array.isArray(pts) || pts.length < need) {
      error.value = `请完善「${item.label || item.key}」（至少 ${need} 个点）`;
      return false;
    }
  }
  return true;
}

function isGeometry(type: string): boolean {
  return type === "polygon" || type === "polyline" || type === "point";
}

// 挂载时拉取场景目录；若已带场景码（编辑态）且参数/条件为空，则回填默认规则
onMounted(async () => {
  loadingScenes.value = true;
  try {
    const res = await getSceneCatalog();
    scenes.value = (res.data?.data?.items ?? []) as SceneDefinition[];
  } catch {
    // 请求失败已由全局拦截器提示，保持空目录
  } finally {
    loadingScenes.value = false;
  }
  if (!props.sceneType) return;
  const def = currentScene.value;
  if (!def) return;
  if (Object.keys(params.value).length === 0 && isEmptyTree(conditions.value)) {
    emit("update:modelValue", {
      params: buildParamDefaults(def),
      conditions: (cloneTree(def.default_rule) as Record<string, unknown>) ?? null,
    });
  }
});

defineExpose({ validate });
</script>

<style scoped>
.rule-editor__error {
  margin-bottom: 12px;
}

.rule-editor__hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.rule-editor__preview {
  max-height: 200px;
  padding: 8px;
  margin: 0;
  overflow: auto;
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
}
</style>
