/** 评测页通用：把 Blob 存成本地文件（导出 CSV 用）。 */
export function saveBlob(data: any, filename: string) {
  const blob = data instanceof Blob ? data : new Blob([data]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // 立刻 revoke 在部分浏览器会中断下载，延迟一拍
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
