"""留出法：近义题必须同集（否则错题沉淀会从"近义题"泄漏答案）。"""
import asyncio


def test_similarity_detects_near_duplicates():
    from app.plugin.module_ai.query.eval_split import similarity

    a = "每个供应商的矿点数量占全部矿点数量的比例是多少"
    b = "每个供应商的矿点数量占全部矿点数量的比例是多少？"
    c = "按煤种类型统计记录数并排名"
    assert similarity(a, b) > 0.9, similarity(a, b)
    assert similarity(a, c) < 0.3, similarity(a, c)


def test_assign_splits_keeps_near_duplicates_in_same_set():
    from app.plugin.module_ai.query.eval_split import assign_splits

    qs = [
        "每个供应商的矿点数量占全部矿点数量的比例是多少",
        "每个供应商的矿点数量占全部矿点数量的比例是多少？",
        "每个供应商关联的矿点记录数占全部供应商矿点关联记录数的比例是多少",
        "按煤种类型统计记录数并排名",
        "各煤种类型的记录占比是多少",
    ]
    got = assign_splits(qs)
    # 前三条是近义 → 必须同集
    assert got[qs[0]] == got[qs[1]] == got[qs[2]], got
    # 两集都要有题（不是全塞一边）
    assert set(got.values()) == {"A", "B"}, got


def test_assign_splits_covers_every_question():
    from app.plugin.module_ai.query.eval_split import assign_splits

    qs = ["q1 测点排名", "q2 煤质化验", "q3 供应商占比"]
    got = assign_splits(qs)
    assert set(got) == set(qs)
    assert all(v in ("A", "B") for v in got.values())
