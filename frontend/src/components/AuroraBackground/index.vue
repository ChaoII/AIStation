<!--
  AuroraBackground —— 登录页「极光」背景层。

  目的：让毛玻璃登录卡的模糊效果明显——卡片背后需要有**明暗对比**的背景内容，
  blur 后才会呈现明显的磨砂玻璃感。用多个大尺寸径向渐变光斑
  （银白/浅灰，黑白风格）缓慢漂移 + 大面积 blur 实现。

  注意：
  - 该层位于登录卡（z-index: 1）之下，卡片 backdrop-filter 会模糊它。
  - pointer-events: none，不遮挡/不拦截交互。
  - 黑白科幻风格：光斑仅用白/灰阶，靠明暗层次而非彩色。
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
    opacity: 0.7;
  }

  .b1 {
    top: -12%;
    left: -6%;
    background: radial-gradient(circle at 35% 35%, rgba(64, 158, 255, 0.7), transparent 62%);
    animation: drift1 26s ease-in-out infinite;
  }

  .b2 {
    right: -12%;
    bottom: -14%;
    background: radial-gradient(circle at 65% 65%, rgba(54, 207, 201, 0.6), transparent 62%);
    animation: drift2 32s ease-in-out infinite;
  }

  .b3 {
    top: -4%;
    right: 8%;
    background: radial-gradient(circle at 60% 40%, rgba(120, 170, 255, 0.45), transparent 58%);
    opacity: 0.75;
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
