// 首页占位组件：FE-002 阶段用于验证「统一 API 层 + 全局状态」真实可用。
// 数据来源全部走规范路径：会话数据来自 AppContext（内部经 api/ 模块请求），
// 后端连通性来自 api/health.ts，组件里没有直接 fetch。
// FE-003 会用应用 Shell（侧边栏 + 主区域）替换这个占位页面。
import { useEffect, useState } from 'react'
import { useAppStore } from '../state/AppContext'
import { checkHealth } from '../api/health'

export default function HomePage() {
  const { conversations } = useAppStore()
  // 后端连通状态：null 检测中，true 可用，false 不可用
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  useEffect(() => {
    checkHealth()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false))
  }, [])

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-50 text-neutral-900">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">法律知识库助手</h1>
        <p className="mt-2 text-sm text-neutral-500">
          {backendOk === null && '正在连接后端…'}
          {backendOk === true && `后端已连接，读取到历史会话 ${conversations.length} 条`}
          {backendOk === false && '后端未连接，请先启动后端服务'}
        </p>
      </div>
    </div>
  )
}
