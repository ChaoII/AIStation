<!--
  AuroraBackground —— 登录页「极光」背景层。

  目的：让毛玻璃登录卡的模糊效果明显——卡片背后需要有**彩色、有对比**的
  背景内容，blur 后才会呈现明显的磨砂玻璃感。用多个大尺寸径向渐变光斑
  （蓝/青/紫）缓慢漂移 + 大面积 blur 实现，等价于 vue-bits 的 Aurora 观感，
  但不引入 WebGL/Tailwind 依赖。

  注意：
  - 该层位于登录卡（z-index: 1）之下，卡片 backdrop-filter 会模糊它。
  - pointer-events: none，不遮挡/不拦截交互。
  - 亮/暗主题下均用品牌色系，_el 变量不适用于纯装饰光斑，故用固定色。
-->
<template>
  <div class="aurora-bg" aria-hidden="true">
    <span class="blob b1" />
    <span class="blob b2" />
    <span class="blob b3" />
  </div>
</template>

<style lang="scss" scoped>
.aurora-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;

  .blob {
    position: absolute;
    width: 62vmax;
    height: 62vmax;
    border-radius: 50%;
    filter: blur(72px);
    opacity: 0.5;
  }

  .b1 {
    top: -12%;
    left: -6%;
    background: radial-gradient(circle at 35% 35%, #409eff, transparent 62%);
    animation: drift1 26s ease-in-out infinite;
  }

  .b2 {
    right: -12%;
    bottom: -14%;
    background: radial-gradient(circle at 65% 65%, #36cfc9, transparent 62%);
    animation: drift2 32s ease-in-out infinite;
  }

  .b3 {
    top: -4%;
    right: 8%;
    background: radial-gradient(circle at 60% 40%, #7c5cff, transparent 58%);
    opacity: 0.4;
    animation: drift3 38s ease-in-out infinite;
  }

  @keyframes drift1 {
    0%,
    100% {
      transform: translate(0, 0) scale(1);
    }
    50% {
      transform: translate(9%, -7%) scale(1.12);
    }
  }
  @keyframes drift2 {
    0%,
    100% {
      transform: translate(0, 0) scale(1);
    }
    50% {
      transform: translate(-9%, 7%) scale(1.16);
    }
  }
  @keyframes drift3 {
    0%,
    100% {
      transform: translate(0, 0) scale(1);
    }
    50% {
      transform: translate(-7%, 8%) scale(1.06);
    }
  }
}
</style>
