// 单条消息的展示：用户消息右侧气泡，助手消息左侧 Markdown 渲染（低干扰的 Codex 风格）。
// 助手回答用 Markdown 渲染的原因：模型输出普遍含 **加粗**、列表等格式，
// 按字面显示会出现星号噪声；react-markdown 默认不解析原始 HTML，无注入风险。
import Markdown from 'react-markdown'
import type { Message } from '../types'

interface MessageBlockProps {
  message: Message
  /** 该消息是否正在流式生成中（末尾显示闪烁光标） */
  streaming?: boolean
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
    </div>
  )
}
