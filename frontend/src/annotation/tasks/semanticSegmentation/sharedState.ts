import { ref } from "vue";

/** 语义分割「背景」类别 id（面板设置，渲染器据此垫底），插件内共享，不依赖 core。 */
export const segBackgroundClassId = ref<number | null>(null);
