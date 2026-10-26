export default {
  // 页面标题 / 描述
  title: "License Plate Data Synthesis",
  sub: "Generate various domestic license plates (blue / new energy / yellow / double-decker / black / coach / police), with perturbations such as perspective, rotation, noise, stains, occlusion and blur, plus detection box annotations.",

  // 表单
  plateType: "Plate Type",
  dataset: "Target Dataset",
  datasetPlaceholder: "Dataset to write to",
  count: "Count",
  seed: "Random Seed",
  disturbance: "Perturbations",
  closed: "Disabled",
  restoreDefault: "Restore Default",
  collapseAll: "Collapse All",
  expandAll: "Expand All",
  disturbHint:
    "Disabled perturbations are excluded from generation; parameters are random ranges [lower ~ upper].",
  output: "Output",
  writeDataset: "Write to Dataset",
  previewOnly: "Preview Only",
  writeAnnotation: "Write Annotation",
  noAnnotation: "No Annotation",
  start: "Start Synthesis",
  tip: "Tip: when no dataset is selected or 'Write to Dataset' is off, only a preview is shown; after selecting a dataset and enabling write, the synthesized images are stored and a detection annotation task is created automatically.",

  // 结果
  resultCount: "Synthesis Results ({count})",
  notUploaded: "Not written (preview only)",
  taskNo: "Task #{id}",
  resultAlt: "Synthesized plate",
  savedStore: "Stored #{id}",

  // 历史
  historyTitle: "Synthesis Task History",
  refresh: "Refresh",
  noJobs: "No synthesis tasks yet",
  jobId: "Task ID",
  params: "Params",
  total: "Total",
  status: "Status",
  createdTime: "Created Time",

  // 脚本可见文案
  plateTypeBlue: "Blue (passenger car)",
  statusCompleted: "Completed",
  statusRunning: "Running",
  statusFailed: "Failed",
  statusPending: "Pending",
  jobParamText: "{count} generated · {mode}",
  store: "Store",
  preview: "Preview",
  generateSuccess: "Synthesis complete, {count} images in total",
  generateFailed: "Synthesis failed",
};
