// 知识库管理主页面：文档上传（点击/拖拽）+ 文档列表（状态、大小、删除）。
// 交互反馈原则（PRODUCT.md）：上传有成功/失败反馈，文档有处理状态显示。
// 所有请求经 AppContext（内部走 api/documents），组件不直接 fetch。
import { useRef, useState } from 'react'
import { FileText, Trash, UploadSimple } from '@phosphor-icons/react'
import { useAppStore } from '../state/AppContext'
import { ALLOWED_EXTENSIONS, MAX_FILE_SIZE } from '../api/documents'
import type { DocumentStatus } from '../types'
import { formatDate, formatFileSize } from '../utils/format'

/** 文档状态 → 徽标文案与配色（只用主题 token，明暗主题都成立） */
const STATUS_PILL: Record<DocumentStatus, { text: string; cls: string }> = {
  ready: { text: '可检索', cls: 'bg-accent-soft text-accent' },
  pending: { text: '排队中', cls: 'bg-ink-soft/10 text-ink-soft' },
  processing: { text: '处理中', cls: 'bg-ink-soft/10 text-ink-soft' },
  failed: { text: '失败', cls: 'bg-danger-soft text-danger' },
}

/** 上传反馈条的类型 */
interface Feedback {
  ok: boolean
  message: string
}

export default function KnowledgePage() {
  const { documents, uploadDocument, removeDocument } = useAppStore()

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [feedback, setFeedback] = useState<Feedback | null>(null)
  /** 正在二次确认删除的文档 id */
  const [confirmingId, setConfirmingId] = useState<string | null>(null)

  /** 处理选择的文件：前端先做格式与大小预校验（即时反馈），再交给状态层上传 */
  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    for (const file of Array.from(files)) {
      const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        setFeedback({ ok: false, message: `《${file.name}》格式不支持，仅支持 PDF / TXT / MD` })
        continue
      }
      if (file.size > MAX_FILE_SIZE) {
        setFeedback({ ok: false, message: `《${file.name}》超过 20MB 上限，请压缩后再上传` })
        continue
      }
      setUploading(true)
      setFeedback(await uploadDocument(file))
      setUploading(false)
    }
    // 清空 input 的值：保证同一文件可以再次选择上传
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  /** 确认删除文档（后端级联删除向量数据） */
  async function handleDelete(id: string) {
    try {
      await removeDocument(id)
      setConfirmingId(null)
      setFeedback({ ok: true, message: '文档已删除，相关向量数据已同步清理' })
    } catch (error) {
      setFeedback({ ok: false, message: error instanceof Error ? error.message : '删除失败，请重试' })
    }
  }

  return (
    <div className="flex h-full flex-col bg-app">
      {/* 顶栏：标题 + 文档数量 */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-line px-6">
        <span className="text-sm font-medium text-ink">知识库管理</span>
        <span className="text-xs text-ink-faint">{documents.length} 个文档</span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-8">
          {/* 上传面板：点击选择 + 拖拽上传，两种方式共用同一套校验与反馈 */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') fileInputRef.current?.click()
            }}
            onDragOver={(event) => {
              event.preventDefault()
              setDragActive(true)
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragActive(false)
              void handleFiles(event.dataTransfer.files)
            }}
            className={`cursor-pointer rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
              dragActive ? 'border-accent bg-accent-soft' : 'border-line bg-elevated hover:border-accent'
            }`}
          >
            {/* accept 限制文件选择器的候选类型；多文件允许批量上传 */}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md"
              multiple
              className="hidden"
              onChange={(event) => void handleFiles(event.target.files)}
            />
            <UploadSimple size={28} className="mx-auto text-ink-faint" />
            <p className="mt-3 text-sm font-medium text-ink">
              {uploading ? '正在上传并处理…' : '点击选择或拖拽文件到此处上传'}
            </p>
            <p className="mt-1 text-xs text-ink-faint">支持 PDF / TXT / MD，单个文件不超过 20MB</p>
          </div>

          {/* 上传/删除反馈条 */}
          {feedback && (
            <div
              className={`flex items-center justify-between gap-3 rounded-lg px-4 py-2.5 text-sm ${
                feedback.ok ? 'bg-accent-soft text-accent' : 'bg-danger-soft text-danger'
              }`}
            >
              <span className="truncate">{feedback.message}</span>
              <button
                type="button"
                onClick={() => setFeedback(null)}
                className="shrink-0 text-xs underline-offset-2 hover:underline"
              >
                关闭
              </button>
            </div>
          )}

          {/* 文档列表：名称、大小、上传日期、处理状态、删除 */}
          {documents.length === 0 ? (
            <p className="py-10 text-center text-sm text-ink-faint">
              知识库还没有文档，上传一份法律文档后即可开始问答
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {documents.map((doc) => {
                const status = STATUS_PILL[doc.status]
                const confirming = confirmingId === doc.id
                return (
                  <li
                    key={doc.id}
                    className="flex items-center gap-3 rounded-xl border border-line bg-elevated px-4 py-3"
                  >
                    <FileText size={18} className="shrink-0 text-ink-faint" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink" title={doc.filename}>
                        {doc.filename}
                      </p>
                      <p className="mt-0.5 text-xs text-ink-faint">
                        {formatFileSize(doc.file_size)} · {formatDate(doc.created_at)}
                      </p>
                    </div>
                    <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs ${status.cls}`}>
                      {status.text}
                    </span>
                    {confirming ? (
                      // 二次确认态：删除 / 取消
                      <span className="flex shrink-0 items-center gap-1">
                        <span className="text-xs text-ink-soft">确认删除？</span>
                        <button
                          type="button"
                          onClick={() => void handleDelete(doc.id)}
                          className="rounded-md bg-red-600 px-2 py-0.5 text-xs text-white transition hover:bg-red-500 active:scale-[0.98]"
                        >
                          删除
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmingId(null)}
                          className="rounded-md px-1.5 py-0.5 text-xs text-ink-soft transition hover:text-ink"
                        >
                          取消
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        aria-label={`删除文档 ${doc.filename}`}
                        onClick={() => setConfirmingId(doc.id)}
                        className="shrink-0 rounded-md p-1.5 text-ink-faint transition hover:text-danger active:scale-[0.98]"
                      >
                        <Trash size={15} />
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
