export default {
  // 页面标题 / 描述
  title: "Tổng hợp dữ liệu biển số xe",
  sub: "Tạo các biển số xe nội địa khác nhau (xanh / năng lượng mới / vàng / hai tầng / đen / xe khách / cảnh sát), với các nhiễu như phối cảnh, xoay, nhiễu, vết bẩn, che khuất và mờ, cùng chú thích hộp phát hiện.",

  // 表单
  plateType: "Loại biển số",
  dataset: "Tập dữ liệu đích",
  datasetPlaceholder: "Tập dữ liệu để ghi vào",
  count: "Số lượng",
  seed: "Hạt giống ngẫu nhiên",
  disturbance: "Nhiễu",
  closed: "Đã tắt",
  restoreDefault: "Khôi phục mặc định",
  collapseAll: "Thu gọn tất cả",
  expandAll: "Mở rộng tất cả",
  disturbHint:
    "Các nhiễu đã tắt sẽ bị loại khỏi quá trình tạo; tham số là khoảng ngẫu nhiên [thấp ~ cao].",
  output: "Đầu ra",
  writeDataset: "Ghi vào tập dữ liệu",
  previewOnly: "Chỉ xem trước",
  writeAnnotation: "Ghi chú thích",
  noAnnotation: "Không chú thích",
  start: "Bắt đầu tổng hợp",
  tip: "Mẹo: khi không chọn tập dữ liệu hoặc tắt 'Ghi vào tập dữ liệu', chỉ hiển thị bản xem trước; sau khi chọn tập dữ liệu và bật ghi, các hình ảnh tổng hợp được lưu trữ và một nhiệm vụ chú thích phát hiện được tạo tự động.",

  // 结果
  resultCount: "Kết quả tổng hợp ({count})",
  notUploaded: "Chưa ghi (chỉ xem trước)",
  taskNo: "Nhiệm vụ #{id}",
  resultAlt: "Biển số đã tổng hợp",
  savedStore: "Đã lưu #{id}",

  // 历史
  historyTitle: "Lịch sử nhiệm vụ tổng hợp",
  refresh: "Làm mới",
  noJobs: "Chưa có nhiệm vụ tổng hợp nào",
  jobId: "ID nhiệm vụ",
  params: "Tham số",
  total: "Tổng",
  status: "Trạng thái",
  createdTime: "Thời gian tạo",

  // 脚本可见文案
  plateTypeBlue: "Xanh (xe con)",
  statusCompleted: "Hoàn thành",
  statusRunning: "Đang chạy",
  statusFailed: "Thất bại",
  statusPending: "Đang chờ",
  jobParamText: "Đã tạo {count} · {mode}",
  store: "Lưu trữ",
  preview: "Xem trước",
  generateSuccess: "Tổng hợp hoàn tất, tổng cộng {count} hình ảnh",
  generateFailed: "Tổng hợp thất bại",
};
