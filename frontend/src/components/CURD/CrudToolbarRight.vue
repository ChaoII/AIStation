<!-- PageContent 右侧圆形工具条：与业务页 #toolbar 中重复的 v-for 逻辑一致，含 Tooltip / 列筛选 -->
<template>
  <slot name="prepend" />
  <template v-for="(btn, index) in buttons" :key="index">
    <el-popover v-if="btn.name === 'filter'" placement="bottom" trigger="click">
      <template #reference>
        <el-button v-bind="btn.attrs" />
      </template>
      <el-scrollbar max-height="350px">
        <template v-for="c in cols" :key="c.prop">
          <el-checkbox v-if="c.prop" v-model="c.show" :label="c.label" />
        </template>
      </el-scrollbar>
    </el-popover>
    <el-tooltip v-else-if="tooltipContent(btn.name)" :content="tooltipContent(btn.name)!">
      <el-button v-hasPerm="btn.perm ?? '*:*:*'" v-bind="btn.attrs" @click="onToolbar(btn.name)" />
    </el-tooltip>
    <el-button
      v-else
      v-hasPerm="btn.perm ?? '*:*:*'"
      v-bind="btn.attrs"
      @click="onToolbar(btn.name)"
    />
  </template>
</template>

<script setup lang="ts">
import type { ButtonProps } from "element-plus";
import type { CSSProperties } from "vue";
import { useI18n } from "vue-i18n";

const { t } = useI18n();

/** 与 PageContent createToolbar 产出的右侧按钮结构一致 */
export type CrudToolbarRightButton = {
  name: string;
  text?: string;
  attrs?: Partial<ButtonProps> & { style?: CSSProperties };
  perm?: string | string[] | null;
};

defineProps<{
  buttons: CrudToolbarRightButton[];
  cols: Array<{ prop?: string; label?: string; show?: boolean }>;
  onToolbar: (name: string) => void;
}>();

const TOOLTIP_KEYS: Record<string, string> = {
  import: "common.import",
  export: "common.export",
  filter: "common.filter",
  refresh: "common.refresh",
};

function tooltipContent(name: string): string | undefined {
  const k = TOOLTIP_KEYS[name];
  return k ? t(k) : undefined;
}
</script>
