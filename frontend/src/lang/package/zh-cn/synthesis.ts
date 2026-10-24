export default {
  // 页面标题 / 描述
  title: "车牌数据合成",
  sub: "生成国内各类车牌（蓝/新能源/黄/双层/黑/教练/警用），带透视、旋转、噪点、污渍、遮挡、模糊等扰动，并产出检测框标注",

  // 表单
  plateType: "车牌类型",
  dataset: "目标数据集",
  datasetPlaceholder: "写入的数据集",
  count: "生成数量",
  seed: "随机种子",
  disturbance: "扰动",
  closed: "已关闭",
  restoreDefault: "恢复默认",
  collapseAll: "收起全部",
  expandAll: "展开全部",
  disturbHint: "关闭的扰动不参与生成；参数为随机区间 [下限 ~ 上限]",
  output: "输出",
  writeDataset: "写入数据集",
  previewOnly: "仅预览",
  writeAnnotation: "写标注",
  noAnnotation: "不写标注",
  start: "开始合成",
  tip: "提示：未选择数据集或关闭「写入数据集」时仅预览；选择数据集并开启写入后，合成图会入库并自动建立检测标注任务。",

  // 结果
  resultCount: "合成结果（{count} 张）",
  notUploaded: "未写入（仅预览）",
  taskNo: "任务 #{id}",
  resultAlt: "合成车牌",
  savedStore: "已入库 #{id}",

  // 历史
  historyTitle: "合成任务历史",
  refresh: "刷新",
  noJobs: "暂无合成任务",
  jobId: "任务ID",
  params: "参数",
  total: "数量",
  status: "状态",
  createdTime: "创建时间",

  // 脚本可见文案
  plateTypeBlue: "蓝牌(小型汽车)",
  statusCompleted: "已完成",
  statusRunning: "进行中",
  statusFailed: "失败",
  statusPending: "待生成",
  jobParamText: "生成{count}张·{mode}",
  store: "入库",
  preview: "预览",
  generateSuccess: "合成完成，共 {count} 张",
  generateFailed: "合成失败",
};
