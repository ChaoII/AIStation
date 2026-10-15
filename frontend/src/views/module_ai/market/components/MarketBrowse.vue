<!-- 能力市场：推荐精选 + 类型/分类筛选 + 商品卡片网格 + 详情抽屉 -->
<template>
  <div class="market-browse">
    <!-- 顶部工具条：类型筛选 + 搜索 + 个人筛选 + 提交入口 -->
    <div class="browse-toolbar">
      <div class="type-tabs">
        <span
          v-for="t in typeOptions"
          :key="t.value"
          class="type-tab"
          :class="{ 'is-active': typeFilter === t.value }"
          @click="switchType(t.value)"
        >
          {{ t.label }}
        </span>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="keyword"
          class="search-input"
          :prefix-icon="Search"
          placeholder="搜索能力名称或描述"
          clearable
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-button :icon="Star" :type="onlyFavorite ? 'primary' : 'default'" @click="toggleFavoriteFilter">
          只看收藏
        </el-button>
        <el-button :icon="Download" :type="onlyInstalled ? 'primary' : 'default'" @click="toggleInstalledFilter">
          已安装
        </el-button>
      </div>
    </div>

    <!-- 精选推荐 -->
    <template v-if="featured.length && !hasFilter">
      <div class="section-head">
        <span class="section-title">推荐能力</span>
        <span class="section-sub">平台精选，一键安装为你的资产</span>
      </div>
      <el-row :gutter="12" class="card-grid">
        <el-col v-for="f in featured" :key="`f-${f.id}`" :xs="24" :sm="12" :md="8" :lg="6">
          <market-card :item="f" @open="openDetail" @install="installItem" @favorite="toggleFavorite" />
        </el-col>
      </el-row>
    </template>

    <!-- 分类筛选：随类型联动（无「全部」项，点已选项可取消） -->
    <div v-if="categories.length" class="category-bar">
      <span class="section-title">{{ currentTypeLabel }}能力</span>
      <div class="category-tabs">
        <span
          v-for="c in categories"
          :key="c.name"
          class="category-tab"
          :class="{ 'is-active': categoryFilter === c.name }"
          @click="switchCategory(c.name)"
        >
          {{ c.name }}
          <em class="category-count">{{ c.count }}</em>
        </span>
      </div>
    </div>

    <!-- 卡片网格 -->
    <el-row v-loading="loading" :gutter="12" class="card-grid">
      <el-col v-for="item in items" :key="item.id" :xs="24" :sm="12" :md="8" :lg="6">
        <market-card :item="item" @open="openDetail" @install="installItem" @favorite="toggleFavorite" />
      </el-col>
    </el-row>
    <el-empty v-if="!loading && !items.length" description="暂无符合条件的商品" />

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="pageNo"
      class="pager"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="loadItems"
    />

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" title="商品详情" size="480px">
      <div v-if="detail" class="detail-body">
        <div class="detail-head">
          <icon-tile :item="detail" size="lg" />
          <div>
            <div class="detail-name">{{ detail.name }}</div>
            <div class="detail-tags">
              <el-tag size="small" effect="plain">{{ assetLabel(detail.asset_type) }}</el-tag>
              <el-tag v-if="detail.category" size="small" type="info" effect="plain">
                {{ detail.category }}
              </el-tag>
              <el-tag v-if="detail.is_official" size="small" type="success" effect="plain">官方</el-tag>
              <el-tag v-if="detail.featured" size="small" type="warning" effect="plain">精选</el-tag>
            </div>
          </div>
        </div>
        <el-descriptions :column="1" border class="detail-desc">
          <el-descriptions-item label="版本">{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ detail.category || "未分类" }}</el-descriptions-item>
          <el-descriptions-item label="标签">
            <template v-if="detail.tags?.length">
              <el-tag v-for="t in detail.tags" :key="t" size="small" class="tag-gap">{{ t }}</el-tag>
            </template>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="安装/收藏">
            {{ detail.install_count }} / {{ detail.favorite_count }}
          </el-descriptions-item>
          <el-descriptions-item label="描述">
            {{ detail.description || "暂无描述" }}
          </el-descriptions-item>
        </el-descriptions>
        <div class="detail-actions">
          <el-button
            v-hasPerm="['module_ai:market:install']"
            type="primary"
            :icon="Download"
            :disabled="detail.installed"
            @click="installItem(detail)"
          >
            {{ detail.installed ? "已安装" : "安装" }}
          </el-button>
          <el-button :icon="Star" @click="toggleFavorite(detail)">
            {{ detail.favorited ? "取消收藏" : "收藏" }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
  import { Download, Search, Star } from "@element-plus/icons-vue";
  import { ElMessage, ElMessageBox } from "element-plus";
  import { computed, onMounted, ref } from "vue";

  import {
    favoriteMarketItem,
    getMarketHome,
    getMarketItemDetail,
    getMarketItems,
    installMarketItem,
    unfavoriteMarketItem,
    type MarketItem,
  } from "@/api/module_ai/market";

  import IconTile from "./IconTile.vue";
  import MarketCard from "./MarketCard.vue";

  defineOptions({ name: "MarketBrowse" });

  const loading = ref(false);
  const featured = ref<MarketItem[]>([]);
  const categories = ref<{ name: string; count: number }[]>([]);
  const items = ref<MarketItem[]>([]);
  const total = ref(0);
  const pageNo = ref(1);
  const pageSize = 12;
  const typeFilter = ref("");
  const categoryFilter = ref("");
  const keyword = ref("");
  const onlyFavorite = ref(false);
  const onlyInstalled = ref(false);

  const detailVisible = ref(false);
  const detail = ref<MarketItem | null>(null);

  const typeOptions = [
    { label: "全部", value: "" },
    { label: "工具", value: "tool" },
    { label: "技能", value: "skill" },
    { label: "MCP", value: "mcp" },
    { label: "插件", value: "plugin" },
  ];

  const hasFilter = computed(
    () => !!typeFilter.value || !!categoryFilter.value || !!keyword.value || onlyFavorite.value || onlyInstalled.value
  );

  /** 当前类型的中文名（用于分类栏标题） */
  const currentTypeLabel = computed(
    () => typeOptions.find((t) => t.value === typeFilter.value)?.label || "全部"
  );

  function assetLabel(type: string) {
    return { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" }[type] || type;
  }

  async function loadHome() {
    const res: any = await getMarketHome({ asset_type: typeFilter.value || undefined });
    featured.value = res.data?.data?.featured || [];
    categories.value = res.data?.data?.categories || [];
  }

  async function loadItems() {
    loading.value = true;
    try {
      const res: any = await getMarketItems({
        type: typeFilter.value || undefined,
        category: categoryFilter.value || undefined,
        keyword: keyword.value || undefined,
        favorite: onlyFavorite.value,
        installed: onlyInstalled.value,
        page_no: pageNo.value,
        page_size: pageSize,
      });
      items.value = res.data?.data?.items || [];
      total.value = res.data?.data?.total || 0;
    } finally {
      loading.value = false;
    }
  }

  function reload() {
    pageNo.value = 1;
    loadItems();
  }

  function switchType(value: string) {
    typeFilter.value = value;
    // 分类集合随类型变化 → 清空已选分类并重新加载分类计数
    categoryFilter.value = "";
    loadHome();
    reload();
  }

  function switchCategory(name: string) {
    // 再点同一分类即取消（回到该类型全部）
    categoryFilter.value = categoryFilter.value === name ? "" : name;
    reload();
  }

  function toggleFavoriteFilter() {
    onlyFavorite.value = !onlyFavorite.value;
    reload();
  }

  function toggleInstalledFilter() {
    onlyInstalled.value = !onlyInstalled.value;
    reload();
  }

  async function openDetail(item: MarketItem) {
    const res: any = await getMarketItemDetail(item.id);
    detail.value = res.data?.data;
    detailVisible.value = true;
  }

  async function installItem(item: MarketItem) {
    await ElMessageBox.confirm(
      `将把「${item.name}」复制为你自己的${assetLabel(item.asset_type)}资产，可在对应管理页维护。是否继续？`,
      "安装确认",
      { confirmButtonText: "安装", cancelButtonText: "取消", type: "info" }
    );
    const res: any = await installMarketItem(item.id);
    if (res.data?.data?.installed) {
      ElMessage.success(`已安装「${item.name}」`);
    } else {
      ElMessage.info("该商品已安装过");
    }
    item.installed = true;
    if (detail.value && detail.value.id === item.id) detail.value.installed = true;
    loadItems();
  }

  async function toggleFavorite(item: MarketItem) {
    if (item.favorited) {
      await unfavoriteMarketItem(item.id);
      item.favorited = false;
      item.favorite_count = Math.max(item.favorite_count - 1, 0);
    } else {
      await favoriteMarketItem(item.id);
      item.favorited = true;
      item.favorite_count += 1;
    }
    if (detail.value && detail.value.id === item.id) {
      detail.value.favorited = item.favorited;
      detail.value.favorite_count = item.favorite_count;
    }
  }

  onMounted(() => {
    loadHome();
    loadItems();
  });
</script>

<style lang="scss" scoped>
  .browse-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .type-tabs {
    display: flex;
    align-items: center;
    gap: 18px;
  }

  .type-tab {
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    cursor: pointer;
    padding: 2px 0;
    border-bottom: 2px solid transparent;
    transition: color 0.2s;

    &:hover {
      color: var(--el-color-primary);
    }

    &.is-active {
      color: var(--el-color-primary);
      font-weight: 600;
      border-bottom-color: var(--el-color-primary);
    }
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .search-input {
    width: 240px;
  }

  .section-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin: 16px 0 10px;
  }

  .section-title {
    font-weight: 600;
  }

  .section-sub {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .category-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    margin: 16px 0 10px;
    overflow: hidden;
  }

  .category-tabs {
    display: flex;
    align-items: center;
    gap: 14px;
    overflow-x: auto;
    padding-bottom: 2px;
    white-space: nowrap;
  }

  .category-tab {
    font-size: var(--el-font-size-base);
    color: var(--el-text-color-regular);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 2px;

    &:hover {
      color: var(--el-color-primary);
    }

    &.is-active {
      color: var(--el-color-primary);
      font-weight: 600;
    }
  }

  .category-count {
    font-style: normal;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .card-grid {
    min-height: 120px;
  }

  .pager {
    margin-top: 12px;
    justify-content: flex-end;
  }

  .detail-body {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .detail-head {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }

  .detail-name {
    font-weight: 600;
    margin-bottom: 4px;
  }

  .detail-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .detail-desc {
    margin-top: 4px;
  }

  .detail-actions {
    display: flex;
    gap: 8px;
  }

  .tag-gap {
    margin-right: 4px;
  }
</style>
