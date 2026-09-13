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
  /** 参考文档来源：仅 RAG 检索有命中的回答携带（后端持久化，历史消息同样可展示） */
  sources?: ReferenceSource[] | null
  /**
   * 思考块过程记录（BE-041/BE-042/FE-016）：仅本地展示不持久化，刷新后消失；
   * done 时由 AppContext 把流式过程快照挂到消息上
   */
  steps?: ThoughtLine[] | null
  /** 检索策略快照（FE-014/FE-016）：done 时挂到消息上，思考块内展示 */
  subQueries?: string[] | null
  /** 思考总耗时（毫秒，前端墙钟）：done 时记录，思考块收起标题显示 */
  thinkingMs?: number
}

/** 节点执行状态（BE-041）：一个后端处理环节的展示条目 */
export interface NodeStatus {
  /** 节点名（如 hybrid_retriever_node），同一节点重跑时复用同一行 */
  node: string
  /** 中文展示标签（如「检索知识库」） */
  label: string
  /** 结束耗时（毫秒）；undefined 表示该环节仍在执行中 */
  durationMs?: number
}

/**
 * 思考块内的一行（BE-042/FE-016）：节点状态行或思考内容行。
 * kind 兼容缺省：FE-015 的旧快照行没有 kind 字段，按状态行渲染。
 */
export interface ThoughtLine {
  /** status = 节点起止行（同节点复用同一行）；text = 思考内容行（追加） */
  kind?: 'status' | 'text'
  /** 产生该行的节点名 */
  node: string
  /** 中文展示标签（如「检索知识库」） */
  label: string
  /** status 行：结束耗时（毫秒）；undefined 表示仍在执行中 */
  durationMs?: number
  /** text 行：思考内容文本（后端已截断 ≤120 字，前端零截断逻辑） */
  text?: string
}

/** 参考文档来源：RAG 回答引用的一条知识库片段（数组顺序即展示序号） */
export interface ReferenceSource {
  source: string
  content: string
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
  | { type: 'sources'; sources: ReferenceSource[] } // RAG 检索命中：参考文档来源（先于当轮 delta）
  | { type: 'plan'; sub_queries: string[] } // 检索规划产出的全部查询（检索策略展示，重规划时再次出现）
  | { type: 'regenerating' } // 校验未通过，回答将清空重写
  | { type: 'status'; node: string; label: string; phase: 'start' | 'end'; duration_ms?: number } // 节点执行状态（BE-041，浅色过程展示）
  | { type: 'think'; node: string; label: string; text: string } // 思考内容行（BE-042：决策输出/运行细节/流转说明，后端已截断）
  | { type: 'done'; conversation_id: string } // 回答正常结束
  | { type: 'error'; message: string } // 服务端处理出错
