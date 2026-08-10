### Task 8: 前端仓库页两级展示 + eval/predict 版本选择

**Files:**
- Modify: `frontend/web/src/api/module_train/index.ts`
- Modify: `frontend/web/src/views/module_train/repo/index.vue`
- Modify: `frontend/web/src/views/module_train/eval/index.vue`
- Modify: `frontend/web/src/views/module_train/predict/index.vue`
- Modify: `frontend/web/src/views/module_train/task/detail.vue`
- Test: `cd frontend/web && pnpm run type-check`

**Interfaces:**
- Consumes: `GET /train/model/repos`, `GET /train/model/{repo_id}/versions`（Task 3 产物）
- Produces: 前端仓库两级表格、版本选择联动

- [ ] **Step 1: API 层补充方法**

`frontend/web/src/api/module_train/index.ts` 添加：

```typescript
  listModelRepos(query?: TablePageQuery) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/repos`,
      method: "get",
      params: query,
    });
  },
  listModelVersions(repoId: number) {
    return request<ApiResponse>({
      url: `${API_PATH}/model/${repoId}/versions`,
      method: "get",
    });
  },
```

- [ ] **Step 2: 仓库页改为两级展示**

`repo/index.vue`：
- 搜索栏保留 name/framework
- 主表列改为：名称、框架、版本数、最新版本、创建时间、操作（去评估/去训练/删除）
- 新增"展开行/抽屉"展示版本列表（`listModelVersions`），版本行操作：评估、预测、导出、下载

关键改动（抽屉内版本表格）：

```vue
<ElDrawer v-model="versionsDrawer.visible" :title="versionsDrawer.repoName" size="600px">
  <ElTable v-loading="versionsLoading" :data="versionItems" border stripe>
    <ElTableColumn prop="version" label="版本" width="80" />
    <ElTableColumn label="mAP50" width="90" align="center">
      <template #default="{ row }">{{ row.metrics?.map50 != null ? Number(row.metrics.map50).toFixed(3) : "-" }}</template>
    </ElTableColumn>
    <ElTableColumn prop="format" label="格式" width="90" align="center" />
    <ElTableColumn prop="created_time" label="创建时间" min-width="160" />
    <ElTableColumn label="操作" width="220" fixed="right">
      <template #default="{ row }">
        <ElButton link type="primary" size="small" @click="goEval(repo, row)">评估</ElButton>
        <ElButton link type="success" size="small" @click="goPredict(repo, row)">推理</ElButton>
        <ElButton link type="warning" size="small" @click="exportVersion(row)">导出</ElButton>
      </template>
    </ElTableColumn>
  </ElTable>
</ElDrawer>
```

- [ ] **Step 3: eval/predict 表单版本联动**

`eval/index.vue`：选择仓库后调 `listModelVersions(repoId)` 填充版本下拉；提交时 `model_id=版本id, model_repo_id=仓库id`。

`predict/index.vue`：同样的版本联动。

- [ ] **Step 4: task/detail 跳转修正**

`task/detail.vue` 中 `model_repo_id` 跳转改为查该版本所属仓库：

```typescript
  if (task.value?.model_repo_id) {
    const repo = await TrainAPI.detailModelRepoOfVersion(task.value.model_repo_id);
    router.push(`/train/repo?repo_id=${repo?.repo_id}`);
  }
```

> 需要后端补一个 `GET /train/model/version/{version_id}/repo` 端点（在 Task 3 中一并提供）返回 `{repo_id, repo_name}`。

- [ ] **Step 5: type-check 验证**

Run: `cd frontend/web && pnpm run type-check`
Expected: 0 errors

- [ ] **Step 6: 构建验证**

Run: `cd frontend/web && npx vite build 2>&1 | Select-Object -Last 3`
Expected: `built in` 无报错

- [ ] **Step 7: 提交**

```bash
git add frontend/web/src/api/module_train/index.ts frontend/web/src/views/module_train/repo/index.vue frontend/web/src/views/module_train/eval/index.vue frontend/web/src/views/module_train/predict/index.vue frontend/web/src/views/module_train/task/detail.vue
git commit -m "feat(train): repo two-level UI with version selection for eval/predict"
```

---


