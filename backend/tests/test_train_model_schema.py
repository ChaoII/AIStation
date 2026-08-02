"""测试模型仓库/版本双表结构。"""
from app.plugin.module_train.model import TrainModel, TrainModelRepo


def test_train_model_repo_table_declared():
    assert TrainModelRepo.__tablename__ == "train_model_repos"
    assert "name" in TrainModelRepo.__table__.columns


def test_train_model_has_repo_id_column():
    assert "repo_id" in TrainModel.__table__.columns
