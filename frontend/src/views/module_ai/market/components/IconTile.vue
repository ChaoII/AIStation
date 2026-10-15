<!-- 商品图标：图片优先，缺图时按资产类型回退 emoji -->
<template>
  <span class="icon-tile" :class="`icon-tile--${size}`">
    <img v-if="isImage" :src="src" alt="" class="icon-tile__img" />
    <span v-else class="icon-tile__emoji">{{ emoji }}</span>
  </span>
</template>

<script setup lang="ts">
  import { computed } from "vue";

  const props = withDefaults(
    defineProps<{
      item: { icon?: string | null; asset_type: string };
      size?: "sm" | "lg";
    }>(),
    { size: "sm" }
  );

  const FALLBACK: Record<string, string> = {
    tool: "🧰",
    skill: "🧩",
    mcp: "🔌",
    plugin: "📦",
  };

  const icon = computed(() => (props.item.icon || "").trim());

  /** 图片判定：http(s) 链接、带图片扩展名、或 market-icons/ 相对路径 */
  const isImage = computed(() => {
    const i = icon.value;
    return (
      /^https?:\/\//i.test(i) ||
      /\.(png|jpe?g|svg|webp|gif)$/i.test(i) ||
      i.startsWith("market-icons/")
    );
  });

  const src = computed(() => {
    const i = icon.value;
    if (/^https?:\/\//i.test(i)) return i;
    // public 目录资源需拼接 Vite base（项目 base=/web，注意其不带尾斜杠）
    const base = import.meta.env.BASE_URL || "/";
    const normalized = base.endsWith("/") ? base : `${base}/`;
    return `${normalized}${i.replace(/^\//, "")}`;
  });

  const emoji = computed(() => icon.value || FALLBACK[props.item.asset_type] || "📦");
</script>

<style lang="scss" scoped>
  .icon-tile {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
    border-radius: 8px;
    background: var(--el-fill-color-light);
    overflow: hidden;
  }

  .icon-tile--sm {
    width: 40px;
    height: 40px;
    font-size: 22px;
  }

  .icon-tile--lg {
    width: 52px;
    height: 52px;
    font-size: 28px;
  }

  .icon-tile__img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .icon-tile__emoji {
    line-height: 1;
  }
</style>
