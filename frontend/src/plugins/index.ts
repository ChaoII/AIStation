import type { App } from "vue";

import { setupDirective } from "@/directives";
import { setupI18n } from "@/lang";
import { setupRouter } from "@/router";
import { setupStore } from "@/store";
import { setupElIcons } from "./icons";
import { setupPermission } from "./permission";
import ElementPlus from "element-plus";

export default {
  install(app: App<Element>) {
    // 自定义指令(directive)
    setupDirective(app);
    // 路由(router)
    setupRouter(app);
    // 状态管理(store)
    setupStore(app);
    // 国际化
    setupI18n(app);
    // Element-plus图标
    setupElIcons(app);
    // 路由守卫
    setupPermission();
    // 注册 ElementPlus
    app.use(ElementPlus);

    // 全局错误处理，防止组件销毁异常导致路由切换失败
    app.config.errorHandler = (err, instance, info) => {
      console.error("[Global Error]", err, info);
    };
  },
};
