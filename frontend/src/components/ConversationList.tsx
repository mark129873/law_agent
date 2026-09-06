// 侧边栏「对话」列表：展示历史会话，点击切换到对应会话。
// 数据来自全局状态（AppContext），本组件不直接请求接口。
// 删除交互属于 FE-006，在此文件基础上扩展。
import { useAppStore } from '../state/AppContext'

export default function ConversationList() {
  const { conversations, activeId, openConversation } = useAppStore()

  // 空状态：还没有任何会话
  if (conversations.length === 0) {
    return <p className="px-2 py-8 text-center text-xs text-ink-faint">暂无历史对话</p>
  }

  return (
    <ul className="space-y-0.5">
      {conversations.map((conversation) => {
        const active = conversation.id === activeId
        return (
          <li key={conversation.id}>
            <button
              type="button"
              onClick={() => void openConversation(conversation.id)}
              // 选中态浮起；未选中态弱化、hover 恢复。truncate 防止长标题撑破布局
              className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm transition ${
                active
                  ? 'bg-elevated font-medium text-ink shadow-sm'
                  : 'text-ink-soft hover:bg-app hover:text-ink'
              }`}
              title={conversation.title}
            >
              {conversation.title}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
