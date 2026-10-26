export default {
  // 頁面標題 / 描述
  title: "車牌資料合成",
  sub: "產生國內各類車牌（藍/新能源/黃/雙層/黑/教練/警用），帶透視、旋轉、噪點、污漬、遮擋、模糊等擾動，並產出偵測框標註",

  // 表單
  plateType: "車牌類型",
  dataset: "目標資料集",
  datasetPlaceholder: "寫入的資料集",
  count: "產生數量",
  seed: "隨機種子",
  disturbance: "擾動",
  closed: "已關閉",
  restoreDefault: "恢復預設",
  collapseAll: "收合全部",
  expandAll: "展開全部",
  disturbHint: "關閉的擾動不參與產生；參數為隨機區間 [下限 ~ 上限]",
  output: "輸出",
  writeDataset: "寫入資料集",
  previewOnly: "僅預覽",
  writeAnnotation: "寫標註",
  noAnnotation: "不寫標註",
  start: "開始合成",
  tip: "提示：未選擇資料集或關閉「寫入資料集」時僅預覽；選擇資料集並開啟寫入後，合成圖會入庫並自動建立偵測標註任務。",

  // 結果
  resultCount: "合成結果（{count} 張）",
  notUploaded: "未寫入（僅預覽）",
  taskNo: "任務 #{id}",
  resultAlt: "合成車牌",
  savedStore: "已入庫 #{id}",

  // 歷史
  historyTitle: "合成任務歷史",
  refresh: "重新整理",
  noJobs: "暫無合成任務",
  jobId: "任務ID",
  params: "參數",
  total: "數量",
  status: "狀態",
  createdTime: "建立時間",

  // 腳本可見文案
  plateTypeBlue: "藍牌(小型汽車)",
  statusCompleted: "已完成",
  statusRunning: "進行中",
  statusFailed: "失敗",
  statusPending: "待產生",
  jobParamText: "產生{count}張·{mode}",
  store: "入庫",
  preview: "預覽",
  generateSuccess: "合成完成，共 {count} 張",
  generateFailed: "合成失敗",
};
