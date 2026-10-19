<!-- 市场商品卡片：图标 + 名称/分类 + 「+」安装 + 描述 + 安装/收藏数 -->
<template>
  <div class="market-card" @click="$emit('open', item)">
    <div class="market-card__head">
      <IconTile :item="item" />
      <div class="market-card__title">
        <div class="market-card__name">{{ item.name }}</div>
        <div class="market-card__sub">
          <el-tag size="small" effect="plain">{{ assetLabel }}</el-tag>
          <span v-if="item.category" class="market-card__cat">{{ item.category }}</span>
          <span v-if="item.owner_name || item.is_official" class="market-card__author">
            {{ item.owner_name || "官方" }}
          </span>
        </div>
      </div>
      <el-tooltip :content="item.installed ? '已安装' : '安装'" placement="top">
        <el-button
          v-hasPerm="['module_ai:market:install']"
          class="market-card__add"
          circle
          size="small"
          :icon="item.installed ? Check : Plus"
          :disabled="item.installed"
          @click.stop="$emit('install', item)"
        />
      </el-tooltip>
    </div>
    <div class="market-card__desc">{{ item.description || "暂无描述" }}</div>
    <div class="market-card__foot">
      <span class="metric" title="安装数">
        <el-icon><Download /></el-icon>
        {{ formatCount(item.install_count) }}
      </span>
      <span
        class="metric metric--clickable"
        :class="{ 'is-on': item.favorited }"
        title="收藏"
        @click.stop="$emit('favorite', item)"
      >
        <el-icon><Star /></el-icon>
        {{ formatCount(item.favorite_count) }}
      </span>
      <el-link
        v-if="docsUrl"
        class="market-card__doc"
        :href="docsUrl"
        target="_blank"
        :icon="Link"
        @click.stop
      >
        文档
      </el-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Check, Download, Link, Plus, Star } from "@element-plus/icons-vue";
import { computed } from "vue";

import type { MarketItem } from "@/api/module_ai/market";

import IconTile from "./IconTile.vue";

const props = defineProps<{ item: MarketItem }>();
defineEmits<{
  open: [item: MarketItem];
  install: [item: MarketItem];
  favorite: [item: MarketItem];
}>();

const LABELS: Record<string, string> = { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" };
const assetLabel = computed(() => LABELS[props.item.asset_type] || props.item.asset_type);

/** MCP 等商品若带文档链接，卡片展示「文档」跳转 */
const docsUrl = computed(() => props.item.payload?.docs || "");

/** 数量格式化：>=1 万显示「x.x万」 */
function formatCount(n: number | undefined): string {
  const v = Number(n || 0);
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`;
  return String(v);
}
</script>

<style lang="scss" scoped>
.market-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 18px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  cursor: pointer;
  transition:
    box-shadow 0.2s,
    transform 0.2s,
    border-color 0.2s;

  &:hover {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 6px 18px rgb(0 0 0 / 8%);
    transform: translateY(-2px);
  }
}

.market-card__head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.market-card__title {
  min-width: 0;
  flex: 1;
}

.market-card__name {
  font-weight: 600;
  font-size: var(--el-font-size-base);
  line-height: 1.5;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-card__sub {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.market-card__cat {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.market-card__author {
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 96px;
}

.market-card__add {
  flex: 0 0 auto;
}

.market-card__desc {
  margin: 12px 0 12px;
  color: var(--el-text-color-regular);
  font-size: var(--el-font-size-base);
  line-height: 1.7;
  min-height: 40px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.market-card__foot {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.metric {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.metric--clickable {
  cursor: pointer;

  &:hover {
    color: var(--el-color-primary);
  }

  &.is-on {
    color: var(--el-color-warning);
  }
}

.market-card__doc {
  margin-left: auto;
  font-size: 12px;
}
</style>
