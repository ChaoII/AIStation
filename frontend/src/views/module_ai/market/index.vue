<!-- AI 能力市场：市场橱窗 / 我的资产 / 分享给我 / 审核中心 -->
<template>
  <div class="app-container ai-market-page">
    <el-tabs v-model="activeTab" class="market-main-tabs">
      <el-tab-pane label="能力市场" name="browse">
        <MarketBrowse />
      </el-tab-pane>
      <el-tab-pane label="我的资产" name="mine">
        <MarketMine />
      </el-tab-pane>
      <el-tab-pane label="分享给我" name="shared">
        <MarketShared />
      </el-tab-pane>
      <el-tab-pane v-if="canReview" label="审核中心" name="review">
        <MarketReview />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
  import { computed, ref } from "vue";

  import { ROLE_ROOT } from "@/constants";
  import { useUserStore } from "@/store";

  import MarketBrowse from "./components/MarketBrowse.vue";
  import MarketMine from "./components/MarketMine.vue";
  import MarketReview from "./components/MarketReview.vue";
  import MarketShared from "./components/MarketShared.vue";

  defineOptions({ name: "AiMarket" });

  const activeTab = ref("browse");
  const userStore = useUserStore();

  /** 审核中心仅对超管或持有 review 权限的用户可见 */
  const canReview = computed(() => {
    const roles = userStore.basicInfo.roles?.map((r) => r.code) || [];
    return roles.includes(ROLE_ROOT) || userStore.prems.includes("module_ai:market:review");
  });
</script>

<style lang="scss" scoped>
  .market-main-tabs {
    :deep(.el-tabs__header) {
      margin-bottom: 12px;
    }
  }
</style>
