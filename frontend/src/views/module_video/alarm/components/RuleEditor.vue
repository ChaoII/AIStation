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
          data-testid="rule-scope-select"
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
          data-testid="rule-camera-select"
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
          data-testid="rule-group-select"
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
          data-testid="rule-scene-select"
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
            :label="sceneOptionLabel(s)"
            :value="s.code"
            :title="s.configurable === false ? s.unsupported_reason || '' : ''"
            :disabled="s.configurable === false"
          />
        </el-select>
        <div v-if="sceneUnsupportedReason" class="rule-editor__field-error">
          <template v-if="currentScene?.blockers?.length">
            <div v-for="(blocker, i) in currentScene.blockers" :key="i">{{ blocker }}</div>
          </template>
          <template v-else>{{ sceneUnsupportedReason }}</template>
        </div>
        <!-- 可配置但需注意的运行期提示（如「人脸底库为空」），非阻断但需醒目 -->
        <div v-else-if="sceneHints.length" class="rule-editor__hint">
          <el-alert
            v-for="(hint, i) in sceneHints"
            :key="i"
            type="warning"
            :closable="false"
            show-icon
            :title="hint"
          />
        </div>
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

      <el-divider content-position="left">灰度</el-divider>

      <el-form-item label="生效时间段">
        <div class="schedule-grid-wrapper">
          <div class="schedule-header-row">
            <div class="schedule-corner" />
            <div v-for="h in 24" :key="h" class="schedule-header-cell">
              {{ String(h - 1).padStart(2, "0") }}
            </div>
          </div>
          <div v-for="day in 7" :key="day" class="schedule-row">
            <div class="schedule-day-label">{{ weekDays[day - 1] }}</div>
            <div
              v-for="hour in 24"
              :key="hour"
              class="schedule-cell"
              :class="{ active: scheduleGrid[day - 1]?.[hour - 1], disabled }"
              @mousedown.prevent="onCellMouseDown(day - 1, hour - 1, $event)"
              @mouseenter="onCellMouseEnter(day - 1, hour - 1)"
            />
          </div>
        </div>
        <div class="schedule-actions">
          <el-button size="small" :disabled="disabled" @click="fillSchedule(true)">全选</el-button>
          <el-button size="small" :disabled="disabled" @click="fillSchedule(false)">清空</el-button>
          <el-button size="small" :disabled="disabled" @click="fillWorkHours">
            工作日 08-18
          </el-button>
          <span class="rule-editor__hint">不选择任何时段 = 全天生效</span>
        </div>
      </el-form-item>

      <el-form-item label="灰度比例">
        <div class="rollout-percent">
          <el-slider
            data-testid="rule-rollout-percent"
            :model-value="rolloutPercent"
            :min="0"
            :max="100"
            :disabled="disabled"
            @update:model-value="(v: number | number[]) => updateRolloutPercent(Number(v))"
          />
          <span class="rollout-percent__value">{{ rolloutPercentText }}</span>
        </div>
      </el-form-item>

      <el-form-item label="相机白名单">
        <el-select
          data-testid="rule-rollout-whitelist"
          :model-value="rolloutWhitelist"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          :disabled="disabled"
          :loading="cameraLoading"
          placeholder="白名单相机始终生效（忽略比例）"
          style="width: 100%"
          @update:model-value="(v: number[]) => updateRolloutList('whitelist', v)"
        >
          <el-option v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="相机黑名单">
        <el-select
          data-testid="rule-rollout-blacklist"
          :model-value="rolloutBlacklist"
          multiple
          filterable
          clearable
          collapse-tags
          collapse-tags-tooltip
          :disabled="disabled"
          :loading="cameraLoading"
          placeholder="黑名单相机强制跳过"
          style="width: 100%"
          @update:model-value="(v: number[]) => updateRolloutList('blacklist', v)"
        >
          <el-option v-for="c in cameraOptions" :key="c.id" :label="c.name" :value="c.id" />
        </el-select>
        <div v-if="rolloutError" class="rule-editor__field-error">{{ rolloutError }}</div>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  getSceneCatalog,
  type SceneDefinition,
  type SceneParamSchema,
} from "@/api/module_video/scene";
import { getCameraList, getCameraGroupList } from "@/api/module_video/camera";
import type { AlarmRuleRollout, AlarmRuleSchedule, AlarmRuleScope } from "@/api/module_video/alarm";
import { cachedOptions, useLazyOptions } from "@/composables/useOptions";
import SceneParamsForm from "./SceneParamsForm.vue";
import ConditionTree from "./ConditionTree.vue";

/** 编辑器产物：作用域 + 目标 + 场景参数原值 + 条件树 + 灰度配置（后端编译后落库） */
export interface RuleEditorValue {
  /** 作用域：相机 / 相机组（camera_id 与 group_id 恰有其一） */
  scope: AlarmRuleScope;
  /** 相机作用域目标（scope=camera 时使用） */
  camera_id?: number;
  /** 相机组作用域目标（scope=group 时使用） */
  group_id?: number;
  params: Record<string, unknown>;
  conditions: Record<string, unknown> | null;
  /** 生效时间段（周计划 slots；null/空 = 全天） */
  schedule_json?: AlarmRuleSchedule | null;
  /** 灰度配置 {percent, whitelist, blacklist}；{} = 全量生效 */
  rollout?: AlarmRuleRollout;
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
    modelValue: () => ({
      scope: "camera",
      params: {},
      conditions: null,
      schedule_json: null,
      rollout: {},
    }),
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

const weekDays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
/** 拖选状态：mousedown 决定本次是「填充」还是「清除」 */
const gridDragState = ref<{ active: boolean; mode: "set" | "clear" }>({
  active: false,
  mode: "set",
});

/**
 * 生效时间段网格（7×24）由 schedule_json 派生，不保留本地副本，
 * 避免与父级 v-model 出现不同步（复用既有周计划数据结构 {type,slots:[{day,start,end}]}）。
 */
const scheduleGrid = computed<boolean[][]>(() => {
  const grid = Array.from({ length: 7 }, () => Array(24).fill(false));
  const slots = (props.modelValue?.schedule_json as AlarmRuleSchedule | null)?.slots;
  if (!Array.isArray(slots)) return grid;
  for (const slot of slots) {
    const day = Number(slot?.day);
    const start = Number(slot?.start);
    const end = Number(slot?.end);
    if (!Number.isInteger(day) || day < 0 || day > 6) continue;
    for (let h = Math.max(0, start); h < Math.min(24, end); h++) grid[day][h] = true;
  }
  return grid;
});

/** 网格 → schedule_json：连续小时合并为 slot，空网格回 null（= 全天） */
function gridToSchedule(grid: boolean[][]): AlarmRuleSchedule | null {
  const slots: Array<{ day: number; start: number; end: number }> = [];
  for (let d = 0; d < 7; d++) {
    let start = -1;
    for (let h = 0; h <= 24; h++) {
      const active = h < 24 && grid[d][h];
      if (active && start === -1) start = h;
      if (!active && start !== -1) {
        slots.push({ day: d, start, end: h });
        start = -1;
      }
    }
  }
  return slots.length ? { type: "weekly", slots } : null;
}

function commitSchedule(grid: boolean[][]) {
  emitPayload({ schedule_json: gridToSchedule(grid) });
}

function onCellMouseDown(day: number, hour: number, e: MouseEvent) {
  if (props.disabled || e.button !== 0) return;
  const grid = scheduleGrid.value.map((row) => row.slice());
  const current = grid[day][hour];
  gridDragState.value = { active: true, mode: current ? "clear" : "set" };
  grid[day][hour] = !current;
  commitSchedule(grid);
}

function onCellMouseEnter(day: number, hour: number) {
  if (!gridDragState.value.active) return;
  const grid = scheduleGrid.value.map((row) => row.slice());
  grid[day][hour] = gridDragState.value.mode === "set";
  commitSchedule(grid);
}

function onGridDragEnd() {
  gridDragState.value.active = false;
}

function fillSchedule(val: boolean) {
  commitSchedule(Array.from({ length: 7 }, () => Array(24).fill(val)));
}

function fillWorkHours() {
  const grid = Array.from({ length: 7 }, () => Array(24).fill(false));
  for (let d = 0; d < 5; d++) for (let h = 8; h < 18; h++) grid[d][h] = true;
  commitSchedule(grid);
}

// ---- 灰度比例 / 白黑名单 ----

/** 当前灰度配置（缺省 = 全量 + 空名单） */
const rollout = computed<AlarmRuleRollout>(() => props.modelValue?.rollout ?? {});
const rolloutPercent = computed(() => rollout.value.percent ?? 100);
const rolloutWhitelist = computed<number[]>(() => rollout.value.whitelist ?? []);
const rolloutBlacklist = computed<number[]>(() => rollout.value.blacklist ?? []);
const rolloutPercentText = computed(() => {
  if (rolloutPercent.value <= 0) return "0（不生效）";
  if (rolloutPercent.value >= 100) return "100（全量）";
  return `${rolloutPercent.value}%`;
});

/** 白黑名单交集（非空即非法，提交前拦截） */
const rolloutConflict = computed(() => {
  const white = new Set(rolloutWhitelist.value);
  return rolloutBlacklist.value.filter((id) => white.has(id));
});

const rolloutError = computed(() => {
  if (!rolloutConflict.value.length) return "";
  const names = rolloutConflict.value.map((id) => cameraName(id));
  return `白名单与黑名单冲突：${names.join("、")} 不能同时出现在两个名单中`;
});

function cameraName(id: number): string {
  const hit = (cameraOptions.value as any[]).find((c) => c.id === id);
  return hit?.name || `#${id}`;
}

/** 归一化灰度配置：去重正整数；全量且无名单时回 {}（保持「不设灰度」语义） */
function normalizeRollout(next: AlarmRuleRollout): AlarmRuleRollout {
  const clean = (arr?: number[]) => Array.from(new Set((arr ?? []).filter((x) => x > 0)));
  const percent = Math.min(100, Math.max(0, Math.round(next.percent ?? 100)));
  const whitelist = clean(next.whitelist);
  const blacklist = clean(next.blacklist);
  if (percent >= 100 && !whitelist.length && !blacklist.length) return {};
  return { percent, whitelist, blacklist };
}

function updateRolloutPercent(v: number) {
  emitPayload({ rollout: normalizeRollout({ ...rollout.value, percent: v }) });
}

function updateRolloutList(key: "whitelist" | "blacklist", ids: number[]) {
  emitPayload({ rollout: normalizeRollout({ ...rollout.value, [key]: ids }) });
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
    // 切到相机组：补齐组参数默认值（组叶子必填键依赖参数注入）
    emitPayload({
      scope,
      camera_id: undefined,
      group_id: groupId.value,
      params: { ...groupParamDefaults(), ...params.value },
    });
    ensureGroupOptions();
  } else {
    // 切回相机：剔除组作用域参数，并清理条件树中的组叶子
    const nextParams = { ...params.value };
    for (const key of groupParamKeys()) delete nextParams[key];
    emitPayload({
      scope,
      group_id: undefined,
      camera_id: cameraId.value,
      params: nextParams,
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

/** 场景下拉标签：不可配置时直接标注原因，避免「能看见却选不了」的困惑 */
function sceneOptionLabel(s: SceneDefinition): string {
  const base = `${s.name}（${s.code}）`;
  if (s.configurable === false) {
    return `${base} · 不可配置：${s.unsupported_reason || "求值器/模型族未就绪"}`;
  }
  if (s.edge_supported === false) return `${base} · 边缘未实现`;
  return base;
}

/** 当前场景不可配置的原因（编辑历史规则时可见；不可配置场景已在下拉中禁用） */
const sceneUnsupportedReason = computed(() => {
  const s = currentScene.value;
  return s && s.configurable === false ? s.unsupported_reason || "该场景暂不可配置" : "";
});

/** 当前场景的运行期提示（如「人脸底库为空」），仅可配置场景展示 */
const sceneHints = computed(() => currentScene.value?.hints ?? []);

/** 按作用域过滤参数 schema：未声明 scope 的为通用参数，声明 scope="group" 的仅在相机组作用域展示 */
function paramSchemaFor(def: SceneDefinition | null, scope: AlarmRuleScope): SceneParamSchema[] {
  return (def?.param_schema ?? []).filter((p) => !p.scope || p.scope === scope);
}

const schema = computed<SceneParamSchema[]>(() =>
  paramSchemaFor(currentScene.value, currentScope.value)
);
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
function buildParamDefaults(items: SceneParamSchema[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const item of items) {
    if (item.default !== undefined && item.default !== null) out[item.key] = item.default;
  }
  return out;
}

/** 当前场景声明的组作用域参数键（切回相机作用域时需清理，避免残留无效配置） */
function groupParamKeys(): string[] {
  return (currentScene.value?.param_schema ?? [])
    .filter((p) => p.scope === "group")
    .map((p) => p.key);
}

/** 组作用域参数默认值（切到相机组作用域时补齐，保证组叶子必填键可被编译层注入） */
function groupParamDefaults(): Record<string, unknown> {
  return buildParamDefaults(
    (currentScene.value?.param_schema ?? []).filter((p) => p.scope === "group")
  );
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
    params: buildParamDefaults(paramSchemaFor(def, currentScope.value)),
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
  // 灰度白/黑名单互斥：有交集则阻止提交（后端也会 400）
  if (rolloutError.value) {
    error.value = rolloutError.value;
    return false;
  }
  return true;
}

function isGeometry(type: string): boolean {
  return type === "polygon" || type === "polyline" || type === "point";
}

// 挂载时拉取场景目录 + 当前作用域的目标下拉；
// 灰度白/黑名单始终需要相机列表，故无论作用域都预加载相机选项。
// 若已带场景码（编辑态）且参数/条件为空，则回填默认规则
onMounted(async () => {
  if (currentScope.value === "group") ensureGroupOptions();
  ensureCameraOptions();
  document.addEventListener("mouseup", onGridDragEnd);
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
      params: buildParamDefaults(schema.value),
      conditions: currentScope.value === "camera" ? stripGroupLeaves(defaultRule) : defaultRule,
    });
  }
});

defineExpose({ validate });

onBeforeUnmount(() => {
  document.removeEventListener("mouseup", onGridDragEnd);
});
</script>

<style scoped>
.rule-editor__error {
  margin-bottom: 12px;
}

.rule-editor__hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.rule-editor__field-error {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-color-danger);
}

/* 生效时间段网格（与任务/录像计划保持同一交互与视觉） */
.schedule-grid-wrapper {
  padding-bottom: 4px;
  overflow-x: auto;
}
.schedule-header-row {
  display: flex;
  gap: 2px;
  margin-bottom: 2px;
}
.schedule-corner {
  flex-shrink: 0;
  width: 44px;
}
.schedule-header-cell {
  flex-shrink: 0;
  width: 24px;
  font-size: 10px;
  line-height: 20px;
  color: var(--el-text-color-placeholder);
  text-align: center;
}
.schedule-row {
  display: flex;
  gap: 2px;
  align-items: center;
  margin-bottom: 2px;
}
.schedule-day-label {
  flex-shrink: 0;
  width: 44px;
  padding-right: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: right;
}
.schedule-cell {
  flex-shrink: 0;
  width: 24px;
  height: 20px;
  cursor: pointer;
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 2px;
  transition: all 0.15s;
}
.schedule-cell:hover {
  border-color: var(--el-color-primary);
}
.schedule-cell.active {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}
.schedule-cell.disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.schedule-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 8px;
}

.rollout-percent {
  display: flex;
  flex: 1;
  gap: 12px;
  align-items: center;
  width: 100%;
}
.rollout-percent :deep(.el-slider) {
  flex: 1;
  min-width: 0;
}
.rollout-percent__value {
  flex-shrink: 0;
  min-width: 72px;
  font-size: 13px;
  color: var(--el-text-color-regular);
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
