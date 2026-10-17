<!-- 治理（Governance / Oversight）——功能已并入「数据与集成」页签；此页面保留为薄壳（复用 GovernancePanel），未挂独立菜单。 -->
<template>
  <div class="app-container ai-mod ai-governance-page">
    <GovernancePanel />
  </div>
</template>

<script setup lang="ts">
import GovernancePanel from "@/views/module_ai/integration/components/GovernancePanel.vue";

defineOptions({ name: "AiGovernance" });
</script>

<style scoped lang="scss">
.ai-governance-page {
  padding: 12px;
}
</style>
