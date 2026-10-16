import type { App } from "vue";
import { createRouter, createWebHashHistory, type RouteRecordRaw } from "vue-router";
export const Layout = () => import("@/layouts/index.vue");
/**
 * 静态路由
 */
export const constantRoutes: RouteRecordRaw[] = [
  {
    path: "/redirect",
    meta: { hidden: true },
    component: Layout,
    children: [
      {
        path: "/redirect/:path(.*)",
        component: () => import("@/views/redirect/index.vue"),
      },
    ],
  },
  {
    path: "/login",
    name: "Login",
    meta: { hidden: true },
    component: () => import("@/views/module_system/auth/index.vue"),
  },
  {
    path: "/401",
    name: "401",
    meta: { hidden: true, title: "401" },
    component: () => import("@/views/error/401.vue"),
  },
  {
    path: "/404",
    name: "404",
    meta: { hidden: true, title: "404" },
    component: () => import("@/views/error/404.vue"),
  },
  {
    path: "/500",
    name: "500",
    meta: { hidden: true, title: "500" },
    component: () => import("@/views/error/500.vue"),
  },
  {
    path: "/",
    name: "/",
    redirect: "/home",
    component: Layout,
    children: [
      {
        path: "home",
        component: () => import("@/views/dashboard/index.vue"),
        // 用于 keep-alive 功能，需要与 SFC 中自动推导或显式声明的组件名称一致
        // 参考文档: https://cn.vuejs.org/guide/built-ins/keep-alive.html#include-exclude
        name: "Home",
        meta: {
          title: "首页",
          icon: "homepage",
          affix: true,
          keepAlive: true,
        },
      },
      {
        path: "profile",
        name: "Profile",
        meta: { title: "个人中心", icon: "user", hidden: true },
        component: () => import("@/views/current/profile.vue"),
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    component: () => import("@/views/error/404.vue"),
    meta: { hidden: true, title: "404" },
  },
  // 数据资产：并入「数据与集成」子菜单（后端动态路由已带 redirect，此处静态兜底防 404）
  {
    path: "/ai/asset",
    name: "AiAssetMoved",
    redirect: "/ai/integration",
    meta: { hidden: true, title: "数据资产（已并入数据与集成）" },
  },
  // 工作台对话（独立聊天页，静态兜底避免 404）
  {
    path: "/ai/workspace/chat/:kind/:id",
    name: "AiWorkspaceChat",
    component: () => import("@/views/module_ai/workspace/chat.vue"),
    meta: { hidden: true, title: "工作台对话" },
  },
  // Big screen display (standalone, no sidebar)
  {
    path: "/video/big-screen",
    name: "VideoBigScreen",
    meta: { hidden: true, title: "大屏展示" },
    component: () => import("@/views/module_video/layout/big-screen.vue"),
  },
  // 公开分享运行页（独立、无登录，受令牌+限流+白名单节点保护）
  {
    path: "/share",
    name: "AiShareRun",
    meta: { hidden: true, title: "工作流分享运行" },
    component: () => import("@/views/module_ai/workflow/ShareRun.vue"),
  },
];

/**
 * 创建路由
 */
const router = createRouter({
  history: createWebHashHistory(),
  routes: constantRoutes,
  // 刷新时，滚动条位置还原
  scrollBehavior: () => ({ left: 0, top: 0 }),
});

// 兼容旧书签/旧链接：/ai/query?tab=integration|eval|reports → 对应独立页面
// （「智能问数」已从页签工作台改为独立菜单目录 + 4 个子菜单；无 tab / tab=ask / 非法值留在问数页）
router.beforeEach((to) => {
  if (to.path === "/ai/query" && to.query.tab) {
    const tab = String(to.query.tab);
    if (tab === "integration") return { path: "/ai/integration" };
    if (tab === "eval") return { path: "/ai/eval" };
    if (tab === "reports") return { path: "/ai/query/reports" };
  }
});

// 全局注册 router
// 为了捕获并处理全局错误，在注册路由时添加错误处理
export function setupRouter(app: App<Element>) {
  app.use(router);
}

export default router;
