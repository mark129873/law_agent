// 前端类型定义：与后端 API 契约（docs/ARCHITECTURE.md 第 7 节）一一对应。
// 为什么集中定义：后端接口字段变化时只改这里，TypeScript 编译器会把所有
// 受影响的组件标红，避免"改了接口忘了改页面"这类低级错误。

/** 会话（对应后端 ConversationResponse） */
export interface Conversation {
  id: string
  title: string
  created_at: string
}

/** 消息角色：user 是用户提问，assistant 是模型回答 */
export type MessageRole = 'user' | 'assistant'

/** 消息（对应后端 MessageResponse） */
export interface Message {
  id: string
  role: MessageRole
  content: string
  created_at: string
}

/** 文档处理状态：pending/processing 处理中，ready 已入库可检索，failed 处理失败 */
export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed'

/** 知识库文档（对应后端 DocumentResponse） */
export interface KnowledgeDocument {
  id: string
  filename: string
  file_size: number
  status: DocumentStatus
  created_at: string
}

/** 健康检查响应（对应后端 GET /api/health） */
export interface HealthResponse {
  status: string
}

/** 后端统一错误结构：所有非 2xx 响应都是这个形状 */
export interface ApiErrorBody {
  code: number
  message: string
}

/** 流式问答接口的 SSE 事件（即每条 data: {...} 里的 JSON） */
export type ChatStreamEvent =
  | { type: 'delta'; content: string } // 一小段增量回答文本
  | { type: 'done'; conversation_id: string } // 回答正常结束
  | { type: 'error'; message: string } // 服务端处理出错
