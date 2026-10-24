export default {
  // 页面标题 / 描述
  title: "ナンバープレートデータ合成",
  sub: "様々な国内のナンバープレート（青 / 新エネルギー / 黄 / 二階建て / 黒 / 教習車 / 警察車）を生成し、遠近法、回転、ノイズ、汚れ、遮蔽、ぼやけなどの摂動と、検出ボックスのアノテーションを加えます。",

  // 表单
  plateType: "プレート種別",
  dataset: "対象データセット",
  datasetPlaceholder: "書き込み先データセット",
  count: "枚数",
  seed: "ランダムシード",
  disturbance: "摂動",
  closed: "無効",
  restoreDefault: "デフォルトに戻す",
  collapseAll: "すべて折りたたむ",
  expandAll: "すべて展開",
  disturbHint:
    "無効にした摂動は生成から除外されます。パラメータはランダム範囲 [下限 ~ 上限] です。",
  output: "出力",
  writeDataset: "データセットに書き込む",
  previewOnly: "プレビューのみ",
  writeAnnotation: "アノテーションを書き込む",
  noAnnotation: "アノテーションなし",
  start: "合成を開始",
  tip: "ヒント：データセットを選択しない場合、または 'データセットに書き込む' がオフの場合はプレビューのみ表示されます。データセットを選択して書き込みを有効にすると、合成画像が保存され、検出アノテーションタスクが自動作成されます。",

  // 结果
  resultCount: "合成結果（{count}）",
  notUploaded: "未書き込み（プレビューのみ）",
  taskNo: "タスク #{id}",
  resultAlt: "合成されたプレート",
  savedStore: "保存済み #{id}",

  // 历史
  historyTitle: "合成タスク履歴",
  refresh: "更新",
  noJobs: "合成タスクがまだありません",
  jobId: "タスク ID",
  params: "パラメータ",
  total: "合計",
  status: "状態",
  createdTime: "作成時刻",

  // 脚本可见文案
  plateTypeBlue: "青（乗用車）",
  statusCompleted: "完了",
  statusRunning: "実行中",
  statusFailed: "失敗",
  statusPending: "保留中",
  jobParamText: "{count} 枚生成 · {mode}",
  store: "保存",
  preview: "プレビュー",
  generateSuccess: "合成が完了しました。合計 {count} 枚",
  generateFailed: "合成に失敗しました",
};
