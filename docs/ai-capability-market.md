# AI 能力市场（工具 / 技能 / MCP / 插件）

> 设计文档：`docs/superpowers/specs/2026-10-15-ai-capability-market-design.md`
> 实施计划：`docs/superpowers/plans/2026-10-15-ai-capability-market.md`

## 一、它解决什么问题

平台此前的能力（工具 / 技能 / MCP / 插件）各自为政：工具只有「内置 + HTTP」，技能有广场雏形，
MCP 完全没有，插件是硬编码的 key。用户之间也无法互相分享能力。

能力市场把它们统一成**一个橱窗**：

- **市场是橱窗，安装 = 把商品 payload 复制成自己的真实资产**（`ai_tools` / `ai_skills` /
  `ai_mcp_servers` / `ai_plugins`）。安装后就是你自己的一条记录，可自由编辑、启停、删除。
- **Agent 绑定零侵入**：Agent 绑定的仍是用户自己的真实资产（`tool_ids` / `skill_ids` / `mcp_ids`），
  市场只负责「复制」这一步。
- 支持**提交审核**（个人资产 → 市场商品）与**点对点分享**（A 直接分享给 B）。

## 二、数据模型

| 表 | 用途 | 关键列 |
|----|------|--------|
| `ai_market_items` | 市场商品（统一橱窗） | `asset_type`(tool/skill/mcp/plugin)、`payload`(资产快照)、`status`(draft/pending/approved/rejected/offline)、`featured`、`install_count`、`owner_id`、`source_id` |
| `ai_market_relations` | 用户与商品的关系 | `user_id`、`item_id`、`kind`(installed/favorited)、`description`(存已复制的真实资产 id) |
| `ai_market_shares` | 点对点分享 | `item_id`、`from_user_id`、`to_user_id`、`status`(pending/accepted/rejected) |
| `ai_mcp_servers` | MCP 服务器配置（个人） | `transport`(stdio/sse/streamable-http)、`command`/`args`/`env`、`url`/`headers`、`auth_type`、`enabled` |
| `ai_plugins` | AI 能力插件（能力包） | `key`、`label`、`config`、`config_schema`、`executor_ready`、`enabled` |

既有表增列：

- `ai_tools.code`（脚本源码）、`ai_tools.timeout`（脚本超时秒）
- `ai_agents.mcp_ids`（JSONB，绑定的 MCP 服务器 id 列表）

迁移文件：`backend/app/alembic/versions/2026_10_15_ai_market_models.py`（手写，避免 autogenerate
把库中大量历史/影子表（`ont_*`）误判为待删除）。

```bash
cd backend && uv run main.py upgrade --env=dev
```

## 三、权限码与菜单

权限码（`backend/app/scripts/init_app.py` 的 `AI_BUTTON_PERMS`）：

| 权限码 | 含义 |
|--------|------|
| `module_ai:market:query` | 浏览市场、我的资产、分享列表；收藏/取消收藏 |
| `module_ai:market:install` | 安装市场商品 |
| `module_ai:market:submit` | 提交个人资产到市场、撤回自己的商品 |
| `module_ai:market:share` | 发起分享 |
| `module_ai:market:review` | 审核（通过/驳回/下架/精选）——**建议只给管理员** |
| `module_ai:mcp:query/create/update/delete` | MCP 服务器管理 |
| `module_ai:plugin:query/create/update/delete` | 能力插件管理 |

菜单：`能力市场`（`/ai/market`）、`MCP 管理`（`/ai/mcp`）、`能力插件`（`/ai/plugin`）。

**存量库如何生效**：菜单与按钮权限由 `_ensure_ai_menus()` 在**应用启动时幂等补齐**
（新库与存量库都会补，且自动授权给 admin 角色）。因此**升级后重启一次后端**即可看到菜单，
无需手工 INSERT。若使用自定义角色，请在「角色管理」中勾选对应按钮权限。

> 前端「审核中心」页签仅对超管或持有 `module_ai:market:review` 的用户显示。

## 四、依赖变更（重要）

接入 MCP 需要 agno 的原生 `MCPTools`，其硬依赖与项目原 pin 冲突，因此本次调整：

| 包 | 变更 | 原因 |
|----|------|------|
| `mcp` | 新增 `>=2.1.0,<3.0.0` | agno `MCPTools` 必需（**客户端**用法，未引入 fastmcp 服务端） |
| `pyjwt` | `2.9.0` → `2.15.1` | mcp 要求 `pyjwt>=2.10.1` |
| `uvicorn` | `0.30.6` → `0.54.0` | mcp 要求 `uvicorn>=0.31.1` |
| `requires-python` | `>=3.10` → `>=3.10,<3.14` | 3.14 解析分支下 mcp 要求 `starlette>=0.48`，与 `fastapi==0.115.2`（`starlette<0.41`）冲突 |

安装走清华镜像：

```bash
cd backend && uv add "mcp>=2.1.0,<3.0.0" --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 五、自定义 Python 脚本工具（受控沙箱）

工具新增 `kind="script"`：在「工具管理」页新建时把「工具类型」切到 **Python 脚本**，填写代码即可。

入口约定：

```python
def run(args: dict) -> dict:
    # args 为大模型给出的入参
    return {"result": ...}
```

安全设计（三层，见 `backend/app/plugin/module_ai/tools_catalog/script_executor.py`）：

1. **静态校验（创建/更新时）**：AST 白名单——
   - 仅允许导入 `json / math / re / datetime / random / statistics / collections / itertools /
     functools / typing / string / decimal / fractions / hashlib / base64 / uuid / csv`；
   - 禁止 `eval / exec / compile / open / __import__ / getattr / setattr / input / globals /
     locals / type / object` 等；
   - 禁止双下划线名称与属性访问（阻断 `__class__` / `__subclasses__` 逃逸）；
   - 禁止 `with / async / await / global / nonlocal`。
   - **非法脚本在保存时即被拒绝**（不是运行时报错）。
2. **受限内建**：执行时只注入白名单 builtins（无 `open`、`__import__` 走白名单包装）。
3. **超时**：`sys.settrace` 行计数（Windows 无 `signal.alarm`），超时抛业务错误，不会挂死进程。

**风险提示**：沙箱面向「受信任用户写简单数据处理逻辑」，不是对抗恶意代码的强隔离
（Python 层沙箱无法抵御所有逃逸手法）。请勿向不可信用户开放 `module_ai:tool:create` 权限。

试运行：编辑弹窗底部「试运行」按钮（`POST /ai/tools/test-script/{id}`），返回 `{ok, result|error}`。

## 六、MCP 接入

1. 在「MCP 管理」页新增服务器：
   - **stdio**：填写启动命令 + 参数（每行一个）+ 环境变量（每行 `KEY=VALUE`）；
   - **sse / streamable-http**：填写地址 + 请求头 + 鉴权方式。
2. 点「测试」做**可达性探测**：stdio 检查命令是否在 PATH 中；http 方式 GET 一次（状态码 <500 视为可达，
   401/403 亦说明服务在线）。测试不建立真实 MCP 会话。
3. 在「智能体」编辑弹窗的 **MCP** 多选里绑定（写入 `ai_agents.mcp_ids`）。
4. 运行时：`run_agno_tool_stream` 按 `mcp_ids` 取**当前用户自己的启用服务器**，
   用 agno `MCPTools` 连接后并入 Agent 工具集，运行结束自动关闭。
   **任何服务器连不上都只跳过该项**（降级运行），不影响 Agent 其它能力。

工具名以 `服务器名_` 为前缀，避免多服务器重名。

## 七、能力插件

> **官方种子**：应用启动时 `ensure_market_seed()`（`market/seed.py`）幂等写入官方商品，共 **33 条**：
> - **16 个通用技能**（内容创作 / 办公效率 / 开发编程 / 数据分析 / 设计多媒体 / AI Agent / 知识管理 / 商业运营 / 行业专业 / 生活服务），
>   content 为可直接注入 Agent 的中文指令；
> - **9 个 agno 免密钥工具**（calculator / webtools / hackernews / duckduckgo / wikipedia / arxiv / newspaper / csv_toolkit / visualization），
>   安装时**复用**平台同名 `ai_tools` 行（不复制副本，否则派发按名字找不到 agno 工具）；
> - **8 个办公类 MCP**（飞书官方、企业微信机器人、GitHub / Notion / GitLab 官方、Playwright、Context7、本地文件系统），
>   凭据以 `<占位>` 给出，安装后由用户填写并启用。
>
> 图标：`backend/scripts/gen_market_icons.py` 用 Qwen-Image 网关批量生成（统一扁平 App 图标风格），
> 落盘到 `frontend/public/market-icons/<key>.png`（1024 生成 → 256 压缩，每张约 40–60KB）；缺失时前端回退 emoji。

插件是**能力包**（非平台代码插件）。首次打开「能力插件」页会惰性预置内置 key：

| key | 执行器 | 说明 |
|-----|--------|------|
| `web_fetch` | ✅ | 抓取 URL 正文（只读，返回前 4000 字） |
| `table_export` | ✅ | 结构化数据导出为 CSV 文本（不落盘） |
| `email_send` / `report_generate` / `data_pipeline` | ❌ | 预留（`executor_ready=false`，不可运行） |

启用的插件会以「已启用能力插件」小节注入 Agent 系统提示词。

## 八、接口清单

```
# 市场
GET    /api/v1/ai/market/home                    首页（精选 + 分类计数）
GET    /api/v1/ai/market/items                   列表（type/category/keyword/favorite/installed + 分页）
GET    /api/v1/ai/market/items/{id}              详情（含 installed/favorited）
POST   /api/v1/ai/market/items/{id}/install      安装（幂等）
POST   /api/v1/ai/market/items/{id}/favorite     收藏
DELETE /api/v1/ai/market/items/{id}/favorite     取消收藏
POST   /api/v1/ai/market/submit                  提交个人资产到市场
GET    /api/v1/ai/market/mine                    我的资产（含市场状态）
POST   /api/v1/ai/market/items/{id}/withdraw     撤回（下架）
GET    /api/v1/ai/market/review/list             审核列表（review 权限）
POST   /api/v1/ai/market/review                  审核（approve/reject）
POST   /api/v1/ai/market/items/{id}/feature      设置精选
POST   /api/v1/ai/market/shares/share            分享给用户
GET    /api/v1/ai/market/shares?direction=in|out 分享列表（严格按 from/to 过滤）
POST   /api/v1/ai/market/shares/{id}/accept      接收（复制资产给自己）
POST   /api/v1/ai/market/shares/{id}/reject      拒绝

# MCP
GET/POST/PUT/DELETE /api/v1/ai/mcp/...           配置 CRUD（按 created_id 隔离）
PUT    /api/v1/ai/mcp/toggle/{id}                启停
POST   /api/v1/ai/mcp/test/{id}                  连接测试

# 能力插件
GET/POST/PUT/DELETE /api/v1/ai/plugins/...       插件 CRUD
PUT    /api/v1/ai/plugins/toggle/{id}            启停

# 工具（新增）
POST   /api/v1/ai/tools/test-script/{id}         脚本试运行
```

## 九、测试

```bash
cd backend
uv run pytest tests/test_market_models.py tests/test_market_install.py tests/test_market_review.py \
              tests/test_market_share.py tests/test_script_tool.py tests/test_mcp.py \
              tests/test_mcp_runtime.py tests/test_plugins.py tests/test_market_menus.py -q
# 全量（并行）
uv run pytest -q -n 4
```

覆盖要点：安装幂等、审核越权 403、分享可见性隔离、脚本沙箱（静态拒绝 + 超时）、
MCP 降级（禁用/空配置不影响运行）、菜单与权限种子。
