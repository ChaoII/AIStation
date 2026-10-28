# 实施计划：开放能力清单扩充 + 应用管理卡片美化

> 规格：`docs/superpowers/specs/2026-10-28-develop-capabilities-expansion.md`
> 分支：`main`（联调服务后端 8002 / 前端 5183 保持运行，改后端须杀干净再重启并验 `/openapi.json`）

## 目标

1. **扩充开放能力清单**：按 spec 阶段 A / B / C 逐批把平台资产域开放为 REST + MCP 能力。
2. **美化应用管理卡片**：`frontend/src/views/module_ai/develop/index.vue` 的 `.app-card`（学习 `MarketCard`），去掉卡片上的掩码星号 appid。

## 需求 2（卡片美化）—— 范围小，先做

### 步骤
- [x] C1 重做 `.app-card` 结构，学习 `MarketCard`：图标+名称+副行（类型/状态 tag）+固定描述区+footer（创建时间/调用量）。
- [x] C2 **移除卡片上的 `appid_masked` 星号**；appid/appkey 只进「凭据」弹窗（现有 `keyDialog`/`reveal`）。
- [x] C3 卡片头部放操作（试调/编辑/AppKey/删除），与能力市场卡片交互一致；开关保留在卡片。
- [x] C4 前端 `type-check` + eslint（本文件）+ 无头浏览器截图核验（有数据态 + 空态 + 弹窗）。

## 需求 1（能力扩充）—— 架构级，分阶段

> 每阶段独立可交付：改 `capabilities.py` 品类/权限点 + 新建/扩充 `handlers/<category>.py` + `handlers/__init__.py` 挂载 + 前端 `CATEGORIES` + i18n + 后端测试 + 重启联调 + 提交。

### 阶段 A（高价值）
- [x] A1 `knowledge`：list/get/create/update/delete/search/documents/分类/图谱
- [ ] A2 `query` 智能问数：ask/metrics/terms/assets/pipelines
- [x] A3 `workflow`：list/get/create/update/delete/versions/rollback/runs
- [x] A4 `app`：list/get/create/update/delete
- [x] A5 `cron`：list/create/update/delete/run/runs
- [x] A6 `model` + `prompt` + `provider`：标准 CRUD
- [x] A7 前端 `CATEGORIES` + i18n 补品类名；应用表单能力勾选自动加载

> 已交付：14 → **58** 能力、11 类（train/agent/chat/bot/knowledge/workflow/cron/model/prompt/app/provider）。提交 `1eb8394a`。

### 阶段 B（资产广度）
- [ ] B1 `dataset`
- [ ] B2 `ontology`
- [ ] B3 `sessions`
- [ ] B4 `space`
- [ ] B5 `provider`

### 阶段 C（能力资产 + 运维 + train 扩容）
- [ ] C1 `skill` / `tool` / `mcp` / `plugin`
- [ ] C2 `market`
- [ ] C3 `overview` / `logs`
- [ ] C4 `train` 横向扩容（模型仓库/评估/预测/部署）

## 验收

- 后端 `pytest` 新增能力用例通过；`/openapi.json` 出现新品类能力；`ruff` 通过。
- 前端 `type-check` + 本文件 eslint + 无头截图核验。
- 提交信息 `feat(develop): ...`，与无关工作区改动隔离（只 add 目标文件）。
