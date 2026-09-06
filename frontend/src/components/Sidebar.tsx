// 应用侧边栏：品牌标识、「新对话」按钮、「对话 / 知识库」视图切换、列表区。
// 布局参考 Codex Web：窄边栏、低饱和背景、克制的交互反馈（仅 hover / active 微动效）。
import { BookOpenText, ChatCircleDots, Plus } from '@phosphor-icons/react'
import { useAppStore } from '../state/AppContext'
import ConversationList from './ConversationList'
import KnowledgeSummary from './KnowledgeSummary'

/** 视图切换按钮的样式：选中态浮起（浅底 + 描边 + 阴影），未选中态弱化 */
function tabClass(active: boolean): string {
  return `flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition active:scale-[0.98] ${
    active
      ? 'border-line bg-elevated font-medium text-ink shadow-sm'
      : 'border-transparent text-ink-soft hover:text-ink'
  }`
}

export default function Sidebar() {
  const { sidebarView, setSidebarView, startNewChat } = useAppStore()

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col border-r border-line bg-sidebar">
      {/* 品牌区：方块字标 + 产品名 */}
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-ink text-sm font-semibold text-app">
          法
        </div>
        <span className="text-sm font-semibold text-ink">法律知识库助手</span>
      </div>

      {/* 新对话：回到空白对话状态（第一句提问发出时才真正创建会话） */}
      <div className="px-3">
        <button
          type="button"
          onClick={startNewChat}
          className="flex w-full items-center gap-2 rounded-lg border border-line bg-elevated px-3 py-2 text-sm font-medium text-ink transition hover:border-ink-faint active:scale-[0.98]"
        >
          <Plus size={15} weight="bold" />
          新对话
        </button>
      </div>

      {/* 视图切换：PRODUCT.md 要求对话历史与知识库管理同处侧边栏，通过按钮切换 */}
      <div className="flex gap-1 px-3 py-3">
        <button
          type="button"
          onClick={() => setSidebarView('chat')}
          className={tabClass(sidebarView === 'chat')}
        >
          <ChatCircleDots size={15} />
          对话
        </button>
        <button
          type="button"
          onClick={() => setSidebarView('knowledge')}
          className={tabClass(sidebarView === 'knowledge')}
        >
          <BookOpenText size={15} />
          知识库
        </button>
      </div>

      {/* 列表区：随视图切换显示历史会话或知识库汇总 */}
      <nav className="flex-1 overflow-y-auto px-3 pb-3">
        {sidebarView === 'chat' ? <ConversationList /> : <KnowledgeSummary />}
      </nav>
    </aside>
  )
}
