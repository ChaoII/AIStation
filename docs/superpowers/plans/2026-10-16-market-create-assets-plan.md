# 能力市场「我的资产」集成四类资产创建/编辑/高阶操作

## 目标
把 工具管理 / MCP管理 / 技能广场 / 能力插件 四个独立模块的**创建/编辑/配置/测试**能力
整体搬进「能力市场 → 我的资产」，并下线四个独立菜单、物理删除四个独立页面文件。

## 决策（已与用户确认）
- 创建入口形态：各类型页签内各自「新建XX」按钮。
- 高阶操作（配置/测试/试运行）保留，随编辑一起进入对话框。
- 四个独立页：菜单下线 + **物理删除** `frontend/src/views/module_ai/{tool,mcp,skill,plugin}/index.vue`。
- 前端动态路由由后端菜单驱动；菜单下线后路由不可达。

## 待办
- [ ] 后端 `init_app.py`：`AI_MERGED_INTO_MARKET` 增加 `AiTool`/`AiMcp`（隐藏+重定向 /ai/market）
- [ ] 后端 `init_app.py`：四类菜单条目不再创建/隐藏（AiTool/AiMcp 已在下线清单中）
- [ ] 前端组件 `CreateToolDialog.vue`（HTTP/脚本/Agno 配置 + 测试/试运行）
- [ ] 前端组件 `CreateMcpDialog.vue`（stdio/sse/http + 连接测试）
- [ ] 前端组件 `CreateSkillDialog.vue`（新建 + 导入 SKILL.md/Zip）
- [ ] 前端组件 `CreatePluginDialog.vue`（JSON 配置）
- [ ] `MarketMine.vue`：各类型页签加「新建XX」按钮 + 卡片加「编辑」按钮，挂载 4 个 Dialog
- [ ] 物理删除四个独立页 `frontend/src/views/module_ai/{tool,mcp,skill,plugin}/index.vue`
- [ ] 前端 type-check 无新增错误
- [ ] 后端启动、浏览器截图视觉确认（四页签新建/编辑/配置/测试）
- [ ] 提交：`feat(ui): 能力市场我的资产集成四类资产创建/编辑与高阶操作`
