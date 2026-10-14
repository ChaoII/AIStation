<!--
  本体维护抽屉
  收纳索引 / 提案 / 场景 / 决策 / 对象探索 / 高级类型(对象类型组、值类型、共享属性、接口) 面板。
  各面板复用既有组件，数据与刷新走 useOntologyData。
-->
<template>
  <div class="ont-maint">
    <!-- 索引 -->
    <OntIndexView v-if="panel === 'index'" />
    <!-- 提案 -->
    <OntProposalView v-else-if="panel === 'proposals'" @refresh="reloadAll" />
    <!-- 场景 -->
    <OntScenarioView v-else-if="panel === 'scenarios'" @refresh="reloadAll" />
    <!-- 决策 -->
    <OntDecisionView v-else-if="panel === 'decisions'" @refresh="reloadAll" />
    <!-- 对象探索 -->
    <OntInstanceExplorer v-else-if="panel === 'explore'" :objects="scopedObjects" />
    <!-- 对象类型组 -->
    <OntAdvancedTypes
      v-else-if="panel === 'groups'"
      section="groups"
      :objects="scopedObjects"
      :object-label="objectLabel"
    />
    <!-- 值类型 -->
    <OntAdvancedTypes
      v-else-if="panel === 'valueTypes'"
      section="valueTypes"
      :objects="scopedObjects"
      :object-label="objectLabel"
    />
    <!-- 共享属性 -->
    <OntAdvancedTypes
      v-else-if="panel === 'shared'"
      section="shared"
      :objects="scopedObjects"
      :object-label="objectLabel"
    />
    <!-- 接口 -->
    <OntAdvancedTypes
      v-else-if="panel === 'interfaces'"
      section="interfaces"
      :objects="scopedObjects"
      :object-label="objectLabel"
    />
    <el-empty v-else :image-size="60" description="该面板暂未接入" />
  </div>
</template>

<script setup lang="ts">
import { useOntologyData } from "../composables/useOntologyData";
import OntIndexView from "./OntIndexView.vue";
import OntProposalView from "./OntProposalView.vue";
import OntScenarioView from "./OntScenarioView.vue";
import OntDecisionView from "./OntDecisionView.vue";
import OntInstanceExplorer from "./OntInstanceExplorer.vue";
import OntAdvancedTypes from "./OntAdvancedTypes.vue";

const props = defineProps<{ panel: string }>();

const { scopedObjects, objectLabel, reloadAll } = useOntologyData();
void props;
</script>

<style scoped lang="scss">
.ont-maint {
  min-height: 200px;
}
</style>
