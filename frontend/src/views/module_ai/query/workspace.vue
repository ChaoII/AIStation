<template>
  <div class="app-container ai-query-workspace">
    <el-tabs v-model="tab" type="border-card" class="aqw-tabs">
      <el-tab-pane label="数据与集成" name="integration" lazy>
        <IntegrationPage />
      </el-tab-pane>
      <el-tab-pane label="智能问数" name="ask" lazy>
        <QueryPage />
      </el-tab-pane>
      <el-tab-pane label="问数评测" name="eval" lazy>
        <EvalPage />
      </el-tab-pane>
      <el-tab-pane label="自定义报表" name="reports" lazy>
        <ReportsPage />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import IntegrationPage from "../integration/index.vue";
import QueryPage from "./index.vue";
import EvalPage from "../eval/index.vue";
import ReportsPage from "./reports.vue";

defineOptions({ name: "AiQuery" });

const router = useRouter();
const route = useRoute();

const VALID_TABS = ["integration", "ask", "eval", "reports"] as const;
type TabValue = (typeof VALID_TABS)[number];

function normalizeTab(v: unknown): TabValue {
  const s = String(v ?? "");
  return (VALID_TABS as readonly string[]).includes(s) ? (s as TabValue) : "ask";
}

// 初始值直接从路由同步：深链 ?tab=integration 时首帧就渲染对应页签，避免先闪「智能问数」
const tab = ref<TabValue>(normalizeTab(route.query.tab));

/** 地址栏 → 页签状态（含从旧地址重定向带来的 tab 参数）。 */
function syncTabFromRoute() {
  const t = normalizeTab(route.query.tab);
  if (t !== tab.value) {
    tab.value = t;
  }
}

/** 页签状态 → 地址栏（保留其它 query 参数，如 object_code/object_key）。 */
function syncTabToRoute(v: TabValue) {
  const q = { ...(route.query || {}) } as Record<string, any>;
  if (q.tab === v) return;
  q.tab = v;
  router.replace({ path: "/ai/query", query: q });
}

watch(tab, (v) => syncTabToRoute(v));
watch(
  () => route.query.tab,
  () => syncTabFromRoute()
);

onMounted(() => {
  syncTabFromRoute();
  // 缺省/非法 tab 时回写 URL，保证地址栏恒有合法 tab
  const q = { ...(route.query || {}) } as Record<string, any>;
  if (q.tab !== tab.value) {
    q.tab = tab.value;
    router.replace({ path: "/ai/query", query: q });
  }
});
</script>

<style lang="scss">
/* 非 scoped + 唯一类：避免与全局 .app-container 的 flex 规则冲突（见训练详情页教训） */
.app-container.ai-query-workspace {
  overflow: hidden;

  .aqw-tabs {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;

    .el-tabs__header {
      margin-bottom: 0;
      flex-shrink: 0;
    }

    .el-tabs__content {
      flex: 1;
      min-height: 0;
      overflow: hidden;
    }

    .el-tab-pane {
      height: 100%;
      overflow: hidden;
    }
  }
}
</style>
