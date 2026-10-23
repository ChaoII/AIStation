# 前端国际化（i18n）设计文档 2026-10-23

## 一、目标与范围

- **目标**：让平台切换为英文后，界面文案真正变成英文（当前 `vue-i18n` + 中英语言包已搭好，但绝大多数页面文案仍是硬编码中文）。
- **本次范围（阶段一 + 试点）**：
  1. 完善基础设施：语言包按模块拆分、Element Plus locale 随语言切换（已接）、框架文案（分页/空态/校验消息等）走 i18n、`translateRouteTitle` 覆盖菜单路径、新增「未翻译中文串」检测脚本。
  2. **系统管理模块（`module_system`）试点**：把该模块下所有页面/表单/弹窗/列表/确认文案接入 i18n，作为全平台范本。
- **不在本次范围（另议）**：
  - 后端返回/写入的系统校验错误消息、数据库枚举文案（属后端 i18n）。
  - AI 模块、视频、训练、标注等其余模块（在试点验收后按同法铺开）。
  - 后端菜单表（`sys_menu`）的双语存储 —— 菜单标题通过前端 `route.*` key 的 `translateRouteTitle` 翻译。

## 二、现状（摸底结论）

- `vue-i18n` v11 已装并全局注册（`src/lang/index.ts`，`legacy:false`、`globalInjection:true`）。
- 语言包：`src/lang/package/en.ts`（约230行）、`zh-cn.ts`（约232行），目前只有 `common/route/login` 等少数命名空间，覆盖框架壳与登录页。
- Element Plus locale 已按语言切换：`appStore.locale` 返回 `en`/`zhCn` 对象（`app.store.ts`），`App.vue` 的 `<el-config-provider :locale>` 已接。
- 路由/菜单标题翻译：`translateRouteTitle(title)`（`src/utils/i18n.ts`）判断 `route.<title>` 是否存在 key，存在则翻译，否则原样返回。需确保所有菜单路径有对应 `route.*` key。
- 语言切换入口：`src/components/LangSelect/index.vue`；应用语言存于 `appStore.language`。
- 缺口：页面/组件里大量硬编码中文未抽成 key，切英文后主体仍为中文。

## 三、方案（混合式，分阶段）

采用「人工抽 key + LLM 辅助翻译 + 子代理分模块并行」，基础设施先行，再按模块铺开。抽 key 一律用 vue-i18n 的 `$t('namespace.key')` / `t()`，中英文 key 对齐。

## 四、语言包结构（按模块拆分）

```
src/lang/package/
  common.ts        # 通用（按钮/表格/弹窗/提示，从现有 common 扩展）
  route.ts         # 菜单/路由标题（route.*）
  login.ts         # 登录页
  system/
    user.ts        # 用户管理
    role.ts        # 角色管理
    menu.ts        # 菜单管理
    dept.ts        # 部门
    tenant.ts      # 租户
    param.ts       # 参数
    dict.ts        # 字典
    notice.ts      # 公告
    position.ts    # 岗位
    auth.ts        # 登录/鉴权相关
  ...               # 后续模块：ai/video/train/annotation 等
```

- 约定：key 命名 `命名空间.元素.语义`，例如 `system.user.search.name`、`system.role.deleteConfirm`。
- `src/lang/index.ts` 统一聚合各模块包（`messages` 下的 `zh-cn`/`en` 分别聚合）。
- 中英文同一 key 分别落在 `zh-cn` / `en` 对应模块包内。

## 五、基础设施落地清单（阶段一）

1. **拆分语言包**：把现 `en.ts`/`zh-cn.ts` 拆为 `common/route/login` + `system/*` 骨架；`index.ts` 聚合。
2. **Element Plus 语言切换**：已由 `appStore.locale` 完成，验证分页「上一页/下一页/共 x 条」、空态、表格筛选等内置文案随语言切换。
3. **框架层文案**：`PageContent.vue`（分页布局/删除确认/空态）、`PageSearch`、`EnhancedDialog` 等 CURD 组件的默认文案抽成 i18n（有默认中英文），页面可通过覆盖保留自定义。
4. **路由/菜单标题**：为 `sys_menu` 现有路由路径补 `route.*` key（中英），确保 `translateRouteTitle` 命中；侧边栏/面包屑/标签页标题随语言切换。
5. **「未翻译中文串」检测脚本**：`frontend/scripts/check_i18n_missing.mjs`（或 .ts），正则扫描 `src/views`、`src/components`、`src/api`、`src/utils` 下的中文字面量（template 文本与 JS 字符串），排除已用 `$t`/`t()` 的，输出「模块 → 待翻译串清单」到控制台或文件，作为每模块验收基线。
6. **登录页**：`module_system/auth` 下的登录/注册/忘记密码等页面接入 i18n。

## 六、`module_system` 试点执行

- 覆盖子模块：`user/role/menu/dept/tenant/param/dict/notice/position/log/auth(登录)`。
- 每页/组件：提取模板与 `<script>` 中的中文 → `$t('system.xxx')` → 中英 key 同补。
- 覆盖点：页面标题、搜索区 label、表格列名、操作列（编辑/删除/详情）、弹窗表单 label、按钮、空态、确认文案、校验消息、toast/成功/失败提示。
- 完成后 `pnpm type-check` + `pnpm run lint`，再语言切换冒烟（切英文后 `module_system` 界面为英文）。

## 七、验证标准

- `pnpm run type-check` 通过；改动文件 `eslint` 无新错误。
- 切英文后：`module_system` 全部界面（含弹窗/空态/确认框/分页）为英文；Element Plus 内置组件文案为英文；菜单/面包屑标题为英文。
- 切回中文后：一切恢复中文，无 key 缺失（`$t` 命中、无「key not found」）。
- 检测脚本对 `module_system` 报告的中文串为 0（或已全部接入）。

## 八、风险与权衡

- **规模大**：全平台几百页，需分批；本次只做基础设施 + 系统管理试点，验收后按同法铺开。
- **上下文与插值**：含变量/模板语法的文案（如「将删除 {n} 项」）需用 vue-i18n 插值语法 `{n}`，翻译时保留占位符。
- **职责边界**：后端错误/枚举不接管；菜单标题走前端 `route.*`。
- **子代理并行质量**：试点模块由单个主流程手动精细完成以确立范本，后续模块再引入子代理并行。
