<template>
  <div class="poc-page">
    <h2 class="poc-page__title">SP5-a 第三方组件集成 POC</h2>
    <p class="poc-page__desc">
      验证 vue-konva（ROI 画布）与 @svar-ui/vue-filter（条件树）在本项目的可用性。临时页面，Task 9 删除。
    </p>

    <el-card class="poc-page__card" shadow="never">
      <template #header>ROI 画布：vue-konva 4.0.1 + konva 10.5.0</template>
      <PocRoi />
    </el-card>

    <el-card class="poc-page__card" shadow="never">
      <template #header>条件树：@svar-ui/vue-filter 2.6.1（FilterBuilder）</template>
      <PocFilter />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import PocFilter from "./PocFilter.vue";
import PocRoi from "./PocRoi.vue";
</script>

<style scoped>
.poc-page {
  padding: 16px;
}

.poc-page__title {
  margin: 0 0 4px;
  font-size: 18px;
}

.poc-page__desc {
  margin: 0 0 12px;
  color: #909399;
  font-size: 13px;
}

.poc-page__card {
  margin-bottom: 16px;
}
</style>
