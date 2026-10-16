# skillhub.cn 技能精选固化 —— 设计文档

日期：2026-10-16
状态：已定稿（待实现）
应用范围：AI 能力市场（技能/工具/MCP 内置）

## 1. 背景与目标

平台「能力市场」已有统一橱窗（`ai_market_items`），可安装工具/技能/MCP/插件，技能（instruction 类型）安装后写入 `ai_skills` 并被 Agent 注入。当前内置技能较少（约 20 个）。

用户要求：从 skillhub.cn（腾讯 AI Skills 社区，公开 HTTP+JSON 接口，总量 19.7 万+ 技能）**精选 200+ 个技能并固化内置**到平台能力市场，同时补充一批工具/MCP。

**核心约束与决策（已与用户确认）**
- 采用**精选固化**：预取内容转为平台指令技能，固化进种子；**运行时离线**，不依赖 skillhub 外部接口。
- 类型范围：**技能为主（200+）+ 补充一批工具/MCP**。skillhub.cn 一级分类均为技能类（无 MCP/工具资产），故工具/MCP 走稳定官方源。
- 内容转换：**中文描述 + SKILL.md 结构抽取**。技能角色/触发用中文（`description_zh`），工作流/要点抽取自 SKILL.md 小节；**抽到的英文小节原样保留**（中文小节标签 + 原文 bullet），抽不到的中文占位说明。
- 精选标准：**综合评分 + 下载量 + 有中文描述 + 免 API Key**，剔除付费（`pay-skill`/`pricing_type=paid`）与高风险项。
- 存储：独立数据模块 `market/data/skillhub_skills.py`（由生成脚本产物） + 生成脚本 `scripts/_generate_skillhub_skills.py`（可复跑）。
- 图标：设为空，前端按分类回退 emoji，避免离线时远程图标裂图。

## 2. 架构与组件

### 2.1 数据模块
`backend/app/plugin/module_ai/market/data/skillhub_skills.py`
- 定义 `SKILLHUB_SKILLS: list[dict]`，每项结构：
  ```python
  {
    "key": "skillhub-xxx",          # 唯一 key，slug 派生
    "name": "中文显示名",            # 来自 skillhub name/displayName
    "category": "内容创作",           # 平台分类（已映射）
    "description": "中文描述",       # 来自 description_zh
    "content": "...",               # 组装的中文指令 content
    "tags": ["来源:skillhub", ...],  # 技能标签
    "featured": False,
    "icon": "",                     # 空 → 前端 emoji 回退
    "source": "skillhub.cn",
    "source_slug": "content-writer", # 原 slug，便于溯源
    "license": "MIT",
  }
  ```
- 文件头部注释：由生成脚本产出，勿手改。

### 2.2 生成脚本
`backend/scripts/_generate_skillhub_skills.py`
- 纯函数 + 主流程。纯函数（可单测）：`map_category()`、`clean_name()`、`normalize_names()`、`build_skill_content()`、`extract_sections()`。
- 主流程：分页拉取 → 过滤 → 去重 → 逐个取内容 → 组装 → 写数据模块。
- 运行：`uv run python scripts/_generate_skillhub_skills.py`（在后端目录）。输出直接覆写 `market/data/skillhub_skills.py`。

### 2.3 种子接入
`backend/app/plugin/module_ai/market/seed.py`
- `ensure_market_seed()` 在现有 `_SKILLS` 循环后，增加对 `SKILLHUB_SKILLS` 的循环，走同一 `_add("skill", ...)` 与 `_payload_of()`。
- `_payload_of()` 增加：`icon` 取 `skill.get("icon") or market-icons/{key}.png`（兼容现有，空 icon 时仍回落），`author` 保持 "AIStation 官方"；可选在 payload 增加 `source`/`source_slug` 标识来源（不破坏安装逻辑）。
- 幂等：`_add` 按 `(asset_type, name)` 去重，撞名跳过，不影响用户/审核数据。

## 3. 生成与精选流程

1. **拉取**：`GET /api/skills?labels=requires_api_key:false,pricing_type:!paid&sortBy=score&order=desc&page=1..N&pageSize=100`，累计候选直至充足。
2. **过滤**：
   - `description_zh` 存在且含中文（CJK）；
   - `labels.requires_api_key == "false"`（已由接口条件保证）；
   - `labels.pricing_type != "paid"`；
   - `category != "pay-skill"`；
   - `score` / `downloads` 达阈值（保证“精选”）。
3. **去重**：
   - 规范化显示名（去 `.Skill`/`SKILL`/空格/括号），同名保留最高分实例；
   - 与现有 `_SKILLS` 的名称集合去重，避免和内置技能撞名。
4. **取内容**（对前 ~220 个已筛候选）：
   - `GET /api/v1/skills/{slug}` 取 `summary_zh`、`tags`、`stats`、`license`（若有）；
   - `GET /api/v1/skills/{slug}/files` 定位 `SKILL.md`；
   - `GET /api/v1/skills/{slug}/file?path=SKILL.md`（自动跟随 302）取原文。
5. **组装 content**：见 §4。
6. **限速与重试**：对 `429`/`5xx`/超时指数退避重试；请求间小延时，避免触发频率保护。

## 4. content 组装模板

```
## 角色 / 目标
{description_zh（清理控制符、截断至 ~400 字）}

## 触发场景
{SKILL.md「When to Activate / Trigger」小节，否则用 description_zh 关键触发词}

## 工作流
{抽取「Workflow / Process / Steps / Method / 流程 / 步骤 / 工作流」，逐条 bullet；缺失则「（未提供，请结合目标判断）」}

## 关键要点
{抽取「Guidelines / Checklist / Rules / Constraints / 约束 / 规则 / 清单」，逐条 bullet；缺失则跳过}

## 输出格式
{抽取「Output / Format / 输出 / 格式」小节；缺失则「（按平台既有风格输出 Markdown）」}

## 来源
skillhub.cn/{source_slug}（{license}）
```

- 输出为 Markdown 字符串，总长上限约 2000 字符（超出按阈值截断并保留关键部分）。
- 中文小节标签固定；原文 bullet 原样保留（允许英文）。

## 5. 分类映射（skillhub 一级分类 → 平台分类）

| skillhub key | 平台分类 |
|--------------|----------|
| content-creation | 内容创作 |
| dev-programming | 开发编程 |
| data-analysis | 数据分析 |
| design-media | 设计多媒体 |
| ai-agent | AI Agent |
| knowledge-management | 知识管理 |
| business-ops | 商业运营 |
| education | 教育学习 |
| professional | 行业专业 |
| it-ops-security | IT 运维与安全 |
| life-service | 生活服务 |
| office-efficiency | 办公效率 |
| pay-skill | （跳过） |
| 其它/未知 | 通用 |

## 6. 工具/MCP 补充

skillhub.cn 无 MCP/工具资产，从稳定官方源补充（不来自 skillhub API）：
- `_TOOLS`：追加约 3 个 agno 内置免密钥通用工具（如天气、时间、数学等，按 agno 实际可用性）。
- `_MCPS`：追加约 12 项官方/主流稳定 MCP（如 Google Drive、AWS、Snowflake、Chrome DevTools、Perplexity、DeepSeek 等），凭据用 `<占位>`，`enabled=False`，并补充 `_MCP_DOCS`。
- 与现有内置 MCP/工具幂等共处（`_add` 按名去重）。

## 7. 测试（TDD）

`backend/tests/test_skillhub_curation.py`：
- `SKILLHUB_SKILLS` 长度 ≥ 200；
- 每条 `name/description/content/category` 非空，`content` 含中文（CJK）；`key` 唯一、`name` 无重复；
- `map_category` 对已知 key 映射正确、未知回落「通用」；
- `build_skill_content` 用样例 SKILL.md（含中/英文小节）验证：能抽取「工作流/约束」、缺失小节给中文占位、长度上限生效；
- 与现有 `_SKILLS` 名称集合无交集（避免撞名冲突）。

`backend/tests/test_skillhub_curation.py` 纯逻辑，可用 `PYTEST_NO_APP=1` 快跑。

## 8. 验收标准

- 重启后端后，能力市场「技能」页展示 200+ 官方技能（`is_official=True`、`status=approved`），分类正确，可安装为 `ai_skills`。
- 工具/MCP 页新增补充项，安装即建对应资产。
- 生成脚本可复跑且幂等（重跑不产生重复）。
- `ruff` 通过，既有测试回归通过。

## 9. 非目标（明确不做）

- 不做 skillhub.cn 动态同步/实时搜索（用户已选固化）。
- 不做全量 LLM 翻译（用户已选中文描述+结构抽取）。
- 不接入 skillhub 付费/需密钥技能。
- 不新增后端依赖（生成脚本用标准库 `urllib`，运行时零外部调用）。
