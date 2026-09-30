"""模型引用列的可空性测试。

为什么这些列必须可空
--------------------
2026-07 的数据事故删掉了一批模型行，留下 47 条悬空引用。其中三列当时是
``NOT NULL``，结构上**无法表达"引用的模型已被删除"这一合法状态**——这类行只能
卡在指向一个不存在的 id 上，既不能修复也不能如实记录，只能留着坏链。

修复方式是置空引用（保留历史行），前提是列可空。迁移 ``tk1m0d2l4r6`` 放宽了
``train_evals.model_repo_id`` / ``train_predicts.model_id`` /
``train_predicts.model_repo_id``。

这些列有个共同点：字段名叫 ``model_repo_id``，实际存的是**模型版本行 id**
（``train_models.id``），不是仓库 id。所以它们本质是"可空的软引用"——
被引用的模型可能先于引用记录消失（模型可以删，记录要留）。

本文件防止列被改回 ``NOT NULL``。
"""

import ast
import pathlib

import pytest

from app.plugin.module_train.model import (
    TrainEval,
    TrainModel,
    TrainModelRepo,
    TrainPredict,
    TrainTask,
)

VERSIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "alembic" / "versions"

#: (类, 列名, 为何必须可空)
MUST_BE_NULLABLE = (
    (TrainModelRepo, "latest_version_id", "仓库的最新版本可能已被删除"),
    (TrainTask, "model_repo_id", "历史任务的产出模型可能已被删除"),
    (TrainEval, "model_repo_id", "评估目标模型可能已被删除"),
    (TrainEval, "model_id", "同上"),
    (TrainPredict, "model_id", "预测目标模型可能已被删除"),
    (TrainPredict, "model_repo_id", "同上"),
)


@pytest.mark.parametrize("cls, column, reason", MUST_BE_NULLABLE,
                         ids=[f"{c.__tablename__}.{col}" for c, col, _ in MUST_BE_NULLABLE])
def test_model_reference_columns_are_nullable(cls, column, reason):
    """ORM 声明必须是 nullable=True（否则新库 create_all 建出来的列与迁移后的不一致）。"""
    col = cls.__table__.c[column]
    assert col.nullable is True, (
        f"{cls.__tablename__}.{column} 必须可空：{reason}。"
        f"NOT NULL 时结构上无法表达「引用的模型已删除」，只能留坏链。"
    )


def test_model_reference_columns_are_plain_integer_not_fk():
    """这些列**故意不是** ForeignKey。

    若加了外键 + ON DELETE CASCADE，删模型会连带删掉历史评估/预测记录——那正是
    事故当初最该避免的：一次误删把用户的评估历史一起带走。现在是软引用 + 置空，
    历史记录能活下来，代价是要显式置空（本仓库有对应的一次性脚本）。
    """
    for cls, column, _ in MUST_BE_NULLABLE:
        col = cls.__table__.c[column]
        assert not col.foreign_keys, (
            f"{cls.__tablename__}.{column} 不应是外键：加外键后删模型会级联删历史记录"
        )
        assert col.type.__class__.__name__ == "Integer", (
            f"{cls.__tablename__}.{column} 应保持 Integer（语义是 train_models.id 的软引用）"
        )


def test_migration_exists_and_is_applied():
    """迁移文件必须在，且 down_revision 指向真正的链尾（避免撞 id / 断链）。"""
    f = VERSIONS_DIR / "tk1m0d2l4r6_训练模块模型引用列可空.py"
    assert f.exists(), "迁移 tk1m0d2l4r6 丢失——新库将建出 NOT NULL 的列"
    src = f.read_text(encoding="utf-8")
    assert 'revision: str = "tk1m0d2l4r6"' in src
    assert 'down_revision: str | Sequence[str] | None = "b3c4d5e6f7a8"' in src
    # 三个目标列都要在 upgrade 里被 DROP NOT NULL
    for table, column in (("train_evals", "model_repo_id"),
                          ("train_predicts", "model_id"),
                          ("train_predicts", "model_repo_id")):
        assert f'("{table}", "{column}")' in src, f"迁移漏了 {table}.{column}"


def test_revision_ids_are_unique_across_migrations():
    """⚠️ 防止再次出现 revision id 撞车。

    实测教训：我按"下一个十六进制"猜了个 id，正好撞上早已存在的
    ``c4d5e6f7a8b9``（告警记录时间索引），于是 alembic 报
    ``Cycle is detected in revisions(...)`` —— 一个只涉及可空性的改动，
    错误信息却指向十几条无关迁移，极难定位。

    撞车不会报"duplicate revision"，而是伪装成**迁移链成环**，所以只能靠
    这个测试提前拦住。
    """
    seen: dict[str, str] = {}
    for py in VERSIONS_DIR.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # 只认模块级的 `revision: str = "..."` 赋值
            if not isinstance(node, ast.AnnAssign):
                continue
            tgt = node.target
            if not (isinstance(tgt, ast.Name) and tgt.id == "revision"):
                continue
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                continue
            rev = node.value.value
            assert rev not in seen, (
                f"revision id 冲突：{py.name} 与 {seen[rev]} 都是 {rev!r}。"
                f"改用带前缀的 id（如 tk1m0d2l4r6）避免与纯十六进制 id 撞车。"
            )
            seen[rev] = py.name
    assert len(seen) > 20, "解析到的迁移数异常偏少，测试本身可能失效"


def test_migration_chain_has_single_head_and_no_cycle():
    """迁移链必须无环且单头——否则连 ``alembic heads`` 都跑不了。"""
    revs: dict[str, str | None] = {}
    for py in VERSIONS_DIR.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        rev = down = None
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "revision" and isinstance(node.value, ast.Constant):
                    rev = node.value.value
                elif node.target.id == "down_revision":
                    if isinstance(node.value, ast.Constant):
                        down = node.value.value
                    else:  # `str | Sequence[str] | None = "x"` 这类带注解的简写
                        val = node.value
                        if isinstance(val, ast.BinOp):
                            val = val.right
                        down = val.value if isinstance(val, ast.Constant) else None
        if rev:
            revs[rev] = down

    # 无环：每个 revision 沿 down 走必须能走到 None
    for start in revs:
        seen, cur = set(), start
        while cur:
            assert cur not in seen, f"迁移链成环：{cur}（从 {start} 出发绕回来了）"
            seen.add(cur)
            cur = revs.get(cur)

    # head 的定义：**没有任何其它迁移以它为 down_revision**（即没人从它继续往下建）。
    # ⚠️ 别写成「它的 down 指向谁」——链是单根的，除根外每个节点的 down 都存在，
    #    那样算出来 head 恒为 0（实测踩过一次）。
    # ⚠️ 也别把 down=None 的**根**当 head（另一个踩过的坑）：根是链的起点。
    roots = [r for r, d in revs.items() if d is None]
    built_on = {d for d in revs.values() if d is not None}
    heads = [r for r in revs if r not in built_on]

    assert len(roots) == 1, f"迁移链有 {len(roots)} 个根：{roots}（应恰好 1 个）"
    assert len(heads) == 1, f"迁移链有 {len(heads)} 个头：{heads}（应恰好 1 个）"
    assert heads[0] == "tk1m0d2l4r6", (
        f"当前 head 是 {heads[0]}，但仓库里最新的迁移是 tk1m0d2l4r6——"
        f"新迁移的 down_revision 可能写错"
    )


def test_model_reference_points_at_version_row_not_repo():
    """钉死"字段名有误导"这一事实，避免有人按字面理解去改成指向仓库。

    ``TrainTask.model_repo_id`` / ``TrainEval.model_repo_id`` 存的是
    ``train_models.id``（模型**版本**行），不是 ``train_model_repos.id``。
    本项目已逐条查过历史任务确认这一点；照字面改成仓库 id 会让所有历史行失效。
    """
    # 模型版本行 id 与仓库 id 是不同的取值空间，且会重叠（历史数据里 model 13 在 repo 6）
    m = TrainModel.__table__
    r = TrainModelRepo.__table__
    assert "repo_id" in m.c and "id" in m.c and "latest_version_id" in r.c
    # 注释里必须写明，避免后人"顺手修正"字段语义
    src = pathlib.Path(__file__).resolve().parents[1] / "app" / "plugin" / "module_train" / "model.py"
    text = src.read_text(encoding="utf-8")
    assert "字段名沿用历史" in text, (
        "model.py 里应注明 model_repo_id 实为版本行 id，防止被当成字段名错误"
        "「顺手修正」而使所有历史行失效"
    )
