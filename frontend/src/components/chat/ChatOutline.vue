<!--
  ChatOutline：长会话的「问题导航」。

  会话一长（几十轮），想回到某个问题只能一直滚。这里在对话区右侧挂一个列表按钮，
  点开是**按顺序列出用户提过的每个问题**，点哪条就滚到那条消息。

  用法：
    <ChatOutline :items="outlineItems" container=".chat-shell__body" />
  items: [{ id: "q-3", text: "昨天多少条告警？" }]
-->
<template>
  <div v-show="items.length > 1" class="chat-outline">
    <el-tooltip :content="title" placement="left">
      <button class="chat-outline__btn" type="button" @click="open = true">
        <el-icon><Operation /></el-icon>
        <span class="chat-outline__count">{{ items.length }}</span>
      </button>
    </el-tooltip>

    <el-drawer v-model="open" :title="title" size="360px" append-to-body>
      <div class="chat-outline__list">
        <div
          v-for="(it, i) in items"
          :key="it.id"
          class="chat-outline__item"
          :class="{ 'is-active': i === activeIndex }"
          @click="jump(it, i)"
        >
          <span class="chat-outline__idx">{{ i + 1 }}</span>
          <span class="chat-outline__text" :title="it.text">{{ it.text }}</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { Operation } from "@element-plus/icons-vue";

interface Props {
  /** 按顺序列出用户提问：{ id: 目标元素 id, text: 问题文本 } */
  items: Array<{ id: string; text: string }>;
  /** 滚动容器选择器；不传则用元素的最近可滚动祖先 */
  container?: string;
  /** 抽屉标题 */
  title?: string;
}

const props = withDefaults(defineProps<Props>(), { container: "", title: "问题导航" });

const open = ref(false);
const activeIndex = ref(0);
let scroller: HTMLElement | null = null;

function jump(it: { id: string }, i: number) {
  activeIndex.value = i;
  open.value = false;
  const el = document.getElementById(it.id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  // 高亮闪一下，滚过去能看清是哪一条
  el.classList.add("chat-outline__flash");
  setTimeout(() => el.classList.remove("chat-outline__flash"), 1200);
}

/** 找出真正的滚动容器：给定的选择器若本身不滚（比如外层只是个 flex 壳），
    就沿着第一个问题的祖先向上找第一个可滚动的元素。
    问数页踩过：传 `.chat-shell__body`，实际滚动的是外层 `.el-card__body`。 */
function resolveScroller(): HTMLElement | null {
  const pick = (sel: string) => document.querySelector(sel) as HTMLElement | null;
  const scrollable = (el: HTMLElement | null) =>
    !!el &&
    el.scrollHeight - el.clientHeight > 8 &&
    ["auto", "scroll"].includes(getComputedStyle(el).overflowY);

  const given = props.container ? pick(props.container) : null;
  if (scrollable(given)) return given;

  const first = props.items[0] && document.getElementById(props.items[0].id);
  let el = first?.parentElement || null;
  while (el && el !== document.body) {
    if (scrollable(el)) return el;
    el = el.parentElement;
  }
  return given;
}

/** 根据滚动位置高亮最近的一条（纯视觉，失败也不影响跳转） */
function onScroll() {
  if (!props.items.length) return;
  const base = scroller ? scroller.getBoundingClientRect().top : 0;
  // 滚到底时最后一个问题往往顶不到阈值线（内容不够高），直接高亮最后一条
  if (scroller && scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 4) {
    activeIndex.value = props.items.length - 1;
    return;
  }
  let idx = 0;
  props.items.forEach((it, i) => {
    const el = document.getElementById(it.id);
    if (el && el.getBoundingClientRect().top - base <= 80) idx = i;
  });
  activeIndex.value = idx;
}

onMounted(() => {
  scroller = resolveScroller();
  // 用捕获阶段监听：真正的滚动条可能是某一层祖先（问数页是 .el-card__body），
  // 直接绑在 body 上会漏掉。
  window.addEventListener("scroll", onScroll, { capture: true, passive: true });
});

onBeforeUnmount(() => {
  window.removeEventListener("scroll", onScroll, { capture: true });
});
</script>

<style lang="scss">
.chat-outline {
  position: absolute;
  top: 50%;
  right: 6px;
  z-index: 5;
  transform: translateY(-50%);
}

.chat-outline__btn {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-items: center;
  justify-content: center;
  width: 30px;
  padding: 6px 0;
  font-size: 15px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  box-shadow: var(--el-box-shadow-light);
  transition: color 0.2s;

  &:hover {
    color: var(--el-color-primary);
  }
}

.chat-outline__count {
  font-size: 10px;
  line-height: 1;
}

.chat-outline__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-outline__item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  cursor: pointer;
  border-radius: 6px;

  &:hover {
    background: var(--el-fill-color-light);
  }

  &.is-active {
    background: var(--el-color-primary-light-9);
  }
}

.chat-outline__idx {
  flex: 0 0 auto;
  min-width: 18px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.chat-outline__text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--el-text-color-primary);
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

/* 跳转后短暂高亮目标消息 */
.chat-outline__flash {
  animation: chat-outline-flash 1.2s ease-out;
}

@keyframes chat-outline-flash {
  0% {
    background: var(--el-color-primary-light-8);
  }
  100% {
    background: transparent;
  }
}
</style>
