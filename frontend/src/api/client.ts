// 统一 API 客户端：所有普通请求都从这里发出，UI 组件不允许直接写 fetch。
// 好处：错误结构解析、JSON 序列化只写一遍；后端契约变化时只改这一个文件。
import type { ApiErrorBody } from '../types'

/** 带后端错误码的错误对象：页面捕获后可以给出友好提示 */
export class ApiError extends Error {
  /** 后端业务错误码（如 40401 会话不存在、40001 格式不支持） */
  code: number

  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

/** request 的可选参数：请求方法与请求体 */
interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE'
  /** 任意可 JSON 序列化的对象，会自动转成 JSON 字符串并补上请求头 */
  body?: unknown
}

/**
 * 发起请求并把响应解析成 JSON。
 * - 2xx：返回解析后的数据；204（删除成功）没有响应体，返回 null；
 * - 非 2xx：按后端统一错误结构 {code,message} 解析后抛出 ApiError。
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const res = await fetch(path, {
    method: options.method ?? 'GET',
    headers: options.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  })

  if (!res.ok) {
    // 后端保证非 2xx 都是 {code,message}；万一解析失败就用兜底文案
    let code = res.status
    let message = `请求失败（HTTP ${res.status}）`
    try {
      const data = (await res.json()) as ApiErrorBody
      if (typeof data.code === 'number' && typeof data.message === 'string') {
        code = data.code
        message = data.message
      }
    } catch {
      // 响应体不是 JSON 时保持兜底文案即可
    }
    throw new ApiError(code, message)
  }

  if (res.status === 204) return null as T
  return (await res.json()) as T
}
