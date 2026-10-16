"""skillhub.cn 技能精选：纯函数与数据集形状测试。

纯逻辑用例，可用 ``PYTEST_NO_APP=1`` 快速跑（约 2 秒），不触发应用构造。
"""
from app.plugin.module_ai.market.skillhub_curation import (
    MAX_CONTENT_LEN,
    build_skill_content,
    category_emoji,
    clean_display_name,
    extract_sections,
    has_cjk,
    map_category,
)


def test_map_category_known():
    assert map_category("content-creation") == "内容创作"
    assert map_category("dev-programming") == "开发编程"
    assert map_category("data-analysis") == "数据分析"
    assert map_category("design-media") == "设计多媒体"
    assert map_category("ai-agent") == "AI Agent"
    assert map_category("knowledge-management") == "知识管理"
    assert map_category("business-ops") == "商业运营"
    assert map_category("education") == "教育学习"
    assert map_category("professional") == "行业专业"
    assert map_category("it-ops-security") == "IT 运维与安全"
    assert map_category("life-service") == "生活服务"
    assert map_category("office-efficiency") == "办公效率"


def test_map_category_unknown_and_pay():
    assert map_category("zzz-unknown") == "通用"
    assert map_category("pay-skill") == "通用"


def test_category_emoji():
    assert category_emoji("内容创作") == "✍️"
    assert category_emoji("开发编程") == "💻"
    assert category_emoji("通用") == "🧩"
    assert category_emoji("不存在分类") == "🧩"


def test_has_cjk():
    assert has_cjk("中文文本abc") is True
    assert has_cjk("english only") is False
    assert has_cjk("") is False


def test_clean_display_name():
    assert clean_display_name("编程大神.Skill") == "编程大神"
    assert clean_display_name("防骗大师.SKILL") == "防骗大师"
    assert clean_display_name("  Content  Writer  ") == "Content Writer"


def test_extract_sections_english():
    md = "## Workflow\n- step1\n- step2\n\n## Guidelines\n- g1\n- g2\n"
    out = extract_sections(md)
    assert out["工作流"] == "- step1\n- step2\n"
    assert out["关键要点"] == "- g1\n- g2\n"


def test_extract_sections_chinese_and_missing():
    md = "## 流程\n- 步骤1\n## 输出格式\n- markdown\n"
    out = extract_sections(md)
    assert out["工作流"] == "- 步骤1\n"
    assert out["输出格式"] == "- markdown\n"
    assert "关键要点" not in out


def test_build_skill_content_full():
    desc = "生成小红书笔记"
    md = "## Workflow\n- 确定平台\n- 撰写正文\n## Guidelines\n- 排重\n- 平台原生化\n"
    content = build_skill_content(
        source_slug="content-writer",
        description_zh=desc,
        sk_md=md,
        license="MIT",
    )
    assert "## 角色 / 目标" in content
    assert "生成小红书笔记" in content
    assert "## 工作流" in content
    assert "- 确定平台" in content
    assert "## 关键要点" in content
    assert "- 排重" in content
    assert "## 来源" in content
    assert "content-writer" in content
    assert "MIT" in content


def test_build_skill_content_missing_sections():
    desc = "写周报"
    md = "## Workflow\n- 汇总\n"
    content = build_skill_content(source_slug="weekly", description_zh=desc, sk_md=md)
    # 无 Guidelines → 不含关键要点小节
    assert "## 关键要点" not in content
    # 无 When to Activate → 触发场景缺省（未提供占位）
    assert "## 工作流" in content


def test_build_skill_content_length_cap():
    desc = "很长的描述" * 200
    md = "## Workflow\n" + "- 内容超长\n" * 300
    content = build_skill_content(source_slug="long", description_zh=desc, sk_md=md)
    assert len(content) <= MAX_CONTENT_LEN


def test_skillhub_skills_shape():
    """固化数据集形状锚点：≥200、字段齐全、content 含中文、无重复、不与内置技能撞名。"""
    from app.plugin.module_ai.market.skillhub_skills import SKILLHUB_SKILLS
    from app.plugin.module_ai.market.seed import _SKILLS

    assert len(SKILLHUB_SKILLS) >= 200
    keys: set[str] = set()
    names: set[str] = set()
    builtin = {s["name"] for s in _SKILLS}
    for s in SKILLHUB_SKILLS:
        for field in ("name", "description", "content", "category"):
            assert s[field], f"{s.get('key')} 缺字段 {field}"
        assert has_cjk(s["content"])
        assert s["key"] not in keys and s["name"] not in names
        assert s["name"] not in builtin
        assert s["icon"], "图标应为非空（分类 emoji）"
        keys.add(s["key"])
        names.add(s["name"])
