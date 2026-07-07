# Task 9 Report — Frontend API: 新增预测 + 评估 API 调用

## 修改文件
- `frontend/src/api/module_train.ts`

## 新增方法（共 10 个）

### Eval 扩展（3 个）
- `getEvalDetail(id)` → GET `/eval/{id}/detail`
- `startEval(id)` → POST `/eval/{id}/start`
- `stopEval(id)` → POST `/eval/{id}/stop`

### Predict（7 个）
- `createPredict(data)` → POST `/predict/create`
- `getPredictList()` → GET `/predict/list`
- `getPredictDetail(id)` → GET `/predict/{id}/detail`
- `startPredict(id)` → POST `/predict/{id}/start`
- `stopPredict(id)` → POST `/predict/{id}/stop`
- `deletePredict(ids)` → DELETE `/predict/delete`
- `uploadPredictImages(files)` → POST `/predict/upload` (multipart/form-data)

所有方法添加到 `TrainAPI` 对象中，位于 `exportDataset` 之后。
