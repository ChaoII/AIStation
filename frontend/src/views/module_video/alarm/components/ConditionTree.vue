<template>
  <div class="condition-tree" :data-scene="sceneType || undefined">
    <!-- 历史一元 NOT：库只支持 AND/OR，此处只读展示，保存时原样保留 -->
    <el-alert
      v-if="notNodes.length"
      class="condition-tree__alert"
      type="warning"
      :closable="false"
      show-icon
      title="检测到历史一元 NOT 条件"
    >
      <div class="condition-tree__alert-tip">
        当前条件树只支持 AND/OR，NOT 节点不可编辑；保存时按原样保留：
      </div>
      <pre class="condition-tree__json">{{ stringify(notNodes) }}</pre>
    </el-alert>

    <!-- 叶子能力异步加载中 -->
    <div v-if="loading" class="condition-tree__loading">正在加载规则能力…</div>

    <!-- 条件树主体：第三方 FilterBuilder；必须由 Willow 提供 .wx-willow-theme 变量，否则无样式 -->
    <Willow v-else :fonts="false">
      <FilterBuilder :fields="fields" :options="options" :value="filterValue" :init="handleInit" />
    </Willow>

    <!-- 无法识别的条件叶子：只读提示（保存时不保留，后端也会拒绝） -->
    <div v-if="unsupportedLeaves.length" class="condition-tree__section">
      <div class="condition-tree__section-title">无法识别的条件（只读，保存时不保留）</div>
      <div class="condition-tree__tags">
        <el-tag
          v-for="(leaf, i) in unsupportedLeaves"
          :key="i"
          type="info"
          size="small"
          disable-transitions
        >
          {{ leaf.subject || "未知叶子" }}
        </el-tag>
      </div>
    </div>

    <!-- 未实现叶子：库不支持禁用单个字段，故不进 fields，仅置灰列出 -->
    <div v-if="unavailableLeaves.length" class="condition-tree__section">
      <div class="condition-tree__section-title">暂不支持的叶子</div>
      <div class="condition-tree__tags">
        <span
          v-for="leaf in unavailableLeaves"
          :key="leaf.subject"
          class="condition-tree__tag-pair"
        >
          <el-tag type="info" size="small" disable-transitions>{{ leaf.label }}</el-tag>
          <el-tag type="info" size="small" effect="plain" disable-transitions>未实现</el-tag>
        </span>
      </div>
    </div>

    <!-- 只读预览：便于核对将要保存的条件树 JSON -->
    <div class="condition-tree__section">
      <div class="condition-tree__section-title">条件 JSON 预览（只读）</div>
      <pre class="condition-tree__json">{{ preview }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  FilterBuilder,
  Willow,
  type IFilter,
  type IFilterSet,
  type IField,
  type TFilterType,
  type TType,
} from "@svar-ui/vue-filter";
import "@svar-ui/vue-filter/all.css";
import { getRuleCapabilities, type LeafCapability } from "@/api/module_video/scene";
import type { AlarmRuleScope } from "@/api/module_video/alarm";

/**
 * 条件树组件：封装 @svar-ui/vue-filter 的 FilterBuilder，按后端「叶子能力注册表」渲染字段，
 * 并在库的 IFilterSet 与后端条件树 JSON（{op:"and"|"or", children:[{subject,...}]}）之间双向转换。
 *
 * 能力限制（见 docs/superpowers/runbooks/sp5a-poc.md）：
 * - 库不支持自定义 value 编辑组件 → 叶子的 region/line/阈值/窗口等参数一律由参数区编辑，
 *   本组件只产出树内语义键（label/regex/contains/value/op）；
 * - 库不支持禁用单个 field → implemented:false 的叶子不进 fields，另置灰列出；
 * - 库算子由 field 的 type 推导，无法按叶子限制 → 经 OP_MAP 映射到项目算子，必要时回退。
 */

/** 后端条件树节点（叶子或逻辑分组） */
interface ConditionNode {
  op?: string;
  subject?: string;
  children?: ConditionNode[];
  [key: string]: unknown;
}

const props = withDefaults(
  defineProps<{
    /** 后端条件树 JSON（v-model 双向） */
    modelValue?: Record<string, unknown>;
    /** 场景码，仅作标识透出（能力集不随场景变化） */
    sceneType?: string;
    /** 规则作用域：相机作用域下隐藏跨相机聚合叶子（group_count/group_coverage） */
    scope?: AlarmRuleScope;
  }>(),
  { modelValue: () => ({}), sceneType: "", scope: "camera" }
);

const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();

/** 库的 filter id → 项目算子；e.g. greater→">"、equal→"=="、less→"<"（POC 实测 id） */
const OP_MAP: Record<string, string> = {
  greater: ">",
  more: ">",
  greaterOrEqual: ">=",
  less: "<",
  lower: "<",
  lessOrEqual: "<=",
  equal: "==",
  equals: "==",
  notEqual: "!=",
  contains: "contains",
  notContains: "not_contains",
  beginsWith: "starts_with",
  notBeginsWith: "not_starts_with",
  endsWith: "ends_with",
  notEndsWith: "not_ends_with",
  between: "between",
  notBetween: "not_between",
};

/** 项目算子 → 库 filter id（反解，优先使用库的实际 id） */
const OP_TO_LIB: Record<string, TFilterType> = {
  ">": "greater",
  gt: "greater",
  ">=": "greaterOrEqual",
  ge: "greaterOrEqual",
  "<": "less",
  lt: "less",
  "<=": "lessOrEqual",
  le: "lessOrEqual",
  "==": "equal",
  eq: "equal",
  "!=": "notEqual",
  ne: "notEqual",
  contains: "contains",
  not_contains: "notContains",
};

/** 数值语义（计数/阈值类）叶子：优先用 number 值编辑器 */
const NUMERIC_LEAVES = new Set(["count", "count_window", "dwell", "absence", "attribute"]);
/** 项目数值算子（用于按 ops 推断字段类型） */
const NUMERIC_PROJECT_OPS = new Set([
  ">",
  ">=",
  "<",
  "<=",
  "==",
  "!=",
  "gt",
  "ge",
  "lt",
  "le",
  "eq",
  "ne",
]);

/** 跨相机聚合叶子：仅相机组作用域可用，相机作用域下从 fields 与解析中剔除 */
const GROUP_LEAVES = new Set(["group_count", "group_coverage"]);

/** 叶子主取值键：库 field 的 value 落到该键上（其余参数由参数区编辑） */
const PRIMARY_VALUE_KEY: Record<string, string> = {
  object_present: "label",
  zone_enter: "label",
  line_cross: "label",
  text_match: "regex",
  ocr_label: "contains",
  attribute: "value",
  count: "value",
  count_window: "value",
  dwell: "min_sec",
  absence: "gap_sec",
};

const leaves = ref<LeafCapability[]>([]);
const loading = ref(true);
/** 叶子取值候选（库有 options 时值为复选列表）；能力接口未提供候选，故留空即文本/数值输入 */
const options = ref<Record<string, (number | string)[]>>({});
const filterValue = ref<IFilterSet>({ glue: "and", rules: [] });
/** 最近一次由库回写的条件树序列化值，用于打断「父级回填 → 重新初始化」回环 */
let lastEmitted = "";
/** 最近一次渲染使用的作用域：作用域切换时强制重建 filterValue（丢弃不可见叶子） */
let lastScope: AlarmRuleScope | null = null;

/** 当前作用域可见的叶子：相机作用域下组聚合叶子不可见（后端也不允许） */
const visibleLeaves = computed(() =>
  leaves.value.filter((l) => !(props.scope === "camera" && GROUP_LEAVES.has(l.subject)))
);
const leafMap = computed(() => new Map(visibleLeaves.value.map((l) => [l.subject, l])));
const implementedLeaves = computed(() => visibleLeaves.value.filter((l) => l.implemented));
const unavailableLeaves = computed(() => visibleLeaves.value.filter((l) => !l.implemented));

/** 每个已实现叶子一个 field，type 按取值语义选（计数/阈值为 number，其余 text） */
const fields = computed<IField[]>(() =>
  implementedLeaves.value.map((leaf) => ({
    id: leaf.subject,
    label: leaf.label || leaf.subject,
    type: fieldTypeOf(leaf),
  }))
);

const notNodes = computed(() => collectNotNodes(props.modelValue));
const unsupportedLeaves = computed(() => collectUnsupported(props.modelValue));
const preview = computed(() => stringify(props.modelValue));

function stringify(v: unknown): string {
  try {
    return JSON.stringify(v ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

/** 叶子取值类型：计数/阈值类或声明了数值算子的叶子为 number，其余 text */
function fieldTypeOf(leaf: LeafCapability): TType {
  if (NUMERIC_LEAVES.has(leaf.subject)) return "number";
  return leaf.ops.some((op) => NUMERIC_PROJECT_OPS.has(op)) ? "number" : "text";
}

function primaryKeyOf(leaf: LeafCapability): string {
  if (PRIMARY_VALUE_KEY[leaf.subject]) return PRIMARY_VALUE_KEY[leaf.subject];
  return leaf.params.some((p) => p.key === "label") ? "label" : "value";
}

function toNumber(v: unknown): number | string {
  if (v === undefined || v === null || v === "") return "";
  const n = Number(v);
  return Number.isFinite(n) ? n : String(v);
}

/** 项目算子 → 库 filter；缺省时按类型给默认算子 */
function filterFor(leaf: LeafCapability, op?: string): TFilterType {
  if (op && OP_TO_LIB[op]) return OP_TO_LIB[op];
  return fieldTypeOf(leaf) === "number" ? "greaterOrEqual" : "contains";
}

/** 库 filter → 项目算子；映射结果不在叶子声明集内时回退到首个声明算子（保证后端校验通过） */
function projectOpFor(leaf: LeafCapability, filter?: TFilterType): string {
  if (!leaf.ops.length) return "";
  const mapped = filter ? OP_MAP[filter] : undefined;
  if (mapped && leaf.ops.includes(mapped)) return mapped;
  return leaf.ops[0];
}

/** 后端条件树 → 库 IFilterSet（无法表达的一元 NOT 由只读区承载） */
function toFilterSet(tree: ConditionNode | undefined): IFilterSet {
  if (!tree || typeof tree !== "object") return { glue: "and", rules: [] };
  if (tree.op === "and" || tree.op === "or") {
    const rule = toFilterSetRule(tree);
    return (rule as IFilterSet) ?? { glue: "and", rules: [] };
  }
  if (tree.op === "not") return { glue: "and", rules: [] };
  const rule = toFilterSetRule(tree);
  return { glue: "and", rules: rule ? [rule] : [] };
}

function toFilterSetRule(node: ConditionNode | undefined): IFilter | IFilterSet | null {
  if (!node || typeof node !== "object") return null;
  if (node.op === "and" || node.op === "or") {
    const rules = (node.children ?? [])
      .map((c) => toFilterSetRule(c))
      .filter((r): r is IFilter | IFilterSet => !!r);
    return { glue: node.op, rules };
  }
  if (node.op === "not") return null;
  const subject = node.subject;
  const leaf = typeof subject === "string" ? leafMap.value.get(subject) : undefined;
  if (typeof subject !== "string" || !leaf || !leaf.implemented) return null;
  const type = fieldTypeOf(leaf);
  const key = primaryKeyOf(leaf);
  const raw = node[key];
  const value = type === "number" ? toNumber(raw) : ((raw as string) ?? "");
  return {
    field: subject,
    type,
    filter: filterFor(leaf, typeof node.op === "string" ? node.op : undefined),
    value,
    includes: [],
  } as IFilter;
}

/** 库 IFilterSet → 后端条件树（只产 AND/OR；历史 NOT 节点原样保留在根 children 末尾） */
function fromFilterSet(set: IFilterSet): Record<string, unknown> {
  const children = (set.rules ?? [])
    .map((r) => fromRule(r))
    .filter((r): r is Record<string, unknown> => !!r);
  return {
    op: set.glue === "or" ? "or" : "and",
    children: [...children, ...notNodes.value],
  };
}

function fromRule(rule: IFilter | IFilterSet): Record<string, unknown> | null {
  if (!rule || typeof rule !== "object") return null;
  if ("glue" in rule || "rules" in rule) {
    const children = (((rule as IFilterSet).rules ?? []) as (IFilter | IFilterSet)[])
      .map((r) => fromRule(r))
      .filter((r): r is Record<string, unknown> => !!r);
    if (!children.length) return null;
    return { op: (rule as IFilterSet).glue === "or" ? "or" : "and", children };
  }
  const f = rule as IFilter;
  const subject = f.field;
  if (typeof subject !== "string" || subject === "*") return null;
  const leaf = leafMap.value.get(subject);
  if (!leaf || !leaf.implemented) return null;
  const node: Record<string, unknown> = { subject };
  const key = primaryKeyOf(leaf);
  const raw = f.value;
  if (raw !== undefined && raw !== null && raw !== "") {
    node[key] = fieldTypeOf(leaf) === "number" ? toNumber(raw) : raw;
  }
  const op = projectOpFor(leaf, f.filter);
  if (op) node.op = op;
  return node;
}

/** 递归收集一元 NOT 节点（历史数据，只读展示并保留） */
function collectNotNodes(tree: unknown, out: ConditionNode[] = []): ConditionNode[] {
  if (!tree || typeof tree !== "object") return out;
  const node = tree as ConditionNode;
  if (node.op === "not") {
    out.push(node);
    return out;
  }
  if (Array.isArray(node.children)) node.children.forEach((c) => collectNotNodes(c, out));
  return out;
}

/** 递归收集无法识别/未实现的叶子（只读展示，保存时不保留） */
function collectUnsupported(tree: unknown, out: ConditionNode[] = []): ConditionNode[] {
  if (!tree || typeof tree !== "object") return out;
  if (!leafMap.value.size) return out;
  const node = tree as ConditionNode;
  if (node.op === "not") return out;
  if (node.op === "and" || node.op === "or") {
    (node.children ?? []).forEach((c) => collectUnsupported(c, out));
    return out;
  }
  const leaf = typeof node.subject === "string" ? leafMap.value.get(node.subject) : undefined;
  if (!leaf || !leaf.implemented) out.push(node);
  return out;
}

function handleInit(api: {
  on: (action: string, cb: (ev: { value: IFilterSet }) => void) => void;
}) {
  api.on("change", (ev) => {
    const tree = fromFilterSet(ev.value);
    lastEmitted = stringify(tree);
    emit("update:modelValue", tree);
  });
}

/** 外部条件树（含能力集/作用域变化）→ 重建库的 IFilterSet；能力未就绪时先不转换，避免叶子全被判为未知 */
watch(
  [() => props.modelValue, leaves, () => props.scope],
  () => {
    const tree = props.modelValue as ConditionNode;
    if (!leaves.value.length && Object.keys(tree ?? {}).length) return;
    const scopeChanged = props.scope !== lastScope;
    lastScope = props.scope;
    if (!scopeChanged && stringify(tree) === lastEmitted) return;
    filterValue.value = toFilterSet(tree);
  },
  { immediate: true, deep: true }
);

onMounted(async () => {
  try {
    const res = await getRuleCapabilities();
    leaves.value = res.data.data?.leaves ?? [];
  } catch {
    // 请求失败已由全局拦截器提示，此处保持空能力（fields 为空）
  } finally {
    loading.value = false;
  }
});
</script>

<!-- 主题对齐：FilterBuilder 的 .wx-willow-theme 变量定义在同名元素上，
     必须用更高优先级选择器覆盖，并映射到 Element Plus 的 --el-* 变量，避免观感割裂 -->
<style lang="scss">
.condition-tree {
  .wx-theme {
    --wx-color-primary: var(--el-color-primary);
    --wx-color-primary-font: var(--el-color-white);
    --wx-color-font: var(--el-text-color-primary);
    --wx-color-font-alt: var(--el-text-color-regular);
    --wx-color-disabled: var(--el-text-color-disabled);
    --wx-color-link: var(--el-color-primary);
    --wx-font-family: var(--el-font-family, inherit);
    --wx-font-size: var(--el-font-size-base);
    --wx-border-color: var(--el-border-color);
    --wx-border-radius: var(--el-border-radius-base);
    --wx-background: var(--el-bg-color);
    --wx-background-hover: var(--el-fill-color-light);
    --wx-input-height: var(--el-component-size);
    --wx-input-border: 1px solid var(--el-border-color);
    --wx-input-border-focus: var(--el-color-primary);
    --wx-input-border-radius: var(--el-border-radius-base);
    --wx-input-background: var(--el-fill-color-blank);
    --wx-input-font-color: var(--el-text-color-regular);
    --wx-input-font-size: var(--el-font-size-base);
    --wx-input-placeholder-color: var(--el-text-color-placeholder);
    --wx-button-height: var(--el-component-size);
    --wx-button-border-radius: var(--el-border-radius-base);
    --wx-button-background: var(--el-color-primary);
    --wx-button-font-color: var(--el-color-white);
    --wx-button-font-size: var(--el-font-size-base);
    --wx-popup-background: var(--el-bg-color-overlay);
    --wx-popup-border: 1px solid var(--el-border-color-light);
    --wx-popup-border-radius: var(--el-border-radius-base);
    --wx-popup-shadow: var(--el-box-shadow-light);
    --wx-box-shadow: var(--el-box-shadow-light);
  }
}

/* 缺陷修复：第三方弹层（字段下拉）默认 --wx-popup-z-index:1001，低于 el-dialog，
   且选项较多时末项超出视口、鼠标点击被对话框内容拦截。实测该弹层未必渲染在
   `.condition-tree` 子树内（会挂到 theme 子树），故用非 scoped 全局选择器直接锁定
   `.wx-popup` 提升层级并限高滚动，保证所有候选项均可鼠标点击。 */
.wx-willow-theme {
  --wx-popup-z-index: 3000;
}

.wx-popup {
  z-index: 3000 !important;
  max-height: 60vh;
  overflow-y: auto !important;
}

.condition-tree__alert {
  margin-bottom: 12px;
}

.condition-tree__alert-tip {
  margin-bottom: 4px;
}

.condition-tree__loading {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.condition-tree__section {
  margin-top: 12px;
}

.condition-tree__section-title {
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.condition-tree__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.condition-tree__tag-pair {
  display: inline-flex;
  gap: 2px;
  align-items: center;
}

.condition-tree__json {
  max-height: 200px;
  padding: 8px;
  margin: 0;
  overflow: auto;
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: var(--el-border-radius-base);
}
</style>
