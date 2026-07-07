# Task 8: 权限与菜单注册 + 评估调度器启动

## 要修改的文件
- `backend/app/scripts/init_app.py`（修改）

## 要求

### 1. 在 `_ensure_train_menus` 中添加预测菜单和详情页路由

现有菜单在第 308-312 行（评估菜单），在其后添加：

```python
MenuModel(name="模型预测", type=2, icon="el-icon-VideoCamera", order=4,
          route_name="TrainPredict", route_path="/train/predict",
          component_path="module_train/predict/index",
          permission="module_train:predict:query", parent_id=parent.id,
          status="0", is_deleted=False, title="模型预测"),
```

现有详情页菜单在第 319-328 行（训练详情），在其后添加：

```python
detail_eval = MenuModel(
    name="评估详情", type=2, icon=None, order=99,
    route_name="TrainEvalDetail", route_path="/train/eval/:id",
    component_path="module_train/eval/detail",
    permission="module_train:eval:query", parent_id=parent.id,
    status="0", is_deleted=False, title="评估详情", hidden=True,
)
db.add(detail_eval)
await db.flush()
db.add(RoleMenusModel(role_id=1, menu_id=detail_eval.id))

detail_predict = MenuModel(
    name="预测详情", type=2, icon=None, order=99,
    route_name="TrainPredictDetail", route_path="/train/predict/:id",
    component_path="module_train/predict/detail",
    permission="module_train:predict:query", parent_id=parent.id,
    status="0", is_deleted=False, title="预测详情", hidden=True,
)
db.add(detail_predict)
await db.flush()
db.add(RoleMenusModel(role_id=1, menu_id=detail_predict.id))
```

### 2. 添加预测权限

现有 button_perms 在第 332-343 行，在最后添加：

```python
("module_train:predict:query", "查询预测"),
("module_train:predict:create", "创建预测"),
("module_train:predict:delete", "删除预测"),
```

### 3. 启动评估调度器

现有 scheduler 启动在第 463-465 行：

```python
from app.plugin.module_train.scheduler import start_scheduler
asyncio.create_task(start_scheduler())
log.info("✅ 训练调度器已启动")
```

在其后添加：

```python
from app.plugin.module_train.eval_scheduler import start_evaluation_scheduler
asyncio.create_task(start_evaluation_scheduler())
log.info("✅ 评估调度器已启动")
```

## 提交信息
```bash
git add backend/app/scripts/init_app.py
git commit -m "feat(train): register predict/eval menus, permissions, start eval scheduler"
```
