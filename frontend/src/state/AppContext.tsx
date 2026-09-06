// 全局状态中心：把「会话、消息、文档」等跨组件共享的数据集中在一处。
// 为什么用 React Context 而不是 Redux 之类的库：
//   本项目状态简单，Context 是 React 自带能力，代码量少、概念少（前端规范：简洁精炼）。
// 使用方式：组件里调用 useAppStore() 拿到状态和动作方法。
// 所有网络请求都发生在 state/api 层，UI 组件不直接 fetch，保证数据访问只有一份实现。
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { Conversation, KnowledgeDocument, Message } from '../types'
import * as conversationsApi from '../api/conversations'
import * as documentsApi from '../api/documents'
import { streamChat } from '../api/chat'

/** 侧边栏的两个视图：对话列表 / 知识库管理（PRODUCT.md：两者同处侧边栏，按钮切换） */
export type SidebarView = 'chat' | 'knowledge'

/** Context 暴露给组件的全部内容（状态 + 动作方法） */
interface AppContextValue {
  // —— 界面状态 ——
  sidebarView: SidebarView
  setSidebarView: (view: SidebarView) => void

  // —— 会话状态 ——
  conversations: Conversation[]
  /** 当前会话 id；null 表示"新对话"（会话对象还没真正创建） */
  activeId: string | null
  /** 顶栏显示的标题：有会话用会话标题，否则是"新对话" */
  activeTitle: string
  /** 当前会话的消息（按时间正序） */
  messages: Message[]
  /** 正在加载历史消息 */
  loadingMessages: boolean

  // —— 流式问答状态 ——
  /** 正在流式生成回答（生成中禁止重复发送与切换会话） */
  isStreaming: boolean
  /** 流式/提问过程的错误信息；null 表示无错误 */
  streamError: string | null

  // —— 会话动作 ——
  refreshConversations: () => Promise<void>
  openConversation: (id: string) => Promise<void>
  startNewChat: () => void
  /** 创建会话并置为当前会话（插入列表顶部）；失败时抛 ApiError 由调用方提示 */
  createConversation: (title: string) => Promise<Conversation>
  /** 删除会话并同步本地列表；删的是当前会话时自动回到"新对话" */
  removeConversation: (id: string) => Promise<void>
  /** 发送提问：必要时先建会话，然后流式接收回答并写入 messages */
  sendQuestion: (question: string) => Promise<void>
  clearStreamError: () => void

  // —— 知识库状态与动作 ——
  documents: KnowledgeDocument[]
  refreshDocuments: () => Promise<void>
  /** 上传文档；返回结果对象（不抛异常）方便页面直接展示成功/失败反馈 */
  uploadDocument: (file: File) => Promise<{ ok: boolean; message: string }>
  /** 删除文档并同步本地列表；失败时抛 ApiError 由调用方提示 */
  removeDocument: (id: string) => Promise<void>
}

const AppContext = createContext<AppContextValue | null>(null)

/** 最外层 Provider：把状态分发给整棵组件树 */
export function AppProvider({ children }: { children: ReactNode }) {
  const [sidebarView, setSidebarView] = useState<SidebarView>('chat')

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loadingMessages, setLoadingMessages] = useState(false)
  // 用 ref 同步记录流式状态：异步回调里读 state 变量会拿到闭包旧值，
  // 导致"生成中"判断失效。声明在最前面，会话动作与提问动作都要用它做守卫。
  const streamingRef = useRef(false)

  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])

  // ———————— 会话动作 ————————

  /** 拉取会话列表（后端按创建时间倒序返回）；失败静默（侧边栏显示为空即可） */
  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await conversationsApi.listConversations())
    } catch (error) {
      console.error('加载会话列表失败', error)
    }
  }, [])

  /** 打开某个会话：记录 id 并加载它的全部历史消息 */
  const openConversation = useCallback(async (id: string) => {
    // 生成中禁止切换：切换会清空消息区，会打断流式增量写入，造成状态错乱
    if (streamingRef.current) return
    setActiveId(id)
    setLoadingMessages(true)
    try {
      setMessages(await conversationsApi.listMessages(id))
    } catch (error) {
      console.error('加载历史消息失败', error)
      setMessages([])
    } finally {
      setLoadingMessages(false)
    }
  }, [])

  /** 回到"新对话"空白状态；会话对象延迟到真正发送第一句提问时才创建 */
  const startNewChat = useCallback(() => {
    // 生成中禁止新建/切换视图，理由同 openConversation
    if (streamingRef.current) return
    setActiveId(null)
    setMessages([])
    // 新对话是对话行为：若当前在知识库视图，自动切回对话视图
    setSidebarView('chat')
  }, [])

  /** 创建会话：置为当前会话并插入列表顶部 */
  const createConversation = useCallback(async (title: string) => {
    const created = await conversationsApi.createConversation(title)
    setActiveId(created.id)
    setMessages([])
    setConversations((prev) => [created, ...prev])
    return created
  }, [])

  /** 删除会话：调用后端（级联删消息），成功后同步本地状态 */
  const removeConversation = useCallback(
    async (id: string) => {
      await conversationsApi.deleteConversation(id)
      setConversations((prev) => prev.filter((c) => c.id !== id))
      // 删除的正好是当前打开的会话：回到"新对话"
      if (activeId === id) {
        setActiveId(null)
        setMessages([])
      }
    },
    [activeId],
  )

  // ———————— 流式问答 ————————

  const [isStreaming, setIsStreaming] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)

  const clearStreamError = useCallback(() => setStreamError(null), [])

  /** 发送提问：必要时先建会话 → 乐观插入本地消息 → 消费 SSE 流增量更新 */
  const sendQuestion = useCallback(
    async (question: string) => {
      // 生成中不允许重复发送
      if (streamingRef.current) return
      streamingRef.current = true
      setIsStreaming(true)
      setStreamError(null)

      // 本地乐观消息的临时 id 声明在 try 外：catch 里才能清理它们
      const tempUserId = `local-user-${Date.now()}`
      const assistantId = `streaming-${Date.now()}`

      try {
        // 1) 还没有会话：用提问内容（截短）当标题创建，侧边栏能看出每个会话聊了什么
        let conversationId = activeId
        if (!conversationId) {
          conversationId = (await createConversation(question.slice(0, 20))).id
        }

        // 2) 界面先显示用户消息和一个空的助手消息（内容靠流式增量填充）。
        //    本地临时 id 与后端真实 id 无关，仅用于本次渲染。
        const now = new Date().toISOString()
        setMessages((prev) => [
          ...prev,
          { id: tempUserId, role: 'user', content: question, created_at: now },
          { id: assistantId, role: 'assistant', content: '', created_at: now },
        ])

        // 3) 消费 SSE 流：每段增量追加到助手消息；完成后后端已持久化完整回答
        await streamChat(
          { conversationId, question },
          {
            onDelta: (content) =>
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + content } : m)),
              ),
            onDone: () => {
              // 换掉临时 id（移除流式光标标记），本地内容与后端持久化内容一致，无需重新拉取
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, id: `assistant-${Date.now()}` } : m)),
              )
            },
            onError: (message) => {
              setStreamError(message)
              // 出错时移除空的助手占位；已有部分内容的保留展示。
              // 后端"异常中断不落库"，所以刷新后看到的与本地一致。
              setMessages((prev) => prev.filter((m) => m.id !== assistantId || m.content !== ''))
            },
          },
        )
      } catch (error) {
        // 会话创建失败或网络层异常：清掉本条乐观消息（界面上不留半截内容）并提示
        setMessages((prev) => prev.filter((m) => m.id !== tempUserId && m.id !== assistantId))
        setStreamError(error instanceof Error ? error.message : '网络异常，请稍后重试')
      } finally {
        streamingRef.current = false
        setIsStreaming(false)
      }
    },
    [activeId, createConversation],
  )

  // ———————— 知识库动作 ————————

  /** 拉取文档列表；失败静默 */
  const refreshDocuments = useCallback(async () => {
    try {
      setDocuments(await documentsApi.listDocuments())
    } catch (error) {
      console.error('加载文档列表失败', error)
    }
  }, [])

  /**
   * 上传文档。返回 {ok, message} 而不是抛异常，
   * 这样页面只需要一行 if 就能展示成功/失败反馈。
   */
  const uploadDocument = useCallback(
    async (file: File) => {
      try {
        const doc = await documentsApi.uploadDocument(file)
        await refreshDocuments()
        return {
          ok: doc.status !== 'failed',
          message:
            doc.status === 'failed'
              ? `《${doc.filename}》处理失败，请检查文件内容`
              : `《${doc.filename}》上传成功，已可用于问答`,
        }
      } catch (error) {
        return { ok: false, message: error instanceof Error ? error.message : '上传失败，请稍后重试' }
      }
    },
    [refreshDocuments],
  )

  /** 删除文档：调用后端（级联删向量），成功后同步本地列表 */
  const removeDocument = useCallback(async (id: string) => {
    await documentsApi.deleteDocument(id)
    setDocuments((prev) => prev.filter((d) => d.id !== id))
  }, [])

  // 首次挂载：拉取两份列表
  useEffect(() => {
    void refreshConversations()
    void refreshDocuments()
  }, [refreshConversations, refreshDocuments])

  // 当前会话标题：从列表里查标题；找不到（或还没创建）就显示"新对话"
  const activeTitle = useMemo(
    () => conversations.find((c) => c.id === activeId)?.title ?? '新对话',
    [conversations, activeId],
  )

  // 用 useMemo 缓存 value：避免每次渲染都生成新对象导致所有组件白白重渲染
  const value = useMemo<AppContextValue>(
    () => ({
      sidebarView,
      setSidebarView,
      conversations,
      activeId,
      activeTitle,
      messages,
      loadingMessages,
      refreshConversations,
      openConversation,
      startNewChat,
      createConversation,
      removeConversation,
      sendQuestion,
      isStreaming,
      streamError,
      clearStreamError,
      documents,
      refreshDocuments,
      uploadDocument,
      removeDocument,
    }),
    [
      sidebarView,
      conversations,
      activeId,
      activeTitle,
      messages,
      loadingMessages,
      refreshConversations,
      openConversation,
      startNewChat,
      createConversation,
      removeConversation,
      sendQuestion,
      isStreaming,
      streamError,
      clearStreamError,
      documents,
      refreshDocuments,
      uploadDocument,
      removeDocument,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

/** 组件里获取全局状态的钩子；必须在 AppProvider 内使用 */
export function useAppStore(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) {
    throw new Error('useAppStore 必须在 AppProvider 内使用')
  }
  return ctx
}
