// 侧边栏「知识库」列表：展示已上传文档的名称与处理状态。
// 状态点颜色对应真实语义（非装饰）：绿 = 可检索，黄 = 处理中，红 = 失败。
// 上传入口与删除交互属于 FE-008，在此文件基础上扩展。
import { useAppStore } from '../state/AppContext'
import type { DocumentStatus } from '../types'

/** 文档状态 → 状态点颜色（颜色只在此处定义一次，全站复用） */
const STATUS_DOT: Record<DocumentStatus, string> = {
  ready: 'bg-emerald-500',
  pending: 'bg-amber-500',
  processing: 'bg-amber-500',
  failed: 'bg-red-500',
}

export default function KnowledgeList() {
  const { documents } = useAppStore()

  // 空状态：还没有上传过文档
  if (documents.length === 0) {
    return <p className="px-2 py-8 text-center text-xs text-ink-faint">知识库还没有文档</p>
  }

  return (
    <ul className="space-y-0.5">
      {documents.map((doc) => (
        <li
          key={doc.id}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-ink-soft"
        >
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[doc.status]}`} />
          <span className="truncate" title={doc.filename}>
            {doc.filename}
          </span>
        </li>
      ))}
    </ul>
  )
}
