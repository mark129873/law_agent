// 单条消息的展示：用户消息右侧气泡，助手消息左侧 Markdown 渲染（低干扰的 Codex 风格）。
// 助手回答用 Markdown 渲染的原因：模型输出普遍含 **加粗**、列表等格式，
// 按字面显示会出现星号噪声；react-markdown 默认不解析原始 HTML，无注入风险。
import { useState } from 'react'
import Markdown from 'react-markdown'
import { Books, Brain, CaretDown, Globe } from '@phosphor-icons/react'
import type { Message, ThoughtLine, ReferenceSource } from '../types'

interface MessageBlockProps {
  message: Message
  /** 该消息是否正在流式生成中（末尾显示闪烁光标 + 思考块默认展开） */
  streaming?: boolean
  /** 检索策略（FE-014/FE-016）：生成中来自 Context，完成后来自消息快照；并入思考块展示 */
  subQueries?: string[] | null
  /** 思考过程行（FE-016）：节点状态行 + 思考内容行，生成中来自 Context，完成后来自消息快照 */
  steps?: ThoughtLine[] | null
  /** 思考总耗时（毫秒）：完成后标题显示「已完成思考 · Ns」 */
  thinkingMs?: number
}

/**
 * 思考块（BE-042/FE-016，豆包式交互）：聚合节点状态行、思考内容行与检索策略。
 * - 生成中默认展开（实时滚动执行过程），完成后自动收起为一行摘要；
 * - 点击标题可随时展开/收回；manualOpen 为 null 表示"跟随默认值"——
 *   这样同一组件在 streaming 由 true 变 false 时自动切换默认形态，
 *   用户手动点过之后则以手动选择为准。
 * - 整体浅色小字 + 左侧竖线缩进，保证"可见但不抢视线"。
 */
function ThinkingPanel({
  lines,
  subQueries,
  streaming,
  thinkingMs,
}: {
  lines: ThoughtLine[]
  subQueries?: string[] | null
  streaming: boolean
  thinkingMs?: number
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null)
  const open = manualOpen ?? streaming
  // 无任何过程内容时不渲染（历史消息刷新后恢复的场景）
  if (lines.length === 0 && !(subQueries && subQueries.length > 0)) return null

  const headerText = streaming
    ? '思考中…'
    : `已完成思考 · ${((thinkingMs ?? 0) / 1000).toFixed(1)}s`

  return (
    <div className="mb-3">
      {/* 标题行：图标 + 文案 + 展开箭头；aria-expanded 让读屏软件感知状态 */}
      <button
        type="button"
        onClick={() => setManualOpen(!open)}
        aria-expanded={open}
        className="inline-flex items-center gap-1 text-[11px] font-medium text-ink-faint transition-colors hover:text-ink-soft"
      >
        <Brain size={13} aria-hidden />
        {headerText}
        <CaretDown
          size={11}
          className={`transition-transform duration-200 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>

      {open && (
        <div className="mt-1.5 space-y-0.5 border-l border-line pl-3">
          {/* 检索策略（plan 事件）：思考块内的独立小节，重规划时覆盖更新 */}
          {subQueries && subQueries.length > 0 && (
            <div className="mb-1.5">
              <p className="text-[11px] font-medium text-ink-faint">
                检索策略（{subQueries.length} 条查询）
              </p>
              <ol className="mt-0.5 list-decimal space-y-0.5 pl-4">
                {subQueries.map((query, index) => (
                  <li key={index} className="text-[11px] leading-relaxed text-ink-faint">
                    {query}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {/* 过程行：按事件到达顺序渲染。状态行显示「正在…/耗时」，
              内容行显示思考文本（后端已截断，前端零截断逻辑） */}
          {lines.map((line, index) => (
            <p key={`${line.kind}-${line.node}-${index}`} className="text-[11px] leading-relaxed text-ink-faint">
              {line.kind === 'text'
                ? line.text
                : line.durationMs === undefined
                  ? `正在${line.label}…`
                  : `${line.label} · ${(line.durationMs / 1000).toFixed(1)}s`}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * 参考文档折叠面板（FE-011）：RAG 回答的引用依据展示。
 * 交互：默认收起只显示按钮，点击展开按序号列出文档名与命中内容；
 * 为什么默认收起：参考内容只是回答的佐证，展开会占据大量纵向空间，
 * 收起态让"有依据可查"与"不干扰阅读"同时成立。
 */
function ReferencePanel({ sources }: { sources: ReferenceSource[] }) {
  const [open, setOpen] = useState(false)
  // aria-expanded/aria-controls 让读屏软件能感知展开状态（无障碍）
  const panelId = `ref-panel-${sources.length}-${sources[0]?.source ?? ''}`

  return (
    <div className="mt-3">
      {/* 折叠按钮：次级样式（描边 + 悬停浮起），强调色只用在图标与计数上，
          保持"参考文档是辅助信息"的视觉层级（色彩一致性：全站唯一强调色） */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-elevated hover:text-ink active:scale-[0.98] motion-reduce:active:scale-100"
      >
        <Books size={14} className="text-accent" aria-hidden />
        参考文档
        {/* 计数徽标：文档数量一眼可读 */}
        <span className="rounded-full bg-accent-soft px-1.5 text-[11px] font-semibold text-accent">
          {sources.length}
        </span>
        <CaretDown
          size={12}
          className={`transition-transform duration-200 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>

      {/* 展开的来源列表：按检索相关度排序（后端顺序即序号），内容纯文本渲染
          （不进 Markdown 解析，文档原文中的特殊字符不会破坏排版） */}
      {open && (
        <ol id={panelId} className="ref-panel-in mt-2 max-h-80 list-none overflow-y-auto rounded-xl border border-line bg-elevated p-0">
          {sources.map((item, index) => (
            <li key={index} className={index > 0 ? 'border-t border-line p-3' : 'p-3'}>
              <div className="flex items-center gap-2">
                {/* 序号徽标：对应"按序号显示参考文档"的产品要求 */}
                <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent">
                  {index + 1}
                </span>
                <span className="truncate text-xs font-medium text-ink" title={item.source}>
                  {item.source}
                </span>
              </div>
              <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">{item.content}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/**
 * 联网搜索内容折叠面板：显示网页标题、可点击地址和最多 300 字预览。
 * 完整正文不会进入前端消息，后端独立搜索日志才是完整留档依据。
 */
function WebSearchPanel({ sources }: { sources: ReferenceSource[] }) {
  const [open, setOpen] = useState(false)
  const panelId = `web-search-panel-${sources.length}`

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-elevated hover:text-ink active:scale-[0.98] motion-reduce:active:scale-100"
      >
        <Globe size={14} className="text-accent" aria-hidden />
        联网搜索内容
        <span className="rounded-full bg-accent-soft px-1.5 text-[11px] font-semibold text-accent">
          {sources.length}
        </span>
        <CaretDown
          size={12}
          className={`transition-transform duration-200 motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
          aria-hidden
        />
      </button>

      {open && (
        <ol id={panelId} className="ref-panel-in mt-2 max-h-96 list-none overflow-y-auto rounded-xl border border-line bg-elevated p-0">
          {sources.map((item, index) => {
            const title = item.title || item.source || '网页来源'
            const preview = item.content.slice(0, 300)
            const isSafeUrl = /^https?:\/\//i.test(item.url || '')
            return (
              <li key={`${item.url}-${index}`} className={index > 0 ? 'border-t border-line p-3' : 'p-3'}>
                <div className="flex items-start gap-2">
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    {isSafeUrl ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="break-words text-xs font-medium text-accent underline-offset-2 hover:underline"
                      >
                        {title}
                      </a>
                    ) : (
                      <span className="break-words text-xs font-medium text-ink">{title}</span>
                    )}
                    {isSafeUrl && <p className="mt-0.5 break-all text-[10px] text-ink-faint">{item.url}</p>}
                  </div>
                </div>
                <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">{preview}</p>
                {item.truncated && <p className="mt-1 text-[10px] text-ink-faint">内容已截断，完整内容已保存到后端搜索日志</p>}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

export default function MessageBlock({
  message,
  streaming = false,
  subQueries = null,
  steps = null,
  thinkingMs,
}: MessageBlockProps) {
  // 用户消息：右侧气泡，限制最大宽度防止长问题占满整行；保持纯文本（whitespace-pre-wrap）
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl border border-line bg-elevated px-4 py-2.5 text-sm leading-relaxed text-ink">
          {message.content}
        </div>
      </div>
    )
  }

  // 是否展示参考文档：仅"有来源 且 不在流式生成中"——
  // 生成中隐藏，让按钮按产品定义在回答完成后出现（避免流式期间布局跳动）
  const allSources = !streaming ? message.sources ?? [] : []
  const localSources = allSources.filter((item) => item.kind !== 'web')
  const webSources = allSources.filter((item) => item.kind === 'web')

  // 助手消息：左侧平铺 + Markdown 渲染；流式光标放在内容之后
  return (
    <div className="text-sm leading-relaxed text-ink">
      {/* 思考块（FE-016）：节点状态 + 思考内容 + 检索策略统一容器，
          生成中默认展开、完成后收起一行，点击标题展开/收回 */}
      <ThinkingPanel
        lines={steps ?? []}
        subQueries={subQueries}
        streaming={streaming}
        thinkingMs={thinkingMs}
      />
      {message.webSearchNotice && (
        <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-[11px] text-accent">
          <Globe size={13} aria-hidden />
          {message.webSearchNotice.message}
        </div>
      )}
      <Markdown
        components={{
          // 给常见元素补充与整体风格一致的间距（Markdown 默认渲染无样式）
          p: ({ children }) => <p className="mb-2 whitespace-pre-wrap last:mb-0">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          h1: ({ children }) => <h1 className="mb-2 text-base font-semibold">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 text-base font-semibold">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 text-sm font-semibold">{children}</h3>,
          blockquote: ({ children }) => (
            <blockquote className="mb-2 border-l-2 border-line pl-3 text-ink-soft">{children}</blockquote>
          ),
          code: ({ children }) => <code className="rounded bg-elevated px-1 py-0.5 text-xs">{children}</code>,
        }}
      >
        {message.content}
      </Markdown>
      {/* 流式生成中的光标：强调色小块闪烁；系统开启"减少动态效果"时静止 */}
      {streaming && (
        <span className="ml-0.5 inline-block h-4 w-[3px] animate-pulse rounded-full bg-accent align-text-bottom motion-reduce:animate-none" />
      )}
      {/* 参考文档折叠面板（历史恢复的消息同样携带 sources，刷新后仍可查看） */}
      {localSources.length > 0 && <ReferencePanel sources={localSources} />}
      {webSources.length > 0 && <WebSearchPanel sources={webSources} />}
    </div>
  )
}
