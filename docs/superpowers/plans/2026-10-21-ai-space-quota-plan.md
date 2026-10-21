# 个人工作空间：默认 2G + 申请扩容（管理员审核）+ 拖拽上传 + 样式

> 设计确认：提交申请 → 管理员审核 → 按用户增额；需要管理员审核页。
> 关联文档：`docs/ai-personal-workspace.md`

## 目标
- 默认配额 2GB（`AI_SPACE_QUOTA_MB` 10240 → 2048）。
- 用户侧：用量条 +「申请扩容」链接 + 我的申请；拖拽上传；搜索占位「搜索个人空间文件…」。
- 管理员侧：扩容审核页（列表 + 通过/驳回，通过时按用户增额）。

## 数据模型（2 张新表，均继承 ModelMixin）
- `ai_space_quota_requests`（扩容申请）：user_id / target_mb / reason / status(pending/approved/rejected) / reviewed_by / review_note / review_time
- `ai_space_user_quota`（按用户配额覆盖）：user_id(unique) / quota_mb / updated_by
- 生效配额 = 用户 override 或全局默认。

## 任务
1. 后端模型 + 迁移（has_table 幂等）+ 测试建表回归
2. `setting.py` 默认 2G + `SpaceService.effective_quota` 接入 `quota/_check_quota`
3. `SpaceService` 申请/列表/审核方法
4. schema + controller 路由 + 权限码 `module_ai:space:quota_review` + 菜单
5. 前端 API + 用户页（申请扩容弹窗/我的申请/拖拽上传/搜索占位）
6. 前端管理员审核页 `module_ai/space/quota-review.vue`
7. 回归 + 文档

## 验证
- 后端 `uv run pytest tests/test_ai_space_quota.py -q`
- 前端 `pnpm run type-check` + `pnpm exec eslint`
- 全量 `-n 4` 回归
