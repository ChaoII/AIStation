"""Agno 精选工具注册表（离线安全 + 联网精选，仅收录常用工具）。

每个条目为「工具集（toolkit）」：
- ``key``：唯一键，也是 ``ai_tools`` 行的 ``name``（用户开关/配置的单元）。
- ``module`` / ``class_name``：Agno 真实模块与类名（已按 2.5.8 探测核对）。
- ``requires``：可选**导入模块名**（供 ``importlib.util.find_spec`` 探测）；缺失时标记「未就绪」。
- ``pip_name``：可选 pip 分发名，仅用于提示文案（与导入名不同的包才有）。
- ``config_fields``：前端自动生成配置表单的字段声明。
- ``group`` / ``risk`` / ``description``：分组、风险级别与简介。
"""
from __future__ import annotations

AGNO_CATALOG: list[dict] = [
    {
        "key": "calculator",
        "title": "计算器",
        "module": "agno.tools.calculator",
        "class_name": "CalculatorTools",
        "requires": None,
        "config_fields": [],
        "group": "基础",
        "risk": "low",
        "description": "加减乘除、阶乘、开方等基础运算",
    },
    {
        "key": "csv_toolkit",
        "title": "CSV 工具",
        "module": "agno.tools.csv_toolkit",
        "class_name": "CsvTools",
        "requires": "duckdb",
        "config_fields": [],
        "group": "数据",
        "risk": "low",
        "description": "用 SQL 查询 CSV/Excel 文件（依赖 DuckDB）",
    },
    {
        "key": "visualization",
        "title": "图表可视化",
        "module": "agno.tools.visualization",
        "class_name": "VisualizationTools",
        "requires": "matplotlib",
        "config_fields": [],
        "group": "数据",
        "risk": "low",
        "description": "生成折线、柱状、饼图等图表",
    },
    {
        "key": "webtools",
        "title": "网页工具",
        "module": "agno.tools.webtools",
        "class_name": "WebTools",
        "requires": None,
        "config_fields": [],
        "group": "网络",
        "risk": "low",
        "description": "网页抓取与链接解析（expand_url 等）",
    },
    {
        "key": "hackernews",
        "title": "HackerNews",
        "module": "agno.tools.hackernews",
        "class_name": "HackerNewsTools",
        "requires": None,
        "config_fields": [],
        "group": "资讯",
        "risk": "low",
        "description": "获取 HackerNews 热门故事与用户信息",
    },
    {
        "key": "python",
        "title": "Python 执行",
        "module": "agno.tools.python",
        "class_name": "PythonTools",
        "requires": None,
        "config_fields": [],
        "group": "高级",
        "risk": "high",
        "description": "在受控环境执行 Python 代码（高风险）",
    },
    {
        "key": "shell",
        "title": "Shell 执行",
        "module": "agno.tools.shell",
        "class_name": "ShellTools",
        "requires": None,
        "config_fields": [],
        "group": "高级",
        "risk": "high",
        "description": "执行 Shell 命令（高风险，默认关闭）",
    },
    {
        "key": "tavily",
        "title": "Tavily 搜索",
        "module": "agno.tools.tavily",
        "class_name": "TavilyTools",
        "requires": "tavily",
        "pip_name": "tavily-python",
        "config_fields": [
            {"key": "api_key", "label": "API Key", "secret": True, "required": True}
        ],
        "group": "网络",
        "risk": "low",
        "description": "Tavily AI 搜索 API",
    },
    {
        "key": "serpapi",
        "title": "SerpAPI 搜索",
        "module": "agno.tools.serpapi",
        "class_name": "SerpApiTools",
        "requires": "serpapi",
        "pip_name": "google-search-results",
        "config_fields": [
            {"key": "api_key", "label": "API Key", "secret": True, "required": True}
        ],
        "group": "网络",
        "risk": "low",
        "description": "SerpAPI 谷歌搜索结果",
    },
    {
        "key": "duckduckgo",
        "title": "DuckDuckGo 搜索",
        "module": "agno.tools.duckduckgo",
        "class_name": "DuckDuckGoTools",
        "requires": "ddgs",
        "config_fields": [],
        "group": "网络",
        "risk": "low",
        "description": "DuckDuckGo 网页搜索",
    },
    {
        "key": "wikipedia",
        "title": "维基百科",
        "module": "agno.tools.wikipedia",
        "class_name": "WikipediaTools",
        "requires": "wikipedia",
        "config_fields": [],
        "group": "网络",
        "risk": "low",
        "description": "维基百科条目查询",
    },
    {
        "key": "openweather",
        "title": "城市天气",
        "module": "agno.tools.openweather",
        "class_name": "OpenWeatherTools",
        "requires": None,
        "config_fields": [
            {"key": "api_key", "label": "API Key", "secret": True, "required": True}
        ],
        "group": "网络",
        "risk": "low",
        "description": "查询城市当前天气与预报",
    },
    {
        "key": "newspaper",
        "title": "新闻抓取",
        "module": "agno.tools.newspaper",
        "class_name": "NewspaperTools",
        "requires": "newspaper",
        "pip_name": "newspaper3k",
        "config_fields": [],
        "group": "资讯",
        "risk": "low",
        "description": "抓取新闻文章正文",
    },
    {
        "key": "arxiv",
        "title": "arXiv 论文",
        "module": "agno.tools.arxiv",
        "class_name": "ArxivTools",
        "requires": "arxiv",
        "config_fields": [],
        "group": "资讯",
        "risk": "low",
        "description": "检索 arXiv 学术论文",
    },
]

# key -> spec 的快速索引
AGNO_BY_KEY: dict[str, dict] = {spec["key"]: spec for spec in AGNO_CATALOG}
