// 纯函数工具：不依赖 React、不发请求，只做数据格式化，方便复用与阅读。

/** 文件大小格式化：把字节数转成人类可读的 B / KB / MB */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 日期格式化：后端返回 ISO 字符串，界面只显示本地日期 */
export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString('zh-CN')
}
