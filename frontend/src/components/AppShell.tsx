// 应用整体布局（Shell）：左侧边栏 + 右侧主区域。
// 主区域内容跟随侧边栏视图切换：对话 → 聊天页；知识库 → 知识库管理页。
// 所有页面共用这一套布局与间距规范，保证视觉一致（FE-003 的核心目标）。
import { useAppStore } from '../state/AppContext'
import Sidebar from './Sidebar'
import ChatPage from '../pages/ChatPage'
import KnowledgePage from '../pages/KnowledgePage'

export default function AppShell() {
  const { sidebarView } = useAppStore()

  return (
    // h-dvh：占满可视高度且不受移动端地址栏伸缩影响（比 h-screen 稳定）
    <div className="flex h-dvh overflow-hidden">
      <Sidebar />
      <main className="min-w-0 flex-1">
        {sidebarView === 'chat' ? <ChatPage /> : <KnowledgePage />}
      </main>
    </div>
  )
}
