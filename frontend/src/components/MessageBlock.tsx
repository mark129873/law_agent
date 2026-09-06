// 单条消息的展示：用户消息右侧气泡，助手消息左侧 Markdown 渲染（低干扰的 Codex 风格）。
// 助手回答用 Markdown 渲染的原因：模型输出普遍含 **加粗**、列表等格式，
// 按字面显示会出现星号噪声；react-markdown 默认不解析原始 HTML，无注入风险。
import { useState } from 'react'
import Markdown from 'react-markdown'
import { Books, CaretDown } from '@phosphor-icons/react'
import type { Message, ReferenceSource } from '../types'

interface MessageBlockProps {
  message: Message
  /** 该消息是否正在流式生成中（末尾显示闪烁光标） */
  streaming?: boolean
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

export default function MessageBlock({ message, streaming = false }: MessageBlockProps) {
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
  const hasSources = !streaming && !!message.sources && message.sources.length > 0

  // 助手消息：左侧平铺 + Markdown 渲染；流式光标放在内容之后
  return (
    <div className="text-sm leading-relaxed text-ink">
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
      {hasSources && <ReferencePanel sources={message.sources!} />}
    </div>
  )
}
