import { useUserStore } from "@/store";
import { ROLE_ROOT } from "@/constants";

/**
 * 按钮权限判断函数（供模板用 v-if 管控）。
 *
 * 为什么不用 v-hasPerm 指令：v-hasPerm 在 `mounted` 时操作 el.parentNode 移除元素，
 * 用在 `el-dropdown-item` 这类「根节点非元素」的组件上会失效（Vue 会警告
 * “Runtime directive used on component with non-element root node”）。
 * 因此下拉菜单等组件级节点统一改用本函数 + v-if。
 */
export function usePerm() {
  const userStore = useUserStore();
  return (required: string | string[]): boolean => {
    const { roles } = userStore.basicInfo;
    const prems = userStore.prems;
    // 超级管理员直接放行（与 v-hasPerm 一致）
    if (roles && roles.some((r) => r.code === ROLE_ROOT)) return true;
    const reqs = Array.isArray(required) ? required : [required];
    return reqs.some((p) => prems.includes(p));
  };
}
