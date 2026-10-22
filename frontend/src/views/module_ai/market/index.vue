<!-- AI 能力市场：市场橱窗 / 我的资产 / 分享给我 / 审核中心 -->
<template>
  <div class="app-container ai-market-page">
    <!-- 白色面板：铺满可用区域，四周为蓝灰色边框；四个页签在其之上 -->
    <el-card shadow="never" class="market-shell" :body-style="{ padding: '0 16px 12px' }">
      <el-tabs v-model="activeTab" class="market-main-tabs">
        <el-tab-pane label="能力市场" name="browse">
          <MarketBrowse @go-configure="goConfigure" />
        </el-tab-pane>
        <el-tab-pane label="我的资产" name="mine">
          <MarketMine :target="mineTarget" @target-handled="mineTarget = null" />
        </el-tab-pane>
        <el-tab-pane label="分享给我" name="shared">
          <MarketShared />
        </el-tab-pane>
        <el-tab-pane v-if="canReview" label="审核中心" name="review">
          <MarketReview />
        </el-tab-pane>
      </el-tabs>
    </el-card>
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

/** 安装需密钥资产后，跳转到「我的资产」并指定要打开编辑的资产 */
const mineTarget = ref<{ asset_type: string; name: string } | null>(null);

function goConfigure(target: { asset_type: string; name: string }) {
  activeTab.value = "mine";
  mineTarget.value = target;
}

/** 审核中心仅对超管或持有 review 权限的用户可见 */
const canReview = computed(() => {
  const roles = userStore.basicInfo.roles?.map((r) => r.code) || [];
  return roles.includes(ROLE_ROOT) || userStore.prems.includes("module_ai:market:review");
});
</script>

<!--
  非 scoped 样式：全局 `.app-container` 为 flex column + height:100% + overflow:auto，
  若用 scoped 覆盖在 keep-alive/HMR 下曾出现 hash 不同步（项目已踩过），故用非 scoped + 唯一类名。
-->
<style lang="scss">
.app-container.ai-market-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 16px;
  box-sizing: border-box;
}

/* 白色面板：铺满剩余高度，蓝灰色边框 */
.ai-market-page .market-shell {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-light);
  border-radius: var(--el-border-radius-base);
}

.ai-market-page .market-shell > .el-card__body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 页签撑满面板，内容区独立滚动 */
.ai-market-page .market-main-tabs {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.ai-market-page .market-main-tabs > .el-tabs__header {
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.ai-market-page .market-main-tabs > .el-tabs__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}
</style>
