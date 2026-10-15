<!-- 能力市场：精选推荐 + 类型/分类筛选 + 商品网格 + 详情抽屉 -->
<template>
  <div class="market-browse">
    <!-- 精选推荐 -->
    <el-card v-if="featured.length" shadow="never" class="featured-card">
      <template #header>
        <div class="section-head">
          <span class="section-title">精选推荐</span>
          <span class="section-sub">编辑精选的能力，一键安装为你的资产</span>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col v-for="f in featured" :key="f.id" :xs="24" :sm="12" :md="8" :lg="6">
          <el-card shadow="hover" class="featured-item" @click="openDetail(f)">
            <div class="featured-item__head">
              <span class="item-icon">{{ f.icon || assetIcon(f.asset_type) }}</span>
              <div class="item-head-main">
                <div class="item-name">{{ f.name }}</div>
                <el-tag size="small" effect="plain">{{ assetLabel(f.asset_type) }}</el-tag>
              </div>
            </div>
            <div class="item-desc">{{ f.description || "暂无描述" }}</div>
            <div class="item-foot">
              <span class="item-count">{{ f.install_count }} 次安装</span>
              <el-button
                v-hasPerm="['module_ai:market:install']"
                size="small"
                type="primary"
                :icon="Download"
                :disabled="f.installed"
                @click.stop="installItem(f)"
              >
                {{ f.installed ? "已安装" : "安装" }}
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </el-card>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-radio-group v-model="typeFilter" @change="reload">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="tool">工具</el-radio-button>
          <el-radio-button value="skill">技能</el-radio-button>
          <el-radio-button value="mcp">MCP</el-radio-button>
          <el-radio-button value="plugin">插件</el-radio-button>
        </el-radio-group>
        <el-select
          v-model="categoryFilter"
          class="category-select"
          placeholder="全部分类"
          clearable
          @change="reload"
        >
          <el-option v-for="c in categories" :key="c.name" :label="`${c.name} (${c.count})`" :value="c.name" />
        </el-select>
        <el-input
          v-model="keyword"
          class="search-input"
          :prefix-icon="Search"
          placeholder="搜索名称或描述"
          clearable
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-checkbox v-model="onlyFavorite" @change="reload">只看收藏</el-checkbox>
        <el-checkbox v-model="onlyInstalled" @change="reload">只看已安装</el-checkbox>
        <el-button type="primary" :icon="Search" @click="reload">查询</el-button>
      </div>
    </el-card>

    <!-- 商品网格 -->
    <el-row v-loading="loading" :gutter="12" class="item-grid">
      <el-col v-for="item in items" :key="item.id" :xs="24" :sm="12" :md="8" :lg="6">
        <el-card shadow="hover" class="market-item">
          <div class="item-head">
            <span class="item-icon">{{ item.icon || assetIcon(item.asset_type) }}</span>
            <div class="item-head-main">
              <div class="item-name">{{ item.name }}</div>
              <div class="item-tags">
                <el-tag size="small" effect="plain">{{ assetLabel(item.asset_type) }}</el-tag>
                <el-tag v-if="item.category" size="small" type="info" effect="plain">
                  {{ item.category }}
                </el-tag>
              </div>
            </div>
          </div>
          <div class="item-desc">{{ item.description || "暂无描述" }}</div>
          <div class="item-foot">
            <span class="item-count">
              {{ item.install_count }} 安装 · {{ item.favorite_count }} 收藏
            </span>
            <div class="item-actions">
              <el-button size="small" :icon="View" @click="openDetail(item)">详情</el-button>
              <el-button
                v-hasPerm="['module_ai:market:install']"
                size="small"
                type="primary"
                :icon="Download"
                :disabled="item.installed"
                @click="installItem(item)"
              >
                {{ item.installed ? "已安装" : "安装" }}
              </el-button>
            </div>
          </div>
        </el-card>
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
          <span class="detail-icon">{{ detail.icon || assetIcon(detail.asset_type) }}</span>
          <div>
            <div class="detail-name">{{ detail.name }}</div>
            <div class="detail-tags">
              <el-tag size="small" effect="plain">{{ assetLabel(detail.asset_type) }}</el-tag>
              <el-tag v-if="detail.category" size="small" type="info" effect="plain">
                {{ detail.category }}
              </el-tag>
              <el-tag v-if="detail.is_official" size="small" type="success" effect="plain">
                官方
              </el-tag>
              <el-tag v-if="detail.featured" size="small" type="warning" effect="plain">
                精选
              </el-tag>
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
  import { Download, Search, Star, View } from "@element-plus/icons-vue";
  import { ElMessage, ElMessageBox } from "element-plus";
  import { onMounted, ref } from "vue";

  import {
    favoriteMarketItem,
    getMarketHome,
    getMarketItemDetail,
    getMarketItems,
    installMarketItem,
    unfavoriteMarketItem,
    type MarketItem,
  } from "@/api/module_ai/market";

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

  function assetLabel(type: string) {
    return { tool: "工具", skill: "技能", mcp: "MCP", plugin: "插件" }[type] || type;
  }

  function assetIcon(type: string) {
    return { tool: "🧰", skill: "🧩", mcp: "🔌", plugin: "📦" }[type] || "📦";
  }

  async function loadHome() {
    const res: any = await getMarketHome();
    featured.value = res.data?.featured || [];
    categories.value = res.data?.categories || [];
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
      items.value = res.data?.items || [];
      total.value = res.data?.total || 0;
    } finally {
      loading.value = false;
    }
  }

  function reload() {
    pageNo.value = 1;
    loadItems();
  }

  async function openDetail(item: MarketItem) {
    const res: any = await getMarketItemDetail(item.id);
    detail.value = res.data;
    detailVisible.value = true;
  }

  async function installItem(item: MarketItem) {
    await ElMessageBox.confirm(
      `将把「${item.name}」复制为你自己的${assetLabel(item.asset_type)}资产，可在对应管理页维护。是否继续？`,
      "安装确认",
      { confirmButtonText: "安装", cancelButtonText: "取消", type: "info" }
    );
    const res: any = await installMarketItem(item.id);
    if (res.data?.installed) {
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
  .featured-card,
  .filter-card {
    margin-bottom: 12px;
  }

  .section-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }

  .section-title {
    font-weight: 600;
  }

  .section-sub {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .featured-item {
    margin-bottom: 12px;
    cursor: pointer;
  }

  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }

  .category-select {
    width: 180px;
  }

  .search-input {
    width: 240px;
  }

  .item-grid {
    min-height: 120px;
  }

  .market-item {
    margin-bottom: 12px;
    height: 100%;
  }

  .item-head,
  .featured-item__head,
  .detail-head {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }

  .item-icon,
  .detail-icon {
    font-size: 24px;
    line-height: 1;
  }

  .item-head-main {
    min-width: 0;
    flex: 1;
  }

  .item-name,
  .detail-name {
    font-weight: 600;
    margin-bottom: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .item-tags,
  .detail-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .item-desc {
    margin: 10px 0;
    color: var(--el-text-color-regular);
    font-size: var(--el-font-size-base);
    min-height: 40px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .item-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .item-count {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .item-actions {
    display: flex;
    gap: 4px;
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
