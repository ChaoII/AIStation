import { ref } from "vue";

/** 全景分割类别列表（面板 from ctx.classes 写入，canvas 据此判断 is_instance），插件内共享，不依赖 core。 */
export const panopticClasses = ref<any[]>([]);

/** 重置类别列表（面板卸载/插件复位时调用，避免跨会话残留）。 */
export function resetPanopticClasses() {
  panopticClasses.value = [];
}
