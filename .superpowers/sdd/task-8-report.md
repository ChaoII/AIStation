# Task 8 完成报告

## 修改文件
- `backend/app/scripts/init_app.py`

## 修改内容

### 1. 预测菜单注册
- 在 `_ensure_train_menus` 的 children 列表末尾添加了 `模型预测` 菜单项（type=2, order=4, route=TrainPredict）

### 2. 详情页菜单注册
- 在训练详情菜单之后，添加了 `评估详情`（TrainEvalDetail, /train/eval/:id）和 `预测详情`（TrainPredictDetail, /train/predict/:id）两个隐藏详情路由
- 均为 admin 角色（role_id=1）分配了菜单权限

### 3. 预测权限注册
- 在 button_perms 末尾添加了查询、创建、删除预测三条按钮权限

### 4. 评估调度器启动
- 在 lifespan 中的训练调度器启动之后，新增了评估调度器（eval_scheduler）的异步启动

## 验证
- Python 语法检查通过
