// 首页占位组件：用于验证「路由可以访问 + Tailwind 样式生效」这两件基础能力。
// 刻意保持极简、不写业务逻辑：FE-003（应用 Shell）与 FE-004（对话页面）
// 会用真实布局替换这里的占位内容。
export default function HomePage() {
  return (
    // 下面全部使用 Tailwind 工具类：
    // min-h-screen 占满整屏高度；flex + items-center + justify-center 让内容水平垂直居中
    <div className="flex min-h-screen items-center justify-center bg-neutral-50">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-neutral-900">法律知识库助手</h1>
        <p className="mt-2 text-sm text-neutral-500">前端基础框架已就绪（FE-001）</p>
      </div>
    </div>
  )
}
