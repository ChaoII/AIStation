<!--
  ParticlesNet —— 登录页「粒子网络 + 鼠标吸附跟随」背景层。

  用成熟库 **tsParticles**（`@tsparticles/vue3` + `@tsparticles/slim`），不手写特效。
  关键点：
  - `interactivity.detectsOn: "window"`：鼠标在**任意位置**（包括表单上方）都能触发吸附；
    同时画布 `pointer-events: none`，不会遮挡/拦截表单交互。
  - `onHover.mode: ["attract", "grab"]`：光标把附近粒子**吸过来**（attract），并与粒子**连线**（grab）。
  - 粒子间 `links` 连线 + 缓慢漂移 → 数据网络观感。
-->
<template>
  <div class="particles-net">
    <VueParticles id="login-particles" :options="options" />
  </div>
</template>

<script setup lang="ts">
const options = {
  fullScreen: { enable: false },
  fpsLimit: 60,
  detectRetina: true,
  background: { color: { value: "transparent" } },
  particles: {
    number: { value: 60, density: { enable: true, width: 1200, height: 800 } },
    color: { value: ["#409EFF", "#36CFC9"] },
    opacity: { value: { min: 0.28, max: 0.55 } },
    size: { value: { min: 2, max: 4 } },
    links: {
      enable: true,
      distance: 150,
      color: "#409EFF",
      opacity: 0.28,
      width: 1,
    },
    move: {
      enable: true,
      speed: 1.1,
      outModes: { default: "out" },
    },
  },
  interactivity: {
    detectsOn: "window",
    events: {
      onHover: { enable: true, mode: ["attract", "grab"] },
      onClick: { enable: true, mode: ["push"] },
      resize: { enable: true },
    },
    modes: {
      attract: { distance: 240, duration: 0.6, speed: 2.4 },
      grab: { distance: 200, links: { opacity: 0.4 } },
      push: { quantity: 3 },
    },
  },
};
</script>

<style lang="scss" scoped>
.particles-net {
  position: absolute;
  inset: 0;
  // 不遮挡/不拦截表单交互（鼠标事件由 window 侦听，故仍能吸附）
  pointer-events: none;

  :deep(#login-particles) {
    position: absolute;
    inset: 0;
  }

  :deep(canvas) {
    display: block;
    width: 100% !important;
    height: 100% !important;
  }
}
</style>
