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
      <el-form-item label="作用域" required>
        <el-radio-group
          :model-value="currentScope"
          :disabled="disabled"
          @update:model-value="handleScopeChange"
        >
          <el-radio value="camera">相机</el-radio>
          <el-radio value="group">相机组</el-radio>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="currentScope === 'camera'" label="关联摄像机" required>
        <el-select
          :model-value="cameraId"
          filterable
          clearable
          :disabled="disabled"
          :loading="cameraLoading"
          placeholder="请选择摄像机"
          style="width: 100%"
          @update:model-value="handleCameraChange"
        >
          <el-option v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </el-form-item>

      <el-form-item v-else label="关联相机组" required>
        <el-select
          :model-value="groupId"
          filterable
          clearable
          :disabled="disabled"
          :loading="groupLoading"
          placeholder="请选择相机组（组规则对该组内全部相机生效）"
          style="width: 100%"
          @update:model-value="handleGroupChange"
        >
          <el-option v-for="g in groupOptions" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
      </el-form-item>

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
          :scope="currentScope"
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
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import type { AlarmRuleScope } from "@/api/module_video/alarm";
import { cachedOptions, useLazyOptions } from "@/composables/useOptions";
import SceneParamsForm from "./SceneParamsForm.vue";
import ConditionTree from "./ConditionTree.vue";

/** 编辑器产物：作用域 + 目标 + 场景参数原值 + 条件树（后端编译后落库） */
export interface RuleEditorValue {
  /** 作用域：相机 / 相机组（camera_id 与 group_id 恰有其一） */
  scope: AlarmRuleScope;
  /** 相机作用域目标（scope=camera 时使用） */
  camera_id?: number;
  /** 相机组作用域目标（scope=group 时使用） */
  group_id?: number;
  params: Record<string, unknown>;
  conditions: Record<string, unknown> | null;
}

/** 跨相机聚合叶子：相机作用域禁用（后端编译层拒绝），切换作用域时清理 */
const GROUP_LEAVES = new Set(["group_count", "group_coverage"]);

const props = withDefaults(
  defineProps<{
    /** 场景码（v-model:scene-type） */
    sceneType?: string;
    /** { scope, camera_id, group_id, params, conditions }（v-model） */
    modelValue?: RuleEditorValue;
    /** 网格底图快照 URL（可选） */
    background?: string;
    disabled?: boolean;
  }>(),
  {
    sceneType: "",
    modelValue: () => ({ scope: "camera", params: {}, conditions: null }),
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
/** 当前作用域（缺省按相机，兼容旧数据） */
const currentScope = computed<AlarmRuleScope>(() =>
  props.modelValue?.scope === "group" ? "group" : "camera"
);
const cameraId = computed(() => props.modelValue?.camera_id);
const groupId = computed(() => props.modelValue?.group_id);

// 相机 / 相机组下拉：懒加载 + 缓存（与告警列表共用缓存键，避免重复请求）
const {
  options: cameraOptions,
  loading: cameraLoading,
  ensure: ensureCameraOptions,
} = useLazyOptions(() =>
  cachedOptions(
    "video:cameras",
    async () => (await getCameraList({ page_size: 100 })).data?.data?.items || []
  )
);
const {
  options: groupOptions,
  loading: groupLoading,
  ensure: ensureGroupOptions,
} = useLazyOptions(() =>
  cachedOptions("video:cameraGroups", async () =>
    flattenTree((await getCameraGroupList()).data?.data || [])
  )
);

/** 相机组为树结构，下拉需要扁平化（保留全部层级节点） */
function flattenTree(nodes: any[], out: any[] = []): any[] {
  for (const node of nodes || []) {
    if (node?.id !== undefined) out.push({ id: node.id, name: node.name });
    if (Array.isArray(node?.children)) flattenTree(node.children, out);
  }
  return out;
}

/** 合并当前载荷并回写（避免丢失未修改字段） */
function emitPayload(patch: Partial<RuleEditorValue>) {
  const base: RuleEditorValue = props.modelValue ?? {
    scope: "camera",
    params: {},
    conditions: null,
  };
  emit("update:modelValue", { ...base, ...patch });
}

/** 递归剔除组聚合叶子（相机作用域不允许，后端会 400） */
function stripGroupLeaves(tree: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!tree || typeof tree !== "object") return tree;
  const node: Record<string, unknown> = { ...tree };
  if (Array.isArray(node.children)) {
    node.children = (node.children as Record<string, unknown>[])
      .filter((c) => !(typeof c?.subject === "string" && GROUP_LEAVES.has(c.subject)))
      .map((c) => stripGroupLeaves(c) as Record<string, unknown>);
  }
  return node;
}

/** 切换作用域：清空另一作用域的 id，避免同时携带 camera_id 与 group_id */
function handleScopeChange(next: string | number | boolean | undefined) {
  const scope: AlarmRuleScope = next === "group" ? "group" : "camera";
  if (scope === currentScope.value) return;
  error.value = "";
  if (scope === "group") {
    emitPayload({ scope, camera_id: undefined, group_id: groupId.value });
    ensureGroupOptions();
  } else {
    emitPayload({
      scope,
      group_id: undefined,
      camera_id: cameraId.value,
      conditions: stripGroupLeaves(conditions.value),
    });
    ensureCameraOptions();
  }
}

function handleCameraChange(v: number | undefined) {
  emitPayload({ camera_id: v ?? undefined });
}

function handleGroupChange(v: number | undefined) {
  emitPayload({ group_id: v ?? undefined });
}

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
  emitPayload({ params: value });
}

function updateConditions(value: Record<string, unknown>) {
  emitPayload({ conditions: value });
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
  const defaultRule = (cloneTree(def?.default_rule) as Record<string, unknown>) ?? null;
  emitPayload({
    params: buildParamDefaults(def),
    conditions: currentScope.value === "camera" ? stripGroupLeaves(defaultRule) : defaultRule,
  });
}

/** 校验：作用域目标必填 + 已配置数据时必须选场景 + 已绘制的点列需满足最小点数 */
function validate(): boolean {
  error.value = "";
  if (currentScope.value === "camera" && cameraId.value === undefined) {
    error.value = "请选择关联摄像机";
    return false;
  }
  if (currentScope.value === "group" && groupId.value === undefined) {
    error.value = "请选择关联相机组";
    return false;
  }
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

// 挂载时拉取场景目录 + 当前作用域的目标下拉；
// 若已带场景码（编辑态）且参数/条件为空，则回填默认规则
onMounted(async () => {
  if (currentScope.value === "group") ensureGroupOptions();
  else ensureCameraOptions();
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
    const defaultRule = (cloneTree(def.default_rule) as Record<string, unknown>) ?? null;
    emitPayload({
      params: buildParamDefaults(def),
      conditions: currentScope.value === "camera" ? stripGroupLeaves(defaultRule) : defaultRule,
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
