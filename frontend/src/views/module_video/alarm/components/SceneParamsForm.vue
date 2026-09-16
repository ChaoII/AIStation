<template>
  <div class="scene-params-form">
    <el-empty v-if="!schema.length" :image-size="60" description="该场景暂无参数配置" />

    <template v-else>
      <el-form-item v-for="item in schema" :key="item.key" :label="labelOf(item)">
        <!-- 点列类：polygon/polyline/point 一律用 ROI 画布（point 按折线模式渲染单点） -->
        <RoiCanvas
          v-if="isGeometry(item.type)"
          :mode="item.type === 'polygon' ? 'polygon' : 'polyline'"
          :background="background"
          :disabled="disabled"
          :model-value="pointsOf(item.key)"
          @update:model-value="(v: number[][]) => setParam(item.key, v)"
        />

        <!-- 整数 / 浮点 -->
        <el-input-number
          v-else-if="item.type === 'int' || item.type === 'float'"
          :model-value="numberOf(item.key)"
          :min="0"
          :step="item.type === 'float' ? 0.1 : 1"
          :precision="item.type === 'float' ? 2 : 0"
          :disabled="disabled"
          style="width: 100%"
          @update:model-value="(v: number | undefined) => setParam(item.key, v)"
        />

        <!-- 布尔 -->
        <el-switch
          v-else-if="item.type === 'bool'"
          :model-value="Boolean(params[item.key])"
          :disabled="disabled"
          @update:model-value="(v: string | number | boolean) => setParam(item.key, v)"
        />

        <!-- 列表：多选 + allow-create（选项由 default 作初始项） -->
        <el-select
          v-else-if="item.type === 'list'"
          :model-value="listOf(item.key)"
          multiple
          filterable
          allow-create
          default-first-option
          :disabled="disabled"
          placeholder="请选择或输入后回车"
          style="width: 100%"
          @update:model-value="(v: unknown[]) => setParam(item.key, v)"
        >
          <el-option
            v-for="opt in optionsOf(item)"
            :key="String(opt)"
            :label="String(opt)"
            :value="opt"
          />
        </el-select>

        <!-- 字符串（兜底） -->
        <el-input
          v-else
          :model-value="stringOf(item.key)"
          :disabled="disabled"
          @update:model-value="(v: string) => setParam(item.key, v)"
        />
      </el-form-item>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { SceneParamSchema } from "@/api/module_video/scene";
import RoiCanvas from "./RoiCanvas.vue";

/**
 * 场景参数表单：按后端 `catalog.param_schema` 的 `type` 分派编辑器（spec §4.6）。
 * 只产 `params` 原值对象（0~1 归一化坐标由 RoiCanvas 保证），不参与条件树。
 */
const props = withDefaults(
  defineProps<{
    /** 参数 schema（来自场景目录） */
    schema: SceneParamSchema[];
    /** 参数原值对象（v-model） */
    modelValue?: Record<string, unknown>;
    /** 网格底图快照 URL（可选，透传给 RoiCanvas） */
    background?: string;
    disabled?: boolean;
  }>(),
  { modelValue: () => ({}), background: "", disabled: false }
);

const emit = defineEmits<{ "update:modelValue": [value: Record<string, unknown>] }>();

/** 参数原值（只读视图；写回通过 setParam 以新对象 emit） */
const params = computed(() => props.modelValue ?? {});

const isGeometry = (type: string) => type === "polygon" || type === "polyline" || type === "point";

function labelOf(item: SceneParamSchema): string {
  return item.label || item.key;
}

/** 列表选项：来自 schema default（数组），allow-create 负责追加自定义项 */
function optionsOf(item: SceneParamSchema): Array<string | number | boolean> {
  return Array.isArray(item.default) ? (item.default as Array<string | number | boolean>) : [];
}

function pointsOf(key: string): number[][] {
  const v = params.value[key];
  return Array.isArray(v) ? (v as number[][]) : [];
}

function listOf(key: string): unknown[] {
  const v = params.value[key];
  return Array.isArray(v) ? v : [];
}

function numberOf(key: string): number | undefined {
  const v = params.value[key];
  return typeof v === "number" ? v : undefined;
}

function stringOf(key: string): string {
  const v = params.value[key];
  return typeof v === "string" ? v : v === undefined || v === null ? "" : String(v);
}

/** 写回参数：空值（undefined/null/空串/空数组）视为“未配置”，删除该键以保留 default_rule 原值 */
function setParam(key: string, value: unknown) {
  const next: Record<string, unknown> = { ...params.value };
  const empty =
    value === undefined ||
    value === null ||
    (typeof value === "string" && value === "") ||
    (Array.isArray(value) && value.length === 0);
  if (empty) {
    delete next[key];
  } else {
    next[key] = value;
  }
  emit("update:modelValue", next);
}
</script>

<style scoped>
.scene-params-form {
  width: 100%;
}

.scene-params-form :deep(.roi-canvas) {
  width: 100%;
}

.scene-params-form :deep(.el-input-number),
.scene-params-form :deep(.el-select) {
  width: 100%;
}
</style>
