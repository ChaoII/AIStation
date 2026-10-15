<template>
  <div class="logo">
    <transition enter-active-class="animate__animated animate__fadeInLeft">
      <router-link :key="+collapse" class="wh-full flex-center" to="/">
        <img :src="logoUrl" class="w50px h50px" />
        <span v-if="!collapse" class="title">
          {{ configStore.configData.sys_web_title.config_value }}
        </span>
      </router-link>
    </transition>
  </div>
</template>

<script lang="ts" setup>
import { computed } from "vue";
import { useConfigStore } from "@/store";
import { resolveSiteLogo } from "@/utils/siteLogo";

const configStore = useConfigStore();

// logo 兜底：配置为空/失效时回落内置 logo.png（此前导致侧边栏出现破损图）
const logoUrl = computed(() => resolveSiteLogo(configStore.configData?.sys_web_logo?.config_value));

defineProps({
  collapse: {
    type: Boolean,
    required: true,
  },
});
</script>

<style lang="scss" scoped>
.logo {
  width: 100%;
  height: $navbar-height;
  background-color: var(--layout-logo-bg);

  .title {
    max-width: 100px;
    margin-left: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 14px;
    font-weight: bold;
    color: $sidebar-logo-text-color;
    white-space: nowrap;
  }
}
</style>

<style lang="scss">
// 顶部布局和混合布局的特殊处理
.layout-top,
.layout-mix {
  .logo {
    background-color: transparent !important;

    .title {
      color: var(--menu-text);
    }
  }
}

// 宽屏时：openSidebar 状态下显示完整Logo+文字
.openSidebar {
  &.layout-top .layout__header-left .logo,
  &.layout-mix .layout__header-logo .logo {
    width: $sidebar-width; // 210px，显示logo+文字
  }
}

// 窄屏时：hideSidebar 状态下只显示Logo图标
.hideSidebar {
  &.layout-top .layout__header-left .logo,
  &.layout-mix .layout__header-logo .logo {
    width: $sidebar-width-collapsed; // 54px，只显示logo
  }

  // 隐藏文字，只显示图标
  .logo .title {
    display: none;
  }
}
</style>
