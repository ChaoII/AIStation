<template>
  <div class="auth-view" :style="{ '--login-background-url': `url(${loginBackgroundUrl})` }">
    <!-- 跟随鼠标的聚光淡网格（零依赖组件；触摸设备自动禁用） -->
    <GridSpotlight
      :cell="46"
      :radius="240"
      :grid-opacity="0.25"
      :glow-opacity="0.12"
      line-color="rgba(64, 158, 255, 0.42)"
      glow-color="rgba(64, 158, 255, 0.5)"
    />
    <!-- 极光光斑背景：让毛玻璃卡的模糊效果明显 -->
    <AuroraBackground />
    <ParticlesNet />
    <!-- 右侧语言切换按钮（登录页为固定深色沉浸式，不提供明暗切换） -->
    <div class="auth-view__toolbar">
      <el-tooltip :content="t('login.languageToggle')" placement="bottom">
        <CommonWrapper>
          <LangSelect size="text-20px" />
        </CommonWrapper>
      </el-tooltip>
    </div>
    <!-- 登录页主体 -->
    <div class="auth-view__wrapper">
      <!-- 登录页主体容器 -->
      <section class="auth-panel">
        <!-- 标题 -->
        <div class="auth-panel__brand">
          <div class="auth-panel__logo-wrap">
            <!-- logo -->
            <el-image :src="loginLogoUrl" class="auth-panel__logo" />
          </div>
          <div class="auth-panel__meta">
            <div class="auth-panel__title-row">
              <span class="auth-panel__title">
                {{ configStore.configData?.sys_web_title?.config_value || "" }}
              </span>
              <el-tooltip
                :content="configStore.configData?.sys_web_description?.config_value || ''"
                placement="bottom"
              >
                <el-icon class="cursor-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <div class="auth-panel__version-row">
              <span class="auth-panel__version-label">Version</span>
              <span class="auth-panel__version-pill">
                v{{ configStore.configData?.sys_web_version?.config_value || "" }}
              </span>
            </div>
          </div>
        </div>
        <!-- 组件切换 -->
        <transition name="fade-slide" mode="out-in">
          <component
            :is="formComponents[component]"
            v-model="component"
            v-model:preset-username="loginPreset.username"
            v-model:preset-password="loginPreset.password"
            class="auth-panel__form"
          />
        </transition>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import CommonWrapper from "@/components/CommonWrapper/index.vue";
import { useConfigStore } from "@/store";
import { resolveLoginBackground, resolveSiteLogo } from "@/utils/siteLogo";

const configStore = useConfigStore();

// 登录背景兜底：配置为空时用内置背景（此前配置指向失效地址 → 登录页背景空白）
const loginBackgroundUrl = computed(() =>
  resolveLoginBackground(configStore.configData?.sys_login_background?.config_value)
);

// logo 兜底：配置为空时用内置 logo（此前配置指向失效地址 → 登录页显示"加载失败"）
const loginLogoUrl = computed(() =>
  resolveSiteLogo(configStore.configData?.sys_web_logo?.config_value)
);

type LayoutMap = "login" | "register" | "resetPwd";

const t = useI18n().t;

const component = ref<LayoutMap>("login"); // 切换显示的组件
const formComponents = {
  login: defineAsyncComponent(() => import("./components/Login.vue")),
  register: defineAsyncComponent(() => import("./components/Register.vue")),
  resetPwd: defineAsyncComponent(() => import("./components/ResetPwd.vue")),
};

// 预填登录信息（通过具名 v-model 双向绑定传递）
const loginPreset = reactive<{ username: string; password: string }>({
  username: "admin",
  password: "123456",
});
</script>

<style lang="scss" scoped>
.auth-view {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  padding: clamp(1rem, 3vw, 2rem);
  overflow: hidden;
  // 聚光网格层：在背景之上、内容之下（否则绝对定位会盖住卡片）
  :deep(.grid-spotlight) {
    z-index: 0;
  }
  .auth-view__toolbar,
  .auth-view__wrapper {
    position: relative;
    z-index: 1;
  }
  // 登录页为固定深色沉浸式：兜底背景锁定深蓝黑（正常被背景图覆盖）
  background-color: #070d1a;

  &::before {
    position: fixed;
    inset: 0;
    z-index: -2;
    content: "";
    background: var(--login-background-url) center/cover no-repeat;
  }

  &::after {
    position: fixed;
    inset: 0;
    z-index: -1;
    pointer-events: none;
    content: "";
    // 深蓝黑氛围罩：贴合深蓝科幻底图，柔和铺底不冲淡
    background: linear-gradient(
      120deg,
      rgba(6, 12, 24, 0.38),
      rgba(6, 12, 24, 0.06) 55%,
      rgba(6, 12, 24, 0.24)
    );
  }
}

.auth-view__toolbar {
  display: inline-flex;
  gap: 0.75rem;
  align-self: flex-end;
  padding: 0.5rem 0.75rem;
  // 固定深色玻璃托盘（不随系统明暗变化），语言图标统一浅色
  --el-text-color-primary: rgba(255, 255, 255, 0.92);
  color: rgba(255, 255, 255, 0.92);
  background-color: rgba(10, 16, 30, 0.72);
  border: 1px solid rgba(140, 170, 220, 0.25);
  border-radius: 999px;
  box-shadow: 0 8px 24px -8px rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  transition:
    transform 0.3s ease,
    box-shadow 0.3s ease;

  &:hover {
    box-shadow: 0 12px 28px -8px rgba(0, 0, 0, 0.5);
    transform: translateY(-2px);
  }

  @media (max-width: 640px) {
    position: fixed;
    top: 12px;
    right: 16px;
    z-index: 20;
    align-self: flex-end;
    justify-content: center;
  }

  // 暗色/亮色交给 Element Plus 变量处理，不在页面里写死颜色分支
}

/* 暗色样式交给全局主题变量 */

.auth-view__wrapper {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: clamp(1.5rem, 2vw, 2.5rem);
}

@media (max-width: 768px) {
  .auth-view__wrapper {
    padding: 1.25rem 0.75rem 1.75rem;
  }

  .auth-panel {
    width: 100%;
    margin-inline: 0;
    box-shadow: var(--el-box-shadow);
  }
}

.auth-panel {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  justify-content: flex-start;
  width: min(440px, 100%);
  padding: clamp(2rem, 3vw, 2.5rem);
  margin-inline: auto;
  // 深蓝黑玻璃卡片：与背景同色系融入，文字统一浅色（覆盖文本变量）
  --el-text-color-primary: rgba(255, 255, 255, 0.94);
  --el-text-color-regular: rgba(226, 232, 244, 0.78);
  --el-text-color-secondary: rgba(180, 195, 220, 0.6);
  --el-text-color-placeholder: rgba(255, 255, 255, 0.4);
  --el-border-color: rgba(120, 150, 200, 0.28);
  --el-border-color-light: rgba(140, 170, 220, 0.22);
  --el-border-color-lighter: rgba(120, 150, 200, 0.18);
  --el-fill-color-lighter: rgba(255, 255, 255, 0.06);
  background: linear-gradient(
    165deg,
    rgba(18, 28, 48, 0.66),
    rgba(10, 16, 30, 0.58) 60%,
    rgba(14, 22, 40, 0.62)
  );
  border: 1px solid rgba(140, 170, 220, 0.22);
  border-radius: 22px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.14),
    0 22px 48px -16px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(42px) saturate(1.8);
  -webkit-backdrop-filter: blur(42px) saturate(1.8);
  animation: panelLift 0.7s ease;
}

.auth-panel__brand {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.85rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.auth-panel__logo-wrap {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  background: rgba(64, 128, 255, 0.14);
  border: 1px solid rgba(140, 170, 220, 0.22);
  border-radius: 18px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.auth-panel__logo {
  flex-shrink: 0;
  width: 52px;
  height: 52px;
}

.auth-panel__meta {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
}

.auth-panel__title-row {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}

.auth-panel__title {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 1.2rem;
  font-weight: 650;
  line-height: 1.4;
  color: var(--el-text-color-primary);
  white-space: nowrap;
}

.auth-panel__version-row {
  display: inline-flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.78rem;
}

.auth-panel__version-label {
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.auth-panel__version-pill {
  padding: 0.1rem 0.55rem;
  font-weight: 500;
  color: #7fb2ff;
  background: rgba(64, 128, 255, 0.16);
  border: 1px solid rgba(64, 128, 255, 0.3);
  border-radius: 999px;
}

.auth-panel__form {
  width: 100%;
  max-width: 100%;
  margin-inline: auto;

  :deep(.el-form-item) {
    margin-bottom: 1.25rem;
  }

  :deep(.el-input__wrapper) {
    background: rgba(8, 14, 26, 0.5);
    box-shadow: 0 0 0 1px rgba(120, 150, 200, 0.3) inset;
    transition: all 0.2s ease;

    &:hover {
      box-shadow: 0 0 0 1px rgba(140, 170, 220, 0.45) inset;
    }

    &.is-focus {
      box-shadow: 0 0 0 1px var(--el-color-primary) inset;
    }

    :deep(.el-input__inner) {
      color: rgba(255, 255, 255, 0.92);
    }
  }

  // 主按钮：蓝青轻渐变（基于 Element Plus 变量，非写死主题色）
  :deep(.el-button--primary) {
    border: none;
    background-image: linear-gradient(
      135deg,
      var(--el-color-primary-light-3),
      var(--el-color-primary)
    );

    &:hover {
      background-image: linear-gradient(
        135deg,
        var(--el-color-primary-light-4),
        var(--el-color-primary-light-2)
      );
    }
  }

  :deep(.el-card) {
    background: transparent;
    box-shadow: none;
  }
}

@keyframes panelLift {
  from {
    opacity: 0;
    transform: translateY(30px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateX(-40px) scale(0.95);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(40px) scale(0.95);
}

.fade-slide-enter-to,
.fade-slide-leave-from {
  opacity: 1;
  transform: translateX(0) scale(1);
}
</style>
