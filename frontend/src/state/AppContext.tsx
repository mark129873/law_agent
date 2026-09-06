// 全局状态中心：把「会话、消息、文档」等跨组件共享的数据集中在一处。
// 为什么用 React Context 而不是 Redux 之类的库：
//   本项目状态简单，Context 是 React 自带能力，代码量少、概念少（前端规范：简洁精炼）。
// 使用方式：组件里调用 useAppStore() 拿到状态和动作方法。
// 所有网络请求都发生在 state/api 层，UI 组件不直接 fetch，保证数据访问只有一份实现。
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Conversation, KnowledgeDocument, Message } from '../types'
import * as conversationsApi from '../api/conversations'
import * as documentsApi from '../api/documents'

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

  // —— 会话动作 ——
  refreshConversations: () => Promise<void>
  openConversation: (id: string) => Promise<void>
  startNewChat: () => void
  /** 创建会话并置为当前会话（插入列表顶部）；失败时抛 ApiError 由调用方提示 */
  createConversation: (title: string) => Promise<Conversation>
  /** 删除会话并同步本地列表；删的是当前会话时自动回到"新对话" */
  removeConversation: (id: string) => Promise<void>

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
    setActiveId(null)
    setMessages([])
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
