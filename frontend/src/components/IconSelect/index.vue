<!-- 图标选择器 -->
<template>
  <div ref="iconSelectRef" :style="{ width: props.width }">
    <el-popover :visible="popoverVisible" :width="props.width" placement="bottom-end">
      <template #reference>
        <div @click="popoverVisible = !popoverVisible">
          <slot>
            <el-input v-model="selectedIcon" readonly placeholder="点击选择图标" class="reference">
              <template #prepend>
                <!-- 根据图标类型展示 -->
                <el-icon v-if="isElementIcon">
                  <component :is="selectedIcon.replace('el-icon-', '')" />
                </el-icon>
                <i v-else-if="isRemixIcon" :class="selectedIcon" />
                <div v-else :class="`i-svg:${selectedIcon}`" />
              </template>
              <template #suffix>
                <!-- 清空按钮 -->
                <el-icon
                  v-if="selectedIcon"
                  style="margin-right: 8px"
                  @click.stop="clearSelectedIcon"
                >
                  <CircleClose />
                </el-icon>

                <el-icon
                  :style="{
                    transform: popoverVisible ? 'rotate(180deg)' : 'rotate(0)',
                    transition: 'transform .5s',
                  }"
                >
                  <ArrowDown @click.stop="togglePopover" />
                </el-icon>
              </template>
            </el-input>
          </slot>
        </div>
      </template>

      <!-- 图标选择弹窗 -->
      <div ref="popoverContentRef">
        <el-input v-model="filterText" placeholder="搜索图标" clearable @input="filterIcons" />
        <el-tabs v-model="activeTab" @tab-click="handleTabClick">
          <el-tab-pane label="SVG 图标" name="svg">
            <el-scrollbar height="300px">
              <ul class="icon-grid">
                <li
                  v-for="icon in filteredSvgIcons"
                  :key="'svg-' + icon"
                  class="icon-grid-item"
                  @click="selectIcon(icon)"
                >
                  <el-tooltip :content="icon" placement="bottom" effect="light">
                    <div :class="`i-svg:${icon}`" />
                  </el-tooltip>
                </li>
              </ul>
            </el-scrollbar>
          </el-tab-pane>
          <el-tab-pane label="Element 图标" name="element">
            <el-scrollbar height="300px">
              <ul class="icon-grid">
                <li
                  v-for="icon in filteredElementIcons"
                  :key="icon"
                  class="icon-grid-item"
                  @click="selectIcon(icon)"
                >
                  <el-icon>
                    <component :is="icon" />
                  </el-icon>
                </li>
              </ul>
            </el-scrollbar>
          </el-tab-pane>
          <el-tab-pane label="Remix 图标" name="remix">
            <el-scrollbar height="300px" @scroll="onRemixScroll">
              <ul class="icon-grid">
                <li
                  v-for="icon in visibleRemixIcons"
                  :key="'ri-' + icon"
                  class="icon-grid-item"
                  @click="selectIcon(icon)"
                >
                  <el-tooltip :content="'ri-' + icon" placement="bottom" effect="light">
                    <i :class="'ri-' + icon" style="font-size: 16px" />
                  </el-tooltip>
                </li>
              </ul>
            </el-scrollbar>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-popover>
  </div>
</template>

<script setup lang="ts">
import * as ElementPlusIconsVue from "@element-plus/icons-vue";
import remixCss from "remixicon/fonts/remixicon.css?raw";

// 从 remixicon.css 提取全部图标类名（避免手写清单，覆盖 3000+ 图标）
function extractRemixNames(css: string): string[] {
  const names = new Set<string>();
  const re = /\.ri-([a-z0-9-]+):before/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(css))) names.add(m[1]);
  return Array.from(names).sort();
}

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  width: {
    type: String,
    default: "500px",
  },
});

const emit = defineEmits(["update:modelValue"]);

const iconSelectRef = ref();
const popoverContentRef = ref();
const popoverVisible = ref(false);
const activeTab = ref("svg");

const svgIcons = ref<string[]>([]);
const elementIcons = ref<string[]>(Object.keys(ElementPlusIconsVue));
const remixIcons = ref<string[]>(extractRemixNames(remixCss));
const selectedIcon = defineModel("modelValue", {
  type: String,
  required: true,
  default: "",
});

const filterText = ref("");
const filteredSvgIcons = ref<string[]>([]);
const filteredElementIcons = ref<string[]>(elementIcons.value);
const filteredRemixIcons = ref<string[]>([]);
// 分批懒加载：避免一次性渲染 3000+ 图标卡顿；滚动近底再追加
const REMIX_BATCH = 160;
const visibleRemixIcons = ref<string[]>([]);
const isElementIcon = computed(() => {
  return selectedIcon.value && selectedIcon.value.startsWith("el-icon");
});
const isRemixIcon = computed(() => {
  return selectedIcon.value && selectedIcon.value.startsWith("ri-");
});

function resetRemixVisible() {
  visibleRemixIcons.value = filteredRemixIcons.value.slice(0, REMIX_BATCH);
}

function onRemixScroll(e: any) {
  const st = e?.scrollTop ?? 0;
  const sh = e?.scrollHeight ?? 0;
  const vh = e?.offsetHeight ?? 0;
  if (st + vh >= sh - 240) {
    const next = filteredRemixIcons.value.slice(
      visibleRemixIcons.value.length,
      visibleRemixIcons.value.length + REMIX_BATCH
    );
    if (next.length) {
      visibleRemixIcons.value = [...visibleRemixIcons.value, ...next];
    }
  }
}

function loadIcons() {
  const icons = import.meta.glob("../../assets/icons/*.svg");
  for (const path in icons) {
    const iconName = path.replace(/.*\/(.*)\.svg$/, "$1");
    svgIcons.value.push(iconName);
  }
  filteredSvgIcons.value = svgIcons.value;
}

function handleTabClick(tabPane: any) {
  activeTab.value = tabPane.props.name;
  filterIcons();
}

function filterIcons() {
  const kw = filterText.value.toLowerCase();
  if (activeTab.value === "svg") {
    filteredSvgIcons.value = kw
      ? svgIcons.value.filter((i) => i.toLowerCase().includes(kw))
      : svgIcons.value;
  } else if (activeTab.value === "remix") {
    filteredRemixIcons.value = kw
      ? remixIcons.value.filter((i) => i.toLowerCase().includes(kw))
      : remixIcons.value;
    resetRemixVisible();
  } else {
    filteredElementIcons.value = kw
      ? elementIcons.value.filter((i) => i.toLowerCase().includes(kw))
      : elementIcons.value;
  }
}

function selectIcon(icon: string) {
  const iconName =
    activeTab.value === "element"
      ? "el-icon-" + icon
      : activeTab.value === "remix"
        ? "ri-" + icon
        : icon;
  emit("update:modelValue", iconName);
  popoverVisible.value = false;
}

function togglePopover() {
  popoverVisible.value = !popoverVisible.value;
}

onClickOutside(iconSelectRef, () => (popoverVisible.value = false), {
  ignore: [popoverContentRef],
});

/**
 * 清空已选图标
 */
function clearSelectedIcon() {
  selectedIcon.value = "";
}

onMounted(() => {
  loadIcons();
  if (selectedIcon.value) {
    if (selectedIcon.value.startsWith("ri-")) {
      activeTab.value = "remix";
      filterIcons(); // 初始化 remix 可见批次
    } else if (elementIcons.value.includes(selectedIcon.value.replace("el-icon-", ""))) {
      activeTab.value = "element";
    } else {
      activeTab.value = "svg";
    }
  }
});
</script>

<style scoped lang="scss">
.reference :deep(.el-input__wrapper),
.reference :deep(.el-input__inner) {
  cursor: pointer;
}

.icon-grid {
  display: flex;
  flex-wrap: wrap;
}

.icon-grid-item {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  margin: 4px;
  cursor: pointer;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  transition: all 0.3s;
}

.icon-grid-item:hover {
  border-color: var(--el-color-primary);
  transform: scale(1.2);
}
</style>
