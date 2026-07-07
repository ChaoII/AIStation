# Task 9: Frontend API — 新增预测 + 评估 API 调用

## 要修改的文件
- `frontend/src/api/module_train.ts`（修改）

## 要求
在 `TrainAPI` 对象中添加新的 API 方法。现有 eval 方法保留。在 `exportDataset` 之后添加：

```typescript
  getEvalDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/detail`, method: "get" });
  },
  startEval(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/start`, method: "post" });
  },
  stopEval(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/stop`, method: "post" });
  },

  createPredict(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/create`, method: "post", data });
  },
  getPredictList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/predict/list`, method: "get" });
  },
  getPredictDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/detail`, method: "get" });
  },
  startPredict(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/start`, method: "post" });
  },
  stopPredict(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/stop`, method: "post" });
  },
  deletePredict(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/delete`, method: "delete", data: ids });
  },
  uploadPredictImages(files: File[]) {
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));
    return request<ApiResponse<string[]>>({ url: `${API_PATH}/predict/upload`, method: "post", data: formData, headers: { "Content-Type": "multipart/form-data" } });
  },
```

## 现有文件
- `frontend/src/api/module_train.ts`（58 行）
- `request` 来自 `@/utils/request`，`ApiResponse` 来自全局类型
- `API_PATH = "/train"` 已有

## 提交信息
```bash
git add frontend/src/api/module_train.ts
git commit -m "feat(train): add predict API and eval detail/start/stop API"
```
