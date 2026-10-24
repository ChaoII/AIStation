<template>
  <el-collapse class="gencode-help-collapse mb-4" accordion>
    <el-collapse-item name="rules">
      <template #title>
        <span class="gencode-help-collapse__title">
          <el-icon class="gencode-help-collapse__icon"><InfoFilled /></el-icon>
          {{ t("generator.helpCollapseTitle") }}
        </span>
      </template>
      <el-table stripe :data="rows" border size="small" class="gencode-rules-table">
        <el-table-column prop="parent" :label="t('generator.colParent')" min-width="88" />
        <el-table-column prop="sidebar" :label="t('generator.colSidebar')" min-width="200" />
        <el-table-column prop="page" :label="t('generator.colPage')" min-width="160" />
        <el-table-column prop="api" :label="t('generator.colApi')" min-width="160" />
      </el-table>
      <p class="gencode-help-footnote" v-html="t('generator.helpFootnote')"></p>
    </el-collapse-item>
  </el-collapse>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { InfoFilled } from "@element-plus/icons-vue";

defineOptions({ name: "GencodeHelpPanel" });

const { t } = useI18n();

const rows = [
  {
    parent: t("generator.rowSelectedParent"),
    sidebar: t("generator.rowSidebarSelected"),
    page: t("generator.rowPageSelected"),
    api: t("generator.rowApi"),
  },
  {
    parent: t("generator.rowUnselectedParent"),
    sidebar: t("generator.rowSidebarUnselected"),
    page: t("generator.rowPageUnselected"),
    api: t("generator.rowApi"),
  },
];
</script>

<style scoped lang="scss">
.gencode-help-collapse {
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--el-border-radius-base);
}

.gencode-help-collapse :deep(.el-collapse-item__header) {
  padding: 8px 12px;
  font-size: var(--el-font-size-small);
  font-weight: 500;
  background: var(--el-fill-color-light);
}

.gencode-help-collapse :deep(.el-collapse-item__wrap) {
  border-top: 1px solid var(--el-border-color-lighter);
}

.gencode-help-collapse :deep(.el-collapse-item__content) {
  padding: 10px 12px 12px;
}

.gencode-help-collapse__title {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.gencode-help-collapse__icon {
  flex-shrink: 0;
}

.gencode-rules-table :deep(.el-table__cell) {
  font-size: 12px;
}

.gencode-help-footnote {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--el-text-color-secondary);
}

.gencode-help-footnote code {
  padding: 0 4px;
  font-size: 11px;
  background: var(--el-fill-color);
  border-radius: 3px;
}
</style>
