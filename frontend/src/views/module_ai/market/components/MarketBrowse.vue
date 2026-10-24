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
          :placeholder="t('ai_market.browseSearchPlaceholder')"
          clearable
          @keyup.enter="reload"
          @clear="reload"
        />
        <el-button
          :icon="Star"
          :type="onlyFavorite ? 'primary' : 'default'"
          @click="toggleFavoriteFilter"
        >
          {{ t("ai_market.browseOnlyFavorite") }}
        </el-button>
        <el-button
          :icon="Download"
          :type="onlyInstalled ? 'primary' : 'default'"
          @click="toggleInstalledFilter"
        >
          {{ t("ai_market.browseInstalled") }}
        </el-button>
        <el-button
          :icon="OfficeBuilding"
          :type="onlyOfficial ? 'primary' : 'default'"
          @click="
            onlyOfficial = !onlyOfficial;
            reload();
          "
        >
          {{ t("ai_market.browseOfficial") }}
        </el-button>
        <el-button
          :icon="Aim"
          :type="onlyMine ? 'primary' : 'default'"
          @click="
            onlyMine = !onlyMine;
            reload();
          "
        >
          {{ t("ai_market.browseMine") }}
        </el-button>
        <el-select
          v-model="sortBy"
          class="sort-select"
          :placeholder="t('ai_market.browseSortPlaceholder')"
          @change="reload"
        >
          <el-option :label="t('ai_market.browseSortNewest')" value="newest" />
          <el-option :label="t('ai_market.browseSortInstall')" value="install" />
          <el-option :label="t('ai_market.browseSortFavorite')" value="favorite" />
        </el-select>
      </div>
    </div>

    <!-- 精选推荐 -->
    <template v-if="featured.length && !hasFilter">
      <div class="section-head">
        <span class="section-title">{{ t("ai_market.browseFeatured") }}</span>
        <span class="section-sub">{{ t("ai_market.browseFeaturedSub") }}</span>
        <el-button size="small" :icon="RefreshRight" text @click="refreshFeatured">
          {{ t("ai_market.browseRefresh") }}
        </el-button>
      </div>
      <el-row :gutter="16" class="card-grid">
        <el-col v-for="f in featured" :key="`f-${f.id}`" :xs="24" :sm="12" :md="8" :lg="6">
          <MarketCard
            :item="f"
            @open="openDetail"
            @install="installItem"
            @favorite="toggleFavorite"
          />
        </el-col>
      </el-row>
    </template>

    <!-- 分类筛选：随类型联动（无「全部」项，点已选项可取消） -->
    <div v-if="categories.length" class="category-bar">
      <span class="section-title">
        {{ t("ai_market.browseCategoryTitle", { type: currentTypeLabel }) }}
      </span>
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

    <!-- 卡片网格：加载骨架屏 + 空状态建议 -->
    <el-skeleton v-if="loading" :rows="3" animated class="grid-skeleton" />
    <template v-else>
      <el-row :gutter="16" class="card-grid">
        <el-col v-for="item in items" :key="item.id" :xs="24" :sm="12" :md="8" :lg="6">
          <MarketCard
            :item="item"
            @open="openDetail"
            @install="installItem"
            @favorite="toggleFavorite"
          />
        </el-col>
      </el-row>
      <div v-if="!items.length" class="empty-state">
        <el-empty :description="t('ai_market.noMatching')">
          <el-button type="primary" plain @click="clearFilters">
            {{ t("ai_market.clearFilters") }}
          </el-button>
        </el-empty>
        <div v-if="categories.length" class="empty-suggest">
          <span class="empty-suggest-label">{{ t("ai_market.tryCategories") }}</span>
          <el-tag
            v-for="c in categories.slice(0, 5)"
            :key="c.name"
            size="small"
            effect="plain"
            class="suggest-tag"
            @click="switchCategory(c.name)"
          >
            {{ c.name }}
          </el-tag>
        </div>
      </div>
    </template>

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
    <el-drawer v-model="detailVisible" :title="t('ai_market.detailTitle')" size="480px">
      <div v-if="detail" class="detail-body">
        <div class="detail-head">
          <IconTile :item="detail" size="lg" />
          <div>
            <div class="detail-name">{{ detail.name }}</div>
            <div class="detail-tags">
              <el-tag size="small" effect="plain">{{ assetLabel(detail.asset_type) }}</el-tag>
              <el-tag v-if="detail.category" size="small" type="info" effect="plain">
                {{ detail.category }}
              </el-tag>
              <el-tag v-if="detail.is_official" size="small" type="success" effect="plain">
                {{ t("ai_market.official") }}
              </el-tag>
              <el-tag v-if="detail.featured" size="small" type="warning" effect="plain">
                {{ t("ai_market.featuredTag") }}
              </el-tag>
            </div>
          </div>
        </div>
        <el-descriptions :column="1" border class="detail-desc">
          <el-descriptions-item :label="t('ai_market.detailVersion')">
            {{ detail.version }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_market.detailAuthor')">
            {{ detail.owner_name || (detail.is_official ? t("ai_market.official") : "—") }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_market.category')">
            {{ detail.category || t("ai_market.uncategorized") }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_market.detailTag')">
            <template v-if="detail.tags?.length">
              <el-tag v-for="t in detail.tags" :key="t" size="small" class="tag-gap">
                {{ t }}
              </el-tag>
            </template>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_market.detailInstallFavorite')">
            {{ detail.install_count }} / {{ detail.favorite_count }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('ai_market.description')">
            {{ detail.description || t("ai_market.noDescription") }}
          </el-descriptions-item>
          <el-descriptions-item v-if="detail.payload?.docs" :label="t('ai_market.detailDoc')">
            <el-link :href="detail.payload.docs" target="_blank" :icon="Link" type="primary">
              {{ t("ai_market.detailDocsLink") }}
            </el-link>
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
            {{ detail.installed ? t("ai_market.installedBtn") : t("ai_market.installBtn") }}
          </el-button>
          <el-button :icon="Star" @click="toggleFavorite(detail)">
            {{ detail.favorited ? t("ai_market.unfavorite") : t("ai_market.favorite") }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import {
  Aim,
  Download,
  Link,
  OfficeBuilding,
  RefreshRight,
  Search,
  Star,
} from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

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

const emit = defineEmits<{ goConfigure: [target: { asset_type: string; name: string }] }>();

const { t } = useI18n();

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
const onlyOfficial = ref(false);
const onlyMine = ref(false);
const sortBy = ref("newest");

const detailVisible = ref(false);
const detail = ref<MarketItem | null>(null);

const typeOptions = [
  { label: t("ai_market.assetTool"), value: "tool" },
  { label: t("ai_market.assetSkill"), value: "skill" },
  { label: t("ai_market.assetMcp"), value: "mcp" },
  { label: t("ai_market.assetPlugin"), value: "plugin" },
];

const hasFilter = computed(
  () =>
    !!typeFilter.value ||
    !!categoryFilter.value ||
    !!keyword.value ||
    onlyFavorite.value ||
    onlyInstalled.value ||
    onlyOfficial.value ||
    onlyMine.value
);

/** 当前类型的中文名（用于分类栏标题） */
const currentTypeLabel = computed(
  () => typeOptions.find((t) => t.value === typeFilter.value)?.label || t("ai_market.allType")
);

function assetLabel(type: string) {
  return (
    {
      tool: t("ai_market.assetTool"),
      skill: t("ai_market.assetSkill"),
      mcp: t("ai_market.assetMcp"),
      plugin: t("ai_market.assetPlugin"),
    }[type] || type
  );
}

/** 判定商品是否需配置密钥（MCP 且 auth_type 非 none，或 env/args 含占位符）。 */
function needsKey(item: MarketItem) {
  const p: any = item.payload || {};
  const hasPlaceholder = JSON.stringify(p.env || p.args || "").includes("<");
  return item.asset_type === "mcp" && ((p.auth_type && p.auth_type !== "none") || hasPlaceholder);
}

async function loadHome(shuffle = false) {
  const res: any = await getMarketHome({ asset_type: typeFilter.value || undefined, shuffle });
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
      official: onlyOfficial.value,
      mine: onlyMine.value,
      sort: sortBy.value || undefined,
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

async function refreshFeatured() {
  await loadHome(true);
}

function clearFilters() {
  typeFilter.value = "";
  categoryFilter.value = "";
  keyword.value = "";
  onlyFavorite.value = false;
  onlyInstalled.value = false;
  onlyOfficial.value = false;
  onlyMine.value = false;
  sortBy.value = "newest";
  loadHome();
  reload();
}

function switchType(value: string) {
  // 再点同一类型 = 取消筛选（回到全部，无「全部」页签）
  typeFilter.value = typeFilter.value === value ? "" : value;
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
    t("ai_market.browseInstallConfirm", {
      name: item.name,
      asset: assetLabel(item.asset_type),
    }),
    t("ai_market.installConfirmTitle"),
    {
      confirmButtonText: t("ai_market.installBtn"),
      cancelButtonText: t("ai_market.cancel"),
      type: "info",
    }
  );
  const res: any = await installMarketItem(item.id);
  const firstInstall = !!res.data?.data?.installed;
  if (firstInstall) {
    ElMessage.success(t("ai_market.installSuccess", { name: item.name }));
  } else {
    ElMessage.info(t("ai_market.alreadyInstalled"));
  }
  item.installed = true;
  if (detail.value && detail.value.id === item.id) detail.value.installed = true;
  loadItems();
  if (firstInstall && needsKey(item)) {
    await ElMessageBox.alert(
      t("ai_market.needsKeyMessage", { name: item.name }),
      t("ai_market.needsKeyTitle"),
      { confirmButtonText: t("ai_market.goConfigure"), type: "warning" }
    );
    emit("goConfigure", { asset_type: item.asset_type, name: item.name });
  }
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
  height: 30px;
  line-height: 30px;
  padding: 0 2px;
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

.sort-select {
  width: 130px;
}

.grid-skeleton {
  margin-top: 4px;
}

.empty-state {
  padding: 24px 0 8px;
  text-align: center;
}

.empty-suggest {
  margin-top: -8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.empty-suggest-label {
  color: var(--el-text-color-secondary);
}

.suggest-tag {
  cursor: pointer;
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
  row-gap: 16px;
  margin-bottom: 8px;
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
