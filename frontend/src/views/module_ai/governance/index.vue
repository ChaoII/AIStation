<!-- 治理：数据治理独立页（原「数据与集成」页面内嵌套的治理 tab 拆出） -->
<template>
  <div class="app-container ai-mod governance-page">
    <el-card shadow="never" class="gov-shell">
      <GovernancePanel />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import GovernancePanel from "./../integration/components/GovernancePanel.vue";

defineOptions({ name: "GovernancePage" });
</script>

<style lang="scss">
/* 非 scoped：避免 keep-alive / HMR 下 data-v 失效；对齐框架白面板外壳 */
.app-container.governance-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 16px;
  box-sizing: border-box;
}

.governance-page .gov-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.governance-page .gov-shell :deep(.el-card__body) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px;
}

/* 让 GovernancePanel 内部的 el-tabs 撑满并自身滚动 */
.governance-page .gov-shell .gp-wrap {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.governance-page .gov-shell .gp-wrap .el-tabs {
  flex: 1 1 auto;
  min-height: 0;
}

.governance-page .gov-shell .gp-wrap .el-tabs__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
</style>
