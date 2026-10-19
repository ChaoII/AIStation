"""分块测试：历史行为兼容、位置/页码、token 口径、标题树。"""
from app.plugin.module_ai.knowledge.chunking import chunk_drafts, chunk_text


def test_legacy_chunk_text_unchanged():
    assert chunk_text("ABCDEFGHIJ", chunk_size=4, overlap=1) == ["ABCD", "DEFG", "GHIJ"]
    assert chunk_text("", 100) == []


def test_paragraph_and_sentence_still_work():
    text = "第一段内容。\n\n第二段内容。"
    assert chunk_text(text, 100, 0, "paragraph") == ["第一段内容。", "第二段内容。"]
    assert chunk_text("一句。两句。", 100, 0, "sentence") == ["一句。两句。"]


def test_drafts_carry_positions_and_pages():
    text = "AAAABBBBCCCC"
    drafts = chunk_drafts(text, chunk_size=4, overlap=0, page_offsets=[0, 8])
    assert [d.content for d in drafts] == ["AAAA", "BBBB", "CCCC"]
    assert drafts[0].char_start == 0 and drafts[0].char_end == 4
    assert drafts[1].page == 0 and drafts[2].page == 1
    assert all(d.token_count > 0 for d in drafts)


def test_token_unit_keeps_within_budget():
    from app.plugin.module_ai.knowledge.chunking.tokens import estimate_tokens

    text = "。".join(["知识库检索"] * 200)
    drafts = chunk_drafts(text, chunk_size=20, overlap=0, unit="token")
    assert drafts
    assert all(d.token_count <= 20 for d in drafts)
    assert sum(d.token_count for d in drafts) > 0
    assert estimate_tokens("") == 0


def test_heading_splits_by_tree_and_keeps_titles():
    md = "# 一级\n\n甲段内容。\n\n## 二级\n\n乙段内容。\n\n" + ("长" * 600)
    drafts = chunk_drafts(md, strategy="heading", chunk_size=200, overlap=0)
    assert drafts
    assert drafts[0].content.startswith("【一级】")
    assert any("【一级 / 二级】" in d.content for d in drafts)
    assert all(len(d.content) <= 300 for d in drafts)


def test_heading_second_level_split():
    md = "# 标题\n\n" + ("句子内容。" * 200)
    drafts = chunk_drafts(md, strategy="heading", chunk_size=100, overlap=0)
    assert len(drafts) > 1, "超长节必须二级切分"
