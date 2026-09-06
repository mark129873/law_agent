// 会话相关 API：列表 / 创建 / 消息查询 / 删除（对应后端 /api/conversations）
import { request } from './client'
import type { Conversation, Message } from '../types'

/** 获取全部会话（后端按创建时间倒序返回） */
export function listConversations(): Promise<Conversation[]> {
  return request<Conversation[]>('/api/conversations')
}

/**
 * 创建会话。
 * title 传用户的第一句提问（截短即可），这样侧边栏列表能看出每个会话聊了什么，
 * 因为后端不会在提问后自动改标题。
 */
export function createConversation(title: string): Promise<Conversation> {
  return request<Conversation>('/api/conversations', { method: 'POST', body: { title } })
}

/** 获取某个会话的全部消息（按时间正序） */
export function listMessages(conversationId: string): Promise<Message[]> {
  return request<Message[]>(`/api/conversations/${conversationId}/messages`)
}

/** 删除会话（后端会级联删除其中的消息） */
export function deleteConversation(conversationId: string): Promise<null> {
  return request<null>(`/api/conversations/${conversationId}`, { method: 'DELETE' })
}
