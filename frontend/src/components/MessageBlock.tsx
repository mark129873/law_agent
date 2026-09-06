// 单条消息的展示：用户消息右侧气泡，助手消息左侧平铺文本（低干扰的 Codex 风格）。
import type { Message } from '../types'

interface MessageBlockProps {
  message: Message
  /** 该消息是否正在流式生成中（末尾显示闪烁光标） */
  streaming?: boolean
}

export default function MessageBlock({ message, streaming = false }: MessageBlockProps) {
  // 用户消息：右侧气泡，限制最大宽度防止长问题占满整行
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl border border-line bg-elevated px-4 py-2.5 text-sm leading-relaxed text-ink">
          {message.content}
        </div>
      </div>
    )
  }

  // 助手消息：左侧平铺文本，不需要气泡包裹（回答通常较长，平铺更易读）
  return (
    <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
      {message.content}
      {/* 流式生成中的光标：强调色小块闪烁；系统开启"减少动态效果"时静止 */}
      {streaming && (
        <span className="ml-0.5 inline-block h-4 w-[3px] animate-pulse rounded-full bg-accent align-text-bottom motion-reduce:animate-none" />
      )}
    </div>
  )
}
