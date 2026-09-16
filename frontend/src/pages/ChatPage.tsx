// 对话主页面：顶部标题栏 + 消息滚动区 + 底部输入区。
// 职责边界：本组件只负责"长什么样"，提问与流式回答的逻辑都在
// AppContext 的 sendQuestion 里（state 层），页面代码保持简单易读。
import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Globe } from '@phosphor-icons/react'
import { useAppStore } from '../state/AppContext'
import MessageBlock from '../components/MessageBlock'

/** 空状态展示的建议问题：点击直接填入输入框 */
const SUGGESTIONS = [
  '试用期最长不能超过几个月？',
  '发明专利权的保护期限是多少年？',
  '合同违约金约定过高怎么办？',
]

export default function ChatPage() {
  const {
    activeTitle,
    messages,
    loadingMessages,
    isStreaming,
    streamError,
    clearStreamError,
    subQueries,
    thoughts,
    sendQuestion,
    webSearchMode,
    webSearchNotice,
    toggleWebSearch,
  } = useAppStore()

  const [draft, setDraft] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // 消息变化（含流式增量）时滚到底部，保证始终看到最新内容
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  /** 输入框自适应高度：随内容增长，到 160px 后内部滚动 */
  function autoResize() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  /** 发送提问：交给状态层处理，随后清空输入框 */
  async function handleSend() {
    const text = draft.trim()
    if (!text || isStreaming) return
    setDraft('')
    requestAnimationFrame(autoResize) // 等输入框内容清空后再重算高度
    await sendQuestion(text, webSearchMode)
  }

  return (
    <div className="flex h-full flex-col bg-app">
      {/* 顶栏：当前会话标题 + 生成状态 */}
      <header className="flex h-12 shrink-0 items-center justify-between gap-4 border-b border-line px-6">
        <span className="truncate text-sm font-medium text-ink">{activeTitle}</span>
        {isStreaming && <span className="shrink-0 text-xs text-ink-faint">正在生成…</span>}
      </header>

      {/* 消息区：为空时展示欢迎态，否则渲染消息列表 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {messages.length === 0 && !loadingMessages ? (
          <div className="flex h-full flex-col items-center justify-center gap-6 px-6">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ink text-lg font-semibold text-app">
              法
            </div>
            <div className="text-center">
              <h1 className="text-xl font-semibold text-ink">有什么法律问题？</h1>
              <p className="mt-1.5 text-sm text-ink-soft">
                基于知识库中的文档回答并注明来源；没有依据时会明确告知
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => {
                    setDraft(suggestion)
                    textareaRef.current?.focus()
                  }}
                  className="rounded-full border border-line px-3.5 py-1.5 text-xs text-ink-soft transition hover:border-ink-faint hover:text-ink active:scale-[0.98]"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8">
            {loadingMessages && (
              <p className="text-center text-xs text-ink-faint">正在加载历史消息…</p>
            )}
            {messages.map((message) => {
              const isCurrent = message.id.startsWith('streaming-')
              return (
                <MessageBlock
                  key={message.id}
                  message={message}
                  streaming={isCurrent}
                  // 检索策略：生成中用 Context 实时值；已完成的消息用快照（思考块内展示）
                  subQueries={isCurrent ? subQueries : message.subQueries}
                  // 思考过程行：生成中用 Context 实时值；已完成的消息用快照（FE-016 保留显示）
                  steps={isCurrent ? thoughts : message.steps}
                  thinkingMs={message.thinkingMs}
                />
              )
            })}
          </div>
        )}
      </div>

      {/* 错误提示条：提问或生成失败时显示，可手动关闭。颜色用主题 danger token，明暗主题都成立 */}
      {streamError && (
        <div className="mx-auto mb-2 flex w-full max-w-3xl items-center justify-between gap-3 rounded-lg border border-danger/30 bg-danger-soft px-4 py-2.5 text-sm text-danger">
          <span className="truncate">{streamError}</span>
          <button
            type="button"
            onClick={clearStreamError}
            className="shrink-0 text-xs underline-offset-2 hover:underline"
          >
            关闭
          </button>
        </div>
      )}

      {/* 输入区：自适应高度输入框 + 联网搜索模式按钮 + 发送按钮 */}
      <div className="shrink-0 px-6 pb-5">
        {webSearchNotice && (
          <div className="mx-auto mb-2 flex w-full max-w-3xl items-center gap-1.5 px-2 text-[11px] text-ink-faint">
            <Globe size={13} className="shrink-0 text-accent" aria-hidden />
            <span className="rounded-full bg-accent-soft px-2 py-1 text-accent">{webSearchNotice.message}</span>
          </div>
        )}
        <div className="mx-auto flex w-full max-w-3xl items-end gap-2 rounded-2xl border border-line bg-elevated p-2 shadow-sm transition focus-within:border-accent">
          <textarea
            ref={textareaRef}
            rows={1}
            value={draft}
            placeholder="输入你的法律问题…"
            className="max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-faint"
            onChange={(event) => {
              setDraft(event.target.value)
              autoResize()
            }}
            onKeyDown={(event) => {
              // Enter 发送；Shift + Enter 换行
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void handleSend()
              }
            }}
          />
          {/* 联网搜索模式按钮：选中态持续显示，直到用户再次点击关闭。 */}
          <button
            type="button"
            onClick={() => void toggleWebSearch()}
            disabled={isStreaming}
            aria-label="联网搜索"
            aria-pressed={webSearchMode}
            title={webSearchMode ? '关闭联网搜索' : '开启联网搜索'}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition active:scale-[0.98] motion-reduce:active:scale-100 ${
              webSearchMode
                ? 'border-accent bg-accent-soft text-accent'
                : 'border-transparent bg-elevated text-ink-faint hover:border-line hover:text-ink-soft'
            } ${isStreaming ? 'cursor-not-allowed opacity-50' : ''}`}
          >
            <Globe size={17} weight={webSearchMode ? 'fill' : 'regular'} />
          </button>
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={!draft.trim() || isStreaming}
            aria-label="发送"
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition active:scale-[0.98] ${
              draft.trim() && !isStreaming
                ? 'bg-accent text-accent-contrast hover:opacity-90'
                : 'bg-elevated text-ink-faint'
            }`}
          >
            <ArrowUp size={16} weight="bold" />
          </button>
        </div>
        <p className="mt-2 text-center text-[11px] text-ink-faint">
          Enter 发送，Shift + Enter 换行；回答由 AI 基于知识库生成，请注意甄别
        </p>
      </div>
    </div>
  )
}
