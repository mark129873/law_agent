// 侧边栏「知识库」视图的汇总卡片：只显示文档数量与处理状态概览。
// 为什么不罗列文件名（PRODUCT.md 交互决策）：文档明细（名称/大小/状态/删除）
// 已经完整展示在右侧管理页，窄侧边栏里长文件名只会被截断，属于重复信息。
import { useAppStore } from '../state/AppContext'

export default function KnowledgeSummary() {
  const { documents } = useAppStore()

  // 空状态：还没有上传过文档
  if (documents.length === 0) {
    return <p className="px-2 py-8 text-center text-xs text-ink-faint">知识库还没有文档</p>
  }

  // 状态汇总：只有存在对应状态的文档时才显示，避免无意义的"0 个处理中"
  const processingCount = documents.filter(
    (d) => d.status === 'pending' || d.status === 'processing',
  ).length
  const failedCount = documents.filter((d) => d.status === 'failed').length
  const statusHint =
    [processingCount > 0 ? `${processingCount} 个处理中` : '', failedCount > 0 ? `${failedCount} 个处理失败` : '']
      .filter(Boolean)
      .join('，')

  return (
    <div className="rounded-lg bg-app px-3 py-2.5">
      <p className="text-sm text-ink">共 {documents.length} 个文档</p>
      <p className="mt-1 text-xs leading-relaxed text-ink-faint">
        {statusHint && `${statusHint}。`}上传与删除请使用右侧管理页
      </p>
    </div>
  )
}
