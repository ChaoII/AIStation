"""skillhub.cn 技能精选：纯函数集合（可单测，无 IO/无 app 依赖）。

负责：
- 分类映射 / 分类 emoji；
- 中文（CJK）判断 / 显示名清洗；
- 从 SKILL.md 抽取小节（工作流/关键要点/输出格式/触发场景）；
- 组装中文指令 content（中文角色/触发 + 原文结构抽取）。

由 ``scripts/_generate_skillhub_skills.py`` 调用，测试见 ``tests/test_skillhub_curation.py``。
"""
from __future__ import annotations

import re

MAX_CONTENT_LEN = 2000

# skillhub 一级分类 key → 平台分类
CATEGORY_MAP: dict[str, str] = {
    "content-creation": "内容创作",
    "dev-programming": "开发编程",
    "data-analysis": "数据分析",
    "design-media": "设计多媒体",
    "ai-agent": "AI Agent",
    "knowledge-management": "知识管理",
    "business-ops": "商业运营",
    "education": "教育学习",
    "professional": "行业专业",
    "it-ops-security": "IT 运维与安全",
    "life-service": "生活服务",
    "office-efficiency": "办公效率",
}

# 平台分类 → 前端可用作图标的 emoji（IconTile 对非图片 icon 直接渲染为文本/emoji）
CATEGORY_EMOJI: dict[str, str] = {
    "内容创作": "✍️",
    "开发编程": "💻",
    "数据分析": "📊",
    "设计多媒体": "🎨",
    "AI Agent": "🤖",
    "知识管理": "📚",
    "商业运营": "💼",
    "教育学习": "🎓",
    "行业专业": "🧭",
    "IT 运维与安全": "🛡️",
    "生活服务": "🏠",
    "办公效率": "📝",
    "通用": "🧩",
}

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def map_category(category_key: str) -> str:
    """skillhub 一级分类 → 平台分类；未知回退「通用」。"""
    return CATEGORY_MAP.get(category_key or "", "通用")


def category_emoji(category: str) -> str:
    """平台分类 → emoji；未知回退「🧩」。"""
    return CATEGORY_EMOJI.get(category or "", "🧩")


def has_cjk(text: str | None) -> bool:
    """是否含中文（CJK 基本区 + 扩展 A）。"""
    return bool(_CJK_RE.search(text or ""))


def clean_display_name(name: str | None) -> str:
    """清洗技能显示名：去 `.Skill`/`.SKILL` 后缀、两端空白、折叠连续空格。"""
    s = (name or "").strip()
    s = re.sub(r"\.skill$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# 期望小节名 → 命中的标题关键词（中英文）
_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "工作流": (
        "workflow", "process", "steps", "step by step", "method",
        "流程", "步骤", "工作流", "操作步骤", "执行",
    ),
    "关键要点": (
        "guideline", "checklist", "rule", "constraint", "best practice",
        "要点", "约束", "规则", "清单", "注意事项", "原则",
    ),
    "输出格式": (
        "output", "format", "输出", "格式", "输出格式",
    ),
    "触发场景": (
        "when to activate", "trigger", "适用场景", "触发场景", "使用场景", "when",
    ),
}

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$")


def extract_sections(md: str | None) -> dict[str, str]:
    """从 SKILL.md 抽取指定小节正文（bullets 原样保留，尾随单换行）。

    命中规则：标题（忽略大小写）包含该小节任一关键词，取该标题之后到
    下一同级/更高级标题之前的正文；只取首个命中标题；未命中则结果不含该键。
    """
    lines = (md or "").splitlines()
    headings: list[tuple[int, int, str]] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip().lower()))

    out: dict[str, str] = {}
    for section, keywords in _SECTION_KEYWORDS.items():
        for idx, level, title in headings:
            if any(k in title for k in keywords):
                end = len(lines)
                for j, lv, _t in headings:
                    if j > idx and lv <= level:
                        end = j
                        break
                body = "\n".join(lines[idx + 1 : end]).strip()
                if body:
                    out[section] = body + "\n"
                break
    return out


def build_skill_content(
    *,
    source_slug: str,
    description_zh: str,
    sk_md: str,
    license: str | None = None,
) -> str:
    """按「中文角色 + 结构抽取」组装中文指令 content，并限制总长度。

    模板见设计文档 §4；未命中的小节用中文占位说明；「关键要点」未命中则整节约略。
    中文角色取 ``description_zh``（清洗控制符后截断 400 字）。
    """
    sections = extract_sections(sk_md)

    role = re.sub(r"[\x00-\x1f]", " ", description_zh or "").strip()[:400]
    role = role or "（未提供技能描述）"
    trigger = sections.get("触发场景") or "（描述技能适用的场景，原文未提供则结合目标判断）"
    workflow = sections.get("工作流") or "（未提供，请结合目标判断）"
    output = sections.get("输出格式") or "（按平台既有风格输出 Markdown）"

    parts = [
        "## 角色 / 目标",
        role,
        "",
        "## 触发场景",
        trigger,
        "",
        "## 工作流",
        workflow,
    ]
    if "关键要点" in sections:
        parts += ["", "## 关键要点", sections["关键要点"]]
    parts += [
        "",
        "## 输出格式",
        output,
        "",
        "## 来源",
        f"skillhub.cn/{source_slug}（{license or '未知许可'}）",
    ]

    content = "\n".join(parts)
    if len(content) > MAX_CONTENT_LEN:
        content = content[:MAX_CONTENT_LEN]
    return content
