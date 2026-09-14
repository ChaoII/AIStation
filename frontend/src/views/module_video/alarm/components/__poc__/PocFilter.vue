<template>
  <div class="poc-filter">
    <!-- 两个模拟叶子字段：object_present(text+选项) / count(number) -->
    <!-- 必须由 Willow 提供 .wx-willow-theme 变量，否则组件无边框/无样式；fonts=false 避免拉取外部字体 -->
    <Willow :fonts="false">
      <FilterBuilder :fields="fields" :options="options" :value="filterValue" :init="handleInit" />
    </Willow>

    <div class="poc-filter__json">
      <div class="poc-filter__json-title">输出条件 JSON（IFilterSet）</div>
      <pre>{{ output }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { FilterBuilder, Willow, type IFilterSet, type IField } from "@svar-ui/vue-filter";
import "@svar-ui/vue-filter/all.css";

/** filter-store 的字段形状：{ id, label, type }，type 仅 number|text|date|tuple */
const fields: IField[] = [
  { id: "object_present", label: "存在目标", type: "text" },
  { id: "count", label: "目标计数", type: "number" },
];

/** options 存在时值为下拉选择，否则为文本输入 */
const options = {
  object_present: ["person", "car", "truck"],
  count: [1, 2, 3, 5, 10],
};

const filterValue = ref<IFilterSet>({ glue: "and", rules: [] });
const output = ref(JSON.stringify(filterValue.value, null, 2));

/** init 回调拿到 api，订阅 change 事件 + 回填/联动 */
function handleInit(api: { on: (action: string, cb: (ev: { value: IFilterSet }) => void) => void }) {
  api.on("change", (ev) => {
    output.value = JSON.stringify(ev.value, null, 2);
  });
}
</script>

<style scoped>
.poc-filter__json {
  margin-top: 12px;
}

.poc-filter__json-title {
  margin-bottom: 4px;
  color: #606266;
  font-size: 12px;
}

.poc-filter__json pre {
  max-height: 200px;
  padding: 8px;
  overflow: auto;
  font-size: 12px;
  background: #f5f7fa;
  border-radius: 4px;
}
</style>
