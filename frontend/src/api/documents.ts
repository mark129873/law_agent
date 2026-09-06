// 知识库文档 API：列表 / 上传 / 删除（对应后端 /api/documents）
import { ApiError, request } from './client'
import type { KnowledgeDocument } from '../types'

/** 允许上传的扩展名白名单（与后端校验保持一致，前端先拦一道给用户即时反馈） */
export const ALLOWED_EXTENSIONS = ['.pdf', '.txt', '.md']

/** 上传大小上限：20MB（与后端一致） */
export const MAX_FILE_SIZE = 20 * 1024 * 1024

/** 获取已上传的文档列表 */
export function listDocuments(): Promise<KnowledgeDocument[]> {
  return request<KnowledgeDocument[]>('/api/documents')
}

/**
 * 上传文档。
 * 上传用的是 multipart/form-data（文件无法转成 JSON），所以不能走统一的 request，
 * 但错误处理保持一致：后端非 2xx 仍是 {code,message}，解析后抛 ApiError。
 */
export async function uploadDocument(file: File): Promise<KnowledgeDocument> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch('/api/documents', { method: 'POST', body: form })
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { code?: number; message?: string } | null
    throw new ApiError(data?.code ?? res.status, data?.message ?? `上传失败（HTTP ${res.status}）`)
  }
  return (await res.json()) as KnowledgeDocument
}

/** 删除文档（后端会级联删除向量库中的对应数据） */
export function deleteDocument(documentId: string): Promise<null> {
  return request<null>(`/api/documents/${documentId}`, { method: 'DELETE' })
}
