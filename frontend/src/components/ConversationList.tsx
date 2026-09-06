// 侧边栏「对话」列表：展示历史会话，点击切换到对应会话。
// 删除交互（FE-006）：悬停条目出现删除图标 → 点击进入二次确认态 → 确认后删除。
// 两步确认的原因：删除是危险操作且不可恢复，直接删除容易误触。
// 数据来自全局状态（AppContext），本组件不直接请求接口。
import { useState } from 'react'
import { Trash } from '@phosphor-icons/react'
import { useAppStore } from '../state/AppContext'

export default function ConversationList() {
  const { conversations, activeId, openConversation, removeConversation } = useAppStore()

  /** 正在二次确认删除的会话 id；null 表示没有条目处于确认态 */
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  /** 删除失败的提示信息（删除失败时显示在列表顶部，不打断列表） */
  const [deleteError, setDeleteError] = useState<string | null>(null)

  /** 确认删除：交给全局状态层处理，成功后退出确认态，失败显示提示 */
  async function handleDelete(id: string) {
    try {
      await removeConversation(id)
      setConfirmingId(null)
      setDeleteError(null)
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '删除失败，请重试')
    }
  }

  if (conversations.length === 0) {
    return <p className="px-2 py-8 text-center text-xs text-ink-faint">暂无历史对话</p>
  }

  return (
    <div>
      {deleteError && (
        <p className="mb-2 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">{deleteError}</p>
      )}
      <ul className="space-y-0.5">
        {conversations.map((conversation) => {
          const active = conversation.id === activeId
          const confirming = confirmingId === conversation.id
          return (
            <li key={conversation.id} className="group relative">
              {confirming ? (
                // 二次确认态：条目展开为「删除该对话？+ 删除/取消」
                <div className="flex items-center justify-between gap-1 rounded-lg border border-line bg-elevated px-3 py-2 shadow-sm">
                  <span className="truncate text-xs text-ink-soft">删除该对话？</span>
                  <span className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      onClick={() => void handleDelete(conversation.id)}
                      className="rounded-md bg-red-600 px-2 py-0.5 text-xs text-white transition hover:bg-red-500 active:scale-[0.98]"
                    >
                      删除
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingId(null)}
                      className="rounded-md px-2 py-0.5 text-xs text-ink-soft transition hover:text-ink"
                    >
                      取消
                    </button>
                  </span>
                </div>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => void openConversation(conversation.id)}
                    // 右侧留出删除图标的位置（pr-8），选中态浮起，未选中态弱化
                    className={`w-full truncate rounded-lg px-3 py-2 pr-8 text-left text-sm transition ${
                      active
                        ? 'bg-elevated font-medium text-ink shadow-sm'
                        : 'text-ink-soft hover:bg-app hover:text-ink'
                    }`}
                    title={conversation.title}
                  >
                    {conversation.title}
                  </button>
                  {/* 悬停出现的删除入口：平时透明，group-hover 时显示 */}
                  <button
                    type="button"
                    aria-label={`删除对话 ${conversation.title}`}
                    onClick={() => setConfirmingId(conversation.id)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-ink-faint opacity-0 transition hover:text-danger group-hover:opacity-100"
                  >
                    <Trash size={13} />
                  </button>
                </>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
