# 标注模块权限修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补齐 `module_annotation:*` 前端权限菜单，使 ANNOTATOR 角色能正常使用所有标注功能

**Architecture:** 在 `_ensure_annotation_menus()` 中创建 `module_annotation:*` 按钮级权限菜单（type=3），更新 `ensure_annotation_access` 的 `needed_perms` 列表，补充前后端权限映射

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Vue 3

## Global Constraints

- 前后端权限命名不同但功能相同：前端 `module_annotation:*` ↔ 后端 `annotation:*`
- Type=3 菜单为按钮级权限，不显示在导航栏
- `permPrefix` 用于 CRUD 自动生成 create/delete/patch 权限检查

---

### Task 1: 在 `_ensure_annotation_menus()` 中创建 `module_annotation:*` 菜单

**Files:**
- Modify: `backend/app/scripts/init_app.py:134-213`

**Interfaces:**
- Produces: 9 个 type=3 的 `sys_menu` 记录，关联到 role_id=1 (ADMIN)

- [ ] **Step 1: 在 _ensure_annotation_menus 添加 type=3 菜单**

在 `init_app.py` 的 `_ensure_annotation_menus()` 函数中，在创建完 type=2 菜单后，添加 type=3 按钮权限菜单。这些菜单的 `parent_id` 指向对应的父级页面：

```python
# 按钮级权限（type=3）
buttons = [
    MenuModel(name="查询数据集", type=3, order=1, permission="module_annotation:dataset:query",
              parent_id=dataset_menu.id, status="0", is_deleted=False),
    MenuModel(name="创建数据集", type=3, order=2, permission="module_annotation:dataset:create",
              parent_id=dataset_menu.id, status="0", is_deleted=False),
    MenuModel(name="编辑数据集", type=3, order=3, permission="module_annotation:dataset:update",
              parent_id=dataset_menu.id, status="0", is_deleted=False),
    MenuModel(name="删除数据集", type=3, order=4, permission="module_annotation:dataset:delete",
              parent_id=dataset_menu.id, status="0", is_deleted=False),
    MenuModel(name="上传图片", type=3, order=5, permission="module_annotation:dataset:upload",
              parent_id=dataset_menu.id, status="0", is_deleted=False),
    MenuModel(name="查询任务", type=3, order=1, permission="module_annotation:task:query",
              parent_id=task_menu.id, status="0", is_deleted=False),
    MenuModel(name="创建任务", type=3, order=2, permission="module_annotation:task:create",
              parent_id=task_menu.id, status="0", is_deleted=False),
    MenuModel(name="编辑任务", type=3, order=3, permission="module_annotation:task:update",
              parent_id=task_menu.id, status="0", is_deleted=False),
    MenuModel(name="删除任务", type=3, order=4, permission="module_annotation:task:delete",
              parent_id=task_menu.id, status="0", is_deleted=False),
    MenuModel(name="批量操作", type=3, order=5, permission="module_annotation:task:patch",
              parent_id=task_menu.id, status="0", is_deleted=False),
    MenuModel(name="进入标注", type=3, order=6, permission="module_annotation:task:workbench",
              parent_id=task_menu.id, status="0", is_deleted=False),
    MenuModel(name="查询统计", type=3, order=1, permission="module_annotation:stats:query",
              parent_id=stats_menu.id, status="0", is_deleted=False),
]
```

注意：需要先获取 `dataset_menu`、`task_menu`、`stats_menu` 的子查询结果（当前代码已有 `child` 变量，需要改成具体命名变量）。

- [ ] **Step 2: 注册按钮菜单到 ADMIN 角色**

```python
for btn in buttons:
    db.add(btn)
    await db.flush()
    db.add(RoleMenusModel(role_id=1, menu_id=btn.id))
```

- [ ] **Step 3: 重启后端验证**

```bash
# 登录 admin 查看菜单
docker exec aistation-pg psql -U root -d aistation -c "SELECT id, name, permission, type FROM sys_menu WHERE permission LIKE 'module_annotation:%' ORDER BY permission;"
```

预期输出：12 条 `module_annotation:*` 记录

### Task 2: 更新 ensure_annotation_access 补充 module_annotation 权限

**Files:**
- Modify: `backend/app/api/v1/module_annotation/task/service.py:79-114`

**Interfaces:**
- Consumes: Task 1 创建的 `module_annotation:*` 菜单 ID
- Produces: ANNOTATOR 角色拥有所有 `module_annotation:*` + `annotation:*` 权限

- [ ] **Step 1: 扩展 needed_perms 列表**

将 `ensure_annotation_access` 中的 `needed_perms` 扩展为包含所有 `module_annotation:*` 权限：

```python
annotator_perms = [
    # 后端权限
    "annotation:dataset:query", "annotation:dataset:create", "annotation:dataset:update", "annotation:dataset:delete",
    "annotation:task:query", "annotation:task:create", "annotation:task:update", "annotation:task:delete",
    "annotation:workbench:query", "annotation:stats:query",
    # 前端按钮权限
    "module_annotation:dataset:query", "module_annotation:dataset:create", "module_annotation:dataset:update", "module_annotation:dataset:delete", "module_annotation:dataset:upload",
    "module_annotation:task:query", "module_annotation:task:create", "module_annotation:task:update", "module_annotation:task:delete", "module_annotation:task:patch", "module_annotation:task:workbench",
    "module_annotation:stats:query",
    # 系统基础查询
    "module_system:user:query", "module_system:role:query",
]
```

- [ ] **Step 2: 重启后端 + 触发同步**

```bash
# 重启后端后，调用任务更新触发 ensure_annotation_access
curl -X PUT "http://localhost:8001/api/v1/annotation/task/update/6" \
  -H "Content-Type: application/json" \
  -d '{"assignees":[4]}' \
  -H "Authorization: Bearer $(curl -s http://localhost:8001/api/v1/system/auth/login -X POST -d 'username=admin&password=123456&captcha=&captcha_key=' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"data\"][\"access_token\"])')"
```

- [ ] **Step 3: 测试验证**

```python
# 以 test_acc 登录验证所有接口
import requests
r = requests.post('http://localhost:8001/api/v1/system/auth/login',
    data={'username':'test_acc','password':'123456'})
token = r.json()['data']['access_token']
h = {'Authorization': f'Bearer {token}'}

for url in [
    '/api/v1/annotation/dataset/list?page_no=1&page_size=10',
    '/api/v1/annotation/task/list?page_no=1&page_size=10',
    '/api/v1/annotation/task/6/progress',
    '/api/v1/system/user/list?page_no=1&page_size=5',
]:
    r2 = requests.get(f'http://localhost:8001{url}', headers=h)
    print(f'{url}: {"OK" if r2.json()["success"] else "FAIL"}')
```
