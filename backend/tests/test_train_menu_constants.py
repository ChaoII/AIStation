"""训练菜单/权限种子常量测试。"""
from app.scripts import init_app


def test_model_update_permission_seeded():
    perms = dict(init_app.TRAIN_BUTTON_PERMS)
    assert perms.get("module_train:model:update") == "编辑模型"


def test_predict_permissions_seeded():
    perms = dict(init_app.TRAIN_BUTTON_PERMS)
    for code in (
        "module_train:predict:query",
        "module_train:predict:create",
        "module_train:predict:delete",
    ):
        assert code in perms


def test_task_detail_menu_in_extra_menus():
    route_names = {row[1] for row in init_app.TRAIN_EXTRA_MENUS}
    assert "TrainTaskDetail" in route_names
    assert "TrainPredict" in route_names
