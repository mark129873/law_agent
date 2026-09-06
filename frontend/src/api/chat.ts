// 流式问答 API：用 fetch 消费后端的 SSE 流（POST /api/chat/stream）。
// 为什么不用浏览器自带的 EventSource：它只支持 GET 请求，
// 而提交问题需要 POST JSON，所以必须用 fetch 手动读取响应字节流。
import type { ChatStreamEvent } from '../types'

/** 流式问答入参 */
interface ChatStreamParams {
  conversationId: string
  question: string
}

/** 流式问答回调：每收到一段增量、结束信号或错误就通知调用方 */
interface ChatStreamHandlers {
  onDelta: (content: string) => void
  onDone: (conversationId: string) => void
  onError: (message: string) => void
}

/**
 * 提交问题并持续消费流式回答。
 * 协议（docs/ARCHITECTURE.md 第 7 节）：响应体由若干条 "data: {json}\n\n" 组成，
 * json 的 type 字段区分 delta（增量文本）/ done（结束）/ error（出错）。
 */
export async function streamChat(params: ChatStreamParams, handlers: ChatStreamHandlers): Promise<void> {
  const res = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: params.conversationId, question: params.question }),
  })

  // 还没进入流就出错（例如会话不存在返回 404）：响应体是统一错误结构
  if (!res.ok || !res.body) {
    const data = (await res.json().catch(() => null)) as { message?: string } | null
    handlers.onError(data?.message ?? `请求失败（HTTP ${res.status}）`)
    return
  }

  // 逐块读取字节流 → 解码成文本 → 按 SSE 协议用空行拆分事件
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // 事件之间以空行分隔；最后一段可能不完整，留在 buffer 等下一块拼齐
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data:')) continue
      try {
        const event = JSON.parse(line.slice(5)) as ChatStreamEvent
        if (event.type === 'delta') handlers.onDelta(event.content)
        else if (event.type === 'done') handlers.onDone(event.conversation_id)
        else if (event.type === 'error') handlers.onError(event.message)
      } catch {
        // 个别残缺事件直接跳过，不影响后续内容
      }
    }
  }
}
