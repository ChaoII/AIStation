export default {
  // 页面标题 / 描述
  title: "차량 번호판 데이터 합성",
  sub: "다양한 국내 차량 번호판(파란색 / 신에너지 / 노란색 / 2층 / 검은색 / 버스 / 경찰)을 생성하며, 원근, 회전, 노이즈, 오염, 가림, 블러 등의 변형과 검출 상자 주석을 포함합니다.",

  // 表单
  plateType: "번호판 유형",
  dataset: "대상 데이터셋",
  datasetPlaceholder: "기록할 데이터셋",
  count: "수량",
  seed: "랜덤 시드",
  disturbance: "변형",
  closed: "비활성화",
  restoreDefault: "기본값 복원",
  collapseAll: "모두 접기",
  expandAll: "모두 펼치기",
  disturbHint:
    "비활성화된 변형은 생성에서 제외됩니다. 매개변수는 랜덤 범위 [하한 ~ 상한]입니다.",
  output: "출력",
  writeDataset: "데이터셋에 기록",
  previewOnly: "미리보기만",
  writeAnnotation: "주석 기록",
  noAnnotation: "주석 없음",
  start: "합성 시작",
  tip: "팁: 데이터셋이 선택되지 않았거나 '데이터셋에 기록'이 꺼져 있으면 미리보기만 표시됩니다. 데이터셋을 선택하고 기록을 활성화하면 합성된 이미지가 저장되고 검출 주석 작업이 자동으로 생성됩니다.",

  // 结果
  resultCount: "합성 결과 ({count})",
  notUploaded: "기록되지 않음 (미리보기만)",
  taskNo: "작업 #{id}",
  resultAlt: "합성된 번호판",
  savedStore: "저장됨 #{id}",

  // 历史
  historyTitle: "합성 작업 기록",
  refresh: "새로고침",
  noJobs: "아직 합성 작업이 없습니다",
  jobId: "작업 ID",
  params: "매개변수",
  total: "전체",
  status: "상태",
  createdTime: "생성 시간",

  // 脚本可见文案
  plateTypeBlue: "파란색 (승용차)",
  statusCompleted: "완료",
  statusRunning: "실행 중",
  statusFailed: "실패",
  statusPending: "대기 중",
  jobParamText: "{count}개 생성 · {mode}",
  store: "저장",
  preview: "미리보기",
  generateSuccess: "합성 완료, 총 {count}개 이미지",
  generateFailed: "합성에 실패했습니다",
};
