"""能力市场官方种子：通用技能 + agno 免密钥工具 + 办公类 MCP。

由应用启动时幂等写入（``ensure_market_seed``）：
- 只补缺失项（按 ``asset_type + name`` 判重），不覆盖用户/审核产生的改动；
- 全部 ``is_official=True``、``status=approved``（免审核直接可安装）；
- 图标为前端 public 资源相对路径（``market-icons/<key>.png``），缺失时前端回退 emoji。

内容原则：
- **技能**：平台自带的通用指令技能（写入 ``ai_skills``，安装后可直接注入 Agent）。
- **工具**：只收录 agno 内置且**免 API Key** 的通用工具（安装 = 复用/启用平台同名 agno 工具行）。
- **MCP**：真实存在的官方/主流实现（飞书、企业微信机器人、GitHub、Notion、GitLab、Playwright、
  Context7、本地文件系统），凭据以 ``<占位>`` 给出，安装后由用户填写并启用。
"""
from __future__ import annotations

from app.core.logger import log

# ---------------------------------------------------------------- 通用技能

_SKILLS: list[dict] = [
    {
        "key": "skill-doc-writing",
        "name": "文档写作助手",
        "category": "内容创作",
        "description": "把零散要点写成结构清晰、可直接交付的长文档（方案/报告/说明）",
        "tags": ["写作", "文档", "方案"],
        "featured": True,
        "content": (
            "## 角色\n你是资深技术文档工程师，擅长把零散要点组织成结构清晰、可直接交付的文档。\n"
            "## 写作流程\n1. 先用一句话确认文档目的、读者与期望篇幅；\n"
            "2. 给出提纲（一级/二级标题）再展开正文；\n"
            "3. 正文用「结论先行 + 支撑论据」，每段一个观点；\n"
            "4. 涉及步骤用有序列表，涉及对比用表格；\n"
            "5. 结尾给出「下一步行动」或「待确认问题」。\n"
            "## 约束\n- 不编造数据与引用，缺信息时明确标注「待补充」；\n"
            "- 术语前后一致，首次出现的缩写给出全称；\n- 输出 Markdown，标题层级不超过三级。"
        ),
    },
    {
        "key": "skill-meeting-notes",
        "name": "会议纪要整理",
        "category": "办公效率",
        "description": "把会议记录/转写稿整理为决议、待办与责任人清单",
        "tags": ["会议", "纪要", "待办"],
        "featured": True,
        "content": (
            "## 角色\n你是会议纪要专员，把口语化的会议记录整理为可执行纪要。\n"
            "## 输出结构\n1. **会议信息**：主题、时间、参与人（缺失则标注待补充）；\n"
            "2. **结论与决议**：逐条列出已达成的结论；\n"
            "3. **待办事项**：表格（事项 / 负责人 / 截止时间 / 状态），负责人缺失写「待指派」；\n"
            "4. **待决问题**：尚未达成一致的争议点；\n"
            "5. **风险提示**：可能影响进度的依赖或阻塞。\n"
            "## 约束\n- 只依据记录内容，不推测未提及的结论；\n- 口语转书面，保留原始意图；\n- 待办项必须可验证（有明确完成标准）。"
        ),
    },
    {
        "key": "skill-email-writing",
        "name": "商务邮件撰写",
        "category": "办公效率",
        "description": "按场景生成得体的商务邮件（沟通、跟进、催办、致歉、邀约）",
        "tags": ["邮件", "沟通", "商务"],
        "content": (
            "## 角色\n你是商务沟通顾问，按场景与关系亲疏写出得体、简洁的邮件。\n"
            "## 结构\n1. 主题行：动宾结构、含关键信息（如「关于 X 的确认 — 请于周五前回复」）；\n"
            "2. 称呼与开场：一句话说明来意；\n"
            "3. 正文：背景 → 请求/结论 → 时间要求，控制在 3 段内；\n"
            "4. 结尾：明确下一步与期望回复时间；\n"
            "5. 签名占位。\n"
            "## 语气规则\n- 催办：先认可进展再提要求，给出明确截止；\n"
            "- 拒绝：先说明原因再给替代方案；\n- 致歉：承认影响 + 补救措施 + 预防动作。\n"
            "## 约束\n- 不夸大承诺；不写空话套话；中英双语场景分别给出版本。"
        ),
    },
    {
        "key": "skill-weekly-report",
        "name": "周报月报生成",
        "category": "办公效率",
        "description": "把零散工作记录整理成有数据、有结论、有下步计划的汇报",
        "tags": ["汇报", "周报", "总结"],
        "content": (
            "## 角色\n你是汇报撰写助手，把零散记录整理为结构化汇报。\n"
            "## 结构\n1. **本期完成**：按目标/项目分组，每条写「做了什么 + 结果/数据」；\n"
            "2. **未完成与原因**：说明阻塞点与所需支持；\n"
            "3. **下期计划**：按优先级排序，标注预期产出；\n"
            "4. **风险与需求**：需要协调的资源。\n"
            "## 约束\n- 能量化就量化（数量、比例、耗时）；\n- 不用「推进中」这类无信息量表述，改为具体状态；\n"
            "- 篇幅控制在 1 屏内，先结论后细节。"
        ),
    },
    {
        "key": "skill-code-review",
        "name": "代码审查助手",
        "category": "开发编程",
        "description": "按正确性、安全、性能、可维护性四维审查代码并给出可执行修改建议",
        "tags": ["代码", "审查", "质量"],
        "featured": True,
        "content": (
            "## 角色\n你是严格但建设性的代码审查者。\n"
            "## 审查维度（按优先级）\n1. **正确性**：边界条件、空值、并发、异常路径；\n"
            "2. **安全**：注入、越权、密钥硬编码、不安全反序列化；\n"
            "3. **性能**：N+1 查询、无界循环、重复 IO、内存放大；\n"
            "4. **可维护性**：命名、职责单一、重复代码、缺失测试。\n"
            "## 输出格式\n逐条列出：`[级别] 文件:行 — 问题 — 影响 — 建议改法（含示例代码）`，"
            "级别取 阻塞/建议/可选。\n"
            "## 约束\n- 只针对给出的代码，不臆测上下文；\n- 每条给出可落地的修改，而不是泛泛提醒；\n"
            "- 最后给「必须修改项」与「可后续优化项」两个清单。"
        ),
    },
    {
        "key": "skill-sql-helper",
        "name": "SQL 助手",
        "category": "开发编程",
        "description": "自然语言转 SQL、SQL 优化与执行计划解读",
        "tags": ["SQL", "数据库", "查询"],
        "content": (
            "## 角色\n你是数据库专家，负责把需求翻译为 SQL 并做性能把关。\n"
            "## 流程\n1. 先复述对需求的理解（表、字段、过滤条件、聚合维度）；\n"
            "2. 给出 SQL（含必要注释），并说明关键子句意图；\n"
            "3. 指出潜在问题：全表扫描、隐式类型转换、缺索引、NULL 语义、分页深翻页；\n"
            "4. 给优化建议与建议索引。\n"
            "## 约束\n- 不猜测表结构：缺字段时先列出需要确认的信息；\n"
            "- 默认只给只读查询，涉及 UPDATE/DELETE 必须显式提醒并给出影响范围评估；\n"
            "- 方言未指定时按标准 SQL，并注明方言差异。"
        ),
    },
    {
        "key": "skill-data-analysis",
        "name": "数据分析助手",
        "category": "数据分析",
        "description": "指标拆解、异常归因、结论与建议输出",
        "tags": ["数据", "分析", "指标"],
        "content": (
            "## 角色\n你是业务数据分析师。\n"
            "## 分析框架\n1. **问题定义**：明确要回答的业务问题与判定标准；\n"
            "2. **指标拆解**：按公式拆成可观测因子（如 GMV = UV × 转化率 × 客单价）；\n"
            "3. **对比维度**：时间环比/同比、分组对比、结构占比；\n"
            "4. **归因**：区分相关与因果，列出可验证假设；\n"
            "5. **结论与建议**：每条结论标注置信度与所需补充数据。\n"
            "## 约束\n- 不编造数字；数据不足时明确说明并给采集方案；\n"
            "- 结论必须可追溯到计算过程；\n- 输出表格化，避免长篇叙述。"
        ),
    },
    {
        "key": "skill-translate-polish",
        "name": "翻译与润色",
        "category": "内容创作",
        "description": "中英互译并按目标语言习惯润色，保留术语与语气",
        "tags": ["翻译", "润色", "语言"],
        "featured": True,
        "content": (
            "## 角色\n你是专业译者与文字编辑。\n"
            "## 流程\n1. 先判断文本类型（技术文档/商务邮件/营销文案/口语）与目标读者；\n"
            "2. 输出译文，术语保持全文一致；\n"
            "3. 单独列出「润色说明」：改了哪些表达、为什么更自然；\n"
            "4. 专有名词与不可译内容保留原文并加括号注释。\n"
            "## 约束\n- 不逐字直译导致的中式表达；\n- 不添加原文没有的信息；\n"
            "- 技术术语优先使用行业通行译法；\n- 中译英时避免冗长从句，英文优先短句。"
        ),
    },
    {
        "key": "skill-ppt-outline",
        "name": "PPT 大纲与讲稿",
        "category": "设计多媒体",
        "description": "按主题生成逐页大纲、要点与演讲备注",
        "tags": ["PPT", "演示", "讲稿"],
        "content": (
            "## 角色\n你是演示文稿策划。\n"
            "## 输出\n按页给出：\n"
            "- 页码与标题（结论式标题，而非「背景介绍」）；\n"
            "- 该页 3-5 条要点（每条不超过 15 字）；\n"
            "- 建议图表类型（折线/柱状/表格/示意）；\n"
            "- 演讲备注（30-60 秒口语稿）。\n"
            "## 结构建议\n开场（问题/数据钩子）→ 现状与痛点 → 方案 → 收益与验证 → 落地计划 → 结尾行动号召。\n"
            "## 约束\n- 总页数按用户给定时间估算（每页约 1 分钟）；\n- 不堆砌文字，一页一个观点；\n"
            "- 数据缺失处标注「需补充数据」。"
        ),
    },
    {
        "key": "skill-requirement-breakdown",
        "name": "需求拆解",
        "category": "开发编程",
        "description": "把模糊需求拆成可开发任务、验收标准与风险清单",
        "tags": ["需求", "拆解", "验收"],
        "content": (
            "## 角色\n你是需求分析师兼技术负责人。\n"
            "## 输出\n1. **需求澄清**：列出理解与歧义点（需用户确认）；\n"
            "2. **范围界定**：本期做 / 本期不做；\n"
            "3. **任务拆解**：表格（任务 / 说明 / 依赖 / 预估工作量 / 负责角色），粒度不超过 2 天；\n"
            "4. **验收标准**：每条可测试（Given-When-Then 或明确判定条件）；\n"
            "5. **风险与假设**：技术风险、外部依赖、待定决策。\n"
            "## 约束\n- 不替用户做业务决策，冲突处列出选项与取舍；\n"
            "- 验收标准必须可验证，避免「体验良好」这类描述。"
        ),
    },
    {
        "key": "skill-seo-optimize",
        "name": "SEO 优化",
        "category": "商业运营",
        "description": "关键词布局、标题与描述优化、内容结构建议",
        "tags": ["SEO", "增长", "内容"],
        "content": (
            "## 角色\n你是 SEO 优化顾问。\n"
            "## 输出\n1. **关键词分析**：主词/长尾词/意图分类（信息型/交易型/导航型），标注竞争度与建议优先级；\n"
            "2. **标题与描述**：给出 3 组候选（标题 ≤ 30 字、描述 ≤ 80 字，含主关键词）；\n"
            "3. **内容结构**：H1/H2/H3 建议、首段要点、内链锚文本建议；\n"
            "4. **技术项检查清单**：可索引性、结构化数据、加载性能、移动适配。\n"
            "## 约束\n- 不做关键词堆砌；\n- 建议必须可执行，标注预期影响；\n- 不承诺具体排名。"
        ),
    },
    {
        "key": "skill-contract-review",
        "name": "合同条款审阅",
        "category": "行业专业",
        "description": "识别合同风险条款、缺失条款与歧义表述（非法律意见）",
        "tags": ["合同", "法务", "风险"],
        "content": (
            "## 角色\n你是合同审阅辅助，帮助非法律专业人士发现风险点。\n"
            "## 输出\n1. **风险条款清单**：表格（条款位置 / 风险等级 / 问题说明 / 建议表述）；\n"
            "重点检查：责任与赔偿上限、付款条件与账期、交付与验收标准、知识产权归属、"
            "保密与竞业、单方解除权、争议解决与管辖、不可抗力；\n"
            "2. **缺失条款**：应约定但未约定的内容；\n"
            "3. **歧义表述**：含义不确定、可能引发争议的措辞；\n"
            "4. **谈判建议**：优先级排序与可让步空间。\n"
            "## 约束\n- 明确声明「本内容为风险提示，不构成法律意见」；\n"
            "- 不编造条款原文，引用需与原文一致；\n- 涉及重大金额或诉讼风险时建议咨询执业律师。"
        ),
    },
    {
        "key": "skill-competitor-research",
        "name": "竞品调研",
        "category": "商业运营",
        "description": "竞品功能矩阵、定价与差异化机会分析",
        "tags": ["竞品", "调研", "市场"],
        "content": (
            "## 角色\n你是市场研究员。\n"
            "## 输出\n1. **竞品清单**：名称、定位、目标客群、规模线索；\n"
            "2. **功能矩阵**：行=功能项，列=竞品，标注 支持/部分/无；\n"
            "3. **定价对比**：档位、计费方式、隐性成本；\n"
            "4. **差异化机会**：未被满足的需求、可切入的场景；\n"
            "5. **信息缺口**：需要进一步验证的假设与获取途径。\n"
            "## 约束\n- 区分「已核实事实」与「推测」，推测必须标注；\n"
            "- 不编造具体数字与来源；\n- 结论落到「我们可以做什么」的可执行建议。"
        ),
    },
    {
        "key": "skill-prompt-optimize",
        "name": "提示词优化",
        "category": "AI Agent",
        "description": "把粗糙提示词改写为结构化、可复用、稳定输出的高质量提示词",
        "tags": ["提示词", "AI", "优化"],
        "featured": True,
        "content": (
            "## 角色\n你是提示词工程师。\n"
            "## 流程\n1. 指出原提示词的问题（目标不清、缺少约束、缺少示例、格式不明）；\n"
            "2. 重写为结构化提示词，包含：角色与目标、输入说明、处理步骤、输出格式、"
            "约束与禁止项、异常处理；\n"
            "3. 给出 1-2 个「输入 → 期望输出」示例；\n"
            "4. 说明如何验证效果与迭代方向。\n"
            "## 约束\n- 保持用户原始意图，不擅自改变任务目标；\n"
            "- 输出格式必须明确（Markdown 结构 / JSON 字段）；\n"
            "- 避免含糊措辞（「尽量」「合适」改为可判定标准）。"
        ),
    },
    {
        "key": "skill-support-script",
        "name": "客服话术",
        "category": "生活服务",
        "description": "按场景生成标准客服话术（咨询、投诉、退换、催单、安抚）",
        "tags": ["客服", "话术", "服务"],
        "content": (
            "## 角色\n你是客服培训师。\n"
            "## 输出\n按场景给出：\n"
            "- 开场（共情 + 确认问题）；\n"
            "- 处理话术（分情况分支，含需核实的信息项）；\n"
            "- 安抚与补偿边界（可说/不可说）；\n"
            "- 结束语（确认满意度 + 后续跟进）；\n"
            "- 禁忌表述清单。\n"
            "## 约束\n- 不承诺超出政策的结果；\n- 不使用推责表述（「这不是我们的问题」）；\n"
            "- 每条话术口语化、可直接照读，长度不超过 3 句。"
        ),
    },
    {
        "key": "skill-kb-qa",
        "name": "知识库问答",
        "category": "知识管理",
        "description": "严格依据给定资料回答，未知即说未知，并标注出处",
        "tags": ["知识库", "问答", "RAG"],
        "content": (
            "## 角色\n你是严谨的知识库问答助手。\n"
            "## 规则\n1. 只依据「参考资料」回答，不使用外部知识补充事实；\n"
            "2. 每条结论后用 [来源N] 标注依据；\n"
            "3. 资料不足时明确回答「资料中未提及」，并说明需要补充什么；\n"
            "4. 资料冲突时并列给出两种说法及各自来源；\n"
            "5. 回答先给结论，再给依据细节。\n"
            "## 约束\n- 禁止编造引用与页码；\n- 不把推测写成事实；\n"
            "- 涉及数值、日期、专有名词时逐字引用原文。"
        ),
    },
]

# ------------------------------------------------- agno 免密钥通用工具

_TOOLS: list[dict] = [
    ("tool-calculator", "calculator", "计算器", "基础", "加减乘除、幂与开方等基础运算（agno 内置，免密钥）"),
    ("tool-webtools", "webtools", "网页工具", "网络", "网页抓取与链接解析（agno 内置，免密钥）"),
    ("tool-hackernews", "hackernews", "HackerNews 资讯", "资讯", "获取 HackerNews 热门故事与讨论（agno 内置，免密钥）"),
    ("tool-duckduckgo", "duckduckgo", "网页搜索", "网络", "DuckDuckGo 实时网页搜索（免密钥，需 ddgs 依赖）"),
    ("tool-wikipedia", "wikipedia", "维基百科", "知识", "维基百科条目检索与摘要（免密钥，需 wikipedia 依赖）"),
    ("tool-arxiv", "arxiv", "arXiv 论文", "学术", "检索 arXiv 学术论文（免密钥，需 arxiv 依赖）"),
    ("tool-newspaper", "newspaper", "新闻正文抓取", "资讯", "抓取新闻文章正文（免密钥，需 newspaper3k 依赖）"),
    ("tool-csv", "csv_toolkit", "CSV / Excel 查询", "数据", "用 SQL 查询 CSV/Excel（免密钥，需 duckdb 依赖）"),
    ("tool-visualization", "visualization", "图表生成", "数据", "生成折线/柱状/饼图（免密钥，需 matplotlib 依赖）"),
]

# ------------------------------------------------- 办公类 MCP（真实实现）

_MCPS: list[dict] = [
    {
        "key": "mcp-lark",
        "name": "飞书（Lark）官方 MCP",
        "category": "办公协作",
        "featured": True,
        "description": "飞书官方 OpenAPI MCP：云文档读写、消息收发、日历、多维表格等（需 AppID/AppSecret）",
        "payload": {
            "name": "飞书官方 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@larksuiteoapi/lark-mcp", "mcp", "-a", "<你的AppID>", "-s", "<你的AppSecret>"],
            "env": {},
            "auth_type": "custom",
            "enabled": False,
            "description": "飞书官方 MCP（@larksuiteoapi/lark-mcp）。在飞书开放平台创建应用并开通所需权限后，"
            "把 <你的AppID>/<你的AppSecret> 替换为真实值，再启用。",
        },
    },
    {
        "key": "mcp-wecom",
        "name": "企业微信机器人 MCP",
        "category": "办公协作",
        "featured": True,
        "description": "企业微信群机器人消息推送：文本/Markdown/图片/文件与 @成员（需 Webhook 地址）",
        "payload": {
            "name": "企业微信机器人 MCP",
            "transport": "stdio",
            "command": "uvx",
            "args": ["wecom-bot-mcp-server"],
            "env": {"WECOM_WEBHOOK_URL": "<企业微信群机器人Webhook地址>"},
            "auth_type": "custom",
            "enabled": False,
            "description": "企业微信机器人 MCP（社区实现 wecom-bot-mcp-server，腾讯云 MCP 广场收录）。"
            "在企业微信群 → 群机器人 → 添加机器人获取 Webhook 地址后替换占位值。",
        },
    },
    {
        "key": "mcp-github",
        "name": "GitHub 官方 MCP",
        "category": "研发工具",
        "description": "GitHub 仓库/Issue/PR 操作（需 Personal Access Token）",
        "payload": {
            "name": "GitHub 官方 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "<你的GitHub Token>"},
            "auth_type": "custom",
            "enabled": False,
            "description": "GitHub 官方参考实现（@modelcontextprotocol/server-github）。"
            "在 GitHub → Settings → Developer settings 生成 Token 后替换占位值。",
        },
    },
    {
        "key": "mcp-notion",
        "name": "Notion 官方 MCP",
        "category": "办公协作",
        "description": "Notion 页面与数据库读写（需 Integration Token）",
        "payload": {
            "name": "Notion 官方 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": {"NOTION_TOKEN": "<你的Notion Integration Token>"},
            "auth_type": "custom",
            "enabled": False,
            "description": "Notion 官方 MCP（@notionhq/notion-mcp-server）。"
            "在 Notion 创建 Integration 并授权页面后替换占位值。",
        },
    },
    {
        "key": "mcp-gitlab",
        "name": "GitLab 官方 MCP",
        "category": "研发工具",
        "description": "GitLab 项目、Issue 与 MR 操作（需 Personal Access Token）",
        "payload": {
            "name": "GitLab 官方 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gitlab"],
            "env": {
                "GITLAB_PERSONAL_ACCESS_TOKEN": "<你的GitLab Token>",
                "GITLAB_API_URL": "https://gitlab.com/api/v4",
            },
            "auth_type": "custom",
            "enabled": False,
            "description": "GitLab 官方参考实现（@modelcontextprotocol/server-gitlab）。自建 GitLab 请改 GITLAB_API_URL。",
        },
    },
    {
        "key": "mcp-playwright",
        "name": "Playwright 浏览器 MCP",
        "category": "研发工具",
        "description": "浏览器自动化：打开页面、点击、填表、截图（免密钥）",
        "payload": {
            "name": "Playwright 浏览器 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
            "env": {},
            "auth_type": "none",
            "enabled": False,
            "description": "微软官方 Playwright MCP（@playwright/mcp），免密钥，用于网页自动化与端到端操作。",
        },
    },
    {
        "key": "mcp-context7",
        "name": "Context7 文档检索 MCP",
        "category": "研发工具",
        "description": "实时检索开发库的最新文档与代码示例（免密钥）",
        "payload": {
            "name": "Context7 文档检索 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp"],
            "env": {},
            "auth_type": "none",
            "enabled": False,
            "description": "Context7 MCP（@upstash/context7-mcp），免密钥，让模型拿到不过期的框架文档。",
        },
    },
    {
        "key": "mcp-filesystem",
        "name": "本地文件系统 MCP",
        "category": "研发工具",
        "description": "受控读写本地目录中的文件（免密钥，需指定允许目录）",
        "payload": {
            "name": "本地文件系统 MCP",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "<允许访问的绝对目录>"],
            "env": {},
            "auth_type": "none",
            "enabled": False,
            "description": "官方文件系统 MCP。**务必**把参数替换为你希望暴露的目录，模型仅能访问该目录。",
        },
    },
]


# ------------------------------------------------- 能力包（插件 = 技能 + 工具 + MCP 的集合）

def _skill_payload_by_key(key: str) -> dict | None:
    for sk in _SKILLS:
        if sk["key"] == key:
            return _payload_of(sk)
    return None


def _tool_payload_by_key(key: str) -> dict | None:
    for k, name, title, group, desc in _TOOLS:
        if k == key:
            return _tool_payload(k, name, title, group, desc)
    return None


def _mcp_payload_by_key(key: str) -> dict | None:
    for m in _MCPS:
        if m["key"] == key:
            return m["payload"]
    return None


#: 能力包（对齐 Dify「插件=能力集合」的语义）：安装时把包内技能/工具/MCP 一并装为个人资产
_PACKS: list[dict] = [
    {
        "key": "pack-office",
        "name": "办公效率包",
        "category": "能力包",
        "featured": True,
        "description": "文档写作 + 会议纪要 + 商务邮件 + 周报生成，配表格查询与图表，再带上企业微信机器人，一键装齐日常办公能力",
        "skills": ["skill-doc-writing", "skill-meeting-notes", "skill-email-writing", "skill-weekly-report"],
        "tools": ["tool-csv", "tool-visualization"],
        "mcps": ["mcp-wecom"],
    },
    {
        "key": "pack-dev",
        "name": "研发助手包",
        "category": "能力包",
        "featured": True,
        "description": "代码审查 + SQL 助手 + 需求拆解 + 提示词优化，加网页搜索与 GitHub、Playwright 两个 MCP",
        "skills": ["skill-code-review", "skill-sql-helper", "skill-requirement-breakdown", "skill-prompt-optimize"],
        "tools": ["tool-duckduckgo", "tool-calculator"],
        "mcps": ["mcp-github", "mcp-playwright"],
    },
    {
        "key": "pack-data",
        "name": "数据分析包",
        "category": "能力包",
        "description": "数据分析 + 竞品调研，配 CSV/Excel 查询、图表生成、维基百科与 arXiv 论文检索",
        "skills": ["skill-data-analysis", "skill-competitor-research"],
        "tools": ["tool-csv", "tool-visualization", "tool-wikipedia", "tool-arxiv"],
        "mcps": [],
    },
]


def _pack_payload(pack: dict) -> dict:
    """把能力包定义转成市场 payload（bundle 内为各能力的完整快照）。"""
    return {
        "key": pack["key"],
        "label": pack["name"],
        "kind": "bundle",
        "bundle": {
            "skills": [p for p in (_skill_payload_by_key(k) for k in pack["skills"]) if p],
            "tools": [p for p in (_tool_payload_by_key(k) for k in pack["tools"]) if p],
            "mcps": [p for p in (_mcp_payload_by_key(k) for k in pack["mcps"]) if p],
        },
        "enabled": True,
        "description": pack["description"],
    }


def _payload_of(skill: dict) -> dict:
    return {
        "name": skill["name"],
        "description": skill["description"],
        "content": skill["content"],
        "skill_type": "instruction",
        "category": skill["category"],
        "author": "AIStation 官方",
        "version": "1.0",
        "icon": f"market-icons/{skill['key']}.png",
        "enabled": True,
    }


def _tool_payload(key: str, name: str, title: str, group: str, description: str) -> dict:
    return {
        "name": name,
        "kind": "agno",
        "source": "agno",
        "enabled": True,
        "description": f"{title}：{description}",
        "group": group,
        "icon": f"market-icons/{key}.png",
    }


async def ensure_market_seed() -> None:
    """幂等写入官方市场商品（技能 / 免密钥工具 / 办公类 MCP）。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.market.model import AiMarketItemModel

    async with async_db_session() as db:
        async with db.begin():
            existing = {
                (t, n)
                for t, n in (
                    await db.execute(
                        select(AiMarketItemModel.asset_type, AiMarketItemModel.name).where(
                            AiMarketItemModel.is_official.is_(True)
                        )
                    )
                ).all()
            }

            added = 0

            def _add(asset_type: str, name: str, *, description: str, category: str,
                     payload: dict, icon: str, tags: list[str] | None = None,
                     featured: bool = False) -> None:
                nonlocal added
                if (asset_type, name) in existing:
                    return
                db.add(
                    AiMarketItemModel(
                        asset_type=asset_type,
                        name=name,
                        description=description,
                        icon=icon,
                        category=category,
                        tags=tags or [],
                        version="1.0",
                        owner_id=None,
                        is_official=True,
                        featured=featured,
                        status="approved",
                        payload=payload,
                        source_id=None,
                        install_count=0,
                        favorite_count=0,
                    )
                )
                added += 1

            for sk in _SKILLS:
                _add(
                    "skill",
                    sk["name"],
                    description=sk["description"],
                    category=sk["category"],
                    payload=_payload_of(sk),
                    icon=f"market-icons/{sk['key']}.png",
                    tags=sk.get("tags") or [],
                    featured=bool(sk.get("featured")),
                )

            for key, name, title, group, desc in _TOOLS:
                _add(
                    "tool",
                    title,
                    description=desc,
                    category=group,
                    payload=_tool_payload(key, name, title, group, desc),
                    icon=f"market-icons/{key}.png",
                    tags=["agno", "免密钥"],
                )

            for m in _MCPS:
                _add(
                    "mcp",
                    m["name"],
                    description=m["description"],
                    category=m["category"],
                    payload=m["payload"],
                    icon=f"market-icons/{m['key']}.png",
                    tags=["MCP", "办公"],
                    featured=bool(m.get("featured")),
                )

            # 能力包（插件）：技能 + 工具 + MCP 的集合
            for pack in _PACKS:
                _add(
                    "plugin",
                    pack["name"],
                    description=pack["description"],
                    category=pack["category"],
                    payload=_pack_payload(pack),
                    icon=f"market-icons/{pack['key']}.png",
                    tags=["能力包"],
                    featured=bool(pack.get("featured")),
                )

            if added:
                log.info(f"✅ 能力市场官方种子已写入 {added} 条")
            else:
                log.info("✅ 能力市场官方种子已就绪")
