<!-- 统一产品页头部：主标题 + 副标题 + 右侧操作（复用 Element Plus 变量，保持框架一致） -->
<template>
  <div class="ph">
    <div class="ph__main">
      <div class="ph__title">{{ title }}</div>
      <div v-if="subtitle" class="ph__sub">{{ subtitle }}</div>
    </div>
    <div class="ph__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>();
</script>

<style scoped lang="scss">
.ph {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 2px 14px;
}
.ph__title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  line-height: 1.3;
}
.ph__sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
