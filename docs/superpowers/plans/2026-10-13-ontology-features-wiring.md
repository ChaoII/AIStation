# 本体模块六项能力接入对象详情页 — 实现计划

目标：把本体模块「有代码、无入口」的六项能力接入对象类型详情页，并清理 index.vue 死代码。

## 设计概览
- 对象类型详情弹窗（OntObjectTypeView）改为**多子页**（el-tabs）：概览 / 属性 / 安全 / 对象视图 / 数据源 / 使用量 / 函数 / 版本历史 / 清理建议 / 导入导出。
- index.vue 用 `objPage` 控制当前子页，传入 `:page`，监听 `@update:page`。
- 新建 4 个独立子组件，把 index.vue 里对应逻辑+弹窗整体迁入。

## 步骤
1. 新建 `components/OntObjectFunctions.vue`：本对象函数清单 + 新建/编辑/删除/校验/运行。迁自 index.vue 函数 CRUD（421–572 模板 + 1540–1788 逻辑）。
2. 新建 `components/OntObjectVersions.vue`：本对象版本历史 + 每行恢复。迁自 restoreVersion（1527）。
3. 新建 `components/OntObjectCleanup.vue`：针对本对象的清理建议 + 「标记弃用」。迁自 loadCleanup/deprecateByCleanup（1425–1445）。
4. 新建 `components/OntImportExport.vue`：导出/导入/数据源批量导入/套模板。迁自 doExport/doImport/onImportFile/doBatchImport/applyTemplate/loadImportPanel。
5. 改 `OntObjectTypeView.vue`：顶部加 el-tabs（model-value=props.page，@update:model-value 发出 update:page）；新增 functions/versions/cleanup/importexport 四个 `v-else-if` 分支渲染子组件；emits 增加 `update:page`。
6. 改 `index.vue`：
   - `const objPage = ref("overview")`；传给 `OntObjectTypeView :page="objPage" @update:page="objPage=$event"`。
   - 删除已迁走的死代码：函数 CRUD 块、导入导出/模板、清理、版本恢复、用量(本地)、相关 imports。
   - 深链 `openDeepLink` 设置 objPage="objectviews"。
7. vue-tsc + eslint 验证，确认 `module_ai/ontology` 无新增错误。

## 备注
- fnBuiltins / parseJsonList 迁入 OntObjectFunctions。
- funcForm.object_code 固定为本对象，置 disabled/静态展示。
- 导入导出/清理建议作用于当前整个 domain（exportOntology(domain_code)）；在对象详情页标题/说明中注明。
