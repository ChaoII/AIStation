# skillhub.cn 技能精选固化 —— 实现计划

日期：2026-10-16
依据设计文档：`docs/superpowers/specs/2026-10-16-skillhub-skill-curation-design.md`
执行者：未见过本代码库的工程师。保持项目惯例（包结构、命名、4 空格缩进、ruff 配置、中文注释/提交信息）。

## 已核实的关键事实（实现前必读）

1. **API**：
   - 列表 `GET /api/skills?labels=requires_api_key:false&sortBy=score&order=desc&pageSize=100&page=N`，返回 `{code:0,data:{skills:[...],total}}`，每项含 `name`、`description`、`description_zh`、`category`、`labels`、`score`、`downloads`、`slug`、`namespace.displayName`。
   - 详情 `GET /api/v1/skills/{slug}` 含 `skill.category`、`skill.displayName`、`skill.stats`、`skill.tags`、`skill.labels`、`skill.securityReports`（`keen/sanbu` 两项 `status`，非 `benign` 即风险）、`skill.subCategories`。
   - 文件 `GET /api/v1/skills/{slug}/files` 返回 `{files:[{path:'SKILL.md',...}]}`；正文 `GET /api/v1/skills/{slug}/file?path=SKILL.md`（自动跟随 302）。
   - **注意**：详情接口没有 `description_zh`（只有 `summary_zh`，clawhub 技能其为英文）；`description_zh` 只在列表项里，必须以列表项为准带进 content 组装。
2. **seed.py**：顶部仅 `from app.core.logger import log`（轻量）；`ensure_market_seed()` 内含 `_add`，按 `(asset_type, name)` 去重、`is_official=True`/`status=approved`。`_payload_of(skill)` 目前把 `icon` 写死为 `market-icons/{key}.png`。`_MCP_DOCS` 是 `key→docs url` 字典；`_MCPS` 已有 21 项，`mcp-time` 不在其中。
3. **前端 IconTile**（`frontend/src/views/module_ai/market/components/IconTile.vue`）：`icon` 为 http(s)、图片扩展名或 `market-icons/` 前缀 → 渲染 `<img>`；否则渲染 `emoji = icon || FALLBACK[asset_type]`。故设 `icon` 为**分类 emoji**（如 `✍️`/`💻`）既能当彩色图标、又离线不裂图。`_add` 的 `icon` 入参直接写进商品行，payload 图标由 `_payload_of` 决定。
4. **图标决策（重要）**：不要设 `icon="market-icons/skillhub-xxx.png"`（会渲染成 404 裂图）。应设 `icon` 为分类 emoji（真值 → `_add` 的 `sk.get("icon") or ""` 取到 emoji；`_payload_of` 的 None 判断取到 emoji）。`_payload_of` 改为：`skill.get("icon") if skill.get("icon") is not None else f"market-icons/{skill['key']}.png"`（既有技能无 `icon` 键 → None → 保持默认路径；skillhub 技能有 `icon` 键=emoji → 用 emoji）。
5. **测试快速模式**：纯逻辑用例可 `PYTEST_NO_APP=1` 跑，约 2 秒。本特性的数据/纯函数测试不触碰应用构造，属快速用例。
6. **生成脚本可直连**：已实测 shell 内 `backend\.venv\Scripts\python.exe` 用标准库 `urllib` 可 GET 到 `api.skillhub.cn`。生成脚本用标准库，零新增依赖。

## 文件清单（新增 / 修改）

**新增**
- `backend/app/plugin/module_ai/market/skillhub_curation.py` —— 纯函数（可单测）。
- `backend/app/plugin/module_ai/market/skillhub_skills.py` —— 生成的数据（`SKILLHUB_SKILLS`），由脚本产出。
- `backend/scripts/_generate_skillhub_skills.py` —— 一键生成脚本。
- `backend/tests/test_skillhub_curation.py` —— 测试。

**修改**
- `backend/app/plugin/module_ai/market/seed.py` —— `_payload_of` 图标判断 + `ensure_market_seed` 追加 skillhub 技能 + 模块 docstring + 补 `mcp-time` 到 `_MCPS`/`_MCP_DOCS`。

## 关键接口（纯函数，供脚本/测试使用）

模块 `app.plugin.module_ai.market.skillhub_curation` 导出：

- `CATEGORY_MAP: dict[str, str]`（见设计 §5）
- `CATEGORY_EMOJI: dict[str, str]`（平台分类 → emoji）
- `map_category(category_key: str) -> str`（未知回退 `"通用"`）
- `category_emoji(category: str) -> str`（未知回退 `"🧩"`）
- `has_cjk(text: str) -> bool`
- `clean_display_name(name: str) -> str`（去 `.Skill`/`.SKILL` 后缀、两端空白、折叠空格）
- `extract_sections(md: str) -> dict[str, str]`（按小节关键词抽取，键为中文小节名：`工作流`/`关键要点`/`输出格式`/`触发场景`）
- `build_skill_content(*, source_slug: str, description_zh: str, sk_md: str, license: str | None = None) -> str`（组装 + 长度上限 `MAX_CONTENT_LEN = 2000`）

数据模块 `app.plugin.module_ai.market.skillhub_skills` 导出：
- `SKILLHUB_SKILLS: list[dict]`，每项：`{key, name, category, description, tags, content, featured, icon, source, source_slug, license}`。

---

# 任务

## 任务 1 —— 纯函数模块 + 单元测试

先写测试 `backend/tests/test_skillhub_curation.py`，再实现 `skillhub_curation.py` 使测试通过。

**测试内容**（`test_skillhub_curation.py`）：
- `map_category("content-creation") == "内容创作"`；对设计 §5 全表每个 key 断言映射正确；`map_category("zzz") == "通用"`；`map_category("pay-skill")` → 仍返回 `"通用"`（脚本在调用前已排除 pay-skill，但函数不抛错）。
- `category_emoji("内容创作") == "✍️"`；`category_emoji("开发编程") == "💻"`；`category_emoji("通用") == "🧩"`。
- `has_cjk("中文文本abc") is True`；`has_cjk("english only") is False`；`has_cjk("") is False`。
- `clean_display_name("编程大神.Skill") == "编程大神"`；`clean_display_name("防骗大师.SKILL") == "防骗大师"`；`clean_display_name("  Content  Writer  ") == "Content Writer"`。
- `extract_sections`：给定含 `## Workflow`+`- step1\n- step2`、`## Guidelines`+`- g1\n- g2`、`## 输出格式`+`- md` 的 SKILL.md，返回 `{"工作流":"- step1\n- step2\n","关键要点":"- g1\n- g2\n","输出格式":"- md\n"}`（`触发场景` 缺失则不在结果里）。
  - 中文标题 `## 流程` 也能命中 `工作流`。
- `build_skill_content`：
  - 传入 `description_zh="生成小红书笔记"`、`sk_md` 含 Workflow/Guidelines、`source_slug="content-writer"`、`license="MIT"`：结果含 `## 角色 / 目标` 与 `生成小红书笔记`、`## 工作流` 与 step、`## 关键要点` 与 guideline、`## 来源` 与 `content-writer`、`MIT`。
  - 无 Guidelines 时结果**不含** `## 关键要点`；无 Workflow 时 `## 工作流` 下为占位 `（未提供，请结合目标判断）`。
  - 构造超过 `MAX_CONTENT_LEN` 的输入 → 结果 `len <= MAX_CONTENT_LEN`。

**实现** `skillhub_curation.py`，`exclude`：`MAX_CONTENT_LEN = 2000`、`CATEGORY_MAP`、`CATEGORY_EMOJI`、`map_category`、`category_emoji`、`has_cjk`、`clean_display_name`、`_SECTION_KEYWORDS`（中英文关键词映射）、`extract_sections`（用正则按 `^#{2,3}\s*` 分节，命中关键词取该节正文，保留 bullet；贪心到下一个同/更低级标题）、`build_skill_content`（按设计 §4 模板组装；`角色` 取 `description_zh` 清理控制符后截断 400 字；`来源` 含 slug + license；超长截断）。

**运行**：`cd backend && PYTEST_NO_APP=1 .\.venv\Scripts\python.exe -m pytest tests\test_skillhub_curation.py -q`（应绿）。再 `ruff check app/plugin/module_ai/market/skillhub_curation.py tests/test_skillhub_curation.py`。

**提交**：`git add` 上述两文件 → `feat(skillhub): 技能精选纯函数与单元测试`。

---

## 任务 2 —— 数据模块形状断言（TDD 锚点）

- 创建 `backend/app/plugin/module_ai/market/skillhub_skills.py`，先只放：
  ```python
  """由 scripts/_generate_skillhub_skills.py 生成，勿手改。"""
  from __future__ import annotations
  SKILLHUB_SKILLS: list[dict] = []
  ```
- 在 `test_skillhub_curation.py` 增加：
  ```python
  from app.plugin.module_ai.market.skillhub_skills import SKILLHUB_SKILLS
  from app.plugin.module_ai.market.seed import _SKILLS
  from app.plugin.module_ai.market.skillhub_curation import has_cjk

  def test_skillhub_skills_shape():
      assert len(SKILLHUB_SKILLS) >= 200
      keys: set[str] = set(); names: set[str] = set()
      builtin = {s["name"] for s in _SKILLS}
      for s in SKILLHUB_SKILLS:
          for f in ("name", "description", "content", "category"):
              assert s[f]
          assert has_cjk(s["content"])
          assert s["key"] not in keys and s["name"] not in names
          assert s["name"] not in builtin
          assert s["icon"]                       # 非空（分类 emoji）
          keys.add(s["key"]); names.add(s["name"])
  ```
- 运行该测试（应**红**：`len == 0 < 200`）——作为生成步骤的 TDD 锚点。

**提交**：`git add` 数据占位模块 + 测试 → `test(skillhub): 技能数据集形状断言（数据未生成，先行锚定）`。

---

## 任务 3 —— 一键生成脚本

创建 `backend/scripts/_generate_skillhub_skills.py`：

- 顶部 `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`（其它 scripts 同款惯例，把 backend 根加入，能 `import app`）。
- `from app.plugin.module_ai.market.skillhub_curation import build_skill_content, category_emoji, clean_display_name, has_cjk, map_category`
- `from app.plugin.module_ai.market.seed import _SKILLS`（用于撞名去重；seed 顶部只 import log，轻量安全）。
- 依赖：标准库 `urllib.request`、`json`、`time`、`os`、`sys`、`argparse`。**不新增项目依赖**。
- `fetch_json(url, retries=3, timeout=30)`：设 `User-Agent`、`Accept: application/json`；处理 `429/5xx` 指数退避重试（`time.sleep(2**attempt)`）；源码 str 需带 `errors="replace"`。
- `collect_candidates(max_pages=15)`：分页拉列表（`pageSize=100`），累计候选；返回原始 list 项。
- `is_usable(c)`：
  - `category != "pay-skill"`；
  - `(c.get("labels") or {}).get("requires_api_key") != "true"`；
  - `(c.get("labels") or {}).get("pricing_type") != "paid"`；
  - `has_cjk(c.get("description_zh") or "")`；
  - `c.get("slug")`；
  - `score > 0`。
- `select_skills(candidates, limit)`：
  - 过滤 `is_usable`；
  - 按规范化名去重（`clean_display_name(c["namespace"]["displayName"] or c["name"])`），保留 `score` 最高者；
  - 丢弃与 `{clean_display_name(s["name"]) for s in _SKILLS}` 交集的项（撞名）；
  - 按 `score` 降序返回。
- `fetch_skill(slug, cand)`：
  - 详情 `GET /api/v1/skills/{slug}` → 若 `securityReports` 存在且任一 `status != "benign"` → 返回 `None`（风险剔除）；
  - `files` → 找 `path == "SKILL.md"`；无则返回 `None`；
  - `file?path=SKILL.md` → 原文 `sk_md`；
  - `description_zh = cand["description_zh"]`（列表项为唯一中文描述来源）；
  - `license`：从 `sk_md` frontmatter 的 `license:` 行提取，否则 `None`；
  - `content = build_skill_content(source_slug=slug, description_zh=..., sk_md=sk_md, license=license)`；
  - 组装 dict：`key=f"skillhub-{slug}"`、`name=cand["namespace"]["displayName"] or cand["name"]`、`category=map_category(cand["category"])`、`description=(cand["description_zh"] or cand["description"])[:200]`、`tags=(list((cand.get("tags") or {}).keys()) or [])[:5] + ["skillhub"]`、`content`、`featured=False`、`icon=category_emoji(category)`、`source="skillhub.cn"`、`source_slug=slug`、`license`。
- `main()`：
  - argparse：`--limit`（默认 200）、`--out`（默认 `app/plugin/module_ai/market/skillhub_skills.py`）。
  - 收集 → 精选 → 逐个 `fetch_skill`，成功则 append，达到 `limit` 停止；拉取间 `time.sleep(0.2)`。
  - 唯一性兜底：跳过 `key`/规范化名重复。
  - 生成 `.py`：文件头注释（勿手改）+ `from __future__ import annotations` + `SKILLHUB_SKILLS: list[dict] = [` + `json.dumps(..., ensure_ascii=False, indent=2)` 逐项 + `]`；写文件（utf-8）。
  - 打印 `✅ 写入 N 项技能`；若 `len(SKILLHUB_SKILLS) < limit` 打印警告。

**提交**：`git add scripts/_generate_skillhub_skills.py` → `feat(skillhub): skillhub 精选生成脚本`。

---

## 任务 4 —— 运行生成脚本，固化 200+ 数据

- 运行：`cd backend && .\.venv\Scripts\python.exe scripts\_generate_skillhub_skills.py --limit 200`
- 确认输出文件存在且 `SKILLHUB_SKILLS` 条数 ≥ 200（脚本会打印）。
- 跑测试：`PYTEST_NO_APP=1 .\.venv\Scripts\python.exe -m pytest tests\test_skillhub_curation.py -q`（应**绿**，任务 2 的红转绿）。
- `ruff check app/plugin/module_ai/market/skillhub_skills.py`，若有告警用 `ruff check --fix` 修（E501/W293 已忽略，生成的 dict 基本干净）。

**提交**：`git add app/plugin/module_ai/market/skillhub_skills.py` → `feat(skillhub): 生成并固化 200+ skillhub 精选技能数据集`。

---

## 任务 5 —— 接入 seed.py + 补 mcp-time

修改 `backend/app/plugin/module_ai/market/seed.py`：

1. 模块 docstring 第 2 段补一句「另含 skillhub.cn 精选固化技能（`market/skillhub_skills.py`，生成脚本产出）」。
2. 顶部 import 区加 `from app.plugin.module_ai.market.skillhub_skills import SKILLHUB_SKILLS`。
3. `_payload_of` 图标行改为：
   ```python
   "icon": skill.get("icon") if skill.get("icon") is not None else f"market-icons/{skill['key']}.png",
   ```
4. `ensure_market_seed` 在 `for sk in _SKILLS:` 循环后追加：
   ```python
   for sk in SKILLHUB_SKILLS:
       _add(
           "skill",
           sk["name"],
           description=sk["description"],
           category=sk["category"],
           payload=_payload_of(sk),
           icon=sk.get("icon") or "",
           tags=sk.get("tags") or [],
           featured=bool(sk.get("featured")),
       )
   ```
5. `_MCPS` 追加 `mcp-time`（官方无密钥参考实现）：`{"key":"mcp-time","name":"时间/时区 MCP","category":"研发工具","description":"获取当前时间、时区与世界时钟（官方参考实现，免密钥）","payload":{"name":"时间/时区 MCP","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-time"],"env":{},"auth_type":"none","enabled":False,"description":"官方 @modelcontextprotocol/server-time，免密钥，用于时间/时区/世界时钟。"}}`。`_MCP_DOCS` 加 `"mcp-time": "https://github.com/modelcontextprotocol/servers/tree/main/src/time"`。
6. 验证 import 无循环、种子代码可加载：
   `cd backend && .\.venv\Scripts\python.exe -c "import app.plugin.module_ai.market.seed as s; from app.plugin.module_ai.market.skillhub_skills import SKILLHUB_SKILLS; print('seed ok, skillhub items =', len(SKILLHUB_SKILLS))"`
7. `ruff check app/plugin/module_ai/market/seed.py`。

**提交**：`git add app/plugin/module_ai/market/seed.py` → `feat(skillhub): 能力市场种子接入 skillhub 精选技能与时间 MCP`。

---

## 任务 6 —— 回归与格式校验

- `PYTEST_NO_APP=1 .\.venv\Scripts\python.exe -m pytest tests\test_skillhub_curation.py -q`（绿）。
- `ruff check` 本次涉及文件（`skillhub_curation.py`、`skillhub_skills.py`、`seed.py`、`_generate_skillhub_skills.py`、`test_skillhub_curation.py`）。
- 确认已提交 5 个 commit，工作区无残留改动（`git status --short` 仅剩与本特性无关的既有脏文件）。

**说明**：本特性不改 Agent 模板/其它模块，无需跑全量；能触及的应用启动种子逻辑已通过 import + 数据形状测试间接验证。若时间允许，补跑 `PYTEST_NO_APP=1 pytest tests/test_agent_market.py -q` 作为回归（不依赖市场种子计数）。

**提交**：仅当校验产生改动时提交，否则不提交。

---

## 任务 7 —— 收尾

- 停掉后台服务（后端 8002 `sh_143bd80190012SXX9kdSIbmP2S`、前端 5181 `sh_143bd8019002tROiA5MiUTygAd`）——若仍在运行。
- 汇总：新增/修改文件、commit 清单、验收对照（200+ 技能、分类 emoji、安装为 ai_skills、mcp-time、离线可用）。

## 验收对照

- [ ] `SKILLHUB_SKILLS` ≥ 200，每个 `content` 含中文、字段齐全、不撞名内置技能。
- [ ] `test_skillhub_curation.py` 全绿（快速模式）。
- [ ] `ensure_market_seed` 会以 `is_official=True`/`status=approved` 写入 200+ 技能与 `mcp-time`；重跑幂等（`_add` 按名去重）。
- [ ] 图标为分类 emoji，前端 `skill` 类型卡展示 emoji、离线不裂图。
- [ ] 生成脚本可复跑，`--limit` 可调；数据文件入库，运行时零外部调用。
- [ ] 无新增依赖、无 DB 迁移。
