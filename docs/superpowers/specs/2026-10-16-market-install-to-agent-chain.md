# 市场能力「安装 → 配置 key → 绑定智能体 → 对话可用」链路打通设计

> 日期：2026-10-16
> 范围：AI 能力市场 + 智能体中心（前端 Vue3 + Element Plus / 后端 FastAPI + SQLAlchemy）

## 背景与问题

用户从能力市场安装的 MCP / 工具 / 技能，最终要能进「智能体中心」被选用、并在点开智能体对话时被真正调用。排查后发现链路多数环节已通，但存在以下断点：

| # | 环节 | 现状 / 断点 | 证据 |
|---|------|------------|------|
| 1 | 安装后引导 | 点「安装」只弹一条 `ElMessage`，无「去配置 key / 去启用」引导，尤其需密钥 MCP | `MarketBrowse.vue:373-388` |
| 2 | 智能体绑 MCP | 种子 MCP `payload.enabled=False` → 安装即停用 → 表单 `:disabled="!m.enabled"` 把未启用 MCP 置灰无法选择 | `agent/index.vue:603-609` |
| 3 | 提示文案 | 表单提示「在『MCP 管理』页配置」，但项目无独立 MCP 管理页；实际入口是「能力市场→我的资产」 | `agent/index.vue:611` |
| 4 | 后端一致性 | `create/update` 智能体不校验 `tool_ids/skill_ids/mcp_ids/knowledge_ids` 归属/存在，可绑他人 MCP（含其密钥） | `agent/service.py:201-250` |
| 5 | 工具解析(次要) | `_build_app_tools` 只处理 agno/http，`script` 源工具绑定后不出 schema | `apps/service.py:241-262` |

已确认畅通的环节：工具/技能/知识库选择器不按用户过滤，安装后默认启用即可选；`agent/service.py:run_ui_stream` 已把绑定的技能/知识/MCP/工具装配进 agno 对话。

## 设计决策

- **「需密钥」判定**：MCP 且 `payload.auth_type` 非空且非 `none`，或其 `env`/`args` 值含 `<` 占位符 → 判定为需填 key。
- **未启用 MCP 允许绑定**：Agent 表单允许勾选未启用的 MCP（加「未启用」标记）；运行时 `enabled_servers` 只取启用者，未绑定生效由后端语义保证，前端仅作提示，不再硬置灰。
- **后端校验语义**：`mcp_ids`（用户私有）须存在、未删、`created_id==当前用户`；`tool_ids`（平台共享，按名）须存在、未删、启用；`skill_ids`/`knowledge_ids`（共享）须存在、未删。避免绑定他人资产与不存在资产。
- **script 工具**：`_build_app_tools` 增加 `script` 源分支，对齐 `get_enabled_tool_schemas`，使提交市场的脚本工具也能进智能体（`dispatch_tool` 已支持 script 执行）。

## 改动清单

### ① 前端 · 安装后引导（需密钥 MCP）
- `frontend/src/views/module_ai/market/components/MarketBrowse.vue`
  - 新增 `_needsKey(payload)` 判定；`installItem` 成功后：需密钥 MCP → `ElMessageBox.alert` 引导 + `emit('go-configure',{asset_type,name})`；否则成功提示「已可在智能体中选用」。
  - 新增 `defineEmits<{ goConfigure:[target:{asset_type:string;name:string}] }>()`。
- `frontend/src/views/module_ai/market/index.vue`
  - `mineTarget=ref<{asset_type,name}|null>(null)`；`<MarketBrowse @go-configure="goConfigure"/>`、`<MarketMine :target="mineTarget"/>`；`goConfigure(t){activeTab='mine';mineTarget=t}`；监听 `@target-handled` 清空。
- `frontend/src/views/module_ai/market/components/MarketMine.vue`
  - `props:{target:...}`；watch 到非空：设 `assetType=target.asset_type` → 加载后按 `name` 匹配 `openEdit(row)` → `emit('target-handled')`。

### ② 前端 · 智能体 MCP 选择器
- `frontend/src/views/module_ai/agent/index.vue:595-611`
  - 移除 `:disabled="!m.enabled"`；label 增加 `· 未启用` 标记；hint 改为「MCP 服务器在『能力市场→我的资产』配置并启用；未启用的绑定后在对话中暂不生效」。

### ③ 后端 · 智能体绑定校验
- `backend/app/plugin/module_ai/agent/service.py`
  - 新增 `_validate_agent_bindings(db, tool_ids, skill_ids, knowledge_ids, mcp_ids, user_id)`，在 `create`/`update` 调用（仅校验请求实际提供的字段）。
  - 引入 `AiMcpServerModel`/`AiSkillModel`/`AiKnowledgeBaseModel`/`AiToolModel`。

### ④ 后端 · `_build_app_tools` 支持 script 工具
- `backend/app/plugin/module_ai/apps/service.py` `_build_app_tools`: `http` 分支后加 `elif source=="script": schemas.append(build_http_tool_schema(tool))`。

## 测试

- 后端：新增 `backend/tests/test_agent_binding_validation.py`（DB 集成，`test_client` fixture）：
  - 3a：绑定他人 MCP 被拒；绑定不存在 skill/knowledge/tool 被拒。
  - 3b：绑定自己（`created_id` 一致）的合法 MCP/技能/工具/知识库通过。
  - 4a：`_build_app_tools` 对 `script` 源工具返回非空 schema。
- 前端：用无头浏览器截图核验（市场安装引导弹窗、我的资产自动打开编辑、智能体 MCP 下拉含未启用项），与既有页面对照风格一致。

## 非目标（本次不做）
- Agent Studio 画布增加 MCP 能力卡片（主弹窗可绑，画布暂不绑定）。
- 「AI 智能助手」加载市场资产（用户明确不要该功能）。
- 技能 `config` 运行期密钥注入。
