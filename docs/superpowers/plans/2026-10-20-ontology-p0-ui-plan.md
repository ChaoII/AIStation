# 本体 P0 裂缝修复 + 界面优化 计划

> 审查后经用户确认：后端修全部 P0 五条；界面做「必做 4 项 + 可选项」。

## 后端 P0（TDD，先写失败测试）

- [x] 1. 提案合并非单事务 → 单事务，task 失败全回滚（proposal.py merge_proposal）✅ 通过
  - 实现：`service._ont_transaction()` 集中式事务 + `_exec/_exec_write` 路由；`merge_proposal` 单事务包裹
  - 测试：`TestProposalAtomicity`（失败回滚 + 成功路径）
- [x] 2. 实例写回未校验值类型 → 复用 `validate_value`（writeback_instance）✅ 通过
  - 测试：`TestWritebackValueType`（非法值被拦、合法值通过）
- [x] 3. 动作写路径 `required` 校验 → `_missing_required_props` + 接入 create_object（含场景）✅ 通过
  - 测试：`TestActionRequired`（必填缺失识别）
- [x] 4. 建表 DDL 裸 `except pass` → 记 warning（service `_ensure_ontology_schema`）✅ 通过
  - 测试：`TestOntSchemaFailure`（坏 DDL 触发告警而非静默）
- [x] 5. 版本 diff 太浅 → 扩到 关系/动作/函数（version_diff）✅ 通过
  - 测试：`TestVersionDiff`（新增属性/关系/动作 全被 diff 到）

## 界面优化（前端）

- [x] 6. 治理功能可见化：9 个面板已是 `OntGraphWorkspace` 顶部**图标工具条**（`MAINT_ITEMS`），非下拉 ✅ 已就位
- [x] 7. "能填不生效"字段整改：副作用提示改准确（支持通知/webhook）、insert/delete 选项禁用 ✅
- [x] 8. 对象详情 12 Tab 精简：清理建议/导入导出/指标 折进「更多」下拉 ✅
- [x] 9. 引导 tour 处理：`settings.showGuide` 默认 `false`（默认关，可手动开启）+ `GUIDE_AUTO_SHOWN_KEY` 仅首次自动弹出（避免每次登录都弹）✅
- [x] 10. 本体域面板可折叠：`ont-side` 头部加折叠按钮，收起域名列表释放图谱宽度 ✅ 已无头浏览器验证
- [x] 11. 对象详情全局 Tab 快速跳转：`.ont-obj__tabs` 导航条 `position: sticky` 吸顶（滚动任意位置都能一键切换子页）✅ 已无头浏览器验证
  - 注意：el-tabs 在本页是「纯导航」（pane 空、内容是兄弟模板），el-tabs 根仅 ~47px 高；
    只给 `.el-tabs__header` 加 sticky 因其父太矮无法「行程」不生效，须给整条 `.ont-obj__tabs` 加 sticky。

## 验证

- [x] 后端：新增 5 类测试全绿；全量本体测试 **139 passed, 36 skipped** 无回归
- [x] 前端：`pnpm run type-check` 通过；改动文件 `eslint` 干净；`vitest` 本体单测 8/8 通过
  - 注：`pnpm run lint` 全量仍报 48 项**既有**错误（module_annotation/train/video，与本任务无关）
- [x] 无头浏览器验证：本体页/对象详情抽屉/动作编辑表单 均实际渲染
  - 6 维护工具栏 9 按钮、7 副作用提示+insert/delete 禁用、8「更多」折叠了清理建议/导入导出/指标、10 本体域面板折叠 均确认

## 补充（2026-10-20）：P8 接口 link type 约束

- [x] 接口可声明 link type 约束：`check_interface_impl` 支持 `required_link.target_interface`
      —— 对端对象类型未实现该校验不通过（gap-analysis `interface-link-types-overview` 从 🟡 提升）
  - 仅后端改动：`required_links` 为自由 JSON，前端无需改表单
  - 测试：`TestInterfaceLinkConstraint`（对端未实现→报缺失；实现后→通过）
  - 回归：`tests/test_object_view_index_proposal.py` **31 passed, 36 skipped** 无回归
  - 后端已按 `--no-reload` 重启（8002），运行的就是含 P8 的当前源码，P8 已生效

## 验证

- [ ] 后端：新增/调整测试全绿；回归跑 test_ontology*.py
- [ ] 前端：pnpm run type-check + lint 通过；对象详情/图谱组件有覆盖
- [ ] 全量：backend pytest（带 -n 4）+ 前端测试
