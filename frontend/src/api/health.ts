// 健康检查 API：用于前端界面上显示"后端连接状态"
import { request } from './client'
import type { HealthResponse } from '../types'

/** 探测后端服务是否可用 */
export function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health')
}
